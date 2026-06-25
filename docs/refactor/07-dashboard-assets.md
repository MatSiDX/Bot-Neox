# Fase 6 - Extraccion de templates y assets del dashboard

Fecha de actualizacion: 2026-06-18

## Objetivo

Separar el HTML, CSS y JavaScript embebidos del dashboard sin cambiar stack, rutas publicas, OAuth, sesiones ni comportamiento visible.

## Corte aplicado

`web_dashboard.py` sigue siendo el entrypoint operativo y conserva:

- `DashboardHandler`
- las rutas GET/POST/DELETE
- el flujo OAuth y de sesiones
- el acceso a SQLite y JSON
- el control de permisos
- la logica de APIs y payloads

La extraccion se limito a assets estaticos y templates:

- `src/neox/dashboard/templates/login.html`
- `src/neox/dashboard/templates/dashboard.html`
- `src/neox/dashboard/static/css/login.css`
- `src/neox/dashboard/static/css/dashboard.css`
- `src/neox/dashboard/static/js/dashboard.js`

## Como se sirven los assets

El dashboard ahora usa dos helpers puros en `src/neox/dashboard/assets.py`:

- `load_dashboard_template(name)`: carga templates HTML desde disco.
- `resolve_dashboard_static_path(relative_path)`: resuelve archivos estaticos de forma segura y bloquea path traversal.

`web_dashboard.py` sirve los assets bajo la ruta publica:

- `/static/...`

Ejemplos:

- `/static/css/login.css`
- `/static/css/dashboard.css`
- `/static/js/dashboard.js`

## Compatibilidad mantenida

- `run_dashboard.bat` sigue arrancando `web_dashboard.py`.
- `run.bat` sigue funcionando porque `bot_manager.py` no cambia.
- `/` sigue mostrando el login.
- `/dashboard` sigue sirviendo la misma vista principal.
- `/assets/AvalonBot.png` y `/ticket-media/...` siguen con su manejo previo.

## Que no se movio todavia

- el HTML generado dinamicamente para transcripciones
- la logica de rutas y endpoints API
- llamadas a Discord y Albion
- acceso a base de datos y JSON
- reglas de permisos y serializacion de payloads

## Pendiente para la fase siguiente

- separar el JavaScript grande por modulos internos sin cambiar endpoints
- identificar bloques de render y estado que puedan dividirse por vista
- evaluar plantillas auxiliares para fragmentos dinamicos del dashboard
