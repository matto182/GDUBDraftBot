import discord

from admin_views import AdminDraftView
from captain_views import CaptainPickView

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
