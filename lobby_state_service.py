from state import get_state
from database import (
    get_lobby_ban,
    load_lobby_state_from_db,
    save_lobby_state_to_db,
)
from service_runtime import load_players, players


def save_lobby_state(guild_id):
    state = get_state(guild_id)

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

def fill_lobby_from_waiting_room(guild_id):
    state = get_state(guild_id)

    while len(state.lobby) < 16 and state.waiting_room:
        next_player = state.waiting_room.pop(0)

        if get_lobby_ban(guild_id, next_player):
            continue

        if next_player not in state.lobby:
            state.lobby.append(next_player)
