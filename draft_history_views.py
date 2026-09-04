import discord

from draft_history_service import (
    HISTORY_PAGE_SIZE,
    build_draft_detail_embed,
    build_history_embed,
    format_mode,
    get_history_page,
)


class DraftHistorySelect(discord.ui.Select):
    def __init__(self, history_view):
        self.history_view = history_view
        super().__init__(
            placeholder="Select a draft to inspect",
            min_values=1,
            max_values=1,
            options=self._build_options(),
            row=0,
        )

    def _build_options(self):
        options = []
        for draft in self.history_view.page_data["drafts"]:
            draft_id = draft["draft_id"]
            created_at = int(draft["created_at"])
            options.append(
                discord.SelectOption(
                    label=f"#{draft_id} — {format_mode(draft['mode'])}"[:100],
                    description=f"Discord timestamp: {created_at}"[:100],
                    value=str(draft_id),
                    default=draft_id == self.history_view.selected_draft_id,
                )
            )
        return options

    def refresh_options(self):
        self.options = self._build_options()

    async def callback(self, interaction: discord.Interaction):
        self.history_view.selected_draft_id = int(self.values[0])
        self.refresh_options()
        await interaction.response.edit_message(
            embed=self.history_view.build_embed(),
            view=self.history_view,
        )


class DraftHistoryView(discord.ui.View):
    def __init__(self, guild_id, page=0, page_size=HISTORY_PAGE_SIZE, selected_draft_id=None):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.page_size = page_size
        self.page_data = get_history_page(guild_id, page, page_size)

        draft_ids = [draft["draft_id"] for draft in self.page_data["drafts"]]
        if selected_draft_id in draft_ids:
            self.selected_draft_id = selected_draft_id
        else:
            self.selected_draft_id = draft_ids[0] if draft_ids else None

        self.selector = None
        if self.page_data["drafts"]:
            self.selector = DraftHistorySelect(self)
            self.add_item(self.selector)

        self._sync_buttons()

    def _sync_buttons(self):
        self.previous_button.disabled = self.page_data["page"] <= 0
        self.next_button.disabled = self.page_data["page"] >= self.page_data["total_pages"] - 1
        self.view_draft_button.disabled = self.selected_draft_id is None

    def _load_page(self, page):
        self.page_data = get_history_page(self.guild_id, page, self.page_size)
        draft_ids = [draft["draft_id"] for draft in self.page_data["drafts"]]
        self.selected_draft_id = draft_ids[0] if draft_ids else None

        if self.selector:
            self.selector.refresh_options()

        self._sync_buttons()

    def build_embed(self):
        return build_history_embed(self.page_data, self.selected_draft_id)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, row=1)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._load_page(self.page_data["page"] - 1)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="View Draft", style=discord.ButtonStyle.primary, row=1)
    async def view_draft_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.selected_draft_id is None:
            await interaction.response.send_message("No draft is selected.", ephemeral=True)
            return

        embed = build_draft_detail_embed(self.guild_id, self.selected_draft_id)
        if embed is None:
            await interaction.response.send_message(
                "That draft could not be found.",
                ephemeral=True,
            )
            return

        detail_view = DraftDetailView(
            guild_id=self.guild_id,
            page=self.page_data["page"],
            page_size=self.page_size,
            selected_draft_id=self.selected_draft_id,
        )
        await interaction.response.edit_message(embed=embed, view=detail_view)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._load_page(self.page_data["page"] + 1)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class DraftDetailView(discord.ui.View):
    def __init__(self, guild_id, page, page_size, selected_draft_id):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.page = page
        self.page_size = page_size
        self.selected_draft_id = selected_draft_id

    @discord.ui.button(label="Back to History", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        history_view = DraftHistoryView(
            guild_id=self.guild_id,
            page=self.page,
            page_size=self.page_size,
            selected_draft_id=self.selected_draft_id,
        )
        await interaction.response.edit_message(
            embed=history_view.build_embed(),
            view=history_view,
        )
