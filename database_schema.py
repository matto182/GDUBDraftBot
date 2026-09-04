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
            roles TEXT NOT NULL,
            has_played_backline INTEGER NOT NULL DEFAULT 0
        )
    """)

    try:
        cursor.execute(
            "ALTER TABLE players ADD COLUMN has_played_backline INTEGER NOT NULL DEFAULT 0"
        )
    except sqlite3.OperationalError:
        pass

    # Migration only: preserve historical capability from old saved records.
    cursor.execute("""
        UPDATE players
        SET has_played_backline = 1
        WHERE has_played_backline = 0
        AND (
            roles LIKE '%Prot Monk%'
            OR roles LIKE '%Heal Monk%'
            OR roles LIKE '%Support/Flag (8)%'
            OR roles LIKE '%8 Support%'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id INTEGER PRIMARY KEY,
            draft_channel_id INTEGER,
            team_a_voice_channel_id INTEGER,
            team_b_voice_channel_id INTEGER,
            admin_role_id INTEGER,
            owner_role_id INTEGER,
            board_message_id INTEGER
        )
    """)

    try:
        cursor.execute("ALTER TABLE guild_config ADD COLUMN board_message_id INTEGER")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE guild_config ADD COLUMN owner_role_id INTEGER")
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS draft_history (
            draft_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            mode TEXT NOT NULL,
            created_at REAL NOT NULL,
            captain_a INTEGER,
            captain_b INTEGER,
            balance_score INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS draft_players (
            draft_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            team TEXT NOT NULL,
            assigned_role TEXT NOT NULL,
            role_priority_index INTEGER NOT NULL,
            was_captain INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (draft_id, user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_weights (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            weight INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lobby_bans (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            banned_by INTEGER,
            created_at REAL NOT NULL,
            expires_at REAL,
            PRIMARY KEY (guild_id, user_id)
        )
    """)


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_dm_cooldown (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            last_sent_at REAL NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    conn.commit()
    conn.close()
