# Deployment En VPS Con systemd

Esta guia prepara Bot-Neox para correr 24/7 en una VPS Linux usando `systemd`.
En produccion, `bot_manager.py` no debe ser el supervisor principal: ese archivo
queda para uso manual/local. En VPS, el bot y el dashboard se ejecutan como
servicios separados con autoarranque, autoreinicio y logs centralizados.

## Supuestos

- Ruta del proyecto en la VPS: `/opt/bot-neox`
- Usuario del sistema sin privilegios: `botneox`
- Entorno virtual: `/opt/bot-neox/.venv`
- Archivo de variables productivas: `/opt/bot-neox/.env`
- Bot: `bot.py`
- Dashboard: `web_dashboard.py --host 127.0.0.1 --port 8000`

Puedes cambiar `/opt/bot-neox` por otra ruta, pero si lo haces debes ajustar
`WorkingDirectory`, `EnvironmentFile`, `ExecStart`, `Documentation` y
`ReadWritePaths` en los archivos de `deploy/systemd/`.

## Preparar Usuario Y Proyecto

Crear el usuario dedicado de sistema. No se asume que exista; el comando lo
crea solo si falta. Usa `nologin` para evitar login interactivo y un home
controlado en `/opt/bot-neox`:

```bash
if ! id -u botneox >/dev/null 2>&1; then
  sudo useradd --system --user-group --home-dir /opt/bot-neox --create-home --shell /usr/sbin/nologin botneox
fi
getent passwd botneox
getent group botneox
```

Crear el directorio del proyecto. El codigo debe quedar administrado por root y
legible por el servicio, pero no escribible por `botneox`:

```bash
sudo mkdir -p /opt/bot-neox
sudo chown root:botneox /opt/bot-neox
sudo chmod 750 /opt/bot-neox
```

Copiar o clonar el proyecto dentro de `/opt/bot-neox`. Hazlo como root o con tu
usuario operador usando `sudo`, no ejecutando la aplicacion como root. Despues
de copiar, deja el arbol de codigo en modo solo lectura para el servicio:

```bash
sudo chown -R root:botneox /opt/bot-neox
sudo find /opt/bot-neox -type d -exec chmod 750 {} \;
sudo find /opt/bot-neox -type f -exec chmod 640 {} \;
sudo chmod 750 /opt/bot-neox/deploy/scripts/*.sh
```

Instalar Python y dependencias en un venv del proyecto:

```bash
cd /opt/bot-neox
sudo install -d -o botneox -g botneox -m 750 /opt/bot-neox/.venv
sudo -u botneox python3 -m venv /opt/bot-neox/.venv
sudo -u botneox /opt/bot-neox/.venv/bin/python -m pip install --upgrade pip
sudo -u botneox /opt/bot-neox/.venv/bin/pip install -r requirements.txt
sudo chown -R root:botneox /opt/bot-neox/.venv
sudo find /opt/bot-neox/.venv -type d -exec chmod 750 {} \;
sudo find /opt/bot-neox/.venv -type f -exec chmod 640 {} \;
sudo find /opt/bot-neox/.venv/bin -type f -exec chmod 750 {} \;
```

Si el modulo de musica estara activo, instalar FFmpeg en el sistema. No se
instala desde Python ni desde el bot:

```bash
sudo apt update && sudo apt install -y ffmpeg
ffmpeg -version
```

El comando `ffmpeg -version` debe imprimir la version instalada. Si tu FFmpeg
esta fuera de `PATH`, configura `FFMPEG_PATH` en `/opt/bot-neox/.env`.

Crear el archivo `.env` productivo desde el ejemplo:

```bash
cd /opt/bot-neox
sudo cp .env.example .env
sudo chown root:botneox .env
sudo chmod 640 .env
sudo nano .env
```

No guardes secretos reales en Git. Configura como minimo:

- `TOKEN` o `ECONOMY_TOKEN`
- `APP_ENV=production`
- `DASHBOARD_ENV=production` si quieres mantener la marca legacy del dashboard
- `DASHBOARD_SESSION_SECRET`
- `DASHBOARD_ADMIN_PASSWORD_HASH`
- `DASHBOARD_ADMIN_PASSWORD_PEPPER`
- `DASHBOARD_ADMIN_DEVELOPER_IDS`
- `DASHBOARD_CLIENT_ID` y `DASHBOARD_CLIENT_SECRET`, si usaras OAuth
- `DASHBOARD_REDIRECT_URI`
- `DASHBOARD_PUBLIC_URL`
- `DASHBOARD_COOKIE_SECURE=true` cuando el acceso publico sea HTTPS
- `MUSIC_ENABLED=true` si usaras comandos de musica
- `FFMPEG_PATH=/usr/bin/ffmpeg` solo si `ffmpeg` no esta disponible en `PATH`

En produccion el arranque falla si falta un secreto critico o si dejaste un
placeholder del ejemplo. El error solo muestra nombres de variables, no valores.

### Generar Secretos Productivos

Generar `DASHBOARD_SESSION_SECRET`:

```bash
sudo -u botneox /opt/bot-neox/.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Generar `DASHBOARD_ADMIN_PASSWORD_PEPPER`:

```bash
sudo -u botneox /opt/bot-neox/.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Generar `DASHBOARD_ADMIN_PASSWORD_HASH` con Argon2id. Usa el mismo pepper que
guardaras en `.env`; el comando no imprime la clave en claro:

```bash
read -rsp "Admin password: " ADMIN_PASSWORD; echo
read -rsp "Admin pepper: " ADMIN_PEPPER; echo
export ADMIN_PASSWORD ADMIN_PEPPER
sudo --preserve-env=ADMIN_PASSWORD,ADMIN_PEPPER -u botneox /opt/bot-neox/.venv/bin/python -c "import os; from argon2 import PasswordHasher; print(PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16).hash(os.environ['ADMIN_PASSWORD'] + os.environ['ADMIN_PEPPER']))"
unset ADMIN_PASSWORD ADMIN_PEPPER
```

Configurar allowlist admin:

```env
DASHBOARD_ADMIN_DEVELOPER_IDS=123456789012345678,234567890123456789
```

Usa IDs numericos de usuarios Discord autorizados a elevar acceso administrativo.
No uses nombres de usuario ni roles como sustituto de esta allowlist.

Si necesitas cambiar el bind interno en desarrollo, puedes usar
`DASHBOARD_HOST` y `DASHBOARD_PORT`. En produccion deben conservarse como
`127.0.0.1` y `8000`; los servicios systemd de ejemplo lo fuerzan tambien por
CLI para evitar publicar el dashboard accidentalmente.

Crear directorios runtime escribibles por el servicio. Estos son los unicos
lugares del proyecto donde `botneox` debe escribir en produccion:

```bash
sudo mkdir -p /opt/bot-neox/data
sudo mkdir -p /opt/bot-neox/data/ticket_media
sudo mkdir -p /opt/bot-neox/data/fine_proofs
sudo mkdir -p /opt/bot-neox/data/chest_table_images
sudo chown -R botneox:botneox /opt/bot-neox/data
sudo find /opt/bot-neox/data -type d -exec chmod 750 {} \;
sudo find /opt/bot-neox/data -type f -exec chmod 640 {} \;
```

`data/` contiene la base SQLite, JSON runtime, sesiones del dashboard,
transcripts y archivos subidos/evidencias. No uses `chmod 777`; si aparece un
error de permisos, corrige propietario y rutas escribibles en lugar de abrir
todo el arbol.

Los logs normales van a journald mediante systemd. Si configuras
`BOT_NEOX_BACKUP_LOG_FILE`, usa un directorio controlado y escribible solo por
el servicio:

```bash
sudo mkdir -p /var/log/bot-neox
sudo chown botneox:botneox /var/log/bot-neox
sudo chmod 750 /var/log/bot-neox
```

Ejemplo seguro:

```env
BOT_NEOX_BACKUP_LOG_FILE=/var/log/bot-neox/backup.log
```

## Servicios systemd

Los ejemplos viven en:

- `deploy/systemd/bot-neox.service`
- `deploy/systemd/bot-neox-dashboard.service`

Ambos servicios:

- arrancan con la VPS mediante `WantedBy=multi-user.target`
- esperan red con `network-online.target`
- reinician ante fallos con `Restart=on-failure`
- corren con el usuario no root `botneox`
- cargan variables desde `/opt/bot-neox/.env`
- fuerzan `APP_ENV=production` desde systemd para activar validaciones de arranque
- ejecutan desde `/opt/bot-neox`
- usan `/opt/bot-neox/.venv/bin/python`
- no ejecutan Python como root
- desactivan escritura de bytecode Python con `PYTHONDONTWRITEBYTECODE=1`
- endurecen el filesystem con `ProtectSystem=strict`
- permiten escritura solo en `/opt/bot-neox/data`
- envian stdout/stderr a journald

El servicio `bot-neox-dashboard.service` define tambien `DASHBOARD_ENV=production`
por compatibilidad y arranca explicitamente con `--host 127.0.0.1 --port 8000`.

Instalar los servicios:

```bash
cd /opt/bot-neox
sudo cp deploy/systemd/bot-neox.service /etc/systemd/system/bot-neox.service
sudo cp deploy/systemd/bot-neox-dashboard.service /etc/systemd/system/bot-neox-dashboard.service
sudo systemctl daemon-reload
```

Habilitar autoarranque:

```bash
sudo systemctl enable bot-neox.service
sudo systemctl enable bot-neox-dashboard.service
```

Iniciar servicios:

```bash
sudo systemctl start bot-neox.service
sudo systemctl start bot-neox-dashboard.service
```

Ver estado:

```bash
systemctl status bot-neox.service
systemctl status bot-neox-dashboard.service
```

Ver logs:

```bash
journalctl -u bot-neox.service -f
journalctl -u bot-neox-dashboard.service -f
```

Reiniciar servicios:

```bash
sudo systemctl restart bot-neox.service
sudo systemctl restart bot-neox-dashboard.service
```

Detener servicios:

```bash
sudo systemctl stop bot-neox.service
sudo systemctl stop bot-neox-dashboard.service
```

## Backups Automaticos De Runtime

El proyecto incluye un backup fuera del runtime activo para:

- `data/bot.sqlite3`
- sidecars `data/bot.sqlite3-wal` y `data/bot.sqlite3-shm` si existen
- JSON criticos de `data/` configurados por lista segura

El script usa `sqlite3.Connection.backup()`, equivalente al flujo seguro de
`.backup` de SQLite. Esto evita copiar una base WAL a medio escribir y mantiene
el bloqueo durante ventanas cortas. Los sidecars WAL/SHM se agregan al archivo
comprimido solo como referencia operativa; para restaurar se usa
`data/bot.sqlite3` generado por el backup seguro.

Por defecto, el destino productivo es `/var/backups/bot-neox/` y la retencion
conserva los ultimos 7 backups comprimidos. No se incluye `.env`, tokens ni
secretos por defecto.

Variables opcionales en `/opt/bot-neox/.env`:

```env
BOT_NEOX_BACKUP_DIR=/var/backups/bot-neox
BOT_NEOX_BACKUP_RETENTION=7
BOT_NEOX_BACKUP_JSON_FILES=
BOT_NEOX_BACKUP_LOG_FILE=
```

Si `BOT_NEOX_BACKUP_JSON_FILES` esta vacio, se usa la lista por defecto del
script con JSON runtime conocidos como `config.json`, `permissions.json`,
`ping_templates.json`, `dashboard_sessions.json`, `ticket_records.json`,
`report_runtime.json`, `audit_events.json`, `reports.json` y otros JSON
operativos. Si necesitas personalizarla, usa nombres relativos a `data/`:

```env
BOT_NEOX_BACKUP_JSON_FILES=config.json,permissions.json,ping_templates.json,dashboard_sessions.json,ticket_records.json
```

Crear el directorio externo de backups:

```bash
sudo mkdir -p /var/backups/bot-neox
sudo chown botneox:botneox /var/backups/bot-neox
sudo chmod 750 /var/backups/bot-neox
```

El servicio `bot-neox-backup.service` corre tambien como `botneox`, usa
`ProtectSystem=strict`, lee `data/` y solo puede escribir en
`/var/backups/bot-neox` y `/var/log/bot-neox` si activas log adicional. No debe
guardar `.env`, tokens ni secretos.

Instalar el servicio y timer:

```bash
cd /opt/bot-neox
sudo cp deploy/systemd/bot-neox-backup.service /etc/systemd/system/bot-neox-backup.service
sudo cp deploy/systemd/bot-neox-backup.timer /etc/systemd/system/bot-neox-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now bot-neox-backup.timer
```

El timer corre diariamente a las `04:20` con hasta 15 minutos de demora
aleatoria. Cambia `OnCalendar` en `deploy/systemd/bot-neox-backup.timer` si
prefieres otro horario.

Tambien puedes usar cron si tu VPS no usa timers:

```cron
20 4 * * * cd /opt/bot-neox && /opt/bot-neox/.venv/bin/python /opt/bot-neox/scripts/backup_runtime.py >> /var/backups/bot-neox/backup.log 2>&1
```

### Restauracion Basica

1. Detener el bot y el dashboard para que no escriban durante la restauracion:

```bash
sudo systemctl stop bot-neox.service bot-neox-dashboard.service
```

2. Extraer el backup elegido en un directorio temporal:

```bash
sudo mkdir -p /tmp/bot-neox-restore
sudo tar -xzf /var/backups/bot-neox/bot-neox-runtime-YYYYMMDDTHHMMSSZ.tar.gz -C /tmp/bot-neox-restore
```

3. Guardar una copia manual del estado actual antes de reemplazar:

```bash
sudo -u botneox cp /opt/bot-neox/data/bot.sqlite3 /opt/bot-neox/data/bot.sqlite3.before-restore
```

4. Restaurar la base generada por `.backup` y los JSON necesarios:

```bash
sudo -u botneox cp /tmp/bot-neox-restore/data/bot.sqlite3 /opt/bot-neox/data/bot.sqlite3
sudo -u botneox cp /tmp/bot-neox-restore/data/*.json /opt/bot-neox/data/
```

5. Asegurar permisos y arrancar servicios:

```bash
sudo chown -R botneox:botneox /opt/bot-neox/data
sudo systemctl start bot-neox.service bot-neox-dashboard.service
```

Si existian `bot.sqlite3-wal` o `bot.sqlite3-shm` viejos en `data/`, eliminalos
solo con los servicios detenidos y despues de confirmar que restauraste
`bot.sqlite3`. SQLite los recreara cuando sean necesarios.

### Como Probar Backups

Ejecutar backup manual:

```bash
cd /opt/bot-neox
sudo -u botneox /opt/bot-neox/.venv/bin/python /opt/bot-neox/scripts/backup_runtime.py
```

Listar backups generados:

```bash
sudo -u botneox ls -lh /var/backups/bot-neox/
```

Verificar contenido del backup:

```bash
sudo -u botneox tar -tzf /var/backups/bot-neox/bot-neox-runtime-YYYYMMDDTHHMMSSZ.tar.gz
```

El listado debe incluir `data/bot.sqlite3`, `manifest.txt` y los JSON runtime
configurados. No debe incluir `.env` ni archivos de secretos.

Activar timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bot-neox-backup.timer
systemctl list-timers bot-neox-backup.timer
```

Revisar logs:

```bash
journalctl -u bot-neox-backup.service -n 100 --no-pager
journalctl -u bot-neox-backup.service -f
```

Forzar una ejecucion del servicio sin esperar al timer:

```bash
sudo systemctl start bot-neox-backup.service
journalctl -u bot-neox-backup.service -n 100 --no-pager
```

## Dashboard Publico Con Reverse Proxy

El servicio de dashboard escucha por defecto en `127.0.0.1:8000`. Para exponerlo
en Internet, se recomienda usar un reverse proxy como Nginx o Caddy con HTTPS y
mantener el dashboard ligado a localhost.

Ejemplo conceptual:

```text
Internet -> HTTPS reverse proxy -> 127.0.0.1:8000
```

No cambies el dashboard a `0.0.0.0:8000` en produccion. El puerto `8000/tcp`
debe aceptar conexiones solo desde la propia VPS. En el firewall publico abre
unicamente `80/tcp` y `443/tcp`.

El entrypoint acepta estos overrides documentados:

```env
APP_ENV=production
DASHBOARD_ENV=production
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=8000
```

`APP_ENV=production` activa las validaciones obligatorias de secretos. Ademas,
`APP_ENV=production` o `DASHBOARD_ENV=production` activan una advertencia si el
dashboard se inicia ligado a `0.0.0.0` o `::`. La advertencia existe para
detectar una mala configuracion, no para autorizar ese bind en produccion.

Configura `DASHBOARD_PUBLIC_URL` y `DASHBOARD_REDIRECT_URI` con la URL publica
real, por ejemplo:

```env
DASHBOARD_PUBLIC_URL=https://dashboard.tudominio.com
DASHBOARD_REDIRECT_URI=https://dashboard.tudominio.com/oauth/callback
DASHBOARD_COOKIE_SECURE=true
```

Estas variables son importantes cuando hay HTTPS delante del dashboard: evitan
que OAuth calcule callbacks locales `http://127.0.0.1:8000/...` y hacen que el
dashboard conozca su URL publica segura sin exponer el servidor interno.
`DASHBOARD_COOKIE_SECURE=true` hace que las cookies de sesion y de estado OAuth
se emitan con `Secure`, ademas de conservar `HttpOnly` y `SameSite=Lax`. Dejalo
en `false` solo para pruebas locales por `http://127.0.0.1:8000`.

### Opcion Recomendada: Caddy

Caddy es la opcion recomendada si no tienes preferencia previa porque obtiene y
renueva certificados TLS automaticamente.

Instalar Caddy en Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

Instalar la configuracion:

```bash
cd /opt/bot-neox
sudo cp deploy/caddy/Caddyfile.example /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

En `/etc/caddy/Caddyfile`, reemplaza `dashboard.tudominio.com` por tu dominio.
El bloque proxy incluido reenvia a `127.0.0.1:8000` y conserva headers utiles:

```caddyfile
reverse_proxy 127.0.0.1:8000 {
	header_up Host {host}
	header_up X-Forwarded-For {remote_host}
	header_up X-Forwarded-Proto {scheme}
}
```

### Alternativa: Nginx

Nginx tambien es valido si ya lo administras o necesitas integrarlo con una
configuracion existente. A diferencia de Caddy, los certificados TLS suelen
gestionarse aparte; usa Certbot para automatizar la emision y renovacion.

Instalar Nginx y Certbot en Debian/Ubuntu:

```bash
sudo apt update
sudo apt install -y nginx
sudo apt install -y certbot python3-certbot-nginx
```

Instalar la configuracion HTTP inicial:

```bash
cd /opt/bot-neox
sudo cp deploy/nginx/bot-neox-dashboard.conf.example /etc/nginx/sites-available/bot-neox-dashboard
sudo nano /etc/nginx/sites-available/bot-neox-dashboard
sudo ln -s /etc/nginx/sites-available/bot-neox-dashboard /etc/nginx/sites-enabled/bot-neox-dashboard
sudo nginx -t
sudo systemctl reload nginx
```

Emitir certificado y activar HTTPS con Certbot:

```bash
sudo certbot --nginx -d dashboard.tudominio.com
sudo systemctl reload nginx
```

En el archivo de Nginx, reemplaza `dashboard.tudominio.com` por tu dominio. El
proxy debe mantener estos headers:

```nginx
proxy_set_header Host $host;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

Si mantienes una configuracion HTTPS escrita manualmente en Nginx, usa la
variante comentada en `deploy/nginx/bot-neox-dashboard.conf.example` y deja
`X-Forwarded-Proto https`.

## Firewall Minimo De Produccion Con UFW

La VPS debe exponer solamente:

- `22/tcp` para SSH, o el puerto SSH real si lo cambiaste.
- `80/tcp` para HTTP y emision/renovacion de certificados.
- `443/tcp` para HTTPS.

No abras `8000/tcp`. Ese puerto es interno del dashboard y debe quedar accesible
solo desde la propia VPS mediante `127.0.0.1:8000`. Tampoco abras puertos
internos del bot, bases de datos, paneles de desarrollo o herramientas de
debug.

Importante: si tu SSH no usa el puerto `22`, cambia el comando de SSH antes de
activar UFW. Por ejemplo, si SSH usa `2222/tcp`, usa `sudo ufw allow 2222/tcp`
en lugar de `sudo ufw allow OpenSSH`. Verifica tu puerto actual antes de cerrar
la sesion activa:

```bash
sudo ss -ltnp | grep sshd
sudo grep -E '^\s*Port\s+' /etc/ssh/sshd_config
```

Configurar UFW de forma segura:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw status verbose
sudo ufw enable
sudo ufw status numbered
sudo ufw status verbose
```

El orden importa: permite SSH antes de ejecutar `sudo ufw enable` para no
bloquearte fuera de la VPS. Si administras la VPS por una consola del proveedor,
mantela abierta durante la primera activacion.

No ejecutes comandos como estos en produccion:

```bash
sudo ufw allow 8000/tcp
sudo ufw allow 0.0.0.0:8000
```

Si ya existia una regla que abre `8000/tcp`, revisala y eliminala manualmente
por numero despues de confirmar que es la regla correcta:

```bash
sudo ufw status numbered
sudo ufw delete NUMERO_DE_REGLA
sudo ufw status numbered
```

Este proyecto no aplica reglas de firewall desde Python. UFW debe configurarse
manualmente por el operador de la VPS o mediante el script opcional
`deploy/scripts/setup_firewall_ufw.sh`.

El dashboard debe seguir arrancando asi:

```bash
sudo -u botneox /opt/bot-neox/.venv/bin/python /opt/bot-neox/web_dashboard.py --host 127.0.0.1 --port 8000
```

Script opcional:

```bash
cd /opt/bot-neox
chmod +x deploy/scripts/setup_firewall_ufw.sh
sudo deploy/scripts/setup_firewall_ufw.sh
```

Si tu SSH usa un puerto distinto:

```bash
sudo env SSH_PORT=2222 deploy/scripts/setup_firewall_ufw.sh
```

## Como Probarlo

### Validar FFmpeg Y Musica

Verificar que FFmpeg esta instalado y disponible:

```bash
ffmpeg -version
command -v ffmpeg
```

Si `command -v ffmpeg` no devuelve una ruta y el modulo de musica debe estar
activo, instala FFmpeg:

```bash
sudo apt update && sudo apt install -y ffmpeg
```

Arrancar con musica activada usando `PATH`:

```env
MUSIC_ENABLED=true
FFMPEG_PATH=
```

Arrancar con musica activada usando una ruta explicita:

```env
MUSIC_ENABLED=true
FFMPEG_PATH=/usr/bin/ffmpeg
```

Luego reinicia el bot y revisa logs:

```bash
sudo systemctl restart bot-neox.service
journalctl -u bot-neox.service -n 100 --no-pager
```

Si FFmpeg existe, el cog de musica debe cargar y los comandos `/musica` deben
sincronizarse junto con el resto. Si falta FFmpeg con `MUSIC_ENABLED=true`, el
bot debe seguir arrancando, pero el log `bot.music` debe indicar que el modulo
de musica fue desactivado y sugerir instalar FFmpeg.

Arrancar con musica desactivada:

```env
MUSIC_ENABLED=false
```

Con `MUSIC_ENABLED=false`, el bot no carga `cogs.music`, no valida FFmpeg y no
debe fallar aunque FFmpeg no exista en la VPS. Los demas cogs deben arrancar
normalmente.

### Validar Usuario Y Permisos

Confirmar que el usuario existe, es de sistema y no tiene shell interactiva:

```bash
id botneox
getent passwd botneox
getent group botneox
```

El resultado de `getent passwd botneox` debe terminar con `/opt/bot-neox:/usr/sbin/nologin`
o una shell equivalente sin login como `/sbin/nologin`.

Verificar propietarios y modos del proyecto:

```bash
stat -c '%U:%G %a %n' /opt/bot-neox
stat -c '%U:%G %a %n' /opt/bot-neox/.env
stat -c '%U:%G %a %n' /opt/bot-neox/data
stat -c '%U:%G %a %n' /opt/bot-neox/data/ticket_media /opt/bot-neox/data/fine_proofs /opt/bot-neox/data/chest_table_images
stat -c '%U:%G %a %n' /var/backups/bot-neox
```

Valores esperados:

- `/opt/bot-neox`: `root:botneox 750`
- `/opt/bot-neox/.env`: `root:botneox 640`
- `/opt/bot-neox/data`: `botneox:botneox 750`
- subdirectorios de evidencias/uploads en `data/`: `botneox:botneox 750`
- `/var/backups/bot-neox`: `botneox:botneox 750`

Confirmar que no hay permisos `777` en rutas productivas del proyecto:

```bash
sudo find /opt/bot-neox -perm -0002 -ls
sudo find /var/backups/bot-neox -perm -0002 -ls
```

Los comandos no deben listar archivos ni directorios con escritura global.

Confirmar que `botneox` solo escribe donde corresponde:

```bash
sudo -u botneox test -r /opt/bot-neox/bot.py
sudo -u botneox test ! -w /opt/bot-neox/bot.py
sudo -u botneox test -w /opt/bot-neox/data
sudo -u botneox test -w /var/backups/bot-neox
sudo -u botneox sh -c 'touch /opt/bot-neox/data/.write-test && rm /opt/bot-neox/data/.write-test'
sudo -u botneox sh -c 'touch /var/backups/bot-neox/.write-test && rm /var/backups/bot-neox/.write-test'
```

Confirmar hardening de systemd:

```bash
systemctl cat bot-neox.service
systemctl cat bot-neox-dashboard.service
systemctl cat bot-neox-backup.service
```

Los archivos deben mostrar `User=botneox`, `Group=botneox`,
`ProtectSystem=strict`, `PYTHONDONTWRITEBYTECODE=1` y `ReadWritePaths` limitado
a `data/` para bot/dashboard, y a backups/log opcional para el backup.

Confirmar que los procesos no corren como root:

```bash
systemctl status bot-neox.service --no-pager
systemctl status bot-neox-dashboard.service --no-pager
ps aux | grep -E 'bot.py|web_dashboard.py' | grep -v grep
```

En `ps aux`, la primera columna de ambos procesos debe ser `botneox`, no `root`.

### Validar Secretos De Arranque

Probar fallo controlado sin un secreto critico. Este comando simula produccion
sin leer el `.env` completo:

```bash
cd /opt/bot-neox
env -i PATH="$PATH" APP_ENV=production TOKEN=test-token DASHBOARD_SESSION_SECRET=test-session-secret \
  /opt/bot-neox/.venv/bin/python - <<'PY'
from unittest.mock import patch

with patch("dotenv.load_dotenv", return_value=False):
    import src.neox.config.settings as settings
    settings.validate_dashboard_startup()
PY
```

Debe fallar con un `RuntimeError` que mencione variables faltantes como
`DASHBOARD_ADMIN_PASSWORD_HASH`, `DASHBOARD_ADMIN_PASSWORD_PEPPER` y
`DASHBOARD_ADMIN_DEVELOPER_IDS`, sin mostrar valores secretos.

Probar arranque con `.env` productivo valido:

```bash
cd /opt/bot-neox
sudo -u botneox bash -lc 'set -a; . /opt/bot-neox/.env; set +a; /opt/bot-neox/.venv/bin/python -c "from src.neox.config.settings import validate_dashboard_startup; validate_dashboard_startup(); print(\"config ok\")"'
```

El resultado esperado es `config ok`. Si falla, corrige las variables que indique
el error antes de iniciar systemd.

Verificar que systemd carga `/opt/bot-neox/.env`:

```bash
systemctl cat bot-neox.service
systemctl cat bot-neox-dashboard.service
```

Ambos deben mostrar `EnvironmentFile=/opt/bot-neox/.env`; el dashboard tambien
debe mostrar `APP_ENV=production` y `DASHBOARD_ENV=production`.

Verificar que no se imprimen secretos completos:

```bash
journalctl -u bot-neox.service -n 100 --no-pager
journalctl -u bot-neox-dashboard.service -n 100 --no-pager
```

Los logs pueden mostrar nombres de variables faltantes, pero no deben mostrar
`TOKEN`, `DASHBOARD_SESSION_SECRET`, hashes Argon2id completos ni peppers.

Verificar reglas UFW:

```bash
sudo ufw status numbered
sudo ufw status verbose
```

El resultado debe mostrar `22/tcp` o tu puerto SSH real, `80/tcp` y `443/tcp`.
No debe mostrar `8000/tcp` como permitido.

Comprobar puertos escuchando en la VPS:

```bash
sudo ss -ltnp
sudo ss -ltnp | grep -E ':(22|80|443|8000)\b'
```

El resultado esperado para el dashboard debe mostrar `127.0.0.1:8000` y, si
IPv6 esta habilitado, `[::1]:8000`. No debe aparecer `0.0.0.0:8000` ni
`[::]:8000`.

Comprobar que SSH, HTTP y HTTPS son los unicos puertos publicos esperados desde
tu maquina local:

```bash
nc -vz IP_PUBLICA_DE_LA_VPS 22
nc -vz IP_PUBLICA_DE_LA_VPS 80
nc -vz IP_PUBLICA_DE_LA_VPS 443
nc -vz -w 5 IP_PUBLICA_DE_LA_VPS 8000
```

El puerto `8000` debe fallar por timeout, rechazo de conexion o filtrado del
firewall.

Desde la VPS, confirma que el proceso escucha solo en loopback:

```bash
sudo ss -ltnp | grep ':8000'
```

El resultado esperado debe mostrar `127.0.0.1:8000` y, si IPv6 esta habilitado,
`[::1]:8000`. No debe aparecer `0.0.0.0:8000` ni `[::]:8000`.

Desde la VPS, el dashboard interno debe responder:

```bash
curl -I http://127.0.0.1:8000/dashboard
```

Desde tu maquina local, el puerto interno no debe responder usando la IP publica
de la VPS:

```bash
curl -I --connect-timeout 5 http://IP_PUBLICA_DE_LA_VPS:8000/dashboard
```

Ese comando debe fallar por timeout, rechazo de conexion o filtrado del
firewall. En cambio, el acceso publico esperado debe ser por el dominio:

```bash
curl -I https://dashboard.tudominio.com/dashboard
```

## Validaciones Recomendadas

Antes de iniciar en produccion:

```bash
cd /opt/bot-neox
sudo -u botneox env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -c "from pathlib import Path; [compile(path.read_text(encoding='utf-8'), str(path), 'exec') for path in (Path('bot.py'), Path('web_dashboard.py'), Path('scripts/backup_runtime.py'))]; print('syntax ok')"
sudo -u botneox env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v
sudo -u botneox env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/validate_local.py
```

Prueba manual de arranque sin systemd:

```bash
cd /opt/bot-neox
sudo -u botneox .venv/bin/python bot.py
sudo -u botneox .venv/bin/python web_dashboard.py --host 127.0.0.1 --port 8000
```

Deten esas pruebas manuales con `Ctrl+C` antes de iniciar los servicios.

## Notas Operativas

- No ejecutes el bot como `root`.
- No uses `bot_manager.py` como mecanismo principal de produccion.
- Guarda backups de `data/bot.sqlite3` y archivos runtime de `data/` antes de
  actualizar el proyecto.
- Si cambias dependencias, reinstala dentro del venv:

```bash
cd /opt/bot-neox
sudo chown -R botneox:botneox /opt/bot-neox/.venv
sudo -u botneox .venv/bin/pip install -r requirements.txt
sudo chown -R root:botneox /opt/bot-neox/.venv
sudo find /opt/bot-neox/.venv -type d -exec chmod 750 {} \;
sudo find /opt/bot-neox/.venv -type f -exec chmod 640 {} \;
sudo find /opt/bot-neox/.venv/bin -type f -exec chmod 750 {} \;
sudo systemctl restart bot-neox.service bot-neox-dashboard.service
```
