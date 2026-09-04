"""Compatibility facade for draft bot services.

Existing callers can continue importing this module as `draft_service` while
the implementations live in focused service modules.
"""

import service_runtime as _runtime
from service_runtime import players, load_players
from lobby_state_service import (
    fill_lobby_from_waiting_room,
    load_lobby_state,
    save_lobby_state,
)
from board_service import (
    build_draft_board_embed,
    player_label,
    post_new_draft_board,
    refresh_board,
    show_status,
    team_text,
)
from lobby_service import (
    drop_player,
    kick_from_draft,
    reset_draft_only,
    signup_player,
    volunteer_captain,
    vote_player,
    wipe_lobby,
)
from moderation_service import (
    format_timeout_remaining,
    has_owner_role,
    is_draft_admin,
    is_owner,
    timeout_from_draft,
)
from owner_commands_service import handle_owner_prefix_message
from voice_service import move_teams_to_voice
from notification_service import notify_drafted_players
from draft_execution_service import (
    handle_captain_pick,
    run_startdraft,
    start_captain_draft,
)
from view_context_service import get_view_context


def set_bot(client):
    _runtime.set_bot(client)


def __getattr__(name):
    # Preserve access to the old module-level bot_client attribute if any
    # external code still reads it.
    if name == "bot_client":
        return _runtime.bot_client
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
