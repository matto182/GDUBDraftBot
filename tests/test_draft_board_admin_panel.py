from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_draft_board_admin_button_uses_unified_panel():
    source = (ROOT / "draft_board_views.py").read_text(encoding="utf-8")

    assert "from admin_panel_views import AdminPanelView, build_admin_panel_embed" in source
    assert "view=AdminPanelView(interaction.guild.id)" in source
    assert "embed=build_admin_panel_embed(interaction.guild.id)" in source


def test_draft_board_no_longer_opens_legacy_admin_view():
    source = (ROOT / "draft_board_views.py").read_text(encoding="utf-8")

    assert "AdminDraftView" not in source


def test_start_draft_button_still_exists():
    source = (ROOT / "draft_board_views.py").read_text(encoding="utf-8")

    assert 'label="Start Draft"' in source
    assert "await ctx.run_startdraft(interaction)" in source
