import discord
from discord import app_commands

from board_service import post_new_draft_board
from moderation_service import is_draft_admin
from service_runtime import players
from state import get_state
from trade_service import trade_players


def _draft_player_choices(guild_id, current):
    state = get_state(guild_id)
    search = (current or "").strip().lower()
    choices = []

    for team_name, team in (
        ("Team A", getattr(state, "final_team_a", [])),
        ("Team B", getattr(state, "final_team_b", [])),
    ):
        for user_id, _assigned_role in team:
            ign = players.get(user_id, {}).get("ign", str(user_id))
            label = f"{ign} — {team_name}"

            if search and search not in ign.lower() and search not in label.lower():
                continue

            choices.append(
                app_commands.Choice(
                    name=label[:100],
                    value=str(user_id),
                )
            )

    return choices[:25]


def register_trade_commands(bot):
    async def player_1_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ):
        return _draft_player_choices(interaction.guild.id, current)

    async def player_2_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ):
        return _draft_player_choices(interaction.guild.id, current)

    @bot.tree.command(
        name="trade",
        description="Trade one drafted player for a player on the opposing team."
    )
    @app_commands.autocomplete(
        player_1=player_1_autocomplete,
        player_2=player_2_autocomplete,
    )
    async def trade(
        interaction: discord.Interaction,
        player_1: str,
        player_2: str,
    ):
        if not is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can trade players.",
                ephemeral=True,
            )
            return

        try:
            player_1_id = int(player_1)
            player_2_id = int(player_2)
        except ValueError:
            await interaction.response.send_message(
                "Choose both players from the draft autocomplete list.",
                ephemeral=True,
            )
            return

        success, message = trade_players(
            interaction.guild.id,
            player_1_id,
            player_2_id,
        )

        if not success:
            await interaction.response.send_message(
                message,
                ephemeral=True,
            )
            return

        # Acknowledge the slash command before rebuilding the public board.
        await interaction.response.defer(ephemeral=True)

        await post_new_draft_board(interaction.guild.id)

        await interaction.channel.send(message)

        await interaction.followup.send(
            "Trade completed and the draft board was refreshed.",
            ephemeral=True,
        )
