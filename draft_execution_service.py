import random

import discord

from database import (
    get_guild_player_weights,
    save_completed_draft,
)
from draft_logic import (
    CaptainDraft,
    generate_random_teams,
    optimize_team_roles,
)
from state import get_state
from service_runtime import players
from lobby_state_service import load_lobby_state
from board_service import player_label, post_new_draft_board, team_text
from notification_service import notify_drafted_players


def _finalize_captain_draft(guild_id, state):
    captain_draft = state.captain_draft

    # The existing role optimizer is specifically an 8-player team solver.
    # Preserve it for normal 8v8 captain drafts and leave smaller captain
    # teams in the roles selected/displayed during the pick process.
    if len(captain_draft.team_a) == 8:
        captain_draft.team_a = optimize_team_roles(players, captain_draft.team_a)
    if len(captain_draft.team_b) == 8:
        captain_draft.team_b = optimize_team_roles(players, captain_draft.team_b)

    state.final_team_a = captain_draft.team_a
    state.final_team_b = captain_draft.team_b

    save_completed_draft(
        guild_id=guild_id,
        mode="captain",
        team_a=state.final_team_a,
        team_b=state.final_team_b,
        players=players,
        captain_a=captain_draft.captain_a,
        captain_b=captain_draft.captain_b
    )

    state.draft_result = (
        "**Mode:** Captain Draft\n\n"
        "### Team A\n"
        f"{team_text(guild_id, state.final_team_a)}\n\n"
        "### Team B\n"
        f"{team_text(guild_id, state.final_team_b)}"
    )

    # Completed boards render from final_team_a/final_team_b, so clear the
    # active draft before the board refresh.
    state.captain_draft = None


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
        _finalize_captain_draft(guild_id, state)

        await interaction.response.defer()
        await post_new_draft_board(guild_id)

        dm_failed = await notify_drafted_players(
            interaction,
            state.final_team_a,
            state.final_team_b
        )

        if dm_failed:
            await interaction.channel.send(
                "Could not DM:\n" + "\n".join(dm_failed)
            )

        return

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

    # A two-player captain lobby has no picks to make; the captains are the
    # complete teams immediately.
    if state.captain_draft.is_complete():
        _finalize_captain_draft(guild_id, state)

        await interaction.response.send_message(
            "Captain draft complete. Each captain is their team's player.",
            ephemeral=True
        )
        await post_new_draft_board(guild_id)

        dm_failed = await notify_drafted_players(
            interaction,
            state.final_team_a,
            state.final_team_b
        )

        if dm_failed:
            await interaction.channel.send(
                "Could not DM:\n" + "\n".join(dm_failed)
            )
        return

    await interaction.response.send_message(
        f"Captain draft started. First pick: {player_label(guild_id, state.captain_draft.current_picker())}. "
        f"Captains should use `/pickpanel` when it is their turn.",
        ephemeral=True
    )

    await post_new_draft_board(guild_id)


async def run_startdraft(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    state = get_state(guild_id)

    load_lobby_state(guild_id)
    required_players = state.lobby_size

    if len(state.lobby) != required_players:
        await interaction.response.send_message(
            f"Need exactly {required_players} players to start. "
            f"Current lobby: {len(state.lobby)}/{required_players}",
            ephemeral=True
        )
        return

    captain_votes = list(state.votes.values()).count("captain")
    random_votes = list(state.votes.values()).count("random")

    if captain_votes > random_votes:
        await start_captain_draft(interaction)
        return

    # The normal 16-player optimizer can take longer than Discord's initial
    # interaction-response window. Deferring is also harmless for small drafts.
    await interaction.response.defer(ephemeral=True)

    player_weights = get_guild_player_weights(guild_id)

    try:
        team_a, team_b, formation = generate_random_teams(
            players,
            state.lobby,
            player_weights,
        )
    except ValueError as error:
        await interaction.followup.send(str(error), ephemeral=True)
        return

    state.final_team_a = team_a
    state.final_team_b = team_b

    if formation.get("uses_full_optimizer"):
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
    else:
        # Reduced-size drafts are intentionally random after the requested monk
        # seeding, so do not imply that hidden-weight optimization was applied.
        state.last_balance_debug = None

    save_completed_draft(
        guild_id=guild_id,
        mode="random",
        team_a=team_a,
        team_b=team_b,
        players=players,
        balance_score=formation.get("score")
    )

    if formation.get("uses_full_optimizer"):
        state.draft_result = (
            "**Mode:** Random Draft\n\n"
            f"**Team A Comp:** {formation['team_a']}\n"
            f"**Team B Comp:** {formation['team_b']}\n"
            f"**Balancing Score:** {formation['score']} lower is better\n\n"
            "### Team A\n"
            f"{team_text(guild_id, team_a)}\n\n"
            "### Team B\n"
            f"{team_text(guild_id, team_b)}"
        )
    else:
        state.draft_result = (
            "**Mode:** Random Draft\n\n"
            f"**Draft Logic:** {formation['team_a']}\n\n"
            "### Team A\n"
            f"{team_text(guild_id, team_a)}\n\n"
            "### Team B\n"
            f"{team_text(guild_id, team_b)}"
        )

    # Publish the completed draft board before sending assignment DMs.
    await post_new_draft_board(guild_id)

    dm_failed = await notify_drafted_players(interaction, team_a, team_b)

    msg = "Draft started."

    if dm_failed:
        msg += "\n\nCould not DM:\n" + "\n".join(dm_failed)

    await interaction.followup.send(msg, ephemeral=True)
