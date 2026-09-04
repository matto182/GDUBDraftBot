import discord

from database import get_guild_config
from state import get_state
from service_runtime import players


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
