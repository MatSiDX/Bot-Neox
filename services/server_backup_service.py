from repositories.config_repository import ConfigRepository
from repositories.permission_repository import PermissionRepository
from repositories.server_backup_repository import ServerBackupRepository


SERVER_BACKUP_SCHEMA_VERSION = 1


CHANNEL_TYPE_NAMES = {
    0: "text",
    2: "voice",
    4: "category",
    5: "announcement",
    10: "announcement_thread",
    11: "public_thread",
    12: "private_thread",
    13: "stage_voice",
    15: "forum",
    16: "media",
}


class ServerBackupService:
    def __init__(
        self,
        *,
        backup_repo=None,
        config_repo=None,
        permission_repo=None,
        fetch_guild_summary=None,
        fetch_roles=None,
        fetch_channels=None,
    ):
        self.backup_repo = backup_repo or ServerBackupRepository()
        self.config_repo = config_repo or ConfigRepository()
        self.permission_repo = permission_repo or PermissionRepository()
        self.fetch_guild_summary = fetch_guild_summary
        self.fetch_roles = fetch_roles
        self.fetch_channels = fetch_channels

    def list_backups(self, guild_id):
        return self.backup_repo.list_for_guild(guild_id)

    def get_backup(self, backup_id, *, guild_id):
        return self.backup_repo.get(backup_id, guild_id=guild_id)

    def create_backup(
        self,
        *,
        guild_id,
        guild_name="",
        created_by=None,
        replace_oldest=False,
        replace_backup_id=None,
    ):
        if not self.fetch_roles or not self.fetch_channels:
            raise RuntimeError("No hay fetchers de Discord configurados para crear backups.")

        guild_id = str(guild_id or "")
        guild_summary = self._safe_guild_summary(guild_id)
        effective_guild_name = str(guild_summary.get("name") or guild_name or f"Servidor {guild_id}")
        roles = self.fetch_roles(guild_id) or []
        channels = self.fetch_channels(guild_id) or []
        backup = self._build_payload(
            guild_id=guild_id,
            guild_name=effective_guild_name,
            guild_summary=guild_summary,
            roles=roles,
            channels=channels,
        )
        summary = self._build_summary(backup)
        actor = created_by or {}
        return self.backup_repo.create(
            guild_id=guild_id,
            guild_name=effective_guild_name,
            created_by_id=actor.get("id", ""),
            created_by_name=actor.get("username", ""),
            schema_version=SERVER_BACKUP_SCHEMA_VERSION,
            backup=backup,
            summary=summary,
            replace_oldest=replace_oldest,
            replace_backup_id=replace_backup_id,
        )

    def _build_payload(self, *, guild_id, guild_name, guild_summary, roles, channels):
        categories = [channel for channel in channels if self._int(channel.get("type"), -1) == 4]
        non_category_channels = [channel for channel in channels if self._int(channel.get("type"), -1) != 4]
        return {
            "schema_version": SERVER_BACKUP_SCHEMA_VERSION,
            "source": "neox_dashboard_server_backup",
            "guild": {
                "id": guild_id,
                "name": guild_name,
                "original_id": guild_id,
                "features": list(guild_summary.get("features") or []),
                "verification_level": guild_summary.get("verification_level"),
                "default_message_notifications": guild_summary.get("default_message_notifications"),
                "explicit_content_filter": guild_summary.get("explicit_content_filter"),
            },
            "roles": [self._serialize_role(role) for role in sorted(roles, key=lambda item: self._int(item.get("position")))],
            "categories": [self._serialize_channel(channel) for channel in sorted(categories, key=self._channel_sort_key)],
            "channels": [self._serialize_channel(channel) for channel in sorted(non_category_channels, key=self._channel_sort_key)],
            "bot_config": self._serialize_bot_config(guild_id),
        }

    def _serialize_role(self, role):
        role_id = str(role.get("id") or "")
        return {
            "id": role_id,
            "original_id": role_id,
            "name": str(role.get("name") or ""),
            "color": self._int(role.get("color")),
            "permissions": str(role.get("permissions") or "0"),
            "position": self._int(role.get("position")),
            "hoist": bool(role.get("hoist")),
            "mentionable": bool(role.get("mentionable")),
            "managed": bool(role.get("managed")),
        }

    def _serialize_channel(self, channel):
        channel_id = str(channel.get("id") or "")
        channel_type = self._int(channel.get("type"), -1)
        payload = {
            "id": channel_id,
            "original_id": channel_id,
            "name": str(channel.get("name") or ""),
            "type": CHANNEL_TYPE_NAMES.get(channel_type, str(channel_type)),
            "type_id": channel_type,
            "position": self._int(channel.get("position")),
            "parent_id": str(channel.get("parent_id") or ""),
            "permission_overwrites": [
                self._serialize_overwrite(overwrite)
                for overwrite in channel.get("permission_overwrites") or []
            ],
        }
        for source_key, target_key in (
            ("topic", "topic"),
            ("nsfw", "nsfw"),
            ("rate_limit_per_user", "slowmode"),
            ("bitrate", "bitrate"),
            ("user_limit", "user_limit"),
        ):
            if source_key in channel and channel.get(source_key) is not None:
                payload[target_key] = channel.get(source_key)
        return payload

    def _serialize_overwrite(self, overwrite):
        overwrite_id = str(overwrite.get("id") or "")
        overwrite_type = self._int(overwrite.get("type"), -1)
        return {
            "id": overwrite_id,
            "original_id": overwrite_id,
            "type": "member" if overwrite_type == 1 else "role",
            "type_id": overwrite_type,
            "allow": str(overwrite.get("allow") or "0"),
            "deny": str(overwrite.get("deny") or "0"),
        }

    def _serialize_bot_config(self, guild_id):
        return {
            "guild_config": self.config_repo.get_guild_config(guild_id),
            "role_permissions": self.permission_repo.get_permissions(guild_id),
        }

    def _build_summary(self, backup):
        bot_config = backup.get("bot_config") or {}
        return {
            "roles": len(backup.get("roles") or []),
            "categories": len(backup.get("categories") or []),
            "channels": len(backup.get("channels") or []),
            "permission_overwrites": sum(
                len(item.get("permission_overwrites") or [])
                for item in (backup.get("categories") or []) + (backup.get("channels") or [])
            ),
            "bot_config_keys": len(bot_config.get("guild_config") or {}),
            "bot_permission_roles": len(bot_config.get("role_permissions") or {}),
        }

    def _safe_guild_summary(self, guild_id):
        if not self.fetch_guild_summary:
            return {}
        summary = self.fetch_guild_summary(guild_id)
        return summary if isinstance(summary, dict) else {}

    def _channel_sort_key(self, channel):
        return (
            str(channel.get("parent_id") or ""),
            self._int(channel.get("position")),
            str(channel.get("name") or "").casefold(),
            str(channel.get("id") or ""),
        )

    @staticmethod
    def _int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
