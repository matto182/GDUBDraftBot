"""All slash-command registration for GDUB Draft Bot."""

import draft_service as svc


# ========================================================================
# PLAYER COMMANDS
# ========================================================================

from draft_service import PRIORITY_LABELS, format_priority_usage, format_role_frequency, get_player_aliases, record_name_change, resolve_alias_user_id, summarize_player_stats
import discord
from discord import app_commands

from config import ROLES, BACKLINE_ROLES
from database import save_player, get_player_stats, mark_player_has_played_backline
from views import SetNameModal

import draft_service as svc


def register_player_commands(bot):
    @bot.tree.command(name="stats", description="View player draft stats.")
    @app_commands.describe(player="Player IGN")
    async def stats(interaction: discord.Interaction, player: str = None):
        guild_id = interaction.guild.id
        target_id = interaction.user.id

        if player:
            found = False
            for user_id, data in svc.players.items():
                if data["ign"].casefold() == player.casefold():
                    target_id = user_id
                    found = True
                    break

            if not found:
                alias_user_id = resolve_alias_user_id(player)
                if alias_user_id in svc.players:
                    target_id = alias_user_id
                    found = True

            if not found:
                await interaction.response.send_message(
                    f"No player found with current or previous IGN `{player}`.",
                    ephemeral=True,
                )
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

    async def save_name_from_modal(interaction: discord.Interaction, ign: str):
        user_id = interaction.user.id

        if user_id not in svc.players:
            svc.players[user_id] = {
                "discord_name": interaction.user.display_name,
                "ign": ign,
                "roles": [],
                "has_played_backline": False,
            }
        else:
            previous_ign = svc.players[user_id]["ign"]
            record_name_change(user_id, previous_ign, ign)
            svc.players[user_id]["ign"] = ign

        save_player(
            user_id,
            interaction.user.display_name,
            svc.players[user_id]["ign"],
            svc.players[user_id]["roles"],
            has_played_backline=svc.players[user_id].get("has_played_backline", False),
        )
        await interaction.response.send_message(
            f"Registered your IGN as **{ign}**.",
            ephemeral=True,
        )

    @bot.tree.command(name="name", description="Register or change your Guild Wars 1 in-game name.")
    async def name(interaction: discord.Interaction):
        current_ign = None
        player = svc.players.get(interaction.user.id)
        if player:
            current_ign = player.get("ign")

        await interaction.response.send_modal(
            SetNameModal(
                save_callback=save_name_from_modal,
                current_ign=current_ign,
            )
        )

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


# ========================================================================
# LOBBY COMMANDS
# ========================================================================

from database import is_board_hidden
from views import DraftBoardView, CaptainPickView
import discord
from discord import app_commands

from draft_service import get_state

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
        if is_board_hidden(interaction.guild.id):
            await interaction.response.send_message("The draft board is hidden. A draft admin can use /showlobby.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=svc.build_draft_board_embed(interaction.guild.id),
            view=DraftBoardView(svc.get_view_context)
        )

    @bot.tree.command(name="lobbysize", description="Change the active draft lobby size (2-16).")
    @app_commands.describe(size="Number of players required to fill and start the lobby")
    async def lobbysize(interaction: discord.Interaction, size: int):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can change the lobby size.",
                ephemeral=True
            )
            return

        if size < 2 or size > 16:
            await interaction.response.send_message(
                "Lobby size must be between 2 and 16 players.",
                ephemeral=True
            )
            return

        svc.load_lobby_state(interaction.guild.id)
        await svc.set_lobby_size(interaction, size)

    @bot.tree.command(name="startdraft", description="Start the draft once the configured lobby is full.")
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


# ========================================================================
# ADMIN COMMANDS
# ========================================================================

from database import is_board_hidden, set_board_hidden
from views import AdminPanelView, build_admin_panel_embed
import time

import discord

from config import BACKLINE_ROLES
from database import save_player
from draft_service import get_state

import draft_service as svc
from database import get_guild_config, save_board_message_id


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


# ========================================================================
# ADMIN PANEL COMMAND
# ========================================================================

from views import AdminPanelView, build_admin_panel_embed
import discord

import draft_service as svc


def register_admin_panel_commands(bot):
    @bot.tree.command(
        name="admin",
        description="Open the draft admin control panel.",
    )
    async def admin(interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True,
            )
            return

        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can use the admin panel.",
                ephemeral=True,
            )
            return

        svc.load_lobby_state(interaction.guild.id)

        await interaction.response.send_message(
            embed=build_admin_panel_embed(interaction.guild.id),
            view=AdminPanelView(interaction.guild.id),
            ephemeral=True,
        )


# ========================================================================
# MODERATION COMMANDS
# ========================================================================

from views import TimeoutDurationView
import discord
from discord import app_commands

from database import remove_lobby_ban, get_active_lobby_bans
from draft_service import get_state

import draft_service as svc


def register_moderation_commands(bot):
    async def timeout_player_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ):
        if interaction.guild is None:
            return []

        current_lower = current.casefold().strip()
        state = get_state(interaction.guild.id)

        eligible_user_ids = {
            member.id
            for member in interaction.guild.members
        }
        eligible_user_ids.update(state.lobby)
        eligible_user_ids.update(state.waiting_room)

        matches = []

        for user_id, data in svc.players.items():
            ign = data.get("ign")

            if not ign or user_id not in eligible_user_ids:
                continue

            if current_lower and current_lower not in ign.casefold():
                continue

            matches.append((ign, user_id))

        matches.sort(key=lambda item: item[0].casefold())

        return [
            app_commands.Choice(
                name=ign[:100],
                value=str(user_id),
            )
            for ign, user_id in matches[:25]
        ]

    @bot.tree.command(name="timeout", description="Timeout a player from draft lobbies.")
    @app_commands.describe(player="Player IGN")
    @app_commands.autocomplete(player=timeout_player_autocomplete)
    async def timeout(interaction: discord.Interaction, player: str):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can timeout players.",
                ephemeral=True,
            )
            return

        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True,
            )
            return

        state = get_state(interaction.guild.id)

        eligible_user_ids = {
            member.id
            for member in interaction.guild.members
        }
        eligible_user_ids.update(state.lobby)
        eligible_user_ids.update(state.waiting_room)

        user_id = None

        try:
            candidate_id = int(player)

            if candidate_id in eligible_user_ids and candidate_id in svc.players:
                user_id = candidate_id

        except ValueError:
            exact_matches = [
                candidate_id
                for candidate_id, data in svc.players.items()
                if candidate_id in eligible_user_ids
                and data.get("ign", "").casefold() == player.casefold()
            ]

            if len(exact_matches) == 1:
                user_id = exact_matches[0]

            elif len(exact_matches) > 1:
                await interaction.response.send_message(
                    f"More than one player in this server uses the IGN **{player}**. "
                    "Choose one from autocomplete.",
                    ephemeral=True,
                )
                return

        if user_id is None:
            await interaction.response.send_message(
                f"No registered player in this server found with IGN **{player}**.",
                ephemeral=True,
            )
            return

        ign = svc.players[user_id]["ign"]

        await interaction.response.send_message(
            f"Choose how long to timeout **{ign}** from draft lobbies:",
            view=TimeoutDurationView(
                svc.get_view_context(interaction.guild.id),
                user_id,
            ),
            ephemeral=True,
        )

    async def untimeout_player_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ):
        active_bans = get_active_lobby_bans(interaction.guild.id)
        current_lower = current.lower().strip()
        choices = []

        for ban in active_bans:
            user_id = ban["user_id"]
            player = svc.players.get(user_id)

            if not player or not player.get("ign"):
                continue

            ign = player["ign"]

            if current_lower and current_lower not in ign.lower():
                continue

            choices.append(
                app_commands.Choice(
                    name=ign[:100],
                    value=str(user_id),
                )
            )

            if len(choices) >= 25:
                break

        return choices

    @bot.tree.command(name="untimeout", description="Remove a player's draft lobby timeout.")
    @app_commands.describe(player="Player IGN")
    @app_commands.autocomplete(player=untimeout_player_autocomplete)
    async def untimeout(interaction: discord.Interaction, player: str):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can remove lobby timeouts.",
                ephemeral=True,
            )
            return

        user_id = None

        try:
            user_id = int(player)
        except ValueError:
            for candidate_id, data in svc.players.items():
                if data.get("ign", "").lower() == player.lower():
                    user_id = candidate_id
                    break

        if user_id is None:
            await interaction.response.send_message(
                f"No registered player found with IGN **{player}**.",
                ephemeral=True,
            )
            return

        player_data = svc.players.get(user_id)
        ign = player_data["ign"] if player_data and player_data.get("ign") else "Unknown player"

        removed = remove_lobby_ban(interaction.guild.id, user_id)

        if not removed:
            await interaction.response.send_message(
                f"**{ign}** does not have an active draft lobby timeout.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Removed the draft lobby timeout for **{ign}**.",
            ephemeral=True,
        )

    @bot.tree.command(name="timeouts", description="Show active draft lobby timeouts.")
    async def timeouts(interaction: discord.Interaction):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can view lobby timeouts.",
                ephemeral=True,
            )
            return

        active_bans = get_active_lobby_bans(interaction.guild.id)

        if not active_bans:
            await interaction.response.send_message(
                "There are no active draft lobby timeouts.",
                ephemeral=True,
            )
            return

        lines = []

        for ban in active_bans:
            user_id = ban["user_id"]
            if user_id in svc.players and svc.players[user_id].get("ign"):
                name = f"**{svc.players[user_id]['ign']}**"
            else:
                name = "**Unknown player**"

            if ban["expires_at"] is None:
                duration = "**Permanent**"
            else:
                expires_timestamp = int(ban["expires_at"])
                remaining = svc.format_timeout_remaining(ban["expires_at"])
                duration = f"**{remaining}** remaining — <t:{expires_timestamp}:R>"

            lines.append(f"• {name} — {duration}")

        embed = discord.Embed(
            title="Active Draft Lobby Timeouts",
            description="\n".join(lines),
            color=discord.Color.orange(),
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


# ========================================================================
# PLAYER MANAGEMENT COMMANDS
# ========================================================================

import draft_service as player_management
from draft_service import (
    _find_admin_player,
    admin_registered_player_autocomplete,
    admin_signed_player_autocomplete,
    admin_waiting_player_autocomplete,
    admin_lobby_player_autocomplete,
)
import discord
from discord import app_commands

from draft_service import get_state

import draft_service as svc


async def _send_action_result(interaction, success, message):
    await interaction.response.send_message(message, ephemeral=True)

    if success:
        await svc.post_new_draft_board(interaction.guild.id)


def register_player_management_commands(bot):
    @bot.tree.command(name="addplayer", description="Manually add a registered player to the draft.")
    @app_commands.describe(player="IGN, Discord nickname, or username", location="Where to add the player")
    @app_commands.choices(location=[
        app_commands.Choice(name="Lobby", value="lobby"),
        app_commands.Choice(name="Waiting Room", value="waiting"),
    ])
    @app_commands.autocomplete(player=admin_registered_player_autocomplete)
    async def addplayer(
        interaction: discord.Interaction,
        player: str,
        location: app_commands.Choice[str],
    ):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can manage players.",
                ephemeral=True,
            )
            return

        user_id = _find_admin_player(interaction, player)

        if user_id is None:
            await interaction.response.send_message(
                f"No unique registered player in this server found for **{player}**.",
                ephemeral=True,
            )
            return

        success, message = player_management.add_player(
            interaction.guild.id,
            user_id,
            location.value,
        )
        await _send_action_result(interaction, success, message)

    @bot.tree.command(name="moveplayer", description="Move a signed player between lobby and waiting room.")
    @app_commands.describe(player="Player IGN", destination="Where to move the player")
    @app_commands.choices(destination=[
        app_commands.Choice(name="Lobby", value="lobby"),
        app_commands.Choice(name="Waiting Room", value="waiting"),
    ])
    @app_commands.autocomplete(player=admin_signed_player_autocomplete)
    async def moveplayer(
        interaction: discord.Interaction,
        player: str,
        destination: app_commands.Choice[str],
    ):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can manage players.",
                ephemeral=True,
            )
            return

        user_id = _find_admin_player(interaction, player)

        if user_id is None:
            await interaction.response.send_message(
                f"**{player}** is not currently signed up.",
                ephemeral=True,
            )
            return

        success, message = player_management.move_player(
            interaction.guild.id,
            user_id,
            destination.value,
        )
        await _send_action_result(interaction, success, message)

    @bot.tree.command(name="queue", description="Move a waiting-room player to a specific queue position.")
    @app_commands.describe(player="Waiting-room player IGN", position="New queue position, starting at 1")
    @app_commands.autocomplete(player=admin_waiting_player_autocomplete)
    async def queue(
        interaction: discord.Interaction,
        player: str,
        position: int,
    ):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can reorder the waiting room.",
                ephemeral=True,
            )
            return

        user_id = _find_admin_player(interaction, player)

        if user_id is None:
            await interaction.response.send_message(
                f"**{player}** is not currently in the waiting room.",
                ephemeral=True,
            )
            return

        success, message = player_management.set_queue_position(
            interaction.guild.id,
            user_id,
            position,
        )
        await _send_action_result(interaction, success, message)

    @bot.tree.command(name="swapplayers", description="Swap one lobby player with one waiting-room player.")
    @app_commands.describe(
        lobby_player="Player currently in the lobby",
        waiting_player="Player currently in the waiting room",
    )
    @app_commands.autocomplete(
        lobby_player=admin_lobby_player_autocomplete,
        waiting_player=admin_waiting_player_autocomplete,
    )
    async def swapplayers(
        interaction: discord.Interaction,
        lobby_player: str,
        waiting_player: str,
    ):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can manage players.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id
        state = get_state(guild_id)

        if state.captain_draft:
            await interaction.response.send_message(
                "You cannot swap active Captain Draft players.",
                ephemeral=True,
            )
            return

        lobby_id = _find_admin_player(interaction, lobby_player)
        waiting_id = _find_admin_player(interaction, waiting_player)

        if lobby_id is None or lobby_id not in state.lobby:
            await interaction.response.send_message(
                f"**{lobby_player}** is not currently in the lobby.",
                ephemeral=True,
            )
            return

        if waiting_id is None or waiting_id not in state.waiting_room:
            await interaction.response.send_message(
                f"**{waiting_player}** is not currently in the waiting room.",
                ephemeral=True,
            )
            return

        success, message = player_management.swap_players(
            guild_id,
            lobby_id,
            waiting_id,
        )
        await _send_action_result(interaction, success, message)


# ========================================================================
# PLAYER INSPECTOR COMMAND
# ========================================================================

import draft_service as inspector_service
from views import PlayerInspectorView, build_player_inspector_embed
import discord
from discord import app_commands

import draft_service as svc


async def player_inspector_autocomplete(
    interaction: discord.Interaction,
    current: str,
):
    if interaction.guild is None:
        return []

    ctx = svc.get_view_context(interaction.guild.id)
    if not ctx.is_draft_admin(interaction):
        return []

    choices = inspector_service.search_player_choices(current, limit=25)

    return [
        app_commands.Choice(
            name=f"{player['ign']} — {player['discord_name']}"[:100],
            value=str(player["user_id"]),
        )
        for player in choices
    ]


def register_player_inspector_commands(bot):
    @bot.tree.command(
        name="inspectplayer",
        description="View admin-only information about a registered draft player.",
    )
    @app_commands.describe(player="Current/previous IGN, Discord name, or ID")
    @app_commands.autocomplete(player=player_inspector_autocomplete)
    async def inspectplayer(
        interaction: discord.Interaction,
        player: str,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True,
            )
            return

        ctx = svc.get_view_context(interaction.guild.id)

        if not ctx.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can use the player inspector.",
                ephemeral=True,
            )
            return

        record = inspector_service.resolve_player(player)
        if not record:
            await interaction.response.send_message(
                "No registered player matched that current/previous IGN, Discord name, or ID.",
                ephemeral=True,
            )
            return

        snapshot = inspector_service.build_player_snapshot(
            interaction.guild.id,
            record["user_id"],
        )
        if not snapshot:
            await interaction.response.send_message(
                "That registered player could not be loaded.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=build_player_inspector_embed(snapshot),
            view=PlayerInspectorView(
                interaction.guild.id,
                record["user_id"],
                ctx.is_draft_admin,
            ),
            ephemeral=True,
        )


# ========================================================================
# DRAFT HISTORY COMMAND
# ========================================================================

from draft_service import get_history_page
from views import DraftHistoryView
import discord



def register_draft_history_commands(bot):
    @bot.tree.command(
        name="history",
        description="Browse completed draft history for this server.",
    )
    async def history(interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                "Draft history can only be viewed in a server.",
                ephemeral=True,
            )
            return

        page_data = get_history_page(interaction.guild.id, 0)
        if not page_data["drafts"]:
            await interaction.response.send_message(
                "No completed drafts have been recorded for this server yet.",
                ephemeral=True,
            )
            return

        view = DraftHistoryView(interaction.guild.id)
        await interaction.response.send_message(
            embed=view.build_embed(),
            view=view,
            ephemeral=True,
        )


# ========================================================================
# TRADE COMMAND
# ========================================================================

from draft_service import post_new_draft_board, is_draft_admin, players, trade_players
import discord
from discord import app_commands

from draft_service import get_state


def _draft_player_choices(guild_id, current):
    state = get_state(guild_id)
    search = (current or "").strip().lower()
    choices = []

    for team_name, team in (
        ("Team A", getattr(state, "final_team_a", [])),
        ("Team B", getattr(state, "final_team_b", [])),
    ):
        for user_id, _assigned_role in team:
            ign = players.get(user_id, {}).get("ign", str(user_id))
            label = f"{ign} — {team_name}"

            if search and search not in ign.lower() and search not in label.lower():
                continue

            choices.append(
                app_commands.Choice(
                    name=label[:100],
                    value=str(user_id),
                )
            )

    return choices[:25]


def register_trade_commands(bot):
    async def player_1_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ):
        return _draft_player_choices(interaction.guild.id, current)

    async def player_2_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ):
        return _draft_player_choices(interaction.guild.id, current)

    @bot.tree.command(
        name="trade",
        description="Trade one drafted player for a player on the opposing team."
    )
    @app_commands.autocomplete(
        player_1=player_1_autocomplete,
        player_2=player_2_autocomplete,
    )
    async def trade(
        interaction: discord.Interaction,
        player_1: str,
        player_2: str,
    ):
        if not is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can trade players.",
                ephemeral=True,
            )
            return

        try:
            player_1_id = int(player_1)
            player_2_id = int(player_2)
        except ValueError:
            await interaction.response.send_message(
                "Choose both players from the draft autocomplete list.",
                ephemeral=True,
            )
            return

        success, message = trade_players(
            interaction.guild.id,
            player_1_id,
            player_2_id,
        )

        if not success:
            await interaction.response.send_message(
                message,
                ephemeral=True,
            )
            return

        # Acknowledge the slash command before rebuilding the public board.
        await interaction.response.defer(ephemeral=True)

        await post_new_draft_board(interaction.guild.id)

        await interaction.channel.send(message)

        await interaction.followup.send(
            "Trade completed and the draft board was refreshed.",
            ephemeral=True,
        )


# ========================================================================
# SETUP COMMAND
# ========================================================================

from views import SetupWizardView
import discord


import draft_service as svc


def register_setup_commands(bot):
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


# ========================================================================
# COMMAND REGISTRATION
# ========================================================================

from scheduled_events import register_event_commands

def register_commands(bot):
    register_player_commands(bot)
    register_lobby_commands(bot)
    register_admin_commands(bot)
    register_admin_panel_commands(bot)
    register_moderation_commands(bot)
    register_player_management_commands(bot)
    register_player_inspector_commands(bot)
    register_draft_history_commands(bot)
    register_trade_commands(bot)
    register_setup_commands(bot)
    register_event_commands(bot)
