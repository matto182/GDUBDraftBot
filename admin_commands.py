import time

import discord

from config import BACKLINE_ROLES
from database import save_player
from state import get_state
from admin_panel_views import AdminPanelView, build_admin_panel_embed

import draft_service as svc
from database import get_guild_config, save_board_message_id
from guild_repository import is_board_hidden, set_board_hidden


def register_admin_commands(bot):
    @bot.tree.command(name="hidelobby", description="Hide the live draft board until shown again.")
    async def hidelobby(interaction: discord.Interaction):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message("Draft admins only.", ephemeral=True)
            return
        config = get_guild_config(interaction.guild.id) or {}
        set_board_hidden(interaction.guild.id, True)
        channel = interaction.guild.get_channel(config.get("draft_channel_id"))
        if channel and config.get("board_message_id"):
            try:
                await (await channel.fetch_message(config["board_message_id"])).delete()
            except discord.NotFound:
                pass
            except discord.HTTPException:
                await interaction.response.send_message("Hidden state saved, but I could not delete the existing board. Check channel permissions.", ephemeral=True)
                return
        save_board_message_id(interaction.guild.id, None)
        await interaction.response.send_message("Draft board hidden until /showlobby. Players remain in the lobby.", ephemeral=True)

    @bot.tree.command(name="showlobby", description="Show the live draft board again.")
    async def showlobby(interaction: discord.Interaction):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message("Draft admins only.", ephemeral=True)
            return
        if not is_board_hidden(interaction.guild.id):
            await interaction.response.send_message("The draft board is already visible.", ephemeral=True)
            return
        set_board_hidden(interaction.guild.id, False)
        await interaction.response.defer(ephemeral=True)
        try:
            await svc.post_new_draft_board(interaction.guild.id)
        except discord.HTTPException:
            set_board_hidden(interaction.guild.id, True)
            await interaction.followup.send("Could not post the board; it remains hidden.", ephemeral=True)
            return
        await interaction.followup.send("Draft board shown.", ephemeral=True)

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

        await interaction.response.send_message("Test lobby filled with 15 players. Sign up with a real account to test the 16/16 lobby notification.", ephemeral=True)
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
