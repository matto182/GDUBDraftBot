"""
Runtime state and business logic for GDUB Draft Bot.

Lobby behavior, moderation, board rendering, draft execution, player tools,
notifications, history helpers, trades, and admin helpers live here.
"""

import sys
import database as repository

# Compatibility aliases used by code that previously lived in separate modules.
runtime = sys.modules[__name__]
svc = sys.modules[__name__]


# ========================================================================
# PER-GUILD RUNTIME STATE
# ========================================================================

class GuildState:
    def __init__(self):
        self.lobby = []
        self.waiting_room = []
        self.votes = {}
        self.captain_volunteers = []
        self.draft_result = None
        self.captain_draft = None
        self.final_team_a = []
        self.final_team_b = []
        self.last_signup_time = None
        self.last_balance_debug = None
        self.lobby_size = 16


guild_states = {}


def get_state(guild_id):
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildState()

    return guild_states[guild_id]


# ========================================================================
# BOT RUNTIME
# ========================================================================

from database import load_players_into


players = {}
bot_client = None


def set_bot(client):
    global bot_client
    bot_client = client


def load_players():
    load_players_into(players)


# ========================================================================
# LOBBY STATE PERSISTENCE
# ========================================================================

from database import (
    get_lobby_ban,
    load_lobby_state_from_db,
    save_lobby_state_to_db,
)


def enforce_lobby_size(guild_id):
    """Keep the active lobby at or below the configured runtime size."""
    state = get_state(guild_id)

    if len(state.lobby) <= state.lobby_size:
        return []

    overflow = state.lobby[state.lobby_size:]
    del state.lobby[state.lobby_size:]

    # Players displaced by a size reduction keep priority over people who
    # were already waiting, and keep their original relative order.
    existing_waiters = set(state.waiting_room)
    displaced = [user_id for user_id in overflow if user_id not in existing_waiters]
    state.waiting_room[:0] = displaced

    for user_id in overflow:
        state.votes.pop(user_id, None)
        if user_id in state.captain_volunteers:
            state.captain_volunteers.remove(user_id)

    return overflow


def save_lobby_state(guild_id):
    state = get_state(guild_id)
    enforce_lobby_size(guild_id)

    save_lobby_state_to_db(
        guild_id,
        state.lobby,
        state.waiting_room,
        state.last_signup_time
    )


def load_lobby_state(guild_id):
    load_players()

    state = get_state(guild_id)

    state.last_signup_time = load_lobby_state_from_db(
        guild_id,
        players,
        state.lobby,
        state.waiting_room
    )

    # Runtime lobby size is intentionally not stored in the database. If a
    # smaller size is active, never allow a reload to overfill the lobby.
    enforce_lobby_size(guild_id)


def fill_lobby_from_waiting_room(guild_id):
    state = get_state(guild_id)
    moved = []

    while len(state.lobby) < state.lobby_size and state.waiting_room:
        next_player = state.waiting_room.pop(0)

        if get_lobby_ban(guild_id, next_player):
            continue

        if next_player not in state.lobby:
            state.lobby.append(next_player)
            moved.append(next_player)

    return moved


# ========================================================================
# FULL-LOBBY NOTIFICATIONS
# ========================================================================

import asyncio
import time

import discord

from database import (
    claim_lobby_full_notification,
    get_guild_config,
    release_lobby_full_notification_claim,
)


async def maybe_send_lobby_full_notification(guild_id):
    """Ping the active full lobby at most once per guild every 4 hours."""
    state = get_state(guild_id)

    # Only announce a newly full pre-draft lobby.
    if len(state.lobby) != state.lobby_size:
        return False

    if state.captain_draft or state.draft_result:
        return False

    config = get_guild_config(guild_id)
    if not config or not config.get("draft_channel_id"):
        return False

    claimed_at = time.time()

    if not claim_lobby_full_notification(guild_id, claimed_at):
        return False

    # Snapshot the exact players that caused the full-lobby event.
    lobby_user_ids = list(state.lobby)

    try:
        channel = runtime.bot_client.get_channel(config["draft_channel_id"])

        if channel is None:
            channel = await runtime.bot_client.fetch_channel(
                config["draft_channel_id"]
            )

        # If the lobby changed while we were resolving the channel, do not
        # send a stale ping and do not consume the cooldown.
        current_state = get_state(guild_id)
        if (
            len(current_state.lobby) != current_state.lobby_size
            or current_state.captain_draft
            or current_state.draft_result
            or list(current_state.lobby) != lobby_user_ids
        ):
            release_lobby_full_notification_claim(guild_id, claimed_at)
            return False

        mentions = " ".join(f"<@{user_id}>" for user_id in lobby_user_ids)

        await channel.send(
            (
                "**Lobby is full!**\n"
                f"{mentions}\n"
                "Head to **Guild Hall** for the draft."
            ),
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=False,
                replied_user=False,
            ),
        )

        return True
    except Exception as error:
        # Failed sends should not burn the 4-hour window.
        release_lobby_full_notification_claim(guild_id, claimed_at)
        print(f"Lobby full notification failed for guild {guild_id}: {error}")
        return False


def queue_lobby_full_notification(guild_id):
    """Schedule the async notification from synchronous service code."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None

    return loop.create_task(maybe_send_lobby_full_notification(guild_id))


# ========================================================================
# DRAFT BOARD
# ========================================================================

import discord

from config import normalize_roles
from database import get_guild_config, save_board_message_id
from database import is_board_hidden
from draft_logic import role_sort_key


def server_display_name(guild_id, user_id):
    if not runtime.bot_client:
        return None

    guild = runtime.bot_client.get_guild(guild_id)
    if not guild:
        return None

    member = guild.get_member(user_id)
    if not member:
        return None

    # Use the server nickname when present, otherwise Discord's normal
    # display name. This keeps the board consistent for every member.
    return member.display_name


def board_player_name(guild_id, user_id, ign):
    discord_name = server_display_name(guild_id, user_id)

    if not discord_name:
        return f"**{ign}**"

    clean_ign = ign.strip()
    clean_discord_name = discord_name.strip()

    # Avoid pointless duplicates such as "Supreme Bot (Supreme Bot)".
    if clean_discord_name.casefold() == clean_ign.casefold():
        return f"**{clean_ign}**"

    # Avoid nested duplicates such as "Ixxxl (Ixxxl (Tony))".
    ign_prefix = f"{clean_ign} ("
    if (
        clean_discord_name.casefold().startswith(ign_prefix.casefold())
        and clean_discord_name.endswith(")")
    ):
        suffix = clean_discord_name[len(clean_ign):].strip()
        safe_suffix = discord.utils.escape_markdown(suffix)
        return f"**{clean_ign}** {safe_suffix}"

    safe_discord_name = discord.utils.escape_markdown(clean_discord_name)
    return f"**{clean_ign}** ({safe_discord_name})"


def player_label(guild_id, user_id):
    state = get_state(guild_id)
    captain_draft = state.captain_draft
    p = players.get(user_id)
    if not p:
        return f"<@{user_id}>"

    label = f"**{p['ign']}** (<@{user_id}>)"

    if captain_draft:
        if user_id == captain_draft.captain_a:
            label = f"⭐ {label} [Captain A]"
        elif user_id == captain_draft.captain_b:
            label = f"⭐ {label} [Captain B]"

        if user_id == captain_draft.current_picker():
            label = f"👉 {label} **[CURRENT PICK]**"

    return label

def team_text(guild_id, team):
    state = get_state(guild_id)
    captain_draft = state.captain_draft
    lines = []

    sorted_team = sorted(team, key=lambda item: role_sort_key(item[1]))

    for i, (user_id, role) in enumerate(sorted_team, start=1):
        p = players[user_id]

        prefix = ""

        if captain_draft:
            if user_id in [captain_draft.captain_a, captain_draft.captain_b]:
                prefix += "⭐ "

            if user_id == captain_draft.current_picker():
                prefix += "👉 "

        lines.append(f"{i}. {prefix}{board_player_name(guild_id, user_id, p['ign'])} — {role}")

    return "\n".join(lines)

def build_draft_board_embed(guild_id):
    state = get_state(guild_id)

    lobby = state.lobby
    waiting_room = state.waiting_room
    votes = state.votes
    captain_volunteers = state.captain_volunteers
    draft_result = state.draft_result
    captain_draft = state.captain_draft
    final_team_a = state.final_team_a
    final_team_b = state.final_team_b

    captain_votes = list(votes.values()).count("captain")
    random_votes = list(votes.values()).count("random")

    if lobby:
        lobby_text = ""

        for i, user_id in enumerate(lobby, start=1):
            p = players[user_id]
            current_roles = normalize_roles(p.get("roles", []))
            roles = ", ".join(current_roles) if current_roles else "No roles set"

            lobby_text += f"{i}. {board_player_name(guild_id, user_id, p['ign'])} — {roles}\n"
    else:
        lobby_text = "No players signed up yet."

    if waiting_room:
        waiting_text = ""

        for i, user_id in enumerate(waiting_room, start=1):
            p = players[user_id]
            current_roles = normalize_roles(p.get("roles", []))
            roles = ", ".join(current_roles) if current_roles else "No roles set"

            waiting_text += f"{i}. {board_player_name(guild_id, user_id, p['ign'])} — {roles}\n"
    else:
        waiting_text = "Waiting room is empty."

    # Before a draft, show the signup/lobby information. Once a draft is
    # active or complete, the drafted teams already account for the lobby, so
    # only keep the waiting room visible above the draft itself.
    if captain_draft or draft_result:
        description = (
            f"## Waiting Room — {len(waiting_room)}\n"
            f"{waiting_text}"
        )
    else:
        description = (
            "**Before signing up:**\n"
            "1. Use `/name` to set your in-game name.\n"
            "2. Use `/role` to pick your roles, in order of priority.\n\n"
            f"## Lobby — {len(lobby)}/{state.lobby_size}\n"
            f"{lobby_text}\n\n"
            f"## Waiting Room — {len(waiting_room)}\n"
            f"{waiting_text}"
        )

    # Votes and captain volunteers are only useful before a draft starts.
    if not captain_draft and not draft_result:
        description += (
            "\n\n## Votes\n"
            f"Captain Mode: **{captain_votes}**\n"
            f"Random Draft: **{random_votes}**"
        )

        # Keep the board compact until Captain Mode actually has support.
        if captain_votes > 0:
            if captain_volunteers:
                captain_text = "\n".join(
                    player_label(guild_id, p)
                    for p in captain_volunteers
                )
            else:
                captain_text = "No captain volunteers yet."

            description += (
                "\n\n## Captain Volunteers\n"
                f"{captain_text}"
            )

    if captain_draft:
        next_picker = captain_draft.current_picker()

        description += "\n\n## Captain Draft\n"
        description += f"**Team A Captain:** {player_label(guild_id, captain_draft.captain_a)}\n"
        description += f"**Team B Captain:** {player_label(guild_id, captain_draft.captain_b)}\n\n"

        if next_picker:
            description += f"**Current Pick:** {player_label(guild_id, next_picker)}\n\n"
        else:
            description += "**Draft Complete**\n\n"

        description += "### Team A\n"
        description += team_text(guild_id, captain_draft.team_a)

        description += "\n\n### Team B\n"
        description += team_text(guild_id, captain_draft.team_b)

        if captain_draft.available:
            description += "\n\n### Available Players\n"

            description += "\n".join(
                player_label(guild_id, p)
                for p in captain_draft.available
            )

    elif draft_result and final_team_a and final_team_b:
        description += "\n\n## Team A\n"
        description += team_text(guild_id, final_team_a)

        description += "\n\n## Team B\n"
        description += team_text(guild_id, final_team_b)

    return discord.Embed(
        title="GW1 GvG Draft Board",
        description=description,
        color=discord.Color.blue()
    )


async def post_new_draft_board(guild_id):
    if is_board_hidden(guild_id):
        return
    load_players()
    load_lobby_state(guild_id)

    config = get_guild_config(guild_id)

    if not config or not config.get("draft_channel_id"):
        print("No draft channel configured. Use /setup first.")
        return

    channel = runtime.bot_client.get_channel(config["draft_channel_id"])

    if channel is None:
        print("Could not find configured draft channel.")
        return

    old_board_message_id = config.get("board_message_id")

    if old_board_message_id:
        try:
            old_message = await channel.fetch_message(old_board_message_id)
            await old_message.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            print("Bot does not have permission to delete old draft board.")
        except discord.HTTPException as e:
            print(f"Failed to delete old draft board: {e}")

    message = await channel.send(
        embed=build_draft_board_embed(guild_id),
        view=DraftBoardView(get_view_context)
    )

    save_board_message_id(guild_id, message.id)

async def show_status(interaction: discord.Interaction):
    load_lobby_state(interaction.guild.id)
    await interaction.response.send_message(
        embed=build_draft_board_embed(interaction.guild.id),
        ephemeral=True
    )

async def refresh_board(interaction: discord.Interaction):
    await interaction.message.edit(
        embed=build_draft_board_embed(interaction.guild.id),
        view=DraftBoardView(get_view_context)
    )


# ========================================================================
# MODERATION
# ========================================================================

import time

import discord

from database import get_guild_config, remove_lobby_ban, set_lobby_ban


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
    was_full = len(state.lobby) >= state.lobby_size

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

    if not was_full and len(state.lobby) >= state.lobby_size:
        queue_lobby_full_notification(guild_id)

    ign = players.get(user_id, {}).get("ign", "Unknown player")
    await interaction.response.send_message(
        f"**{ign}** has been timed out from draft lobbies **{duration_label}**.",
        ephemeral=True,
    )

    await post_new_draft_board(guild_id)


# ========================================================================
# LOBBY ACTIONS
# ========================================================================

import time

import discord

from database import get_lobby_ban


def _lobby_is_full(state):
    return len(state.lobby) >= state.lobby_size


async def set_lobby_size(interaction: discord.Interaction, size: int):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    if size < 2 or size > 16:
        await interaction.response.send_message(
            "Lobby size must be between 2 and 16 players.",
            ephemeral=True
        )
        return False

    if state.captain_draft or state.draft_result:
        await interaction.response.send_message(
            "Reset the current draft before changing the lobby size.",
            ephemeral=True
        )
        return False

    old_size = state.lobby_size

    if size == old_size:
        await interaction.response.send_message(
            f"Lobby size is already **{size}**.",
            ephemeral=True
        )
        return True

    state.lobby_size = size

    displaced = enforce_lobby_size(guild_id)
    promoted = fill_lobby_from_waiting_room(guild_id)
    save_lobby_state(guild_id)

    details = []
    if displaced:
        details.append(f"Moved **{len(displaced)}** player(s) to the front of the waiting room.")
    if promoted:
        details.append(f"Moved **{len(promoted)}** waiting player(s) into the lobby.")

    message = f"Lobby size changed from **{old_size}** to **{size}**."
    if details:
        message += "\n" + "\n".join(details)

    await interaction.response.send_message(message, ephemeral=True)
    await post_new_draft_board(guild_id)
    return True


async def reset_draft_only(interaction: discord.Interaction, silent=False):
    guild_id = interaction.guild.id
    state = get_state(guild_id)
    was_full = _lobby_is_full(state)

    state.final_team_a = []
    state.final_team_b = []
    state.captain_draft = None
    state.draft_result = None
    state.votes.clear()
    state.captain_volunteers.clear()

    fill_lobby_from_waiting_room(guild_id)
    save_lobby_state(guild_id)

    if not was_full and _lobby_is_full(state):
        queue_lobby_full_notification(guild_id)

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message(
            "Draft reset. Lobby refilled from waiting room if slots were open.",
            ephemeral=True
        )

    return True


async def kick_from_draft(interaction: discord.Interaction, user_id: int):
    guild_id = interaction.guild.id
    state = get_state(guild_id)
    was_full = _lobby_is_full(state)

    removed = False

    if user_id in state.lobby:
        state.lobby.remove(user_id)
        removed = True

    if user_id in state.waiting_room:
        state.waiting_room.remove(user_id)
        removed = True

    state.votes.pop(user_id, None)

    if user_id in state.captain_volunteers:
        state.captain_volunteers.remove(user_id)

    fill_lobby_from_waiting_room(guild_id)
    save_lobby_state(guild_id)

    if not removed:
        await interaction.response.send_message(
            "That player is not in the lobby or waiting room.",
            ephemeral=True
        )
        return

    if not was_full and _lobby_is_full(state):
        queue_lobby_full_notification(guild_id)

    await interaction.response.send_message(
        f"Kicked {player_label(guild_id, user_id)} from the draft.",
        ephemeral=True
    )

    await post_new_draft_board(guild_id)


async def signup_player(interaction: discord.Interaction, silent=False):
    guild_id = interaction.guild.id
    state = get_state(guild_id)
    was_full = _lobby_is_full(state)

    user_id = interaction.user.id

    lobby_ban = get_lobby_ban(guild_id, user_id)

    if lobby_ban:
        if lobby_ban["expires_at"] is None:
            message = "You are permanently banned from draft lobbies."
        else:
            remaining = format_timeout_remaining(lobby_ban["expires_at"])
            expires_timestamp = int(lobby_ban["expires_at"])
            message = (
                "You are currently timed out from draft lobbies.\n"
                f"Time remaining: **{remaining}** (expires <t:{expires_timestamp}:R>)."
            )

        await interaction.response.send_message(message, ephemeral=True)
        return False

    if user_id not in players:
        await interaction.response.send_message("Use `/name` first.", ephemeral=True)
        return False

    if not players[user_id]["roles"]:
        await interaction.response.send_message("Use `/role` first.", ephemeral=True)
        return False

    if user_id in state.lobby:
        await interaction.response.send_message("You are already in the active lobby.", ephemeral=True)
        return False

    if user_id in state.waiting_room:
        await interaction.response.send_message("You are already in the waiting room.", ephemeral=True)
        return False

    # Preserve FIFO: existing waiting-room players always get first claim
    # on any open lobby slots before a brand-new signup can enter.
    if not state.captain_draft and not state.draft_result and len(state.lobby) < state.lobby_size:
        fill_lobby_from_waiting_room(guild_id)

    if (
        state.captain_draft
        or state.draft_result
        or len(state.lobby) >= state.lobby_size
        or state.waiting_room
    ):
        state.waiting_room.append(user_id)
    else:
        state.lobby.append(user_id)

    state.last_signup_time = time.time()
    save_lobby_state(guild_id)

    if not was_full and _lobby_is_full(state):
        queue_lobby_full_notification(guild_id)

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message("Signup updated.", ephemeral=True)

    return True


async def drop_player(interaction: discord.Interaction, silent=False):
    guild_id = interaction.guild.id
    state = get_state(guild_id)
    was_full = _lobby_is_full(state)

    user_id = interaction.user.id
    removed = False

    if user_id in state.lobby:
        state.lobby.remove(user_id)
        removed = True

    if user_id in state.waiting_room:
        state.waiting_room.remove(user_id)
        removed = True

    state.votes.pop(user_id, None)

    if user_id in state.captain_volunteers:
        state.captain_volunteers.remove(user_id)

    if not removed:
        await interaction.response.send_message("You are not signed up.", ephemeral=True)
        return False

    # If the draft is not active, immediately give the newly opened lobby
    # slot to the oldest waiting-room player.
    if not state.captain_draft and not state.draft_result:
        fill_lobby_from_waiting_room(guild_id)

    save_lobby_state(guild_id)

    if not was_full and _lobby_is_full(state):
        queue_lobby_full_notification(guild_id)

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message("You dropped from the lobby/waiting room.", ephemeral=True)

    return True


async def vote_player(interaction: discord.Interaction, mode_value: str, mode_name: str, silent=False):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    user_id = interaction.user.id

    if state.captain_draft or state.draft_result:
        await interaction.response.send_message(
            "Voting is locked while a draft is active.",
            ephemeral=True
        )
        return False

    if user_id not in state.lobby:
        await interaction.response.send_message(
            "Only signed-up players can vote.",
            ephemeral=True
        )
        return False

    state.votes[user_id] = mode_value

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message(
            f"{player_label(guild_id, user_id)} voted for **{mode_name}**.",
            ephemeral=True
        )

    return True


async def volunteer_captain(interaction: discord.Interaction, silent=False):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    user_id = interaction.user.id

    if state.captain_draft or state.draft_result:
        await interaction.response.send_message(
            "Captain volunteering is locked while a draft is active.",
            ephemeral=True
        )
        return False

    if user_id not in state.lobby:
        await interaction.response.send_message(
            "Only signed-up players can volunteer as captain.",
            ephemeral=True
        )
        return False

    if user_id in state.captain_volunteers:
        await interaction.response.send_message(
            "You are already volunteered as captain.",
            ephemeral=True
        )
        return False

    state.captain_volunteers.append(user_id)

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message(
            f"{player_label(guild_id, user_id)} volunteered as captain.",
            ephemeral=True
        )

    return True


async def wipe_lobby(interaction: discord.Interaction, silent=False):
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
    state.last_signup_time = None

    save_lobby_state(guild_id)

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message(
            "Lobby completely wiped.",
            ephemeral=True
        )

    await post_new_draft_board(guild_id)


# ========================================================================
# DRAFT PLAYER NOTIFICATIONS
# ========================================================================

import discord

from database import player_dm_is_on_cooldown, mark_player_dm_sent


async def notify_drafted_players(interaction: discord.Interaction, team_a, team_b):
    guild_id = interaction.guild.id
    dm_failed = []

    async def notify_team(team, team_name):
        for user_id, assigned_role in team:
            member = interaction.guild.get_member(user_id)

            # Only hit Discord's API if the member cache misses.
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(user_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException) as error:
                    print(f"Could not resolve member {user_id}: {error}")
                    if user_id in players:
                        dm_failed.append(players[user_id]["ign"])
                    continue

            if member.voice is not None and member.voice.channel is not None:
                print(f"{member.name} ({user_id}) is already in voice; skipping draft DM")
                continue

            # Limit successful draft DMs to one per player, per guild, every 8 hours.
            if player_dm_is_on_cooldown(guild_id, user_id):
                print(f"DM cooldown active for {user_id}; skipping")
                continue

            try:
                await member.send(
                    f"Your GvG draft is ready.\n\n"
                    f"Team: **{team_name}**\n"
                    f"Role: **{assigned_role}**\n\n"
                    f"Please join your team voice channel."
                )

                # Failed sends do not start the cooldown.
                mark_player_dm_sent(guild_id, user_id)
                print(f"Draft DM sent to {member.name} ({user_id})")

            except (discord.Forbidden, discord.HTTPException) as error:
                print(f"Draft DM failed for {member.name} ({user_id}): {error}")
                if user_id in players:
                    dm_failed.append(players[user_id]["ign"])

    await notify_team(team_a, "A")
    await notify_team(team_b, "B")

    return dm_failed


# ========================================================================
# VOICE CHANNEL MOVEMENT
# ========================================================================

import discord

from database import get_guild_config


async def move_teams_to_voice(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    config = get_guild_config(guild_id)

    if not config:
        await interaction.response.send_message(
            "Server setup is missing. Run `/setup` first.",
            ephemeral=True
        )
        return

    team_a_channel_id = config.get("team_a_voice_channel_id")
    team_b_channel_id = config.get("team_b_voice_channel_id")

    if not team_a_channel_id or not team_b_channel_id:
        await interaction.response.send_message(
            "Voice channels are not configured. Run `/setup` again.",
            ephemeral=True
        )
        return

    team_a_channel = interaction.guild.get_channel(team_a_channel_id)
    team_b_channel = interaction.guild.get_channel(team_b_channel_id)

    if not team_a_channel or not team_b_channel:
        await interaction.response.send_message(
            "Could not find one or both configured voice channels.",
            ephemeral=True
        )
        return

    if state.captain_draft:
        team_a = state.captain_draft.team_a
        team_b = state.captain_draft.team_b
    elif state.draft_result and state.final_team_a and state.final_team_b:
        team_a = state.final_team_a
        team_b = state.final_team_b
    else:
        await interaction.response.send_message(
            "No active draft teams to move.",
            ephemeral=True
        )
        return

    # Moving multiple members can take longer than Discord allows for the
    # initial interaction response. Defer before starting the move operations.
    await interaction.response.defer(ephemeral=True)

    moved = 0
    failed = []

    for user_id, _role in team_a:
        member = interaction.guild.get_member(user_id)
        if member and member.voice:
            try:
                await member.move_to(team_a_channel)
                moved += 1
            except Exception:
                failed.append(players[user_id]["ign"])
        else:
            failed.append(players[user_id]["ign"])

    for user_id, _role in team_b:
        member = interaction.guild.get_member(user_id)
        if member and member.voice:
            try:
                await member.move_to(team_b_channel)
                moved += 1
            except Exception:
                failed.append(players[user_id]["ign"])
        else:
            failed.append(players[user_id]["ign"])

    msg = f"Moved **{moved}** players to team voice channels."

    if failed:
        msg += "\n\nCould not move:\n" + "\n".join(failed)

    await interaction.followup.send(msg, ephemeral=True)


# ========================================================================
# DRAFT EXECUTION
# ========================================================================

import random

import discord

from database import (
    get_guild_player_weights,
    save_completed_draft,
)
from draft_logic import (
    CaptainDraft,
    generate_random_teams,
    optimize_team_roles,
)


def _finalize_captain_draft(guild_id, state):
    captain_draft = state.captain_draft

    # The existing role optimizer is specifically an 8-player team solver.
    # Preserve it for normal 8v8 captain drafts and leave smaller captain
    # teams in the roles selected/displayed during the pick process.
    if len(captain_draft.team_a) == 8:
        captain_draft.team_a = optimize_team_roles(players, captain_draft.team_a)
    if len(captain_draft.team_b) == 8:
        captain_draft.team_b = optimize_team_roles(players, captain_draft.team_b)

    state.final_team_a = captain_draft.team_a
    state.final_team_b = captain_draft.team_b

    save_completed_draft(
        guild_id=guild_id,
        mode="captain",
        team_a=state.final_team_a,
        team_b=state.final_team_b,
        players=players,
        captain_a=captain_draft.captain_a,
        captain_b=captain_draft.captain_b
    )

    state.draft_result = (
        "**Mode:** Captain Draft\n\n"
        "### Team A\n"
        f"{team_text(guild_id, state.final_team_a)}\n\n"
        "### Team B\n"
        f"{team_text(guild_id, state.final_team_b)}"
    )

    # Completed boards render from final_team_a/final_team_b, so clear the
    # active draft before the board refresh.
    state.captain_draft = None


async def handle_captain_pick(interaction: discord.Interaction, picked_id: int):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    if not state.captain_draft:
        await interaction.response.send_message("No captain draft is active.", ephemeral=True)
        return

    picker_id = interaction.user.id

    success, message = state.captain_draft.pick_player(players, picker_id, picked_id)

    if not success:
        await interaction.response.send_message(message, ephemeral=True)
        return

    if state.captain_draft.is_complete():
        _finalize_captain_draft(guild_id, state)

        await interaction.response.defer()
        await post_new_draft_board(guild_id)

        dm_failed = await notify_drafted_players(
            interaction,
            state.final_team_a,
            state.final_team_b
        )

        if dm_failed:
            await interaction.channel.send(
                "Could not DM:\n" + "\n".join(dm_failed)
            )

        return

    await interaction.response.defer()

    if state.captain_draft:
        next_picker = state.captain_draft.current_picker()
        if next_picker:
            await interaction.channel.send(
                f"{player_label(guild_id, next_picker)}, you are on the clock. Click **Pick Player** on the draft board."
            )

    await post_new_draft_board(guild_id)


async def start_captain_draft(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    if len(state.captain_volunteers) < 2:
        await interaction.response.send_message(
            "Captain Mode won, but there need to be at least 2 captain volunteers.",
            ephemeral=True
        )
        return

    chosen = random.sample(state.captain_volunteers, 2)
    random.shuffle(chosen)

    state.captain_draft = CaptainDraft(state.lobby, chosen[0], chosen[1])
    state.draft_result = None
    state.final_team_a = []
    state.final_team_b = []

    # A two-player captain lobby has no picks to make; the captains are the
    # complete teams immediately.
    if state.captain_draft.is_complete():
        _finalize_captain_draft(guild_id, state)

        await interaction.response.send_message(
            "Captain draft complete. Each captain is their team's player.",
            ephemeral=True
        )
        await post_new_draft_board(guild_id)

        dm_failed = await notify_drafted_players(
            interaction,
            state.final_team_a,
            state.final_team_b
        )

        if dm_failed:
            await interaction.channel.send(
                "Could not DM:\n" + "\n".join(dm_failed)
            )
        return

    await interaction.response.send_message(
        f"Captain draft started. First pick: {player_label(guild_id, state.captain_draft.current_picker())}. "
        f"Captains should use `/pickpanel` when it is their turn.",
        ephemeral=True
    )

    await post_new_draft_board(guild_id)


async def run_startdraft(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    load_lobby_state(guild_id)
    required_players = state.lobby_size

    if len(state.lobby) != required_players:
        await interaction.response.send_message(
            f"Need exactly {required_players} players to start. "
            f"Current lobby: {len(state.lobby)}/{required_players}",
            ephemeral=True
        )
        return

    captain_votes = list(state.votes.values()).count("captain")
    random_votes = list(state.votes.values()).count("random")

    if captain_votes > random_votes:
        await start_captain_draft(interaction)
        return

    # The normal 16-player optimizer can take longer than Discord's initial
    # interaction-response window. Deferring is also harmless for small drafts.
    await interaction.response.defer(ephemeral=True)

    player_weights = get_guild_player_weights(guild_id)

    try:
        team_a, team_b, formation = generate_random_teams(
            players,
            state.lobby,
            player_weights,
        )
    except ValueError as error:
        await interaction.followup.send(str(error), ephemeral=True)
        return

    state.final_team_a = team_a
    state.final_team_b = team_b

    if formation.get("uses_full_optimizer"):
        def build_debug_team(team, prefix):
            return {
                "weight": int(formation[f"{prefix}_weight"]),
                "composition_penalty": formation[f"{prefix}_composition_penalty"],
                "effective_strength": int(formation[f"{prefix}_effective_strength"]),
                "off_role_count": formation[f"{prefix}_off_role_count"],
                "players": [
                    {
                        "user_id": user_id,
                        "ign": players[user_id]["ign"],
                        "weight": int(player_weights.get(user_id, 0)),
                    }
                    for user_id, _role in team
                ],
            }

        state.last_balance_debug = {
            "team_a": build_debug_team(team_a, "team_a"),
            "team_b": build_debug_team(team_b, "team_b"),
            "strength_difference": abs(
                int(formation["team_a_effective_strength"])
                - int(formation["team_b_effective_strength"])
            ),
            "optimizer_score": formation["score"],
        }
    else:
        # Reduced-size drafts are intentionally random after the requested monk
        # seeding, so do not imply that hidden-weight optimization was applied.
        state.last_balance_debug = None

    save_completed_draft(
        guild_id=guild_id,
        mode="random",
        team_a=team_a,
        team_b=team_b,
        players=players,
        balance_score=formation.get("score")
    )

    if formation.get("uses_full_optimizer"):
        state.draft_result = (
            "**Mode:** Random Draft\n\n"
            f"**Team A Comp:** {formation['team_a']}\n"
            f"**Team B Comp:** {formation['team_b']}\n"
            f"**Balancing Score:** {formation['score']} lower is better\n\n"
            "### Team A\n"
            f"{team_text(guild_id, team_a)}\n\n"
            "### Team B\n"
            f"{team_text(guild_id, team_b)}"
        )
    else:
        state.draft_result = (
            "**Mode:** Random Draft\n\n"
            f"**Draft Logic:** {formation['team_a']}\n\n"
            "### Team A\n"
            f"{team_text(guild_id, team_a)}\n\n"
            "### Team B\n"
            f"{team_text(guild_id, team_b)}"
        )

    # Publish the completed draft board before sending assignment DMs.
    await post_new_draft_board(guild_id)

    dm_failed = await notify_drafted_players(interaction, team_a, team_b)

    msg = "Draft started."

    if dm_failed:
        msg += "\n\nCould not DM:\n" + "\n".join(dm_failed)

    await interaction.followup.send(msg, ephemeral=True)


# ========================================================================
# HIDDEN OWNER COMMANDS
# ========================================================================

import discord

from database import set_player_weight


async def handle_owner_prefix_message(message: discord.Message):
    """Handle intentionally undiscoverable Owner-only prefix commands."""
    if message.author.bot or message.guild is None:
        return

    content = message.content.strip()
    content_cf = content.casefold()

    is_adjust = content_cf.startswith("!adjust " )
    is_debugweights = content_cf == "!debugweights"

    if not is_adjust and not is_debugweights:
        return

    # Silently ignore anyone without the configured Owner role. This avoids
    # confirming that the hidden commands exist.
    if not has_owner_role(message.guild.id, message.author):
        return

    # Remove the command message immediately when possible.
    try:
        await message.delete()
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        pass

    if is_debugweights:
        state = get_state(message.guild.id)
        debug = state.last_balance_debug

        if not debug:
            response = (
                "No random-draft balance debug data is available yet. "
                "Run an autodraft first, then use this command again."
            )
        else:
            def format_team(team_key, team_name):
                team = debug[team_key]
                lines = [
                    f"**Team {team_name}**",
                    f"Hidden weight total: {team['weight']:+d}",
                    f"Composition penalty: {team['composition_penalty']}",
                    f"Effective strength: {team['effective_strength']:+d}",
                    f"Off-role slots: {team['off_role_count']}",
                    "Player weights:",
                ]

                for player in team["players"]:
                    lines.append(
                        f"- {player['ign']}: {player['weight']:+d}"
                    )

                return "\n".join(lines)

            response = (
                "**Last Random Draft — Hidden Balance Debug**\n\n"
                f"{format_team('team_a', 'A')}\n\n"
                f"{format_team('team_b', 'B')}\n\n"
                f"Effective-strength difference: {debug['strength_difference']}\n"
                f"Final optimizer score: {debug['optimizer_score']}"
            )

        try:
            await message.author.send(response)
        except discord.HTTPException:
            pass
        return

    # !adjust
    payload = content[len("!adjust " ):].strip()
    parts = payload.rsplit(maxsplit=1)

    if len(parts) != 2:
        try:
            await message.author.send("Usage: `!adjust Player IGN 200`")
        except discord.HTTPException:
            pass
        return

    player_name, points_text = parts

    try:
        points = int(points_text)
    except ValueError:
        try:
            await message.author.send(
                "The final value must be a whole number, for example `200` or `-200`."
            )
        except discord.HTTPException:
            pass
        return

    load_players()

    matches = [
        (user_id, data)
        for user_id, data in players.items()
        if data["ign"].casefold() == player_name.casefold()
    ]

    if not matches:
        response = f"No player found with IGN `{player_name}`."
    elif len(matches) > 1:
        response = f"More than one player uses the IGN `{player_name}`."
    else:
        user_id, player_data = matches[0]
        set_player_weight(message.guild.id, user_id, points)

        if points == 0:
            response = f"Cleared {player_data['ign']}'s adjustment."
        else:
            response = f"Set {player_data['ign']} to {points:+d}."

    # Never confirm the adjustment in a public channel.
    try:
        await message.author.send(response)
    except discord.HTTPException:
        pass


# ========================================================================
# PLAYER ALIAS LOGIC
# ========================================================================

import database as repository


def record_name_change(user_id, previous_ign, new_ign, db_file=None):
    previous_ign = str(previous_ign or "").strip()
    new_ign = str(new_ign or "").strip()

    if not previous_ign or not new_ign:
        return False

    if previous_ign.casefold() == new_ign.casefold():
        return False

    saved = repository.save_player_alias(
        user_id,
        previous_ign,
        db_file=db_file,
    )

    # If the player returns to an older IGN, it is current again rather than previous.
    repository.remove_player_alias(user_id, new_ign, db_file=db_file)
    return saved


def get_player_aliases(user_id, db_file=None):
    return repository.get_player_aliases(user_id, db_file=db_file)


def resolve_alias_user_id(identifier, db_file=None):
    return repository.resolve_alias_user_id(identifier, db_file=db_file)


# ========================================================================
# PLAYER STATS
# ========================================================================

from collections import defaultdict

from config import ROLES, normalize_roles


PRIORITY_LABELS = {
    1: "Primary",
    2: "Secondary",
    3: "Tertiary",
    4: "Fourth",
    5: "Fifth",
    999: "Fill/Off-role",
}


def _rate(count, total):
    if not total:
        return 0.0
    return (count / total) * 100.0


def _normalize_role_name(role):
    normalized = normalize_roles([role])
    if normalized:
        return normalized[0]
    return str(role)


def summarize_player_stats(stats_data):
    """Convert raw repository stats into display-ready counts and rates."""
    drafts_played = int(stats_data.get("drafts_played", 0) or 0)
    times_captain = int(stats_data.get("times_captain", 0) or 0)

    role_counts = defaultdict(int)
    for role, count in stats_data.get("roles", []) or []:
        role_counts[_normalize_role_name(role)] += int(count or 0)

    role_order = {role: index for index, role in enumerate(ROLES)}
    role_frequency = [
        {
            "role": role,
            "count": count,
            "rate": _rate(count, drafts_played),
        }
        for role, count in sorted(
            role_counts.items(),
            key=lambda item: (
                -item[1],
                role_order.get(item[0], len(role_order)),
                item[0].casefold(),
            ),
        )
    ]

    priority_counts = {
        int(priority): int(count or 0)
        for priority, count in stats_data.get("priority_stats", []) or []
    }

    preferred_assignments = sum(
        count
        for priority, count in priority_counts.items()
        if 1 <= priority <= 5
    )
    off_role_assignments = priority_counts.get(999, 0)

    priority_usage = [
        {
            "priority": priority,
            "label": PRIORITY_LABELS.get(priority, f"Priority {priority}"),
            "count": count,
            "rate": _rate(count, drafts_played),
        }
        for priority, count in sorted(
            priority_counts.items(),
            key=lambda item: (item[0] == 999, item[0]),
        )
    ]

    return {
        "drafts_played": drafts_played,
        "times_captain": times_captain,
        "captain_rate": _rate(times_captain, drafts_played),
        "preferred_assignments": preferred_assignments,
        "preferred_role_hit_rate": _rate(preferred_assignments, drafts_played),
        "off_role_assignments": off_role_assignments,
        "off_role_rate": _rate(off_role_assignments, drafts_played),
        "role_frequency": role_frequency,
        "priority_usage": priority_usage,
    }


def format_role_frequency(summary):
    rows = summary.get("role_frequency", [])
    if not rows:
        return "No role data."

    return "\n".join(
        f"{row['role']}: {row['count']} ({row['rate']:.1f}%)"
        for row in rows
    )


def format_priority_usage(summary):
    rows = summary.get("priority_usage", [])
    if not rows:
        return "No assignment data."

    return "\n".join(
        f"{row['label']}: {row['count']} ({row['rate']:.1f}%)"
        for row in rows
    )


# ========================================================================
# PLAYER MANAGEMENT
# ========================================================================

import time



def _replace_drafted_player(state, outgoing_user_id, incoming_user_id):
    """Replace one drafted player in-place while preserving team and role."""
    for team_label, attr_name in (
        ("Team A", "final_team_a"),
        ("Team B", "final_team_b"),
    ):
        team = getattr(state, attr_name, [])

        for index, (user_id, assigned_role) in enumerate(team):
            if user_id != outgoing_user_id:
                continue

            team[index] = (incoming_user_id, assigned_role)
            return team_label, assigned_role

    return None, None


def _find_missing_drafted_player(state):
    """Find a drafted player who is no longer present in the active lobby."""
    lobby_ids = set(state.lobby)

    for team in (
        getattr(state, "final_team_a", []),
        getattr(state, "final_team_b", []),
    ):
        for user_id, _assigned_role in team:
            if user_id not in lobby_ids:
                return user_id

    return None


def add_player(guild_id, user_id, location):
    state = get_state(guild_id)
    player = players.get(user_id)

    if not player or not player.get("ign"):
        return False, "That registered player could not be found."

    if user_id in state.lobby or user_id in state.waiting_room:
        return False, f"**{player['ign']}** is already signed up."

    if location == "lobby":
        if state.captain_draft:
            return False, "You cannot add someone to the lobby during an active Captain Draft."

        if len(state.lobby) >= state.lobby_size:
            return False, "The lobby is full. Add them to the waiting room or use `/swapplayers`."

        state.lobby.append(user_id)
        destination = "lobby"
    elif location == "waiting":
        state.waiting_room.append(user_id)
        destination = "waiting room"
    else:
        return False, "Unknown destination."

    state.last_signup_time = time.time()
    save_lobby_state(guild_id)

    if location == "lobby" and len(state.lobby) >= state.lobby_size:
        queue_lobby_full_notification(guild_id)

    return True, f"Added **{player['ign']}** to the **{destination}**."


def move_player(guild_id, user_id, destination):
    state = get_state(guild_id)
    player = players.get(user_id)
    ign = player.get("ign") if player else None

    if not ign:
        return False, "That registered player could not be found."

    if user_id not in state.lobby and user_id not in state.waiting_room:
        return False, f"**{ign}** is not currently signed up."

    completed_random_draft = (
        bool(getattr(state, "draft_result", None))
        and not getattr(state, "captain_draft", None)
        and bool(getattr(state, "final_team_a", []))
        and bool(getattr(state, "final_team_b", []))
    )

    if destination == "waiting":
        if user_id in state.waiting_room:
            return False, f"**{ign}** is already in the waiting room."

        if state.captain_draft:
            return False, "You cannot move an active Captain Draft player out of the lobby."

        if completed_random_draft:
            # During a completed Random Draft, moving a drafted lobby player
            # out is treated as a straight substitution with the next person
            # in the waiting room. The replacement inherits the exact same
            # team and assigned role.
            if not state.waiting_room:
                return (
                    False,
                    "There is nobody in the waiting room to replace that drafted player.",
                )

            team_label = None
            assigned_role = None

            for team in (state.final_team_a, state.final_team_b):
                for drafted_user_id, role in team:
                    if drafted_user_id == user_id:
                        assigned_role = role
                        break
                if assigned_role is not None:
                    break

            if assigned_role is None:
                return False, "That lobby player could not be found in the drafted teams."

            replacement_id = state.waiting_room[0]
            replacement = players.get(replacement_id)
            replacement_ign = (
                replacement.get("ign")
                if replacement and replacement.get("ign")
                else str(replacement_id)
            )

            lobby_index = state.lobby.index(user_id)

            # Preserve both the lobby slot and the waiting-room queue slot.
            state.lobby[lobby_index] = replacement_id
            state.waiting_room[0] = user_id

            team_label, assigned_role = _replace_drafted_player(
                state,
                user_id,
                replacement_id,
            )

            state.votes.pop(user_id, None)

            if user_id in state.captain_volunteers:
                state.captain_volunteers.remove(user_id)

            save_lobby_state(guild_id)

            return (
                True,
                f"Moved **{ign}** to the **waiting room**. "
                f"**{replacement_ign}** replaced them on **{team_label}** "
                f"as **{assigned_role}**.",
            )

        state.lobby.remove(user_id)
        state.waiting_room.append(user_id)
        state.votes.pop(user_id, None)

        if user_id in state.captain_volunteers:
            state.captain_volunteers.remove(user_id)

        destination_label = "waiting room"

    elif destination == "lobby":
        if user_id in state.lobby:
            return False, f"**{ign}** is already in the lobby."

        if state.captain_draft:
            return False, "You cannot add a player to the lobby during an active Captain Draft."

        if len(state.lobby) >= state.lobby_size:
            return False, "The lobby is full. Use `/swapplayers` to exchange them with a lobby player."

        missing_drafted_user_id = None
        if completed_random_draft:
            missing_drafted_user_id = _find_missing_drafted_player(state)

        state.waiting_room.remove(user_id)
        state.lobby.append(user_id)
        destination_label = "lobby"

        # This covers a draft that already has an open lobby slot because a
        # drafted player was removed by some other admin action. The incoming
        # player inherits that missing player's exact drafted slot.
        replacement_note = ""
        if completed_random_draft and missing_drafted_user_id is not None:
            team_label, assigned_role = _replace_drafted_player(
                state,
                missing_drafted_user_id,
                user_id,
            )

            if team_label:
                replacement_note = (
                    f" They replaced the open drafted slot on **{team_label}** "
                    f"as **{assigned_role}**."
                )

    else:
        return False, "Unknown destination."

    save_lobby_state(guild_id)

    if destination == "lobby" and len(state.lobby) >= state.lobby_size:
        queue_lobby_full_notification(guild_id)

    message = f"Moved **{ign}** to the **{destination_label}**."
    if destination == "lobby":
        message += replacement_note

    return True, message


def move_player_to_other_area(guild_id, user_id):
    state = get_state(guild_id)

    if user_id in state.lobby:
        return move_player(guild_id, user_id, "waiting")

    if user_id in state.waiting_room:
        return move_player(guild_id, user_id, "lobby")

    player = players.get(user_id)
    ign = player.get("ign") if player else str(user_id)
    return False, f"**{ign}** is not currently signed up."


def set_queue_position(guild_id, user_id, position):
    state = get_state(guild_id)
    player = players.get(user_id)
    ign = player.get("ign") if player else None

    if not ign:
        return False, "That registered player could not be found."

    if user_id not in state.waiting_room:
        return False, f"**{ign}** is not currently in the waiting room."

    if position < 1 or position > len(state.waiting_room):
        return (
            False,
            f"Position must be between **1** and **{len(state.waiting_room)}**.",
        )

    state.waiting_room.remove(user_id)
    state.waiting_room.insert(position - 1, user_id)
    save_lobby_state(guild_id)

    return True, f"Moved **{ign}** to waiting-room position **#{position}**."


def swap_players(guild_id, lobby_user_id, waiting_user_id):
    state = get_state(guild_id)

    lobby_player = players.get(lobby_user_id)
    waiting_player = players.get(waiting_user_id)

    if not lobby_player or not lobby_player.get("ign"):
        return False, "The selected lobby player could not be found."

    if not waiting_player or not waiting_player.get("ign"):
        return False, "The selected waiting-room player could not be found."

    if state.captain_draft:
        return False, "You cannot swap active Captain Draft players."

    if lobby_user_id not in state.lobby:
        return False, f"**{lobby_player['ign']}** is not currently in the lobby."

    if waiting_user_id not in state.waiting_room:
        return False, f"**{waiting_player['ign']}** is not currently in the waiting room."

    lobby_index = state.lobby.index(lobby_user_id)
    waiting_index = state.waiting_room.index(waiting_user_id)

    completed_random_draft = (
        bool(getattr(state, "draft_result", None))
        and bool(getattr(state, "final_team_a", []))
        and bool(getattr(state, "final_team_b", []))
    )

    if completed_random_draft:
        team_label, assigned_role = _replace_drafted_player(
            state,
            lobby_user_id,
            waiting_user_id,
        )

        if team_label is None:
            return False, "That lobby player could not be found in the drafted teams."
    else:
        team_label = None
        assigned_role = None

    # Preserve each player's exact lobby / waiting-room position.
    state.lobby[lobby_index] = waiting_user_id
    state.waiting_room[waiting_index] = lobby_user_id

    state.votes.pop(lobby_user_id, None)

    if lobby_user_id in state.captain_volunteers:
        state.captain_volunteers.remove(lobby_user_id)

    save_lobby_state(guild_id)

    if team_label:
        return (
            True,
            f"Swapped **{lobby_player['ign']}** with **{waiting_player['ign']}**. "
            f"**{waiting_player['ign']}** took their spot on **{team_label}** "
            f"as **{assigned_role}**.",
        )

    return (
        True,
        f"Swapped **{lobby_player['ign']}** with **{waiting_player['ign']}**.",
    )


# ========================================================================
# PLAYER INSPECTOR
# ========================================================================

import time

from config import normalize_roles
import database as repository


def _percentage(part, whole):
    if not whole:
        return 0.0
    return round((part / whole) * 100, 1)


def _format_remaining(expires_at, now=None):
    if expires_at is None:
        return "Permanent"

    now = time.time() if now is None else now
    remaining = max(0, int(expires_at - now))

    days, remaining = divmod(remaining, 86400)
    hours, remaining = divmod(remaining, 3600)
    minutes, _seconds = divmod(remaining, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")

    return " ".join(parts)


def search_player_choices(query, limit=25, db_file=None):
    return repository.search_registered_players(
        query=query,
        limit=limit,
        db_file=db_file,
    )


def resolve_player(identifier, db_file=None):
    return repository.find_player(identifier, db_file=db_file)


def _live_discord_identity(guild_id, user_id, fallback_name):
    display_name = fallback_name
    username = None

    if runtime.bot_client:
        guild = runtime.bot_client.get_guild(guild_id)
        if guild:
            member = guild.get_member(user_id)
            if member:
                display_name = member.display_name
                username = member.name

    return display_name, username


def _team_assignment(team, user_id):
    for entry in team or []:
        try:
            drafted_user_id, assigned_role = entry
        except (TypeError, ValueError):
            continue

        if drafted_user_id == user_id:
            return assigned_role

    return None


def _current_status(guild_id, user_id):
    state = get_state(guild_id)

    captain_draft = getattr(state, "captain_draft", None)
    if captain_draft:
        role = _team_assignment(
            getattr(captain_draft, "team_a", []),
            user_id,
        )
        if role is not None:
            return f"Captain Draft • Team A — {role}"

        role = _team_assignment(
            getattr(captain_draft, "team_b", []),
            user_id,
        )
        if role is not None:
            return f"Captain Draft • Team B — {role}"

    role = _team_assignment(
        getattr(state, "final_team_a", []),
        user_id,
    )
    if role is not None:
        return f"Team A — {role}"

    role = _team_assignment(
        getattr(state, "final_team_b", []),
        user_id,
    )
    if role is not None:
        return f"Team B — {role}"

    waiting_room = list(getattr(state, "waiting_room", []))
    if user_id in waiting_room:
        return f"Waiting Room #{waiting_room.index(user_id) + 1}"

    lobby = list(getattr(state, "lobby", []))
    if user_id in lobby:
        return f"Lobby #{lobby.index(user_id) + 1}"

    return "Not signed up"


def build_player_snapshot(guild_id, user_id, now=None, db_file=None):
    now = time.time() if now is None else now

    player = repository.get_player_record(user_id, db_file=db_file)
    if not player:
        return None

    roles = normalize_roles(player.get("roles", []))
    aliases = repository.get_player_aliases(user_id, db_file=db_file)
    weight = repository.get_hidden_weight(
        guild_id,
        user_id,
        db_file=db_file,
    )
    timeout = repository.get_active_timeout(
        guild_id,
        user_id,
        now=now,
        db_file=db_file,
    )
    stats = repository.get_draft_stats(
        guild_id,
        user_id,
        db_file=db_file,
    )
    role_history = repository.get_role_history(
        guild_id,
        user_id,
        db_file=db_file,
    )
    recent_drafts = repository.get_recent_drafts(
        guild_id,
        user_id,
        limit=5,
        db_file=db_file,
    )

    drafts_played = stats["drafts_played"]

    timeout_summary = "None"
    if timeout:
        timeout_summary = _format_remaining(timeout["expires_at"], now=now)

    discord_display_name, discord_username = _live_discord_identity(
        guild_id,
        user_id,
        player["discord_name"],
    )
    current_status = _current_status(guild_id, user_id)

    return {
        "user_id": user_id,
        "discord_name": discord_display_name,
        "discord_username": discord_username,
        "ign": player["ign"],
        "aliases": aliases,
        "roles": roles,
        "has_played_backline": player["has_played_backline"],
        "hidden_weight": weight,
        "timeout": timeout,
        "timeout_summary": timeout_summary,
        "current_status": current_status,
        "drafts_played": drafts_played,
        "team_a_assignments": stats["team_a_assignments"],
        "team_b_assignments": stats["team_b_assignments"],
        "times_captain": stats["times_captain"],
        "captain_rate": _percentage(stats["times_captain"], drafts_played),
        "primary_assignments": stats["primary_assignments"],
        "primary_hit_rate": _percentage(
            stats["primary_assignments"],
            drafts_played,
        ),
        "off_role_assignments": stats["off_role_assignments"],
        "off_role_rate": _percentage(
            stats["off_role_assignments"],
            drafts_played,
        ),
        "last_draft_at": stats["last_draft_at"],
        "role_history": role_history,
        "recent_drafts": recent_drafts,
    }


# ========================================================================
# DRAFT HISTORY
# ========================================================================

import math

import discord

from database import (
    get_draft_count,
    get_draft_details,
    get_draft_history_page,
)


HISTORY_PAGE_SIZE = 5


def format_mode(mode):
    normalized = str(mode or "").strip().casefold()
    if normalized == "captain":
        return "Captain Draft"
    if normalized == "random":
        return "Random Draft"
    if not normalized:
        return "Draft"
    return f"{str(mode).strip().title()} Draft"


def format_player_name(player):
    if player.get("ign"):
        return player["ign"]
    if player.get("discord_name"):
        return player["discord_name"]
    return f"<@{player['user_id']}>"


def get_history_page(guild_id, page, page_size=HISTORY_PAGE_SIZE):
    page_size = max(1, int(page_size))
    total = get_draft_count(guild_id)
    total_pages = max(1, math.ceil(total / page_size)) if total else 1
    page = min(max(0, int(page)), total_pages - 1)
    drafts = get_draft_history_page(
        guild_id,
        limit=page_size,
        offset=page * page_size,
    )
    return {
        "drafts": drafts,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def build_history_embed(page_data, selected_draft_id=None):
    drafts = page_data["drafts"]
    page = page_data["page"]
    total = page_data["total"]
    total_pages = page_data["total_pages"]

    embed = discord.Embed(
        title="Draft History",
        description=(
            f"Page **{page + 1}** of **{total_pages}** • "
            f"**{total}** completed draft{'s' if total != 1 else ''}"
        ),
        color=discord.Color.blue(),
    )

    if not drafts:
        embed.add_field(
            name="No completed drafts",
            value="Completed drafts will appear here after they are saved.",
            inline=False,
        )
        return embed

    for draft in drafts:
        draft_id = draft["draft_id"]
        mode = format_mode(draft["mode"])
        created_at = int(draft["created_at"])
        player_count = int(draft.get("player_count") or 0)

        lines = [
            f"<t:{created_at}:f>",
            f"Players: **{player_count}**",
        ]

        if str(draft.get("mode") or "").casefold() == "captain":
            captain_a = draft.get("captain_a_ign") or (
                f"<@{draft['captain_a']}>" if draft.get("captain_a") else "Unknown"
            )
            captain_b = draft.get("captain_b_ign") or (
                f"<@{draft['captain_b']}>" if draft.get("captain_b") else "Unknown"
            )
            lines.append(f"Captains: **{captain_a}** vs **{captain_b}**")

        marker = " • Selected" if draft_id == selected_draft_id else ""
        embed.add_field(
            name=f"#{draft_id} — {mode}{marker}",
            value="\n".join(lines),
            inline=False,
        )

    embed.set_footer(text="Select a draft, then choose View Draft for full teams and roles.")
    return embed


def build_draft_detail_embed(guild_id, draft_id):
    details = get_draft_details(guild_id, draft_id)
    if not details:
        return None

    draft = details["draft"]
    players = details["players"]

    embed = discord.Embed(
        title=f"Draft #{draft['draft_id']} — {format_mode(draft['mode'])}",
        description=f"Completed <t:{int(draft['created_at'])}:f>",
        color=discord.Color.blue(),
    )

    for team_name in ("A", "B"):
        team_players = [player for player in players if player["team"] == team_name]
        lines = []

        for player in team_players:
            name = format_player_name(player)
            captain_text = " — Captain" if player.get("was_captain") else ""
            lines.append(f"**{name}** — {player['assigned_role']}{captain_text}")

        embed.add_field(
            name=f"Team {team_name}",
            value="\n".join(lines) if lines else "No players recorded.",
            inline=False,
        )

    embed.set_footer(text="Draft history does not display hidden player weights.")
    return embed


# ========================================================================
# TEAM TRADES
# ========================================================================

def _find_player(team, user_id):
    for index, (team_user_id, assigned_role) in enumerate(team):
        if team_user_id == user_id:
            return index, assigned_role

    return None, None


def trade_players(guild_id, player_1_id, player_2_id):
    """Swap two drafted players between Team A and Team B.

    Each player keeps their currently assigned role. Only the live draft state
    is changed; historical draft records remain as originally generated.
    """
    state = get_state(guild_id)

    if player_1_id == player_2_id:
        return False, "Choose two different players."

    team_a = getattr(state, "final_team_a", [])
    team_b = getattr(state, "final_team_b", [])

    if not team_a or not team_b or not getattr(state, "draft_result", None):
        return False, "There is no completed draft to trade players in."

    if getattr(state, "captain_draft", None):
        return False, "Finish the active Captain Draft before trading players."

    p1_a_index, p1_a_role = _find_player(team_a, player_1_id)
    p1_b_index, p1_b_role = _find_player(team_b, player_1_id)

    p2_a_index, p2_a_role = _find_player(team_a, player_2_id)
    p2_b_index, p2_b_role = _find_player(team_b, player_2_id)

    player_1_found = p1_a_index is not None or p1_b_index is not None
    player_2_found = p2_a_index is not None or p2_b_index is not None

    if not player_1_found:
        return False, "The first selected player is not in the current draft."

    if not player_2_found:
        return False, "The second selected player is not in the current draft."

    if p1_a_index is not None and p2_a_index is not None:
        return False, "Both selected players are already on Team A."

    if p1_b_index is not None and p2_b_index is not None:
        return False, "Both selected players are already on Team B."

    # Normalize the swap so player_a_id is the player currently on Team A and
    # player_b_id is the player currently on Team B.
    if p1_a_index is not None:
        player_a_id = player_1_id
        player_a_index = p1_a_index
        player_a_role = p1_a_role

        player_b_id = player_2_id
        player_b_index = p2_b_index
        player_b_role = p2_b_role
    else:
        player_a_id = player_2_id
        player_a_index = p2_a_index
        player_a_role = p2_a_role

        player_b_id = player_1_id
        player_b_index = p1_b_index
        player_b_role = p1_b_role

    # Each player keeps their own assigned role when moving teams.
    state.final_team_a[player_a_index] = (player_b_id, player_b_role)
    state.final_team_b[player_b_index] = (player_a_id, player_a_role)

    player_a_ign = players.get(player_a_id, {}).get("ign", str(player_a_id))
    player_b_ign = players.get(player_b_id, {}).get("ign", str(player_b_id))

    return (
        True,
        "**Trade completed**\n"
        f"**{player_a_ign}** — {player_a_role}: Team A → Team B\n"
        f"**{player_b_ign}** — {player_b_role}: Team B → Team A"
    )


# ========================================================================
# ADMIN PLAYER HELPERS
# ========================================================================

import discord
from discord import app_commands


import draft_service as svc


def _admin_manage_eligible_ids(interaction: discord.Interaction):
    state = get_state(interaction.guild.id)

    eligible_ids = {
        member.id
        for member in interaction.guild.members
    }

    eligible_ids.update(state.lobby)
    eligible_ids.update(state.waiting_room)

    return eligible_ids

def _discord_member_names(guild, user_id):
    """Return searchable Discord names for one guild member."""
    member = guild.get_member(user_id)
    if not member:
        return []

    names = []

    for value in (
        member.nick,
        member.display_name,
        member.name,
    ):
        if not value:
            continue

        clean = str(value).strip()
        if clean and clean.casefold() not in {name.casefold() for name in names}:
            names.append(clean)

    return names


def admin_player_identity_text(guild, user_id, ign=None):
    """Compact Discord identity text without repeating the IGN."""
    member = guild.get_member(user_id)
    if not member:
        return ""

    ign_cf = ign.casefold() if ign else None
    parts = []
    seen = set()

    for value, prefix in (
        (member.nick, ""),
        (getattr(member, "name", None), "@"),
        (getattr(member, "display_name", None), ""),
    ):
        if not value:
            continue

        clean = str(value).strip()
        clean_cf = clean.casefold()

        if ign_cf and clean_cf == ign_cf:
            continue
        if clean_cf in seen:
            continue

        parts.append(f"{prefix}{clean}")
        seen.add(clean_cf)

    return " | ".join(parts)


def admin_player_choice_label(guild, user_id, ign):
    """Autocomplete label: IGN plus non-duplicate Discord identity."""
    identity = admin_player_identity_text(guild, user_id, ign)

    if not identity:
        return ign[:100]

    return f"{ign} — {identity}"[:100]


def _player_matches_admin_value(guild, user_id, data, value):
    """Exact-match an IGN, server nickname/display name, or Discord username."""
    target = value.strip()
    if not target:
        return False

    target_cf = target.lstrip("@").casefold()

    ign = data.get("ign", "")
    if ign and ign.casefold() == target.casefold():
        return True

    for discord_name in _discord_member_names(guild, user_id):
        if discord_name.lstrip("@").casefold() == target_cf:
            return True

    return False


def _player_matches_admin_search(guild, user_id, data, current):
    """Substring search across IGN and Discord identities for autocomplete."""
    query = current.strip().lstrip("@").casefold()
    if not query:
        return True

    values = [data.get("ign", "")]
    values.extend(_discord_member_names(guild, user_id))

    return any(
        query in str(value).lstrip("@").casefold()
        for value in values
        if value
    )


def find_player_matches(guild, query, candidate_ids):
    """Find candidate players by partial IGN/nickname/display-name/username."""
    candidate_ids = set(candidate_ids)
    matches = []

    for user_id, data in svc.players.items():
        ign = data.get("ign")
        if not ign or user_id not in candidate_ids:
            continue

        if not _player_matches_admin_search(guild, user_id, data, query):
            continue

        is_exact = _player_matches_admin_value(
            guild,
            user_id,
            data,
            query,
        )
        matches.append((not is_exact, ign.casefold(), user_id))

    matches.sort()
    return [user_id for _not_exact, _ign, user_id in matches]


def resolve_player_search(guild, query, candidate_ids):
    """Return (selected_user_id, matches) without guessing ambiguous names."""
    matches = find_player_matches(guild, query, candidate_ids)

    exact_matches = [
        user_id
        for user_id in matches
        if _player_matches_admin_value(
            guild,
            user_id,
            svc.players[user_id],
            query,
        )
    ]

    if len(exact_matches) == 1:
        return exact_matches[0], matches

    if len(matches) == 1:
        return matches[0], matches

    return None, matches


def find_registered_player_matches(guild, query, excluded_ids=None):
    """Find registered guild members by partial IGN/nickname/username match."""
    excluded_ids = set(excluded_ids or [])
    candidate_ids = {
        member.id
        for member in guild.members
        if member.id not in excluded_ids
    }

    return find_player_matches(
        guild,
        query,
        candidate_ids,
    )


def _find_admin_player(interaction: discord.Interaction, value: str):
    eligible_ids = _admin_manage_eligible_ids(interaction)

    try:
        user_id = int(value)
        if user_id in eligible_ids and user_id in svc.players:
            return user_id
    except ValueError:
        pass

    matches = [
        user_id
        for user_id, data in svc.players.items()
        if user_id in eligible_ids
        and _player_matches_admin_value(
            interaction.guild,
            user_id,
            data,
            value,
        )
    ]

    # Do not guess when two users share the same nickname/username/IGN.
    return matches[0] if len(matches) == 1 else None

async def admin_registered_player_autocomplete(interaction: discord.Interaction, current: str):
    if interaction.guild is None:
        return []

    state = get_state(interaction.guild.id)
    eligible_ids = _admin_manage_eligible_ids(interaction)
    matches = []

    for user_id, data in svc.players.items():
        ign = data.get("ign")
        if not ign or user_id not in eligible_ids:
            continue
        if user_id in state.lobby or user_id in state.waiting_room:
            continue
        if not _player_matches_admin_search(
            interaction.guild,
            user_id,
            data,
            current,
        ):
            continue

        matches.append((
            admin_player_choice_label(interaction.guild, user_id, ign),
            ign,
            user_id,
        ))

    matches.sort(key=lambda item: item[1].casefold())

    return [
        app_commands.Choice(name=label, value=str(user_id))
        for label, _ign, user_id in matches[:25]
    ]

async def admin_signed_player_autocomplete(interaction: discord.Interaction, current: str):
    if interaction.guild is None:
        return []

    state = get_state(interaction.guild.id)
    current_cf = current.casefold().strip()
    matches = []

    for user_id in list(state.lobby) + list(state.waiting_room):
        data = svc.players.get(user_id)
        if not data or not data.get("ign"):
            continue

        ign = data["ign"]
        if current_cf and current_cf not in ign.casefold():
            continue

        matches.append((ign, user_id))

    matches.sort(key=lambda item: item[0].casefold())

    return [
        app_commands.Choice(name=ign[:100], value=str(user_id))
        for ign, user_id in matches[:25]
    ]

async def admin_waiting_player_autocomplete(interaction: discord.Interaction, current: str):
    if interaction.guild is None:
        return []

    state = get_state(interaction.guild.id)
    current_cf = current.casefold().strip()
    matches = []

    for user_id in state.waiting_room:
        data = svc.players.get(user_id)
        if not data or not data.get("ign"):
            continue

        ign = data["ign"]
        if current_cf and current_cf not in ign.casefold():
            continue

        matches.append((ign, user_id))

    return [
        app_commands.Choice(name=ign[:100], value=str(user_id))
        for ign, user_id in matches[:25]
    ]

async def admin_lobby_player_autocomplete(interaction: discord.Interaction, current: str):
    if interaction.guild is None:
        return []

    state = get_state(interaction.guild.id)
    current_cf = current.casefold().strip()
    matches = []

    for user_id in state.lobby:
        data = svc.players.get(user_id)
        if not data or not data.get("ign"):
            continue

        ign = data["ign"]
        if current_cf and current_cf not in ign.casefold():
            continue

        matches.append((ign, user_id))

    return [
        app_commands.Choice(name=ign[:100], value=str(user_id))
        for ign, user_id in matches[:25]
    ]


# ========================================================================
# VIEW CONTEXT
# ========================================================================

from types import SimpleNamespace

from database import save_guild_config


def get_view_context(guild_id):
    state = get_state(guild_id)

    return SimpleNamespace(
        guild_id=guild_id,

        players=players,
        lobby=state.lobby,
        waiting_room=state.waiting_room,
        lobby_size=state.lobby_size,

        get_captain_draft=lambda: state.captain_draft,

        signup_player=signup_player,
        drop_player=drop_player,
        vote_player=vote_player,
        volunteer_captain=volunteer_captain,
        refresh_board=refresh_board,
        show_status=show_status,
        run_startdraft=run_startdraft,
        player_label=player_label,
        is_draft_admin=is_draft_admin,
        kick_from_draft=kick_from_draft,
        timeout_from_draft=timeout_from_draft,
        move_teams_to_voice=move_teams_to_voice,
        wipe_lobby=wipe_lobby,
        reset_draft_only=reset_draft_only,
        post_new_draft_board=post_new_draft_board,
        save_guild_config=save_guild_config,
        handle_captain_pick=handle_captain_pick,
    )

# Imported last to avoid the draft_service <-> views initialization cycle.
from views import DraftBoardView
