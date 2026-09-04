import discord

import draft_service as svc


async def _ensure_admin(interaction):
    if svc.is_draft_admin(interaction):
        return True

    await interaction.response.send_message(
        "Only draft admins can use the admin panel.",
        ephemeral=True,
    )
    return False


class ResetDraftConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        if not await _ensure_admin(interaction):
            return

        await svc.reset_draft_only(interaction, silent=True)
        await svc.post_new_draft_board(interaction.guild.id)
        await interaction.edit_original_response(
            content="Draft reset. Lobby refilled from the waiting room if slots were open.",
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        if not await _ensure_admin(interaction):
            return

        await interaction.response.edit_message(
            content="Draft reset cancelled.",
            view=None,
        )


class WipeLobbyConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.button(label="Confirm Wipe", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        if not await _ensure_admin(interaction):
            return

        await svc.wipe_lobby(interaction, silent=True)
        await interaction.edit_original_response(
            content="Lobby and waiting room completely wiped.",
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        if not await _ensure_admin(interaction):
            return

        await interaction.response.edit_message(
            content="Lobby wipe cancelled.",
            view=None,
        )
