import discord
from discord import app_commands

from admin_player_helpers import (
    _find_admin_player,
    admin_registered_player_autocomplete,
    admin_signed_player_autocomplete,
    admin_waiting_player_autocomplete,
    admin_lobby_player_autocomplete,
)
from state import get_state

import draft_service as svc
import player_management_service as player_management


async def _send_action_result(interaction, success, message):
    await interaction.response.send_message(message, ephemeral=True)

    if success:
        await svc.post_new_draft_board(interaction.guild.id)


def register_player_management_commands(bot):
    @bot.tree.command(name="addplayer", description="Manually add a registered player to the draft.")
    @app_commands.describe(player="Player IGN", location="Where to add the player")
    @app_commands.choices(location=[
        app_commands.Choice(name="Lobby", value="lobby"),
        app_commands.Choice(name="Waiting Room", value="waiting"),
    ])
    @app_commands.autocomplete(player=admin_registered_player_autocomplete)
    async def addplayer(
        interaction: discord.Interaction,
        player: str,
        location: app_commands.Choice[str],
    ):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can manage players.",
                ephemeral=True,
            )
            return

        user_id = _find_admin_player(interaction, player)

        if user_id is None:
            await interaction.response.send_message(
                f"No registered player in this server found for **{player}**.",
                ephemeral=True,
            )
            return

        success, message = player_management.add_player(
            interaction.guild.id,
            user_id,
            location.value,
        )
        await _send_action_result(interaction, success, message)

    @bot.tree.command(name="moveplayer", description="Move a signed player between lobby and waiting room.")
    @app_commands.describe(player="Player IGN", destination="Where to move the player")
    @app_commands.choices(destination=[
        app_commands.Choice(name="Lobby", value="lobby"),
        app_commands.Choice(name="Waiting Room", value="waiting"),
    ])
    @app_commands.autocomplete(player=admin_signed_player_autocomplete)
    async def moveplayer(
        interaction: discord.Interaction,
        player: str,
        destination: app_commands.Choice[str],
    ):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can manage players.",
                ephemeral=True,
            )
            return

        user_id = _find_admin_player(interaction, player)

        if user_id is None:
            await interaction.response.send_message(
                f"**{player}** is not currently signed up.",
                ephemeral=True,
            )
            return

        success, message = player_management.move_player(
            interaction.guild.id,
            user_id,
            destination.value,
        )
        await _send_action_result(interaction, success, message)

    @bot.tree.command(name="queue", description="Move a waiting-room player to a specific queue position.")
    @app_commands.describe(player="Waiting-room player IGN", position="New queue position, starting at 1")
    @app_commands.autocomplete(player=admin_waiting_player_autocomplete)
    async def queue(
        interaction: discord.Interaction,
        player: str,
        position: int,
    ):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can reorder the waiting room.",
                ephemeral=True,
            )
            return

        user_id = _find_admin_player(interaction, player)

        if user_id is None:
            await interaction.response.send_message(
                f"**{player}** is not currently in the waiting room.",
                ephemeral=True,
            )
            return

        success, message = player_management.set_queue_position(
            interaction.guild.id,
            user_id,
            position,
        )
        await _send_action_result(interaction, success, message)

    @bot.tree.command(name="swapplayers", description="Swap one lobby player with one waiting-room player.")
    @app_commands.describe(
        lobby_player="Player currently in the lobby",
        waiting_player="Player currently in the waiting room",
    )
    @app_commands.autocomplete(
        lobby_player=admin_lobby_player_autocomplete,
        waiting_player=admin_waiting_player_autocomplete,
    )
    async def swapplayers(
        interaction: discord.Interaction,
        lobby_player: str,
        waiting_player: str,
    ):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can manage players.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id
        state = get_state(guild_id)

        if state.captain_draft:
            await interaction.response.send_message(
                "You cannot swap active Captain Draft players.",
                ephemeral=True,
            )
            return

        lobby_id = _find_admin_player(interaction, lobby_player)
        waiting_id = _find_admin_player(interaction, waiting_player)

        if lobby_id is None or lobby_id not in state.lobby:
            await interaction.response.send_message(
                f"**{lobby_player}** is not currently in the lobby.",
                ephemeral=True,
            )
            return

        if waiting_id is None or waiting_id not in state.waiting_room:
            await interaction.response.send_message(
                f"**{waiting_player}** is not currently in the waiting room.",
                ephemeral=True,
            )
            return

        success, message = player_management.swap_players(
            guild_id,
            lobby_id,
            waiting_id,
        )
        await _send_action_result(interaction, success, message)
