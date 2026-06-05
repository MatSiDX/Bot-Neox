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
    ):
        super().__init__(timeout=None)
        self.report_data = report_data
        self.permission_service = permission_service
        self.balance_service = balance_service
        self.report_thread = report_thread
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

    def format_full_amount(self, amount):
        return f"{int(amount):,}".replace(",", ".")

    async def apply_distribution(self, interaction):
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

    @discord.ui.button(label="Agregar balance", style=discord.ButtonStyle.success)
    async def add_balance_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.resolved:
            await interaction.response.send_message("El balance de este informe ya fue decidido.", ephemeral=True)
            return

        summary_lines = await self.apply_distribution(interaction)
        if self.report_thread:
            summary_text = "\n".join(summary_lines) if summary_lines else "No habia participantes para aplicar balance."
            await self.report_thread.send(
                "**Balance aplicado automaticamente**\n"
                f"C/U base: {self.format_full_amount(self.report_data.get('per_user', 0))}\n\n"
                + summary_text
            )

        await self.disable_after_balance_decision(interaction, f"Balance agregado por {interaction.user.mention}")
        await interaction.response.send_message("Balance agregado.", ephemeral=True)

    @discord.ui.button(label="No agregar balance", style=discord.ButtonStyle.secondary)
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
        source_view=None,
    ):
        super().__init__(timeout=None)
        self.report_data = report_data
        self.approved_channel_id = approved_channel_id
        self.report_service = report_service
        self.permission_service = permission_service
        self.balance_service = balance_service
        self.source_view = source_view
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

    def format_full_amount(self, amount):
        return f"{int(amount):,}".replace(",", ".")

    async def create_approved_thread(self, approved_message):
        try:
            return await approved_message.create_thread(name=f"Ava {self.report_data['ava']}")
        except discord.HTTPException:
            return None

    @discord.ui.button(label="Aceptar", style=discord.ButtonStyle.success)
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

        approved_message = await channel.send(self.report_data["content"])
        thread = await self.create_approved_thread(approved_message)
        balance_view = ApprovedReportBalanceView(
            report_data=self.report_data,
            permission_service=self.permission_service,
            balance_service=self.balance_service,
            report_thread=thread,
        )
        await approved_message.edit(view=balance_view)

        if thread:
            await thread.send("Informe aprobado. Elige en el mensaje aprobado si se agregara balance.")

        self.log_decision(interaction, "Aceptado")
        await self.disable_after_review(interaction, f"Aceptado por {interaction.user.mention}")
        await interaction.response.send_message("Informe aceptado y publicado. Ahora puedes decidir el balance en el canal aprobado.", ephemeral=True)

    @discord.ui.button(label="Rechazar", style=discord.ButtonStyle.danger)
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.reviewed:
            await interaction.response.send_message("Este informe ya fue revisado.", ephemeral=True)
            return

        await interaction.response.send_modal(RejectReportModal(self))

    async def reject(self, interaction, reason):
        self.log_decision(interaction, "Rechazado", reason)
        if self.source_view is not None:
            await self.source_view.mark_report_rejected()
        await self.disable_after_review(interaction, f"Rechazado por {interaction.user.mention}\n**Motivo:** {reason}")
        await interaction.response.send_message("Informe rechazado y registrado.", ephemeral=True)
