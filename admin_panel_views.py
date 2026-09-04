import discord

from database import get_active_lobby_bans
from state import get_state

import draft_service as svc
from admin_panel_draft_views import ResetDraftConfirmView, WipeLobbyConfirmView
from admin_panel_moderation_views import (
    ActiveTimeoutsView,
    TimeoutPlayerView,
    build_active_timeouts_embed,
)
from admin_panel_player_views import (
    AddPlayerView,
    KickPlayerView,
    MovePlayerView,
    QueuePlayerView,
    SwapPlayersView,
)


def build_admin_panel_embed(guild_id):
    state = get_state(guild_id)
    active_timeouts = get_active_lobby_bans(guild_id)

    if state.captain_draft:
        draft_status = "Captain Draft active"
    elif state.draft_result:
        draft_status = "Draft complete"
    else:
        draft_status = "No active draft"

    captain_votes = list(state.votes.values()).count("captain")
    random_votes = list(state.votes.values()).count("random")

    embed = discord.Embed(
        title="Draft Admin Control Panel",
        description=(
            "Manage the lobby without replacing the normal **Start Draft** flow."
        ),
        color=discord.Color.dark_blue(),
    )

    embed.add_field(
        name="Lobby",
        value=f"**{len(state.lobby)}/16** active",
        inline=True,
    )
    embed.add_field(
        name="Waiting Room",
        value=f"**{len(state.waiting_room)}** waiting",
        inline=True,
    )
    embed.add_field(
        name="Draft",
        value=draft_status,
        inline=True,
    )
    embed.add_field(
        name="Votes",
        value=f"Captain **{captain_votes}** • Random **{random_votes}**",
        inline=True,
    )
    embed.add_field(
        name="Captain Volunteers",
        value=str(len(state.captain_volunteers)),
        inline=True,
    )
    embed.add_field(
        name="Active Timeouts",
        value=str(len(active_timeouts)),
        inline=True,
    )

    embed.set_footer(
        text="Start Draft remains on the normal draft board / command flow."
    )
    return embed


class AdminPanelView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.guild_id = guild_id

    async def _ensure_admin(self, interaction):
        if svc.is_draft_admin(interaction):
            return True

        await interaction.response.send_message(
            "Only draft admins can use the admin panel.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Add Player", style=discord.ButtonStyle.secondary, row=0)
    async def add_player_button(self, interaction, button):
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.send_message(
            "Choose a registered player to add:",
            view=AddPlayerView(interaction.guild),
            ephemeral=True,
        )

    @discord.ui.button(label="Kick Player", style=discord.ButtonStyle.secondary, row=0)
    async def kick_player_button(self, interaction, button):
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.send_message(
            "Choose a player to remove from the draft:",
            view=KickPlayerView(self.guild_id),
            ephemeral=True,
        )

    @discord.ui.button(label="Move Player", style=discord.ButtonStyle.secondary, row=0)
    async def move_player_button(self, interaction, button):
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.send_message(
            "Choose a signed player. They will move to the other lobby area:",
            view=MovePlayerView(self.guild_id),
            ephemeral=True,
        )

    @discord.ui.button(label="Swap Players", style=discord.ButtonStyle.secondary, row=0)
    async def swap_players_button(self, interaction, button):
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.send_message(
            "Choose one lobby player and one waiting-room player:",
            view=SwapPlayersView(self.guild_id),
            ephemeral=True,
        )

    @discord.ui.button(label="Queue Position", style=discord.ButtonStyle.secondary, row=0)
    async def queue_position_button(self, interaction, button):
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.send_message(
            "Choose a waiting-room player to reposition:",
            view=QueuePlayerView(self.guild_id),
            ephemeral=True,
        )

    @discord.ui.button(label="Timeout Player", style=discord.ButtonStyle.secondary, row=1)
    async def timeout_player_button(self, interaction, button):
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.send_message(
            "Choose a registered player to timeout:",
            view=TimeoutPlayerView(interaction),
            ephemeral=True,
        )

    @discord.ui.button(label="Active Timeouts", style=discord.ButtonStyle.secondary, row=1)
    async def active_timeouts_button(self, interaction, button):
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.send_message(
            embed=build_active_timeouts_embed(self.guild_id),
            view=ActiveTimeoutsView(self.guild_id),
            ephemeral=True,
        )

    @discord.ui.button(label="Reset Draft", style=discord.ButtonStyle.danger, row=2)
    async def reset_draft_button(self, interaction, button):
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.send_message(
            "Reset the current draft result and refill the lobby from the waiting room?",
            view=ResetDraftConfirmView(),
            ephemeral=True,
        )

    @discord.ui.button(label="Wipe Lobby", style=discord.ButtonStyle.danger, row=2)
    async def wipe_lobby_button(self, interaction, button):
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.send_message(
            "Wipe the entire active lobby and waiting room?",
            view=WipeLobbyConfirmView(),
            ephemeral=True,
        )

    @discord.ui.button(label="Move to Voice", style=discord.ButtonStyle.primary, row=2)
    async def move_voice_button(self, interaction, button):
        if not await self._ensure_admin(interaction):
            return

        await svc.move_teams_to_voice(interaction)

    @discord.ui.button(label="Refresh Board", style=discord.ButtonStyle.primary, row=3)
    async def refresh_board_button(self, interaction, button):
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.defer(ephemeral=True)
        await svc.post_new_draft_board(self.guild_id)
        await interaction.followup.send(
            "Draft board refreshed.",
            ephemeral=True,
        )

    @discord.ui.button(label="Refresh Panel", style=discord.ButtonStyle.secondary, row=3)
    async def refresh_panel_button(self, interaction, button):
        if not await self._ensure_admin(interaction):
            return

        svc.load_lobby_state(self.guild_id)

        await interaction.response.edit_message(
            embed=build_admin_panel_embed(self.guild_id),
            view=AdminPanelView(self.guild_id),
        )
