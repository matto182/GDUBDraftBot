import sqlite3

from config import DB_FILE


def _connect():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def get_draft_count(guild_id):
    conn = _connect()
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

    conn = _connect()
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
    conn = _connect()
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
