import json
import os
import re
from urllib.parse import urlparse
from datetime import datetime

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from repositories.balance_repository import DATA_DIR
from utils.json_store import (
    mutate_json as mutate_json_file,
    read_json as read_json_file,
    write_json as write_json_file,
)

TICKET_PANELS_FILE = os.path.join(DATA_DIR, "ticket_panels.json")
TICKET_RECORDS_FILE = os.path.join(DATA_DIR, "ticket_records.json")
TICKET_MEDIA_DIR = os.path.join(DATA_DIR, "ticket_media")
TICKET_CHANNEL_PERMISSION_KEYS = {
    "view_channel",
    "send_messages",
    "read_message_history",
    "attach_files",
    "embed_links",
    "add_reactions",
    "use_external_emojis",
    "use_external_stickers",
    "mention_everyone",
    "manage_messages",
    "manage_channels",
    "manage_threads",
    "create_public_threads",
    "create_private_threads",
    "send_messages_in_threads",
    "use_application_commands",
}
TICKET_SEND_PERMISSION_KEYS = {
    "send_messages",
    "attach_files",
    "embed_links",
    "add_reactions",
    "mention_everyone",
    "create_public_threads",
    "create_private_threads",
    "send_messages_in_threads",
}


def read_json(path, fallback):
    return read_json_file(path, fallback)


def write_json(path, data):
    write_json_file(path, data)


def parse_color(value, fallback=0x38BDF8):
    try:
        return int(str(value or "").strip().lstrip("#"), 16)
    except ValueError:
        return fallback


def safe_filename(value, fallback="archivo"):
    name = os.path.basename(str(value or "").split("?", 1)[0]) or fallback
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name or fallback


def media_url(relative_path):
    return "/ticket-media/" + relative_path.replace("\\", "/")


async def download_url_to_media(url, folder, filename):
    if not url:
        return ""

    os.makedirs(folder, exist_ok=True)
    filename = safe_filename(filename)
    path = os.path.join(folder, filename)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as response:
                if response.status != 200:
                    return ""
                with open(path, "wb") as f:
                    async for chunk in response.content.iter_chunked(1024 * 64):
                        f.write(chunk)
    except (aiohttp.ClientError, TimeoutError, OSError):
        return ""

    return media_url(os.path.relpath(path, TICKET_MEDIA_DIR))


async def save_attachment_to_media(attachment, folder):
    os.makedirs(folder, exist_ok=True)
    filename = f"{attachment.id}_{safe_filename(attachment.filename)}"
    path = os.path.join(folder, filename)
    try:
        await attachment.save(path)
    except (discord.HTTPException, OSError):
        return ""

    return media_url(os.path.relpath(path, TICKET_MEDIA_DIR))


async def serialize_embed(embed, folder, message_id, index):
    data = embed.to_dict()
    image = data.get("image", {})
    thumbnail = data.get("thumbnail", {})
    if image.get("url"):
        parsed = urlparse(image["url"])
        local_url = await download_url_to_media(image["url"], folder, f"{message_id}_embed_{index}_image_{safe_filename(parsed.path, 'image')}")
        if local_url:
            image = {**image, "local_url": local_url}
    if thumbnail.get("url"):
        parsed = urlparse(thumbnail["url"])
        local_url = await download_url_to_media(thumbnail["url"], folder, f"{message_id}_embed_{index}_thumbnail_{safe_filename(parsed.path, 'thumbnail')}")
        if local_url:
            thumbnail = {**thumbnail, "local_url": local_url}

    return {
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "url": data.get("url", ""),
        "color": data.get("color"),
        "author": data.get("author", {}),
        "footer": data.get("footer", {}),
        "image": image,
        "thumbnail": thumbnail,
        "fields": data.get("fields", []),
    }


class TicketRuntimeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def load_panels(self, guild_id):
        data = read_json(TICKET_PANELS_FILE, {})
        panels = data.get(str(guild_id), [])
        return panels if isinstance(panels, list) else []

    def load_records(self):
        return read_json(TICKET_RECORDS_FILE, {})

    def save_records(self, data):
        write_json(TICKET_RECORDS_FILE, data)

    def guild_records(self, guild_id):
        data = self.load_records()
        records = data.setdefault(str(guild_id), [])
        return data, records

    def find_panel(self, guild_id, panel_id):
        return next((panel for panel in self.load_panels(guild_id) if str(panel.get("id")) == str(panel_id)), None)

    def next_number(self, guild_id, panel_id):
        data, records = self.guild_records(guild_id)
        highest = 0
        panel_id = str(panel_id or "")
        for record in records:
            if str(record.get("panel_id") or "") != panel_id:
                continue
            try:
                highest = max(highest, int(record.get("number", 0)))
            except (TypeError, ValueError):
                continue
        self.save_records(data)
        return highest + 1

    def reserve_ticket_record(self, guild, panel, owner, option_id=None):
        panel_id = str(panel.get("id") or "")
        guild_id = str(guild.id)
        option = next((item for item in panel.get("options", []) if str(item.get("id")) == str(option_id)), None)
        reserved = {}

        def mutate(data):
            records = data.setdefault(guild_id, [])
            highest = 0
            for record in records:
                if str(record.get("panel_id") or "") != panel_id:
                    continue
                try:
                    highest = max(highest, int(record.get("number", 0)))
                except (TypeError, ValueError):
                    continue

            number = highest + 1
            record = {
                "number": number,
                "status": "open",
                "guild_id": guild_id,
                "channel_id": "",
                "channel_name": "",
                "owner_id": str(owner.id),
                "owner_name": owner.display_name,
                "panel_id": panel_id,
                "panel_name": panel.get("name", "Panel"),
                "option_id": str(option_id or ""),
                "option_label": option.get("label") if option else "",
                "claimed_by_id": "",
                "claimed_by_name": "",
                "created_at": datetime.now().strftime("%d/%m/%Y | %H:%M"),
                "closed_at": "",
                "transcript": [],
            }
            records.append(record)
            reserved["record"] = record
            return data

        mutate_json_file(TICKET_RECORDS_FILE, {}, mutate)
        return dict(reserved["record"])

    def update_reserved_ticket_record(self, guild_id, panel_id, number, *, channel_id, channel_name):
        gid = str(guild_id)
        panel_id = str(panel_id or "")

        def mutate(data):
            for record in data.get(gid, []):
                if str(record.get("panel_id") or "") != panel_id:
                    continue
                if int(record.get("number", 0) or 0) != int(number):
                    continue
                record["channel_id"] = str(channel_id)
                record["channel_name"] = channel_name
                break
            return data

        mutate_json_file(TICKET_RECORDS_FILE, {}, mutate)

    def release_reserved_ticket_record(self, guild_id, panel_id, number):
        gid = str(guild_id)
        panel_id = str(panel_id or "")

        def mutate(data):
            records = data.get(gid, [])
            data[gid] = [
                record
                for record in records
                if not (
                    str(record.get("panel_id") or "") == panel_id
                    and int(record.get("number", 0) or 0) == int(number)
                )
            ]
            if not data[gid]:
                data.pop(gid, None)
            return data

        mutate_json_file(TICKET_RECORDS_FILE, {}, mutate)

    def get_record(self, guild_id, channel_id):
        data, records = self.guild_records(guild_id)
        for record in records:
            if str(record.get("channel_id")) == str(channel_id):
                return data, record
        return data, None

    def role_ids(self, panel, permission_key):
        permissions = panel.get("permissions", {}) if isinstance(panel.get("permissions"), dict) else {}
        values = permissions.get(permission_key, [])
        if isinstance(values, str):
            values = [item.strip() for item in values.split(",") if item.strip()]
        return {int(value) for value in values if str(value).isdigit()}

    def member_has_any_role(self, member, role_ids):
        if member.guild_permissions.administrator:
            return True
        return any(role.id in role_ids for role in member.roles)

    def can_claim(self, member, panel):
        return self.member_has_any_role(member, self.role_ids(panel, "claim_roles"))

    def can_close(self, member, panel, record):
        return self.member_has_any_role(member, self.role_ids(panel, "close_roles"))

    def can_delete(self, member, panel):
        return self.member_has_any_role(member, self.role_ids(panel, "delete_roles"))

    def can_reopen(self, member, panel):
        return self.member_has_any_role(member, self.role_ids(panel, "reopen_roles"))

    def ticket_role_permissions(self, panel):
        permissions = panel.get("permissions", {}) if isinstance(panel.get("permissions"), dict) else {}
        entries = permissions.get("ticket_role_permissions")
        result = {}
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                role_id = str(entry.get("role_id") or "").strip()
                if not role_id.isdigit():
                    continue
                keys = {
                    str(key)
                    for key in entry.get("permissions", [])
                    if str(key) in TICKET_CHANNEL_PERMISSION_KEYS
                }
                if keys:
                    result[int(role_id)] = keys

        if result:
            return result

        writable_roles = (
            self.role_ids(panel, "send_roles")
            | self.role_ids(panel, "claim_roles")
            | self.role_ids(panel, "close_roles")
            | self.role_ids(panel, "reopen_roles")
        )
        for role_id in self.role_ids(panel, "view_roles") | self.role_ids(panel, "delete_roles"):
            result[role_id] = {"view_channel", "read_message_history"}
        for role_id in writable_roles:
            result[role_id] = {
                "view_channel",
                "send_messages",
                "read_message_history",
                "attach_files",
                "embed_links",
            }
        return result

    def ticket_permission_overwrite(self, permission_keys, *, closed=False):
        values = {
            key: True
            for key in permission_keys
            if key in TICKET_CHANNEL_PERMISSION_KEYS
        }
        if closed:
            for key in TICKET_SEND_PERMISSION_KEYS:
                if key in values:
                    values[key] = False
        return discord.PermissionOverwrite(**values)

    def ticket_controls(self, channel_id):
        view = discord.ui.View(timeout=None)
        claim = discord.ui.Button(label="Reclamar ticket", style=discord.ButtonStyle.primary, custom_id=f"ticket_runtime_claim:{channel_id}")
        close = discord.ui.Button(label="Cerrar ticket", style=discord.ButtonStyle.danger, custom_id=f"ticket_runtime_close:{channel_id}")
        view.add_item(claim)
        view.add_item(close)
        return view

    def closed_controls(self, channel_id):
        view = discord.ui.View(timeout=None)
        reopen = discord.ui.Button(label="Reabrir ticket", style=discord.ButtonStyle.success, custom_id=f"ticket_runtime_reopen:{channel_id}")
        transcript = discord.ui.Button(label="Transcribir ticket", style=discord.ButtonStyle.primary, custom_id=f"ticket_runtime_transcript:{channel_id}")
        delete = discord.ui.Button(label="Eliminar ticket", style=discord.ButtonStyle.danger, custom_id=f"ticket_runtime_delete:{channel_id}")
        transcript_delete = discord.ui.Button(label="Transcribir y eliminar ticket", style=discord.ButtonStyle.danger, custom_id=f"ticket_runtime_transcript_delete:{channel_id}")
        view.add_item(reopen)
        view.add_item(transcript)
        view.add_item(delete)
        view.add_item(transcript_delete)
        return view

    def close_confirm_controls(self, channel_id):
        view = discord.ui.View(timeout=60)
        confirm = discord.ui.Button(label="Confirmar cierre", style=discord.ButtonStyle.danger, custom_id=f"ticket_runtime_close_confirm:{channel_id}")
        cancel = discord.ui.Button(label="Cancelar", style=discord.ButtonStyle.secondary, custom_id=f"ticket_runtime_close_cancel:{channel_id}")
        view.add_item(confirm)
        view.add_item(cancel)
        return view

    @staticmethod
    def format_open_message(value, *, interaction, panel, record, channel, option_id):
        option = next(
            (
                item
                for item in panel.get("options", [])
                if str(item.get("id")) == str(option_id)
            ),
            {},
        )
        replacements = {
            "mention": interaction.user.mention,
            "user": interaction.user.mention,
            "username": interaction.user.name,
            "display_name": interaction.user.display_name,
            "user_id": str(interaction.user.id),
            "ticket_number": f"{int(record['number']):04d}",
            "ticket_name": channel.name,
            "panel_name": str(panel.get("name") or ""),
            "option": str(option.get("label") or ""),
        }
        text = str(value or "")
        for key, replacement in replacements.items():
            text = text.replace(f"{{{key}}}", replacement)
        return text

    async def create_ticket(self, interaction, panel, option_id=None):
        guild = interaction.guild
        if guild is None:
            return

        category = guild.get_channel(int(panel.get("open_category_id") or 0)) if str(panel.get("open_category_id") or "").isdigit() else None
        record = self.reserve_ticket_record(guild, panel, interaction.user, option_id)
        panel_id = str(record.get("panel_id") or panel.get("id") or "")
        number = int(record["number"])
        channel_name = f"ticket-{number:04d}"
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True, manage_messages=True),
        }
        for role_id, permission_keys in self.ticket_role_permissions(panel).items():
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = self.ticket_permission_overwrite(permission_keys)

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket {number:04d} | Usuario: {interaction.user} ({interaction.user.id}) | Panel: {panel.get('name')}",
                reason=f"Ticket abierto por {interaction.user}",
            )
        except discord.Forbidden:
            self.release_reserved_ticket_record(guild.id, panel_id, number)
            await interaction.response.send_message("No puedo crear el canal del ticket. Revisa mis permisos.", ephemeral=True)
            return
        except discord.HTTPException:
            self.release_reserved_ticket_record(guild.id, panel_id, number)
            await interaction.response.send_message("No pude crear el canal del ticket.", ephemeral=True)
            return

        self.update_reserved_ticket_record(guild.id, panel_id, number, channel_id=channel.id, channel_name=channel.name)

        format_value = lambda value: self.format_open_message(
            value,
            interaction=interaction,
            panel=panel,
            record=record,
            channel=channel,
            option_id=option_id,
        )
        content = format_value(panel.get("ticket_open_content"))
        title = format_value(panel.get("ticket_open_title"))
        description = format_value(panel.get("ticket_open_description"))
        footer = format_value(panel.get("ticket_open_footer"))
        image_url = str(panel.get("ticket_open_image_url") or "").strip()
        thumbnail_url = str(panel.get("ticket_open_thumbnail_url") or "").strip()
        color_value = str(panel.get("ticket_open_color") or "").strip()
        embed = None
        if any((title, description, footer, image_url, thumbnail_url)):
            embed = discord.Embed(
                title=title or None,
                description=description or None,
                color=parse_color(color_value, 0x38BDF8) if color_value else None,
            )
            if footer:
                embed.set_footer(text=footer)
            if image_url:
                embed.set_image(url=image_url)
            if thumbnail_url:
                embed.set_thumbnail(url=thumbnail_url)

        await channel.send(
            content=content or None,
            embed=embed,
            view=self.ticket_controls(channel.id),
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=True,
                roles=True,
                replied_user=False,
            ),
        )
        await interaction.response.send_message(f"Ticket creado: {channel.mention}", ephemeral=True)

    async def claim_ticket(self, interaction, channel_id):
        data, record = self.get_record(interaction.guild.id, channel_id)
        if not record:
            await interaction.response.send_message("No encontre este ticket.", ephemeral=True)
            return

        if record.get("status") != "open":
            await interaction.response.send_message("Solo puedes reclamar tickets abiertos.", ephemeral=True)
            return

        panel = self.find_panel(interaction.guild.id, record.get("panel_id"))
        if not panel or not self.can_claim(interaction.user, panel):
            await interaction.response.send_message("No tienes permiso para reclamar este ticket.", ephemeral=True)
            return

        if record.get("claimed_by_id"):
            await interaction.response.send_message("Este ticket ya fue reclamado.", ephemeral=True)
            return

        claim_roles = self.role_ids(panel, "claim_roles")
        for role_id in claim_roles:
            role = interaction.guild.get_role(role_id)
            if role:
                await interaction.channel.set_permissions(role, view_channel=True, send_messages=False, read_message_history=True)

        await interaction.channel.set_permissions(interaction.user, view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True)
        record["claimed_by_id"] = str(interaction.user.id)
        record["claimed_by_name"] = interaction.user.display_name
        self.save_records(data)
        await interaction.response.send_message(f"Ticket reclamado por {interaction.user.mention}.")

    async def close_ticket_prompt(self, interaction, channel_id):
        data, record = self.get_record(interaction.guild.id, channel_id)
        panel = self.find_panel(interaction.guild.id, record.get("panel_id")) if record else None
        if not record or not panel or not self.can_close(interaction.user, panel, record):
            await interaction.response.send_message("No tienes permiso para cerrar este ticket.", ephemeral=True)
            return

        await interaction.response.send_message("Confirma que quieres cerrar este ticket.", view=self.close_confirm_controls(channel_id), ephemeral=True)

    async def close_ticket_confirm(self, interaction, channel_id):
        data, record = self.get_record(interaction.guild.id, channel_id)
        if not record:
            await interaction.response.send_message("No encontre este ticket.", ephemeral=True)
            return

        panel = self.find_panel(interaction.guild.id, record.get("panel_id"))
        if not panel or not self.can_close(interaction.user, panel, record):
            await interaction.response.send_message("No tienes permiso para cerrar este ticket.", ephemeral=True)
            return

        if record.get("status") != "open":
            await interaction.response.send_message("Este ticket ya no esta abierto.", ephemeral=True)
            return

        record["status"] = "closed"
        record["closed_at"] = datetime.now().strftime("%d/%m/%Y | %H:%M")
        self.save_records(data)
        try:
            await interaction.channel.set_permissions(
                interaction.guild.default_role,
                view_channel=False,
            )
            await interaction.channel.set_permissions(
                interaction.guild.me,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
            )
            owner_id = int(record.get("owner_id", 0) or 0)
            owner = interaction.guild.get_member(owner_id) if owner_id else None
            if owner is not None:
                await interaction.channel.set_permissions(
                    owner,
                    view_channel=False,
                    send_messages=False,
                    read_message_history=False,
                    attach_files=False,
                    embed_links=False,
                )

            claimed_by_id = int(record.get("claimed_by_id", 0) or 0)
            claimed_member = interaction.guild.get_member(claimed_by_id) if claimed_by_id else None
            if claimed_member is not None:
                await interaction.channel.set_permissions(
                    claimed_member,
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True,
                    attach_files=False,
                    embed_links=False,
                )

            for role_id, permission_keys in self.ticket_role_permissions(panel).items():
                role = interaction.guild.get_role(role_id)
                if role:
                    await interaction.channel.set_permissions(
                        role,
                        overwrite=self.ticket_permission_overwrite(permission_keys, closed=True),
                    )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Marque el ticket como cerrado, pero no pude ajustar los permisos del canal. Revisa mis permisos.",
                ephemeral=True,
            )
            return
        await interaction.channel.send("Ticket cerrado.", view=self.closed_controls(channel_id))
        await interaction.response.send_message("Ticket cerrado.", ephemeral=True)

    async def reopen_ticket(self, interaction, channel_id):
        data, record = self.get_record(interaction.guild.id, channel_id)
        if not record:
            await interaction.response.send_message("No encontre este ticket.", ephemeral=True)
            return

        panel = self.find_panel(interaction.guild.id, record.get("panel_id"))
        if not panel or not self.can_reopen(interaction.user, panel):
            await interaction.response.send_message("No tienes permiso para reabrir este ticket.", ephemeral=True)
            return

        if record.get("status") != "closed":
            await interaction.response.send_message("Solo puedes reabrir tickets cerrados.", ephemeral=True)
            return

        record["status"] = "open"
        record["reopened_at"] = datetime.now().strftime("%d/%m/%Y | %H:%M")
        record["closed_at"] = ""
        self.save_records(data)

        try:
            await interaction.channel.set_permissions(
                interaction.guild.default_role,
                view_channel=False,
            )
            await interaction.channel.set_permissions(
                interaction.guild.me,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
            )
            owner_id = int(record.get("owner_id", 0) or 0)
            owner = interaction.guild.get_member(owner_id) if owner_id else None
            if owner is not None:
                await interaction.channel.set_permissions(
                    owner,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                )

            for role_id, permission_keys in self.ticket_role_permissions(panel).items():
                role = interaction.guild.get_role(role_id)
                if role:
                    await interaction.channel.set_permissions(
                        role,
                        overwrite=self.ticket_permission_overwrite(permission_keys),
                    )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Marque el ticket como abierto, pero no pude ajustar los permisos del canal. Revisa mis permisos.",
                ephemeral=True,
            )
            return

        await interaction.channel.send(
            f"Ticket reabierto por {interaction.user.mention}.",
            view=self.ticket_controls(channel_id),
        )
        await interaction.response.send_message("Ticket reabierto.", ephemeral=True)

    async def transcript_ticket(self, interaction, channel_id):
        data, record = self.get_record(interaction.guild.id, channel_id)
        if not record:
            await interaction.response.send_message("No encontre este ticket.", ephemeral=True)
            return

        panel = self.find_panel(interaction.guild.id, record.get("panel_id"))
        can_transcript = panel and (self.can_close(interaction.user, panel, record) or self.can_delete(interaction.user, panel))
        if not record or not can_transcript:
            await interaction.response.send_message("No tienes permiso para transcribir este ticket.", ephemeral=True)
            return

        if record.get("status") not in {"closed", "deleted"}:
            await interaction.response.send_message("Primero cierra el ticket para guardar la transcripcion final.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.save_ticket_transcript(interaction, channel_id, data, record)
        await interaction.followup.send(
            "Transcripcion guardada en el dashboard.",
            ephemeral=True,
        )

    async def save_ticket_transcript(self, interaction, channel_id, data, record):
        messages = []
        async for message in interaction.channel.history(limit=None, oldest_first=True):
            author = message.author
            media_folder = os.path.join(
                TICKET_MEDIA_DIR,
                str(interaction.guild.id),
                str(channel_id),
                str(message.id),
            )
            attachments = []
            for attachment in message.attachments:
                local_url = await save_attachment_to_media(attachment, media_folder)
                attachments.append({
                    "filename": attachment.filename,
                    "url": attachment.url,
                    "local_url": local_url,
                    "content_type": attachment.content_type or "",
                    "size": attachment.size,
                })
            embeds = [
                await serialize_embed(embed, media_folder, message.id, index)
                for index, embed in enumerate(message.embeds, start=1)
            ]
            messages.append({
                "id": str(message.id),
                "author": str(author),
                "author_name": getattr(author, "display_name", str(author)),
                "author_id": str(author.id),
                "author_avatar": str(author.display_avatar.url) if getattr(author, "display_avatar", None) else "",
                "author_bot": bool(getattr(author, "bot", False)),
                "content": message.content,
                "created_at": message.created_at.strftime("%d/%m/%Y | %H:%M"),
                "attachments": attachments,
                "embeds": embeds,
                "reference": {
                    "message_id": str(message.reference.message_id or ""),
                    "channel_id": str(message.reference.channel_id or ""),
                    "guild_id": str(message.reference.guild_id or ""),
                } if message.reference else None,
            })
        record["transcript"] = messages
        record["transcribed_at"] = datetime.now().strftime("%d/%m/%Y | %H:%M")
        self.save_records(data)

    async def delete_ticket(self, interaction, channel_id):
        data, record = self.get_record(interaction.guild.id, channel_id)
        panel = self.find_panel(interaction.guild.id, record.get("panel_id")) if record else None
        if not record or not panel or not self.can_delete(interaction.user, panel):
            await interaction.response.send_message("No tienes permiso para eliminar este ticket.", ephemeral=True)
            return

        record["status"] = "deleted"
        record["deleted_at"] = datetime.now().strftime("%d/%m/%Y | %H:%M")
        self.save_records(data)
        await interaction.response.send_message("Eliminando ticket...", ephemeral=True)
        await interaction.channel.delete(reason=f"Ticket eliminado por {interaction.user}")

    async def transcript_and_delete_ticket(self, interaction, channel_id):
        data, record = self.get_record(interaction.guild.id, channel_id)
        panel = self.find_panel(interaction.guild.id, record.get("panel_id")) if record else None
        if not record or not panel or not self.can_delete(interaction.user, panel):
            await interaction.response.send_message("No tienes permiso para transcribir y eliminar este ticket.", ephemeral=True)
            return

        if record.get("status") not in {"closed", "deleted"}:
            await interaction.response.send_message("Primero cierra el ticket para guardar la transcripcion final.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.save_ticket_transcript(interaction, channel_id, data, record)
        record["status"] = "deleted"
        record["deleted_at"] = datetime.now().strftime("%d/%m/%Y | %H:%M")
        self.save_records(data)
        await interaction.followup.send("Transcripcion guardada. Eliminando ticket...", ephemeral=True)
        await interaction.channel.delete(reason=f"Ticket transcrito y eliminado por {interaction.user}")

    @app_commands.command(
        name="cerrar-ticket",
        description="Cierra el ticket del canal actual.",
    )
    @app_commands.guild_only()
    async def close_ticket_command(self, interaction: discord.Interaction):
        if not interaction.channel_id:
            await interaction.response.send_message(
                "Este comando solo funciona dentro de un canal de ticket.",
                ephemeral=True,
            )
            return

        await self.close_ticket_prompt(interaction, interaction.channel_id)

    @app_commands.command(
        name="transcribir-ticket",
        description="Guarda la transcripcion del ticket en el dashboard.",
    )
    @app_commands.guild_only()
    async def transcript_ticket_command(self, interaction: discord.Interaction):
        if not interaction.channel_id:
            await interaction.response.send_message(
                "Este comando solo funciona dentro de un canal de ticket.",
                ephemeral=True,
            )
            return

        await self.transcript_ticket(interaction, interaction.channel_id)

    @commands.Cog.listener()
    async def on_interaction(self, interaction):
        if interaction.type != discord.InteractionType.component or not interaction.data:
            return

        custom_id = interaction.data.get("custom_id", "")
        if custom_id.startswith("ticket_button:"):
            _, panel_id, option_id = custom_id.split(":", 2)
            panel = self.find_panel(interaction.guild.id, panel_id)
            if panel:
                await self.create_ticket(interaction, panel, option_id)
            return

        if custom_id.startswith("ticket_select:"):
            _, panel_id = custom_id.split(":", 1)
            values = interaction.data.get("values") or []
            panel = self.find_panel(interaction.guild.id, panel_id)
            if panel:
                await self.create_ticket(interaction, panel, values[0] if values else "")
            return

        if custom_id.startswith("ticket_runtime_claim:"):
            await self.claim_ticket(interaction, custom_id.split(":", 1)[1])
            return

        if custom_id.startswith("ticket_runtime_close:") and not custom_id.startswith("ticket_runtime_close_confirm:") and not custom_id.startswith("ticket_runtime_close_cancel:"):
            await self.close_ticket_prompt(interaction, custom_id.split(":", 1)[1])
            return

        if custom_id.startswith("ticket_runtime_close_confirm:"):
            await self.close_ticket_confirm(interaction, custom_id.split(":", 1)[1])
            return

        if custom_id.startswith("ticket_runtime_close_cancel:"):
            await interaction.response.send_message("Cierre cancelado.", ephemeral=True)
            return

        if custom_id.startswith("ticket_runtime_reopen:"):
            await self.reopen_ticket(interaction, custom_id.split(":", 1)[1])
            return

        if custom_id.startswith("ticket_runtime_transcript:"):
            await self.transcript_ticket(interaction, custom_id.split(":", 1)[1])
            return

        if custom_id.startswith("ticket_runtime_transcript_delete:"):
            await self.transcript_and_delete_ticket(interaction, custom_id.split(":", 1)[1])
            return

        if custom_id.startswith("ticket_runtime_delete:"):
            await self.delete_ticket(interaction, custom_id.split(":", 1)[1])
            return


async def setup(bot):
    await bot.add_cog(TicketRuntimeCog(bot))
