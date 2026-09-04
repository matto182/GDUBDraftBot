import discord

from database import set_player_weight
from state import get_state
from service_runtime import load_players, players
from moderation_service import has_owner_role


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
