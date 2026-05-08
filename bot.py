import discord
import sqlite3
import random
import itertools
from discord import app_commands
import asyncio
import time

from config import (
    TOKEN,
    DB_FILE,
    ROLES,
    FRONTLINE_ROLES,
    MIDLINE_ROLES,
    DEFAULT_PLAYER_WEIGHT,
    AUTO_DRAFT_WEIGHT_BALANCE_MULTIPLIER,
)
last_signup_time = None

players = {}
lobby = []
waiting_room = []
votes = {}
captain_volunteers = []
last_board_message_id = None
draft_result = None
captain_draft = None
final_team_a = []
final_team_b = []


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            discord_id INTEGER PRIMARY KEY,
            discord_name TEXT NOT NULL,
            ign TEXT NOT NULL,
            roles TEXT NOT NULL,
            weight INTEGER NOT NULL DEFAULT 100
        )
    """)

    try:
        cursor.execute(
            "ALTER TABLE players ADD COLUMN weight INTEGER NOT NULL DEFAULT 100"
        )
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guild_config (
            guild_id INTEGER PRIMARY KEY,
            draft_channel_id INTEGER,
            team_a_voice_channel_id INTEGER,
            team_b_voice_channel_id INTEGER,
            admin_role_id INTEGER,
            board_message_id INTEGER
        )
    """)

    try:
        cursor.execute(
            "ALTER TABLE guild_config ADD COLUMN board_message_id INTEGER"
        )
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lobby_state (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            area TEXT NOT NULL,
            position INTEGER NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guild_runtime_state (
            guild_id INTEGER PRIMARY KEY,
            last_signup_time REAL
        )
    """)

    conn.commit()
    conn.close()
def save_guild_config(
    guild_id,
    draft_channel_id=None,
    team_a_voice_channel_id=None,
    team_b_voice_channel_id=None,
    admin_role_id=None
):
    current = get_guild_config(guild_id) or {}

    draft_channel_id = draft_channel_id or current.get("draft_channel_id")
    team_a_voice_channel_id = team_a_voice_channel_id or current.get("team_a_voice_channel_id")
    team_b_voice_channel_id = team_b_voice_channel_id or current.get("team_b_voice_channel_id")
    admin_role_id = admin_role_id or current.get("admin_role_id")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO guild_config (
            guild_id,
            draft_channel_id,
            team_a_voice_channel_id,
            team_b_voice_channel_id,
            admin_role_id
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            draft_channel_id = excluded.draft_channel_id,
            team_a_voice_channel_id = excluded.team_a_voice_channel_id,
            team_b_voice_channel_id = excluded.team_b_voice_channel_id,
            admin_role_id = excluded.admin_role_id
    """, (
        guild_id,
        draft_channel_id,
        team_a_voice_channel_id,
        team_b_voice_channel_id,
        admin_role_id
    ))

    conn.commit()
    conn.close()


def get_guild_config(guild_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            draft_channel_id,
            team_a_voice_channel_id,
            team_b_voice_channel_id,
            admin_role_id,
            board_message_id
        FROM guild_config
        WHERE guild_id = ?
    """, (guild_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "draft_channel_id": row[0],
        "team_a_voice_channel_id": row[1],
        "team_b_voice_channel_id": row[2],
        "admin_role_id": row[3],
        "board_message_id": row[4],
    }
def save_board_message_id(guild_id, board_message_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE guild_config
        SET board_message_id = ?
        WHERE guild_id = ?
    """, (board_message_id, guild_id))

    conn.commit()
    conn.close()
def save_player(discord_id, discord_name, ign, roles, weight=None):
    if weight is None:
        weight = players.get(discord_id, {}).get("weight", DEFAULT_PLAYER_WEIGHT)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO players (discord_id, discord_name, ign, roles, weight)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(discord_id) DO UPDATE SET
            discord_name = excluded.discord_name,
            ign = excluded.ign,
            roles = excluded.roles,
            weight = excluded.weight
    """, (
        discord_id,
        discord_name,
        ign,
        ",".join(roles),
        weight
    ))

    conn.commit()
    conn.close()


def load_players():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("SELECT discord_id, discord_name, ign, roles, weight FROM players")
    rows = cursor.fetchall()

    conn.close()

    for discord_id, discord_name, ign, roles_text, weight in rows:
        players[discord_id] = {
            "discord_name": discord_name,
            "ign": ign,
            "roles": roles_text.split(",") if roles_text else [],
            "weight": weight if weight is not None else DEFAULT_PLAYER_WEIGHT,
        }
def save_lobby_state(guild_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM lobby_state WHERE guild_id = ?", (guild_id,))

    for position, user_id in enumerate(lobby):
        cursor.execute("""
            INSERT INTO lobby_state (guild_id, user_id, area, position)
            VALUES (?, ?, ?, ?)
        """, (guild_id, user_id, "lobby", position))

    for position, user_id in enumerate(waiting_room):
        cursor.execute("""
            INSERT INTO lobby_state (guild_id, user_id, area, position)
            VALUES (?, ?, ?, ?)
        """, (guild_id, user_id, "waiting_room", position))

    cursor.execute("""
        INSERT INTO guild_runtime_state (guild_id, last_signup_time)
        VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            last_signup_time = excluded.last_signup_time
    """, (guild_id, last_signup_time))

    conn.commit()
    conn.close()


def load_lobby_state(guild_id):

    global lobby, waiting_room, last_signup_time
    load_players()

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_id, area
        FROM lobby_state
        WHERE guild_id = ?
        ORDER BY position ASC
    """, (guild_id,))

    rows = cursor.fetchall()

    lobby.clear()
    waiting_room.clear()

    for user_id, area in rows:
        # Only restore players who still have saved /name and /role profile
        if user_id not in players:
            continue

        if area == "lobby":
            lobby.append(user_id)
        elif area == "waiting_room":
            waiting_room.append(user_id)

    cursor.execute("""
        SELECT last_signup_time
        FROM guild_runtime_state
        WHERE guild_id = ?
    """, (guild_id,))

    row = cursor.fetchone()
    conn.close()

    last_signup_time = row[0] if row and row[0] else None

def fill_lobby_from_waiting_room():
    while len(lobby) < 16 and waiting_room:
        next_player = waiting_room.pop(0)

        if next_player not in lobby:
            lobby.append(next_player)
            
def player_label(user_id):
    p = players.get(user_id)
    if not p:
        return f"<@{user_id}>"

    label = f"**{p['ign']}** (<@{user_id}>)"

    if captain_draft:
        if user_id == captain_draft.captain_a:
            label = f"⭐ {label} [Captain A]"
        elif user_id == captain_draft.captain_b:
            label = f"⭐ {label} [Captain B]"

        if user_id == captain_draft.current_picker():
            label = f"👉 {label} **[CURRENT PICK]**"

    return label


def player_weight(user_id):
    try:
        return int(players.get(user_id, {}).get("weight", DEFAULT_PLAYER_WEIGHT))
    except (TypeError, ValueError):
        return DEFAULT_PLAYER_WEIGHT


def team_weight(team):
    return sum(player_weight(user_id) for user_id, _role in team)


def team_weight_text(team_a, team_b):
    weight_a = team_weight(team_a)
    weight_b = team_weight(team_b)
    return (
        f"**Team A Weight:** {weight_a}\n"
        f"**Team B Weight:** {weight_b}\n"
        f"**Weight Difference:** {abs(weight_a - weight_b)}"
    )


def has_role_type(user_id, role_set):
    return bool(set(players[user_id]["roles"]) & role_set)


def role_sort_key(assigned_role):
    order = {
        "Frontline": 1,
        "Lyssa/Flex Derv": 2,
        "Mesmer": 3,
        "Elementalist": 3,
        "Necromancer": 3,
        "Ranger": 3,
        "Prot Monk": 5,
        "Heal Monk": 6,
        "Support/Flag (8)": 7,
    }

    return order.get(assigned_role, 99)


def team_text(team):
    lines = []

    sorted_team = sorted(team, key=lambda item: role_sort_key(item[1]))

    for i, (user_id, role) in enumerate(sorted_team, start=1):
        p = players[user_id]

        prefix = ""

        if captain_draft:
            if user_id in [captain_draft.captain_a, captain_draft.captain_b]:
                prefix += "⭐ "

            if user_id == captain_draft.current_picker():
                prefix += "👉 "

        lines.append(f"{i}. {prefix}**{p['ign']}** — {role}")

    return "\n".join(lines)
def build_draft_board_embed():
    captain_votes = list(votes.values()).count("captain")
    random_votes = list(votes.values()).count("random")

    if lobby:
        lobby_text = ""
        for i, user_id in enumerate(lobby, start=1):
            p = players[user_id]
            roles = ", ".join(p["roles"]) if p["roles"] else "No roles set"
            lobby_text += f"{i}. **{p['ign']}** — {roles}\n"
    else:
        lobby_text = "No players signed up yet."
    if waiting_room:
        waiting_text = ""
        for i, user_id in enumerate(waiting_room, start=1):
            p = players[user_id]
            roles = ", ".join(p["roles"]) if p["roles"] else "No roles set"
            waiting_text += f"{i}. **{p['ign']}** — {roles}\n"
    else:
        waiting_text = "Waiting room is empty."
    if captain_volunteers:
        captain_text = "\n".join(player_label(p) for p in captain_volunteers)
    else:
        captain_text = "No captain volunteers yet."

    description = (
        "**Before signing up:**\n"
        "1. Use `/name` to set your in-game name.\n"
        "2. Use `/role` to pick your roles, in order of priority.\n\n"
        f"## Lobby — {len(lobby)}/16\n"
        f"{lobby_text}\n\n"
        f"## Waiting Room — {len(waiting_room)}\n"
        f"{waiting_text}\n\n"
        f"## Votes\n"
        f"Captain Mode: **{captain_votes}**\n"
        f"Auto-Draft: **{random_votes}**\n\n"
        f"## Captain Volunteers\n"
        f"{captain_text}"
        
    )

    if captain_draft:
        next_picker = captain_draft.current_picker()

        description += "\n\n## Captain Draft\n"
        description += f"**Team A Captain:** {player_label(captain_draft.captain_a)}\n"
        description += f"**Team B Captain:** {player_label(captain_draft.captain_b)}\n\n"

        if next_picker:
            description += f"**Current Pick:** {player_label(next_picker)}\n\n"
        else:
            description += "**Draft Complete**\n\n"

        description += "### Team A\n"
        description += team_text(captain_draft.team_a)
        description += "\n\n### Team B\n"
        description += team_text(captain_draft.team_b)

        if captain_draft.available:
            description += "\n\n### Available Players\n"
            description += "\n".join(player_label(p) for p in captain_draft.available)

    elif draft_result:
        description += f"\n\n## Draft Result\n{draft_result}"

    return discord.Embed(
        title="GW1 GvG Draft Board",
        description=description,
        color=discord.Color.blue()
    )

async def reset_draft_only(interaction: discord.Interaction, silent=False):
    global draft_result, captain_draft, final_team_a, final_team_b
    final_team_a = []
    final_team_b = []
    captain_draft = None
    draft_result = None
    votes.clear()
    captain_volunteers.clear()

    fill_lobby_from_waiting_room()
    save_lobby_state(interaction.guild.id)

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message("Draft reset. Lobby refilled from waiting room if slots were open.", ephemeral=True)

    return True
def is_draft_admin(interaction: discord.Interaction):
    if interaction.user.guild_permissions.administrator:
        return True

    config = get_guild_config(interaction.guild.id)

    if not config or not config.get("admin_role_id"):
        return interaction.user.guild_permissions.manage_guild

    admin_role_id = config["admin_role_id"]

    return any(role.id == admin_role_id for role in interaction.user.roles)
async def kick_from_draft(interaction: discord.Interaction, user_id: int):
    removed = False

    if user_id in lobby:
        lobby.remove(user_id)
        removed = True

    if user_id in waiting_room:
        waiting_room.remove(user_id)
        removed = True

    votes.pop(user_id, None)

    if user_id in captain_volunteers:
        captain_volunteers.remove(user_id)

    fill_lobby_from_waiting_room()
    save_lobby_state(interaction.guild.id)

    if not removed:
        await interaction.response.send_message(
            "That player is not in the lobby or waiting room.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"Kicked {player_label(user_id)} from the draft.",
        ephemeral=True
    )

    await post_new_draft_board(interaction.guild.id)
    
class CaptainDraft:
    def __init__(self, captain_a, captain_b):
        self.captain_a = captain_a
        self.captain_b = captain_b
        self.team_a = [(captain_a, "Captain")]
        self.team_b = [(captain_b, "Captain")]
        self.available = [p for p in lobby if p not in [captain_a, captain_b]]
        self.pick_index = 0
        self.pick_order = self.build_pick_order()

    def build_pick_order(self):
        # 14 remaining picks after captains are placed.
        # A, B, B, A, A, B, B, A...
        order = []
        pattern = [self.captain_a, self.captain_b, self.captain_b, self.captain_a]

        while len(order) < 14:
            order.extend(pattern)

        return order[:14]

    def current_picker(self):
        if self.pick_index >= len(self.pick_order):
            return None
        return self.pick_order[self.pick_index]

    def is_complete(self):
        return len(self.team_a) == 8 and len(self.team_b) == 8

    def pick_player(self, picker_id, picked_id):
        if picker_id != self.current_picker():
            return False, "It is not your pick."

        if picked_id not in self.available:
            return False, "That player is not available."

        assigned_role = players[picked_id]["roles"][0]

        if picker_id == self.captain_a:
            self.team_a.append((picked_id, assigned_role))
        else:
            self.team_b.append((picked_id, assigned_role))

        self.available.remove(picked_id)
        self.pick_index += 1

        return True, "Pick accepted."
class DraftBoardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Sign Up", style=discord.ButtonStyle.success, custom_id="draft_signup")
    async def signup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = await signup_player(interaction, silent=False)
        if result:
            await refresh_board(interaction)

    @discord.ui.button(label="Drop", style=discord.ButtonStyle.danger, custom_id="draft_drop")
    async def drop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = await drop_player(interaction, silent=True)
        if result:
            await refresh_board(interaction)

    @discord.ui.button(label="Vote Captain", style=discord.ButtonStyle.primary, custom_id="draft_vote_captain")
    async def vote_captain_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = await vote_player(interaction, "captain", "Captain Mode", silent=True)
        if result:
            await refresh_board(interaction)

    @discord.ui.button(label="Vote Auto-Draft", style=discord.ButtonStyle.primary, custom_id="draft_vote_random")
    async def vote_random_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = await vote_player(interaction, "random", "Auto-Draft", silent=True)
        if result:
            await refresh_board(interaction)

    @discord.ui.button(label="Volunteer Captain", style=discord.ButtonStyle.secondary, custom_id="draft_captain")
    async def captain_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = await volunteer_captain(interaction, silent=True)
        if result:
            await refresh_board(interaction)
    @discord.ui.button(label="Start Draft", style=discord.ButtonStyle.success, custom_id="draft_start")
    async def start_draft_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can start the draft.",
                ephemeral=True
            )
            return

        if len(lobby) != 16:
            await interaction.response.send_message(
                f"Need exactly 16 players. Current: {len(lobby)}/16",
                ephemeral=True
            )
            return

        # Reuse your existing logic
        await run_startdraft(interaction)
    @discord.ui.button(label="Pick Player", style=discord.ButtonStyle.success, custom_id="draft_pick_player")
    async def pick_player_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not captain_draft:
            await interaction.response.send_message(
                "No captain draft is active.",
                ephemeral=True
            )
            return

        current_picker = captain_draft.current_picker()

        if interaction.user.id != current_picker:
            await interaction.response.send_message(
                f"It is currently {player_label(current_picker)}'s pick.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Choose a player to pick:",
            view=CaptainPickView(),
            ephemeral=True
        )
    @discord.ui.button(label="Admin Panel", style=discord.ButtonStyle.secondary, custom_id="draft_admin_panel")
    async def admin_panel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can use this.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "Admin draft controls:",
            view=AdminDraftView(),
            ephemeral=True
        )
    @discord.ui.button(label="Status", style=discord.ButtonStyle.secondary, custom_id="draft_status")
    async def status_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_status(interaction)


async def refresh_board(interaction: discord.Interaction):
    await interaction.message.edit(
        embed=build_draft_board_embed(),
        view=DraftBoardView()
    )


async def post_new_draft_board(guild_id):
    load_players()
    load_lobby_state(guild_id)

    config = get_guild_config(guild_id)

    if not config or not config.get("draft_channel_id"):
        print("No draft channel configured. Use /setup first.")
        return

    channel = bot.get_channel(config["draft_channel_id"])

    if channel is None:
        print("Could not find configured draft channel.")
        return

    old_board_message_id = config.get("board_message_id")

    if old_board_message_id:
        try:
            old_message = await channel.fetch_message(old_board_message_id)
            await old_message.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            print("Bot does not have permission to delete old draft board.")
        except discord.HTTPException as e:
            print(f"Failed to delete old draft board: {e}")

    message = await channel.send(
        embed=build_draft_board_embed(),
        view=DraftBoardView()
    )

    save_board_message_id(guild_id, message.id)
async def signup_player(interaction: discord.Interaction, silent=False):
    global last_signup_time  # ✅ must be at top

    user_id = interaction.user.id

    if user_id not in players:
        await interaction.response.send_message("Use `/name` first.", ephemeral=True)
        return False

    if not players[user_id]["roles"]:
        await interaction.response.send_message("Use `/role` first.", ephemeral=True)
        return False

    if user_id in lobby:
        await interaction.response.send_message("You are already in the active lobby.", ephemeral=True)
        return False

    if user_id in waiting_room:
        await interaction.response.send_message("You are already in the waiting room.", ephemeral=True)
        return False

    draft_active = captain_draft or draft_result

    if draft_active:
        waiting_room.append(user_id)
        response_text = "A draft is active, so you were added to the waiting room for the next draft."
    elif len(lobby) < 16:
        lobby.append(user_id)
        response_text = "Signup updated."
    else:
        waiting_room.append(user_id)
        response_text = "The active lobby is full, so you were added to the waiting room."

    last_signup_time = time.time()  # only set once here
    save_lobby_state(interaction.guild.id)

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message(response_text, ephemeral=True)

    return True


async def drop_player(interaction: discord.Interaction, silent=False):
    user_id = interaction.user.id

    removed = False

    if user_id in lobby:
        lobby.remove(user_id)
        removed = True

    if user_id in waiting_room:
        waiting_room.remove(user_id)
        removed = True

    votes.pop(user_id, None)

    if user_id in captain_volunteers:
        captain_volunteers.remove(user_id)

    if not removed:
        await interaction.response.send_message("You are not signed up.", ephemeral=True)
        return False

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message("You dropped from the lobby/waiting room.", ephemeral=True)
    save_lobby_state(interaction.guild.id)    
    return True


async def vote_player(interaction: discord.Interaction, mode_value: str, mode_name: str, silent=False):
    user_id = interaction.user.id
    if captain_draft or draft_result:
       await interaction.response.send_message(
            "Voting is locked while a draft is active.",
            ephemeral=True
        )
       return False

    if user_id not in lobby:
        await interaction.response.send_message(
            "Only signed-up players can vote.",
            ephemeral=True
        )
        return False

    votes[user_id] = mode_value

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message(
            f"{player_label(user_id)} voted for **{mode_name}**.",
            ephemeral=True
        )

    return True


async def volunteer_captain(interaction: discord.Interaction, silent=False):
    user_id = interaction.user.id
    if captain_draft or draft_result:
       await interaction.response.send_message(
            "Captain volunteering is locked while a draft is active.",
            ephemeral=True
        )
       return False

    if user_id not in lobby:
        await interaction.response.send_message(
            "Only signed-up players can volunteer as captain.",
            ephemeral=True
        )
        return False

    if user_id in captain_volunteers:
        await interaction.response.send_message(
            "You are already volunteered as captain.",
            ephemeral=True
        )
        return False

    captain_volunteers.append(user_id)

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message(
            f"{player_label(user_id)} volunteered as captain.",
            ephemeral=True
        )

    return True


async def show_status(interaction: discord.Interaction):
    load_lobby_state(interaction.guild.id)
    await interaction.response.send_message(
        embed=build_draft_board_embed(),
        ephemeral=True
    )


def pick_player(pool, team, used):
    random.shuffle(pool)

    for user_id in pool:
        if user_id not in used:
            team.append(user_id)
            used.add(user_id)
            return user_id

    return None

def role_priority_index(player_id, role):
    """
    Lower number = higher priority.
    If role is not in the player's list, return a big number.
    """
    player_roles = players[player_id]["roles"]

    if role in player_roles:
        return player_roles.index(role)

    return 999


def best_role_for_slot(player_id, desired_roles):
    """
    Given a player and a slot type, assign the highest-priority role
    they listed that matches the slot.
    """
    player_roles = players[player_id]["roles"]

    for role in player_roles:
        if role in desired_roles:
            return role

    return None


def pick_for_role(team, used, desired_roles):
    """
    Picks someone for a role slot.
    Priority behavior:
    - Prefer people who listed the needed role higher.
    - If tied, randomize between them.
    """
    candidates = []

    for p in lobby:
        if p in used:
            continue

        assigned_role = best_role_for_slot(p, desired_roles)

        if assigned_role:
            candidates.append((p, assigned_role, role_priority_index(p, assigned_role)))

    if not candidates:
        return False

    # Lower priority index is better: 0 = first role, 1 = second role, etc.
    best_priority = min(priority for _, _, priority in candidates)

    best_candidates = [
        (p, role, priority)
        for p, role, priority in candidates
        if priority == best_priority
    ]

    picked, assigned_role, _ = random.choice(best_candidates)

    team.append((picked, assigned_role))
    used.add(picked)

    return True


def assign_fallback_role(player_id):
    """
    Used only if we have to emergency-fill a team.
    Gives the player their highest-priority listed role.
    """
    return players[player_id]["roles"][0]
def optimize_team_roles(team):
    """
    Assigns one displayed role per player after captain draft.
    Tries to fill the standard comp while respecting player priority.
    """
    desired_slots = [
    ["Frontline"],
    ["Frontline"],
    ["Lyssa/Flex Derv"],
    MIDLINE_ROLES,
    MIDLINE_ROLES,
    ["Prot Monk"],
    ["Heal Monk"],
    ["Support/Flag (8)"],
]

    unassigned = [user_id for user_id, _ in team]
    optimized = []

    for desired_roles in desired_slots:
        candidates = []

        for user_id in unassigned:
            role = best_role_for_slot(user_id, desired_roles)

            if role:
                candidates.append((
                    user_id,
                    role,
                    role_priority_index(user_id, role)
                ))

        if candidates:
            best_priority = min(c[2] for c in candidates)
            best_candidates = [c for c in candidates if c[2] == best_priority]
            picked_id, assigned_role, _ = random.choice(best_candidates)

            optimized.append((picked_id, assigned_role))
            unassigned.remove(picked_id)

    for user_id in unassigned:
        optimized.append((user_id, assign_fallback_role(user_id)))

    return optimized

def count_assigned(team, role_set):
    return len([1 for _, role in team if role in role_set])


def get_priority_role_for_slot(player_id, desired_roles):
    player_roles = players[player_id]["roles"]

    for role in player_roles:
        if role in desired_roles:
            return role

    return None


def assign_team_roles_for_score(team_players):
    desired_slots = [
        ["Frontline"],
        ["Lyssa/Flex Derv"],
        MIDLINE_ROLES,
        MIDLINE_ROLES,
        ["Prot Monk"],
        ["Heal Monk"],
        ["Support/Flag (8)"],
        FRONTLINE_ROLES | MIDLINE_ROLES,
    ]

    unassigned = team_players[:]
    assigned = []

    for desired_roles in desired_slots:
        candidates = []

        for user_id in unassigned:
            role = get_priority_role_for_slot(user_id, desired_roles)

            if role:
                candidates.append((
                    user_id,
                    role,
                    role_priority_index(user_id, role)
                ))

        if candidates:
            best_priority = min(c[2] for c in candidates)
            best_candidates = [c for c in candidates if c[2] == best_priority]
            picked_id, assigned_role, _priority = random.choice(best_candidates)

            assigned.append((picked_id, assigned_role))
            unassigned.remove(picked_id)

    for user_id in unassigned:
        assigned.append((user_id, assign_fallback_role(user_id)))

    return assigned


def score_team(team):
    score = 0
    assigned_roles = [role for _user_id, role in team]

    # Required backline roles
    required_roles = ["Prot Monk", "Heal Monk", "Support/Flag (8)"]

    for role in required_roles:
        count = assigned_roles.count(role)

        if count == 0:
            score += 1000
        elif count > 1:
            score += 200 * (count - 1)

    # Frontline target: exactly 2
    frontline_count = assigned_roles.count("Frontline")

    if frontline_count < 2:
        score += 700 * (2 - frontline_count)
    elif frontline_count > 2:
        score += 300 * (frontline_count - 2)

    # Flex requirement
    flex_count = assigned_roles.count("Lyssa/Flex Derv")
    if flex_count == 0:
        score += 350
    elif flex_count > 1:
        score += 150 * (flex_count - 1)

    # Midline count target: 2 or 3 is good
    mid_count = len([r for r in assigned_roles if r in MIDLINE_ROLES])

    if mid_count < 2:
        score += 400 * (2 - mid_count)
    elif mid_count > 3:
        score += 150 * (mid_count - 3)

    # Penalize people playing lower-priority roles
    for user_id, assigned_role in team:
        priority = role_priority_index(user_id, assigned_role)

        if priority == 0:
            score += 0
        elif priority == 1:
            score += 15
        elif priority == 2:
            score += 40
        elif priority == 3:
            score += 90
        elif priority == 4:
            score += 160
        else:
            score += 300

    return score


def score_match(team_a, team_b):
    score_a = score_team(team_a)
    score_b = score_team(team_b)

    # Penalize uneven role-fit quality.
    role_balance_penalty = abs(score_a - score_b)

    # Penalize uneven manual skill weights.
    weight_balance_penalty = (
        abs(team_weight(team_a) - team_weight(team_b))
        * AUTO_DRAFT_WEIGHT_BALANCE_MULTIPLIER
    )

    return score_a + score_b + role_balance_penalty + weight_balance_penalty


def generate_auto_draft_teams():
    best_result = None
    best_score = None
    anchor_player = lobby[0]
    other_players = lobby[1:]

    for team_a_rest in itertools.combinations(other_players, 7):
        raw_team_a = [anchor_player, *team_a_rest]
        raw_team_b = [p for p in lobby if p not in raw_team_a]

        team_a = assign_team_roles_for_score(raw_team_a)
        team_b = assign_team_roles_for_score(raw_team_b)

        score = score_match(team_a, team_b)

        if best_score is None or score < best_score:
            best_score = score
            best_result = (team_a, team_b)

    team_a, team_b = best_result

    formation = {
        "front": "Auto-Draft balanced",
        "score": best_score
    }

    return team_a, team_b, formation


def generate_random_teams():
    return generate_auto_draft_teams()

class KickPlayerSelect(discord.ui.Select):
    def __init__(self):
        options = []

        for user_id in lobby:
            p = players[user_id]
            options.append(
                discord.SelectOption(
                    label=p["ign"],
                    description="Active Lobby",
                    value=str(user_id)
                )
            )

        for user_id in waiting_room:
            p = players[user_id]
            options.append(
                discord.SelectOption(
                    label=p["ign"],
                    description="Waiting Room",
                    value=str(user_id)
                )
            )

        if not options:
            options.append(
                discord.SelectOption(
                    label="No players available",
                    description="Lobby and waiting room are empty.",
                    value="none"
                )
            )

        super().__init__(
            placeholder="Choose a player to kick",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if not is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can use this.",
                ephemeral=True
            )
            return

        if self.values[0] == "none":
            await interaction.response.send_message(
                "No players to kick.",
                ephemeral=True
            )
            return

        await kick_from_draft(interaction, int(self.values[0]))

async def move_teams_to_voice(interaction: discord.Interaction):
    config = get_guild_config(interaction.guild.id)

    if not config:
        await interaction.response.send_message(
            "Server setup is missing. Run `/setup` first.",
            ephemeral=True
        )
        return

    team_a_channel_id = config.get("team_a_voice_channel_id")
    team_b_channel_id = config.get("team_b_voice_channel_id")

    if not team_a_channel_id or not team_b_channel_id:
        await interaction.response.send_message(
            "Voice channels are not configured. Run `/setup` again.",
            ephemeral=True
        )
        return

    team_a_channel = interaction.guild.get_channel(team_a_channel_id)
    team_b_channel = interaction.guild.get_channel(team_b_channel_id)

    if not team_a_channel or not team_b_channel:
        await interaction.response.send_message(
            "Could not find one or both configured voice channels.",
            ephemeral=True
        )
        return

    team_a = None
    team_b = None

    if captain_draft:
        team_a = captain_draft.team_a
        team_b = captain_draft.team_b
    elif draft_result and final_team_a and final_team_b:
        team_a = final_team_a
        team_b = final_team_b
    else:
        await interaction.response.send_message(
            "No active draft teams to move.",
            ephemeral=True
        )
        return

    moved = 0
    failed = []

    for user_id, _role in team_a:
        member = interaction.guild.get_member(user_id)
        if member and member.voice:
            try:
                await member.move_to(team_a_channel)
                moved += 1
            except Exception:
                failed.append(players[user_id]["ign"])
        else:
            failed.append(players[user_id]["ign"])

    for user_id, _role in team_b:
        member = interaction.guild.get_member(user_id)
        if member and member.voice:
            try:
                await member.move_to(team_b_channel)
                moved += 1
            except Exception:
                failed.append(players[user_id]["ign"])
        else:
            failed.append(players[user_id]["ign"])

    msg = f"Moved **{moved}** players to team voice channels."

    if failed:
        msg += "\n\nCould not move:\n" + "\n".join(failed)

    await interaction.response.send_message(msg, ephemeral=True)
async def wipe_lobby(interaction: discord.Interaction, silent=False):
    global lobby, waiting_room, votes, captain_volunteers
    global draft_result, captain_draft, final_team_a, final_team_b
    global last_signup_time

    lobby.clear()
    waiting_room.clear()
    votes.clear()
    captain_volunteers.clear()

    draft_result = None
    captain_draft = None
    final_team_a = []
    final_team_b = []

    last_signup_time = None

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message(
            "Lobby completely wiped.",
            ephemeral=True
        )

    await post_new_draft_board(interaction.guild.id)    
class AdminDraftView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(KickPlayerSelect())
    @discord.ui.button(label="Move Teams", style=discord.ButtonStyle.primary)
    async def move_teams_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can move teams.",
                ephemeral=True
            )
            return

        await move_teams_to_voice(interaction)
    @discord.ui.button(label="Wipe Lobby", style=discord.ButtonStyle.danger)
    async def wipe_lobby_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can wipe the lobby.",
                ephemeral=True
            )
            return

        await wipe_lobby(interaction, silent=True)    
    @discord.ui.button(label="Reset Draft", style=discord.ButtonStyle.danger)
    async def reset_draft_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can reset the draft.",
                ephemeral=True
            )
            return
    
        await reset_draft_only(interaction, silent=True)
        await post_new_draft_board(interaction.guild.id)
        
class CaptainPickSelect(discord.ui.Select):
    def __init__(self):
        options = []

        if captain_draft:
            for user_id in captain_draft.available:
                p = players[user_id]
                roles = ", ".join(p["roles"])

                options.append(
                    discord.SelectOption(
                        label=p["ign"][:100],
                        description=roles[:100],
                        value=str(user_id)
                    )
                )

        if not options:
            options.append(
                discord.SelectOption(
                    label="No players available",
                    value="none"
                )
            )

        super().__init__(
            placeholder="Pick a player",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        global draft_result, captain_draft, final_team_a, final_team_b

        if not captain_draft:
            await interaction.response.send_message("No captain draft is active.", ephemeral=True)
            return

        if self.values[0] == "none":
            await interaction.response.send_message("No players available.", ephemeral=True)
            return

        picked_id = int(self.values[0])
        picker_id = interaction.user.id

        success, message = captain_draft.pick_player(picker_id, picked_id)

        if not success:
            await interaction.response.send_message(message, ephemeral=True)
            return

        if captain_draft.is_complete():
            captain_draft.team_a = optimize_team_roles(captain_draft.team_a)
            captain_draft.team_b = optimize_team_roles(captain_draft.team_b)
            final_team_a = captain_draft.team_a
            final_team_b = captain_draft.team_b

            draft_result = (
                "**Mode:** Captain Draft\n\n"
                "### Team A\n"
                f"{team_text(captain_draft.team_a)}\n\n"
                "### Team B\n"
                f"{team_text(captain_draft.team_b)}"
            )
            captain_draft = None

        await interaction.response.defer()
        if captain_draft:
            next_picker = captain_draft.current_picker()
            if next_picker:
                channel = interaction.channel
                await channel.send(
                    f"{player_label(next_picker)}, you are on the clock. Click **Pick Player** on the draft board."
                )
        await post_new_draft_board(interaction.guild.id)


class CaptainPickView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(CaptainPickSelect())
        
class SetupWizardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Step 1: Select draft board text channel",
        channel_types=[discord.ChannelType.text],
        min_values=1,
        max_values=1
    )
    async def select_draft_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only server admins can run setup.", ephemeral=True)
            return

        channel = select.values[0]

        save_guild_config(
            interaction.guild.id,
            draft_channel_id=channel.id
        )

        await interaction.response.send_message(
            f"Draft board channel saved: {channel.mention}\n\nNow select Team A voice channel.",
            ephemeral=True,
            view=SetupTeamAVoiceView()
        )


class SetupTeamAVoiceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Step 2: Select Team A voice channel",
        channel_types=[discord.ChannelType.voice],
        min_values=1,
        max_values=1
    )
    async def select_team_a_voice(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only server admins can run setup.", ephemeral=True)
            return

        channel = select.values[0]

        save_guild_config(
            interaction.guild.id,
            team_a_voice_channel_id=channel.id
        )

        await interaction.response.send_message(
            f"Team A voice channel saved: **{channel.name}**\n\nNow select Team B voice channel.",
            ephemeral=True,
            view=SetupTeamBVoiceView()
        )


class SetupTeamBVoiceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Step 3: Select Team B voice channel",
        channel_types=[discord.ChannelType.voice],
        min_values=1,
        max_values=1
    )
    async def select_team_b_voice(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only server admins can run setup.", ephemeral=True)
            return

        channel = select.values[0]

        save_guild_config(
            interaction.guild.id,
            team_b_voice_channel_id=channel.id
        )

        await interaction.response.send_message(
            f"Team B voice channel saved: **{channel.name}**\n\nNow select the Draft Admin role.",
            ephemeral=True,
            view=SetupAdminRoleView()
        )


class SetupAdminRoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Step 4: Select Draft Admin role",
        min_values=1,
        max_values=1
    )
    async def select_admin_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only server admins can run setup.", ephemeral=True)
            return

        role = select.values[0]

        save_guild_config(
            interaction.guild.id,
            admin_role_id=role.id
        )

        await interaction.response.send_message(
            f"Draft Admin role saved: {role.mention}\n\nSetup complete. Posting draft board.",
            ephemeral=True
        )

        await post_new_draft_board(interaction.guild.id)       
class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def inactivity_check_loop(self):
        await self.wait_until_ready()

        while not self.is_closed():
            await asyncio.sleep(60)  # check every minute

            global last_signup_time

            if not last_signup_time:
                continue

            elapsed = time.time() - last_signup_time

            if elapsed >= 7200:  # 2 hours
                print("Auto-wiping lobby due to inactivity.")

                lobby.clear()
                waiting_room.clear()
                votes.clear()
                captain_volunteers.clear()

                global draft_result, captain_draft, final_team_a, final_team_b

                draft_result = None
                captain_draft = None
                final_team_a = []
                final_team_b = []
                last_signup_time = None

                for guild in self.guilds:
                    await post_new_draft_board(guild.id)

    async def setup_hook(self):
        init_db()
        load_players()

        await self.tree.sync()

        self.add_view(DraftBoardView())
        self.loop.create_task(self.inactivity_check_loop())


bot = MyBot()
@bot.tree.command(name="wipelobby", description="Completely wipe the lobby.")
async def wipelobby(interaction: discord.Interaction):
    if not is_draft_admin(interaction):
        await interaction.response.send_message(
            "Only draft admins can wipe the lobby.",
            ephemeral=True
        )
        return

    await wipe_lobby(interaction)
@bot.tree.command(name="setup", description="Run the draft bot setup wizard.")
async def setup(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "Only server admins can run setup.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "Draft bot setup started.\n\nFirst, select the text channel where the draft board should be posted.",
        ephemeral=True,
        view=SetupWizardView()
    )
@bot.tree.command(name="filltest", description="Fill lobby with test players.")
async def filltest(interaction: discord.Interaction):
    if not is_draft_admin(interaction):
        await interaction.response.send_message(
            "Only draft admins can use this.",
            ephemeral=True
        )
        return

    global lobby, waiting_room, votes, captain_volunteers
    global draft_result, captain_draft, final_team_a, final_team_b, last_signup_time

    lobby.clear()
    waiting_room.clear()
    votes.clear()
    captain_volunteers.clear()

    draft_result = None
    captain_draft = None
    final_team_a = []
    final_team_b = []

    role_pool = [
        "Frontline",
        "Lyssa/Flex Derv",
        "Mesmer",
        "Elementalist",
        "Necromancer",
        "Ranger",
        "Prot Monk",
        "Heal Monk",
        "Support/Flag (8)"
    ]

    for i in range(16):
        fake_id = 100000 + i

        players[fake_id] = {
            "discord_name": f"TestUser{i+1}",
            "ign": f"Player{i+1}",
            "roles": random.sample(role_pool, 3),
            "weight": random.randint(70, 140)
        }

        lobby.append(fake_id)

    last_signup_time = time.time()

    await interaction.response.send_message(
        "Test lobby filled with 16 players with random roles and weights.",
        ephemeral=True
    )
    save_lobby_state(interaction.guild.id)
    await post_new_draft_board(interaction.guild.id)
@bot.tree.command(name="pickpanel", description="Open the captain pick panel.")
async def pickpanel(interaction: discord.Interaction):
    if not captain_draft:
        await interaction.response.send_message("No captain draft is active.", ephemeral=True)
        return

    if interaction.user.id != captain_draft.current_picker():
        await interaction.response.send_message(
            f"It is currently {player_label(captain_draft.current_picker())}'s pick.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "Choose a player to pick:",
        view=CaptainPickView(),
        ephemeral=True
    )
@bot.tree.command(name="adminboard", description="Open the admin draft controls.")
async def adminboard(interaction: discord.Interaction):
    load_lobby_state(interaction.guild.id)
    if not is_draft_admin(interaction):
        await interaction.response.send_message(
            "Only draft admins can use this.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "Admin draft controls:",
        view=AdminDraftView(),
        ephemeral=True
    )    
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    if not getattr(bot, "already_synced_commands", False):
        bot.already_synced_commands = True

        for guild in bot.guilds:
            try:
                guild_obj = discord.Object(id=guild.id)

                bot.tree.copy_global_to(guild=guild_obj)
                synced = await bot.tree.sync(guild=guild_obj)

                print(f"Synced {len(synced)} commands to {guild.name}")
            except Exception as e:
                print(f"Failed to sync commands to {guild.name}: {e}")

    if getattr(bot, "already_posted_board", False):
        return

    bot.already_posted_board = True

    for guild in bot.guilds:
        await post_new_draft_board(guild.id)

@bot.tree.command(name="resetdraft", description="Reset only the draft result and refill lobby from waiting room.")
async def resetdraft(interaction: discord.Interaction):
    load_lobby_state(interaction.guild.id)
    await reset_draft_only(interaction)
    
@bot.tree.command(name="name", description="Register your Guild Wars 1 in-game name.")
@app_commands.describe(ign="Your in-game name")
async def name(interaction: discord.Interaction, ign: str):
    user_id = interaction.user.id

    if user_id not in players:
        players[user_id] = {
            "discord_name": interaction.user.display_name,
            "ign": ign,
            "roles": [],
            "weight": DEFAULT_PLAYER_WEIGHT,
        }
    else:
        players[user_id]["ign"] = ign

    save_player(
        user_id,
        interaction.user.display_name,
        players[user_id]["ign"],
        players[user_id]["roles"]
    )

    await interaction.response.send_message(
        f"Registered your IGN as **{ign}**.",
        ephemeral=True
    )


@bot.tree.command(name="role", description="Set the roles you can play.")
@app_commands.describe(
    role1="Primary role",
    role2="Optional role",
    role3="Optional role",
    role4="Optional role",
    role5="Optional role",
)
@app_commands.choices(
    role1=[app_commands.Choice(name=r, value=r) for r in ROLES],
    role2=[app_commands.Choice(name=r, value=r) for r in ROLES],
    role3=[app_commands.Choice(name=r, value=r) for r in ROLES],
    role4=[app_commands.Choice(name=r, value=r) for r in ROLES],
    role5=[app_commands.Choice(name=r, value=r) for r in ROLES],
)
async def role(
    interaction: discord.Interaction,
    role1: app_commands.Choice[str],
    role2: app_commands.Choice[str] = None,
    role3: app_commands.Choice[str] = None,
    role4: app_commands.Choice[str] = None,
    role5: app_commands.Choice[str] = None,
):
    user_id = interaction.user.id

    if user_id not in players:
        await interaction.response.send_message("Use `/name` first.", ephemeral=True)
        return

    chosen = [role1.value]

    for r in [role2, role3, role4, role5]:
        if r and r.value not in chosen:
            chosen.append(r.value)

    players[user_id]["roles"] = chosen

    save_player(
        user_id,
        interaction.user.display_name,
        players[user_id]["ign"],
        players[user_id]["roles"]
    )

    await interaction.response.send_message(
        f"Your roles are now: **{', '.join(chosen)}**.",
        ephemeral=True
    )


@bot.tree.command(name="setweight", description="Set a registered player's Auto-Draft weight.")
@app_commands.describe(
    member="Registered Discord user",
    weight="Skill weight from 50 to 150. Average is 100."
)
async def setweight(
    interaction: discord.Interaction,
    member: discord.Member,
    weight: app_commands.Range[int, 50, 150],
):
    if not is_draft_admin(interaction):
        await interaction.response.send_message(
            "Only draft admins can set player weights.",
            ephemeral=True
        )
        return

    load_players()

    if member.id not in players:
        await interaction.response.send_message(
            f"{member.mention} is not registered yet. They need to use `/name` first.",
            ephemeral=True
        )
        return

    players[member.id]["weight"] = int(weight)

    save_player(
        member.id,
        member.display_name,
        players[member.id]["ign"],
        players[member.id]["roles"],
        weight=int(weight)
    )

    await interaction.response.send_message(
        f"Set **{players[member.id]['ign']}** to Auto-Draft weight **{int(weight)}**.",
        ephemeral=True
    )


@bot.tree.command(name="signup", description="Join the GvG draft lobby.")
async def signup(interaction: discord.Interaction):
    await signup_player(interaction)


@bot.tree.command(name="drop", description="Leave the GvG draft lobby.")
async def drop(interaction: discord.Interaction):
    await drop_player(interaction)


@bot.tree.command(name="vote", description="Vote for captain mode or auto-draft.")
@app_commands.describe(mode="Choose draft mode")
@app_commands.choices(
    mode=[
        app_commands.Choice(name="Captain Mode", value="captain"),
        app_commands.Choice(name="Auto-Draft", value="random"),
    ]
)
async def vote(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    await vote_player(interaction, mode.value, mode.name)


@bot.tree.command(name="captain", description="Volunteer to be a captain.")
async def captain(interaction: discord.Interaction):
    await volunteer_captain(interaction)


@bot.tree.command(name="lobby", description="Show the current GvG draft lobby.")
async def lobby_command(interaction: discord.Interaction):
    await show_status(interaction)


@bot.tree.command(name="draftstatus", description="Show current votes and captain volunteers.")
async def draftstatus(interaction: discord.Interaction):
    await show_status(interaction)


@bot.tree.command(name="draftboard", description="Post the GvG draft board with buttons.")
async def draftboard(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=build_draft_board_embed(),
        view=DraftBoardView()
    )

async def start_captain_draft(interaction: discord.Interaction):
    global captain_draft, draft_result, final_team_a, final_team_b

    if len(captain_volunteers) < 2:
        await interaction.response.send_message(
            "Captain Mode won, but there need to be at least 2 captain volunteers.",
            ephemeral=True
        )
        return

    chosen = random.sample(captain_volunteers, 2)
    random.shuffle(chosen)

    captain_draft = CaptainDraft(chosen[0], chosen[1])
    draft_result = None
    final_team_a = []
    final_team_b = []

    await interaction.response.send_message(
        f"Captain draft started. First pick: {player_label(captain_draft.current_picker())}. "
        f"Captains should use `/pickpanel` when it is their turn.",
        ephemeral=True
    )

    await post_new_draft_board(interaction.guild.id)

async def run_startdraft(interaction: discord.Interaction):
    global draft_result, captain_draft, final_team_a, final_team_b
    
    load_lobby_state(interaction.guild.id)

    if len(lobby) != 16:
        await interaction.response.send_message(
            f"Need exactly 16 players to start. Current lobby: {len(lobby)}/16",
            ephemeral=True
        )
        return

    captain_votes = list(votes.values()).count("captain")
    random_votes = list(votes.values()).count("random")

    if captain_votes > random_votes:
        await start_captain_draft(interaction)
        return

    team_a, team_b, _formation = generate_auto_draft_teams()

    final_team_a = team_a
    final_team_b = team_b

    draft_result = (
        "**Mode:** Auto-Draft\n\n"
        "**Target Comp:** 2 Frontline / 1 Flex / 2 Midline / Prot / Heal / Support\n"
        "**Balanced By:** role fit, role priority, and player weight\n"
        f"{team_weight_text(team_a, team_b)}\n\n"
        "### Team A\n"
        f"{team_text(team_a)}\n\n"
        "### Team B\n"
        f"{team_text(team_b)}"
    )

    await interaction.response.send_message("Draft started.", ephemeral=True)

    await post_new_draft_board(interaction.guild.id)


@bot.tree.command(name="startdraft", description="Start the draft once the lobby has 16 players.")
async def startdraft(interaction: discord.Interaction):
    await run_startdraft(interaction)
    
@bot.tree.command(name="resetlobby", description="Reset the lobby.")
async def resetlobby(interaction: discord.Interaction):
    global draft_result
    global captain_draft
    captain_draft = None
    lobby.clear()
    waiting_room.clear()
    votes.clear()
    captain_volunteers.clear()
    draft_result = None

    await interaction.response.send_message("Lobby reset. Posting a new draft board.", ephemeral=True)

    await post_new_draft_board(interaction.guild.id)


if __name__ == "__main__":
    bot.run(TOKEN)
