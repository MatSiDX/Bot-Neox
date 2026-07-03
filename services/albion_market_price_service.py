import json
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from config.settings import (
    ALBION_MARKET_CACHE_TTL_SECONDS,
    ALBION_MARKET_LOCATIONS,
    ALBION_MARKET_QUALITIES,
    ALBION_MARKET_SERVER,
    ALBION_MARKET_TIMEOUT_SECONDS,
)
from repositories.albion_price_repository import AlbionPriceRepository


class AlbionMarketPriceError(RuntimeError):
    pass


@dataclass(frozen=True)
class AlbionMarketPriceConfig:
    server: str
    locations: tuple[str, ...]
    qualities: tuple[int, ...]
    cache_ttl_seconds: int
    timeout_seconds: int

    @classmethod
    def from_settings(cls):
        return cls(
            server=normalize_server(ALBION_MARKET_SERVER),
            locations=parse_csv_option(ALBION_MARKET_LOCATIONS) or ("Black Market",),
            qualities=parse_quality_option(ALBION_MARKET_QUALITIES) or (1,),
            cache_ttl_seconds=max(60, int(ALBION_MARKET_CACHE_TTL_SECONDS or 21600)),
            timeout_seconds=max(1, int(ALBION_MARKET_TIMEOUT_SECONDS or 8)),
        )


class AlbionMarketPriceClient:
    def __init__(self, *, timeout_seconds=8):
        self.timeout_seconds = max(1, int(timeout_seconds or 8))

    def fetch_prices(self, *, server, item_unique_names, locations, qualities):
        clean_items = [normalize_item_id(item) for item in item_unique_names]
        clean_items = [item for item in dict.fromkeys(clean_items) if item]
        if not clean_items:
            return []

        host = f"https://{normalize_server(server)}.albion-online-data.com"
        path = ",".join(clean_items)
        query = urlencode({
            "locations": ",".join(locations),
            "qualities": ",".join(str(quality) for quality in qualities),
        })
        url = f"{host}/api/v2/stats/prices/{path}.json?{query}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "AvalonBot/1.0 Albion Online Data prices",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AlbionMarketPriceError(
                f"Albion Online Data respondio {exc.code}: {detail[:200]}"
            ) from exc
        except URLError as exc:
            raise AlbionMarketPriceError(
                f"No se pudo conectar con Albion Online Data: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise AlbionMarketPriceError("Albion Online Data tardo demasiado en responder.") from exc

        try:
            payload = json.loads(raw) if raw else []
        except ValueError as exc:
            raise AlbionMarketPriceError("Albion Online Data devolvio JSON invalido.") from exc
        if not isinstance(payload, list):
            raise AlbionMarketPriceError("Albion Online Data devolvio un formato inesperado.")
        return payload


class AlbionMarketPriceService:
    def __init__(self, repository=None, client=None, config=None):
        self.repository = repository or AlbionPriceRepository()
        self.config = config or AlbionMarketPriceConfig.from_settings()
        self.client = client or AlbionMarketPriceClient(timeout_seconds=self.config.timeout_seconds)

    def enrich_loot(self, loot_payload, *, force_refresh=False, server=None, locations=None, quality=None):
        config = self._effective_config(server=server, locations=locations, quality=quality)
        item_refs = self._loot_item_refs(loot_payload, config)
        prices, status = self.get_prices_for_items(
            item_refs,
            force_refresh=force_refresh,
            config=config,
        )

        grand_total = 0
        priced_items = 0
        unpriced_items = 0
        for player in loot_payload.get("players", []):
            player_total = 0
            for item in player.get("items", []):
                item_id = normalize_item_id(item.get("item_unique_name") or item.get("item_id"))
                item_quality = self._item_quality(item, config)
                quantity = int(item.get("quantity") or 0)
                price = prices.get((item_id, item_quality))
                fallback_price = self._fallback_price_from_loot_item(item)
                if price and price.get("available"):
                    item["price"] = price["price"]
                    item["price_available"] = True
                    item["price_status"] = "priced"
                    item["price_location"] = price.get("location", "")
                    item["price_server"] = price.get("server", config.server)
                    item["price_quality"] = price.get("quality", item_quality)
                    item["price_updated_at"] = price.get("updated_at", "")
                elif fallback_price:
                    item["price"] = fallback_price
                    item["price_available"] = True
                    item["price_status"] = "loot_estimate"
                    item["price_location"] = "Estimado del loot"
                    item["price_server"] = config.server
                    item["price_quality"] = item_quality
                    item["price_updated_at"] = ""
                else:
                    item["price"] = None
                    item["price_available"] = False
                    item["price_status"] = "missing"
                    item["price_location"] = config.locations[0]
                    item["price_server"] = config.server
                    item["price_quality"] = item_quality
                    item["price_updated_at"] = ""
                item["total_price"] = int(item["price"] or 0) * quantity if item["price_available"] else 0
                if item["price_available"]:
                    priced_items += 1
                    player_total += item["total_price"]
                else:
                    unpriced_items += 1
            player["total_price"] = player_total
            grand_total += player_total

        loot_payload["pricing"] = {
            "server": config.server,
            "locations": list(config.locations),
            "qualities": list(config.qualities),
            "cache_ttl_seconds": config.cache_ttl_seconds,
            "force_refresh": bool(force_refresh),
            "priced_items": priced_items,
            "unpriced_items": unpriced_items,
            "total_price": grand_total,
            **status,
        }
        return loot_payload

    def normalize_loot_without_prices(self, loot_payload, *, server=None, locations=None, quality=None):
        config = self._effective_config(server=server, locations=locations, quality=quality)
        grand_total = 0
        for player in loot_payload.get("players", []):
            player["total_price"] = 0
            for item in player.get("items", []):
                item["price"] = None
                item["price_available"] = False
                item["price_status"] = "pending"
                item["price_location"] = config.locations[0]
                item["price_server"] = config.server
                item["price_quality"] = self._item_quality(item, config)
                item["price_updated_at"] = ""
                item["total_price"] = 0
        loot_payload["pricing"] = {
            "server": config.server,
            "locations": list(config.locations),
            "qualities": list(config.qualities),
            "cache_ttl_seconds": config.cache_ttl_seconds,
            "force_refresh": False,
            "priced_items": 0,
            "unpriced_items": sum(len(player.get("items", [])) for player in loot_payload.get("players", [])),
            "total_price": grand_total,
            "source": "deferred",
            "errors": [],
            "requested_items": 0,
            "missing_items": 0,
        }
        return loot_payload

    def get_prices(self, item_unique_names, *, force_refresh=False, config=None):
        config = config or self.config
        item_refs = [
            {"item_unique_name": item, "quality": config.qualities[0]}
            for item in item_unique_names
        ]
        keyed_prices, status = self.get_prices_for_items(
            item_refs,
            force_refresh=force_refresh,
            config=config,
        )
        return {
            item_id: price
            for (item_id, _quality), price in keyed_prices.items()
        }, status

    def get_prices_for_items(self, item_refs, *, force_refresh=False, config=None):
        config = config or self.config
        requested = []
        for item in item_refs:
            item_id = normalize_item_id(item.get("item_unique_name") or item.get("item_id"))
            item_quality = self._item_quality(item, config)
            if item_id:
                requested.append((item_id, item_quality))
        requested = list(dict.fromkeys(requested))
        if not requested:
            return {}, {"source": "none", "errors": []}

        item_ids = list(dict.fromkeys(item_id for item_id, _quality in requested))
        qualities = tuple(dict.fromkeys(quality for _item_id, quality in requested))
        cache_candidates = self._load_market_cache_candidates(item_ids, config, qualities=qualities)
        cached_by_item = {
            key: select_preferred_cached_price(rows)
            for key, rows in cache_candidates.items()
            if rows
        }
        fresh_cache = {
            key: cached
            for key, cached in cached_by_item.items()
            if cached and not force_refresh and (
                self._has_complete_fresh_market_cache(
                    cache_candidates.get(key, []),
                    config,
                )
                or self._has_complete_fresh_negative_cache(
                    cache_candidates.get(key, []),
                    config,
                )
            )
        }
        prices = {
            key: cached
            for key, cached in fresh_cache.items()
            if cached.get("available")
        }
        needs_fetch = [
            key
            for key in requested
            if force_refresh or key not in fresh_cache
        ]
        errors = []
        fetched = False
        if needs_fetch:
            try:
                rows = self.client.fetch_prices(
                    server=config.server,
                    item_unique_names=[item_id for item_id, _quality in needs_fetch],
                    locations=config.locations,
                    qualities=tuple(dict.fromkeys(quality for _item_id, quality in needs_fetch)),
                )
                fetched = True
                self._store_api_rows(rows, config)
                refreshed_candidates = self._load_market_cache_candidates(
                    [item_id for item_id, _quality in needs_fetch],
                    config,
                    qualities=tuple(dict.fromkeys(quality for _item_id, quality in needs_fetch)),
                )
                refreshed_cache = {
                    key: select_preferred_cached_price(rows)
                    for key, rows in refreshed_candidates.items()
                    if rows
                }
                for key, cached in refreshed_cache.items():
                    if cached and cached.get("available"):
                        prices[key] = cached
                self._store_missing_items(needs_fetch, prices, config)
            except AlbionMarketPriceError as exc:
                errors.append(str(exc))
                for key in needs_fetch:
                    stale = cached_by_item.get(key)
                    if stale and stale.get("available"):
                        prices[key] = stale

        return prices, {
            "source": "api" if fetched else "cache",
            "errors": errors,
            "requested_items": len(requested),
            "missing_items": len([key for key in requested if key not in prices]),
        }

    def invalidate(self, *, server=None, locations=None, item_unique_names=None):
        count = 0
        clean_locations = parse_csv_option(locations) if isinstance(locations, str) else tuple(locations or [])
        if not clean_locations:
            clean_locations = (None,)
        for location in clean_locations:
            count += self.repository.invalidate(
                server=normalize_server(server) if server else None,
                location=location,
                item_unique_names=item_unique_names,
            )
        return count

    def _effective_config(self, *, server=None, locations=None, quality=None):
        clean_locations = parse_csv_option(locations) if isinstance(locations, str) else tuple(locations or [])
        clean_qualities = parse_quality_option(str(quality)) if quality else self.config.qualities
        return AlbionMarketPriceConfig(
            server=normalize_server(server or self.config.server),
            locations=clean_locations or self.config.locations,
            qualities=clean_qualities or self.config.qualities,
            cache_ttl_seconds=self.config.cache_ttl_seconds,
            timeout_seconds=self.config.timeout_seconds,
        )

    def _loot_item_refs(self, loot_payload, config):
        refs = []
        for player in loot_payload.get("players", []):
            for item in player.get("items", []):
                refs.append({
                    "item_unique_name": item.get("item_unique_name") or item.get("item_id"),
                    "quality": self._item_quality(item, config),
                })
        return refs

    def _load_market_cache_candidates(self, item_ids, config, *, qualities=None):
        result = {}
        clean_qualities = qualities or config.qualities
        for location in config.locations:
            for quality in clean_qualities:
                rows = self.repository.get_many(
                    server=config.server,
                    location=location,
                    item_unique_names=item_ids,
                    quality=quality,
                )
                for item_id in item_ids:
                    key = (item_id, quality)
                    row = rows.get(item_id)
                    if row:
                        result.setdefault(key, []).append(row)
        return result

    def _store_api_rows(self, rows, config):
        for row in rows:
            if not isinstance(row, dict):
                continue
            item_id = normalize_item_id(row.get("item_id"))
            location = str(row.get("city") or "").strip()
            quality = parse_int(row.get("quality"), default=1)
            if not item_id or not location or quality not in config.qualities:
                continue
            price, price_type = select_market_price(row)
            self.repository.save(
                server=config.server,
                location=location,
                item_unique_name=item_id,
                quality=quality,
                price=price,
                price_type=price_type,
                available=price is not None,
                raw=row,
            )

    def _store_missing_items(self, item_keys, prices, config):
        missing = [key for key in item_keys if key not in prices]
        for item_id, quality in missing:
            for location in config.locations:
                self.repository.save(
                    server=config.server,
                    location=location,
                    item_unique_name=item_id,
                    quality=quality,
                    price=None,
                    price_type="",
                    available=False,
                    raw={},
                )

    def _is_fresh(self, cached, config):
        updated_at = parse_utc_datetime(cached.get("updated_at"))
        if not updated_at:
            return False
        age = (datetime.now(timezone.utc) - updated_at).total_seconds()
        return age <= config.cache_ttl_seconds

    def _has_complete_fresh_negative_cache(self, rows, config):
        fresh_locations = {
            row.get("location")
            for row in rows
            if row and not row.get("available") and self._is_fresh(row, config)
        }
        return set(config.locations).issubset(fresh_locations)

    def _has_complete_fresh_market_cache(self, rows, config):
        fresh_locations = {
            row.get("location")
            for row in rows
            if row and self._is_fresh(row, config)
        }
        return set(config.locations).issubset(fresh_locations)

    def _item_quality(self, item, config):
        quality = parse_int(item.get("quality") or item.get("price_quality"), default=0)
        if 1 <= quality <= 5:
            return quality
        return config.qualities[0]

    def _fallback_price_from_loot_item(self, item):
        candidates = [
            item.get("average_est_market_value"),
            item.get("estimated_market_value"),
            item.get("market_value"),
        ]
        for raw in item.get("raw_records", []) if isinstance(item.get("raw_records"), list) else []:
            if not isinstance(raw, dict):
                continue
            raw_item = raw.get("item") if isinstance(raw.get("item"), dict) else {}
            loot = raw.get("loot") if isinstance(raw.get("loot"), dict) else {}
            loot_item = loot.get("item") if isinstance(loot.get("item"), dict) else {}
            candidates.extend([
                raw.get("average_est_market_value"),
                raw.get("estimated_market_value"),
                raw.get("market_value"),
                raw_item.get("average_est_market_value"),
                raw_item.get("estimated_market_value"),
                raw_item.get("market_value"),
                loot_item.get("average_est_market_value"),
                loot_item.get("estimated_market_value"),
                loot_item.get("market_value"),
            ])
        for candidate in candidates:
            price = parse_int(candidate, default=0)
            if price > 0:
                return price
        return None


def normalize_server(value):
    clean = str(value or "west").strip().lower()
    return clean if clean in {"west", "east", "europe"} else "west"


def normalize_item_id(value):
    return str(value or "").strip().upper()


def parse_csv_option(value):
    return tuple(part.strip() for part in str(value or "").split(",") if part.strip())


def parse_quality_option(value):
    qualities = []
    for part in parse_csv_option(value):
        parsed = parse_int(part, default=0)
        if 1 <= parsed <= 5:
            qualities.append(parsed)
    return tuple(dict.fromkeys(qualities))


def parse_int(value, *, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def select_market_price(row):
    candidates = (
        ("sell_price_min", "sell_min"),
        ("buy_price_max", "buy_max"),
        ("sell_price_max", "sell_max"),
        ("buy_price_min", "buy_min"),
    )
    for field, label in candidates:
        value = parse_int(row.get(field), default=0)
        if value > 0:
            return value, label
    return None, ""


def select_preferred_cached_price(rows):
    available = [
        row
        for row in rows
        if row and row.get("available") and parse_int(row.get("price"), default=0) > 0
    ]
    if available:
        return sorted(
            available,
            key=lambda row: (
                parse_int(row.get("price"), default=0),
                str(row.get("location") or ""),
            ),
        )[0]
    for row in rows:
        if row:
            return row
    return None


def parse_utc_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
