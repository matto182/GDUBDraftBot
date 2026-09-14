import time

from config import normalize_roles
from state import get_state
import service_runtime as runtime
import player_inspector_repository as repository


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
