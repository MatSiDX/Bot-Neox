import asyncio

from bot_core import build_bot
from config.settings import ECONOMY_COGS, ECONOMY_TOKEN
from utils.console_logger import log_event


bot = build_bot(cogs=ECONOMY_COGS)


@bot.event
async def on_ready():
    log_event(f"Economy conectado como {bot.user}")


async def main():
    if not ECONOMY_TOKEN:
        raise RuntimeError("Falta configurar ECONOMY_TOKEN o TOKEN en el archivo .env")

    async with bot:
        await bot.start(ECONOMY_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
