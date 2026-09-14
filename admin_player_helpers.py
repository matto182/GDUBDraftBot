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
