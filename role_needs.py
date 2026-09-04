from config import normalize_roles

def analyze_role_needs(players, lobby):
    counts = {role: 0 for role in [
        "Frontline", "Midline", "Prot Monk", "Heal Monk", "8 Support"
    ]}

    for user_id in lobby:
        for role in set(normalize_roles(players[user_id].get("roles", []))):
            if role in counts:
                counts[role] += 1

    high = []
    medium = []
    low = []

    for role in ["Prot Monk", "Heal Monk", "8 Support"]:
        if counts[role] < 2:
            high.append(f"{role} ({counts[role]}/2 preferred)")

    if counts["Frontline"] < 4:
        high.append(f"Frontline ({counts['Frontline']}/4 preferred)")
    elif counts["Frontline"] < 6:
        medium.append(f"Frontline ({counts['Frontline']}/6 ideal flexibility)")

    if counts["Midline"] < 4:
        high.append(f"Midline ({counts['Midline']}/4 preferred)")
    elif counts["Midline"] < 6:
        medium.append(f"Midline ({counts['Midline']}/6 ideal flexibility)")

    combined_front_mid = counts["Frontline"] + counts["Midline"]
    if combined_front_mid < 10:
        medium.append(f"Front/Mid coverage ({combined_front_mid}/10 preferred)")

    return {"high": high, "medium": medium, "low": low, "counts": counts}
