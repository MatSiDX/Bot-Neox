import argparse
import base64
import hashlib
import html
import json
import logging
import mimetypes
import os
import re
import secrets
import shutil
import socket
import sys
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
    DASHBOARD_COOKIE_SECURE,
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    DASHBOARD_PRODUCTION_MODE,
    DASHBOARD_PUBLIC_URL,
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
from repositories.database import get_connection as database_connection, init_database
from repositories.albion_registration_repository import AlbionRegistrationRepository
from repositories.active_avalonian_repository import ActiveAvalonianRepository
from repositories.balance_repository import BalanceRepository, DATA_DIR
from repositories.bot_message_audit_repository import BotMessageAuditRepository
from repositories.dashboard_json_repository import DashboardJsonRepository
from repositories.fine_repository import FineRepository
from repositories.operation_repository import OperationRepository
from repositories.pagination import normalize_page, normalize_page_size, page_response
from repositories.report_dashboard_repository import ReportDashboardRepository
from repositories.server_backup_repository import ServerBackupLimitError
from services.config_service import ConfigService
from services.dashboard_action_service import DashboardActionService
from services.discord_metadata_service import DiscordMetadataCacheSettings, DiscordMetadataService
from services.ping_template_service import MAX_TEMPLATES_PER_GUILD, SCRATCH_TEMPLATE_KEY, PingTemplateService
from services.dashboard_admin_security_service import (
    DashboardAdminAccessError,
    DashboardAdminSecurityService,
)
from services.fine_service import FineService
from services.albion_market_price_service import AlbionMarketPriceService
from services.chest_table_service import ChestTableService
from services.loot_normalization_service import LootNormalizationError, LootNormalizationService
from services.report_service import ReportFormatService
from services.server_backup_service import ServerBackupService
from services.server_template_service import SERVER_TEMPLATE_ACTION_APPLY, ServerTemplateService
from services.permission_service import (
    MODULE_ADMIN_PANEL,
    MODULE_ALBION_REGISTRATION,
    MODULE_AUDIT,
    MODULE_ECONOMY,
    MODULE_EXPORT_ECONOMY,
    MODULE_EXPORT_TEMPLATES,
    MODULE_EXPORT_TICKETS,
    MODULE_FINES,
    MODULE_LOOT,
    MODULE_PERMISSIONS,
    MODULE_REPORT_CALCULATOR,
    MODULE_REPORTS,
    MODULE_TEMPLATES,
    MODULE_TICKETS,
    MODULE_WELCOME,
    PERMISSION_ECONOMY_BALANCE_EDIT,
    PERMISSION_LOOT_USE,
    PERMISSION_TEMPLATES_CREATE,
    PERMISSION_TEMPLATES_DELETE,
    PERMISSION_TEMPLATES_EDIT,
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
LOGGER = logging.getLogger(__name__)
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
DEFAULT_TICKET_OWNER_PERMISSIONS = [
    "view_channel",
    "send_messages",
    "read_message_history",
    "attach_files",
    "embed_links",
]
DISCORD_API_BASE = "https://discord.com/api/v10"
ALBION_API_BASE = "https://gameinfo.albiononline.com/api/gameinfo"
DISCORD_ADMINISTRATOR = 0x8
DISCORD_PERM_VIEW_CHANNEL = 0x400
DISCORD_PERM_SEND_MESSAGES = 0x800
DISCORD_PERM_MANAGE_MESSAGES = 0x2000
DISCORD_PERM_READ_MESSAGE_HISTORY = 0x10000
BOT_MESSAGE_MAX_LENGTH = 2000
BOT_MESSAGE_ACTION_SEND = "bot_message_send"
BOT_MESSAGE_ACTION_EDIT = "bot_message_edit"
BOT_MESSAGE_ACTION_DELETE = "bot_message_delete"
BOT_MESSAGE_ACTIONS = {
    "send": BOT_MESSAGE_ACTION_SEND,
    "edit": BOT_MESSAGE_ACTION_EDIT,
    "delete": BOT_MESSAGE_ACTION_DELETE,
}
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
BOT_GUILDS_CACHE_LOCK = threading.RLock()
ADMIN_MESSAGE_CHANNELS_CACHE = {}
ADMIN_MESSAGE_CHANNELS_CACHE_LOCK = threading.RLock()
ADMIN_MESSAGE_CHANNELS_CACHE_TTL_SECONDS = 300
MEMBER_ROLES_CACHE = {}
MEMBER_NAME_CACHE = {}
MEMBER_STATUS_CACHE = {}
GUILD_SUMMARY_CACHE = {}
GUILD_SUMMARY_CACHE_LOCK = threading.RLock()
GUILD_SUMMARY_TTL_SECONDS = 300
DISCORD_METADATA_CACHE_SETTINGS = DiscordMetadataCacheSettings(
    roles_ttl_seconds=DISCORD_METADATA_ROLES_TTL_SECONDS,
    channels_ttl_seconds=DISCORD_METADATA_CHANNELS_TTL_SECONDS,
    categories_ttl_seconds=DISCORD_METADATA_CATEGORIES_TTL_SECONDS,
    emojis_ttl_seconds=DISCORD_METADATA_EMOJIS_TTL_SECONDS,
    stale_fallback_seconds=DISCORD_METADATA_STALE_FALLBACK_SECONDS,
)
DISCORD_METADATA_SERVICE = None
DASHBOARD_ADMIN_SECURITY_SERVICE = None
DASHBOARD_ADMIN_SECURITY_LOCK = threading.RLock()


def read_json_file(path, fallback):
    return read_json_file_safe(path, fallback)

COOKIE_MANAGER = DashboardCookieManager(
    session_cookie_name=SESSION_COOKIE,
    state_cookie_name=STATE_COOKIE,
    session_secret=SESSION_SECRET,
    cookie_secure=DASHBOARD_COOKIE_SECURE,
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
    max_attempts = 3 if data is None else 1
    last_error = None
    for attempt in range(max_attempts):
        try:
            with urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
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


def get_active_avalonian_state(guild_id, caller_id, numero_ava):
    data = ActiveAvalonianRepository().load()
    state = (
        data.get(str(guild_id), {})
        .get(str(caller_id), {})
        .get(str(numero_ava))
    )
    return dict(state) if isinstance(state, dict) else None


def get_active_report_calculators(guild_id, caller_id=None):
    data = ActiveAvalonianRepository().load()
    guild_states = data.get(str(guild_id), {})
    if not isinstance(guild_states, dict):
        return []

    calculators = []
    for current_caller_id, caller_states in guild_states.items():
        if caller_id is not None and str(current_caller_id) != str(caller_id):
            continue
        if not isinstance(caller_states, dict):
            continue
        for numero_ava, state in caller_states.items():
            if not isinstance(state, dict):
                continue
            if not state.get("finalized") or state.get("cancelled"):
                continue
            if (
                (state.get("report_sent") or state.get("report_generated"))
                and not state.get("report_rejected")
            ):
                continue
            calculators.append(
                {
                    "numero_ava": str(state.get("numero_ava") or numero_ava),
                    "title": str(state.get("title") or f"Ava {numero_ava}"),
                    "caller_id": str(state.get("caller_id") or current_caller_id),
                    "caller_name": str(state.get("caller_name") or ""),
                    "report_sent": bool(state.get("report_sent")),
                    "report_generated": bool(state.get("report_generated", state.get("report_sent"))),
                    "report_rejected": bool(state.get("report_rejected")),
                }
            )
    calculators.sort(
        key=lambda item: (
            int(item.get("numero_ava", 0) or 0),
            str(item.get("caller_name") or "").casefold(),
            str(item.get("caller_id") or ""),
        ),
        reverse=True,
    )
    return calculators


def get_active_report_calculators_for_user(guild_id, caller_id):
    return get_active_report_calculators(guild_id, caller_id=caller_id)


def build_slot_keys_from_roles(slot_names):
    keys = []
    counts = {}
    used = set()
    for index, slot_name in enumerate(slot_names, start=1):
        label = str(slot_name or "").strip()
        if not label:
            continue
        group_key = label.lower()
        counts[group_key] = counts.get(group_key, 0) + 1
        candidate = label if counts[group_key] == 1 else f"{label}#{counts[group_key]}"
        suffix = index
        while candidate in used:
            candidate = f"{label}#{suffix}"
            suffix += 1
        keys.append(candidate)
        used.add(candidate)
    return keys


def ordered_report_slots(state, slots):
    template = state.get("template") if isinstance(state.get("template"), dict) else {}
    roles = template.get("roles") if isinstance(template.get("roles"), list) else []
    slot_order = {
        slot_key: index
        for index, slot_key in enumerate(build_slot_keys_from_roles(roles), start=1)
    }
    return sorted(
        slots.items(),
        key=lambda item: (slot_order.get(str(item[0]), len(slot_order) + 1), str(item[0])),
    )


def serialize_report_calculator_state(state):
    slots = state.get("slots") if isinstance(state.get("slots"), dict) else {}
    participants = []
    guild_id = str(state.get("guild_id") or "")
    for index, (slot_key, user_id) in enumerate(ordered_report_slots(state, slots), start=1):
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
        "report_generated": bool(state.get("report_generated", state.get("report_sent"))),
        "report_rejected": bool(state.get("report_rejected")),
        "participants": participants,
    }


REPORT_FORMATTER = ReportFormatService()


def report_formatter_slots_from_state(state):
    formatter_slots = state.get("formatter_slots") if isinstance(state.get("formatter_slots"), list) else []
    if formatter_slots:
        return formatter_slots

    slots = state.get("slots") if isinstance(state.get("slots"), dict) else {}
    if not slots:
        template = state.get("template") if isinstance(state.get("template"), dict) else {}
        roles = template.get("roles") if isinstance(template.get("roles"), list) else []
        slots = {slot_key: None for slot_key in build_slot_keys_from_roles(roles)}
    result = []
    for index, (slot_key, user_id) in enumerate(ordered_report_slots(state, slots), start=1):
        result.append(
            {
                "index": index,
                "slot": str(slot_key).split("#", 1)[0],
                "user_id": int(user_id or 0) if user_id else 0,
            }
        )
    return result


def build_manual_report_calculator_state(body, session):
    raw_count = str(body.get("participant_count") or "0").strip()
    try:
        participant_count = max(0, min(int(raw_count), 200))
    except ValueError:
        participant_count = 0

    formatter_slots = [
        {
            "index": index,
            "slot": "Participante",
            "user_id": -index,
            "mention": f"Participante {index}",
        }
        for index in range(1, participant_count + 1)
    ]
    user = session.get("user", {}) if isinstance(session, dict) else {}
    return {
        "guild_id": str(body.get("guild_id") or ""),
        "caller_id": str(user.get("id") or body.get("caller_id") or ""),
        "numero_ava": "",
        "title": str(body.get("manual_title") or "Actividad manual")[:120],
        "caller_name": str(user.get("global_name") or user.get("username") or ""),
        "finalized": True,
        "cancelled": False,
        "manual": True,
        "formatter_slots": formatter_slots,
    }


def build_report_calculator_preview(state, body):
    slots = report_formatter_slots_from_state(state)
    occupied_user_ids = [slot["user_id"] for slot in slots if slot.get("user_id")]
    slot_by_user_id = {
        int(slot["user_id"]): slot["slot"]
        for slot in slots
        if slot.get("user_id")
    }
    split_mode = str(body.get("split_mode") or "")
    if split_mode not in {"items", "silver", "items_silver"}:
        split_mode = "items"

    silver = REPORT_FORMATTER.parse_amount(body.get("silver"))
    items = REPORT_FORMATTER.parse_amount(body.get("items"))
    estimated_amount = REPORT_FORMATTER.parse_amount(body.get("estimated"))
    mapa, repa = REPORT_FORMATTER.parse_costs(body.get("costs"))
    caller_percentage = REPORT_FORMATTER.parse_percentage(body.get("caller_percentage"))
    looter_payment = REPORT_FORMATTER.parse_amount(body.get("looter_payment"))
    looter_user_id = int(body.get("looter_user_id") or 0)
    tab_sale_percentage = REPORT_FORMATTER.parse_percentage(body.get("tab_sale_percentage"))
    adjustments = REPORT_FORMATTER.parse_adjustments(
        body.get("adjustments"),
        [slot["slot"] for slot in slots],
    )
    fines = REPORT_FORMATTER.normalize_fines(
        body.get("fines", []),
        occupied_user_ids,
        lambda user_id: slot_by_user_id.get(int(user_id), ""),
    )
    exclusions = REPORT_FORMATTER.normalize_split_exclusions(
        body.get("split_exclusions", []),
        slots,
    )
    split_modifiers = REPORT_FORMATTER.normalize_split_modifiers(
        body.get("split_modifiers", []),
        slots,
    )
    build_loan_discounts = REPORT_FORMATTER.normalize_build_loan_discounts(
        body.get("build_loan_discounts", []),
        slots,
    )
    split_participant_count = REPORT_FORMATTER.split_participant_count(
        occupied_user_ids,
        exclusions,
    )

    warnings = []
    is_manual = bool(state.get("manual"))
    if not is_manual and not state.get("finalized"):
        warnings.append("La Ava todavia no esta finalizada.")
    if not occupied_user_ids:
        warnings.append("No hay participantes cargados para el reparto.")
    if occupied_user_ids and split_participant_count <= 0:
        warnings.append("Todos los participantes estan excluidos del reparto.")
    if not estimated_amount:
        warnings.append("Falta completar el estimado.")
    if split_mode != "silver" and not items:
        warnings.append("Falta completar el valor de items.")
    if split_mode != "items" and not silver:
        warnings.append("Falta completar el silver.")
    if looter_payment and occupied_user_ids and not looter_user_id:
        warnings.append("Selecciona quien fue el looter para aplicar ese pago.")
    if looter_user_id and looter_user_id not in set(occupied_user_ids):
        warnings.append("El looter seleccionado no forma parte de esta party.")
    if looter_user_id and REPORT_FORMATTER.split_participant_weight(looter_user_id, exclusions) < 1:
        warnings.append("El looter tiene descuento de actividad y no recibira pago de looter.")
        looter_user_id = 0
        looter_payment = 0

    split = REPORT_FORMATTER.calculate_split(
        silver,
        items,
        mapa,
        repa,
        split_participant_count,
        split_mode,
        caller_percentage,
        looter_payment,
        looter_user_id,
        tab_sale_percentage,
        split_modifiers,
    )
    distribution = REPORT_FORMATTER.build_distribution(
        slots,
        state.get("caller_id"),
        split,
        adjustments,
        exclusions,
        split_modifiers,
        build_loan_discounts,
    )
    _, available_silver, pp_required, pp_difference = REPORT_FORMATTER.evaluate_pp_distribution(split, distribution)
    if pp_difference < 0:
        warnings.append("El silver disponible no alcanza para cubrir los PP indicados.")

    content = REPORT_FORMATTER.build_report_content(
        title=str(state.get("title") or f"Ava {state.get('numero_ava', '')}"),
        caller_id=state.get("caller_id"),
        estimated=estimated_amount or str(body.get("estimated") or ""),
        silver=silver,
        items=items,
        mapa=mapa,
        repa=repa,
        adjustments=adjustments,
        split=split,
        slots=slots,
        exclusions=exclusions,
        split_modifiers=split_modifiers,
        build_loan_discounts=build_loan_discounts,
    )
    return {
        "content": content,
        "evaluation_content": REPORT_FORMATTER.build_final_report_text(
            content=content,
            fines=fines,
            split=split,
            distribution=distribution,
            build_loan_discounts=build_loan_discounts,
        ),
        "warnings": warnings,
        "split": {
            "mode": split["mode"],
            "label": split["label"],
            "total": split["total"],
            "item_per_user": split["item_per_user"],
            "silver_per_user": split["silver_per_user"],
            "split_participants": split["split_participants"],
            "available_silver": available_silver,
            "pp_required": pp_required,
        },
        "split_exclusions": exclusions,
        "split_modifiers": split_modifiers,
        "build_loan_discounts": build_loan_discounts,
    }


def parse_bool_option(value, default=True):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "si", "sí"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def report_request_idempotency_key(body, *, send_to_channel):
    raw_fines = body.get("fines", [])
    stable_fines = []
    if isinstance(raw_fines, list):
        for entry in raw_fines:
            if not isinstance(entry, dict):
                continue
            stable_fines.append(
                {
                    "user_id": str(entry.get("user_id") or ""),
                    "amount": str(entry.get("amount") or ""),
                    "reason": str(entry.get("reason") or ""),
                    "proof_name": str(entry.get("proof_name") or ""),
                }
            )
    stable_payload = {
        "guild_id": str(body.get("guild_id") or ""),
        "caller_id": str(body.get("caller_id") or ""),
        "numero_ava": str(body.get("numero_ava") or ""),
        "split_mode": str(body.get("split_mode") or ""),
        "send_to_channel": bool(send_to_channel),
        "estimated": str(body.get("estimated") or ""),
        "silver": str(body.get("silver") or ""),
        "items": str(body.get("items") or ""),
        "costs": str(body.get("costs") or ""),
        "caller_percentage": str(body.get("caller_percentage") or ""),
        "looter_payment": str(body.get("looter_payment") or ""),
        "looter_user_id": str(body.get("looter_user_id") or ""),
        "tab_sale_percentage": str(body.get("tab_sale_percentage") or ""),
        "adjustments": str(body.get("adjustments") or ""),
        "split_modifiers": [
            {
                "name": str(entry.get("name") or ""),
                "operation": str(entry.get("operation") or ""),
                "amount": str(entry.get("amount") or ""),
                "description": str(entry.get("description") or ""),
                "target_type": str(entry.get("target_type") or ""),
                "user_id": str(entry.get("user_id") or ""),
            }
            for entry in body.get("split_modifiers", [])
            if isinstance(entry, dict)
        ],
        "build_loan_discounts": [
            {
                "user_id": str(entry.get("user_id") or entry.get("player_id") or ""),
                "amount": str(entry.get("amount") or ""),
                "reason": str(entry.get("reason") or entry.get("description") or entry.get("motivo") or ""),
                "collection_method": str(entry.get("collection_method") or entry.get("method") or entry.get("metodo_cobro") or ""),
                "proof_name": str(entry.get("proof_name") or ""),
                "proof_data_hash": hashlib.sha256(
                    str(entry.get("proof_data_url") or "").encode("utf-8")
                ).hexdigest()[:16] if entry.get("proof_data_url") else "",
            }
            for entry in body.get("build_loan_discounts", [])
            if isinstance(entry, dict)
        ],
        "split_exclusions": [
            {
                "user_id": str(entry.get("user_id") or ""),
                "reason": str(entry.get("reason") or ""),
                "activity_percentage": str(entry.get("activity_percentage") or ""),
            }
            for entry in body.get("split_exclusions", [])
            if isinstance(entry, dict)
        ],
        "fines": stable_fines,
    }
    return hashlib.sha256(
        json.dumps(stable_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def get_bot_guild_ids():
    if not BOT_TOKEN:
        return None

    with BOT_GUILDS_CACHE_LOCK:
        now = time.time()
        if BOT_GUILDS_CACHE["guild_ids"] is not None and BOT_GUILDS_CACHE["expires_at"] > now:
            return BOT_GUILDS_CACHE["guild_ids"]

        guilds = discord_request("/users/@me/guilds", token=BOT_TOKEN, auth_scheme="Bot")
        guild_ids = {str(guild.get("id")) for guild in guilds}
        BOT_GUILDS_CACHE["guild_ids"] = guild_ids
        BOT_GUILDS_CACHE["expires_at"] = time.time() + 300
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


def get_discord_member_status(guild_id, user_id):
    guild_id = str(guild_id or "")
    user_id = str(user_id or "")
    if not guild_id or not user_id or not BOT_TOKEN:
        return "Estado no verificado"

    cache_key = (guild_id, user_id)
    cached = MEMBER_STATUS_CACHE.get(cache_key)
    now = time.time()
    if cached and cached.get("expires_at", 0) > now:
        return str(cached.get("status") or "Estado no verificado")

    status = "Estado no verificado"
    request = Request(
        f"{DISCORD_API_BASE}/guilds/{guild_id}/members/{user_id}",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bot {BOT_TOKEN}",
            "User-Agent": "Bot-Neox-Dashboard/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=10) as response:
            response.read()
        status = "En servidor"
    except HTTPError as exc:
        status = "Fuera del servidor" if exc.code == 404 else "Estado no verificado"
    except URLError:
        status = "Estado no verificado"

    MEMBER_STATUS_CACHE[cache_key] = {
        "status": status,
        "expires_at": now + 300,
    }
    return status


def resolve_dashboard_user_name(guild_id, user_id, user_name):
    cleaned = clean_user_name(user_name, user_id)
    fallback = f"Usuario {user_id}" if user_id else "Usuario"
    if cleaned and cleaned != "Sin nombre":
        return cleaned

    display_name = get_discord_member_display_name(guild_id, user_id)
    display_name = str(display_name or "").strip()
    if display_name and display_name not in {str(user_id), fallback, "Usuario"}:
        return display_name

    return fallback


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


def fetch_discord_bot_user():
    if not BOT_TOKEN:
        raise RuntimeError("Falta configurar ECONOMY_TOKEN o TOKEN en el archivo .env para leer metadata de Discord.")
    return discord_json_request("/users/@me", token=BOT_TOKEN, auth_scheme="Bot")


def fetch_discord_guild_member(guild_id, user_id):
    if not BOT_TOKEN:
        raise RuntimeError("Falta configurar ECONOMY_TOKEN o TOKEN en el archivo .env para leer metadata de Discord.")
    return discord_json_request(
        f"/guilds/{guild_id}/members/{user_id}",
        token=BOT_TOKEN,
        auth_scheme="Bot",
    )


def _permission_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _apply_overwrite(permissions, overwrite):
    permissions &= ~_permission_int(overwrite.get("deny"))
    permissions |= _permission_int(overwrite.get("allow"))
    return permissions


def resolve_member_channel_permissions(guild_id, channel, *, member, roles):
    guild_id = str(guild_id or "")
    role_permissions = {
        str(role.get("id")): _permission_int(role.get("permissions"))
        for role in roles or []
        if role.get("id")
    }
    role_ids = [str(role_id) for role_id in member.get("roles", [])]
    member_id = str(member.get("user", {}).get("id") or "")

    permissions = role_permissions.get(guild_id, 0)
    for role_id in role_ids:
        permissions |= role_permissions.get(role_id, 0)
    if permissions & DISCORD_ADMINISTRATOR:
        return permissions

    overwrites = channel.get("permission_overwrites") or []
    everyone = next(
        (overwrite for overwrite in overwrites if str(overwrite.get("id")) == guild_id and int(overwrite.get("type", -1)) == 0),
        None,
    )
    if everyone:
        permissions = _apply_overwrite(permissions, everyone)

    allow = 0
    deny = 0
    role_id_set = set(role_ids)
    for overwrite in overwrites:
        if int(overwrite.get("type", -1)) != 0 or str(overwrite.get("id")) not in role_id_set:
            continue
        allow |= _permission_int(overwrite.get("allow"))
        deny |= _permission_int(overwrite.get("deny"))
    permissions &= ~deny
    permissions |= allow

    member_overwrite = next(
        (overwrite for overwrite in overwrites if str(overwrite.get("id")) == member_id and int(overwrite.get("type", -1)) == 1),
        None,
    )
    if member_overwrite:
        permissions = _apply_overwrite(permissions, member_overwrite)

    return permissions


def resolve_member_guild_permissions(guild_id, *, member, roles):
    guild_id = str(guild_id or "")
    role_permissions = {
        str(role.get("id")): _permission_int(role.get("permissions"))
        for role in roles or []
    }
    permissions = role_permissions.get(guild_id, 0)
    for role_id in member.get("roles") or []:
        permissions |= role_permissions.get(str(role_id), 0)
    return permissions


def bot_has_server_template_permissions(guild_id):
    bot_user = fetch_discord_bot_user()
    bot_user_id = str(bot_user.get("id") or "")
    if not bot_user_id:
        return False
    roles = fetch_discord_guild_roles(guild_id)
    member = fetch_discord_guild_member(guild_id, bot_user_id)
    permissions = resolve_member_guild_permissions(guild_id, member=member, roles=roles)
    return bool(
        permissions & DISCORD_ADMINISTRATOR
        or (
            permissions & DISCORD_PERM_MANAGE_ROLES
            and permissions & DISCORD_PERM_MANAGE_CHANNELS
        )
    )


def build_server_template_preview_payload(backup_detail, *, target_guild_id, target_guild_name, options=None):
    target_roles = fetch_discord_guild_roles(target_guild_id)
    target_channels = fetch_discord_guild_channels(target_guild_id)
    payload = ServerTemplateService().build_preview(
        backup_detail,
        target_guild_id=target_guild_id,
        target_guild_name=target_guild_name,
        target_roles=target_roles,
        target_channels=target_channels,
        options=options,
    )
    preview = payload.get("preview") or payload
    preview["bot_permissions_ok"] = bot_has_server_template_permissions(target_guild_id)
    if not preview["bot_permissions_ok"]:
        preview.setdefault("warnings", []).append(
            "El bot no tiene Gestionar roles y Gestionar canales en el servidor destino."
        )
    return preview


def build_admin_bot_message_channels_payload(guild_id, *, force_refresh=False):
    guild_id = str(guild_id or "")
    cache_key = guild_id
    now = time.time()
    if not force_refresh:
        with ADMIN_MESSAGE_CHANNELS_CACHE_LOCK:
            cached = ADMIN_MESSAGE_CHANNELS_CACHE.get(cache_key)
            if cached and now < float(cached.get("expires_at") or 0):
                return {"channels": list(cached.get("channels") or []), "cached": True}

    bot_user = fetch_discord_bot_user()
    bot_user_id = str(bot_user.get("id") or "")
    if not bot_user_id:
        raise RuntimeError("No pude identificar el usuario del bot.")

    raw_channels = fetch_discord_guild_channels(guild_id)
    roles = fetch_discord_guild_roles(guild_id)
    member = fetch_discord_guild_member(guild_id, bot_user_id)
    allowed_channels = []
    for channel in raw_channels or []:
        channel_type = int(channel.get("type", -1))
        if channel_type not in (0, 5):
            continue

        permissions = resolve_member_channel_permissions(
            guild_id,
            channel,
            member=member,
            roles=roles,
        )
        has_admin = bool(permissions & DISCORD_ADMINISTRATOR)
        can_view = has_admin or bool(permissions & DISCORD_PERM_VIEW_CHANNEL)
        can_send = has_admin or bool(permissions & DISCORD_PERM_SEND_MESSAGES)
        can_history = has_admin or bool(permissions & DISCORD_PERM_READ_MESSAGE_HISTORY)
        if not (can_view and can_send):
            continue

        allowed_channels.append({
            "id": str(channel.get("id") or ""),
            "name": str(channel.get("name") or channel.get("id") or ""),
            "type": channel_type,
            "can_read_history": can_history,
            "can_manage_messages": has_admin or bool(permissions & DISCORD_PERM_MANAGE_MESSAGES),
        })

    allowed_channels.sort(key=lambda item: item.get("name", "").casefold())
    if force_refresh:
        get_discord_metadata_service().invalidate(str(guild_id), kinds=["channels", "categories"])
    with ADMIN_MESSAGE_CHANNELS_CACHE_LOCK:
        ADMIN_MESSAGE_CHANNELS_CACHE[cache_key] = {
            "channels": list(allowed_channels),
            "expires_at": now + ADMIN_MESSAGE_CHANNELS_CACHE_TTL_SECONDS,
        }
    return {"channels": allowed_channels, "cached": False}


def validate_bot_message_request_payload(body):
    action = str(body.get("action") or "").strip().lower()
    if action not in BOT_MESSAGE_ACTIONS:
        raise ValueError("Accion invalida.")

    guild_id = str(body.get("guild_id") or "").strip()
    channel_id = str(body.get("channel_id") or "").strip()
    message_id = str(body.get("message_id") or "").strip()
    content = str(body.get("content") or "")
    if not guild_id:
        raise ValueError("Debes elegir un servidor.")
    if not channel_id:
        raise ValueError("Debes elegir un canal.")

    if action in {"send", "edit"}:
        content = content.strip()
        if not content:
            raise ValueError("El mensaje no puede estar vacio.")
        if len(content) > BOT_MESSAGE_MAX_LENGTH:
            raise ValueError(f"El mensaje supera el maximo de {BOT_MESSAGE_MAX_LENGTH} caracteres.")
    else:
        content = ""

    if action in {"edit", "delete"} and not message_id.isdigit():
        raise ValueError("Debes indicar un ID de mensaje valido.")

    return {
        "action": action,
        "action_type": BOT_MESSAGE_ACTIONS[action],
        "guild_id": guild_id,
        "channel_id": channel_id,
        "message_id": message_id,
        "content": content,
    }


def validate_bot_message_lookup_query(query):
    guild_id = str(query.get("guild_id", [""])[0] or "").strip()
    channel_id = str(query.get("channel_id", [""])[0] or "").strip()
    message_id = str(query.get("message_id", [""])[0] or "").strip()
    if not guild_id:
        raise ValueError("Debes elegir un servidor.")
    if not channel_id:
        raise ValueError("Debes elegir un canal.")
    if not message_id.isdigit():
        raise ValueError("Debes indicar un ID de mensaje valido.")
    return guild_id, channel_id, message_id


def fetch_admin_bot_message_for_edit(guild_id, channel_id, message_id):
    channels_payload = build_admin_bot_message_channels_payload(guild_id)
    channels_by_id = {
        str(channel.get("id")): channel
        for channel in channels_payload.get("channels", [])
    }
    channel = channels_by_id.get(str(channel_id))
    if not channel:
        raise PermissionError("El bot no tiene permisos suficientes en ese canal.")
    if not channel.get("can_read_history"):
        raise PermissionError("Para editar mensajes el bot debe poder leer el historial del canal.")

    bot_user = fetch_discord_bot_user()
    bot_user_id = str(bot_user.get("id") or "")
    message = discord_json_request(
        f"/channels/{channel_id}/messages/{message_id}",
        token=BOT_TOKEN,
        auth_scheme="Bot",
    )
    author = message.get("author") if isinstance(message.get("author"), dict) else {}
    if str(author.get("id") or "") != bot_user_id:
        raise PermissionError("Solo se pueden editar mensajes enviados por este bot.")

    return {
        "id": str(message.get("id") or ""),
        "channel_id": str(channel_id),
        "content": str(message.get("content") or ""),
        "created_at": discord_timestamp_to_display(message.get("timestamp")),
    }


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


def ticket_record_identity(record):
    for key in ("record_id", "channel_id", "fine_id", "number", "ticket_id", "id"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    return ""


def truthy_record_flag(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def ticket_record_status(record):
    raw_status = str(record.get("status") or "open").strip().lower()
    if raw_status == "deleted" or truthy_record_flag(record.get("is_deleted")) or record.get("deleted_at"):
        return "deleted"
    if raw_status in {"closed", "paid", "resolved"}:
        return "closed"
    if record.get("closed_at"):
        return "closed"
    return "open"


def ticket_record_type(record):
    if str(record.get("ticket_type") or "").strip().lower() == "fine":
        return "fine"
    if str(record.get("panel_id") or "") == "__fine__" or record.get("fine_id"):
        return "fine"
    return "normal"


FINE_EXPORT_FIELDS = (
    "id",
    "guild_id",
    "guild_name",
    "report_ava",
    "fined_user_id",
    "fined_user_name",
    "amount",
    "reason",
    "proof_path",
    "proof_name",
    "status",
    "is_deleted",
    "blocked_role_id",
    "resolver_role_id",
    "ticket_channel_id",
    "ticket_message_id",
    "announcement_channel_id",
    "announcement_message_id",
    "created_by_id",
    "created_by_name",
    "paid_by_id",
    "paid_by_name",
    "created_at",
    "updated_at",
    "paid_at",
    "closed_at",
    "deleted_at",
)


def fine_payload_from_record(record):
    fine = record.get("fine") if isinstance(record.get("fine"), dict) else {}
    payload = {key: fine.get(key) for key in FINE_EXPORT_FIELDS if key in fine}
    aliases = {
        "id": record.get("fine_id") or record.get("id") or record.get("number"),
        "guild_id": record.get("guild_id"),
        "report_ava": record.get("report_ava"),
        "fined_user_id": record.get("fined_user_id") or record.get("owner_id"),
        "fined_user_name": record.get("fined_user_name") or record.get("owner_name"),
        "amount": record.get("amount"),
        "reason": record.get("reason"),
        "proof_path": record.get("proof_path"),
        "proof_name": record.get("proof_name"),
        "status": record.get("fine_status") or fine.get("status"),
        "is_deleted": record.get("is_deleted"),
        "blocked_role_id": record.get("blocked_role_id"),
        "resolver_role_id": record.get("resolver_role_id"),
        "ticket_channel_id": record.get("ticket_channel_id") or record.get("channel_id"),
        "ticket_message_id": record.get("ticket_message_id"),
        "announcement_channel_id": record.get("announcement_channel_id"),
        "announcement_message_id": record.get("announcement_message_id"),
        "created_by_id": record.get("created_by_id"),
        "created_by_name": record.get("created_by_name"),
        "paid_by_id": record.get("paid_by_id"),
        "paid_by_name": record.get("paid_by_name"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "paid_at": record.get("paid_at"),
        "closed_at": record.get("fine_closed_at") or fine.get("closed_at"),
        "deleted_at": record.get("deleted_at"),
    }
    for key, value in aliases.items():
        if value not in (None, ""):
            payload[key] = value
    if "id" in payload:
        payload["id"] = str(payload.get("id") or "")
    if "amount" in payload:
        try:
            payload["amount"] = int(payload.get("amount") or 0)
        except (TypeError, ValueError):
            payload["amount"] = 0
    payload["is_deleted"] = truthy_record_flag(payload.get("is_deleted"))
    return payload


def fine_to_ticket_record(fine):
    fine_id = int(fine.get("id") or 0)
    is_deleted = bool(int(fine.get("is_deleted") or 0)) or bool(fine.get("deleted_at"))
    fine_status = str(fine.get("status") or "open").lower()
    ticket_status = "deleted" if is_deleted else "closed" if fine_status == "paid" else "open"
    fine_payload = fine_payload_from_record({**dict(fine), "fine_id": fine_id, "fine_status": fine_status})
    return {
        "number": fine_id,
        "status": ticket_status,
        "fine_status": fine_status,
        "is_deleted": is_deleted,
        "ticket_type": "fine",
        "fine_id": str(fine_id),
        "guild_id": str(fine.get("guild_id") or ""),
        "channel_id": str(fine.get("ticket_channel_id") or ""),
        "channel_name": f"multa-{fine_id:04d}" if fine_id else "",
        "owner_id": str(fine.get("fined_user_id") or ""),
        "owner_name": str(fine.get("fined_user_name") or ""),
        "panel_id": "__fine__",
        "panel_name": "Multa",
        "option_id": "",
        "option_label": "",
        "claimed_by_id": "",
        "claimed_by_name": "",
        "created_at": str(fine.get("created_at") or ""),
        "closed_at": str(fine.get("closed_at") or ""),
        "deleted_at": str(fine.get("deleted_at") or ""),
        "transcript": [],
        "fine": fine_payload,
    }


def normalize_ticket_record(record):
    normalized = dict(record)
    ticket_type = ticket_record_type(normalized)
    status = ticket_record_status(normalized)
    transcript = normalized.get("transcript") if isinstance(normalized.get("transcript"), list) else []
    normalized["status"] = status
    normalized["ticket_type"] = ticket_type
    normalized["type_label"] = "Multa" if ticket_type == "fine" else "Ticket"
    normalized["record_id"] = ticket_record_identity(normalized)
    normalized["user_id"] = str(normalized.get("owner_id") or normalized.get("fined_user_id") or "")
    normalized["user_name"] = str(normalized.get("owner_name") or normalized.get("fined_user_name") or "")
    normalized["has_transcript"] = bool(normalized.get("transcribed_at") or transcript)
    normalized["transcript_count"] = len(transcript)
    normalized["deleted_at"] = str(normalized.get("deleted_at") or "")
    if ticket_type == "fine":
        fine_payload = fine_payload_from_record(normalized)
        normalized["fine"] = fine_payload
        normalized["fine_id"] = str(normalized.get("fine_id") or fine_payload.get("id") or "")
        normalized["fine_status"] = str(normalized.get("fine_status") or fine_payload.get("status") or "")
        normalized["amount"] = fine_payload.get("amount", normalized.get("amount") or 0)
        normalized["reason"] = fine_payload.get("reason", normalized.get("reason") or "")
        normalized["report_ava"] = fine_payload.get("report_ava", normalized.get("report_ava") or "")
        normalized["proof_name"] = fine_payload.get("proof_name", normalized.get("proof_name") or "")
    return normalized


def _ticket_record_search_blob(record):
    values = [
        record.get("record_id"),
        record.get("number"),
        record.get("ticket_type"),
        record.get("type_label"),
        record.get("channel_id"),
        record.get("channel_name"),
        record.get("user_id"),
        record.get("user_name"),
        record.get("panel_name"),
        record.get("option_label"),
        record.get("claimed_by_name"),
        record.get("report_ava"),
        record.get("reason"),
        (record.get("fine") or {}).get("reason") if isinstance(record.get("fine"), dict) else "",
        (record.get("fine") or {}).get("report_ava") if isinstance(record.get("fine"), dict) else "",
    ]
    return " ".join(str(value or "") for value in values).lower()


def _parse_ticket_record_date(value):
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
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _ticket_record_sort_key(record):
    for field in ("created_at", "closed_at", "deleted_at", "transcribed_at"):
        parsed = _parse_ticket_record_date(record.get(field))
        if parsed:
            return parsed
    return datetime.min


def ticket_record_matches_type(record, record_type):
    record_type = str(record_type or "").strip().lower()
    if not record_type:
        return True
    if record_type in {"fine", "normal"}:
        return ticket_record_type(record) == record_type
    if record_type.startswith("panel:"):
        panel_id = record_type.split(":", 1)[1]
        return str(record.get("panel_id") or "").strip().lower() == panel_id
    return str(record.get("panel_name") or "").strip().lower() == record_type


def _parse_date_filter(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def merge_ticket_record(existing, incoming):
    merged = dict(existing or {})
    incoming = dict(incoming or {})
    existing_status = ticket_record_status(merged)
    incoming_status = ticket_record_status(incoming)

    for key, value in incoming.items():
        if key in {"transcript", "transcribed_at", "claimed_by_id", "claimed_by_name"} and merged.get(key):
            continue
        if key in {"status", "closed_at", "deleted_at", "is_deleted"}:
            continue
        if value not in (None, "", []):
            merged[key] = value

    if incoming.get("fine"):
        merged["fine"] = {
            **(merged.get("fine") if isinstance(merged.get("fine"), dict) else {}),
            **incoming.get("fine"),
        }

    if existing_status == "deleted" or incoming_status == "deleted":
        merged["status"] = "deleted"
        merged["is_deleted"] = True
        merged["deleted_at"] = merged.get("deleted_at") or incoming.get("deleted_at") or ""
    elif existing_status == "closed" or incoming_status == "closed":
        merged["status"] = "closed"
    else:
        merged["status"] = "open"

    merged["closed_at"] = merged.get("closed_at") or incoming.get("closed_at") or ""
    return normalize_ticket_record(merged)


def get_all_guild_ticket_records(guild_id):
    records = [normalize_ticket_record(record) for record in get_guild_ticket_records(guild_id)]
    fine_indexes = {
        str(record.get("fine_id") or ""): index
        for index, record in enumerate(records)
        if ticket_record_type(record) == "fine" and record.get("fine_id")
    }
    channel_indexes = {
        str(record.get("channel_id") or ""): index
        for index, record in enumerate(records)
        if record.get("channel_id")
    }
    for fine in FineService().get_ticket_records(guild_id):
        fine_record = normalize_ticket_record(fine_to_ticket_record(fine))
        fine_id = str(fine_record.get("fine_id") or "")
        channel_id = str(fine_record.get("channel_id") or "")
        existing_index = fine_indexes.get(fine_id) if fine_id else None
        if existing_index is None and channel_id:
            existing_index = channel_indexes.get(channel_id)
        if existing_index is not None:
            records[existing_index] = merge_ticket_record(records[existing_index], fine_record)
            continue
        records.append(fine_record)
        record_index = len(records) - 1
        if fine_id:
            fine_indexes[fine_id] = record_index
        if channel_id:
            channel_indexes[channel_id] = record_index
    return records


def ticket_records_summary(records):
    today = datetime.now(ARGENTINA_TZ).strftime("%d/%m/%Y")
    summary = {
        "open": 0,
        "closed": 0,
        "claimed": 0,
        "closed_today": 0,
        "transcribed": 0,
        "deleted": 0,
        "normal": 0,
        "fine": 0,
        "total": len(records),
        "updated_at": datetime.now(ARGENTINA_TZ).strftime("%d/%m/%Y | %H:%M:%S"),
    }
    for record in records:
        status = ticket_record_status(record)
        ticket_type = ticket_record_type(record)
        if status == "open":
            summary["open"] += 1
        if status == "closed":
            summary["closed"] += 1
        if record.get("claimed_by_id"):
            summary["claimed"] += 1
        if status == "deleted":
            summary["deleted"] += 1
        if ticket_type in {"normal", "fine"}:
            summary[ticket_type] += 1
        if record.get("transcribed_at") or record.get("transcript"):
            summary["transcribed"] += 1
        if str(record.get("closed_at") or "").startswith(today):
            summary["closed_today"] += 1
    return summary


def get_guild_ticket_records_page(guild_id, params):
    records = get_all_guild_ticket_records(guild_id)
    query = str(params["search"] or "").strip().lower()
    status = str(params["status"] or "").strip().lower()
    record_type = str(params["record_type"] or "").strip().lower()
    sort_order = str(params.get("sort") or "newest").strip().lower()
    date_from = str(params["date_from"] or "").strip()
    date_to = str(params["date_to"] or "").strip()

    filtered = []
    for record in records:
        if query and query not in _ticket_record_search_blob(record):
            continue
        if status and ticket_record_status(record) != status:
            continue
        if not ticket_record_matches_type(record, record_type):
            continue
        if date_from or date_to:
            record_date = None
            for field in ("created_at", "closed_at", "deleted_at", "transcribed_at"):
                record_date = _parse_ticket_record_date(record.get(field))
                if record_date:
                    break
            from_date = _parse_date_filter(date_from)
            to_date = _parse_date_filter(date_to)
            if not record_date:
                continue
            if from_date and record_date.date() < from_date:
                continue
            if to_date and record_date.date() > to_date:
                continue
        filtered.append(record)

    filtered.sort(key=_ticket_record_sort_key, reverse=sort_order != "oldest")
    total_items = len(filtered)
    offset = (params["page"] - 1) * params["page_size"]
    paged = filtered[offset:offset + params["page_size"]]
    return page_response(
        paged,
        params["page"],
        params["page_size"],
        total_items,
        item_key="records",
        extra={"summary": ticket_records_summary(records)},
    )


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
    for record in get_all_guild_ticket_records(guild_id):
        if str(record.get("record_id") or record.get("channel_id") or record.get("number") or "") == str(record_id):
            return record
    return None


def ticket_record_transcript(record):
    transcript = record.get("transcript") if isinstance(record.get("transcript"), list) else []
    return transcript


def safe_export_filename(value, fallback="ticket"):
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.-]+", "-", text)
    text = text.strip(".-")
    return text or fallback


def build_ticket_export_payload(guild_id, guild_name, record):
    transcript = ticket_record_transcript(record)
    if not transcript:
        raise ValueError("Este ticket no tiene transcripcion disponible para exportar.")

    record_id = record.get("record_id") or ticket_record_identity(record)
    ticket_type = record.get("ticket_type") or ticket_record_type(record)
    user_id = record.get("user_id") or record.get("owner_id") or record.get("fined_user_id") or ""
    user_name = record.get("user_name") or record.get("owner_name") or record.get("fined_user_name") or ""
    channel_name = record.get("channel_name") or f"ticket-{record.get('number', record_id)}"
    return {
        "guild_id": str(guild_id),
        "guild_name": str(guild_name or f"Servidor {guild_id}"),
        "exported_at": datetime.now(ARGENTINA_TZ).strftime("%d/%m/%Y | %H:%M:%S"),
        "ticket": {
            "record_id": str(record_id or ""),
            "number": record.get("number"),
            "server": {
                "id": str(guild_id),
                "name": str(guild_name or f"Servidor {guild_id}"),
            },
            "channel": {
                "id": str(record.get("channel_id") or ""),
                "name": str(channel_name or ""),
            },
            "user": {
                "id": str(user_id or ""),
                "name": str(user_name or ""),
            },
            "ticket_type": str(ticket_type or "normal"),
            "type_label": record.get("type_label") or ("Multa" if ticket_type == "fine" else "Ticket"),
            "panel_id": str(record.get("panel_id") or ""),
            "panel_name": str(record.get("panel_name") or ""),
            "option_id": str(record.get("option_id") or ""),
            "option_label": str(record.get("option_label") or ""),
            "status": ticket_record_status(record),
            "created_at": str(record.get("created_at") or ""),
            "closed_at": str(record.get("closed_at") or ""),
            "deleted_at": str(record.get("deleted_at") or ""),
            "transcribed_at": str(record.get("transcribed_at") or ""),
            "fine_id": str(record.get("fine_id") or ""),
            "fine": fine_payload_from_record(record) if ticket_record_type(record) == "fine" else None,
        },
        "transcript": {
            "message_count": len(transcript),
            "messages": transcript,
            "content_text": "\n".join(
                f"[{message.get('created_at', '')}] {message.get('author_name') or message.get('author') or 'Usuario'}: {message.get('content') or ''}"
                for message in transcript
                if isinstance(message, dict)
            ),
        },
    }


def delete_guild_ticket_record(guild_id, record_id):
    guild_id = str(guild_id)
    record_id = str(record_id)
    current_record = get_ticket_record(guild_id, record_id)
    if current_record and ticket_record_type(current_record) == "fine":
        fine_id = str(current_record.get("fine_id") or current_record.get("number") or "").strip()
        if not fine_id.isdigit():
            LOGGER.warning("No pude aplicar borrado logico a multa sin fine_id guild=%s record=%s", guild_id, record_id)
            return False

        fine = FineRepository().soft_delete(int(fine_id))
        if fine is None:
            LOGGER.warning("No encontre multa para borrado logico guild=%s fine_id=%s record=%s", guild_id, fine_id, record_id)
            return False

        deleted_at = str(fine.get("deleted_at") or datetime.now(ARGENTINA_TZ).strftime("%d/%m/%Y | %H:%M"))

        def mark_fine_record(data):
            for record in data.get(guild_id, []) if isinstance(data, dict) else []:
                identifiers = {
                    str(record.get("record_id") or ""),
                    str(record.get("channel_id") or ""),
                    str(record.get("fine_id") or ""),
                    str(record.get("number") or ""),
                }
                if record_id not in identifiers and fine_id not in identifiers:
                    continue
                record["status"] = "deleted"
                record["is_deleted"] = True
                record["deleted_at"] = deleted_at
                record["fine"] = fine_payload_from_record({**record, **fine, "fine_id": fine_id})
            return data

        mutate_json_file_safe(TICKET_RECORDS_FILE, {}, mark_fine_record)
        return True

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
    return PermissionService.normalize_permissions(values, include_system_permissions=False)


def get_guild_bot_permissions(guild_id, *, actor_role_ids=None, is_actor_admin=False):
    service = PermissionService()
    visible_permissions = service.get_role_permissions(guild_id, include_system_permissions=False)
    hidden_permissions = service.get_hidden_role_permissions(guild_id)
    cleaned = {}
    for role_id, permissions in visible_permissions.items():
        normalized = normalize_bot_permission_values(permissions)
        if normalized:
            cleaned[str(role_id)] = normalized

    manageable_permissions = service.manageable_permission_keys(
        guild_id,
        role_ids=actor_role_ids or [],
        is_admin=is_actor_admin,
    )
    return {
        "permissions": cleaned,
        "system_permissions": hidden_permissions,
        "options": [
            {
                "key": definition.key,
                "label": definition.label,
                "description": definition.description,
                "category": definition.category,
                "module": definition.module,
                "scope": definition.scope,
                "assignable": definition.assignable,
                "editable": is_actor_admin or definition.key in manageable_permissions,
            }
            for definition in service.list_public_permissions()
        ],
        "manageable_permissions": sorted(manageable_permissions),
        "read_only_role_ids": [] if is_actor_admin else [str(role_id) for role_id in actor_role_ids or []],
        "can_edit": bool(is_actor_admin or manageable_permissions),
    }


def save_guild_bot_permissions(guild_id, payload, *, actor_role_ids=None, is_actor_admin=False):
    service = PermissionService()
    permissions = payload.get("permissions", payload) if isinstance(payload, dict) else {}
    if not isinstance(permissions, dict):
        return None, "La configuracion de permisos no es valida."

    visible_permissions = service.get_role_permissions(guild_id, include_system_permissions=False)
    hidden_permissions = service.get_hidden_role_permissions(guild_id)
    touched_roles = payload.get("role_ids", []) if isinstance(payload, dict) else []
    if not isinstance(touched_roles, list):
        touched_roles = []
    touched_role_ids = {
        str(role_id or "").strip()
        for role_id in touched_roles
        if str(role_id or "").strip().isdigit()
    }

    actor = type("DashboardActor", (), {
        "roles": [type("DashboardRole", (), {"id": current_role_id})() for current_role_id in actor_role_ids or []],
        "guild_permissions": type("DashboardPermissions", (), {"administrator": bool(is_actor_admin)})(),
        "guild": type("DashboardGuild", (), {"owner_id": None})(),
        "id": None,
    })()

    next_visible_permissions = {
        str(role_id): normalize_bot_permission_values(values)
        for role_id, values in visible_permissions.items()
    }
    for role_id, values in permissions.items():
        role_id = str(role_id or "").strip()
        if not role_id.isdigit():
            continue
        touched_role_ids.add(role_id)
        next_visible_permissions.setdefault(role_id, [])
        normalized_values = normalize_bot_permission_values(values)
        error = service.validate_role_permission_update(
            guild_id,
            actor,
            role_id,
            normalized_values,
        )
        if error:
            return None, error
        next_visible_permissions[role_id] = normalized_values

    for role_id in touched_role_ids:
        error = service.validate_role_permission_update(
            guild_id,
            actor,
            role_id,
            next_visible_permissions.get(role_id, []),
        )
        if error:
            return None, error
        if role_id not in permissions:
            next_visible_permissions[role_id] = []

    service.set_role_permissions(
        guild_id,
        next_visible_permissions,
        preserve_hidden_permissions=hidden_permissions,
    )
    return get_guild_bot_permissions(
        guild_id,
        actor_role_ids=actor_role_ids,
        is_actor_admin=is_actor_admin,
    ), None


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
            "ticket_open_content": str(option.get("ticket_open_content") or "")[:2000],
            "ticket_open_title": str(option.get("ticket_open_title") or "")[:256],
            "ticket_open_description": str(option.get("ticket_open_description") or "")[:4000],
            "ticket_open_color": str(option.get("ticket_open_color") or "")[:20],
            "ticket_open_footer": str(option.get("ticket_open_footer") or "")[:2048],
            "ticket_open_image_url": str(option.get("ticket_open_image_url") or "")[:500],
            "ticket_open_thumbnail_url": str(option.get("ticket_open_thumbnail_url") or "")[:500],
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
            "owner_permissions": normalize_ticket_owner_permissions(permissions),
            "add_member_roles": normalize_id_list(permissions.get("add_member_roles"))[:3],
            "add_member_user_ids": normalize_digit_id_list(permissions.get("add_member_user_ids"))[:10],
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


def normalize_digit_id_list(value):
    return [item for item in normalize_id_list(value) if str(item).isdigit()]


def normalize_ticket_owner_permissions(permissions):
    values = permissions.get("owner_permissions")
    if not isinstance(values, list):
        return list(DEFAULT_TICKET_OWNER_PERMISSIONS)

    keys = [
        str(value)
        for value in values
        if str(value) in TICKET_CHANNEL_PERMISSION_KEYS
    ]
    return keys


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
    return database_connection()


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
        balance["user_name"] = resolve_dashboard_user_name(
            guild_id,
            balance.get("user_id"),
            balance.get("user_name"),
        )
        balance["member_status"] = get_discord_member_status(guild_id, balance.get("user_id"))
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
            reason,
            player_status,
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
        "sort": query_text(query, "sort", "newest").strip(),
        "date_from": query_text(query, "date_from", "").strip(),
        "date_to": query_text(query, "date_to", "").strip(),
    }


def serialize_balance_item(item, guild_id=None):
    payload = dict(item)
    payload["user_name"] = resolve_dashboard_user_name(
        guild_id or payload.get("guild_id"),
        payload.get("user_id"),
        payload.get("user_name"),
    )
    payload["member_status"] = get_discord_member_status(
        guild_id or payload.get("guild_id"),
        payload.get("user_id"),
    )
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
        "is_deleted": bool(int(fine.get("is_deleted") or 0)),
        "created_by_name": str(fine.get("created_by_name") or ""),
        "paid_by_name": str(fine.get("paid_by_name") or ""),
        "created_at": str(fine.get("created_at") or ""),
        "paid_at": str(fine.get("paid_at") or ""),
        "deleted_at": str(fine.get("deleted_at") or ""),
        "ticket_channel_id": str(fine.get("ticket_channel_id") or ""),
    }


def apply_dashboard_balance_change(guild_id, body, session):
    identifier = str(body.get("user") or body.get("user_id") or body.get("identifier") or "").strip()
    category = str(body.get("category") or "").strip().lower()
    action = str(body.get("action") or "remove").strip().lower()
    reason = str(body.get("reason") or "").strip()

    if category not in {"items", "silver"}:
        raise ValueError("Selecciona una categoria valida.")
    if action not in {"add", "remove"}:
        raise ValueError("Selecciona una accion valida.")
    if not identifier:
        raise ValueError("Debes indicar un usuario.")

    try:
        amount = int(str(body.get("amount") or "").strip())
    except (TypeError, ValueError):
        raise ValueError("La cantidad debe ser un numero entero.")
    if amount <= 0:
        raise ValueError("La cantidad debe ser mayor a 0.")

    balance_repo = BalanceRepository()
    resolved = balance_repo.resolve_existing_user(guild_id, identifier)
    if not resolved:
        raise LookupError("No encontre ese usuario en la base historica de economia.")

    player_status = get_discord_member_status(guild_id, resolved["user_id"])
    previous_balance, new_balance = balance_repo.modify_existing_balance(
        guild_id,
        resolved["user_id"],
        amount,
        category,
        add=action == "add",
    )
    player_name = resolve_dashboard_user_name(guild_id, resolved["user_id"], resolved.get("user_name"))
    balance_repo.update_user_name(guild_id, resolved["user_id"], player_name)
    viewer = session.get("user", {}) if isinstance(session, dict) else {}
    operator_name = str(viewer.get("global_name") or viewer.get("username") or "Dashboard")
    operator_id = str(viewer.get("id") or "")
    now = datetime.now(ARGENTINA_TZ)
    OperationRepository().append(
        guild_id,
        {
            "action": "Dashboard balance",
            "operator": operator_name,
            "operator_id": operator_id,
            "player": player_name,
            "player_id": str(resolved["user_id"]),
            "type": "ADD" if action == "add" else "REMOVE",
            "category": "Items" if category == "items" else "Silver",
            "amount": amount,
            "previous_balance": previous_balance,
            "new_balance": new_balance,
            "reason": reason,
            "player_status": player_status,
            "date": now.strftime("%d/%m/%Y"),
            "time": now.strftime("%H:%M"),
        },
    )

    updated = balance_repo.get_balance_record(guild_id, resolved["user_id"])
    return {
        "balance": serialize_balance_item(updated or resolved, guild_id),
        "operation": {
            "player": player_name,
            "player_id": str(resolved["user_id"]),
            "previous_balance": previous_balance,
            "new_balance": new_balance,
            "player_status": player_status,
        },
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


def discord_guild_icon_url(guild_id, icon_hash):
    guild_id = str(guild_id or "")
    icon_hash = str(icon_hash or "")
    if not guild_id or not icon_hash:
        return ""
    extension = "gif" if icon_hash.startswith("a_") else "png"
    return f"https://cdn.discordapp.com/icons/{guild_id}/{icon_hash}.{extension}?size=128"


def fetch_discord_guild_summary(guild_id):
    if not BOT_TOKEN:
        return {}
    guild_id = str(guild_id or "")
    now = time.time()
    with GUILD_SUMMARY_CACHE_LOCK:
        entry = GUILD_SUMMARY_CACHE.get(guild_id)
        if entry and entry.get("expires_at", 0) > now:
            return dict(entry.get("summary") or {})

    try:
        guild = discord_json_request(
            f"/guilds/{guild_id}?with_counts=true",
            token=BOT_TOKEN,
            auth_scheme="Bot",
        )
        summary = guild if isinstance(guild, dict) else {}
        with GUILD_SUMMARY_CACHE_LOCK:
            GUILD_SUMMARY_CACHE[guild_id] = {
                "expires_at": now + GUILD_SUMMARY_TTL_SECONDS,
                "summary": summary,
            }
        return summary
    except Exception as exc:
        LOGGER.warning("No pude cargar resumen administrativo guild=%s: %s", guild_id, exc)
        return {}


def fetch_discord_guild_metadata_counts(guild_id):
    try:
        metadata = get_discord_metadata_payload(guild_id, kinds=["channels", "roles"], force_refresh=False)
    except Exception as exc:
        LOGGER.warning("No pude cargar metadata administrativa guild=%s: %s", guild_id, exc)
        return {
            "channel_count": None,
            "role_count": None,
            "metadata_available": False,
        }

    channels = metadata.get("channels", []) if isinstance(metadata, dict) else []
    roles = metadata.get("roles", []) if isinstance(metadata, dict) else []
    return {
        "channel_count": len(channels) if isinstance(channels, list) else None,
        "role_count": len(roles) if isinstance(roles, list) else None,
        "metadata_available": bool(channels or roles),
    }


def has_saved_guild_config(guild_id):
    guild_id = str(guild_id or "")
    if not guild_id:
        return False
    init_database()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM guild_config WHERE guild_id = ? LIMIT 1",
            (guild_id,),
        ).fetchone()
    if row:
        return True

    legacy_config = read_json_file(os.path.join(DATA_DIR, "config.json"), {})
    return isinstance(legacy_config, dict) and bool(legacy_config.get(guild_id))


def build_admin_guild_summary(guild_id, guild_name=None, icon_hash=None, bot_guild_ids=None):
    guild_id = str(guild_id or "")
    guild_summary = fetch_discord_guild_summary(guild_id)
    counts = fetch_discord_guild_metadata_counts(guild_id)
    bot_present = bot_guild_ids is None or guild_id in bot_guild_ids
    resolved_icon = guild_summary.get("icon") or icon_hash or ""

    return {
        "id": guild_id,
        "name": str(guild_summary.get("name") or guild_name or f"Servidor {guild_id}"),
        "icon_url": discord_guild_icon_url(guild_id, resolved_icon),
        "bot": {
            "status": "connected" if bot_present else "not_in_server",
            "present": bot_present,
        },
        "channel_count": counts["channel_count"],
        "role_count": counts["role_count"],
        "metadata_available": bool(counts["metadata_available"] or guild_summary),
        "has_saved_config": has_saved_guild_config(guild_id),
    }


def get_admin_overview_payload(guild_id, guild_name=None):
    guild_id = str(guild_id or "")
    guild_summary = fetch_discord_guild_summary(guild_id)
    counts = fetch_discord_guild_metadata_counts(guild_id)
    bot_guild_ids = get_bot_guild_ids()
    member_count = guild_summary.get("approximate_member_count")
    if member_count is None:
        member_count = guild_summary.get("member_count")
    bot_present = bot_guild_ids is None or guild_id in bot_guild_ids

    return {
        "server": {
            "id": guild_id,
            "name": str(guild_summary.get("name") or guild_name or f"Servidor {guild_id}"),
            "icon_url": discord_guild_icon_url(guild_id, guild_summary.get("icon")),
            "member_count": member_count,
            "channel_count": counts["channel_count"],
            "role_count": counts["role_count"],
            "bot_present": bot_present,
            "has_saved_config": has_saved_guild_config(guild_id),
        },
        "bot": {
            "status": "connected" if bot_present else "not_in_server",
            "metadata_available": bool(counts["metadata_available"] or guild_summary),
        },
        "future_actions": [
            {
                "key": "multi_server",
                "label": "Vista multi-servidor",
                "status": "planned",
                "description": "Base preparada para inventario y comparativas entre servidores autorizados.",
            },
            {
                "key": "bot_messages",
                "label": "Mensajes del bot",
                "status": "planned",
                "description": "Administracion centralizada de mensajes publicados por el bot.",
            },
            {
                "key": "backups",
                "label": "Backups",
                "status": "planned",
                "description": "Punto de entrada reservado para respaldos y restauracion controlada.",
            },
            {
                "key": "templates",
                "label": "Plantillas avanzadas",
                "status": "planned",
                "description": "Extension futura para plantillas globales y por servidor.",
            },
            {
                "key": "advanced_config",
                "label": "Configuracion avanzada",
                "status": "planned",
                "description": "Configuraciones sensibles con auditoria y permisos estrictos.",
            },
        ],
    }


def get_economy_list_payload(guild_id, tab, params):
    tab = str(tab or "balances")
    if tab == "balances":
        payload = BalanceRepository().list_balances_page(
            guild_id,
            page=params["page"],
            page_size=params["page_size"],
            search=params["search"],
        )
        items = [serialize_balance_item(item, guild_id) for item in payload.pop("items", [])]
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
    init_database()
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
LANDING_HTML = load_dashboard_template("landing.html")
BOT_INVITE_PLACEHOLDER = "<!--BOT_INVITE_URL-->"


def render_login_html(next_path):
    return LOGIN_HTML.replace(
        "<!--DASHBOARD_NEXT_INPUT-->",
        f'<input type="hidden" name="next" value="{html.escape(next_path, quote=True)}">',
    )


def build_bot_invite_url():
    client_id = str(DASHBOARD_CLIENT_ID or "").strip()
    if not client_id:
        return "https://discord.com/developers/applications"

    params = urlencode({
        "client_id": client_id,
        "scope": "bot applications.commands",
        "permissions": str(DISCORD_ADMINISTRATOR),
    })
    return f"https://discord.com/oauth2/authorize?{params}"


def render_landing_html():
    return LANDING_HTML.replace(
        BOT_INVITE_PLACEHOLDER,
        html.escape(build_bot_invite_url(), quote=True),
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

    def dashboard_admin_security_service(self):
        global DASHBOARD_ADMIN_SECURITY_SERVICE
        with DASHBOARD_ADMIN_SECURITY_LOCK:
            if DASHBOARD_ADMIN_SECURITY_SERVICE is None:
                DASHBOARD_ADMIN_SECURITY_SERVICE = DashboardAdminSecurityService(
                    session_store=SESSION_STORE,
                )
            return DASHBOARD_ADMIN_SECURITY_SERVICE

    def server_backup_service(self):
        return ServerBackupService(
            fetch_guild_summary=fetch_discord_guild_summary,
            fetch_roles=fetch_discord_guild_roles,
            fetch_channels=fetch_discord_guild_channels,
        )

    def server_template_service(self):
        return ServerTemplateService()

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
        guild_id = str(guild_id or "")
        if not guild_id:
            return False
        bot_guild_ids = get_bot_guild_ids()
        if bot_guild_ids is not None and guild_id not in bot_guild_ids:
            return False
        if guild_id not in self.session_member_guild_ids(session):
            return False
        if self.is_guild_admin(session, guild_id):
            return True
        role_ids = self.session_role_ids(session, guild_id)
        return self.permission_service().has_module_access(guild_id, module_key, role_ids=role_ids)

    def has_guild_permission(self, session, guild_id, *permission_keys):
        guild_id = str(guild_id or "")
        if not guild_id:
            return False
        bot_guild_ids = get_bot_guild_ids()
        if bot_guild_ids is not None and guild_id not in bot_guild_ids:
            return False
        if guild_id not in self.session_member_guild_ids(session):
            return False
        if self.is_guild_admin(session, guild_id):
            return True
        role_ids = self.session_role_ids(session, guild_id)
        return self.permission_service().has_module_access(
            guild_id,
            "",
            role_ids=role_ids,
            required_permissions=permission_keys,
        )

    def can_access_tickets(self, session, guild_id):
        return self.can_access_module(session, guild_id, MODULE_TICKETS)

    def can_access_guild_or_tickets(self, session, guild_id):
        return self.can_access_guild(session, guild_id) or self.can_access_tickets(session, guild_id)

    def can_access_any_dashboard_module(self, session, guild_id):
        if self.is_guild_admin(session, guild_id):
            return True
        role_ids = self.session_role_ids(session, guild_id)
        return self.permission_service().has_any_dashboard_access(guild_id, role_ids=role_ids)

    def can_access_admin_panel(self, session, guild_id):
        return self.can_access_module(session, guild_id, MODULE_ADMIN_PANEL)

    def can_access_any_admin_panel(self, session):
        allowed_guilds = self.dashboard_allowed_guilds(session)
        return any(
            self.can_access_admin_panel(session, guild_id)
            for guild_id in allowed_guilds
        )

    def session_guild_map(self, session):
        guilds = {}
        for guild in (session.get("guilds") or []) + (session.get("admin_guilds") or []):
            guild_id = str(guild.get("id") or "")
            if not guild_id or guild_id in guilds:
                continue
            guilds[guild_id] = {
                "id": guild_id,
                "name": str(guild.get("name") or f"Servidor {guild_id}"),
                "icon": str(guild.get("icon") or ""),
            }
        return guilds

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

    def admin_panel_guilds_payload(self, session):
        bot_guild_ids = get_bot_guild_ids()
        guilds_by_id = self.session_guild_map(session)
        allowed_guilds = self.dashboard_allowed_guilds(session)
        summaries = []
        for guild_id, guild_name in allowed_guilds.items():
            if not self.can_access_admin_panel(session, guild_id):
                continue
            if bot_guild_ids is not None and guild_id not in bot_guild_ids:
                continue
            session_guild = guilds_by_id.get(guild_id, {})
            summaries.append(build_admin_guild_summary(
                guild_id,
                guild_name=session_guild.get("name") or guild_name,
                icon_hash=session_guild.get("icon"),
                bot_guild_ids=bot_guild_ids,
            ))

        summaries.sort(key=lambda guild: str(guild.get("name") or "").casefold())
        return {
            "guilds": summaries,
            "selectedGuildId": str(session.get("last_admin_panel_guild_id") or ""),
        }

    def dashboard_access_payload(self, session, guild_id):
        guild_id = str(guild_id or "")
        if not guild_id:
            return {
                "admin": False,
                "economy": False,
                "tickets": False,
                "fines": False,
                "audit": False,
                "templates": False,
                "permissions": False,
                "adminPanel": False,
                "registration": False,
                "loot": False,
                "reportCalculator": False,
                "welcome": False,
            }
        admin = self.is_guild_admin(session, guild_id)
        return {
            "admin": admin,
            "economy": self.can_access_module(session, guild_id, MODULE_ECONOMY),
            "tickets": self.can_access_module(session, guild_id, MODULE_TICKETS),
            "fines": self.can_access_module(session, guild_id, MODULE_FINES),
            "audit": self.can_access_module(session, guild_id, MODULE_AUDIT),
            "templates": self.can_access_module(session, guild_id, MODULE_TEMPLATES),
            "permissions": self.can_access_module(session, guild_id, MODULE_PERMISSIONS),
            "adminPanel": self.can_access_admin_panel(session, guild_id),
            "registration": self.can_access_module(session, guild_id, MODULE_ALBION_REGISTRATION),
            "loot": self.can_access_module(session, guild_id, MODULE_LOOT),
            "reportCalculator": self.can_access_module(session, guild_id, MODULE_REPORT_CALCULATOR),
            "welcome": self.can_access_module(session, guild_id, MODULE_WELCOME),
        }

    def can_access_report_calculator(self, session, guild_id, caller_id):
        guild_id = str(guild_id or "")
        member_guilds = {
            str(guild["id"])
            for guild in (session.get("guilds") or session.get("admin_guilds", []))
            if guild.get("id")
        }
        bot_guild_ids = get_bot_guild_ids()
        if (
            not guild_id
            or guild_id not in member_guilds
            or (bot_guild_ids is not None and guild_id not in bot_guild_ids)
        ):
            return False
        if self.is_guild_admin(session, guild_id):
            return True
        return (
            str(session.get("user", {}).get("id") or "") == str(caller_id)
        )

    def can_access_chest_tables(self, session, guild_id):
        guild_id = str(guild_id or "")
        if not guild_id:
            return False
        if self.can_access_module(session, guild_id, MODULE_REPORTS):
            return True
        bot_guild_ids = get_bot_guild_ids()
        return (
            guild_id in self.session_member_guild_ids(session)
            and (bot_guild_ids is None or guild_id in bot_guild_ids)
        )

    def guild_id_for_chest_image(self, session, image_id):
        try:
            init_database()
            with database_connection() as connection:
                row = connection.execute(
                    """
                    SELECT image.guild_id
                    FROM chest_table_images image
                    JOIN chest_tables table_record ON table_record.id = image.table_id
                    WHERE image.id = ? AND table_record.is_deleted = 0
                    """,
                    (int(image_id),),
                ).fetchone()
            guild_id = str(row["guild_id"] or "") if row else ""
            if guild_id and self.can_access_chest_tables(session, guild_id):
                return guild_id
        except Exception as exc:
            log_event(f"DASHBOARD CHEST IMAGE LOOKUP ERROR | image={image_id} | {type(exc).__name__}: {exc}")
        return ""

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

        if action_type in {BOT_MESSAGE_ACTION_SEND, BOT_MESSAGE_ACTION_EDIT, BOT_MESSAGE_ACTION_DELETE}:
            return bool(guild_id) and self.can_access_admin_panel(session, guild_id)

        if action_type == SERVER_TEMPLATE_ACTION_APPLY:
            target_guild_id = str((payload or {}).get("target_guild_id") or guild_id)
            source_guild_id = str((payload or {}).get("source_guild_id") or "")
            return (
                bool(target_guild_id)
                and self.can_access_admin_panel(session, target_guild_id)
                and bool(source_guild_id)
                and self.is_guild_admin(session, source_guild_id)
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

    def client_ip_address(self):
        forwarded_for = str(self.headers.get("X-Forwarded-For") or "").split(",", 1)[0].strip()
        if forwarded_for:
            return forwarded_for
        if isinstance(self.client_address, tuple) and self.client_address:
            return str(self.client_address[0] or "")
        return ""

    def require_elevated_admin_panel(self, session, guild_id=None):
        has_admin_permission = (
            self.can_access_admin_panel(session, guild_id)
            if guild_id
            else self.can_access_any_admin_panel(session)
        )
        try:
            return self.dashboard_admin_security_service().ensure_elevated_access(
                session=session,
                has_admin_permission=has_admin_permission,
                ip_address=self.client_ip_address(),
            )
        except DashboardAdminAccessError as exc:
            self.send_json(exc.status, {"error": str(exc)})
            return None

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

        if DASHBOARD_PUBLIC_URL:
            return f"{DASHBOARD_PUBLIC_URL.rstrip('/')}/oauth/callback"

        host = self.headers.get("Host", f"localhost:{self.server.server_port}")
        forwarded_proto = str(self.headers.get("X-Forwarded-Proto") or "").split(",", 1)[0].strip().lower()
        scheme = forwarded_proto if forwarded_proto in {"http", "https"} else "http"
        return f"{scheme}://{host}/oauth/callback"

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
        session = get_session_from_request(self)
        if session:
            try:
                self.dashboard_admin_security_service().logout_elevated(
                    session=session,
                    ip_address=self.client_ip_address(),
                    reason="logout",
                )
            except Exception as exc:
                log_event(f"DASHBOARD ADMIN LOGOUT AUDIT ERROR | {type(exc).__name__}: {exc}")
        clear_session_from_request(self)
        self.send_redirect(
            "/",
            headers={"Set-Cookie": make_cookie_value("", 0)},
        )

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_text(200, render_landing_html(), "text/html")
            return

        if parsed.path == "/dashboard":
            if not get_session_from_request(self):
                self.send_redirect(
                    f"/login?remember=1&{urlencode({'next': self.path})}"
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

        if parsed.path.startswith("/chest-table-image/"):
            session = get_session_from_request(self)
            if not session:
                self.send_text(401, "Inicia sesion.", "text/plain")
                return
            image_id = parsed.path.removeprefix("/chest-table-image/").strip("/")
            if not image_id.isdigit():
                self.send_text(404, "No encontrado", "text/plain")
                return
            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id:
                guild_id = self.guild_id_for_chest_image(session, image_id)
            if not guild_id or not self.can_access_chest_tables(session, guild_id):
                self.send_text(403, "No tienes acceso a ese servidor.", "text/plain")
                return
            image = ChestTableService().get_image_file(guild_id, image_id)
            if not image:
                self.send_text(404, "No encontrado", "text/plain")
                return
            try:
                with open(image["path"], "rb") as handle:
                    self.send_bytes(200, handle.read(), image["content_type"])
            except OSError:
                self.send_text(404, "No encontrado", "text/plain")
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
                init_database()
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
                init_database()
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

        if parsed.path == "/api/admin-access/status":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = str(query.get("guild_id", [""])[0] or "").strip()
            if not guild_id:
                self.send_json(400, {"error": "Selecciona un servidor antes de abrir el panel administrativo."})
                return

            try:
                self.send_json(200, {
                    "status": self.dashboard_admin_security_service().get_status(
                        session=session,
                        has_admin_permission=self.can_access_admin_panel(session, guild_id),
                        ip_address=self.client_ip_address(),
                    ),
                })
            except DashboardAdminAccessError as exc:
                self.send_json(exc.status, {"error": str(exc)})
            except Exception as exc:
                self.send_internal_json_error("/api/admin-access/status", exc)
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
                calculators = (
                    get_active_report_calculators(guild_id)
                    if self.is_guild_admin(session, guild_id)
                    else get_active_report_calculators_for_user(guild_id, caller_id)
                )
                self.send_json(200, {"calculators": calculators})
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

        if parsed.path == "/api/chest-tables":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id or not self.can_access_chest_tables(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return
            try:
                init_database()
                table_id = str(query.get("table_id", [""])[0] or "").strip()
                service = ChestTableService()
                if table_id:
                    if not table_id.isdigit():
                        self.send_json(400, {"error": "Tabla invalida."})
                        return
                    table = service.get_table(guild_id, table_id)
                    if not table:
                        self.send_json(404, {"error": "No encontre esa tabla de cofres."})
                        return
                    self.send_json(200, {"table": table})
                    return
                self.send_json(200, service.list_tables(guild_id))
            except Exception as exc:
                self.send_internal_json_error("/api/chest-tables GET", exc)
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

        if parsed.path == "/api/export/ticket":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            record_id = query.get("record_id", [""])[0]
            if not guild_id or not self.can_access_tickets(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return
            if not record_id:
                self.send_json(400, {"error": "Falta indicar el ticket a exportar."})
                return

            record = get_ticket_record(guild_id, record_id)
            if not record:
                self.send_json(404, {"error": "No encontre ese ticket."})
                return

            guild_name = next(
                (guild.get("name") for guild in session.get("guilds", []) if str(guild.get("id")) == str(guild_id)),
                f"Servidor {guild_id}",
            )
            try:
                export_data = build_ticket_export_payload(guild_id, guild_name, record)
            except ValueError as exc:
                self.send_json(409, {"error": str(exc)})
                return

            ticket = export_data["ticket"]
            ticket_name = ticket.get("channel", {}).get("name") or ticket.get("record_id") or record_id
            file_name = f"ticket_{safe_export_filename(guild_id)}_{safe_export_filename(ticket_name)}.json"
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

        if parsed.path == "/api/ticket-transcript":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            record_id = query.get("record_id", [""])[0]
            if not guild_id or not self.can_access_tickets(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                return
            record = get_ticket_record(guild_id, record_id)
            if not record:
                self.send_json(404, {"error": "No encontre esa transcripcion."})
                return
            transcript = record.get("transcript") if isinstance(record.get("transcript"), list) else []
            self.send_json(200, {
                "record": {
                    "record_id": record.get("record_id") or ticket_record_identity(record),
                    "number": record.get("number"),
                    "ticket_type": record.get("ticket_type") or ticket_record_type(record),
                    "type_label": record.get("type_label") or ("Multa" if ticket_record_type(record) == "fine" else "Ticket"),
                    "panel_name": record.get("panel_name") or "",
                    "channel_id": record.get("channel_id") or "",
                    "channel_name": record.get("channel_name") or "",
                    "user_id": record.get("user_id") or record.get("owner_id") or "",
                    "user_name": record.get("user_name") or record.get("owner_name") or "",
                    "status": ticket_record_status(record),
                    "created_at": record.get("created_at") or "",
                    "closed_at": record.get("closed_at") or "",
                    "deleted_at": record.get("deleted_at") or "",
                    "transcribed_at": record.get("transcribed_at") or "",
                    "fine": fine_payload_from_record(record) if ticket_record_type(record) == "fine" else None,
                },
                "messages": transcript,
                "message_count": len(transcript),
            })
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

            self.send_json(
                200,
                get_guild_bot_permissions(
                    guild_id,
                    actor_role_ids=self.session_role_ids(session, guild_id),
                    is_actor_admin=self.is_guild_admin(session, guild_id),
                ),
            )
            return

        if parsed.path == "/api/admin/guilds":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.require_elevated_admin_panel(session):
                return

            try:
                self.send_json(200, self.admin_panel_guilds_payload(session))
            except Exception as exc:
                self.send_internal_json_error("/api/admin/guilds", exc)
            return

        if parsed.path == "/api/admin/overview":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id:
                self.send_json(400, {"error": "Selecciona un servidor antes de abrir el panel administrativo."})
                return
            if not self.require_elevated_admin_panel(session, guild_id):
                return
            if not self.can_access_admin_panel(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso administrativo a ese servidor."})
                return

            guild_name = next(
                (guild.get("name") for guild in session.get("guilds", []) if str(guild.get("id")) == str(guild_id)),
                f"Servidor {guild_id}",
            )
            try:
                audit_key = f"admin_overview:{guild_id}"
                session.setdefault("admin_audit_seen", [])
                if audit_key not in session["admin_audit_seen"]:
                    self.record_dashboard_admin_change(
                        session,
                        guild_id,
                        category="server",
                        title="Panel administrativo abierto",
                        description="Se consulto la vista general administrativa del servidor desde el dashboard.",
                    )
                    session["admin_audit_seen"].append(audit_key)
                session["last_admin_panel_guild_id"] = str(guild_id)
                self.send_json(200, get_admin_overview_payload(guild_id, guild_name=guild_name))
            except Exception as exc:
                self.send_internal_json_error("/api/admin/overview", exc)
            return

        if parsed.path == "/api/admin/message-channels":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id:
                self.send_json(400, {"error": "Selecciona un servidor antes de cargar canales administrativos."})
                return
            if not self.require_elevated_admin_panel(session, guild_id):
                return
            if not self.can_access_admin_panel(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso administrativo a ese servidor."})
                return

            try:
                self.send_json(
                    200,
                    build_admin_bot_message_channels_payload(
                        guild_id,
                        force_refresh=query_bool(query, "refresh"),
                    ),
                )
            except Exception as exc:
                self.send_internal_json_error("/api/admin/message-channels", exc)
            return

        if parsed.path == "/api/admin/bot-message":
            session = self.get_authenticated_session()
            if not session:
                return

            try:
                query = parse_qs(parsed.query)
                guild_id, channel_id, message_id = validate_bot_message_lookup_query(query)
                if not self.require_elevated_admin_panel(session, guild_id):
                    return
                if not self.can_access_admin_panel(session, guild_id):
                    self.send_json(403, {"error": "No tienes acceso administrativo a ese servidor."})
                    return

                message = fetch_admin_bot_message_for_edit(guild_id, channel_id, message_id)
                self.send_json(200, {"message": message})
            except PermissionError as exc:
                self.send_json(403, {"error": str(exc)})
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
            except RuntimeError as exc:
                status = 404 if "Discord respondio 404" in str(exc) else 502
                self.send_json(status, {"error": "No pude cargar ese mensaje desde Discord."})
            except Exception as exc:
                self.send_internal_json_error("/api/admin/bot-message GET", exc)
            return

        if parsed.path == "/api/admin/server-backups":
            session = self.get_authenticated_session()
            if not session:
                return

            query = parse_qs(parsed.query)
            guild_id = query.get("guild_id", [""])[0]
            if not guild_id:
                self.send_json(400, {"error": "Selecciona un servidor antes de consultar backups."})
                return
            if not self.require_elevated_admin_panel(session, guild_id):
                return
            if not self.can_access_admin_panel(session, guild_id):
                self.send_json(403, {"error": "No tienes acceso administrativo a ese servidor."})
                return

            try:
                backup_id = str(query.get("backup_id", [""])[0] or "").strip()
                service = self.server_backup_service()
                if backup_id:
                    if not backup_id.isdigit():
                        self.send_json(400, {"error": "Backup invalido."})
                        return
                    backup = service.get_backup(backup_id, guild_id=guild_id)
                    if not backup:
                        self.send_json(404, {"error": "No encontre ese backup para este servidor."})
                        return
                    self.send_json(200, {"backup": backup})
                    return

                self.send_json(200, {
                    "backups": service.list_backups(guild_id),
                    "max_backups": 2,
                })
            except Exception as exc:
                self.send_internal_json_error("/api/admin/server-backups GET", exc)
            return

        if parsed.path.startswith("/api/"):
            self.send_text(404, "No encontrado", "text/plain")
            return

        self.send_text(404, "No encontrado", "text/plain")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/loot/normalize":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                guild_id = str(body.get("guild_id") or "")
                if not guild_id or not self.has_guild_permission(session, guild_id, PERMISSION_LOOT_USE):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return

                result = LootNormalizationService().normalize_payload(body)
                loot_payload = result.to_dict()
                price_service = AlbionMarketPriceService()
                if parse_bool_option(body.get("include_prices"), default=True):
                    loot_payload = price_service.enrich_loot(
                        loot_payload,
                        force_refresh=parse_bool_option(body.get("refresh_prices"), default=False),
                        server=body.get("market_server"),
                        locations=body.get("market_locations"),
                        quality=body.get("market_quality"),
                    )
                else:
                    loot_payload = price_service.normalize_loot_without_prices(
                        loot_payload,
                        server=body.get("market_server"),
                        locations=body.get("market_locations"),
                        quality=body.get("market_quality"),
                    )
                self.send_json(200, {"loot": loot_payload})
            except LootNormalizationError as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception as exc:
                self.send_internal_json_error("/api/loot/normalize", exc)
            return

        if parsed.path == "/api/economy/balance":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                guild_id = str(body.get("guild_id") or "")
                if not guild_id or not self.has_guild_permission(session, guild_id, PERMISSION_ECONOMY_BALANCE_EDIT):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return

                payload = apply_dashboard_balance_change(guild_id, body, session)
                operation = payload.get("operation", {})
                self.record_dashboard_admin_change(
                    session,
                    guild_id,
                    category="server",
                    title="Balance modificado desde dashboard",
                    description=(
                        f"Se modifico el balance de {operation.get('player', '')} "
                        f"({operation.get('player_id', '')}). Estado: {operation.get('player_status', '')}."
                    ),
                )
                self.send_json(200, {
                    **payload,
                    **get_economy_summary_payload(guild_id),
                })
            except LookupError as exc:
                self.send_json(404, {"error": str(exc)})
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception as exc:
                self.send_internal_json_error("/api/economy/balance", exc)
            return

        if parsed.path == "/api/report-calculator/preview":
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
                if parse_bool_option(body.get("manual"), default=False):
                    if not guild_id or not (
                        guild_id in self.session_member_guild_ids(session)
                        or self.can_access_guild(session, guild_id)
                        or self.can_access_any_dashboard_module(session, guild_id)
                    ):
                        self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                        return

                    preview = build_report_calculator_preview(
                        build_manual_report_calculator_state(body, session),
                        body,
                    )
                    self.send_json(200, {"preview": preview})
                    return

                if not self.can_access_report_calculator(session, guild_id, caller_id):
                    self.send_json(403, {"error": "Solo el caller puede previsualizar este informe."})
                    return

                state = get_active_avalonian_state(guild_id, caller_id, numero_ava)
                if not state:
                    self.send_json(404, {"error": "Esta Ava ya no esta activa o ya fue cerrada. Abrela de nuevo desde Discord."})
                    return

                preview = build_report_calculator_preview(state, body)
                self.send_json(200, {"preview": preview})
            except Exception as exc:
                self.send_internal_json_error("/api/report-calculator/preview", exc)
            return

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
                report_already_generated = (
                    (state.get("report_sent") or state.get("report_generated"))
                    and not state.get("report_rejected")
                )
                if not state.get("finalized") or state.get("cancelled") or report_already_generated:
                    self.send_json(400, {"error": "Esta Ava no esta disponible para enviar informe."})
                    return

                split_mode = str(body.get("split_mode") or "")
                if split_mode not in {"items", "silver", "items_silver"}:
                    self.send_json(400, {"error": "Selecciona un modo de reparto valido."})
                    return
                send_to_channel = parse_bool_option(body.get("send_to_channel"), default=True)
                idempotency_key = report_request_idempotency_key(
                    body,
                    send_to_channel=send_to_channel,
                )

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

                slots = report_formatter_slots_from_state(state)
                raw_exclusions = body.get("split_exclusions", [])
                if raw_exclusions and not isinstance(raw_exclusions, list):
                    self.send_json(400, {"error": "Las exclusiones del split no tienen un formato valido."})
                    return
                requested_excluded_user_ids = set()
                for entry in raw_exclusions or []:
                    if not isinstance(entry, dict) or not entry.get("user_id"):
                        continue
                    try:
                        requested_excluded_user_ids.add(int(entry.get("user_id") or 0))
                    except (TypeError, ValueError):
                        requested_excluded_user_ids.add(0)
                split_exclusions = REPORT_FORMATTER.normalize_split_exclusions(
                    raw_exclusions,
                    slots,
                )
                normalized_excluded_user_ids = {
                    int(entry.get("user_id") or 0)
                    for entry in split_exclusions
                }
                if requested_excluded_user_ids != normalized_excluded_user_ids:
                    self.send_json(400, {"error": "Solo puedes excluir jugadores que pertenecen a este informe."})
                    return
                raw_modifiers = body.get("split_modifiers", [])
                if raw_modifiers and not isinstance(raw_modifiers, list):
                    self.send_json(400, {"error": "Los modificadores del split no tienen un formato valido."})
                    return
                requested_modifier_player_ids = set()
                requested_modifier_count = 0
                for entry in raw_modifiers or []:
                    if not isinstance(entry, dict):
                        continue
                    if any(str(entry.get(key) or "").strip() for key in ("name", "amount", "description")):
                        requested_modifier_count += 1
                    if str(entry.get("target_type") or "total").strip().lower() != "player":
                        continue
                    try:
                        requested_modifier_player_ids.add(int(entry.get("user_id") or 0))
                    except (TypeError, ValueError):
                        requested_modifier_player_ids.add(0)
                split_modifiers = REPORT_FORMATTER.normalize_split_modifiers(
                    raw_modifiers,
                    slots,
                )
                normalized_modifier_player_ids = {
                    int(entry.get("user_id") or 0)
                    for entry in split_modifiers
                    if entry.get("target_type") == "player"
                }
                if requested_modifier_player_ids != normalized_modifier_player_ids:
                    self.send_json(400, {"error": "Los modificadores por jugador solo pueden apuntar a integrantes del informe."})
                    return
                if requested_modifier_count != len(split_modifiers):
                    self.send_json(400, {"error": "Revisa los modificadores: concepto, operacion y monto deben ser validos."})
                    return
                raw_build_loan_discounts = body.get("build_loan_discounts", [])
                if raw_build_loan_discounts and not isinstance(raw_build_loan_discounts, list):
                    self.send_json(400, {"error": "Los descuentos por prestamo de build no tienen un formato valido."})
                    return
                requested_build_loan_player_ids = set()
                requested_build_loan_count = 0
                requested_build_loan_entries = []
                for entry in raw_build_loan_discounts or []:
                    if not isinstance(entry, dict):
                        continue
                    has_build_loan_data = any(
                        str(entry.get(key) or "").strip()
                        for key in ("user_id", "player_id", "amount", "reason", "description", "motivo")
                    )
                    if not has_build_loan_data:
                        continue
                    requested_build_loan_entries.append(entry)
                    requested_build_loan_count += 1
                    try:
                        requested_build_loan_player_ids.add(int(entry.get("user_id") or entry.get("player_id") or 0))
                    except (TypeError, ValueError):
                        requested_build_loan_player_ids.add(0)
                build_loan_discounts = REPORT_FORMATTER.normalize_build_loan_discounts(
                    raw_build_loan_discounts,
                    slots,
                )
                normalized_build_loan_player_ids = {
                    int(entry.get("user_id") or 0)
                    for entry in build_loan_discounts
                }
                if requested_build_loan_player_ids != normalized_build_loan_player_ids:
                    self.send_json(400, {"error": "Los prestamos de build solo pueden descontarse a integrantes del informe."})
                    return
                if requested_build_loan_count != len(build_loan_discounts):
                    self.send_json(400, {"error": "Revisa los prestamos de build: jugador, motivo y metodo de cobro son obligatorios. El monto solo es obligatorio si no es pago al momento."})
                    return

                chest_table_id = str(body.get("chest_table_id") or "").strip()
                if chest_table_id:
                    if not chest_table_id.isdigit():
                        self.send_json(400, {"error": "Tabla de cofres invalida."})
                        return
                    init_database()
                    if not ChestTableService().get_table(guild_id, chest_table_id):
                        self.send_json(404, {"error": "No encontre esa tabla de cofres para este servidor."})
                        return

                for index, discount in enumerate(build_loan_discounts):
                    raw_entry = requested_build_loan_entries[index] if index < len(requested_build_loan_entries) else {}
                    proof_path = ""
                    proof_name = ""
                    if isinstance(raw_entry, dict) and raw_entry.get("proof_data_url"):
                        proof_path, proof_name = store_embedded_image(
                            raw_entry.get("proof_data_url"),
                            prefix=f"{guild_id}_{caller_id}_{numero_ava}_build_loan_{index + 1}_{int(time.time())}",
                        )
                        log_event(
                            "REPORT BUILD LOAN PROOF STORE | "
                            f"guild={guild_id} ava={numero_ava} index={index + 1} "
                            f"name={proof_name or str(raw_entry.get('proof_name') or '')[:120]} "
                            f"stored={bool(proof_path)} path={proof_path or '-'}"
                        )
                    if isinstance(raw_entry, dict) and not proof_name:
                        proof_name = str(raw_entry.get("proof_name") or "")[:120]
                        if proof_name:
                            log_event(
                                "REPORT BUILD LOAN PROOF MISSING DATA | "
                                f"guild={guild_id} ava={numero_ava} index={index + 1} name={proof_name}"
                            )
                    discount["proof_path"] = proof_path
                    discount["proof_name"] = proof_name

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
                        "split_exclusions": split_exclusions,
                        "split_modifiers": split_modifiers,
                        "build_loan_discounts": build_loan_discounts,
                        "chest_table_id": chest_table_id,
                        "split_mode": split_mode,
                        "send_to_channel": send_to_channel,
                    },
                    requested_by=str(session.get("user", {}).get("id") or ""),
                    idempotency_key=idempotency_key,
                )
                self.send_json(202, {"request": request})
            except Exception as exc:
                self.send_internal_json_error("/api/report-calculator", exc)
            return

        if parsed.path == "/api/chest-tables":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                guild_id = str(body.get("guild_id") or "").strip()
                if not guild_id or not self.can_access_chest_tables(session, guild_id):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return
                init_database()
                table_id = str(body.get("table_id") or "").strip()
                service = ChestTableService()
                if table_id:
                    if not table_id.isdigit():
                        self.send_json(400, {"error": "Tabla invalida."})
                        return
                    table = service.save_table(guild_id, table_id, body.get("table") or body, session.get("user", {}))
                    if not table:
                        self.send_json(404, {"error": "No encontre esa tabla de cofres."})
                        return
                    self.record_dashboard_admin_change(
                        session,
                        guild_id,
                        category="server",
                        title="Tabla de cofres actualizada",
                        description=f"Se guardo la tabla de cofres #{table_id}.",
                    )
                    self.send_json(200, {"table": table, **service.list_tables(guild_id)})
                    return

                table = service.create_table(guild_id, body.get("name"), session.get("user", {}))
                self.record_dashboard_admin_change(
                    session,
                    guild_id,
                    category="server",
                    title="Tabla de cofres creada",
                    description=f"Se creo la tabla de cofres #{table.get('id')}.",
                )
                self.send_json(201, {"table": table, **service.list_tables(guild_id)})
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception as exc:
                self.send_internal_json_error("/api/chest-tables POST", exc)
            return

        if parsed.path == "/api/chest-table-image":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                guild_id = str(body.get("guild_id") or "").strip()
                table_id = str(body.get("table_id") or "").strip()
                if not guild_id or not self.can_access_chest_tables(session, guild_id):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return
                if not table_id.isdigit():
                    self.send_json(400, {"error": "Tabla invalida."})
                    return
                init_database()
                service = ChestTableService()
                image = service.add_image_from_data_url(
                    guild_id,
                    table_id,
                    str(body.get("row_id") or ""),
                    filename=str(body.get("filename") or "evidencia.png"),
                    data_url=str(body.get("data_url") or ""),
                    image_type=str(body.get("image_type") or ""),
                    actor=session.get("user", {}),
                )
                if not image:
                    self.send_json(404, {"error": "No encontre esa tabla de cofres."})
                    return
                table = service.get_table(guild_id, table_id)
                self.record_dashboard_admin_change(
                    session,
                    guild_id,
                    category="server",
                    title="Evidencia de cofres subida",
                    description=f"Se subio una imagen para la tabla de cofres #{table_id}.",
                )
                self.send_json(201, {"image": image, "table": table})
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception as exc:
                self.send_internal_json_error("/api/chest-table-image", exc)
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

        if parsed.path == "/api/admin-access/verify":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                guild_id = str(body.get("guild_id") or "").strip()
                password = str(body.get("password") or "")
                if not guild_id:
                    self.send_json(400, {"error": "Selecciona un servidor antes de validar la clave secundaria."})
                    return
                status = self.dashboard_admin_security_service().verify_password(
                    session=session,
                    has_admin_permission=self.can_access_admin_panel(session, guild_id),
                    ip_address=self.client_ip_address(),
                    password=password,
                )
                self.send_json(200, {"status": status})
            except DashboardAdminAccessError as exc:
                self.send_json(exc.status, {"error": str(exc)})
            except Exception as exc:
                self.send_internal_json_error("/api/admin-access/verify", exc)
            return

        if parsed.path == "/api/admin-access/logout":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                closed = self.dashboard_admin_security_service().logout_elevated(
                    session=session,
                    ip_address=self.client_ip_address(),
                    reason="logout",
                )
                self.send_json(200, {"ok": True, "closed": bool(closed)})
            except Exception as exc:
                self.send_internal_json_error("/api/admin-access/logout", exc)
            return

        if parsed.path == "/api/admin/bot-message":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                payload = validate_bot_message_request_payload(body)
                guild_id = payload["guild_id"]
                if not self.require_elevated_admin_panel(session, guild_id):
                    return
                if not self.can_access_admin_panel(session, guild_id):
                    self.send_json(403, {"error": "No tienes acceso administrativo a ese servidor."})
                    return

                channels_payload = build_admin_bot_message_channels_payload(guild_id)
                channels_by_id = {
                    str(channel.get("id")): channel
                    for channel in channels_payload.get("channels", [])
                }
                channel = channels_by_id.get(payload["channel_id"])
                if not channel:
                    self.send_json(403, {"error": "El bot no tiene permisos suficientes en ese canal."})
                    return
                if payload["action"] in {"edit", "delete"} and not channel.get("can_read_history"):
                    self.send_json(403, {"error": "Para editar o eliminar mensajes el bot debe poder leer el historial del canal."})
                    return
                if payload["action"] == "delete" and not channel.get("can_manage_messages"):
                    self.send_json(403, {"error": "Para eliminar mensajes el bot debe tener Gestionar mensajes en el canal."})
                    return

                operator = session.get("user", {}) if isinstance(session, dict) else {}
                audit_repo = BotMessageAuditRepository()
                audit_id = audit_repo.create(
                    operator_id=operator.get("id", ""),
                    operator_name=operator.get("username", ""),
                    guild_id=guild_id,
                    channel_id=payload["channel_id"],
                    action=payload["action"],
                    message_id=payload["message_id"],
                    new_content=payload["content"],
                    status="queued",
                )
                payload["audit_id"] = audit_id
                request = DashboardActionService().create_request(
                    guild_id=guild_id,
                    action_type=payload["action_type"],
                    payload=payload,
                    requested_by=self.dashboard_actor_label(session),
                    max_retries=2,
                )
                audit_repo.attach_request(audit_id, request.get("id", ""))
                self.record_dashboard_admin_change(
                    session,
                    guild_id,
                    category="messages",
                    title="Solicitud de mensaje del bot",
                    description=(
                        f"Se encolo la accion {payload['action']} para el canal "
                        f"{payload['channel_id']} con solicitud {request.get('id', '')}."
                    ),
                )
                self.send_json(202, {"request": request, "audit_id": audit_id})
            except ValueError as exc:
                self.send_json(400, {"error": str(exc)})
            except Exception as exc:
                self.send_internal_json_error("/api/admin/bot-message", exc)
            return

        if parsed.path == "/api/admin/server-template/preview":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                source_guild_id = str(body.get("source_guild_id") or body.get("guild_id") or "").strip()
                target_guild_id = str(body.get("target_guild_id") or "").strip()
                backup_id = str(body.get("backup_id") or "").strip()
                options = body.get("options") if isinstance(body.get("options"), dict) else {}
                if not source_guild_id or not target_guild_id or not backup_id.isdigit():
                    self.send_json(400, {"error": "Debes seleccionar backup de origen y servidor destino."})
                    return
                if not self.require_elevated_admin_panel(session, source_guild_id):
                    return
                if not self.require_elevated_admin_panel(session, target_guild_id):
                    return
                if not self.can_access_admin_panel(session, source_guild_id) or not self.can_access_admin_panel(session, target_guild_id):
                    self.send_json(403, {"error": "Necesitas permisos administrativos en origen y destino."})
                    return
                bot_guild_ids = get_bot_guild_ids()
                if bot_guild_ids is not None and target_guild_id not in bot_guild_ids:
                    self.send_json(403, {"error": "El bot no esta conectado al servidor destino."})
                    return

                backup = self.server_backup_service().get_backup(backup_id, guild_id=source_guild_id)
                if not backup:
                    self.send_json(404, {"error": "No encontre ese backup para el servidor de origen."})
                    return
                target_guild_name = next(
                    (guild.get("name") for guild in session.get("guilds", []) if str(guild.get("id")) == target_guild_id),
                    f"Servidor {target_guild_id}",
                )
                preview = build_server_template_preview_payload(
                    backup,
                    target_guild_id=target_guild_id,
                    target_guild_name=target_guild_name,
                    options=options,
                )
                self.record_dashboard_admin_change(
                    session,
                    target_guild_id,
                    category="server",
                    title="Plantilla de servidor previsualizada",
                    description=f"Se previsualizo el backup #{backup_id} del servidor {source_guild_id} sobre este servidor.",
                )
                self.send_json(200, {"preview": preview})
            except RuntimeError as exc:
                message = str(exc)
                if "Discord respondio 403" in message:
                    self.send_json(403, {"error": "El bot no tiene permisos suficientes para inspeccionar el servidor destino."})
                elif "Discord respondio 404" in message:
                    self.send_json(404, {"error": "No encontre el servidor destino o el bot ya no esta conectado."})
                else:
                    self.send_json(502, {"error": "No pude validar el servidor destino desde Discord."})
            except Exception as exc:
                self.send_internal_json_error("/api/admin/server-template/preview", exc)
            return

        if parsed.path == "/api/admin/server-template/apply":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                source_guild_id = str(body.get("source_guild_id") or body.get("guild_id") or "").strip()
                target_guild_id = str(body.get("target_guild_id") or "").strip()
                backup_id = str(body.get("backup_id") or "").strip()
                options = body.get("options") if isinstance(body.get("options"), dict) else {}
                confirmation = str(body.get("confirmation") or "").strip().upper()
                if not parse_bool_option(body.get("confirmed"), default=False) or confirmation != "APLICAR":
                    self.send_json(400, {"error": "Debes confirmar escribiendo APLICAR antes de ejecutar la plantilla."})
                    return
                if not source_guild_id or not target_guild_id or not backup_id.isdigit():
                    self.send_json(400, {"error": "Debes seleccionar backup de origen y servidor destino."})
                    return
                if not self.require_elevated_admin_panel(session, source_guild_id):
                    return
                if not self.require_elevated_admin_panel(session, target_guild_id):
                    return
                if not self.can_access_admin_panel(session, source_guild_id) or not self.can_access_admin_panel(session, target_guild_id):
                    self.send_json(403, {"error": "Necesitas permisos administrativos en origen y destino."})
                    return
                bot_guild_ids = get_bot_guild_ids()
                if bot_guild_ids is not None and target_guild_id not in bot_guild_ids:
                    self.send_json(403, {"error": "El bot no esta conectado al servidor destino."})
                    return

                backup = self.server_backup_service().get_backup(backup_id, guild_id=source_guild_id)
                if not backup:
                    self.send_json(404, {"error": "No encontre ese backup para el servidor de origen."})
                    return
                target_guild_name = next(
                    (guild.get("name") for guild in session.get("guilds", []) if str(guild.get("id")) == target_guild_id),
                    f"Servidor {target_guild_id}",
                )
                preview = build_server_template_preview_payload(
                    backup,
                    target_guild_id=target_guild_id,
                    target_guild_name=target_guild_name,
                    options=options,
                )
                if not preview.get("bot_permissions_ok"):
                    self.send_json(403, {"error": "El bot no tiene permisos suficientes en el servidor destino."})
                    return
                request_payload = {
                    "source_guild_id": source_guild_id,
                    "target_guild_id": target_guild_id,
                    "backup_id": int(backup_id),
                    "backup": backup.get("backup") or {},
                    "preview": preview,
                    "options": {
                        "update_existing": parse_bool_option(options.get("update_existing"), default=False),
                        "include_bot_config": parse_bool_option(options.get("include_bot_config"), default=True),
                        "clear_target": parse_bool_option(options.get("clear_target"), default=False),
                    },
                    "requested_by_user_id": str((session.get("user") or {}).get("id") or ""),
                }
                request = DashboardActionService().create_request(
                    guild_id=target_guild_id,
                    action_type=SERVER_TEMPLATE_ACTION_APPLY,
                    payload=request_payload,
                    requested_by=self.dashboard_actor_label(session),
                    max_retries=1,
                )
                self.record_dashboard_admin_change(
                    session,
                    target_guild_id,
                    category="server",
                    title="Aplicacion de plantilla encolada",
                    description=f"Se encolo la aplicacion del backup #{backup_id} desde {source_guild_id}. Solicitud {request.get('id', '')}.",
                )
                self.record_dashboard_admin_change(
                    session,
                    source_guild_id,
                    category="server",
                    title="Backup usado como plantilla",
                    description=f"El backup #{backup_id} se encolo como plantilla hacia el servidor {target_guild_id}. Solicitud {request.get('id', '')}.",
                )
                self.send_json(202, {"request": request, "preview": preview})
            except RuntimeError as exc:
                message = str(exc)
                if "Discord respondio 403" in message:
                    self.send_json(403, {"error": "El bot no tiene permisos suficientes para validar el servidor destino."})
                elif "Discord respondio 404" in message:
                    self.send_json(404, {"error": "No encontre el servidor destino o el bot ya no esta conectado."})
                else:
                    self.send_json(502, {"error": "No pude validar el servidor destino desde Discord."})
            except Exception as exc:
                self.send_internal_json_error("/api/admin/server-template/apply", exc)
            return

        if parsed.path == "/api/admin/server-backups":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                guild_id = str(body.get("guild_id") or "").strip()
                if not guild_id:
                    self.send_json(400, {"error": "Selecciona un servidor antes de crear backups."})
                    return
                if not self.require_elevated_admin_panel(session, guild_id):
                    return
                if not self.can_access_admin_panel(session, guild_id):
                    self.send_json(403, {"error": "No tienes acceso administrativo a ese servidor."})
                    return

                guild_name = next(
                    (guild.get("name") for guild in session.get("guilds", []) if str(guild.get("id")) == str(guild_id)),
                    f"Servidor {guild_id}",
                )
                backup = self.server_backup_service().create_backup(
                    guild_id=guild_id,
                    guild_name=guild_name,
                    created_by=session.get("user", {}),
                    replace_oldest=parse_bool_option(body.get("replace_oldest"), default=False),
                    replace_backup_id=str(body.get("replace_backup_id") or "").strip(),
                )
                self.record_dashboard_admin_change(
                    session,
                    guild_id,
                    category="server",
                    title="Backup de servidor creado",
                    description=f"Se creo el backup estructurado #{backup.get('id')} desde el panel administrativo.",
                )
                self.send_json(201, {"backup": backup})
            except ServerBackupLimitError as exc:
                self.send_json(409, {
                    "error": "Este servidor ya tiene 2 backups. Elige cual quieres reemplazar.",
                    "requires_replacement_choice": True,
                    "backups": exc.backups,
                })
            except RuntimeError as exc:
                message = str(exc)
                if "Discord respondio 403" in message:
                    self.send_json(403, {"error": "El bot no tiene permisos suficientes para leer la estructura de este servidor."})
                elif "Discord respondio 404" in message:
                    self.send_json(404, {"error": "No encontre el servidor en Discord o el bot ya no esta conectado."})
                else:
                    self.send_json(502, {"error": "No pude leer la estructura del servidor desde Discord."})
            except Exception as exc:
                self.send_internal_json_error("/api/admin/server-backups", exc)
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
                if not guild_id or not self.has_guild_permission(
                    session,
                    guild_id,
                    PERMISSION_TEMPLATES_CREATE,
                    PERMISSION_TEMPLATES_EDIT,
                ):
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

                payload, error = save_guild_bot_permissions(
                    guild_id,
                    body,
                    actor_role_ids=self.session_role_ids(session, guild_id),
                    is_actor_admin=self.is_guild_admin(session, guild_id),
                )
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

                records = get_all_guild_ticket_records(guild_id)
                self.send_json(200, {
                    "records": records,
                    "summary": ticket_records_summary(records),
                })
            except Exception as exc:
                self.send_internal_json_error("/api/ticket-record", exc)
            return

        if parsed.path == "/api/chest-tables":
            session = self.get_authenticated_session()
            if not session:
                return
            if not self.validate_csrf(session):
                return

            try:
                body = self.read_json_body()
                guild_id = str(body.get("guild_id") or "").strip()
                table_id = str(body.get("table_id") or "").strip()
                if not guild_id or not self.can_access_chest_tables(session, guild_id):
                    self.send_json(403, {"error": "No tienes acceso a ese servidor."})
                    return
                if not table_id.isdigit():
                    self.send_json(400, {"error": "Tabla invalida."})
                    return
                init_database()
                service = ChestTableService()
                if not service.delete_table(guild_id, table_id, actor=session.get("user", {})):
                    self.send_json(404, {"error": "No encontre esa tabla de cofres."})
                    return
                self.record_dashboard_admin_change(
                    session,
                    guild_id,
                    category="server",
                    title="Tabla de cofres eliminada",
                    description=f"Se desactivo la tabla de cofres #{table_id}.",
                )
                self.send_json(200, service.list_tables(guild_id))
            except Exception as exc:
                self.send_internal_json_error("/api/chest-tables DELETE", exc)
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
                if not guild_id or not self.has_guild_permission(session, guild_id, PERMISSION_TEMPLATES_DELETE):
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


PUBLIC_BIND_HOSTS = {"0.0.0.0", "::", "[::]"}


def dashboard_host_default():
    return DASHBOARD_HOST


def dashboard_port_default():
    return DASHBOARD_PORT


def dashboard_production_mode():
    return DASHBOARD_PRODUCTION_MODE


def warn_if_public_bind_in_production(host):
    normalized_host = str(host or "").strip().lower().strip("[]")
    if dashboard_production_mode() and normalized_host in PUBLIC_BIND_HOSTS:
        print(
            "ADVERTENCIA: el dashboard esta iniciando en 0.0.0.0/:: en modo "
            "produccion. Usa 127.0.0.1:8000 y publica solo mediante Caddy/Nginx.",
            file=sys.stderr,
            flush=True,
        )


def parse_args():
    parser = argparse.ArgumentParser(description="Dashboard local de EconomyBot")
    parser.add_argument("--host", default=dashboard_host_default())
    parser.add_argument("--port", type=int, default=dashboard_port_default())
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
    warn_if_public_bind_in_production(args.host)
    servers = build_servers(args.host, args.port)
    print(f"Dashboard escuchando en {args.host}:{args.port}")
    if str(args.host).strip().lower() in ("127.0.0.1", "localhost"):
        print(f"Dashboard local disponible en http://127.0.0.1:{args.port}")
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
