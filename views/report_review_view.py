from datetime import datetime

import discord


class RejectReportModal(discord.ui.Modal, title="Rechazar informe"):
    reason = discord.ui.TextInput(
        label="Motivo del rechazo",
        style=discord.TextStyle.paragraph,
        min_length=3,
        max_length=500,
    )

    def __init__(self, review_view):
        super().__init__()
        self.review_view = review_view

    async def on_submit(self, interaction: discord.Interaction):
        await self.review_view.reject(interaction, str(self.reason.value))


class ApprovedReportBalanceView(discord.ui.View):
    def __init__(
        self,
        *,
        report_data,
        permission_service,
        balance_service,
        report_thread=None,
        runtime_service=None,
        guild_id=0,
        message_id=0,
        channel_id=0,
        thread_id=0,
    ):
        super().__init__(timeout=None)
        self.report_data = report_data
        self.permission_service = permission_service
        self.balance_service = balance_service
        self.report_thread = report_thread
        self.runtime_service = runtime_service
        self.guild_id = int(guild_id or 0)
        self.message_id = int(message_id or 0)
        self.channel_id = int(channel_id or 0)
        self.thread_id = int(thread_id or 0)
        self.resolved = False

    async def interaction_check(self, interaction):
        if self.permission_service.can_review_reports(interaction.guild.id, interaction.user):
            return True

        await interaction.response.send_message(
            "No tienes permisos para revisar informes.",
            ephemeral=True,
        )
        return False

    async def disable_after_balance_decision(self, interaction, status_text):
        self.resolved = True
        for item in self.children:
            item.disabled = True

        await interaction.message.edit(
            content=f"{interaction.message.content}\n\n**Estado:** {status_text}",
            view=self,
        )
        if self.runtime_service and self.message_id:
            self.runtime_service.remove_balance_decision(self.message_id)

    def to_runtime_state(self):
        return {
            "guild_id": self.guild_id,
            "message_id": self.message_id,
            "channel_id": self.channel_id,
            "thread_id": self.thread_id,
            "report_data": self.report_data,
        }

    def format_full_amount(self, amount):
        return f"{int(amount):,}".replace(",", ".")

    async def apply_distribution(self, interaction):
        available_silver = int(self.report_data.get("available_silver", 0) or 0)
        pp_required = int(self.report_data.get("pp_required", 0) or 0)
        if pp_required > available_silver:
            raise ValueError("El informe requiere mas silver del disponible para cubrir los PP.")

        summary_lines = []
        for entry in self.report_data.get("distribution", []):
            user_id = entry["user_id"]
            amount = int(entry["amount"])
            category = entry["category"]
            note = entry.get("note", "")
            slot_name = entry["slot"]

            previous_items, previous_silver = self.balance_service.get_balance(interaction.guild, user_id)
            previous_balance = previous_silver if category == "silver" else previous_items
            self.balance_service.modify(interaction.guild, user_id, amount, category, True)
            new_balance = previous_balance + amount
            member = interaction.guild.get_member(user_id)
            player_name = member.display_name if member else f"Usuario {user_id}"
            reviewer_name = interaction.user.display_name
            self.balance_service.log_operation(
                interaction.guild,
                {
                    "action": "/approve-report",
                    "operator": reviewer_name,
                    "operator_id": str(interaction.user.id),
                    "player": player_name,
                    "player_id": str(user_id),
                    "type": "ADD",
                    "category": "Silver" if category == "silver" else "Items",
                    "amount": amount,
                    "previous_balance": previous_balance,
                    "new_balance": new_balance,
                    "date": datetime.now().strftime("%d/%m/%Y"),
                    "time": datetime.now().strftime("%H:%M"),
                },
            )

            suffix = f" {note}" if note else ""
            summary_lines.append(
                f"- {slot_name}: <@{user_id}> -> +{self.format_full_amount(amount)} [{'Silver' if category == 'silver' else 'Items'}]{suffix}"
            )

        return summary_lines

    @discord.ui.button(
        label="Agregar balance",
        style=discord.ButtonStyle.success,
        custom_id="report_balance:add",
    )
    async def add_balance_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.resolved:
            await interaction.response.send_message("El balance de este informe ya fue decidido.", ephemeral=True)
            return

        try:
            summary_lines = await self.apply_distribution(interaction)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        if self.report_thread:
            summary_text = "\n".join(summary_lines) if summary_lines else "No habia participantes para aplicar balance."
            base_lines = []
            if int(self.report_data.get("item_per_user", 0) or 0):
                base_lines.append(
                    f"Items C/U: {self.format_full_amount(self.report_data['item_per_user'])}"
                )
            if int(self.report_data.get("silver_per_user", 0) or 0):
                base_lines.append(
                    f"Silver C/U: {self.format_full_amount(self.report_data['silver_per_user'])}"
                )
            if not base_lines:
                base_lines.append(
                    f"C/U base: {self.format_full_amount(self.report_data.get('per_user', 0))}"
                )
            await self.report_thread.send(
                "**Balance aplicado automaticamente**\n"
                f"Modo: {self.report_data.get('split_label', 'Reparto anterior')}\n"
                + "\n".join(base_lines)
                + "\n\n"
                + summary_text
            )

        await self.disable_after_balance_decision(interaction, f"Balance agregado por {interaction.user.mention}")
        await interaction.response.send_message("Balance agregado.", ephemeral=True)

    @discord.ui.button(
        label="No agregar balance",
        style=discord.ButtonStyle.secondary,
        custom_id="report_balance:skip",
    )
    async def skip_balance_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.resolved:
            await interaction.response.send_message("El balance de este informe ya fue decidido.", ephemeral=True)
            return

        if self.report_thread:
            await self.report_thread.send(
                "**Balance no aplicado**\n"
                "El informe fue aprobado sin modificar balances."
            )

        await self.disable_after_balance_decision(interaction, f"Balance no agregado por {interaction.user.mention}")
        await interaction.response.send_message("Informe publicado sin agregar balance.", ephemeral=True)


class ReportReviewView(discord.ui.View):
    def __init__(
        self,
        *,
        report_data,
        approved_channel_id,
        report_service,
        permission_service,
        balance_service,
        fine_service=None,
        register_fine_ticket_view=None,
        source_view=None,
        source_view_resolver=None,
        runtime_service=None,
        guild_id=0,
        message_id=0,
    ):
        super().__init__(timeout=None)
        self.report_data = report_data
        self.approved_channel_id = approved_channel_id
        self.report_service = report_service
        self.permission_service = permission_service
        self.balance_service = balance_service
        self.fine_service = fine_service
        self.register_fine_ticket_view = register_fine_ticket_view
        self.source_view = source_view
        self.source_view_resolver = source_view_resolver
        self.runtime_service = runtime_service
        self.guild_id = int(guild_id or 0)
        self.message_id = int(message_id or 0)
        self.reviewed = False

    async def interaction_check(self, interaction):
        if self.permission_service.can_review_reports(interaction.guild.id, interaction.user):
            return True

        await interaction.response.send_message(
            "No tienes permisos para revisar informes.",
            ephemeral=True,
        )
        return False

    def log_decision(self, interaction, decision, reason="-"):
        now = datetime.now()
        self.report_service.log_review(
            interaction.guild.id,
            {
                "ava": self.report_data["ava"],
                "caller": self.report_data["caller"],
                "caller_id": str(self.report_data["caller_id"]),
                "reviewer": interaction.user.display_name,
                "reviewer_id": str(interaction.user.id),
                "decision": decision,
                "reason": reason or "-",
                "date": now.strftime("%d/%m/%Y"),
                "time": now.strftime("%H:%M"),
            },
        )

    async def get_approved_channel(self, interaction):
        if not self.approved_channel_id:
            return None

        channel = interaction.client.get_channel(self.approved_channel_id)
        if channel:
            return channel

        try:
            return await interaction.client.fetch_channel(self.approved_channel_id)
        except discord.HTTPException:
            return None

    async def disable_after_review(self, interaction, status_text):
        self.reviewed = True
        for item in self.children:
            item.disabled = True

        await interaction.message.edit(
            content=f"{interaction.message.content}\n\n**Estado:** {status_text}",
            view=self,
        )
        if self.runtime_service and self.message_id:
            self.runtime_service.remove_review(self.message_id)

    def resolve_source_view(self):
        if self.source_view is not None:
            return self.source_view
        if self.source_view_resolver is None:
            return None

        return self.source_view_resolver(
            guild_id=self.guild_id,
            caller_id=int(self.report_data.get("caller_id", 0) or 0),
            numero_ava=int(self.report_data.get("ava", 0) or 0),
        )

    def to_runtime_state(self):
        message = getattr(self, "message", None)
        channel = getattr(message, "channel", None)
        return {
            "guild_id": self.guild_id,
            "message_id": self.message_id,
            "channel_id": int(getattr(channel, "id", 0) or 0),
            "approved_channel_id": self.approved_channel_id,
            "report_data": self.report_data,
        }

    def format_full_amount(self, amount):
        return f"{int(amount):,}".replace(",", ".")

    async def create_approved_thread(self, approved_message):
        try:
            return await approved_message.create_thread(name=f"Ava {self.report_data['ava']}")
        except discord.HTTPException:
            return None

    async def apply_fines(self, interaction):
        fines = self.report_data.get("fines", [])
        if not fines:
            return []
        if self.fine_service is None:
            raise ValueError("El sistema de multas no esta disponible.")

        created_lines = []
        guild = interaction.guild
        for fine in fines:
            member = guild.get_member(int(fine.get("user_id", 0) or 0))
            if member is None:
                try:
                    member = await guild.fetch_member(int(fine.get("user_id", 0) or 0))
                except discord.HTTPException as exc:
                    raise ValueError(f"No encontre al usuario multado {fine.get('user_name') or fine.get('user_id')}.") from exc

            blocked_role = await self.fine_service.ensure_blocked_role(guild, member)
            created = self.fine_service.create_fine_record(
                {
                    "guild_id": guild.id,
                    "guild_name": guild.name,
                    "report_ava": self.report_data.get("ava", ""),
                    "fined_user_id": member.id,
                    "fined_user_name": member.display_name,
                    "amount": int(fine.get("amount") or 0),
                    "reason": fine.get("reason", ""),
                    "proof_path": fine.get("proof_path", ""),
                    "proof_name": fine.get("proof_name", ""),
                    "blocked_role_id": blocked_role.id,
                    "resolver_role_id": self.fine_service.config_service.get_fine_config(guild.id).get("resolver_role_id", 0),
                    "created_by_id": interaction.user.id,
                    "created_by_name": interaction.user.display_name,
                    "status": "open",
                }
            )
            ticket_channel = await self.fine_service.create_fine_ticket(guild, member, created)
            from views.fine_ticket_view import FineTicketView

            fine_view = FineTicketView(fine_id=created["id"], fine_service=self.fine_service)
            ticket_message = await ticket_channel.send(
                (
                    f"**Multa pendiente**\n"
                    f"Usuario: {member.mention}\n"
                    f"Monto: {self.format_full_amount(created['amount'])}\n"
                    f"Motivo: {created['reason']}\n\n"
                    "Solo el rol autorizado puede marcar esta multa como pagada."
                ),
                view=fine_view,
            )
            if self.register_fine_ticket_view is not None:
                self.register_fine_ticket_view(fine_view, ticket_message.id)
            announcement_channel, announcement_message = await self.fine_service.send_fine_announcement(
                guild,
                created,
                ticket_channel,
            )
            self.fine_service.update_channels(
                created["id"],
                ticket_channel_id=ticket_channel.id,
                ticket_message_id=ticket_message.id,
                announcement_channel_id=announcement_channel.id,
                announcement_message_id=announcement_message.id,
            )
            created_lines.append(
                f"- {member.mention}: {self.format_full_amount(created['amount'])} ({created['reason']})"
            )
        return created_lines

    @discord.ui.button(
        label="Aceptar",
        style=discord.ButtonStyle.success,
        custom_id="report_review:approve",
    )
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.reviewed:
            await interaction.response.send_message("Este informe ya fue revisado.", ephemeral=True)
            return

        channel = await self.get_approved_channel(interaction)
        if not channel:
            await interaction.response.send_message(
                "No hay canal de informes aprobados configurado.",
                ephemeral=True,
            )
            return

        try:
            fine_lines = await self.apply_fines(interaction)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        approved_message = await channel.send(self.report_data["content"])
        thread = await self.create_approved_thread(approved_message)
        balance_view = ApprovedReportBalanceView(
            report_data=self.report_data,
            permission_service=self.permission_service,
            balance_service=self.balance_service,
            report_thread=thread,
            runtime_service=self.runtime_service,
            guild_id=interaction.guild.id,
            message_id=approved_message.id,
            channel_id=approved_message.channel.id,
            thread_id=getattr(thread, "id", 0),
        )
        await approved_message.edit(view=balance_view)
        if self.runtime_service:
            self.runtime_service.save_balance_decision(balance_view.to_runtime_state())

        if thread:
            await thread.send("Informe aprobado. Elige en el mensaje aprobado si se agregara balance.")
            if fine_lines:
                await thread.send("**Multas generadas**\n" + "\n".join(fine_lines))

        self.log_decision(interaction, "Aceptado")
        await self.disable_after_review(interaction, f"Aceptado por {interaction.user.mention}")
        await interaction.response.send_message("Informe aceptado y publicado. Ahora puedes decidir el balance en el canal aprobado.", ephemeral=True)

    @discord.ui.button(
        label="Rechazar",
        style=discord.ButtonStyle.danger,
        custom_id="report_review:reject",
    )
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.reviewed:
            await interaction.response.send_message("Este informe ya fue revisado.", ephemeral=True)
            return

        await interaction.response.send_modal(RejectReportModal(self))

    async def reject(self, interaction, reason):
        self.log_decision(interaction, "Rechazado", reason)
        source_view = self.resolve_source_view()
        if source_view is not None:
            await source_view.mark_report_rejected()
        await self.disable_after_review(interaction, f"Rechazado por {interaction.user.mention}\n**Motivo:** {reason}")
        await interaction.response.send_message("Informe rechazado y registrado.", ephemeral=True)
