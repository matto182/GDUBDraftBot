import sqlite3
from config import DB_FILE


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            discord_id INTEGER PRIMARY KEY,
            discord_name TEXT NOT NULL,
            ign TEXT NOT NULL,
            roles TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id INTEGER PRIMARY KEY,
            draft_channel_id INTEGER,
            team_a_voice_channel_id INTEGER,
            team_b_voice_channel_id INTEGER,
            admin_role_id INTEGER,
            board_message_id INTEGER
        )
    """)

    try:
        cursor.execute("ALTER TABLE guild_config ADD COLUMN board_message_id INTEGER")
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lobby_state (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            area TEXT NOT NULL,
            position INTEGER NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guild_runtime_state (
            guild_id INTEGER PRIMARY KEY,
            last_signup_time REAL
        )
    """)

    conn.commit()
    conn.close()


def save_player(discord_id, discord_name, ign, roles):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO players (discord_id, discord_name, ign, roles)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(discord_id) DO UPDATE SET
            discord_name = excluded.discord_name,
            ign = excluded.ign,
            roles = excluded.roles
    """, (
        discord_id,
        discord_name,
        ign,
        ",".join(roles)
    ))

    conn.commit()
    conn.close()


def load_players_into(players):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT discord_id, discord_name, ign, roles FROM players")
    rows = cursor.fetchall()

    conn.close()

    players.clear()

    for discord_id, discord_name, ign, roles_text in rows:
        players[discord_id] = {
            "discord_name": discord_name,
            "ign": ign,
            "roles": roles_text.split(",") if roles_text else [],
        }


def save_guild_config(
    guild_id,
    draft_channel_id=None,
    team_a_voice_channel_id=None,
    team_b_voice_channel_id=None,
    admin_role_id=None,
):
    current = get_guild_config(guild_id) or {}

    draft_channel_id = draft_channel_id or current.get("draft_channel_id")
    team_a_voice_channel_id = team_a_voice_channel_id or current.get("team_a_voice_channel_id")
    team_b_voice_channel_id = team_b_voice_channel_id or current.get("team_b_voice_channel_id")
    admin_role_id = admin_role_id or current.get("admin_role_id")
    board_message_id = current.get("board_message_id")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO guild_config (
            guild_id,
            draft_channel_id,
            team_a_voice_channel_id,
            team_b_voice_channel_id,
            admin_role_id,
            board_message_id
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            draft_channel_id = excluded.draft_channel_id,
            team_a_voice_channel_id = excluded.team_a_voice_channel_id,
            team_b_voice_channel_id = excluded.team_b_voice_channel_id,
            admin_role_id = excluded.admin_role_id,
            board_message_id = excluded.board_message_id
    """, (
        guild_id,
        draft_channel_id,
        team_a_voice_channel_id,
        team_b_voice_channel_id,
        admin_role_id,
        board_message_id,
    ))

    conn.commit()
    conn.close()


def get_guild_config(guild_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            draft_channel_id,
            team_a_voice_channel_id,
            team_b_voice_channel_id,
            admin_role_id,
            board_message_id
        FROM guild_config
        WHERE guild_id = ?
    """, (guild_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "draft_channel_id": row[0],
        "team_a_voice_channel_id": row[1],
        "team_b_voice_channel_id": row[2],
        "admin_role_id": row[3],
        "board_message_id": row[4],
    }


def save_board_message_id(guild_id, board_message_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE guild_config
        SET board_message_id = ?
        WHERE guild_id = ?
    """, (board_message_id, guild_id))

    conn.commit()
    conn.close()


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