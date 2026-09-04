import player_management_service as service


class FakeState:
    def __init__(self):
        self.lobby = []
        self.waiting_room = []
        self.votes = {}
        self.captain_volunteers = []
        self.captain_draft = None
        self.last_signup_time = None


def setup_service(monkeypatch):
    state = FakeState()
    saved = []

    monkeypatch.setattr(service, "get_state", lambda guild_id: state)
    monkeypatch.setattr(service, "save_lobby_state", lambda guild_id: saved.append(guild_id))

    service.players.clear()
    service.players.update({
        1: {"ign": "One"},
        2: {"ign": "Two"},
        3: {"ign": "Three"},
    })

    return state, saved


def test_add_player_to_lobby(monkeypatch):
    state, saved = setup_service(monkeypatch)

    success, message = service.add_player(10, 1, "lobby")

    assert success is True
    assert state.lobby == [1]
    assert saved == [10]
    assert "One" in message


def test_add_player_rejects_duplicate(monkeypatch):
    state, saved = setup_service(monkeypatch)
    state.lobby = [1]

    success, message = service.add_player(10, 1, "waiting")

    assert success is False
    assert state.waiting_room == []
    assert saved == []
    assert "already signed up" in message


def test_move_lobby_player_to_waiting_clears_vote_and_captain(monkeypatch):
    state, saved = setup_service(monkeypatch)
    state.lobby = [1]
    state.votes = {1: "captain"}
    state.captain_volunteers = [1]

    success, _message = service.move_player(10, 1, "waiting")

    assert success is True
    assert state.lobby == []
    assert state.waiting_room == [1]
    assert 1 not in state.votes
    assert 1 not in state.captain_volunteers
    assert saved == [10]


def test_move_waiting_player_rejects_full_lobby(monkeypatch):
    state, saved = setup_service(monkeypatch)
    state.lobby = list(range(100, 116))
    state.waiting_room = [1]

    success, message = service.move_player(10, 1, "lobby")

    assert success is False
    assert state.waiting_room == [1]
    assert saved == []
    assert "full" in message.lower()


def test_queue_position_reorders_waiting_room(monkeypatch):
    state, saved = setup_service(monkeypatch)
    state.waiting_room = [1, 2, 3]

    success, _message = service.set_queue_position(10, 3, 1)

    assert success is True
    assert state.waiting_room == [3, 1, 2]
    assert saved == [10]


def test_queue_position_rejects_out_of_range(monkeypatch):
    state, saved = setup_service(monkeypatch)
    state.waiting_room = [1, 2]

    success, message = service.set_queue_position(10, 1, 3)

    assert success is False
    assert state.waiting_room == [1, 2]
    assert saved == []
    assert "between" in message


def test_swap_players_preserves_waiting_position(monkeypatch):
    state, saved = setup_service(monkeypatch)
    state.lobby = [1]
    state.waiting_room = [3, 2]
    state.votes = {1: "random"}
    state.captain_volunteers = [1]

    success, _message = service.swap_players(10, 1, 2)

    assert success is True
    assert state.lobby == [2]
    assert state.waiting_room == [3, 1]
    assert 1 not in state.votes
    assert 1 not in state.captain_volunteers
    assert saved == [10]


def test_swap_rejected_during_captain_draft(monkeypatch):
    state, saved = setup_service(monkeypatch)
    state.lobby = [1]
    state.waiting_room = [2]
    state.captain_draft = object()

    success, message = service.swap_players(10, 1, 2)

    assert success is False
    assert state.lobby == [1]
    assert state.waiting_room == [2]
    assert saved == []
    assert "Captain Draft" in message
