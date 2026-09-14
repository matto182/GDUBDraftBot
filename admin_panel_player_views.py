import discord

import draft_service as svc
import player_management_service as player_management
from state import get_state
from admin_player_helpers import (
    _player_matches_admin_value,
    admin_player_choice_label,
    admin_player_identity_text,
    find_registered_player_matches,
    resolve_player_search,
)


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

        def discord_identity(user_id):
            ign = _player_name(user_id)
            return (
                admin_player_identity_text(guild, user_id, ign)
                or "Discord identity matches IGN"
            )

        super().__init__(
            placeholder="Choose a registered player to add",
            options=_build_options(
                available,
                "No unsigned registered players",
                discord_identity,
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


class AddPlayerSearchResultSelect(discord.ui.Select):
    def __init__(self, guild, user_ids):
        options = []

        for user_id in list(user_ids)[:25]:
            ign = _player_name(user_id)
            options.append(
                discord.SelectOption(
                    label=admin_player_choice_label(guild, user_id, ign),
                    value=str(user_id),
                )
            )

        super().__init__(
            placeholder="Choose the player you meant",
            options=options,
        )

    async def callback(self, interaction):
        if not await _ensure_admin(interaction):
            return

        user_id = int(self.values[0])

        await interaction.response.send_message(
            f"Where should **{_player_name(user_id)}** be added?",
            view=AddPlayerDestinationView(user_id),
            ephemeral=True,
        )


class AddPlayerSearchResultsView(discord.ui.View):
    def __init__(self, guild, user_ids):
        super().__init__(timeout=300)
        self.add_item(AddPlayerSearchResultSelect(guild, user_ids))


class AddPlayerSearchModal(discord.ui.Modal, title="Add Player"):
    player_search = discord.ui.TextInput(
        label="Find player",
        placeholder="IGN, Discord nickname, or username",
        required=True,
        max_length=100,
    )

    async def on_submit(self, interaction):
        if not await _ensure_admin(interaction):
            return

        query = str(self.player_search.value).strip()

        if not query:
            await interaction.response.send_message(
                "Enter an IGN, Discord nickname, or username.",
                ephemeral=True,
            )
            return

        state = get_state(interaction.guild.id)
        excluded_ids = set(state.lobby) | set(state.waiting_room)

        matches = find_registered_player_matches(
            interaction.guild,
            query,
            excluded_ids=excluded_ids,
        )

        if not matches:
            await interaction.response.send_message(
                f"No unsigned registered player matched **{query}**.",
                ephemeral=True,
            )
            return

        exact_matches = [
            user_id
            for user_id in matches
            if _player_matches_admin_value(
                interaction.guild,
                user_id,
                svc.players[user_id],
                query,
            )
        ]

        if len(exact_matches) == 1:
            selected_user_id = exact_matches[0]
        elif len(matches) == 1:
            selected_user_id = matches[0]
        else:
            showing = matches[:25]
            extra_note = ""

            if len(matches) > 25:
                extra_note = (
                    f" Showing the first **25** of **{len(matches)}** matches; "
                    "search more specifically to narrow it down."
                )

            await interaction.response.send_message(
                f"Found **{len(matches)}** matches for **{query}**."
                f"{extra_note}",
                view=AddPlayerSearchResultsView(
                    interaction.guild,
                    showing,
                ),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Where should **{_player_name(selected_user_id)}** be added?",
            view=AddPlayerDestinationView(selected_user_id),
            ephemeral=True,
        )


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


def _search_result_options(guild, user_ids):
    options = []

    for user_id in list(user_ids)[:25]:
        ign = _player_name(user_id)
        options.append(
            discord.SelectOption(
                label=admin_player_choice_label(guild, user_id, ign),
                value=str(user_id),
            )
        )

    return options


def _match_summary(guild, user_ids, limit=10):
    labels = [
        admin_player_choice_label(
            guild,
            user_id,
            _player_name(user_id),
        )
        for user_id in list(user_ids)[:limit]
    ]

    return "\n".join(f"• {label}" for label in labels)


class KickPlayerSearchResultSelect(discord.ui.Select):
    def __init__(self, guild, user_ids):
        super().__init__(
            placeholder="Choose the player to kick",
            options=_search_result_options(guild, user_ids),
        )

    async def callback(self, interaction):
        if not await _ensure_admin(interaction):
            return

        await svc.kick_from_draft(
            interaction,
            int(self.values[0]),
        )


class KickPlayerSearchResultsView(discord.ui.View):
    def __init__(self, guild, user_ids):
        super().__init__(timeout=300)
        self.add_item(KickPlayerSearchResultSelect(guild, user_ids))


class KickPlayerSearchModal(discord.ui.Modal, title="Kick Player"):
    player_search = discord.ui.TextInput(
        label="Find signed player",
        placeholder="IGN, Discord nickname, or username",
        required=True,
        max_length=100,
    )

    async def on_submit(self, interaction):
        if not await _ensure_admin(interaction):
            return

        state = get_state(interaction.guild.id)
        candidate_ids = list(state.lobby) + list(state.waiting_room)
        query = str(self.player_search.value).strip()

        selected_user_id, matches = resolve_player_search(
            interaction.guild,
            query,
            candidate_ids,
        )

        if selected_user_id is not None:
            await svc.kick_from_draft(interaction, selected_user_id)
            return

        if not matches:
            await interaction.response.send_message(
                f"No signed player matched **{query}**.",
                ephemeral=True,
            )
            return

        showing = matches[:25]
        note = ""
        if len(matches) > 25:
            note = (
                f" Showing the first **25** of **{len(matches)}** matches; "
                "search more specifically if needed."
            )

        await interaction.response.send_message(
            f"Found **{len(matches)}** matches for **{query}**.{note}",
            view=KickPlayerSearchResultsView(
                interaction.guild,
                showing,
            ),
            ephemeral=True,
        )


class MovePlayerSearchResultSelect(discord.ui.Select):
    def __init__(self, guild, user_ids):
        super().__init__(
            placeholder="Choose the player to move",
            options=_search_result_options(guild, user_ids),
        )

    async def callback(self, interaction):
        if not await _ensure_admin(interaction):
            return

        success, message = player_management.move_player_to_other_area(
            interaction.guild.id,
            int(self.values[0]),
        )
        await _send_result(interaction, success, message)


class MovePlayerSearchResultsView(discord.ui.View):
    def __init__(self, guild, user_ids):
        super().__init__(timeout=300)
        self.add_item(MovePlayerSearchResultSelect(guild, user_ids))


class MovePlayerSearchModal(discord.ui.Modal, title="Move Player"):
    player_search = discord.ui.TextInput(
        label="Find signed player",
        placeholder="IGN, Discord nickname, or username",
        required=True,
        max_length=100,
    )

    async def on_submit(self, interaction):
        if not await _ensure_admin(interaction):
            return

        state = get_state(interaction.guild.id)
        candidate_ids = list(state.lobby) + list(state.waiting_room)
        query = str(self.player_search.value).strip()

        selected_user_id, matches = resolve_player_search(
            interaction.guild,
            query,
            candidate_ids,
        )

        if selected_user_id is not None:
            success, message = player_management.move_player_to_other_area(
                interaction.guild.id,
                selected_user_id,
            )
            await _send_result(interaction, success, message)
            return

        if not matches:
            await interaction.response.send_message(
                f"No signed player matched **{query}**.",
                ephemeral=True,
            )
            return

        showing = matches[:25]
        note = ""
        if len(matches) > 25:
            note = (
                f" Showing the first **25** of **{len(matches)}** matches; "
                "search more specifically if needed."
            )

        await interaction.response.send_message(
            f"Found **{len(matches)}** matches for **{query}**.{note}",
            view=MovePlayerSearchResultsView(
                interaction.guild,
                showing,
            ),
            ephemeral=True,
        )


class SwapPlayersSearchModal(discord.ui.Modal, title="Swap Players"):
    lobby_player = discord.ui.TextInput(
        label="Lobby player",
        placeholder="IGN, Discord nickname, or username",
        required=True,
        max_length=100,
    )
    waiting_player = discord.ui.TextInput(
        label="Waiting-room player",
        placeholder="IGN, Discord nickname, or username",
        required=True,
        max_length=100,
    )

    async def on_submit(self, interaction):
        if not await _ensure_admin(interaction):
            return

        state = get_state(interaction.guild.id)

        lobby_query = str(self.lobby_player.value).strip()
        waiting_query = str(self.waiting_player.value).strip()

        lobby_user_id, lobby_matches = resolve_player_search(
            interaction.guild,
            lobby_query,
            state.lobby,
        )
        waiting_user_id, waiting_matches = resolve_player_search(
            interaction.guild,
            waiting_query,
            state.waiting_room,
        )

        problems = []

        if lobby_user_id is None:
            if not lobby_matches:
                problems.append(
                    f"No lobby player matched **{lobby_query}**."
                )
            else:
                problems.append(
                    f"Lobby search **{lobby_query}** matched multiple players:\n"
                    f"{_match_summary(interaction.guild, lobby_matches)}"
                )

        if waiting_user_id is None:
            if not waiting_matches:
                problems.append(
                    f"No waiting-room player matched **{waiting_query}**."
                )
            else:
                problems.append(
                    f"Waiting-room search **{waiting_query}** matched multiple players:\n"
                    f"{_match_summary(interaction.guild, waiting_matches)}"
                )

        if problems:
            await interaction.response.send_message(
                "\n\n".join(problems)
                + "\n\nRun **Swap Players** again with a more specific search.",
                ephemeral=True,
            )
            return

        success, message = player_management.swap_players(
            interaction.guild.id,
            lobby_user_id,
            waiting_user_id,
        )
        await _send_result(interaction, success, message)


class QueuePlayerSearchResultSelect(discord.ui.Select):
    def __init__(self, guild, user_ids, position):
        self.position = position

        super().__init__(
            placeholder="Choose the waiting-room player",
            options=_search_result_options(guild, user_ids),
        )

    async def callback(self, interaction):
        if not await _ensure_admin(interaction):
            return

        success, message = player_management.set_queue_position(
            interaction.guild.id,
            int(self.values[0]),
            self.position,
        )
        await _send_result(interaction, success, message)


class QueuePlayerSearchResultsView(discord.ui.View):
    def __init__(self, guild, user_ids, position):
        super().__init__(timeout=300)
        self.add_item(
            QueuePlayerSearchResultSelect(
                guild,
                user_ids,
                position,
            )
        )


class QueuePlayerSearchModal(discord.ui.Modal, title="Set Queue Position"):
    player_search = discord.ui.TextInput(
        label="Find waiting-room player",
        placeholder="IGN, Discord nickname, or username",
        required=True,
        max_length=100,
    )
    position = discord.ui.TextInput(
        label="New queue position",
        placeholder="1",
        required=True,
        max_length=3,
    )

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

        state = get_state(interaction.guild.id)
        query = str(self.player_search.value).strip()

        selected_user_id, matches = resolve_player_search(
            interaction.guild,
            query,
            state.waiting_room,
        )

        if selected_user_id is not None:
            success, message = player_management.set_queue_position(
                interaction.guild.id,
                selected_user_id,
                position,
            )
            await _send_result(interaction, success, message)
            return

        if not matches:
            await interaction.response.send_message(
                f"No waiting-room player matched **{query}**.",
                ephemeral=True,
            )
            return

        showing = matches[:25]
        note = ""
        if len(matches) > 25:
            note = (
                f" Showing the first **25** of **{len(matches)}** matches; "
                "search more specifically if needed."
            )

        await interaction.response.send_message(
            f"Found **{len(matches)}** matches for **{query}**.{note}",
            view=QueuePlayerSearchResultsView(
                interaction.guild,
                showing,
                position,
            ),
            ephemeral=True,
        )


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
