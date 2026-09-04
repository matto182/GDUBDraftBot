import discord

from database import get_active_lobby_bans
from moderation_service import remove_lobby_timeout

import draft_service as svc
from views import TimeoutDurationView


async def _ensure_admin(interaction):
    if svc.is_draft_admin(interaction):
        return True

    await interaction.response.send_message(
        "Only draft admins can use the admin panel.",
        ephemeral=True,
    )
    return False


def _registered_timeout_candidates(interaction):
    guild_member_ids = {member.id for member in interaction.guild.members}
    ctx = svc.get_view_context(interaction.guild.id)

    guild_member_ids.update(ctx.lobby)
    guild_member_ids.update(ctx.waiting_room)

    return sorted(
        (
            user_id
            for user_id, player in svc.players.items()
            if user_id in guild_member_ids and player.get("ign")
        ),
        key=lambda user_id: svc.players[user_id]["ign"].casefold(),
    )[:25]


class TimeoutPlayerSelect(discord.ui.Select):
    def __init__(self, interaction):
        candidates = _registered_timeout_candidates(interaction)

        options = [
            discord.SelectOption(
                label=svc.players[user_id]["ign"][:100],
                value=str(user_id),
            )
            for user_id in candidates
        ]

        if not options:
            options = [
                discord.SelectOption(
                    label="No registered players in this server",
                    value="none",
                )
            ]

        super().__init__(
            placeholder="Choose a player to timeout",
            options=options,
        )

    async def callback(self, interaction):
        if not await _ensure_admin(interaction):
            return

        if self.values[0] == "none":
            await interaction.response.send_message(
                "No registered players are available.",
                ephemeral=True,
            )
            return

        user_id = int(self.values[0])
        player = svc.players.get(user_id)

        if not player:
            await interaction.response.send_message(
                "That registered player could not be found.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Choose how long to timeout **{player['ign']}** from draft lobbies:",
            view=TimeoutDurationView(
                svc.get_view_context(interaction.guild.id),
                user_id,
            ),
            ephemeral=True,
        )


class TimeoutPlayerView(discord.ui.View):
    def __init__(self, interaction):
        super().__init__(timeout=300)
        self.add_item(TimeoutPlayerSelect(interaction))


def build_active_timeouts_embed(guild_id):
    active_bans = get_active_lobby_bans(guild_id)

    if not active_bans:
        return discord.Embed(
            title="Active Draft Lobby Timeouts",
            description="There are no active draft lobby timeouts.",
            color=discord.Color.green(),
        )

    lines = []
    for ban in active_bans:
        user_id = ban["user_id"]
        player = svc.players.get(user_id)
        ign = player.get("ign") if player else "Unknown player"

        if ban["expires_at"] is None:
            duration = "**Permanent**"
        else:
            expires_timestamp = int(ban["expires_at"])
            remaining = svc.format_timeout_remaining(ban["expires_at"])
            duration = f"**{remaining}** remaining — <t:{expires_timestamp}:R>"

        lines.append(f"• **{ign}** — {duration}")

    return discord.Embed(
        title="Active Draft Lobby Timeouts",
        description="\n".join(lines),
        color=discord.Color.orange(),
    )


class ActiveTimeoutSelect(discord.ui.Select):
    def __init__(self, guild_id):
        active_bans = get_active_lobby_bans(guild_id)[:25]
        options = []

        for ban in active_bans:
            user_id = ban["user_id"]
            player = svc.players.get(user_id)
            ign = player.get("ign") if player else f"User {user_id}"
            options.append(
                discord.SelectOption(
                    label=ign[:100],
                    value=str(user_id),
                )
            )

        if not options:
            options.append(
                discord.SelectOption(
                    label="No active timeouts",
                    value="none",
                )
            )

        super().__init__(
            placeholder="Choose a timeout to remove",
            options=options,
        )

    async def callback(self, interaction):
        if not await _ensure_admin(interaction):
            return

        if self.values[0] == "none":
            await interaction.response.send_message(
                "There are no active draft lobby timeouts.",
                ephemeral=True,
            )
            return

        user_id = int(self.values[0])
        player = svc.players.get(user_id)
        ign = player.get("ign") if player else "Unknown player"

        removed = remove_lobby_timeout(interaction.guild.id, user_id)

        if not removed:
            await interaction.response.send_message(
                f"**{ign}** does not have an active draft lobby timeout.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            embed=build_active_timeouts_embed(interaction.guild.id),
            view=ActiveTimeoutsView(interaction.guild.id),
        )


class ActiveTimeoutsView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.add_item(ActiveTimeoutSelect(guild_id))
