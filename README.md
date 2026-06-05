# EconomyBot

Bot de Discord para manejar balances de Items/Silver, rankings, exportacion en Excel, permisos por rol y anuncios de Avalonianas con botones de inscripcion.

## Instalacion

Requisitos recomendados:

```text
Python 3.11 o superior
```

Pasos:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Despues, crea tu archivo `.env` a partir de `.env.example` y completa los valores necesarios.

Para que Auditoria registre entradas al servidor, cambios de nombre y roles asignados/removidos a miembros, deja `ENABLE_MEMBER_INTENT=1` y activa `SERVER MEMBERS INTENT` en el Developer Portal de Discord, dentro de la aplicacion del bot.

## Ejecucion

Para iniciar el bot, ejecuta:

```bat
run.bat
```

Al abrir `run.bat`, se inicia una consola de control y el bot arranca automaticamente.

El dashboard local tambien se enciende automaticamente junto con el bot y se apaga cuando el bot se detiene desde esta consola.

Comandos disponibles dentro de la consola:

```text
start
stop
restart
reset
status
help
exit
```

- `start`: enciende el bot si esta apagado.
- `stop`: apaga el bot.
- `restart`: reinicia el bot.
- `reset`: hace lo mismo que `restart`.
- `status`: muestra si el bot esta encendido o apagado.
- `help`: muestra los comandos disponibles.
- `exit`: apaga el bot y cierra la consola.

La consola tambien muestra registros cuando se usan comandos slash, botones o modales del bot.

## Base De Datos

El bot usa SQLite para la economia en:

```text
data/bot.sqlite3
```

No necesitas instalar un servidor de base de datos. SQLite ya viene incluido con Python mediante el modulo `sqlite3`.

Instalacion recomendada en tu computadora:

```text
Python 3.11 o superior
DB Browser for SQLite (opcional, solo para ver la base con interfaz grafica)
```

Comandos utiles:

```bat
python scripts\migrate_economy_to_sqlite.py
python scripts\backup_database.py
```

- `migrate_economy_to_sqlite.py`: crea/verifica `data/bot.sqlite3` y migra `balances.json` y `operations.json` si la base esta vacia.
- `backup_database.py`: crea una copia segura de la base en `data/backups/sqlite`.

Los archivos JSON anteriores se conservan como respaldo inicial, pero la economia del bot lee y escribe en SQLite.

## Dashboard Local

Puedes ver los mismos datos de `/export` en una pagina local:

```bat
run.bat
```

Cuando el bot este encendido, abre:

```text
http://127.0.0.1:8000
```

Primero veras una pantalla simple para ingresar con Discord. Despues del login, el panel se abre en:

```text
http://127.0.0.1:8000/dashboard
```

Tambien puedes levantar solo el dashboard manualmente para revisar datos sin encender el bot:

```bat
run_dashboard.bat
```

O:

```bat
python web_dashboard.py --host 127.0.0.1 --port 8000
```

La pagina se actualiza automaticamente cada 3 segundos y muestra:

- Balances.
- Registro Balance.
- Registro Avas.
- Registro Informes.

El dashboard usa login de Discord. Para ver un servidor, tu usuario debe estar en ese servidor, tener permiso de administrador y el bot tambien debe estar dentro. Configura en `.env`:

```env
DASHBOARD_CLIENT_ID=ID_DE_TU_APLICACION
DASHBOARD_CLIENT_SECRET=CLIENT_SECRET_DE_TU_APLICACION
DASHBOARD_REDIRECT_URI=http://localhost:8000/oauth/callback
DASHBOARD_SESSION_SECRET=UNA_CLAVE_LARGA_RANDOM
```

En Discord Developer Portal agrega esa misma URL en **OAuth2 > Redirects**.

Si marcas `Recordar este dispositivo`, la sesion queda guardada hasta 30 dias en `data/dashboard_sessions.json`. `DASHBOARD_SESSION_SECRET` debe mantenerse igual para que esas sesiones sigan funcionando despues de reiniciar.

En `Balances`, la columna `Usuario` muestra solo el nombre guardado o recuperado del historial, `ID` muestra el ID de Discord y `Fecha` usa formato de Argentina: `dia/mes/año | hora`.

## Comandos De Balance

### `/balance member`

Muestra el balance de un usuario.

- `member`: usuario que quieres consultar. Si no se indica, muestra tu propio balance.

Muestra:

- Items.
- Silver.
- Total.
- Posicion en el ranking.

### `/top`

Muestra el ranking del servidor segun el total acumulado entre Items y Silver.

Incluye:

- Top de jugadores.
- Total de cada jugador.
- Pagina actual.
- Posicion del usuario que ejecuto el comando.

### `/add categoria member amount`

Agrega saldo a un usuario.

- `categoria`: `Items` o `Silver`.
- `member`: usuario afectado.
- `amount`: cantidad que se agregara.

Ejemplo:

```text
/add Items @Neox2008 100000
```

### `/remove categoria member amount`

Quita saldo a un usuario.

- `categoria`: `Items` o `Silver`.
- `member`: usuario afectado.
- `amount`: cantidad que se quitara.

Ejemplo:

```text
/remove Silver @Neox2008 50000
```

### `/export`

Genera un archivo Excel con la informacion del bot.

El Excel contiene cuatro hojas:

- `Balances`: usuario, ID, Items, Silver y Total.
- `Registro Balance`: historial de operaciones de `/add` y `/remove`.
- `Registro Avas`: interacciones de usuarios con los pings de Avalonianas.
- `Registro Informes`: informes aceptados o rechazados.

## Comandos De Avas / Ping

### `/ping plantilla`

Crea un anuncio de Avalonianas.

- `plantilla`: plantilla que se va a usar.

Ejemplo:

```text
/ping avalonianas
```

Tambien puedes elegir:

```text
/ping desde-cero
```

Esa opcion abre el mismo modal para crear el ping manualmente, pero no guarda ninguna plantilla.

Al elegir la plantilla, el bot abre un modal precargado con:

- Numero.
- Mensaje completo.
- Botones/roles.

El numero se escribe manualmente en el modal. El mensaje completo es el texto base que se publicara en Discord. Los botones/roles definidos en el modal se convierten automaticamente en botones sin emojis predeterminados. El primer rol queda reservado para el caller.

Si repites un rol varias veces, el bot muestra un solo boton para ese nombre y va llenando el siguiente cupo libre. Por ejemplo, `DPS`, `DPS`, `DPS` crea un solo boton `DPS` con tres cupos internos.

Si una linea del mensaje contiene el nombre de un boton, el bot agregara ahi la mencion del jugador cuando alguien tome ese cupo. Ejemplo:

```text
# Ava {numero}

/join {caller}

MainTank:
Heal:
DPS:

Cupos: {occupied}/{total}{status}
```

El bot publica un anuncio con:

- El texto revisado en el modal.
- Los roles definidos en el modal.
- Un boton automatico por cada nombre de rol disponible, excepto el rol del caller.
- Botones fijos de `Cancelar ping` y `Finalizar ping`.

Tambien crea automaticamente un hilo asociado al mensaje con el nombre:

```text
Titulo del ping
```

Ejemplo:

```text
Ava 29
```

### Plantillas De Ping

Las plantillas se guardan en:

```text
data/ping_templates.json
```

Cada servidor puede tener hasta 5 plantillas guardadas propias. Las plantillas base/globales no cuentan para ese limite.

Cada plantilla puede configurar:

- `name`: nombre visible en el autocompletado de `/ping`.
- `mention`: mencion del encabezado, por ejemplo `||@everyone||`.
- `join_command`: texto del join.
- `caller_slot`: rol que queda reservado para el caller.
- `roles`: botones/cupos que se mostraran debajo del mensaje.
- `content`: plantilla completa del mensaje.
- `loot_link`: enlace usado por `{loot_link}`.
- `report_enabled`: permite usar `Enviar informe` al finalizar.

Comandos de plantillas:

```text
/plantilla agregar clave nombre
/plantilla eliminar plantilla
/plantilla listar
/plantilla ayuda
```

- `/plantilla agregar`: abre un modal para crear una plantilla nueva.
- `/plantilla eliminar`: elimina una plantilla guardada del servidor. La plantilla base y `desde-cero` no se pueden eliminar.
- `/plantilla listar`: muestra las plantillas disponibles y cuantas guardadas tiene el servidor.
- `/plantilla ayuda`: muestra ejemplos de mensaje completo y botones.

Placeholders disponibles en `content`:

```text
{title}
{numero}
{template}
{mention}
{caller}
{join_command}
{slots}
{loot_link}
{occupied}
{total}
{status}
```

### `/ping-list`

Muestra todos los pings activos que puedes administrar en el servidor.

El bot responde de forma privada con:

- Numero de Ava.
- Cupos ocupados.
- Enlace directo al mensaje del ping.

Ejemplo de salida:

```text
Ava 18 - Cupos ocupados: 2/10 - Ver ping
Ava 21 - Cupos ocupados: 1/10 - Ver ping
```

Este comando es util cuando tienes varias Avas activas y necesitas recordar que numeros puedes administrar.

### Cupos Disponibles

Los cupos disponibles dependen de la plantilla usada. El primer rol de la lista queda reservado automaticamente para el caller.

Cuando un usuario toca un boton:

- Se anota en ese cupo.
- El boton desaparece.
- El anuncio se actualiza.
- La interaccion queda registrada.

Si un usuario ya esta anotado e intenta tocar otro boton, el bot le muestra la opcion para desanotarse.

Al desanotarse, el usuario debe indicar una justificacion.

### `/ping-add numero_ava member rol`

Permite al caller anotar manualmente a un usuario en una Ava especifica.

- `numero_ava`: numero de la Ava que se va a modificar.
- `member`: usuario que sera anotado.
- `rol`: cupo donde sera anotado.

Ejemplo:

```text
/ping-add 29 @Neox2008 Heal
```

Esto anota a `@Neox2008` como `Heal` en la Ava 29.

El campo `numero_ava` tiene autocompletado. Al escribir el comando, Discord muestra las Avas activas que puedes administrar como caller.

### `/ping-remove numero_ava member`

Permite al caller remover manualmente a un usuario de una Ava especifica.

- `numero_ava`: numero de la Ava que se va a modificar.
- `member`: usuario que sera removido.

Ejemplo:

```text
/ping-remove 29 @Neox2008
```

Si se libera un cupo, el boton de ese cupo vuelve a aparecer.

Si el caller intenta removerse a si mismo, el bot no lo permite directamente. Primero debe transferir el ping a otro caller.

El campo `numero_ava` tiene autocompletado. Al escribir el comando, Discord muestra las Avas activas que puedes administrar como caller.

### `/ping-transfer numero_ava member`

Transfiere el control de una Ava a otro caller.

- `numero_ava`: numero de la Ava que se va a transferir.
- `member`: nuevo caller.

Ejemplo:

```text
/ping-transfer 29 @NuevoCaller
```

Esto hace que:

- El nuevo usuario pase al rol reservado para el caller.
- El `/join` se actualice con el nombre limpio del nuevo caller.
- El nuevo caller pueda administrar esa Ava.
- El caller anterior deje de administrar esa Ava.

Si el nuevo caller ya estaba anotado en otro cupo, se mueve al rol reservado para el caller y su cupo anterior queda libre.

El campo `numero_ava` tiene autocompletado. Al escribir el comando, Discord muestra las Avas activas que puedes administrar como caller.

## Permisos

Los permisos se manejan por conjuntos.

Conjuntos disponibles:

```text
Balance
Ping
Global
```

- `Balance`: permite usar `/add`, `/remove` y `/export`.
- `Ping`: permite usar `/ping`.
- `Informes`: permite aceptar o rechazar informes de Avas.
- `Global`: permite usar todo lo protegido del bot.

Los comandos administrativos de una Ava, como `/ping-add`, `/ping-remove` y `/ping-transfer`, dependen de que el usuario sea el caller de esa Ava activa.

### `/add-permission rol permisos`

Da permisos a un rol.

- `rol`: rol de Discord que recibira permisos.
- `permisos`: `Balance`, `Ping` o `Global`.

Ejemplos:

```text
/add-permission @Staff Balance
/add-permission @Caller Ping
/add-permission @Revisor Informes
/add-permission @Admin Global
```

Solo administradores del servidor pueden usar este comando.

### `/remove-permission rol permisos`

Quita permisos a un rol.

- `rol`: rol al que se le quitaran permisos.
- `permisos`: `Balance`, `Ping` o `Global`.

Ejemplos:

```text
/remove-permission @Staff Balance
/remove-permission @Caller Ping
/remove-permission @Admin Global
```

Si se quita `Global`, se eliminan todos los permisos registrados para ese rol.

Solo administradores del servidor pueden usar este comando.

### `/permissions`

Muestra los permisos configurados por rol.

Ejemplo de salida:

```text
@Caller: Ping
@Staff: Balance
@Admin: Global
```

Solo administradores del servidor pueden usar este comando.

## Resumen Rapido

Balance:

```text
/balance member
/top
/add categoria member amount
/remove categoria member amount
/export
```

Avas:

```text
/ping plantilla
/plantilla agregar clave nombre
/plantilla eliminar plantilla
/ping-list
/ping-add numero_ava member rol
/ping-remove numero_ava member
/ping-transfer numero_ava member
```

Permisos:

```text
/add-permission rol permisos
/remove-permission rol permisos
/permissions
```

Configuracion:

```text
/config canal tipo canal
```

Tipos disponibles:

```text
Evaluacion Informes
Informes Aprobados
```

## Informes De Avas

Cuando una Ava se llena, aparecen dos botones publicos en el ping:

```text
Finalizar ping
Enviar informe
```

Solo el caller puede usar estos botones.

Primero se debe usar `Finalizar ping`. Despues de finalizar, se habilita `Enviar informe`.

Al enviar el informe, el caller completa:

- `Estimado`.
- `Silver`.
- `Items`.
- `Mapa/Repa opcional`, con formato recomendado: `mapa=1000000; repa=500000`.
- `PP/Multas opcional`, con formato recomendado: `Heal:PP; Cobra:-50%`.

El informe se envia al canal configurado como `Evaluacion Informes` y el bot crea un hilo llamado:

```text
Evaluacion Ava {numero}
```

Los revisores con permiso `Informes` pueden aceptar o rechazar el informe.

El informe en evaluacion muestra:

```text
Aceptar
Rechazar
```

- `Aceptar`: publica el informe en el canal configurado como `Informes Aprobados`.
- `Rechazar`: pide el motivo del rechazo.

Cuando el informe ya fue publicado en `Informes Aprobados`, el mensaje aprobado muestra:

```text
Agregar balance
No agregar balance
```

- `Agregar balance`: suma el balance automaticamente.
- `No agregar balance`: deja el informe aprobado sin modificar balances.

Si se rechaza, el bot pide el motivo del rechazo.

El `/export` agrega una hoja llamada `Registro Informes`, con:

```text
Ava N°
Caller
ID Caller
Revisado por
ID
Decision
Motivo
Fecha
Hora
```

Consola local:

```text
start
stop
restart
reset
status
help
exit
```
