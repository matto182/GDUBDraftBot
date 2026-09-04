import discord
from discord import app_commands

from config import ROLES, BACKLINE_ROLES
from database import save_player, get_player_stats, mark_player_has_played_backline

import draft_service as svc
from player_stats_service import (
    format_priority_usage,
    format_role_frequency,
    summarize_player_stats,
)


def register_player_commands(bot):
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
        summary = summarize_player_stats(stats_data)

        embed = discord.Embed(title=f"{player_data['ign']} Draft Stats", color=discord.Color.blue())
        embed.add_field(name="Discord", value=discord_name, inline=False)
        embed.add_field(name="Drafts Played", value=str(summary["drafts_played"]), inline=True)
        embed.add_field(name="Times Captain", value=str(summary["times_captain"]), inline=True)
        embed.add_field(name="Captain Rate", value=f"{summary['captain_rate']:.1f}%", inline=True)
        embed.add_field(
            name="Preferred Role Hit Rate",
            value=f"{summary['preferred_role_hit_rate']:.1f}%",
            inline=True,
        )
        embed.add_field(
            name="Off-Role Rate",
            value=f"{summary['off_role_rate']:.1f}%",
            inline=True,
        )
        embed.add_field(name="Role Frequency", value=format_role_frequency(summary), inline=False)
        embed.add_field(name="Role Priority Usage", value=format_priority_usage(summary), inline=False)
        embed.set_footer(
            text="Preferred Role Hit Rate counts assignments to any registered role preference."
        )
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="name", description="Register your Guild Wars 1 in-game name.")
    @app_commands.describe(ign="Your in-game name")
    async def name(interaction: discord.Interaction, ign: str):
        user_id = interaction.user.id
        if user_id not in svc.players:
            svc.players[user_id] = {
                "discord_name": interaction.user.display_name,
                "ign": ign,
                "roles": [],
                "has_played_backline": False,
            }
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

        if set(chosen) & BACKLINE_ROLES:
            svc.players[user_id]["has_played_backline"] = True
            mark_player_has_played_backline(user_id)

        save_player(
            user_id,
            interaction.user.display_name,
            svc.players[user_id]["ign"],
            svc.players[user_id]["roles"],
            has_played_backline=svc.players[user_id].get("has_played_backline", False),
        )
        await interaction.response.send_message(f"Your roles are now: **{', '.join(chosen)}**.", ephemeral=True)
