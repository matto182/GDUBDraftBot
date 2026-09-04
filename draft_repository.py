import sqlite3
import time

from config import DB_FILE, normalize_roles, BACKLINE_ROLES


def save_completed_draft(
    guild_id,
    mode,
    team_a,
    team_b,
    players,
    captain_a=None,
    captain_b=None,
    balance_score=None
):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO draft_history (
            guild_id,
            mode,
            created_at,
            captain_a,
            captain_b,
            balance_score
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        guild_id,
        mode,
        time.time(),
        captain_a,
        captain_b,
        balance_score
    ))

    draft_id = cursor.lastrowid

    def get_role_priority(user_id, assigned_role):
        roles = normalize_roles(players[user_id].get("roles", []))

        if assigned_role in roles:
            return roles.index(assigned_role) + 1

        return 999

    for team_name, team in [("A", team_a), ("B", team_b)]:
        for user_id, assigned_role in team:
            was_captain = 1 if user_id in [captain_a, captain_b] else 0

            cursor.execute("""
                INSERT INTO draft_players (
                    draft_id,
                    guild_id,
                    user_id,
                    team,
                    assigned_role,
                    role_priority_index,
                    was_captain
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                draft_id,
                guild_id,
                user_id,
                team_name,
                assigned_role,
                get_role_priority(user_id, assigned_role),
                was_captain
            ))

            # Actual backline assignment also makes the capability flag sticky.
            if assigned_role in BACKLINE_ROLES:
                cursor.execute("""
                    UPDATE players
                    SET has_played_backline = 1
                    WHERE discord_id = ?
                """, (user_id,))
                if user_id in players:
                    players[user_id]["has_played_backline"] = True

    conn.commit()
    conn.close()

    return draft_id


def get_player_stats(guild_id, user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    stats = {}

    cursor.execute("""
        SELECT COUNT(DISTINCT draft_id)
        FROM draft_players
        WHERE guild_id = ?
        AND user_id = ?
    """, (guild_id, user_id))

    stats["drafts_played"] = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM draft_players
        WHERE guild_id = ?
        AND user_id = ?
        AND was_captain = 1
    """, (guild_id, user_id))

    stats["times_captain"] = cursor.fetchone()[0]

    cursor.execute("""
        SELECT assigned_role, COUNT(*)
        FROM draft_players
        WHERE guild_id = ?
        AND user_id = ?
        GROUP BY assigned_role
        ORDER BY COUNT(*) DESC
    """, (guild_id, user_id))

    stats["roles"] = cursor.fetchall()

    cursor.execute("""
        SELECT role_priority_index, COUNT(*)
        FROM draft_players
        WHERE guild_id = ?
        AND user_id = ?
        GROUP BY role_priority_index
        ORDER BY role_priority_index ASC
    """, (guild_id, user_id))

    stats["priority_stats"] = cursor.fetchall()

    conn.close()

    return stats
