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
    set_lobby_ban,
    get_lobby_ban,
    remove_lobby_ban,
    get_active_lobby_bans,
)

from draft_logic import (
    CaptainDraft,
    role_sort_key,
    optimize_team_roles,
    generate_random_teams,
    analyze_role_needs,
)
from types import SimpleNamespace

from views import (
    DraftBoardView,
    AdminDraftView,
    CaptainPickView,
    SetupWizardView,
    TimeoutDurationView,
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
    needs = analyze_role_needs(players, lobby)

    needs_text = ""

    if needs["high"]:
        needs_text += "**High Priority:** " + ", ".join(needs["high"]) + "\n"

    if needs["medium"]:
        needs_text += "**Medium Priority:** " + ", ".join(needs["medium"]) + "\n"

    if needs["low"]:
        needs_text += "**Low Priority:** " + ", ".join(needs["low"]) + "\n"

    if not needs_text:
        needs_text = "Lobby role coverage looks good."

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
        f"## Current Needs\n"
        f"{needs_text}\n\n"
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


def format_timeout_remaining(expires_at):
    if expires_at is None:
        return "Permanent"

    remaining = max(0, int(max(0, expires_at - time.time()) + 0.999999))

    if remaining < 60:
        return "less than 1 minute"

    days, remaining = divmod(remaining, 24 * 60 * 60)
    hours, remaining = divmod(remaining, 60 * 60)
    minutes = remaining // 60

    parts = []

    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")

    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")

    if not days and minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

    return ", ".join(parts[:2]) or "less than 1 minute"


async def timeout_from_draft(
    interaction: discord.Interaction,
    user_id: int,
    duration_seconds,
    duration_label: str
):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    if not is_draft_admin(interaction):
        await interaction.response.send_message(
            "Only draft admins can timeout players.",
            ephemeral=True
        )
        return

    # Store/replace the timeout first so a rapid signup cannot slip back in.
    set_lobby_ban(
        guild_id=guild_id,
        user_id=user_id,
        banned_by=interaction.user.id,
        duration_seconds=duration_seconds
    )

    if user_id in state.lobby:
        state.lobby.remove(user_id)

    if user_id in state.waiting_room:
        state.waiting_room.remove(user_id)

    state.votes.pop(user_id, None)

    if user_id in state.captain_volunteers:
        state.captain_volunteers.remove(user_id)

    fill_lobby_from_waiting_room(guild_id)
    save_lobby_state(guild_id)

    await interaction.response.send_message(
        f"{player_label(guild_id, user_id)} has been timed out from draft lobbies **{duration_label}**.",
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

    lobby_ban = get_lobby_ban(guild_id, user_id)

    if lobby_ban:
        if lobby_ban["expires_at"] is None:
            message = "You are permanently banned from draft lobbies."
        else:
            remaining = format_timeout_remaining(lobby_ban["expires_at"])
            expires_timestamp = int(lobby_ban["expires_at"])
            message = (
                "You are currently timed out from draft lobbies.\n"
                f"Time remaining: **{remaining}** (expires <t:{expires_timestamp}:R>)."
            )

        await interaction.response.send_message(message, ephemeral=True)
        return False

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

    # Preserve FIFO: existing waiting-room players always get first claim
    # on any open lobby slots before a brand-new signup can enter.
    if not state.captain_draft and not state.draft_result and len(state.lobby) < 16:
        fill_lobby_from_waiting_room(guild_id)

    if state.captain_draft or state.draft_result or len(state.lobby) >= 16 or state.waiting_room:
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

    # If the draft is not active, immediately give the newly opened lobby
    # slot to the oldest waiting-room player.
    if not state.captain_draft and not state.draft_result:
        fill_lobby_from_waiting_room(guild_id)

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
        timeout_from_draft=timeout_from_draft,
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
        dm_failed = await notify_drafted_players(
            interaction,
            state.final_team_a,
            state.final_team_b
        )

        if dm_failed:
            await interaction.channel.send(
                "Could not DM:\n" + "\n".join(dm_failed)
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
        intents = discord.Intents.default()
        intents.members = True

        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    

    async def setup_hook(self):
        init_db()
        load_players()

        await self.tree.sync()

        self.add_view(DraftBoardView(get_view_context))
        ##self.loop.create_task(self.inactivity_check_loop()) This makes the lobby reset automatically if no one signs up for 2 hours.


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
async def timeout_player_autocomplete(
    interaction: discord.Interaction,
    current: str
):
    if interaction.guild is None:
        return []

    current_lower = current.casefold().strip()
    state = get_state(interaction.guild.id)

    # Use the cached member list, plus anyone already present in this guild's
    # lobby/waiting room as a fallback if the member cache is incomplete.
    eligible_user_ids = {
        member.id
        for member in interaction.guild.members
    }
    eligible_user_ids.update(state.lobby)
    eligible_user_ids.update(state.waiting_room)

    matches = []

    for user_id, data in players.items():
        ign = data.get("ign")

        if not ign or user_id not in eligible_user_ids:
            continue

        if current_lower and current_lower not in ign.casefold():
            continue

        matches.append((ign, user_id))

    matches.sort(key=lambda item: item[0].casefold())

    return [
        app_commands.Choice(
            name=ign[:100],
            value=str(user_id)
        )
        for ign, user_id in matches[:25]
    ]


@bot.tree.command(name="timeout", description="Timeout a player from draft lobbies.")
@app_commands.describe(player="Player IGN")
@app_commands.autocomplete(player=timeout_player_autocomplete)
async def timeout(interaction: discord.Interaction, player: str):
    if not is_draft_admin(interaction):
        await interaction.response.send_message(
            "Only draft admins can timeout players.",
            ephemeral=True
        )
        return

    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True
        )
        return

    state = get_state(interaction.guild.id)

    eligible_user_ids = {
        member.id
        for member in interaction.guild.members
    }
    eligible_user_ids.update(state.lobby)
    eligible_user_ids.update(state.waiting_room)

    user_id = None

    try:
        candidate_id = int(player)

        if candidate_id in eligible_user_ids and candidate_id in players:
            user_id = candidate_id

    except ValueError:
        exact_matches = [
            candidate_id
            for candidate_id, data in players.items()
            if candidate_id in eligible_user_ids
            and data.get("ign", "").casefold() == player.casefold()
        ]

        if len(exact_matches) == 1:
            user_id = exact_matches[0]

        elif len(exact_matches) > 1:
            await interaction.response.send_message(
                f"More than one player in this server uses the IGN **{player}**. "
                "Choose one from autocomplete.",
                ephemeral=True
            )
            return

    if user_id is None:
        await interaction.response.send_message(
            f"No registered player in this server found with IGN **{player}**.",
            ephemeral=True
        )
        return

    ign = players[user_id]["ign"]

    await interaction.response.send_message(
        f"Choose how long to timeout **{ign}** from draft lobbies:",
        view=TimeoutDurationView(
            get_view_context(interaction.guild.id),
            user_id
        ),
        ephemeral=True
    )


async def untimeout_player_autocomplete(
    interaction: discord.Interaction,
    current: str
):
    active_bans = get_active_lobby_bans(interaction.guild.id)
    current_lower = current.lower().strip()
    choices = []

    for ban in active_bans:
        user_id = ban["user_id"]
        player = players.get(user_id)

        if not player or not player.get("ign"):
            continue

        ign = player["ign"]

        if current_lower and current_lower not in ign.lower():
            continue

        choices.append(
            app_commands.Choice(
                name=ign[:100],
                value=str(user_id)
            )
        )

        if len(choices) >= 25:
            break

    return choices


async def untimeout_player_autocomplete(
    interaction: discord.Interaction,
    current: str
):
    active_bans = get_active_lobby_bans(interaction.guild.id)
    current_lower = current.lower().strip()
    choices = []

    for ban in active_bans:
        user_id = ban["user_id"]
        player = players.get(user_id)

        if not player or not player.get("ign"):
            continue

        ign = player["ign"]

        if current_lower and current_lower not in ign.lower():
            continue

        choices.append(
            app_commands.Choice(
                name=ign[:100],
                value=str(user_id)
            )
        )

        if len(choices) >= 25:
            break

    return choices


@bot.tree.command(name="untimeout", description="Remove a player's draft lobby timeout.")
@app_commands.describe(player="Player IGN")
@app_commands.autocomplete(player=untimeout_player_autocomplete)
async def untimeout(interaction: discord.Interaction, player: str):
    if not is_draft_admin(interaction):
        await interaction.response.send_message(
            "Only draft admins can remove lobby timeouts.",
            ephemeral=True
        )
        return

    user_id = None

    # Selecting an autocomplete result sends the hidden Discord ID.
    try:
        user_id = int(player)
    except ValueError:
        # Also allow an admin to manually type an exact IGN.
        for candidate_id, data in players.items():
            if data.get("ign", "").lower() == player.lower():
                user_id = candidate_id
                break

    if user_id is None:
        await interaction.response.send_message(
            f"No registered player found with IGN **{player}**.",
            ephemeral=True
        )
        return

    player_data = players.get(user_id)
    ign = player_data["ign"] if player_data and player_data.get("ign") else "Unknown player"

    removed = remove_lobby_ban(interaction.guild.id, user_id)

    if not removed:
        await interaction.response.send_message(
            f"**{ign}** does not have an active draft lobby timeout.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"Removed the draft lobby timeout for **{ign}**.",
        ephemeral=True
    )


@bot.tree.command(name="timeouts", description="Show active draft lobby timeouts.")
async def timeouts(interaction: discord.Interaction):
    if not is_draft_admin(interaction):
        await interaction.response.send_message(
            "Only draft admins can view lobby timeouts.",
            ephemeral=True
        )
        return

    active_bans = get_active_lobby_bans(interaction.guild.id)

    if not active_bans:
        await interaction.response.send_message(
            "There are no active draft lobby timeouts.",
            ephemeral=True
        )
        return

    lines = []

    for ban in active_bans:
        user_id = ban["user_id"]
        member = interaction.guild.get_member(user_id)

        if user_id in players:
            name = f"**{players[user_id]['ign']}** (<@{user_id}>)"
        elif member:
            name = member.mention
        else:
            name = f"<@{user_id}>"

        if ban["expires_at"] is None:
            duration = "**Permanent**"
        else:
            expires_timestamp = int(ban["expires_at"])
            remaining = format_timeout_remaining(ban["expires_at"])
            duration = f"**{remaining}** remaining — <t:{expires_timestamp}:R>"

        lines.append(f"• {name} — {duration}")

    embed = discord.Embed(
        title="Active Draft Lobby Timeouts",
        description="\n".join(lines),
        color=discord.Color.orange()
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)



# ---------------------------------------------------------------------------
# Admin player / waiting-room management
# Normal /signup behavior remains FIFO. These are explicit admin overrides.
# Lobby ordering is intentionally not exposed because it has no draft effect.
# ---------------------------------------------------------------------------

def _admin_manage_eligible_ids(interaction: discord.Interaction):
    state = get_state(interaction.guild.id)

    eligible_ids = {
        member.id
        for member in interaction.guild.members
    }

    eligible_ids.update(state.lobby)
    eligible_ids.update(state.waiting_room)

    return eligible_ids


def _find_admin_player(interaction: discord.Interaction, value: str):
    eligible_ids = _admin_manage_eligible_ids(interaction)

    try:
        user_id = int(value)
        if user_id in eligible_ids and user_id in players:
            return user_id
    except ValueError:
        pass

    matches = [
        user_id
        for user_id, data in players.items()
        if user_id in eligible_ids
        and data.get("ign", "").casefold() == value.casefold()
    ]

    return matches[0] if len(matches) == 1 else None


async def admin_registered_player_autocomplete(interaction: discord.Interaction, current: str):
    if interaction.guild is None:
        return []

    state = get_state(interaction.guild.id)
    eligible_ids = _admin_manage_eligible_ids(interaction)
    current_cf = current.casefold().strip()
    matches = []

    for user_id, data in players.items():
        ign = data.get("ign")
        if not ign or user_id not in eligible_ids:
            continue
        if user_id in state.lobby or user_id in state.waiting_room:
            continue
        if current_cf and current_cf not in ign.casefold():
            continue
        matches.append((ign, user_id))

    matches.sort(key=lambda item: item[0].casefold())

    return [
        app_commands.Choice(name=ign[:100], value=str(user_id))
        for ign, user_id in matches[:25]
    ]


async def admin_signed_player_autocomplete(interaction: discord.Interaction, current: str):
    if interaction.guild is None:
        return []

    state = get_state(interaction.guild.id)
    current_cf = current.casefold().strip()
    matches = []

    for user_id in list(state.lobby) + list(state.waiting_room):
        data = players.get(user_id)
        if not data or not data.get("ign"):
            continue

        ign = data["ign"]
        if current_cf and current_cf not in ign.casefold():
            continue

        matches.append((ign, user_id))

    matches.sort(key=lambda item: item[0].casefold())

    return [
        app_commands.Choice(name=ign[:100], value=str(user_id))
        for ign, user_id in matches[:25]
    ]


async def admin_waiting_player_autocomplete(interaction: discord.Interaction, current: str):
    if interaction.guild is None:
        return []

    state = get_state(interaction.guild.id)
    current_cf = current.casefold().strip()
    matches = []

    for user_id in state.waiting_room:
        data = players.get(user_id)
        if not data or not data.get("ign"):
            continue

        ign = data["ign"]
        if current_cf and current_cf not in ign.casefold():
            continue

        matches.append((ign, user_id))

    return [
        app_commands.Choice(name=ign[:100], value=str(user_id))
        for ign, user_id in matches[:25]
    ]


async def admin_lobby_player_autocomplete(interaction: discord.Interaction, current: str):
    if interaction.guild is None:
        return []

    state = get_state(interaction.guild.id)
    current_cf = current.casefold().strip()
    matches = []

    for user_id in state.lobby:
        data = players.get(user_id)
        if not data or not data.get("ign"):
            continue

        ign = data["ign"]
        if current_cf and current_cf not in ign.casefold():
            continue

        matches.append((ign, user_id))

    return [
        app_commands.Choice(name=ign[:100], value=str(user_id))
        for ign, user_id in matches[:25]
    ]


@bot.tree.command(name="addplayer", description="Manually add a registered player to the draft.")
@app_commands.describe(player="Player IGN", location="Where to add the player")
@app_commands.choices(location=[
    app_commands.Choice(name="Lobby", value="lobby"),
    app_commands.Choice(name="Waiting Room", value="waiting"),
])
@app_commands.autocomplete(player=admin_registered_player_autocomplete)
async def addplayer(
    interaction: discord.Interaction,
    player: str,
    location: app_commands.Choice[str],
):
    if not is_draft_admin(interaction):
        await interaction.response.send_message(
            "Only draft admins can manage players.",
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    state = get_state(guild_id)
    user_id = _find_admin_player(interaction, player)

    if user_id is None:
        await interaction.response.send_message(
            f"No registered player in this server found for **{player}**.",
            ephemeral=True
        )
        return

    if user_id in state.lobby or user_id in state.waiting_room:
        await interaction.response.send_message(
            f"**{players[user_id]['ign']}** is already signed up.",
            ephemeral=True
        )
        return

    if location.value == "lobby":
        if state.captain_draft:
            await interaction.response.send_message(
                "You cannot add someone to the lobby during an active Captain Draft.",
                ephemeral=True
            )
            return

        if len(state.lobby) >= 16:
            await interaction.response.send_message(
                "The lobby is full. Add them to the waiting room or use `/swapplayers`.",
                ephemeral=True
            )
            return

        state.lobby.append(user_id)
        destination = "lobby"
    else:
        state.waiting_room.append(user_id)
        destination = "waiting room"

    state.last_signup_time = time.time()
    save_lobby_state(guild_id)

    await interaction.response.send_message(
        f"Added **{players[user_id]['ign']}** to the **{destination}**.",
        ephemeral=True
    )

    await post_new_draft_board(guild_id)


@bot.tree.command(name="moveplayer", description="Move a signed player between lobby and waiting room.")
@app_commands.describe(player="Player IGN", destination="Where to move the player")
@app_commands.choices(destination=[
    app_commands.Choice(name="Lobby", value="lobby"),
    app_commands.Choice(name="Waiting Room", value="waiting"),
])
@app_commands.autocomplete(player=admin_signed_player_autocomplete)
async def moveplayer(
    interaction: discord.Interaction,
    player: str,
    destination: app_commands.Choice[str],
):
    if not is_draft_admin(interaction):
        await interaction.response.send_message(
            "Only draft admins can manage players.",
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    state = get_state(guild_id)
    user_id = _find_admin_player(interaction, player)

    if user_id is None or (
        user_id not in state.lobby
        and user_id not in state.waiting_room
    ):
        await interaction.response.send_message(
            f"**{player}** is not currently signed up.",
            ephemeral=True
        )
        return

    ign = players[user_id]["ign"]

    if destination.value == "waiting":
        if user_id in state.waiting_room:
            await interaction.response.send_message(
                f"**{ign}** is already in the waiting room.",
                ephemeral=True
            )
            return

        if state.captain_draft:
            await interaction.response.send_message(
                "You cannot move an active Captain Draft player out of the lobby.",
                ephemeral=True
            )
            return

        state.lobby.remove(user_id)
        state.waiting_room.append(user_id)
        state.votes.pop(user_id, None)

        if user_id in state.captain_volunteers:
            state.captain_volunteers.remove(user_id)

        destination_label = "waiting room"
    else:
        if user_id in state.lobby:
            await interaction.response.send_message(
                f"**{ign}** is already in the lobby.",
                ephemeral=True
            )
            return

        if state.captain_draft:
            await interaction.response.send_message(
                "You cannot add a player to the lobby during an active Captain Draft.",
                ephemeral=True
            )
            return

        if len(state.lobby) >= 16:
            await interaction.response.send_message(
                "The lobby is full. Use `/swapplayers` to exchange them with a lobby player.",
                ephemeral=True
            )
            return

        state.waiting_room.remove(user_id)
        state.lobby.append(user_id)
        destination_label = "lobby"

    save_lobby_state(guild_id)

    await interaction.response.send_message(
        f"Moved **{ign}** to the **{destination_label}**.",
        ephemeral=True
    )

    await post_new_draft_board(guild_id)


@bot.tree.command(name="queue", description="Move a waiting-room player to a specific queue position.")
@app_commands.describe(player="Waiting-room player IGN", position="New queue position, starting at 1")
@app_commands.autocomplete(player=admin_waiting_player_autocomplete)
async def queue(
    interaction: discord.Interaction,
    player: str,
    position: int,
):
    if not is_draft_admin(interaction):
        await interaction.response.send_message(
            "Only draft admins can reorder the waiting room.",
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    state = get_state(guild_id)
    user_id = _find_admin_player(interaction, player)

    if user_id is None or user_id not in state.waiting_room:
        await interaction.response.send_message(
            f"**{player}** is not currently in the waiting room.",
            ephemeral=True
        )
        return

    if position < 1 or position > len(state.waiting_room):
        await interaction.response.send_message(
            f"Position must be between **1** and **{len(state.waiting_room)}**.",
            ephemeral=True
        )
        return

    state.waiting_room.remove(user_id)
    state.waiting_room.insert(position - 1, user_id)

    save_lobby_state(guild_id)

    await interaction.response.send_message(
        f"Moved **{players[user_id]['ign']}** to waiting-room position **#{position}**.",
        ephemeral=True
    )

    await post_new_draft_board(guild_id)


@bot.tree.command(name="swapplayers", description="Swap one lobby player with one waiting-room player.")
@app_commands.describe(
    lobby_player="Player currently in the lobby",
    waiting_player="Player currently in the waiting room"
)
@app_commands.autocomplete(
    lobby_player=admin_lobby_player_autocomplete,
    waiting_player=admin_waiting_player_autocomplete
)
async def swapplayers(
    interaction: discord.Interaction,
    lobby_player: str,
    waiting_player: str,
):
    if not is_draft_admin(interaction):
        await interaction.response.send_message(
            "Only draft admins can manage players.",
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    state = get_state(guild_id)

    if state.captain_draft:
        await interaction.response.send_message(
            "You cannot swap active Captain Draft players.",
            ephemeral=True
        )
        return

    lobby_id = _find_admin_player(interaction, lobby_player)
    waiting_id = _find_admin_player(interaction, waiting_player)

    if lobby_id is None or lobby_id not in state.lobby:
        await interaction.response.send_message(
            f"**{lobby_player}** is not currently in the lobby.",
            ephemeral=True
        )
        return

    if waiting_id is None or waiting_id not in state.waiting_room:
        await interaction.response.send_message(
            f"**{waiting_player}** is not currently in the waiting room.",
            ephemeral=True
        )
        return

    waiting_index = state.waiting_room.index(waiting_id)

    state.lobby.remove(lobby_id)
    state.waiting_room.pop(waiting_index)
    state.lobby.append(waiting_id)

    # Demoted lobby player takes the promoted waiter's exact queue spot.
    state.waiting_room.insert(waiting_index, lobby_id)

    state.votes.pop(lobby_id, None)

    if lobby_id in state.captain_volunteers:
        state.captain_volunteers.remove(lobby_id)

    save_lobby_state(guild_id)

    await interaction.response.send_message(
        f"Swapped **{players[lobby_id]['ign']}** with **{players[waiting_id]['ign']}**.",
        ephemeral=True
    )

    await post_new_draft_board(guild_id)

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
@bot.tree.command(name="subnext", description="Move the next waiting room player into the lobby.")
async def subnext(interaction: discord.Interaction):
    if not is_draft_admin(interaction):
        await interaction.response.send_message(
            "Only draft admins can use this.",
            ephemeral=True
        )
        return

    guild_id = interaction.guild.id
    state = get_state(guild_id)

    if not state.waiting_room:
        await interaction.response.send_message(
            "Waiting room is empty.",
            ephemeral=True
        )
        return

    if len(state.lobby) >= 16:
        await interaction.response.send_message(
            "Lobby is already full. Kick or drop someone first.",
            ephemeral=True
        )
        return

    next_player = state.waiting_room.pop(0)
    state.lobby.append(next_player)

    save_lobby_state(guild_id)

    await interaction.response.send_message(
        f"Moved {player_label(guild_id, next_player)} from waiting room into the lobby.",
        ephemeral=True
    )

    await post_new_draft_board(guild_id)
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
@app_commands.describe(player="Player IGN")
async def stats(
    interaction: discord.Interaction,
    player: str = None
):
    guild_id = interaction.guild.id

    target_id = interaction.user.id

    if player:
        found = False

        for user_id, data in players.items():
            if data["ign"].lower() == player.lower():
                target_id = user_id
                found = True
                break

        if not found:
            await interaction.response.send_message(
                f"No player found with IGN `{player}`.",
                ephemeral=True
            )
            return

    if target_id not in players:
        await interaction.response.send_message(
            "Player data not found.",
            ephemeral=True
        )
        return

    player_data = players[target_id]

    member = interaction.guild.get_member(target_id)

    discord_name = (
        f"{member.display_name} (@{member.name})"
        if member
        else player_data["discord_name"]
    )

    stats_data = get_player_stats(guild_id, target_id)

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
        title=f"{player_data['ign']} Draft Stats",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="Discord",
        value=discord_name,
        inline=False
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
        view=DraftBoardView(get_view_context)
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
async def notify_drafted_players(interaction: discord.Interaction, team_a, team_b):
    dm_failed = []

    async def notify_team(team, team_name):
        for user_id, assigned_role in team:
            print(f"Checking DM for {user_id}")

            member = interaction.guild.get_member(user_id)

            if not member:
                print(f"Member not found: {user_id}")
                continue

            print(f"Found member: {member.name}")

            if member.voice:
                print(f"{member.name} already in voice")
                continue

            try:
                print(f"Sending DM to {member.name}")

                await member.send(
                    f"The draft is ready.\n\n"
                    f"You were drafted to **Team {team_name}** as **{assigned_role}**.\n"
                    f"Please join Discord voice when you can."
                )

                print(f"DM sent to {member.name}")

            except Exception as e:
                print(f"DM failed for {member.name}: {e}")
                dm_failed.append(players[user_id]["ign"])

    await notify_team(team_a, "A")
    await notify_team(team_b, "B")

    return dm_failed
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
    dm_failed = await notify_drafted_players(interaction, team_a, team_b)

    msg = "Draft started."

    if dm_failed:
        msg += "\n\nCould not DM:\n" + "\n".join(dm_failed)

    await interaction.response.send_message(msg, ephemeral=True)

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
