import sqlite3
import time

from config import DB_FILE


def _connect(db_file=None):
    return sqlite3.connect(db_file or DB_FILE)


def save_player_alias(user_id, alias, created_at=None, db_file=None):
    alias = str(alias or "").strip()
    if not alias:
        return False

    created_at = time.time() if created_at is None else created_at
    conn = _connect(db_file)
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

    conn = _connect(db_file)
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
    conn = _connect(db_file)
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

    conn = _connect(db_file)
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
    conn = _connect(db_file)
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
