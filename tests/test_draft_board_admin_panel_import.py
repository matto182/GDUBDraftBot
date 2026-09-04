from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_admin_panel_import_is_lazy():
    source = (ROOT / "draft_board_views.py").read_text(encoding="utf-8")

    lines = source.splitlines()
    top_level_imports = [
        line for line in lines[:10]
        if "admin_panel_views" in line
    ]

    assert top_level_imports == []
    assert "from admin_panel_views import AdminPanelView, build_admin_panel_embed" in source


def test_draft_board_admin_button_still_uses_unified_panel():
    source = (ROOT / "draft_board_views.py").read_text(encoding="utf-8")

    assert "embed=build_admin_panel_embed(interaction.guild.id)" in source
    assert "view=AdminPanelView(interaction.guild.id)" in source


def test_start_draft_button_is_untouched():
    source = (ROOT / "draft_board_views.py").read_text(encoding="utf-8")

    assert 'label="Start Draft"' in source
    assert "await ctx.run_startdraft(interaction)" in source
