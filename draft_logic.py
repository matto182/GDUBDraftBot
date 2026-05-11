import random

from config import (
    FRONTLINE_ROLES,
    MIDLINE_ROLES,
)


def has_role_type(players, user_id, role_set):
    return bool(set(players[user_id]["roles"]) & role_set)


def role_sort_key(assigned_role):
    order = {
        "Frontline": 1,
        "Lyssa/Flex Derv": 2,
        "Mesmer": 3,
        "Elementalist": 3,
        "Necromancer": 3,
        "Ranger": 3,
        "Prot Monk": 5,
        "Heal Monk": 6,
        "Support/Flag (8)": 7,
        "Captain": 0,
    }

    return order.get(assigned_role, 99)


def role_priority_index(players, player_id, role):
    player_roles = players[player_id]["roles"]

    if role in player_roles:
        return player_roles.index(role)

    return 999


def best_role_for_slot(players, player_id, desired_roles):
    player_roles = players[player_id]["roles"]

    for role in player_roles:
        if role in desired_roles:
            return role

    return None


def assign_fallback_role(players, player_id):
    return players[player_id]["roles"][0]


def optimize_team_roles(players, team):
    desired_slots = [
        ["Frontline"],
        ["Frontline"],
        ["Lyssa/Flex Derv"],
        MIDLINE_ROLES,
        MIDLINE_ROLES,
        ["Prot Monk"],
        ["Heal Monk"],
        ["Support/Flag (8)"],
    ]

    unassigned = [user_id for user_id, _ in team]
    optimized = []

    for desired_roles in desired_slots:
        candidates = []

        for user_id in unassigned:
            role = best_role_for_slot(players, user_id, desired_roles)

            if role:
                candidates.append((
                    user_id,
                    role,
                    role_priority_index(players, user_id, role)
                ))

        if candidates:
            best_priority = min(c[2] for c in candidates)
            best_candidates = [c for c in candidates if c[2] == best_priority]
            picked_id, assigned_role, _ = random.choice(best_candidates)

            optimized.append((picked_id, assigned_role))
            unassigned.remove(picked_id)

    for user_id in unassigned:
        optimized.append((user_id, assign_fallback_role(players, user_id)))

    return optimized


def count_assigned(team, role_set):
    return len([1 for _, role in team if role in role_set])


def get_priority_role_for_slot(players, player_id, desired_roles):
    player_roles = players[player_id]["roles"]

    for role in player_roles:
        if role in desired_roles:
            return role

    return None


def assign_team_roles_for_score(players, team_players):
    desired_slots = [
        ["Prot Monk"],
        ["Heal Monk"],
        ["Support/Flag (8)"],
        ["Frontline"],
        ["Frontline"],
        MIDLINE_ROLES,
        MIDLINE_ROLES,
        ["Lyssa/Flex Derv", "Frontline", "Mesmer", "Elementalist", "Necromancer", "Ranger"],
    ]

    unassigned = team_players[:]
    assigned = []

    for desired_roles in desired_slots:
        candidates = []

        for user_id in unassigned:
            role = get_priority_role_for_slot(players, user_id, desired_roles)

            if role:
                candidates.append((
                    user_id,
                    role,
                    role_priority_index(players, user_id, role)
                ))

        if candidates:
            best_priority = min(c[2] for c in candidates)
            best_candidates = [c for c in candidates if c[2] == best_priority]
            picked_id, assigned_role, _priority = random.choice(best_candidates)

            assigned.append((picked_id, assigned_role))
            unassigned.remove(picked_id)

    for user_id in unassigned:
        assigned.append((user_id, assign_fallback_role(players, user_id)))

    return assigned


def score_team(players, team):
    score = 0
    assigned_roles = [role for _user_id, role in team]

    # Backline is the highest priority.
    required_backline = ["Prot Monk", "Heal Monk", "Support/Flag (8)"]

    for role in required_backline:
        count = assigned_roles.count(role)

        if count == 0:
            score += 3000
        elif count > 1:
            score += 400 * (count - 1)

    # Frontline is second most important.
    frontline_count = assigned_roles.count("Frontline")

    if frontline_count == 0:
        score += 2500
    elif frontline_count == 1:
        score += 1200
    elif frontline_count == 2:
        score += 0
    elif frontline_count == 3:
        score += 50
    else:
        score += 300 * (frontline_count - 3)

    # Midline is important, but less important than backline/frontline.
    mid_count = len([r for r in assigned_roles if r in MIDLINE_ROLES])

    if mid_count == 0:
        score += 1200
    elif mid_count == 1:
        score += 400
    elif mid_count == 2:
        score += 0
    elif mid_count == 3:
        score += 75
    else:
        score += 250 * (mid_count - 3)

    # Flex is useful, but least important.
    flex_count = assigned_roles.count("Lyssa/Flex Derv")

    if flex_count == 0:
        score += 100
    elif flex_count == 1:
        score += 0
    else:
        score += 150 * (flex_count - 1)

    # Role preference penalty.
    for user_id, assigned_role in team:
        priority = role_priority_index(players, user_id, assigned_role)

        if priority == 0:
            score += 0
        elif priority == 1:
            score += 20
        elif priority == 2:
            score += 60
        elif priority == 3:
            score += 120
        elif priority == 4:
            score += 220
        else:
            score += 400

    return score


def score_match(players, team_a, team_b):
    score_a = score_team(players, team_a)
    score_b = score_team(players, team_b)

    balance_penalty = abs(score_a - score_b)

    return score_a + score_b + balance_penalty


def generate_random_teams(players, lobby):
    best_result = None
    best_score = None

    attempts = 1500

    for _ in range(attempts):
        shuffled = lobby[:]
        random.shuffle(shuffled)

        raw_team_a = shuffled[:8]
        raw_team_b = shuffled[8:]

        team_a = assign_team_roles_for_score(players, raw_team_a)
        team_b = assign_team_roles_for_score(players, raw_team_b)

        score = score_match(players, team_a, team_b)

        if best_score is None or score < best_score:
            best_score = score
            best_result = (team_a, team_b)

            if best_score <= 50:
                break

    team_a, team_b = best_result

    formation = {
        "front": "Smart balanced",
        "score": best_score
    }

    return team_a, team_b, formation


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

        assigned_role = players[picked_id]["roles"][0]

        if picker_id == self.captain_a:
            self.team_a.append((picked_id, assigned_role))
        else:
            self.team_b.append((picked_id, assigned_role))

        self.available.remove(picked_id)
        self.pick_index += 1

        return True, "Pick accepted."
def analyze_role_needs(players, lobby):
    counts = {
        "Prot Monk": 0,
        "Heal Monk": 0,
        "Support/Flag (8)": 0,
        "Frontline": 0,
        "Midline": 0,
        "Flex": 0,
    }

    for user_id in lobby:
        roles = players[user_id]["roles"]

        if "Prot Monk" in roles:
            counts["Prot Monk"] += 1

        if "Heal Monk" in roles:
            counts["Heal Monk"] += 1

        if "Support/Flag (8)" in roles:
            counts["Support/Flag (8)"] += 1

        if "Frontline" in roles:
            counts["Frontline"] += 1

        if any(role in roles for role in MIDLINE_ROLES):
            counts["Midline"] += 1

        if "Lyssa/Flex Derv" in roles:
            counts["Flex"] += 1

    high = []
    medium = []
    low = []

    if counts["Prot Monk"] < 2:
        high.append("Prot Monk")

    if counts["Heal Monk"] < 2:
        high.append("Heal Monk")

    if counts["Support/Flag (8)"] < 2:
        high.append("Support/Flag")

    if counts["Frontline"] < 4:
        medium.append(f"Frontline ({counts['Frontline']}/4 preferred)")

    if counts["Midline"] < 4:
        medium.append(f"Midline ({counts['Midline']}/4 preferred)")

    if counts["Flex"] < 2:
        low.append("Flex/Lyssa optional")

    return {
        "high": high,
        "medium": medium,
        "low": low,
        "counts": counts,
    }