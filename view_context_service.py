from types import SimpleNamespace

from database import save_guild_config
from state import get_state
from service_runtime import players
from board_service import player_label, post_new_draft_board, refresh_board, show_status
from draft_execution_service import handle_captain_pick, run_startdraft
from lobby_service import (
    drop_player,
    kick_from_draft,
    reset_draft_only,
    signup_player,
    volunteer_captain,
    vote_player,
    wipe_lobby,
)
from moderation_service import is_draft_admin, timeout_from_draft
from voice_service import move_teams_to_voice


def get_view_context(guild_id):
    state = get_state(guild_id)

    return SimpleNamespace(
        guild_id=guild_id,

        players=players,
        lobby=state.lobby,
        waiting_room=state.waiting_room,

        get_captain_draft=lambda: state.captain_draft,

        signup_player=signup_player,
        drop_player=drop_player,
        vote_player=vote_player,
        volunteer_captain=volunteer_captain,
        refresh_board=refresh_board,
        show_status=show_status,
        run_startdraft=run_startdraft,
        player_label=player_label,
        is_draft_admin=is_draft_admin,
        kick_from_draft=kick_from_draft,
        timeout_from_draft=timeout_from_draft,
        move_teams_to_voice=move_teams_to_voice,
        wipe_lobby=wipe_lobby,
        reset_draft_only=reset_draft_only,
        post_new_draft_board=post_new_draft_board,
        save_guild_config=save_guild_config,
        handle_captain_pick=handle_captain_pick,
    )
