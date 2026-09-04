import time

import discord

from config import BACKLINE_ROLES
from database import save_player
from state import get_state
from admin_panel_views import AdminPanelView, build_admin_panel_embed

import draft_service as svc


def register_admin_commands(bot):
    @bot.tree.command(name="wipelobby", description="Completely wipe the lobby.")
    async def wipelobby(interaction: discord.Interaction):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message("Only draft admins can wipe the lobby.", ephemeral=True)
            return

        await svc.wipe_lobby(interaction)

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
                "roles": roles,
                "has_played_backline": bool(set(roles) & BACKLINE_ROLES),
            }
            save_player(fake_id, f"TestUser{i+1}", ign, roles)
            state.lobby.append(fake_id)

        state.last_signup_time = time.time()
        svc.save_lobby_state(guild_id)

        await interaction.response.send_message("Test lobby filled with 16 players.", ephemeral=True)
        await svc.post_new_draft_board(guild_id)

    @bot.tree.command(name="adminboard", description="Open the admin draft controls.")
    async def adminboard(interaction: discord.Interaction):
        svc.load_lobby_state(interaction.guild.id)
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message("Only draft admins can use this.", ephemeral=True)
            return

        await interaction.response.send_message(
            embed=build_admin_panel_embed(interaction.guild.id),
            view=AdminPanelView(interaction.guild.id),
            ephemeral=True
        )
