from state import get_state
from database import (
    get_lobby_ban,
    load_lobby_state_from_db,
    save_lobby_state_to_db,
)
from service_runtime import load_players, players


def enforce_lobby_size(guild_id):
    """Keep the active lobby at or below the configured runtime size."""
    state = get_state(guild_id)

    if len(state.lobby) <= state.lobby_size:
        return []

    overflow = state.lobby[state.lobby_size:]
    del state.lobby[state.lobby_size:]

    # Players displaced by a size reduction keep priority over people who
    # were already waiting, and keep their original relative order.
    existing_waiters = set(state.waiting_room)
    displaced = [user_id for user_id in overflow if user_id not in existing_waiters]
    state.waiting_room[:0] = displaced

    for user_id in overflow:
        state.votes.pop(user_id, None)
        if user_id in state.captain_volunteers:
            state.captain_volunteers.remove(user_id)

    return overflow


def save_lobby_state(guild_id):
    state = get_state(guild_id)
    enforce_lobby_size(guild_id)

    save_lobby_state_to_db(
        guild_id,
        state.lobby,
        state.waiting_room,
        state.last_signup_time
    )


def load_lobby_state(guild_id):
    load_players()

    state = get_state(guild_id)

    state.last_signup_time = load_lobby_state_from_db(
        guild_id,
        players,
        state.lobby,
        state.waiting_room
    )

    # Runtime lobby size is intentionally not stored in the database. If a
    # smaller size is active, never allow a reload to overfill the lobby.
    enforce_lobby_size(guild_id)


def fill_lobby_from_waiting_room(guild_id):
    state = get_state(guild_id)
    moved = []

    while len(state.lobby) < state.lobby_size and state.waiting_room:
        next_player = state.waiting_room.pop(0)

        if get_lobby_ban(guild_id, next_player):
            continue

        if next_player not in state.lobby:
            state.lobby.append(next_player)
            moved.append(next_player)

    return moved
