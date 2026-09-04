import sqlite3
import time

from config import DB_FILE


def set_lobby_ban(guild_id, user_id, banned_by, duration_seconds=None):
    now = time.time()
    expires_at = None if duration_seconds is None else now + duration_seconds

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO lobby_bans (
            guild_id,
            user_id,
            banned_by,
            created_at,
            expires_at
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET
            banned_by = excluded.banned_by,
            created_at = excluded.created_at,
            expires_at = excluded.expires_at
    """, (
        guild_id,
        user_id,
        banned_by,
        now,
        expires_at
    ))

    conn.commit()
    conn.close()

    return expires_at


def remove_lobby_ban(guild_id, user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM lobby_bans
        WHERE guild_id = ?
        AND user_id = ?
    """, (guild_id, user_id))

    removed = cursor.rowcount > 0

    conn.commit()
    conn.close()

    return removed


def get_lobby_ban(guild_id, user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT banned_by, created_at, expires_at
        FROM lobby_bans
        WHERE guild_id = ?
        AND user_id = ?
    """, (guild_id, user_id))

    row = cursor.fetchone()

    if not row:
        conn.close()
        return None

    banned_by, created_at, expires_at = row

    # Expired temporary bans clean themselves up the next time they are checked.
    if expires_at is not None and expires_at <= time.time():
        cursor.execute("""
            DELETE FROM lobby_bans
            WHERE guild_id = ?
            AND user_id = ?
        """, (guild_id, user_id))
        conn.commit()
        conn.close()
        return None

    conn.close()

    return {
        "guild_id": guild_id,
        "user_id": user_id,
        "banned_by": banned_by,
        "created_at": created_at,
        "expires_at": expires_at,
    }


def cleanup_expired_lobby_bans(guild_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM lobby_bans
        WHERE guild_id = ?
        AND expires_at IS NOT NULL
        AND expires_at <= ?
    """, (guild_id, time.time()))

    removed = cursor.rowcount

    conn.commit()
    conn.close()

    return removed


def get_active_lobby_bans(guild_id):
    cleanup_expired_lobby_bans(guild_id)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_id, banned_by, created_at, expires_at
        FROM lobby_bans
        WHERE guild_id = ?
        ORDER BY
            CASE WHEN expires_at IS NULL THEN 1 ELSE 0 END,
            expires_at ASC,
            created_at ASC
    """, (guild_id,))

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "user_id": user_id,
            "banned_by": banned_by,
            "created_at": created_at,
            "expires_at": expires_at,
        }
        for user_id, banned_by, created_at, expires_at in rows
    ]
