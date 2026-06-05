import asyncio
import json
import os
from datetime import datetime, timezone

import discord
from discord.ext import commands

from repositories.balance_repository import DATA_DIR

AUDIT_CONFIG_FILE = os.path.join(DATA_DIR, "audit_config.json")
AUDIT_EVENTS_FILE = os.path.join(DATA_DIR, "audit_events.json")


class AuditCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def load_config(self):
        if not os.path.isfile(AUDIT_CONFIG_FILE):
            return {}

        try:
            with open(AUDIT_CONFIG_FILE, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def get_channel_id(self, guild_id, category):
        data = self.load_config()
        guild_config = data.get(str(guild_id), {})
        channels = guild_config.get("channels", {}) if isinstance(guild_config, dict) else {}
        value = channels.get(category)
        return int(value) if value else 0

    def append_event(self, guild_id, category, title, description):
        data = {}
        if os.path.isfile(AUDIT_EVENTS_FILE):
            try:
                with open(AUDIT_EVENTS_FILE, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                data = {}

        events = data.setdefault(str(guild_id), [])
        events.append({
            "category": category,
            "title": title,
            "description": description,
            "created_at": datetime.now().strftime("%d/%m/%Y | %H:%M"),
        })
        data[str(guild_id)] = events[-1000:]
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(AUDIT_EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    async def send_audit(self, guild, category, title, description, *, color=discord.Color.blurple()):
        self.append_event(guild.id, category, title, description)
        channel_id = self.get_channel_id(guild.id, category)
        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException:
                return

        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text=datetime.now().strftime("%d/%m/%Y | %H:%M"))
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            return

    async def find_executor(self, guild, action, target_id, max_age_seconds=None):
        for attempt in range(3):
            if attempt:
                await asyncio.sleep(1)
            try:
                async for entry in guild.audit_logs(limit=10, action=action):
                    if getattr(entry.target, "id", None) == target_id:
                        if max_age_seconds is not None:
                            age = (datetime.now(timezone.utc) - entry.created_at).total_seconds()
                            if age > max_age_seconds:
                                continue
                        return entry.user
            except (discord.Forbidden, discord.HTTPException):
                return None

        return None

    def actor_text(self, user):
        return user.mention if user else "No pude detectar el responsable"

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        actor = await self.find_executor(channel.guild, discord.AuditLogAction.channel_create, channel.id)
        await self.send_audit(
            channel.guild,
            "channels",
            "Canal creado",
            f"Canal: {channel.mention}\nResponsable: {self.actor_text(actor)}",
            color=discord.Color.green(),
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        actor = await self.find_executor(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
        await self.send_audit(
            channel.guild,
            "channels",
            "Canal eliminado",
            f"Canal: **{channel.name}**\nResponsable: {self.actor_text(actor)}",
            color=discord.Color.red(),
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        if before.name == after.name and before.category_id == after.category_id:
            return

        actor = await self.find_executor(after.guild, discord.AuditLogAction.channel_update, after.id)
        await self.send_audit(
            after.guild,
            "channels",
            "Canal modificado",
            f"Antes: **{before.name}**\nDespues: {after.mention}\nResponsable: {self.actor_text(actor)}",
        )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        actor = await self.find_executor(role.guild, discord.AuditLogAction.role_create, role.id)
        await self.send_audit(role.guild, "roles", "Rol creado", f"Rol: {role.mention}\nResponsable: {self.actor_text(actor)}", color=discord.Color.green())

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        actor = await self.find_executor(role.guild, discord.AuditLogAction.role_delete, role.id)
        await self.send_audit(role.guild, "roles", "Rol eliminado", f"Rol: **{role.name}**\nResponsable: {self.actor_text(actor)}", color=discord.Color.red())

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        if before.name == after.name and before.permissions == after.permissions and before.color == after.color:
            return

        actor = await self.find_executor(after.guild, discord.AuditLogAction.role_update, after.id)
        await self.send_audit(after.guild, "roles", "Rol modificado", f"Antes: **{before.name}**\nDespues: {after.mention}\nResponsable: {self.actor_text(actor)}")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self.send_audit(member.guild, "joins", "Miembro entro al servidor", f"Usuario: {member.mention}", color=discord.Color.green())

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await self.send_audit(
            member.guild,
            "joins",
            "Miembro salio del servidor",
            f"Usuario: {member.mention} (`{member.id}`)",
            color=discord.Color.orange(),
        )

        actor = await self.find_executor(member.guild, discord.AuditLogAction.kick, member.id, max_age_seconds=20)
        if not actor:
            return

        await self.send_audit(
            member.guild,
            "member_actions",
            "Miembro expulsado",
            f"Usuario: {member.mention}\nResponsable: {self.actor_text(actor)}",
            color=discord.Color.red(),
        )

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.nick != after.nick:
            actor = await self.find_executor(after.guild, discord.AuditLogAction.member_update, after.id)
            await self.send_audit(
                after.guild,
                "member_actions",
                "Nombre de miembro modificado",
                (
                    f"Usuario: {after.mention}\n"
                    f"Nombre anterior: **{before.nick or before.name}**\n"
                    f"Nombre nuevo: **{after.nick or after.name}**\n"
                    f"Responsable: {self.actor_text(actor)}"
                ),
            )

        before_roles = {role.id: role for role in before.roles}
        after_roles = {role.id: role for role in after.roles}
        added = [role for role_id, role in after_roles.items() if role_id not in before_roles and role.name != "@everyone"]
        removed = [role for role_id, role in before_roles.items() if role_id not in after_roles and role.name != "@everyone"]

        if added:
            actor = await self.find_executor(after.guild, discord.AuditLogAction.member_role_update, after.id)
            await self.send_audit(
                after.guild,
                "member_actions",
                "Roles asignados",
                (
                    f"Usuario: {after.mention}\n"
                    f"Roles: {', '.join(role.mention for role in added)}\n"
                    f"Responsable: {self.actor_text(actor)}"
                ),
                color=discord.Color.green(),
            )

        if removed:
            actor = await self.find_executor(after.guild, discord.AuditLogAction.member_role_update, after.id)
            await self.send_audit(
                after.guild,
                "member_actions",
                "Roles removidos",
                (
                    f"Usuario: {after.mention}\n"
                    f"Roles: {', '.join(role.mention for role in removed)}\n"
                    f"Responsable: {self.actor_text(actor)}"
                ),
                color=discord.Color.orange(),
            )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel == after.channel:
            return

        if before.channel is None and after.channel is not None:
            title = "Usuario entro a voz"
            description = f"Usuario: {member.mention}\nCanal: {after.channel.mention}"
        elif before.channel is not None and after.channel is None:
            title = "Usuario salio de voz"
            description = f"Usuario: {member.mention}\nCanal: **{before.channel.name}**"
        else:
            title = "Usuario se movio en voz"
            description = f"Usuario: {member.mention}\nDesde: **{before.channel.name}**\nHacia: {after.channel.mention}"

        await self.send_audit(member.guild, "voice", title, description)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.guild or message.author.bot:
            return

        content = message.content[:900] if message.content else "Sin contenido de texto"
        await self.send_audit(message.guild, "messages", "Mensaje eliminado", f"Autor: {message.author.mention}\nCanal: {message.channel.mention}\nContenido: {content}", color=discord.Color.red())

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not before.guild or before.author.bot or before.content == after.content:
            return

        await self.send_audit(before.guild, "messages", "Mensaje editado", f"Autor: {before.author.mention}\nCanal: {before.channel.mention}\nAntes: {before.content[:500]}\nDespues: {after.content[:500]}")

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        await self.send_audit(guild, "member_actions", "Usuario baneado", f"Usuario: {user.mention}", color=discord.Color.red())

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        await self.send_audit(guild, "member_actions", "Usuario desbaneado", f"Usuario: {user.mention}", color=discord.Color.green())


async def setup(bot):
    await bot.add_cog(AuditCog(bot))
