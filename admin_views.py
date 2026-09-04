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
