import sqlite3

import draft_history_repository as repo


def _build_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE players (
            discord_id INTEGER PRIMARY KEY,
            discord_name TEXT NOT NULL,
            ign TEXT NOT NULL,
            roles TEXT NOT NULL,
            has_played_backline INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE draft_history (
            draft_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            mode TEXT NOT NULL,
            created_at REAL NOT NULL,
            captain_a INTEGER,
            captain_b INTEGER,
            balance_score INTEGER
        );

        CREATE TABLE draft_players (
            draft_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            team TEXT NOT NULL,
            assigned_role TEXT NOT NULL,
            role_priority_index INTEGER NOT NULL,
            was_captain INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (draft_id, user_id)
        );
        """
    )
    return conn


def _seed(conn):
    conn.executemany(
        "INSERT INTO players (discord_id, discord_name, ign, roles) VALUES (?, ?, ?, ?)",
        [
            (10, "AlphaDiscord", "Alpha", "Frontline"),
            (20, "BravoDiscord", "Bravo", "Midline"),
            (30, "CharlieDiscord", "Charlie", "Prot Monk"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO draft_history
            (draft_id, guild_id, mode, created_at, captain_a, captain_b, balance_score)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, 100, "random", 1000.0, None, None, 12),
            (2, 100, "captain", 2000.0, 10, 20, None),
            (3, 200, "random", 3000.0, None, None, 5),
        ],
    )
    conn.executemany(
        """
        INSERT INTO draft_players
            (draft_id, guild_id, user_id, team, assigned_role, role_priority_index, was_captain)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, 100, 10, "A", "Frontline", 1, 0),
            (1, 100, 20, "B", "Midline", 1, 0),
            (2, 100, 10, "A", "Frontline", 1, 1),
            (2, 100, 30, "A", "Prot Monk", 1, 0),
            (2, 100, 20, "B", "Midline", 1, 1),
            (3, 200, 30, "A", "Prot Monk", 1, 0),
        ],
    )
    conn.commit()


def test_draft_count_is_guild_scoped(tmp_path, monkeypatch):
    db_path = tmp_path / "history.db"
    conn = _build_db(db_path)
    _seed(conn)
    conn.close()
    monkeypatch.setattr(repo, "DB_FILE", str(db_path))

    assert repo.get_draft_count(100) == 2
    assert repo.get_draft_count(200) == 1
    assert repo.get_draft_count(999) == 0


def test_history_page_is_newest_first(tmp_path, monkeypatch):
    db_path = tmp_path / "history.db"
    conn = _build_db(db_path)
    _seed(conn)
    conn.close()
    monkeypatch.setattr(repo, "DB_FILE", str(db_path))

    drafts = repo.get_draft_history_page(100, limit=10, offset=0)

    assert [draft["draft_id"] for draft in drafts] == [2, 1]
    assert drafts[0]["player_count"] == 3
    assert drafts[0]["captain_a_ign"] == "Alpha"
    assert drafts[0]["captain_b_ign"] == "Bravo"


def test_history_page_supports_pagination(tmp_path, monkeypatch):
    db_path = tmp_path / "history.db"
    conn = _build_db(db_path)
    _seed(conn)
    conn.close()
    monkeypatch.setattr(repo, "DB_FILE", str(db_path))

    first = repo.get_draft_history_page(100, limit=1, offset=0)
    second = repo.get_draft_history_page(100, limit=1, offset=1)

    assert [draft["draft_id"] for draft in first] == [2]
    assert [draft["draft_id"] for draft in second] == [1]


def test_draft_details_include_teams_roles_and_names(tmp_path, monkeypatch):
    db_path = tmp_path / "history.db"
    conn = _build_db(db_path)
    _seed(conn)
    conn.close()
    monkeypatch.setattr(repo, "DB_FILE", str(db_path))

    details = repo.get_draft_details(100, 2)

    assert details["draft"]["mode"] == "captain"
    assert [(p["team"], p["ign"], p["assigned_role"], p["was_captain"]) for p in details["players"]] == [
        ("A", "Alpha", "Frontline", 1),
        ("A", "Charlie", "Prot Monk", 0),
        ("B", "Bravo", "Midline", 1),
    ]


def test_draft_details_reject_cross_guild_lookup(tmp_path, monkeypatch):
    db_path = tmp_path / "history.db"
    conn = _build_db(db_path)
    _seed(conn)
    conn.close()
    monkeypatch.setattr(repo, "DB_FILE", str(db_path))

    assert repo.get_draft_details(200, 2) is None
