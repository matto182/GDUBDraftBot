import discord
from discord import app_commands

from state import get_state
from views import DraftBoardView, CaptainPickView

import draft_service as svc


def register_lobby_commands(bot):
    @bot.tree.command(name="pickpanel", description="Open the captain pick panel.")
    async def pickpanel(interaction: discord.Interaction):
        state = get_state(interaction.guild.id)
        captain_draft = state.captain_draft

        if not captain_draft:
            await interaction.response.send_message("No captain draft is active.", ephemeral=True)
            return

        if interaction.user.id != captain_draft.current_picker():
            await interaction.response.send_message(
                f"It is currently {svc.player_label(interaction.guild.id, captain_draft.current_picker())}'s pick.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Choose a player to pick:",
            view=CaptainPickView(svc.get_view_context(interaction.guild.id)),
            ephemeral=True
        )

    @bot.tree.command(name="resetdraft", description="Reset only the draft result and refill lobby from waiting room.")
    async def resetdraft(interaction: discord.Interaction):
        svc.load_lobby_state(interaction.guild.id)
        await svc.reset_draft_only(interaction)

    @bot.tree.command(name="signup", description="Join the GvG draft lobby.")
    async def signup(interaction: discord.Interaction):
        await svc.signup_player(interaction)

    @bot.tree.command(name="drop", description="Leave the GvG draft lobby.")
    async def drop(interaction: discord.Interaction):
        await svc.drop_player(interaction)

    @bot.tree.command(name="vote", description="Vote for captain mode or random draft.")
    @app_commands.describe(mode="Choose draft mode")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Captain Mode", value="captain"),
        app_commands.Choice(name="Random Draft", value="random"),
    ])
    async def vote(interaction: discord.Interaction, mode: app_commands.Choice[str]):
        await svc.vote_player(interaction, mode.value, mode.name)

    @bot.tree.command(name="captain", description="Volunteer to be a captain.")
    async def captain(interaction: discord.Interaction):
        await svc.volunteer_captain(interaction)

    @bot.tree.command(name="lobby", description="Show the current GvG draft lobby.")
    async def lobby_command(interaction: discord.Interaction):
        await svc.show_status(interaction)

    @bot.tree.command(name="draftstatus", description="Show current votes and captain volunteers.")
    async def draftstatus(interaction: discord.Interaction):
        await svc.show_status(interaction)

    @bot.tree.command(name="draftboard", description="Post the GvG draft board with buttons.")
    async def draftboard(interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=svc.build_draft_board_embed(interaction.guild.id),
            view=DraftBoardView(svc.get_view_context)
        )

    @bot.tree.command(name="startdraft", description="Start the draft once the lobby has 16 players.")
    async def startdraft(interaction: discord.Interaction):
        await svc.run_startdraft(interaction)

    @bot.tree.command(name="resetlobby", description="Reset the lobby.")
    async def resetlobby(interaction: discord.Interaction):
        guild_id = interaction.guild.id
        state = get_state(guild_id)

        state.captain_draft = None
        state.draft_result = None
        state.final_team_a = []
        state.final_team_b = []
        state.lobby.clear()
        state.waiting_room.clear()
        state.votes.clear()
        state.captain_volunteers.clear()
        state.last_signup_time = None

        svc.save_lobby_state(guild_id)

        await interaction.response.send_message("Lobby reset. Posting a new draft board.", ephemeral=True)
        await svc.post_new_draft_board(guild_id)
