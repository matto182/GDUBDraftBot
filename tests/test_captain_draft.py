import draft_logic
from conftest import build_perfect_players, player


def test_captain_draft_initializes_opposite_captains_and_available_pool():
    lobby = list(range(1, 17))
    draft = draft_logic.CaptainDraft(lobby, 1, 2)

    assert draft.team_a == [(1, "Captain")]
    assert draft.team_b == [(2, "Captain")]
    assert 1 not in draft.available
    assert 2 not in draft.available
    assert set(draft.available) == set(range(3, 17))
    assert len(draft.available) == 14


def test_captain_pick_order_is_current_snake_pattern():
    draft = draft_logic.CaptainDraft(list(range(1, 17)), 1, 2)

    assert draft.pick_order == [
        1, 2, 2, 1,
        1, 2, 2, 1,
        1, 2, 2, 1,
        1, 2,
    ]


def test_wrong_captain_cannot_pick_and_state_does_not_change():
    players = build_perfect_players()
    draft = draft_logic.CaptainDraft(list(players), 1, 2)

    before_available = list(draft.available)
    before_a = list(draft.team_a)
    before_b = list(draft.team_b)

    ok, message = draft.pick_player(players, 2, 3)

    assert not ok
    assert message == "It is not your pick."
    assert draft.available == before_available
    assert draft.team_a == before_a
    assert draft.team_b == before_b
    assert draft.pick_index == 0


def test_unavailable_player_cannot_be_picked():
    players = build_perfect_players()
    draft = draft_logic.CaptainDraft(list(players), 1, 2)

    ok, message = draft.pick_player(players, 1, 1)

    assert not ok
    assert message == "That player is not available."
    assert draft.pick_index == 0


def test_successful_pick_uses_players_primary_normalized_role():
    players = build_perfect_players()
    players[3] = player(["Mesmer", "Frontline"], ign="Legacy Mesmer")
    draft = draft_logic.CaptainDraft(list(players), 1, 2)

    ok, message = draft.pick_player(players, 1, 3)

    assert ok
    assert message == "Pick accepted."
    assert (3, "Midline") in draft.team_a
    assert 3 not in draft.available
    assert draft.pick_index == 1


def test_full_captain_draft_finishes_eight_vs_eight_with_all_players_once():
    players = build_perfect_players()
    lobby = list(players)
    draft = draft_logic.CaptainDraft(lobby, 1, 2)

    for picked_id in list(draft.available):
        picker = draft.current_picker()
        ok, message = draft.pick_player(players, picker, picked_id)
        assert ok, message

    ids_a = [user_id for user_id, _role in draft.team_a]
    ids_b = [user_id for user_id, _role in draft.team_b]

    assert draft.is_complete()
    assert draft.current_picker() is None
    assert len(ids_a) == 8
    assert len(ids_b) == 8
    assert set(ids_a).isdisjoint(ids_b)
    assert set(ids_a + ids_b) == set(lobby)
    assert draft.available == []


def test_role_optimization_after_captain_draft_cannot_change_membership():
    players = build_perfect_players()
    lobby = list(players)
    draft = draft_logic.CaptainDraft(lobby, 1, 2)

    for picked_id in list(draft.available):
        ok, message = draft.pick_player(
            players,
            draft.current_picker(),
            picked_id,
        )
        assert ok, message

    original_a = {user_id for user_id, _role in draft.team_a}
    original_b = {user_id for user_id, _role in draft.team_b}

    optimized_a = draft_logic.optimize_team_roles(players, draft.team_a)
    optimized_b = draft_logic.optimize_team_roles(players, draft.team_b)

    assert {user_id for user_id, _role in optimized_a} == original_a
    assert {user_id for user_id, _role in optimized_b} == original_b
