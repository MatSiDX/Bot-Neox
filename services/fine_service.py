import os
from io import BytesIO

import discord

from repositories.fine_repository import FineRepository
from services.config_service import ConfigService


class FineService:
    def __init__(self):
        self.repo = FineRepository()
        self.config_service = ConfigService()

    def get_guild_fines(self, guild_id):
        return self.repo.list_by_guild(guild_id)

    def has_unpaid_fines(self, guild_id, user_id):
        return len(self.repo.list_unpaid_by_user(guild_id, user_id)) > 0

    def get_unpaid_fines(self, guild_id, user_id):
        return self.repo.list_unpaid_by_user(guild_id, user_id)

    def open_fines(self):
        return self.repo.list_open()

    def create_fine_record(self, payload):
        return self.repo.create(payload)

    def get(self, fine_id):
        return self.repo.get(fine_id)

    def update_channels(self, fine_id, **kwargs):
        return self.repo.update_channels(fine_id, **kwargs)

    def mark_paid(self, fine_id, *, paid_by_id, paid_by_name):
        return self.repo.mark_paid(
            fine_id,
            paid_by_id=paid_by_id,
            paid_by_name=paid_by_name,
        )

    def user_still_has_open_fines(self, guild_id, user_id):
        return self.has_unpaid_fines(guild_id, user_id)

    async def ensure_blocked_role(self, guild, member):
        config = self.config_service.get_fine_config(guild.id)
        role_id = int(config.get("blocked_role_id") or 0)
        if not role_id:
            raise ValueError("Configura el rol de multado en el dashboard antes de aprobar informes con multas.")
        role = guild.get_role(role_id)
        if role is None:
            role = await guild.fetch_role(role_id)
        if role not in member.roles:
            await member.add_roles(role, reason="Multa pendiente")
        return role

    async def maybe_remove_blocked_role(self, guild, member):
        if self.user_still_has_open_fines(guild.id, member.id):
            return
        config = self.config_service.get_fine_config(guild.id)
        role_id = int(config.get("blocked_role_id") or 0)
        if not role_id:
            return
        role = guild.get_role(role_id)
        if role and role in member.roles:
            await member.remove_roles(role, reason="Multa pagada")

    async def create_fine_ticket(self, guild, member, fine):
        config = self.config_service.get_fine_config(guild.id)
        resolver_role_id = int(config.get("resolver_role_id") or 0)
        category_id = int(config.get("ticket_category_id") or 0)
        if not resolver_role_id:
            raise ValueError("Configura el rol que puede resolver multas en el dashboard.")

        resolver_role = guild.get_role(resolver_role_id)
        if resolver_role is None:
            resolver_role = await guild.fetch_role(resolver_role_id)

        category = guild.get_channel(category_id) if category_id else None
        if category is None and category_id:
            try:
                category = await guild.fetch_channel(category_id)
            except discord.HTTPException:
                category = None

        channel_name = f"multa-{int(fine['id']):04d}"
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True, manage_messages=True),
            resolver_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Multa {fine['id']} | Usuario: {member} ({member.id})",
                reason=f"Ticket de multa para {member}",
            )
        except discord.HTTPException as exc:
            raise ValueError("No pude crear el ticket de multa. Revisa permisos y configuracion.") from exc
        return channel

    def build_fine_announcement_lines(self, fine, ticket_channel):
        return [
            f"**Persona multada:** <@{int(fine['fined_user_id'])}>",
            f"**Motivo:** {fine['reason']}",
            f"**Monto a pagar:** {int(fine['amount']):,}".replace(",", "."),
            "**Pruebas:**",
            "Adjuntas en este mensaje." if fine.get("proof_path") else "Sin pruebas adjuntas.",
            "",
            f"Puedes apelar tu multa en: {ticket_channel.mention}",
        ]

    async def send_fine_announcement(self, guild, fine, ticket_channel):
        config = self.config_service.get_fine_config(guild.id)
        channel_id = int(config.get("channel_id") or 0)
        if not channel_id:
            raise ValueError("Configura el canal de multas en el dashboard.")

        channel = guild.get_channel(channel_id)
        if channel is None:
            channel = await guild.fetch_channel(channel_id)

        file = None
        proof_path = str(fine.get("proof_path") or "")
        if proof_path and os.path.isfile(proof_path):
            with open(proof_path, "rb") as f:
                file = discord.File(BytesIO(f.read()), filename=str(fine.get("proof_name") or os.path.basename(proof_path)))

        try:
            message = await channel.send(
                "\n".join(self.build_fine_announcement_lines(fine, ticket_channel)),
                file=file,
            )
        except discord.HTTPException as exc:
            raise ValueError("No pude enviar la multa al canal configurado.") from exc
        return channel, message
