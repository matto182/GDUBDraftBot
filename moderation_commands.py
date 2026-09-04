import discord
from discord import app_commands

from database import remove_lobby_ban, get_active_lobby_bans
from state import get_state
from views import TimeoutDurationView

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
