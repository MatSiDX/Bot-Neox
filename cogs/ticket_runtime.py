import json
import os
import re
from urllib.parse import urlparse
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

try:
    import aiohttp
except ModuleNotFoundError:
    aiohttp = None

from repositories.balance_repository import DATA_DIR
from repositories.fine_repository import FineRepository
from utils.json_store import (
    mutate_json as mutate_json_file,
    read_json as read_json_file,
    write_json as write_json_file,
)
from services.permission_service import (
    PERMISSION_FINES_RECORDS_MANAGE,
    PERMISSION_TICKETS_RECORDS_ADD_MEMBER,
    PERMISSION_TICKETS_RECORDS_CLAIM,
    PERMISSION_TICKETS_RECORDS_CLOSE,
    PERMISSION_TICKETS_RECORDS_DELETE,
    PERMISSION_TICKETS_RECORDS_REOPEN,
    PERMISSION_TICKETS_RECORDS_TRANSCRIPT,
    PermissionService,
)
from utils.console_logger import log_exception
from utils.interaction_safety import describe_interaction, send_safe_interaction_error

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
DEFAULT_TICKET_OWNER_PERMISSION_KEYS = {
    "view_channel",
    "send_messages",
    "read_message_history",
    "attach_files",
    "embed_links",
}
CLOSED_TICKET_CHANNEL_PREFIX = "cerrado"
CLOSED_TICKET_CHANNEL_RE = re.compile(r"^cerrado-[a-z0-9]+(?:-[0-9]+)?$")


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


def safe_discord_channel_name(value, fallback="ticket"):
    name = str(value or "").strip().lower()
    name = re.sub(r"[^a-z0-9-]+", "-", name)
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return (name or fallback)[:100]


async def download_url_to_media(url, folder, filename):
    if not url or aiohttp is None:
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
        self.permission_service = PermissionService()
        self.fine_repo = FineRepository()

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

    def ticket_number_scope(self, panel, option_id=None):
        if str(panel.get("mode") or "") == "select" and str(option_id or "").strip():
            return str(option_id)
        return ""

    def record_matches_number_scope(self, record, panel_id, number_scope):
        if str(record.get("panel_id") or "") != str(panel_id or ""):
            return False
        if number_scope:
            return str(record.get("option_id") or "") == number_scope
        return True

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
        number_scope = self.ticket_number_scope(panel, option_id)
        reserved = {}

        def mutate(data):
            records = data.setdefault(guild_id, [])
            highest = 0
            for record in records:
                if not self.record_matches_number_scope(record, panel_id, number_scope):
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
                "added_users": [],
                "created_at": datetime.now().strftime("%d/%m/%Y | %H:%M"),
                "closed_at": "",
                "transcript": [],
            }
            records.append(record)
            reserved["record"] = record
            return data

        mutate_json_file(TICKET_RECORDS_FILE, {}, mutate)
        return dict(reserved["record"])

    def update_reserved_ticket_record(self, guild_id, panel_id, number, *, channel_id, channel_name, option_id=""):
        gid = str(guild_id)
        panel_id = str(panel_id or "")
        option_id = str(option_id or "")

        def mutate(data):
            for record in data.get(gid, []):
                if str(record.get("panel_id") or "") != panel_id:
                    continue
                if option_id and str(record.get("option_id") or "") != option_id:
                    continue
                if int(record.get("number", 0) or 0) != int(number):
                    continue
                record["channel_id"] = str(channel_id)
                record["channel_name"] = channel_name
                break
            return data

        mutate_json_file(TICKET_RECORDS_FILE, {}, mutate)

    def release_reserved_ticket_record(self, guild_id, panel_id, number, option_id=""):
        gid = str(guild_id)
        panel_id = str(panel_id or "")
        option_id = str(option_id or "")

        def mutate(data):
            records = data.get(gid, [])
            data[gid] = [
                record
                for record in records
                if not (
                    str(record.get("panel_id") or "") == panel_id
                    and (not option_id or str(record.get("option_id") or "") == option_id)
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
                if self.refresh_fine_record(record):
                    self.save_records(data)
                return data, record

        fine = self.find_fine_by_channel(guild_id, channel_id)
        if fine:
            record = self.fine_to_ticket_record(fine)
            records.append(record)
            self.save_records(data)
            return data, record
        return data, None

    def find_fine_by_channel(self, guild_id, channel_id):
        fine_repo = getattr(self, "fine_repo", None)
        if not fine_repo or not channel_id:
            return None
        return fine_repo.get_by_ticket_channel(guild_id, channel_id)

    def fine_payload(self, fine):
        return {
            "id": str(fine.get("id") or ""),
            "guild_id": str(fine.get("guild_id") or ""),
            "guild_name": str(fine.get("guild_name") or ""),
            "report_ava": str(fine.get("report_ava") or ""),
            "fined_user_id": str(fine.get("fined_user_id") or ""),
            "fined_user_name": str(fine.get("fined_user_name") or ""),
            "amount": int(fine.get("amount") or 0),
            "reason": str(fine.get("reason") or ""),
            "proof_path": str(fine.get("proof_path") or ""),
            "proof_name": str(fine.get("proof_name") or ""),
            "status": str(fine.get("status") or "open"),
            "is_deleted": bool(int(fine.get("is_deleted") or 0)) or bool(fine.get("deleted_at")),
            "blocked_role_id": str(fine.get("blocked_role_id") or ""),
            "resolver_role_id": str(fine.get("resolver_role_id") or ""),
            "ticket_channel_id": str(fine.get("ticket_channel_id") or ""),
            "ticket_message_id": str(fine.get("ticket_message_id") or ""),
            "announcement_channel_id": str(fine.get("announcement_channel_id") or ""),
            "announcement_message_id": str(fine.get("announcement_message_id") or ""),
            "created_by_id": str(fine.get("created_by_id") or ""),
            "created_by_name": str(fine.get("created_by_name") or ""),
            "paid_by_id": str(fine.get("paid_by_id") or ""),
            "paid_by_name": str(fine.get("paid_by_name") or ""),
            "created_at": str(fine.get("created_at") or ""),
            "updated_at": str(fine.get("updated_at") or ""),
            "paid_at": str(fine.get("paid_at") or ""),
            "closed_at": str(fine.get("closed_at") or ""),
            "deleted_at": str(fine.get("deleted_at") or ""),
        }

    def fine_to_ticket_record(self, fine):
        fine_id = int(fine.get("id") or 0)
        is_deleted = bool(int(fine.get("is_deleted") or 0)) or bool(fine.get("deleted_at"))
        fine_status = str(fine.get("status") or "open").lower()
        ticket_status = "deleted" if is_deleted else "closed" if fine_status == "paid" else "open"
        fine_payload = self.fine_payload(fine)
        return {
            "number": fine_id,
            "status": ticket_status,
            "fine_status": fine_status,
            "is_deleted": is_deleted,
            "ticket_type": "fine",
            "fine_id": str(fine_id),
            "guild_id": str(fine.get("guild_id") or ""),
            "channel_id": str(fine.get("ticket_channel_id") or ""),
            "channel_name": f"multa-{fine_id:04d}" if fine_id else "",
            "owner_id": str(fine.get("fined_user_id") or ""),
            "owner_name": str(fine.get("fined_user_name") or ""),
            "panel_id": "__fine__",
            "panel_name": "Multa",
            "option_id": "",
            "option_label": "",
            "claimed_by_id": "",
            "claimed_by_name": "",
            "resolver_role_id": str(fine.get("resolver_role_id") or ""),
            "created_at": str(fine.get("created_at") or ""),
            "closed_at": str(fine.get("closed_at") or ""),
            "deleted_at": str(fine.get("deleted_at") or ""),
            "report_ava": fine_payload["report_ava"],
            "amount": fine_payload["amount"],
            "reason": fine_payload["reason"],
            "proof_name": fine_payload["proof_name"],
            "proof_path": fine_payload["proof_path"],
            "created_by_id": fine_payload["created_by_id"],
            "created_by_name": fine_payload["created_by_name"],
            "paid_by_id": fine_payload["paid_by_id"],
            "paid_by_name": fine_payload["paid_by_name"],
            "paid_at": fine_payload["paid_at"],
            "fine": fine_payload,
            "transcript": [],
        }

    def is_fine_record(self, record):
        return isinstance(record, dict) and str(record.get("ticket_type") or "") == "fine"

    def is_ticket_deleted(self, record):
        return (
            str(record.get("status") or "").lower() == "deleted"
            or bool(record.get("is_deleted"))
            or bool(record.get("deleted_at"))
        )

    def soft_delete_ticket_record(self, record):
        deleted_at = datetime.now().strftime("%d/%m/%Y | %H:%M")

        if self.is_fine_record(record):
            fine_repo = getattr(self, "fine_repo", None)
            fine_id = str(record.get("fine_id") or record.get("number") or "").strip()
            if not fine_repo or not fine_id.isdigit():
                return False
            fine = fine_repo.soft_delete(int(fine_id))
            if fine is None:
                return False
            deleted_at = str(fine.get("deleted_at") or deleted_at)

        record["status"] = "deleted"
        record["is_deleted"] = True
        record["deleted_at"] = deleted_at
        if not record.get("closed_at"):
            record["closed_at"] = deleted_at
        return True

    def refresh_fine_record(self, record):
        if not self.is_fine_record(record):
            return False

        fine_repo = getattr(self, "fine_repo", None)
        if not fine_repo:
            return False

        fine = None
        fine_id = str(record.get("fine_id") or "").strip()
        if fine_id.isdigit():
            fine = fine_repo.get(int(fine_id))
        if fine is None:
            fine = self.find_fine_by_channel(record.get("guild_id"), record.get("channel_id"))
        if fine is None:
            return False

        updated = self.fine_to_ticket_record(fine)
        changed = False
        if updated.get("status") in {"closed", "deleted"} and record.get("status") != updated.get("status"):
            record["status"] = updated.get("status")
            changed = True
        synced_keys = [
            "fine_status",
            "is_deleted",
            "deleted_at",
            "resolver_role_id",
            "report_ava",
            "amount",
            "reason",
            "proof_name",
            "proof_path",
            "created_by_id",
            "created_by_name",
            "paid_by_id",
            "paid_by_name",
            "paid_at",
            "fine",
        ]
        if updated.get("status") in {"closed", "deleted"}:
            synced_keys.append("closed_at")
        for key in synced_keys:
            if record.get(key) != updated.get(key):
                record[key] = updated.get(key)
                changed = True
        return changed

    def ticket_channel_identifier(self, record, channel=None):
        for key in ("number", "fine_id", "ticket_id", "id"):
            value = str(record.get(key) or "").strip()
            if value:
                return f"{int(value):04d}" if value.isdigit() else value

        value = str(record.get("channel_id") or "").strip()
        if value:
            return value

        channel_id = str(getattr(channel, "id", "") or "").strip()
        return channel_id or "ticket"

    def closed_ticket_channel_name(self, record, channel=None):
        identifier = safe_discord_channel_name(self.ticket_channel_identifier(record, channel))
        return safe_discord_channel_name(f"{CLOSED_TICKET_CHANNEL_PREFIX}-{identifier}", "cerrado-ticket")

    def fallback_open_ticket_channel_name(self, record, channel=None):
        original = str(record.get("original_channel_name") or record.get("channel_name") or "").strip()
        if original and not CLOSED_TICKET_CHANNEL_RE.fullmatch(original):
            return safe_discord_channel_name(original)

        prefix = "multa" if self.is_fine_record(record) else "ticket"
        identifier = safe_discord_channel_name(self.ticket_channel_identifier(record, channel))
        return safe_discord_channel_name(f"{prefix}-{identifier}", f"{prefix}-ticket")

    def unique_channel_name(self, guild, channel, preferred_name):
        base_name = safe_discord_channel_name(preferred_name)
        channels = getattr(guild, "channels", None) or getattr(guild, "text_channels", []) or []
        used_names = {
            getattr(existing_channel, "name", None)
            for existing_channel in channels
            if getattr(existing_channel, "id", None) != getattr(channel, "id", None)
        }
        if base_name not in used_names:
            return base_name

        suffix = str(getattr(channel, "id", "") or self.ticket_channel_identifier({}, channel))
        for counter in ["", *[f"-{index}" for index in range(2, 1000)]]:
            full_suffix = f"{suffix}{counter}"
            max_base_length = max(1, 100 - len(full_suffix) - 1)
            candidate = safe_discord_channel_name(f"{base_name[:max_base_length]}-{full_suffix}")
            if candidate not in used_names:
                return candidate

        max_base_length = max(1, 100 - len(suffix) - 5)
        return safe_discord_channel_name(f"{base_name[:max_base_length]}-{suffix}-999")

    async def rename_ticket_channel(self, interaction, record, *, closed):
        channel = interaction.channel
        guild = interaction.guild
        if channel is None or guild is None:
            return False

        if closed:
            current_name = str(getattr(channel, "name", "") or "")
            expected_base_name = self.closed_ticket_channel_name(record, channel)
            expected_name = self.unique_channel_name(guild, channel, expected_base_name)
            if current_name == expected_name:
                return False

            if not record.get("original_channel_name") and not CLOSED_TICKET_CHANNEL_RE.fullmatch(current_name):
                record["original_channel_name"] = current_name
            reason = "Ticket cerrado"
        else:
            expected_base_name = self.fallback_open_ticket_channel_name(record, channel)
            expected_name = self.unique_channel_name(guild, channel, expected_base_name)
            if str(getattr(channel, "name", "") or "") == expected_name:
                return False
            reason = "Ticket reabierto"

        try:
            await channel.edit(name=expected_name, reason=reason)
        except discord.Forbidden as exc:
            log_exception(
                f"No pude renombrar el canal del ticket {self.ticket_channel_identifier(record, channel)} por permisos",
                exc,
            )
            return False
        except discord.HTTPException as exc:
            log_exception(
                f"No pude renombrar el canal del ticket {self.ticket_channel_identifier(record, channel)} a {expected_name}",
                exc,
            )
            return False

        record["channel_name"] = expected_name
        return True

    async def rename_ticket_channel_and_save(self, interaction, data, record, *, closed):
        if await self.rename_ticket_channel(interaction, record, closed=closed):
            self.save_records(data)

    def schedule_ticket_channel_rename(self, interaction, data, record, *, closed):
        loop = getattr(getattr(self, "bot", None), "loop", None)
        coroutine = self.rename_ticket_channel_and_save(interaction, data, record, closed=closed)
        if loop and not loop.is_closed():
            loop.create_task(coroutine)
            return
        try:
            import asyncio

            asyncio.create_task(coroutine)
        except RuntimeError:
            coroutine.close()
            log_exception("No pude programar el renombrado del canal del ticket")

    def role_ids(self, panel, permission_key):
        if not isinstance(panel, dict):
            return set()

        permissions = panel.get("permissions", {}) if isinstance(panel.get("permissions"), dict) else {}
        values = permissions.get(permission_key, [])
        if isinstance(values, str):
            values = [item.strip() for item in values.split(",") if item.strip()]
        return {int(value) for value in values if str(value).isdigit()}

    def can_manage_ticket_action(self, guild_id, member):
        guild_id = guild_id or getattr(getattr(member, "guild", None), "id", None)
        if PermissionService.is_administrator(member):
            return True

        permission_service = getattr(self, "permission_service", None)
        return bool(guild_id and permission_service and permission_service.can_manage_tickets(guild_id, member))

    def has_ticket_permission(self, guild_id, member, *permission_keys):
        guild_id = guild_id or getattr(getattr(member, "guild", None), "id", None)
        if PermissionService.is_administrator(member):
            return True

        permission_service = getattr(self, "permission_service", None)
        if not guild_id or not permission_service:
            return False

        return permission_service.has_module_access(
            guild_id,
            "tickets",
            member=member,
            required_permissions=permission_keys,
        )

    def member_has_any_role(self, member, role_ids, guild_id=None):
        guild_id = guild_id or getattr(getattr(member, "guild", None), "id", None)
        if self.can_manage_ticket_action(guild_id, member):
            return True

        return any(role.id in role_ids for role in getattr(member, "roles", []) or [])

    def can_claim(self, member, panel, guild_id=None):
        if self.has_ticket_permission(guild_id, member, PERMISSION_TICKETS_RECORDS_CLAIM):
            return True
        return self.member_has_any_role(member, self.role_ids(panel, "claim_roles"), guild_id)

    def can_add_member(self, member, panel, guild_id=None):
        if self.has_ticket_permission(guild_id, member, PERMISSION_TICKETS_RECORDS_ADD_MEMBER):
            return True
        if not isinstance(panel, dict):
            return self.member_has_any_role(member, set(), guild_id)

        permissions = panel.get("permissions", {}) if isinstance(panel.get("permissions"), dict) else {}
        user_ids = {
            str(value)
            for value in permissions.get("add_member_user_ids", [])
            if str(value).isdigit()
        } if isinstance(permissions.get("add_member_user_ids"), list) else set()
        if str(getattr(member, "id", "") or "") in user_ids:
            return True

        return self.member_has_any_role(member, self.role_ids(panel, "add_member_roles"), guild_id)

    def can_close(self, member, panel, record, guild_id=None):
        if self.is_fine_record(record):
            return self.can_manage_fine_ticket_action(guild_id, member, record)
        if self.has_ticket_permission(guild_id, member, PERMISSION_TICKETS_RECORDS_CLOSE):
            return True
        return self.member_has_any_role(member, self.role_ids(panel, "close_roles"), guild_id)

    def can_delete(self, member, panel, guild_id=None, record=None):
        if self.is_fine_record(record):
            return self.can_manage_fine_ticket_action(guild_id, member, record)
        if self.has_ticket_permission(guild_id, member, PERMISSION_TICKETS_RECORDS_DELETE):
            return True
        return self.member_has_any_role(member, self.role_ids(panel, "delete_roles"), guild_id)

    def can_reopen(self, member, panel, guild_id=None, record=None):
        if self.is_fine_record(record):
            return self.can_manage_fine_ticket_action(guild_id, member, record)
        if self.has_ticket_permission(guild_id, member, PERMISSION_TICKETS_RECORDS_REOPEN):
            return True
        return self.member_has_any_role(member, self.role_ids(panel, "reopen_roles"), guild_id)

    def can_manage_fine_ticket_action(self, guild_id, member, record):
        guild_id = guild_id or getattr(getattr(member, "guild", None), "id", None)
        if PermissionService.is_administrator(member):
            return True

        resolver_role_id = int(record.get("resolver_role_id") or 0)
        if resolver_role_id and any(role.id == resolver_role_id for role in getattr(member, "roles", []) or []):
            return True

        permission_service = getattr(self, "permission_service", None)
        if not guild_id or not permission_service:
            return False

        return (
            permission_service.has_module_access(
                guild_id,
                "tickets",
                member=member,
                required_permissions=(
                    PERMISSION_TICKETS_RECORDS_CLOSE,
                    PERMISSION_TICKETS_RECORDS_REOPEN,
                    PERMISSION_TICKETS_RECORDS_DELETE,
                ),
            )
            or permission_service.has_module_access(
                guild_id,
                "fines",
                member=member,
                required_permissions=(PERMISSION_FINES_RECORDS_MANAGE,),
            )
        )

    async def apply_fine_ticket_permissions(self, interaction, record, *, closed):
        if not self.is_fine_record(record):
            return

        owner_id = int(record.get("owner_id", 0) or 0)
        owner = interaction.guild.get_member(owner_id) if owner_id else None
        if owner is not None:
            await interaction.channel.set_permissions(
                owner,
                view_channel=not closed,
                send_messages=not closed,
                read_message_history=not closed,
                attach_files=not closed,
                embed_links=not closed,
            )

        resolver_role_id = int(record.get("resolver_role_id") or 0)
        resolver_role = interaction.guild.get_role(resolver_role_id) if resolver_role_id else None
        if resolver_role is not None:
            await interaction.channel.set_permissions(
                resolver_role,
                view_channel=True,
                send_messages=not closed,
                read_message_history=True,
            )

    def ticket_role_permissions(self, panel):
        if not isinstance(panel, dict):
            return {}

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
            | self.role_ids(panel, "add_member_roles")
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

    def ticket_owner_permissions(self, panel):
        if not isinstance(panel, dict):
            return set(DEFAULT_TICKET_OWNER_PERMISSION_KEYS)

        permissions = panel.get("permissions", {}) if isinstance(panel.get("permissions"), dict) else {}
        owner_permissions = permissions.get("owner_permissions")
        if not isinstance(owner_permissions, list):
            return set(DEFAULT_TICKET_OWNER_PERMISSION_KEYS)

        keys = {
            str(key)
            for key in owner_permissions
            if str(key) in TICKET_CHANNEL_PERMISSION_KEYS
        }
        return keys

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

    def closed_ticket_owner_overwrite(self):
        return discord.PermissionOverwrite(**{
            key: False
            for key in TICKET_CHANNEL_PERMISSION_KEYS
        })

    def added_ticket_users(self, record):
        added_users = record.get("added_users") if isinstance(record, dict) else []
        if not isinstance(added_users, list):
            return []
        return [
            entry
            for entry in added_users
            if isinstance(entry, dict) and str(entry.get("id") or "").isdigit()
        ]

    def is_user_added_to_ticket(self, record, member):
        member_id = str(getattr(member, "id", "") or "")
        return any(str(entry.get("id") or "") == member_id for entry in self.added_ticket_users(record))

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
    def selected_panel_option(panel, option_id):
        return next(
            (
                item
                for item in panel.get("options", [])
                if str(item.get("id")) == str(option_id)
            ),
            {},
        )

    @staticmethod
    def option_or_panel_value(panel, option, key):
        value = option.get(key) if isinstance(option, dict) else ""
        return value if str(value or "").strip() else panel.get(key)

    @staticmethod
    def format_open_message(value, *, interaction, panel, record, channel, option_id):
        option = TicketRuntimeCog.selected_panel_option(panel, option_id)
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
            interaction.user: self.ticket_permission_overwrite(self.ticket_owner_permissions(panel)),
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
            self.release_reserved_ticket_record(guild.id, panel_id, number, option_id)
            await interaction.response.send_message("No puedo crear el canal del ticket. Revisa mis permisos.", ephemeral=True)
            return
        except discord.HTTPException:
            self.release_reserved_ticket_record(guild.id, panel_id, number, option_id)
            await interaction.response.send_message("No pude crear el canal del ticket.", ephemeral=True)
            return

        self.update_reserved_ticket_record(guild.id, panel_id, number, channel_id=channel.id, channel_name=channel.name, option_id=option_id)
        option = self.selected_panel_option(panel, option_id)

        format_value = lambda value: self.format_open_message(
            value,
            interaction=interaction,
            panel=panel,
            record=record,
            channel=channel,
            option_id=option_id,
        )
        content = format_value(self.option_or_panel_value(panel, option, "ticket_open_content"))
        title = format_value(self.option_or_panel_value(panel, option, "ticket_open_title"))
        description = format_value(self.option_or_panel_value(panel, option, "ticket_open_description"))
        footer = format_value(self.option_or_panel_value(panel, option, "ticket_open_footer"))
        image_url = str(self.option_or_panel_value(panel, option, "ticket_open_image_url") or "").strip()
        thumbnail_url = str(self.option_or_panel_value(panel, option, "ticket_open_thumbnail_url") or "").strip()
        color_value = str(self.option_or_panel_value(panel, option, "ticket_open_color") or "").strip()
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
        if not self.can_claim(interaction.user, panel, interaction.guild.id):
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

    async def add_member_to_ticket(self, interaction, channel_id, member):
        data, record = self.get_record(interaction.guild.id, channel_id)
        if not record:
            await interaction.response.send_message("No encontre este ticket.", ephemeral=True)
            return

        panel = self.find_panel(interaction.guild.id, record.get("panel_id"))
        if not self.can_add_member(interaction.user, panel, interaction.guild.id):
            await interaction.response.send_message("No tienes permiso para agregar personas a este ticket.", ephemeral=True)
            return

        if record.get("status") != "open":
            await interaction.response.send_message("Solo puedes agregar personas a tickets abiertos.", ephemeral=True)
            return

        if getattr(member, "bot", False):
            await interaction.response.send_message("No puedes agregar bots a un ticket.", ephemeral=True)
            return

        if str(member.id) == str(record.get("owner_id") or ""):
            await interaction.response.send_message("Esa persona ya es quien abrio el ticket.", ephemeral=True)
            return

        if self.is_user_added_to_ticket(record, member):
            await interaction.response.send_message("Esa persona ya tiene acceso a este ticket.", ephemeral=True)
            return

        try:
            await interaction.channel.set_permissions(
                member,
                overwrite=self.ticket_permission_overwrite(self.ticket_owner_permissions(panel)),
            )
        except discord.Forbidden:
            await interaction.response.send_message("No pude ajustar los permisos del canal. Revisa mis permisos.", ephemeral=True)
            return

        added_users = record.get("added_users")
        if not isinstance(added_users, list):
            added_users = []
            record["added_users"] = added_users
        added_users.append({
            "id": str(member.id),
            "name": member.display_name,
            "added_by_id": str(interaction.user.id),
            "added_by_name": interaction.user.display_name,
            "added_at": datetime.now().strftime("%d/%m/%Y | %H:%M"),
        })
        self.save_records(data)
        await interaction.response.send_message(
            f"{member.mention} fue agregado al ticket por {interaction.user.mention}.",
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )

    async def close_ticket_prompt(self, interaction, channel_id):
        data, record = self.get_record(interaction.guild.id, channel_id)
        panel = self.find_panel(interaction.guild.id, record.get("panel_id")) if record else None
        if not record:
            await interaction.response.send_message("No encontre este ticket.", ephemeral=True)
            return

        if self.is_ticket_deleted(record):
            await interaction.response.send_message("Este ticket fue eliminado y ya no puede cerrarse.", ephemeral=True)
            return

        if not self.can_close(interaction.user, panel, record, interaction.guild.id):
            await interaction.response.send_message("No tienes permiso para cerrar este ticket.", ephemeral=True)
            return

        await interaction.response.send_message("Confirma que quieres cerrar este ticket.", view=self.close_confirm_controls(channel_id), ephemeral=True)

    async def close_ticket_confirm(self, interaction, channel_id):
        data, record = self.get_record(interaction.guild.id, channel_id)
        if not record:
            await interaction.response.send_message("No encontre este ticket.", ephemeral=True)
            return

        if self.is_ticket_deleted(record):
            await interaction.response.send_message("Este ticket fue eliminado y ya no puede cerrarse.", ephemeral=True)
            return

        panel = self.find_panel(interaction.guild.id, record.get("panel_id"))
        if not self.can_close(interaction.user, panel, record, interaction.guild.id):
            await interaction.response.send_message("No tienes permiso para cerrar este ticket.", ephemeral=True)
            return

        if record.get("status") != "open":
            await interaction.response.send_message("Este ticket ya no esta abierto.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        record["status"] = "closed"
        record["closed_at"] = datetime.now().strftime("%d/%m/%Y | %H:%M")
        self.save_records(data)
        self.schedule_ticket_channel_rename(interaction, data, record, closed=True)
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
                    overwrite=self.closed_ticket_owner_overwrite(),
                )
            for added_user in self.added_ticket_users(record):
                member = interaction.guild.get_member(int(added_user.get("id") or 0))
                if member is not None:
                    await interaction.channel.set_permissions(
                        member,
                        overwrite=self.closed_ticket_owner_overwrite(),
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
            await self.apply_fine_ticket_permissions(interaction, record, closed=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "Marque el ticket como cerrado, pero no pude ajustar los permisos del canal. Revisa mis permisos.",
                ephemeral=True,
            )
            return
        await interaction.channel.send("Ticket cerrado.", view=self.closed_controls(channel_id))
        await interaction.followup.send("Ticket cerrado.", ephemeral=True)

    async def reopen_ticket(self, interaction, channel_id):
        data, record = self.get_record(interaction.guild.id, channel_id)
        if not record:
            await interaction.response.send_message("No encontre este ticket.", ephemeral=True)
            return

        if self.is_ticket_deleted(record):
            await interaction.response.send_message("Este ticket fue eliminado y ya no puede reabrirse.", ephemeral=True)
            return

        panel = self.find_panel(interaction.guild.id, record.get("panel_id"))
        if not self.can_reopen(interaction.user, panel, interaction.guild.id, record):
            await interaction.response.send_message("No tienes permiso para reabrir este ticket.", ephemeral=True)
            return

        if record.get("status") != "closed":
            await interaction.response.send_message("Solo puedes reabrir tickets cerrados.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        record["status"] = "open"
        record["reopened_at"] = datetime.now().strftime("%d/%m/%Y | %H:%M")
        record["closed_at"] = ""
        self.save_records(data)
        self.schedule_ticket_channel_rename(interaction, data, record, closed=False)

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
                    overwrite=self.ticket_permission_overwrite(self.ticket_owner_permissions(panel)),
                )
            for added_user in self.added_ticket_users(record):
                member = interaction.guild.get_member(int(added_user.get("id") or 0))
                if member is not None:
                    await interaction.channel.set_permissions(
                        member,
                        overwrite=self.ticket_permission_overwrite(self.ticket_owner_permissions(panel)),
                    )

            for role_id, permission_keys in self.ticket_role_permissions(panel).items():
                role = interaction.guild.get_role(role_id)
                if role:
                    await interaction.channel.set_permissions(
                        role,
                        overwrite=self.ticket_permission_overwrite(permission_keys),
                    )
            await self.apply_fine_ticket_permissions(interaction, record, closed=False)
        except discord.Forbidden:
            await interaction.followup.send(
                "Marque el ticket como abierto, pero no pude ajustar los permisos del canal. Revisa mis permisos.",
                ephemeral=True,
            )
            return

        await interaction.channel.send(
            f"Ticket reabierto por {interaction.user.mention}.",
            view=self.ticket_controls(channel_id),
        )
        await interaction.followup.send("Ticket reabierto.", ephemeral=True)

    async def transcript_ticket(self, interaction, channel_id):
        data, record = self.get_record(interaction.guild.id, channel_id)
        if not record:
            await interaction.response.send_message("No encontre este ticket.", ephemeral=True)
            return

        panel = self.find_panel(interaction.guild.id, record.get("panel_id"))
        can_transcript = (
            self.has_ticket_permission(interaction.guild.id, interaction.user, PERMISSION_TICKETS_RECORDS_TRANSCRIPT)
            or (
            self.can_close(interaction.user, panel, record, interaction.guild.id)
            or self.can_delete(interaction.user, panel, interaction.guild.id, record)
            )
        )
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
        if not record:
            await interaction.response.send_message("No encontre este ticket.", ephemeral=True)
            return

        if not self.can_delete(interaction.user, panel, interaction.guild.id, record):
            await interaction.response.send_message("No tienes permiso para eliminar este ticket.", ephemeral=True)
            return

        if record.get("status") not in {"closed", "deleted"}:
            await interaction.response.send_message("Primero cierra el ticket antes de eliminarlo.", ephemeral=True)
            return

        if not self.soft_delete_ticket_record(record):
            await interaction.response.send_message("No encontre la multa asociada a este ticket.", ephemeral=True)
            return

        self.save_records(data)
        await interaction.response.send_message("Eliminando ticket...", ephemeral=True)
        await interaction.channel.delete(reason=f"Ticket eliminado por {interaction.user}")

    async def transcript_and_delete_ticket(self, interaction, channel_id):
        data, record = self.get_record(interaction.guild.id, channel_id)
        panel = self.find_panel(interaction.guild.id, record.get("panel_id")) if record else None
        if not record:
            await interaction.response.send_message("No encontre este ticket.", ephemeral=True)
            return

        if not self.can_delete(interaction.user, panel, interaction.guild.id, record):
            await interaction.response.send_message("No tienes permiso para transcribir y eliminar este ticket.", ephemeral=True)
            return

        if record.get("status") not in {"closed", "deleted"}:
            await interaction.response.send_message("Primero cierra el ticket para guardar la transcripcion final.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.save_ticket_transcript(interaction, channel_id, data, record)
        if not self.soft_delete_ticket_record(record):
            await interaction.followup.send("No encontre la multa asociada a este ticket.", ephemeral=True)
            return
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
        name="agregar-a-ticket",
        description="Agrega otra persona al ticket del canal actual.",
    )
    @app_commands.describe(usuario="Persona que recibira acceso al ticket.")
    @app_commands.guild_only()
    async def add_member_ticket_command(self, interaction: discord.Interaction, usuario: discord.Member):
        if not interaction.channel_id:
            await interaction.response.send_message(
                "Este comando solo funciona dentro de un canal de ticket.",
                ephemeral=True,
            )
            return

        await self.add_member_to_ticket(interaction, interaction.channel_id, usuario)

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

    @app_commands.command(
        name="reabrir-ticket",
        description="Reabre el ticket cerrado del canal actual.",
    )
    @app_commands.guild_only()
    async def reopen_ticket_command(self, interaction: discord.Interaction):
        if not interaction.channel_id:
            await interaction.response.send_message(
                "Este comando solo funciona dentro de un canal de ticket.",
                ephemeral=True,
            )
            return

        await self.reopen_ticket(interaction, interaction.channel_id)

    @app_commands.command(
        name="eliminar-ticket",
        description="Elimina el ticket del canal actual.",
    )
    @app_commands.guild_only()
    async def delete_ticket_command(self, interaction: discord.Interaction):
        if not interaction.channel_id:
            await interaction.response.send_message(
                "Este comando solo funciona dentro de un canal de ticket.",
                ephemeral=True,
            )
            return

        await self.delete_ticket(interaction, interaction.channel_id)

    @app_commands.command(
        name="eliminar-y-transcribir-ticket",
        description="Guarda la transcripcion y elimina el ticket del canal actual.",
    )
    @app_commands.guild_only()
    async def transcript_delete_ticket_command(self, interaction: discord.Interaction):
        if not interaction.channel_id:
            await interaction.response.send_message(
                "Este comando solo funciona dentro de un canal de ticket.",
                ephemeral=True,
            )
            return

        await self.transcript_and_delete_ticket(interaction, interaction.channel_id)

    @commands.Cog.listener()
    async def on_interaction(self, interaction):
        try:
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

            if custom_id.startswith("ticket_runtime_transcript_delete:"):
                await self.transcript_and_delete_ticket(interaction, custom_id.split(":", 1)[1])
                return

            if custom_id.startswith("ticket_runtime_transcript:"):
                await self.transcript_ticket(interaction, custom_id.split(":", 1)[1])
                return

            if custom_id.startswith("ticket_runtime_delete:"):
                await self.delete_ticket(interaction, custom_id.split(":", 1)[1])
                return
        except Exception as exc:
            log_exception(f"Error en interaccion de tickets {describe_interaction(interaction)}", exc)
            await send_safe_interaction_error(interaction)


async def setup(bot):
    await bot.add_cog(TicketRuntimeCog(bot))
