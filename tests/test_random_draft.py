from copy import deepcopy
import random

import pytest

import draft_logic
from conftest import build_all_frontline_players, build_perfect_players


def _ids(team):
    return [user_id for user_id, _role in team]


def assert_core_draft_invariants(players, lobby, team_a, team_b):
    ids_a = _ids(team_a)
    ids_b = _ids(team_b)

    assert len(team_a) == 8
    assert len(team_b) == 8
    assert len(set(ids_a)) == 8
    assert len(set(ids_b)) == 8
    assert set(ids_a).isdisjoint(ids_b)
    assert set(ids_a + ids_b) == set(lobby)
    assert set(ids_a + ids_b) == set(players)


def test_random_draft_requires_exactly_16_players():
    players = build_perfect_players()

    with pytest.raises(ValueError, match="exactly 16 players"):
        draft_logic.generate_random_teams(players, list(players)[:15])

    extra_players = deepcopy(players)
    extra_players[17] = {
        "ign": "Player 17",
        "roles": ["Midline"],
        "has_played_backline": False,
    }

    with pytest.raises(ValueError, match="exactly 16 players"):
        draft_logic.generate_random_teams(extra_players, list(extra_players))


def test_random_draft_assigns_every_player_exactly_once():
    players = build_perfect_players()
    lobby = list(players)

    random.seed(2001)
    team_a, team_b, _formation = draft_logic.generate_random_teams(
        players,
        lobby,
    )

    assert_core_draft_invariants(players, lobby, team_a, team_b)


def test_random_draft_does_not_mutate_lobby_or_player_preferences():
    players = build_perfect_players()
    lobby = list(players)
    original_lobby = list(lobby)
    original_players = deepcopy(players)

    random.seed(2002)
    draft_logic.generate_random_teams(players, lobby)

    assert lobby == original_lobby
    assert players == original_players


def test_perfect_lobby_produces_zero_composition_penalties():
    players = build_perfect_players()
    lobby = list(players)

    random.seed(2003)
    team_a, team_b, formation = draft_logic.generate_random_teams(
        players,
        lobby,
    )

    assert_core_draft_invariants(players, lobby, team_a, team_b)
    assert formation["team_a_composition_penalty"] == 0
    assert formation["team_b_composition_penalty"] == 0
    assert formation["team_a_off_role_count"] == 0
    assert formation["team_b_off_role_count"] == 0
    assert formation["team_a_historical_backline_fills"] == 0
    assert formation["team_b_historical_backline_fills"] == 0


def test_random_draft_is_reproducible_with_fixed_seed():
    players = build_perfect_players()
    lobby = list(players)

    random.seed(2004)
    first = draft_logic.generate_random_teams(players, lobby)

    random.seed(2004)
    second = draft_logic.generate_random_teams(players, lobby)

    assert first == second


def test_role_shortage_uses_off_role_assignments_instead_of_crashing():
    players = build_all_frontline_players()
    lobby = list(players)

    random.seed(2005)
    team_a, team_b, formation = draft_logic.generate_random_teams(
        players,
        lobby,
    )

    assert_core_draft_invariants(players, lobby, team_a, team_b)
    assert formation["team_a_off_role_count"] > 0
    assert formation["team_b_off_role_count"] > 0
    assert formation["team_a_composition_penalty"] > 0
    assert formation["team_b_composition_penalty"] > 0


@pytest.mark.parametrize("seed", range(10))
def test_seeded_random_draft_stress_preserves_core_invariants(seed):
    players = build_perfect_players()
    lobby = list(players)

    random.seed(seed)
    team_a, team_b, formation = draft_logic.generate_random_teams(
        players,
        lobby,
    )

    assert_core_draft_invariants(players, lobby, team_a, team_b)
    assert formation["team_a"] in {
        "2 Front / 3 Mid / 3 Back",
        "3 Front / 2 Mid / 3 Back",
    }
    assert formation["team_b"] in {
        "2 Front / 3 Mid / 3 Back",
        "3 Front / 2 Mid / 3 Back",
    }
