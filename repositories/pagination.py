import math


DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


def normalize_page(value, default=DEFAULT_PAGE):
    try:
        page = int(value or default)
    except (TypeError, ValueError):
        page = int(default)
    return max(page, 1)


def normalize_page_size(value, default=DEFAULT_PAGE_SIZE, max_page_size=MAX_PAGE_SIZE):
    try:
        page_size = int(value or default)
    except (TypeError, ValueError):
        page_size = int(default)
    page_size = max(page_size, 1)
    return min(page_size, int(max_page_size))


def page_metadata(page, page_size, total_items):
    total_items = max(int(total_items or 0), 0)
    total_pages = math.ceil(total_items / page_size) if total_items else 0
    if total_pages and page > total_pages:
        page = total_pages
    return {
        "page": page,
        "page_size": page_size,
        "total_items": total_items,
        "total_pages": total_pages,
    }


def page_response(items, page, page_size, total_items, *, item_key="items", extra=None):
    payload = {
        item_key: items,
        "items": items,
    }
    payload.update(page_metadata(page, page_size, total_items))
    if extra:
        payload.update(extra)
    return payload
