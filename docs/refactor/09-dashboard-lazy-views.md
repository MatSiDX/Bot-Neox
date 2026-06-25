# Fase 8 - Carga lazy por vista en el dashboard

Fecha de actualizacion: 2026-06-18

## Objetivo

Separar la carga de datos del dashboard por vista para que cada modulo llame solo a los endpoints que necesita cuando el usuario entra en esa seccion.

## Router y loaders

Se agrego un router ligero en:

- `src/neox/dashboard/static/js/router.js`

Y loaders por vista en:

- `src/neox/dashboard/static/js/pages/economy.js`
- `src/neox/dashboard/static/js/pages/pings.js`
- `src/neox/dashboard/static/js/pages/tickets.js`
- `src/neox/dashboard/static/js/pages/fines.js`
- `src/neox/dashboard/static/js/pages/audit.js`
- `src/neox/dashboard/static/js/pages/permissions.js`
- `src/neox/dashboard/static/js/pages/albion.js`
- `src/neox/dashboard/static/js/pages/report-calculator.js`

`dashboard.js` mantiene:

- estado global compartido
- render de cada seccion
- handlers de UI
- utilidades comunes
- bootstrap minimo de sesion, guilds y access

## Endpoints por vista

`Economia`

- `/api/data`

`Plantillas / Pings`

- `/api/ping-templates`

`Tickets`

- `/api/ticket-panels`
- `/api/ticket-records`
- metadata Discord compartida:
  - `/api/discord-channels`
  - `/api/discord-categories`
  - `/api/discord-emojis`
  - `/api/discord-roles`

`Multas`

- `/api/fine-config`

`Auditoria`

- `/api/audit-config`
- `/api/audit-events`
- metadata Discord compartida

`Permisos`

- `/api/bot-permissions`
- metadata Discord compartida

`Registro Albion`

- `/api/albion-registration`
- metadata Discord compartida

`Calculadora de reparto`

- `/api/report-calculator`

## Datos que ya no se renderizan de golpe

`render()` ya no llama a todos los renderers de todos los modulos. Ahora:

- actualiza shell comun
- renderiza solo la vista activa

La navegacion entre secciones dispara:

- render del shell
- render de la vista activa
- loader lazy de la vista activa

## Compatibilidad mantenida

- `web_dashboard.py` sigue siendo el entrypoint
- los endpoints legacy siguen disponibles
- OAuth, sesiones, SQLite y JSON no cambian
- las vistas mantienen su comportamiento funcional actual
