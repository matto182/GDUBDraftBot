import sqlite3
import time

from config import DB_FILE


LOBBY_FULL_NOTIFICATION_COOLDOWN_SECONDS = 4 * 60 * 60


def get_lobby_full_notification_last_sent(guild_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT last_sent_at
        FROM lobby_full_notification_cooldown
        WHERE guild_id = ?
        """,
        (guild_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def claim_lobby_full_notification(guild_id, now=None):
    """Atomically claim the guild's 4-hour lobby-full notification slot."""
    now = time.time() if now is None else now

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            """
            SELECT last_sent_at
            FROM lobby_full_notification_cooldown
            WHERE guild_id = ?
            """,
            (guild_id,),
        )
        row = cursor.fetchone()

        if row and (now - row[0]) < LOBBY_FULL_NOTIFICATION_COOLDOWN_SECONDS:
            conn.rollback()
            return False

        cursor.execute(
            """
            INSERT INTO lobby_full_notification_cooldown (guild_id, last_sent_at)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                last_sent_at = excluded.last_sent_at
            """,
            (guild_id, now),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def release_lobby_full_notification_claim(guild_id, claimed_at):
    """Release a failed-send claim so the next full-lobby event can retry."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM lobby_full_notification_cooldown
        WHERE guild_id = ? AND last_sent_at = ?
        """,
        (guild_id, claimed_at),
    )
    conn.commit()
    conn.close()
