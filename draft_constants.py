TEAM_FORMATIONS = (
    ("2 Front / 3 Mid / 3 Back", [
        "Prot Monk", "Heal Monk", "8 Support",
        "Frontline", "Frontline",
        "Midline", "Midline", "Midline",
    ]),
    ("3 Front / 2 Mid / 3 Back", [
        "Prot Monk", "Heal Monk", "8 Support",
        "Frontline", "Frontline", "Frontline",
        "Midline", "Midline",
    ]),
)
ROLE_ORDER = {
    "Captain": 0,
    "Frontline": 1,
    "Midline": 2,
    "Prot Monk": 3,
    "Heal Monk": 4,
    "8 Support": 5,
    "Unassigned": 99,
}
PREFERENCE_COST = {0: 0, 1: 20, 2: 60, 3: 120, 4: 220}
HISTORICAL_BACKLINE_COST = 700
OFF_ROLE_COST = 3000
COMPOSITION_QUALITY_WEIGHT = 0.10
EXTREME_WEIGHT_THRESHOLD = 200
