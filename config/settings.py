import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
ECONOMY_TOKEN = os.getenv("ECONOMY_TOKEN") or TOKEN
SECONDARY_TOKEN = os.getenv("SECONDARY_TOKEN")

ALLOWED_ROLE_ID = int(os.getenv("ALLOWED_ROLE_ID", "0"))
AVALONIAN_LOG_CHANNEL_ID = int(os.getenv("AVALONIAN_LOG_CHANNEL_ID", "0"))

ECONOMY_COGS = [
    "cogs.console",
    "cogs.economy",
    "cogs.export",
]

SECONDARY_COGS = [
    "secondary_cogs.core",
]
