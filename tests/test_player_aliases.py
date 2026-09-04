import sqlite3

import player_alias_repository as alias_repository
import player_alias_service as alias_service
import player_inspector_repository as inspector_repository


def _make_db(tmp_path):
    db_file = tmp_path / "players.db"
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE players (
            discord_id INTEGER PRIMARY KEY,
            discord_name TEXT NOT NULL,
            ign TEXT NOT NULL,
            roles TEXT NOT NULL,
            has_played_backline INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE player_aliases (
            user_id INTEGER NOT NULL,
            alias TEXT NOT NULL COLLATE NOCASE,
            created_at REAL NOT NULL,
            PRIMARY KEY (user_id, alias)
        )
        """
    )
    cursor.execute(
        "INSERT INTO players VALUES (?, ?, ?, ?, ?)",
        (1001, "RelicDiscord", "Relic", "Midline", 0),
    )
    cursor.execute(
        "INSERT INTO players VALUES (?, ?, ?, ?, ?)",
        (1002, "CanaryDiscord", "Canary", "Frontline", 0),
    )
    conn.commit()
    conn.close()
    return str(db_file)


def test_name_change_saves_previous_ign(tmp_path):
    db_file = _make_db(tmp_path)

    saved = alias_service.record_name_change(1001, "Relic", "New Relic", db_file=db_file)

    assert saved is True
    assert alias_repository.get_player_aliases(1001, db_file=db_file) == ["Relic"]


def test_same_name_does_not_create_alias(tmp_path):
    db_file = _make_db(tmp_path)

    saved = alias_service.record_name_change(1001, "Relic", "RELIC", db_file=db_file)

    assert saved is False
    assert alias_repository.get_player_aliases(1001, db_file=db_file) == []


def test_returning_to_old_ign_removes_it_from_previous_names(tmp_path):
    db_file = _make_db(tmp_path)
    alias_service.record_name_change(1001, "Relic", "New Relic", db_file=db_file)
    alias_service.record_name_change(1001, "New Relic", "Relic", db_file=db_file)

    assert alias_repository.get_player_aliases(1001, db_file=db_file) == ["New Relic"]


def test_inspector_resolves_previous_ign(tmp_path):
    db_file = _make_db(tmp_path)
    alias_service.record_name_change(1001, "Relic", "New Relic", db_file=db_file)

    conn = sqlite3.connect(db_file)
    conn.execute("UPDATE players SET ign = ? WHERE discord_id = ?", ("New Relic", 1001))
    conn.commit()
    conn.close()

    record = inspector_repository.find_player("Relic", db_file=db_file)

    assert record["user_id"] == 1001
    assert record["ign"] == "New Relic"


def test_inspector_autocomplete_searches_previous_ign(tmp_path):
    db_file = _make_db(tmp_path)
    alias_service.record_name_change(1001, "Relic", "New Relic", db_file=db_file)

    conn = sqlite3.connect(db_file)
    conn.execute("UPDATE players SET ign = ? WHERE discord_id = ?", ("New Relic", 1001))
    conn.commit()
    conn.close()

    results = inspector_repository.search_registered_players("Relic", db_file=db_file)

    assert [row["user_id"] for row in results] == [1001]
    assert results[0]["ign"] == "New Relic"


def test_duplicate_alias_is_ambiguous_in_alias_only_resolution(tmp_path):
    db_file = _make_db(tmp_path)
    alias_repository.save_player_alias(1001, "OldName", created_at=1, db_file=db_file)
    alias_repository.save_player_alias(1002, "OldName", created_at=2, db_file=db_file)

    assert alias_repository.resolve_alias_user_id("OldName", db_file=db_file) is None
