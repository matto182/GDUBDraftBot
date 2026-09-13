import asyncio
import time

import discord

from database import (
    claim_lobby_full_notification,
    get_guild_config,
    release_lobby_full_notification_claim,
)
from state import get_state
import service_runtime as runtime


async def maybe_send_lobby_full_notification(guild_id):
    """Ping the active 16-player lobby at most once per guild every 4 hours."""
    state = get_state(guild_id)

    # Only announce a newly full pre-draft lobby.
    if len(state.lobby) != 16:
        return False

    if state.captain_draft or state.draft_result:
        return False

    config = get_guild_config(guild_id)
    if not config or not config.get("draft_channel_id"):
        return False

    claimed_at = time.time()

    if not claim_lobby_full_notification(guild_id, claimed_at):
        return False

    # Snapshot the exact 16 players that caused the full-lobby event.
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
            len(current_state.lobby) != 16
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
