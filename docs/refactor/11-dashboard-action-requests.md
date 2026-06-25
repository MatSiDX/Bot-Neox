# Fase 11 - Dashboard Action Requests

## Objetivo

Introducir un patron estable para que el dashboard deje de crecer ejecutando mutaciones directas sobre Discord.

## Flujo

1. El dashboard valida sesion y permisos.
2. El dashboard registra una solicitud en SQLite.
3. El bot reclama una solicitud pendiente de forma exclusiva.
4. El bot ejecuta la accion con `discord.py`.
5. El bot marca la solicitud como `completed`, `retry` o `failed`.
6. El dashboard consulta el estado y el resultado.

## Tabla SQLite

Tabla creada: `dashboard_action_requests`

Campos principales:

- `id`
- `guild_id`
- `action_type`
- `payload_json`
- `status`
- `requested_by`
- `result_json`
- `error`
- `created_at`
- `updated_at`
- `processed_at`
- `retry_count`
- `max_retries`
- `next_retry_at`
- `locked_by`
- `locked_at`
- `idempotency_key`
- `correlation_id`

## Estados

- `pending`
- `processing`
- `completed`
- `failed`
- `retry`

## Infraestructura creada

- Repositorio SQLite: `DashboardActionRequestRepository`
- Servicio: `DashboardActionService`
- Endpoint de consulta: `/api/dashboard-action-request`
- Worker en el bot: `EconomyCog.process_dashboard_action_requests`

## Accion piloto

Accion piloto migrada: `publish_report`

Antes:

- Dashboard escribia en `report_dashboard_requests.json`
- El bot lo recorria por polling

Ahora:

- Dashboard crea una fila en `dashboard_action_requests`
- El bot reclama solo acciones `publish_report`
- El resultado vuelve por la misma consulta legacy del dashboard

## Compatibilidad mantenida

- `ReportDashboardRepository` sigue existiendo como wrapper compatible
- `/api/report-calculator` sigue siendo el punto de entrada visible para la UI actual

## Pendiente para fases posteriores

- Migrar de forma progresiva otras mutaciones directas:
  - publicar panel de ticket
  - enviar mensaje desde dashboard
  - cerrar ticket
  - crear canal
  - editar mensaje
  - agregar o quitar rol
  - sincronizar usuario Albion
  - publicar ping

- Agregar workers por accion o por modulo cuando el dashboard deje de hacer llamadas directas a Discord en esas rutas
