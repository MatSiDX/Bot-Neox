# Operacion Local De Bot-Neox

## Requisitos

- Python 3.11 o superior
- Dependencias instaladas con `pip install -r requirements.txt`
- Archivo `.env` creado a partir de `.env.example`

## Inicio Del Bot

Opciones soportadas:

```bat
run.bat
```

o, si quieres iniciar solo el bot principal:

```bat
python bot.py
```

`run.bat` sigue siendo el flujo recomendado para operacion local porque levanta la consola de control y arranca el dashboard local junto con el bot.

## Inicio Del Dashboard

Opciones soportadas:

```bat
run_dashboard.bat
```

o:

```bat
python web_dashboard.py --host 127.0.0.1 --port 8000
```

URL local por defecto:

```text
http://127.0.0.1:8000/dashboard
```

## Variables De Entorno

### Bot

- `APP_ENV`: entorno general. Usa `production` en VPS/systemd para validar secretos obligatorios al arrancar.
- `TOKEN`: token principal del bot. Obligatorio si `ECONOMY_TOKEN` esta vacio.
- `ECONOMY_TOKEN`: alias compatible del token del bot. Si existe, tiene prioridad sobre `TOKEN`.
- `ALLOWED_ROLE_ID`: compatibilidad legacy para restricciones por rol.
- `AVALONIAN_LOG_CHANNEL_ID`: canal de logs para interacciones de Avalonianas.
- `ENABLE_MEMBER_INTENT`: habilita intents de miembros.
- `ENABLE_VOICE_INTENT`: habilita intents de voz.

### Dashboard

- `DASHBOARD_SESSION_SECRET`: obligatorio para sesiones firmadas. En produccion debe ser aleatorio y externo al repo.
- `DASHBOARD_ENV`: marca legacy del dashboard; si esta vacio hereda `APP_ENV`.
- `DASHBOARD_HOST`: host interno del dashboard; default seguro `127.0.0.1`.
- `DASHBOARD_PORT`: puerto interno del dashboard; default `8000`.
- `DASHBOARD_ADMIN_PASSWORD_HASH`: hash Argon2id de la clave secundaria del panel administrativo. Obligatorio en produccion.
- `DASHBOARD_ADMIN_PASSWORD_PEPPER`: pepper obligatoria para verificar esa clave secundaria. Obligatoria en produccion.
- `DASHBOARD_ADMIN_DEVELOPER_IDS`: lista separada por comas con los IDs de Discord autorizados. Obligatoria en produccion.
- `DASHBOARD_ADMIN_ELEVATED_TTL_SECONDS`: duracion de la sesion elevada, acotada entre 10 y 15 minutos.
- `DASHBOARD_CLIENT_ID`: cliente OAuth del dashboard.
- `DASHBOARD_CLIENT_SECRET`: secreto OAuth del dashboard.
- `DASHBOARD_REDIRECT_URI`: callback OAuth.
- `DASHBOARD_PUBLIC_URL`: URL publica base del dashboard.

En `APP_ENV=production`, el arranque falla si faltan `TOKEN`/`ECONOMY_TOKEN`,
`DASHBOARD_SESSION_SECRET`, `DASHBOARD_ADMIN_PASSWORD_HASH`,
`DASHBOARD_ADMIN_PASSWORD_PEPPER` o `DASHBOARD_ADMIN_DEVELOPER_IDS`, o si aun
contienen placeholders del ejemplo. Los errores no imprimen secretos completos.

### Generar Secretos Del Dashboard

`DASHBOARD_SESSION_SECRET`:

```bat
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

`DASHBOARD_ADMIN_PASSWORD_PEPPER`:

```bat
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

`DASHBOARD_ADMIN_PASSWORD_HASH` con Argon2id:

```bat
python -c "import getpass; from argon2 import PasswordHasher; password=getpass.getpass('Admin password: '); pepper=getpass.getpass('Admin pepper: '); print(PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16).hash(password + pepper))"
```

`DASHBOARD_ADMIN_DEVELOPER_IDS` debe contener IDs numericos de usuarios Discord,
separados por coma, por ejemplo:

```env
DASHBOARD_ADMIN_DEVELOPER_IDS=123456789012345678,234567890123456789
```

### Cache De Metadata De Discord

- `DISCORD_METADATA_ROLES_TTL_SECONDS`
- `DISCORD_METADATA_CHANNELS_TTL_SECONDS`
- `DISCORD_METADATA_CATEGORIES_TTL_SECONDS`
- `DISCORD_METADATA_EMOJIS_TTL_SECONDS`
- `DISCORD_METADATA_STALE_FALLBACK_SECONDS`

## Validaciones Locales Seguras

Estas validaciones no arrancan el bot ni conectan a Discord:

```bat
python -m compileall .
python -m unittest discover -s tests -v
python scripts\validate_local.py
python -m pytest
```

Notas:

- `scripts\validate_local.py` ejecuta `compileall`, una suite unitaria segura, `unittest discover` y `pytest` si esta disponible.
- Las pruebas que requieren `discord.py` o `aiohttp` se marcan como omitidas si esas dependencias no estan instaladas.

## Estructura Actual

```text
bot.py
web_dashboard.py
config/
repositories/
services/
cogs/
src/neox/
  config/
  core/
  dashboard/
tests/
docs/
```

Reglas actuales:

- `bot.py` sigue siendo el entrypoint del bot.
- `web_dashboard.py` sigue siendo el entrypoint del dashboard.
- `src/neox/core` concentra servicios y repositorios compartidos de bajo acoplamiento.
- `src/neox/dashboard/static` y `src/neox/dashboard/templates` contienen assets y templates del dashboard.

## Persistencia, Migraciones Y Backups

Persistencia principal:

- SQLite runtime: `data/bot.sqlite3`
- JSON legacy y runtime: bajo `data/`

Scripts utiles:

```bat
python scripts\backup_database.py
python scripts\migrate_economy_to_sqlite.py
python scripts\import_economy_data.py
python scripts\import_balance_names.py
```

Backups recomendados antes de cambios estructurales:

- `data/bot.sqlite3`
- `data/bot.sqlite3-wal`
- `data/bot.sqlite3-shm`
- `data/config.json`
- `data/permissions.json`
- `data/ping_templates.json`
- `data/dashboard_sessions.json`

## Manejo De JSON Legacy

Estado actual:

- `config.json` y `permissions.json` ya tienen migracion progresiva a SQLite con compatibilidad temporal.
- Los JSON originales no se eliminan automaticamente.
- La estrategia actual es `SQLite primero + fallback/backfill a JSON legacy + dual-write donde corresponde`.

Buenas practicas:

- No editar manualmente JSON legacy sin backup.
- No borrar JSON aunque ya exista tabla equivalente, salvo en una fase posterior explicitamente planeada.
- Si una migracion falla, restaurar primero backup de SQLite y JSON antes de repetir.
