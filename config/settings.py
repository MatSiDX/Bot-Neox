import os
from dotenv import load_dotenv

load_dotenv()


def _read_env_value(name: str):
    value = os.getenv(name)
    if value is None:
        return None

    cleaned = value.strip().strip('"').strip("'")
    return cleaned or None


TOKEN = _read_env_value("TOKEN")
ECONOMY_TOKEN = _read_env_value("ECONOMY_TOKEN") or TOKEN
SECONDARY_TOKEN = _read_env_value("SECONDARY_TOKEN")
DASHBOARD_REDIRECT_URI = _read_env_value("DASHBOARD_REDIRECT_URI")
DASHBOARD_PUBLIC_URL = (
    _read_env_value("DASHBOARD_PUBLIC_URL")
    or (
        DASHBOARD_REDIRECT_URI.removesuffix("/oauth/callback")
        if DASHBOARD_REDIRECT_URI
        else None
    )
    or "http://localhost:8000"
).rstrip("/")

ALLOWED_ROLE_ID = int(os.getenv("ALLOWED_ROLE_ID", "0"))
AVALONIAN_LOG_CHANNEL_ID = int(os.getenv("AVALONIAN_LOG_CHANNEL_ID", "0"))
ENABLE_MEMBER_INTENT = os.getenv("ENABLE_MEMBER_INTENT", "0").strip().lower() in ("1", "true", "yes", "on")
ENABLE_VOICE_INTENT = os.getenv("ENABLE_VOICE_INTENT", "1").strip().lower() in ("1", "true", "yes", "on")

ECONOMY_COGS = [
    "cogs.console",
    "cogs.economy",
    "cogs.albion_registration",
    "cogs.export",
    "cogs.audit",
    "cogs.ticket_runtime",
]

SECONDARY_COGS = [
    "secondary_cogs.core",
]
