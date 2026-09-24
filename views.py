"""All Discord UI views, selects, buttons, and modals."""


# ========================================================================
# DRAFT BOARD ADMIN CONTROLS
# ========================================================================

import discord

class KickPlayerSelect(discord.ui.Select):
    def __init__(self, ctx):
        self.ctx = ctx
        options = []

        for user_id in ctx.lobby:
            p = ctx.players[user_id]
            options.append(
                discord.SelectOption(
                    label=p["ign"],
                    description="Active Lobby",
                    value=str(user_id)
                )
            )

        for user_id in ctx.waiting_room:
            p = ctx.players[user_id]
            options.append(
                discord.SelectOption(
                    label=p["ign"],
                    description="Waiting Room",
                    value=str(user_id)
                )
            )

        if not options:
            options.append(
                discord.SelectOption(
                    label="No players available",
                    description="Lobby and waiting room are empty.",
                    value="none"
                )
            )

        super().__init__(
            placeholder="Choose a player to kick",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if not self.ctx.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can use this.",
                ephemeral=True
            )
            return

        if self.values[0] == "none":
            await interaction.response.send_message(
                "No players to kick.",
                ephemeral=True
            )
            return

        await self.ctx.kick_from_draft(interaction, int(self.values[0]))

class TimeoutPlayerSelect(discord.ui.Select):
    def __init__(self, ctx, registered_players):
        self.ctx = ctx
        options = []

        # registered_players has already been filtered to members of the
        # Discord server where the Admin Panel was opened.
        for user_id, player in registered_players[:25]:
            options.append(
                discord.SelectOption(
                    label=player["ign"][:100],
                    value=str(user_id)
                )
            )

        if not options:
            options.append(
                discord.SelectOption(
                    label="No registered players in this server",
                    value="none"
                )
            )

        super().__init__(
            placeholder="Choose an IGN to timeout",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if not self.ctx.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can use this.",
                ephemeral=True
            )
            return

        if self.values[0] == "none":
            await interaction.response.send_message(
                "No registered players from this server are available.",
                ephemeral=True
            )
            return

        user_id = int(self.values[0])
        player = self.ctx.players.get(user_id)

        if not player or not player.get("ign"):
            await interaction.response.send_message(
                "That registered player could not be found.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"Choose how long to timeout **{player['ign']}** from draft lobbies:",
            view=TimeoutDurationView(self.ctx, user_id),
            ephemeral=True
        )

class TimeoutPlayerView(discord.ui.View):
    def __init__(self, ctx, registered_players):
        super().__init__(timeout=300)
        self.add_item(TimeoutPlayerSelect(ctx, registered_players))

class TimeoutDurationView(discord.ui.View):
    def __init__(self, ctx, user_id):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.user_id = user_id

    async def apply_timeout(self, interaction, duration_seconds, duration_label):
        if not self.ctx.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can use this.",
                ephemeral=True
            )
            return

        await self.ctx.timeout_from_draft(
            interaction,
            self.user_id,
            duration_seconds,
            duration_label
        )

    @discord.ui.button(label="1 Hour", style=discord.ButtonStyle.secondary)
    async def one_hour(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.apply_timeout(interaction, 60 * 60, "1 hour")

    @discord.ui.button(label="1 Day", style=discord.ButtonStyle.secondary)
    async def one_day(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.apply_timeout(interaction, 24 * 60 * 60, "1 day")

    @discord.ui.button(label="3 Days", style=discord.ButtonStyle.secondary)
    async def three_days(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.apply_timeout(interaction, 3 * 24 * 60 * 60, "3 days")

    @discord.ui.button(label="5 Days", style=discord.ButtonStyle.secondary)
    async def five_days(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.apply_timeout(interaction, 5 * 24 * 60 * 60, "5 days")

    @discord.ui.button(label="Permanent", style=discord.ButtonStyle.danger)
    async def permanent(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.apply_timeout(interaction, None, "permanently")

class AdminDraftView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.add_item(KickPlayerSelect(ctx))

    @discord.ui.button(label="Timeout Player", style=discord.ButtonStyle.secondary)
    async def timeout_player_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.ctx.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can use this.",
                ephemeral=True
            )
            return

        guild_member_ids = {
            member.id
            for member in interaction.guild.members
        }
        guild_member_ids.update(self.ctx.lobby)
        guild_member_ids.update(self.ctx.waiting_room)

        guild_players = sorted(
            (
                (user_id, player)
                for user_id, player in self.ctx.players.items()
                if user_id in guild_member_ids
                and player.get("ign")
            ),
            key=lambda item: item[1]["ign"].lower()
        )[:25]

        await interaction.response.send_message(
            "Choose a player to timeout from draft lobbies:",
            view=TimeoutPlayerView(self.ctx, guild_players),
            ephemeral=True
        )

    @discord.ui.button(label="Move Teams", style=discord.ButtonStyle.primary)
    async def move_teams_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.ctx.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can move teams.",
                ephemeral=True
            )
            return

        await self.ctx.move_teams_to_voice(interaction)

    @discord.ui.button(label="Wipe Lobby", style=discord.ButtonStyle.danger)
    async def wipe_lobby_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.ctx.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can wipe the lobby.",
                ephemeral=True
            )
            return

        await self.ctx.wipe_lobby(interaction, silent=True)

    @discord.ui.button(label="Reset Draft", style=discord.ButtonStyle.danger)
    async def reset_draft_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.ctx.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can reset the draft.",
                ephemeral=True
            )
            return

        await self.ctx.reset_draft_only(interaction, silent=True)
        await self.ctx.post_new_draft_board(interaction.guild.id)


# ========================================================================
# CAPTAIN PICK UI
# ========================================================================

import draft_service as runtime
import discord

from config import normalize_roles


def server_display_name(guild_id, user_id):
    if not runtime.bot_client:
        return None

    guild = runtime.bot_client.get_guild(guild_id)
    if not guild:
        return None

    member = guild.get_member(user_id)
    if not member:
        return None

    return member.nick


class CaptainPickSelect(discord.ui.Select):
    def __init__(self, ctx):
        self.ctx = ctx
        options = []
        captain_draft = ctx.get_captain_draft()

        if captain_draft:
            for user_id in captain_draft.available:
                p = ctx.players[user_id]
                roles = ", ".join(normalize_roles(p["roles"]))

                discord_name = server_display_name(ctx.guild_id, user_id)
                player_label = p["ign"]

                if discord_name:
                    player_label = f"{player_label} — {discord_name}"

                options.append(
                    discord.SelectOption(
                        label=player_label[:100],
                        description=roles[:100],
                        value=str(user_id)
                    )
                )

        if not options:
            options.append(
                discord.SelectOption(
                    label="No players available",
                    value="none"
                )
            )

        super().__init__(
            placeholder="Pick a player",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("No players available.", ephemeral=True)
            return

        await self.ctx.handle_captain_pick(interaction, int(self.values[0]))

class CaptainPickView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.add_item(CaptainPickSelect(ctx))


# ========================================================================
# DRAFT BOARD UI
# ========================================================================

import discord


class DraftBoardView(discord.ui.View):
    def __init__(self, ctx_factory):
        super().__init__(timeout=None)
        self.ctx_factory = ctx_factory

    @discord.ui.button(label="Sign Up", style=discord.ButtonStyle.success, custom_id="draft_signup")
    async def signup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ctx = self.ctx_factory(interaction.guild.id)
        result = await ctx.signup_player(interaction, silent=True)
        if result:
            await ctx.refresh_board(interaction)

    @discord.ui.button(label="Drop", style=discord.ButtonStyle.danger, custom_id="draft_drop")
    async def drop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ctx = self.ctx_factory(interaction.guild.id)
        result = await ctx.drop_player(interaction, silent=True)
        if result:
            await ctx.refresh_board(interaction)

    @discord.ui.button(label="Vote Captain", style=discord.ButtonStyle.primary, custom_id="draft_vote_captain")
    async def vote_captain_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ctx = self.ctx_factory(interaction.guild.id)
        result = await ctx.vote_player(interaction, "captain", "Captain Mode", silent=True)
        if result:
            await ctx.refresh_board(interaction)

    @discord.ui.button(label="Vote Random", style=discord.ButtonStyle.primary, custom_id="draft_vote_random")
    async def vote_random_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ctx = self.ctx_factory(interaction.guild.id)
        result = await ctx.vote_player(interaction, "random", "Random Draft", silent=True)
        if result:
            await ctx.refresh_board(interaction)

    @discord.ui.button(label="Volunteer Captain", style=discord.ButtonStyle.secondary, custom_id="draft_captain")
    async def captain_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ctx = self.ctx_factory(interaction.guild.id)
        result = await ctx.volunteer_captain(interaction, silent=True)
        if result:
            await ctx.refresh_board(interaction)

    @discord.ui.button(label="Start Draft", style=discord.ButtonStyle.success, custom_id="draft_start")
    async def start_draft_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ctx = self.ctx_factory(interaction.guild.id)

        if not ctx.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can start the draft.",
                ephemeral=True
            )
            return

        if len(ctx.lobby) != ctx.lobby_size:
            await interaction.response.send_message(
                f"Need exactly {ctx.lobby_size} players. Current: {len(ctx.lobby)}/{ctx.lobby_size}",
                ephemeral=True
            )
            return

        await ctx.run_startdraft(interaction)

    @discord.ui.button(label="Pick Player", style=discord.ButtonStyle.success, custom_id="draft_pick_player")
    async def pick_player_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ctx = self.ctx_factory(interaction.guild.id)
        captain_draft = ctx.get_captain_draft()

        if not captain_draft:
            await interaction.response.send_message(
                "No captain draft is active.",
                ephemeral=True
            )
            return

        current_picker = captain_draft.current_picker()

        if interaction.user.id != current_picker:
            await interaction.response.send_message(
                f"It is currently {ctx.player_label(ctx.guild_id, current_picker)}'s pick.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Choose a player to pick:",
            view=CaptainPickView(ctx),
            ephemeral=True
        )

    @discord.ui.button(label="Admin Panel", style=discord.ButtonStyle.secondary, custom_id="draft_admin_panel")
    async def admin_panel_button(self, interaction: discord.Interaction, button: discord.ui.Button):

        ctx = self.ctx_factory(interaction.guild.id)

        if not ctx.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can use this.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            embed=build_admin_panel_embed(interaction.guild.id),
            view=AdminPanelView(interaction.guild.id),
            ephemeral=True
        )

    @discord.ui.button(label="Status", style=discord.ButtonStyle.secondary, custom_id="draft_status")
    async def status_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ctx = self.ctx_factory(interaction.guild.id)
        await ctx.show_status(interaction)


# ========================================================================
# SETUP UI
# ========================================================================

import discord

class SetupWizardView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx = ctx

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Step 1: Select draft board text channel",
        channel_types=[discord.ChannelType.text],
        min_values=1,
        max_values=1
    )
    async def select_draft_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only server admins can run setup.", ephemeral=True)
            return

        channel = select.values[0]

        self.ctx.save_guild_config(
            interaction.guild.id,
            draft_channel_id=channel.id
        )

        await interaction.response.send_message(
            f"Draft board channel saved: {channel.mention}\n\nNow select the scheduled events channel, or use the draft board channel.",
            ephemeral=True,
            view=SetupEventChannelView(self.ctx, channel.id)
        )

class SetupEventChannelView(discord.ui.View):
    def __init__(self, ctx, draft_channel_id):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.draft_channel_id = draft_channel_id

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Step 2: Select scheduled events text channel",
        channel_types=[discord.ChannelType.text],
        min_values=1,
        max_values=1
    )
    async def select_event_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only server admins can run setup.", ephemeral=True)
            return

        channel = select.values[0]
        self.ctx.save_guild_config(interaction.guild.id, event_channel_id=channel.id)
        await interaction.response.send_message(
            f"Scheduled events channel saved: {channel.mention}\n\nNow select Team A voice channel.",
            ephemeral=True,
            view=SetupTeamAVoiceView(self.ctx)
        )

    @discord.ui.button(label="Use draft board channel", style=discord.ButtonStyle.secondary)
    async def use_draft_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only server admins can run setup.", ephemeral=True)
            return

        self.ctx.save_guild_config(interaction.guild.id, event_channel_id=self.draft_channel_id)
        await interaction.response.send_message(
            "Scheduled events will use the draft board channel.\n\nNow select Team A voice channel.",
            ephemeral=True,
            view=SetupTeamAVoiceView(self.ctx)
        )

class SetupTeamAVoiceView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx = ctx

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Step 3: Select Team A voice channel",
        channel_types=[discord.ChannelType.voice],
        min_values=1,
        max_values=1
    )
    async def select_team_a_voice(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only server admins can run setup.", ephemeral=True)
            return

        channel = select.values[0]

        self.ctx.save_guild_config(
            interaction.guild.id,
            team_a_voice_channel_id=channel.id
        )

        await interaction.response.send_message(
            f"Team A voice channel saved: **{channel.name}**\n\nNow select Team B voice channel.",
            ephemeral=True,
            view=SetupTeamBVoiceView(self.ctx)
        )

class SetupTeamBVoiceView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx = ctx

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Step 4: Select Team B voice channel",
        channel_types=[discord.ChannelType.voice],
        min_values=1,
        max_values=1
    )
    async def select_team_b_voice(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only server admins can run setup.", ephemeral=True)
            return

        channel = select.values[0]

        self.ctx.save_guild_config(
            interaction.guild.id,
            team_b_voice_channel_id=channel.id
        )

        await interaction.response.send_message(
            f"Team B voice channel saved: **{channel.name}**\n\nNow select the Draft Admin role.",
            ephemeral=True,
            view=SetupAdminRoleView(self.ctx)
        )

class SetupAdminRoleView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx = ctx

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Step 5: Select Draft Admin role",
        min_values=1,
        max_values=1
    )
    async def select_admin_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only server admins can run setup.", ephemeral=True)
            return

        role = select.values[0]

        self.ctx.save_guild_config(
            interaction.guild.id,
            admin_role_id=role.id
        )

        await interaction.response.send_message(
            f"Draft Admin role saved: {role.mention}\n\nNow select the Owner role.",
            ephemeral=True,
            view=SetupOwnerRoleView(self.ctx)
        )

class SetupOwnerRoleView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx = ctx

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Step 6: Select Owner role",
        min_values=1,
        max_values=1
    )
    async def select_owner_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only server admins can run setup.", ephemeral=True)
            return

        role = select.values[0]

        self.ctx.save_guild_config(
            interaction.guild.id,
            owner_role_id=role.id
        )

        await interaction.response.send_message(
            f"Owner role saved: {role.mention}\n\nSetup complete. Posting draft board.",
            ephemeral=True
        )

        await self.ctx.post_new_draft_board(interaction.guild.id)


# ========================================================================
# ADMIN PANEL - DRAFT ACTIONS
# ========================================================================

import discord

import draft_service as svc


async def _ensure_admin_draft(interaction):
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
        if not await _ensure_admin_draft(interaction):
            return

        await svc.reset_draft_only(interaction, silent=True)
        await svc.post_new_draft_board(interaction.guild.id)
        await interaction.edit_original_response(
            content="Draft reset. Lobby refilled from the waiting room if slots were open.",
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        if not await _ensure_admin_draft(interaction):
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
        if not await _ensure_admin_draft(interaction):
            return

        await svc.wipe_lobby(interaction, silent=True)
        await interaction.edit_original_response(
            content="Lobby and waiting room completely wiped.",
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        if not await _ensure_admin_draft(interaction):
            return

        await interaction.response.edit_message(
            content="Lobby wipe cancelled.",
            view=None,
        )


# ========================================================================
# ADMIN PANEL - MODERATION
# ========================================================================

from draft_service import remove_lobby_timeout, admin_player_choice_label, resolve_player_search
import discord

from database import get_active_lobby_bans

import draft_service as svc


async def _ensure_admin_moderation(interaction):
    if svc.is_draft_admin(interaction):
        return True

    await interaction.response.send_message(
        "Only draft admins can use the admin panel.",
        ephemeral=True,
    )
    return False


def _registered_timeout_candidates(interaction):
    guild_member_ids = {member.id for member in interaction.guild.members}
    ctx = svc.get_view_context(interaction.guild.id)

    guild_member_ids.update(ctx.lobby)
    guild_member_ids.update(ctx.waiting_room)

    return sorted(
        (
            user_id
            for user_id, player in svc.players.items()
            if user_id in guild_member_ids and player.get("ign")
        ),
        key=lambda user_id: svc.players[user_id]["ign"].casefold(),
    )


async def _show_timeout_duration(interaction, user_id):
    player = svc.players.get(user_id)

    if not player:
        await interaction.response.send_message(
            "That registered player could not be found.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        f"Choose how long to timeout **{player['ign']}** from draft lobbies:",
        view=TimeoutDurationView(
            svc.get_view_context(interaction.guild.id),
            user_id,
        ),
        ephemeral=True,
    )


class TimeoutPlayerSearchResultSelect(discord.ui.Select):
    def __init__(self, guild, user_ids):
        options = []

        for user_id in list(user_ids)[:25]:
            player = svc.players[user_id]
            options.append(
                discord.SelectOption(
                    label=admin_player_choice_label(
                        guild,
                        user_id,
                        player["ign"],
                    ),
                    value=str(user_id),
                )
            )

        super().__init__(
            placeholder="Choose the player to timeout",
            options=options,
        )

    async def callback(self, interaction):
        if not await _ensure_admin_moderation(interaction):
            return

        await _show_timeout_duration(
            interaction,
            int(self.values[0]),
        )


class TimeoutPlayerSearchResultsView(discord.ui.View):
    def __init__(self, guild, user_ids):
        super().__init__(timeout=300)
        self.add_item(
            TimeoutPlayerSearchResultSelect(
                guild,
                user_ids,
            )
        )


class TimeoutPlayerSearchModal(discord.ui.Modal, title="Timeout Player"):
    player_search = discord.ui.TextInput(
        label="Find registered player",
        placeholder="IGN, Discord nickname, or username",
        required=True,
        max_length=100,
    )

    async def on_submit(self, interaction):
        if not await _ensure_admin_moderation(interaction):
            return

        query = str(self.player_search.value).strip()
        candidate_ids = _registered_timeout_candidates(interaction)

        selected_user_id, matches = resolve_player_search(
            interaction.guild,
            query,
            candidate_ids,
        )

        if selected_user_id is not None:
            await _show_timeout_duration(
                interaction,
                selected_user_id,
            )
            return

        if not matches:
            await interaction.response.send_message(
                f"No registered player matched **{query}**.",
                ephemeral=True,
            )
            return

        showing = matches[:25]
        note = ""
        if len(matches) > 25:
            note = (
                f" Showing the first **25** of **{len(matches)}** matches; "
                "search more specifically if needed."
            )

        await interaction.response.send_message(
            f"Found **{len(matches)}** matches for **{query}**.{note}",
            view=TimeoutPlayerSearchResultsView(
                interaction.guild,
                showing,
            ),
            ephemeral=True,
        )


class AdminPanelTimeoutPlayerSelect(discord.ui.Select):
    def __init__(self, interaction):
        candidates = _registered_timeout_candidates(interaction)

        options = [
            discord.SelectOption(
                label=svc.players[user_id]["ign"][:100],
                value=str(user_id),
            )
            for user_id in candidates
        ]

        if not options:
            options = [
                discord.SelectOption(
                    label="No registered players in this server",
                    value="none",
                )
            ]

        super().__init__(
            placeholder="Choose a player to timeout",
            options=options,
        )

    async def callback(self, interaction):
        if not await _ensure_admin_moderation(interaction):
            return

        if self.values[0] == "none":
            await interaction.response.send_message(
                "No registered players are available.",
                ephemeral=True,
            )
            return

        user_id = int(self.values[0])
        player = svc.players.get(user_id)

        if not player:
            await interaction.response.send_message(
                "That registered player could not be found.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Choose how long to timeout **{player['ign']}** from draft lobbies:",
            view=TimeoutDurationView(
                svc.get_view_context(interaction.guild.id),
                user_id,
            ),
            ephemeral=True,
        )


class AdminPanelTimeoutPlayerView(discord.ui.View):
    def __init__(self, interaction):
        super().__init__(timeout=300)
        self.add_item(AdminPanelTimeoutPlayerSelect(interaction))


def build_active_timeouts_embed(guild_id):
    active_bans = get_active_lobby_bans(guild_id)

    if not active_bans:
        return discord.Embed(
            title="Active Draft Lobby Timeouts",
            description="There are no active draft lobby timeouts.",
            color=discord.Color.green(),
        )

    lines = []
    for ban in active_bans:
        user_id = ban["user_id"]
        player = svc.players.get(user_id)
        ign = player.get("ign") if player else "Unknown player"

        if ban["expires_at"] is None:
            duration = "**Permanent**"
        else:
            expires_timestamp = int(ban["expires_at"])
            remaining = svc.format_timeout_remaining(ban["expires_at"])
            duration = f"**{remaining}** remaining — <t:{expires_timestamp}:R>"

        lines.append(f"• **{ign}** — {duration}")

    return discord.Embed(
        title="Active Draft Lobby Timeouts",
        description="\n".join(lines),
        color=discord.Color.orange(),
    )


class ActiveTimeoutSelect(discord.ui.Select):
    def __init__(self, guild_id):
        active_bans = get_active_lobby_bans(guild_id)[:25]
        options = []

        for ban in active_bans:
            user_id = ban["user_id"]
            player = svc.players.get(user_id)
            ign = player.get("ign") if player else f"User {user_id}"
            options.append(
                discord.SelectOption(
                    label=ign[:100],
                    value=str(user_id),
                )
            )

        if not options:
            options.append(
                discord.SelectOption(
                    label="No active timeouts",
                    value="none",
                )
            )

        super().__init__(
            placeholder="Choose a timeout to remove",
            options=options,
        )

    async def callback(self, interaction):
        if not await _ensure_admin_moderation(interaction):
            return

        if self.values[0] == "none":
            await interaction.response.send_message(
                "There are no active draft lobby timeouts.",
                ephemeral=True,
            )
            return

        user_id = int(self.values[0])
        player = svc.players.get(user_id)
        ign = player.get("ign") if player else "Unknown player"

        removed = remove_lobby_timeout(interaction.guild.id, user_id)

        if not removed:
            await interaction.response.send_message(
                f"**{ign}** does not have an active draft lobby timeout.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            embed=build_active_timeouts_embed(interaction.guild.id),
            view=ActiveTimeoutsView(interaction.guild.id),
        )


class ActiveTimeoutsView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.add_item(ActiveTimeoutSelect(guild_id))


# ========================================================================
# ADMIN PANEL - PLAYER MANAGEMENT
# ========================================================================

import draft_service as player_management
from draft_service import get_state, _player_matches_admin_value, admin_player_choice_label, admin_player_identity_text, find_registered_player_matches, resolve_player_search
import discord

import draft_service as svc


def _player_name(user_id):
    player = svc.players.get(user_id, {})
    return player.get("ign") or str(user_id)


def _build_options(user_ids, empty_label, description=None):
    options = []

    for user_id in list(user_ids)[:25]:
        kwargs = {
            "label": _player_name(user_id)[:100],
            "value": str(user_id),
        }
        if description:
            kwargs["description"] = description(user_id)[:100]

        options.append(discord.SelectOption(**kwargs))

    if not options:
        options.append(discord.SelectOption(label=empty_label[:100], value="none"))

    return options


async def _ensure_admin_player(interaction):
    if svc.is_draft_admin(interaction):
        return True

    await interaction.response.send_message(
        "Only draft admins can use the admin panel.",
        ephemeral=True,
    )
    return False


async def _send_result(interaction, success, message):
    await interaction.response.send_message(message, ephemeral=True)

    if success:
        await svc.post_new_draft_board(interaction.guild.id)


class AddPlayerSelect(discord.ui.Select):
    def __init__(self, guild):
        state = get_state(guild.id)
        guild_member_ids = {member.id for member in guild.members}
        available = sorted(
            (
                user_id
                for user_id, player in svc.players.items()
                if user_id in guild_member_ids
                and player.get("ign")
                and user_id not in state.lobby
                and user_id not in state.waiting_room
            ),
            key=lambda user_id: _player_name(user_id).casefold(),
        )

        def discord_identity(user_id):
            ign = _player_name(user_id)
            return (
                admin_player_identity_text(guild, user_id, ign)
                or "Discord identity matches IGN"
            )

        super().__init__(
            placeholder="Choose a registered player to add",
            options=_build_options(
                available,
                "No unsigned registered players",
                discord_identity,
            ),
        )

    async def callback(self, interaction):
        if not await _ensure_admin_player(interaction):
            return

        if self.values[0] == "none":
            await interaction.response.send_message(
                "There are no available registered players to add.",
                ephemeral=True,
            )
            return

        user_id = int(self.values[0])
        await interaction.response.send_message(
            f"Where should **{_player_name(user_id)}** be added?",
            view=AddPlayerDestinationView(user_id),
            ephemeral=True,
        )


class AddPlayerView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=300)
        self.add_item(AddPlayerSelect(guild))


class AddPlayerSearchResultSelect(discord.ui.Select):
    def __init__(self, guild, user_ids):
        options = []

        for user_id in list(user_ids)[:25]:
            ign = _player_name(user_id)
            options.append(
                discord.SelectOption(
                    label=admin_player_choice_label(guild, user_id, ign),
                    value=str(user_id),
                )
            )

        super().__init__(
            placeholder="Choose the player you meant",
            options=options,
        )

    async def callback(self, interaction):
        if not await _ensure_admin_player(interaction):
            return

        user_id = int(self.values[0])

        await interaction.response.send_message(
            f"Where should **{_player_name(user_id)}** be added?",
            view=AddPlayerDestinationView(user_id),
            ephemeral=True,
        )


class AddPlayerSearchResultsView(discord.ui.View):
    def __init__(self, guild, user_ids):
        super().__init__(timeout=300)
        self.add_item(AddPlayerSearchResultSelect(guild, user_ids))


class AddPlayerSearchModal(discord.ui.Modal, title="Add Player"):
    player_search = discord.ui.TextInput(
        label="Find player",
        placeholder="IGN, Discord nickname, or username",
        required=True,
        max_length=100,
    )

    async def on_submit(self, interaction):
        if not await _ensure_admin_player(interaction):
            return

        query = str(self.player_search.value).strip()

        if not query:
            await interaction.response.send_message(
                "Enter an IGN, Discord nickname, or username.",
                ephemeral=True,
            )
            return

        state = get_state(interaction.guild.id)
        excluded_ids = set(state.lobby) | set(state.waiting_room)

        matches = find_registered_player_matches(
            interaction.guild,
            query,
            excluded_ids=excluded_ids,
        )

        if not matches:
            await interaction.response.send_message(
                f"No unsigned registered player matched **{query}**.",
                ephemeral=True,
            )
            return

        exact_matches = [
            user_id
            for user_id in matches
            if _player_matches_admin_value(
                interaction.guild,
                user_id,
                svc.players[user_id],
                query,
            )
        ]

        if len(exact_matches) == 1:
            selected_user_id = exact_matches[0]
        elif len(matches) == 1:
            selected_user_id = matches[0]
        else:
            showing = matches[:25]
            extra_note = ""

            if len(matches) > 25:
                extra_note = (
                    f" Showing the first **25** of **{len(matches)}** matches; "
                    "search more specifically to narrow it down."
                )

            await interaction.response.send_message(
                f"Found **{len(matches)}** matches for **{query}**."
                f"{extra_note}",
                view=AddPlayerSearchResultsView(
                    interaction.guild,
                    showing,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Where should **{_player_name(selected_user_id)}** be added?",
            view=AddPlayerDestinationView(selected_user_id),
            ephemeral=True,
        )


class AddPlayerDestinationView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=300)
        self.user_id = user_id

    async def _add(self, interaction, destination):
        if not await _ensure_admin_player(interaction):
            return

        success, message = player_management.add_player(
            interaction.guild.id,
            self.user_id,
            destination,
        )
        await _send_result(interaction, success, message)

    @discord.ui.button(label="Lobby", style=discord.ButtonStyle.primary)
    async def lobby_button(self, interaction, button):
        await self._add(interaction, "lobby")

    @discord.ui.button(label="Waiting Room", style=discord.ButtonStyle.secondary)
    async def waiting_button(self, interaction, button):
        await self._add(interaction, "waiting")


def _search_result_options(guild, user_ids):
    options = []

    for user_id in list(user_ids)[:25]:
        ign = _player_name(user_id)
        options.append(
            discord.SelectOption(
                label=admin_player_choice_label(guild, user_id, ign),
                value=str(user_id),
            )
        )

    return options


def _match_summary(guild, user_ids, limit=10):
    labels = [
        admin_player_choice_label(
            guild,
            user_id,
            _player_name(user_id),
        )
        for user_id in list(user_ids)[:limit]
    ]

    return "\n".join(f"• {label}" for label in labels)


class KickPlayerSearchResultSelect(discord.ui.Select):
    def __init__(self, guild, user_ids):
        super().__init__(
            placeholder="Choose the player to kick",
            options=_search_result_options(guild, user_ids),
        )

    async def callback(self, interaction):
        if not await _ensure_admin_player(interaction):
            return

        await svc.kick_from_draft(
            interaction,
            int(self.values[0]),
        )


class KickPlayerSearchResultsView(discord.ui.View):
    def __init__(self, guild, user_ids):
        super().__init__(timeout=300)
        self.add_item(KickPlayerSearchResultSelect(guild, user_ids))


class KickPlayerSearchModal(discord.ui.Modal, title="Kick Player"):
    player_search = discord.ui.TextInput(
        label="Find signed player",
        placeholder="IGN, Discord nickname, or username",
        required=True,
        max_length=100,
    )

    async def on_submit(self, interaction):
        if not await _ensure_admin_player(interaction):
            return

        state = get_state(interaction.guild.id)
        candidate_ids = list(state.lobby) + list(state.waiting_room)
        query = str(self.player_search.value).strip()

        selected_user_id, matches = resolve_player_search(
            interaction.guild,
            query,
            candidate_ids,
        )

        if selected_user_id is not None:
            await svc.kick_from_draft(interaction, selected_user_id)
            return

        if not matches:
            await interaction.response.send_message(
                f"No signed player matched **{query}**.",
                ephemeral=True,
            )
            return

        showing = matches[:25]
        note = ""
        if len(matches) > 25:
            note = (
                f" Showing the first **25** of **{len(matches)}** matches; "
                "search more specifically if needed."
            )

        await interaction.response.send_message(
            f"Found **{len(matches)}** matches for **{query}**.{note}",
            view=KickPlayerSearchResultsView(
                interaction.guild,
                showing,
            ),
            ephemeral=True,
        )


class MovePlayerSearchResultSelect(discord.ui.Select):
    def __init__(self, guild, user_ids):
        super().__init__(
            placeholder="Choose the player to move",
            options=_search_result_options(guild, user_ids),
        )

    async def callback(self, interaction):
        if not await _ensure_admin_player(interaction):
            return

        success, message = player_management.move_player_to_other_area(
            interaction.guild.id,
            int(self.values[0]),
        )
        await _send_result(interaction, success, message)


class MovePlayerSearchResultsView(discord.ui.View):
    def __init__(self, guild, user_ids):
        super().__init__(timeout=300)
        self.add_item(MovePlayerSearchResultSelect(guild, user_ids))


class MovePlayerSearchModal(discord.ui.Modal, title="Move Player"):
    player_search = discord.ui.TextInput(
        label="Find signed player",
        placeholder="IGN, Discord nickname, or username",
        required=True,
        max_length=100,
    )

    async def on_submit(self, interaction):
        if not await _ensure_admin_player(interaction):
            return

        state = get_state(interaction.guild.id)
        candidate_ids = list(state.lobby) + list(state.waiting_room)
        query = str(self.player_search.value).strip()

        selected_user_id, matches = resolve_player_search(
            interaction.guild,
            query,
            candidate_ids,
        )

        if selected_user_id is not None:
            success, message = player_management.move_player_to_other_area(
                interaction.guild.id,
                selected_user_id,
            )
            await _send_result(interaction, success, message)
            return

        if not matches:
            await interaction.response.send_message(
                f"No signed player matched **{query}**.",
                ephemeral=True,
            )
            return

        showing = matches[:25]
        note = ""
        if len(matches) > 25:
            note = (
                f" Showing the first **25** of **{len(matches)}** matches; "
                "search more specifically if needed."
            )

        await interaction.response.send_message(
            f"Found **{len(matches)}** matches for **{query}**.{note}",
            view=MovePlayerSearchResultsView(
                interaction.guild,
                showing,
            ),
            ephemeral=True,
        )


class SwapPlayersSearchModal(discord.ui.Modal, title="Swap Players"):
    lobby_player = discord.ui.TextInput(
        label="Lobby player",
        placeholder="IGN, Discord nickname, or username",
        required=True,
        max_length=100,
    )
    waiting_player = discord.ui.TextInput(
        label="Waiting-room player",
        placeholder="IGN, Discord nickname, or username",
        required=True,
        max_length=100,
    )

    async def on_submit(self, interaction):
        if not await _ensure_admin_player(interaction):
            return

        state = get_state(interaction.guild.id)

        lobby_query = str(self.lobby_player.value).strip()
        waiting_query = str(self.waiting_player.value).strip()

        lobby_user_id, lobby_matches = resolve_player_search(
            interaction.guild,
            lobby_query,
            state.lobby,
        )
        waiting_user_id, waiting_matches = resolve_player_search(
            interaction.guild,
            waiting_query,
            state.waiting_room,
        )

        problems = []

        if lobby_user_id is None:
            if not lobby_matches:
                problems.append(
                    f"No lobby player matched **{lobby_query}**."
                )
            else:
                problems.append(
                    f"Lobby search **{lobby_query}** matched multiple players:\n"
                    f"{_match_summary(interaction.guild, lobby_matches)}"
                )

        if waiting_user_id is None:
            if not waiting_matches:
                problems.append(
                    f"No waiting-room player matched **{waiting_query}**."
                )
            else:
                problems.append(
                    f"Waiting-room search **{waiting_query}** matched multiple players:\n"
                    f"{_match_summary(interaction.guild, waiting_matches)}"
                )

        if problems:
            await interaction.response.send_message(
                "\n\n".join(problems)
                + "\n\nRun **Swap Players** again with a more specific search.",
                ephemeral=True,
            )
            return

        success, message = player_management.swap_players(
            interaction.guild.id,
            lobby_user_id,
            waiting_user_id,
        )
        await _send_result(interaction, success, message)


class QueuePlayerSearchResultSelect(discord.ui.Select):
    def __init__(self, guild, user_ids, position):
        self.position = position

        super().__init__(
            placeholder="Choose the waiting-room player",
            options=_search_result_options(guild, user_ids),
        )

    async def callback(self, interaction):
        if not await _ensure_admin_player(interaction):
            return

        success, message = player_management.set_queue_position(
            interaction.guild.id,
            int(self.values[0]),
            self.position,
        )
        await _send_result(interaction, success, message)


class QueuePlayerSearchResultsView(discord.ui.View):
    def __init__(self, guild, user_ids, position):
        super().__init__(timeout=300)
        self.add_item(
            QueuePlayerSearchResultSelect(
                guild,
                user_ids,
                position,
            )
        )


class QueuePlayerSearchModal(discord.ui.Modal, title="Set Queue Position"):
    player_search = discord.ui.TextInput(
        label="Find waiting-room player",
        placeholder="IGN, Discord nickname, or username",
        required=True,
        max_length=100,
    )
    position = discord.ui.TextInput(
        label="New queue position",
        placeholder="1",
        required=True,
        max_length=3,
    )

    async def on_submit(self, interaction):
        if not await _ensure_admin_player(interaction):
            return

        try:
            position = int(str(self.position.value).strip())
        except ValueError:
            await interaction.response.send_message(
                "Queue position must be a whole number.",
                ephemeral=True,
            )
            return

        state = get_state(interaction.guild.id)
        query = str(self.player_search.value).strip()

        selected_user_id, matches = resolve_player_search(
            interaction.guild,
            query,
            state.waiting_room,
        )

        if selected_user_id is not None:
            success, message = player_management.set_queue_position(
                interaction.guild.id,
                selected_user_id,
                position,
            )
            await _send_result(interaction, success, message)
            return

        if not matches:
            await interaction.response.send_message(
                f"No waiting-room player matched **{query}**.",
                ephemeral=True,
            )
            return

        showing = matches[:25]
        note = ""
        if len(matches) > 25:
            note = (
                f" Showing the first **25** of **{len(matches)}** matches; "
                "search more specifically if needed."
            )

        await interaction.response.send_message(
            f"Found **{len(matches)}** matches for **{query}**.{note}",
            view=QueuePlayerSearchResultsView(
                interaction.guild,
                showing,
                position,
            ),
            ephemeral=True,
        )


class AdminPanelKickPlayerSelect(discord.ui.Select):
    def __init__(self, guild_id):
        state = get_state(guild_id)
        signed = list(state.lobby) + list(state.waiting_room)

        def area(user_id):
            return "Active Lobby" if user_id in state.lobby else "Waiting Room"

        super().__init__(
            placeholder="Choose a player to kick",
            options=_build_options(signed, "Lobby and waiting room are empty", area),
        )

    async def callback(self, interaction):
        if not await _ensure_admin_player(interaction):
            return

        if self.values[0] == "none":
            await interaction.response.send_message(
                "No players are currently signed up.",
                ephemeral=True,
            )
            return

        await svc.kick_from_draft(interaction, int(self.values[0]))


class KickPlayerView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.add_item(AdminPanelKickPlayerSelect(guild_id))


class MovePlayerSelect(discord.ui.Select):
    def __init__(self, guild_id):
        state = get_state(guild_id)
        signed = list(state.lobby) + list(state.waiting_room)

        def destination(user_id):
            if user_id in state.lobby:
                return "Move to Waiting Room"
            return "Move to Lobby"

        super().__init__(
            placeholder="Choose a player to move",
            options=_build_options(signed, "No signed players", destination),
        )

    async def callback(self, interaction):
        if not await _ensure_admin_player(interaction):
            return

        if self.values[0] == "none":
            await interaction.response.send_message(
                "No players are currently signed up.",
                ephemeral=True,
            )
            return

        success, message = player_management.move_player_to_other_area(
            interaction.guild.id,
            int(self.values[0]),
        )
        await _send_result(interaction, success, message)


class MovePlayerView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.add_item(MovePlayerSelect(guild_id))


class SwapLobbySelect(discord.ui.Select):
    def __init__(self, parent, guild_id):
        self.parent_view = parent
        state = get_state(guild_id)

        super().__init__(
            placeholder="Lobby player",
            options=_build_options(state.lobby, "Lobby is empty"),
            row=0,
        )

    async def callback(self, interaction):
        if not await _ensure_admin_player(interaction):
            return

        self.parent_view.lobby_user_id = (
            None if self.values[0] == "none" else int(self.values[0])
        )
        await interaction.response.defer()


class SwapWaitingSelect(discord.ui.Select):
    def __init__(self, parent, guild_id):
        self.parent_view = parent
        state = get_state(guild_id)

        super().__init__(
            placeholder="Waiting-room player",
            options=_build_options(state.waiting_room, "Waiting room is empty"),
            row=1,
        )

    async def callback(self, interaction):
        if not await _ensure_admin_player(interaction):
            return

        self.parent_view.waiting_user_id = (
            None if self.values[0] == "none" else int(self.values[0])
        )
        await interaction.response.defer()


class SwapPlayersView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.lobby_user_id = None
        self.waiting_user_id = None
        self.add_item(SwapLobbySelect(self, guild_id))
        self.add_item(SwapWaitingSelect(self, guild_id))

    @discord.ui.button(label="Swap Players", style=discord.ButtonStyle.primary, row=2)
    async def confirm_swap(self, interaction, button):
        if not await _ensure_admin_player(interaction):
            return

        if self.lobby_user_id is None or self.waiting_user_id is None:
            await interaction.response.send_message(
                "Choose both a lobby player and a waiting-room player first.",
                ephemeral=True,
            )
            return

        success, message = player_management.swap_players(
            interaction.guild.id,
            self.lobby_user_id,
            self.waiting_user_id,
        )
        await _send_result(interaction, success, message)


class QueuePositionModal(discord.ui.Modal, title="Set Waiting-Room Position"):
    position = discord.ui.TextInput(
        label="New queue position",
        placeholder="1",
        required=True,
        max_length=3,
    )

    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction):
        if not await _ensure_admin_player(interaction):
            return

        try:
            position = int(str(self.position.value).strip())
        except ValueError:
            await interaction.response.send_message(
                "Queue position must be a whole number.",
                ephemeral=True,
            )
            return

        success, message = player_management.set_queue_position(
            interaction.guild.id,
            self.user_id,
            position,
        )
        await _send_result(interaction, success, message)


class QueuePlayerSelect(discord.ui.Select):
    def __init__(self, guild_id):
        state = get_state(guild_id)
        super().__init__(
            placeholder="Choose a waiting-room player",
            options=_build_options(state.waiting_room, "Waiting room is empty"),
        )

    async def callback(self, interaction):
        if not await _ensure_admin_player(interaction):
            return

        if self.values[0] == "none":
            await interaction.response.send_message(
                "The waiting room is empty.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            QueuePositionModal(int(self.values[0]))
        )


class QueuePlayerView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.add_item(QueuePlayerSelect(guild_id))


# ========================================================================
# ADMIN PANEL
# ========================================================================

from draft_service import get_state
import discord

from database import get_active_lobby_bans

import draft_service as svc


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
        value=f"**{len(state.lobby)}/{state.lobby_size}** active",
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

        await interaction.response.send_modal(
            AddPlayerSearchModal()
        )

    @discord.ui.button(label="Kick Player", style=discord.ButtonStyle.secondary, row=0)
    async def kick_player_button(self, interaction, button):
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.send_modal(
            KickPlayerSearchModal()
        )

    @discord.ui.button(label="Move Player", style=discord.ButtonStyle.secondary, row=0)
    async def move_player_button(self, interaction, button):
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.send_modal(
            MovePlayerSearchModal()
        )

    @discord.ui.button(label="Swap Players", style=discord.ButtonStyle.secondary, row=0)
    async def swap_players_button(self, interaction, button):
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.send_modal(
            SwapPlayersSearchModal()
        )

    @discord.ui.button(label="Queue Position", style=discord.ButtonStyle.secondary, row=0)
    async def queue_position_button(self, interaction, button):
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.send_modal(
            QueuePlayerSearchModal()
        )

    @discord.ui.button(label="Timeout Player", style=discord.ButtonStyle.secondary, row=1)
    async def timeout_player_button(self, interaction, button):
        if not await self._ensure_admin(interaction):
            return

        await interaction.response.send_modal(
            TimeoutPlayerSearchModal()
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


# ========================================================================
# PLAYER INSPECTOR UI
# ========================================================================

import draft_service as moderation_service
import draft_service as inspector_service
from datetime import datetime, timezone

import discord

import draft_service as svc


def _discord_timestamp(timestamp, style="R"):
    if not timestamp:
        return "Never"
    return f"<t:{int(timestamp)}:{style}>"


def _role_history_text(snapshot):
    history = snapshot.get("role_history", [])
    if not history:
        return "No draft history."

    return "\n".join(
        f"**{entry['role']}** — {entry['count']}"
        for entry in history[:8]
    )


def _recent_activity_text(snapshot):
    drafts = snapshot.get("recent_drafts", [])
    if not drafts:
        return "No completed drafts recorded."

    lines = []
    for draft in drafts:
        captain = " • Captain" if draft["was_captain"] else ""
        balance = (
            f" • Balance {draft['balance_score']}"
            if draft["balance_score"] is not None
            else ""
        )
        lines.append(
            f"**#{draft['draft_id']}** • {draft['mode']} • Team {draft['team']} "
            f"• {draft['assigned_role']}{captain}{balance} "
            f"• {_discord_timestamp(draft['created_at'])}"
        )

    return "\n".join(lines)


def _timeout_control_state(snapshot):
    active = bool(snapshot and snapshot.get("timeout"))
    return {
        "label": "Change Timeout" if active else "Timeout Player",
        "show_remove": active,
    }


def _role_preferences_text(snapshot):
    roles = snapshot.get("roles", [])
    if not roles:
        return "No roles set."

    return "\n".join(
        f"**{index}.** {role}"
        for index, role in enumerate(roles, start=1)
    )


def _discord_identity_text(snapshot):
    display_name = snapshot.get("discord_name") or "Unknown"
    username = snapshot.get("discord_username")

    if not username:
        return display_name

    if username.casefold() == display_name.casefold():
        return display_name

    return f"{display_name} (@{username})"


def build_player_inspector_embed(snapshot):
    aliases = snapshot.get("aliases", [])
    aliases_text = ", ".join(aliases) if aliases else "None"
    weight = snapshot["hidden_weight"]
    weight_text = f"{weight:+d}" if isinstance(weight, int) else str(weight)

    embed = discord.Embed(
        title=f"Player Inspector — {snapshot['ign']}",
        description=(
            f"**Discord:** {_discord_identity_text(snapshot)}\n"
            f"**Discord ID:** `{snapshot['user_id']}`\n"
            f"**Current status:** {snapshot['current_status']}"
        ),
    )

    embed.add_field(
        name="Registration",
        value=(
            f"**Current IGN:** {snapshot['ign']}\n"
            f"**Previous IGNs:** {aliases_text}"
        ),
        inline=False,
    )

    embed.add_field(
        name="Role Preferences",
        value=_role_preferences_text(snapshot),
        inline=False,
    )

    embed.add_field(
        name="Admin / Balance",
        value=(
            f"**Hidden weight:** {weight_text}\n"
            f"**Has played backline:** "
            f"{'Yes' if snapshot['has_played_backline'] else 'No'}\n"
            f"**Lobby timeout:** {snapshot['timeout_summary']}"
        ),
        inline=False,
    )

    embed.add_field(
        name="Draft Stats",
        value=(
            f"**Drafts played:** {snapshot['drafts_played']}\n"
            f"**Team A:** {snapshot['team_a_assignments']}\n"
            f"**Team B:** {snapshot['team_b_assignments']}\n"
            f"**Captain:** {snapshot['times_captain']} "
            f"({snapshot['captain_rate']}%)\n"
            f"**Primary preference:** {snapshot['primary_assignments']} "
            f"({snapshot['primary_hit_rate']}%)\n"
            f"**Off-role:** {snapshot['off_role_assignments']} "
            f"({snapshot['off_role_rate']}%)\n"
            f"**Last draft:** {_discord_timestamp(snapshot['last_draft_at'])}"
        ),
        inline=False,
    )

    embed.add_field(
        name="Assigned Role History",
        value=_role_history_text(snapshot),
        inline=False,
    )

    embed.add_field(
        name="Recent Draft Activity",
        value=_recent_activity_text(snapshot),
        inline=False,
    )

    embed.set_footer(text="Admin-only player information")
    return embed



class PlayerInspectorView(discord.ui.View):
    def __init__(self, guild_id, user_id, is_admin_check):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.user_id = user_id
        self.is_admin_check = is_admin_check

        self.timeout_button = discord.ui.Button(
            label="Timeout Player",
            style=discord.ButtonStyle.danger,
            row=1,
        )
        self.timeout_button.callback = self._timeout_button_callback
        self.add_item(self.timeout_button)

        self.remove_timeout_button = discord.ui.Button(
            label="Remove Timeout",
            style=discord.ButtonStyle.success,
            row=1,
        )
        self.remove_timeout_button.callback = self._remove_timeout_button_callback

        snapshot = inspector_service.build_player_snapshot(
            self.guild_id,
            self.user_id,
        )
        self._sync_timeout_controls(snapshot)

    def _sync_timeout_controls(self, snapshot):
        state = _timeout_control_state(snapshot)
        self.timeout_button.label = state["label"]

        remove_is_present = self.remove_timeout_button in self.children
        if state["show_remove"] and not remove_is_present:
            self.add_item(self.remove_timeout_button)
        elif not state["show_remove"] and remove_is_present:
            self.remove_item(self.remove_timeout_button)

    async def _timeout_button_callback(self, interaction: discord.Interaction):
        if not await self._ensure_admin(interaction):
            return

        snapshot = inspector_service.build_player_snapshot(
            self.guild_id,
            self.user_id,
        )
        if not snapshot:
            await interaction.response.send_message(
                "That player is no longer registered.",
                ephemeral=True,
            )
            return

        # Import lazily so the inspector can reuse the existing timeout picker
        # without introducing a module-load cycle through the views facade.

        action = "change the timeout for" if snapshot.get("timeout") else "timeout"
        await interaction.response.send_message(
            f"Choose how long to {action} **{snapshot['ign']}** from draft lobbies. "
            "Use **Refresh** on the inspector after choosing a duration.",
            view=TimeoutDurationView(
                svc.get_view_context(self.guild_id),
                self.user_id,
            ),
            ephemeral=True,
        )

    async def _remove_timeout_button_callback(self, interaction: discord.Interaction):
        if not await self._ensure_admin(interaction):
            return

        snapshot = inspector_service.build_player_snapshot(
            self.guild_id,
            self.user_id,
        )
        if not snapshot:
            await interaction.response.send_message(
                "That player is no longer registered.",
                ephemeral=True,
            )
            return

        ign = snapshot["ign"]
        removed = moderation_service.remove_lobby_timeout(
            self.guild_id,
            self.user_id,
        )

        refreshed = inspector_service.build_player_snapshot(
            self.guild_id,
            self.user_id,
        )
        self._sync_timeout_controls(refreshed)

        if not removed:
            await interaction.response.edit_message(
                embed=build_player_inspector_embed(refreshed),
                view=self,
            )
            await interaction.followup.send(
                f"**{ign}** does not have an active draft lobby timeout.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            embed=build_player_inspector_embed(refreshed),
            view=self,
        )
        await interaction.followup.send(
            f"Removed the draft lobby timeout for **{ign}**.",
            ephemeral=True,
        )

    async def _ensure_admin(self, interaction):
        if self.is_admin_check(interaction):
            return True

        await interaction.response.send_message(
            "Only draft admins can use the player inspector.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary)
    async def refresh_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if not await self._ensure_admin(interaction):
            return

        snapshot = inspector_service.build_player_snapshot(
            self.guild_id,
            self.user_id,
        )
        if not snapshot:
            await interaction.response.send_message(
                "That player is no longer registered.",
                ephemeral=True,
            )
            return

        self._sync_timeout_controls(snapshot)
        await interaction.response.edit_message(
            embed=build_player_inspector_embed(snapshot),
            view=self,
        )

    @discord.ui.button(
        label="Recent Activity",
        style=discord.ButtonStyle.primary,
    )
    async def recent_activity_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if not await self._ensure_admin(interaction):
            return

        snapshot = inspector_service.build_player_snapshot(
            self.guild_id,
            self.user_id,
        )
        if not snapshot:
            await interaction.response.send_message(
                "That player is no longer registered.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            _recent_activity_text(snapshot),
            ephemeral=True,
        )


# ========================================================================
# DRAFT HISTORY UI
# ========================================================================

from draft_service import HISTORY_PAGE_SIZE, build_draft_detail_embed, build_history_embed, format_mode, get_history_page
import discord



class DraftHistorySelect(discord.ui.Select):
    def __init__(self, history_view):
        self.history_view = history_view
        super().__init__(
            placeholder="Select a draft to inspect",
            min_values=1,
            max_values=1,
            options=self._build_options(),
            row=0,
        )

    def _build_options(self):
        options = []
        for draft in self.history_view.page_data["drafts"]:
            draft_id = draft["draft_id"]
            created_at = int(draft["created_at"])
            options.append(
                discord.SelectOption(
                    label=f"#{draft_id} — {format_mode(draft['mode'])}"[:100],
                    description=f"Discord timestamp: {created_at}"[:100],
                    value=str(draft_id),
                    default=draft_id == self.history_view.selected_draft_id,
                )
            )
        return options

    def refresh_options(self):
        self.options = self._build_options()

    async def callback(self, interaction: discord.Interaction):
        self.history_view.selected_draft_id = int(self.values[0])
        self.refresh_options()
        await interaction.response.edit_message(
            embed=self.history_view.build_embed(),
            view=self.history_view,
        )


class DraftHistoryView(discord.ui.View):
    def __init__(self, guild_id, page=0, page_size=HISTORY_PAGE_SIZE, selected_draft_id=None):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.page_size = page_size
        self.page_data = get_history_page(guild_id, page, page_size)

        draft_ids = [draft["draft_id"] for draft in self.page_data["drafts"]]
        if selected_draft_id in draft_ids:
            self.selected_draft_id = selected_draft_id
        else:
            self.selected_draft_id = draft_ids[0] if draft_ids else None

        self.selector = None
        if self.page_data["drafts"]:
            self.selector = DraftHistorySelect(self)
            self.add_item(self.selector)

        self._sync_buttons()

    def _sync_buttons(self):
        self.previous_button.disabled = self.page_data["page"] <= 0
        self.next_button.disabled = self.page_data["page"] >= self.page_data["total_pages"] - 1
        self.view_draft_button.disabled = self.selected_draft_id is None

    def _load_page(self, page):
        self.page_data = get_history_page(self.guild_id, page, self.page_size)
        draft_ids = [draft["draft_id"] for draft in self.page_data["drafts"]]
        self.selected_draft_id = draft_ids[0] if draft_ids else None

        if self.selector:
            self.selector.refresh_options()

        self._sync_buttons()

    def build_embed(self):
        return build_history_embed(self.page_data, self.selected_draft_id)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, row=1)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._load_page(self.page_data["page"] - 1)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="View Draft", style=discord.ButtonStyle.primary, row=1)
    async def view_draft_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.selected_draft_id is None:
            await interaction.response.send_message("No draft is selected.", ephemeral=True)
            return

        embed = build_draft_detail_embed(self.guild_id, self.selected_draft_id)
        if embed is None:
            await interaction.response.send_message(
                "That draft could not be found.",
                ephemeral=True,
            )
            return

        detail_view = DraftDetailView(
            guild_id=self.guild_id,
            page=self.page_data["page"],
            page_size=self.page_size,
            selected_draft_id=self.selected_draft_id,
        )
        await interaction.response.edit_message(embed=embed, view=detail_view)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._load_page(self.page_data["page"] + 1)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class DraftDetailView(discord.ui.View):
    def __init__(self, guild_id, page, page_size, selected_draft_id):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.page = page
        self.page_size = page_size
        self.selected_draft_id = selected_draft_id

    @discord.ui.button(label="Back to History", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        history_view = DraftHistoryView(
            guild_id=self.guild_id,
            page=self.page,
            page_size=self.page_size,
            selected_draft_id=self.selected_draft_id,
        )
        await interaction.response.edit_message(
            embed=history_view.build_embed(),
            view=history_view,
        )
