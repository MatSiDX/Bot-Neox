import asyncio
from dataclasses import dataclass

import discord

from repositories.config_repository import ConfigRepository
from repositories.permission_repository import PermissionRepository


SERVER_TEMPLATE_ACTION_APPLY = "server_template_apply"
SERVER_TEMPLATE_ACTION_TYPES = (SERVER_TEMPLATE_ACTION_APPLY,)

MANAGE_ROLES = 0x10000000
MANAGE_CHANNELS = 0x10
MANAGE_GUILD = 0x20
ADMINISTRATOR = 0x8

CHANNEL_CREATORS = {
    0: "text",
    2: "voice",
    4: "category",
    5: "text",
    13: "stage",
    15: "forum",
}


class ServerTemplateValidationError(ValueError):
    pass


@dataclass
class TemplateOptions:
    update_existing: bool = False
    include_bot_config: bool = True
    clear_target: bool = False


class ServerTemplateService:
    def __init__(self, *, config_repo=None, permission_repo=None):
        self.config_repo = config_repo or ConfigRepository()
        self.permission_repo = permission_repo or PermissionRepository()

    def build_preview(self, backup_detail, *, target_guild_id, target_guild_name="", target_roles=None, target_channels=None, options=None):
        options = self._options(options)
        backup = (backup_detail or {}).get("backup") or {}
        roles = self._template_roles(backup)
        categories = backup.get("categories") if isinstance(backup.get("categories"), list) else []
        channels = backup.get("channels") if isinstance(backup.get("channels"), list) else []
        target_roles = target_roles or []
        target_channels = target_channels or []
        existing_role_names = set() if options.clear_target else self._name_counts(role.get("name") for role in target_roles)
        existing_channel_names = set() if options.clear_target else self._channel_name_counts(target_channels)

        role_preview = []
        for role in roles:
            name = str(role.get("name") or "").strip()
            conflict = name.casefold() in existing_role_names
            role_preview.append({
                "original_id": str(role.get("original_id") or role.get("id") or ""),
                "name": name,
                "target_name": name,
                "conflict": conflict,
                "action": "update_existing" if conflict and options.update_existing else "map_existing" if conflict else "create",
                "permissions": str(role.get("permissions") or "0"),
                "color": int(role.get("color") or 0),
            })

        category_preview = [
            self._channel_preview_item(category, existing_channel_names, options, default_type="category")
            for category in categories
        ]
        channel_preview = [
            self._channel_preview_item(channel, existing_channel_names, options)
            for channel in channels
        ]
        overwrite_total = sum(len(item.get("permission_overwrites") or []) for item in categories + channels)
        role_overwrites = sum(
            1
            for item in categories + channels
            for overwrite in item.get("permission_overwrites") or []
            if str(overwrite.get("type") or "role") == "role"
        )
        member_overwrites = max(overwrite_total - role_overwrites, 0)
        bot_config = backup.get("bot_config") if isinstance(backup.get("bot_config"), dict) else {}

        preview = {
            "source": {
                "guild_id": str((backup.get("guild") or {}).get("id") or backup_detail.get("guild_id") or ""),
                "guild_name": str((backup.get("guild") or {}).get("name") or backup_detail.get("guild_name") or ""),
                "backup_id": int(backup_detail.get("id") or 0),
                "created_at": str(backup_detail.get("created_at") or ""),
            },
            "target": {
                "guild_id": str(target_guild_id or ""),
                "guild_name": str(target_guild_name or f"Servidor {target_guild_id}"),
            },
            "options": {
                "update_existing": options.update_existing,
                "include_bot_config": options.include_bot_config,
                "clear_target": options.clear_target,
            },
            "roles_to_create": [item for item in role_preview if item["action"] == "create"],
            "roles_to_update": [item for item in role_preview if item["action"] == "update_existing"],
            "roles_to_map": [item for item in role_preview if item["action"] == "map_existing"],
            "categories_to_create": [item for item in category_preview if item["action"] == "create"],
            "categories_to_update": [item for item in category_preview if item["action"] == "update_existing"],
            "categories_to_map": [item for item in category_preview if item["action"] == "map_existing"],
            "channels_to_create": [item for item in channel_preview if item["action"] == "create"],
            "channels_to_update": [item for item in channel_preview if item["action"] == "update_existing"],
            "channels_to_map": [item for item in channel_preview if item["action"] == "map_existing"],
            "permission_overwrites": {
                "total": overwrite_total,
                "role_overwrites": role_overwrites,
                "member_overwrites_skipped": member_overwrites,
            },
            "bot_config": {
                "enabled": options.include_bot_config,
                "guild_config_keys": len(bot_config.get("guild_config") or {}),
                "role_permission_entries": len(bot_config.get("role_permissions") or {}),
            },
            "warnings": self._preview_warnings(roles, categories, channels, member_overwrites, options),
        }
        return preview

    async def apply_template(self, bot, payload):
        payload = payload if isinstance(payload, dict) else {}
        backup = payload.get("backup") if isinstance(payload.get("backup"), dict) else {}
        if not backup:
            raise ValueError("La solicitud no incluye el backup a aplicar.")
        preview = payload.get("preview") if isinstance(payload.get("preview"), dict) else {}
        options = self._options(payload.get("options"))
        target_guild_id = int(payload.get("target_guild_id") or 0)
        guild = bot.get_guild(target_guild_id)
        if guild is None:
            raise ValueError("El bot no esta conectado al servidor destino.")

        bot_member = guild.me or guild.get_member(bot.user.id if bot.user else 0)
        if bot_member is None and bot.user:
            bot_member = await guild.fetch_member(bot.user.id)
        if bot_member is None:
            raise ValueError("No pude resolver el miembro del bot en el servidor destino.")

        guild_permissions = bot_member.guild_permissions
        if not (guild_permissions.administrator or (guild_permissions.manage_roles and guild_permissions.manage_channels)):
            raise PermissionError("El bot necesita Gestionar roles y Gestionar canales en el servidor destino.")

        result = {
            "guild_id": str(guild.id),
            "guild_name": guild.name,
            "backup_id": preview.get("source", {}).get("backup_id") or payload.get("backup_id"),
            "created": {"roles": [], "categories": [], "channels": []},
            "updated": {"roles": [], "categories": [], "channels": []},
            "id_map": {"roles": {}, "categories": {}, "channels": {}},
            "skipped_overwrites": [],
            "bot_config": {"applied": False, "guild_config_keys": 0, "role_permission_entries": 0},
            "deleted": {"roles": [], "channels": []},
        }

        if options.clear_target:
            await self._clear_target_guild(guild, result)
            self._clear_bot_config(str(guild.id))

        role_map = {str((backup.get("guild") or {}).get("id") or ""): guild.default_role}
        await self._apply_roles(guild, backup, role_map, result, options)
        category_map = await self._apply_categories(guild, backup, role_map, result, options)
        await self._apply_channels(guild, backup, role_map, category_map, result, options)
        if options.include_bot_config:
            self._apply_bot_config(str(guild.id), backup, result["id_map"])
            bot_config = backup.get("bot_config") if isinstance(backup.get("bot_config"), dict) else {}
            result["bot_config"] = {
                "applied": True,
                "guild_config_keys": len(bot_config.get("guild_config") or {}),
                "role_permission_entries": len(bot_config.get("role_permissions") or {}),
            }
        return result

    async def _apply_roles(self, guild, backup, role_map, result, options):
        existing_by_name = {} if options.clear_target else {role.name.casefold(): role for role in guild.roles}
        used_names = {role.name.casefold() for role in guild.roles}
        roles = self._template_roles(backup)
        for role_data in roles:
            original_id = str(role_data.get("original_id") or role_data.get("id") or "")
            name = str(role_data.get("name") or "").strip()
            if not original_id or not name:
                continue
            existing = existing_by_name.get(name.casefold())
            if existing:
                if options.update_existing:
                    await existing.edit(
                        permissions=discord.Permissions(int(role_data.get("permissions") or 0)),
                        colour=discord.Colour(int(role_data.get("color") or 0)),
                        hoist=bool(role_data.get("hoist")),
                        mentionable=bool(role_data.get("mentionable")),
                        reason="Neox dashboard server template",
                    )
                    result["updated"]["roles"].append({"original_id": original_id, "id": str(existing.id), "name": existing.name})
                role_map[original_id] = existing
                result["id_map"]["roles"][original_id] = str(existing.id)
                await asyncio.sleep(0.25)
                continue

            role = await guild.create_role(
                name=name,
                permissions=discord.Permissions(int(role_data.get("permissions") or 0)),
                colour=discord.Colour(int(role_data.get("color") or 0)),
                hoist=bool(role_data.get("hoist")),
                mentionable=bool(role_data.get("mentionable")),
                reason="Neox dashboard server template",
            )
            used_names.add(role.name.casefold())
            role_map[original_id] = role
            result["id_map"]["roles"][original_id] = str(role.id)
            result["created"]["roles"].append({"original_id": original_id, "id": str(role.id), "name": role.name})
            await asyncio.sleep(0.35)

    async def _apply_categories(self, guild, backup, role_map, result, options):
        category_map = {}
        existing_by_name = {} if options.clear_target else {channel.name.casefold(): channel for channel in guild.categories}
        used_names = {channel.name.casefold() for channel in guild.categories}
        for category_data in backup.get("categories") or []:
            original_id = str(category_data.get("original_id") or category_data.get("id") or "")
            name = str(category_data.get("name") or "").strip()
            if not original_id or not name:
                continue
            overwrites = self._discord_overwrites(category_data, role_map, result)
            existing = existing_by_name.get(name.casefold())
            if existing:
                if options.update_existing:
                    await existing.edit(overwrites=overwrites, reason="Neox dashboard server template")
                    result["updated"]["categories"].append({"original_id": original_id, "id": str(existing.id), "name": existing.name})
                category_map[original_id] = existing
                result["id_map"]["categories"][original_id] = str(existing.id)
                await asyncio.sleep(0.25)
                continue
            category = await guild.create_category(
                name=name,
                overwrites=overwrites,
                reason="Neox dashboard server template",
            )
            used_names.add(category.name.casefold())
            category_map[original_id] = category
            result["id_map"]["categories"][original_id] = str(category.id)
            result["created"]["categories"].append({"original_id": original_id, "id": str(category.id), "name": category.name})
            await asyncio.sleep(0.35)
        return category_map

    async def _apply_channels(self, guild, backup, role_map, category_map, result, options):
        existing_by_key = {} if options.clear_target else {(channel.name.casefold(), getattr(channel, "type", None)): channel for channel in guild.channels}
        used_names = {channel.name.casefold() for channel in guild.channels}
        for channel_data in backup.get("channels") or []:
            original_id = str(channel_data.get("original_id") or channel_data.get("id") or "")
            name = str(channel_data.get("name") or "").strip()
            if not original_id or not name:
                continue
            channel_type_id = int(channel_data.get("type_id") or 0)
            creator = CHANNEL_CREATORS.get(channel_type_id)
            if creator is None:
                result["skipped_overwrites"].append({"channel_original_id": original_id, "reason": f"Tipo de canal no soportado: {channel_type_id}"})
                continue
            overwrites = self._discord_overwrites(channel_data, role_map, result)
            parent = category_map.get(str(channel_data.get("parent_id") or ""))
            target_name = name
            existing = existing_by_key.get((name.casefold(), self._discord_channel_type(channel_type_id)))
            if existing:
                if options.update_existing:
                    await existing.edit(overwrites=overwrites, category=parent, reason="Neox dashboard server template")
                    result["updated"]["channels"].append({"original_id": original_id, "id": str(existing.id), "name": existing.name})
                result["id_map"]["channels"][original_id] = str(existing.id)
                await asyncio.sleep(0.25)
                continue
            channel = await self._create_channel(guild, creator, target_name, channel_data, parent, overwrites)
            used_names.add(channel.name.casefold())
            result["id_map"]["channels"][original_id] = str(channel.id)
            result["created"]["channels"].append({"original_id": original_id, "id": str(channel.id), "name": channel.name})
            await asyncio.sleep(0.35)

    async def _create_channel(self, guild, creator, name, data, parent, overwrites):
        reason = "Neox dashboard server template"
        common = {"name": name, "category": parent, "overwrites": overwrites, "reason": reason}
        if creator == "voice":
            return await guild.create_voice_channel(
                **common,
                bitrate=int(data.get("bitrate") or 64000),
                user_limit=int(data.get("user_limit") or 0),
            )
        if creator == "stage":
            return await guild.create_stage_channel(**common)
        if creator == "forum" and hasattr(guild, "create_forum"):
            return await guild.create_forum(**common)
        return await guild.create_text_channel(
            **common,
            topic=str(data.get("topic") or "")[:1024] or None,
            nsfw=bool(data.get("nsfw")),
            slowmode_delay=int(data.get("slowmode") or 0),
        )

    async def _clear_target_guild(self, guild, result):
        reason = "Neox dashboard server template clear target"
        for channel in sorted(guild.channels, key=lambda item: 0 if not isinstance(item, discord.CategoryChannel) else 1):
            await channel.delete(reason=reason)
            result["deleted"]["channels"].append({"id": str(channel.id), "name": channel.name})
            await asyncio.sleep(0.35)

        bot_top_role = guild.me.top_role if guild.me else None
        removable_roles = [
            role for role in guild.roles
            if role != guild.default_role
            and not role.managed
            and (bot_top_role is None or role < bot_top_role)
        ]
        for role in sorted(removable_roles, key=lambda item: item.position, reverse=True):
            await role.delete(reason=reason)
            result["deleted"]["roles"].append({"id": str(role.id), "name": role.name})
            await asyncio.sleep(0.35)

    def _clear_bot_config(self, target_guild_id):
        config = self.config_repo.load()
        config.pop(str(target_guild_id), None)
        self.config_repo.save(config)
        self.permission_repo.set_guild_permissions(str(target_guild_id), {})

    def _discord_overwrites(self, channel_data, role_map, result):
        overwrites = {}
        for overwrite in channel_data.get("permission_overwrites") or []:
            if str(overwrite.get("type") or "role") != "role":
                result["skipped_overwrites"].append({
                    "channel_original_id": str(channel_data.get("original_id") or channel_data.get("id") or ""),
                    "overwrite_original_id": str(overwrite.get("original_id") or overwrite.get("id") or ""),
                    "reason": "Los overwrites de miembros no se copian entre servidores.",
                })
                continue
            target = role_map.get(str(overwrite.get("original_id") or overwrite.get("id") or ""))
            if target is None:
                result["skipped_overwrites"].append({
                    "channel_original_id": str(channel_data.get("original_id") or channel_data.get("id") or ""),
                    "overwrite_original_id": str(overwrite.get("original_id") or overwrite.get("id") or ""),
                    "reason": "No pude mapear el rol del overwrite.",
                })
                continue
            overwrites[target] = discord.PermissionOverwrite.from_pair(
                discord.Permissions(int(overwrite.get("allow") or 0)),
                discord.Permissions(int(overwrite.get("deny") or 0)),
            )
        return overwrites

    def _apply_bot_config(self, target_guild_id, backup, id_map):
        bot_config = backup.get("bot_config") if isinstance(backup.get("bot_config"), dict) else {}
        channel_map = id_map.get("channels") or {}
        channel_map.update(id_map.get("categories") or {})
        for key, value in (bot_config.get("guild_config") or {}).items():
            mapped = channel_map.get(str(value)) or id_map.get("roles", {}).get(str(value)) or value
            self.config_repo.set_value(target_guild_id, key, mapped)

        mapped_permissions = {}
        for role_id, permissions in (bot_config.get("role_permissions") or {}).items():
            mapped_role_id = id_map.get("roles", {}).get(str(role_id))
            if mapped_role_id:
                mapped_permissions[mapped_role_id] = permissions
        self.permission_repo.set_guild_permissions(target_guild_id, mapped_permissions)

    def _channel_preview_item(self, channel, existing_names, options, default_type=None):
        name = str(channel.get("name") or "").strip()
        channel_type = default_type or str(channel.get("type") or channel.get("type_id") or "channel")
        type_id = 4 if default_type == "category" else int(channel.get("type_id") or 0)
        key = (name.casefold(), str(type_id))
        conflict = key in existing_names or (name.casefold(), channel_type) in existing_names
        return {
            "original_id": str(channel.get("original_id") or channel.get("id") or ""),
            "name": name,
            "target_name": name,
            "type": channel_type,
            "type_id": type_id,
            "parent_id": str(channel.get("parent_id") or ""),
            "overwrites": len(channel.get("permission_overwrites") or []),
            "conflict": conflict,
            "action": "update_existing" if conflict and options.update_existing else "map_existing" if conflict else "create",
        }

    def _preview_warnings(self, roles, categories, channels, member_overwrites, options):
        warnings = []
        if options.clear_target:
            warnings.append("Modo limpieza activado: se eliminaran canales, roles y configuracion local del bot en el servidor destino antes de aplicar.")
        managed_roles = [role.get("name") for role in roles if role.get("managed")]
        if managed_roles:
            warnings.append(f"{len(managed_roles)} roles administrados por integraciones no se copiaran.")
        if member_overwrites:
            warnings.append(f"{member_overwrites} overwrites de miembros se omitiran porque no son portables entre servidores.")
        unsupported = [channel for channel in channels if int(channel.get("type_id") or 0) not in CHANNEL_CREATORS]
        if unsupported:
            warnings.append(f"{len(unsupported)} canales tienen un tipo no soportado para creacion automatica.")
        if not categories and not channels and not roles:
            warnings.append("El backup no contiene estructura portable.")
        return warnings

    def _template_roles(self, backup):
        roles = backup.get("roles") if isinstance(backup.get("roles"), list) else []
        return [
            role for role in roles
            if str(role.get("name") or "") != "@everyone" and not role.get("managed")
        ]

    def _options(self, options):
        options = options if isinstance(options, dict) else {}
        return TemplateOptions(
            update_existing=bool(options.get("update_existing")),
            include_bot_config=options.get("include_bot_config") is not False,
            clear_target=bool(options.get("clear_target")),
        )

    def _name_counts(self, names):
        return {str(name or "").casefold() for name in names if str(name or "").strip()}

    def _channel_name_counts(self, channels):
        return {
            (str(channel.get("name") or "").casefold(), str(channel.get("type") or channel.get("type_id") or ""))
            for channel in channels
            if str(channel.get("name") or "").strip()
        }

    def _discord_channel_type(self, type_id):
        return {
            0: discord.ChannelType.text,
            2: discord.ChannelType.voice,
            4: discord.ChannelType.category,
            5: discord.ChannelType.news,
            13: discord.ChannelType.stage_voice,
            15: discord.ChannelType.forum,
        }.get(int(type_id or 0))
