import time

import discord
from discord import app_commands

from admin_player_helpers import (
    _find_admin_player,
    admin_registered_player_autocomplete,
    admin_signed_player_autocomplete,
    admin_waiting_player_autocomplete,
    admin_lobby_player_autocomplete,
)
from state import get_state

import draft_service as svc


def register_player_management_commands(bot):
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
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can manage players.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id
        state = get_state(guild_id)
        user_id = _find_admin_player(interaction, player)

        if user_id is None:
            await interaction.response.send_message(
                f"No registered player in this server found for **{player}**.",
                ephemeral=True,
            )
            return

        if user_id in state.lobby or user_id in state.waiting_room:
            await interaction.response.send_message(
                f"**{svc.players[user_id]['ign']}** is already signed up.",
                ephemeral=True,
            )
            return

        if location.value == "lobby":
            if state.captain_draft:
                await interaction.response.send_message(
                    "You cannot add someone to the lobby during an active Captain Draft.",
                    ephemeral=True,
                )
                return

            if len(state.lobby) >= 16:
                await interaction.response.send_message(
                    "The lobby is full. Add them to the waiting room or use `/swapplayers`.",
                    ephemeral=True,
                )
                return

            state.lobby.append(user_id)
            destination = "lobby"
        else:
            state.waiting_room.append(user_id)
            destination = "waiting room"

        state.last_signup_time = time.time()
        svc.save_lobby_state(guild_id)

        await interaction.response.send_message(
            f"Added **{svc.players[user_id]['ign']}** to the **{destination}**.",
            ephemeral=True,
        )

        await svc.post_new_draft_board(guild_id)

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
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can manage players.",
                ephemeral=True,
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
                ephemeral=True,
            )
            return

        ign = svc.players[user_id]["ign"]

        if destination.value == "waiting":
            if user_id in state.waiting_room:
                await interaction.response.send_message(
                    f"**{ign}** is already in the waiting room.",
                    ephemeral=True,
                )
                return

            if state.captain_draft:
                await interaction.response.send_message(
                    "You cannot move an active Captain Draft player out of the lobby.",
                    ephemeral=True,
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
                    ephemeral=True,
                )
                return

            if state.captain_draft:
                await interaction.response.send_message(
                    "You cannot add a player to the lobby during an active Captain Draft.",
                    ephemeral=True,
                )
                return

            if len(state.lobby) >= 16:
                await interaction.response.send_message(
                    "The lobby is full. Use `/swapplayers` to exchange them with a lobby player.",
                    ephemeral=True,
                )
                return

            state.waiting_room.remove(user_id)
            state.lobby.append(user_id)
            destination_label = "lobby"

        svc.save_lobby_state(guild_id)

        await interaction.response.send_message(
            f"Moved **{ign}** to the **{destination_label}**.",
            ephemeral=True,
        )

        await svc.post_new_draft_board(guild_id)

    @bot.tree.command(name="queue", description="Move a waiting-room player to a specific queue position.")
    @app_commands.describe(player="Waiting-room player IGN", position="New queue position, starting at 1")
    @app_commands.autocomplete(player=admin_waiting_player_autocomplete)
    async def queue(
        interaction: discord.Interaction,
        player: str,
        position: int,
    ):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can reorder the waiting room.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id
        state = get_state(guild_id)
        user_id = _find_admin_player(interaction, player)

        if user_id is None or user_id not in state.waiting_room:
            await interaction.response.send_message(
                f"**{player}** is not currently in the waiting room.",
                ephemeral=True,
            )
            return

        if position < 1 or position > len(state.waiting_room):
            await interaction.response.send_message(
                f"Position must be between **1** and **{len(state.waiting_room)}**.",
                ephemeral=True,
            )
            return

        state.waiting_room.remove(user_id)
        state.waiting_room.insert(position - 1, user_id)

        svc.save_lobby_state(guild_id)

        await interaction.response.send_message(
            f"Moved **{svc.players[user_id]['ign']}** to waiting-room position **#{position}**.",
            ephemeral=True,
        )

        await svc.post_new_draft_board(guild_id)

    @bot.tree.command(name="swapplayers", description="Swap one lobby player with one waiting-room player.")
    @app_commands.describe(
        lobby_player="Player currently in the lobby",
        waiting_player="Player currently in the waiting room",
    )
    @app_commands.autocomplete(
        lobby_player=admin_lobby_player_autocomplete,
        waiting_player=admin_waiting_player_autocomplete,
    )
    async def swapplayers(
        interaction: discord.Interaction,
        lobby_player: str,
        waiting_player: str,
    ):
        if not svc.is_draft_admin(interaction):
            await interaction.response.send_message(
                "Only draft admins can manage players.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild.id
        state = get_state(guild_id)

        if state.captain_draft:
            await interaction.response.send_message(
                "You cannot swap active Captain Draft players.",
                ephemeral=True,
            )
            return

        lobby_id = _find_admin_player(interaction, lobby_player)
        waiting_id = _find_admin_player(interaction, waiting_player)

        if lobby_id is None or lobby_id not in state.lobby:
            await interaction.response.send_message(
                f"**{lobby_player}** is not currently in the lobby.",
                ephemeral=True,
            )
            return

        if waiting_id is None or waiting_id not in state.waiting_room:
            await interaction.response.send_message(
                f"**{waiting_player}** is not currently in the waiting room.",
                ephemeral=True,
            )
            return

        waiting_index = state.waiting_room.index(waiting_id)

        state.lobby.remove(lobby_id)
        state.waiting_room.pop(waiting_index)
        state.lobby.append(waiting_id)

        state.waiting_room.insert(waiting_index, lobby_id)

        state.votes.pop(lobby_id, None)

        if lobby_id in state.captain_volunteers:
            state.captain_volunteers.remove(lobby_id)

        svc.save_lobby_state(guild_id)

        await interaction.response.send_message(
            f"Swapped **{svc.players[lobby_id]['ign']}** with **{svc.players[waiting_id]['ign']}**.",
            ephemeral=True,
        )

        await svc.post_new_draft_board(guild_id)
