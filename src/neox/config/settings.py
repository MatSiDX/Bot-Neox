import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False

TRUE_VALUES = ("1", "true", "yes", "on")
PRODUCTION_ENVIRONMENTS = ("prod", "production")
SECRET_PLACEHOLDER_FRAGMENTS = (
    "your_",
    "replace_with",
    "change_me",
    "changeme",
    "example",
    "placeholder",
)


def _read_env_value(name: str):
    value = os.getenv(name)
    if value is None:
        return None

    cleaned = value.strip().strip('"').strip("'")
    return cleaned or None


def _read_env_bool(name: str, default: bool):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def _read_env_int(name: str, default: int):
    value = _read_env_value(name)
    if value is None:
        return default
    return int(value)


def _is_production_environment(value: str | None):
    return str(value or "").strip().lower() in PRODUCTION_ENVIRONMENTS


def _looks_like_placeholder(value: str | None):
    cleaned = str(value or "").strip().lower()
    return bool(cleaned) and any(fragment in cleaned for fragment in SECRET_PLACEHOLDER_FRAGMENTS)


def _secret_is_configured(value: str | None):
    return bool(value) and not _looks_like_placeholder(value)


def _raise_missing_production_secrets(names):
    joined = ", ".join(names)
    raise RuntimeError(
        "Faltan secretos obligatorios para produccion o contienen placeholders: "
        f"{joined}. Configuralos fuera del repo en .env productivo o variables del sistema."
    )


_PROJECT_ROOT_PATH = Path(__file__).resolve().parents[3]
_DATA_DIR_PATH = _PROJECT_ROOT_PATH / "data"
_ASSETS_DIR_PATH = _PROJECT_ROOT_PATH / "assets"
_ENV_FILE_PATH = _PROJECT_ROOT_PATH / ".env"

# Solo se carga el archivo .env real del proyecto.
# .env.example queda exclusivamente como referencia editable.
load_dotenv(dotenv_path=_ENV_FILE_PATH, override=False)

PROJECT_ROOT = str(_PROJECT_ROOT_PATH)
DATA_DIR = str(_DATA_DIR_PATH)
ASSETS_DIR = str(_ASSETS_DIR_PATH)
DATABASE_FILE = str(_DATA_DIR_PATH / "bot.sqlite3")
DASHBOARD_SESSIONS_FILE = str(_DATA_DIR_PATH / "dashboard_sessions.json")
DASHBOARD_LOG_FILE = str(_DATA_DIR_PATH / "dashboard.log")
DASHBOARD_ERROR_LOG_FILE = str(_DATA_DIR_PATH / "dashboard.err")
AVALON_BOT_LOGO_FILE = str(_ASSETS_DIR_PATH / "AvalonBot.png")

TOKEN = _read_env_value("TOKEN")
ECONOMY_TOKEN = _read_env_value("ECONOMY_TOKEN") or TOKEN
DASHBOARD_BOT_TOKEN = ECONOMY_TOKEN
DASHBOARD_CLIENT_ID = _read_env_value("DASHBOARD_CLIENT_ID") or _read_env_value("DISCORD_CLIENT_ID")
DASHBOARD_CLIENT_SECRET = _read_env_value("DASHBOARD_CLIENT_SECRET") or _read_env_value("DISCORD_CLIENT_SECRET")
DASHBOARD_REDIRECT_URI = _read_env_value("DASHBOARD_REDIRECT_URI")
DASHBOARD_SESSION_SECRET = _read_env_value("DASHBOARD_SESSION_SECRET")
DASHBOARD_HOST = _read_env_value("DASHBOARD_HOST") or "127.0.0.1"
DASHBOARD_PORT = _read_env_int("DASHBOARD_PORT", 8000)
DASHBOARD_COOKIE_SECURE = _read_env_bool(
    "DASHBOARD_COOKIE_SECURE",
    default=_read_env_bool("DASHBOARD_PUBLIC_HTTPS", default=False),
)
DASHBOARD_ADMIN_PASSWORD_HASH = _read_env_value("DASHBOARD_ADMIN_PASSWORD_HASH")
DASHBOARD_ADMIN_PASSWORD_PEPPER = _read_env_value("DASHBOARD_ADMIN_PASSWORD_PEPPER")
DASHBOARD_ADMIN_DEVELOPER_IDS = tuple(
    dict.fromkeys(
        value
        for value in (
            item.strip()
            for item in (_read_env_value("DASHBOARD_ADMIN_DEVELOPER_IDS") or "").split(",")
        )
        if value
    )
)
DASHBOARD_ADMIN_ELEVATED_TTL_SECONDS = max(
    600,
    min(900, _read_env_int("DASHBOARD_ADMIN_ELEVATED_TTL_SECONDS", 900)),
)
DASHBOARD_ADMIN_MAX_ATTEMPTS = max(1, _read_env_int("DASHBOARD_ADMIN_MAX_ATTEMPTS", 5))
DASHBOARD_ADMIN_ATTEMPT_WINDOW_SECONDS = max(
    60,
    _read_env_int("DASHBOARD_ADMIN_ATTEMPT_WINDOW_SECONDS", 900),
)
DASHBOARD_ADMIN_LOCKOUT_SECONDS = max(
    60,
    _read_env_int("DASHBOARD_ADMIN_LOCKOUT_SECONDS", 900),
)
DASHBOARD_PUBLIC_URL = (
    _read_env_value("DASHBOARD_PUBLIC_URL")
    or (
        DASHBOARD_REDIRECT_URI.removesuffix("/oauth/callback")
        if DASHBOARD_REDIRECT_URI
        else None
    )
    or "http://localhost:8000"
).rstrip("/")
APP_ENV = (_read_env_value("APP_ENV") or _read_env_value("DASHBOARD_ENV") or "development").lower()
DASHBOARD_ENVIRONMENT = (_read_env_value("DASHBOARD_ENV") or APP_ENV).lower()
DASHBOARD_PRODUCTION_MODE = (
    _is_production_environment(APP_ENV)
    or _is_production_environment(DASHBOARD_ENVIRONMENT)
    or DASHBOARD_COOKIE_SECURE
    or DASHBOARD_PUBLIC_URL.startswith("https://")
)
ALLOWED_ROLE_ID = _read_env_int("ALLOWED_ROLE_ID", 0)
AVALONIAN_LOG_CHANNEL_ID = _read_env_int("AVALONIAN_LOG_CHANNEL_ID", 0)
ENABLE_MEMBER_INTENT = _read_env_bool("ENABLE_MEMBER_INTENT", default=False)
ENABLE_VOICE_INTENT = _read_env_bool("ENABLE_VOICE_INTENT", default=True)
ENABLE_MESSAGE_CONTENT_INTENT = _read_env_bool("ENABLE_MESSAGE_CONTENT_INTENT", default=False)
MUSIC_ENABLED = _read_env_bool("MUSIC_ENABLED", default=True)
FFMPEG_PATH = _read_env_value("FFMPEG_PATH")
DISCORD_METADATA_ROLES_TTL_SECONDS = _read_env_int("DISCORD_METADATA_ROLES_TTL_SECONDS", 900)
DISCORD_METADATA_CHANNELS_TTL_SECONDS = _read_env_int("DISCORD_METADATA_CHANNELS_TTL_SECONDS", 300)
DISCORD_METADATA_CATEGORIES_TTL_SECONDS = _read_env_int("DISCORD_METADATA_CATEGORIES_TTL_SECONDS", 300)
DISCORD_METADATA_EMOJIS_TTL_SECONDS = _read_env_int("DISCORD_METADATA_EMOJIS_TTL_SECONDS", 1800)
DISCORD_METADATA_STALE_FALLBACK_SECONDS = _read_env_int("DISCORD_METADATA_STALE_FALLBACK_SECONDS", 3600)
ALBION_MARKET_SERVER = (_read_env_value("ALBION_MARKET_SERVER") or "west").lower()
ALBION_MARKET_LOCATIONS = _read_env_value("ALBION_MARKET_LOCATIONS") or "Black Market,Caerleon,Bridgewatch,Martlock,Lymhurst,Fort Sterling,Thetford,Brecilien"
ALBION_MARKET_QUALITIES = _read_env_value("ALBION_MARKET_QUALITIES") or "1"
ALBION_MARKET_CACHE_TTL_SECONDS = _read_env_int("ALBION_MARKET_CACHE_TTL_SECONDS", 21600)
ALBION_MARKET_TIMEOUT_SECONDS = _read_env_int("ALBION_MARKET_TIMEOUT_SECONDS", 8)

ECONOMY_COGS = [
    "cogs.general",
    "cogs.console",
    "cogs.economy",
    "cogs.albion_registration",
    "cogs.export",
    "cogs.audit",
    "cogs.ticket_runtime",
]
if MUSIC_ENABLED:
    ECONOMY_COGS.append("cogs.music")


@dataclass(frozen=True)
class BotSettings:
    token: str | None
    environment: str
    production_mode: bool
    allowed_role_id: int
    avalonian_log_channel_id: int
    enable_member_intent: bool
    enable_voice_intent: bool
    enable_message_content_intent: bool
    music_enabled: bool
    ffmpeg_path: str | None
    cogs: tuple[str, ...]

    def require_token(self):
        if self.token and (not self.production_mode or _secret_is_configured(self.token)):
            return self.token
        if self.production_mode:
            _raise_missing_production_secrets(["TOKEN o ECONOMY_TOKEN"])
        raise RuntimeError("Falta configurar ECONOMY_TOKEN o TOKEN en el archivo .env")


@dataclass(frozen=True)
class DashboardSettings:
    bot_token: str | None
    client_id: str | None
    client_secret: str | None
    redirect_uri: str | None
    public_url: str
    host: str
    port: int
    environment: str
    production_mode: bool
    session_secret: str | None
    cookie_secure: bool
    admin_password_hash: str | None
    admin_password_pepper: str | None
    admin_developer_ids: tuple[str, ...]
    admin_elevated_ttl_seconds: int
    admin_max_attempts: int
    admin_attempt_window_seconds: int
    admin_lockout_seconds: int

    def oauth_configured(self):
        return bool(self.client_id and self.client_secret)

    def validate_startup(self):
        if self.production_mode:
            missing = []
            if not _secret_is_configured(self.bot_token):
                missing.append("TOKEN o ECONOMY_TOKEN")
            if not _secret_is_configured(self.session_secret):
                missing.append("DASHBOARD_SESSION_SECRET")
            if not _secret_is_configured(self.admin_password_hash):
                missing.append("DASHBOARD_ADMIN_PASSWORD_HASH")
            if not _secret_is_configured(self.admin_password_pepper):
                missing.append("DASHBOARD_ADMIN_PASSWORD_PEPPER")
            if not self.admin_developer_ids:
                missing.append("DASHBOARD_ADMIN_DEVELOPER_IDS")
            if missing:
                _raise_missing_production_secrets(missing)
        if not self.session_secret:
            raise RuntimeError(
                "Falta configurar DASHBOARD_SESSION_SECRET en el archivo .env. "
                "El dashboard ya no reutiliza el token del bot como secreto de sesion."
            )
        if not self.bot_token:
            raise RuntimeError("Falta configurar ECONOMY_TOKEN o TOKEN en el archivo .env para el dashboard.")
        if bool(self.client_id) != bool(self.client_secret):
            raise RuntimeError(
                "Configura DASHBOARD_CLIENT_ID y DASHBOARD_CLIENT_SECRET juntos, "
                "o deja ambos vacios si todavia no habilitaras el login de Discord."
            )
        if self.admin_password_hash and not self.admin_password_pepper:
            raise RuntimeError(
                "Configura DASHBOARD_ADMIN_PASSWORD_PEPPER cuando uses "
                "DASHBOARD_ADMIN_PASSWORD_HASH para el panel administrativo."
            )
        return self


BOT_SETTINGS = BotSettings(
    token=ECONOMY_TOKEN,
    environment=APP_ENV,
    production_mode=DASHBOARD_PRODUCTION_MODE,
    allowed_role_id=ALLOWED_ROLE_ID,
    avalonian_log_channel_id=AVALONIAN_LOG_CHANNEL_ID,
    enable_member_intent=ENABLE_MEMBER_INTENT,
    enable_voice_intent=ENABLE_VOICE_INTENT,
    enable_message_content_intent=ENABLE_MESSAGE_CONTENT_INTENT,
    music_enabled=MUSIC_ENABLED,
    ffmpeg_path=FFMPEG_PATH,
    cogs=tuple(ECONOMY_COGS),
)

DASHBOARD_SETTINGS = DashboardSettings(
    bot_token=DASHBOARD_BOT_TOKEN,
    client_id=DASHBOARD_CLIENT_ID,
    client_secret=DASHBOARD_CLIENT_SECRET,
    redirect_uri=DASHBOARD_REDIRECT_URI,
    public_url=DASHBOARD_PUBLIC_URL,
    host=DASHBOARD_HOST,
    port=DASHBOARD_PORT,
    environment=DASHBOARD_ENVIRONMENT,
    production_mode=DASHBOARD_PRODUCTION_MODE,
    session_secret=DASHBOARD_SESSION_SECRET,
    cookie_secure=DASHBOARD_COOKIE_SECURE,
    admin_password_hash=DASHBOARD_ADMIN_PASSWORD_HASH,
    admin_password_pepper=DASHBOARD_ADMIN_PASSWORD_PEPPER,
    admin_developer_ids=DASHBOARD_ADMIN_DEVELOPER_IDS,
    admin_elevated_ttl_seconds=DASHBOARD_ADMIN_ELEVATED_TTL_SECONDS,
    admin_max_attempts=DASHBOARD_ADMIN_MAX_ATTEMPTS,
    admin_attempt_window_seconds=DASHBOARD_ADMIN_ATTEMPT_WINDOW_SECONDS,
    admin_lockout_seconds=DASHBOARD_ADMIN_LOCKOUT_SECONDS,
)


def require_bot_token():
    return BOT_SETTINGS.require_token()


def validate_dashboard_startup():
    return DASHBOARD_SETTINGS.validate_startup()
