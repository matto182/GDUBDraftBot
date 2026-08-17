import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "players.db")

ROLES = [
    "Frontline",
    "Midline",
    "Prot Monk",
    "Heal Monk",
    "8 Support",
]

FRONTLINE_ROLES = {"Frontline"}
MIDLINE_ROLES = {"Midline"}
BACKLINE_ROLES = {"Prot Monk", "Heal Monk", "8 Support"}

# Converts player records created under the old role system.
ROLE_ALIASES = {
    "Frontline": "Frontline",
    "Lyssa/Flex Derv": "Frontline",
    "Mesmer": "Midline",
    "Elementalist": "Midline",
    "Necromancer": "Midline",
    "Ranger": "Midline",
    "Midline": "Midline",
    "Prot Monk": "Prot Monk",
    "Heal Monk": "Heal Monk",
    "Support/Flag (8)": "8 Support",
    "8 Support": "8 Support",
}


def normalize_roles(roles):
    """Map legacy roles to the current role list while preserving priority."""
    normalized = []

    for role in roles or []:
        mapped = ROLE_ALIASES.get(role)
        if mapped and mapped not in normalized:
            normalized.append(mapped)

    return normalized
