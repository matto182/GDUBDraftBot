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
        placeholder="Step 5: Select Owner role",
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
