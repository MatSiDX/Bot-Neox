def select_dashboard_guilds(guilds, requested_guild_id="", allowed_guilds=None, bot_guild_ids=None):
    allowed_guilds = allowed_guilds or None
    bot_guild_ids = set(bot_guild_ids) if bot_guild_ids is not None else None
    normalized = []

    for guild in guilds or []:
        guild_id = str(guild.get("id") or "")
        if not guild_id:
            continue
        if allowed_guilds is not None and guild_id not in allowed_guilds:
            continue
        if bot_guild_ids is not None and guild_id not in bot_guild_ids:
            continue

        guild_name = str(guild.get("name") or f"Servidor {guild_id}")
        if allowed_guilds is not None and guild_name.startswith("Servidor "):
            guild_name = str(allowed_guilds.get(guild_id, guild_name))
        normalized.append({"id": guild_id, "name": guild_name})

    requested_guild_id = str(requested_guild_id or "")
    available_guild_ids = {guild["id"] for guild in normalized}
    if requested_guild_id and requested_guild_id in available_guild_ids:
        selected_guild_id = requested_guild_id
    else:
        selected_guild_id = normalized[0]["id"] if normalized else ""

    return normalized, selected_guild_id
