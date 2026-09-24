import discord

from dm_cooldown_repository import player_dm_is_on_cooldown, mark_player_dm_sent
from service_runtime import players


async def notify_drafted_players(interaction: discord.Interaction, team_a, team_b):
    guild_id = interaction.guild.id
    dm_failed = []

    async def notify_team(team, team_name):
        for user_id, assigned_role in team:
            member = interaction.guild.get_member(user_id)

            # Only hit Discord's API if the member cache misses.
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(user_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException) as error:
                    print(f"Could not resolve member {user_id}: {error}")
                    if user_id in players:
                        dm_failed.append(players[user_id]["ign"])
                    continue

            if member.voice is not None and member.voice.channel is not None:
                print(f"{member.name} ({user_id}) is already in voice; skipping draft DM")
                continue

            # Limit successful draft DMs to one per player, per guild, every 8 hours.
            if player_dm_is_on_cooldown(guild_id, user_id):
                print(f"DM cooldown active for {user_id}; skipping")
                continue

            try:
                await member.send(
                    f"Your GvG draft is ready.\n\n"
                    f"Team: **{team_name}**\n"
                    f"Role: **{assigned_role}**\n\n"
                    f"Please join your team voice channel."
                )

                # Failed sends do not start the cooldown.
                mark_player_dm_sent(guild_id, user_id)
                print(f"Draft DM sent to {member.name} ({user_id})")

            except (discord.Forbidden, discord.HTTPException) as error:
                print(f"Draft DM failed for {member.name} ({user_id}): {error}")
                if user_id in players:
                    dm_failed.append(players[user_id]["ign"])

    await notify_team(team_a, "A")
    await notify_team(team_b, "B")

    return dm_failed
