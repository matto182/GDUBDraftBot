from datetime import datetime, timezone

import discord

import player_inspector_service as inspector_service


def _discord_timestamp(timestamp, style="R"):
    if not timestamp:
        return "Never"
    return f"<t:{int(timestamp)}:{style}>"


def _role_history_text(snapshot):
    history = snapshot.get("role_history", [])
    if not history:
        return "No draft history."

    return "\n".join(
        f"**{entry['role']}** — {entry['count']}"
        for entry in history[:8]
    )


def _recent_activity_text(snapshot):
    drafts = snapshot.get("recent_drafts", [])
    if not drafts:
        return "No completed drafts recorded."

    lines = []
    for draft in drafts:
        captain = " • Captain" if draft["was_captain"] else ""
        balance = (
            f" • Balance {draft['balance_score']}"
            if draft["balance_score"] is not None
            else ""
        )
        lines.append(
            f"**#{draft['draft_id']}** • {draft['mode']} • Team {draft['team']} "
            f"• {draft['assigned_role']}{captain}{balance} "
            f"• {_discord_timestamp(draft['created_at'])}"
        )

    return "\n".join(lines)


def build_player_inspector_embed(snapshot):
    roles = ", ".join(snapshot["roles"]) if snapshot["roles"] else "None"
    aliases = snapshot.get("aliases", [])
    aliases_text = ", ".join(aliases) if aliases else "None"
    weight = snapshot["hidden_weight"]
    weight_text = f"{weight:+d}" if isinstance(weight, int) else str(weight)

    embed = discord.Embed(
        title=f"Player Inspector — {snapshot['ign']}",
        description=f"<@{snapshot['user_id']}> • `{snapshot['user_id']}`",
    )

    embed.add_field(
        name="Registration",
        value=(
            f"**Discord:** {snapshot['discord_name']}\n"
            f"**Previous IGNs:** {aliases_text}\n"
            f"**Roles:** {roles}\n"
            f"**Backline history:** "
            f"{'Yes' if snapshot['has_played_backline'] else 'No'}"
        ),
        inline=False,
    )

    embed.add_field(
        name="Admin / Balance",
        value=(
            f"**Hidden weight:** {weight_text}\n"
            f"**Lobby timeout:** {snapshot['timeout_summary']}"
        ),
        inline=False,
    )

    embed.add_field(
        name="Draft Stats",
        value=(
            f"**Drafts played:** {snapshot['drafts_played']}\n"
            f"**Captain:** {snapshot['times_captain']} "
            f"({snapshot['captain_rate']}%)\n"
            f"**Primary preference:** {snapshot['primary_assignments']} "
            f"({snapshot['primary_hit_rate']}%)\n"
            f"**Off-role:** {snapshot['off_role_assignments']} "
            f"({snapshot['off_role_rate']}%)\n"
            f"**Last draft:** {_discord_timestamp(snapshot['last_draft_at'])}"
        ),
        inline=False,
    )

    embed.add_field(
        name="Assigned Role History",
        value=_role_history_text(snapshot),
        inline=False,
    )

    embed.add_field(
        name="Recent Draft Activity",
        value=_recent_activity_text(snapshot),
        inline=False,
    )

    embed.set_footer(text="Admin-only player information")
    return embed


class PlayerInspectorView(discord.ui.View):
    def __init__(self, guild_id, user_id, is_admin_check):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.user_id = user_id
        self.is_admin_check = is_admin_check

    async def _ensure_admin(self, interaction):
        if self.is_admin_check(interaction):
            return True

        await interaction.response.send_message(
            "Only draft admins can use the player inspector.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary)
    async def refresh_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if not await self._ensure_admin(interaction):
            return

        snapshot = inspector_service.build_player_snapshot(
            self.guild_id,
            self.user_id,
        )
        if not snapshot:
            await interaction.response.send_message(
                "That player is no longer registered.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            embed=build_player_inspector_embed(snapshot),
            view=self,
        )

    @discord.ui.button(
        label="Recent Activity",
        style=discord.ButtonStyle.primary,
    )
    async def recent_activity_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if not await self._ensure_admin(interaction):
            return

        snapshot = inspector_service.build_player_snapshot(
            self.guild_id,
            self.user_id,
        )
        if not snapshot:
            await interaction.response.send_message(
                "That player is no longer registered.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            _recent_activity_text(snapshot),
            ephemeral=True,
        )
