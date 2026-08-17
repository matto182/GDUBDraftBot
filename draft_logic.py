import random

from config import normalize_roles


TEAM_FORMATIONS = (
    (
        "2 Front / 3 Mid / 3 Back",
        [
            "Prot Monk",
            "Heal Monk",
            "8 Support",
            "Frontline",
            "Frontline",
            "Midline",
            "Midline",
            "Midline",
        ],
    ),
    (
        "3 Front / 2 Mid / 3 Back",
        [
            "Prot Monk",
            "Heal Monk",
            "8 Support",
            "Frontline",
            "Frontline",
            "Frontline",
            "Midline",
            "Midline",
        ],
    ),
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

PREFERENCE_COST = {
    0: 0,
    1: 20,
    2: 60,
    3: 120,
    4: 220,
}

OFF_ROLE_COST = 3000
COMPOSITION_QUALITY_WEIGHT = 0.10


def role_sort_key(assigned_role):
    return ROLE_ORDER.get(assigned_role, 99)


def role_priority_index(players, player_id, role):
    roles = normalize_roles(players[player_id].get("roles", []))
    return roles.index(role) if role in roles else 999


def assignment_cost(players, player_id, slot_role):
    priority = role_priority_index(players, player_id, slot_role)

    if priority == 999:
        return OFF_ROLE_COST

    return PREFERENCE_COST.get(priority, OFF_ROLE_COST)


def display_role_for_slot(players, player_id, slot_role):
    roles = normalize_roles(players[player_id].get("roles", []))

    if slot_role in roles:
        return slot_role

    if roles:
        return roles[0]

    return "Unassigned"


def _solve_formation(players, team_players, slots):
    """
    Find the lowest-cost assignment of eight players to a preferred formation.

    Missing role coverage is allowed. A player covering an unsupported slot
    receives OFF_ROLE_COST rather than making the formation invalid.
    """
    memo = {}

    def search(slot_index, used_mask):
        key = (slot_index, used_mask)

        if key in memo:
            return memo[key]

        if slot_index == len(slots):
            return 0, []

        slot_role = slots[slot_index]
        local_best = None

        for index, user_id in enumerate(team_players):
            if used_mask & (1 << index):
                continue

            cost = assignment_cost(players, user_id, slot_role)

            tail = search(
                slot_index + 1,
                used_mask | (1 << index),
            )

            if tail is None:
                continue

            total_cost = cost + tail[0]

            entry = {
                "user_id": user_id,
                "slot_role": slot_role,
                "display_role": display_role_for_slot(
                    players,
                    user_id,
                    slot_role,
                ),
                "off_role": role_priority_index(
                    players,
                    user_id,
                    slot_role,
                ) == 999,
            }

            candidate = (
                total_cost,
                [entry] + tail[1],
            )

            if local_best is None or total_cost < local_best[0]:
                local_best = candidate
            elif total_cost == local_best[0] and random.random() < 0.5:
                local_best = candidate

        memo[key] = local_best
        return local_best

    return search(0, 0)


def assign_best_team_roles(players, team_players):
    """
    Assign a team to whichever preferred formation produces the lowest penalty.

    This always returns a result for any eight players.
    """
    if len(team_players) != 8:
        raise ValueError("A draft team must contain exactly 8 players.")

    best = None

    for formation_name, slots in TEAM_FORMATIONS:
        result = _solve_formation(players, team_players, slots)

        if result is None:
            continue

        cost, internal_assignment = result

        public_team = [
            (
                entry["user_id"],
                entry["display_role"],
            )
            for entry in internal_assignment
        ]

        off_role_count = sum(
            1
            for entry in internal_assignment
            if entry["off_role"]
        )

        candidate = {
            "team": public_team,
            "internal_assignment": internal_assignment,
            "score": cost,
            "formation": formation_name,
            "off_role_count": off_role_count,
        }

        if best is None or candidate["score"] < best["score"]:
            best = candidate
        elif candidate["score"] == best["score"] and random.random() < 0.5:
            best = candidate

    if best is None:
        fallback_team = []

        for user_id in team_players:
            roles = normalize_roles(players[user_id].get("roles", []))
            fallback_team.append(
                (
                    user_id,
                    roles[0] if roles else "Unassigned",
                )
            )

        return {
            "team": fallback_team,
            "internal_assignment": [],
            "score": OFF_ROLE_COST * 8,
            "formation": "Fallback",
            "off_role_count": 8,
        }

    return best


def optimize_team_roles(players, team):
    team_players = [
        user_id
        for user_id, _role in team
    ]

    if len(team_players) != 8:
        return team

    result = assign_best_team_roles(
        players,
        team_players,
    )

    return result["team"]


def team_weight(team_result, player_weights):
    return sum(
        player_weights.get(user_id, 0)
        for user_id, _role in team_result["team"]
    )


def effective_team_strength(team_result, player_weights):
    hidden_weight = team_weight(
        team_result,
        player_weights,
    )

    composition_penalty = team_result["score"]

    return hidden_weight - composition_penalty


def score_match(team_a_result, team_b_result, player_weights):
    strength_a = effective_team_strength(
        team_a_result,
        player_weights,
    )

    strength_b = effective_team_strength(
        team_b_result,
        player_weights,
    )

    strength_difference = abs(
        strength_a - strength_b
    )

    composition_total = (
        team_a_result["score"]
        + team_b_result["score"]
    )

    return (
        strength_difference
        + (composition_total * COMPOSITION_QUALITY_WEIGHT)
    )


def generate_random_teams(players, lobby, player_weights=None):
    """
    Always split a full 16-player lobby into two teams of 8.

    Role formations and hidden weights are optimization signals only.
    No role composition can block the draft.
    """
    player_weights = player_weights or {}

    if len(lobby) != 16:
        raise ValueError(
            "Random draft requires exactly 16 players."
        )

    best_result = None
    best_score = None

    attempts = 500

    for _ in range(attempts):
        shuffled = lobby[:]
        random.shuffle(shuffled)

        raw_team_a = shuffled[:8]
        raw_team_b = shuffled[8:]

        team_a_result = assign_best_team_roles(
            players,
            raw_team_a,
        )

        team_b_result = assign_best_team_roles(
            players,
            raw_team_b,
        )

        score = score_match(
            team_a_result,
            team_b_result,
            player_weights,
        )

        if best_score is None or score < best_score:
            best_score = score
            best_result = (
                team_a_result,
                team_b_result,
            )

            if best_score == 0:
                break

    team_a_result, team_b_result = best_result

    formation = {
        "score": round(best_score, 2),
        "team_a": team_a_result["formation"],
        "team_b": team_b_result["formation"],

        # Hidden/internal diagnostics only.
        "team_a_weight": team_weight(
            team_a_result,
            player_weights,
        ),
        "team_b_weight": team_weight(
            team_b_result,
            player_weights,
        ),
        "team_a_effective_strength": effective_team_strength(
            team_a_result,
            player_weights,
        ),
        "team_b_effective_strength": effective_team_strength(
            team_b_result,
            player_weights,
        ),
        "team_a_composition_penalty": team_a_result["score"],
        "team_b_composition_penalty": team_b_result["score"],
        "team_a_off_role_count": team_a_result["off_role_count"],
        "team_b_off_role_count": team_b_result["off_role_count"],
    }

    return (
        team_a_result["team"],
        team_b_result["team"],
        formation,
    )


class CaptainDraft:
    def __init__(self, lobby, captain_a, captain_b):
        self.captain_a = captain_a
        self.captain_b = captain_b

        self.team_a = [
            (captain_a, "Captain")
        ]

        self.team_b = [
            (captain_b, "Captain")
        ]

        self.available = [
            player_id
            for player_id in lobby
            if player_id not in [
                captain_a,
                captain_b,
            ]
        ]

        self.pick_index = 0
        self.pick_order = self.build_pick_order()

    def build_pick_order(self):
        order = []

        pattern = [
            self.captain_a,
            self.captain_b,
            self.captain_b,
            self.captain_a,
        ]

        while len(order) < 14:
            order.extend(pattern)

        return order[:14]

    def current_picker(self):
        if self.pick_index >= len(self.pick_order):
            return None

        return self.pick_order[
            self.pick_index
        ]

    def is_complete(self):
        return (
            len(self.team_a) == 8
            and len(self.team_b) == 8
        )

    def pick_player(
        self,
        players,
        picker_id,
        picked_id,
    ):
        if picker_id != self.current_picker():
            return False, "It is not your pick."

        if picked_id not in self.available:
            return False, "That player is not available."

        roles = normalize_roles(
            players[picked_id].get(
                "roles",
                [],
            )
        )

        assigned_role = (
            roles[0]
            if roles
            else "Unassigned"
        )

        if picker_id == self.captain_a:
            self.team_a.append(
                (
                    picked_id,
                    assigned_role,
                )
            )
        else:
            self.team_b.append(
                (
                    picked_id,
                    assigned_role,
                )
            )

        self.available.remove(
            picked_id
        )

        self.pick_index += 1

        return True, "Pick accepted."


def analyze_role_needs(players, lobby):
    """
    Report preferred coverage only.

    These values are informational and never prevent a draft from starting.
    """
    counts = {
        role: 0
        for role in [
            "Frontline",
            "Midline",
            "Prot Monk",
            "Heal Monk",
            "8 Support",
        ]
    }

    for user_id in lobby:
        roles = set(
            normalize_roles(
                players[user_id].get(
                    "roles",
                    [],
                )
            )
        )

        for role in roles:
            if role in counts:
                counts[role] += 1

    high = []
    medium = []
    low = []

    for role in [
        "Prot Monk",
        "Heal Monk",
        "8 Support",
    ]:
        if counts[role] < 2:
            high.append(
                f"{role} ({counts[role]}/2 preferred)"
            )

    if counts["Frontline"] < 4:
        high.append(
            f"Frontline ({counts['Frontline']}/4 preferred)"
        )
    elif counts["Frontline"] < 6:
        medium.append(
            f"Frontline ({counts['Frontline']}/6 ideal flexibility)"
        )

    if counts["Midline"] < 4:
        high.append(
            f"Midline ({counts['Midline']}/4 preferred)"
        )
    elif counts["Midline"] < 6:
        medium.append(
            f"Midline ({counts['Midline']}/6 ideal flexibility)"
        )

    combined_front_mid = (
        counts["Frontline"]
        + counts["Midline"]
    )

    if combined_front_mid < 10:
        medium.append(
            f"Front/Mid coverage ({combined_front_mid}/10 preferred)"
        )

    return {
        "high": high,
        "medium": medium,
        "low": low,
        "counts": counts,
    }
