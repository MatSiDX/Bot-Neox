import csv
import io
import json
import re
from dataclasses import dataclass, field
from typing import Any


class LootNormalizationError(ValueError):
    pass


PLAYER_NAME_FIELDS = (
    "looted_by__name",
    "looted_by_name",
    "looted_by.name",
    "player_name",
    "player",
    "looter",
    "name",
)
PLAYER_ID_FIELDS = (
    "looted_by__id",
    "looted_by_id",
    "looted_by.id",
    "player_id",
    "discord_user_id",
    "user_id",
)
ITEM_ID_FIELDS = (
    "item_id",
    "item_unique_name",
    "unique_name",
    "uniqueName",
    "item.unique_name",
    "item.id",
    "id",
)
ITEM_NAME_FIELDS = (
    "item_name",
    "item.name",
    "name",
    "localized_name",
)
QUANTITY_FIELDS = ("quantity", "qty", "amount", "count")
ENCHANTMENT_FIELDS = ("enchantment", "enchant", "enchantment_level")
TIER_FIELDS = ("tier", "item_tier")
QUALITY_FIELDS = ("quality", "item_quality")


@dataclass(frozen=True)
class LootIssue:
    code: str
    message: str
    severity: str = "error"
    record_number: int | None = None
    field: str = ""
    raw_payload: Any = None

    def to_dict(self):
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "record_number": self.record_number,
            "field": self.field,
            "raw_payload": self.raw_payload,
        }


@dataclass(frozen=True)
class LootItemRecord:
    player_name: str
    item_name: str
    item_unique_name: str
    quantity: int
    player_id: str = ""
    enchantment: int | None = None
    tier: int | None = None
    quality: int | None = None
    stackable: bool = False
    raw_payload: Any = None

    def aggregation_key(self):
        return (
            self.player_id or self.player_name.casefold(),
            self.item_unique_name.casefold(),
            self.quality or 0,
        )

    def to_dict(self):
        return {
            "player_name": self.player_name,
            "player_id": self.player_id,
            "item_name": self.item_name,
            "item_unique_name": self.item_unique_name,
            "item_id": self.item_unique_name,
            "quantity": self.quantity,
            "enchantment": self.enchantment,
            "tier": self.tier,
            "quality": self.quality,
            "stackable": self.stackable,
            "raw_payload": self.raw_payload,
        }


@dataclass
class LootItemAggregate:
    player_name: str
    item_name: str
    item_unique_name: str
    quantity: int = 0
    player_id: str = ""
    enchantment: int | None = None
    tier: int | None = None
    quality: int | None = None
    stackable: bool = False
    record_count: int = 0
    raw_records: list[Any] = field(default_factory=list)

    def add(self, record: LootItemRecord):
        self.quantity += record.quantity
        self.record_count += 1
        self.stackable = self.stackable or record.stackable
        self.raw_records.append(record.raw_payload)
        if not self.item_name and record.item_name:
            self.item_name = record.item_name

    @property
    def stack_mode(self):
        if self.stackable:
            return "stacked_quantity"
        if self.record_count > 1:
            return "multiple_single_records"
        return "single_record"

    def to_dict(self):
        return {
            "player_name": self.player_name,
            "player_id": self.player_id,
            "item_name": self.item_name,
            "item_unique_name": self.item_unique_name,
            "item_id": self.item_unique_name,
            "quantity": self.quantity,
            "enchantment": self.enchantment,
            "tier": self.tier,
            "quality": self.quality,
            "stackable": self.stackable,
            "stack_mode": self.stack_mode,
            "record_count": self.record_count,
            "raw_records": self.raw_records,
        }


@dataclass
class LootPlayerGroup:
    player_name: str
    player_id: str = ""
    items: dict[tuple[str, int], LootItemAggregate] = field(default_factory=dict)

    def add(self, record: LootItemRecord):
        key = (record.item_unique_name.casefold(), record.quality or 0)
        if key not in self.items:
            self.items[key] = LootItemAggregate(
                player_name=record.player_name,
                player_id=record.player_id,
                item_name=record.item_name,
                item_unique_name=record.item_unique_name,
                enchantment=record.enchantment,
                tier=record.tier,
                quality=record.quality,
            )
        self.items[key].add(record)

    def to_dict(self):
        items = sorted(
            self.items.values(),
            key=lambda item: (
                item.tier if item.tier is not None else 99,
                item.item_name.casefold(),
                item.item_unique_name.casefold(),
                item.quality or 0,
            ),
        )
        return {
            "player_name": self.player_name,
            "player_id": self.player_id,
            "item_count": len(items),
            "quantity": sum(item.quantity for item in items),
            "items": [item.to_dict() for item in items],
        }


@dataclass
class LootNormalizationResult:
    source_format: str
    records: list[LootItemRecord]
    issues: list[LootIssue]
    skipped_records: int = 0

    @property
    def valid(self):
        return bool(self.records)

    def grouped_players(self):
        groups: dict[str, LootPlayerGroup] = {}
        for record in self.records:
            key = record.player_id or record.player_name.casefold()
            if key not in groups:
                groups[key] = LootPlayerGroup(record.player_name, record.player_id)
            groups[key].add(record)
        return sorted(groups.values(), key=lambda group: group.player_name.casefold())

    def to_dict(self):
        players = self.grouped_players()
        return {
            "source_format": self.source_format,
            "valid": self.valid,
            "record_count": len(self.records),
            "skipped_records": self.skipped_records,
            "invalid_records": len([issue for issue in self.issues if issue.severity == "error"]),
            "warning_count": len([issue for issue in self.issues if issue.severity == "warning"]),
            "player_count": len(players),
            "item_count": sum(len(player.items) for player in players),
            "quantity": sum(record.quantity for record in self.records),
            "records": [record.to_dict() for record in self.records],
            "players": [player.to_dict() for player in players],
            "issues": [issue.to_dict() for issue in self.issues],
        }


class LootNormalizationService:
    def normalize_csv_text(self, text, *, source_name=""):
        clean_text = str(text or "").replace("\ufeff", "", 1)
        if not clean_text.strip():
            raise LootNormalizationError("El CSV de loot esta vacio.")

        rows = self._read_csv_rows(clean_text)
        if not rows:
            raise LootNormalizationError("El CSV de loot no contiene filas.")

        headers = [self._normalize_header(header) for header in rows[0]]
        if not any(headers):
            raise LootNormalizationError("El CSV de loot no contiene encabezados validos.")

        records = []
        issues = []
        for index, values in enumerate(rows[1:], start=2):
            row = {
                headers[column_index]: values[column_index].strip() if column_index < len(values) else ""
                for column_index in range(len(headers))
                if headers[column_index]
            }
            if not any(row.values()):
                continue
            record, record_issues = self._normalize_mapping(row, index)
            issues.extend(record_issues)
            if record:
                records.append(record)

        self._ensure_supported_result(records, issues, "CSV", source_name)
        return LootNormalizationResult("csv", records, issues)

    def normalize_json_text(self, text, *, source_name=""):
        if not str(text or "").strip():
            raise LootNormalizationError("El JSON de loot esta vacio.")
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LootNormalizationError(f"El JSON de loot no es valido: {exc.msg}.") from exc
        return self.normalize_json_value(value, source_name=source_name)

    def normalize_json_value(self, value, *, source_name=""):
        entries = self._extract_json_entries(value)
        if entries is None:
            raise LootNormalizationError(
                'El JSON debe ser una lista o contener una lista en "entries", "items", "loot" o "data".'
            )

        records = []
        issues = []
        skipped = 0
        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                issues.append(LootIssue(
                    "invalid_json_entry",
                    "La entrada JSON debe ser un objeto.",
                    record_number=index,
                    raw_payload=entry,
                ))
                continue
            if self._is_non_loot_event(entry):
                skipped += 1
                continue
            mapping = self._flatten_json_loot_entry(entry)
            record, record_issues = self._normalize_mapping(mapping, index, raw_payload=entry)
            issues.extend(record_issues)
            if record:
                records.append(record)

        self._ensure_supported_result(records, issues, "JSON", source_name)
        return LootNormalizationResult("json", records, issues, skipped)

    def normalize_payload(self, payload):
        source_format = str(payload.get("format") or payload.get("source_format") or "").strip().lower()
        source_name = str(payload.get("file_name") or payload.get("source_name") or "")
        if "content" in payload:
            content = payload.get("content")
            if source_format == "csv" or source_name.lower().endswith(".csv"):
                return self.normalize_csv_text(content, source_name=source_name)
            if source_format == "json" or source_name.lower().endswith(".json"):
                return self.normalize_json_text(content, source_name=source_name)
            raise LootNormalizationError("Indica el formato del loot: csv o json.")
        if "data" in payload:
            return self.normalize_json_value(payload.get("data"), source_name=source_name)
        raise LootNormalizationError('El payload debe incluir "content" o "data".')

    def _read_csv_rows(self, text):
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
            return list(csv.reader(io.StringIO(text), dialect))
        except csv.Error:
            delimiter = ";" if sample.count(";") >= sample.count(",") else ","
            return list(csv.reader(io.StringIO(text), delimiter=delimiter))

    def _normalize_mapping(self, mapping, record_number, raw_payload=None):
        raw = raw_payload if raw_payload is not None else dict(mapping)
        player_name = self._first_text(mapping, PLAYER_NAME_FIELDS)
        player_id = self._first_text(mapping, PLAYER_ID_FIELDS)
        item_unique_name = self._first_text(mapping, ITEM_ID_FIELDS)
        item_name = self._first_text(mapping, ITEM_NAME_FIELDS)
        quantity_value = self._first_text(mapping, QUANTITY_FIELDS)
        issues = []

        if not player_name and not player_id:
            issues.append(LootIssue(
                "missing_player",
                "El registro no indica player_name ni player_id.",
                record_number=record_number,
                field="player_name",
                raw_payload=raw,
            ))
        if not item_unique_name and not item_name:
            issues.append(LootIssue(
                "missing_item",
                "El registro no indica item_unique_name/item_id ni item_name.",
                record_number=record_number,
                field="item_unique_name",
                raw_payload=raw,
            ))
        quantity, quantity_issue = self._parse_positive_int(quantity_value, "quantity", record_number, raw)
        if quantity_issue:
            issues.append(quantity_issue)

        if issues:
            return None, issues

        item_unique_name = item_unique_name or item_name
        item_name = item_name or item_unique_name
        tier = self._parse_optional_int(self._first_text(mapping, TIER_FIELDS))
        enchantment = self._parse_optional_int(self._first_text(mapping, ENCHANTMENT_FIELDS))
        quality = self._parse_optional_int(self._first_text(mapping, QUALITY_FIELDS))
        inferred_tier, inferred_enchantment = self._infer_item_parts(item_unique_name)
        if tier is None:
            tier = inferred_tier
        if enchantment is None:
            enchantment = inferred_enchantment

        return LootItemRecord(
            player_name=player_name or player_id,
            player_id=player_id,
            item_name=item_name,
            item_unique_name=item_unique_name,
            quantity=quantity,
            enchantment=enchantment,
            tier=tier,
            quality=quality,
            stackable=quantity > 1,
            raw_payload=raw,
        ), []

    def _extract_json_entries(self, value):
        if isinstance(value, list):
            return value
        if not isinstance(value, dict):
            return None
        for key in ("entries", "items", "loot", "data", "records"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                return candidate
        return None

    def _flatten_json_loot_entry(self, entry):
        loot = entry.get("loot") if isinstance(entry.get("loot"), dict) else {}
        item = loot.get("item") if isinstance(loot.get("item"), dict) else entry.get("item")
        if not isinstance(item, dict):
            item = {}
        looted_by = loot.get("looted_by") if isinstance(loot.get("looted_by"), dict) else entry.get("looted_by")
        if not isinstance(looted_by, dict):
            looted_by = {}
        return {
            "player_name": self._first_text(looted_by, ("name", "player_name", "Name")),
            "player_id": self._first_text(looted_by, ("id", "player_id", "Id")),
            "item_unique_name": self._first_text(item, ("id", "unique_name", "uniqueName", "item_id")),
            "item_name": self._first_text(item, ("name", "localized_name", "Name")),
            "quantity": item.get("quantity", entry.get("quantity")),
            "quality": item.get("quality", entry.get("quality")),
            "tier": item.get("tier", entry.get("tier")),
            "enchantment": item.get("enchantment", item.get("enchant", entry.get("enchantment"))),
            **entry,
        }

    def _is_non_loot_event(self, entry):
        event_type = str(entry.get("type") or entry.get("event_type") or "").strip().lower()
        return bool(event_type and event_type != "loot" and "item" not in entry)

    def _ensure_supported_result(self, records, issues, label, source_name):
        if records:
            return
        error_count = len([issue for issue in issues if issue.severity == "error"])
        detail = f" en {source_name}" if source_name else ""
        if error_count:
            return
        raise LootNormalizationError(f"No se encontraron registros de loot validos en el {label}{detail}.")

    def _first_text(self, mapping, field_names):
        if not isinstance(mapping, dict):
            return ""
        normalized = {self._normalize_header(key): value for key, value in mapping.items()}
        for field_name in field_names:
            value = normalized.get(self._normalize_header(field_name))
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    def _parse_positive_int(self, value, field, record_number, raw):
        try:
            quantity = int(str(value).strip())
        except (TypeError, ValueError):
            return None, LootIssue(
                "invalid_quantity",
                "La cantidad del item debe ser un entero mayor a 0.",
                record_number=record_number,
                field=field,
                raw_payload=raw,
            )
        if quantity <= 0:
            return None, LootIssue(
                "invalid_quantity",
                "La cantidad del item debe ser mayor a 0.",
                record_number=record_number,
                field=field,
                raw_payload=raw,
            )
        return quantity, None

    def _parse_optional_int(self, value):
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None

    def _infer_item_parts(self, item_unique_name):
        item_id = str(item_unique_name or "").strip().upper()
        tier = None
        enchantment = None
        tier_match = re.match(r"^T([1-8])_", item_id)
        if tier_match:
            tier = int(tier_match.group(1))
        enchantment_match = re.search(r"@([1-4])(?:$|_)", item_id)
        if enchantment_match:
            enchantment = int(enchantment_match.group(1))
        return tier, enchantment

    def _normalize_header(self, value):
        return str(value or "").strip().replace("-", "_").lower()
