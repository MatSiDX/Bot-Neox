import discord


class FineTicketView(discord.ui.View):
    def __init__(self, *, fine_id, fine_service):
        super().__init__(timeout=None)
        self.fine_id = int(fine_id)
        self.fine_service = fine_service
        self.mark_paid_button.custom_id = f"fine_ticket:paid:{self.fine_id}"

    async def interaction_check(self, interaction):
        fine = self.fine_service.get(self.fine_id)
        if not fine or fine.get("status") != "open":
            await interaction.response.send_message("Esta multa ya no esta pendiente.", ephemeral=True)
            return False

        if interaction.user.guild_permissions.administrator:
            return True

        resolver_role_id = int(fine.get("resolver_role_id") or 0)
        if any(role.id == resolver_role_id for role in interaction.user.roles):
            return True

        await interaction.response.send_message("No tienes permisos para resolver esta multa.", ephemeral=True)
        return False

    async def close_ticket_channel(self, interaction, member):
        channel = interaction.channel
        guild = interaction.guild
        resolver_role_id = int(self.fine_service.get(self.fine_id).get("resolver_role_id") or 0)
        resolver_role = guild.get_role(resolver_role_id) if resolver_role_id else None
        await channel.set_permissions(guild.default_role, view_channel=False)
        await channel.set_permissions(member, view_channel=False, send_messages=False, read_message_history=False, attach_files=False, embed_links=False)
        if resolver_role is not None:
            await channel.set_permissions(resolver_role, view_channel=True, send_messages=False, read_message_history=True)
        await channel.set_permissions(guild.me, view_channel=True, send_messages=True, read_message_history=True, manage_channels=True, manage_messages=True)

    @discord.ui.button(label="Marcar multa pagada", style=discord.ButtonStyle.success, custom_id="fine_ticket:paid")
    async def mark_paid_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        fine = self.fine_service.get(self.fine_id)
        if not fine:
            await interaction.response.send_message("No encontre esta multa.", ephemeral=True)
            return

        member = interaction.guild.get_member(int(fine.get("fined_user_id") or 0))
        if member is None:
            try:
                member = await interaction.guild.fetch_member(int(fine.get("fined_user_id") or 0))
            except discord.HTTPException:
                member = None

        self.fine_service.mark_paid(
            self.fine_id,
            paid_by_id=interaction.user.id,
            paid_by_name=interaction.user.display_name,
        )
        if member is not None:
            await self.fine_service.maybe_remove_blocked_role(interaction.guild, member)

        try:
            if member is not None:
                await self.close_ticket_channel(interaction, member)
        except discord.HTTPException:
            await interaction.response.send_message(
                "Marque la multa como pagada, pero no pude cerrar el ticket correctamente.",
                ephemeral=True,
            )
            return

        for item in self.children:
            item.disabled = True

        await interaction.message.edit(view=self)
        await interaction.channel.send(f"Multa pagada y ticket cerrado por {interaction.user.mention}.")
        await interaction.response.send_message("La multa fue marcada como pagada.", ephemeral=True)
