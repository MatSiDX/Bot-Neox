# Release Checklist Limpio

## Antes Del Release

1. Ejecutar:

```bat
python -m compileall .
python -m unittest discover -s tests -v
python scripts\validate_local.py
python -m pytest
```

2. Confirmar que `.env`, sesiones, logs y archivos SQLite runtime no estan en `git status`.
3. Confirmar que no quedan referencias activas a archivos legacy eliminados.
4. Confirmar que README y `.env.example` reflejan el estado actual del proyecto.

## Backups

1. Respaldar `data/bot.sqlite3`.
2. Respaldar `data/bot.sqlite3-wal` y `data/bot.sqlite3-shm` si existen.
3. Respaldar JSON legacy criticos:
   - `data/config.json`
   - `data/permissions.json`
   - `data/ping_templates.json`
   - `data/dashboard_sessions.json`

## Verificacion Funcional Minima

1. Bot arranca sin requerir segundo token.
2. Dashboard arranca con `web_dashboard.py`.
3. Login del dashboard no reutiliza el token del bot como secreto de sesion.
4. Los permisos por modulo siguen consistentes entre bot y dashboard.
5. Las exportaciones siguen protegidas por el permiso correcto.

## Cierre

1. Revisar `git diff`.
2. Revisar `git status --short`.
3. Confirmar que no hay secretos ni artefactos runtime listos para commit.
4. Adjuntar en notas de release:
   - cambios estructurales relevantes
   - migraciones aplicadas
   - JSON legacy que siguen vigentes
   - riesgos pendientes conocidos
