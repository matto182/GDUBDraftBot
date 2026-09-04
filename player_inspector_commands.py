import discord
from discord import app_commands

import draft_service as svc
import player_inspector_service as inspector_service
from player_inspector_views import (
    PlayerInspectorView,
    build_player_inspector_embed,
)


async def player_inspector_autocomplete(
    interaction: discord.Interaction,
    current: str,
):
    if interaction.guild is None:
        return []

    ctx = svc.get_view_context(interaction.guild.id)
    if not ctx.is_draft_admin(interaction):
        return []

    choices = inspector_service.search_player_choices(current, limit=25)

    return [
        app_commands.Choice(
            name=f"{player['ign']} — {player['discord_name']}"[:100],
            value=str(player["user_id"]),
        )
        for player in choices
    ]


def register_player_inspector_commands(bot):
    @bot.tree.command(
        name="inspectplayer",
        description="View admin-only information about a registered draft player.",
    )
    @app_commands.describe(player="Player IGN, Discord name, or ID")
    @app_commands.autocomplete(player=player_inspector_autocomplete)
    async def inspectplayer(
        interaction: discord.Interaction,
        player: str,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True,
            )
            return

        ctx = svc.get_view_context(interaction.guild.id)

        if not ctx.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can use the player inspector.",
                ephemeral=True,
            )
            return

        record = inspector_service.resolve_player(player)
        if not record:
            await interaction.response.send_message(
                "No registered player matched that IGN, Discord name, or ID.",
                ephemeral=True,
            )
            return

        snapshot = inspector_service.build_player_snapshot(
            interaction.guild.id,
            record["user_id"],
        )
        if not snapshot:
            await interaction.response.send_message(
                "That registered player could not be loaded.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=build_player_inspector_embed(snapshot),
            view=PlayerInspectorView(
                interaction.guild.id,
                record["user_id"],
                ctx.is_draft_admin,
            ),
            ephemeral=True,
        )
