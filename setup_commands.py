import discord

from views import SetupWizardView

import draft_service as svc


def register_setup_commands(bot):
    @bot.tree.command(name="setup", description="Run the draft bot setup wizard.")
    async def setup(interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only server admins can run setup.", ephemeral=True)
            return

        await interaction.response.send_message(
            "Draft bot setup started.\n\nFirst, select the text channel where the draft board should be posted.",
            ephemeral=True,
            view=SetupWizardView(svc.get_view_context(interaction.guild.id))
        )
