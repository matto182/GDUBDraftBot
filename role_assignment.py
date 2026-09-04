from functools import lru_cache

from config import BACKLINE_ROLES, normalize_roles
from draft_constants import (
    TEAM_FORMATIONS,
    ROLE_ORDER,
    PREFERENCE_COST,
    HISTORICAL_BACKLINE_COST,
    OFF_ROLE_COST,
)

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
    roles = _normalized_roles_for_player(players, player_id)
    return _cost_from_roles(
        roles,
        role,
        players[player_id].get("has_played_backline", False),
    )

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

def _cost_from_roles(roles, role, has_played_backline=False):
    priority = _priority_from_roles(roles, role)
    if priority != 999:
        return PREFERENCE_COST.get(priority, OFF_ROLE_COST)

    # Historical backline players are the preferred emergency autofill pool.
    # They are still more expensive than anyone who selected the role now.
    if role in BACKLINE_ROLES and has_played_backline:
        return HISTORICAL_BACKLINE_COST

    return OFF_ROLE_COST

def _solve_formation(players, team_players, slots, role_cache=None):
    """Return the cheapest assignment for a preferred 8-player formation."""
    team_players = tuple(team_players)
    if role_cache is None:
        role_cache = _build_role_cache(players, team_players)

    costs = tuple(
        tuple(
            _cost_from_roles(
                role_cache[user_id],
                slot_role,
                players[user_id].get("has_played_backline", False),
            )
            for user_id in team_players
        )
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
        priority = _priority_from_roles(roles, slot_role)
        historical_backline_fill = (
            priority == 999
            and slot_role in BACKLINE_ROLES
            and players[user_id].get("has_played_backline", False)
        )

        internal_assignment.append({
            "user_id": user_id,
            # Display the role the player was actually assigned to fill.
            "display_role": slot_role,
            "slot_role": slot_role,
            "off_role": priority == 999,
            "historical_backline_fill": historical_backline_fill,
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
            "historical_backline_fills": sum(
                1 for entry in internal_assignment if entry["historical_backline_fill"]
            ),
        }
        if best is None or candidate["score"] < best["score"]:
            best = candidate

    return best

def optimize_team_roles(players, team):
    team_players = [user_id for user_id, _role in team]
    if len(team_players) != 8:
        return team
    return assign_best_team_roles(players, team_players)["team"]
