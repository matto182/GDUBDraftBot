import random

from config import BACKLINE_ROLES, normalize_roles
from draft_constants import HISTORICAL_BACKLINE_COST, OFF_ROLE_COST, COMPOSITION_QUALITY_WEIGHT
from role_assignment import _build_role_cache, assign_best_team_roles
from balance_scoring import (
    _extreme_rule_is_feasible,
    _violates_extreme_stack,
    score_match,
    team_weight,
    effective_team_strength,
)

def _quick_team_penalty(team_ids, role_cache, players):
    """Cheap estimate used only to decide which splits deserve exact solving."""
    counts = {role: 0 for role in ("Frontline", "Midline", "Prot Monk", "Heal Monk", "8 Support")}

    for user_id in team_ids:
        for role in set(role_cache[user_id]):
            if role in counts:
                counts[role] += 1

    missing_backline = sum(
        1 for role in ("Prot Monk", "Heal Monk", "8 Support")
        if counts[role] == 0
    )

    historical_candidates = sum(
        1 for user_id in team_ids
        if players[user_id].get("has_played_backline", False)
        and not (set(role_cache[user_id]) & BACKLINE_ROLES)
    )
    historical_fills = min(missing_backline, historical_candidates)
    generic_backline_missing = missing_backline - historical_fills

    backline_penalty = (
        historical_fills * HISTORICAL_BACKLINE_COST
        + generic_backline_missing * OFF_ROLE_COST
    )

    formation_penalties = []
    for front_needed, mid_needed in ((1, 4), (2, 3), (3, 2)):
        formation_penalties.append(
            backline_penalty
            + max(0, front_needed - counts["Frontline"]) * OFF_ROLE_COST
            + max(0, mid_needed - counts["Midline"]) * OFF_ROLE_COST
        )

    return min(formation_penalties)


def _role_available_for_both_teams(lobby, role_cache, role):
    """Return True when at least two lobby players explicitly selected a role."""
    return sum(1 for user_id in lobby if role in role_cache[user_id]) >= 2


def _team_has_explicit_role(team_ids, role_cache, role):
    return any(role in role_cache[user_id] for user_id in team_ids)


def _split_has_required_coverage(
    split_key,
    role_cache,
    require_frontline,
    required_backline_roles,
):
    """Reject obviously bad splits before running the expensive exact solver."""
    for team_ids in split_key:
        if require_frontline and not _team_has_explicit_role(
            team_ids, role_cache, "Frontline"
        ):
            return False

        for role in required_backline_roles:
            if not _team_has_explicit_role(team_ids, role_cache, role):
                return False

    return True


def _generate_full_8v8_teams(players, lobby, player_weights=None):
    """Build two balanced teams while respecting role fit and hidden weights."""
    player_weights = player_weights or {}
    lobby = tuple(lobby)

    if len(lobby) != 16:
        raise ValueError("Random draft requires exactly 16 players.")

    role_cache = _build_role_cache(players, lobby)
    all_players = frozenset(lobby)
    seen_splits = set()
    quick_candidates = []
    enforce_extreme_rule = _extreme_rule_is_feasible(lobby, player_weights)

    # When the lobby has enough explicitly registered players to put one of
    # these roles on each team, reject splits that fail that basic structure.
    require_frontline = _role_available_for_both_teams(
        lobby, role_cache, "Frontline"
    )
    required_backline_roles = tuple(
        role
        for role in ("Prot Monk", "Heal Monk", "8 Support")
        if _role_available_for_both_teams(lobby, role_cache, role)
    )

    # The previous 1500/180 search was unnecessarily expensive for a
    # 16-player lobby. These values keep a useful candidate pool while
    # reducing quick split work by 80% and exact finalists by 83%.
    QUICK_SPLIT_SAMPLES = 300
    EXACT_FINALISTS = 30

    while len(seen_splits) < QUICK_SPLIT_SAMPLES:
        team_a_set = frozenset(random.sample(lobby, 8))
        team_b_set = all_players - team_a_set

        key_a = tuple(sorted(team_a_set))
        key_b = tuple(sorted(team_b_set))
        split_key = (key_a, key_b) if key_a < key_b else (key_b, key_a)

        if split_key in seen_splits:
            continue
        seen_splits.add(split_key)

        if not _split_has_required_coverage(
            split_key,
            role_cache,
            require_frontline,
            required_backline_roles,
        ):
            continue

        if enforce_extreme_rule and (
            _violates_extreme_stack(split_key[0], player_weights)
            or _violates_extreme_stack(split_key[1], player_weights)
        ):
            continue

        penalty_a = _quick_team_penalty(split_key[0], role_cache, players)
        penalty_b = _quick_team_penalty(split_key[1], role_cache, players)
        weight_a = sum(player_weights.get(uid, 0) for uid in split_key[0])
        weight_b = sum(player_weights.get(uid, 0) for uid in split_key[1])
        quick_score = (
            abs(weight_a - weight_b)
            + ((penalty_a + penalty_b) * COMPOSITION_QUALITY_WEIGHT)
            + (abs(penalty_a - penalty_b) * 0.05)
        )
        quick_candidates.append((quick_score, split_key))

    # If role overlap or unusual registrations make the strict filters produce
    # no candidates, fall back to unrestricted splits rather than failing a
    # live draft. Exact role costs will still strongly prefer proper backline
    # and at least one Frontline.
    if not quick_candidates:
        enforce_extreme_rule = False
        seen_splits.clear()
        while len(seen_splits) < QUICK_SPLIT_SAMPLES:
            team_a_set = frozenset(random.sample(lobby, 8))
            team_b_set = all_players - team_a_set
            key_a = tuple(sorted(team_a_set))
            key_b = tuple(sorted(team_b_set))
            split_key = (key_a, key_b) if key_a < key_b else (key_b, key_a)
            if split_key in seen_splits:
                continue
            seen_splits.add(split_key)
            penalty_a = _quick_team_penalty(split_key[0], role_cache, players)
            penalty_b = _quick_team_penalty(split_key[1], role_cache, players)
            weight_a = sum(player_weights.get(uid, 0) for uid in split_key[0])
            weight_b = sum(player_weights.get(uid, 0) for uid in split_key[1])
            quick_score = (
                abs(weight_a - weight_b)
                + ((penalty_a + penalty_b) * COMPOSITION_QUALITY_WEIGHT)
                + (abs(penalty_a - penalty_b) * 0.05)
            )
            quick_candidates.append((quick_score, split_key))

    quick_candidates.sort(key=lambda item: item[0])
    finalists = quick_candidates[:EXACT_FINALISTS]

    team_eval_cache = {}

    def evaluate_team(team_ids):
        key = tuple(sorted(team_ids))
        if key not in team_eval_cache:
            team_eval_cache[key] = assign_best_team_roles(
                players,
                key,
                role_cache=role_cache,
            )
        return team_eval_cache[key]

    best_result = None
    best_score = None

    for _quick_score, split_key in finalists:
        team_a_result = evaluate_team(split_key[0])
        team_b_result = evaluate_team(split_key[1])
        score = score_match(team_a_result, team_b_result, player_weights)

        if best_score is None or score < best_score:
            best_score = score
            best_result = (team_a_result, team_b_result)

    if best_result is None:
        raise ValueError("Could not generate a random draft from this lobby.")

    team_a_result, team_b_result = best_result
    formation = {
        "score": round(best_score, 2),
        "team_a": team_a_result["formation"],
        "team_b": team_b_result["formation"],
        "team_a_weight": team_weight(team_a_result, player_weights),
        "team_b_weight": team_weight(team_b_result, player_weights),
        "team_a_effective_strength": effective_team_strength(team_a_result, player_weights),
        "team_b_effective_strength": effective_team_strength(team_b_result, player_weights),
        "team_a_composition_penalty": team_a_result["score"],
        "team_b_composition_penalty": team_b_result["score"],
        "team_a_off_role_count": team_a_result["off_role_count"],
        "team_b_off_role_count": team_b_result["off_role_count"],
        "team_a_historical_backline_fills": team_a_result["historical_backline_fills"],
        "team_b_historical_backline_fills": team_b_result["historical_backline_fills"],
        "candidate_splits_checked": len(seen_splits),
        "exact_splits_checked": len(finalists),
        "unique_teams_evaluated": len(team_eval_cache),
        "extreme_stack_rule_enforced": enforce_extreme_rule,
    }
    return team_a_result["team"], team_b_result["team"], formation

MONK_ROLES = ("Prot Monk", "Heal Monk")


def _primary_display_role(players, user_id):
    roles = normalize_roles(players[user_id].get("roles", []))
    return roles[0] if roles else "Unassigned"


def _monk_roles_for_player(players, user_id):
    roles = normalize_roles(players[user_id].get("roles", []))
    return tuple(role for role in MONK_ROLES if role in roles)


def _can_cover_both_monk_roles(players, user_ids):
    if len(user_ids) < 2:
        return False

    first_roles = set(_monk_roles_for_player(players, user_ids[0]))
    second_roles = set(_monk_roles_for_player(players, user_ids[1]))

    return (
        ("Prot Monk" in first_roles and "Heal Monk" in second_roles)
        or ("Heal Monk" in first_roles and "Prot Monk" in second_roles)
    )


def _choose_monk_backlines(players, lobby):
    """Choose up to two monk-capable players per team, best effort."""
    monk_candidates = [
        user_id
        for user_id in lobby
        if _monk_roles_for_player(players, user_id)
    ]
    random.shuffle(monk_candidates)

    slot_teams = ("A", "A", "B", "B")
    best_score = None
    best_selection = {"A": [], "B": []}

    def score_selection(selection):
        count_a = len(selection["A"])
        count_b = len(selection["B"])
        filled = count_a + count_b
        spread = min(count_a, count_b)
        complete_pairs = int(_can_cover_both_monk_roles(players, selection["A"]))
        complete_pairs += int(_can_cover_both_monk_roles(players, selection["B"]))
        return filled, spread, complete_pairs

    def search(slot_index, used, selection):
        nonlocal best_score, best_selection

        if slot_index == len(slot_teams):
            candidate_score = score_selection(selection)
            if best_score is None or candidate_score > best_score:
                best_score = candidate_score
                best_selection = {
                    "A": list(selection["A"]),
                    "B": list(selection["B"]),
                }
            return

        team_name = slot_teams[slot_index]

        # Skipping a slot allows the search to find the best possible result
        # when fewer than four monk-capable players are available.
        search(slot_index + 1, used, selection)

        for user_id in monk_candidates:
            if user_id in used:
                continue

            selection[team_name].append(user_id)
            used.add(user_id)
            search(slot_index + 1, used, selection)
            used.remove(user_id)
            selection[team_name].pop()

    search(0, set(), {"A": [], "B": []})
    return best_selection


def _assign_monk_roles(players, user_ids):
    """Label selected monk players, preferring Prot + Heal when possible."""
    if not user_ids:
        return []

    if len(user_ids) == 1:
        roles = _monk_roles_for_player(players, user_ids[0])
        role = roles[0] if roles else _primary_display_role(players, user_ids[0])
        return [(user_ids[0], role)]

    first_id, second_id = user_ids[:2]
    first_roles = _monk_roles_for_player(players, first_id)
    second_roles = _monk_roles_for_player(players, second_id)

    options = [
        (first_role, second_role)
        for first_role in first_roles
        for second_role in second_roles
    ]

    if options:
        random.shuffle(options)
        first_role, second_role = max(
            options,
            key=lambda pair: int(set(pair) == set(MONK_ROLES)),
        )
        return [(first_id, first_role), (second_id, second_role)]

    return [
        (first_id, _primary_display_role(players, first_id)),
        (second_id, _primary_display_role(players, second_id)),
    ]


def _simple_formation(team_a, team_b, player_weights, mode_label):
    weight_a = sum(player_weights.get(user_id, 0) for user_id, _role in team_a)
    weight_b = sum(player_weights.get(user_id, 0) for user_id, _role in team_b)

    return {
        "score": 0,
        "team_a": mode_label,
        "team_b": mode_label,
        "team_a_weight": weight_a,
        "team_b_weight": weight_b,
        "team_a_effective_strength": weight_a,
        "team_b_effective_strength": weight_b,
        "team_a_composition_penalty": 0,
        "team_b_composition_penalty": 0,
        "team_a_off_role_count": 0,
        "team_b_off_role_count": 0,
        "team_a_historical_backline_fills": 0,
        "team_b_historical_backline_fills": 0,
        "candidate_splits_checked": 0,
        "exact_splits_checked": 0,
        "unique_teams_evaluated": 0,
        "extreme_stack_rule_enforced": False,
        "uses_full_optimizer": False,
    }


def _generate_monk_random_teams(players, lobby, player_weights):
    """For 6v6/7v7-sized drafts, seed monk backlines then randomize the rest."""
    lobby = tuple(lobby)
    team_a_target = (len(lobby) + 1) // 2
    team_b_target = len(lobby) // 2

    selected = _choose_monk_backlines(players, lobby)
    team_a = _assign_monk_roles(players, selected["A"])
    team_b = _assign_monk_roles(players, selected["B"])

    selected_ids = set(selected["A"]) | set(selected["B"])
    remaining_players = [user_id for user_id in lobby if user_id not in selected_ids]
    random.shuffle(remaining_players)

    open_slots = (
        ["A"] * max(0, team_a_target - len(team_a))
        + ["B"] * max(0, team_b_target - len(team_b))
    )
    random.shuffle(open_slots)

    for user_id, team_name in zip(remaining_players, open_slots):
        entry = (user_id, _primary_display_role(players, user_id))
        if team_name == "A":
            team_a.append(entry)
        else:
            team_b.append(entry)

    mode_label = "2 Monk Backline + Random Remainder"
    formation = _simple_formation(team_a, team_b, player_weights, mode_label)
    return team_a, team_b, formation


def _generate_fully_random_teams(players, lobby, player_weights):
    """For 5v5 and smaller formats, randomize the entire lobby."""
    shuffled = list(lobby)
    random.shuffle(shuffled)

    team_a_target = (len(shuffled) + 1) // 2
    team_a_ids = shuffled[:team_a_target]
    team_b_ids = shuffled[team_a_target:]

    team_a = [
        (user_id, _primary_display_role(players, user_id))
        for user_id in team_a_ids
    ]
    team_b = [
        (user_id, _primary_display_role(players, user_id))
        for user_id in team_b_ids
    ]

    mode_label = "Full Random"
    formation = _simple_formation(team_a, team_b, player_weights, mode_label)
    return team_a, team_b, formation


def generate_random_teams(players, lobby, player_weights=None):
    """Generate teams using the rules for the currently configured lobby size."""
    player_weights = player_weights or {}
    lobby = tuple(lobby)
    lobby_size = len(lobby)

    if lobby_size < 2 or lobby_size > 16:
        raise ValueError("Random draft requires between 2 and 16 players.")

    # Preserve the existing full 8v8 optimizer exactly for the standard lobby.
    if lobby_size == 16:
        team_a, team_b, formation = _generate_full_8v8_teams(
            players,
            lobby,
            player_weights,
        )
        formation["uses_full_optimizer"] = True
        return team_a, team_b, formation

    # Odd sizes inherit the rule of the smaller team: 15 -> 8v7, 13 -> 7v6,
    # 11 -> 6v5. Only formats where both teams have at least six players get
    # the best-effort two-monk backline seeding.
    if min(lobby_size // 2, (lobby_size + 1) // 2) >= 6:
        return _generate_monk_random_teams(players, lobby, player_weights)

    return _generate_fully_random_teams(players, lobby, player_weights)

