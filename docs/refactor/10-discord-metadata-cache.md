# Fase 10 - Cache De Metadata De Discord

## Objetivo

Reducir llamadas repetidas a la API de Discord desde el dashboard sin cambiar el comportamiento funcional del bot ni de las vistas administrativas.

## Servicio

- Servicio principal: `DiscordMetadataService`
- Ubicacion core: `src/neox/core/services/discord_metadata_service.py`
- Wrapper legacy: `services/discord_metadata_service.py`

## Metadata cacheada por guild

- `roles`
- `channels`
- `categories`
- `emojis`

## TTL por tipo

- `roles`: 900 segundos
- `channels`: 300 segundos
- `categories`: 300 segundos
- `emojis`: 1800 segundos
- `stale fallback`: 3600 segundos

Los TTL se pueden ajustar por entorno con:

- `DISCORD_METADATA_ROLES_TTL_SECONDS`
- `DISCORD_METADATA_CHANNELS_TTL_SECONDS`
- `DISCORD_METADATA_CATEGORIES_TTL_SECONDS`
- `DISCORD_METADATA_EMOJIS_TTL_SECONDS`
- `DISCORD_METADATA_STALE_FALLBACK_SECONDS`

## Comportamiento

- `channels` y `categories` comparten una sola consulta a `/guilds/{guild_id}/channels`.
- Si una entrada sigue fresca, se devuelve desde memoria y no se consulta Discord.
- Si la entrada expiro y Discord responde con error o rate limit, se reutiliza la ultima copia cacheada mientras siga dentro del margen `stale fallback`.
- La recarga manual usa `refresh=1` en los endpoints del dashboard y fuerza la actualizacion de la metadata solicitada.

## Endpoints

- Nuevo endpoint agregado:
  - `/api/discord-metadata`

- Endpoints legacy que ahora reutilizan la misma cache:
  - `/api/discord-channels`
  - `/api/discord-categories`
  - `/api/discord-emojis`
  - `/api/discord-roles`

## Carga por vista

- `Tickets`: canales, categorias, emojis y roles
- `Auditoria`: canales
- `Permisos`: roles
- `Registro Albion`: canales y roles

Con esto, el dashboard deja de disparar cuatro requests de metadata en cada vista aunque no todas las necesiten.
