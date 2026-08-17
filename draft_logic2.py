import itertools
import random

from config import normalize_roles


# The bot may build either of these valid eight-player formations.
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
    "Frontline": 1,
    "Midline": 2,
    "Prot Monk": 3,
    "Heal Monk": 4,
    "8 Support": 5,
    "Captain": 0,
}

# Cost of assigning a player to each preference level.
PREFERENCE_COST = {
    0: 0,
    1: 20,
    2: 60,
    3: 120,
    4: 220,
}



def role_sort_key(assigned_role):
    return ROLE_ORDER.get(assigned_role, 99)



def role_priority_index(players, player_id, role):
    roles = normalize_roles(players[player_id].get("roles", []))
    return roles.index(role) if role in roles else 999



def assignment_cost(players, player_id, role):
    priority = role_priority_index(players, player_id, role)
    return PREFERENCE_COST.get(priority, 10000)



def _solve_formation(players, team_players, slots):
    """Find the lowest-preference-cost exact assignment for one formation."""
    best_assignment = None
    best_cost = None

    # Only eight players are involved, so a memoized bitmask search is fast and
    # deterministic while guaranteeing the best valid assignment.
    memo = {}

    def search(slot_index, used_mask):
        key = (slot_index, used_mask)
        if key in memo:
            return memo[key]

        if slot_index == len(slots):
            return 0, []

        role = slots[slot_index]
        local_best = None

        for index, user_id in enumerate(team_players):
            if used_mask & (1 << index):
                continue

            cost = assignment_cost(players, user_id, role)
            if cost >= 10000:
                continue

            tail = search(slot_index + 1, used_mask | (1 << index))
            if tail is None:
                continue

            total = cost + tail[0]
            candidate = (total, [(user_id, role)] + tail[1])

            if local_best is None or total < local_best[0]:
                local_best = candidate
            elif total == local_best[0] and random.random() < 0.5:
                local_best = candidate

        memo[key] = local_best
        return local_best

    result = search(0, 0)
    if result:
        best_cost, best_assignment = result

    return best_assignment, best_cost



def assign_best_team_roles(players, team_players):
    """Assign a team to whichever valid formation best fits its preferences."""
    best = None

    for formation_name, slots in TEAM_FORMATIONS:
        assignment, cost = _solve_formation(players, team_players, slots)
        if assignment is None:
            continue

        candidate = {
            "team": assignment,
            "score": cost,
            "formation": formation_name,
        }

        if best is None or candidate["score"] < best["score"]:
            best = candidate
        elif candidate["score"] == best["score"] and random.random() < 0.5:
            best = candidate

    return best



def optimize_team_roles(players, team):
    """Reassign a completed captain-drafted team to its best valid formation."""
    team_players = [user_id for user_id, _role in team]
    result = assign_best_team_roles(players, team_players)

    if result:
        return result["team"]

    # Captain drafts are player-selected and can create an impossible comp.
    # Keep everyone visible rather than crashing, using their first role.
    return [
        (user_id, normalize_roles(players[user_id].get("roles", []))[0])
        for user_id in team_players
        if normalize_roles(players[user_id].get("roles", []))
    ]



def team_weight(team_result, player_weights):
    return sum(player_weights.get(user_id, 0) for user_id, _role in team_result["team"])


def score_match(team_a_result, team_b_result, player_weights):
    preference_a = team_a_result["score"]
    preference_b = team_b_result["score"]
    preference_total = preference_a + preference_b

    weight_a = team_weight(team_a_result, player_weights)
    weight_b = team_weight(team_b_result, player_weights)

    # Role-preference cost acts like lost team strength: a team forced onto more
    # secondary roles is weaker. This lets a +200 player be offset by a harder
    # composition assignment instead of the weight being a constant penalty.
    effective_strength_a = weight_a - preference_a
    effective_strength_b = weight_b - preference_b
    strength_balance = abs(effective_strength_a - effective_strength_b)

    # First avoid poor role assignments overall, then make effective team
    # strength as equal as possible. One hidden point equals one role-cost point.
    return preference_total + strength_balance



def generate_random_teams(players, lobby, player_weights=None):
    player_weights = player_weights or {}
    best_result = None
    best_score = None
    attempts = 6000

    for _ in range(attempts):
        shuffled = lobby[:]
        random.shuffle(shuffled)

        team_a_result = assign_best_team_roles(players, shuffled[:8])
        team_b_result = assign_best_team_roles(players, shuffled[8:])

        # Reject the split outright if either team cannot form one of the two
        # approved compositions.
        if not team_a_result or not team_b_result:
            continue

        score = score_match(team_a_result, team_b_result, player_weights)

        if best_score is None or score < best_score:
            best_score = score
            best_result = (team_a_result, team_b_result)

            if best_score == 0:
                break

    if best_result is None:
        raise ValueError(
            "The lobby cannot be split into two valid teams. "
            "Each team needs Prot Monk, Heal Monk, 8 Support, and enough "
            "Frontline/Midline players for a 2/3 or 3/2 formation."
        )

    team_a_result, team_b_result = best_result

    formation = {
        "score": best_score,
        "team_a": team_a_result["formation"],
        "team_b": team_b_result["formation"],
        # Internal-only diagnostics. Do not expose these on public draft output.
        "team_a_weight": team_weight(team_a_result, player_weights),
        "team_b_weight": team_weight(team_b_result, player_weights),
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
            counts[role] += 1

    high = []
    medium = []
    low = []

    # Exactly two of each specialist backline role are required across two teams.
    for role in ["Prot Monk", "Heal Monk", "8 Support"]:
        if counts[role] < 2:
            high.append(f"{role} ({counts[role]}/2 required)")

    # Across two teams, valid formations require 4-6 frontliners and 4-6 mids.
    if counts["Frontline"] < 4:
        high.append(f"Frontline ({counts['Frontline']}/4 minimum)")
    elif counts["Frontline"] < 6:
        medium.append(f"Frontline ({counts['Frontline']}/6 supports either comp)")

    if counts["Midline"] < 4:
        high.append(f"Midline ({counts['Midline']}/4 minimum)")
    elif counts["Midline"] < 6:
        medium.append(f"Midline ({counts['Midline']}/6 supports either comp)")

    # At least ten combined front/mid-capable players are required after the six
    # specialist backline slots are filled.
    if counts["Frontline"] + counts["Midline"] < 10:
        high.append(
            f"Front/Mid coverage ({counts['Frontline'] + counts['Midline']}/10 minimum)"
        )

    return {
        "high": high,
        "medium": medium,
        "low": low,
        "counts": counts,
    }
