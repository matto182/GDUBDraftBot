import time

import discord

from database import get_guild_config, remove_lobby_ban, set_lobby_ban
from state import get_state
from service_runtime import players
from lobby_state_service import fill_lobby_from_waiting_room, save_lobby_state
from board_service import post_new_draft_board


def format_timeout_remaining(expires_at):
    if expires_at is None:
        return "Permanent"

    remaining = max(0, int(max(0, expires_at - time.time()) + 0.999999))

    if remaining < 60:
        return "less than 1 minute"

    days, remaining = divmod(remaining, 24 * 60 * 60)
    hours, remaining = divmod(remaining, 60 * 60)
    minutes = remaining // 60

    parts = []

    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")

    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")

    if not days and minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

    return ", ".join(parts[:2]) or "less than 1 minute"

def remove_lobby_timeout(guild_id: int, user_id: int):
    """Remove an existing draft lobby timeout for a player."""
    return remove_lobby_ban(guild_id, user_id)


def is_draft_admin(interaction: discord.Interaction):
    if interaction.user.guild_permissions.administrator:
        return True

    config = get_guild_config(interaction.guild.id)

    if not config or not config.get("admin_role_id"):
        return interaction.user.guild_permissions.manage_guild

    admin_role_id = config["admin_role_id"]

    return any(role.id == admin_role_id for role in interaction.user.roles)

def has_owner_role(guild_id, member):
    """Check the configured Owner role by ID. No admin fallback is allowed."""
    config = get_guild_config(guild_id)

    if not config or not config.get("owner_role_id"):
        return False

    owner_role_id = config["owner_role_id"]
    return any(role.id == owner_role_id for role in getattr(member, "roles", []))

def is_owner(interaction: discord.Interaction):
    return has_owner_role(interaction.guild.id, interaction.user)

async def timeout_from_draft(
    interaction: discord.Interaction,
    user_id: int,
    duration_seconds,
    duration_label: str,
):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    if not is_draft_admin(interaction):
        await interaction.response.send_message(
            "Only draft admins can timeout players.",
            ephemeral=True,
        )
        return

    set_lobby_ban(
        guild_id=guild_id,
        user_id=user_id,
        banned_by=interaction.user.id,
        duration_seconds=duration_seconds,
    )

    if user_id in state.lobby:
        state.lobby.remove(user_id)

    if user_id in state.waiting_room:
        state.waiting_room.remove(user_id)

    state.votes.pop(user_id, None)

    if user_id in state.captain_volunteers:
        state.captain_volunteers.remove(user_id)

    fill_lobby_from_waiting_room(guild_id)
    save_lobby_state(guild_id)

    ign = players.get(user_id, {}).get("ign", "Unknown player")
    await interaction.response.send_message(
        f"**{ign}** has been timed out from draft lobbies **{duration_label}**.",
        ephemeral=True,
    )

    await post_new_draft_board(guild_id)
