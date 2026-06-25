from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable


MetadataFetcher = Callable[[str], list]


@dataclass(frozen=True)
class DiscordMetadataCacheSettings:
    roles_ttl_seconds: int = 900
    channels_ttl_seconds: int = 300
    categories_ttl_seconds: int = 300
    emojis_ttl_seconds: int = 1800
    stale_fallback_seconds: int = 3600


@dataclass
class _CacheEntry:
    value: list
    fetched_at: float
    expires_at: float

    def is_fresh(self, now: float) -> bool:
        return now < self.expires_at

    def is_usable_stale(self, now: float, stale_fallback_seconds: int) -> bool:
        max_age = self.expires_at + max(0, int(stale_fallback_seconds))
        return now <= max_age


class DiscordMetadataService:
    def __init__(
        self,
        *,
        fetch_channels: MetadataFetcher,
        fetch_roles: MetadataFetcher,
        fetch_emojis: MetadataFetcher,
        cache_settings: DiscordMetadataCacheSettings | None = None,
        now_func: Callable[[], float] | None = None,
    ):
        self.fetch_channels = fetch_channels
        self.fetch_roles = fetch_roles
        self.fetch_emojis = fetch_emojis
        self.cache_settings = cache_settings or DiscordMetadataCacheSettings()
        self.now_func = now_func or time.time
        self._lock = threading.RLock()
        self._cache: dict[tuple[str, str], _CacheEntry] = {}

    def invalidate(self, guild_id: str | None = None, *, kinds: list[str] | tuple[str, ...] | None = None):
        with self._lock:
            if guild_id is None and not kinds:
                self._cache.clear()
                return

            normalized_kinds = set(self._normalize_kinds(kinds))
            normalized_guild_id = str(guild_id or "")
            keys_to_delete = []
            for cached_guild_id, kind in self._cache.keys():
                if normalized_guild_id and cached_guild_id != normalized_guild_id:
                    continue
                if normalized_kinds and kind not in normalized_kinds:
                    continue
                keys_to_delete.append((cached_guild_id, kind))

            for key in keys_to_delete:
                self._cache.pop(key, None)

    def get_channels(self, guild_id: str, *, force_refresh: bool = False) -> list:
        return list(self._get_channel_bundle(guild_id, force_refresh=force_refresh)["channels"])

    def get_categories(self, guild_id: str, *, force_refresh: bool = False) -> list:
        return list(self._get_channel_bundle(guild_id, force_refresh=force_refresh)["categories"])

    def get_roles(self, guild_id: str, *, force_refresh: bool = False) -> list:
        return list(
            self._get_or_refresh(
                str(guild_id),
                "roles",
                ttl_seconds=self.cache_settings.roles_ttl_seconds,
                loader=lambda current_guild_id: self._serialize_roles(self.fetch_roles(current_guild_id)),
                force_refresh=force_refresh,
            )
        )

    def get_emojis(self, guild_id: str, *, force_refresh: bool = False) -> list:
        return list(
            self._get_or_refresh(
                str(guild_id),
                "emojis",
                ttl_seconds=self.cache_settings.emojis_ttl_seconds,
                loader=lambda current_guild_id: self._serialize_emojis(self.fetch_emojis(current_guild_id)),
                force_refresh=force_refresh,
            )
        )

    def get_guild_metadata(
        self,
        guild_id: str,
        *,
        kinds: list[str] | tuple[str, ...] | None = None,
        force_refresh: bool = False,
    ) -> dict[str, list]:
        guild_id = str(guild_id or "")
        payload: dict[str, list] = {}
        normalized_kinds = self._normalize_kinds(kinds)
        channel_bundle = None
        if "channels" in normalized_kinds or "categories" in normalized_kinds:
            channel_bundle = self._get_channel_bundle(guild_id, force_refresh=force_refresh)

        for kind in normalized_kinds:
            if kind == "channels":
                payload["channels"] = list((channel_bundle or {}).get("channels", []))
            elif kind == "categories":
                payload["categories"] = list((channel_bundle or {}).get("categories", []))
            elif kind == "roles":
                payload["roles"] = self.get_roles(guild_id, force_refresh=force_refresh)
            elif kind == "emojis":
                payload["emojis"] = self.get_emojis(guild_id, force_refresh=force_refresh)
        return payload

    def _normalize_kinds(self, kinds):
        if not kinds:
            kinds = ("channels", "categories", "roles", "emojis")

        normalized = []
        for kind in kinds:
            clean_kind = str(kind or "").strip().lower()
            if clean_kind in {"channels", "categories", "roles", "emojis"} and clean_kind not in normalized:
                normalized.append(clean_kind)
        return normalized

    def _get_channel_bundle(self, guild_id: str, *, force_refresh: bool = False) -> dict[str, list]:
        guild_id = str(guild_id or "")
        if not guild_id:
            return {"channels": [], "categories": []}

        now = self.now_func()
        with self._lock:
            channels_entry = self._cache.get((guild_id, "channels"))
            categories_entry = self._cache.get((guild_id, "categories"))
            if (
                not force_refresh
                and channels_entry
                and categories_entry
                and channels_entry.is_fresh(now)
                and categories_entry.is_fresh(now)
            ):
                return {
                    "channels": list(channels_entry.value),
                    "categories": list(categories_entry.value),
                }

        try:
            raw_channels = self.fetch_channels(guild_id)
            bundle = self._serialize_channel_bundle(raw_channels)
            self._store_entry(guild_id, "channels", bundle["channels"], self.cache_settings.channels_ttl_seconds)
            self._store_entry(guild_id, "categories", bundle["categories"], self.cache_settings.categories_ttl_seconds)
            return {
                "channels": list(bundle["channels"]),
                "categories": list(bundle["categories"]),
            }
        except Exception:
            with self._lock:
                channels_entry = self._cache.get((guild_id, "channels"))
                categories_entry = self._cache.get((guild_id, "categories"))
                if (
                    channels_entry
                    and categories_entry
                    and channels_entry.is_usable_stale(now, self.cache_settings.stale_fallback_seconds)
                    and categories_entry.is_usable_stale(now, self.cache_settings.stale_fallback_seconds)
                ):
                    return {
                        "channels": list(channels_entry.value),
                        "categories": list(categories_entry.value),
                    }
            raise

    def _get_or_refresh(self, guild_id: str, kind: str, *, ttl_seconds: int, loader, force_refresh: bool):
        guild_id = str(guild_id or "")
        if not guild_id:
            return []

        now = self.now_func()
        with self._lock:
            entry = self._cache.get((guild_id, kind))
            if entry and not force_refresh and entry.is_fresh(now):
                return list(entry.value)

        try:
            value = list(loader(guild_id))
            self._store_entry(guild_id, kind, value, ttl_seconds)
            return list(value)
        except Exception:
            with self._lock:
                entry = self._cache.get((guild_id, kind))
                if entry and entry.is_usable_stale(now, self.cache_settings.stale_fallback_seconds):
                    return list(entry.value)
            raise

    def _store_entry(self, guild_id: str, kind: str, value: list, ttl_seconds: int):
        now = self.now_func()
        entry = _CacheEntry(
            value=list(value),
            fetched_at=now,
            expires_at=now + max(1, int(ttl_seconds)),
        )
        with self._lock:
            self._cache[(str(guild_id), kind)] = entry

    @staticmethod
    def _serialize_channel_bundle(raw_channels):
        channels = []
        categories = []
        for channel in raw_channels or []:
            channel_type = int(channel.get("type", -1))
            item = {
                "id": str(channel["id"]),
                "name": str(channel.get("name") or channel["id"]),
            }
            if channel_type in (0, 5):
                channels.append(item)
            elif channel_type == 4:
                categories.append(item)
        return {
            "channels": channels,
            "categories": categories,
        }

    @staticmethod
    def _serialize_roles(raw_roles):
        return [
            {"id": str(role["id"]), "name": str(role.get("name") or role["id"])}
            for role in raw_roles or []
            if str(role.get("name") or "") != "@everyone"
        ]

    @staticmethod
    def _serialize_emojis(raw_emojis):
        return [
            {
                "id": str(emoji["id"]),
                "name": str(emoji.get("name") or emoji["id"]),
                "animated": bool(emoji.get("animated")),
                "value": f"<{'a' if emoji.get('animated') else ''}:{emoji.get('name') or emoji['id']}:{emoji['id']}>",
            }
            for emoji in raw_emojis or []
        ]
