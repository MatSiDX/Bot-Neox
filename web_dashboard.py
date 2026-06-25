import argparse
import base64
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
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

from config.settings import (
    AVALON_BOT_LOGO_FILE,
    DASHBOARD_BOT_TOKEN,
    DASHBOARD_CLIENT_ID,
    DASHBOARD_CLIENT_SECRET,
    DISCORD_METADATA_CATEGORIES_TTL_SECONDS,
    DISCORD_METADATA_CHANNELS_TTL_SECONDS,
    DISCORD_METADATA_EMOJIS_TTL_SECONDS,
    DISCORD_METADATA_ROLES_TTL_SECONDS,
    DISCORD_METADATA_STALE_FALLBACK_SECONDS,
    DASHBOARD_REDIRECT_URI,
    DASHBOARD_SESSIONS_FILE,
    DASHBOARD_SESSION_SECRET,
    validate_dashboard_startup,
)
from src.neox.dashboard.assets import (
    load_dashboard_template,
    resolve_dashboard_static_path,
)
from src.neox.dashboard.auth import (
    admin_guilds_from_discord as auth_admin_guilds_from_discord,
    guilds_from_discord as auth_guilds_from_discord,
    oauth_configured as auth_oauth_configured,
)
from src.neox.dashboard.bootstrap import select_dashboard_guilds
from src.neox.dashboard.http_utils import (
    ARGENTINA_TZ,
    argentina_now_display,
    clean_user_name,
    format_argentina_datetime,
    format_number,
)
from src.neox.dashboard.security import DashboardCookieManager, safe_dashboard_next
from src.neox.dashboard.sessions import DashboardSessionStore
from repositories.database import DATABASE_FILE, init_database
from repositories.albion_registration_repository import AlbionRegistrationRepository
from repositories.active_avalonian_repository import ACTIVE_AVALONIAN_FILE
from repositories.balance_repository import BalanceRepository, DATA_DIR
from repositories.dashboard_json_repository import DashboardJsonRepository
from repositories.fine_repository import FineRepository
from repositories.operation_repository import OperationRepository
from repositories.pagination import normalize_page, normalize_page_size, page_response
from repositories.report_dashboard_repository import ReportDashboardRepository
from services.config_service import ConfigService
from services.dashboard_action_service import DashboardActionService
from services.discord_metadata_service import DiscordMetadataCacheSettings, DiscordMetadataService
from services.ping_template_service import MAX_TEMPLATES_PER_GUILD, SCRATCH_TEMPLATE_KEY, PingTemplateService
from services.fine_service import FineService
from services.permission_service import (
    BOT_PERMISSION_DEFINITIONS,
    BOT_PERMISSION_KEYS,
    BOT_PERMISSION_LABELS,
    MODULE_ALBION_REGISTRATION,
    MODULE_AUDIT,
    MODULE_ECONOMY,
    MODULE_EXPORT_ECONOMY,
    MODULE_EXPORT_TEMPLATES,
    MODULE_EXPORT_TICKETS,
    MODULE_FINES,
    MODULE_PERMISSIONS,
    MODULE_TEMPLATES,
    MODULE_TICKETS,
    PERMISSION_GLOBAL,
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
from utils.console_logger import log_event

REPORTS_FILE = os.path.join(DATA_DIR, "reports.json")
AVALONIAN_FILE = os.path.join(DATA_DIR, "avalonian_interactions.json")
SESSIONS_FILE = DASHBOARD_SESSIONS_FILE
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
BOT_PERMISSION_OPTIONS = list(BOT_PERMISSION_DEFINITIONS)
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
SESSION_SECRET = DASHBOARD_SESSION_SECRET or ""
BOT_TOKEN = DASHBOARD_BOT_TOKEN or ""
SESSIONS = {}
SESSIONS_LOCK = threading.RLock()
OAUTH_STATES = {}
OAUTH_STATES_LOCK = threading.RLock()
BOT_GUILDS_CACHE = {"expires_at": 0, "guild_ids": None}
MEMBER_ROLES_CACHE = {}
MEMBER_NAME_CACHE = {}
DISCORD_METADATA_CACHE_SETTINGS = DiscordMetadataCacheSettings(
    roles_ttl_seconds=DISCORD_METADATA_ROLES_TTL_SECONDS,
    channels_ttl_seconds=DISCORD_METADATA_CHANNELS_TTL_SECONDS,
    categories_ttl_seconds=DISCORD_METADATA_CATEGORIES_TTL_SECONDS,
    emojis_ttl_seconds=DISCORD_METADATA_EMOJIS_TTL_SECONDS,
    stale_fallback_seconds=DISCORD_METADATA_STALE_FALLBACK_SECONDS,
)
DISCORD_METADATA_SERVICE = None


def read_json_file(path, fallback):
    return read_json_file_safe(path, fallback)

COOKIE_MANAGER = DashboardCookieManager(
    session_cookie_name=SESSION_COOKIE,
    state_cookie_name=STATE_COOKIE,
    session_secret=SESSION_SECRET,
)
make_cookie_value = COOKIE_MANAGER.make_session_cookie
make_state_cookie = COOKIE_MANAGER.make_state_cookie
parse_cookie_header = COOKIE_MANAGER.parse_cookie_header
sign_session_id = COOKIE_MANAGER.sign_session_id
encode_session_cookie = COOKIE_MANAGER.encode_session_cookie
decode_session_cookie = COOKIE_MANAGER.decode_session_cookie

SESSION_STORE = DashboardSessionStore(
    sessions=SESSIONS,
    sessions_lock=SESSIONS_LOCK,
    oauth_states=OAUTH_STATES,
    oauth_states_lock=OAUTH_STATES_LOCK,
    sessions_file=SESSIONS_FILE,
    read_json=read_json_file,
    write_json=write_json_file_safe,
    cookie_manager=COOKIE_MANAGER,
    session_cookie_name=SESSION_COOKIE,
    session_ttl_seconds=SESSION_TTL_SECONDS,
    remember_session_ttl_seconds=REMEMBER_SESSION_TTL_SECONDS,
)
remember_oauth_state = SESSION_STORE.remember_oauth_state
consume_oauth_state = SESSION_STORE.consume_oauth_state
load_persisted_sessions = SESSION_STORE.load_persisted_sessions
save_persisted_sessions = SESSION_STORE.save_persisted_sessions
create_session = SESSION_STORE.create_session
get_session_from_request = SESSION_STORE.get_session_from_request
clear_session_from_request = SESSION_STORE.clear_session_from_request


with SESSIONS_LOCK:
    SESSIONS.update(load_persisted_sessions())


def oauth_configured():
    return auth_oauth_configured(DASHBOARD_CLIENT_ID, DASHBOARD_CLIENT_SECRET)


def admin_guilds_from_discord(guilds):
    return auth_admin_guilds_from_discord(guilds, DISCORD_ADMINISTRATOR)


def guilds_from_discord(guilds):
    return auth_guilds_from_discord(guilds)


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


def get_guild_fines_payload(guild_id, params=None):
    if params:
        page_payload = FineRepository().list_by_guild_page(
            guild_id,
            page=params["page"],
            page_size=params["page_size"],
            search=params["search"],
            status=params["status"],
            record_type=params["record_type"],
            date_from=params["date_from"],
            date_to=params["date_to"],
        )
        items = [serialize_fine_item(fine) for fine in page_payload.pop("items", [])]
        return page_response(
            items,
            page_payload["page"],
            page_payload["page_size"],
            page_payload["total_items"],
            item_key="fines",
        )

    fines = FineService().get_guild_fines(guild_id)
    return {"fines": [serialize_fine_item(fine) for fine in fines]}


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
    max_attempts = 3 if str(method).upper() == "GET" else 1
    last_error = None
    for attempt in range(max_attempts):
        try:
            with urlopen(request, timeout=15) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"Discord respondio {exc.code}: {detail}")
            if exc.code == 429 or exc.code >= 500:
                retry_after = exc.headers.get("Retry-After")
                try:
                    delay = max(0.0, min(float(retry_after), 5.0))
                except (TypeError, ValueError):
                    delay = min(1.0 + attempt, 3.0)
                if attempt + 1 < max_attempts:
                    time.sleep(delay)
                    continue
            raise last_error from exc
        except URLError as exc:
            last_error = RuntimeError(f"No pude conectar con Discord: {exc.reason}")
            if attempt + 1 < max_attempts:
                time.sleep(min(1.0 + attempt, 3.0))
                continue
            raise last_error from exc

    raise last_error or RuntimeError("No pude consultar la API de Discord.")


def fetch_discord_guild_channels(guild_id):
    if not BOT_TOKEN:
        raise RuntimeError("Falta configurar ECONOMY_TOKEN o TOKEN en el archivo .env para leer metadata de Discord.")
    return discord_json_request(
        f"/guilds/{guild_id}/channels",
        token=BOT_TOKEN,
        auth_scheme="Bot",
    )


def fetch_discord_guild_roles(guild_id):
    if not BOT_TOKEN:
        raise RuntimeError("Falta configurar ECONOMY_TOKEN o TOKEN en el archivo .env para leer metadata de Discord.")
    return discord_json_request(
        f"/guilds/{guild_id}/roles",
        token=BOT_TOKEN,
        auth_scheme="Bot",
    )


def fetch_discord_guild_emojis(guild_id):
    if not BOT_TOKEN:
        raise RuntimeError("Falta configurar ECONOMY_TOKEN o TOKEN en el archivo .env para leer metadata de Discord.")
    return discord_json_request(
        f"/guilds/{guild_id}/emojis",
        token=BOT_TOKEN,
        auth_scheme="Bot",
    )


def get_discord_metadata_service():
    global DISCORD_METADATA_SERVICE
    if DISCORD_METADATA_SERVICE is None:
        DISCORD_METADATA_SERVICE = DiscordMetadataService(
            fetch_channels=fetch_discord_guild_channels,
            fetch_roles=fetch_discord_guild_roles,
            fetch_emojis=fetch_discord_guild_emojis,
            cache_settings=DISCORD_METADATA_CACHE_SETTINGS,
        )
    return DISCORD_METADATA_SERVICE


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


def get_albion_registration_payload(guild_id, params=None):
    repository = AlbionRegistrationRepository()
    config = repository.get_config(guild_id)
    if config:
        config["sync_nickname"] = bool(config.get("sync_nickname"))
        config["enabled"] = bool(config.get("enabled"))
    if params:
        page_payload = repository.list_registrations_page(
            guild_id,
            page=params["page"],
            page_size=params["page_size"],
            search=params["search"],
            status=params["status"],
            date_from=params["date_from"],
            date_to=params["date_to"],
        )
        items = page_payload.pop("items", [])
        return page_response(
            items,
            page_payload["page"],
            page_payload["page_size"],
            page_payload["total_items"],
            item_key="registrations",
            extra={
                "region": "America",
                "config": config,
            },
        )
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


def get_guild_ticket_records_page(guild_id, params):
    payload = DashboardJsonRepository(TICKET_RECORDS_FILE).list_guild_items_page(
        guild_id,
        page=params["page"],
        page_size=params["page_size"],
        search=params["search"],
        status=params["status"],
        record_type=params["record_type"],
        date_from=params["date_from"],
        date_to=params["date_to"],
        candidate_date_fields=("created_at", "closed_at", "transcribed_at"),
        item_key="records",
    )
    payload["summary"] = ticket_records_summary(get_guild_ticket_records(guild_id))
    payload["records"] = payload["items"]
    return payload


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


def get_guild_audit_events_page(guild_id, params):
    payload = DashboardJsonRepository(AUDIT_EVENTS_FILE).list_guild_items_page(
        guild_id,
        page=params["page"],
        page_size=params["page_size"],
        search=params["search"],
        status=params["status"],
        record_type=params["record_type"],
        date_from=params["date_from"],
        date_to=params["date_to"],
        candidate_date_fields=("created_at", "date"),
        item_key="events",
    )
    payload["events"] = payload["items"]
    return payload


def append_dashboard_audit_event(guild_id, *, category, title, description, actor=None):
    guild_id = str(guild_id or "")
    if not guild_id:
        return

    event = {
        "category": str(category or "server"),
        "title": str(title or "Cambio administrativo")[:160],
        "description": str(description or "")[:800],
        "created_at": datetime.now(ARGENTINA_TZ).strftime("%d/%m/%Y | %H:%M:%S"),
        "source": "dashboard",
    }
    if actor:
        event["actor"] = str(actor)[:160]

    def mutate(data):
        if not isinstance(data, dict):
            data = {}
        events = data.get(guild_id)
        if not isinstance(events, list):
            events = []
        events.append(event)
        data[guild_id] = events[-1000:]
        return data

    mutate_json_file_safe(AUDIT_EVENTS_FILE, {}, mutate)


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


def query_text(query, name, default=""):
    return str(query.get(name, [default])[0] or default)


def query_bool(query, name):
    return query_text(query, name, "").strip().lower() in {"1", "true", "yes", "on"}


def query_metadata_kinds(query):
    raw_values = []
    for key in ("kinds", "kind"):
        raw_values.extend(query.get(key, []))

    kinds = []
    for raw_value in raw_values:
        for item in str(raw_value or "").split(","):
            clean_item = item.strip().lower()
            if clean_item in {"channels", "categories", "roles", "emojis"} and clean_item not in kinds:
                kinds.append(clean_item)
    return kinds or ["channels", "categories", "roles", "emojis"]


def query_pagination(query):
    return {
        "page": normalize_page(query_text(query, "page", "1")),
        "page_size": normalize_page_size(query_text(query, "page_size", "25")),
        "search": query_text(query, "q", query_text(query, "search", "")).strip(),
        "status": query_text(query, "status", "").strip(),
        "record_type": query_text(query, "type", "").strip(),
        "date_from": query_text(query, "date_from", "").strip(),
        "date_to": query_text(query, "date_to", "").strip(),
    }


def serialize_balance_item(item):
    payload = dict(item)
    payload["user_name"] = clean_user_name(payload.get("user_name"), payload.get("user_id"))
    payload["updated_at_display"] = format_argentina_datetime(payload.get("updated_at"))
    return payload


def serialize_operation_item(item):
    return dict(item)


def serialize_fine_item(fine):
    return {
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


def get_economy_summary_payload(guild_id):
    summary = BalanceRepository().get_dashboard_summary(guild_id)
    return {
        "totals": summary,
        "updatedAt": argentina_now_display(),
    }


def get_discord_metadata_payload(guild_id, *, kinds=None, force_refresh=False):
    return get_discord_metadata_service().get_guild_metadata(
        guild_id,
        kinds=kinds,
        force_refresh=force_refresh,
    )


def get_economy_list_payload(guild_id, tab, params):
    tab = str(tab or "balances")
    if tab == "balances":
        payload = BalanceRepository().list_balances_page(
            guild_id,
            page=params["page"],
            page_size=params["page_size"],
            search=params["search"],
        )
        items = [serialize_balance_item(item) for item in payload.pop("items", [])]
    elif tab == "operations":
        payload = OperationRepository().list_operations_page(
            guild_id,
            page=params["page"],
            page_size=params["page_size"],
            search=params["search"],
            operation_type=params["record_type"],
            date_from=params["date_from"],
            date_to=params["date_to"],
        )
        items = [serialize_operation_item(item) for item in payload.pop("items", [])]
    elif tab == "fines":
        payload = FineRepository().list_by_guild_page(
            guild_id,
            page=params["page"],
            page_size=params["page_size"],
            search=params["search"],
            status=params["status"],
            record_type=params["record_type"],
            date_from=params["date_from"],
            date_to=params["date_to"],
        )
        items = [serialize_fine_item(item) for item in payload.pop("items", [])]
    elif tab == "avalonians":
        payload = DashboardJsonRepository(AVALONIAN_FILE).list_guild_items_page(
            guild_id,
            page=params["page"],
            page_size=params["page_size"],
            search=params["search"],
            status=params["status"],
            record_type=params["record_type"],
            date_from=params["date_from"],
            date_to=params["date_to"],
            candidate_date_fields=("date", "created_at"),
        )
        items = payload.pop("items", [])
    elif tab == "reports":
        payload = DashboardJsonRepository(REPORTS_FILE).list_guild_items_page(
            guild_id,
            page=params["page"],
            page_size=params["page_size"],
            search=params["search"],
            status=params["status"],
            record_type=params["record_type"],
            date_from=params["date_from"],
            date_to=params["date_to"],
            candidate_date_fields=("date", "created_at"),
        )
        items = payload.pop("items", [])
    else:
        raise ValueError("La lista solicitada no existe.")

    return page_response(
        items,
        payload["page"],
        payload["page_size"],
        payload["total_items"],
        extra={"tab": tab},
    )


def build_dashboard_data(guild_id=None, allowed_guilds=None, bot_guild_ids=None, viewer=None):
    with get_connection() as connection:
        guilds, selected_guild_id = select_dashboard_guilds(
            get_guilds(connection),
            requested_guild_id=guild_id,
            allowed_guilds=allowed_guilds,
            bot_guild_ids=bot_guild_ids,
        )
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


LOGIN_HTML = load_dashboard_template("login.html")
INDEX_HTML = load_dashboard_template("dashboard.html")


def render_login_html(next_path):
    return LOGIN_HTML.replace(
        "<!--DASHBOARD_NEXT_INPUT-->",
        f'<input type="hidden" name="next" value="{html.escape(next_path, quote=True)}">',
    )


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

    def permission_service(self):
        return PermissionService()

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

    def session_role_ids(self, session, guild_id):
        guild_id = str(guild_id or "")
        if not guild_id:
            return []
        bot_guild_ids = get_bot_guild_ids()
        if bot_guild_ids is not None and guild_id not in bot_guild_ids:
            return []
        if guild_id not in self.session_member_guild_ids(session):
            return []
        return get_discord_member_role_ids(guild_id, session.get("user", {}).get("id"))

    def can_access_module(self, session, guild_id, module_key):
        if self.is_guild_admin(session, guild_id):
            return True
        role_ids = self.session_role_ids(session, guild_id)
        return self.permission_service().has_module_access(guild_id, module_key, role_ids=role_ids)

    def can_access_tickets(self, session, guild_id):
        return self.can_access_module(session, guild_id, MODULE_TICKETS)

    def can_access_guild_or_tickets(self, session, guild_id):
        return self.can_access_guild(session, guild_id) or self.can_access_tickets(session, guild_id)

    def can_access_any_dashboard_module(self, session, guild_id):
        if self.is_guild_admin(session, guild_id):
            return True
        role_ids = self.session_role_ids(session, guild_id)
        return self.permission_service().has_any_dashboard_access(guild_id, role_ids=role_ids)

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
            if self.permission_service().has_any_dashboard_access(guild_id, role_ids=role_ids):
                allowed[guild_id] = str(guild.get("name") or f"Servidor {guild_id}")
        return allowed

    def dashboard_access_payload(self, session, guild_id):
        guild_id = str(guild_id or "")
        if not guild_id:
            return {
                "admin": False,
                "economy": False,
                "tickets": False,
                "audit": False,
                "templates": False,
                "permissions": False,
                "registration": False,
            }
        admin = self.is_guild_admin(session, guild_id)
        return {
            "admin": admin,
            "economy": self.can_access_module(session, guild_id, MODULE_ECONOMY),
            "tickets": self.can_access_module(session, guild_id, MODULE_TICKETS),
            "audit": self.can_access_module(session, guild_id, MODULE_AUDIT),
            "templates": self.can_access_module(session, guild_id, MODULE_TEMPLATES),
            "permissions": self.can_access_module(session, guild_id, MODULE_PERMISSIONS),
            "registration": self.can_access_module(session, guild_id, MODULE_ALBION_REGISTRATION),
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

    def can_access_dashboard_action_request(self, session, request):
        if not isinstance(request, dict):
            return False

        action_type = str(request.get("action_type") or "")
        guild_id = str(request.get("guild_id") or "")
        payload = request.get("payload") or {}

        if action_type == "publish_report":
            return self.can_access_report_calculator(
                session,
                payload.get("guild_id") or guild_id,
                payload.get("caller_id"),
            )

        return bool(guild_id) and self.can_access_guild_or_tickets(session, guild_id)

    def dashboard_actor_label(self, session):
        user = session.get("user", {}) if isinstance(session, dict) else {}
        username = str(user.get("username") or "Usuario")
        user_id = str(user.get("id") or "")
        return f"{username} ({user_id})" if user_id else username

    def record_dashboard_admin_change(self, session, guild_id, *, category, title, description):
        append_dashboard_audit_event(
            guild_id,
            category=category,
            title=title,
            description=description,
            actor=self.dashboard_actor_label(session),
        )

    def send_internal_json_error(self, context, exc):
        log_event(f"DASHBOARD ERROR {context} | {type(exc).__name__}: {exc}")
        self.send_json(500, {"error": "Ocurrio un error interno. Intenta de nuevo en unos segundos."})

    def send_internal_text_error(self, context, exc):
        log_event(f"DASHBOARD ERROR {context} | {type(exc).__name__}: {exc}")
        self.send_text(500, "Ocurrio un error interno. Intenta de nuevo en unos segundos.", "text/plain")

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

    def send_dashboard_static(self, relative_path):
        path = resolve_dashboard_static_path(relative_path)
        if not path:
            self.send_text(404, "No encontrado", "text/plain")
            return

        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_file(200, str(path), content_type)

    def send_ticket_media(self, relative_path):
        session = get_session_from_request(self)
        if not session:
            self.send_text(401, "Inicia sesion.", "text/plain")
            return

        requested = unquote(relative_path).replace("\\", "/").lstrip("/")
        guild_id = requested.split("/", 1)[0] if requested else ""
        if not guild_id or not self.can_access_tickets(session, guild_id):
            self.send_text(403, "No tienes acceso a este archivo.", "text/plain")
            return

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

            self.send_text(200, render_login_html(next_path), "text/html")
            return

        if parsed.path == "/dashboard":
            if not get_session_from_request(self):
                self.send_redirect(
                    f"/?next={urlencode({'value': self.path})[6:]}"
                )
                return

            self.send_text(200, INDEX_HTML, "text/html")
            return

        if parsed.path.startswith("/static/"):
            self.send_dashboard_static(parsed.path.removeprefix("/static/"))
            return

        if parsed.path == "/ticket-transcript":
            session = get_session_from_request(self)
            if not session:
                self.send_redirect("/")
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            record_id = query.get("record_id", [""])[0]
            if not guild_id or not self.can_access_tickets(session, guild_id):
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
                self.send_internal_text_error("/login", exc)
            return

        if parsed.path == "/oauth/callback":
            try:
                self.handle_oauth_callback(parsed)
            except Exception as exc:
                self.send_internal_text_error("/oauth/callback", exc)
            return

        if parsed.path == "/logout":
            self.handle_logout()
            return

        if parsed.path == "/api/me":
            session = self.get_authenticated_session()
            if not session:
                return

            self.send_json(200, {
                "viewer": session.get("user", {}),
                "csrf_token": session.get("csrf_token", ""),
            })
            return

        if parsed.path == "/api/guilds":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            requested_guild_id = query.get("guild_id", [""])[0]
            try:
                allowed_guilds = self.dashboard_allowed_guilds(session)
                with get_connection() as connection:
                    guilds, selected_guild_id = select_dashboard_guilds(
                        get_guilds(connection),
                        requested_guild_id=requested_guild_id,
                        allowed_guilds=allowed_guilds,
                        bot_guild_ids=get_bot_guild_ids(),
                    )
                self.send_json(200, {
                    "guilds": guilds,
                    "selectedGuildId": selected_guild_id,
                })
            except Exception as exc:
                self.send_internal_json_error("/api/guilds", exc)
            return

        if parsed.path == "/api/dashboard/access":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            requested_guild_id = query.get("guild_id", [""])[0]
            try:
                allowed_guilds = self.dashboard_allowed_guilds(session)
                with get_connection() as connection:
                    _, selected_guild_id = select_dashboard_guilds(
                        get_guilds(connection),
                        requested_guild_id=requested_guild_id,
                        allowed_guilds=allowed_guilds,
                        bot_guild_ids=get_bot_guild_ids(),
                    )
                self.send_json(200, {
                    "selectedGuildId": selected_guild_id,
                    "access": self.dashboard_access_payload(session, selected_guild_id),
                })
            except Exception as exc:
                self.send_internal_json_error("/api/dashboard/access", exc)
            return

        if parsed.path == "/api/economy/summary":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_module(session, guild_id, MODULE_ECONOMY):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            try:
                self.send_json(200, get_economy_summary_payload(guild_id))
            except Exception as exc:
                self.send_internal_json_error("/api/economy/summary", exc)
            return

        if parsed.path == "/api/economy/list":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_module(session, guild_id, MODULE_ECONOMY):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            try:
                params = query_pagination(query)
                tab = query_text(query, "tab", "balances")
                self.send_json(200, get_economy_list_payload(guild_id, tab, params))
            except Exception as exc:
                self.send_internal_json_error("/api/economy/list", exc)
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
                self.send_internal_json_error("/api/data", exc)
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

        if parsed.path == "/api/dashboard-action-request":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            request_id = query.get("request_id", [""])[0]
            request = DashboardActionService().get_request(request_id)
            if not request or not self.can_access_dashboard_action_request(session, request):
                self.send_json(404, {"error": "No encontre esa solicitud."})
                return
            self.send_json(200, {"request": request})
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
                if not request or not self.can_access_dashboard_action_request(session, request):
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
            if not guild_id or not self.can_access_module(session, guild_id, MODULE_FINES):
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
            if not guild_id or not self.can_access_module(session, guild_id, MODULE_FINES):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return
            self.send_json(200, get_guild_fines_payload(guild_id, params=query_pagination(query)))
            return

        if parsed.path in {"/api/export/economy", "/api/export/templates", "/api/export/tickets"}:
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            export_module = {
                "/api/export/economy": MODULE_EXPORT_ECONOMY,
                "/api/export/templates": MODULE_EXPORT_TEMPLATES,
                "/api/export/tickets": MODULE_EXPORT_TICKETS,
            }.get(parsed.path)
            if not guild_id or not export_module or not self.can_access_module(session, guild_id, export_module):
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
            if not guild_id or not self.can_access_module(session, guild_id, MODULE_ALBION_REGISTRATION):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            try:
                self.send_json(200, get_albion_registration_payload(guild_id, params=query_pagination(query)))
            except Exception as exc:
                self.send_internal_json_error("/api/albion-registration", exc)
            return

        if parsed.path == "/api/discord-metadata":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_any_dashboard_module(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            try:
                self.send_json(200, get_discord_metadata_payload(
                    guild_id,
                    kinds=query_metadata_kinds(query),
                    force_refresh=query_bool(query, "refresh"),
                ))
            except Exception as exc:
                self.send_internal_json_error("/api/discord-metadata", exc)
            return

        if parsed.path == "/api/discord-channels":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not (
                self.can_access_module(session, guild_id, MODULE_TICKETS)
                or self.can_access_module(session, guild_id, MODULE_FINES)
                or self.can_access_module(session, guild_id, MODULE_AUDIT)
            ):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            try:
                self.send_json(200, {
                    "channels": get_discord_metadata_service().get_channels(
                        guild_id,
                        force_refresh=query_bool(query, "refresh"),
                    )
                })
            except Exception as exc:
                self.send_internal_json_error("/api/discord-channels", exc)
            return

        if parsed.path == "/api/discord-categories":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not (
                self.can_access_module(session, guild_id, MODULE_TICKETS)
                or self.can_access_module(session, guild_id, MODULE_FINES)
                or self.can_access_module(session, guild_id, MODULE_AUDIT)
            ):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            try:
                self.send_json(200, {
                    "categories": get_discord_metadata_service().get_categories(
                        guild_id,
                        force_refresh=query_bool(query, "refresh"),
                    )
                })
            except Exception as exc:
                self.send_internal_json_error("/api/discord-categories", exc)
            return

        if parsed.path == "/api/discord-emojis":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_module(session, guild_id, MODULE_TEMPLATES):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            try:
                self.send_json(200, {
                    "emojis": get_discord_metadata_service().get_emojis(
                        guild_id,
                        force_refresh=query_bool(query, "refresh"),
                    )
                })
            except Exception as exc:
                self.send_internal_json_error("/api/discord-emojis", exc)
            return

        if parsed.path == "/api/discord-roles":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not (
                self.can_access_module(session, guild_id, MODULE_PERMISSIONS)
                or self.can_access_module(session, guild_id, MODULE_FINES)
            ):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            try:
                self.send_json(200, {
                    "roles": get_discord_metadata_service().get_roles(
                        guild_id,
                        force_refresh=query_bool(query, "refresh"),
                    )
                })
            except Exception as exc:
                self.send_internal_json_error("/api/discord-roles", exc)
            return

        if parsed.path == "/api/audit-config":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_module(session, guild_id, MODULE_AUDIT):
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

            self.send_json(200, get_guild_ticket_records_page(guild_id, query_pagination(query)))
            return

        if parsed.path == "/api/ticket-live":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            channel_id = query.get("channel_id", [""])[0]
            if not guild_id or not self.can_access_tickets(session, guild_id):
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
                self.send_internal_json_error("/api/ticket-live", exc)
            return

        if parsed.path == "/api/audit-events":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_module(session, guild_id, MODULE_AUDIT):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return

            self.send_json(200, get_guild_audit_events_page(guild_id, query_pagination(query)))
            return

        if parsed.path == "/api/ping-templates":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_module(session, guild_id, MODULE_TEMPLATES):
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
            if not guild_id or not self.can_access_module(session, guild_id, MODULE_PERMISSIONS):
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

                request = ReportDashboardRepository().create(
                    {
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
                    },
                    requested_by=str(session.get("user", {}).get("id") or ""),
                )
                self.send_json(202, {"request": request})
            except Exception as exc:
                self.send_internal_json_error("/api/report-calculator", exc)
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
                if not guild_id or not self.can_access_module(session, guild_id, MODULE_FINES):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return
                payload = save_fine_config(guild_id, body)
                self.record_dashboard_admin_change(
                    session,
                    guild_id,
                    category="server",
                    title="Configuracion de multas actualizada",
                    description="Se actualizaron canal, roles o categoria de tickets para multas.",
                )
                self.send_json(200, payload)
            except Exception as exc:
                self.send_internal_json_error("/api/fine-config", exc)
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
                if not guild_id or not self.can_access_module(session, guild_id, MODULE_ALBION_REGISTRATION):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return

                payload = save_albion_registration_config(guild_id, body)
                self.record_dashboard_admin_change(
                    session,
                    guild_id,
                    category="server",
                    title="Registro Albion actualizado",
                    description="Se actualizaron los datos de configuracion del registro Albion.",
                )
                self.send_json(
                    200,
                    payload,
                )
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception as exc:
                self.send_internal_json_error("/api/albion-registration", exc)
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
                self.record_dashboard_admin_change(
                    session,
                    guild_id,
                    category="channels",
                    title="Paneles de ticket actualizados",
                    description=f"Se guardaron {len(panels)} paneles de ticket para el servidor.",
                )
                self.send_json(200, {"panels": panels})
            except Exception as exc:
                self.send_internal_json_error("/api/ticket-panels", exc)
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
                self.record_dashboard_admin_change(
                    session,
                    guild_id,
                    category="channels",
                    title="Panel de ticket publicado",
                    description=f"Se publico un panel de ticket en el canal {channel_id}.",
                )
                self.send_json(200, {"message_id": str(result.get("id", "")), "channel_id": channel_id})
            except Exception as exc:
                self.send_internal_json_error("/api/publish-ticket-panel", exc)
            return

        if parsed.path == "/api/ticket-live-message":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
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
                self.send_internal_json_error("/api/ticket-live-message", exc)
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
                if not guild_id or not self.can_access_module(session, guild_id, MODULE_AUDIT):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return

                save_guild_audit_config(guild_id, body.get("config", {}))
                self.record_dashboard_admin_change(
                    session,
                    guild_id,
                    category="server",
                    title="Configuracion de auditoria actualizada",
                    description="Se actualizaron los canales de auditoria del servidor.",
                )
                self.send_json(200, {"config": get_guild_audit_config(guild_id)})
            except Exception as exc:
                self.send_internal_json_error("/api/audit-config", exc)
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
                if not guild_id or not self.can_access_module(session, guild_id, MODULE_TEMPLATES):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return

                template, error = save_guild_ping_template(guild_id, body.get("template", {}))
                if error:
                    self.send_json(400, {"error": error})
                    return

                payload = get_guild_ping_templates(guild_id)
                payload["template"] = template
                self.record_dashboard_admin_change(
                    session,
                    guild_id,
                    category="server",
                    title="Plantilla de ping guardada",
                    description=f"Se guardo o actualizo la plantilla `{template.get('key', '')}`.",
                )
                self.send_json(200, payload)
            except Exception as exc:
                self.send_internal_json_error("/api/ping-templates", exc)
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
                if not guild_id or not self.can_access_module(session, guild_id, MODULE_PERMISSIONS):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return

                payload, error = save_guild_bot_permissions(guild_id, body)
                if error:
                    self.send_json(400, {"error": error})
                    return

                self.record_dashboard_admin_change(
                    session,
                    guild_id,
                    category="roles",
                    title="Permisos del bot actualizados",
                    description="Se actualizaron los permisos asignados a roles dentro del bot.",
                )
                self.send_json(200, payload)
            except Exception as exc:
                self.send_internal_json_error("/api/bot-permissions", exc)
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
                self.send_internal_json_error("/api/ticket-record", exc)
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
                if not guild_id or not self.can_access_module(session, guild_id, MODULE_TEMPLATES):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return

                removed = ping_template_service().delete_template(guild_id, key)
                if not removed:
                    self.send_json(400, {"error": "No pude eliminar esa plantilla. La base y desde-cero no se pueden eliminar."})
                    return

                self.record_dashboard_admin_change(
                    session,
                    guild_id,
                    category="server",
                    title="Plantilla de ping eliminada",
                    description=f"Se elimino la plantilla `{key}`.",
                )
                self.send_json(200, get_guild_ping_templates(guild_id))
            except Exception as exc:
                self.send_internal_json_error("/api/ping-templates", exc)
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
    validate_dashboard_startup()
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
