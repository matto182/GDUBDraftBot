import sqlite3
import time

from config import DB_FILE


DM_COOLDOWN_SECONDS = 4 * 60 * 60


def get_player_dm_last_sent(guild_id, user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT last_sent_at
        FROM player_dm_cooldown
        WHERE guild_id = ? AND user_id = ?
    """, (guild_id, user_id))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def player_dm_is_on_cooldown(guild_id, user_id, now=None):
    now = time.time() if now is None else now
    last_sent_at = get_player_dm_last_sent(guild_id, user_id)
    return last_sent_at is not None and (now - last_sent_at) < DM_COOLDOWN_SECONDS


def mark_player_dm_sent(guild_id, user_id, sent_at=None):
    sent_at = time.time() if sent_at is None else sent_at
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO player_dm_cooldown (guild_id, user_id, last_sent_at)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET
            last_sent_at = excluded.last_sent_at
    """, (guild_id, user_id, sent_at))
    conn.commit()
    conn.close()
