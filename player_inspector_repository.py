import sqlite3
import time

from config import DB_FILE


def _connect(db_file=None):
    return sqlite3.connect(db_file or DB_FILE)


def search_registered_players(query="", limit=25, db_file=None):
    query = (query or "").strip()
    limit = max(1, min(int(limit), 25))

    conn = _connect(db_file)
    cursor = conn.cursor()

    if query:
        like = f"%{query}%"
        cursor.execute(
            """
            SELECT discord_id, discord_name, ign
            FROM players
            WHERE ign LIKE ? COLLATE NOCASE
               OR discord_name LIKE ? COLLATE NOCASE
               OR CAST(discord_id AS TEXT) LIKE ?
            ORDER BY LOWER(ign), discord_id
            LIMIT ?
            """,
            (like, like, like, limit),
        )
    else:
        cursor.execute(
            """
            SELECT discord_id, discord_name, ign
            FROM players
            ORDER BY LOWER(ign), discord_id
            LIMIT ?
            """,
            (limit,),
        )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "user_id": user_id,
            "discord_name": discord_name,
            "ign": ign,
        }
        for user_id, discord_name, ign in rows
    ]


def get_player_record(user_id, db_file=None):
    conn = _connect(db_file)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT discord_id, discord_name, ign, roles, has_played_backline
        FROM players
        WHERE discord_id = ?
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "user_id": row[0],
        "discord_name": row[1],
        "ign": row[2],
        "roles": row[3],
        "has_played_backline": bool(row[4]),
    }


def find_player(identifier, db_file=None):
    text = str(identifier or "").strip()
    if not text:
        return None

    if text.isdigit():
        record = get_player_record(int(text), db_file=db_file)
        if record:
            return record

    conn = _connect(db_file)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT discord_id, discord_name, ign, roles, has_played_backline
        FROM players
        WHERE ign = ? COLLATE NOCASE
        ORDER BY discord_id
        LIMIT 1
        """,
        (text,),
    )
    row = cursor.fetchone()

    if not row:
        cursor.execute(
            """
            SELECT discord_id, discord_name, ign, roles, has_played_backline
            FROM players
            WHERE discord_name = ? COLLATE NOCASE
            ORDER BY discord_id
            LIMIT 1
            """,
            (text,),
        )
        row = cursor.fetchone()

    conn.close()

    if not row:
        return None

    return {
        "user_id": row[0],
        "discord_name": row[1],
        "ign": row[2],
        "roles": row[3],
        "has_played_backline": bool(row[4]),
    }


def get_hidden_weight(guild_id, user_id, db_file=None):
    conn = _connect(db_file)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT weight
        FROM player_weights
        WHERE guild_id = ? AND user_id = ?
        """,
        (guild_id, user_id),
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0


def get_active_timeout(guild_id, user_id, now=None, db_file=None):
    now = time.time() if now is None else now

    conn = _connect(db_file)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT banned_by, created_at, expires_at
        FROM lobby_bans
        WHERE guild_id = ? AND user_id = ?
        """,
        (guild_id, user_id),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    banned_by, created_at, expires_at = row
    if expires_at is not None and expires_at <= now:
        return None

    return {
        "banned_by": banned_by,
        "created_at": created_at,
        "expires_at": expires_at,
    }


def get_draft_stats(guild_id, user_id, db_file=None):
    conn = _connect(db_file)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            COUNT(*),
            COALESCE(SUM(CASE WHEN dp.was_captain = 1 THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN dp.role_priority_index = 1 THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN dp.role_priority_index = 999 THEN 1 ELSE 0 END), 0),
            MAX(dh.created_at)
        FROM draft_players dp
        JOIN draft_history dh ON dh.draft_id = dp.draft_id
        WHERE dp.guild_id = ? AND dp.user_id = ?
        """,
        (guild_id, user_id),
    )
    row = cursor.fetchone()

    conn.close()

    return {
        "drafts_played": row[0] or 0,
        "times_captain": row[1] or 0,
        "primary_assignments": row[2] or 0,
        "off_role_assignments": row[3] or 0,
        "last_draft_at": row[4],
    }


def get_role_history(guild_id, user_id, db_file=None):
    conn = _connect(db_file)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT assigned_role, COUNT(*)
        FROM draft_players
        WHERE guild_id = ? AND user_id = ?
        GROUP BY assigned_role
        ORDER BY COUNT(*) DESC, assigned_role ASC
        """,
        (guild_id, user_id),
    )
    rows = cursor.fetchall()
    conn.close()

    return [
        {"role": role, "count": count}
        for role, count in rows
    ]


def get_recent_drafts(guild_id, user_id, limit=5, db_file=None):
    limit = max(1, min(int(limit), 10))

    conn = _connect(db_file)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            dh.draft_id,
            dh.mode,
            dh.created_at,
            dh.balance_score,
            dp.team,
            dp.assigned_role,
            dp.role_priority_index,
            dp.was_captain
        FROM draft_players dp
        JOIN draft_history dh ON dh.draft_id = dp.draft_id
        WHERE dp.guild_id = ? AND dp.user_id = ?
        ORDER BY dh.created_at DESC, dh.draft_id DESC
        LIMIT ?
        """,
        (guild_id, user_id, limit),
    )
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "draft_id": draft_id,
            "mode": mode,
            "created_at": created_at,
            "balance_score": balance_score,
            "team": team,
            "assigned_role": assigned_role,
            "role_priority_index": role_priority_index,
            "was_captain": bool(was_captain),
        }
        for (
            draft_id,
            mode,
            created_at,
            balance_score,
            team,
            assigned_role,
            role_priority_index,
            was_captain,
        ) in rows
    ]
