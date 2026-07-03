def oauth_configured(client_id, client_secret):
    return bool(client_id and client_secret)


def admin_guilds_from_discord(guilds, administrator_permission):
    admin_guilds = []
    for guild in guilds:
        permissions = int(guild.get("permissions", 0) or 0)
        if guild.get("owner") or permissions & administrator_permission:
            admin_guilds.append({
                "id": str(guild.get("id")),
                "name": str(guild.get("name") or f"Servidor {guild.get('id')}"),
                "icon": str(guild.get("icon") or ""),
            })
    return admin_guilds


def guilds_from_discord(guilds):
    return [
        {
            "id": str(guild.get("id")),
            "name": str(guild.get("name") or f"Servidor {guild.get('id')}"),
            "icon": str(guild.get("icon") or ""),
        }
        for guild in guilds
        if guild.get("id")
    ]
