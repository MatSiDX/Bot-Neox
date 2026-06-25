# Fase 7 - Reduccion de carga inicial del dashboard

Fecha de actualizacion: 2026-06-18

## Objetivo

Reducir la carga inicial del dashboard para que el shell principal pueda abrir mas rapido y las secciones pesadas se carguen solo cuando el usuario entra a cada modulo.

## Bootstrap minimo actual

Al abrir `/dashboard`, el frontend solo pide:

- `/api/me`
- `/api/guilds`
- `/api/dashboard/access`

Con eso obtiene unicamente:

- sesion actual
- usuario actual
- `csrf_token`
- guilds disponibles
- guild seleccionado
- permisos minimos del guild seleccionado

## Datos que ya no se cargan al inicio

Ya no se cargan automaticamente al entrar:

- economia
- registros de balance
- registros de Avas
- informes
- multas
- paneles de tickets
- tickets en vivo
- metadata pesada de Discord como roles, canales, categorias y emojis
- auditoria
- plantillas de ping
- permisos del bot
- registro de Albion
- calculadora de reparto

## Carga por seccion

Cada seccion carga sus datos cuando el usuario entra a ella:

- `Economia`: `/api/data`
- `Plantillas`: `/api/ping-templates`
- `Tickets`: `/api/ticket-panels`, `/api/ticket-records`, `/api/fine-config` y metadata de Discord
- `Auditoria`: `/api/audit-config`, `/api/audit-events` y metadata de Discord
- `Permisos`: `/api/bot-permissions` y metadata de Discord
- `Registro Albion`: `/api/albion-registration` y metadata de Discord
- `Calculadora`: `/api/report-calculator`

## Compatibilidad mantenida

- `web_dashboard.py` sigue siendo el entrypoint.
- `/api/data` se mantiene como endpoint legacy para la seccion de economia y compatibilidad temporal.
- OAuth, sesiones, rutas publicas y estructura general del dashboard no cambian.

## Pendiente para una fase posterior

- dividir `dashboard.js` en modulos mas pequenos
- mover la carga por seccion a archivos JS dedicados
- seguir recortando endpoints grandes sin romper compatibilidad temporal
