import draft_logic
from conftest import build_perfect_players, player


def test_role_needs_counts_current_role_preferences():
    players = build_perfect_players()
    result = draft_logic.analyze_role_needs(players, list(players))

    assert result["counts"] == {
        "Frontline": 4,
        "Midline": 6,
        "Prot Monk": 2,
        "Heal Monk": 2,
        "8 Support": 2,
    }


def test_exact_minimum_frontline_is_medium_not_high_priority():
    players = build_perfect_players()
    result = draft_logic.analyze_role_needs(players, list(players))

    assert not any("Frontline" in item for item in result["high"])
    assert "Frontline (4/6 ideal flexibility)" in result["medium"]


def test_missing_backline_roles_are_high_priority():
    players = {
        user_id: player(["Frontline"])
        for user_id in range(1, 5)
    }
    players.update({
        user_id: player(["Midline"])
        for user_id in range(5, 11)
    })

    result = draft_logic.analyze_role_needs(players, list(players))

    assert "Prot Monk (0/2 preferred)" in result["high"]
    assert "Heal Monk (0/2 preferred)" in result["high"]
    assert "8 Support (0/2 preferred)" in result["high"]


def test_legacy_roles_count_under_their_normalized_current_roles():
    players = {
        1: player(["Lyssa/Flex Derv"]),
        2: player(["Mesmer"]),
        3: player(["Support/Flag (8)"]),
    }

    result = draft_logic.analyze_role_needs(players, list(players))

    assert result["counts"]["Frontline"] == 1
    assert result["counts"]["Midline"] == 1
    assert result["counts"]["8 Support"] == 1
