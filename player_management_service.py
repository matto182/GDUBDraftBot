import time

from lobby_state_service import save_lobby_state
from service_runtime import players
from state import get_state


def _replace_drafted_player(state, outgoing_user_id, incoming_user_id):
    """Replace one drafted player in-place while preserving team and role."""
    for team_label, attr_name in (
        ("Team A", "final_team_a"),
        ("Team B", "final_team_b"),
    ):
        team = getattr(state, attr_name, [])

        for index, (user_id, assigned_role) in enumerate(team):
            if user_id != outgoing_user_id:
                continue

            team[index] = (incoming_user_id, assigned_role)
            return team_label, assigned_role

    return None, None


def _find_missing_drafted_player(state):
    """Find a drafted player who is no longer present in the active lobby."""
    lobby_ids = set(state.lobby)

    for team in (
        getattr(state, "final_team_a", []),
        getattr(state, "final_team_b", []),
    ):
        for user_id, _assigned_role in team:
            if user_id not in lobby_ids:
                return user_id

    return None


def add_player(guild_id, user_id, location):
    state = get_state(guild_id)
    player = players.get(user_id)

    if not player or not player.get("ign"):
        return False, "That registered player could not be found."

    if user_id in state.lobby or user_id in state.waiting_room:
        return False, f"**{player['ign']}** is already signed up."

    if location == "lobby":
        if state.captain_draft:
            return False, "You cannot add someone to the lobby during an active Captain Draft."

        if len(state.lobby) >= 16:
            return False, "The lobby is full. Add them to the waiting room or use `/swapplayers`."

        state.lobby.append(user_id)
        destination = "lobby"
    elif location == "waiting":
        state.waiting_room.append(user_id)
        destination = "waiting room"
    else:
        return False, "Unknown destination."

    state.last_signup_time = time.time()
    save_lobby_state(guild_id)

    return True, f"Added **{player['ign']}** to the **{destination}**."


def move_player(guild_id, user_id, destination):
    state = get_state(guild_id)
    player = players.get(user_id)
    ign = player.get("ign") if player else None

    if not ign:
        return False, "That registered player could not be found."

    if user_id not in state.lobby and user_id not in state.waiting_room:
        return False, f"**{ign}** is not currently signed up."

    completed_random_draft = (
        bool(getattr(state, "draft_result", None))
        and not getattr(state, "captain_draft", None)
        and bool(getattr(state, "final_team_a", []))
        and bool(getattr(state, "final_team_b", []))
    )

    if destination == "waiting":
        if user_id in state.waiting_room:
            return False, f"**{ign}** is already in the waiting room."

        if state.captain_draft:
            return False, "You cannot move an active Captain Draft player out of the lobby."

        if completed_random_draft:
            # During a completed Random Draft, moving a drafted lobby player
            # out is treated as a straight substitution with the next person
            # in the waiting room. The replacement inherits the exact same
            # team and assigned role.
            if not state.waiting_room:
                return (
                    False,
                    "There is nobody in the waiting room to replace that drafted player.",
                )

            team_label = None
            assigned_role = None

            for team in (state.final_team_a, state.final_team_b):
                for drafted_user_id, role in team:
                    if drafted_user_id == user_id:
                        assigned_role = role
                        break
                if assigned_role is not None:
                    break

            if assigned_role is None:
                return False, "That lobby player could not be found in the drafted teams."

            replacement_id = state.waiting_room[0]
            replacement = players.get(replacement_id)
            replacement_ign = (
                replacement.get("ign")
                if replacement and replacement.get("ign")
                else str(replacement_id)
            )

            lobby_index = state.lobby.index(user_id)

            # Preserve both the lobby slot and the waiting-room queue slot.
            state.lobby[lobby_index] = replacement_id
            state.waiting_room[0] = user_id

            team_label, assigned_role = _replace_drafted_player(
                state,
                user_id,
                replacement_id,
            )

            state.votes.pop(user_id, None)

            if user_id in state.captain_volunteers:
                state.captain_volunteers.remove(user_id)

            save_lobby_state(guild_id)

            return (
                True,
                f"Moved **{ign}** to the **waiting room**. "
                f"**{replacement_ign}** replaced them on **{team_label}** "
                f"as **{assigned_role}**.",
            )

        state.lobby.remove(user_id)
        state.waiting_room.append(user_id)
        state.votes.pop(user_id, None)

        if user_id in state.captain_volunteers:
            state.captain_volunteers.remove(user_id)

        destination_label = "waiting room"

    elif destination == "lobby":
        if user_id in state.lobby:
            return False, f"**{ign}** is already in the lobby."

        if state.captain_draft:
            return False, "You cannot add a player to the lobby during an active Captain Draft."

        if len(state.lobby) >= 16:
            return False, "The lobby is full. Use `/swapplayers` to exchange them with a lobby player."

        missing_drafted_user_id = None
        if completed_random_draft:
            missing_drafted_user_id = _find_missing_drafted_player(state)

        state.waiting_room.remove(user_id)
        state.lobby.append(user_id)
        destination_label = "lobby"

        # This covers a draft that already has an open lobby slot because a
        # drafted player was removed by some other admin action. The incoming
        # player inherits that missing player's exact drafted slot.
        replacement_note = ""
        if completed_random_draft and missing_drafted_user_id is not None:
            team_label, assigned_role = _replace_drafted_player(
                state,
                missing_drafted_user_id,
                user_id,
            )

            if team_label:
                replacement_note = (
                    f" They replaced the open drafted slot on **{team_label}** "
                    f"as **{assigned_role}**."
                )

    else:
        return False, "Unknown destination."

    save_lobby_state(guild_id)

    message = f"Moved **{ign}** to the **{destination_label}**."
    if destination == "lobby":
        message += replacement_note

    return True, message


def move_player_to_other_area(guild_id, user_id):
    state = get_state(guild_id)

    if user_id in state.lobby:
        return move_player(guild_id, user_id, "waiting")

    if user_id in state.waiting_room:
        return move_player(guild_id, user_id, "lobby")

    player = players.get(user_id)
    ign = player.get("ign") if player else str(user_id)
    return False, f"**{ign}** is not currently signed up."


def set_queue_position(guild_id, user_id, position):
    state = get_state(guild_id)
    player = players.get(user_id)
    ign = player.get("ign") if player else None

    if not ign:
        return False, "That registered player could not be found."

    if user_id not in state.waiting_room:
        return False, f"**{ign}** is not currently in the waiting room."

    if position < 1 or position > len(state.waiting_room):
        return (
            False,
            f"Position must be between **1** and **{len(state.waiting_room)}**.",
        )

    state.waiting_room.remove(user_id)
    state.waiting_room.insert(position - 1, user_id)
    save_lobby_state(guild_id)

    return True, f"Moved **{ign}** to waiting-room position **#{position}**."


def swap_players(guild_id, lobby_user_id, waiting_user_id):
    state = get_state(guild_id)

    lobby_player = players.get(lobby_user_id)
    waiting_player = players.get(waiting_user_id)

    if not lobby_player or not lobby_player.get("ign"):
        return False, "The selected lobby player could not be found."

    if not waiting_player or not waiting_player.get("ign"):
        return False, "The selected waiting-room player could not be found."

    if state.captain_draft:
        return False, "You cannot swap active Captain Draft players."

    if lobby_user_id not in state.lobby:
        return False, f"**{lobby_player['ign']}** is not currently in the lobby."

    if waiting_user_id not in state.waiting_room:
        return False, f"**{waiting_player['ign']}** is not currently in the waiting room."

    lobby_index = state.lobby.index(lobby_user_id)
    waiting_index = state.waiting_room.index(waiting_user_id)

    completed_random_draft = (
        bool(getattr(state, "draft_result", None))
        and bool(getattr(state, "final_team_a", []))
        and bool(getattr(state, "final_team_b", []))
    )

    if completed_random_draft:
        team_label, assigned_role = _replace_drafted_player(
            state,
            lobby_user_id,
            waiting_user_id,
        )

        if team_label is None:
            return False, "That lobby player could not be found in the drafted teams."
    else:
        team_label = None
        assigned_role = None

    # Preserve each player's exact lobby / waiting-room position.
    state.lobby[lobby_index] = waiting_user_id
    state.waiting_room[waiting_index] = lobby_user_id

    state.votes.pop(lobby_user_id, None)

    if lobby_user_id in state.captain_volunteers:
        state.captain_volunteers.remove(lobby_user_id)

    save_lobby_state(guild_id)

    if team_label:
        return (
            True,
            f"Swapped **{lobby_player['ign']}** with **{waiting_player['ign']}**. "
            f"**{waiting_player['ign']}** took their spot on **{team_label}** "
            f"as **{assigned_role}**.",
        )

    return (
        True,
        f"Swapped **{lobby_player['ign']}** with **{waiting_player['ign']}**.",
    )

