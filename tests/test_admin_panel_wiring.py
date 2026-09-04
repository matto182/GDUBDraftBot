from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_admin_panel_is_registered():
    commands = (ROOT / "commands.py").read_text(encoding="utf-8")
    assert "register_admin_panel_commands" in commands


def test_admin_panel_does_not_start_draft():
    panel = (ROOT / "admin_panel_views.py").read_text(encoding="utf-8")
    lowered = panel.casefold()

    assert "run_startdraft" not in panel
    assert 'label="start draft"' not in lowered


def test_legacy_adminboard_uses_new_panel():
    source = (ROOT / "admin_commands.py").read_text(encoding="utf-8")

    assert "AdminPanelView" in source
    assert "build_admin_panel_embed" in source


def test_player_commands_share_service():
    source = (ROOT / "player_management_commands.py").read_text(encoding="utf-8")

    assert "import player_management_service as player_management" in source
    assert "player_management.add_player" in source
    assert "player_management.move_player" in source
    assert "player_management.set_queue_position" in source
    assert "player_management.swap_players" in source
