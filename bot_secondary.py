import asyncio

from bot_core import build_bot
from config.settings import SECONDARY_COGS, SECONDARY_TOKEN


bot = build_bot(cogs=SECONDARY_COGS, enable_message_content=False)


@bot.event
async def on_ready():
    print(f"[Niveles] Conectado como {bot.user}")


async def main():
    if not SECONDARY_TOKEN:
        raise RuntimeError("Falta configurar SECONDARY_TOKEN en el archivo .env")

    async with bot:
        await bot.start(SECONDARY_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
