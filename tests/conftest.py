from copy import deepcopy


def player(roles, *, has_played_backline=False, ign=None):
    return {
        "ign": ign or "Test Player",
        "roles": list(roles),
        "has_played_backline": has_played_backline,
    }


def build_perfect_players():
    """
    16 players that can form two exact 2 Front / 3 Mid / 3 Back teams:
      4 Frontline
      6 Midline
      2 Prot Monk
      2 Heal Monk
      2 8 Support
    """
    specs = (
        [("Frontline",)] * 4
        + [("Midline",)] * 6
        + [("Prot Monk",)] * 2
        + [("Heal Monk",)] * 2
        + [("8 Support",)] * 2
    )

    return {
        user_id: player(roles, ign=f"Player {user_id}")
        for user_id, roles in enumerate(specs, start=1)
    }


def build_perfect_team():
    """One exact 8-player 2F / 3M / 3B team."""
    specs = [
        ("Frontline",),
        ("Frontline",),
        ("Midline",),
        ("Midline",),
        ("Midline",),
        ("Prot Monk",),
        ("Heal Monk",),
        ("8 Support",),
    ]

    return {
        user_id: player(roles, ign=f"Team Player {user_id}")
        for user_id, roles in enumerate(specs, start=1)
    }


def build_all_frontline_players(count=16):
    return {
        user_id: player(("Frontline",), ign=f"Front {user_id}")
        for user_id in range(1, count + 1)
    }


def clone_players(players):
    return deepcopy(players)
