import discord

from draft_history_service import get_history_page
from draft_history_views import DraftHistoryView


def register_draft_history_commands(bot):
    @bot.tree.command(
        name="history",
        description="Browse completed draft history for this server.",
    )
    async def history(interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                "Draft history can only be viewed in a server.",
                ephemeral=True,
            )
            return

        page_data = get_history_page(interaction.guild.id, 0)
        if not page_data["drafts"]:
            await interaction.response.send_message(
                "No completed drafts have been recorded for this server yet.",
                ephemeral=True,
            )
            return

        view = DraftHistoryView(interaction.guild.id)
        await interaction.response.send_message(
            embed=view.build_embed(),
            view=view,
            ephemeral=True,
        )
