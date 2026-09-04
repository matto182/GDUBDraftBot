from admin_commands import register_admin_commands
from admin_panel_commands import register_admin_panel_commands
from lobby_commands import register_lobby_commands
from moderation_commands import register_moderation_commands
from player_commands import register_player_commands
from player_inspector_commands import register_player_inspector_commands
from draft_history_commands import register_draft_history_commands
from player_management_commands import register_player_management_commands
from setup_commands import register_setup_commands


def register_commands(bot):
    register_player_commands(bot)
    register_lobby_commands(bot)
    register_admin_commands(bot)
    register_admin_panel_commands(bot)
    register_moderation_commands(bot)
    register_player_management_commands(bot)
    register_player_inspector_commands(bot)
    register_draft_history_commands(bot)
    register_setup_commands(bot)
