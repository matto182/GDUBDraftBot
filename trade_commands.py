import discord

from board_service import post_new_draft_board
from moderation_service import is_draft_admin
from trade_service import trade_players


def register_trade_commands(bot):
    @bot.tree.command(
        name="trade",
        description="Trade one drafted player for a player on the opposing team."
    )
    async def trade(
        interaction: discord.Interaction,
        player_1: discord.Member,
        player_2: discord.Member,
    ):
        if not is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can trade players.",
                ephemeral=True,
            )
            return

        success, message = trade_players(
            interaction.guild.id,
            player_1.id,
            player_2.id,
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
