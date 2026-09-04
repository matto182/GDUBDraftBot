import sqlite3

from config import DB_FILE


def save_lobby_state_to_db(guild_id, lobby, waiting_room, last_signup_time):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM lobby_state WHERE guild_id = ?", (guild_id,))

    for position, user_id in enumerate(lobby):
        cursor.execute("""
            INSERT INTO lobby_state (guild_id, user_id, area, position)
            VALUES (?, ?, ?, ?)
        """, (guild_id, user_id, "lobby", position))

    for position, user_id in enumerate(waiting_room):
        cursor.execute("""
            INSERT INTO lobby_state (guild_id, user_id, area, position)
            VALUES (?, ?, ?, ?)
        """, (guild_id, user_id, "waiting_room", position))

    cursor.execute("""
        INSERT INTO guild_runtime_state (guild_id, last_signup_time)
        VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            last_signup_time = excluded.last_signup_time
    """, (guild_id, last_signup_time))

    conn.commit()
    conn.close()


def load_lobby_state_from_db(guild_id, players, lobby, waiting_room):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_id, area
        FROM lobby_state
        WHERE guild_id = ?
        ORDER BY position ASC
    """, (guild_id,))

    rows = cursor.fetchall()

    lobby.clear()
    waiting_room.clear()

    for user_id, area in rows:
        if user_id not in players:
            continue

        if area == "lobby":
            lobby.append(user_id)
        elif area == "waiting_room":
            waiting_room.append(user_id)

    cursor.execute("""
        SELECT last_signup_time
        FROM guild_runtime_state
        WHERE guild_id = ?
    """, (guild_id,))

    row = cursor.fetchone()
    conn.close()

    return row[0] if row and row[0] else None
