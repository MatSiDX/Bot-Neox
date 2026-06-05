import argparse
import base64
from http.cookies import SimpleCookie
import hashlib
import html
import json
import mimetypes
import os
import re
import secrets
import socket
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

from repositories.database import DATABASE_FILE, init_database
from repositories.balance_repository import DATA_DIR
from services.ping_template_service import MAX_TEMPLATES_PER_GUILD, SCRATCH_TEMPLATE_KEY, PingTemplateService
from services.permission_service import (
    PERMISSION_ECONOMY,
    PERMISSION_GLOBAL,
    PERMISSION_PERMISSIONS,
    PERMISSION_PING,
    PERMISSION_REPORTS,
    PERMISSION_TEMPLATES,
    PermissionService,
)
from utils.json_store import (
    mutate_json as mutate_json_file_safe,
    read_json as read_json_file_safe,
    write_json as write_json_file_safe,
)


load_dotenv()

REPORTS_FILE = os.path.join(DATA_DIR, "reports.json")
AVALONIAN_FILE = os.path.join(DATA_DIR, "avalonian_interactions.json")
SESSIONS_FILE = os.path.join(DATA_DIR, "dashboard_sessions.json")
AVALON_BOT_LOGO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "AvalonBot.png")
TICKET_PANELS_FILE = os.path.join(DATA_DIR, "ticket_panels.json")
TICKET_RECORDS_FILE = os.path.join(DATA_DIR, "ticket_records.json")
TICKET_MEDIA_DIR = os.path.join(DATA_DIR, "ticket_media")
AUDIT_CONFIG_FILE = os.path.join(DATA_DIR, "audit_config.json")
AUDIT_EVENTS_FILE = os.path.join(DATA_DIR, "audit_events.json")
DEFAULT_LIMIT = 500
AUDIT_CATEGORIES = [
    ("channels", "Canales", "Crear, editar o eliminar canales"),
    ("roles", "Roles", "Crear, editar o eliminar roles"),
    ("joins", "Entradas / salidas del servidor", "Usuarios que entran o salen del servidor"),
    ("member_actions", "Acciones de miembros", "Cambios de nombre, roles asignados/removidos, baneos, desbaneos y expulsiones"),
    ("voice", "Voz", "Entradas, salidas y movimientos en canales de voz"),
    ("messages", "Mensajes", "Mensajes editados o eliminados"),
    ("server", "Servidor", "Cambios generales del servidor, emojis e invitaciones"),
]
BOT_PERMISSION_OPTIONS = [
    (PERMISSION_ECONOMY, "Economia", "Agregar o quitar balance y exportar datos de economia."),
    (PERMISSION_PING, "Ping", "Usar /ping y /ping-test para publicar pings."),
    (PERMISSION_TEMPLATES, "Plantillas", "Crear, editar, listar y eliminar plantillas de ping."),
    (PERMISSION_REPORTS, "Informes", "Revisar y gestionar informes/Avalonianas."),
    (PERMISSION_PERMISSIONS, "Permisos", "Administrar permisos de otros roles."),
    (PERMISSION_GLOBAL, "Global", "Acceso completo a todos los permisos del bot."),
]
BOT_PERMISSION_LABELS = {
    key: label
    for key, label, _ in BOT_PERMISSION_OPTIONS
}
BOT_PERMISSION_KEYS = {
    key
    for key, _, _ in BOT_PERMISSION_OPTIONS
}
DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_ADMINISTRATOR = 0x8
SESSION_COOKIE = "dashboard_session"
STATE_COOKIE = "dashboard_oauth_state"
SESSION_TTL_SECONDS = 60 * 60 * 12
REMEMBER_SESSION_TTL_SECONDS = 60 * 60 * 24 * 30
SESSION_SECRET = os.getenv("DASHBOARD_SESSION_SECRET") or os.getenv("TOKEN") or secrets.token_urlsafe(32)
DASHBOARD_CLIENT_ID = os.getenv("DASHBOARD_CLIENT_ID") or os.getenv("DISCORD_CLIENT_ID") or ""
DASHBOARD_CLIENT_SECRET = os.getenv("DASHBOARD_CLIENT_SECRET") or os.getenv("DISCORD_CLIENT_SECRET") or ""
DASHBOARD_REDIRECT_URI = os.getenv("DASHBOARD_REDIRECT_URI") or ""
BOT_TOKEN = os.getenv("ECONOMY_TOKEN") or os.getenv("TOKEN") or ""
SESSIONS = {}
SESSIONS_LOCK = threading.RLock()
OAUTH_STATES = {}
OAUTH_STATES_LOCK = threading.RLock()
BOT_GUILDS_CACHE = {"expires_at": 0, "guild_ids": None}
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


def read_json_file(path, fallback):
    return read_json_file_safe(path, fallback)


def oauth_configured():
    return bool(DASHBOARD_CLIENT_ID and DASHBOARD_CLIENT_SECRET)


def make_cookie_value(value, max_age=None):
    cookie = SimpleCookie()
    cookie[SESSION_COOKIE] = value
    cookie[SESSION_COOKIE]["path"] = "/"
    cookie[SESSION_COOKIE]["samesite"] = "Lax"
    cookie[SESSION_COOKIE]["httponly"] = True
    if max_age is not None:
        cookie[SESSION_COOKIE]["max-age"] = str(int(max_age))
    return cookie.output(header="").strip()


def make_state_cookie(value, max_age=300):
    cookie = SimpleCookie()
    cookie[STATE_COOKIE] = value
    cookie[STATE_COOKIE]["path"] = "/"
    cookie[STATE_COOKIE]["samesite"] = "Lax"
    cookie[STATE_COOKIE]["httponly"] = True
    cookie[STATE_COOKIE]["max-age"] = str(int(max_age))
    return cookie.output(header="").strip()


def remember_oauth_state(state, remember_device=False):
    with OAUTH_STATES_LOCK:
        OAUTH_STATES[state] = {
            "expires_at": time.time() + 300,
            "remember_device": bool(remember_device),
        }


def consume_oauth_state(state):
    if not state:
        return False

    now = time.time()
    with OAUTH_STATES_LOCK:
        expired = [
            key
            for key, payload in OAUTH_STATES.items()
            if payload.get("expires_at", 0) < now
        ]
        for key in expired:
            OAUTH_STATES.pop(key, None)

        payload = OAUTH_STATES.pop(state, None)
        if not payload or payload.get("expires_at", 0) < now:
            return None

        return payload


def parse_cookie_header(header):
    cookie = SimpleCookie()
    if header:
        cookie.load(header)
    return {key: morsel.value for key, morsel in cookie.items()}


def sign_session_id(session_id):
    digest = hashlib.sha256(f"{session_id}.{SESSION_SECRET}".encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def encode_session_cookie(session_id):
    return f"{session_id}.{sign_session_id(session_id)}"


def decode_session_cookie(value):
    if not value or "." not in value:
        return None

    session_id, signature = value.rsplit(".", 1)
    expected = sign_session_id(session_id)
    if not secrets.compare_digest(signature, expected):
        return None

    return session_id


def load_persisted_sessions():
    sessions = read_json_file(SESSIONS_FILE, {})
    if not isinstance(sessions, dict):
        return {}

    now = time.time()
    return {
        session_id: session
        for session_id, session in sessions.items()
        if isinstance(session, dict) and session.get("expires_at", 0) >= now
    }


def save_persisted_sessions():
    write_json_file_safe(SESSIONS_FILE, SESSIONS)


with SESSIONS_LOCK:
    SESSIONS.update(load_persisted_sessions())


def create_session(user, admin_guilds, remember_device=False):
    session_id = secrets.token_urlsafe(32)
    ttl = REMEMBER_SESSION_TTL_SECONDS if remember_device else SESSION_TTL_SECONDS
    with SESSIONS_LOCK:
        SESSIONS[session_id] = {
            "user": user,
            "admin_guilds": admin_guilds,
            "expires_at": time.time() + ttl,
            "remember_device": bool(remember_device),
            "csrf_token": secrets.token_urlsafe(24),
        }
        save_persisted_sessions()
    return session_id


def get_session_from_request(handler):
    cookies = parse_cookie_header(handler.headers.get("Cookie", ""))
    session_id = decode_session_cookie(cookies.get(SESSION_COOKIE, ""))
    if not session_id:
        return None

    with SESSIONS_LOCK:
        session = SESSIONS.get(session_id)
        if not session:
            return None
        if session.get("expires_at", 0) < time.time():
            SESSIONS.pop(session_id, None)
            save_persisted_sessions()
            return None
        if not session.get("csrf_token"):
            session["csrf_token"] = secrets.token_urlsafe(24)
            save_persisted_sessions()
        return session


def clear_session_from_request(handler):
    cookies = parse_cookie_header(handler.headers.get("Cookie", ""))
    session_id = decode_session_cookie(cookies.get(SESSION_COOKIE, ""))
    if session_id:
        with SESSIONS_LOCK:
            SESSIONS.pop(session_id, None)
            save_persisted_sessions()


def discord_request(path, *, token=None, auth_scheme="Bearer", data=None):
    headers = {
        "Accept": "application/json",
        "User-Agent": "Bot-Neox-Dashboard/1.0",
    }
    if token:
        headers["Authorization"] = f"{auth_scheme} {token}"
    if data is not None:
        encoded = urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    else:
        encoded = None

    request = Request(f"{DISCORD_API_BASE}{path}", data=encoded, headers=headers)
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Discord respondio {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"No pude conectar con Discord: {exc.reason}") from exc


def admin_guilds_from_discord(guilds):
    admin_guilds = []
    for guild in guilds:
        permissions = int(guild.get("permissions", 0) or 0)
        if guild.get("owner") or permissions & DISCORD_ADMINISTRATOR:
            admin_guilds.append({
                "id": str(guild.get("id")),
                "name": str(guild.get("name") or f"Servidor {guild.get('id')}"),
            })
    return admin_guilds


def get_bot_guild_ids():
    if not BOT_TOKEN:
        return None

    now = time.time()
    if BOT_GUILDS_CACHE["guild_ids"] is not None and BOT_GUILDS_CACHE["expires_at"] > now:
        return BOT_GUILDS_CACHE["guild_ids"]

    guilds = discord_request("/users/@me/guilds", token=BOT_TOKEN, auth_scheme="Bot")
    guild_ids = {str(guild.get("id")) for guild in guilds}
    BOT_GUILDS_CACHE["guild_ids"] = guild_ids
    BOT_GUILDS_CACHE["expires_at"] = now + 60
    return guild_ids


def discord_json_request(path, *, token=None, auth_scheme="Bot", method="GET", payload=None):
    headers = {
        "Accept": "application/json",
        "User-Agent": "Bot-Neox-Dashboard/1.0",
    }
    data = None
    if token:
        headers["Authorization"] = f"{auth_scheme} {token}"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(f"{DISCORD_API_BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Discord respondio {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"No pude conectar con Discord: {exc.reason}") from exc


def load_ticket_panels():
    data = read_json_file(TICKET_PANELS_FILE, {})
    return data if isinstance(data, dict) else {}


def save_ticket_panels(data):
    write_json_file_safe(TICKET_PANELS_FILE, data)


def get_guild_ticket_panels(guild_id):
    data = load_ticket_panels()
    panels = data.get(str(guild_id), [])
    return panels if isinstance(panels, list) else []


def save_guild_ticket_panels(guild_id, panels):
    def mutate(data):
        data[str(guild_id)] = panels
        return data

    mutate_json_file_safe(TICKET_PANELS_FILE, {}, mutate)


def load_audit_config():
    data = read_json_file(AUDIT_CONFIG_FILE, {})
    return data if isinstance(data, dict) else {}


def save_audit_config(data):
    write_json_file_safe(AUDIT_CONFIG_FILE, data)


def get_guild_audit_config(guild_id):
    data = load_audit_config()
    config = data.get(str(guild_id), {})
    if not isinstance(config, dict):
        config = {}

    channels = config.get("channels", {})
    if not isinstance(channels, dict):
        channels = {}

    return {
        "channels": {
            key: str(channels.get(key) or "")
            for key, _, _ in AUDIT_CATEGORIES
        }
    }


def save_guild_audit_config(guild_id, config):
    channels = config.get("channels", {}) if isinstance(config, dict) else {}

    def mutate(data):
        data[str(guild_id)] = {
            "channels": {
                key: str(channels.get(key) or "")
                for key, _, _ in AUDIT_CATEGORIES
            }
        }
        return data

    mutate_json_file_safe(AUDIT_CONFIG_FILE, {}, mutate)


def get_guild_ticket_records(guild_id):
    data = read_json_file(TICKET_RECORDS_FILE, {})
    records = data.get(str(guild_id), []) if isinstance(data, dict) else []
    return records if isinstance(records, list) else []


def get_ticket_record(guild_id, record_id):
    for record in get_guild_ticket_records(guild_id):
        if str(record.get("channel_id") or record.get("number") or "") == str(record_id):
            return record
    return None


def html_text(value):
    return html.escape(str(value or ""), quote=True)


def transcript_url(value):
    return html.escape(str(value or "#"), quote=True)


def is_image_attachment(attachment):
    content_type = str(attachment.get("content_type") or "")
    filename = str(attachment.get("filename") or "")
    return content_type.startswith("image/") or bool(re.search(r"\.(png|jpe?g|gif|webp|bmp)$", filename, re.IGNORECASE))


def render_transcript_avatar(message):
    avatar = str(message.get("author_avatar") or "")
    name = str(message.get("author_name") or message.get("author") or "U")
    if avatar:
        return f'<span class="avatar"><img src="{transcript_url(avatar)}" alt=""></span>'
    return f'<span class="avatar fallback">{html_text(name[:1].upper() or "U")}</span>'


def render_transcript_embeds(embeds):
    if not isinstance(embeds, list):
        return ""

    rendered = []
    for embed in embeds:
        if not isinstance(embed, dict):
            continue
        color = embed.get("color")
        try:
            color_text = f"#{int(color):06x}" if color is not None else "#22c55e"
        except (TypeError, ValueError):
            color_text = "#22c55e"
        image = embed.get("image") if isinstance(embed.get("image"), dict) else {}
        thumbnail = embed.get("thumbnail") if isinstance(embed.get("thumbnail"), dict) else {}
        fields = embed.get("fields") if isinstance(embed.get("fields"), list) else []
        rendered.append(
            f"""
            <div class="embed" style="border-left-color:{html_text(color_text)}">
              {f'<div class="embed-title">{html_text(embed.get("title"))}</div>' if embed.get("title") else ""}
              {f'<div class="embed-description">{html_text(embed.get("description"))}</div>' if embed.get("description") else ""}
              {''.join(f'<div class="embed-field"><strong>{html_text(field.get("name"))}</strong><span>{html_text(field.get("value"))}</span></div>' for field in fields if isinstance(field, dict))}
              {f'<img class="chat-image" src="{transcript_url(thumbnail.get("local_url") or thumbnail.get("url"))}" alt="Miniatura">' if thumbnail.get("local_url") or thumbnail.get("url") else ""}
              {f'<img class="chat-image" src="{transcript_url(image.get("local_url") or image.get("url"))}" alt="Imagen">' if image.get("local_url") or image.get("url") else ""}
              {f'<div class="embed-footer">{html_text((embed.get("footer") or {}).get("text"))}</div>' if isinstance(embed.get("footer"), dict) and embed.get("footer", {}).get("text") else ""}
            </div>
            """
        )
    return "".join(rendered)


def render_transcript_attachments(attachments):
    if not isinstance(attachments, list):
        return ""

    items = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        url = attachment.get("local_url") or attachment.get("url") or "#"
        filename = attachment.get("filename") or "Archivo adjunto"
        if is_image_attachment(attachment):
            items.append(f'<a href="{transcript_url(url)}" target="_blank" rel="noreferrer"><img class="chat-image" src="{transcript_url(url)}" alt="{html_text(filename)}"></a>')
        else:
            items.append(f'<a class="attachment" href="{transcript_url(url)}" target="_blank" rel="noreferrer">{html_text(filename)}</a>')
    return f'<div class="attachments">{"".join(items)}</div>' if items else ""


def render_transcript_message(message):
    author = message.get("author_name") or message.get("author") or "Usuario"
    content = message.get("content") or ""
    reference = message.get("reference") if isinstance(message.get("reference"), dict) else None
    has_visible = bool(content or message.get("embeds") or message.get("attachments"))
    return f"""
      <article class="message">
        {render_transcript_avatar(message)}
        <div class="message-body">
          {f'<div class="reply-line">reply to message ({html_text(reference.get("message_id"))})</div>' if reference and reference.get("message_id") else ""}
          <div class="message-meta">
            <span class="author">{html_text(author)}</span>
            {('<span class="bot-badge">BOT</span>' if message.get("author_bot") else "")}
            <span class="time">{html_text(message.get("created_at"))}</span>
          </div>
          {f'<div class="message-content">{html_text(content)}</div>' if content else ""}
          {render_transcript_embeds(message.get("embeds"))}
          {render_transcript_attachments(message.get("attachments"))}
          {'' if has_visible else '<div class="empty-message">(mensaje sin contenido visible)</div>'}
        </div>
      </article>
    """


def build_ticket_transcript_html(guild_name, record):
    transcript = record.get("transcript") if isinstance(record.get("transcript"), list) else []
    channel_name = record.get("channel_name") or f"ticket-{record.get('number', '')}"
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_text(channel_name)} - Transcripcion</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background: #111821;
      color: #fff;
      font-family: Arial, "Segoe UI", sans-serif;
      font-size: 16px;
    }}
    .page {{ min-height: 100vh; padding: 12px 14px 40px; }}
    .header {{ display: grid; grid-template-columns: 78px minmax(0, 1fr); gap: 14px; align-items: center; margin-bottom: 20px; }}
    .logo {{ width: 78px; height: 78px; object-fit: cover; background: #0b1220; }}
    .header h1 {{ margin: 0; font-size: 24px; line-height: 1.02; font-weight: 700; }}
    .header a {{ color: #8ab4ff; text-decoration: none; font-size: 13px; display: inline-block; margin-top: 8px; }}
    .messages {{ display: grid; gap: 18px; max-width: 1120px; }}
    .message {{ display: grid; grid-template-columns: 50px minmax(0, 1fr); gap: 12px; align-items: start; }}
    .avatar {{ width: 38px; height: 38px; border-radius: 50%; overflow: hidden; display: inline-flex; align-items: center; justify-content: center; background: #263449; color: #fff; font-weight: 700; margin-left: 4px; }}
    .avatar img {{ width: 100%; height: 100%; object-fit: cover; }}
    .message-body {{ min-width: 0; }}
    .message-meta {{ display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; margin-bottom: 2px; }}
    .author {{ font-weight: 700; color: #fff; }}
    .time {{ color: #667386; font-size: 13px; }}
    .bot-badge {{ background: #5865f2; color: #fff; border-radius: 3px; padding: 1px 4px; font-size: 10px; font-weight: 700; }}
    .message-content {{ color: #fff; line-height: 1.45; white-space: pre-wrap; overflow-wrap: anywhere; }}
    .message-content a, a {{ color: #00aff4; }}
    .reply-line {{ color: #566274; font-size: 13px; border-left: 2px solid #4b5563; padding-left: 6px; margin-bottom: 2px; }}
    .embed {{ width: min(520px, 100%); margin-top: 6px; padding: 10px 12px; border-left: 4px solid #22c55e; border-radius: 3px; background: #1d2533; color: #cfd6e2; }}
    .embed-title {{ color: #fff; font-weight: 700; margin-bottom: 6px; }}
    .embed-description {{ white-space: pre-wrap; line-height: 1.35; font-size: 14px; }}
    .embed-field {{ display: grid; gap: 2px; margin-top: 6px; font-size: 13px; }}
    .embed-field strong {{ color: #fff; }}
    .embed-footer {{ color: #cfd6e2; font-size: 12px; margin-top: 10px; }}
    .attachments {{ display: grid; gap: 8px; justify-items: start; margin-top: 6px; }}
    .attachment {{ border: 1px solid #2f3b4d; border-radius: 4px; padding: 8px 10px; color: #00aff4; background: #17202c; text-decoration: none; }}
    .chat-image {{ max-width: min(620px, 100%); max-height: 520px; object-fit: contain; border-radius: 3px; border: 1px solid #222c3a; background: #0f1722; }}
    .empty-message {{ color: #667386; font-style: italic; }}
  </style>
</head>
<body>
  <main class="page">
    <header class="header">
      <img class="logo" src="/assets/AvalonBot.png" alt="AvalonBot">
      <div>
        <h1>{html_text(guild_name)}<br>{html_text(channel_name)}<br>{len(transcript)} mensajes</h1>
        <a href="/dashboard">Volver al dashboard</a>
      </div>
    </header>
    <section class="messages">
      {''.join(render_transcript_message(message) for message in transcript)}
    </section>
  </main>
</body>
</html>"""


def get_guild_audit_events(guild_id):
    data = read_json_file(AUDIT_EVENTS_FILE, {})
    events = data.get(str(guild_id), []) if isinstance(data, dict) else []
    return list(reversed(events[-500:])) if isinstance(events, list) else []


def ping_template_service():
    return PingTemplateService()


def get_guild_ping_templates(guild_id):
    service = ping_template_service()
    saved_templates = service.get_saved_templates(guild_id)
    global_templates = service.repo.get_global_templates()
    templates = service.get_templates(guild_id, include_scratch=True)
    items = []
    for key, template in templates.items():
        if key == SCRATCH_TEMPLATE_KEY:
            source = "scratch"
        elif key in saved_templates:
            source = "server"
        elif key in global_templates:
            source = "global"
        else:
            source = "server"

        item = dict(template)
        item["key"] = key
        item["source"] = source
        item["editable"] = source == "server"
        item["deletable"] = source == "server"
        item["overrides_global"] = source == "server" and key in global_templates
        items.append(item)

    return {
        "templates": items,
        "saved_count": service.get_template_count(guild_id),
        "max_templates": MAX_TEMPLATES_PER_GUILD,
    }


def save_guild_ping_template(guild_id, payload):
    service = ping_template_service()
    key = service.normalize_key(payload.get("key"))
    original_key = service.normalize_key(payload.get("original_key"))
    if not key:
        return None, "La clave de la plantilla no es valida."
    if key == SCRATCH_TEMPLATE_KEY:
        return None, "Esa clave esta reservada para la plantilla temporal desde cero."
    roles = [line.strip() for line in str(payload.get("roles") or "").replace(",", "\n").splitlines() if line.strip()]
    if len(roles) < 2:
        return None, "La plantilla necesita al menos dos roles: caller y un cupo disponible."
    if len(roles) > 21:
        return None, "La plantilla puede tener como maximo 21 roles."

    content = str(payload.get("content") or "").strip()
    if not content:
        return None, "Debes indicar el mensaje de la plantilla."

    original_is_saved = bool(original_key and service.repo.guild_template_exists(guild_id, original_key))
    is_update = service.repo.guild_template_exists(guild_id, key) or original_is_saved
    is_global_override = service.repo.global_template_exists(key)
    if original_is_saved and original_key != key and service.repo.guild_template_exists(guild_id, key):
        return None, "Ya existe otra plantilla del servidor con esa clave."
    if not is_update and not service.can_add_template(guild_id):
        return None, "Este servidor ya tiene 5 plantillas guardadas. Elimina una antes de crear otra."

    template = service.normalize_template({
        "key": key,
        "name": str(payload.get("name") or key).strip() or key,
        "title": str(payload.get("title") or ""),
        "title_editable": bool(payload.get("title_editable", True)),
        "mention": str(payload.get("mention") or ""),
        "join_command": str(payload.get("join_command") or "/join {caller}"),
        "caller_slot": str(payload.get("caller_slot") or roles[0]),
        "roles": roles,
        "slot_format": str(payload.get("slot_format") or ""),
        "content": content,
        "loot_link": str(payload.get("loot_link") or ""),
        "report_enabled": bool(payload.get("report_enabled", True)),
    })
    service.repo.upsert(guild_id, key, template)
    if original_is_saved and original_key != key:
        service.repo.delete(guild_id, original_key)
    template["source"] = "server"
    template["editable"] = True
    template["deletable"] = True
    template["overrides_global"] = bool(is_global_override)
    return template, None


def normalize_bot_permission_values(values):
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        values = []

    normalized = []
    for value in values:
        permission = str(value or "").strip().lower()
        if permission in BOT_PERMISSION_KEYS and permission not in normalized:
            normalized.append(permission)

    if PERMISSION_GLOBAL in normalized:
        return [PERMISSION_GLOBAL]

    return normalized


def get_guild_bot_permissions(guild_id):
    service = PermissionService()
    role_permissions = service.get_role_permissions(guild_id)
    cleaned = {}
    for role_id, permissions in role_permissions.items():
        normalized = normalize_bot_permission_values(permissions)
        if normalized:
            cleaned[str(role_id)] = normalized

    return {
        "permissions": cleaned,
        "options": [
            {"key": key, "label": label, "description": description}
            for key, label, description in BOT_PERMISSION_OPTIONS
        ],
    }


def save_guild_bot_permissions(guild_id, payload):
    service = PermissionService()
    permissions = payload.get("permissions", payload) if isinstance(payload, dict) else {}
    if not isinstance(permissions, dict):
        return None, "La configuracion de permisos no es valida."

    cleaned = {}
    for role_id, values in permissions.items():
        role_id = str(role_id or "").strip()
        if not role_id.isdigit():
            continue
        normalized = normalize_bot_permission_values(values)
        if normalized:
            cleaned[role_id] = normalized

    service.repo.set_guild_permissions(guild_id, cleaned)
    return get_guild_bot_permissions(guild_id), None


def normalize_ticket_panel(panel):
    panel = panel if isinstance(panel, dict) else {}
    options = panel.get("options")
    if not isinstance(options, list):
        options = []
    normalized_options = []
    for index, option in enumerate(options[:10], start=1):
        if not isinstance(option, dict):
            continue
        normalized_options.append({
            "id": str(option.get("id") or secrets.token_urlsafe(6)),
            "label": str(option.get("label") or f"Opcion {index}")[:80],
            "emoji": str(option.get("emoji") or "")[:80],
            "description": str(option.get("description") or "")[:100],
        })

    if not normalized_options:
        normalized_options.append({
            "id": secrets.token_urlsafe(6),
            "label": "Abrir ticket",
            "emoji": "",
            "description": "Crear un ticket privado",
        })

    permissions = panel.get("permissions") if isinstance(panel.get("permissions"), dict) else {}
    return {
        "id": str(panel.get("id") or secrets.token_urlsafe(8)),
        "name": str(panel.get("name") or "Nuevo panel")[:80],
        "mode": str(panel.get("mode") or "buttons"),
        "channel_id": str(panel.get("channel_id") or ""),
        "open_category_id": str(panel.get("open_category_id") or ""),
        "message_content": str(panel.get("message_content") or ""),
        "embed_title": str(panel.get("embed_title") or "")[:256],
        "embed_description": str(panel.get("embed_description") or "")[:4000],
        "embed_color": str(panel.get("embed_color") or "#22c55e")[:20],
        "embed_footer": str(panel.get("embed_footer") or "")[:2048],
        "image_url": str(panel.get("image_url") or "")[:500],
        "ticket_open_title": str(panel.get("ticket_open_title") or "Ticket abierto")[:256],
        "ticket_open_description": str(panel.get("ticket_open_description") or "Un miembro del staff te atendera pronto.")[:4000],
        "ticket_open_color": str(panel.get("ticket_open_color") or "#38bdf8")[:20],
        "options": normalized_options,
        "permissions": {
            "claim_roles": normalize_id_list(permissions.get("claim_roles"))[:3],
            "close_roles": normalize_id_list(permissions.get("close_roles"))[:3],
            "reopen_roles": normalize_id_list(permissions.get("reopen_roles"))[:3],
            "delete_roles": normalize_id_list(permissions.get("delete_roles"))[:3],
        },
        "updated_at": argentina_now_display(),
    }


def normalize_id_list(value):
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def parse_hex_color(value):
    text = str(value or "").strip().lstrip("#")
    try:
        return int(text, 16)
    except ValueError:
        return 0x22C55E


def build_ticket_components(panel):
    mode = panel.get("mode")
    options = panel.get("options", [])
    if mode == "select":
        return [{
            "type": 1,
            "components": [{
                "type": 3,
                "custom_id": f"ticket_select:{panel['id']}",
                "placeholder": "Selecciona una opcion",
                "options": [
                    {
                        "label": option["label"],
                        "value": option["id"],
                        "description": option.get("description") or "Abrir ticket",
                        **({"emoji": parse_component_emoji(option["emoji"])} if option.get("emoji") else {}),
                    }
                    for option in options[:25]
                ],
            }],
        }]

    rows = []
    current_row = []
    for option in options[:25]:
        current_row.append({
            "type": 2,
            "style": 1,
            "custom_id": f"ticket_button:{panel['id']}:{option['id']}",
            "label": option["label"][:80],
            **({"emoji": parse_component_emoji(option["emoji"])} if option.get("emoji") else {}),
        })
        if len(current_row) == 5:
            rows.append({"type": 1, "components": current_row})
            current_row = []
    if current_row:
        rows.append({"type": 1, "components": current_row})
    return rows


def parse_component_emoji(value):
    text = str(value or "").strip()
    match = re.match(r"^<(?P<animated>a?):(?P<name>[A-Za-z0-9_]+):(?P<id>\d+)>$", text)
    if match:
        emoji = {
            "name": match.group("name"),
            "id": match.group("id"),
        }
        if match.group("animated"):
            emoji["animated"] = True
        return emoji

    return {"name": text}


def build_ticket_message_payload(panel):
    embed = {
        "title": panel.get("embed_title") or panel.get("name"),
        "description": panel.get("embed_description") or "Selecciona una opcion para abrir un ticket.",
        "color": parse_hex_color(panel.get("embed_color")),
    }
    if panel.get("embed_footer"):
        embed["footer"] = {"text": panel["embed_footer"]}
    if panel.get("image_url"):
        embed["image"] = {"url": panel["image_url"]}

    return {
        "content": panel.get("message_content") or "",
        "embeds": [embed],
        "components": build_ticket_components(panel),
        "allowed_mentions": {"parse": []},
    }


def get_connection():
    init_database()
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def row_to_dict(row):
    return {key: row[key] for key in row.keys()}


def get_guilds(connection):
    rows = connection.execute(
        """
        SELECT guild_id, MAX(guild_name) AS guild_name
        FROM (
            SELECT guild_id, guild_name FROM economy_balances
            UNION ALL
            SELECT guild_id, guild_name FROM economy_operations
        )
        GROUP BY guild_id
        ORDER BY COALESCE(NULLIF(MAX(guild_name), ''), guild_id) COLLATE NOCASE
        """
    ).fetchall()

    guilds = []
    seen = set()
    for row in rows:
        guild_id = str(row["guild_id"])
        guild_name = row["guild_name"] or f"Servidor {guild_id}"
        guilds.append({"id": guild_id, "name": guild_name})
        seen.add(guild_id)

    for source in (read_json_file(REPORTS_FILE, {}), read_json_file(AVALONIAN_FILE, {})):
        if not isinstance(source, dict):
            continue
        for guild_id in source.keys():
            guild_id = str(guild_id)
            if guild_id not in seen:
                guilds.append({"id": guild_id, "name": f"Servidor {guild_id}"})
                seen.add(guild_id)

    return guilds


def get_balances(connection, guild_id):
    rows = connection.execute(
        """
        SELECT
            user_id,
            COALESCE(
                NULLIF(user_name, ''),
                (
                    SELECT NULLIF(player, '')
                    FROM economy_operations
                    WHERE guild_id = economy_balances.guild_id
                      AND player_id = economy_balances.user_id
                      AND NULLIF(player, '') IS NOT NULL
                      AND player != 'Usuario ' || economy_balances.user_id
                    ORDER BY id DESC
                    LIMIT 1
                ),
                (
                    SELECT NULLIF(operator, '')
                    FROM economy_operations
                    WHERE guild_id = economy_balances.guild_id
                      AND operator_id = economy_balances.user_id
                      AND NULLIF(operator, '') IS NOT NULL
                      AND operator != 'Usuario ' || economy_balances.user_id
                    ORDER BY id DESC
                    LIMIT 1
                ),
                ''
            ) AS user_name,
            items,
            silver,
            items + silver AS total,
            updated_at
        FROM economy_balances
        WHERE guild_id = ?
        ORDER BY total DESC, user_name COLLATE NOCASE, user_id
        """,
        (str(guild_id),),
    ).fetchall()

    balances = []
    for index, row in enumerate(rows, start=1):
        balance = row_to_dict(row)
        balance["rank"] = index
        balance["user_name"] = clean_user_name(balance.get("user_name"), balance.get("user_id"))
        balance["updated_at_display"] = format_argentina_datetime(balance.get("updated_at"))
        balances.append(balance)

    return balances


def get_operations(connection, guild_id, limit=DEFAULT_LIMIT):
    rows = connection.execute(
        """
        SELECT
            id,
            action,
            operator,
            operator_id,
            player,
            player_id,
            type,
            category,
            amount,
            previous_balance,
            new_balance,
            date,
            time,
            created_at
        FROM economy_operations
        WHERE guild_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (str(guild_id), int(limit)),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_json_records(path, guild_id, limit=DEFAULT_LIMIT):
    data = read_json_file(path, {})
    records = data.get(str(guild_id), []) if isinstance(data, dict) else []
    if not isinstance(records, list):
        return []
    return list(reversed(records[-int(limit):]))


def build_dashboard_data(guild_id=None, allowed_guilds=None, bot_guild_ids=None, viewer=None):
    with get_connection() as connection:
        guilds = get_guilds(connection)
        if allowed_guilds is not None:
            guilds = [
                {
                    "id": guild["id"],
                    "name": guild["name"] if not guild["name"].startswith("Servidor ") else allowed_guilds.get(guild["id"], guild["name"]),
                }
                for guild in guilds
                if guild["id"] in allowed_guilds
            ]
        if bot_guild_ids is not None:
            guilds = [guild for guild in guilds if guild["id"] in bot_guild_ids]
        requested_guild_id = str(guild_id or "")
        available_guild_ids = {guild["id"] for guild in guilds}
        if requested_guild_id and requested_guild_id in available_guild_ids:
            selected_guild_id = requested_guild_id
        else:
            selected_guild_id = guilds[0]["id"] if guilds else ""
        balances = get_balances(connection, selected_guild_id) if selected_guild_id else []
        operations = get_operations(connection, selected_guild_id) if selected_guild_id else []

    reports = get_json_records(REPORTS_FILE, selected_guild_id) if selected_guild_id else []
    avalonians = get_json_records(AVALONIAN_FILE, selected_guild_id) if selected_guild_id else []
    totals = {
        "players": len(balances),
        "items": sum(int(row["items"] or 0) for row in balances),
        "silver": sum(int(row["silver"] or 0) for row in balances),
    }
    totals["total"] = totals["items"] + totals["silver"]

    return {
        "guilds": guilds,
        "selectedGuildId": selected_guild_id,
        "balances": balances,
        "operations": operations,
        "avalonians": avalonians,
        "reports": reports,
        "totals": totals,
        "updatedAt": argentina_now_display(),
        "viewer": viewer or {},
    }


LOGIN_HTML = r"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AvalonBot</title>
  <style>
    :root {
      --bg: #f5f7fb;
      --panel: #ffffff;
      --ink: #18212f;
      --muted: #657084;
      --line: #d9e0ea;
      --brand: #0b6bcb;
      --shadow: 0 10px 28px rgba(25, 35, 55, .08);
    }

    * { box-sizing: border-box; }
    [hidden] { display: none !important; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: var(--bg);
      color: var(--ink);
      font-family: "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
      letter-spacing: 0;
    }

    main {
      width: min(420px, calc(100vw - 32px));
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 24px;
    }

    h1 {
      margin: 0 0 8px;
      font-size: 32px;
      line-height: 1.2;
      background: linear-gradient(90deg, #16a34a, #0ea5e9, #2563eb);
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
    }

    img {
      width: 118px;
      height: 118px;
      display: block;
      object-fit: cover;
      border-radius: 10px;
      margin: 0 auto 14px;
      box-shadow: 0 12px 30px rgba(37, 99, 235, .22);
    }

    p {
      margin: 0 0 18px;
      color: var(--muted);
      line-height: 1.5;
    }

    form {
      display: grid;
      gap: 14px;
    }

    label {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 14px;
    }

    input {
      width: 16px;
      height: 16px;
      accent-color: var(--brand);
    }

    button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 100%;
      min-height: 40px;
      border: 1px solid var(--brand);
      border-radius: 6px;
      background: var(--brand);
      color: #fff;
      cursor: pointer;
      font: inherit;
      font-weight: 700;
    }
  </style>
</head>
<body>
  <main>
    <img src="/assets/AvalonBot.png" alt="AvalonBot">
    <h1>AvalonBot</h1>
    <p>Ingresa con Discord para administrar los servidores donde tienes permisos.</p>
    <form action="/login" method="get">
      <label>
        <input type="checkbox" name="remember" value="1" checked>
        Recordar este dispositivo
      </label>
      <button type="submit">Ingresar</button>
    </form>
  </main>
</body>
</html>
"""


INDEX_HTML = r"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AvalonBot</title>
  <style>
    :root {
      --bg: #f4f7fb;
      --panel: #ffffff;
      --ink: #18212f;
      --muted: #657084;
      --line: #d9e0ea;
      --brand: #2563eb;
      --brand-soft: #eaf1ff;
      --teal: #0f766e;
      --teal-soft: #e7f7f4;
      --violet: #7c3aed;
      --violet-soft: #f1ebff;
      --green: #13795b;
      --gold: #9a6700;
      --red: #b42318;
      --shadow: 0 10px 28px rgba(25, 35, 55, .08);
      --page-gradient: linear-gradient(180deg, #eef5ff 0, #f7fafc 190px, var(--bg) 100%);
      --header-bg: rgba(255, 255, 255, .94);
      --control-bg: #ffffff;
      --table-head: #eef4fb;
      --row-hover: #f8fbff;
      --active-ink: #074d94;
      --panel-glass: rgba(255, 255, 255, .76);
      --add-bg: #eaf7f1;
      --add-line: #b9e2d3;
      --remove-bg: #fff0ef;
      --remove-line: #f3c0bc;
      --silver-bg: #fff7df;
      --silver-line: #eed892;
    }

    body.theme-dark {
      --bg: #0d1117;
      --panel: #151b23;
      --ink: #eef6ff;
      --muted: #9aa8ba;
      --line: #2b3442;
      --brand: #38bdf8;
      --brand-soft: #0c3145;
      --teal: #34d399;
      --teal-soft: #0f3028;
      --violet: #a78bfa;
      --violet-soft: #2a2146;
      --green: #5ee58a;
      --gold: #facc15;
      --red: #fb7185;
      --shadow: 0 12px 32px rgba(0, 0, 0, .28);
      --page-gradient: linear-gradient(180deg, #08111f 0, #0f172a 220px, var(--bg) 100%);
      --header-bg: rgba(13, 17, 23, .92);
      --control-bg: #101722;
      --table-head: #101722;
      --row-hover: #101722;
      --active-ink: #d9f4ff;
      --panel-glass: rgba(21, 27, 35, .78);
      --add-bg: #113326;
      --add-line: #23684e;
      --remove-bg: #371920;
      --remove-line: #7f2d3d;
      --silver-bg: #33290c;
      --silver-line: #705c16;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--page-gradient);
      color: var(--ink);
      font-family: "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
      letter-spacing: 0;
    }

    header {
      background: var(--header-bg);
      border-bottom: 1px solid var(--line);
      position: sticky;
      top: 0;
      z-index: 3;
      backdrop-filter: blur(10px);
    }

    .bar {
      max-width: 1280px;
      margin: 0 auto;
      padding: 14px 18px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto auto;
      gap: 12px;
      align-items: center;
    }

    .top-brand {
      min-width: 0;
      display: flex;
      align-items: center;
      gap: 12px;
      color: var(--ink);
    }

    .brand-logo {
      width: 54px;
      height: 54px;
      border-radius: 8px;
      object-fit: cover;
      box-shadow: 0 8px 20px rgba(37, 99, 235, .22);
    }

    .top-brand strong {
      font-size: 31px;
      line-height: 1.1;
      letter-spacing: 0;
      background: linear-gradient(90deg, #16a34a 0%, #22c55e 35%, #0ea5e9 72%, #2563eb 100%);
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
    }

    .top-brand span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-top: 2px;
    }

    h1, h2 {
      margin: 0;
      font-weight: 700;
    }

    .controls {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    select, input, button {
      height: 36px;
      border: 1px solid var(--line);
      background: var(--control-bg);
      color: var(--ink);
      border-radius: 6px;
      padding: 0 10px;
      font: inherit;
    }

    button {
      cursor: pointer;
      padding: 0 12px;
    }

    .primary-button {
      border-color: var(--brand);
      background: var(--brand);
      color: #fff;
      font-weight: 700;
    }

    .session {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }

    #userLabel {
      min-height: 36px;
      display: inline-flex;
      align-items: center;
      border: 1px solid rgba(37, 99, 235, .28);
      border-radius: 999px;
      padding: 0 12px;
      background: linear-gradient(135deg, var(--brand-soft), var(--teal-soft));
      color: var(--active-ink);
      font-weight: 800;
      box-shadow: 0 8px 18px rgba(37, 99, 235, .10);
    }

    body.theme-dark #userLabel {
      border-color: rgba(56, 189, 248, .34);
      box-shadow: 0 8px 22px rgba(56, 189, 248, .10);
    }

    .theme-button {
      width: 40px;
      min-width: 40px;
      border-color: var(--line);
      background: var(--control-bg);
      color: var(--ink);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 18px;
      font-weight: 700;
      padding: 0;
    }

    .status {
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }

    main {
      max-width: 1280px;
      margin: 0 auto;
      padding: 16px 18px 18px;
    }

    .app-shell {
      display: grid;
      grid-template-columns: 230px minmax(0, 1fr);
      gap: 16px;
      align-items: start;
    }

    .app-shell.sidebar-collapsed {
      grid-template-columns: 64px minmax(0, 1fr);
    }

    .app-shell.transcript-open {
      grid-template-columns: minmax(0, 1fr);
      padding: 0;
      min-height: 100vh;
    }

    .app-shell.transcript-open .sections {
      display: none;
    }

    body.transcript-open header {
      display: none;
    }

    .sections {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 12px;
      transition: width .18s ease;
    }

    .menu-button {
      width: 40px;
      height: 36px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
      flex-direction: column;
      margin-bottom: 12px;
      border-color: var(--line);
      background: var(--control-bg);
    }

    .sidebar-collapsed .menu-button {
      width: 100%;
    }

    .menu-button span {
      width: 18px;
      height: 2px;
      border-radius: 999px;
      background: var(--ink);
    }

    .section-label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      margin: 2px 0 8px;
    }

    .sidebar-collapsed .section-label {
      display: none;
    }

    .section-list {
      display: grid;
      gap: 8px;
    }

    .section-button {
      width: 100%;
      display: flex;
      align-items: center;
      gap: 8px;
      justify-content: flex-start;
      text-align: left;
      border-color: var(--line);
      background: var(--control-bg);
      color: var(--ink);
      font-weight: 700;
    }

    .section-button.active {
      border-color: var(--brand);
      background: var(--brand-soft);
      color: var(--active-ink);
    }

    .section-icon {
      width: 22px;
      min-width: 22px;
      text-align: center;
      font-size: 15px;
    }

    .sidebar-collapsed .section-text {
      display: none;
    }

    .sidebar-collapsed .section-button {
      justify-content: center;
      padding: 0;
    }

    .module-header {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }

    .module-header h2 {
      margin: 0;
      font-size: 18px;
      line-height: 1.2;
    }

    .module-header p {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 13px;
    }

    .economy-panel {
      background: var(--panel-glass);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 12px;
    }

    .module-panel {
      background: var(--panel-glass);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 18px;
    }

    .placeholder {
      min-height: 280px;
      display: grid;
      align-content: center;
      justify-items: center;
      gap: 8px;
      text-align: center;
      color: var(--muted);
    }

    .placeholder strong {
      color: var(--ink);
      font-size: 20px;
    }

    .ticket-dashboard {
      display: grid;
      gap: 14px;
    }

    .ticket-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }

    .ticket-toolbar h2 {
      font-size: 20px;
      line-height: 1.2;
    }

    .ticket-toolbar p {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 13px;
    }

    .ticket-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .action-button {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      font-weight: 800;
    }

    .action-button.primary {
      border-color: var(--brand);
      background: var(--brand);
      color: #fff;
    }

    .action-button.warning {
      border-color: var(--gold);
      background: var(--silver-bg);
      color: var(--gold);
    }

    .action-button.danger {
      border-color: var(--red);
      background: var(--remove-bg);
      color: var(--red);
    }

    .ticket-summary {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }

    .ticket-stat {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      box-shadow: var(--shadow);
    }

    .ticket-stat span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
    }

    .ticket-stat strong {
      font-size: 22px;
      line-height: 1.2;
    }

    .ticket-list {
      display: grid;
      gap: 8px;
    }

    .ticket-builder {
      display: grid;
      grid-template-columns: minmax(220px, 320px) minmax(0, 1fr);
      gap: 14px;
      align-items: start;
    }

    .template-builder {
      display: grid;
      grid-template-columns: minmax(220px, 320px) minmax(0, 1fr);
      gap: 14px;
      align-items: start;
      min-width: 0;
    }

    .template-builder aside {
      display: grid;
      gap: 8px;
      align-content: start;
    }

    .ticket-builder aside {
      display: grid;
      gap: 8px;
      align-content: start;
    }

    .panel-list {
      display: grid;
      gap: 8px;
    }

    .panel-list button {
      height: auto;
      min-height: 44px;
      display: block;
      text-align: left;
      padding: 10px;
      background: var(--control-bg);
      color: var(--ink);
    }

    .panel-list button.active {
      border-color: var(--brand);
      background: var(--brand-soft);
      color: var(--active-ink);
      font-weight: 800;
    }

    .ticket-editor {
      display: grid;
      gap: 12px;
    }

    .template-editor {
      display: grid;
      gap: 12px;
      min-width: 0;
      overflow: hidden;
    }

    .check-row {
      min-height: 36px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--ink);
      font-weight: 800;
    }

    .check-row input {
      width: 18px;
      height: 18px;
    }

    .placeholder-list {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
      min-width: 0;
      overflow-wrap: anywhere;
    }

    .editor-tabs {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--control-bg);
      padding: 8px;
    }

    .editor-tab {
      min-height: 34px;
      font-weight: 800;
    }

    .editor-tab.active {
      border-color: var(--brand);
      background: var(--brand-soft);
      color: var(--active-ink);
    }

    .ticket-editor[hidden],
    .ticket-empty-editor[hidden] {
      display: none;
    }

    .ticket-empty-editor {
      min-height: 360px;
      display: grid;
      align-content: center;
      justify-items: center;
      gap: 8px;
      text-align: center;
      color: var(--muted);
      border: 1px dashed var(--line);
      border-radius: 8px;
      background: var(--control-bg);
      padding: 22px;
    }

    .ticket-empty-editor strong {
      color: var(--ink);
      font-size: 18px;
    }

    .form-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      min-width: 0;
    }

    .editor-section {
      display: grid;
      gap: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--control-bg);
      padding: 12px;
    }

    .editor-section[hidden] {
      display: none;
    }

    .editor-section-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 9px;
      margin-bottom: 2px;
    }

    .editor-section-header strong {
      font-size: 14px;
      line-height: 1.2;
    }

    .editor-section-header span {
      color: var(--muted);
      font-size: 12px;
    }

    .field {
      display: grid;
      gap: 5px;
      min-width: 0;
    }

    .field.full {
      grid-column: 1 / -1;
    }

    .field label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
    }

    textarea {
      width: 100%;
      max-width: 100%;
      min-height: 92px;
      resize: vertical;
      border: 1px solid var(--line);
      background: var(--control-bg);
      color: var(--ink);
      border-radius: 6px;
      padding: 10px;
      font: inherit;
      overflow-wrap: anywhere;
      white-space: pre-wrap;
    }

    .template-editor input,
    .template-editor textarea {
      width: 100%;
      max-width: 100%;
      min-width: 0;
      box-sizing: border-box;
    }

    .option-list {
      display: grid;
      gap: 8px;
    }

    .role-picker {
      position: relative;
      display: grid;
      gap: 6px;
    }

    .role-picker-trigger {
      width: 100%;
      justify-content: space-between;
      text-align: left;
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }

    .role-picker-trigger::after {
      content: "";
      width: 8px;
      height: 8px;
      border-right: 2px solid currentColor;
      border-bottom: 2px solid currentColor;
      transform: rotate(45deg) translateY(-2px);
      opacity: .7;
      flex: 0 0 auto;
    }

    .role-picker.open .role-picker-trigger::after {
      transform: rotate(225deg) translateY(-1px);
    }

    .role-picker-selected {
      min-height: 28px;
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }

    .role-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 24px;
      border: 1px solid color-mix(in srgb, var(--brand) 42%, var(--line));
      background: color-mix(in srgb, var(--brand) 12%, var(--control-bg));
      color: var(--ink);
      border-radius: 999px;
      padding: 0 8px;
      font-size: 12px;
      font-weight: 800;
    }

    .role-chip button {
      width: 18px;
      height: 18px;
      min-width: 18px;
      padding: 0;
      border-radius: 999px;
      display: inline-grid;
      place-items: center;
      border-color: transparent;
      background: transparent;
      color: var(--muted);
      font-weight: 900;
    }

    .role-picker-menu {
      position: absolute;
      z-index: 30;
      top: calc(100% + 4px);
      left: 0;
      right: 0;
      display: none;
      max-height: 260px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
      padding: 8px;
    }

    .role-picker.open .role-picker-menu {
      display: grid;
      gap: 8px;
    }

    .role-picker-search {
      width: 100%;
    }

    .role-picker-options {
      display: grid;
      gap: 4px;
      max-height: 198px;
      overflow: auto;
      padding-right: 2px;
    }

    .role-picker-option {
      width: 100%;
      display: grid;
      grid-template-columns: 18px minmax(0, 1fr);
      align-items: center;
      gap: 8px;
      text-align: left;
      border-color: transparent;
      background: transparent;
      color: var(--ink);
      min-height: 32px;
    }

    .role-picker-option:hover,
    .role-picker-option.active {
      border-color: color-mix(in srgb, var(--brand) 42%, var(--line));
      background: color-mix(in srgb, var(--brand) 10%, transparent);
    }

    .role-picker-option:disabled {
      cursor: not-allowed;
      opacity: .45;
    }

    .role-picker-check {
      width: 16px;
      height: 16px;
      border: 1px solid var(--line);
      border-radius: 4px;
      display: inline-grid;
      place-items: center;
      color: var(--brand);
      font-weight: 900;
    }

    .role-picker-empty {
      color: var(--muted);
      font-size: 12px;
      padding: 8px;
    }

    .option-row {
      display: grid;
      grid-template-columns: minmax(120px, .8fr) minmax(0, 1fr) minmax(0, 1.2fr) 36px;
      gap: 8px;
      align-items: center;
    }

    .publish-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
      justify-content: flex-end;
    }

    .preview-box {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--control-bg);
      padding: 12px;
      min-width: 0;
      overflow: hidden;
    }

    .preview-box strong {
      display: block;
      margin-bottom: 6px;
    }

    .discord-preview {
      display: grid;
      gap: 10px;
      border-left: 4px solid var(--brand);
      background: var(--panel);
      border-radius: 8px;
      padding: 12px;
      box-shadow: var(--shadow);
      min-width: 0;
    }

    .discord-preview-title {
      font-weight: 900;
      color: var(--ink);
    }

    .discord-preview-description {
      color: var(--muted);
      white-space: pre-wrap;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }

    .discord-preview-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .discord-preview-action {
      min-height: 30px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--control-bg);
      padding: 0 10px;
      font-size: 12px;
      font-weight: 800;
    }

    .records-toolbar {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      margin-bottom: 8px;
    }

    .records-toolbar.compact {
      display: grid;
      gap: 8px;
    }

    .records-toolbar.compact button,
    .records-toolbar.compact input {
      width: 100%;
    }

    .ticket-records-side {
      display: grid;
      gap: 8px;
      margin-top: 12px;
      border-top: 1px solid var(--line);
      padding-top: 12px;
    }

    .ticket-records-side .ticket-list {
      max-height: 420px;
      overflow: auto;
      padding-right: 2px;
    }

    .ticket-records-side .ticket-card {
      grid-template-columns: 1fr;
      gap: 8px;
      padding: 10px;
    }

    .ticket-records-side .ticket-card-actions {
      justify-content: stretch;
    }

    .ticket-records-side .ticket-card-actions button {
      width: 100%;
    }

    .transcript-box {
      display: grid;
      gap: 0;
      height: calc(100vh - 74px);
      min-height: 540px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 0;
      background: var(--control-bg);
      padding: 0;
    }

    .ticket-transcript-page {
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      gap: 10px;
      min-height: calc(100vh - 86px);
      margin: -18px;
    }

    .ticket-transcript-page .ticket-toolbar {
      padding: 14px 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }

    .transcript-summary {
      display: grid;
      gap: 4px;
      border: 1px solid var(--line);
      border-radius: 0;
      background: var(--panel);
      padding: 10px;
      color: var(--muted);
      font-size: 12px;
    }

    .transcript-summary strong {
      margin: 0;
      color: var(--ink);
      font-size: 14px;
    }

    .transcript-message {
      display: grid;
      grid-template-columns: 42px minmax(0, 1fr);
      gap: 10px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      padding: 12px;
    }

    .transcript-message:last-child {
      border-bottom: 0;
    }

    .transcript-avatar {
      width: 38px;
      height: 38px;
      border-radius: 50%;
      border: 1px solid var(--line);
      background: linear-gradient(135deg, var(--brand), var(--green));
      color: #fff;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-weight: 900;
      overflow: hidden;
    }

    .transcript-avatar img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }

    .transcript-body {
      min-width: 0;
      display: grid;
      gap: 6px;
    }

    .transcript-author-line {
      display: flex;
      gap: 8px;
      align-items: baseline;
      flex-wrap: wrap;
    }

    .transcript-author {
      color: var(--ink);
      font-weight: 900;
    }

    .transcript-bot-badge {
      border-radius: 4px;
      background: var(--brand);
      color: #fff;
      padding: 1px 5px;
      font-size: 10px;
      font-weight: 900;
      text-transform: uppercase;
    }

    .transcript-content {
      color: var(--ink);
      line-height: 1.45;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }

    .transcript-embed {
      display: grid;
      gap: 6px;
      border-left: 4px solid var(--brand);
      border-radius: 8px;
      background: var(--control-bg);
      padding: 10px;
    }

    .transcript-embed-title {
      font-weight: 900;
      color: var(--ink);
    }

    .transcript-embed-field {
      display: grid;
      gap: 2px;
      color: var(--muted);
      font-size: 12px;
    }

    .transcript-attachments {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .transcript-attachment {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--control-bg);
      padding: 8px 10px;
      color: var(--brand);
      font-weight: 800;
      text-decoration: none;
    }

    .transcript-image {
      max-width: min(520px, 100%);
      max-height: 420px;
      border: 1px solid var(--line);
      border-radius: 8px;
      object-fit: contain;
      background: var(--control-bg);
    }

    .permissions-list {
      display: grid;
      gap: 8px;
      min-width: 860px;
    }

    .permissions-grid {
      overflow-x: auto;
      padding-bottom: 4px;
    }

    .permissions-list-head,
    .permission-row {
      display: grid;
      grid-template-columns: minmax(180px, 1.1fr) repeat(6, minmax(82px, .55fr));
      gap: 8px;
      align-items: center;
    }

    .permissions-list-head {
      color: var(--muted);
      font-size: 11px;
      font-weight: 900;
      text-transform: uppercase;
      padding: 0 10px;
    }

    .permission-row {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 10px;
      box-shadow: var(--shadow);
    }

    .permission-role {
      display: grid;
      gap: 3px;
      min-width: 0;
    }

    .permission-role strong {
      color: var(--ink);
      font-size: 14px;
      overflow-wrap: anywhere;
    }

    .permission-pill {
      min-height: 32px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--control-bg);
      color: var(--muted);
      font-size: 12px;
      font-weight: 900;
      cursor: pointer;
      padding: 0 10px;
      user-select: none;
    }

    .permission-pill input {
      width: 15px;
      height: 15px;
      margin: 0;
      accent-color: var(--brand);
    }

    .permission-pill.active {
      border-color: color-mix(in srgb, var(--brand) 55%, var(--line));
      background: color-mix(in srgb, var(--brand) 14%, var(--control-bg));
      color: var(--ink);
    }

    .permission-pill.global {
      border-color: color-mix(in srgb, var(--green) 48%, var(--line));
      background: color-mix(in srgb, var(--green) 12%, var(--control-bg));
    }

    .permission-pill:has(input:disabled) {
      opacity: .45;
      cursor: not-allowed;
    }

    .ticket-card {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: center;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      box-shadow: var(--shadow);
    }

    .ticket-card h3 {
      margin: 0 0 6px;
      font-size: 15px;
      line-height: 1.2;
    }

    .ticket-meta {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 12px;
    }

    .ticket-card-actions {
      display: flex;
      gap: 6px;
      align-items: center;
    }

    .view-transcript-button.active {
      border-color: var(--brand);
      background: var(--brand);
      color: #fff;
    }

    .icon-button {
      width: 36px;
      min-width: 36px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0;
      font-weight: 900;
    }

    .ticket-status {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 0 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 800;
      color: var(--green);
      background: var(--add-bg);
      border: 1px solid var(--add-line);
    }

    .audit-dashboard {
      display: grid;
      gap: 14px;
    }

    .audit-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .audit-card {
      display: grid;
      gap: 8px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--control-bg);
      padding: 12px;
    }

    .audit-card strong {
      font-size: 14px;
    }

    .audit-card p {
      margin: 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }

    .audit-event-sections {
      display: grid;
      gap: 10px;
    }

    .audit-event-section {
      display: grid;
      gap: 8px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--control-bg);
      overflow: hidden;
    }

    .audit-event-section summary {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      cursor: pointer;
      padding: 12px;
      font-weight: 900;
      color: var(--ink);
      list-style: none;
    }

    .audit-event-section summary::-webkit-details-marker {
      display: none;
    }

    .audit-event-section summary::after {
      content: "+";
      width: 24px;
      min-width: 24px;
      height: 24px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--brand);
      background: var(--panel);
    }

    .audit-event-section[open] summary::after {
      content: "-";
    }

    .audit-event-list {
      display: grid;
      gap: 8px;
      padding: 0 10px 10px;
    }

    .audit-event-section h3 {
      margin: 0;
      font-size: 14px;
      line-height: 1.2;
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }

    .metric {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      box-shadow: var(--shadow);
    }

    .metric:nth-child(1) { border-top: 3px solid var(--brand); }
    .metric:nth-child(2) { border-top: 3px solid var(--teal); }
    .metric:nth-child(3) { border-top: 3px solid var(--gold); }
    .metric:nth-child(4) { border-top: 3px solid var(--violet); }

    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
    }

    .metric strong {
      font-size: 21px;
      line-height: 1.2;
    }

    .tabs {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin: 8px 0 12px;
    }

    .tab {
      border: 1px solid var(--line);
      background: var(--control-bg);
      color: var(--ink);
      border-radius: 6px;
      min-height: 36px;
      padding: 0 12px;
      font: inherit;
      cursor: pointer;
    }

    .tab.active {
      border-color: var(--brand);
      background: var(--brand-soft);
      color: var(--active-ink);
      font-weight: 700;
    }

    .table-wrap {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow: auto;
      max-height: calc(100vh - 240px);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 860px;
    }

    th, td {
      border-bottom: 1px solid var(--line);
      padding: 9px 10px;
      text-align: left;
      font-size: 14px;
      vertical-align: middle;
    }

    th {
      background: var(--table-head);
      color: #27364a;
      position: sticky;
      top: 0;
      z-index: 2;
      font-size: 12px;
      text-transform: uppercase;
    }

    td.number, th.number { text-align: right; font-variant-numeric: tabular-nums; }
    tr:hover td { background: var(--row-hover); }
    .muted { color: var(--muted); }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 0 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid var(--line);
      background: var(--control-bg);
    }
    .add, .accepted { color: var(--green); background: var(--add-bg); border-color: var(--add-line); }
    .remove, .rejected { color: var(--red); background: var(--remove-bg); border-color: var(--remove-line); }
    .silver { color: var(--gold); background: var(--silver-bg); border-color: var(--silver-line); }
    .items { color: var(--brand); background: #eaf3ff; border-color: #bad8f7; }

    .empty {
      padding: 26px;
      text-align: center;
      color: var(--muted);
    }

    @media (max-width: 760px) {
      .bar { grid-template-columns: 1fr; }
      .controls, .session { justify-content: stretch; }
      select, input, button { width: 100%; }
      .app-shell, .app-shell.sidebar-collapsed { grid-template-columns: 1fr; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .ticket-summary { grid-template-columns: 1fr; }
      .ticket-card { grid-template-columns: 1fr; }
      .ticket-card-actions { justify-content: flex-start; }
      .ticket-builder { grid-template-columns: 1fr; }
      .template-builder { grid-template-columns: 1fr; }
      .form-grid { grid-template-columns: 1fr; }
      .option-row { grid-template-columns: 1fr; }
      .audit-grid { grid-template-columns: 1fr; }
      .permissions-list { min-width: 0; }
      .permissions-list-head { display: none; }
      .permission-row {
        grid-template-columns: 1fr;
        align-items: stretch;
      }
      .permission-pill {
        justify-content: flex-start;
      }
      .table-wrap { max-height: calc(100vh - 330px); }
      .transcript-box { min-height: 420px; }
    }
  </style>
</head>
<body>
  <header>
    <div class="bar">
      <div class="top-brand">
        <img class="brand-logo" src="/assets/AvalonBot.png" alt="AvalonBot">
        <div>
          <strong>AvalonBot</strong>
          <span>Panel de administracion</span>
        </div>
      </div>
      <div class="controls">
        <select id="guildSelect" aria-label="Servidor"></select>
        <input id="searchInput" type="search" placeholder="Buscar" aria-label="Buscar">
      </div>
      <div class="session">
        <span id="userLabel">No conectado</span>
        <button id="themeToggle" class="theme-button" type="button" aria-label="Cambiar tema" title="Cambiar tema"></button>
        <button id="logoutButton" type="button" hidden>Salir</button>
      </div>
    </div>
  </header>
  <main>
    <div id="appShell" class="app-shell">
      <aside class="sections" aria-label="Modulos">
        <button id="sidebarToggle" class="menu-button" type="button" aria-label="Minimizar secciones">
          <span></span>
          <span></span>
          <span></span>
        </button>
        <div class="section-label">Secciones</div>
        <nav class="section-list">
          <button class="section-button active" type="button" data-section="economy" title="Economia">
            <span class="section-icon">$</span>
            <span class="section-text">Economia</span>
          </button>
          <button class="section-button" type="button" data-section="templates" title="Plantillas">
            <span class="section-icon">P</span>
            <span class="section-text">Plantillas</span>
          </button>
          <button class="section-button" type="button" data-section="tickets" title="Tickets">
            <span class="section-icon">#</span>
            <span class="section-text">Tickets</span>
          </button>
          <button class="section-button" type="button" data-section="welcome" title="Bienvenidas">
            <span class="section-icon">+</span>
            <span class="section-text">Bienvenidas</span>
          </button>
          <button class="section-button" type="button" data-section="audit" title="Auditoria">
            <span class="section-icon">!</span>
            <span class="section-text">Auditoria</span>
          </button>
          <button class="section-button" type="button" data-section="permissions" title="Permisos">
            <span class="section-icon">*</span>
            <span class="section-text">Permisos</span>
          </button>
        </nav>
      </aside>
      <section id="economySection" aria-label="Economia">
        <div class="economy-panel">
          <div class="module-header">
            <p>Balances, registros de balance, Avas e informes.</p>
            <div id="status" class="status">Cargando...</div>
          </div>

          <nav class="tabs" aria-label="Opciones de Economia">
            <button class="tab active" data-tab="balances">Balances</button>
            <button class="tab" data-tab="operations">Registro Balance</button>
            <button class="tab" data-tab="avalonians">Registro Avas</button>
            <button class="tab" data-tab="reports">Registro Informes</button>
          </nav>

          <section class="metrics" aria-label="Totales">
            <div class="metric"><span>Jugadores</span><strong id="playersTotal">0</strong></div>
            <div class="metric"><span>Items</span><strong id="itemsTotal">0</strong></div>
            <div class="metric"><span>Silver</span><strong id="silverTotal">0</strong></div>
            <div class="metric"><span>Total</span><strong id="overallTotal">0</strong></div>
          </section>

          <section class="table-wrap">
            <table>
              <thead id="tableHead"></thead>
              <tbody id="tableBody"></tbody>
            </table>
            <div id="emptyState" class="empty" hidden>No hay datos para mostrar.</div>
          </section>
        </div>
      </section>
      <section id="templatesSection" class="module-panel" aria-label="Plantillas" hidden>
        <div class="ticket-dashboard">
          <div class="ticket-toolbar">
            <div>
              <h2>Plantillas</h2>
              <p>Gestiona las plantillas de ping que tambien usa el comando /plantilla.</p>
            </div>
            <div class="ticket-actions">
              <button id="newTemplateButton" class="action-button primary" type="button">+ Nueva plantilla</button>
              <button id="saveTemplateButton" class="action-button primary" type="button">Guardar plantilla</button>
              <button id="deleteTemplateButton" class="action-button danger" type="button">Eliminar plantilla</button>
            </div>
          </div>

          <section class="ticket-summary" aria-label="Resumen de plantillas">
            <div class="ticket-stat"><span>Guardadas</span><strong id="templateSavedTotal">0</strong></div>
            <div class="ticket-stat"><span>Limite</span><strong id="templateLimitTotal">5</strong></div>
            <div class="ticket-stat"><span>Disponibles</span><strong id="templateAvailableTotal">0</strong></div>
          </section>

          <section class="template-builder" aria-label="Editor de plantillas">
            <aside>
              <div class="section-label">Plantillas disponibles</div>
              <div id="templateList" class="panel-list"></div>
            </aside>

            <div class="template-editor">
              <div class="form-grid">
                <div class="field">
                  <label for="templateKey">Clave</label>
                  <input id="templateKey" type="text" placeholder="postulacion-ava">
                  <input id="templateOriginalKey" type="hidden">
                </div>
                <div class="field">
                  <label for="templateName">Nombre visible</label>
                  <input id="templateName" type="text" placeholder="Postulacion Avalonianas">
                </div>
                <div class="field">
                  <label for="templateTitle">Titulo base</label>
                  <input id="templateTitle" type="text" placeholder="Ava {numero}">
                </div>
                <div class="field">
                  <label for="templateMention">Mencion</label>
                  <input id="templateMention" type="text" placeholder="||@everyone||">
                </div>
                <div class="field">
                  <label for="templateJoinCommand">Comando join</label>
                  <input id="templateJoinCommand" type="text" placeholder="/join {caller}">
                </div>
                <div class="field">
                  <label for="templateCallerSlot">Slot caller</label>
                  <input id="templateCallerSlot" type="text" placeholder="MainTank">
                </div>
                <div class="field full">
                  <label for="templateRoles">Botones / cupos, uno por linea</label>
                  <textarea id="templateRoles" placeholder="MainTank&#10;OffTank&#10;Heal&#10;DPS"></textarea>
                </div>
                <div class="field full">
                  <label for="templateContent">Mensaje que se publica en Discord</label>
                  <textarea id="templateContent" placeholder="# {title} {mention}&#10;&#10;{join_command}&#10;&#10;{slots}&#10;&#10;Cupos: {occupied}/{total}{status}"></textarea>
                </div>
                <div class="field">
                  <label for="templateSlotFormat">Formato de cupo</label>
                  <input id="templateSlotFormat" type="text" placeholder="> **{index}.{slot}:** {user}">
                </div>
                <div class="field">
                  <label for="templateLootLink">Loot link</label>
                  <input id="templateLootLink" type="text" placeholder="https://...">
                </div>
                <label class="check-row">
                  <input id="templateReportEnabled" type="checkbox">
                  <span>Permitir informes al finalizar</span>
                </label>
              </div>

              <div class="preview-box">
                <strong>Vista previa</strong>
                <div id="templatePreview" class="discord-preview"></div>
              </div>
              <div class="preview-box">
                <strong>Placeholders disponibles</strong>
                <div class="placeholder-list">{title} {numero} {template} {mention} {caller} {join_command} {slots} {loot_link} {occupied} {total} {status}</div>
              </div>
              <div id="templateStatus" class="status"></div>
            </div>
          </section>
        </div>
      </section>
      <section id="ticketsSection" class="module-panel" aria-label="Tickets" hidden>
        <div id="ticketDashboardMain" class="ticket-dashboard">
          <div class="ticket-toolbar">
            <div>
              <h2>Tickets</h2>
              <p>Configura paneles, mensajes, opciones, emojis, permisos y publicacion en Discord.</p>
            </div>
            <div class="ticket-actions">
              <button id="createPanelButton" class="action-button primary" type="button">
                <span>+</span>
                Crear panel
              </button>
              <button id="clonePanelButton" class="action-button warning" type="button">
                <span>*</span>
                Clonar panel
              </button>
              <button id="deletePanelButton" class="action-button danger" type="button">
                <span>x</span>
                Eliminar panel
              </button>
            </div>
          </div>

          <section class="ticket-summary" aria-label="Resumen de tickets">
            <div class="ticket-stat"><span>Paneles</span><strong id="ticketPanelTotal">0</strong></div>
            <div class="ticket-stat"><span>Abiertos</span><strong>0</strong></div>
            <div class="ticket-stat"><span>Cerrados hoy</span><strong>0</strong></div>
          </section>

          <section class="ticket-builder" aria-label="Constructor de tickets">
            <aside>
              <div class="section-label">Paneles creados</div>
              <div id="ticketPanelList" class="panel-list"></div>
              <div class="ticket-records-side">
                <div class="section-label">Tickets y transcripciones</div>
                <div class="records-toolbar compact">
                  <input id="ticketRecordSearch" type="search" placeholder="Buscar ticket">
                  <button id="refreshTicketRecordsButton" class="action-button" type="button">Actualizar</button>
                </div>
                <div id="ticketRecordsList" class="ticket-list"></div>
              </div>
            </aside>

            <div id="ticketEmptyEditor" class="ticket-empty-editor">
              <strong>Selecciona o crea un panel</strong>
              <p>Cuando crees un panel, apareceran aca todas sus opciones configurables.</p>
            </div>

            <div id="ticketEditor" class="ticket-editor" hidden>
              <nav class="editor-tabs" aria-label="Opciones del panel de ticket">
                <button class="editor-tab active" type="button" data-editor-section="identity">Identidad</button>
                <button class="editor-tab" type="button" data-editor-section="send">Enviar a</button>
                <button class="editor-tab" type="button" data-editor-section="message">Mensaje Discord</button>
                <button class="editor-tab" type="button" data-editor-section="ticketMessage">Mensaje ticket</button>
                <button class="editor-tab" type="button" data-editor-section="options">Emojis/opciones</button>
                <button class="editor-tab" type="button" data-editor-section="permissions">Permisos</button>
                <button class="editor-tab" type="button" data-editor-section="preview">Vista/envio</button>
              </nav>

              <div class="editor-section" data-editor-panel="identity">
                <div class="editor-section-header">
                  <div>
                    <strong>Identidad del panel</strong>
                    <span>Nombre interno y formato que vera Discord.</span>
                  </div>
                </div>
                <div class="form-grid">
                  <div class="field">
                    <label for="ticketName">Nombre</label>
                    <input id="ticketName" type="text" placeholder="Postulacion Avalonianas">
                  </div>
                  <div class="field">
                    <label for="ticketMode">Modo en Discord</label>
                    <select id="ticketMode">
                      <option value="buttons">Botones / emojis</option>
                      <option value="select">Lista desplegable</option>
                    </select>
                  </div>
                </div>
              </div>

              <div class="editor-section" data-editor-panel="send" hidden>
                <div class="editor-section-header">
                  <div>
                    <strong>Enviar a</strong>
                    <span>Elegis el canal donde se publicara el panel cuando decidas enviarlo.</span>
                  </div>
                </div>
                <div class="form-grid">
                  <div class="field">
                    <label for="ticketChannel">Canal destino</label>
                    <select id="ticketChannel">
                      <option value="">Seleccionar canal</option>
                    </select>
                  </div>
                  <div class="field">
                    <label for="ticketOpenCategory">Categoria donde se abren</label>
                    <select id="ticketOpenCategory">
                      <option value="">Seleccionar categoria</option>
                    </select>
                  </div>
                  <div class="field">
                    <label for="ticketColor">Color del embed</label>
                    <input id="ticketColor" type="text" placeholder="#22c55e">
                  </div>
                </div>
              </div>

              <div class="editor-section" data-editor-panel="message" hidden>
                <div class="module-header">
                  <p>Mensaje de Discord</p>
                </div>
                <div class="form-grid">
                  <div class="field full">
                    <label for="ticketContent">Texto del mensaje</label>
                    <textarea id="ticketContent" placeholder="Texto opcional arriba del embed."></textarea>
                  </div>
                  <div class="field">
                    <label for="ticketTitle">Titulo del embed</label>
                    <input id="ticketTitle" type="text" placeholder="Postulacion Avalonianas">
                  </div>
                  <div class="field">
                    <label for="ticketFooter">Footer</label>
                    <input id="ticketFooter" type="text" placeholder="AvalonBot Tickets">
                  </div>
                  <div class="field full">
                    <label for="ticketDescription">Descripcion del embed</label>
                    <textarea id="ticketDescription" placeholder="Escribe el mensaje completo que vera la gente en Discord."></textarea>
                  </div>
                  <div class="field full">
                    <label for="ticketImage">Imagen URL</label>
                    <input id="ticketImage" type="text" placeholder="https://...">
                  </div>
                </div>
              </div>

              <div class="editor-section" data-editor-panel="ticketMessage" hidden>
                <div class="editor-section-header">
                  <div>
                    <strong>Mensaje inicial del ticket</strong>
                    <span>Primer embed que el bot envia dentro del canal del ticket.</span>
                  </div>
                </div>
                <div class="form-grid">
                  <div class="field">
                    <label for="ticketOpenTitle">Titulo</label>
                    <input id="ticketOpenTitle" type="text" placeholder="Ticket abierto">
                  </div>
                  <div class="field">
                    <label for="ticketOpenColor">Color</label>
                    <input id="ticketOpenColor" type="text" placeholder="#38bdf8">
                  </div>
                  <div class="field full">
                    <label for="ticketOpenDescription">Descripcion</label>
                    <textarea id="ticketOpenDescription" placeholder="Un miembro del staff te atendera pronto."></textarea>
                  </div>
                </div>
                <div class="preview-box">
                  <strong>Vista ticket</strong>
                  <div id="ticketOpenPreview"></div>
                </div>
              </div>

              <div class="editor-section" data-editor-panel="options" hidden>
                <div class="editor-section-header">
                  <div>
                    <strong>Opciones y emojis</strong>
                    <span>Configura una opcion, varias opciones o una lista desplegable.</span>
                  </div>
                  <button id="addTicketOptionButton" class="action-button" type="button">+ Agregar opcion</button>
                </div>
                <div id="ticketOptions" class="option-list"></div>
              </div>

              <div class="editor-section" data-editor-panel="permissions" hidden>
                <div class="editor-section-header">
                  <div>
                    <strong>Administrar permisos</strong>
                    <span>Define quienes pueden reclamar, cerrar, reabrir o borrar tickets.</span>
                  </div>
                </div>
                <div class="form-grid">
                  <div class="field">
                    <label for="claimRolesButton">Roles que reclaman, maximo 3</label>
                    <input id="claimRoles" type="hidden">
                    <div id="claimRolesPicker" class="role-picker" data-role-picker="claimRoles"></div>
                  </div>
                  <div class="field">
                    <label for="closeRolesButton">Roles que cierran, maximo 3</label>
                    <input id="closeRoles" type="hidden">
                    <div id="closeRolesPicker" class="role-picker" data-role-picker="closeRoles"></div>
                  </div>
                  <div class="field">
                    <label for="reopenRolesButton">Roles que reabren, maximo 3</label>
                    <input id="reopenRoles" type="hidden">
                    <div id="reopenRolesPicker" class="role-picker" data-role-picker="reopenRoles"></div>
                  </div>
                  <div class="field">
                    <label for="deleteRolesButton">Roles que borran, maximo 3</label>
                    <input id="deleteRoles" type="hidden">
                    <div id="deleteRolesPicker" class="role-picker" data-role-picker="deleteRoles"></div>
                  </div>
                </div>
              </div>

              <div class="editor-section" data-editor-panel="preview" hidden>
                <div class="editor-section-header">
                  <div>
                    <strong>Vista previa y envio</strong>
                    <span>Guardar solo almacena cambios; enviar publica el panel en Discord.</span>
                  </div>
                </div>
                <div class="preview-box">
                  <strong>Vista previa del panel</strong>
                  <div id="ticketPreview"></div>
                </div>
                <div class="publish-row">
                  <button id="savePanelButton" class="action-button primary" type="button">Guardar configuracion</button>
                  <button id="publishPanelButton" class="action-button warning" type="button">Enviar a canal</button>
                  <div id="ticketStatus" class="status"></div>
                </div>
              </div>

            </div>
          </section>
        </div>
        <div id="ticketTranscriptViewer" class="ticket-transcript-page" hidden>
          <div class="ticket-toolbar">
            <div>
              <h2 id="ticketTranscriptTitle">Transcripcion</h2>
              <p id="ticketTranscriptSubtitle">Historial completo del ticket.</p>
            </div>
            <div class="ticket-actions">
              <button id="backToTicketsButton" class="action-button" type="button">Volver a tickets</button>
            </div>
          </div>
          <div id="ticketTranscriptContent" class="transcript-box"></div>
        </div>
      </section>
      <section id="welcomeSection" class="module-panel" aria-label="Bienvenidas" hidden></section>
      <section id="auditSection" class="module-panel" aria-label="Auditoria" hidden>
        <div class="audit-dashboard">
          <div class="ticket-toolbar">
            <div>
              <h2>Auditoria</h2>
              <p>Configura un canal distinto para cada tipo de registro del servidor.</p>
            </div>
            <div class="ticket-actions">
              <button id="saveAuditConfigButton" class="action-button primary" type="button">Guardar auditoria</button>
            </div>
          </div>

          <section class="ticket-summary" aria-label="Resumen de auditoria">
            <div class="ticket-stat"><span>Categorias</span><strong id="auditCategoryTotal">0</strong></div>
            <div class="ticket-stat"><span>Configuradas</span><strong id="auditConfiguredTotal">0</strong></div>
            <div class="ticket-stat"><span>Sin canal</span><strong id="auditMissingTotal">0</strong></div>
          </section>

          <section id="auditConfigGrid" class="audit-grid" aria-label="Canales de auditoria"></section>
          <div class="editor-section">
            <div class="editor-section-header">
              <div>
                <strong>Eventos recientes</strong>
                <span>Se guardan en el dashboard aunque no haya canal de Discord configurado.</span>
              </div>
            </div>
            <div id="auditEventsList" class="audit-event-sections"></div>
          </div>
          <div id="auditStatus" class="status"></div>
        </div>
      </section>
      <section id="permissionsSection" class="module-panel" aria-label="Permisos" hidden>
        <div class="module-header">
          <div>
            <h2>Permisos</h2>
            <p>Configura que roles pueden usar cada parte del bot. Los comandos de Discord siguen funcionando y usan esta misma configuracion.</p>
          </div>
          <div class="ticket-actions">
            <button id="refreshPermissionsButton" class="action-button" type="button">Recargar</button>
            <button id="savePermissionsButton" class="action-button primary" type="button">Guardar permisos</button>
          </div>
        </div>
        <section class="ticket-summary" aria-label="Resumen de permisos">
          <div class="ticket-stat"><span>Roles con permisos</span><strong id="permissionRoleTotal">0</strong></div>
          <div class="ticket-stat"><span>Permisos activos</span><strong id="permissionActiveTotal">0</strong></div>
          <div class="ticket-stat"><span>Roles disponibles</span><strong id="permissionAvailableTotal">0</strong></div>
        </section>
        <div class="editor-section">
          <div class="editor-section-header">
            <div>
              <strong>Permisos por rol</strong>
              <span>Activa permisos especificos o marca Global para darle acceso completo a ese rol.</span>
            </div>
          </div>
          <div class="records-toolbar compact">
            <input id="permissionRoleSearch" type="search" placeholder="Buscar rol por nombre o ID">
          </div>
          <div id="permissionsGrid" class="permissions-grid"></div>
        </div>
        <div id="permissionsStatus" class="status"></div>
      </section>
    </div>
  </main>

  <script>
    const state = {
      data: null,
      section: localStorage.getItem("dashboardSection") || "economy",
      sidebarCollapsed: localStorage.getItem("dashboardSidebarCollapsed") === "1",
      theme: localStorage.getItem("dashboardTheme") || "light",
      tab: "balances",
      guildId: localStorage.getItem("dashboardGuildId") || "",
      search: "",
      pingTemplates: [],
      pingTemplateDrafts: {},
      pingTemplateSavedCount: 0,
      pingTemplateMax: 5,
      currentPingTemplateKey: localStorage.getItem("dashboardPingTemplateKey") || "",
      ticketPanels: [],
      ticketChannels: [],
      ticketCategories: [],
      ticketEmojis: [],
      ticketRoles: [],
      ticketRecords: [],
      ticketRecordSearch: "",
      selectedTicketRecordId: "",
      ticketTranscriptOpen: false,
      templateStatusMessage: "",
      auditCategories: [],
      auditConfig: { channels: {} },
      auditEvents: [],
      botPermissions: {},
      botPermissionOptions: [],
      csrfToken: "",
      permissionSearch: "",
      currentTicketPanelId: localStorage.getItem("dashboardTicketPanelId") || "",
      ticketEditorSection: localStorage.getItem("dashboardTicketEditorSection") || "identity",
      openRolePicker: "",
      rolePickerSearch: {},
      ticketConfigGuildId: "",
      ticketPanelsDirty: false,
      userInteracting: false
    };

    applyTheme();

    const columns = {
      balances: [
        ["rank", "#", "number"],
        ["user_name", "Usuario"],
        ["user_id", "ID"],
        ["items", "Items", "number"],
        ["silver", "Silver", "number"],
        ["total", "Total", "number"],
        ["updated_at_display", "Fecha"]
      ],
      operations: [
        ["action", "Accion"],
        ["operator", "Operador"],
        ["player", "Jugador"],
        ["type", "Tipo"],
        ["category", "Categoria"],
        ["amount", "Cantidad", "number"],
        ["previous_balance", "Anterior", "number"],
        ["new_balance", "Nuevo", "number"],
        ["date", "Fecha"],
        ["time", "Hora"]
      ],
      avalonians: [
        ["ava", "Ava"],
        ["action", "Accion"],
        ["user", "Usuario"],
        ["user_id", "ID"],
        ["slot", "Cupo"],
        ["reason", "Justificacion"],
        ["date", "Fecha"],
        ["time", "Hora"]
      ],
      reports: [
        ["ava", "Ava"],
        ["caller", "Caller"],
        ["caller_id", "ID Caller"],
        ["reviewer", "Revisado por"],
        ["decision", "Decision"],
        ["reason", "Motivo"],
        ["date", "Fecha"],
        ["time", "Hora"]
      ]
    };

    const numberFields = new Set(["items", "silver", "total", "amount", "previous_balance", "new_balance"]);
    const defaultTicketEmojis = [
      ["", "Sin emoji"],
      ["🎫", "🎫"],
      ["📩", "📩"],
      ["🛡️", "🛡️"],
      ["⚔️", "⚔️"],
      ["💰", "💰"],
      ["❓", "❓"],
      ["✅", "✅"]
    ];

    const globalTicketEmojis = [
      ["", "Sin emoji"],
      ["\uD83C\uDFAB", "\uD83C\uDFAB"],
      ["\uD83D\uDCE9", "\uD83D\uDCE9"],
      ["\uD83D\uDCE8", "\uD83D\uDCE8"],
      ["\u2705", "\u2705"],
      ["\u2753", "\u2753"],
      ["\uD83D\uDEE1\uFE0F", "\uD83D\uDEE1\uFE0F"],
      ["\u2694\uFE0F", "\u2694\uFE0F"],
      ["\uD83D\uDCB0", "\uD83D\uDCB0"],
      ["\uD83D\uDCCC", "\uD83D\uDCCC"],
      ["\uD83D\uDCDD", "\uD83D\uDCDD"],
      ["\uD83D\uDD27", "\uD83D\uDD27"],
      ["\u2B50", "\u2B50"],
      ["\uD83D\uDD25", "\uD83D\uDD25"],
      ["\uD83D\uDC8E", "\uD83D\uDC8E"],
      ["\uD83D\uDCCB", "\uD83D\uDCCB"],
      ["\uD83C\uDFAE", "\uD83C\uDFAE"],
      ["\uD83D\uDC51", "\uD83D\uDC51"],
      ["\uD83D\uDEA8", "\uD83D\uDEA8"],
      ["\uD83D\uDCAC", "\uD83D\uDCAC"],
      ["\uD83D\uDD12", "\uD83D\uDD12"]
    ];

    function newTicketPanel(name = "Nuevo panel") {
      const id = crypto.randomUUID ? crypto.randomUUID() : String(Date.now());
      return {
        id,
        name,
        mode: "buttons",
        channel_id: "",
        open_category_id: "",
        message_content: "",
        embed_title: name,
        embed_description: "Selecciona una opcion para abrir un ticket.",
        embed_color: "#22c55e",
        embed_footer: "AvalonBot Tickets",
        image_url: "",
        ticket_open_title: "Ticket abierto",
        ticket_open_description: "Un miembro del staff te atendera pronto.",
        ticket_open_color: "#38bdf8",
        options: [
          {
            id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-option`,
            label: "Abrir ticket",
            emoji: "",
            description: "Crear un ticket privado"
          }
        ],
        permissions: {
          claim_roles: "",
          close_roles: "",
          reopen_roles: "",
          delete_roles: ""
        }
      };
    }

    function formatNumber(value) {
      const number = Number(value || 0);
      return Number.isFinite(number) ? number.toLocaleString("es-AR") : value;
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function badge(value, field) {
      const text = String(value ?? "");
      const lowered = text.toLowerCase();
      let cls = "";
      if (field === "type" || field === "action") {
        if (lowered.includes("add") || lowered.includes("signup")) cls = "add";
        if (lowered.includes("remove") || lowered.includes("leave")) cls = "remove";
      }
      if (field === "category") {
        if (lowered.includes("silver")) cls = "silver";
        if (lowered.includes("items")) cls = "items";
      }
      if (field === "decision") {
        if (lowered.includes("acept")) cls = "accepted";
        if (lowered.includes("rechaz")) cls = "rejected";
      }
      return cls ? `<span class="pill ${cls}">${escapeHtml(text)}</span>` : escapeHtml(text);
    }

    function activeRows() {
      if (!state.data) return [];
      const rows = state.data[state.tab] || [];
      const query = state.search.trim().toLowerCase();
      if (!query) return rows;
      return rows.filter(row => JSON.stringify(row).toLowerCase().includes(query));
    }

    function renderGuilds() {
      const select = document.getElementById("guildSelect");
      const guilds = state.data?.guilds || [];
      if (!guilds.length) {
        select.innerHTML = `<option value="">Sin servidores disponibles</option>`;
        select.disabled = true;
        return;
      }

      select.disabled = false;
      select.innerHTML = guilds.map(guild => {
        const selected = guild.id === state.data.selectedGuildId ? " selected" : "";
        return `<option value="${escapeHtml(guild.id)}"${selected}>${escapeHtml(guild.name)}</option>`;
      }).join("");
    }

    function renderMetrics() {
      const totals = state.data?.totals || {};
      document.getElementById("playersTotal").textContent = formatNumber(totals.players);
      document.getElementById("itemsTotal").textContent = formatNumber(totals.items);
      document.getElementById("silverTotal").textContent = formatNumber(totals.silver);
      document.getElementById("overallTotal").textContent = formatNumber(totals.total);
    }

    function renderTable() {
      const head = document.getElementById("tableHead");
      const body = document.getElementById("tableBody");
      const empty = document.getElementById("emptyState");
      const selectedColumns = columns[state.tab];
      const rows = activeRows();

      head.innerHTML = `<tr>${selectedColumns.map(([, label, cls]) => `<th class="${cls || ""}">${label}</th>`).join("")}</tr>`;
      body.innerHTML = rows.map(row => {
        const cells = selectedColumns.map(([field, , cls]) => {
          const raw = row[field] ?? "";
          const value = numberFields.has(field) ? formatNumber(raw) : badge(raw, field);
          return `<td class="${cls || ""}">${value}</td>`;
        });
        return `<tr>${cells.join("")}</tr>`;
      }).join("");
      empty.hidden = rows.length > 0;
    }

    function render() {
      renderTheme();
      renderGuilds();
      renderMetrics();
      renderTable();
      renderSections();
      renderTemplates();
      renderTickets();
      renderAudit();
      renderPermissions();
      document.querySelectorAll(".tab").forEach(button => {
        button.classList.toggle("active", button.dataset.tab === state.tab);
      });
      const status = document.getElementById("status");
      status.textContent = state.data ? `Refrescado ${state.data.updatedAt}` : "Sin datos";
      renderSession();
    }

    function currentTicketPanel() {
      return state.ticketPanels.find(panel => panel.id === state.currentTicketPanelId) || null;
    }

    function currentPingTemplate() {
      return state.pingTemplates.find(template => template.key === state.currentPingTemplateKey) || null;
    }

    function newPingTemplate() {
      return {
        key: "",
        name: "",
        title: "Ava {numero}",
        title_editable: true,
        mention: "",
        join_command: "/join {caller}",
        caller_slot: "MainTank",
        roles: ["MainTank", "Heal", "DPS"],
        slot_format: "> **{index}.{slot}:** {user}",
        content: "# {title} {mention}\\n\\n{join_command}\\n\\n{slots}\\n\\nCupos: {occupied}/{total}{status}",
        loot_link: "",
        report_enabled: true,
        source: "server",
        editable: true,
        deletable: false
      };
    }

    function renderTemplates() {
      document.getElementById("templateSavedTotal").textContent = state.pingTemplateSavedCount;
      document.getElementById("templateLimitTotal").textContent = state.pingTemplateMax;
      document.getElementById("templateAvailableTotal").textContent = state.pingTemplates.length;
      renderTemplateList();
      renderTemplateEditor();
    }

    function renderTemplateList() {
      const list = document.getElementById("templateList");
      if (!state.pingTemplates.length) {
        list.innerHTML = `<button type="button" disabled>No hay plantillas cargadas</button>`;
        return;
      }

      list.innerHTML = state.pingTemplates.map(template => {
        const active = template.key === state.currentPingTemplateKey ? " active" : "";
        const source = template.source === "server"
          ? (template.overrides_global ? "Servidor, reemplaza base" : "Servidor")
          : template.source === "global" ? "Base" : "Temporal";
        return `<button class="template-select${active}" type="button" data-template-key="${escapeHtml(template.key)}">${escapeHtml(template.name || template.key)}<br><span class="muted">${escapeHtml(template.key)} - ${source}</span></button>`;
      }).join("");

      list.querySelectorAll(".template-select").forEach(button => {
        button.addEventListener("click", () => {
          state.currentPingTemplateKey = button.dataset.templateKey;
          localStorage.setItem("dashboardPingTemplateKey", state.currentPingTemplateKey);
          renderTemplates();
        });
      });
    }

    function templateFormData() {
      return {
        key: document.getElementById("templateKey").value.trim(),
        original_key: document.getElementById("templateOriginalKey").value.trim(),
        name: document.getElementById("templateName").value.trim(),
        title: document.getElementById("templateTitle").value,
        mention: document.getElementById("templateMention").value,
        join_command: document.getElementById("templateJoinCommand").value,
        caller_slot: document.getElementById("templateCallerSlot").value,
        roles: document.getElementById("templateRoles").value.replace(/\\n/g, "\n"),
        slot_format: document.getElementById("templateSlotFormat").value,
        content: document.getElementById("templateContent").value.replace(/\\n/g, "\n"),
        loot_link: document.getElementById("templateLootLink").value,
        report_enabled: document.getElementById("templateReportEnabled").checked,
        title_editable: true
      };
    }

    function normalizeTemplateText(value) {
      return String(value || "").replace(/\\n/g, "\n");
    }

    function saveTemplateDraft() {
      const originalKey = document.getElementById("templateOriginalKey").value.trim() || state.currentPingTemplateKey;
      if (!originalKey) return;
      state.pingTemplateDrafts[originalKey] = templateFormData();
    }

    function renderTemplateEditor() {
      const template = currentPingTemplate() || newPingTemplate();
      const draft = state.pingTemplateDrafts[state.currentPingTemplateKey];
      const formTemplate = draft ? { ...template, ...draft } : template;
      const editable = true;
      const isBase = template.source === "global" || template.source === "scratch";
      document.getElementById("templateKey").value = formTemplate.key || "";
      document.getElementById("templateOriginalKey").value = draft?.original_key || template.key || "";
      document.getElementById("templateName").value = formTemplate.name || "";
      document.getElementById("templateTitle").value = formTemplate.title || "";
      document.getElementById("templateMention").value = formTemplate.mention || "";
      document.getElementById("templateJoinCommand").value = formTemplate.join_command || "";
      document.getElementById("templateCallerSlot").value = formTemplate.caller_slot || "";
      document.getElementById("templateRoles").value = Array.isArray(formTemplate.roles) ? formTemplate.roles.join("\n") : normalizeTemplateText(formTemplate.roles);
      document.getElementById("templateSlotFormat").value = formTemplate.slot_format || "";
      document.getElementById("templateContent").value = normalizeTemplateText(formTemplate.content);
      document.getElementById("templateLootLink").value = formTemplate.loot_link || "";
      document.getElementById("templateReportEnabled").checked = formTemplate.report_enabled !== false;

      ["templateKey", "templateName", "templateTitle", "templateMention", "templateJoinCommand", "templateCallerSlot", "templateRoles", "templateSlotFormat", "templateContent", "templateLootLink", "templateReportEnabled"].forEach(id => {
        document.getElementById(id).disabled = !editable;
      });
      document.getElementById("saveTemplateButton").disabled = !editable;
      document.getElementById("deleteTemplateButton").disabled = !template.deletable;
      renderTemplatePreview();
      if (state.templateStatusMessage) {
        document.getElementById("templateStatus").textContent = state.templateStatusMessage;
        state.templateStatusMessage = "";
      } else if (isBase) {
        document.getElementById("templateStatus").textContent = "Estas viendo una plantilla base. Si guardas con esta clave, se crea una version del servidor que reemplaza a la base solo en este servidor.";
      } else {
        document.getElementById("templateStatus").textContent = template.overrides_global
          ? "Plantilla del servidor que reemplaza a una base. Puedes modificarla y guardar los cambios."
          : "Plantilla del servidor. Puedes modificarla y guardar los cambios.";
      }
    }

    function renderTemplatePreview() {
      const data = templateFormData();
      const roles = String(data.roles || "").split(/\\n|,|;/).map(item => item.trim()).filter(Boolean);
      const slots = roles.map((role, index) => `> **${index + 1}.${role}:** ${index === 0 ? "Caller" : "-"}`).join("\\n");
      const values = {
        title: data.title || "Ava 29",
        numero: "29",
        template: data.name || data.key || "Plantilla",
        mention: data.mention || "",
        caller: "Neox",
        join_command: data.join_command || "/join Neox",
        slots,
        loot_link: data.loot_link || "",
        occupied: "1",
        total: String(Math.max(roles.length, 1)),
        status: ""
      };
      const rendered = String(data.content || "").replace(/\\{([a-z_]+)\\}/gi, (match, key) => values[key] ?? match);
      document.getElementById("templatePreview").innerHTML = `
        <div class="discord-preview-title">${escapeHtml(data.name || data.key || "Nueva plantilla")}</div>
        <div class="discord-preview-description">${escapeHtml(rendered || "Completa el mensaje para ver la vista previa.")}</div>
      `;
    }

    function renderTickets() {
      document.getElementById("appShell").classList.toggle("transcript-open", state.section === "tickets" && state.ticketTranscriptOpen);
      document.body.classList.toggle("transcript-open", state.section === "tickets" && state.ticketTranscriptOpen);
      document.getElementById("ticketDashboardMain").hidden = state.ticketTranscriptOpen;
      document.getElementById("ticketTranscriptViewer").hidden = !state.ticketTranscriptOpen;
      document.getElementById("ticketPanelTotal").textContent = state.ticketPanels.length;
      const hasPanel = Boolean(currentTicketPanel());
      document.getElementById("clonePanelButton").hidden = !hasPanel;
      document.getElementById("deletePanelButton").hidden = !hasPanel;
      renderTicketPanelList();
      renderTicketChannels();
      renderTicketCategories();
      renderTicketEditor();
      renderTicketEditorSections();
      renderTicketRecords();
      renderTicketTranscript();
    }

    function renderTicketEditorSections() {
      document.querySelectorAll(".editor-tab").forEach(button => {
        button.classList.toggle("active", button.dataset.editorSection === state.ticketEditorSection);
      });
      document.querySelectorAll("[data-editor-panel]").forEach(panel => {
        panel.hidden = panel.dataset.editorPanel !== state.ticketEditorSection;
      });
    }

    function renderAudit() {
      const categories = state.auditCategories || [];
      const channels = state.auditConfig?.channels || {};
      const configured = categories.filter(category => channels[category.key]).length;
      document.getElementById("auditCategoryTotal").textContent = categories.length;
      document.getElementById("auditConfiguredTotal").textContent = configured;
      document.getElementById("auditMissingTotal").textContent = Math.max(categories.length - configured, 0);

      const grid = document.getElementById("auditConfigGrid");
      if (!categories.length) {
        grid.innerHTML = `<div class="ticket-empty-editor"><strong>Sin categorias cargadas</strong><p>Inicia sesion y selecciona un servidor.</p></div>`;
        return;
      }

      grid.innerHTML = categories.map(category => `
        <article class="audit-card">
          <div>
            <strong>${escapeHtml(category.name)}</strong>
            <p>${escapeHtml(category.description)}</p>
          </div>
          <select class="audit-channel-select" data-audit-key="${escapeHtml(category.key)}">
            <option value="">Sin canal</option>
            ${state.ticketChannels.map(channel => {
              const selected = channels[category.key] === channel.id ? " selected" : "";
              return `<option value="${escapeHtml(channel.id)}"${selected}>#${escapeHtml(channel.name)}</option>`;
            }).join("")}
          </select>
        </article>
      `).join("");

      grid.querySelectorAll(".audit-channel-select").forEach(select => {
        select.addEventListener("change", () => {
          state.auditConfig.channels[select.dataset.auditKey] = select.value;
          renderAudit();
        });
      });

      const eventsList = document.getElementById("auditEventsList");
      const events = state.auditEvents || [];
      const categoryNames = Object.fromEntries(categories.map(category => [category.key, category.name]));
      const grouped = {};
      for (const event of events) {
        const key = event.category || "otros";
        grouped[key] = grouped[key] || [];
        grouped[key].push(event);
      }

      const orderedGroups = categories.map(category => ({
        key: category.key,
        name: category.name,
        events: grouped[category.key] || []
      }));
      for (const [category, categoryEvents] of Object.entries(grouped)) {
        if (!categoryNames[category]) {
          orderedGroups.push({ key: category, name: category, events: categoryEvents });
        }
      }

      eventsList.innerHTML = orderedGroups.map((group, index) => `
        <details class="audit-event-section"${index === 0 ? " open" : ""}>
          <summary>
            <span>${escapeHtml(group.name)}</span>
            <span class="muted">${group.events.length} eventos</span>
          </summary>
          <div class="audit-event-list">
            ${group.events.length ? group.events.slice(0, 8).map(event => `
              <article class="ticket-card">
                <div>
                  <h3>${escapeHtml(event.title || "Evento")}</h3>
                  <div class="ticket-meta">
                    <span>${escapeHtml(event.created_at || "")}</span>
                  </div>
                  <div class="muted">${escapeHtml(event.description || "")}</div>
                </div>
              </article>
            `).join("") : `
              <article class="ticket-card">
                <div>
                  <h3>Sin eventos recientes</h3>
                  <div class="ticket-meta"><span>Cuando ocurra algo de esta categoria, aparecera aca.</span></div>
                </div>
              </article>
            `}
          </div>
        </details>
      `).join("");
    }

    function permissionValuesForRole(roleId) {
      const values = state.botPermissions?.[String(roleId)] || [];
      return Array.isArray(values) ? values.map(String) : [];
    }

    function renderPermissions() {
      const grid = document.getElementById("permissionsGrid");
      const roles = state.ticketRoles || [];
      const options = state.botPermissionOptions || [];
      const search = String(state.permissionSearch || "").trim().toLowerCase();
      const visibleRoles = search
        ? roles.filter(role => String(role.name || "").toLowerCase().includes(search) || String(role.id || "").includes(search))
        : roles;
      const configuredRoles = Object.values(state.botPermissions || {}).filter(values => Array.isArray(values) && values.length).length;
      const activeTotal = Object.values(state.botPermissions || {}).reduce((total, values) => total + (Array.isArray(values) ? values.length : 0), 0);

      document.getElementById("permissionRoleTotal").textContent = configuredRoles;
      document.getElementById("permissionActiveTotal").textContent = activeTotal;
      document.getElementById("permissionAvailableTotal").textContent = roles.length;
      document.getElementById("permissionRoleSearch").value = state.permissionSearch;

      if (!roles.length || !options.length) {
        grid.innerHTML = `<div class="ticket-empty-editor"><strong>Sin roles cargados</strong><p>Selecciona un servidor para cargar los roles disponibles.</p></div>`;
        return;
      }

      if (!visibleRoles.length) {
        grid.innerHTML = `<div class="ticket-empty-editor"><strong>No encontre roles</strong><p>Prueba con otro nombre o ID.</p></div>`;
        return;
      }

      grid.innerHTML = `
        <div class="permissions-list">
          <div class="permissions-list-head">
            <span>Rol</span>
            ${options.map(option => `<span title="${escapeHtml(option.description)}">${escapeHtml(option.label)}</span>`).join("")}
          </div>
          ${visibleRoles.map(role => {
        const values = permissionValuesForRole(role.id);
        const hasGlobal = values.includes("global");
        return `
            <article class="permission-row" data-role-id="${escapeHtml(role.id)}">
              <div class="permission-role">
                <strong>@${escapeHtml(role.name)}</strong>
                <span class="muted">${escapeHtml(role.id)}</span>
              </div>
              ${options.map(option => {
                const checked = values.includes(option.key) ? " checked" : "";
                const disabled = hasGlobal && option.key !== "global" ? " disabled" : "";
                const active = checked ? " active" : "";
                const globalClass = option.key === "global" ? " global" : "";
                return `
                  <label class="permission-pill${active}${globalClass}" title="${escapeHtml(option.description)}">
                    <input type="checkbox" data-permission-role="${escapeHtml(role.id)}" data-permission-key="${escapeHtml(option.key)}"${checked}${disabled}>
                    <span>${escapeHtml(option.label)}</span>
                  </label>
                `;
              }).join("")}
            </article>
        `;
          }).join("")}
        </div>
      `;
    }

    function collectBotPermissions() {
      const permissions = { ...(state.botPermissions || {}) };
      document.querySelectorAll(".permission-row").forEach(row => {
        const roleId = String(row.dataset.roleId || "");
        if (roleId) delete permissions[roleId];
      });
      document.querySelectorAll("[data-permission-role]").forEach(input => {
        if (!input.checked) return;
        const roleId = String(input.dataset.permissionRole || "");
        const key = String(input.dataset.permissionKey || "");
        if (!roleId || !key) return;
        permissions[roleId] = permissions[roleId] || [];
        permissions[roleId].push(key);
      });

      for (const [roleId, values] of Object.entries(permissions)) {
        if (values.includes("global")) {
          permissions[roleId] = ["global"];
        }
      }

      return permissions;
    }

    function renderTicketPanelList() {
      const list = document.getElementById("ticketPanelList");
      if (!state.ticketPanels.length) {
        list.innerHTML = `<button type="button" disabled>No hay paneles creados</button>`;
        return;
      }

      list.innerHTML = state.ticketPanels.map(panel => {
        const active = panel.id === state.currentTicketPanelId ? " active" : "";
        return `<button class="ticket-panel-select${active}" type="button" data-panel-id="${escapeHtml(panel.id)}">${escapeHtml(panel.name)}</button>`;
      }).join("");

      list.querySelectorAll(".ticket-panel-select").forEach(button => {
        button.addEventListener("click", () => {
          persistCurrentTicketPanel();
          state.currentTicketPanelId = button.dataset.panelId;
          localStorage.setItem("dashboardTicketPanelId", state.currentTicketPanelId);
          renderTickets();
        });
      });
    }

    function renderTicketChannels() {
      const select = document.getElementById("ticketChannel");
      const panel = currentTicketPanel();
      select.innerHTML = `<option value="">Seleccionar canal</option>` + state.ticketChannels.map(channel => {
        const selected = panel?.channel_id === channel.id ? " selected" : "";
        return `<option value="${escapeHtml(channel.id)}"${selected}>#${escapeHtml(channel.name)}</option>`;
      }).join("");
    }

    function renderTicketCategories() {
      const select = document.getElementById("ticketOpenCategory");
      const panel = currentTicketPanel();
      select.innerHTML = `<option value="">Seleccionar categoria</option>` + state.ticketCategories.map(category => {
        const selected = panel?.open_category_id === category.id ? " selected" : "";
        return `<option value="${escapeHtml(category.id)}"${selected}>${escapeHtml(category.name)}</option>`;
      }).join("");
    }

    function renderTicketRecords() {
      const list = document.getElementById("ticketRecordsList");
      const query = state.ticketRecordSearch.trim().toLowerCase();
      const records = (state.ticketRecords || []).filter(record => {
        if (!query) return true;
        return JSON.stringify(record).toLowerCase().includes(query);
      });
      if (!records.length) {
        list.innerHTML = `
          <article class="ticket-card">
            <div>
              <h3>No hay tickets para mostrar</h3>
              <div class="ticket-meta"><span>Los tickets abiertos y transcritos apareceran aca.</span></div>
            </div>
          </article>`;
        state.selectedTicketRecordId = "";
        state.ticketTranscriptOpen = false;
        return;
      }

      list.innerHTML = records.map(record => `
        <article class="ticket-card">
          <div>
            <h3>${escapeHtml(record.channel_name || `ticket-${record.number || ""}`)}</h3>
            <div class="ticket-meta">
              <span class="ticket-status">${escapeHtml(record.status || "abierto")}</span>
              <span>Usuario: ${escapeHtml(record.owner_name || record.owner_id || "Desconocido")}</span>
              <span>Panel: ${escapeHtml(record.panel_name || "Sin panel")}</span>
              ${record.claimed_by_name ? `<span>Reclamado por: ${escapeHtml(record.claimed_by_name)}</span>` : ""}
              ${record.transcribed_at ? `<span>Transcrito: ${escapeHtml(record.transcribed_at)}</span>` : ""}
            </div>
          </div>
          <div class="ticket-card-actions">
            <button class="action-button view-transcript-button${String(state.selectedTicketRecordId) === String(record.channel_id || record.number || "") ? " active" : ""}" type="button" data-record-id="${escapeHtml(record.channel_id || record.number || "")}" title="Ver transcripcion" aria-label="Ver transcripcion">Ver transcripcion</button>
          </div>
        </article>
      `).join("");

      list.querySelectorAll(".view-transcript-button").forEach(button => {
        button.addEventListener("click", () => {
          openTicketTranscript(button.dataset.recordId);
        });
      });
    }

    function openTicketTranscript(recordId) {
      const params = new URLSearchParams({
        guild_id: state.guildId,
        record_id: recordId
      });
      window.location.href = `/ticket-transcript?${params.toString()}`;
    }

    function closeTicketTranscript() {
      state.ticketTranscriptOpen = false;
      document.getElementById("appShell").classList.remove("transcript-open");
      document.body.classList.remove("transcript-open");
      document.getElementById("ticketTranscriptViewer").hidden = true;
      document.getElementById("ticketDashboardMain").hidden = false;
      renderTicketRecords();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function initialForName(name) {
      const clean = String(name || "U").trim();
      return escapeHtml(clean.slice(0, 1).toUpperCase() || "U");
    }

    function renderTranscriptAvatar(message) {
      const avatar = message.author_avatar || "";
      if (avatar) {
        return `<span class="transcript-avatar"><img src="${escapeHtml(avatar)}" alt=""></span>`;
      }
      return `<span class="transcript-avatar">${initialForName(message.author_name || message.author)}</span>`;
    }

    function renderTranscriptEmbeds(embeds) {
      if (!Array.isArray(embeds) || !embeds.length) return "";
      return embeds.map(embed => {
        const color = embed.color ? `#${Number(embed.color).toString(16).padStart(6, "0").slice(-6)}` : "#5865f2";
        const fields = Array.isArray(embed.fields) ? embed.fields : [];
        const imageUrl = embed.image?.local_url || embed.image?.url || "";
        const thumbnailUrl = embed.thumbnail?.local_url || embed.thumbnail?.url || "";
        return `
          <div class="transcript-embed" style="border-left-color:${escapeHtml(color)}">
            ${embed.author?.name ? `<div class="muted">${escapeHtml(embed.author.name)}</div>` : ""}
            ${embed.title ? `<div class="transcript-embed-title">${escapeHtml(embed.title)}</div>` : ""}
            ${embed.description ? `<div class="transcript-content">${escapeHtml(embed.description)}</div>` : ""}
            ${fields.map(field => `
              <div class="transcript-embed-field">
                <strong>${escapeHtml(field.name || "")}</strong>
                <span>${escapeHtml(field.value || "")}</span>
              </div>
            `).join("")}
            ${thumbnailUrl ? `<img class="transcript-image" src="${escapeHtml(thumbnailUrl)}" alt="Miniatura del embed">` : ""}
            ${imageUrl ? `<img class="transcript-image" src="${escapeHtml(imageUrl)}" alt="Imagen del embed">` : ""}
            ${embed.footer?.text ? `<div class="muted">${escapeHtml(embed.footer.text)}</div>` : ""}
          </div>
        `;
      }).join("");
    }

    function renderTranscriptAttachments(attachments) {
      if (!Array.isArray(attachments) || !attachments.length) return "";
      return `
        <div class="transcript-attachments">
          ${attachments.map(attachment => {
            const url = attachment.local_url || attachment.url || "#";
            const filename = attachment.filename || "Archivo adjunto";
            const contentType = attachment.content_type || "";
            const looksImage = contentType.startsWith("image/") || /\.(png|jpe?g|gif|webp|bmp)$/i.test(filename);
            return looksImage
              ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer"><img class="transcript-image" src="${escapeHtml(url)}" alt="${escapeHtml(filename)}"></a>`
              : `<a class="transcript-attachment" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(filename)}</a>`;
          }).join("")}
        </div>
      `;
    }

    function renderTranscriptMessage(message) {
      const authorName = message.author_name || message.author || "Usuario";
      const hasContent = Boolean(message.content);
      const hasEmbeds = Array.isArray(message.embeds) && message.embeds.length;
      const hasAttachments = Array.isArray(message.attachments) && message.attachments.length;
      return `
        <div class="transcript-message">
          ${renderTranscriptAvatar(message)}
          <div class="transcript-body">
            <div class="transcript-author-line">
              <span class="transcript-author">${escapeHtml(authorName)}</span>
              ${message.author_bot ? `<span class="transcript-bot-badge">Bot</span>` : ""}
              <span class="muted">${escapeHtml(message.created_at || "")}</span>
            </div>
            ${hasContent ? `<div class="transcript-content">${escapeHtml(message.content)}</div>` : ""}
            ${renderTranscriptEmbeds(message.embeds)}
            ${renderTranscriptAttachments(message.attachments)}
            ${!hasContent && !hasEmbeds && !hasAttachments ? `<div class="muted">(mensaje sin contenido visible)</div>` : ""}
          </div>
        </div>
      `;
    }

    function renderTicketTranscript() {
      const viewer = document.getElementById("ticketTranscriptViewer");
      const content = document.getElementById("ticketTranscriptContent");
      const title = document.getElementById("ticketTranscriptTitle");
      const subtitle = document.getElementById("ticketTranscriptSubtitle");
      const record = (state.ticketRecords || []).find(item => String(item.channel_id || item.number || "") === String(state.selectedTicketRecordId));
      if (!state.ticketTranscriptOpen) {
        viewer.hidden = true;
        content.innerHTML = "";
        return;
      }

      if (!record) {
        state.ticketTranscriptOpen = false;
        document.getElementById("ticketDashboardMain").hidden = false;
        viewer.hidden = true;
        content.innerHTML = "";
        return;
      }

      viewer.hidden = false;
      document.getElementById("ticketDashboardMain").hidden = true;
      const transcript = Array.isArray(record.transcript) ? record.transcript : [];
      title.textContent = record.channel_name || `ticket-${record.number || ""}`;
      subtitle.textContent = `${record.panel_name || "Sin panel"} - ${record.owner_name || record.owner_id || "Usuario desconocido"}`;
      const summary = `
        <div class="transcript-summary">
          <strong>${escapeHtml(record.channel_name || `ticket-${record.number || ""}`)}</strong>
          <span>Usuario: ${escapeHtml(record.owner_name || record.owner_id || "Desconocido")}</span>
          <span>Panel: ${escapeHtml(record.panel_name || "Sin panel")}</span>
          <span>Estado: ${escapeHtml(record.status || "abierto")}</span>
          ${record.created_at ? `<span>Creado: ${escapeHtml(record.created_at)}</span>` : ""}
          ${record.closed_at ? `<span>Cerrado: ${escapeHtml(record.closed_at)}</span>` : ""}
          ${record.deleted_at ? `<span>Eliminado: ${escapeHtml(record.deleted_at)}</span>` : ""}
          ${record.transcribed_at ? `<span>Transcrito: ${escapeHtml(record.transcribed_at)}</span>` : ""}
        </div>
      `;
      if (!transcript.length) {
        content.innerHTML = `${summary}<div class="muted">Este ticket todavia no tiene transcripcion guardada.</div>`;
        return;
      }

      content.innerHTML = summary + transcript.map(renderTranscriptMessage).join("");
    }

    function permissionValues(value) {
      if (Array.isArray(value)) return value.map(String);
      return String(value || "").split(",").map(item => item.trim()).filter(Boolean);
    }

    function rolePickerValues(inputId) {
      return permissionValues(document.getElementById(inputId)?.value || "");
    }

    function roleById(roleId) {
      return state.ticketRoles.find(role => String(role.id) === String(roleId));
    }

    function setRolePickerValues(inputId, values) {
      document.getElementById(inputId).value = values.map(String).slice(0, 3).join(",");
    }

    function renderRoleSelect(inputId, selectedValues) {
      const values = permissionValues(selectedValues).slice(0, 3);
      const selected = new Set(values);
      const input = document.getElementById(inputId);
      const picker = document.getElementById(`${inputId}Picker`);
      if (!input || !picker) return;

      input.value = values.join(",");
      const search = String(state.rolePickerSearch[inputId] || "").toLowerCase();
      const selectedRoles = values.map(roleById).filter(Boolean);
      const visibleRoles = state.ticketRoles.filter(role => String(role.name || "").toLowerCase().includes(search));
      const open = state.openRolePicker === inputId;
      const disabled = input.disabled ? " disabled" : "";

      picker.classList.toggle("open", open);
      picker.innerHTML = `
        <button id="${inputId}Button" class="role-picker-trigger" type="button" data-role-picker-toggle="${inputId}"${disabled}>
          ${selectedRoles.length ? `${selectedRoles.length} rol${selectedRoles.length === 1 ? "" : "es"} seleccionado${selectedRoles.length === 1 ? "" : "s"}` : "Seleccionar roles"}
        </button>
        <div class="role-picker-selected">
          ${selectedRoles.length ? selectedRoles.map(role => `
            <span class="role-chip">@${escapeHtml(role.name)}
              <button type="button" data-role-picker-remove="${inputId}" data-role-id="${escapeHtml(role.id)}" aria-label="Quitar ${escapeHtml(role.name)}">x</button>
            </span>
          `).join("") : `<span class="muted">Sin roles seleccionados</span>`}
        </div>
        <div class="role-picker-menu">
          <input class="role-picker-search" type="text" placeholder="Buscar rol" value="${escapeHtml(state.rolePickerSearch[inputId] || "")}" data-role-picker-search="${inputId}">
          <div class="role-picker-options">
            ${visibleRoles.length ? visibleRoles.map(role => {
              const active = selected.has(String(role.id));
              const full = !active && selected.size >= 3;
              return `
                <button class="role-picker-option${active ? " active" : ""}" type="button" data-role-picker-option="${inputId}" data-role-id="${escapeHtml(role.id)}"${full ? " disabled" : ""}>
                  <span class="role-picker-check">${active ? "✓" : ""}</span>
                  <span>@${escapeHtml(role.name)}</span>
                </button>
              `;
            }).join("") : `<div class="role-picker-empty">No hay roles para mostrar.</div>`}
          </div>
        </div>
      `;
    }

    function renderAllRolePickers(panel) {
      renderRoleSelect("claimRoles", panel.permissions?.claim_roles || []);
      renderRoleSelect("closeRoles", panel.permissions?.close_roles || []);
      renderRoleSelect("reopenRoles", panel.permissions?.reopen_roles || []);
      renderRoleSelect("deleteRoles", panel.permissions?.delete_roles || []);
    }

    function renderRolePickerById(inputId) {
      const panel = currentTicketPanel();
      if (!panel) return;
      const map = {
        claimRoles: "claim_roles",
        closeRoles: "close_roles",
        reopenRoles: "reopen_roles",
        deleteRoles: "delete_roles"
      };
      renderRoleSelect(inputId, panel.permissions?.[map[inputId]] || rolePickerValues(inputId));
    }

    function enforceRoleLimit(input) {
      if (!input) return;
      const values = rolePickerValues(input.id).slice(0, 3);
      setRolePickerValues(input.id, values);
      if (permissionValues(input.value).length > 3) {
        document.getElementById("ticketStatus").textContent = "Puedes seleccionar maximo 3 roles por permiso.";
      }
    }

    function renderTicketEditor() {
      const panel = currentTicketPanel();
      document.getElementById("ticketEmptyEditor").hidden = Boolean(panel);
      document.getElementById("ticketEditor").hidden = !panel;
      const disabled = !panel;
      ["ticketName", "ticketMode", "ticketChannel", "ticketOpenCategory", "ticketColor", "ticketContent", "ticketTitle", "ticketFooter", "ticketDescription", "ticketImage", "ticketOpenTitle", "ticketOpenColor", "ticketOpenDescription", "claimRoles", "closeRoles", "reopenRoles", "deleteRoles"].forEach(id => {
        document.getElementById(id).disabled = disabled;
      });

      document.getElementById("savePanelButton").disabled = disabled;
      document.getElementById("publishPanelButton").disabled = disabled;
      document.getElementById("clonePanelButton").disabled = disabled;
      document.getElementById("deletePanelButton").disabled = disabled;
      document.getElementById("addTicketOptionButton").disabled = disabled;

      if (!panel) {
        document.getElementById("ticketPreview").textContent = "Crea un panel para empezar.";
        document.getElementById("ticketOptions").innerHTML = "";
        ["claimRoles", "closeRoles", "reopenRoles", "deleteRoles"].forEach(id => {
          document.getElementById(id).value = "";
          document.getElementById(`${id}Picker`).innerHTML = "";
        });
        return;
      }

      document.getElementById("ticketName").value = panel.name || "";
      document.getElementById("ticketMode").value = panel.mode || "buttons";
      document.getElementById("ticketChannel").value = panel.channel_id || "";
      document.getElementById("ticketOpenCategory").value = panel.open_category_id || "";
      document.getElementById("ticketColor").value = panel.embed_color || "#22c55e";
      document.getElementById("ticketContent").value = panel.message_content || "";
      document.getElementById("ticketTitle").value = panel.embed_title || "";
      document.getElementById("ticketFooter").value = panel.embed_footer || "";
      document.getElementById("ticketDescription").value = panel.embed_description || "";
      document.getElementById("ticketImage").value = panel.image_url || "";
      document.getElementById("ticketOpenTitle").value = panel.ticket_open_title || "Ticket abierto";
      document.getElementById("ticketOpenColor").value = panel.ticket_open_color || "#38bdf8";
      document.getElementById("ticketOpenDescription").value = panel.ticket_open_description || "Un miembro del staff te atendera pronto.";
      renderAllRolePickers(panel);
      renderTicketOptions(panel);
      renderTicketPreview(panel);
      renderTicketOpenPreview(panel);
    }

    function renderTicketOptions(panel) {
      const container = document.getElementById("ticketOptions");
      const emojiOptions = buildEmojiOptions();
      container.innerHTML = (panel.options || []).map((option, index) => `
        <div class="option-row" data-option-index="${index}">
          <select class="ticket-option-emoji">${emojiOptions(option.emoji || "")}</select>
          <input class="ticket-option-label" type="text" placeholder="Nombre de opcion" value="${escapeHtml(option.label || "")}">
          <input class="ticket-option-description" type="text" placeholder="Descripcion" value="${escapeHtml(option.description || "")}">
          <button class="icon-button remove-ticket-option" type="button" title="Quitar opcion" aria-label="Quitar opcion">x</button>
        </div>
      `).join("");

      container.querySelectorAll("input, select").forEach(input => {
        input.addEventListener("input", () => {
          persistCurrentTicketPanel();
          renderCurrentTicketPreviews();
        });
        input.addEventListener("change", () => {
          persistCurrentTicketPanel();
          renderCurrentTicketPreviews();
        });
      });
      container.querySelectorAll(".remove-ticket-option").forEach(button => {
        button.addEventListener("click", event => {
          const row = event.target.closest(".option-row");
          const index = Number(row.dataset.optionIndex);
          const current = currentTicketPanel();
          if (!current || current.options.length <= 1) return;
          current.options.splice(index, 1);
          state.ticketPanelsDirty = true;
          renderTickets();
        });
      });
    }

    function buildEmojiOptions(selectedValue) {
      return function optionsMarkup(currentValue) {
        const selected = currentValue || selectedValue || "";
        const defaults = globalTicketEmojis.map(([value, label]) => {
          const isSelected = value === selected ? " selected" : "";
          return `<option value="${escapeHtml(value)}"${isSelected}>${escapeHtml(label)}</option>`;
        }).join("");
        return defaults;
      };
    }

    function collectTicketOptions() {
      return Array.from(document.querySelectorAll(".option-row")).map(row => ({
        id: currentTicketPanel()?.options?.[Number(row.dataset.optionIndex)]?.id || (crypto.randomUUID ? crypto.randomUUID() : String(Date.now())),
        emoji: row.querySelector(".ticket-option-emoji").value.trim(),
        label: row.querySelector(".ticket-option-label").value.trim() || "Abrir ticket",
        description: row.querySelector(".ticket-option-description").value.trim()
      }));
    }

    function persistCurrentTicketPanel() {
      const panel = currentTicketPanel();
      if (!panel) return;

      panel.name = document.getElementById("ticketName").value.trim() || "Nuevo panel";
      panel.mode = document.getElementById("ticketMode").value;
      panel.channel_id = document.getElementById("ticketChannel").value;
      panel.open_category_id = document.getElementById("ticketOpenCategory").value;
      panel.embed_color = document.getElementById("ticketColor").value.trim() || "#22c55e";
      panel.message_content = document.getElementById("ticketContent").value;
      panel.embed_title = document.getElementById("ticketTitle").value.trim() || panel.name;
      panel.embed_footer = document.getElementById("ticketFooter").value.trim();
      panel.embed_description = document.getElementById("ticketDescription").value || "Selecciona una opcion para abrir un ticket.";
      panel.image_url = document.getElementById("ticketImage").value.trim();
      panel.ticket_open_title = document.getElementById("ticketOpenTitle").value.trim() || "Ticket abierto";
      panel.ticket_open_color = document.getElementById("ticketOpenColor").value.trim() || "#38bdf8";
      panel.ticket_open_description = document.getElementById("ticketOpenDescription").value || "Un miembro del staff te atendera pronto.";
      panel.options = collectTicketOptions();
      panel.permissions = {
        claim_roles: rolePickerValues("claimRoles"),
        close_roles: rolePickerValues("closeRoles"),
        reopen_roles: rolePickerValues("reopenRoles"),
        delete_roles: rolePickerValues("deleteRoles")
      };
      state.ticketPanelsDirty = true;
    }

    function renderCurrentTicketPreviews() {
      const panel = currentTicketPanel();
      renderTicketPreview(panel);
      renderTicketOpenPreview(panel);
    }

    function renderTicketPreview(panel) {
      if (!panel) return;
      const mode = panel.mode === "select" ? "Lista desplegable" : "Botones";
      const actions = (panel.options || []).map(option => `
        <span class="discord-preview-action">${escapeHtml(option.emoji || "")}${option.emoji ? " " : ""}${escapeHtml(option.label)}</span>
      `).join("");
      document.getElementById("ticketPreview").innerHTML = `
        <div class="discord-preview" style="border-left-color:${escapeHtml(panel.embed_color || "#22c55e")}">
          ${panel.message_content ? `<div class="muted">${escapeHtml(panel.message_content)}</div>` : ""}
          <div class="discord-preview-title">${escapeHtml(panel.embed_title || panel.name)}</div>
          <div class="discord-preview-description">${escapeHtml(panel.embed_description || "")}</div>
          <div class="muted">Modo: ${escapeHtml(mode)}</div>
          <div class="discord-preview-actions">${actions || `<span class="muted">Sin opciones</span>`}</div>
          ${panel.embed_footer ? `<div class="muted">${escapeHtml(panel.embed_footer)}</div>` : ""}
        </div>
      `;
    }

    function renderTicketOpenPreview(panel) {
      if (!panel) return;
      document.getElementById("ticketOpenPreview").innerHTML = `
        <div class="discord-preview" style="border-left-color:${escapeHtml(panel.ticket_open_color || "#38bdf8")}">
          <div class="discord-preview-title">${escapeHtml(panel.ticket_open_title || "Ticket abierto")}</div>
          <div class="discord-preview-description">${escapeHtml(panel.ticket_open_description || "")}</div>
          <div class="discord-preview-actions">
            <span class="discord-preview-action">Reclamar ticket</span>
            <span class="discord-preview-action">Cerrar ticket</span>
          </div>
        </div>
      `;
    }

    function applyTheme() {
      document.body.classList.toggle("theme-dark", state.theme === "dark");
    }

    function renderTheme() {
      applyTheme();
      const button = document.getElementById("themeToggle");
      button.innerHTML = state.theme === "dark"
        ? `<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path></svg>`
        : `<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.99 12.35A8.5 8.5 0 1 1 11.65 3a6.5 6.5 0 0 0 9.34 9.35Z"></path></svg>`;
      button.title = state.theme === "dark" ? "Cambiar a tema claro" : "Cambiar a tema oscuro";
      button.setAttribute("aria-label", button.title);
    }

    function renderSections() {
      document.getElementById("appShell").classList.toggle("sidebar-collapsed", state.sidebarCollapsed);
      document.getElementById("appShell").classList.toggle("transcript-open", state.section === "tickets" && state.ticketTranscriptOpen);
      document.body.classList.toggle("transcript-open", state.section === "tickets" && state.ticketTranscriptOpen);
      document.getElementById("economySection").hidden = state.section !== "economy";
      document.getElementById("templatesSection").hidden = state.section !== "templates";
      document.getElementById("ticketsSection").hidden = state.section !== "tickets";
      document.getElementById("welcomeSection").hidden = state.section !== "welcome";
      document.getElementById("auditSection").hidden = state.section !== "audit";
      document.getElementById("permissionsSection").hidden = state.section !== "permissions";
      document.getElementById("searchInput").hidden = state.section !== "economy";
      document.querySelectorAll(".section-button").forEach(button => {
        button.classList.toggle("active", button.dataset.section === state.section);
      });
    }

    function renderSession() {
      const viewer = state.data?.viewer || null;
      const authenticated = Boolean(viewer?.id);
      document.getElementById("userLabel").textContent = authenticated ? viewer.username : "No conectado";
      document.getElementById("logoutButton").hidden = !authenticated;
    }

    function renderBlocked(message) {
      state.data = {
        guilds: [],
        selectedGuildId: "",
        balances: [],
        operations: [],
        avalonians: [],
        reports: [],
        totals: { players: 0, items: 0, silver: 0, total: 0 },
        updatedAt: "",
        viewer: {}
      };
      render();
      document.getElementById("status").textContent = message;
    }

    async function loadData() {
      const params = new URLSearchParams();
      if (state.guildId) params.set("guild_id", state.guildId);
      const response = await fetch(`/api/data?${params.toString()}`, { cache: "no-store" });
      if (response.status === 401 || response.status === 503) {
        window.location.href = "/";
        return;
      }
      if (!response.ok) throw new Error("No se pudo cargar la informacion.");
      state.data = await response.json();
      state.csrfToken = state.data.csrf_token || "";
      state.guildId = state.data.selectedGuildId || "";
      if (state.guildId) localStorage.setItem("dashboardGuildId", state.guildId);
      await loadTicketConfig();
      render();
    }

    function csrfHeaders(extra = {}) {
      const headers = { ...extra };
      if (state.csrfToken) headers["X-CSRF-Token"] = state.csrfToken;
      return headers;
    }

    async function loadTicketConfig() {
      if (!state.guildId) return;
      if (state.ticketConfigGuildId === state.guildId && state.ticketPanelsDirty) return;
      if (state.ticketConfigGuildId === state.guildId && state.ticketPanels.length) return;

      const params = new URLSearchParams({ guild_id: state.guildId });
      const [panelsResponse, channelsResponse, categoriesResponse, emojisResponse, rolesResponse, recordsResponse, auditResponse, auditEventsResponse, templatesResponse, botPermissionsResponse] = await Promise.all([
        fetch(`/api/ticket-panels?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/discord-channels?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/discord-categories?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/discord-emojis?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/discord-roles?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/ticket-records?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/audit-config?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/audit-events?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/ping-templates?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/bot-permissions?${params.toString()}`, { cache: "no-store" })
      ]);

      if (panelsResponse.ok) {
        const payload = await panelsResponse.json();
        state.ticketPanels = payload.panels || [];
      }
      if (channelsResponse.ok) {
        const payload = await channelsResponse.json();
        state.ticketChannels = payload.channels || [];
      }
      if (categoriesResponse.ok) {
        const payload = await categoriesResponse.json();
        state.ticketCategories = payload.categories || [];
      }
      if (emojisResponse.ok) {
        const payload = await emojisResponse.json();
        state.ticketEmojis = payload.emojis || [];
      }
      if (rolesResponse.ok) {
        const payload = await rolesResponse.json();
        state.ticketRoles = payload.roles || [];
      }
      if (recordsResponse.ok) {
        const payload = await recordsResponse.json();
        state.ticketRecords = payload.records || [];
      }
      if (auditResponse.ok) {
        const payload = await auditResponse.json();
        state.auditCategories = payload.categories || [];
        state.auditConfig = payload.config || { channels: {} };
      }
      if (auditEventsResponse.ok) {
        const payload = await auditEventsResponse.json();
        state.auditEvents = payload.events || [];
      }
      if (templatesResponse.ok) {
        const payload = await templatesResponse.json();
        state.pingTemplates = payload.templates || [];
        state.pingTemplateSavedCount = payload.saved_count || 0;
        state.pingTemplateMax = payload.max_templates || 5;
        if (!state.pingTemplates.some(template => template.key === state.currentPingTemplateKey)) {
          state.currentPingTemplateKey = state.pingTemplates[0]?.key || "";
          if (state.currentPingTemplateKey) localStorage.setItem("dashboardPingTemplateKey", state.currentPingTemplateKey);
        }
      }
      if (botPermissionsResponse.ok) {
        const payload = await botPermissionsResponse.json();
        state.botPermissions = payload.permissions || {};
        state.botPermissionOptions = payload.options || [];
      }
      state.ticketConfigGuildId = state.guildId;
      state.ticketPanelsDirty = false;
      if (!state.ticketPanels.some(panel => panel.id === state.currentTicketPanelId)) {
        state.currentTicketPanelId = "";
        localStorage.removeItem("dashboardTicketPanelId");
      }
    }

    async function saveTicketPanels() {
      persistCurrentTicketPanel();
      const response = await fetch("/api/ticket-panels", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          panels: state.ticketPanels
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude guardar los paneles.");
      state.ticketPanels = payload.panels || [];
      state.ticketPanelsDirty = false;
      document.getElementById("ticketStatus").textContent = "Configuracion guardada.";
      renderTickets();
    }

    async function readJsonResponse(response) {
      const text = await response.text();
      if (!text) return {};
      try {
        return JSON.parse(text);
      } catch (error) {
        throw new Error(text.slice(0, 180) || "Respuesta invalida del dashboard.");
      }
    }

    function applyPingTemplatesPayload(payload) {
      state.pingTemplates = payload.templates || [];
      state.pingTemplateSavedCount = payload.saved_count || 0;
      state.pingTemplateMax = payload.max_templates || 5;
      if (!state.pingTemplates.some(template => template.key === state.currentPingTemplateKey)) {
        state.currentPingTemplateKey = state.pingTemplates[0]?.key || "";
      }
      localStorage.setItem("dashboardPingTemplateKey", state.currentPingTemplateKey);
    }

    async function savePingTemplate() {
      const data = templateFormData();
      if (!state.guildId) {
        throw new Error("Selecciona un servidor antes de guardar la plantilla.");
      }
      document.getElementById("templateStatus").textContent = "Guardando plantilla...";
      const response = await fetch("/api/ping-templates", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          template: data
        })
      });
      const payload = await readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude guardar la plantilla.");
      delete state.pingTemplateDrafts[data.original_key];
      delete state.pingTemplateDrafts[data.key];
      applyPingTemplatesPayload(payload);
      state.currentPingTemplateKey = payload.template?.key || state.currentPingTemplateKey;
      localStorage.setItem("dashboardPingTemplateKey", state.currentPingTemplateKey);
      state.templateStatusMessage = "Plantilla guardada. Los comandos /ping y /plantilla ya usan esta configuracion.";
      renderTemplates();
    }

    async function deletePingTemplate() {
      const template = currentPingTemplate();
      const key = document.getElementById("templateOriginalKey").value.trim() || template?.key || "";
      if (!state.guildId) {
        throw new Error("Selecciona un servidor antes de eliminar la plantilla.");
      }
      if (!template || !template.deletable || !key) {
        throw new Error("Esta plantilla todavia no se puede eliminar. Guarda una version del servidor primero.");
      }
      document.getElementById("templateStatus").textContent = "Eliminando plantilla...";
      const response = await fetch("/api/ping-templates", {
        method: "DELETE",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          key
        })
      });
      const payload = await readJsonResponse(response);
      if (!response.ok) throw new Error(payload.error || "No pude eliminar la plantilla.");
      delete state.pingTemplateDrafts[key];
      applyPingTemplatesPayload(payload);
      state.templateStatusMessage = "Plantilla eliminada.";
      renderTemplates();
    }

    async function saveAuditConfig() {
      const response = await fetch("/api/audit-config", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          config: state.auditConfig
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude guardar auditoria.");
      state.auditConfig = payload.config || { channels: {} };
      document.getElementById("auditStatus").textContent = "Auditoria guardada.";
      renderAudit();
    }

    async function saveBotPermissions() {
      const response = await fetch("/api/bot-permissions", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          permissions: collectBotPermissions()
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude guardar los permisos.");
      state.botPermissions = payload.permissions || {};
      state.botPermissionOptions = payload.options || state.botPermissionOptions;
      document.getElementById("permissionsStatus").textContent = "Permisos guardados. Los comandos de Discord ya usan esta configuracion.";
      renderPermissions();
    }

    async function publishCurrentTicketPanel() {
      persistCurrentTicketPanel();
      const panel = currentTicketPanel();
      if (!panel) return;
      const response = await fetch("/api/publish-ticket-panel", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          channel_id: panel.channel_id,
          panel
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude publicar el panel.");
      document.getElementById("ticketStatus").textContent = `Publicado en Discord. Mensaje ${payload.message_id || ""}`;
    }

    document.getElementById("guildSelect").addEventListener("change", event => {
      state.guildId = event.target.value;
      localStorage.setItem("dashboardGuildId", state.guildId);
      loadData().catch(showError);
    });

    document.getElementById("searchInput").addEventListener("input", event => {
      state.search = event.target.value;
      renderTable();
    });

    document.getElementById("logoutButton").addEventListener("click", () => {
      window.location.href = "/logout";
    });

    document.getElementById("themeToggle").addEventListener("click", () => {
      state.theme = state.theme === "dark" ? "light" : "dark";
      localStorage.setItem("dashboardTheme", state.theme);
      renderTheme();
    });

    document.getElementById("sidebarToggle").addEventListener("click", () => {
      state.sidebarCollapsed = !state.sidebarCollapsed;
      localStorage.setItem("dashboardSidebarCollapsed", state.sidebarCollapsed ? "1" : "0");
      renderSections();
    });

    document.querySelectorAll(".section-button").forEach(button => {
      button.addEventListener("click", () => {
        state.section = button.dataset.section;
        localStorage.setItem("dashboardSection", state.section);
        render();
      });
    });

    document.querySelectorAll(".editor-tab").forEach(button => {
      button.addEventListener("click", () => {
        state.ticketEditorSection = button.dataset.editorSection;
        localStorage.setItem("dashboardTicketEditorSection", state.ticketEditorSection);
        renderTicketEditorSections();
      });
    });

    ["ticketName", "ticketMode", "ticketChannel", "ticketOpenCategory", "ticketColor", "ticketContent", "ticketTitle", "ticketFooter", "ticketDescription", "ticketImage", "ticketOpenTitle", "ticketOpenColor", "ticketOpenDescription", "claimRoles", "closeRoles", "reopenRoles", "deleteRoles"].forEach(id => {
      document.getElementById(id).addEventListener("input", () => {
        if (id.endsWith("Roles")) enforceRoleLimit(document.getElementById(id));
        persistCurrentTicketPanel();
        renderCurrentTicketPreviews();
      });
      document.getElementById(id).addEventListener("change", () => {
        if (id.endsWith("Roles")) enforceRoleLimit(document.getElementById(id));
        persistCurrentTicketPanel();
        renderCurrentTicketPreviews();
      });
    });

    document.addEventListener("click", event => {
      const toggle = event.target.closest("[data-role-picker-toggle]");
      const option = event.target.closest("[data-role-picker-option]");
      const remove = event.target.closest("[data-role-picker-remove]");
      const insidePicker = event.target.closest(".role-picker");

      if (toggle) {
        const inputId = toggle.dataset.rolePickerToggle;
        state.openRolePicker = state.openRolePicker === inputId ? "" : inputId;
        renderRolePickerById(inputId);
        return;
      }

      if (option) {
        const inputId = option.dataset.rolePickerOption;
        const roleId = String(option.dataset.roleId || "");
        const values = rolePickerValues(inputId);
        const exists = values.includes(roleId);
        if (exists) {
          setRolePickerValues(inputId, values.filter(value => value !== roleId));
        } else if (values.length < 3) {
          setRolePickerValues(inputId, [...values, roleId]);
        } else {
          document.getElementById("ticketStatus").textContent = "Puedes seleccionar maximo 3 roles por permiso.";
        }
        state.openRolePicker = inputId;
        persistCurrentTicketPanel();
        renderRolePickerById(inputId);
        return;
      }

      if (remove) {
        const inputId = remove.dataset.rolePickerRemove;
        const roleId = String(remove.dataset.roleId || "");
        setRolePickerValues(inputId, rolePickerValues(inputId).filter(value => value !== roleId));
        state.openRolePicker = inputId;
        persistCurrentTicketPanel();
        renderRolePickerById(inputId);
        return;
      }

      if (!insidePicker && state.openRolePicker) {
        const inputId = state.openRolePicker;
        state.openRolePicker = "";
        renderRolePickerById(inputId);
      }
    });

    document.addEventListener("input", event => {
      const search = event.target.closest("[data-role-picker-search]");
      if (!search) return;
      const inputId = search.dataset.rolePickerSearch;
      state.rolePickerSearch[inputId] = search.value;
      state.openRolePicker = inputId;
      renderRolePickerById(inputId);
      setTimeout(() => {
        const refreshed = document.querySelector(`[data-role-picker-search="${inputId}"]`);
        if (refreshed) {
          refreshed.focus();
          refreshed.setSelectionRange(refreshed.value.length, refreshed.value.length);
        }
      }, 0);
    });

    document.getElementById("ticketRecordSearch").addEventListener("input", event => {
      state.ticketRecordSearch = event.target.value;
      renderTicketRecords();
    });

    document.getElementById("refreshTicketRecordsButton").addEventListener("click", () => {
      state.ticketConfigGuildId = "";
      loadTicketConfig().then(renderTickets).catch(showError);
    });

    document.getElementById("newTemplateButton").addEventListener("click", () => {
      const template = newPingTemplate();
      template.key = `plantilla-${Date.now().toString().slice(-4)}`;
      template.name = "Nueva plantilla";
      state.pingTemplates = [template, ...state.pingTemplates.filter(item => item.key !== template.key)];
      state.currentPingTemplateKey = template.key;
      localStorage.setItem("dashboardPingTemplateKey", state.currentPingTemplateKey);
      renderTemplates();
    });

    document.getElementById("saveTemplateButton").addEventListener("click", () => {
      savePingTemplate().catch(error => {
        document.getElementById("templateStatus").textContent = error.message;
      });
    });

    document.getElementById("deleteTemplateButton").addEventListener("click", () => {
      deletePingTemplate().catch(error => {
        document.getElementById("templateStatus").textContent = error.message;
      });
    });

    ["templateKey", "templateName", "templateTitle", "templateMention", "templateJoinCommand", "templateCallerSlot", "templateRoles", "templateSlotFormat", "templateContent", "templateLootLink", "templateReportEnabled"].forEach(id => {
      document.getElementById(id).addEventListener("input", () => {
        saveTemplateDraft();
        renderTemplatePreview();
      });
      document.getElementById(id).addEventListener("change", () => {
        saveTemplateDraft();
        renderTemplatePreview();
      });
    });

    document.getElementById("backToTicketsButton").addEventListener("click", () => {
      closeTicketTranscript();
    });

    document.getElementById("createPanelButton").addEventListener("click", () => {
      persistCurrentTicketPanel();
      const panel = newTicketPanel("Nuevo panel");
      state.ticketPanels.push(panel);
      state.currentTicketPanelId = panel.id;
      state.ticketPanelsDirty = true;
      localStorage.setItem("dashboardTicketPanelId", panel.id);
      renderTickets();
    });

    document.getElementById("clonePanelButton").addEventListener("click", () => {
      persistCurrentTicketPanel();
      const panel = currentTicketPanel();
      if (!panel) return;
      const clone = JSON.parse(JSON.stringify(panel));
      clone.id = crypto.randomUUID ? crypto.randomUUID() : String(Date.now());
      clone.name = `${panel.name} copia`;
      clone.options = (clone.options || []).map(option => ({
        ...option,
        id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`
      }));
      state.ticketPanels.push(clone);
      state.currentTicketPanelId = clone.id;
      state.ticketPanelsDirty = true;
      localStorage.setItem("dashboardTicketPanelId", clone.id);
      renderTickets();
    });

    document.getElementById("deletePanelButton").addEventListener("click", () => {
      const panel = currentTicketPanel();
      if (!panel) return;
      state.ticketPanels = state.ticketPanels.filter(item => item.id !== panel.id);
      state.currentTicketPanelId = state.ticketPanels[0]?.id || "";
      state.ticketPanelsDirty = true;
      localStorage.setItem("dashboardTicketPanelId", state.currentTicketPanelId);
      renderTickets();
    });

    document.getElementById("addTicketOptionButton").addEventListener("click", () => {
      persistCurrentTicketPanel();
      const panel = currentTicketPanel();
      if (!panel) return;
      panel.options.push({
        id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()),
        emoji: "",
        label: `Opcion ${panel.options.length + 1}`,
        description: ""
      });
      state.ticketPanelsDirty = true;
      renderTickets();
    });

    document.getElementById("savePanelButton").addEventListener("click", () => {
      saveTicketPanels().catch(error => {
        document.getElementById("ticketStatus").textContent = error.message;
      });
    });

    document.getElementById("publishPanelButton").addEventListener("click", () => {
      publishCurrentTicketPanel().catch(error => {
        document.getElementById("ticketStatus").textContent = error.message;
      });
    });

    document.getElementById("saveAuditConfigButton").addEventListener("click", () => {
      saveAuditConfig().catch(error => {
        document.getElementById("auditStatus").textContent = error.message;
      });
    });

    document.getElementById("savePermissionsButton").addEventListener("click", () => {
      state.botPermissions = collectBotPermissions();
      saveBotPermissions().catch(error => {
        document.getElementById("permissionsStatus").textContent = error.message;
      });
    });

    document.getElementById("refreshPermissionsButton").addEventListener("click", () => {
      state.ticketConfigGuildId = "";
      loadTicketConfig().then(() => {
        document.getElementById("permissionsStatus").textContent = "Permisos recargados.";
        renderPermissions();
      }).catch(error => {
        document.getElementById("permissionsStatus").textContent = error.message;
      });
    });

    document.getElementById("permissionsGrid").addEventListener("change", event => {
      if (!event.target.matches("[data-permission-role]")) return;
      state.botPermissions = collectBotPermissions();
      document.getElementById("permissionsStatus").textContent = "Cambios sin guardar.";
      renderPermissions();
    });

    document.getElementById("permissionRoleSearch").addEventListener("input", event => {
      state.botPermissions = collectBotPermissions();
      state.permissionSearch = event.target.value;
      renderPermissions();
    });

    document.querySelectorAll(".tab").forEach(button => {
      button.addEventListener("click", () => {
        state.tab = button.dataset.tab;
        render();
      });
    });

    function showError(error) {
      document.getElementById("status").textContent = error.message;
    }

    loadData().catch(showError);
    document.addEventListener("focusin", event => {
      if (event.target.matches("select, input, textarea, button")) state.userInteracting = true;
    });

    document.addEventListener("focusout", () => {
      setTimeout(() => {
        state.userInteracting = Boolean(document.activeElement?.matches("select, input, textarea, button"));
      }, 250);
    });

    setInterval(() => {
      if (state.userInteracting || state.section !== "economy") return;
      loadData().catch(showError);
    }, 3000);
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def send_text(self, status, content, content_type, headers=None):
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(encoded)

    def send_json(self, status, data):
        self.send_text(status, json.dumps(data, ensure_ascii=False), "application/json")

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}

        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def get_authenticated_session(self):
        if not oauth_configured():
            self.send_json(503, {
                "error": "Configura DASHBOARD_CLIENT_ID y DASHBOARD_CLIENT_SECRET para habilitar el acceso por Discord."
            })
            return None

        session = get_session_from_request(self)
        if not session:
            self.send_json(401, {"error": "Inicia sesion con Discord para ver el dashboard."})
            return None

        return session

    def can_access_guild(self, session, guild_id):
        allowed_guilds = {guild["id"] for guild in session.get("admin_guilds", [])}
        bot_guild_ids = get_bot_guild_ids()
        return str(guild_id) in allowed_guilds and (bot_guild_ids is None or str(guild_id) in bot_guild_ids)

    def has_same_origin(self):
        host = self.headers.get("Host", "")
        if not host:
            return False

        expected = {
            f"http://{host}",
            f"https://{host}",
        }
        for header_name in ("Origin", "Referer"):
            value = self.headers.get(header_name, "")
            if not value:
                continue
            parsed = urlparse(value)
            base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
            if base in expected:
                return True
            return False

        return True

    def validate_csrf(self, session):
        if not self.has_same_origin():
            self.send_json(403, {"error": "Origen invalido para esta sesion."})
            return False

        expected = str(session.get("csrf_token") or "")
        provided = str(self.headers.get("X-CSRF-Token") or "")
        if not expected or not provided or not secrets.compare_digest(provided, expected):
            self.send_json(403, {"error": "Token CSRF invalido. Recarga el dashboard e intenta de nuevo."})
            return False

        return True

    def send_file(self, status, path, content_type):
        try:
            with open(path, "rb") as f:
                content = f.read()
        except OSError:
            self.send_text(404, "No encontrado", "text/plain")
            return

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(content)

    def send_ticket_media(self, relative_path):
        session = get_session_from_request(self)
        if not session:
            self.send_text(401, "Inicia sesion.", "text/plain")
            return

        requested = unquote(relative_path).replace("\\", "/").lstrip("/")
        root = os.path.abspath(TICKET_MEDIA_DIR)
        path = os.path.abspath(os.path.join(root, requested))
        if path != root and not path.startswith(root + os.sep):
            self.send_text(403, "No permitido", "text/plain")
            return

        content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        self.send_file(200, path, content_type)

    def send_redirect(self, location, headers=None):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def get_redirect_uri(self):
        if DASHBOARD_REDIRECT_URI:
            return DASHBOARD_REDIRECT_URI

        host = self.headers.get("Host", f"localhost:{self.server.server_port}")
        return f"http://{host}/oauth/callback"

    def handle_login(self):
        if not oauth_configured():
            self.send_text(
                503,
                "Falta configurar DASHBOARD_CLIENT_ID y DASHBOARD_CLIENT_SECRET en el archivo .env.",
                "text/plain",
            )
            return

        query = parse_qs(urlparse(self.path).query)
        remember_device = query.get("remember", [""])[0] == "1"
        state = secrets.token_urlsafe(24)
        params = urlencode({
            "client_id": DASHBOARD_CLIENT_ID,
            "redirect_uri": self.get_redirect_uri(),
            "response_type": "code",
            "scope": "identify guilds",
            "state": state,
        })
        remember_oauth_state(state, remember_device)
        self.send_redirect(
            f"https://discord.com/oauth2/authorize?{params}",
            headers={"Set-Cookie": make_state_cookie(state)},
        )

    def handle_oauth_callback(self, parsed):
        if not oauth_configured():
            self.send_redirect("/")
            return

        query = parse_qs(parsed.query)
        code = query.get("code", [""])[0]
        state = query.get("state", [""])[0]
        state_payload = consume_oauth_state(state)
        if not code or not state_payload:
            self.send_text(400, "Estado de OAuth invalido. Intenta iniciar sesion de nuevo.", "text/plain")
            return

        token_data = discord_request(
            "/oauth2/token",
            data={
                "client_id": DASHBOARD_CLIENT_ID,
                "client_secret": DASHBOARD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.get_redirect_uri(),
            },
        )
        access_token = token_data.get("access_token")
        if not access_token:
            self.send_text(500, "Discord no devolvio access_token.", "text/plain")
            return

        user = discord_request("/users/@me", token=access_token)
        guilds = discord_request("/users/@me/guilds", token=access_token)
        admin_guilds = admin_guilds_from_discord(guilds)
        session_id = create_session(
            {
                "id": str(user.get("id")),
                "username": str(user.get("global_name") or user.get("username") or "Discord"),
            },
            admin_guilds,
            remember_device=state_payload.get("remember_device", False),
        )
        ttl = REMEMBER_SESSION_TTL_SECONDS if state_payload.get("remember_device", False) else SESSION_TTL_SECONDS
        headers = {
            "Set-Cookie": make_cookie_value(encode_session_cookie(session_id), ttl),
        }
        self.send_redirect("/dashboard", headers=headers)

    def handle_logout(self):
        clear_session_from_request(self)
        self.send_redirect(
            "/",
            headers={"Set-Cookie": make_cookie_value("", 0)},
        )

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            if get_session_from_request(self):
                self.send_redirect("/dashboard")
                return

            self.send_text(200, LOGIN_HTML, "text/html")
            return

        if parsed.path == "/dashboard":
            if not get_session_from_request(self):
                self.send_redirect("/")
                return

            self.send_text(200, INDEX_HTML, "text/html")
            return

        if parsed.path == "/ticket-transcript":
            session = get_session_from_request(self)
            if not session:
                self.send_redirect("/")
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            record_id = query.get("record_id", [""])[0]
            if not guild_id or not self.can_access_guild(session, guild_id):
                self.send_text(403, "No tienes acceso a ese servidor.", "text/plain")
                return

            record = get_ticket_record(guild_id, record_id)
            if not record:
                self.send_text(404, "No encontre esa transcripcion.", "text/plain")
                return

            guild_name = next((guild.get("name") for guild in session.get("admin_guilds", []) if guild.get("id") == str(guild_id)), f"Servidor {guild_id}")
            self.send_text(200, build_ticket_transcript_html(guild_name, record), "text/html")
            return

        if parsed.path == "/assets/AvalonBot.png":
            self.send_file(200, AVALON_BOT_LOGO_FILE, "image/png")
            return

        if parsed.path.startswith("/ticket-media/"):
            self.send_ticket_media(parsed.path.removeprefix("/ticket-media/"))
            return

        if parsed.path == "/login":
            try:
                self.handle_login()
            except Exception as exc:
                self.send_text(500, str(exc), "text/plain")
            return

        if parsed.path == "/oauth/callback":
            try:
                self.handle_oauth_callback(parsed)
            except Exception as exc:
                self.send_text(500, str(exc), "text/plain")
            return

        if parsed.path == "/logout":
            self.handle_logout()
            return

        if parsed.path == "/api/data":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            try:
                allowed_guilds = {
                    guild["id"]: guild["name"]
                    for guild in session.get("admin_guilds", [])
                }
                payload = build_dashboard_data(
                    guild_id,
                    allowed_guilds=allowed_guilds,
                    bot_guild_ids=get_bot_guild_ids(),
                    viewer=session.get("user", {}),
                )
                payload["csrf_token"] = session.get("csrf_token", "")
                self.send_json(200, payload)
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        if parsed.path == "/api/ticket-panels":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_guild(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            self.send_json(200, {"panels": get_guild_ticket_panels(guild_id)})
            return

        if parsed.path == "/api/discord-channels":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_guild(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            try:
                channels = discord_json_request(
                    f"/guilds/{guild_id}/channels",
                    token=BOT_TOKEN,
                    auth_scheme="Bot",
                )
                text_channels = [
                    {"id": str(channel["id"]), "name": str(channel.get("name") or channel["id"])}
                    for channel in channels
                    if int(channel.get("type", -1)) in (0, 5)
                ]
                self.send_json(200, {"channels": text_channels})
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        if parsed.path == "/api/discord-categories":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_guild(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            try:
                channels = discord_json_request(
                    f"/guilds/{guild_id}/channels",
                    token=BOT_TOKEN,
                    auth_scheme="Bot",
                )
                categories = [
                    {"id": str(channel["id"]), "name": str(channel.get("name") or channel["id"])}
                    for channel in channels
                    if int(channel.get("type", -1)) == 4
                ]
                self.send_json(200, {"categories": categories})
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        if parsed.path == "/api/discord-emojis":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_guild(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            try:
                emojis = discord_json_request(
                    f"/guilds/{guild_id}/emojis",
                    token=BOT_TOKEN,
                    auth_scheme="Bot",
                )
                self.send_json(200, {
                    "emojis": [
                        {
                            "id": str(emoji["id"]),
                            "name": str(emoji.get("name") or emoji["id"]),
                            "animated": bool(emoji.get("animated")),
                            "value": f"<{'a' if emoji.get('animated') else ''}:{emoji.get('name') or emoji['id']}:{emoji['id']}>",
                        }
                        for emoji in emojis
                    ]
                })
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        if parsed.path == "/api/discord-roles":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_guild(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            try:
                roles = discord_json_request(
                    f"/guilds/{guild_id}/roles",
                    token=BOT_TOKEN,
                    auth_scheme="Bot",
                )
                filtered = [
                    {"id": str(role["id"]), "name": str(role.get("name") or role["id"])}
                    for role in roles
                    if str(role.get("name") or "") != "@everyone"
                ]
                self.send_json(200, {"roles": filtered})
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        if parsed.path == "/api/audit-config":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_guild(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            self.send_json(200, {
                "categories": [
                    {"key": key, "name": name, "description": description}
                    for key, name, description in AUDIT_CATEGORIES
                ],
                "config": get_guild_audit_config(guild_id),
            })
            return

        if parsed.path == "/api/ticket-records":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_guild(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            self.send_json(200, {"records": get_guild_ticket_records(guild_id)})
            return

        if parsed.path == "/api/audit-events":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_guild(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            self.send_json(200, {"events": get_guild_audit_events(guild_id)})
            return

        if parsed.path == "/api/ping-templates":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_guild(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            self.send_json(200, get_guild_ping_templates(guild_id))
            return

        if parsed.path == "/api/bot-permissions":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_guild(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            self.send_json(200, get_guild_bot_permissions(guild_id))
            return

        self.send_text(404, "No encontrado", "text/plain")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/ticket-panels":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                guild_id = str(body.get("guild_id") or "")
                if not guild_id or not self.can_access_guild(session, guild_id):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return

                panels = [normalize_ticket_panel(panel) for panel in body.get("panels", []) if isinstance(panel, dict)]
                save_guild_ticket_panels(guild_id, panels)
                self.send_json(200, {"panels": panels})
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        if parsed.path == "/api/publish-ticket-panel":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                guild_id = str(body.get("guild_id") or "")
                channel_id = str(body.get("channel_id") or "")
                panel = normalize_ticket_panel(body.get("panel", {}))
                if not guild_id or not self.can_access_guild(session, guild_id):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return
                if not channel_id:
                    self.send_json(400, {"error": "Debes elegir un canal."})
                    return

                payload = build_ticket_message_payload(panel)
                result = discord_json_request(
                    f"/channels/{channel_id}/messages",
                    token=BOT_TOKEN,
                    auth_scheme="Bot",
                    method="POST",
                    payload=payload,
                )
                self.send_json(200, {"message_id": str(result.get("id", "")), "channel_id": channel_id})
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        if parsed.path == "/api/audit-config":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                guild_id = str(body.get("guild_id") or "")
                if not guild_id or not self.can_access_guild(session, guild_id):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return

                save_guild_audit_config(guild_id, body.get("config", {}))
                self.send_json(200, {"config": get_guild_audit_config(guild_id)})
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        if parsed.path == "/api/ping-templates":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                guild_id = str(body.get("guild_id") or "")
                if not guild_id or not self.can_access_guild(session, guild_id):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return

                template, error = save_guild_ping_template(guild_id, body.get("template", {}))
                if error:
                    self.send_json(400, {"error": error})
                    return

                payload = get_guild_ping_templates(guild_id)
                payload["template"] = template
                self.send_json(200, payload)
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        if parsed.path == "/api/bot-permissions":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                guild_id = str(body.get("guild_id") or "")
                if not guild_id or not self.can_access_guild(session, guild_id):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return

                payload, error = save_guild_bot_permissions(guild_id, body)
                if error:
                    self.send_json(400, {"error": error})
                    return

                self.send_json(200, payload)
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        self.send_json(404, {"error": "No encontrado"})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/ping-templates":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                guild_id = str(body.get("guild_id") or "")
                key = str(body.get("key") or "")
                if not guild_id or not self.can_access_guild(session, guild_id):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return

                removed = ping_template_service().delete_template(guild_id, key)
                if not removed:
                    self.send_json(400, {"error": "No pude eliminar esa plantilla. La base y desde-cero no se pueden eliminar."})
                    return

                self.send_json(200, get_guild_ping_templates(guild_id))
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        self.send_json(404, {"error": "No encontrado"})

    def log_message(self, format, *args):
        timestamp = datetime.now().strftime("%H:%M:%S")
        message = html.escape(format % args)
        print(f"[{timestamp}] {self.address_string()} {message}")


def parse_args():
    parser = argparse.ArgumentParser(description="Dashboard local de EconomyBot")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


class IPv6ThreadingHTTPServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6


def build_servers(host, port):
    requested_host = str(host or "").strip().lower()
    hosts = [host]
    if requested_host in ("127.0.0.1", "localhost"):
        hosts = ["127.0.0.1", "::1"]

    servers = []
    for bind_host in hosts:
        server_class = IPv6ThreadingHTTPServer if ":" in bind_host else ThreadingHTTPServer
        try:
            servers.append(server_class((bind_host, port), DashboardHandler))
        except OSError:
            for server in servers:
                server.server_close()
            raise

    return servers


def main():
    args = parse_args()
    servers = build_servers(args.host, args.port)
    print(f"Dashboard disponible en http://localhost:{args.port}")
    print(f"Tambien disponible en http://127.0.0.1:{args.port}")
    print("Presiona Ctrl+C para detenerlo.")
    try:
        for server in servers:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
