import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "players.db")

ROLES = [
    "Frontline",
    "Lyssa/Flex Derv",
    "Mesmer",
    "Elementalist",
    "Necromancer",
    "Ranger",
    "Prot Monk",
    "Heal Monk",
    "Support/Flag (8)",
]

FRONTLINE_ROLES = {"Frontline"}
MIDLINE_ROLES = {"Mesmer", "Elementalist", "Necromancer", "Ranger"}

# Auto-Draft weight defaults.
# Individual player weights are stored in players.db via /setweight.
# Higher numbers mean stronger players, sensible value are from 50-150 with 150
# being the strongest player and 50 being the weakest player.
DEFAULT_PLAYER_WEIGHT = 100
AUTO_DRAFT_WEIGHT_BALANCE_MULTIPLIER = 25
