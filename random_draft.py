import random

from config import BACKLINE_ROLES
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
    for front_needed, mid_needed in ((2, 3), (3, 2)):
        formation_penalties.append(
            backline_penalty
            + max(0, front_needed - counts["Frontline"]) * OFF_ROLE_COST
            + max(0, mid_needed - counts["Midline"]) * OFF_ROLE_COST
        )

    return min(formation_penalties)

def generate_random_teams(players, lobby, player_weights=None):
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

    QUICK_SPLIT_SAMPLES = 1500
    EXACT_FINALISTS = 180

    while len(seen_splits) < QUICK_SPLIT_SAMPLES:
        team_a_set = frozenset(random.sample(lobby, 8))
        team_b_set = all_players - team_a_set

        key_a = tuple(sorted(team_a_set))
        key_b = tuple(sorted(team_b_set))
        split_key = (key_a, key_b) if key_a < key_b else (key_b, key_a)

        if split_key in seen_splits:
            continue
        seen_splits.add(split_key)

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

    # A full lobby with feasible extreme rules should always yield candidates,
    # but fall back to unrestricted splits rather than failing a live draft.
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
