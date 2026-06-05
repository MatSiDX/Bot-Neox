import asyncio

from bot_core import build_bot
from config.settings import ECONOMY_COGS, ECONOMY_TOKEN, SECONDARY_COGS, SECONDARY_TOKEN


economy_bot = build_bot(cogs=ECONOMY_COGS)
secondary_bot = build_bot(cogs=SECONDARY_COGS, enable_message_content=False)


@economy_bot.event
async def on_ready():
    print(f"[Economy] Conectado como {economy_bot.user}")


@secondary_bot.event
async def on_ready():
    print(f"[Niveles] Conectado como {secondary_bot.user}")


async def run_bot(bot, token_name, token):
    if not token:
        raise RuntimeError(f"Falta configurar {token_name} en el archivo .env")

    async with bot:
        await bot.start(token)


async def main():
    await asyncio.gather(
        run_bot(economy_bot, "ECONOMY_TOKEN o TOKEN", ECONOMY_TOKEN),
        run_bot(secondary_bot, "SECONDARY_TOKEN", SECONDARY_TOKEN),
    )


if __name__ == "__main__":
    asyncio.run(main())
