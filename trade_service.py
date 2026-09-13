from service_runtime import players
from state import get_state


def _find_player(team, user_id):
    for index, (team_user_id, assigned_role) in enumerate(team):
        if team_user_id == user_id:
            return index, assigned_role

    return None, None


def trade_players(guild_id, player_1_id, player_2_id):
    """Swap two drafted players between Team A and Team B.

    Each player keeps their currently assigned role. Only the live draft state
    is changed; historical draft records remain as originally generated.
    """
    state = get_state(guild_id)

    if player_1_id == player_2_id:
        return False, "Choose two different players."

    team_a = getattr(state, "final_team_a", [])
    team_b = getattr(state, "final_team_b", [])

    if not team_a or not team_b or not getattr(state, "draft_result", None):
        return False, "There is no completed draft to trade players in."

    if getattr(state, "captain_draft", None):
        return False, "Finish the active Captain Draft before trading players."

    p1_a_index, p1_a_role = _find_player(team_a, player_1_id)
    p1_b_index, p1_b_role = _find_player(team_b, player_1_id)

    p2_a_index, p2_a_role = _find_player(team_a, player_2_id)
    p2_b_index, p2_b_role = _find_player(team_b, player_2_id)

    player_1_found = p1_a_index is not None or p1_b_index is not None
    player_2_found = p2_a_index is not None or p2_b_index is not None

    if not player_1_found:
        return False, "The first selected player is not in the current draft."

    if not player_2_found:
        return False, "The second selected player is not in the current draft."

    if p1_a_index is not None and p2_a_index is not None:
        return False, "Both selected players are already on Team A."

    if p1_b_index is not None and p2_b_index is not None:
        return False, "Both selected players are already on Team B."

    # Normalize the swap so player_a_id is the player currently on Team A and
    # player_b_id is the player currently on Team B.
    if p1_a_index is not None:
        player_a_id = player_1_id
        player_a_index = p1_a_index
        player_a_role = p1_a_role

        player_b_id = player_2_id
        player_b_index = p2_b_index
        player_b_role = p2_b_role
    else:
        player_a_id = player_2_id
        player_a_index = p2_a_index
        player_a_role = p2_a_role

        player_b_id = player_1_id
        player_b_index = p1_b_index
        player_b_role = p1_b_role

    # Each player keeps their own assigned role when moving teams.
    state.final_team_a[player_a_index] = (player_b_id, player_b_role)
    state.final_team_b[player_b_index] = (player_a_id, player_a_role)

    player_a_ign = players.get(player_a_id, {}).get("ign", str(player_a_id))
    player_b_ign = players.get(player_b_id, {}).get("ign", str(player_b_id))

    return (
        True,
        "**Trade completed**\n"
        f"**{player_a_ign}** — {player_a_role}: Team A → Team B\n"
        f"**{player_b_ign}** — {player_b_role}: Team B → Team A"
    )
