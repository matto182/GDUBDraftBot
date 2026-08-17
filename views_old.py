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

        if len(ctx.lobby) != 16:
            await interaction.response.send_message(
                f"Need exactly 16 players. Current: {len(ctx.lobby)}/16",
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
            "Admin draft controls:",
            view=AdminDraftView(ctx),
            ephemeral=True
        )

    @discord.ui.button(label="Status", style=discord.ButtonStyle.secondary, custom_id="draft_status")
    async def status_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ctx = self.ctx_factory(interaction.guild.id)
        await ctx.show_status(interaction)

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


class AdminDraftView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.add_item(KickPlayerSelect(ctx))

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


class CaptainPickSelect(discord.ui.Select):
    def __init__(self, ctx):
        self.ctx = ctx
        options = []
        captain_draft = ctx.get_captain_draft()

        if captain_draft:
            for user_id in captain_draft.available:
                p = ctx.players[user_id]
                roles = ", ".join(p["roles"])

                options.append(
                    discord.SelectOption(
                        label=p["ign"][:100],
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
            f"Draft board channel saved: {channel.mention}\n\nNow select Team A voice channel.",
            ephemeral=True,
            view=SetupTeamAVoiceView(self.ctx)
        )


class SetupTeamAVoiceView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx = ctx

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Step 2: Select Team A voice channel",
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
        placeholder="Step 3: Select Team B voice channel",
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
        placeholder="Step 4: Select Draft Admin role",
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
            f"Draft Admin role saved: {role.mention}\n\nSetup complete. Posting draft board.",
            ephemeral=True
        )

        await self.ctx.post_new_draft_board(interaction.guild.id)