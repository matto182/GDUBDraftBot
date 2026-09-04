import pytest

import draft_logic
from conftest import build_perfect_team, player


def test_role_sort_key_keeps_current_display_order():
    ordered = [
        "Captain",
        "Frontline",
        "Midline",
        "Prot Monk",
        "Heal Monk",
        "8 Support",
        "Unassigned",
    ]
    assert sorted(ordered, key=draft_logic.role_sort_key) == ordered


def test_role_priority_index_reports_registered_priority():
    players = {
        1: player(["Midline", "Frontline", "Heal Monk"]),
    }

    assert draft_logic.role_priority_index(players, 1, "Midline") == 0
    assert draft_logic.role_priority_index(players, 1, "Frontline") == 1
    assert draft_logic.role_priority_index(players, 1, "Heal Monk") == 2
    assert draft_logic.role_priority_index(players, 1, "Prot Monk") == 999


def test_assignment_cost_matches_current_preference_costs():
    players = {
        1: player([
            "Frontline",
            "Midline",
            "Prot Monk",
            "Heal Monk",
            "8 Support",
        ]),
    }

    assert draft_logic.assignment_cost(players, 1, "Frontline") == 0
    assert draft_logic.assignment_cost(players, 1, "Midline") == 20
    assert draft_logic.assignment_cost(players, 1, "Prot Monk") == 60
    assert draft_logic.assignment_cost(players, 1, "Heal Monk") == 120
    assert draft_logic.assignment_cost(players, 1, "8 Support") == 220


def test_generic_off_role_cost_is_3000():
    players = {1: player(["Frontline"])}
    assert draft_logic.assignment_cost(players, 1, "Heal Monk") == 3000


def test_historical_backline_autofill_cost_is_700():
    players = {
        1: player(["Midline"], has_played_backline=True),
    }
    assert draft_logic.assignment_cost(players, 1, "8 Support") == 700


def test_historical_backline_flag_does_not_discount_frontline_or_midline():
    players = {
        1: player(["Frontline"], has_played_backline=True),
    }
    assert draft_logic.assignment_cost(players, 1, "Midline") == 3000


def test_perfect_team_has_zero_assignment_penalty():
    players = build_perfect_team()

    result = draft_logic.assign_best_team_roles(players, list(players))

    assert result["formation"] == "2 Front / 3 Mid / 3 Back"
    assert result["score"] == 0
    assert result["off_role_count"] == 0
    assert result["historical_backline_fills"] == 0
    assert {user_id for user_id, _role in result["team"]} == set(players)


def test_historical_backline_player_is_used_before_generic_off_role():
    players = {
        1: player(["Frontline"]),
        2: player(["Frontline"]),
        3: player(["Midline"]),
        4: player(["Midline"]),
        5: player(["Midline"]),
        6: player(["Prot Monk"]),
        7: player(["Heal Monk"]),
        8: player(["Midline"], has_played_backline=True),
    }

    result = draft_logic.assign_best_team_roles(players, list(players))

    assert result["score"] == draft_logic.HISTORICAL_BACKLINE_COST
    assert result["historical_backline_fills"] == 1
    assert (8, "8 Support") in result["team"]


def test_missing_backline_without_history_uses_generic_off_role():
    players = {
        1: player(["Frontline"]),
        2: player(["Frontline"]),
        3: player(["Midline"]),
        4: player(["Midline"]),
        5: player(["Midline"]),
        6: player(["Prot Monk"]),
        7: player(["Heal Monk"]),
        8: player(["Midline"]),
    }

    result = draft_logic.assign_best_team_roles(players, list(players))

    assert result["score"] == draft_logic.OFF_ROLE_COST
    assert result["historical_backline_fills"] == 0
    assert result["off_role_count"] == 1


def test_assign_best_team_roles_requires_exactly_eight_players():
    players = {
        user_id: player(["Frontline"])
        for user_id in range(1, 8)
    }

    with pytest.raises(ValueError, match="exactly 8 players"):
        draft_logic.assign_best_team_roles(players, list(players))


def test_optimize_team_roles_preserves_team_members():
    players = build_perfect_team()
    original_team = [(user_id, "Unassigned") for user_id in players]

    optimized = draft_logic.optimize_team_roles(players, original_team)

    assert {user_id for user_id, _role in optimized} == set(players)
    assert len(optimized) == 8


def test_optimize_team_roles_leaves_non_eight_player_team_unchanged():
    players = {
        user_id: player(["Frontline"])
        for user_id in range(1, 8)
    }
    team = [(user_id, "Frontline") for user_id in players]

    assert draft_logic.optimize_team_roles(players, team) is team
