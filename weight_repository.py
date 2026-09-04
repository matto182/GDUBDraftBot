import sqlite3

from config import DB_FILE


def get_guild_player_weights(guild_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, weight
        FROM player_weights
        WHERE guild_id = ?
    """, (guild_id,))
    rows = cursor.fetchall()
    conn.close()
    return {user_id: weight for user_id, weight in rows}


def get_player_weights(guild_id):
    return get_guild_player_weights(guild_id)


def get_player_weight(guild_id, user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT weight
        FROM player_weights
        WHERE guild_id = ? AND user_id = ?
    """, (guild_id, user_id))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0


def set_player_weight(guild_id, user_id, weight):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    if weight == 0:
        cursor.execute(
            "DELETE FROM player_weights WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
    else:
        cursor.execute("""
            INSERT INTO player_weights (guild_id, user_id, weight)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                weight = excluded.weight
        """, (guild_id, user_id, weight))

    conn.commit()
    conn.close()
