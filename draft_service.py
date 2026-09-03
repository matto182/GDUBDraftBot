import random
import time
from types import SimpleNamespace

import discord

from state import get_state
from database import (
    save_player,
    load_players_into,
    save_guild_config,
    get_guild_config,
    save_board_message_id,
    save_lobby_state_to_db,
    load_lobby_state_from_db,
    save_completed_draft,
    get_player_weights,
    set_player_weight,
)
from draft_logic import (
    CaptainDraft,
    role_sort_key,
    optimize_team_roles,
    generate_random_teams,
    analyze_role_needs,
)
from views import (
    DraftBoardView,
    AdminDraftView,
    CaptainPickView,
    SetupWizardView,
)

players = {}
bot_client = None


def set_bot(client):
    global bot_client
    bot_client = client



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



async def post_new_draft_board(guild_id):
    load_players()
    load_lobby_state(guild_id)

    config = get_guild_config(guild_id)

    if not config or not config.get("draft_channel_id"):
        print("No draft channel configured. Use /setup first.")
        return

    channel = bot_client.get_channel(config["draft_channel_id"])

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

    # Moving multiple members can take longer than Discord allows for the
    # initial interaction response. Defer before starting the move operations.
    await interaction.response.defer(ephemeral=True)

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

    await interaction.followup.send(msg, ephemeral=True)
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


def has_owner_role(guild_id, member):
    """Check the configured Owner role by ID. No admin fallback is allowed."""
    config = get_guild_config(guild_id)

    if not config or not config.get("owner_role_id"):
        return False

    owner_role_id = config["owner_role_id"]
    return any(role.id == owner_role_id for role in getattr(member, "roles", []))


def is_owner(interaction: discord.Interaction):
    return has_owner_role(interaction.guild.id, interaction.user)


async def handle_owner_prefix_message(message: discord.Message):
    """Handle intentionally undiscoverable Owner-only prefix commands."""
    if message.author.bot or message.guild is None:
        return

    content = message.content.strip()
    content_cf = content.casefold()

    is_adjust = content_cf.startswith("!adjust " )
    is_debugweights = content_cf == "!debugweights"

    if not is_adjust and not is_debugweights:
        return

    # Silently ignore anyone without the configured Owner role. This avoids
    # confirming that the hidden commands exist.
    if not has_owner_role(message.guild.id, message.author):
        return

    # Remove the command message immediately when possible.
    try:
        await message.delete()
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        pass

    if is_debugweights:
        state = get_state(message.guild.id)
        debug = state.last_balance_debug

        if not debug:
            response = (
                "No random-draft balance debug data is available yet. "
                "Run an autodraft first, then use this command again."
            )
        else:
            def format_team(team_key, team_name):
                team = debug[team_key]
                lines = [
                    f"**Team {team_name}**",
                    f"Hidden weight total: {team['weight']:+d}",
                    f"Composition penalty: {team['composition_penalty']}",
                    f"Effective strength: {team['effective_strength']:+d}",
                    f"Off-role slots: {team['off_role_count']}",
                    "Player weights:",
                ]

                for player in team["players"]:
                    lines.append(
                        f"- {player['ign']}: {player['weight']:+d}"
                    )

                return "\n".join(lines)

            response = (
                "**Last Random Draft — Hidden Balance Debug**\n\n"
                f"{format_team('team_a', 'A')}\n\n"
                f"{format_team('team_b', 'B')}\n\n"
                f"Effective-strength difference: {debug['strength_difference']}\n"
                f"Final optimizer score: {debug['optimizer_score']}"
            )

        try:
            await message.author.send(response)
        except discord.HTTPException:
            pass
        return

    # !adjust
    payload = content[len("!adjust " ):].strip()
    parts = payload.rsplit(maxsplit=1)

    if len(parts) != 2:
        try:
            await message.author.send("Usage: `!adjust Player IGN 200`")
        except discord.HTTPException:
            pass
        return

    player_name, points_text = parts

    try:
        points = int(points_text)
    except ValueError:
        try:
            await message.author.send(
                "The final value must be a whole number, for example `200` or `-200`."
            )
        except discord.HTTPException:
            pass
        return

    load_players()

    matches = [
        (user_id, data)
        for user_id, data in players.items()
        if data["ign"].casefold() == player_name.casefold()
    ]

    if not matches:
        response = f"No player found with IGN `{player_name}`."
    elif len(matches) > 1:
        response = f"More than one player uses the IGN `{player_name}`."
    else:
        user_id, player_data = matches[0]
        set_player_weight(message.guild.id, user_id, points)

        if points == 0:
            response = f"Cleared {player_data['ign']}'s adjustment."
        else:
            response = f"Set {player_data['ign']} to {points:+d}."

    # Never confirm the adjustment in a public channel.
    try:
        await message.author.send(response)
    except discord.HTTPException:
        pass


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

    # Random team generation can take longer than Discord's initial
    # interaction-response window. Acknowledge the button immediately, then
    # use follow-up messages once the draft work finishes.
    await interaction.response.defer(ephemeral=True)

    try:
        team_a, team_b, formation = generate_random_teams(
            players,
            state.lobby,
            get_player_weights(guild_id),
        )
    except ValueError as error:
        await interaction.followup.send(str(error), ephemeral=True)
        return

    state.final_team_a = team_a
    state.final_team_b = team_b

    # Keep the latest random-draft internals in memory for the hidden
    # Owner-only !debugweights command. Nothing here is shown publicly.
    player_weights = get_player_weights(guild_id)

    def build_debug_team(team, prefix):
        return {
            "weight": int(formation[f"{prefix}_weight"]),
            "composition_penalty": formation[f"{prefix}_composition_penalty"],
            "effective_strength": int(formation[f"{prefix}_effective_strength"]),
            "off_role_count": formation[f"{prefix}_off_role_count"],
            "players": [
                {
                    "user_id": user_id,
                    "ign": players[user_id]["ign"],
                    "weight": int(player_weights.get(user_id, 0)),
                }
                for user_id, _role in team
            ],
        }

    state.last_balance_debug = {
        "team_a": build_debug_team(team_a, "team_a"),
        "team_b": build_debug_team(team_b, "team_b"),
        "strength_difference": abs(
            int(formation["team_a_effective_strength"])
            - int(formation["team_b_effective_strength"])
        ),
        "optimizer_score": formation["score"],
    }

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
        "### Team A\n"
        f"{team_text(guild_id, team_a)}\n\n"
        "### Team B\n"
        f"{team_text(guild_id, team_b)}"
    )
    dm_failed = await notify_drafted_players(interaction, team_a, team_b)

    msg = "Draft started."

    if dm_failed:
        msg += "\n\nCould not DM:\n" + "\n".join(dm_failed)

    await interaction.followup.send(msg, ephemeral=True)

    await post_new_draft_board(guild_id)


