import discord
from discord import app_commands

from state import get_state

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
        and data.get("ign", "").casefold() == value.casefold()
    ]

    return matches[0] if len(matches) == 1 else None

async def admin_registered_player_autocomplete(interaction: discord.Interaction, current: str):
    if interaction.guild is None:
        return []

    state = get_state(interaction.guild.id)
    eligible_ids = _admin_manage_eligible_ids(interaction)
    current_cf = current.casefold().strip()
    matches = []

    for user_id, data in svc.players.items():
        ign = data.get("ign")
        if not ign or user_id not in eligible_ids:
            continue
        if user_id in state.lobby or user_id in state.waiting_room:
            continue
        if current_cf and current_cf not in ign.casefold():
            continue
        matches.append((ign, user_id))

    matches.sort(key=lambda item: item[0].casefold())

    return [
        app_commands.Choice(name=ign[:100], value=str(user_id))
        for ign, user_id in matches[:25]
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
