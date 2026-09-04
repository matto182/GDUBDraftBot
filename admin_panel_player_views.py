import discord

import draft_service as svc
import player_management_service as player_management
from state import get_state


def _player_name(user_id):
    player = svc.players.get(user_id, {})
    return player.get("ign") or str(user_id)


def _build_options(user_ids, empty_label, description=None):
    options = []

    for user_id in list(user_ids)[:25]:
        kwargs = {
            "label": _player_name(user_id)[:100],
            "value": str(user_id),
        }
        if description:
            kwargs["description"] = description(user_id)[:100]

        options.append(discord.SelectOption(**kwargs))

    if not options:
        options.append(discord.SelectOption(label=empty_label[:100], value="none"))

    return options


async def _ensure_admin(interaction):
    if svc.is_draft_admin(interaction):
        return True

    await interaction.response.send_message(
        "Only draft admins can use the admin panel.",
        ephemeral=True,
    )
    return False


async def _send_result(interaction, success, message):
    await interaction.response.send_message(message, ephemeral=True)

    if success:
        await svc.post_new_draft_board(interaction.guild.id)


class AddPlayerSelect(discord.ui.Select):
    def __init__(self, guild):
        state = get_state(guild.id)
        guild_member_ids = {member.id for member in guild.members}
        available = sorted(
            (
                user_id
                for user_id, player in svc.players.items()
                if user_id in guild_member_ids
                and player.get("ign")
                and user_id not in state.lobby
                and user_id not in state.waiting_room
            ),
            key=lambda user_id: _player_name(user_id).casefold(),
        )

        super().__init__(
            placeholder="Choose a registered player to add",
            options=_build_options(
                available,
                "No unsigned registered players",
            ),
        )

    async def callback(self, interaction):
        if not await _ensure_admin(interaction):
            return

        if self.values[0] == "none":
            await interaction.response.send_message(
                "There are no available registered players to add.",
                ephemeral=True,
            )
            return

        user_id = int(self.values[0])
        await interaction.response.send_message(
            f"Where should **{_player_name(user_id)}** be added?",
            view=AddPlayerDestinationView(user_id),
            ephemeral=True,
        )


class AddPlayerView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=300)
        self.add_item(AddPlayerSelect(guild))


class AddPlayerDestinationView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=300)
        self.user_id = user_id

    async def _add(self, interaction, destination):
        if not await _ensure_admin(interaction):
            return

        success, message = player_management.add_player(
            interaction.guild.id,
            self.user_id,
            destination,
        )
        await _send_result(interaction, success, message)

    @discord.ui.button(label="Lobby", style=discord.ButtonStyle.primary)
    async def lobby_button(self, interaction, button):
        await self._add(interaction, "lobby")

    @discord.ui.button(label="Waiting Room", style=discord.ButtonStyle.secondary)
    async def waiting_button(self, interaction, button):
        await self._add(interaction, "waiting")


class KickPlayerSelect(discord.ui.Select):
    def __init__(self, guild_id):
        state = get_state(guild_id)
        signed = list(state.lobby) + list(state.waiting_room)

        def area(user_id):
            return "Active Lobby" if user_id in state.lobby else "Waiting Room"

        super().__init__(
            placeholder="Choose a player to kick",
            options=_build_options(signed, "Lobby and waiting room are empty", area),
        )

    async def callback(self, interaction):
        if not await _ensure_admin(interaction):
            return

        if self.values[0] == "none":
            await interaction.response.send_message(
                "No players are currently signed up.",
                ephemeral=True,
            )
            return

        await svc.kick_from_draft(interaction, int(self.values[0]))


class KickPlayerView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.add_item(KickPlayerSelect(guild_id))


class MovePlayerSelect(discord.ui.Select):
    def __init__(self, guild_id):
        state = get_state(guild_id)
        signed = list(state.lobby) + list(state.waiting_room)

        def destination(user_id):
            if user_id in state.lobby:
                return "Move to Waiting Room"
            return "Move to Lobby"

        super().__init__(
            placeholder="Choose a player to move",
            options=_build_options(signed, "No signed players", destination),
        )

    async def callback(self, interaction):
        if not await _ensure_admin(interaction):
            return

        if self.values[0] == "none":
            await interaction.response.send_message(
                "No players are currently signed up.",
                ephemeral=True,
            )
            return

        success, message = player_management.move_player_to_other_area(
            interaction.guild.id,
            int(self.values[0]),
        )
        await _send_result(interaction, success, message)


class MovePlayerView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.add_item(MovePlayerSelect(guild_id))


class SwapLobbySelect(discord.ui.Select):
    def __init__(self, parent, guild_id):
        self.parent_view = parent
        state = get_state(guild_id)

        super().__init__(
            placeholder="Lobby player",
            options=_build_options(state.lobby, "Lobby is empty"),
            row=0,
        )

    async def callback(self, interaction):
        if not await _ensure_admin(interaction):
            return

        self.parent_view.lobby_user_id = (
            None if self.values[0] == "none" else int(self.values[0])
        )
        await interaction.response.defer()


class SwapWaitingSelect(discord.ui.Select):
    def __init__(self, parent, guild_id):
        self.parent_view = parent
        state = get_state(guild_id)

        super().__init__(
            placeholder="Waiting-room player",
            options=_build_options(state.waiting_room, "Waiting room is empty"),
            row=1,
        )

    async def callback(self, interaction):
        if not await _ensure_admin(interaction):
            return

        self.parent_view.waiting_user_id = (
            None if self.values[0] == "none" else int(self.values[0])
        )
        await interaction.response.defer()


class SwapPlayersView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.lobby_user_id = None
        self.waiting_user_id = None
        self.add_item(SwapLobbySelect(self, guild_id))
        self.add_item(SwapWaitingSelect(self, guild_id))

    @discord.ui.button(label="Swap Players", style=discord.ButtonStyle.primary, row=2)
    async def confirm_swap(self, interaction, button):
        if not await _ensure_admin(interaction):
            return

        if self.lobby_user_id is None or self.waiting_user_id is None:
            await interaction.response.send_message(
                "Choose both a lobby player and a waiting-room player first.",
                ephemeral=True,
            )
            return

        success, message = player_management.swap_players(
            interaction.guild.id,
            self.lobby_user_id,
            self.waiting_user_id,
        )
        await _send_result(interaction, success, message)


class QueuePositionModal(discord.ui.Modal, title="Set Waiting-Room Position"):
    position = discord.ui.TextInput(
        label="New queue position",
        placeholder="1",
        required=True,
        max_length=3,
    )

    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction):
        if not await _ensure_admin(interaction):
            return

        try:
            position = int(str(self.position.value).strip())
        except ValueError:
            await interaction.response.send_message(
                "Queue position must be a whole number.",
                ephemeral=True,
            )
            return

        success, message = player_management.set_queue_position(
            interaction.guild.id,
            self.user_id,
            position,
        )
        await _send_result(interaction, success, message)


class QueuePlayerSelect(discord.ui.Select):
    def __init__(self, guild_id):
        state = get_state(guild_id)
        super().__init__(
            placeholder="Choose a waiting-room player",
            options=_build_options(state.waiting_room, "Waiting room is empty"),
        )

    async def callback(self, interaction):
        if not await _ensure_admin(interaction):
            return

        if self.values[0] == "none":
            await interaction.response.send_message(
                "The waiting room is empty.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            QueuePositionModal(int(self.values[0]))
        )


class QueuePlayerView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.add_item(QueuePlayerSelect(guild_id))
