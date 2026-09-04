import sqlite3

import player_inspector_repository as repository
import player_inspector_service as service


def create_test_db(path):
    conn = sqlite3.connect(path)
    cursor = conn.cursor()

    cursor.executescript(
        """
        CREATE TABLE players (
            discord_id INTEGER PRIMARY KEY,
            discord_name TEXT NOT NULL,
            ign TEXT NOT NULL,
            roles TEXT NOT NULL,
            has_played_backline INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE player_weights (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            weight INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        );

        CREATE TABLE lobby_bans (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            banned_by INTEGER,
            created_at REAL NOT NULL,
            expires_at REAL,
            PRIMARY KEY (guild_id, user_id)
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

    cursor.execute(
        """
        INSERT INTO players
        (discord_id, discord_name, ign, roles, has_played_backline)
        VALUES (101, 'discord-user', 'Test IGN', 'Frontline,Midline', 1)
        """
    )
    cursor.execute(
        """
        INSERT INTO players
        (discord_id, discord_name, ign, roles, has_played_backline)
        VALUES (102, 'another-user', 'Alpha Monk', 'Prot Monk', 0)
        """
    )

    cursor.execute(
        "INSERT INTO player_weights VALUES (1, 101, 250)"
    )
    cursor.execute(
        "INSERT INTO lobby_bans VALUES (1, 101, 999, 900, 2000)"
    )

    drafts = [
        ("random", 1000, 10, "A", "Frontline", 1, 0),
        ("captain", 1100, 20, "B", "Midline", 2, 1),
        ("random", 1200, 30, "A", "Heal Monk", 999, 0),
        ("random", 1300, 40, "B", "Frontline", 1, 0),
    ]

    for mode, created_at, balance_score, team, role, priority, captain in drafts:
        cursor.execute(
            """
            INSERT INTO draft_history
            (guild_id, mode, created_at, balance_score)
            VALUES (1, ?, ?, ?)
            """,
            (mode, created_at, balance_score),
        )
        draft_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO draft_players
            (draft_id, guild_id, user_id, team, assigned_role,
             role_priority_index, was_captain)
            VALUES (?, 1, 101, ?, ?, ?, ?)
            """,
            (draft_id, team, role, priority, captain),
        )

    conn.commit()
    conn.close()


def test_search_registered_players_matches_ign_and_discord_name(tmp_path):
    db = tmp_path / "players.db"
    create_test_db(db)

    by_ign = repository.search_registered_players(
        "monk",
        db_file=str(db),
    )
    by_discord = repository.search_registered_players(
        "discord",
        db_file=str(db),
    )

    assert [row["user_id"] for row in by_ign] == [102]
    assert [row["user_id"] for row in by_discord] == [101]


def test_find_player_accepts_id_and_exact_ign(tmp_path):
    db = tmp_path / "players.db"
    create_test_db(db)

    assert repository.find_player("101", db_file=str(db))["ign"] == "Test IGN"
    assert repository.find_player("test ign", db_file=str(db))["user_id"] == 101


def test_snapshot_contains_admin_and_stat_information(tmp_path):
    db = tmp_path / "players.db"
    create_test_db(db)

    snapshot = service.build_player_snapshot(
        1,
        101,
        now=1000,
        db_file=str(db),
    )

    assert snapshot["ign"] == "Test IGN"
    assert snapshot["roles"] == ["Frontline", "Midline"]
    assert snapshot["has_played_backline"] is True
    assert snapshot["hidden_weight"] == 250
    assert snapshot["timeout_summary"] == "16m"
    assert snapshot["drafts_played"] == 4
    assert snapshot["times_captain"] == 1
    assert snapshot["captain_rate"] == 25.0
    assert snapshot["primary_assignments"] == 2
    assert snapshot["primary_hit_rate"] == 50.0
    assert snapshot["off_role_assignments"] == 1
    assert snapshot["off_role_rate"] == 25.0
    assert snapshot["last_draft_at"] == 1300


def test_expired_timeout_is_not_reported_active(tmp_path):
    db = tmp_path / "players.db"
    create_test_db(db)

    snapshot = service.build_player_snapshot(
        1,
        101,
        now=3000,
        db_file=str(db),
    )

    assert snapshot["timeout"] is None
    assert snapshot["timeout_summary"] == "None"


def test_role_history_and_recent_activity_are_ordered(tmp_path):
    db = tmp_path / "players.db"
    create_test_db(db)

    snapshot = service.build_player_snapshot(
        1,
        101,
        now=1000,
        db_file=str(db),
    )

    assert snapshot["role_history"][0] == {
        "role": "Frontline",
        "count": 2,
    }
    assert [draft["created_at"] for draft in snapshot["recent_drafts"]] == [
        1300,
        1200,
        1100,
        1000,
    ]


def test_missing_weight_defaults_to_zero(tmp_path):
    db = tmp_path / "players.db"
    create_test_db(db)

    snapshot = service.build_player_snapshot(
        1,
        102,
        now=1000,
        db_file=str(db),
    )

    assert snapshot["hidden_weight"] == 0
    assert snapshot["drafts_played"] == 0
    assert snapshot["captain_rate"] == 0.0
    assert snapshot["primary_hit_rate"] == 0.0
    assert snapshot["off_role_rate"] == 0.0
