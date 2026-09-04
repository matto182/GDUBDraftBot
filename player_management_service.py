import time

from lobby_state_service import save_lobby_state
from service_runtime import players
from state import get_state


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

    if destination == "waiting":
        if user_id in state.waiting_room:
            return False, f"**{ign}** is already in the waiting room."

        if state.captain_draft:
            return False, "You cannot move an active Captain Draft player out of the lobby."

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

        state.waiting_room.remove(user_id)
        state.lobby.append(user_id)
        destination_label = "lobby"

    else:
        return False, "Unknown destination."

    save_lobby_state(guild_id)
    return True, f"Moved **{ign}** to the **{destination_label}**."


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

    waiting_index = state.waiting_room.index(waiting_user_id)

    state.lobby.remove(lobby_user_id)
    state.waiting_room.pop(waiting_index)
    state.lobby.append(waiting_user_id)
    state.waiting_room.insert(waiting_index, lobby_user_id)

    state.votes.pop(lobby_user_id, None)

    if lobby_user_id in state.captain_volunteers:
        state.captain_volunteers.remove(lobby_user_id)

    save_lobby_state(guild_id)

    return (
        True,
        f"Swapped **{lobby_player['ign']}** with **{waiting_player['ign']}**.",
    )
