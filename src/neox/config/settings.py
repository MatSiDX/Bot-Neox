import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return False


load_dotenv()

TRUE_VALUES = ("1", "true", "yes", "on")


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


_PROJECT_ROOT_PATH = Path(__file__).resolve().parents[3]
_DATA_DIR_PATH = _PROJECT_ROOT_PATH / "data"
_ASSETS_DIR_PATH = _PROJECT_ROOT_PATH / "assets"

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
DASHBOARD_PUBLIC_URL = (
    _read_env_value("DASHBOARD_PUBLIC_URL")
    or (
        DASHBOARD_REDIRECT_URI.removesuffix("/oauth/callback")
        if DASHBOARD_REDIRECT_URI
        else None
    )
    or "http://localhost:8000"
).rstrip("/")

ALLOWED_ROLE_ID = _read_env_int("ALLOWED_ROLE_ID", 0)
AVALONIAN_LOG_CHANNEL_ID = _read_env_int("AVALONIAN_LOG_CHANNEL_ID", 0)
ENABLE_MEMBER_INTENT = _read_env_bool("ENABLE_MEMBER_INTENT", default=False)
ENABLE_VOICE_INTENT = _read_env_bool("ENABLE_VOICE_INTENT", default=True)
ENABLE_MESSAGE_CONTENT_INTENT = _read_env_bool("ENABLE_MESSAGE_CONTENT_INTENT", default=False)
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
    "cogs.music",
]


@dataclass(frozen=True)
class BotSettings:
    token: str | None
    allowed_role_id: int
    avalonian_log_channel_id: int
    enable_member_intent: bool
    enable_voice_intent: bool
    enable_message_content_intent: bool
    cogs: tuple[str, ...]

    def require_token(self):
        if self.token:
            return self.token
        raise RuntimeError("Falta configurar ECONOMY_TOKEN o TOKEN en el archivo .env")


@dataclass(frozen=True)
class DashboardSettings:
    bot_token: str | None
    client_id: str | None
    client_secret: str | None
    redirect_uri: str | None
    public_url: str
    session_secret: str | None

    def oauth_configured(self):
        return bool(self.client_id and self.client_secret)

    def validate_startup(self):
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
        return self


BOT_SETTINGS = BotSettings(
    token=ECONOMY_TOKEN,
    allowed_role_id=ALLOWED_ROLE_ID,
    avalonian_log_channel_id=AVALONIAN_LOG_CHANNEL_ID,
    enable_member_intent=ENABLE_MEMBER_INTENT,
    enable_voice_intent=ENABLE_VOICE_INTENT,
    enable_message_content_intent=ENABLE_MESSAGE_CONTENT_INTENT,
    cogs=tuple(ECONOMY_COGS),
)

DASHBOARD_SETTINGS = DashboardSettings(
    bot_token=DASHBOARD_BOT_TOKEN,
    client_id=DASHBOARD_CLIENT_ID,
    client_secret=DASHBOARD_CLIENT_SECRET,
    redirect_uri=DASHBOARD_REDIRECT_URI,
    public_url=DASHBOARD_PUBLIC_URL,
    session_secret=DASHBOARD_SESSION_SECRET,
)


def require_bot_token():
    return BOT_SETTINGS.require_token()


def validate_dashboard_startup():
    return DASHBOARD_SETTINGS.validate_startup()
