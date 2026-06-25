from datetime import datetime

from repositories.pagination import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    normalize_page,
    normalize_page_size,
    page_response,
)
from utils.json_store import read_json


def _matches_text(value, query):
    if not query:
        return True
    return query in str(value or "").lower()


def _record_matches_query(record, query):
    if not query:
        return True
    return _matches_text(record, query)


def _record_matches_status(record, status):
    if not status:
        return True
    return str(record.get("status") or "").strip().lower() == status


def _record_matches_type(record, record_type):
    if not record_type:
        return True
    candidates = (
        record.get("type"),
        record.get("category"),
        record.get("action"),
        record.get("panel_name"),
        record.get("option_label"),
    )
    return any(str(value or "").strip().lower() == record_type for value in candidates)


def _parse_date_filter(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_record_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d",
        "%d/%m/%Y | %H:%M:%S",
        "%d/%m/%Y | %H:%M",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _record_matches_date(record, date_from, date_to, candidate_fields):
    from_date = _parse_date_filter(date_from)
    to_date = _parse_date_filter(date_to)
    if not from_date and not to_date:
        return True

    record_date = None
    for field in candidate_fields:
        record_date = _parse_record_date(record.get(field))
        if record_date:
            break
    if not record_date:
        return False
    if from_date and record_date < from_date:
        return False
    if to_date and record_date > to_date:
        return False
    return True


class DashboardJsonRepository:
    def __init__(self, path):
        self.path = path

    def list_guild_items_page(
        self,
        guild_id,
        *,
        page=DEFAULT_PAGE,
        page_size=DEFAULT_PAGE_SIZE,
        search="",
        status="",
        record_type="",
        date_from="",
        date_to="",
        candidate_date_fields=(),
        item_key="items",
    ):
        page = normalize_page(page)
        page_size = normalize_page_size(page_size)
        query = str(search or "").strip().lower()
        status = str(status or "").strip().lower()
        record_type = str(record_type or "").strip().lower()

        data = read_json(self.path, {})
        items = data.get(str(guild_id), []) if isinstance(data, dict) else []
        if not isinstance(items, list):
            items = []

        filtered = []
        for item in reversed(items):
            if not _record_matches_query(item, query):
                continue
            if not _record_matches_status(item, status):
                continue
            if not _record_matches_type(item, record_type):
                continue
            if not _record_matches_date(item, date_from, date_to, candidate_date_fields):
                continue
            filtered.append(item)

        total_items = len(filtered)
        offset = (page - 1) * page_size
        paged = filtered[offset:offset + page_size]
        return page_response(
            paged,
            page,
            page_size,
            total_items,
            item_key=item_key,
        )
