from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None


try:
    ARGENTINA_TZ = ZoneInfo("America/Argentina/Buenos_Aires") if ZoneInfo else timezone(timedelta(hours=-3))
except Exception:
    ARGENTINA_TZ = timezone(timedelta(hours=-3))


def format_number(value):
    return f"{int(value or 0):,}".replace(",", ".")


def parse_iso_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


def format_argentina_datetime(value):
    parsed = parse_iso_datetime(value)
    if not parsed:
        return ""

    return parsed.astimezone(ARGENTINA_TZ).strftime("%d/%m/%Y | %H:%M")


def argentina_now_display():
    return datetime.now(timezone.utc).astimezone(ARGENTINA_TZ).strftime("%d/%m/%Y | %H:%M")


def clean_user_name(user_name, user_id):
    text = str(user_name or "").strip()
    fallback = f"Usuario {user_id}"
    if not text or text == "Usuario" or text == fallback:
        return "Sin nombre"

    return text
