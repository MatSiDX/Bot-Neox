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
import shutil
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
from repositories.albion_registration_repository import AlbionRegistrationRepository
from repositories.active_avalonian_repository import ACTIVE_AVALONIAN_FILE
from repositories.balance_repository import DATA_DIR
from repositories.report_dashboard_repository import ReportDashboardRepository
from services.config_service import ConfigService
from services.ping_template_service import MAX_TEMPLATES_PER_GUILD, SCRATCH_TEMPLATE_KEY, PingTemplateService
from services.fine_service import FineService
from services.permission_service import (
    PERMISSION_ECONOMY,
    PERMISSION_GLOBAL,
    PERMISSION_PERMISSIONS,
    PERMISSION_PING,
    PERMISSION_REPORTS,
    PERMISSION_TEMPLATES,
    PERMISSION_TICKETS,
    PermissionService,
)
from services.config_service import (
    CONFIG_FINE_CHANNEL,
    CONFIG_FINE_RESOLVER_ROLE,
    CONFIG_FINE_ROLE,
    CONFIG_FINE_TICKET_CATEGORY,
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
FINE_PROOF_DIR = os.path.join(DATA_DIR, "fine_proofs")
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
    (PERMISSION_TICKETS, "Tickets", "Ver y gestionar la seccion completa de tickets del dashboard."),
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
TICKET_CHANNEL_PERMISSION_OPTIONS = [
    ("view_channel", "Ver canal"),
    ("send_messages", "Enviar mensajes"),
    ("read_message_history", "Leer historial"),
    ("attach_files", "Adjuntar archivos"),
    ("embed_links", "Insertar enlaces"),
    ("add_reactions", "Agregar reacciones"),
    ("use_external_emojis", "Usar emojis externos"),
    ("use_external_stickers", "Usar stickers externos"),
    ("mention_everyone", "Mencionar everyone/here"),
    ("manage_messages", "Gestionar mensajes"),
    ("manage_channels", "Gestionar canal"),
    ("manage_threads", "Gestionar hilos"),
    ("create_public_threads", "Crear hilos publicos"),
    ("create_private_threads", "Crear hilos privados"),
    ("send_messages_in_threads", "Enviar en hilos"),
    ("use_application_commands", "Usar comandos"),
]
TICKET_CHANNEL_PERMISSION_KEYS = {
    key
    for key, _ in TICKET_CHANNEL_PERMISSION_OPTIONS
}
DISCORD_API_BASE = "https://discord.com/api/v10"
ALBION_API_BASE = "https://gameinfo.albiononline.com/api/gameinfo"
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
MEMBER_ROLES_CACHE = {}
MEMBER_NAME_CACHE = {}
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


def remember_oauth_state(state, remember_device=False, next_path="/dashboard"):
    with OAUTH_STATES_LOCK:
        OAUTH_STATES[state] = {
            "expires_at": time.time() + 300,
            "remember_device": bool(remember_device),
            "next_path": safe_dashboard_next(next_path),
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


def create_session(user, admin_guilds, guilds=None, remember_device=False):
    session_id = secrets.token_urlsafe(32)
    ttl = REMEMBER_SESSION_TTL_SECONDS if remember_device else SESSION_TTL_SECONDS
    with SESSIONS_LOCK:
        SESSIONS[session_id] = {
            "user": user,
            "admin_guilds": admin_guilds,
            "guilds": guilds or admin_guilds,
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


def guilds_from_discord(guilds):
    return [
        {
            "id": str(guild.get("id")),
            "name": str(guild.get("name") or f"Servidor {guild.get('id')}"),
        }
        for guild in guilds
        if guild.get("id")
    ]


def safe_dashboard_next(value):
    value = str(value or "").strip()
    if value.startswith("/dashboard") and not value.startswith("//"):
        return value
    return "/dashboard"


def get_active_avalonian_state(guild_id, caller_id, numero_ava):
    data = read_json_file(ACTIVE_AVALONIAN_FILE, {})
    state = (
        data.get(str(guild_id), {})
        .get(str(caller_id), {})
        .get(str(numero_ava))
    )
    return dict(state) if isinstance(state, dict) else None


def get_active_report_calculators_for_user(guild_id, caller_id):
    data = read_json_file(ACTIVE_AVALONIAN_FILE, {})
    caller_states = data.get(str(guild_id), {}).get(str(caller_id), {})
    if not isinstance(caller_states, dict):
        return []

    calculators = []
    for numero_ava, state in caller_states.items():
        if not isinstance(state, dict):
            continue
        if not state.get("finalized") or state.get("cancelled"):
            continue
        if state.get("report_sent") and not state.get("report_rejected"):
            continue
        calculators.append(
            {
                "numero_ava": str(state.get("numero_ava") or numero_ava),
                "title": str(state.get("title") or f"Ava {numero_ava}"),
                "caller_name": str(state.get("caller_name") or ""),
                "report_sent": bool(state.get("report_sent")),
                "report_rejected": bool(state.get("report_rejected")),
            }
        )
    calculators.sort(key=lambda item: int(item.get("numero_ava", 0) or 0), reverse=True)
    return calculators


def serialize_report_calculator_state(state):
    slots = state.get("slots") if isinstance(state.get("slots"), dict) else {}
    participants = []
    guild_id = str(state.get("guild_id") or "")
    for index, (slot_key, user_id) in enumerate(slots.items(), start=1):
        if not user_id:
            continue
        label = str(slot_key).split("#", 1)[0]
        display_name = get_discord_member_display_name(guild_id, user_id)
        participants.append({
            "index": index,
            "slot": label,
            "user_id": str(user_id),
            "display_name": display_name or f"Usuario {user_id}",
        })
    return {
        "guild_id": guild_id,
        "caller_id": str(state.get("caller_id") or ""),
        "numero_ava": str(state.get("numero_ava") or ""),
        "title": str(state.get("title") or f"Ava {state.get('numero_ava', '')}"),
        "caller_name": str(state.get("caller_name") or ""),
        "finalized": bool(state.get("finalized")),
        "cancelled": bool(state.get("cancelled")),
        "report_sent": bool(state.get("report_sent")),
        "participants": participants,
    }


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


def get_discord_member_role_ids(guild_id, user_id):
    guild_id = str(guild_id or "")
    user_id = str(user_id or "")
    if not guild_id or not user_id or not BOT_TOKEN:
        return []

    cache_key = (guild_id, user_id)
    cached = MEMBER_ROLES_CACHE.get(cache_key)
    now = time.time()
    if cached and cached.get("expires_at", 0) > now:
        return list(cached.get("roles", []))

    try:
        member = discord_json_request(
            f"/guilds/{guild_id}/members/{user_id}",
            token=BOT_TOKEN,
            auth_scheme="Bot",
        )
        roles = [str(role_id) for role_id in member.get("roles", [])]
    except Exception:
        roles = []

    MEMBER_ROLES_CACHE[cache_key] = {
        "roles": roles,
        "expires_at": now + 60,
    }
    return roles


def get_fine_config_payload(guild_id):
    service = ConfigService()
    config = service.get_fine_config(guild_id)
    return {
        "channel_id": str(config.get("channel_id") or ""),
        "blocked_role_id": str(config.get("blocked_role_id") or ""),
        "resolver_role_id": str(config.get("resolver_role_id") or ""),
        "ticket_category_id": str(config.get("ticket_category_id") or ""),
    }


def save_fine_config(guild_id, payload):
    service = ConfigService()
    service.set_channel(guild_id, CONFIG_FINE_CHANNEL, str(payload.get("channel_id") or ""))
    service.set_role(guild_id, CONFIG_FINE_ROLE, str(payload.get("blocked_role_id") or ""))
    service.set_role(guild_id, CONFIG_FINE_RESOLVER_ROLE, str(payload.get("resolver_role_id") or ""))
    service.set_channel(guild_id, CONFIG_FINE_TICKET_CATEGORY, str(payload.get("ticket_category_id") or ""))
    return get_fine_config_payload(guild_id)


def get_guild_fines_payload(guild_id):
    fines = FineService().get_guild_fines(guild_id)
    return {
        "fines": [
            {
                "id": int(fine.get("id") or 0),
                "report_ava": str(fine.get("report_ava") or ""),
                "fined_user_id": str(fine.get("fined_user_id") or ""),
                "fined_user_name": str(fine.get("fined_user_name") or fine.get("fined_user_id") or ""),
                "amount": int(fine.get("amount") or 0),
                "reason": str(fine.get("reason") or ""),
                "status": str(fine.get("status") or "open"),
                "created_by_name": str(fine.get("created_by_name") or ""),
                "paid_by_name": str(fine.get("paid_by_name") or ""),
                "created_at": str(fine.get("created_at") or ""),
                "paid_at": str(fine.get("paid_at") or ""),
                "ticket_channel_id": str(fine.get("ticket_channel_id") or ""),
            }
            for fine in fines
        ]
    }


def store_embedded_image(data_url, *, prefix):
    text = str(data_url or "")
    if not text.startswith("data:") or ";base64," not in text:
        return "", ""

    header, encoded = text.split(",", 1)
    mime_type = header[5:].split(";", 1)[0].lower()
    extension = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(mime_type, "")
    if not extension:
        return "", ""

    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception:
        return "", ""
    if not raw:
        return "", ""

    os.makedirs(FINE_PROOF_DIR, exist_ok=True)
    file_name = f"{prefix}{extension}"
    path = os.path.join(FINE_PROOF_DIR, file_name)
    with open(path, "wb") as f:
        f.write(raw)
    return path, file_name


def get_discord_member_display_name(guild_id, user_id):
    guild_id = str(guild_id or "")
    user_id = str(user_id or "")
    if not guild_id or not user_id or not BOT_TOKEN:
        return ""

    cache_key = (guild_id, user_id)
    cached = MEMBER_NAME_CACHE.get(cache_key)
    now = time.time()
    if cached and cached.get("expires_at", 0) > now:
        return str(cached.get("name") or "")

    try:
        member = discord_json_request(
            f"/guilds/{guild_id}/members/{user_id}",
            token=BOT_TOKEN,
            auth_scheme="Bot",
        )
        user = member.get("user", {}) if isinstance(member, dict) else {}
        display_name = str(
            member.get("nick")
            or user.get("global_name")
            or user.get("username")
            or user_id
        )
    except Exception:
        display_name = str(user_id)

    MEMBER_NAME_CACHE[cache_key] = {
        "name": display_name,
        "expires_at": now + 60,
    }
    return display_name


def role_ids_have_permission(guild_id, role_ids, permission):
    role_permissions = PermissionService().get_role_permissions(guild_id)
    for role_id in role_ids:
        permissions = role_permissions.get(str(role_id), [])
        if PERMISSION_GLOBAL in permissions or permission in permissions:
            return True
    return False


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


def albion_json_request(path, *, params=None):
    query = f"?{urlencode(params)}" if params else ""
    request = Request(
        f"{ALBION_API_BASE}/{path.lstrip('/')}{query}",
        headers={
            "Accept": "application/json",
            "User-Agent": "AvalonBot/1.0 Albion dashboard",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Albion Online respondio {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"No pude conectar con Albion Online: {exc.reason}") from exc


def find_albion_guild_exact(guild_name):
    clean_name = str(guild_name or "").strip()
    if not clean_name:
        return None
    data = albion_json_request("search", params={"q": clean_name})
    guilds = data.get("guilds", []) if isinstance(data, dict) else []
    exact = [
        guild
        for guild in guilds
        if str(guild.get("Name") or "").casefold() == clean_name.casefold()
    ]
    exact.sort(key=lambda guild: str(guild.get("Name") or ""))
    return exact[0] if exact else None


def get_albion_registration_payload(guild_id):
    repository = AlbionRegistrationRepository()
    config = repository.get_config(guild_id)
    if config:
        config["sync_nickname"] = bool(config.get("sync_nickname"))
        config["enabled"] = bool(config.get("enabled"))
    return {
        "region": "America",
        "config": config,
        "registrations": repository.list_registrations(guild_id),
    }


def save_albion_registration_config(guild_id, body):
    albion_guild_name = str(body.get("albion_guild_name") or "").strip()
    role_id = str(body.get("role_id") or "").strip()
    leave_action = str(body.get("leave_action") or "remove_roles").strip()
    log_channel_id = str(body.get("log_channel_id") or "").strip() or None
    if not albion_guild_name:
        raise ValueError("Escribe el nombre exacto del gremio de Albion.")
    if not role_id.isdigit():
        raise ValueError("Selecciona el rol que recibiran los miembros registrados.")
    if leave_action not in {"remove_roles", "kick"}:
        raise ValueError("La accion al abandonar el gremio no es valida.")

    albion_guild = find_albion_guild_exact(albion_guild_name)
    if not albion_guild:
        raise ValueError(
            f"No encontre el gremio '{albion_guild_name}' en la region America."
        )

    repository = AlbionRegistrationRepository()
    repository.save_config(
        guild_id,
        albion_guild_id=albion_guild["Id"],
        albion_guild_name=albion_guild["Name"],
        role_id=role_id,
        leave_action=leave_action,
        sync_nickname=bool(body.get("sync_nickname")),
        log_channel_id=log_channel_id,
    )
    return get_albion_registration_payload(guild_id)


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


def ticket_records_summary(records):
    today = datetime.now(ARGENTINA_TZ).strftime("%d/%m/%Y")
    summary = {
        "open": 0,
        "claimed": 0,
        "closed_today": 0,
        "transcribed": 0,
        "deleted": 0,
        "total": len(records),
        "updated_at": datetime.now(ARGENTINA_TZ).strftime("%d/%m/%Y | %H:%M:%S"),
    }
    for record in records:
        status = str(record.get("status") or "open").lower()
        if status == "open":
            summary["open"] += 1
        if record.get("claimed_by_id"):
            summary["claimed"] += 1
        if status == "deleted":
            summary["deleted"] += 1
        if record.get("transcribed_at") or record.get("transcript"):
            summary["transcribed"] += 1
        if str(record.get("closed_at") or "").startswith(today):
            summary["closed_today"] += 1
    return summary


def discord_timestamp_to_display(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(ARGENTINA_TZ).strftime("%d/%m/%Y | %H:%M")
    except Exception:
        return str(value or "")


def serialize_discord_message(message):
    author = message.get("author") if isinstance(message.get("author"), dict) else {}
    attachments = message.get("attachments") if isinstance(message.get("attachments"), list) else []
    embeds = message.get("embeds") if isinstance(message.get("embeds"), list) else []
    avatar = ""
    if author.get("id") and author.get("avatar"):
        avatar = f"https://cdn.discordapp.com/avatars/{author.get('id')}/{author.get('avatar')}.png?size=1024"

    return {
        "id": str(message.get("id") or ""),
        "author": f"{author.get('username', 'Usuario')}#{author.get('discriminator', '0')}",
        "author_name": str(author.get("global_name") or author.get("username") or "Usuario"),
        "author_id": str(author.get("id") or ""),
        "author_avatar": avatar,
        "author_bot": bool(author.get("bot")),
        "content": str(message.get("content") or ""),
        "created_at": discord_timestamp_to_display(message.get("timestamp")),
        "attachments": [
            {
                "id": str(item.get("id") or ""),
                "filename": str(item.get("filename") or "Archivo adjunto"),
                "url": str(item.get("url") or ""),
                "content_type": str(item.get("content_type") or ""),
            }
            for item in attachments
            if isinstance(item, dict)
        ],
        "embeds": embeds,
        "reference": message.get("message_reference") if isinstance(message.get("message_reference"), dict) else None,
    }


def get_ticket_record(guild_id, record_id):
    for record in get_guild_ticket_records(guild_id):
        if str(record.get("channel_id") or record.get("number") or "") == str(record_id):
            return record
    return None


def delete_guild_ticket_record(guild_id, record_id):
    guild_id = str(guild_id)
    record_id = str(record_id)
    removed = {"record": None}

    def mutate(data):
        records = data.get(guild_id, []) if isinstance(data, dict) else []
        remaining = []
        for record in records:
            current_id = str(record.get("channel_id") or record.get("number") or "")
            if current_id == record_id and removed["record"] is None:
                if str(record.get("status") or "open").lower() == "open":
                    remaining.append(record)
                    continue
                removed["record"] = dict(record)
                continue
            remaining.append(record)
        if remaining:
            data[guild_id] = remaining
        else:
            data.pop(guild_id, None)
        return data

    mutate_json_file_safe(TICKET_RECORDS_FILE, {}, mutate)
    record = removed["record"]
    if not record:
        return False

    channel_id = str(record.get("channel_id") or "")
    if channel_id.isdigit() and guild_id.isdigit():
        media_root = os.path.abspath(TICKET_MEDIA_DIR)
        media_folder = os.path.abspath(
            os.path.join(TICKET_MEDIA_DIR, guild_id, channel_id)
        )
        if os.path.commonpath([media_root, media_folder]) == media_root:
            shutil.rmtree(media_folder, ignore_errors=True)
    return True


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
    .page {{ width: min(1380px, 100%); min-height: 100vh; margin: 0 auto; padding: 24px 24px 56px; }}
    .header {{ display: grid; grid-template-columns: 78px minmax(0, 1fr); gap: 16px; align-items: center; margin-bottom: 24px; padding: 16px; border: 1px solid #263449; border-radius: 12px; background: #151f2c; }}
    .logo {{ width: 78px; height: 78px; object-fit: cover; background: #0b1220; }}
    .header h1 {{ margin: 0; font-size: clamp(24px, 3vw, 34px); line-height: 1.08; font-weight: 700; }}
    .header a {{ color: #8ab4ff; text-decoration: none; font-size: 13px; display: inline-block; margin-top: 8px; }}
    .messages {{ display: grid; gap: 6px; }}
    .message {{ display: grid; grid-template-columns: 56px minmax(0, 1fr); gap: 14px; align-items: start; padding: 12px 10px; border-radius: 10px; }}
    .message:hover {{ background: rgba(255, 255, 255, .035); }}
    .avatar {{ width: 44px; height: 44px; border-radius: 50%; overflow: hidden; display: inline-flex; align-items: center; justify-content: center; background: #263449; color: #fff; font-weight: 700; margin-left: 4px; }}
    .avatar img {{ width: 100%; height: 100%; object-fit: cover; }}
    .message-body {{ min-width: 0; }}
    .message-meta {{ display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; margin-bottom: 2px; }}
    .author {{ font-weight: 700; color: #fff; }}
    .time {{ color: #667386; font-size: 13px; }}
    .bot-badge {{ background: #5865f2; color: #fff; border-radius: 3px; padding: 1px 4px; font-size: 10px; font-weight: 700; }}
    .message-content {{ color: #fff; line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere; }}
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
    @media (max-width: 680px) {{
      .page {{ padding: 14px 12px 38px; }}
      .header {{ grid-template-columns: 1fr; }}
      .message {{ grid-template-columns: 44px minmax(0, 1fr); padding: 10px 4px; }}
      .avatar {{ width: 36px; height: 36px; margin-left: 0; }}
    }}
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
        "ticket_open_content": str(panel.get("ticket_open_content") or "")[:2000],
        "ticket_open_title": str(panel.get("ticket_open_title") or "")[:256],
        "ticket_open_description": str(panel.get("ticket_open_description") or "")[:4000],
        "ticket_open_color": str(panel.get("ticket_open_color") or "")[:20],
        "ticket_open_footer": str(panel.get("ticket_open_footer") or "")[:2048],
        "ticket_open_image_url": str(panel.get("ticket_open_image_url") or "")[:500],
        "ticket_open_thumbnail_url": str(panel.get("ticket_open_thumbnail_url") or "")[:500],
        "options": normalized_options,
        "permissions": {
            "ticket_role_permissions": normalize_ticket_role_permissions(permissions),
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


def normalize_ticket_role_permissions(permissions):
    entries = permissions.get("ticket_role_permissions")
    normalized = []
    seen = set()
    if isinstance(entries, list):
        for entry in entries[:20]:
            if not isinstance(entry, dict):
                continue
            role_id = str(entry.get("role_id") or "").strip()
            if not role_id.isdigit() or role_id in seen:
                continue
            values = entry.get("permissions")
            if not isinstance(values, list):
                values = []
            keys = [
                str(value)
                for value in values
                if str(value) in TICKET_CHANNEL_PERMISSION_KEYS
            ]
            if keys:
                normalized.append({"role_id": role_id, "permissions": keys})
                seen.add(role_id)

    if normalized:
        return normalized

    legacy = {}
    for role_id in normalize_id_list(permissions.get("view_roles")):
        legacy[str(role_id)] = ["view_channel", "read_message_history"]
    for role_id in normalize_id_list(permissions.get("send_roles")):
        legacy[str(role_id)] = [
            "view_channel",
            "send_messages",
            "read_message_history",
            "attach_files",
            "embed_links",
        ]
    return [
        {"role_id": role_id, "permissions": values}
        for role_id, values in legacy.items()
        if role_id.isdigit()
    ][:20]


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
    fines = get_guild_fines_payload(selected_guild_id).get("fines", []) if selected_guild_id else []
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
        "fines": fines,
        "totals": totals,
        "updatedAt": argentina_now_display(),
        "viewer": viewer or {},
        "access": {},
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
    [hidden] { display: none !important; }
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
      grid-template-columns: 248px minmax(0, 1fr);
      gap: 16px;
      align-items: start;
      transition: grid-template-columns .2s ease;
    }

    .app-shell.sidebar-collapsed {
      grid-template-columns: 76px minmax(0, 1fr);
    }

    .sections {
      position: sticky;
      top: 86px;
      min-width: 0;
      overflow: hidden;
      background:
        linear-gradient(155deg, rgba(37, 99, 235, .08), transparent 38%),
        var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      box-shadow: var(--shadow);
      padding: 10px;
      transition: padding .2s ease, border-radius .2s ease;
    }

    body.theme-dark .sections {
      background:
        linear-gradient(155deg, rgba(56, 189, 248, .10), transparent 38%),
        var(--panel);
    }

    .sidebar-head {
      min-height: 50px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 8px;
      padding: 5px 4px 10px 8px;
      border-bottom: 1px solid var(--line);
    }

    .sidebar-heading {
      min-width: 0;
      display: grid;
      gap: 2px;
    }

    .sidebar-heading strong {
      font-size: 13px;
      line-height: 1.2;
    }

    .sidebar-heading span {
      color: var(--muted);
      font-size: 11px;
      line-height: 1.2;
    }

    .menu-button {
      width: 36px;
      min-width: 36px;
      height: 36px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-color: var(--line);
      background: var(--control-bg);
      color: var(--muted);
      padding: 0;
      transition: border-color .16s ease, color .16s ease, background .16s ease, transform .16s ease;
    }

    .menu-button:hover {
      border-color: var(--brand);
      background: var(--brand-soft);
      color: var(--brand);
    }

    .menu-button svg {
      width: 18px;
      height: 18px;
      transition: transform .2s ease;
    }

    .sidebar-collapsed .menu-button svg {
      transform: rotate(180deg);
    }

    .section-label {
      color: var(--muted);
      font-size: 10px;
      font-weight: 800;
      letter-spacing: .08em;
      text-transform: uppercase;
      margin: 12px 10px 7px;
    }

    .section-list {
      display: grid;
      gap: 5px;
    }

    .section-button {
      width: 100%;
      min-height: 48px;
      position: relative;
      display: flex;
      align-items: center;
      gap: 11px;
      justify-content: flex-start;
      text-align: left;
      border-color: transparent;
      background: transparent;
      color: var(--ink);
      font-weight: 750;
      padding: 6px 9px;
      transition: color .16s ease, background .16s ease, border-color .16s ease, transform .16s ease;
    }

    .section-button::before {
      content: "";
      width: 3px;
      height: 22px;
      position: absolute;
      left: -1px;
      top: 50%;
      border-radius: 0 999px 999px 0;
      background: var(--brand);
      opacity: 0;
      transform: translateY(-50%) scaleY(.4);
      transition: opacity .16s ease, transform .16s ease;
    }

    .section-button:hover {
      border-color: rgba(37, 99, 235, .16);
      background: var(--row-hover);
      color: var(--active-ink);
      transform: translateX(2px);
    }

    .section-button.active {
      border-color: rgba(37, 99, 235, .24);
      background: linear-gradient(90deg, var(--brand-soft), rgba(37, 99, 235, .04));
      color: var(--active-ink);
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .22);
    }

    .section-button.active::before {
      opacity: 1;
      transform: translateY(-50%) scaleY(1);
    }

    .section-icon {
      width: 32px;
      min-width: 32px;
      height: 32px;
      display: grid;
      place-items: center;
      border: 1px solid var(--line);
      border-radius: 9px;
      background: var(--control-bg);
      color: var(--muted);
      transition: border-color .16s ease, background .16s ease, color .16s ease, box-shadow .16s ease;
    }

    .section-icon svg {
      width: 17px;
      height: 17px;
    }

    .section-button:hover .section-icon {
      border-color: rgba(37, 99, 235, .35);
      color: var(--brand);
    }

    .section-button.active .section-icon {
      border-color: var(--brand);
      background: var(--brand);
      color: #fff;
      box-shadow: 0 7px 16px rgba(37, 99, 235, .22);
    }

    .section-copy {
      min-width: 0;
      display: grid;
      gap: 1px;
    }

    .section-text {
      line-height: 1.2;
    }

    .section-hint {
      color: var(--muted);
      font-size: 10px;
      font-weight: 500;
      line-height: 1.2;
    }

    .sidebar-collapsed .sections {
      padding: 9px;
    }

    .sidebar-collapsed .sidebar-head {
      justify-content: center;
      padding: 5px 0 10px;
    }

    .sidebar-collapsed .sidebar-heading,
    .sidebar-collapsed .section-label,
    .sidebar-collapsed .section-copy {
      display: none;
    }

    .sidebar-collapsed .section-list {
      gap: 7px;
    }

    .sidebar-collapsed .section-button {
      justify-content: center;
      min-height: 48px;
      padding: 6px;
    }

    .sidebar-collapsed .section-button:hover {
      transform: translateX(0) scale(1.03);
    }

    .sidebar-collapsed .section-icon {
      width: 34px;
      min-width: 34px;
      height: 34px;
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
      justify-content: center;
      gap: 7px;
      font-weight: 800;
      text-decoration: none;
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

    .field[hidden] {
      display: none;
    }

    .field.full {
      grid-column: 1 / -1;
    }

    .report-participant-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(196px, 1fr));
      gap: 10px;
    }

    .report-participant-card {
      display: grid;
      gap: 8px;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: linear-gradient(180deg, color-mix(in srgb, var(--panel) 90%, transparent), var(--panel));
      box-shadow: 0 8px 20px rgba(15, 23, 42, .08);
      min-width: 0;
      transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
    }

    .report-participant-card:hover {
      transform: translateY(-1px);
      border-color: color-mix(in srgb, var(--brand) 36%, var(--line));
      box-shadow: 0 12px 28px rgba(15, 23, 42, .12);
    }

    .report-participant-card strong,
    .report-participant-card span {
      overflow-wrap: anywhere;
    }

    .report-participant-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }

    .report-participant-card strong {
      font-size: 16px;
      line-height: 1.25;
    }

    .report-participant-name {
      color: var(--ink);
      font-size: 14px;
      font-weight: 700;
      line-height: 1.35;
    }

    .report-participant-role {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 24px;
      border-radius: 999px;
      border: 1px solid color-mix(in srgb, var(--brand) 34%, var(--line));
      background: color-mix(in srgb, var(--brand) 10%, var(--control-bg));
      color: var(--active-ink);
      padding: 0 10px;
      font-size: 11px;
      font-weight: 900;
      text-transform: uppercase;
      letter-spacing: .06em;
      white-space: nowrap;
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

    .ticket-permission-list {
      display: grid;
      gap: 8px;
    }

    .ticket-permission-card {
      display: grid;
      gap: 6px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: var(--panel);
      padding: 8px;
    }

    .ticket-permission-card-head {
      display: grid;
      grid-template-columns: minmax(180px, 1fr) auto;
      gap: 8px;
      align-items: center;
    }

    .ticket-permission-actions {
      display: flex;
      gap: 6px;
      align-items: center;
      justify-content: flex-end;
      white-space: nowrap;
    }

    .ticket-permission-count {
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
    }

    .ticket-permission-actions .action-button {
      min-height: 34px;
      padding: 6px 10px;
    }

    .ticket-permission-details {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--control-bg);
      padding: 6px 9px;
    }

    .ticket-permission-details summary {
      cursor: pointer;
      color: var(--brand);
      font-size: 12px;
      font-weight: 900;
      text-transform: uppercase;
      letter-spacing: .04em;
    }

    .ticket-permission-options {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 6px;
      margin-top: 8px;
    }

    .ticket-permission-options .permission-pill {
      min-height: 28px;
      padding: 3px 8px;
      font-size: 11px;
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

    .report-calculator-shell {
      display: grid;
      gap: 18px;
    }

    .report-calculator-toolbar {
      align-items: flex-end;
      padding-bottom: 8px;
      border-bottom: 1px solid color-mix(in srgb, var(--line) 84%, transparent);
    }

    .report-calculator-heading {
      display: grid;
      gap: 4px;
      max-width: 760px;
    }

    .report-calculator-heading h2 {
      margin: 0;
      font-size: 28px;
      letter-spacing: -.03em;
    }

    .report-calculator-heading p {
      margin: 0;
      font-size: 14px;
    }

    .report-calculator-picker {
      min-width: min(320px, 100%);
      display: grid;
      gap: 6px;
    }

    .report-calculator-picker select {
      min-width: 0;
    }

    .report-calculator-summary {
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 12px;
    }

    .report-calculator-summary .ticket-stat {
      border-radius: 12px;
      padding: 14px 16px;
      background: linear-gradient(180deg, color-mix(in srgb, var(--panel) 88%, transparent), var(--panel));
      box-shadow: 0 10px 24px rgba(15, 23, 42, .08);
    }

    .report-calculator-summary .ticket-stat span {
      margin-bottom: 6px;
      font-size: 11px;
      letter-spacing: .08em;
      text-transform: uppercase;
    }

    .report-calculator-summary .ticket-stat strong {
      font-size: 26px;
      line-height: 1.1;
    }

    .report-calculator-participants {
      padding: 14px;
      border-radius: 12px;
      background: color-mix(in srgb, var(--control-bg) 88%, transparent);
    }

    .report-calculator-workspace {
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(280px, .9fr);
      gap: 16px;
      align-items: start;
      min-width: 0;
    }

    .report-calculator-form {
      gap: 14px;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: color-mix(in srgb, var(--control-bg) 92%, transparent);
      box-shadow: 0 10px 24px rgba(15, 23, 42, .08);
    }

    .report-calculator-form .editor-section-header {
      padding-bottom: 10px;
      border-bottom: 1px solid color-mix(in srgb, var(--line) 82%, transparent);
    }

    .report-calculator-form .form-grid {
      gap: 12px;
    }

    .report-calculator-form .field {
      display: grid;
      gap: 6px;
      min-width: 0;
    }

    .report-fines-section .editor-section-header {
      align-items: flex-start;
      flex-wrap: wrap;
    }

    .report-fines-section .editor-section-header > div {
      min-width: 0;
    }

    .report-fine-row {
      display: grid;
      grid-template-columns: minmax(170px, 1.15fr) minmax(120px, .72fr) minmax(180px, 1fr);
      gap: 12px;
      align-items: start;
      padding: 12px;
      border: 1px solid color-mix(in srgb, var(--line) 86%, transparent);
      border-radius: 12px;
      background: color-mix(in srgb, var(--panel) 88%, var(--control-bg));
      min-width: 0;
    }

    .report-fine-row .field {
      gap: 5px;
      min-width: 0;
    }

    .report-fine-user-field,
    .report-fine-proof-field {
      grid-column: span 2;
    }

    .report-fine-remove {
      align-self: end;
      min-height: 42px;
    }

    .report-fine-proof-name {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
      overflow-wrap: anywhere;
    }

    .report-calculator-form input,
    .report-calculator-form select,
    .report-calculator-form textarea {
      border-radius: 10px;
      background: color-mix(in srgb, var(--panel) 76%, var(--control-bg));
    }

    .report-calculator-form textarea {
      min-height: 108px;
    }

    .report-calculator-actions {
      padding-top: 6px;
      border-top: 1px solid color-mix(in srgb, var(--line) 82%, transparent);
    }

    .report-calculator-aside {
      display: grid;
      gap: 12px;
      align-content: start;
      position: sticky;
      top: 86px;
    }

    .report-calculator-breakdown {
      border-radius: 12px;
      padding: 16px;
      background: linear-gradient(180deg, color-mix(in srgb, var(--brand-soft) 26%, var(--control-bg)), color-mix(in srgb, var(--control-bg) 96%, transparent));
      box-shadow: 0 12px 28px rgba(15, 23, 42, .08);
    }

    .report-calculator-panel-head {
      display: grid;
      gap: 4px;
      margin-bottom: 12px;
    }

    .report-calculator-panel-head strong {
      margin: 0;
    }

    .report-calculator-panel-head span {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.4;
    }

    .report-breakdown-list {
      display: grid;
      gap: 9px;
    }

    .report-breakdown-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 11px 12px;
      border: 1px solid color-mix(in srgb, var(--line) 88%, transparent);
      border-radius: 10px;
      background: color-mix(in srgb, var(--panel) 78%, var(--control-bg));
    }

    .report-breakdown-item.negative {
      border-color: color-mix(in srgb, var(--red) 24%, var(--line));
      background: color-mix(in srgb, var(--remove-bg) 56%, var(--panel));
    }

    .report-breakdown-item.accent {
      border-color: color-mix(in srgb, var(--brand) 34%, var(--line));
      background: color-mix(in srgb, var(--brand-soft) 38%, var(--panel));
    }

    .report-breakdown-label {
      color: var(--muted);
      font-size: 11px;
      font-weight: 900;
      text-transform: uppercase;
      letter-spacing: .08em;
    }

    .report-breakdown-value {
      color: var(--ink);
      font-size: 15px;
      line-height: 1.2;
      text-align: right;
    }

    .report-breakdown-empty {
      border: 1px dashed var(--line);
      border-radius: 10px;
      padding: 14px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
      text-align: center;
      background: color-mix(in srgb, var(--panel) 72%, transparent);
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
      gap: 14px;
      flex-wrap: wrap;
      align-items: center;
      margin-bottom: 8px;
    }

    .records-toolbar .ticket-actions {
      align-items: center;
    }

    .records-toolbar input[type="search"] {
      min-width: min(420px, 100%);
      min-height: 42px;
    }

    .records-toolbar.compact {
      display: grid;
      gap: 8px;
    }

    .records-toolbar.compact button,
    .records-toolbar.compact input {
      width: 100%;
    }

    .ticket-records-side,
    .ticket-records-panel {
      display: grid;
      gap: 8px;
      margin-top: 12px;
      border-top: 1px solid var(--line);
      padding-top: 12px;
    }

    .ticket-records-panel {
      gap: 14px;
      margin-top: 0;
      border: 1px solid var(--line);
      border-radius: 12px;
      background:
        linear-gradient(145deg, color-mix(in srgb, var(--brand) 8%, transparent), transparent 42%),
        var(--control-bg);
      padding: 16px;
    }

    .ticket-records-panel .section-label {
      margin: 0;
    }

    .ticket-records-side .ticket-list,
    .ticket-records-panel .ticket-list {
      max-height: 560px;
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

    .ticket-records-panel .ticket-list {
      display: grid;
      gap: 12px;
    }

    .ticket-records-panel .ticket-card {
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 18px;
      align-items: start;
      padding: 16px;
      border-radius: 12px;
    }

    .ticket-records-panel .ticket-card h3 {
      font-size: 17px;
      line-height: 1.2;
    }

    .ticket-record-title {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
      margin-bottom: 10px;
    }

    .ticket-record-title h3 {
      margin: 0;
    }

    .ticket-record-meta {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 8px;
    }

    .ticket-record-meta span {
      display: grid;
      gap: 2px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--control-bg);
      padding: 8px 10px;
      color: var(--ink);
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    .ticket-record-meta b {
      color: var(--muted);
      font-size: 10px;
      letter-spacing: .06em;
      text-transform: uppercase;
    }

    .ticket-records-panel .ticket-card-actions {
      min-width: 210px;
      align-self: stretch;
      align-items: stretch;
      flex-direction: column;
    }

    .ticket-records-panel .ticket-card-actions button {
      min-height: 42px;
    }

    .ticket-live-viewer {
      display: grid;
      gap: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--control-bg);
      padding: 12px;
      min-width: 0;
    }

    .ticket-live-viewer[hidden] {
      display: none;
    }

    .live-chat-box {
      display: grid;
      align-content: start;
      gap: 0;
      min-height: 620px;
      max-height: 72vh;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }

    .live-chat-form {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: end;
    }

    .live-chat-form textarea {
      min-height: 58px;
      max-height: 160px;
    }

    .live-chat-form button {
      height: 58px;
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

    .live-status {
      font-size: 12px;
      line-height: 1.35;
    }

    .live-ticket.open {
      border-left: 4px solid var(--green);
    }

    .live-ticket.closed {
      border-left: 4px solid var(--gold);
    }

    .live-ticket.deleted {
      border-left: 4px solid var(--red);
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

    .loot-dashboard {
      display: grid;
      gap: 14px;
    }

    .loot-dropzone {
      min-height: 220px;
      display: grid;
      place-items: center;
      gap: 10px;
      padding: 28px;
      border: 2px dashed var(--line);
      border-radius: 10px;
      background: linear-gradient(135deg, var(--brand-soft), var(--teal-soft));
      text-align: center;
      cursor: pointer;
      transition: border-color .18s ease, transform .18s ease, background .18s ease;
    }

    .loot-dropzone:hover,
    .loot-dropzone.dragging {
      border-color: var(--brand);
      transform: translateY(-1px);
    }

    .loot-dropzone input {
      position: absolute;
      width: 1px;
      height: 1px;
      opacity: 0;
      pointer-events: none;
    }

    .loot-dropzone-icon {
      width: 52px;
      height: 52px;
      display: grid;
      place-items: center;
      border-radius: 50%;
      background: var(--panel);
      color: var(--brand);
      font-size: 26px;
      font-weight: 800;
      box-shadow: var(--shadow);
    }

    .loot-dropzone strong {
      font-size: 18px;
    }

    .loot-dropzone span {
      color: var(--muted);
      font-size: 13px;
    }

    .loot-file-summary {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }

    .loot-file-summary strong,
    .loot-file-summary span {
      display: block;
    }

    .loot-file-summary span {
      margin-top: 3px;
      color: var(--muted);
      font-size: 12px;
    }

    .loot-controls {
      display: grid;
      grid-template-columns: minmax(0, 1.5fr) minmax(180px, .7fr) minmax(180px, .7fr);
      gap: 10px;
    }

    .loot-control-card {
      display: grid;
      align-content: start;
      gap: 8px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }

    .loot-control-card > strong {
      font-size: 13px;
    }

    .loot-tier-buttons {
      display: flex;
      gap: 7px;
      flex-wrap: wrap;
    }

    .loot-tier-button {
      min-width: 48px;
      font-weight: 800;
    }

    .loot-tier-button.all {
      border-color: var(--violet);
      background: var(--violet-soft);
      color: var(--violet);
    }

    .loot-tier-button.none {
      border-color: var(--red);
      background: var(--remove-bg);
      color: var(--red);
    }

    .loot-tier-button.partial {
      border-color: var(--gold);
      background: var(--silver-bg);
      color: var(--gold);
    }

    .loot-range {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
    }

    .loot-range input {
      width: 100%;
      padding: 0;
    }

    .loot-switch-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      color: var(--muted);
      font-size: 12px;
    }

    .loot-switch {
      min-width: 72px;
      font-weight: 800;
    }

    .loot-switch.active {
      border-color: var(--brand);
      background: var(--brand);
      color: #fff;
    }

    .loot-players {
      display: grid;
      gap: 12px;
    }

    .loot-player-card {
      display: grid;
      gap: 12px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
    }

    .loot-player-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    .loot-player-header h3 {
      margin: 0;
      font-size: 18px;
    }

    .loot-player-total {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      color: var(--gold);
      font-weight: 800;
    }

    .loot-tier-group {
      display: grid;
      gap: 8px;
    }

    .loot-tier-group h4 {
      margin: 0;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
    }

    .loot-grid {
      display: flex;
      flex-wrap: wrap;
      gap: 9px;
    }

    .loot-item-wrap {
      position: relative;
    }

    .loot-item {
      width: calc(var(--loot-icon-size, 60px) + 12px);
      height: calc(var(--loot-icon-size, 60px) + 12px);
      position: relative;
      display: grid;
      place-items: center;
      padding: 5px;
      border-radius: 8px;
      background: var(--control-bg);
      overflow: hidden;
    }

    .loot-item img {
      width: var(--loot-icon-size, 60px);
      height: var(--loot-icon-size, 60px);
      object-fit: contain;
    }

    .loot-item.excluded {
      opacity: .32;
      filter: grayscale(1);
      border-color: var(--red);
    }

    .loot-item.no-price {
      border-style: dashed;
    }

    .loot-quantity {
      position: absolute;
      right: 4px;
      bottom: 3px;
      min-width: 22px;
      padding: 1px 5px;
      border-radius: 999px;
      background: rgba(8, 15, 28, .88);
      color: #fff;
      font-size: 12px;
      font-weight: 800;
      text-align: center;
    }

    .loot-info {
      width: 22px;
      height: 22px;
      min-width: 22px;
      position: absolute;
      top: -6px;
      right: -6px;
      z-index: 1;
      display: grid;
      place-items: center;
      padding: 0;
      border-radius: 50%;
      border-color: var(--brand);
      background: var(--brand);
      color: #fff;
      font-size: 11px;
      font-weight: 900;
    }

    .loot-error {
      padding: 12px;
      border: 1px solid var(--remove-line);
      border-radius: 8px;
      background: var(--remove-bg);
      color: var(--red);
    }

    .loot-modal {
      position: fixed;
      inset: 0;
      z-index: 20;
      display: grid;
      place-items: center;
      padding: 20px;
      background: rgba(6, 12, 24, .72);
    }

    .loot-modal[hidden] {
      display: none;
    }

    .loot-modal-panel {
      width: min(520px, 100%);
      position: relative;
      display: grid;
      gap: 14px;
      padding: 20px;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: var(--panel);
      box-shadow: 0 24px 70px rgba(0, 0, 0, .36);
    }

    .loot-modal-close {
      width: 34px;
      min-width: 34px;
      position: absolute;
      top: 12px;
      right: 12px;
      padding: 0;
      font-size: 20px;
    }

    .loot-modal-hero {
      display: flex;
      align-items: center;
      gap: 14px;
      padding-right: 38px;
    }

    .loot-modal-hero img {
      width: 92px;
      height: 92px;
      object-fit: contain;
    }

    .loot-modal-hero h3,
    .loot-modal-hero p {
      margin: 0;
    }

    .loot-modal-hero p {
      margin-top: 4px;
      color: var(--muted);
    }

    .loot-detail-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }

    .loot-detail {
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: var(--control-bg);
    }

    .loot-detail span,
    .loot-detail strong {
      display: block;
    }

    .loot-detail span {
      margin-bottom: 4px;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
    }

    @media (max-width: 760px) {
      .bar { grid-template-columns: 1fr; }
      .controls, .session { justify-content: stretch; }
      select, input, button { width: 100%; }
      .app-shell, .app-shell.sidebar-collapsed { grid-template-columns: minmax(0, 1fr); }
      .app-shell > * { min-width: 0; }
      .sections {
        position: static;
        padding: 10px;
        border-radius: 12px;
      }
      .sidebar-head {
        min-height: 0;
        margin-bottom: 9px;
        padding: 4px 5px 9px;
      }
      .sidebar-heading,
      .sidebar-collapsed .sidebar-heading {
        display: grid;
      }
      .menu-button { display: none; }
      .section-label { display: none; }
      .section-list,
      .sidebar-collapsed .section-list {
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 7px;
      }
      .section-button,
      .sidebar-collapsed .section-button {
        min-height: 66px;
        flex-direction: column;
        justify-content: center;
        gap: 5px;
        padding: 7px 4px;
        text-align: center;
      }
      .section-button:hover,
      .sidebar-collapsed .section-button:hover {
        transform: translateY(-1px);
      }
      .section-button::before {
        width: 22px;
        height: 3px;
        left: 50%;
        top: auto;
        bottom: -1px;
        border-radius: 999px 999px 0 0;
        transform: translateX(-50%) scaleX(.4);
      }
      .section-button.active::before {
        transform: translateX(-50%) scaleX(1);
      }
      .section-icon,
      .sidebar-collapsed .section-icon {
        width: 30px;
        min-width: 30px;
        height: 30px;
      }
      .section-copy,
      .sidebar-collapsed .section-copy {
        display: grid;
      }
      .section-text {
        font-size: 11px;
      }
      .section-hint { display: none; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .ticket-summary { grid-template-columns: 1fr; }
      .ticket-card { grid-template-columns: 1fr; }
      .ticket-card-actions { justify-content: flex-start; }
      .ticket-records-panel .ticket-card { grid-template-columns: 1fr; }
      .ticket-records-panel .ticket-card-actions {
        min-width: 0;
        justify-content: stretch;
      }
      .ticket-records-panel .ticket-card-actions button { width: 100%; }
      .live-chat-box {
        min-height: 440px;
        max-height: 64vh;
      }
      .ticket-builder { grid-template-columns: 1fr; }
      .template-builder { grid-template-columns: 1fr; }
      .report-calculator-workspace { grid-template-columns: 1fr; }
      .report-calculator-aside { position: static; }
      .report-calculator-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .report-fine-row { grid-template-columns: 1fr; }
      .form-grid { grid-template-columns: 1fr; }
      .option-row { grid-template-columns: 1fr; }
      .audit-grid { grid-template-columns: 1fr; }
      .loot-controls { grid-template-columns: 1fr; }
      .loot-file-summary { align-items: stretch; flex-direction: column; }
      .loot-detail-grid { grid-template-columns: 1fr; }
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
    }

    @media (max-width: 460px) {
      .report-calculator-heading h2 { font-size: 24px; }
      .report-calculator-summary { grid-template-columns: 1fr; }
      .report-participant-head { align-items: flex-start; flex-direction: column; }
      .section-list,
      .sidebar-collapsed .section-list {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
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
        <div class="sidebar-head">
          <div class="sidebar-heading">
            <strong>Centro de control</strong>
            <span>Modulos de AvalonBot</span>
          </div>
          <button id="sidebarToggle" class="menu-button" type="button" aria-label="Minimizar secciones">
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="m15 18-6-6 6-6"></path>
            </svg>
          </button>
        </div>
        <div class="section-label">Secciones</div>
        <nav class="section-list">
          <button class="section-button active" type="button" data-section="economy" title="Economia">
            <span class="section-icon">
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="9"></circle>
                <path d="M16 8h-6a2 2 0 0 0 0 4h4a2 2 0 0 1 0 4H8"></path>
                <path d="M12 6v12"></path>
              </svg>
            </span>
            <span class="section-copy"><span class="section-text">Economia</span><span class="section-hint">Balances y registros</span></span>
          </button>
          <button class="section-button" type="button" data-section="templates" title="Plantillas">
            <span class="section-icon">
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"></path>
                <path d="M14 2v6h6"></path>
                <path d="M8 13h8"></path>
                <path d="M8 17h5"></path>
              </svg>
            </span>
            <span class="section-copy"><span class="section-text">Plantillas</span><span class="section-hint">Pings y contenido</span></span>
          </button>
          <button class="section-button" type="button" data-section="loot" title="Analizador de loot">
            <span class="section-icon">
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M4 9h16l-1 11H5L4 9Z"></path>
                <path d="M8 9V7a4 4 0 0 1 8 0v2"></path>
                <path d="M9 13h6"></path>
              </svg>
            </span>
            <span class="section-copy"><span class="section-text">Loot</span><span class="section-hint">Analisis de reportes</span></span>
          </button>
          <button class="section-button" type="button" data-section="report-calculator" title="Calculadora de reparto">
            <span class="section-icon">
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="4" y="2" width="16" height="20" rx="2"></rect>
                <path d="M8 6h8"></path>
                <path d="M8 10h2"></path><path d="M14 10h2"></path>
                <path d="M8 14h2"></path><path d="M14 14h2"></path>
                <path d="M8 18h2"></path><path d="M14 18h2"></path>
              </svg>
            </span>
            <span class="section-copy"><span class="section-text">Calculadora</span><span class="section-hint">Reparto de informes</span></span>
          </button>
          <button class="section-button" type="button" data-section="tickets" title="Tickets">
            <span class="section-icon">
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M2 9a3 3 0 0 0 0 6v4a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-4a3 3 0 0 0 0-6V5a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"></path>
                <path d="M13 5v2"></path>
                <path d="M13 17v2"></path>
                <path d="M13 11v2"></path>
              </svg>
            </span>
            <span class="section-copy"><span class="section-text">Tickets</span><span class="section-hint">Paneles y soporte</span></span>
          </button>
          <button class="section-button" type="button" data-section="registration" title="Registro Albion">
            <span class="section-icon">
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                <circle cx="8.5" cy="7" r="4"></circle>
                <path d="m17 11 2 2 4-4"></path>
              </svg>
            </span>
            <span class="section-copy"><span class="section-text">Registro Albion</span><span class="section-hint">Miembros y gremio</span></span>
          </button>
          <button class="section-button" type="button" data-section="welcome" title="Bienvenidas">
            <span class="section-icon">
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path>
                <circle cx="9" cy="7" r="4"></circle>
                <path d="M19 8v6"></path>
                <path d="M22 11h-6"></path>
              </svg>
            </span>
            <span class="section-copy"><span class="section-text">Bienvenidas</span><span class="section-hint">Ingreso de miembros</span></span>
          </button>
          <button class="section-button" type="button" data-section="audit" title="Auditoria">
            <span class="section-icon">
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"></path>
                <path d="M12 8v4"></path>
                <path d="M12 16h.01"></path>
              </svg>
            </span>
            <span class="section-copy"><span class="section-text">Auditoria</span><span class="section-hint">Eventos del servidor</span></span>
          </button>
          <button class="section-button" type="button" data-section="permissions" title="Permisos">
            <span class="section-icon">
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="8" cy="15" r="3"></circle>
                <path d="m10.5 12.5 7-7a2.1 2.1 0 0 1 3 3l-7 7"></path>
                <path d="m18 8 2 2"></path>
              </svg>
            </span>
            <span class="section-copy"><span class="section-text">Permisos</span><span class="section-hint">Accesos por rol</span></span>
          </button>
        </nav>
      </aside>
      <section id="economySection" aria-label="Economia">
        <div class="economy-panel">
          <div class="module-header">
            <p>Balances, registros de balance, Avas e informes.</p>
            <div class="ticket-actions">
              <button id="exportEconomyButton" class="action-button" type="button">Exportar economia</button>
              <div id="status" class="status">Cargando...</div>
            </div>
          </div>

          <nav class="tabs" aria-label="Opciones de Economia">
            <button class="tab active" data-tab="balances">Balances</button>
            <button class="tab" data-tab="operations">Registro Balance</button>
            <button class="tab" data-tab="avalonians">Registro Avas</button>
            <button class="tab" data-tab="reports">Registro Informes</button>
            <button class="tab" data-tab="fines">Registro Multas</button>
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
              <button id="exportTemplatesButton" class="action-button" type="button">Exportar plantillas</button>
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
              <button id="exportTicketsButton" class="action-button" type="button">Exportar tickets</button>
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
            <div class="ticket-stat"><span>Abiertos</span><strong id="ticketOpenTotal">0</strong></div>
            <div class="ticket-stat"><span>Cerrados hoy</span><strong id="ticketClosedTodayTotal">0</strong></div>
          </section>

          <section class="editor-section" aria-label="Configuracion de multas">
            <div class="editor-section-header">
              <div>
                <strong>Configuracion de multas</strong>
                <span>Define el canal, rol de bloqueo, rol que resuelve multas y categoria para tickets de multa.</span>
              </div>
              <button id="saveFineConfigButton" class="action-button primary" type="button">Guardar multas</button>
            </div>
            <div class="form-grid">
              <div class="field">
                <label for="fineChannel">Canal de multas</label>
                <select id="fineChannel"></select>
              </div>
              <div class="field">
                <label for="fineBlockedRole">Rol multado</label>
                <select id="fineBlockedRole"></select>
              </div>
              <div class="field">
                <label for="fineResolverRole">Rol que resuelve</label>
                <select id="fineResolverRole"></select>
              </div>
              <div class="field">
                <label for="fineTicketCategory">Categoria ticket multa</label>
                <select id="fineTicketCategory"></select>
              </div>
            </div>
            <div id="fineConfigStatus" class="status"></div>
          </section>

          <section class="ticket-builder" aria-label="Constructor de tickets">
            <aside>
              <div class="section-label">Paneles creados</div>
              <div id="ticketPanelList" class="panel-list"></div>
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
                    <span>Todo es opcional. El bot no agregara ningun texto que no hayas configurado.</span>
                  </div>
                </div>
                <div class="form-grid">
                  <div class="field full">
                    <label for="ticketOpenContent">Mensaje arriba del embed</label>
                    <textarea id="ticketOpenContent" placeholder="Ejemplo: Bienvenido {mention}, completa el formulario."></textarea>
                  </div>
                  <div class="field">
                    <label for="ticketOpenTitle">Titulo del embed</label>
                    <input id="ticketOpenTitle" type="text" placeholder="Opcional">
                  </div>
                  <div class="field">
                    <label for="ticketOpenColor">Color del embed</label>
                    <input id="ticketOpenColor" type="text" placeholder="#38bdf8 (opcional)">
                  </div>
                  <div class="field full">
                    <label for="ticketOpenDescription">Contenido del embed</label>
                    <textarea id="ticketOpenDescription" placeholder="Puedes escribir instrucciones, listas y menciones."></textarea>
                  </div>
                  <div class="field full">
                    <label for="ticketOpenFooter">Footer del embed</label>
                    <input id="ticketOpenFooter" type="text" placeholder="Opcional">
                  </div>
                  <div class="field">
                    <label for="ticketOpenImage">Imagen grande URL</label>
                    <input id="ticketOpenImage" type="url" placeholder="https://...">
                  </div>
                  <div class="field">
                    <label for="ticketOpenThumbnail">Miniatura URL</label>
                    <input id="ticketOpenThumbnail" type="url" placeholder="https://...">
                  </div>
                </div>
                <div class="preview-box">
                  <strong>Variables disponibles</strong>
                  <div class="placeholder-list">{mention} {user} {username} {display_name} {user_id} {ticket_number} {ticket_name} {panel_name} {option}</div>
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
                  <div class="field full">
                    <div class="editor-section-header">
                      <div>
                        <strong>Permisos en ticket por rol</strong>
                        <span>Elige un rol y marca los permisos que tendra dentro del canal privado.</span>
                      </div>
                      <button id="addTicketPermissionRoleButton" class="action-button" type="button">+ Agregar rol</button>
                    </div>
                    <div id="ticketRolePermissionsList" class="ticket-permission-list"></div>
                  </div>
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

            <div id="ticketLiveViewer" class="ticket-live-viewer" hidden>
              <div class="editor-section-header">
                <div>
                  <strong id="ticketLiveTitle">Ticket en vivo</strong>
                  <span id="ticketLiveSubtitle">Mensajes del canal en Discord.</span>
                </div>
                <button id="closeLiveTicketButton" class="action-button" type="button">Cerrar vista</button>
              </div>
              <div id="ticketLiveMessages" class="live-chat-box"></div>
              <form id="ticketLiveForm" class="live-chat-form">
                <textarea id="ticketLiveMessageInput" placeholder="Escribe un mensaje para enviarlo al ticket..."></textarea>
                <button id="sendLiveTicketMessageButton" class="action-button primary" type="submit">Enviar</button>
              </form>
              <div id="ticketLiveMessageStatus" class="status"></div>
            </div>
          </section>

          <section class="ticket-records-panel" aria-label="Tickets y transcripciones">
            <div class="records-toolbar">
              <div>
                <div class="section-label">Tickets y transcripciones</div>
                <div id="ticketLiveStatus" class="muted live-status">En vivo: esperando datos.</div>
                <div id="ticketRecordsCount" class="muted live-status">0 tickets visibles.</div>
              </div>
              <div class="ticket-actions">
                <input id="ticketRecordSearch" type="search" placeholder="Buscar ticket, usuario o panel">
                <button id="refreshTicketRecordsButton" class="action-button" type="button">Actualizar</button>
              </div>
            </div>
            <div id="ticketRecordsList" class="ticket-list"></div>
          </section>
        </div>
      </section>
      <section id="reportCalculatorSection" class="module-panel" aria-label="Calculadora de reparto" hidden>
        <div class="ticket-dashboard report-calculator-shell">
          <div class="ticket-toolbar report-calculator-toolbar">
            <div class="report-calculator-heading">
              <div class="section-label">Modulo de reparto</div>
              <h2>Calculadora de reparto</h2>
              <p id="reportCalculatorSubtitle">Carga una Ava desde el boton Enviar informe de Discord.</p>
            </div>
            <div class="field report-calculator-picker">
              <label for="reportCalculatorSelect">Pings activos</label>
              <select id="reportCalculatorSelect">
                <option value="">Selecciona una Ava</option>
              </select>
            </div>
          </div>

          <section class="ticket-summary report-calculator-summary">
            <div class="ticket-stat"><span>Integrantes</span><strong id="reportCalculatorParticipantsTotal">0</strong></div>
            <div class="ticket-stat"><span>Reparten</span><strong id="reportSplitParticipantsTotal">0</strong></div>
            <div id="reportItemsPerUserStat" class="ticket-stat"><span>Items C/U</span><strong id="reportItemsPerUser">0</strong></div>
            <div id="reportSilverPerUserStat" class="ticket-stat"><span>Silver C/U</span><strong id="reportSilverPerUser">0</strong></div>
            <div class="ticket-stat"><span>Total neto</span><strong id="reportNetTotal">0</strong></div>
          </section>

          <section class="editor-section report-calculator-participants">
            <div class="editor-section-header">
              <div>
                <strong>Integrantes del reparto</strong>
                <span>Estos jugadores vienen cargados desde la Ava seleccionada.</span>
              </div>
            </div>
            <div id="reportParticipantsList" class="report-participant-list"></div>
          </section>

          <div class="report-calculator-workspace">
            <div class="template-editor report-calculator-form">
              <div class="editor-section-header">
                <div>
                  <strong>Datos del informe</strong>
                  <span>Incluye todas las opciones del antiguo modal de Discord.</span>
                </div>
              </div>
              <div class="form-grid">
                <div class="field full">
                  <label for="reportSplitMode">Modo de reparto</label>
                  <select id="reportSplitMode">
                    <option value="items">Solo items</option>
                    <option value="silver">Solo silver</option>
                    <option value="items_silver">Items + silver</option>
                  </select>
                </div>
                <div class="field">
                  <label for="reportEstimated">Estimado</label>
                  <input id="reportEstimated" type="text" placeholder="Ej: 12.5m">
                </div>
                <div id="reportItemsField" class="field">
                  <label for="reportItems">Valor de items</label>
                  <input id="reportItems" type="text" placeholder="Ej: 10m">
                </div>
                <div id="reportSilverField" class="field">
                  <label for="reportSilver">Silver / bolsas</label>
                  <input id="reportSilver" type="text" placeholder="Ej: 2.5m">
                </div>
                <div id="reportMapCostField" class="field">
                  <label for="reportMapCost">Costo del mapa</label>
                  <input id="reportMapCost" type="text" placeholder="Ej: 1m">
                </div>
                <div id="reportRepairCostField" class="field">
                  <label for="reportRepairCost">Reparaciones</label>
                  <input id="reportRepairCost" type="text" placeholder="Ej: 500k">
                </div>
                <div id="reportCallerPercentField" class="field" hidden>
                  <label for="reportCallerPercent">Porcentaje caller</label>
                  <input id="reportCallerPercent" type="text" placeholder="Ej: 10%">
                </div>
                <div id="reportLooterPaymentField" class="field" hidden>
                  <label for="reportLooterPayment">Pago looter</label>
                  <input id="reportLooterPayment" type="text" placeholder="Ej: 1m">
                </div>
                <div id="reportLooterUserField" class="field" hidden>
                  <label for="reportLooterUser">Quien fue el looter</label>
                  <select id="reportLooterUser">
                    <option value="">Selecciona un integrante</option>
                  </select>
                </div>
                <div id="reportTabSaleField" class="field" hidden>
                  <label for="reportTabSalePercent">Venta de tab</label>
                  <input id="reportTabSalePercent" type="text" placeholder="Ej: 15%">
                </div>
                <div class="field full">
                  <div class="editor-section report-fines-section">
                    <div class="editor-section-header">
                      <div>
                        <strong>Multas</strong>
                        <span>Asigna monto, motivo y prueba para los jugadores multados.</span>
                      </div>
                      <button id="addReportFineButton" class="action-button" type="button">+ Agregar multa</button>
                    </div>
                    <div id="reportFinesList" class="option-list"></div>
                  </div>
                </div>
              </div>
              <div class="publish-row report-calculator-actions">
                <button id="resetReportCalculatorButton" class="action-button" type="button">Reiniciar calculadora</button>
                <button id="submitReportCalculatorButton" class="action-button primary" type="button">Enviar informe a evaluacion</button>
                <div id="reportCalculatorStatus" class="status"></div>
              </div>
            </div>

            <aside class="report-calculator-aside">
              <div class="preview-box report-calculator-breakdown">
                <div class="report-calculator-panel-head">
                  <strong>Balance del reparto</strong>
                  <span>Resumen neto antes de enviar el informe a evaluacion.</span>
                </div>
                <div id="reportCalculatorBreakdown" class="report-breakdown-list"></div>
              </div>
            </aside>
          </div>
        </div>
      </section>
      <section id="registrationSection" class="module-panel" aria-label="Registro Albion" hidden>
        <div class="ticket-dashboard">
          <div class="ticket-toolbar">
            <div>
              <h2>Registro de Albion</h2>
              <p>Configura el registro por personaje para la region America y controla que pasa cuando alguien abandona el gremio.</p>
            </div>
            <div class="ticket-actions">
              <button id="refreshAlbionRegistrationButton" class="action-button" type="button">Recargar</button>
              <button id="saveAlbionRegistrationButton" class="action-button primary" type="button">Guardar configuracion</button>
            </div>
          </div>

          <section class="ticket-summary" aria-label="Resumen de registro">
            <div class="ticket-stat"><span>Region</span><strong>America</strong></div>
            <div class="ticket-stat"><span>Registrados</span><strong id="albionRegistrationTotal">0</strong></div>
            <div class="ticket-stat"><span>Activos</span><strong id="albionRegistrationActiveTotal">0</strong></div>
          </section>

          <div class="editor-section">
            <div class="editor-section-header">
              <div>
                <strong>Configuracion del gremio</strong>
                <span>El nombre se valida contra la API oficial de Albion Online antes de guardar.</span>
              </div>
            </div>
            <div class="form-grid">
              <div class="field">
                <label for="albionGuildName">Nombre exacto del gremio</label>
                <input id="albionGuildName" type="text" placeholder="Nombre del gremio">
              </div>
              <div class="field">
                <label for="albionRole">Rol para miembros registrados</label>
                <select id="albionRole"><option value="">Seleccionar rol</option></select>
              </div>
              <div class="field">
                <label for="albionLeaveAction">Si abandona el gremio</label>
                <select id="albionLeaveAction">
                  <option value="remove_roles">Quitar los roles</option>
                  <option value="kick">Expulsar del Discord</option>
                </select>
              </div>
              <div class="field">
                <label for="albionLogChannel">Canal de registros</label>
                <select id="albionLogChannel"><option value="">Sin canal de registros</option></select>
              </div>
              <label class="check-row">
                <input id="albionSyncNickname" type="checkbox">
                <span>Cambiar el apodo de Discord al nombre del personaje de Albion</span>
              </label>
            </div>
            <div id="albionRegistrationStatus" class="status"></div>
          </div>

          <div class="editor-section">
            <div class="editor-section-header">
              <div>
                <strong>Personas registradas</strong>
                <span>Los usuarios se registran con el comando /albion registrar.</span>
              </div>
            </div>
            <section class="table-wrap">
              <table>
                <thead>
                  <tr><th>Discord</th><th>Personaje</th><th>Gremio</th><th>Estado</th><th>Ultima revision</th></tr>
                </thead>
                <tbody id="albionRegistrationsBody"></tbody>
              </table>
              <div id="albionRegistrationsEmpty" class="empty">Todavia no hay personas registradas.</div>
            </section>
          </div>
        </div>
      </section>
      <section id="welcomeSection" class="module-panel" aria-label="Bienvenidas" hidden></section>
      <section id="lootSection" class="module-panel" aria-label="Analizador de loot" hidden>
        <div class="loot-dashboard">
          <div class="ticket-toolbar">
            <div>
              <h2>Analizador de loot</h2>
              <p>Importa reportes de StatisticsAnalysisTool y consolida el botin por jugador.</p>
            </div>
            <div class="ticket-actions">
              <button id="lootReplaceButton" class="action-button primary" type="button" hidden>Cargar otro archivo</button>
              <button id="lootClearButton" class="action-button danger" type="button" hidden>Limpiar</button>
            </div>
          </div>

          <label id="lootDropzone" class="loot-dropzone">
            <input id="lootFileInput" type="file" accept=".csv,.json">
            <span class="loot-dropzone-icon" aria-hidden="true">+</span>
            <strong>Arrastra un CSV o JSON</strong>
            <span>Tambien puedes hacer clic para seleccionar el reporte. El archivo se procesa localmente.</span>
          </label>

          <div id="lootError" class="loot-error" hidden></div>

          <div id="lootResults" hidden>
            <div class="loot-file-summary">
              <div>
                <strong id="lootFileName">Reporte</strong>
                <span id="lootFileMeta"></span>
              </div>
              <div class="loot-player-total">
                <span id="lootGrandTotal"></span>
              </div>
            </div>

            <section class="loot-controls" aria-label="Opciones de loot">
              <div class="loot-control-card">
                <strong>Filtro por tier</strong>
                <div id="lootTierButtons" class="loot-tier-buttons"></div>
                <span class="muted">Morado: visible. Rojo: oculto. Amarillo: visible parcialmente.</span>
              </div>
              <div class="loot-control-card">
                <strong>Tamano de iconos</strong>
                <div class="loot-range">
                  <input id="lootIconSize" type="range" min="48" max="96" value="60">
                  <span id="lootIconSizeLabel">60px</span>
                </div>
              </div>
              <div class="loot-control-card">
                <strong>Agrupacion</strong>
                <div class="loot-switch-row">
                  <span>Separar objetos por tier</span>
                  <button id="lootGroupToggle" class="loot-switch" type="button" aria-pressed="false">No</button>
                </div>
              </div>
            </section>

            <div id="lootPlayers" class="loot-players"></div>
          </div>
        </div>
      </section>
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

  <div id="lootModal" class="loot-modal" role="dialog" aria-modal="true" aria-labelledby="lootModalTitle" hidden>
    <div id="lootModalPanel" class="loot-modal-panel"></div>
  </div>

  <script>
    const pageParams = new URLSearchParams(window.location.search);
    const linkedReportSection = pageParams.get("section") === "report-calculator";
    const state = {
      data: null,
      section: linkedReportSection ? "report-calculator" : (localStorage.getItem("dashboardSection") || "economy"),
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
      ticketRecordsSummary: {},
      ticketRecordSearch: "",
      selectedTicketRecordId: "",
      selectedLiveTicketId: "",
      ticketLiveMessages: [],
      ticketLiveStatus: "",
      templateStatusMessage: "",
      auditCategories: [],
      auditConfig: { channels: {} },
      auditEvents: [],
      botPermissions: {},
      botPermissionOptions: [],
      albionRegistrationConfig: null,
      albionRegistrations: [],
      reportCalculator: null,
      reportCalculatorOptions: [],
      reportRequestId: "",
      reportContext: linkedReportSection ? {
        guildId: pageParams.get("guild_id") || "",
        callerId: pageParams.get("caller_id") || "",
        ava: pageParams.get("ava") || ""
      } : null,
      fineConfig: null,
      csrfToken: "",
      permissionSearch: "",
      loot: {
        data: null,
        fileName: "",
        format: "",
        iconSize: 60,
        groupByTier: false,
        excludedTiers: new Set(),
        manualHides: new Set(),
        manualShows: new Set()
      },
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
      ],
      fines: [
        ["id", "#", "number"],
        ["report_ava", "Ava"],
        ["fined_user_name", "Usuario"],
        ["amount", "Monto", "number"],
        ["reason", "Motivo"],
        ["status", "Estado"],
        ["created_by_name", "Creado por"],
        ["paid_by_name", "Pagado por"],
        ["created_at", "Creado"],
        ["paid_at", "Pagado"]
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

    const ticketChannelPermissionOptions = [
      ["view_channel", "Ver canal"],
      ["send_messages", "Enviar mensajes"],
      ["read_message_history", "Leer historial"],
      ["attach_files", "Adjuntar archivos"],
      ["embed_links", "Insertar enlaces"],
      ["add_reactions", "Agregar reacciones"],
      ["use_external_emojis", "Usar emojis externos"],
      ["use_external_stickers", "Usar stickers externos"],
      ["mention_everyone", "Mencionar everyone/here"],
      ["manage_messages", "Gestionar mensajes"],
      ["manage_channels", "Gestionar canal"],
      ["manage_threads", "Gestionar hilos"],
      ["create_public_threads", "Crear hilos publicos"],
      ["create_private_threads", "Crear hilos privados"],
      ["send_messages_in_threads", "Enviar en hilos"],
      ["use_application_commands", "Usar comandos"]
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
        ticket_open_content: "",
        ticket_open_title: "",
        ticket_open_description: "",
        ticket_open_color: "",
        ticket_open_footer: "",
        ticket_open_image_url: "",
        ticket_open_thumbnail_url: "",
        options: [
          {
            id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-option`,
            label: "Abrir ticket",
            emoji: "",
            description: "Crear un ticket privado"
          }
        ],
        permissions: {
          ticket_role_permissions: [],
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

    const lootTiers = [4, 5, 6, 7, 8];

    function lootItemKey(playerName, itemId) {
      return `${playerName}\u0000${itemId}`;
    }

    function resolveLootTier(itemId) {
      if (itemId === "QUESTITEM_TOKEN_AVALON") return 6;
      if (itemId.startsWith("QUESTITEM_EXP_TOKEN")) return 4;
      const treasure = itemId.match(/^TREASURE_.+_(RARITY[123])$/);
      if (treasure) return { RARITY1: 4, RARITY2: 5, RARITY3: 6 }[treasure[1]] || null;
      const prefix = itemId.match(/^T([4-8])_/);
      return prefix ? Number(prefix[1]) : null;
    }

    function lootTierLabel(tier) {
      return tier == null ? "N/A" : `T${tier}`;
    }

    function lootImageUrl(itemId) {
      return `https://render.albiononline.com/v1/item/${encodeURIComponent(itemId)}.png`;
    }

    function createLootItem(itemId, itemName) {
      return {
        itemId,
        itemName: itemName || itemId || "Objeto desconocido",
        tier: resolveLootTier(itemId),
        totalQuantity: 0,
        price: 0,
        totalPrice: 0,
        imageUrl: lootImageUrl(itemId)
      };
    }

    function addLootEntry(lootMap, playerName, itemId, itemName, quantity, price = 0) {
      const cleanPlayer = String(playerName || "").trim();
      const cleanItemId = String(itemId || "").trim();
      const numericQuantity = Number(quantity);
      const numericPrice = Number(price || 0);
      if (!cleanPlayer || !cleanItemId || !Number.isFinite(numericQuantity) || numericQuantity <= 0) return;
      if (!lootMap[cleanPlayer]) lootMap[cleanPlayer] = {};
      if (!lootMap[cleanPlayer][cleanItemId]) {
        lootMap[cleanPlayer][cleanItemId] = createLootItem(cleanItemId, itemName);
      }
      const item = lootMap[cleanPlayer][cleanItemId];
      item.totalQuantity += numericQuantity;
      if (!item.price && Number.isFinite(numericPrice)) item.price = numericPrice;
      if (Number.isFinite(numericPrice)) item.totalPrice += numericPrice * numericQuantity;
    }

    function detectCsvDelimiter(text) {
      const firstLine = String(text || "").split(/\r?\n/, 1)[0] || "";
      const delimiters = [";", ",", "\t"];
      return delimiters.sort((a, b) => firstLine.split(b).length - firstLine.split(a).length)[0];
    }

    function parseCsvRows(text, delimiter) {
      const rows = [];
      let row = [];
      let field = "";
      let quoted = false;
      for (let index = 0; index < text.length; index += 1) {
        const character = text[index];
        if (quoted) {
          if (character === '"' && text[index + 1] === '"') {
            field += '"';
            index += 1;
          } else if (character === '"') {
            quoted = false;
          } else {
            field += character;
          }
          continue;
        }
        if (character === '"') {
          quoted = true;
        } else if (character === delimiter) {
          row.push(field);
          field = "";
        } else if (character === "\n") {
          row.push(field.replace(/\r$/, ""));
          if (row.some(value => value.trim())) rows.push(row);
          row = [];
          field = "";
        } else {
          field += character;
        }
      }
      row.push(field.replace(/\r$/, ""));
      if (row.some(value => value.trim())) rows.push(row);
      return rows;
    }

    function parseLootCsvText(text) {
      const rows = parseCsvRows(text.replace(/^\uFEFF/, ""), detectCsvDelimiter(text));
      if (rows.length < 2) throw new Error("El CSV no contiene filas de loot.");
      const headers = rows[0].map(value => value.trim().toLowerCase());
      const required = ["looted_by__name", "item_id", "quantity"];
      const missing = required.filter(name => !headers.includes(name));
      if (missing.length) throw new Error(`Faltan columnas requeridas: ${missing.join(", ")}.`);
      const lootMap = {};
      rows.slice(1).forEach(values => {
        const row = Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]));
        addLootEntry(
          lootMap,
          row.looted_by__name,
          row.item_id,
          row.item_name,
          Number.parseInt(row.quantity, 10),
          0
        );
      });
      return lootMap;
    }

    function parseLootJsonValue(value) {
      const entries = Array.isArray(value) ? value : value?.entries;
      if (!Array.isArray(entries)) throw new Error('El JSON debe contener una lista "entries" o ser una lista de eventos.');
      const lootMap = {};
      entries.forEach(entry => {
        if (!entry || entry.type !== "loot") return;
        const item = entry.loot?.item || {};
        addLootEntry(
          lootMap,
          entry.loot?.looted_by?.name,
          item.id,
          item.name || item.id,
          item.quantity,
          item.average_est_market_value
        );
      });
      return lootMap;
    }

    function resetLootVisibility() {
      state.loot.excludedTiers = new Set();
      state.loot.manualHides = new Set();
      state.loot.manualShows = new Set();
    }

    function isLootItemIncluded(playerName, item) {
      const key = lootItemKey(playerName, item.itemId);
      if (item.tier == null) return !state.loot.manualHides.has(key);
      if (state.loot.excludedTiers.has(item.tier)) return state.loot.manualShows.has(key);
      return !state.loot.manualHides.has(key);
    }

    function lootItemsForTier(tier) {
      const matches = [];
      Object.entries(state.loot.data || {}).forEach(([playerName, items]) => {
        Object.values(items).forEach(item => {
          if (item.tier === tier) matches.push([playerName, item]);
        });
      });
      return matches;
    }

    function lootTierState(tier) {
      if (!state.loot.excludedTiers.has(tier)) return "all";
      return lootItemsForTier(tier).some(([playerName, item]) =>
        state.loot.manualShows.has(lootItemKey(playerName, item.itemId))
      ) ? "partial" : "none";
    }

    function clearLootTierOverrides(tier) {
      lootItemsForTier(tier).forEach(([playerName, item]) => {
        const key = lootItemKey(playerName, item.itemId);
        state.loot.manualHides.delete(key);
        state.loot.manualShows.delete(key);
      });
    }

    function toggleLootTier(tier) {
      clearLootTierOverrides(tier);
      if (state.loot.excludedTiers.has(tier)) state.loot.excludedTiers.delete(tier);
      else state.loot.excludedTiers.add(tier);
      renderLoot();
    }

    function toggleLootItem(playerName, itemId) {
      const item = state.loot.data?.[playerName]?.[itemId];
      if (!item) return;
      const key = lootItemKey(playerName, itemId);
      const visible = isLootItemIncluded(playerName, item);
      if (item.tier != null && state.loot.excludedTiers.has(item.tier)) {
        if (visible) state.loot.manualShows.delete(key);
        else state.loot.manualShows.add(key);
      } else if (visible) {
        state.loot.manualHides.add(key);
      } else {
        state.loot.manualHides.delete(key);
      }
      renderLoot();
    }

    function sortedLootItems(items) {
      return [...items].sort((a, b) => {
        const tierDifference = (a.tier ?? 99) - (b.tier ?? 99);
        return tierDifference || b.totalQuantity - a.totalQuantity || a.itemName.localeCompare(b.itemName);
      });
    }

    function lootItemHtml(playerName, item) {
      const included = isLootItemIncluded(playerName, item);
      const noPrice = item.price === 0 && item.totalPrice === 0;
      return `
        <div class="loot-item-wrap">
          <button class="loot-item${included ? "" : " excluded"}${noPrice ? " no-price" : ""}" type="button"
            data-loot-player="${escapeHtml(playerName)}" data-loot-item="${escapeHtml(item.itemId)}"
            title="${escapeHtml(item.itemName)} - ${included ? "clic para excluir" : "clic para incluir"}">
            <img src="${escapeHtml(item.imageUrl)}" alt="${escapeHtml(item.itemName)}" loading="lazy">
            <span class="loot-quantity">${formatNumber(item.totalQuantity)}</span>
          </button>
          <button class="loot-info" type="button" data-loot-detail-player="${escapeHtml(playerName)}"
            data-loot-detail-item="${escapeHtml(item.itemId)}" aria-label="Ver detalles de ${escapeHtml(item.itemName)}">i</button>
        </div>
      `;
    }

    function lootPlayerHtml(playerName, items) {
      const itemList = sortedLootItems(Object.values(items));
      const total = itemList.reduce((sum, item) =>
        isLootItemIncluded(playerName, item) ? sum + item.totalPrice : sum, 0
      );
      let content = "";
      if (state.loot.groupByTier) {
        content = [...lootTiers, null].map(tier => {
          const tierItems = itemList.filter(item => item.tier === tier);
          if (!tierItems.length) return "";
          return `<section class="loot-tier-group"><h4>${lootTierLabel(tier)}</h4><div class="loot-grid">${tierItems.map(item => lootItemHtml(playerName, item)).join("")}</div></section>`;
        }).join("");
      } else {
        content = `<div class="loot-grid">${itemList.map(item => lootItemHtml(playerName, item)).join("")}</div>`;
      }
      return `
        <article class="loot-player-card">
          <div class="loot-player-header">
            <h3>${escapeHtml(playerName)}</h3>
            ${state.loot.format === "json" ? `<span class="loot-player-total">${formatNumber(total)} silver</span>` : `<span class="muted">${itemList.length} objetos</span>`}
          </div>
          ${content}
        </article>
      `;
    }

    function renderLoot() {
      const hasData = Boolean(state.loot.data);
      document.getElementById("lootDropzone").hidden = hasData;
      document.getElementById("lootResults").hidden = !hasData;
      document.getElementById("lootReplaceButton").hidden = !hasData;
      document.getElementById("lootClearButton").hidden = !hasData;
      if (!hasData) return;

      const players = Object.entries(state.loot.data);
      const itemKinds = players.reduce((sum, [, items]) => sum + Object.keys(items).length, 0);
      document.getElementById("lootFileName").textContent = state.loot.fileName;
      document.getElementById("lootFileMeta").textContent =
        `${players.length} jugadores - ${itemKinds} objetos agrupados - ${state.loot.format.toUpperCase()}`;
      document.getElementById("lootGrandTotal").textContent = state.loot.format === "json"
        ? `${formatNumber(players.reduce((sum, [playerName, items]) => sum + Object.values(items).reduce((subtotal, item) => isLootItemIncluded(playerName, item) ? subtotal + item.totalPrice : subtotal, 0), 0))} silver total`
        : "";
      document.getElementById("lootTierButtons").innerHTML = lootTiers.map(tier =>
        `<button class="loot-tier-button ${lootTierState(tier)}" type="button" data-loot-tier="${tier}">T${tier}</button>`
      ).join("");
      document.getElementById("lootIconSize").value = state.loot.iconSize;
      document.getElementById("lootIconSizeLabel").textContent = `${state.loot.iconSize}px`;
      document.getElementById("lootGroupToggle").classList.toggle("active", state.loot.groupByTier);
      document.getElementById("lootGroupToggle").textContent = state.loot.groupByTier ? "Si" : "No";
      document.getElementById("lootGroupToggle").setAttribute("aria-pressed", String(state.loot.groupByTier));
      document.getElementById("lootPlayers").style.setProperty("--loot-icon-size", `${state.loot.iconSize}px`);
      document.getElementById("lootPlayers").innerHTML = players.map(([playerName, items]) =>
        lootPlayerHtml(playerName, items)
      ).join("");
    }

    function showLootDetail(playerName, itemId) {
      const item = state.loot.data?.[playerName]?.[itemId];
      if (!item) return;
      const noPrice = item.price === 0 && item.totalPrice === 0;
      document.getElementById("lootModalPanel").innerHTML = `
        <button class="loot-modal-close" type="button" data-loot-modal-close aria-label="Cerrar">x</button>
        <div class="loot-modal-hero">
          <img src="${escapeHtml(item.imageUrl)}" alt="${escapeHtml(item.itemName)}">
          <div><h3 id="lootModalTitle">${escapeHtml(item.itemName)}</h3><p>${escapeHtml(playerName)}</p></div>
        </div>
        <div class="loot-detail-grid">
          <div class="loot-detail"><span>ID</span><strong>${escapeHtml(item.itemId)}</strong></div>
          <div class="loot-detail"><span>Tier</span><strong>${lootTierLabel(item.tier)}</strong></div>
          <div class="loot-detail"><span>Cantidad total</span><strong>${formatNumber(item.totalQuantity)}</strong></div>
          <div class="loot-detail"><span>Precio estimado</span><strong>${noPrice ? "N/A" : `${formatNumber(item.price)} silver`}</strong></div>
          <div class="loot-detail"><span>Valor total</span><strong>${noPrice ? "N/A" : `${formatNumber(item.totalPrice)} silver`}</strong></div>
          <div class="loot-detail"><span>Estado</span><strong>${isLootItemIncluded(playerName, item) ? "Incluido" : "Excluido"}</strong></div>
        </div>
      `;
      document.getElementById("lootModal").hidden = false;
    }

    function closeLootDetail() {
      document.getElementById("lootModal").hidden = true;
    }

    async function loadLootFile(file) {
      if (!file) return;
      const extension = file.name.split(".").pop()?.toLowerCase();
      if (!["csv", "json"].includes(extension)) throw new Error("Formato no soportado. Usa un archivo CSV o JSON.");
      const text = await file.text();
      const data = extension === "csv" ? parseLootCsvText(text) : parseLootJsonValue(JSON.parse(text));
      if (!Object.keys(data).length) throw new Error("No se encontraron eventos de loot validos en el archivo.");
      state.loot.data = data;
      state.loot.fileName = file.name;
      state.loot.format = extension;
      resetLootVisibility();
      document.getElementById("lootError").hidden = true;
      renderLoot();
    }

    function clearLoot() {
      state.loot.data = null;
      state.loot.fileName = "";
      state.loot.format = "";
      resetLootVisibility();
      document.getElementById("lootFileInput").value = "";
      document.getElementById("lootError").hidden = true;
      closeLootDetail();
      renderLoot();
    }

    function showLootError(error) {
      const element = document.getElementById("lootError");
      element.textContent = error instanceof SyntaxError
        ? "El archivo JSON no tiene un formato valido."
        : (error.message || "No pude procesar el archivo.");
      element.hidden = false;
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
      renderAlbionRegistration();
      renderReportCalculator();
      renderLoot();
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
      document.getElementById("ticketPanelTotal").textContent = state.ticketPanels.length;
      renderTicketLiveSummary();
      renderFineConfig();
      const hasPanel = Boolean(currentTicketPanel());
      document.getElementById("clonePanelButton").hidden = !hasPanel;
      document.getElementById("deletePanelButton").hidden = !hasPanel;
      renderTicketPanelList();
      renderTicketChannels();
      renderTicketCategories();
      renderTicketEditor();
      renderTicketEditorSections();
      renderTicketRecords();
      renderTicketLiveViewer();
    }

    function renderFineConfig() {
      const config = state.fineConfig || {};
      const channelSelect = document.getElementById("fineChannel");
      const blockedRoleSelect = document.getElementById("fineBlockedRole");
      const resolverRoleSelect = document.getElementById("fineResolverRole");
      const categorySelect = document.getElementById("fineTicketCategory");

      channelSelect.innerHTML = `<option value="">Seleccionar canal</option>${state.ticketChannels.map(channel =>
        `<option value="${escapeHtml(channel.id)}"># ${escapeHtml(channel.name)}</option>`
      ).join("")}`;
      categorySelect.innerHTML = `<option value="">Sin categoria</option>${state.ticketCategories.map(category =>
        `<option value="${escapeHtml(category.id)}">${escapeHtml(category.name)}</option>`
      ).join("")}`;
      const roleOptions = `<option value="">Seleccionar rol</option>${state.ticketRoles.map(role =>
        `<option value="${escapeHtml(role.id)}">${escapeHtml(role.name)}</option>`
      ).join("")}`;
      blockedRoleSelect.innerHTML = roleOptions;
      resolverRoleSelect.innerHTML = roleOptions;

      channelSelect.value = config.channel_id || "";
      blockedRoleSelect.value = config.blocked_role_id || "";
      resolverRoleSelect.value = config.resolver_role_id || "";
      categorySelect.value = config.ticket_category_id || "";
    }

    function renderTicketLiveSummary() {
      const summary = state.ticketRecordsSummary || {};
      document.getElementById("ticketOpenTotal").textContent = summary.open ?? 0;
      document.getElementById("ticketClosedTodayTotal").textContent = summary.closed_today ?? 0;
      document.getElementById("ticketLiveStatus").textContent = summary.updated_at
        ? `En vivo: ${summary.open || 0} abiertos, ${summary.claimed || 0} reclamados, ${summary.transcribed || 0} transcritos. Ultima actualizacion: ${summary.updated_at}`
        : "En vivo: esperando datos.";
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
      const countLabel = records.length === 1 ? "1 ticket visible." : `${records.length} tickets visibles.`;
      document.getElementById("ticketRecordsCount").textContent = countLabel;
      if (!records.length) {
        list.innerHTML = `
          <article class="ticket-card">
            <div>
              <h3>No hay tickets para mostrar</h3>
              <div class="ticket-meta"><span>Los tickets abiertos y transcritos apareceran aca.</span></div>
            </div>
          </article>`;
        state.selectedTicketRecordId = "";
        return;
      }

      list.innerHTML = records.map(record => {
        const status = String(record.status || "open").toLowerCase();
        const label = status === "open" ? "Abierto" : status === "closed" ? "Cerrado" : status === "deleted" ? "Eliminado" : status;
        const recordId = record.channel_id || record.number || "";
        const hasTranscript = Boolean(record.transcribed_at || (Array.isArray(record.transcript) && record.transcript.length));
        const metadata = [
          ["Usuario", record.owner_name || record.owner_id || "Desconocido"],
          ["Panel", record.panel_name || "Sin panel"],
          record.option_label ? ["Opcion", record.option_label] : null,
          record.created_at ? ["Creado", record.created_at] : null,
          record.claimed_by_name ? ["Reclamado por", record.claimed_by_name] : null,
          record.closed_at ? ["Cerrado", record.closed_at] : null,
          record.transcribed_at ? ["Transcrito", record.transcribed_at] : null
        ].filter(Boolean);
        return `
          <article class="ticket-card live-ticket ${escapeHtml(status)}">
            <div>
              <div class="ticket-record-title">
                <h3>${escapeHtml(record.channel_name || `ticket-${record.number || ""}`)}</h3>
                <span class="ticket-status">${escapeHtml(label)}</span>
              </div>
              <div class="ticket-record-meta">
                ${metadata.map(([name, value]) => `<span><b>${escapeHtml(name)}</b>${escapeHtml(value)}</span>`).join("")}
              </div>
            </div>
            <div class="ticket-card-actions">
              ${status === "open" && record.channel_id ? `<button class="action-button view-live-ticket-button${String(state.selectedLiveTicketId) === String(record.channel_id) ? " active" : ""}" type="button" data-channel-id="${escapeHtml(record.channel_id)}">Ver ticket</button>` : ""}
              <button class="action-button view-transcript-button${String(state.selectedTicketRecordId) === String(recordId) ? " active" : ""}" type="button" data-record-id="${escapeHtml(recordId)}" title="Ver transcripcion" aria-label="Ver transcripcion"${hasTranscript ? "" : " disabled"}>Ver transcripcion</button>
              ${status !== "open" ? `<button class="action-button danger delete-ticket-record-button" type="button" data-record-id="${escapeHtml(recordId)}" data-channel-id="${escapeHtml(record.channel_id || "")}" data-record-name="${escapeHtml(record.channel_name || `ticket-${record.number || ""}`)}">Eliminar registro</button>` : ""}
            </div>
          </article>
        `;
      }).join("");

      list.querySelectorAll(".view-live-ticket-button").forEach(button => {
        button.addEventListener("click", () => {
          openLiveTicket(button.dataset.channelId).catch(error => {
            document.getElementById("ticketLiveMessageStatus").textContent = error.message;
          });
        });
      });

      list.querySelectorAll(".view-transcript-button").forEach(button => {
        button.addEventListener("click", () => {
          openTicketTranscript(button.dataset.recordId);
        });
      });

      list.querySelectorAll(".delete-ticket-record-button").forEach(button => {
        button.addEventListener("click", () => {
          deleteTicketRecord(
            button.dataset.recordId,
            button.dataset.channelId,
            button.dataset.recordName
          ).catch(error => {
            document.getElementById("ticketStatus").textContent = error.message;
          });
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

    async function deleteTicketRecord(recordId, channelId, recordName) {
      const confirmed = window.confirm(
        `Eliminar definitivamente ${recordName || "este ticket"} de la base de datos? Desaparecera de la lista junto con su transcripcion y archivos guardados.`
      );
      if (!confirmed) return;

      const response = await fetch("/api/ticket-record", {
        method: "DELETE",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          record_id: recordId
        })
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "No pude eliminar el registro del ticket.");
      }

      state.ticketRecords = payload.records || [];
      state.ticketRecordsSummary = payload.summary || {};
      if (String(state.selectedTicketRecordId) === String(recordId)) {
        state.selectedTicketRecordId = "";
      }
      if (String(state.selectedLiveTicketId) === String(channelId)) {
        closeLiveTicket();
      }
      document.getElementById("ticketStatus").textContent = "Registro del ticket eliminado definitivamente.";
      renderTickets();
    }

    function liveTicketRecord() {
      return (state.ticketRecords || []).find(record => String(record.channel_id || "") === String(state.selectedLiveTicketId || ""));
    }

    async function openLiveTicket(channelId) {
      state.selectedLiveTicketId = String(channelId || "");
      state.ticketLiveMessages = [];
      state.ticketLiveStatus = "Cargando mensajes...";
      renderTickets();
      await loadLiveTicketMessages();
    }

    function closeLiveTicket() {
      state.selectedLiveTicketId = "";
      state.ticketLiveMessages = [];
      state.ticketLiveStatus = "";
      renderTickets();
    }

    async function loadLiveTicketMessages() {
      if (!state.guildId || !state.selectedLiveTicketId) return;
      const params = new URLSearchParams({
        guild_id: state.guildId,
        channel_id: state.selectedLiveTicketId
      });
      const response = await fetch(`/api/ticket-live?${params.toString()}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude cargar el ticket en vivo.");
      state.ticketLiveMessages = payload.messages || [];
      state.ticketLiveStatus = payload.updated_at ? `Actualizado: ${payload.updated_at}` : "";
      renderTicketLiveViewer();
    }

    async function sendLiveTicketMessage() {
      const input = document.getElementById("ticketLiveMessageInput");
      const content = input.value.trim();
      if (!content) return;
      const response = await fetch("/api/ticket-live-message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          guild_id: state.guildId,
          channel_id: state.selectedLiveTicketId,
          content
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude enviar el mensaje.");
      input.value = "";
      state.ticketLiveStatus = "Mensaje enviado.";
      await loadLiveTicketMessages();
    }

    function renderTicketLiveViewer() {
      const viewer = document.getElementById("ticketLiveViewer");
      const empty = document.getElementById("ticketEmptyEditor");
      const editor = document.getElementById("ticketEditor");
      const record = liveTicketRecord();
      const open = Boolean(state.selectedLiveTicketId && record && String(record.status || "open").toLowerCase() === "open");
      viewer.hidden = !open;
      if (!open) {
        if (!currentTicketPanel()) empty.hidden = false;
        editor.hidden = !currentTicketPanel();
        return;
      }

      empty.hidden = true;
      editor.hidden = true;
      document.getElementById("ticketLiveTitle").textContent = record.channel_name || `ticket-${record.number || ""}`;
      document.getElementById("ticketLiveSubtitle").textContent = `${record.panel_name || "Sin panel"} - ${record.owner_name || record.owner_id || "Usuario desconocido"}`;
      document.getElementById("ticketLiveMessageStatus").textContent = state.ticketLiveStatus || "";
      const box = document.getElementById("ticketLiveMessages");
      box.innerHTML = state.ticketLiveMessages.length
        ? state.ticketLiveMessages.map(renderTranscriptMessage).join("")
        : `<div class="transcript-message"><div></div><div class="muted">Todavia no hay mensajes cargados.</div></div>`;
      box.scrollTop = box.scrollHeight;
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

    function normalizeTicketRolePermissions(entries) {
      if (!Array.isArray(entries)) return [];
      const seen = new Set();
      return entries.map(entry => {
        const roleId = String(entry?.role_id || "").trim();
        const values = Array.isArray(entry?.permissions) ? entry.permissions : [];
        const permissions = values.map(String).filter(value => ticketChannelPermissionOptions.some(([key]) => key === value));
        return { role_id: roleId, permissions };
      }).filter(entry => {
        if (!entry.role_id || seen.has(entry.role_id) || !entry.permissions.length) return false;
        seen.add(entry.role_id);
        return true;
      }).slice(0, 20);
    }

    function roleOptionsHtml(selectedRoleId) {
      return `<option value="">Seleccionar rol</option>` + state.ticketRoles.map(role => {
        const selected = String(role.id) === String(selectedRoleId || "") ? " selected" : "";
        return `<option value="${escapeHtml(role.id)}"${selected}>@${escapeHtml(role.name)}</option>`;
      }).join("");
    }

    function renderTicketRolePermissions(panel) {
      const container = document.getElementById("ticketRolePermissionsList");
      if (!container) return;
      const savedEntries = panel?.permissions?.ticket_role_permissions;
      const entries = Array.isArray(savedEntries)
        ? savedEntries.map(entry => ({
            role_id: String(entry?.role_id || ""),
            permissions: Array.isArray(entry?.permissions) ? entry.permissions.map(String) : []
          }))
        : [];
      container.innerHTML = entries.length ? entries.map((entry, index) => {
        const selected = new Set(entry.permissions || []);
        const selectedLabels = ticketChannelPermissionOptions
          .filter(([key]) => selected.has(key))
          .map(([, label]) => label);
        const permissionCount = selectedLabels.length;
        return `
          <article class="ticket-permission-card" data-ticket-permission-index="${index}">
            <div class="ticket-permission-card-head">
              <div class="field">
                <label>Permisos en ticket para rol</label>
                <select class="ticket-permission-role">${roleOptionsHtml(entry.role_id)}</select>
              </div>
              <div class="ticket-permission-actions">
                <span class="ticket-permission-count">${permissionCount} permiso${permissionCount === 1 ? "" : "s"}</span>
                <button class="action-button danger remove-ticket-permission-role" type="button">Quitar</button>
              </div>
            </div>
            <details class="ticket-permission-details">
              <summary>Editar permisos</summary>
              <div class="ticket-permission-options">
                ${ticketChannelPermissionOptions.map(([key, label]) => `
                  <label class="permission-pill${selected.has(key) ? " active" : ""}">
                    <input class="ticket-permission-checkbox" type="checkbox" value="${escapeHtml(key)}"${selected.has(key) ? " checked" : ""}>
                    ${escapeHtml(label)}
                  </label>
                `).join("")}
              </div>
            </details>
          </article>
        `;
      }).join("") : `<div class="ticket-empty-editor"><strong>Sin roles configurados</strong><p>Agrega un rol para elegir que permisos tendra dentro del canal del ticket.</p></div>`;

      container.querySelectorAll("select, input").forEach(input => {
        input.addEventListener("change", () => {
          persistCurrentTicketPanel();
          renderTicketRolePermissions(currentTicketPanel());
        });
      });
      container.querySelectorAll(".remove-ticket-permission-role").forEach(button => {
        button.addEventListener("click", event => {
          const row = event.target.closest("[data-ticket-permission-index]");
          const index = Number(row?.dataset.ticketPermissionIndex || -1);
          const current = currentTicketPanel();
          if (!current || index < 0) return;
          current.permissions = current.permissions || {};
          current.permissions.ticket_role_permissions = Array.isArray(current.permissions.ticket_role_permissions)
            ? current.permissions.ticket_role_permissions
            : [];
          current.permissions.ticket_role_permissions.splice(index, 1);
          state.ticketPanelsDirty = true;
          renderTicketRolePermissions(current);
        });
      });
    }

    function collectTicketRolePermissions() {
      return Array.from(document.querySelectorAll("[data-ticket-permission-index]")).map(row => {
        const roleId = row.querySelector(".ticket-permission-role")?.value || "";
        const permissions = Array.from(row.querySelectorAll(".ticket-permission-checkbox:checked")).map(input => input.value);
        return { role_id: roleId, permissions };
      }).filter(entry => entry.role_id && entry.permissions.length);
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
      ["ticketName", "ticketMode", "ticketChannel", "ticketOpenCategory", "ticketColor", "ticketContent", "ticketTitle", "ticketFooter", "ticketDescription", "ticketImage", "ticketOpenContent", "ticketOpenTitle", "ticketOpenColor", "ticketOpenDescription", "ticketOpenFooter", "ticketOpenImage", "ticketOpenThumbnail", "claimRoles", "closeRoles", "reopenRoles", "deleteRoles"].forEach(id => {
        document.getElementById(id).disabled = disabled;
      });

      document.getElementById("savePanelButton").disabled = disabled;
      document.getElementById("publishPanelButton").disabled = disabled;
      document.getElementById("clonePanelButton").disabled = disabled;
      document.getElementById("deletePanelButton").disabled = disabled;
      document.getElementById("addTicketOptionButton").disabled = disabled;
      document.getElementById("addTicketPermissionRoleButton").disabled = disabled;

      if (!panel) {
        document.getElementById("ticketPreview").textContent = "Crea un panel para empezar.";
        document.getElementById("ticketOptions").innerHTML = "";
        document.getElementById("ticketRolePermissionsList").innerHTML = "";
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
      document.getElementById("ticketOpenContent").value = panel.ticket_open_content || "";
      document.getElementById("ticketOpenTitle").value = panel.ticket_open_title || "";
      document.getElementById("ticketOpenColor").value = panel.ticket_open_color || "";
      document.getElementById("ticketOpenDescription").value = panel.ticket_open_description || "";
      document.getElementById("ticketOpenFooter").value = panel.ticket_open_footer || "";
      document.getElementById("ticketOpenImage").value = panel.ticket_open_image_url || "";
      document.getElementById("ticketOpenThumbnail").value = panel.ticket_open_thumbnail_url || "";
      renderTicketRolePermissions(panel);
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
      panel.ticket_open_content = document.getElementById("ticketOpenContent").value;
      panel.ticket_open_title = document.getElementById("ticketOpenTitle").value.trim();
      panel.ticket_open_color = document.getElementById("ticketOpenColor").value.trim();
      panel.ticket_open_description = document.getElementById("ticketOpenDescription").value;
      panel.ticket_open_footer = document.getElementById("ticketOpenFooter").value.trim();
      panel.ticket_open_image_url = document.getElementById("ticketOpenImage").value.trim();
      panel.ticket_open_thumbnail_url = document.getElementById("ticketOpenThumbnail").value.trim();
      panel.options = collectTicketOptions();
      panel.permissions = {
        ticket_role_permissions: normalizeTicketRolePermissions(collectTicketRolePermissions()),
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
      const hasEmbed = Boolean(
        panel.ticket_open_title ||
        panel.ticket_open_description ||
        panel.ticket_open_footer ||
        panel.ticket_open_image_url ||
        panel.ticket_open_thumbnail_url
      );
      const embed = hasEmbed ? `
        <div class="discord-preview" style="${panel.ticket_open_color ? `border-left-color:${escapeHtml(panel.ticket_open_color)}` : ""}">
          ${panel.ticket_open_title ? `<div class="discord-preview-title">${escapeHtml(panel.ticket_open_title)}</div>` : ""}
          ${panel.ticket_open_description ? `<div class="discord-preview-description">${escapeHtml(panel.ticket_open_description)}</div>` : ""}
          ${panel.ticket_open_thumbnail_url ? `<div class="muted">Miniatura: ${escapeHtml(panel.ticket_open_thumbnail_url)}</div>` : ""}
          ${panel.ticket_open_image_url ? `<div class="muted">Imagen: ${escapeHtml(panel.ticket_open_image_url)}</div>` : ""}
          ${panel.ticket_open_footer ? `<div class="muted">${escapeHtml(panel.ticket_open_footer)}</div>` : ""}
        </div>
      ` : `<div class="muted">Sin embed configurado.</div>`;
      document.getElementById("ticketOpenPreview").innerHTML = `
        ${panel.ticket_open_content ? `<div class="discord-preview-description">${escapeHtml(panel.ticket_open_content)}</div>` : `<div class="muted">Sin mensaje superior.</div>`}
        ${embed}
        <div class="discord-preview-actions">
          <span class="discord-preview-action">Reclamar ticket</span>
          <span class="discord-preview-action">Cerrar ticket</span>
        </div>
      `;
    }

    function renderAlbionRegistration() {
      const config = state.albionRegistrationConfig || {};
      const roleSelect = document.getElementById("albionRole");
      const channelSelect = document.getElementById("albionLogChannel");
      roleSelect.innerHTML = `<option value="">Seleccionar rol</option>${state.ticketRoles.map(role =>
        `<option value="${escapeHtml(role.id)}">${escapeHtml(role.name)}</option>`
      ).join("")}`;
      channelSelect.innerHTML = `<option value="">Sin canal de registros</option>${state.ticketChannels.map(channel =>
        `<option value="${escapeHtml(channel.id)}"># ${escapeHtml(channel.name)}</option>`
      ).join("")}`;

      document.getElementById("albionGuildName").value = config.albion_guild_name || "";
      roleSelect.value = config.role_id || "";
      document.getElementById("albionLeaveAction").value = config.leave_action || "remove_roles";
      channelSelect.value = config.log_channel_id || "";
      document.getElementById("albionSyncNickname").checked = Boolean(config.sync_nickname);

      const active = state.albionRegistrations.filter(item => item.status === "active").length;
      document.getElementById("albionRegistrationTotal").textContent = state.albionRegistrations.length;
      document.getElementById("albionRegistrationActiveTotal").textContent = active;
      const body = document.getElementById("albionRegistrationsBody");
      body.innerHTML = state.albionRegistrations.map(item => `
        <tr>
          <td>${escapeHtml(item.discord_user_name || item.discord_user_id || "")}</td>
          <td>${escapeHtml(item.player_name || "")}</td>
          <td>${escapeHtml(item.albion_guild_name || "Sin gremio")}</td>
          <td>${escapeHtml(item.status === "active" ? "Activo" : item.status === "kicked" ? "Expulsado" : "Fuera del gremio")}</td>
          <td>${escapeHtml(item.last_checked_at || "")}</td>
        </tr>
      `).join("");
      document.getElementById("albionRegistrationsEmpty").hidden = state.albionRegistrations.length > 0;
    }

    function parseReportAmount(value) {
      const text = String(value || "").trim().toLowerCase().replace(",", ".");
      const suffixMatch = text.match(/(k|m|b|mil|millon|millones)\b/);
      const multipliers = {
        k: 1000,
        mil: 1000,
        m: 1000000,
        millon: 1000000,
        millones: 1000000,
        b: 1000000000
      };
      if (suffixMatch) {
        const amountMatch = text.match(/\d+(?:\.\d+)?/);
        if (!amountMatch) return 0;
        return Math.floor(Number(amountMatch[0]) * (multipliers[suffixMatch[1]] || 1));
      }
      const digits = text.replace(/\D/g, "");
      return digits ? Number(digits) : 0;
    }

    function reportCalculatorModeConfig(mode) {
      return {
        showItems: mode !== "silver",
        showSilver: mode !== "items",
        showCosts: mode !== "items",
        showBothExtras: mode === "items_silver"
      };
    }

    function parseReportPercentage(value) {
      const text = String(value || "").trim().replace(",", ".");
      const match = text.match(/\d+(?:\.\d+)?/);
      if (!match) return 0;
      return Math.max(0, Math.min(Number(match[0]), 100));
    }

    function setReportFieldVisible(fieldId, visible) {
      const field = document.getElementById(fieldId);
      if (field) field.hidden = !visible;
    }

    function applyReportModeVisibility(mode) {
      const config = reportCalculatorModeConfig(mode);
      setReportFieldVisible("reportItemsField", config.showItems);
      setReportFieldVisible("reportSilverField", config.showSilver);
      setReportFieldVisible("reportMapCostField", config.showCosts);
      setReportFieldVisible("reportRepairCostField", config.showCosts);
      setReportFieldVisible("reportCallerPercentField", config.showBothExtras);
      setReportFieldVisible("reportLooterPaymentField", config.showBothExtras);
      const looterPayment = config.showBothExtras ? parseReportAmount(document.getElementById("reportLooterPayment").value) : 0;
      setReportFieldVisible("reportLooterUserField", config.showBothExtras && looterPayment > 0);
      setReportFieldVisible("reportTabSaleField", config.showBothExtras);
      return config;
    }

    function populateReportLooterOptions(participants) {
      const select = document.getElementById("reportLooterUser");
      const selectedValue = select.value;
      select.innerHTML = `<option value="">Selecciona un integrante</option>` + participants.map(participant => (
        `<option value="${escapeHtml(participant.user_id)}">${escapeHtml(participant.display_name || participant.user_id)} - ${escapeHtml(participant.slot)}</option>`
      )).join("");
      if (participants.some(participant => participant.user_id === selectedValue)) {
        select.value = selectedValue;
      }
    }

    function reportParticipantOptionsMarkup(participants, selectedValue = "") {
      return `<option value="">Selecciona un integrante</option>` + participants.map(participant => {
        const selected = participant.user_id === selectedValue ? " selected" : "";
        return `<option value="${escapeHtml(participant.user_id)}"${selected}>${escapeHtml(participant.display_name || participant.user_id)} - ${escapeHtml(participant.slot)}</option>`;
      }).join("");
    }

    function syncReportFineParticipantOptions(participants) {
      document.querySelectorAll(".report-fine-user").forEach(select => {
        const previous = select.value;
        select.innerHTML = reportParticipantOptionsMarkup(participants, previous);
      });
    }

    async function fileToDataUrl(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ""));
        reader.onerror = () => reject(new Error("No pude leer la prueba adjunta."));
        reader.readAsDataURL(file);
      });
    }

    function bindReportFineRow(row) {
      row.querySelectorAll("select, input").forEach(element => {
        element.addEventListener("input", () => renderReportCalculator());
        element.addEventListener("change", () => renderReportCalculator());
      });
      row.querySelector(".report-fine-remove").addEventListener("click", () => {
        row.remove();
        renderReportCalculator();
      });
      row.querySelector(".report-fine-proof").addEventListener("change", async event => {
        const file = event.target.files?.[0];
        const label = row.querySelector(".report-fine-proof-name");
        if (!file) {
          event.target.dataset.proofDataUrl = "";
          event.target.dataset.proofName = "";
          label.textContent = "";
          return;
        }
        try {
          event.target.dataset.proofDataUrl = await fileToDataUrl(file);
          event.target.dataset.proofName = file.name;
          label.textContent = file.name;
        } catch (error) {
          event.target.value = "";
          event.target.dataset.proofDataUrl = "";
          event.target.dataset.proofName = "";
          label.textContent = error.message;
        }
      });
    }

    function appendReportFineRow(fine = {}) {
      const container = document.getElementById("reportFinesList");
      const participants = state.reportCalculator?.participants || [];
      const row = document.createElement("div");
      row.className = "report-fine-row";
      row.innerHTML = `
        <div class="field report-fine-user-field">
          <label>Jugador</label>
          <select class="report-fine-user">${reportParticipantOptionsMarkup(participants, fine.user_id || "")}</select>
        </div>
        <div class="field report-fine-amount-field">
          <label>Monto</label>
          <input class="report-fine-amount" type="text" placeholder="Ej: 1m" value="${escapeHtml(fine.amount || "")}">
        </div>
        <div class="field report-fine-reason-field">
          <label>Motivo</label>
          <input class="report-fine-reason" type="text" placeholder="Describe el motivo" value="${escapeHtml(fine.reason || "")}">
        </div>
        <div class="field report-fine-proof-field">
          <label>Prueba</label>
          <input class="report-fine-proof" type="file" accept="image/*">
          <div class="report-fine-proof-name">${escapeHtml(fine.proof_name || "")}</div>
        </div>
        <button class="action-button danger report-fine-remove" type="button">Quitar</button>
      `;
      const proofInput = row.querySelector(".report-fine-proof");
      if (fine.proof_data_url) proofInput.dataset.proofDataUrl = fine.proof_data_url;
      if (fine.proof_name) proofInput.dataset.proofName = fine.proof_name;
      bindReportFineRow(row);
      container.appendChild(row);
    }

    function collectReportFines() {
      return [...document.querySelectorAll(".report-fine-row")].map(row => {
        const userSelect = row.querySelector(".report-fine-user");
        const selectedOption = userSelect.options[userSelect.selectedIndex];
        const proofInput = row.querySelector(".report-fine-proof");
        return {
          user_id: userSelect.value,
          user_name: selectedOption?.textContent?.split(" - ")[0] || "",
          slot: selectedOption?.textContent?.split(" - ").slice(1).join(" - ") || "",
          amount: row.querySelector(".report-fine-amount").value,
          reason: row.querySelector(".report-fine-reason").value,
          proof_data_url: proofInput.dataset.proofDataUrl || "",
          proof_name: proofInput.dataset.proofName || "",
        };
      }).filter(fine => fine.user_id && fine.amount && fine.reason);
    }

    async function loadReportCalculatorOptions() {
      if (!state.guildId || !state.data?.viewer?.id) {
        state.reportCalculatorOptions = [];
        return;
      }
      const params = new URLSearchParams({ guild_id: state.guildId, list: "1" });
      const response = await fetch(`/api/report-calculator?${params.toString()}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude cargar los pings activos.");
      state.reportCalculatorOptions = payload.calculators || [];
      const currentAva = state.reportContext?.ava || "";
      if (!state.reportCalculatorOptions.length) {
        state.reportContext = null;
        state.reportCalculator = null;
        return;
      }
      const selected = state.reportCalculatorOptions.find(item => item.numero_ava === currentAva) || state.reportCalculatorOptions[0];
      state.reportContext = {
        guildId: state.guildId,
        callerId: state.data.viewer.id,
        ava: selected.numero_ava,
      };
    }

    function renderReportCalculatorOptions() {
      const select = document.getElementById("reportCalculatorSelect");
      const options = state.reportCalculatorOptions || [];
      const currentAva = state.reportContext?.ava || "";
      select.innerHTML = `<option value="">Selecciona una Ava</option>` + options.map(option => {
        const selected = option.numero_ava === currentAva ? " selected" : "";
        const suffix = option.report_rejected ? " - Rechazado" : option.report_sent ? " - Enviado" : "";
        return `<option value="${escapeHtml(option.numero_ava)}"${selected}>${escapeHtml(option.title)}${escapeHtml(suffix)}</option>`;
      }).join("");
      select.disabled = options.length === 0;
    }

    function reportCalculatorValues() {
      const participants = state.reportCalculator?.participants || [];
      const participantCount = participants.length;
      const mode = document.getElementById("reportSplitMode").value;
      const config = applyReportModeVisibility(mode);
      const items = config.showItems ? parseReportAmount(document.getElementById("reportItems").value) : 0;
      const silver = config.showSilver ? parseReportAmount(document.getElementById("reportSilver").value) : 0;
      const mapCost = config.showCosts ? parseReportAmount(document.getElementById("reportMapCost").value) : 0;
      const repairCost = config.showCosts ? parseReportAmount(document.getElementById("reportRepairCost").value) : 0;
      const callerPercent = config.showBothExtras ? parseReportPercentage(document.getElementById("reportCallerPercent").value) : 0;
      const callerPayment = config.showBothExtras ? Math.floor(silver * callerPercent / 100) : 0;
      const looterPayment = config.showBothExtras ? parseReportAmount(document.getElementById("reportLooterPayment").value) : 0;
      const looterUserId = config.showBothExtras && looterPayment > 0 ? document.getElementById("reportLooterUser").value : "";
      const tabSalePercent = config.showBothExtras ? parseReportPercentage(document.getElementById("reportTabSalePercent").value) : 0;
      const netSilver = Math.max(silver - callerPayment - looterPayment - mapCost - repairCost, 0);
      const soldTabValue = config.showBothExtras && tabSalePercent > 0
        ? Math.floor(items * ((100 - tabSalePercent) / 100))
        : 0;
      const splitParticipantCount = participantCount - (looterPayment > 0 && looterUserId ? 1 : 0);
      let itemPool = 0;
      let silverPool = 0;
      if (mode === "items") itemPool = items;
      else if (mode === "silver") silverPool = netSilver;
      else if (tabSalePercent > 0) silverPool = netSilver + soldTabValue;
      else {
        itemPool = items;
        silverPool = netSilver;
      }
      return {
        mode,
        config,
        items,
        silver,
        mapCost,
        repairCost,
        callerPercent,
        callerPayment,
        looterPayment,
        looterUserId,
        tabSalePercent,
        soldTabValue,
        splitParticipantCount: Math.max(splitParticipantCount, 0),
        itemPool,
        silverPool,
        total: itemPool + silverPool,
        itemPerUser: splitParticipantCount > 0 ? Math.floor(itemPool / splitParticipantCount) : 0,
        silverPerUser: splitParticipantCount > 0 ? Math.floor(silverPool / splitParticipantCount) : 0
      };
    }

    function renderReportCalculator() {
      const calculator = state.reportCalculator;
      const participants = calculator?.participants || [];
      renderReportCalculatorOptions();
      populateReportLooterOptions(participants);
      syncReportFineParticipantOptions(participants);
      const selectedLooterId = document.getElementById("reportLooterUser").value;
      document.getElementById("reportCalculatorParticipantsTotal").textContent = participants.length;
      document.getElementById("reportCalculatorSubtitle").textContent = calculator
        ? `${calculator.title} - Caller: ${calculator.caller_name || calculator.caller_id}`
        : "Abre esta seccion desde el boton Enviar informe de una Ava finalizada.";
      document.getElementById("reportParticipantsList").innerHTML = participants.length
        ? participants.map(participant => `
            <article class="report-participant-card">
              <div class="report-participant-head">
                <strong>${escapeHtml(`${participant.index}. ${participant.slot}`)}</strong>
                ${participant.user_id === selectedLooterId ? '<span class="report-participant-role">Looter</span>' : ''}
              </div>
              <span class="report-participant-name">${escapeHtml(participant.display_name || participant.user_id)}</span>
            </article>
          `).join("")
        : `<article class="report-participant-card">
              <div class="report-participant-head">
                <strong>Sin integrantes cargados</strong>
              </div>
              <span class="muted">Abre una Ava finalizada desde Discord.</span>
            </article>
          `;

      const values = reportCalculatorValues();
      document.getElementById("reportSplitParticipantsTotal").textContent = formatNumber(values.splitParticipantCount);
      document.getElementById("reportItemsPerUserStat").hidden = values.itemPool <= 0;
      document.getElementById("reportSilverPerUserStat").hidden = values.silverPool <= 0;
      document.getElementById("reportItemsPerUser").textContent = formatNumber(values.itemPerUser);
      document.getElementById("reportSilverPerUser").textContent = formatNumber(values.silverPerUser);
      document.getElementById("reportNetTotal").textContent = formatNumber(values.total);
      const breakdown = [];
      if (values.itemPool) {
        breakdown.push({
          label: "Items netos",
          value: formatNumber(values.itemPool),
          tone: "accent"
        });
      }
      if (values.silverPool) {
        breakdown.push({
          label: "Silver neto",
          value: formatNumber(values.silverPool),
          tone: "accent"
        });
      }
      if (values.config.showCosts) {
        if (values.callerPayment) {
          breakdown.push({
            label: `Caller (${values.callerPercent}%)`,
            value: `-${formatNumber(values.callerPayment)}`,
            tone: "negative"
          });
        }
        if (values.looterPayment) {
          breakdown.push({
            label: "Pago looter",
            value: `-${formatNumber(values.looterPayment)}`,
            tone: "negative"
          });
        }
        if (values.mapCost) {
          breakdown.push({
            label: "Mapa",
            value: `-${formatNumber(values.mapCost)}`,
            tone: "negative"
          });
        }
        if (values.repairCost) {
          breakdown.push({
            label: "Reparaciones",
            value: `-${formatNumber(values.repairCost)}`,
            tone: "negative"
          });
        }
      }
      document.getElementById("reportCalculatorBreakdown").innerHTML = breakdown.length
        ? breakdown.map(item => `
            <div class="report-breakdown-item ${item.tone ? escapeHtml(item.tone) : ""}">
              <span class="report-breakdown-label">${escapeHtml(item.label)}</span>
              <strong class="report-breakdown-value">${escapeHtml(item.value)}</strong>
            </div>
          `).join("")
        : `<div class="report-breakdown-empty">Completa los datos para calcular el reparto.</div>`;
      if (values.looterPayment && !values.looterUserId) {
        document.getElementById("reportCalculatorBreakdown").innerHTML += `
          <div class="report-breakdown-empty">Selecciona quien fue el looter para excluirlo del split.</div>
        `;
      }
      document.getElementById("submitReportCalculatorButton").disabled = !calculator || calculator.report_sent || calculator.cancelled || !calculator.finalized || (values.looterPayment > 0 && !values.looterUserId);
    }

    function resetReportCalculator() {
      ["reportEstimated", "reportItems", "reportSilver", "reportMapCost", "reportRepairCost", "reportCallerPercent", "reportLooterPayment", "reportLooterUser", "reportTabSalePercent"].forEach(id => {
        document.getElementById(id).value = "";
      });
      document.getElementById("reportFinesList").innerHTML = "";
      document.getElementById("reportCalculatorStatus").textContent = "";
      renderReportCalculator();
    }

    async function loadReportCalculator() {
      renderReportCalculatorOptions();
      if (!state.reportContext) {
        state.reportCalculator = null;
        renderReportCalculator();
        return;
      }
      const params = new URLSearchParams({
        guild_id: state.reportContext.guildId,
        caller_id: state.reportContext.callerId,
        ava: state.reportContext.ava
      });
      const response = await fetch(`/api/report-calculator?${params.toString()}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) {
        state.reportCalculator = null;
        renderReportCalculator();
        if (response.status === 404) {
          throw new Error("Esta Ava ya no esta activa o ya fue cerrada. Abrela de nuevo desde Discord.");
        }
        throw new Error(payload.error || "No pude cargar la calculadora.");
      }
      state.reportCalculator = payload.calculator;
      document.getElementById("reportFinesList").innerHTML = "";
      state.guildId = payload.calculator.guild_id;
      renderReportCalculator();
    }

    async function submitReportCalculator() {
      if (!state.reportCalculator) throw new Error("No hay una Ava cargada.");
      const status = document.getElementById("reportCalculatorStatus");
      const mode = document.getElementById("reportSplitMode").value;
      const config = reportCalculatorModeConfig(mode);
      status.textContent = "Enviando informe al bot...";
      const response = await fetch("/api/report-calculator", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.reportCalculator.guild_id,
          caller_id: state.reportCalculator.caller_id,
          numero_ava: state.reportCalculator.numero_ava,
          split_mode: mode,
          estimated: document.getElementById("reportEstimated").value,
          items: config.showItems ? document.getElementById("reportItems").value : "",
          silver: config.showSilver ? document.getElementById("reportSilver").value : "",
          costs: config.showCosts ? `mapa=${document.getElementById("reportMapCost").value}; repa=${document.getElementById("reportRepairCost").value}` : "",
          caller_percentage: config.showBothExtras ? document.getElementById("reportCallerPercent").value : "",
          looter_payment: config.showBothExtras ? document.getElementById("reportLooterPayment").value : "",
          looter_user_id: config.showBothExtras ? document.getElementById("reportLooterUser").value : "",
          tab_sale_percentage: config.showBothExtras ? document.getElementById("reportTabSalePercent").value : "",
          adjustments: "",
          fines: collectReportFines(),
        })
      });
      const payload = await response.json();
      if (!response.ok) {
        if (response.status === 404) {
          state.reportCalculator = null;
          renderReportCalculator();
          throw new Error("Esta Ava ya no esta activa o ya fue cerrada. Abrela de nuevo desde Discord.");
        }
        throw new Error(payload.error || "No pude enviar el informe.");
      }
      state.reportRequestId = payload.request.id;
      status.textContent = "El bot esta procesando el informe...";
      await pollReportRequest();
    }

    async function pollReportRequest() {
      if (!state.reportRequestId) return;
      const params = new URLSearchParams({ request_id: state.reportRequestId });
      const response = await fetch(`/api/report-calculator?${params.toString()}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude consultar el envio.");
      const request = payload.request;
      if (request.status === "completed") {
        document.getElementById("reportCalculatorStatus").textContent = "Informe enviado a evaluacion.";
        state.reportCalculator.report_sent = true;
        renderReportCalculator();
        return;
      }
      if (request.status === "error") {
        throw new Error(request.error || "El bot no pudo enviar el informe.");
      }
      setTimeout(() => pollReportRequest().catch(error => {
        document.getElementById("reportCalculatorStatus").textContent = error.message;
      }), 1500);
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
      const sidebarToggle = document.getElementById("sidebarToggle");
      const sidebarToggleLabel = state.sidebarCollapsed ? "Expandir secciones" : "Minimizar secciones";
      sidebarToggle.setAttribute("aria-label", sidebarToggleLabel);
      sidebarToggle.title = sidebarToggleLabel;
      sidebarToggle.setAttribute("aria-expanded", String(!state.sidebarCollapsed));
      if (!canUseSection(state.section)) {
        const firstAllowed = [...document.querySelectorAll(".section-button")]
          .find(button => canUseSection(button.dataset.section));
        state.section = firstAllowed?.dataset.section || "tickets";
        localStorage.setItem("dashboardSection", state.section);
      }
      document.getElementById("economySection").hidden = state.section !== "economy";
      document.getElementById("templatesSection").hidden = state.section !== "templates";
      document.getElementById("lootSection").hidden = state.section !== "loot";
      document.getElementById("ticketsSection").hidden = state.section !== "tickets";
      document.getElementById("reportCalculatorSection").hidden = state.section !== "report-calculator";
      document.getElementById("registrationSection").hidden = state.section !== "registration";
      document.getElementById("welcomeSection").hidden = state.section !== "welcome";
      document.getElementById("auditSection").hidden = state.section !== "audit";
      document.getElementById("permissionsSection").hidden = state.section !== "permissions";
      document.getElementById("searchInput").hidden = state.section !== "economy";
      document.querySelectorAll(".section-button").forEach(button => {
        button.hidden = !canUseSection(button.dataset.section);
        const active = button.dataset.section === state.section;
        button.classList.toggle("active", active);
        if (active) button.setAttribute("aria-current", "page");
        else button.removeAttribute("aria-current");
      });
    }

    function canUseSection(section) {
      const access = state.data?.access || {};
      if (access.admin) return true;
      if (section === "tickets") return Boolean(access.tickets);
      if (section === "permissions") return Boolean(access.permissions);
      if (section === "report-calculator") return Boolean(state.guildId);
      return false;
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
        fines: [],
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
      await loadReportCalculatorOptions();
      await loadReportCalculator();
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
      const [panelsResponse, channelsResponse, categoriesResponse, emojisResponse, rolesResponse, recordsResponse, auditResponse, auditEventsResponse, templatesResponse, botPermissionsResponse, albionRegistrationResponse, fineConfigResponse] = await Promise.all([
        fetch(`/api/ticket-panels?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/discord-channels?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/discord-categories?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/discord-emojis?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/discord-roles?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/ticket-records?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/audit-config?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/audit-events?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/ping-templates?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/bot-permissions?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/albion-registration?${params.toString()}`, { cache: "no-store" }),
        fetch(`/api/fine-config?${params.toString()}`, { cache: "no-store" })
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
        state.ticketRecordsSummary = payload.summary || {};
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
      if (albionRegistrationResponse.ok) {
        const payload = await albionRegistrationResponse.json();
        state.albionRegistrationConfig = payload.config || null;
        state.albionRegistrations = payload.registrations || [];
      }
      if (fineConfigResponse.ok) {
        state.fineConfig = await fineConfigResponse.json();
      }
      state.ticketConfigGuildId = state.guildId;
      state.ticketPanelsDirty = false;
      if (!state.ticketPanels.some(panel => panel.id === state.currentTicketPanelId)) {
        state.currentTicketPanelId = "";
        localStorage.removeItem("dashboardTicketPanelId");
      }
    }

    async function loadTicketRecordsLive() {
      if (!state.guildId) return;
      const params = new URLSearchParams({ guild_id: state.guildId });
      const response = await fetch(`/api/ticket-records?${params.toString()}`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude cargar tickets en vivo.");
      state.ticketRecords = payload.records || [];
      state.ticketRecordsSummary = payload.summary || {};
      renderTicketLiveSummary();
      renderTicketRecords();
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

    async function saveAlbionRegistration() {
      const status = document.getElementById("albionRegistrationStatus");
      status.textContent = "Validando el gremio en Albion Online...";
      const response = await fetch("/api/albion-registration", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          albion_guild_name: document.getElementById("albionGuildName").value.trim(),
          role_id: document.getElementById("albionRole").value,
          leave_action: document.getElementById("albionLeaveAction").value,
          log_channel_id: document.getElementById("albionLogChannel").value,
          sync_nickname: document.getElementById("albionSyncNickname").checked
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude guardar el registro de Albion.");
      state.albionRegistrationConfig = payload.config || null;
      state.albionRegistrations = payload.registrations || [];
      renderAlbionRegistration();
      status.textContent = `Configuracion guardada para ${payload.config?.albion_guild_name || "el gremio"}.`;
    }

    async function saveFineConfig() {
      const response = await fetch("/api/fine-config", {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          guild_id: state.guildId,
          channel_id: document.getElementById("fineChannel").value,
          blocked_role_id: document.getElementById("fineBlockedRole").value,
          resolver_role_id: document.getElementById("fineResolverRole").value,
          ticket_category_id: document.getElementById("fineTicketCategory").value,
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "No pude guardar la configuracion de multas.");
      state.fineConfig = payload;
      document.getElementById("fineConfigStatus").textContent = "Configuracion de multas guardada.";
      renderFineConfig();
    }

    async function publishCurrentTicketPanel() {
      persistCurrentTicketPanel();
      if (state.ticketPanelsDirty) {
        await saveTicketPanels();
      }
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
        if (!canUseSection(button.dataset.section)) return;
        state.section = button.dataset.section;
        localStorage.setItem("dashboardSection", state.section);
        render();
      });
    });

    document.getElementById("lootFileInput").addEventListener("change", event => {
      const file = event.target.files?.[0];
      loadLootFile(file)
        .catch(showLootError)
        .finally(() => {
          event.target.value = "";
        });
    });

    document.getElementById("lootReplaceButton").addEventListener("click", () => {
      document.getElementById("lootFileInput").value = "";
      document.getElementById("lootFileInput").click();
    });

    document.getElementById("lootClearButton").addEventListener("click", clearLoot);

    document.getElementById("lootIconSize").addEventListener("input", event => {
      state.loot.iconSize = Number(event.target.value);
      renderLoot();
    });

    document.getElementById("lootGroupToggle").addEventListener("click", () => {
      state.loot.groupByTier = !state.loot.groupByTier;
      renderLoot();
    });

    const lootDropzone = document.getElementById("lootDropzone");
    ["dragenter", "dragover"].forEach(eventName => {
      lootDropzone.addEventListener(eventName, event => {
        event.preventDefault();
        lootDropzone.classList.add("dragging");
      });
    });
    ["dragleave", "drop"].forEach(eventName => {
      lootDropzone.addEventListener(eventName, event => {
        event.preventDefault();
        lootDropzone.classList.remove("dragging");
      });
    });
    lootDropzone.addEventListener("drop", event => {
      loadLootFile(event.dataTransfer?.files?.[0]).catch(showLootError);
    });

    document.getElementById("lootTierButtons").addEventListener("click", event => {
      const button = event.target.closest("[data-loot-tier]");
      if (button) toggleLootTier(Number(button.dataset.lootTier));
    });

    document.getElementById("lootPlayers").addEventListener("click", event => {
      const detail = event.target.closest("[data-loot-detail-item]");
      if (detail) {
        showLootDetail(detail.dataset.lootDetailPlayer, detail.dataset.lootDetailItem);
        return;
      }
      const item = event.target.closest("[data-loot-item]");
      if (item) toggleLootItem(item.dataset.lootPlayer, item.dataset.lootItem);
    });

    document.getElementById("lootModal").addEventListener("click", event => {
      if (event.target.id === "lootModal" || event.target.closest("[data-loot-modal-close]")) {
        closeLootDetail();
      }
    });

    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && !document.getElementById("lootModal").hidden) closeLootDetail();
    });

    document.querySelectorAll(".editor-tab").forEach(button => {
      button.addEventListener("click", () => {
        state.ticketEditorSection = button.dataset.editorSection;
        localStorage.setItem("dashboardTicketEditorSection", state.ticketEditorSection);
        renderTicketEditorSections();
      });
    });

    ["ticketName", "ticketMode", "ticketChannel", "ticketOpenCategory", "ticketColor", "ticketContent", "ticketTitle", "ticketFooter", "ticketDescription", "ticketImage", "ticketOpenContent", "ticketOpenTitle", "ticketOpenColor", "ticketOpenDescription", "ticketOpenFooter", "ticketOpenImage", "ticketOpenThumbnail", "claimRoles", "closeRoles", "reopenRoles", "deleteRoles"].forEach(id => {
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
      loadTicketRecordsLive().catch(error => {
        document.getElementById("ticketLiveStatus").textContent = error.message;
      });
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

    document.getElementById("closeLiveTicketButton").addEventListener("click", () => {
      closeLiveTicket();
    });

    document.getElementById("ticketLiveForm").addEventListener("submit", event => {
      event.preventDefault();
      sendLiveTicketMessage().catch(error => {
        document.getElementById("ticketLiveMessageStatus").textContent = error.message;
      });
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
      document.getElementById("ticketStatus").textContent = "Panel clonado. Guarda la configuracion y envia este panel a Discord para que tenga numeracion propia.";
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

    document.getElementById("addTicketPermissionRoleButton").addEventListener("click", () => {
      persistCurrentTicketPanel();
      const panel = currentTicketPanel();
      if (!panel) return;
      panel.permissions = panel.permissions || {};
      const entries = Array.isArray(panel.permissions.ticket_role_permissions)
        ? panel.permissions.ticket_role_permissions
        : [];
      if (entries.length >= 20) {
        document.getElementById("ticketStatus").textContent = "Puedes configurar maximo 20 roles con permisos de canal.";
        return;
      }
      entries.push({
        role_id: "",
        permissions: ["view_channel", "read_message_history"]
      });
      panel.permissions.ticket_role_permissions = entries;
      state.ticketPanelsDirty = true;
      renderTicketRolePermissions(panel);
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

    document.getElementById("saveFineConfigButton").addEventListener("click", () => {
      saveFineConfig().catch(error => {
        document.getElementById("fineConfigStatus").textContent = error.message;
      });
    });

    document.getElementById("savePermissionsButton").addEventListener("click", () => {
      state.botPermissions = collectBotPermissions();
      saveBotPermissions().catch(error => {
        document.getElementById("permissionsStatus").textContent = error.message;
      });
    });

    document.getElementById("exportEconomyButton").addEventListener("click", () => {
      if (!state.guildId) return;
      window.location.href = `/api/export/economy?${new URLSearchParams({ guild_id: state.guildId }).toString()}`;
    });

    document.getElementById("exportTemplatesButton").addEventListener("click", () => {
      if (!state.guildId) return;
      window.location.href = `/api/export/templates?${new URLSearchParams({ guild_id: state.guildId }).toString()}`;
    });

    document.getElementById("exportTicketsButton").addEventListener("click", () => {
      if (!state.guildId) return;
      window.location.href = `/api/export/tickets?${new URLSearchParams({ guild_id: state.guildId }).toString()}`;
    });

    document.getElementById("saveAlbionRegistrationButton").addEventListener("click", () => {
      saveAlbionRegistration().catch(error => {
        document.getElementById("albionRegistrationStatus").textContent = error.message;
      });
    });

    ["reportSplitMode", "reportEstimated", "reportItems", "reportSilver", "reportMapCost", "reportRepairCost", "reportCallerPercent", "reportLooterPayment", "reportLooterUser", "reportTabSalePercent"].forEach(id => {
      document.getElementById(id).addEventListener("input", renderReportCalculator);
      document.getElementById(id).addEventListener("change", renderReportCalculator);
    });

    document.getElementById("addReportFineButton").addEventListener("click", () => {
      appendReportFineRow();
      renderReportCalculator();
    });

    document.getElementById("reportCalculatorSelect").addEventListener("change", event => {
      const ava = event.target.value;
      if (!ava) {
        state.reportContext = null;
        state.reportCalculator = null;
        renderReportCalculator();
        return;
      }
      state.reportContext = {
        guildId: state.guildId,
        callerId: state.data?.viewer?.id || "",
        ava,
      };
      loadReportCalculator().catch(error => {
        document.getElementById("reportCalculatorStatus").textContent = error.message;
      });
    });

    document.getElementById("submitReportCalculatorButton").addEventListener("click", () => {
      submitReportCalculator().catch(error => {
        document.getElementById("reportCalculatorStatus").textContent = error.message;
      });
    });

    document.getElementById("resetReportCalculatorButton").addEventListener("click", resetReportCalculator);

    document.getElementById("refreshAlbionRegistrationButton").addEventListener("click", () => {
      state.ticketConfigGuildId = "";
      loadTicketConfig().then(() => {
        renderAlbionRegistration();
        document.getElementById("albionRegistrationStatus").textContent = "Registro recargado.";
      }).catch(error => {
        document.getElementById("albionRegistrationStatus").textContent = error.message;
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

    setInterval(() => {
      if (state.section !== "tickets") return;
      loadTicketRecordsLive().catch(error => {
        document.getElementById("ticketLiveStatus").textContent = error.message;
      });
      if (state.selectedLiveTicketId) {
        loadLiveTicketMessages().catch(error => {
          document.getElementById("ticketLiveMessageStatus").textContent = error.message;
        });
      }
    }, 5000);
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

    def send_bytes(self, status, content, content_type, headers=None):
        payload = content if isinstance(content, bytes) else bytes(content)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

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

    def is_guild_admin(self, session, guild_id):
        return str(guild_id) in {guild["id"] for guild in session.get("admin_guilds", [])}

    def session_member_guild_ids(self, session):
        return {
            str(guild.get("id"))
            for guild in (session.get("guilds") or session.get("admin_guilds", []))
            if guild.get("id")
        }

    def session_has_bot_permission(self, session, guild_id, permission):
        guild_id = str(guild_id or "")
        if not guild_id:
            return False
        bot_guild_ids = get_bot_guild_ids()
        if bot_guild_ids is not None and guild_id not in bot_guild_ids:
            return False
        if self.is_guild_admin(session, guild_id):
            return True
        if guild_id not in self.session_member_guild_ids(session):
            return False
        role_ids = get_discord_member_role_ids(guild_id, session.get("user", {}).get("id"))
        return role_ids_have_permission(guild_id, role_ids, permission)

    def can_access_tickets(self, session, guild_id):
        return self.session_has_bot_permission(session, guild_id, PERMISSION_TICKETS)

    def can_access_guild_or_tickets(self, session, guild_id):
        return self.can_access_guild(session, guild_id) or self.can_access_tickets(session, guild_id)

    def dashboard_allowed_guilds(self, session):
        bot_guild_ids = get_bot_guild_ids()
        allowed = {
            guild["id"]: guild["name"]
            for guild in session.get("admin_guilds", [])
            if bot_guild_ids is None or str(guild["id"]) in bot_guild_ids
        }
        user_id = session.get("user", {}).get("id")
        for guild in session.get("guilds", []):
            guild_id = str(guild.get("id") or "")
            if not guild_id or guild_id in allowed:
                continue
            if bot_guild_ids is not None and guild_id not in bot_guild_ids:
                continue
            role_ids = get_discord_member_role_ids(guild_id, user_id)
            if role_ids_have_permission(guild_id, role_ids, PERMISSION_TICKETS):
                allowed[guild_id] = str(guild.get("name") or f"Servidor {guild_id}")
        return allowed

    def dashboard_access_payload(self, session, guild_id):
        admin = self.is_guild_admin(session, guild_id)
        return {
            "admin": admin,
            "tickets": self.can_access_tickets(session, guild_id),
            "permissions": self.session_has_bot_permission(session, guild_id, PERMISSION_PERMISSIONS),
        }

    def can_access_report_calculator(self, session, guild_id, caller_id):
        member_guilds = {
            guild["id"]
            for guild in (session.get("guilds") or session.get("admin_guilds", []))
        }
        bot_guild_ids = get_bot_guild_ids()
        return (
            str(session.get("user", {}).get("id") or "") == str(caller_id)
            and str(guild_id) in member_guilds
            and (bot_guild_ids is None or str(guild_id) in bot_guild_ids)
        )

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
        next_path = safe_dashboard_next(query.get("next", ["/dashboard"])[0])
        state = secrets.token_urlsafe(24)
        params = urlencode({
            "client_id": DASHBOARD_CLIENT_ID,
            "redirect_uri": self.get_redirect_uri(),
            "response_type": "code",
            "scope": "identify guilds",
            "state": state,
        })
        remember_oauth_state(state, remember_device, next_path)
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
            guilds_from_discord(guilds),
            remember_device=state_payload.get("remember_device", False),
        )
        ttl = REMEMBER_SESSION_TTL_SECONDS if state_payload.get("remember_device", False) else SESSION_TTL_SECONDS
        headers = {
            "Set-Cookie": make_cookie_value(encode_session_cookie(session_id), ttl),
        }
        self.send_redirect(
            safe_dashboard_next(state_payload.get("next_path")),
            headers=headers,
        )

    def handle_logout(self):
        clear_session_from_request(self)
        self.send_redirect(
            "/",
            headers={"Set-Cookie": make_cookie_value("", 0)},
        )

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            query = parse_qs(parsed.query)
            next_path = safe_dashboard_next(query.get("next", ["/dashboard"])[0])
            if get_session_from_request(self):
                self.send_redirect(next_path)
                return

            login_html = LOGIN_HTML.replace(
                '<form action="/login" method="get">',
                (
                    '<form action="/login" method="get">'
                    f'<input type="hidden" name="next" value="{html.escape(next_path, quote=True)}">'
                ),
            )
            self.send_text(200, login_html, "text/html")
            return

        if parsed.path == "/dashboard":
            if not get_session_from_request(self):
                self.send_redirect(
                    f"/?next={urlencode({'value': self.path})[6:]}"
                )
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
                allowed_guilds = self.dashboard_allowed_guilds(session)
                payload = build_dashboard_data(
                    guild_id,
                    allowed_guilds=allowed_guilds,
                    bot_guild_ids=get_bot_guild_ids(),
                    viewer=session.get("user", {}),
                )
                payload["csrf_token"] = session.get("csrf_token", "")
                payload["access"] = self.dashboard_access_payload(session, payload.get("selectedGuildId"))
                if payload.get("selectedGuildId") and not payload["access"].get("admin"):
                    payload["balances"] = []
                    payload["operations"] = []
                    payload["avalonians"] = []
                    payload["reports"] = []
                    payload["fines"] = []
                    payload["totals"] = {"players": 0, "items": 0, "silver": 0, "total": 0}
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
            if not guild_id or not self.can_access_tickets(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            self.send_json(200, {"panels": get_guild_ticket_panels(guild_id)})
            return

        if parsed.path == "/api/report-calculator":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            caller_id = query.get("caller_id", [""])[0]
            numero_ava = query.get("ava", [""])[0]
            request_id = query.get("request_id", [""])[0]
            if query.get("list", [""])[0] == "1":
                caller_id = str(session.get("user", {}).get("id") or "")
                if not guild_id or not self.can_access_report_calculator(session, guild_id, caller_id):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return
                self.send_json(200, {"calculators": get_active_report_calculators_for_user(guild_id, caller_id)})
                return
            if request_id:
                request = ReportDashboardRepository().get(request_id)
                payload = request.get("payload", {}) if request else {}
                if (
                    not request
                    or not self.can_access_report_calculator(
                        session,
                        payload.get("guild_id"),
                        payload.get("caller_id"),
                    )
                ):
                    self.send_json(404, {"error": "No encontre esa solicitud."})
                    return
                self.send_json(200, {"request": request})
                return

            if not self.can_access_report_calculator(session, guild_id, caller_id):
                self.send_json(403, {"error": "Solo el caller puede abrir esta calculadora."})
                return

            state = get_active_avalonian_state(guild_id, caller_id, numero_ava)
            if not state:
                self.send_json(404, {"error": "Esta Ava ya no esta activa o ya fue cerrada. Abrela de nuevo desde Discord."})
                return
            self.send_json(200, {"calculator": serialize_report_calculator_state(state)})
            return

        if parsed.path == "/api/fine-config":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_guild_or_tickets(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return
            self.send_json(200, get_fine_config_payload(guild_id))
            return

        if parsed.path == "/api/fines":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_guild_or_tickets(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return
            self.send_json(200, get_guild_fines_payload(guild_id))
            return

        if parsed.path in {"/api/export/economy", "/api/export/templates", "/api/export/tickets"}:
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_guild_or_tickets(session, guild_id):
                self.send_text(403, "No tienes acceso a ese servidor.", "text/plain")
                return

            guild_name = next(
                (guild.get("name") for guild in session.get("guilds", []) if str(guild.get("id")) == str(guild_id)),
                f"Servidor {guild_id}",
            )
            if parsed.path == "/api/export/economy":
                payload = build_dashboard_data(guild_id).copy()
                export_data = {
                    "guild_id": guild_id,
                    "guild_name": guild_name,
                    "balances": payload.get("balances", []),
                    "operations": payload.get("operations", []),
                    "avalonians": payload.get("avalonians", []),
                    "reports": payload.get("reports", []),
                    "fines": payload.get("fines", []),
                }
                file_name = f"economia_{guild_id}.json"
            elif parsed.path == "/api/export/templates":
                export_data = {
                    "guild_id": guild_id,
                    "guild_name": guild_name,
                    "templates": PingTemplateService().get_templates(guild_id, include_scratch=True),
                }
                file_name = f"plantillas_{guild_id}.json"
            else:
                export_data = {
                    "guild_id": guild_id,
                    "guild_name": guild_name,
                    "panels": get_guild_ticket_panels(guild_id),
                    "records": get_guild_ticket_records(guild_id),
                }
                file_name = f"tickets_{guild_id}.json"
            self.send_bytes(
                200,
                json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8"),
                "application/json",
                headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
            )
            return

        if parsed.path == "/api/albion-registration":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_guild_or_tickets(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            try:
                self.send_json(200, get_albion_registration_payload(guild_id))
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        if parsed.path == "/api/discord-channels":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_guild_or_tickets(session, guild_id):
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
            if not guild_id or not self.can_access_guild_or_tickets(session, guild_id):
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
            if not guild_id or not self.can_access_guild_or_tickets(session, guild_id):
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
            if not guild_id or not self.can_access_guild_or_tickets(session, guild_id):
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
            if not guild_id or not self.can_access_tickets(session, guild_id):
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
            if not guild_id or not self.can_access_tickets(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            records = get_guild_ticket_records(guild_id)
            self.send_json(200, {
                "records": records,
                "summary": ticket_records_summary(records),
            })
            return

        if parsed.path == "/api/ticket-live":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            channel_id = query.get("channel_id", [""])[0]
            if not guild_id or not self.can_access_guild(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return
            record = get_ticket_record(guild_id, channel_id)
            if not record:
                self.send_json(404, {"error": "No encontre ese ticket."})
                return

            try:
                messages = discord_json_request(
                    f"/channels/{channel_id}/messages?limit=50",
                    token=BOT_TOKEN,
                    auth_scheme="Bot",
                )
                serialized = [serialize_discord_message(message) for message in reversed(messages)]
                self.send_json(200, {
                    "messages": serialized,
                    "updated_at": datetime.now(ARGENTINA_TZ).strftime("%d/%m/%Y | %H:%M:%S"),
                })
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
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
        if parsed.path == "/api/report-calculator":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                guild_id = str(body.get("guild_id") or "")
                caller_id = str(body.get("caller_id") or "")
                numero_ava = str(body.get("numero_ava") or "")
                if not self.can_access_report_calculator(session, guild_id, caller_id):
                    self.send_json(403, {"error": "Solo el caller puede enviar este informe."})
                    return

                state = get_active_avalonian_state(guild_id, caller_id, numero_ava)
                if not state:
                    self.send_json(404, {"error": "Esta Ava ya no esta activa o ya fue cerrada. Abrela de nuevo desde Discord."})
                    return
                if not state.get("finalized") or state.get("cancelled") or state.get("report_sent"):
                    self.send_json(400, {"error": "Esta Ava no esta disponible para enviar informe."})
                    return

                split_mode = str(body.get("split_mode") or "")
                if split_mode not in {"items", "silver", "items_silver"}:
                    self.send_json(400, {"error": "Selecciona un modo de reparto valido."})
                    return

                fines = []
                raw_fines = body.get("fines", [])
                if isinstance(raw_fines, list):
                    for index, entry in enumerate(raw_fines, start=1):
                        if not isinstance(entry, dict):
                            continue
                        proof_path = ""
                        proof_name = ""
                        if entry.get("proof_data_url"):
                            proof_path, proof_name = store_embedded_image(
                                entry.get("proof_data_url"),
                                prefix=f"{guild_id}_{caller_id}_{numero_ava}_{index}_{int(time.time())}",
                            )
                        fines.append(
                            {
                                "user_id": str(entry.get("user_id") or ""),
                                "user_name": str(entry.get("user_name") or "")[:120],
                                "slot": str(entry.get("slot") or "")[:80],
                                "amount": str(entry.get("amount") or "")[:50],
                                "reason": str(entry.get("reason") or "")[:300],
                                "proof_path": proof_path,
                                "proof_name": proof_name or str(entry.get("proof_name") or "")[:120],
                            }
                        )

                request = ReportDashboardRepository().create({
                    "guild_id": guild_id,
                    "caller_id": caller_id,
                    "numero_ava": numero_ava,
                    "estimated": str(body.get("estimated") or "")[:50],
                    "silver": str(body.get("silver") or "")[:50],
                    "items": str(body.get("items") or "")[:50],
                    "costs": str(body.get("costs") or "")[:120],
                    "caller_percentage": str(body.get("caller_percentage") or "")[:20],
                    "looter_payment": str(body.get("looter_payment") or "")[:50],
                    "looter_user_id": str(body.get("looter_user_id") or "")[:30],
                    "tab_sale_percentage": str(body.get("tab_sale_percentage") or "")[:20],
                    "adjustments": str(body.get("adjustments") or "")[:500],
                    "fines": fines,
                    "split_mode": split_mode,
                })
                self.send_json(202, {"request": request})
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        if parsed.path == "/api/fine-config":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                guild_id = str(body.get("guild_id") or "")
                if not guild_id or not self.can_access_guild_or_tickets(session, guild_id):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return
                self.send_json(200, save_fine_config(guild_id, body))
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        if parsed.path == "/api/albion-registration":
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

                self.send_json(
                    200,
                    save_albion_registration_config(guild_id, body),
                )
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
            return

        if parsed.path == "/api/ticket-panels":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                guild_id = str(body.get("guild_id") or "")
                if not guild_id or not self.can_access_tickets(session, guild_id):
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
                if not guild_id or not self.can_access_tickets(session, guild_id):
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

        if parsed.path == "/api/ticket-live-message":
            session = self.get_authenticated_session()
            if not session:
                return

            try:
                body = self.read_json_body()
                guild_id = str(body.get("guild_id") or "")
                channel_id = str(body.get("channel_id") or "")
                content = str(body.get("content") or "").strip()
                if not guild_id or not self.can_access_tickets(session, guild_id):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return
                record = get_ticket_record(guild_id, channel_id)
                if not channel_id or not record:
                    self.send_json(404, {"error": "No encontre ese ticket."})
                    return
                if str(record.get("status") or "open").lower() != "open":
                    self.send_json(400, {"error": "Solo puedes responder tickets abiertos."})
                    return
                if not content:
                    self.send_json(400, {"error": "El mensaje no puede estar vacio."})
                    return
                if len(content) > 1800:
                    self.send_json(400, {"error": "El mensaje es demasiado largo."})
                    return

                viewer = session.get("user", {}).get("username") or "Dashboard"
                result = discord_json_request(
                    f"/channels/{channel_id}/messages",
                    token=BOT_TOKEN,
                    auth_scheme="Bot",
                    method="POST",
                    payload={
                        "content": f"**{viewer} desde dashboard:**\n{content}",
                        "allowed_mentions": {"parse": []},
                    },
                )
                self.send_json(200, {"message": serialize_discord_message(result)})
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
        if parsed.path == "/api/ticket-record":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                guild_id = str(body.get("guild_id") or "")
                record_id = str(body.get("record_id") or "")
                if not guild_id or not self.can_access_tickets(session, guild_id):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return
                if not record_id:
                    self.send_json(400, {"error": "No se indico el ticket."})
                    return
                record = get_ticket_record(guild_id, record_id)
                if not record:
                    self.send_json(404, {"error": "No encontre ese ticket."})
                    return
                if str(record.get("status") or "open").lower() == "open":
                    self.send_json(400, {"error": "Primero debes cerrar o eliminar el ticket de Discord."})
                    return
                if not delete_guild_ticket_record(guild_id, record_id):
                    self.send_json(404, {"error": "No pude eliminar el registro del ticket."})
                    return

                records = get_guild_ticket_records(guild_id)
                self.send_json(200, {
                    "records": records,
                    "summary": ticket_records_summary(records),
                })
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
