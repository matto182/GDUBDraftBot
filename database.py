import sqlite3
from config import DB_FILE, normalize_roles


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

    # Backfill the flag for existing players whose currently saved roles already
    # include a backline role under either the old or current role names.
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

    conn.commit()
    conn.close()


def save_player(discord_id, discord_name, ign, roles, has_played_backline=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    normalized_roles = normalize_roles(roles)

    if has_played_backline is None:
        cursor.execute(
            "SELECT has_played_backline FROM players WHERE discord_id = ?",
            (discord_id,)
        )
        row = cursor.fetchone()
        has_played_backline = row[0] if row else 0

    cursor.execute("""
        INSERT INTO players (
            discord_id,
            discord_name,
            ign,
            roles,
            has_played_backline
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(discord_id) DO UPDATE SET
            discord_name = excluded.discord_name,
            ign = excluded.ign,
            roles = excluded.roles,
            has_played_backline = CASE
                WHEN players.has_played_backline = 1 THEN 1
                ELSE excluded.has_played_backline
            END
    """, (
        discord_id,
        discord_name,
        ign,
        ",".join(normalized_roles),
        1 if has_played_backline else 0
    ))

    conn.commit()
    conn.close()


def load_players_into(players):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT discord_id, discord_name, ign, roles, has_played_backline
        FROM players
    """)
    rows = cursor.fetchall()
    conn.close()

    players.clear()

    for discord_id, discord_name, ign, roles_text, has_played_backline in rows:
        players[discord_id] = {
            "discord_name": discord_name,
            "ign": ign,
            "roles": normalize_roles(roles_text),
            "has_played_backline": bool(has_played_backline),
        }


def save_guild_config(
    guild_id,
    draft_channel_id=None,
    team_a_voice_channel_id=None,
    team_b_voice_channel_id=None,
    admin_role_id=None,
    owner_role_id=None,
):
    current = get_guild_config(guild_id) or {}

    draft_channel_id = draft_channel_id or current.get("draft_channel_id")
    team_a_voice_channel_id = team_a_voice_channel_id or current.get("team_a_voice_channel_id")
    team_b_voice_channel_id = team_b_voice_channel_id or current.get("team_b_voice_channel_id")
    admin_role_id = admin_role_id or current.get("admin_role_id")
    owner_role_id = owner_role_id or current.get("owner_role_id")
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
            owner_role_id,
            board_message_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            draft_channel_id = excluded.draft_channel_id,
            team_a_voice_channel_id = excluded.team_a_voice_channel_id,
            team_b_voice_channel_id = excluded.team_b_voice_channel_id,
            admin_role_id = excluded.admin_role_id,
            owner_role_id = excluded.owner_role_id,
            board_message_id = excluded.board_message_id
    """, (
        guild_id,
        draft_channel_id,
        team_a_voice_channel_id,
        team_b_voice_channel_id,
        admin_role_id,
        owner_role_id,
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
            owner_role_id,
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
        "owner_role_id": row[4],
        "board_message_id": row[5],
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
import time


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
        roles = players[user_id]["roles"]

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


def mark_player_has_played_backline(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE players
        SET has_played_backline = 1
        WHERE discord_id = ?
    """, (user_id,))

    conn.commit()
    conn.close()

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
