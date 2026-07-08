import logging

import discord
from discord import app_commands

from utils.console_logger import configure_logging, log_exception


GENERIC_ERROR_MESSAGE = "Ocurrio un error procesando esta interaccion. Ya quedo registrado en los logs."


def describe_interaction(interaction):
    if interaction is None:
        return "interaction=unknown"

    user = getattr(interaction, "user", None)
    guild = getattr(interaction, "guild", None)
    custom_id = ""
    if getattr(interaction, "data", None):
        custom_id = interaction.data.get("custom_id", "")

    command = getattr(interaction, "command", None)
    parts = [
        f"type={getattr(interaction, 'type', 'unknown')}",
        f"user={getattr(user, 'id', 'unknown')}",
        f"guild={getattr(guild, 'id', 'dm')}",
    ]
    if command:
        parts.append(f"command={getattr(command, 'qualified_name', command)}")
    if custom_id:
        parts.append(f"custom_id={custom_id}")
    return " ".join(parts)


async def send_safe_interaction_error(interaction, message=GENERIC_ERROR_MESSAGE):
    if interaction is None:
        return

    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except (discord.HTTPException, discord.NotFound, discord.Forbidden):
        logging.getLogger("bot").warning("No pude enviar respuesta de error a Discord: %s", describe_interaction(interaction))


class SafeView(discord.ui.View):
    async def on_error(self, interaction, error, item):
        item_name = getattr(item, "custom_id", None) or getattr(item, "label", None) or type(item).__name__
        log_exception(f"Error en callback de view item={item_name} {describe_interaction(interaction)}", error)
        await send_safe_interaction_error(interaction)


class SafeModal(discord.ui.Modal):
    async def on_error(self, interaction, error):
        log_exception(f"Error en modal {type(self).__name__} {describe_interaction(interaction)}", error)
        await send_safe_interaction_error(interaction)


class SafeCommandTree(app_commands.CommandTree):
    async def on_error(self, interaction, error):
        log_exception(f"Error en slash command {describe_interaction(interaction)}", error)
        await send_safe_interaction_error(interaction)


def configure_asyncio_exception_handler(loop):
    configure_logging()

    def handle_exception(_loop, context):
        exception = context.get("exception")
        message = context.get("message", "Error no controlado en tarea asyncio")
        if exception:
            log_exception(message, exception)
        else:
            logging.getLogger("bot").error(message)

    loop.set_exception_handler(handle_exception)
