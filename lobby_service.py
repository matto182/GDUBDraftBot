import time

import discord

from database import get_lobby_ban
from state import get_state
from service_runtime import players
from lobby_state_service import fill_lobby_from_waiting_room, save_lobby_state
from board_service import build_draft_board_embed, player_label, post_new_draft_board
from moderation_service import format_timeout_remaining


async def reset_draft_only(interaction: discord.Interaction, silent=False):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    state.final_team_a = []
    state.final_team_b = []
    state.captain_draft = None
    state.draft_result = None
    state.votes.clear()
    state.captain_volunteers.clear()

    fill_lobby_from_waiting_room(guild_id)
    save_lobby_state(guild_id)

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

    await interaction.response.send_message(
        f"Kicked {player_label(guild_id, user_id)} from the draft.",
        ephemeral=True
    )

    await post_new_draft_board(guild_id)

async def signup_player(interaction: discord.Interaction, silent=False):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

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
    if not state.captain_draft and not state.draft_result and len(state.lobby) < 16:
        fill_lobby_from_waiting_room(guild_id)

    if state.captain_draft or state.draft_result or len(state.lobby) >= 16 or state.waiting_room:
        state.waiting_room.append(user_id)
    else:
        state.lobby.append(user_id)

    state.last_signup_time = time.time()
    save_lobby_state(guild_id)

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message("Signup updated.", ephemeral=True)

    return True

async def drop_player(interaction: discord.Interaction, silent=False):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

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

