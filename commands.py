import time

import discord
from discord import app_commands

from config import ROLES
from database import save_player, get_player_stats
from state import get_state
from views import DraftBoardView, AdminDraftView, CaptainPickView, SetupWizardView

import draft_service as svc


def register_commands(bot):
    @bot.tree.command(name="wipelobby", description="Completely wipe the lobby.")
    async def wipelobby(interaction: discord.Interaction):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message("Only draft admins can wipe the lobby.", ephemeral=True)
            return

        await svc.wipe_lobby(interaction)

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

    @bot.tree.command(name="subnext", description="Move the next waiting room player into the lobby.")
    async def subnext(interaction: discord.Interaction):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message("Only draft admins can use this.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        state = get_state(guild_id)

        if not state.waiting_room:
            await interaction.response.send_message("Waiting room is empty.", ephemeral=True)
            return

        if len(state.lobby) >= 16:
            await interaction.response.send_message("Lobby is already full. Kick or drop someone first.", ephemeral=True)
            return

        next_player = state.waiting_room.pop(0)
        state.lobby.append(next_player)
        svc.save_lobby_state(guild_id)

        await interaction.response.send_message(
            f"Moved {svc.player_label(guild_id, next_player)} from waiting room into the lobby.",
            ephemeral=True
        )
        await svc.post_new_draft_board(guild_id)

    @bot.tree.command(name="filltest", description="Fill lobby with test players.")
    async def filltest(interaction: discord.Interaction):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message("Only draft admins can use this.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        state = get_state(guild_id)

        state.lobby.clear()
        state.waiting_room.clear()
        state.votes.clear()
        state.captain_volunteers.clear()
        state.draft_result = None
        state.captain_draft = None
        state.final_team_a = []
        state.final_team_b = []

        test_lobby = [
            ("Player1",  ["Frontline", "Midline"]),
            ("Player2",  ["Frontline"]),
            ("Player3",  ["Midline", "Frontline"]),
            ("Player4",  ["Midline"]),
            ("Player5",  ["Prot Monk", "Heal Monk"]),
            ("Player6",  ["Heal Monk", "Prot Monk"]),
            ("Player7",  ["8 Support", "Midline"]),
            ("Player8",  ["Frontline", "Midline"]),
            ("Player9",  ["Frontline", "Midline"]),
            ("Player10", ["Frontline"]),
            ("Player11", ["Midline", "Frontline"]),
            ("Player12", ["Midline"]),
            ("Player13", ["Prot Monk", "Heal Monk"]),
            ("Player14", ["Heal Monk", "Prot Monk"]),
            ("Player15", ["8 Support", "Midline"]),
            ("Player16", ["Frontline", "Midline"]),
        ]

        for i, (ign, roles) in enumerate(test_lobby):
            fake_id = 100000 + i
            svc.players[fake_id] = {
                "discord_name": f"TestUser{i+1}",
                "ign": ign,
                "roles": roles
            }
            save_player(fake_id, f"TestUser{i+1}", ign, roles)
            state.lobby.append(fake_id)

        state.last_signup_time = time.time()
        svc.save_lobby_state(guild_id)

        await interaction.response.send_message("Test lobby filled with 16 players.", ephemeral=True)
        await svc.post_new_draft_board(guild_id)

    @bot.tree.command(name="stats", description="View player draft stats.")
    @app_commands.describe(player="Player IGN")
    async def stats(interaction: discord.Interaction, player: str = None):
        guild_id = interaction.guild.id
        target_id = interaction.user.id

        if player:
            found = False
            for user_id, data in svc.players.items():
                if data["ign"].lower() == player.lower():
                    target_id = user_id
                    found = True
                    break
            if not found:
                await interaction.response.send_message(f"No player found with IGN `{player}`.", ephemeral=True)
                return

        if target_id not in svc.players:
            await interaction.response.send_message("Player data not found.", ephemeral=True)
            return

        player_data = svc.players[target_id]
        member = interaction.guild.get_member(target_id)
        discord_name = f"{member.display_name} (@{member.name})" if member else player_data["discord_name"]
        stats_data = get_player_stats(guild_id, target_id)

        roles_text = ""
        if stats_data["roles"]:
            for role, count in stats_data["roles"]:
                roles_text += f"{role}: {count}\n"
        else:
            roles_text = "No role data."

        priority_map = {1: "Primary", 2: "Secondary", 3: "Tertiary", 4: "Fourth", 999: "Fill/Off-role"}
        priority_text = ""
        if stats_data["priority_stats"]:
            for priority, count in stats_data["priority_stats"]:
                label = priority_map.get(priority, f"Priority {priority}")
                priority_text += f"{label}: {count}\n"
        else:
            priority_text = "No assignment data."

        embed = discord.Embed(title=f"{player_data['ign']} Draft Stats", color=discord.Color.blue())
        embed.add_field(name="Discord", value=discord_name, inline=False)
        embed.add_field(name="Drafts Played", value=str(stats_data["drafts_played"]), inline=True)
        embed.add_field(name="Times Captain", value=str(stats_data["times_captain"]), inline=True)
        embed.add_field(name="Roles Played", value=roles_text, inline=False)
        embed.add_field(name="Role Priority Usage", value=priority_text, inline=False)
        await interaction.response.send_message(embed=embed)

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

    @bot.tree.command(name="adminboard", description="Open the admin draft controls.")
    async def adminboard(interaction: discord.Interaction):
        svc.load_lobby_state(interaction.guild.id)
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message("Only draft admins can use this.", ephemeral=True)
            return

        await interaction.response.send_message(
            "Admin draft controls:",
            view=AdminDraftView(svc.get_view_context(interaction.guild.id)),
            ephemeral=True
        )

    @bot.tree.command(name="resetdraft", description="Reset only the draft result and refill lobby from waiting room.")
    async def resetdraft(interaction: discord.Interaction):
        svc.load_lobby_state(interaction.guild.id)
        await svc.reset_draft_only(interaction)

    @bot.tree.command(name="name", description="Register your Guild Wars 1 in-game name.")
    @app_commands.describe(ign="Your in-game name")
    async def name(interaction: discord.Interaction, ign: str):
        user_id = interaction.user.id
        if user_id not in svc.players:
            svc.players[user_id] = {"discord_name": interaction.user.display_name, "ign": ign, "roles": []}
        else:
            svc.players[user_id]["ign"] = ign

        save_player(user_id, interaction.user.display_name, svc.players[user_id]["ign"], svc.players[user_id]["roles"])
        await interaction.response.send_message(f"Registered your IGN as **{ign}**.", ephemeral=True)

    @bot.tree.command(name="role", description="Set the roles you can play.")
    @app_commands.describe(
        role1="Primary role",
        role2="Optional role",
        role3="Optional role",
        role4="Optional role",
        role5="Optional role",
    )
    @app_commands.choices(
        role1=[app_commands.Choice(name=r, value=r) for r in ROLES],
        role2=[app_commands.Choice(name=r, value=r) for r in ROLES],
        role3=[app_commands.Choice(name=r, value=r) for r in ROLES],
        role4=[app_commands.Choice(name=r, value=r) for r in ROLES],
        role5=[app_commands.Choice(name=r, value=r) for r in ROLES],
    )
    async def role(
        interaction: discord.Interaction,
        role1: app_commands.Choice[str],
        role2: app_commands.Choice[str] = None,
        role3: app_commands.Choice[str] = None,
        role4: app_commands.Choice[str] = None,
        role5: app_commands.Choice[str] = None,
    ):
        user_id = interaction.user.id
        if user_id not in svc.players:
            await interaction.response.send_message("Use `/name` first.", ephemeral=True)
            return

        chosen = [role1.value]
        for r in [role2, role3, role4, role5]:
            if r and r.value not in chosen:
                chosen.append(r.value)

        svc.players[user_id]["roles"] = chosen
        save_player(user_id, interaction.user.display_name, svc.players[user_id]["ign"], svc.players[user_id]["roles"])
        await interaction.response.send_message(f"Your roles are now: **{', '.join(chosen)}**.", ephemeral=True)

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
