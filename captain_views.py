import discord

from config import normalize_roles

class CaptainPickSelect(discord.ui.Select):
    def __init__(self, ctx):
        self.ctx = ctx
        options = []
        captain_draft = ctx.get_captain_draft()

        if captain_draft:
            for user_id in captain_draft.available:
                p = ctx.players[user_id]
                roles = ", ".join(normalize_roles(p["roles"]))

                options.append(
                    discord.SelectOption(
                        label=p["ign"][:100],
                        description=roles[:100],
                        value=str(user_id)
                    )
                )

        if not options:
            options.append(
                discord.SelectOption(
                    label="No players available",
                    value="none"
                )
            )

        super().__init__(
            placeholder="Pick a player",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("No players available.", ephemeral=True)
            return

        await self.ctx.handle_captain_pick(interaction, int(self.values[0]))

class CaptainPickView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.add_item(CaptainPickSelect(ctx))
