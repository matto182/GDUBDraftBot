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
FLEX_ROLES = {"Lyssa/Flex Derv"}
MIDLINE_ROLES = {"Mesmer", "Elementalist", "Necromancer", "Ranger"}
BACKLINE_ROLES = {"Prot Monk", "Heal Monk", "Support/Flag (8)"}