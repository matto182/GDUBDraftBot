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
