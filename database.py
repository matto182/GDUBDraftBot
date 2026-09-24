"""
All SQLite persistence for GDUB Draft Bot.

Consolidated from the former schema/repository modules so database behavior has
one obvious home.
"""

import sys

alias_repository = sys.modules[__name__]


# ========================================================================
# DATABASE SCHEMA
# ========================================================================

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
        CREATE TABLE IF NOT EXISTS player_aliases (
            user_id INTEGER NOT NULL,
            alias TEXT NOT NULL COLLATE NOCASE,
            created_at REAL NOT NULL,
            PRIMARY KEY (user_id, alias)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_player_aliases_alias
        ON player_aliases(alias COLLATE NOCASE)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id INTEGER PRIMARY KEY,
            draft_channel_id INTEGER,
            event_channel_id INTEGER,
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

    try:
        cursor.execute("ALTER TABLE guild_config ADD COLUMN event_channel_id INTEGER")
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lobby_full_notification_cooldown (
            guild_id INTEGER PRIMARY KEY,
            last_sent_at REAL NOT NULL
        )
    """)

    try:
        cursor.execute("ALTER TABLE guild_config ADD COLUMN board_hidden INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


# ========================================================================
# PLAYER RECORDS
# ========================================================================

import sqlite3

from config import DB_FILE, normalize_roles, BACKLINE_ROLES


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
        has_played_backline = bool(row[0]) if row else False

    # Sticky capability flag: once a player has selected backline, remember it.
    if set(normalized_roles) & BACKLINE_ROLES:
        has_played_backline = True

    cursor.execute("""
        INSERT INTO players (
            discord_id, discord_name, ign, roles, has_played_backline
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


# ========================================================================
# GUILD CONFIGURATION
# ========================================================================

import sqlite3

from config import DB_FILE


def save_guild_config(
    guild_id,
    draft_channel_id=None,
    event_channel_id=None,
    team_a_voice_channel_id=None,
    team_b_voice_channel_id=None,
    admin_role_id=None,
    owner_role_id=None,
):
    current = get_guild_config(guild_id) or {}

    draft_channel_id = draft_channel_id or current.get("draft_channel_id")
    event_channel_id = event_channel_id or current.get("event_channel_id")
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
            event_channel_id,
            team_a_voice_channel_id,
            team_b_voice_channel_id,
            admin_role_id,
            owner_role_id,
            board_message_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            draft_channel_id = excluded.draft_channel_id,
            event_channel_id = excluded.event_channel_id,
            team_a_voice_channel_id = excluded.team_a_voice_channel_id,
            team_b_voice_channel_id = excluded.team_b_voice_channel_id,
            admin_role_id = excluded.admin_role_id,
            owner_role_id = excluded.owner_role_id,
            board_message_id = excluded.board_message_id
    """, (
        guild_id,
        draft_channel_id,
        event_channel_id,
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
            event_channel_id,
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
        "event_channel_id": row[1],
        "team_a_voice_channel_id": row[2],
        "team_b_voice_channel_id": row[3],
        "admin_role_id": row[4],
        "owner_role_id": row[5],
        "board_message_id": row[6],
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


def is_board_hidden(guild_id):
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("SELECT board_hidden FROM guild_config WHERE guild_id = ?", (guild_id,)).fetchone()
    return bool(row and row[0])

def set_board_hidden(guild_id, hidden):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("UPDATE guild_config SET board_hidden = ? WHERE guild_id = ?", (int(hidden), guild_id))


# ========================================================================
# LOBBY PERSISTENCE
# ========================================================================

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


# ========================================================================
# DRAFT RECORDING AND PLAYER STATS
# ========================================================================

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


# ========================================================================
# HIDDEN PLAYER WEIGHTS
# ========================================================================

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


# ========================================================================
# LOBBY MODERATION DATA
# ========================================================================

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


# ========================================================================
# DRAFT DM COOLDOWNS
# ========================================================================

import sqlite3
import time

from config import DB_FILE


DM_COOLDOWN_SECONDS = 8 * 60 * 60


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


# ========================================================================
# LOBBY FULL NOTIFICATION COOLDOWN
# ========================================================================

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


# ========================================================================
# DRAFT HISTORY QUERIES
# ========================================================================

import sqlite3

from config import DB_FILE


def _history_connect():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def get_draft_count(guild_id):
    conn = _history_connect()
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS draft_count
            FROM draft_history
            WHERE guild_id = ?
            """,
            (guild_id,),
        ).fetchone()
        return int(row["draft_count"] if row else 0)
    finally:
        conn.close()


def get_draft_history_page(guild_id, limit=5, offset=0):
    limit = max(1, int(limit))
    offset = max(0, int(offset))

    conn = _history_connect()
    try:
        rows = conn.execute(
            """
            SELECT
                dh.draft_id,
                dh.guild_id,
                dh.mode,
                dh.created_at,
                dh.captain_a,
                dh.captain_b,
                dh.balance_score,
                pa.ign AS captain_a_ign,
                pb.ign AS captain_b_ign,
                COUNT(dp.user_id) AS player_count
            FROM draft_history AS dh
            LEFT JOIN draft_players AS dp
                ON dp.draft_id = dh.draft_id
                AND dp.guild_id = dh.guild_id
            LEFT JOIN players AS pa
                ON pa.discord_id = dh.captain_a
            LEFT JOIN players AS pb
                ON pb.discord_id = dh.captain_b
            WHERE dh.guild_id = ?
            GROUP BY dh.draft_id
            ORDER BY dh.created_at DESC, dh.draft_id DESC
            LIMIT ? OFFSET ?
            """,
            (guild_id, limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_draft_details(guild_id, draft_id):
    conn = _history_connect()
    try:
        draft = conn.execute(
            """
            SELECT
                dh.draft_id,
                dh.guild_id,
                dh.mode,
                dh.created_at,
                dh.captain_a,
                dh.captain_b,
                dh.balance_score,
                pa.ign AS captain_a_ign,
                pb.ign AS captain_b_ign
            FROM draft_history AS dh
            LEFT JOIN players AS pa
                ON pa.discord_id = dh.captain_a
            LEFT JOIN players AS pb
                ON pb.discord_id = dh.captain_b
            WHERE dh.guild_id = ?
              AND dh.draft_id = ?
            """,
            (guild_id, draft_id),
        ).fetchone()

        if not draft:
            return None

        player_rows = conn.execute(
            """
            SELECT
                dp.draft_id,
                dp.guild_id,
                dp.user_id,
                dp.team,
                dp.assigned_role,
                dp.role_priority_index,
                dp.was_captain,
                p.ign,
                p.discord_name
            FROM draft_players AS dp
            LEFT JOIN players AS p
                ON p.discord_id = dp.user_id
            WHERE dp.guild_id = ?
              AND dp.draft_id = ?
            ORDER BY
                CASE dp.team WHEN 'A' THEN 0 WHEN 'B' THEN 1 ELSE 2 END,
                CASE dp.assigned_role
                    WHEN 'Frontline' THEN 0
                    WHEN 'Midline' THEN 1
                    WHEN 'Prot Monk' THEN 2
                    WHEN 'Heal Monk' THEN 3
                    WHEN '8 Support' THEN 4
                    ELSE 99
                END,
                dp.user_id
            """,
            (guild_id, draft_id),
        ).fetchall()

        return {
            "draft": dict(draft),
            "players": [dict(row) for row in player_rows],
        }
    finally:
        conn.close()


# ========================================================================
# PLAYER ALIASES
# ========================================================================

import sqlite3
import time

from config import DB_FILE


def _alias_connect(db_file=None):
    return sqlite3.connect(db_file or DB_FILE)


def save_player_alias(user_id, alias, created_at=None, db_file=None):
    alias = str(alias or "").strip()
    if not alias:
        return False

    created_at = time.time() if created_at is None else created_at
    conn = _alias_connect(db_file)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT OR IGNORE INTO player_aliases (user_id, alias, created_at)
            VALUES (?, ?, ?)
            """,
            (user_id, alias, created_at),
        )
        inserted = cursor.rowcount > 0
        conn.commit()
    except sqlite3.OperationalError as error:
        if "no such table: player_aliases" not in str(error).lower():
            raise
        inserted = False
    finally:
        conn.close()

    return inserted


def remove_player_alias(user_id, alias, db_file=None):
    alias = str(alias or "").strip()
    if not alias:
        return False

    conn = _alias_connect(db_file)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            DELETE FROM player_aliases
            WHERE user_id = ? AND alias = ? COLLATE NOCASE
            """,
            (user_id, alias),
        )
        removed = cursor.rowcount > 0
        conn.commit()
    except sqlite3.OperationalError as error:
        if "no such table: player_aliases" not in str(error).lower():
            raise
        removed = False
    finally:
        conn.close()

    return removed


def get_player_aliases(user_id, db_file=None):
    conn = _alias_connect(db_file)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT alias
            FROM player_aliases
            WHERE user_id = ?
            ORDER BY created_at ASC, alias COLLATE NOCASE ASC
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
    except sqlite3.OperationalError as error:
        if "no such table: player_aliases" not in str(error).lower():
            raise
        rows = []
    finally:
        conn.close()

    return [row[0] for row in rows]


def resolve_alias_user_id(alias, db_file=None):
    alias = str(alias or "").strip()
    if not alias:
        return None

    conn = _alias_connect(db_file)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT DISTINCT user_id
            FROM player_aliases
            WHERE alias = ? COLLATE NOCASE
            ORDER BY user_id
            LIMIT 2
            """,
            (alias,),
        )
        rows = cursor.fetchall()
    except sqlite3.OperationalError as error:
        if "no such table: player_aliases" not in str(error).lower():
            raise
        rows = []
    finally:
        conn.close()

    if len(rows) != 1:
        return None

    return rows[0][0]


def search_alias_user_ids(query, limit=25, db_file=None):
    query = str(query or "").strip()
    if not query:
        return []

    limit = max(1, min(int(limit), 25))
    conn = _alias_connect(db_file)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            SELECT user_id, MIN(created_at)
            FROM player_aliases
            WHERE alias LIKE ? COLLATE NOCASE
            GROUP BY user_id
            ORDER BY MIN(created_at), user_id
            LIMIT ?
            """,
            (f"%{query}%", limit),
        )
        rows = cursor.fetchall()
    except sqlite3.OperationalError as error:
        if "no such table: player_aliases" not in str(error).lower():
            raise
        rows = []
    finally:
        conn.close()

    return [row[0] for row in rows]


# ========================================================================
# PLAYER INSPECTOR QUERIES
# ========================================================================

import sqlite3
import time

from config import DB_FILE


def _inspector_connect(db_file=None):
    return sqlite3.connect(db_file or DB_FILE)


def search_registered_players(query="", limit=25, db_file=None):
    query = (query or "").strip()
    limit = max(1, min(int(limit), 25))

    conn = _inspector_connect(db_file)
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

    results = [
        {
            "user_id": user_id,
            "discord_name": discord_name,
            "ign": ign,
        }
        for user_id, discord_name, ign in rows
    ]

    if query and len(results) < limit:
        seen_ids = {entry["user_id"] for entry in results}
        alias_ids = alias_repository.search_alias_user_ids(
            query,
            limit=limit,
            db_file=db_file,
        )

        for user_id in alias_ids:
            if user_id in seen_ids:
                continue
            record = get_player_record(user_id, db_file=db_file)
            if not record:
                continue
            results.append(
                {
                    "user_id": record["user_id"],
                    "discord_name": record["discord_name"],
                    "ign": record["ign"],
                }
            )
            seen_ids.add(user_id)
            if len(results) >= limit:
                break

    return results


def get_player_record(user_id, db_file=None):
    conn = _inspector_connect(db_file)
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

    conn = _inspector_connect(db_file)
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

    if row:
        return {
            "user_id": row[0],
            "discord_name": row[1],
            "ign": row[2],
            "roles": row[3],
            "has_played_backline": bool(row[4]),
        }

    alias_user_id = alias_repository.resolve_alias_user_id(text, db_file=db_file)
    if alias_user_id is None:
        return None

    return get_player_record(alias_user_id, db_file=db_file)




def get_hidden_weight(guild_id, user_id, db_file=None):
    conn = _inspector_connect(db_file)
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

    conn = _inspector_connect(db_file)
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
    conn = _inspector_connect(db_file)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            COUNT(*),
            COALESCE(SUM(
                CASE
                    WHEN UPPER(TRIM(COALESCE(dp.team, ''))) IN ('A', 'TEAM A')
                    THEN 1 ELSE 0
                END
            ), 0),
            COALESCE(SUM(
                CASE
                    WHEN UPPER(TRIM(COALESCE(dp.team, ''))) IN ('B', 'TEAM B')
                    THEN 1 ELSE 0
                END
            ), 0),
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
        "team_a_assignments": row[1] or 0,
        "team_b_assignments": row[2] or 0,
        "times_captain": row[3] or 0,
        "primary_assignments": row[4] or 0,
        "off_role_assignments": row[5] or 0,
        "last_draft_at": row[6],
    }


def get_role_history(guild_id, user_id, db_file=None):
    conn = _inspector_connect(db_file)
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

    conn = _inspector_connect(db_file)
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
