import math

import discord

from draft_history_repository import (
    get_draft_count,
    get_draft_details,
    get_draft_history_page,
)


HISTORY_PAGE_SIZE = 5


def format_mode(mode):
    normalized = str(mode or "").strip().casefold()
    if normalized == "captain":
        return "Captain Draft"
    if normalized == "random":
        return "Random Draft"
    if not normalized:
        return "Draft"
    return f"{str(mode).strip().title()} Draft"


def format_player_name(player):
    if player.get("ign"):
        return player["ign"]
    if player.get("discord_name"):
        return player["discord_name"]
    return f"<@{player['user_id']}>"


def get_history_page(guild_id, page, page_size=HISTORY_PAGE_SIZE):
    page_size = max(1, int(page_size))
    total = get_draft_count(guild_id)
    total_pages = max(1, math.ceil(total / page_size)) if total else 1
    page = min(max(0, int(page)), total_pages - 1)
    drafts = get_draft_history_page(
        guild_id,
        limit=page_size,
        offset=page * page_size,
    )
    return {
        "drafts": drafts,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


def build_history_embed(page_data, selected_draft_id=None):
    drafts = page_data["drafts"]
    page = page_data["page"]
    total = page_data["total"]
    total_pages = page_data["total_pages"]

    embed = discord.Embed(
        title="Draft History",
        description=(
            f"Page **{page + 1}** of **{total_pages}** • "
            f"**{total}** completed draft{'s' if total != 1 else ''}"
        ),
        color=discord.Color.blue(),
    )

    if not drafts:
        embed.add_field(
            name="No completed drafts",
            value="Completed drafts will appear here after they are saved.",
            inline=False,
        )
        return embed

    for draft in drafts:
        draft_id = draft["draft_id"]
        mode = format_mode(draft["mode"])
        created_at = int(draft["created_at"])
        player_count = int(draft.get("player_count") or 0)

        lines = [
            f"<t:{created_at}:f>",
            f"Players: **{player_count}**",
        ]

        if str(draft.get("mode") or "").casefold() == "captain":
            captain_a = draft.get("captain_a_ign") or (
                f"<@{draft['captain_a']}>" if draft.get("captain_a") else "Unknown"
            )
            captain_b = draft.get("captain_b_ign") or (
                f"<@{draft['captain_b']}>" if draft.get("captain_b") else "Unknown"
            )
            lines.append(f"Captains: **{captain_a}** vs **{captain_b}**")

        marker = " • Selected" if draft_id == selected_draft_id else ""
        embed.add_field(
            name=f"#{draft_id} — {mode}{marker}",
            value="\n".join(lines),
            inline=False,
        )

    embed.set_footer(text="Select a draft, then choose View Draft for full teams and roles.")
    return embed


def build_draft_detail_embed(guild_id, draft_id):
    details = get_draft_details(guild_id, draft_id)
    if not details:
        return None

    draft = details["draft"]
    players = details["players"]

    embed = discord.Embed(
        title=f"Draft #{draft['draft_id']} — {format_mode(draft['mode'])}",
        description=f"Completed <t:{int(draft['created_at'])}:f>",
        color=discord.Color.blue(),
    )

    for team_name in ("A", "B"):
        team_players = [player for player in players if player["team"] == team_name]
        lines = []

        for player in team_players:
            name = format_player_name(player)
            captain_text = " — Captain" if player.get("was_captain") else ""
            lines.append(f"**{name}** — {player['assigned_role']}{captain_text}")

        embed.add_field(
            name=f"Team {team_name}",
            value="\n".join(lines) if lines else "No players recorded.",
            inline=False,
        )

    embed.set_footer(text="Draft history does not display hidden player weights.")
    return embed
