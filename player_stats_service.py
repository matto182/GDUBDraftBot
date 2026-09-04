from collections import defaultdict

from config import ROLES, normalize_roles


PRIORITY_LABELS = {
    1: "Primary",
    2: "Secondary",
    3: "Tertiary",
    4: "Fourth",
    5: "Fifth",
    999: "Fill/Off-role",
}


def _rate(count, total):
    if not total:
        return 0.0
    return (count / total) * 100.0


def _normalize_role_name(role):
    normalized = normalize_roles([role])
    if normalized:
        return normalized[0]
    return str(role)


def summarize_player_stats(stats_data):
    """Convert raw repository stats into display-ready counts and rates."""
    drafts_played = int(stats_data.get("drafts_played", 0) or 0)
    times_captain = int(stats_data.get("times_captain", 0) or 0)

    role_counts = defaultdict(int)
    for role, count in stats_data.get("roles", []) or []:
        role_counts[_normalize_role_name(role)] += int(count or 0)

    role_order = {role: index for index, role in enumerate(ROLES)}
    role_frequency = [
        {
            "role": role,
            "count": count,
            "rate": _rate(count, drafts_played),
        }
        for role, count in sorted(
            role_counts.items(),
            key=lambda item: (
                -item[1],
                role_order.get(item[0], len(role_order)),
                item[0].casefold(),
            ),
        )
    ]

    priority_counts = {
        int(priority): int(count or 0)
        for priority, count in stats_data.get("priority_stats", []) or []
    }

    preferred_assignments = sum(
        count
        for priority, count in priority_counts.items()
        if 1 <= priority <= 5
    )
    off_role_assignments = priority_counts.get(999, 0)

    priority_usage = [
        {
            "priority": priority,
            "label": PRIORITY_LABELS.get(priority, f"Priority {priority}"),
            "count": count,
            "rate": _rate(count, drafts_played),
        }
        for priority, count in sorted(
            priority_counts.items(),
            key=lambda item: (item[0] == 999, item[0]),
        )
    ]

    return {
        "drafts_played": drafts_played,
        "times_captain": times_captain,
        "captain_rate": _rate(times_captain, drafts_played),
        "preferred_assignments": preferred_assignments,
        "preferred_role_hit_rate": _rate(preferred_assignments, drafts_played),
        "off_role_assignments": off_role_assignments,
        "off_role_rate": _rate(off_role_assignments, drafts_played),
        "role_frequency": role_frequency,
        "priority_usage": priority_usage,
    }


def format_role_frequency(summary):
    rows = summary.get("role_frequency", [])
    if not rows:
        return "No role data."

    return "\n".join(
        f"{row['role']}: {row['count']} ({row['rate']:.1f}%)"
        for row in rows
    )


def format_priority_usage(summary):
    rows = summary.get("priority_usage", [])
    if not rows:
        return "No assignment data."

    return "\n".join(
        f"{row['label']}: {row['count']} ({row['rate']:.1f}%)"
        for row in rows
    )
