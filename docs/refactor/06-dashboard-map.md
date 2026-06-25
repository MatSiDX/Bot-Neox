# Fase 5 - Primer corte del dashboard

Fecha de actualizacion: 2026-06-18

## Objetivo

Reducir el acoplamiento interno de `web_dashboard.py` sin cambiar stack, rutas publicas ni comportamiento visible.

## Mapa actual del dashboard

`web_dashboard.py` sigue siendo el entrypoint y conserva:

- el `DashboardHandler`
- las rutas GET/POST/DELETE
- el acceso a SQLite y JSON
- la logica de permisos ligada al flujo HTTP
- las llamadas a Discord y Albion

Desde la Fase 6, el HTML principal y los assets del dashboard viven fuera de este archivo:

- `src/neox/dashboard/templates/login.html`
- `src/neox/dashboard/templates/dashboard.html`
- `src/neox/dashboard/static/css/login.css`
- `src/neox/dashboard/static/css/dashboard.css`
- `src/neox/dashboard/static/js/dashboard.js`

## Funciones extraidas en esta fase

`src/neox/dashboard/http_utils.py`

- `format_number`
- `parse_iso_datetime`
- `format_argentina_datetime`
- `argentina_now_display`
- `clean_user_name`
- `ARGENTINA_TZ`

`src/neox/dashboard/security.py`

- `safe_dashboard_next`
- `DashboardCookieManager`
  - `make_session_cookie`
  - `make_state_cookie`
  - `parse_cookie_header`
  - `sign_session_id`
  - `encode_session_cookie`
  - `decode_session_cookie`

`src/neox/dashboard/sessions.py`

- `DashboardSessionStore`
  - `remember_oauth_state`
  - `consume_oauth_state`
  - `load_persisted_sessions`
  - `save_persisted_sessions`
  - `create_session`
  - `get_session_from_request`
  - `clear_session_from_request`

`src/neox/dashboard/auth.py`

- `oauth_configured`
- `admin_guilds_from_discord`
- `guilds_from_discord`

## Corte aplicado

La integracion se hizo por alias y objetos dentro de `web_dashboard.py`:

- `COOKIE_MANAGER`
- `SESSION_STORE`

Esto permite conservar el resto del archivo casi intacto mientras se reduce el bloque de helpers embebidos.

## Que queda dentro de `web_dashboard.py`

- networking contra Discord y Albion
- serializacion de mensajes y transcripts
- carga/guardado de ticket panels y audit config
- payloads de plantillas, multas, permisos y Albion registration
- acceso SQL y construccion de datos del dashboard
- `DashboardHandler`
- HTML dinamico de transcripts

## Que queda pendiente para la siguiente fase

- extraer helpers de API (`discord_request`, `discord_json_request`, `albion_json_request`)
- separar mas serializacion/render de transcript y mensajes
- evaluar corte de acceso a datos del dashboard en modulos propios
- seguir reduciendo responsabilidades directas del handler sin cambiar rutas
