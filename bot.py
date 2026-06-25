import asyncio

from bot_core import build_bot
from config.settings import ECONOMY_COGS, require_bot_token
from utils.console_logger import log_event


bot = build_bot(cogs=ECONOMY_COGS)


@bot.event
async def on_ready():
    log_event(f"Economy conectado como {bot.user}")


async def main():
    token = require_bot_token()

    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
