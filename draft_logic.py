import random
from functools import lru_cache

from config import normalize_roles

TEAM_FORMATIONS = (
    ("2 Front / 3 Mid / 3 Back", [
        "Prot Monk", "Heal Monk", "8 Support",
        "Frontline", "Frontline",
        "Midline", "Midline", "Midline",
    ]),
    ("3 Front / 2 Mid / 3 Back", [
        "Prot Monk", "Heal Monk", "8 Support",
        "Frontline", "Frontline", "Frontline",
        "Midline", "Midline",
    ]),
)

ROLE_ORDER = {
    "Captain": 0,
    "Frontline": 1,
    "Midline": 2,
    "Prot Monk": 3,
    "Heal Monk": 4,
    "8 Support": 5,
    "Unassigned": 99,
}

PREFERENCE_COST = {0: 0, 1: 20, 2: 60, 3: 120, 4: 220}
OFF_ROLE_COST = 3000
COMPOSITION_QUALITY_WEIGHT = 0.10
RANDOM_SPLIT_ATTEMPTS = 500


def role_sort_key(assigned_role):
    return ROLE_ORDER.get(assigned_role, 99)


def _normalized_roles_for_player(players, player_id, role_cache=None):
    if role_cache is not None and player_id in role_cache:
        return role_cache[player_id]
    return tuple(normalize_roles(players[player_id].get("roles", [])))


def role_priority_index(players, player_id, role):
    roles = _normalized_roles_for_player(players, player_id)
    return roles.index(role) if role in roles else 999


def assignment_cost(players, player_id, role):
    priority = role_priority_index(players, player_id, role)
    if priority == 999:
        return OFF_ROLE_COST
    return PREFERENCE_COST.get(priority, OFF_ROLE_COST)


def _build_role_cache(players, player_ids):
    return {
        user_id: tuple(normalize_roles(players[user_id].get("roles", [])))
        for user_id in player_ids
    }


def _priority_from_roles(roles, role):
    try:
        return roles.index(role)
    except ValueError:
        return 999


def _cost_from_roles(roles, role):
    priority = _priority_from_roles(roles, role)
    if priority == 999:
        return OFF_ROLE_COST
    return PREFERENCE_COST.get(priority, OFF_ROLE_COST)


def _display_role_from_roles(roles, slot_role):
    if slot_role in roles:
        return slot_role
    if roles:
        return roles[0]
    return "Unassigned"


def _solve_formation(players, team_players, slots, role_cache=None):
    """Return the cheapest assignment for a preferred formation.

    Missing role coverage is always allowed and receives OFF_ROLE_COST. The
    solver uses a tiny bitmask DP and pre-normalized role data, avoiding the
    repeated role normalization that made the old draft path slow.
    """
    team_players = tuple(team_players)
    if role_cache is None:
        role_cache = _build_role_cache(players, team_players)

    # Precompute the 8x8 cost table once for this formation/team.
    costs = tuple(
        tuple(_cost_from_roles(role_cache[user_id], slot_role) for user_id in team_players)
        for slot_role in slots
    )

    @lru_cache(maxsize=None)
    def search(slot_index, used_mask):
        if slot_index == len(slots):
            return 0, ()

        best_cost = None
        best_indices = None

        for player_index in range(len(team_players)):
            if used_mask & (1 << player_index):
                continue

            tail_cost, tail_indices = search(
                slot_index + 1,
                used_mask | (1 << player_index),
            )
            total = costs[slot_index][player_index] + tail_cost

            if best_cost is None or total < best_cost:
                best_cost = total
                best_indices = (player_index,) + tail_indices

        return best_cost, best_indices

    total_cost, assignment_indices = search(0, 0)

    internal_assignment = []
    for slot_role, player_index in zip(slots, assignment_indices):
        user_id = team_players[player_index]
        roles = role_cache[user_id]
        internal_assignment.append({
            "user_id": user_id,
            "slot_role": slot_role,
            "display_role": _display_role_from_roles(roles, slot_role),
            "off_role": _priority_from_roles(roles, slot_role) == 999,
        })

    return total_cost, internal_assignment


def assign_best_team_roles(players, team_players, role_cache=None):
    """Assign any eight players to the least-bad preferred formation."""
    team_players = tuple(team_players)
    if len(team_players) != 8:
        raise ValueError("A draft team must contain exactly 8 players.")

    if role_cache is None:
        role_cache = _build_role_cache(players, team_players)

    best = None
    for formation_name, slots in TEAM_FORMATIONS:
        cost, internal_assignment = _solve_formation(
            players, team_players, slots, role_cache
        )
        public_team = [
            (entry["user_id"], entry["display_role"])
            for entry in internal_assignment
        ]
        candidate = {
            "team": public_team,
            "internal_assignment": internal_assignment,
            "score": cost,
            "formation": formation_name,
            "off_role_count": sum(1 for entry in internal_assignment if entry["off_role"]),
        }
        if best is None or candidate["score"] < best["score"]:
            best = candidate

    return best


def optimize_team_roles(players, team):
    team_players = [user_id for user_id, _role in team]
    if len(team_players) != 8:
        return team
    return assign_best_team_roles(players, team_players)["team"]


def team_weight(team_result, player_weights):
    return sum(player_weights.get(user_id, 0) for user_id, _role in team_result["team"])


def effective_team_strength(team_result, player_weights):
    return team_weight(team_result, player_weights) - team_result["score"]


def score_match(team_a_result, team_b_result, player_weights):
    strength_a = effective_team_strength(team_a_result, player_weights)
    strength_b = effective_team_strength(team_b_result, player_weights)
    strength_difference = abs(strength_a - strength_b)
    composition_total = team_a_result["score"] + team_b_result["score"]
    return strength_difference + (composition_total * COMPOSITION_QUALITY_WEIGHT)


def _quick_team_penalty(team_ids, role_cache):
    """Cheap estimate used only to decide which splits deserve exact solving."""
    counts = {role: 0 for role in ROLE_ORDER if role not in {"Captain", "Unassigned"}}
    primary_cost = 0

    for user_id in team_ids:
        roles = role_cache[user_id]
        for role in set(roles):
            if role in counts:
                counts[role] += 1

    # Backline is structurally unique: ideally one of each.
    back_missing = sum(
        1 for role in ("Prot Monk", "Heal Monk", "8 Support")
        if counts[role] == 0
    )

    formation_shortages = []
    for front_needed, mid_needed in ((2, 3), (3, 2)):
        shortage = (
            max(0, front_needed - counts["Frontline"])
            + max(0, mid_needed - counts["Midline"])
            + back_missing
        )
        formation_shortages.append(shortage)

    return min(formation_shortages) * OFF_ROLE_COST


def generate_random_teams(players, lobby, player_weights=None):
    """Build balanced teams using a fast two-stage search.

    Stage 1 samples many unique A/B splits and ranks them with a cheap role/MMR
    estimate. Stage 2 runs the exact role-assignment solver only on the best
    candidates. This checks a broader field while doing far fewer expensive
    formation solves.
    """
    player_weights = player_weights or {}
    lobby = tuple(lobby)

    if len(lobby) != 16:
        raise ValueError("Random draft requires exactly 16 players.")

    role_cache = _build_role_cache(players, lobby)
    all_players = frozenset(lobby)
    seen_splits = set()
    quick_candidates = []

    # Cheaply inspect a large set of unique splits.
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

        penalty_a = _quick_team_penalty(split_key[0], role_cache)
        penalty_b = _quick_team_penalty(split_key[1], role_cache)
        weight_a = sum(player_weights.get(uid, 0) for uid in split_key[0])
        weight_b = sum(player_weights.get(uid, 0) for uid in split_key[1])
        approximate_strength_a = weight_a - penalty_a
        approximate_strength_b = weight_b - penalty_b
        quick_score = (
            abs(approximate_strength_a - approximate_strength_b)
            + ((penalty_a + penalty_b) * COMPOSITION_QUALITY_WEIGHT)
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
            if best_score == 0:
                break

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
        "candidate_splits_checked": len(seen_splits),
        "exact_splits_checked": len(finalists),
        "unique_teams_evaluated": len(team_eval_cache),
    }
    return team_a_result["team"], team_b_result["team"], formation


class CaptainDraft:
    def __init__(self, lobby, captain_a, captain_b):
        self.captain_a = captain_a
        self.captain_b = captain_b
        self.team_a = [(captain_a, "Captain")]
        self.team_b = [(captain_b, "Captain")]
        self.available = [p for p in lobby if p not in [captain_a, captain_b]]
        self.pick_index = 0
        self.pick_order = self.build_pick_order()

    def build_pick_order(self):
        order = []
        pattern = [self.captain_a, self.captain_b, self.captain_b, self.captain_a]
        while len(order) < 14:
            order.extend(pattern)
        return order[:14]

    def current_picker(self):
        if self.pick_index >= len(self.pick_order):
            return None
        return self.pick_order[self.pick_index]

    def is_complete(self):
        return len(self.team_a) == 8 and len(self.team_b) == 8

    def pick_player(self, players, picker_id, picked_id):
        if picker_id != self.current_picker():
            return False, "It is not your pick."
        if picked_id not in self.available:
            return False, "That player is not available."
        roles = normalize_roles(players[picked_id].get("roles", []))
        assigned_role = roles[0] if roles else "Unassigned"
        if picker_id == self.captain_a:
            self.team_a.append((picked_id, assigned_role))
        else:
            self.team_b.append((picked_id, assigned_role))
        self.available.remove(picked_id)
        self.pick_index += 1
        return True, "Pick accepted."


def analyze_role_needs(players, lobby):
    counts = {role: 0 for role in [
        "Frontline", "Midline", "Prot Monk", "Heal Monk", "8 Support"
    ]}

    for user_id in lobby:
        for role in set(normalize_roles(players[user_id].get("roles", []))):
            if role in counts:
                counts[role] += 1

    high = []
    medium = []
    low = []

    for role in ["Prot Monk", "Heal Monk", "8 Support"]:
        if counts[role] < 2:
            high.append(f"{role} ({counts[role]}/2 preferred)")

    if counts["Frontline"] < 4:
        high.append(f"Frontline ({counts['Frontline']}/4 preferred)")
    elif counts["Frontline"] < 6:
        medium.append(f"Frontline ({counts['Frontline']}/6 ideal flexibility)")

    if counts["Midline"] < 4:
        high.append(f"Midline ({counts['Midline']}/4 preferred)")
    elif counts["Midline"] < 6:
        medium.append(f"Midline ({counts['Midline']}/6 ideal flexibility)")

    combined_front_mid = counts["Frontline"] + counts["Midline"]
    if combined_front_mid < 10:
        medium.append(f"Front/Mid coverage ({combined_front_mid}/10 preferred)")

    return {"high": high, "medium": medium, "low": low, "counts": counts}
