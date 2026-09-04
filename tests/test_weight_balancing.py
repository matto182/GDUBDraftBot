import random

import draft_logic
from conftest import build_perfect_players


def _team_ids(team):
    return {user_id for user_id, _role in team}


def test_team_weight_sums_hidden_weights_and_defaults_missing_to_zero():
    team_result = {
        "team": [(1, "Frontline"), (2, "Midline"), (3, "Heal Monk")],
        "score": 0,
    }
    weights = {1: 200, 2: -50}

    assert draft_logic.team_weight(team_result, weights) == 150


def test_effective_team_strength_is_weight_minus_composition_penalty():
    team_result = {
        "team": [(1, "Frontline"), (2, "Midline")],
        "score": 60,
    }
    weights = {1: 200, 2: -20}

    assert draft_logic.effective_team_strength(team_result, weights) == 120


def test_score_match_uses_current_weight_and_composition_formula():
    team_a = {
        "team": [(1, "Frontline")],
        "score": 100,
    }
    team_b = {
        "team": [(2, "Frontline")],
        "score": 300,
    }
    weights = {1: 250, 2: 100}

    # weight diff 150
    # composition total 400 * .10 = 40
    # composition difference 200 * .05 = 10
    assert draft_logic.score_match(team_a, team_b, weights) == 200


def test_extreme_threshold_is_inclusive_at_positive_200():
    weights = {1: 200, 2: 200}
    lobby = list(range(1, 17))

    assert draft_logic._extreme_rule_is_feasible(lobby, weights)
    assert draft_logic._violates_extreme_stack([1, 2], weights)


def test_extreme_threshold_is_inclusive_at_negative_200():
    weights = {1: -200, 2: -200}
    lobby = list(range(1, 17))

    assert draft_logic._extreme_rule_is_feasible(lobby, weights)
    assert draft_logic._violates_extreme_stack([1, 2], weights)


def test_199_is_not_an_extreme_weight():
    weights = {1: 199, 2: 199, 3: -199, 4: -199}

    assert not draft_logic._violates_extreme_stack([1, 2, 3, 4], weights)


def test_more_than_two_positive_extremes_disables_extreme_rule():
    lobby = list(range(1, 17))
    weights = {1: 300, 2: 300, 3: 300}

    assert not draft_logic._extreme_rule_is_feasible(lobby, weights)


def test_more_than_two_negative_extremes_disables_extreme_rule():
    lobby = list(range(1, 17))
    weights = {1: -300, 2: -300, 3: -300}

    assert not draft_logic._extreme_rule_is_feasible(lobby, weights)


def test_two_strong_and_two_weak_players_are_split_across_teams():
    players = build_perfect_players()
    lobby = list(players)
    weights = {
        1: 500,
        2: 500,
        3: -500,
        4: -500,
    }

    random.seed(1001)
    team_a, team_b, formation = draft_logic.generate_random_teams(
        players,
        lobby,
        weights,
    )

    ids_a = _team_ids(team_a)
    ids_b = _team_ids(team_b)

    assert len(ids_a & {1, 2}) == 1
    assert len(ids_b & {1, 2}) == 1
    assert len(ids_a & {3, 4}) == 1
    assert len(ids_b & {3, 4}) == 1
    assert formation["extreme_stack_rule_enforced"] is True
    assert formation["team_a_weight"] == formation["team_b_weight"] == 0


def test_three_positive_extremes_are_allowed_without_enforcement():
    players = build_perfect_players()
    lobby = list(players)
    weights = {1: 500, 2: 500, 3: 500}

    random.seed(1002)
    _team_a, _team_b, formation = draft_logic.generate_random_teams(
        players,
        lobby,
        weights,
    )

    assert formation["extreme_stack_rule_enforced"] is False
