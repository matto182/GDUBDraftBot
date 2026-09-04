import discord

from config import normalize_roles
from database import get_guild_config, save_board_message_id
from draft_logic import analyze_role_needs, role_sort_key
from state import get_state
import service_runtime as runtime
from service_runtime import load_players, players
from lobby_state_service import load_lobby_state
from views import DraftBoardView


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
            current_roles = normalize_roles(p.get("roles", []))
            roles = ", ".join(current_roles) if current_roles else "No roles set"

            lobby_text += f"{i}. **{p['ign']}** — {roles}\n"
    else:
        lobby_text = "No players signed up yet."

    if waiting_room:
        waiting_text = ""

        for i, user_id in enumerate(waiting_room, start=1):
            p = players[user_id]
            current_roles = normalize_roles(p.get("roles", []))
            roles = ", ".join(current_roles) if current_roles else "No roles set"

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


async def post_new_draft_board(guild_id):
    from view_context_service import get_view_context
    load_players()
    load_lobby_state(guild_id)

    config = get_guild_config(guild_id)

    if not config or not config.get("draft_channel_id"):
        print("No draft channel configured. Use /setup first.")
        return

    channel = runtime.bot_client.get_channel(config["draft_channel_id"])

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

async def show_status(interaction: discord.Interaction):
    load_lobby_state(interaction.guild.id)
    await interaction.response.send_message(
        embed=build_draft_board_embed(interaction.guild.id),
        ephemeral=True
    )

async def refresh_board(interaction: discord.Interaction):
    from view_context_service import get_view_context
    await interaction.message.edit(
        embed=build_draft_board_embed(interaction.guild.id),
        view=DraftBoardView(get_view_context)
    )
