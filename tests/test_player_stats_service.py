from player_stats_service import (
    format_priority_usage,
    format_role_frequency,
    summarize_player_stats,
)


def test_zero_drafts_produce_zero_rates():
    summary = summarize_player_stats(
        {
            "drafts_played": 0,
            "times_captain": 0,
            "roles": [],
            "priority_stats": [],
        }
    )

    assert summary["captain_rate"] == 0.0
    assert summary["preferred_role_hit_rate"] == 0.0
    assert summary["off_role_rate"] == 0.0
    assert format_role_frequency(summary) == "No role data."
    assert format_priority_usage(summary) == "No assignment data."


def test_requested_rates_are_calculated_from_drafts_played():
    summary = summarize_player_stats(
        {
            "drafts_played": 10,
            "times_captain": 2,
            "roles": [("Frontline", 4), ("Midline", 6)],
            "priority_stats": [(1, 4), (2, 3), (999, 3)],
        }
    )

    assert summary["captain_rate"] == 20.0
    assert summary["preferred_assignments"] == 7
    assert summary["preferred_role_hit_rate"] == 70.0
    assert summary["off_role_assignments"] == 3
    assert summary["off_role_rate"] == 30.0


def test_role_frequency_includes_counts_and_percentages():
    summary = summarize_player_stats(
        {
            "drafts_played": 8,
            "times_captain": 0,
            "roles": [("Frontline", 5), ("Midline", 3)],
            "priority_stats": [(1, 8)],
        }
    )

    assert summary["role_frequency"] == [
        {"role": "Frontline", "count": 5, "rate": 62.5},
        {"role": "Midline", "count": 3, "rate": 37.5},
    ]
    assert format_role_frequency(summary) == "Frontline: 5 (62.5%)\nMidline: 3 (37.5%)"


def test_legacy_role_names_are_merged_into_current_role_categories():
    summary = summarize_player_stats(
        {
            "drafts_played": 8,
            "times_captain": 0,
            "roles": [
                ("Mesmer", 2),
                ("Midline", 3),
                ("Support/Flag (8)", 1),
                ("8 Support", 2),
            ],
            "priority_stats": [(1, 8)],
        }
    )

    assert summary["role_frequency"] == [
        {"role": "Midline", "count": 5, "rate": 62.5},
        {"role": "8 Support", "count": 3, "rate": 37.5},
    ]


def test_all_five_preferences_count_as_preferred_assignments():
    summary = summarize_player_stats(
        {
            "drafts_played": 6,
            "times_captain": 0,
            "roles": [("Midline", 6)],
            "priority_stats": [(1, 1), (2, 1), (3, 1), (4, 1), (5, 1), (999, 1)],
        }
    )

    assert summary["preferred_assignments"] == 5
    assert round(summary["preferred_role_hit_rate"], 1) == 83.3
    assert round(summary["off_role_rate"], 1) == 16.7


def test_priority_usage_includes_fifth_preference_label():
    summary = summarize_player_stats(
        {
            "drafts_played": 2,
            "times_captain": 0,
            "roles": [("Midline", 2)],
            "priority_stats": [(5, 1), (999, 1)],
        }
    )

    assert format_priority_usage(summary) == "Fifth: 1 (50.0%)\nFill/Off-role: 1 (50.0%)"


def test_role_frequency_ties_follow_current_role_order():
    summary = summarize_player_stats(
        {
            "drafts_played": 4,
            "times_captain": 0,
            "roles": [("Heal Monk", 2), ("Frontline", 2)],
            "priority_stats": [(1, 4)],
        }
    )

    assert [row["role"] for row in summary["role_frequency"]] == ["Frontline", "Heal Monk"]
