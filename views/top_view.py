import discord


class TopView(discord.ui.View):
    def __init__(self, embeds, owner_id):
        super().__init__(timeout=None)
        self.embeds = embeds
        self.owner_id = owner_id
        self.current_page = 0
        self.sync_buttons()

    def sync_buttons(self):
        self.prev.disabled = self.current_page == 0
        self.next.disabled = self.current_page >= len(self.embeds) - 1
        self.prev.style = discord.ButtonStyle.secondary
        self.next.style = discord.ButtonStyle.primary

    async def update(self, interaction):
        self.sync_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Solo quien ejecuto el comando puede usar esta paginacion.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Previous Page")
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
        await self.update(interaction)

    @discord.ui.button(label="Next Page")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
        await self.update(interaction)
