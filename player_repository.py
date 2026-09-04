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
