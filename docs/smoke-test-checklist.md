# Smoke Test Manual

## Preparacion

1. Crear `.env` a partir de `.env.example`.
2. Instalar dependencias con `pip install -r requirements.txt`.
3. Ejecutar:

```bat
python -m compileall .
python -m unittest discover -s tests -v
```

## Bot

1. Ejecutar `run.bat` o `python bot.py`.
2. Confirmar que el proceso arranca sin traceback inmediato.
3. Confirmar que los cogs cargan sin errores de importacion.
4. Confirmar que la consola de control responde a `status`.

## Dashboard

1. Ejecutar `run_dashboard.bat` o `python web_dashboard.py --host 127.0.0.1 --port 8000`.
2. Abrir `http://127.0.0.1:8000/`.
3. Confirmar que la pagina de login carga sin errores de assets.
4. Confirmar que `http://127.0.0.1:8000/static/css/dashboard.css` responde.

## Seguridad Basica

1. Confirmar que el dashboard no inicia si falta `DASHBOARD_SESSION_SECRET`.
2. Confirmar que `ticket-media` devuelve `403` si no hay sesion o permiso de tickets.
3. Confirmar que un POST sensible sin CSRF devuelve error.
4. Confirmar que un error interno no muestra traceback crudo al usuario.

## Dashboard Por Modulo

1. Entrar con un usuario administrador y confirmar acceso a Economia, Tickets, Auditoria, Plantillas, Permisos y Registro Albion.
2. Entrar con un usuario con permisos parciales y confirmar que solo ve las secciones permitidas.
3. Confirmar que la carga inicial del dashboard no intenta renderizar todos los modulos pesados a la vez.

## Persistencia

1. Confirmar que `data/bot.sqlite3` existe o se crea correctamente.
2. Confirmar que `config.json` y `permissions.json` no se eliminan.
3. Confirmar que backups manuales de SQLite y JSON siguen siendo posibles.

## Cierre

1. Detener el bot/dashboard.
2. Confirmar que no se generaron archivos sensibles nuevos fuera de `data/`.
3. Confirmar que `git status` no muestra secretos, sesiones ni logs runtime.
