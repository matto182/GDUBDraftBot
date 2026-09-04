import moderation_service
from player_inspector_views import _timeout_control_state


def test_timeout_control_state_without_timeout():
    state = _timeout_control_state({"timeout": None})

    assert state == {
        "label": "Timeout Player",
        "show_remove": False,
    }


def test_timeout_control_state_with_timeout():
    state = _timeout_control_state({"timeout": {"expires_at": None}})

    assert state == {
        "label": "Change Timeout",
        "show_remove": True,
    }


def test_remove_lobby_timeout_delegates_to_repository_facade(monkeypatch):
    calls = []

    def fake_remove(guild_id, user_id):
        calls.append((guild_id, user_id))
        return True

    monkeypatch.setattr(moderation_service, "remove_lobby_ban", fake_remove)

    assert moderation_service.remove_lobby_timeout(123, 456) is True
    assert calls == [(123, 456)]
