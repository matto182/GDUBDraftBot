import discord
import sqlite3
import random
from discord import app_commands
import asyncio
import time
from state import get_state

last_signup_time = None
guild_states = {}
active_guild_id = None

from config import (
    TOKEN,
    DB_FILE,
    ROLES,
    FRONTLINE_ROLES,
    FLEX_ROLES,
    MIDLINE_ROLES,
    BACKLINE_ROLES,
)

from database import (
    init_db,
    save_player,
    load_players_into,
    save_guild_config,
    get_guild_config,
    save_board_message_id,
    save_lobby_state_to_db,
    load_lobby_state_from_db,
    save_completed_draft,
    get_player_stats,
)

from draft_logic import (
    CaptainDraft,
    role_sort_key,
    optimize_team_roles,
    generate_random_teams,
)
from types import SimpleNamespace

from views import (
    DraftBoardView,
    AdminDraftView,
    CaptainPickView,
    SetupWizardView,
)


players = {}
lobby = []
waiting_room = []
votes = {}
captain_volunteers = []
last_board_message_id = None
draft_result = None
captain_draft = None



def load_players():
    load_players_into(players)


def save_lobby_state(guild_id):
    state = get_state(guild_id)

    save_lobby_state_to_db(
        guild_id,
        state.lobby,
        state.waiting_room,
        state.last_signup_time
    )


def load_lobby_state(guild_id):
    load_players()

    state = get_state(guild_id)

    state.last_signup_time = load_lobby_state_from_db(
        guild_id,
        players,
        state.lobby,
        state.waiting_room
    )
def fill_lobby_from_waiting_room(guild_id):
    state = get_state(guild_id)

    while len(state.lobby) < 16 and state.waiting_room:
        next_player = state.waiting_room.pop(0)

        if next_player not in state.lobby:
            state.lobby.append(next_player)
            
def player_label(guild_id, user_id):
    state = get_state(guild_id)
    captain_draft = state.captain_draft
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



def team_text(guild_id, team):
    state = get_state(guild_id)
    captain_draft = state.captain_draft
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
def build_draft_board_embed(guild_id):
    state = get_state(guild_id)

    lobby = state.lobby
    waiting_room = state.waiting_room
    votes = state.votes
    captain_volunteers = state.captain_volunteers
    draft_result = state.draft_result
    captain_draft = state.captain_draft

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
        captain_text = "\n".join(
            player_label(guild_id, p)
            for p in captain_volunteers
        )
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
        f"Random Draft: **{random_votes}**\n\n"
        f"## Captain Volunteers\n"
        f"{captain_text}"
    )

    if captain_draft:
        next_picker = captain_draft.current_picker()

        description += "\n\n## Captain Draft\n"
        description += f"**Team A Captain:** {player_label(guild_id, captain_draft.captain_a)}\n"
        description += f"**Team B Captain:** {player_label(guild_id, captain_draft.captain_b)}\n\n"

        if next_picker:
            description += f"**Current Pick:** {player_label(guild_id, next_picker)}\n\n"
        else:
            description += "**Draft Complete**\n\n"

        description += "### Team A\n"
        description += team_text(guild_id, captain_draft.team_a)

        description += "\n\n### Team B\n"
        description += team_text(guild_id, captain_draft.team_b)

        if captain_draft.available:
            description += "\n\n### Available Players\n"

            description += "\n".join(
                player_label(guild_id, p)
                for p in captain_draft.available
            )

    elif draft_result:
        description += f"\n\n## Draft Result\n{draft_result}"

    return discord.Embed(
        title="GW1 GvG Draft Board",
        description=description,
        color=discord.Color.blue()
    )

async def reset_draft_only(interaction: discord.Interaction, silent=False):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    state.final_team_a = []
    state.final_team_b = []
    state.captain_draft = None
    state.draft_result = None
    state.votes.clear()
    state.captain_volunteers.clear()

    fill_lobby_from_waiting_room(guild_id)
    save_lobby_state(guild_id)

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message(
            "Draft reset. Lobby refilled from waiting room if slots were open.",
            ephemeral=True
        )

    return True
async def kick_from_draft(interaction: discord.Interaction, user_id: int):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    removed = False

    if user_id in state.lobby:
        state.lobby.remove(user_id)
        removed = True

    if user_id in state.waiting_room:
        state.waiting_room.remove(user_id)
        removed = True

    state.votes.pop(user_id, None)

    if user_id in state.captain_volunteers:
        state.captain_volunteers.remove(user_id)

    fill_lobby_from_waiting_room(guild_id)
    save_lobby_state(guild_id)

    if not removed:
        await interaction.response.send_message(
            "That player is not in the lobby or waiting room.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"Kicked {player_label(guild_id, user_id)} from the draft.",
        ephemeral=True
    )

    await post_new_draft_board(guild_id)



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
        embed=build_draft_board_embed(guild_id),
        view=DraftBoardView(get_view_context)
    )

    save_board_message_id(guild_id, message.id)
async def signup_player(interaction: discord.Interaction, silent=False):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    user_id = interaction.user.id

    if user_id not in players:
        await interaction.response.send_message("Use `/name` first.", ephemeral=True)
        return False

    if not players[user_id]["roles"]:
        await interaction.response.send_message("Use `/role` first.", ephemeral=True)
        return False

    if user_id in state.lobby:
        await interaction.response.send_message("You are already in the active lobby.", ephemeral=True)
        return False

    if user_id in state.waiting_room:
        await interaction.response.send_message("You are already in the waiting room.", ephemeral=True)
        return False

    if state.captain_draft or state.draft_result or len(state.lobby) >= 16:
        state.waiting_room.append(user_id)
    else:
        state.lobby.append(user_id)

    state.last_signup_time = time.time()
    save_lobby_state(guild_id)

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message("Signup updated.", ephemeral=True)

    return True


async def drop_player(interaction: discord.Interaction, silent=False):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    user_id = interaction.user.id
    removed = False

    if user_id in state.lobby:
        state.lobby.remove(user_id)
        removed = True

    if user_id in state.waiting_room:
        state.waiting_room.remove(user_id)
        removed = True

    state.votes.pop(user_id, None)

    if user_id in state.captain_volunteers:
        state.captain_volunteers.remove(user_id)

    if not removed:
        await interaction.response.send_message("You are not signed up.", ephemeral=True)
        return False

    save_lobby_state(guild_id)

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message("You dropped from the lobby/waiting room.", ephemeral=True)

    return True


async def vote_player(interaction: discord.Interaction, mode_value: str, mode_name: str, silent=False):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    user_id = interaction.user.id

    if state.captain_draft or state.draft_result:
        await interaction.response.send_message(
            "Voting is locked while a draft is active.",
            ephemeral=True
        )
        return False

    if user_id not in state.lobby:
        await interaction.response.send_message(
            "Only signed-up players can vote.",
            ephemeral=True
        )
        return False

    state.votes[user_id] = mode_value

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message(
            f"{player_label(guild_id, user_id)} voted for **{mode_name}**.",
            ephemeral=True
        )

    return True


async def volunteer_captain(interaction: discord.Interaction, silent=False):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    user_id = interaction.user.id

    if state.captain_draft or state.draft_result:
        await interaction.response.send_message(
            "Captain volunteering is locked while a draft is active.",
            ephemeral=True
        )
        return False

    if user_id not in state.lobby:
        await interaction.response.send_message(
            "Only signed-up players can volunteer as captain.",
            ephemeral=True
        )
        return False

    if user_id in state.captain_volunteers:
        await interaction.response.send_message(
            "You are already volunteered as captain.",
            ephemeral=True
        )
        return False

    state.captain_volunteers.append(user_id)

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message(
            f"{player_label(guild_id, user_id)} volunteered as captain.",
            ephemeral=True
        )

    return True


async def show_status(interaction: discord.Interaction):
    load_lobby_state(interaction.guild.id)
    await interaction.response.send_message(
        embed=build_draft_board_embed(interaction.guild.id),
        ephemeral=True
    )






async def move_teams_to_voice(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    config = get_guild_config(guild_id)

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

    if state.captain_draft:
        team_a = state.captain_draft.team_a
        team_b = state.captain_draft.team_b
    elif state.draft_result and state.final_team_a and state.final_team_b:
        team_a = state.final_team_a
        team_b = state.final_team_b
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
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    state.lobby.clear()
    state.waiting_room.clear()
    state.votes.clear()
    state.captain_volunteers.clear()

    state.draft_result = None
    state.captain_draft = None
    state.final_team_a = []
    state.final_team_b = []
    state.last_signup_time = None

    save_lobby_state(guild_id)

    if silent:
        await interaction.response.defer()
    else:
        await interaction.response.send_message(
            "Lobby completely wiped.",
            ephemeral=True
        )

    await post_new_draft_board(guild_id)
def is_draft_admin(interaction: discord.Interaction):
    if interaction.user.guild_permissions.administrator:
        return True

    config = get_guild_config(interaction.guild.id)

    if not config or not config.get("admin_role_id"):
        return interaction.user.guild_permissions.manage_guild

    admin_role_id = config["admin_role_id"]

    return any(role.id == admin_role_id for role in interaction.user.roles)
def get_captain_draft():
    return captain_draft
async def refresh_board(interaction: discord.Interaction):
    await interaction.message.edit(
        embed=build_draft_board_embed(interaction.guild.id),
        view=DraftBoardView(get_view_context)
    )

def get_view_context(guild_id):
    state = get_state(guild_id)

    return SimpleNamespace(
        guild_id=guild_id,

        players=players,
        lobby=state.lobby,
        waiting_room=state.waiting_room,

        get_captain_draft=lambda: state.captain_draft,

        signup_player=signup_player,
        drop_player=drop_player,
        vote_player=vote_player,
        volunteer_captain=volunteer_captain,
        refresh_board=refresh_board,
        show_status=show_status,
        run_startdraft=run_startdraft,
        player_label=player_label,
        is_draft_admin=is_draft_admin,
        kick_from_draft=kick_from_draft,
        move_teams_to_voice=move_teams_to_voice,
        wipe_lobby=wipe_lobby,
        reset_draft_only=reset_draft_only,
        post_new_draft_board=post_new_draft_board,
        save_guild_config=save_guild_config,
        handle_captain_pick=handle_captain_pick,
    )
async def handle_captain_pick(interaction: discord.Interaction, picked_id: int):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    if not state.captain_draft:
        await interaction.response.send_message("No captain draft is active.", ephemeral=True)
        return

    picker_id = interaction.user.id

    success, message = state.captain_draft.pick_player(players, picker_id, picked_id)

    if not success:
        await interaction.response.send_message(message, ephemeral=True)
        return

    if state.captain_draft.is_complete():
        state.captain_draft.team_a = optimize_team_roles(players, state.captain_draft.team_a)
        state.captain_draft.team_b = optimize_team_roles(players, state.captain_draft.team_b)

        state.final_team_a = state.captain_draft.team_a
        state.final_team_b = state.captain_draft.team_b
        save_completed_draft(
            guild_id=guild_id,
            mode="captain",
            team_a=state.final_team_a,
            team_b=state.final_team_b,
            players=players,
            captain_a=state.captain_draft.captain_a,
            captain_b=state.captain_draft.captain_b
            )

        state.draft_result = (
            "**Mode:** Captain Draft\n\n"
            "### Team A\n"
            f"{team_text(guild_id, state.final_team_a)}\n\n"
            "### Team B\n"
            f"{team_text(guild_id, state.final_team_b)}"
        )

        state.captain_draft = None

    await interaction.response.defer()

    if state.captain_draft:
        next_picker = state.captain_draft.current_picker()
        if next_picker:
            await interaction.channel.send(
                f"{player_label(guild_id, next_picker)}, you are on the clock. Click **Pick Player** on the draft board."
            )

    await post_new_draft_board(guild_id)    
     
class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def inactivity_check_loop(self):
        await self.wait_until_ready()

        while not self.is_closed():
            await asyncio.sleep(60)

            for guild in self.guilds:
                guild_id = guild.id
                state = get_state(guild_id)

                if not state.last_signup_time:
                    continue

                elapsed = time.time() - state.last_signup_time

                if elapsed >= 7200:
                    print(f"Auto-wiping lobby due to inactivity for guild {guild_id}.")

                    state.lobby.clear()
                    state.waiting_room.clear()
                    state.votes.clear()
                    state.captain_volunteers.clear()

                    state.draft_result = None
                    state.captain_draft = None
                    state.final_team_a = []
                    state.final_team_b = []
                    state.last_signup_time = None

                    save_lobby_state(guild_id)
                    await post_new_draft_board(guild_id)

    async def setup_hook(self):
        init_db()
        load_players()

        await self.tree.sync()

        self.add_view(DraftBoardView(get_view_context))
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
        view=SetupWizardView(get_view_context(interaction.guild.id))
    )
@bot.tree.command(name="filltest", description="Fill lobby with test players.")
async def filltest(interaction: discord.Interaction):
    if not is_draft_admin(interaction):
        await interaction.response.send_message(
            "Only draft admins can use this.",
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    state = get_state(guild_id)

    state.lobby.clear()
    state.waiting_room.clear()
    state.votes.clear()
    state.captain_volunteers.clear()

    state.draft_result = None
    state.captain_draft = None
    state.final_team_a = []
    state.final_team_b = []

    test_lobby = [
        ("Player1",  ["Frontline", "Lyssa/Flex Derv", "Mesmer"]),
        ("Player2",  ["Frontline", "Lyssa/Flex Derv", "Ranger"]),
        ("Player3",  ["Mesmer", "Elementalist", "Necromancer"]),
        ("Player4",  ["Elementalist", "Necromancer", "Ranger"]),
        ("Player5",  ["Prot Monk", "Heal Monk", "Support/Flag (8)"]),
        ("Player6",  ["Heal Monk", "Prot Monk", "Support/Flag (8)"]),
        ("Player7",  ["Support/Flag (8)", "Heal Monk", "Prot Monk"]),
        ("Player8",  ["Frontline", "Mesmer", "Ranger"]),

        ("Player9",  ["Frontline", "Lyssa/Flex Derv", "Elementalist"]),
        ("Player10", ["Frontline", "Lyssa/Flex Derv", "Necromancer"]),
        ("Player11", ["Mesmer", "Elementalist", "Ranger"]),
        ("Player12", ["Elementalist", "Necromancer", "Mesmer"]),
        ("Player13", ["Prot Monk", "Heal Monk", "Support/Flag (8)"]),
        ("Player14", ["Heal Monk", "Prot Monk", "Support/Flag (8)"]),
        ("Player15", ["Support/Flag (8)", "Heal Monk", "Prot Monk"]),
        ("Player16", ["Frontline", "Necromancer", "Ranger"]),
    ]

    for i, (ign, roles) in enumerate(test_lobby):
        fake_id = 100000 + i

        players[fake_id] = {
            "discord_name": f"TestUser{i+1}",
            "ign": ign,
            "roles": roles
        }

        save_player(
            fake_id,
            f"TestUser{i+1}",
            ign,
            roles
        )

        state.lobby.append(fake_id)

    state.last_signup_time = time.time()

    save_lobby_state(guild_id)

    await interaction.response.send_message(
        "Test lobby filled with 16 players.",
        ephemeral=True
    )

    await post_new_draft_board(guild_id)
@bot.tree.command(name="stats", description="View player draft stats.")
@app_commands.describe(player="Optional player to view")
async def stats(
    interaction: discord.Interaction,
    player: discord.Member = None
):
    target = player or interaction.user

    guild_id = interaction.guild.id
    stats_data = get_player_stats(guild_id, target.id)

    drafts_played = stats_data["drafts_played"]
    times_captain = stats_data["times_captain"]

    roles_text = ""

    if stats_data["roles"]:
        for role, count in stats_data["roles"]:
            roles_text += f"{role}: {count}\n"
    else:
        roles_text = "No role data."

    priority_text = ""

    priority_map = {
        1: "Primary",
        2: "Secondary",
        3: "Tertiary",
        4: "Fourth",
        999: "Fill/Off-role"
    }

    if stats_data["priority_stats"]:
        for priority, count in stats_data["priority_stats"]:
            label = priority_map.get(priority, f"Priority {priority}")
            priority_text += f"{label}: {count}\n"
    else:
        priority_text = "No assignment data."

    embed = discord.Embed(
        title=f"{target.display_name} Draft Stats",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="Drafts Played",
        value=str(drafts_played),
        inline=True
    )

    embed.add_field(
        name="Times Captain",
        value=str(times_captain),
        inline=True
    )

    embed.add_field(
        name="Roles Played",
        value=roles_text,
        inline=False
    )

    embed.add_field(
        name="Role Priority Usage",
        value=priority_text,
        inline=False
    )

    await interaction.response.send_message(embed=embed)
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
        view=CaptainPickView(get_view_context(interaction.guild.id)),
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
        view=AdminDraftView(get_view_context(interaction.guild.id)),
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


@bot.tree.command(name="signup", description="Join the GvG draft lobby.")
async def signup(interaction: discord.Interaction):
    await signup_player(interaction)


@bot.tree.command(name="drop", description="Leave the GvG draft lobby.")
async def drop(interaction: discord.Interaction):
    await drop_player(interaction)


@bot.tree.command(name="vote", description="Vote for captain mode or random draft.")
@app_commands.describe(mode="Choose draft mode")
@app_commands.choices(
    mode=[
        app_commands.Choice(name="Captain Mode", value="captain"),
        app_commands.Choice(name="Random Draft", value="random"),
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
        embed=build_draft_board_embed(interaction.guild.id),
        view=DraftBoardView(get_view_context())
    )

async def start_captain_draft(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    if len(state.captain_volunteers) < 2:
        await interaction.response.send_message(
            "Captain Mode won, but there need to be at least 2 captain volunteers.",
            ephemeral=True
        )
        return

    chosen = random.sample(state.captain_volunteers, 2)
    random.shuffle(chosen)

    state.captain_draft = CaptainDraft(state.lobby, chosen[0], chosen[1])
    state.draft_result = None
    state.final_team_a = []
    state.final_team_b = []

    await interaction.response.send_message(
        f"Captain draft started. First pick: {player_label(guild_id, state.captain_draft.current_picker())}. "
        f"Captains should use `/pickpanel` when it is their turn.",
        ephemeral=True
    )

    await post_new_draft_board(guild_id)

async def run_startdraft(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    load_lobby_state(guild_id)

    if len(state.lobby) != 16:
        await interaction.response.send_message(
            f"Need exactly 16 players to start. Current lobby: {len(state.lobby)}/16",
            ephemeral=True
        )
        return

    captain_votes = list(state.votes.values()).count("captain")
    random_votes = list(state.votes.values()).count("random")

    if captain_votes > random_votes:
        await start_captain_draft(interaction)
        return

    team_a, team_b, formation = generate_random_teams(players, state.lobby)

    state.final_team_a = team_a
    state.final_team_b = team_b
    #Saving draft stats
    save_completed_draft(
        guild_id=guild_id,
        mode="random",
        team_a=team_a,
        team_b=team_b,
        players=players,
        balance_score=formation["score"]
    )

    state.draft_result = (
        "**Mode:** Random Draft\n\n"
        "**Target Comp:** 2 Frontline / 1 Flex / 2 Midline / Prot / Heal / Support\n"
        f"**Balancing Score:** {formation['score']} lower is better\n\n"
        "### Team A\n"
        f"{team_text(guild_id, team_a)}\n\n"
        "### Team B\n"
        f"{team_text(guild_id, team_b)}"
    )

    await interaction.response.send_message("Draft started.", ephemeral=True)

    await post_new_draft_board(guild_id)


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


bot.run(TOKEN)
