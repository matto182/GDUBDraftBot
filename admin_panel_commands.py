import discord

import draft_service as svc
from admin_panel_views import AdminPanelView, build_admin_panel_embed


def register_admin_panel_commands(bot):
    @bot.tree.command(
        name="admin",
        description="Open the draft admin control panel.",
    )
    async def admin(interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True,
            )
            return

        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can use the admin panel.",
                ephemeral=True,
            )
            return

        svc.load_lobby_state(interaction.guild.id)

        await interaction.response.send_message(
            embed=build_admin_panel_embed(interaction.guild.id),
            view=AdminPanelView(interaction.guild.id),
            ephemeral=True,
        )
