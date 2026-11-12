# OGame Bot — Panel de control web

Aplicación web autocontenida que opera una cuenta de OGame de forma autónoma y 24/7: gestiona edificios, investigación, hangar y defensas, escanea galaxias, espía y ataca inactivos, envía expediciones, coloniza, transporta recursos entre planetas y pone la flota a salvo cuando detecta un ataque — con notificaciones por Telegram.

Inspirado en proyectos como [ogame.ninja](https://www.ogame.ninja), [ogame-tbot/TBot](https://github.com/ogame-tbot/TBot), [r4fek/ogame-bot](https://github.com/r4fek/ogame-bot) y [alaingilbert/pyogame](https://github.com/alaingilbert/pyogame).

> ⚠️ **Aviso**: usar bots viola las reglas de OGame y puede suponer el baneo de la cuenta. Úsalo bajo tu responsabilidad, idealmente en universos de prueba. El **modo demo** incluye un universo simulado completo para probar todo sin cuenta real.

## Funciones

- **9 módulos autónomos** con planificador, intervalos configurables y jitter aleatorio:
  | Módulo | Función |
  |---|---|
  | Fleet-save | Detecta ataques (event box) y despacha flota + recursos en expedición o reciclaje |
  | Modo noche | No interactúa con la cuenta en las horas configuradas (solo vigila ataques) |
  | Edificios | Cola por planeta con orden de prioridad, niveles máximos y reservas |
  | Investigación | Cola única con orden de prioridad y niveles máximos |
  | Hangar y defensas | Cuotas de naves y defensas por planeta, construcción por lotes |
  | Farmer | Escaneo rotativo de galaxias → espionaje de inactivos → informes → ataques con cargas calculadas |
  | Expediciones | Envío periódico con plantilla de flota y tiempo de retención |
  | Auto-colonización | Envía naves colonizadoras a las coordenadas que indiques |
  | Transportes | Equilibra excedentes de recursos hacia el planeta principal |
- **Notificaciones Telegram**: ataques, fleet-save, errores y eventos importantes en tu móvil.
- **Panel web en tiempo real** (SSE): tarjetas de recursos totales, gráfico de evolución, switches de módulos, alertas, imperio con colas y almacenes, flotas en vuelo, objetivos, escaneo manual de sistemas, configuración editable y registros filtrables.
- **Modo demo**: universo simulado con 3 planetas, galaxia, espionaje, botín y ataques entrantes.
- **Login real** vía lobby de Gameforge (token Bearer, relogin automático, throttling aleatorio).
- **Protección por contraseña** del panel (variable `WEB_PASSWORD`).
- **Persistencia SQLite**: cuenta, configuración, logs, objetivos, historial de recursos y estadísticas.

## Arranque local

```bash
pip install -r requirements.txt
python run.py
```

Abre `http://127.0.0.1:8300` (variables `HOST` y `PORT` configurables).

## Despliegue online (24/7)

### Docker (VPS o NAS) — instalación con un comando

Estos comandos se ejecutan **en el servidor**, no en tu PC. Conéctate primero con SSH (la terminal de tu PC se convierte en una terminal *del servidor*):

```bash
ssh root@IP-DEL-SERVIDOR
```

Y dentro del servidor:

```bash
wget -qO install.sh https://raw.githubusercontent.com/algotrading1369-commits/try/main/install.sh
sudo bash install.sh
```

El script instala Docker si falta, clona el repo, te pregunta el dominio (opcional) y genera una contraseña aleatoria si no escribes una. Al terminar te muestra la URL de acceso.

**Con dominio propio (HTTPS gratis):** el script usa Caddy, que solicita y renueva el certificado de Let's Encrypt automáticamente. Solo necesitas:

1. Un dominio (Namecheap, Porkbun, o gratis en DuckDNS)
2. En el panel de tu dominio, crear un registro **A** apuntando a la IP del VPS
3. Abrir los puertos **80 y 443** en el firewall del VPS

Si lo prefieres a mano:

```bash
git clone https://github.com/algotrading1369-commits/try.git ogame-bot && cd ogame-bot
WEB_PASSWORD=tu-clave DOMAIN=bot.tudominio.com sudo docker compose --profile https up -d --build
```

Sin dominio, `install.sh` sirve el panel por HTTP en el puerto 8300.

La base de datos persiste en `./data` del servidor.

### Railway / Render / Fly.io

1. Conecta el repositorio a la plataforma.
2. La plataforma detecta el `Dockerfile` automáticamente.
3. Define la variable `WEB_PASSWORD` (obligatoria para que el panel no quede abierto).
4. Monta un volumen en `/data` si la plataforma lo permite (Railway/Render: disco persistente).

> **Nota**: Vercel/Netlify no sirven para esto — el bot necesita un proceso continuo, no funciones serverless. Válidos: cualquier VPS, Railway, Render, Fly.io, un Raspberry Pi en casa, o GitHub Codespaces para pruebas.

### Consejos de seguridad al exponerlo online

- Pon siempre `WEB_PASSWORD`. Una buena: 20+ caracteres aleatorios (`openssl rand -hex 16`).
- La API **bloquea 15 minutos** a las IPs que fallen 5 veces seguidas (anti fuerza bruta).
- Con dominio, todo va por **HTTPS** (Caddy + Let's Encrypt, gratis y automático) con cabeceras HSTS.
- La contraseña y las credenciales del juego se guardan en SQLite en el servidor: protege el acceso al VPS (usa claves SSH, no contraseñas).

## Telegram

1. Habla con [@BotFather](https://t.me/BotFather) → `/newbot` → copia el **token**
2. Habla con [@userinfobot](https://t.me/userinfobot) → copia tu **chat_id**
3. Pestaña **Cuenta → Notificaciones por Telegram** → pega token y chat_id → activa → **Guardar y probar**

Recibirás avisos de: ataques detectados, fleet-save ejecutado, errores del bot y ataques del farmer.

## Estructura

```
install.sh              Instalación automática en el VPS (Docker + HTTPS)
Caddyfile               Proxy con HTTPS automático (Let's Encrypt)
docker-compose.yml      Bot + Caddy (perfil https)
app/
├── main.py              API FastAPI (REST + SSE, auth con rate-limit) y panel estático
├── db.py                SQLite (cuenta, config, logs, objetivos, snapshots)
├── events.py            Bus de eventos para SSE
├── notify.py            Notificaciones Telegram
├── ogame/
│   ├── client.py        Cliente real: login lobby, parsing de páginas, acciones
│   ├── mock.py          Universo simulado (modo demo)
│   └── constants.py     IDs, costes, misiones y estadísticas de naves
├── bot/
│   ├── engine.py        Planificador, ciclo principal, snapshots, reconexión
│   ├── base.py          Clase Module y utilidades de flota/carga
│   └── modules/         buildings, research, shipyard, farmer, fleet, sleep, colonize
└── web/                 index.html + app.js + style.css
```

## Notas técnicas

- Endpoints del juego usados: `page=ingame`, `resourceSettings`, `supplies`/`facilities`/`research`/`shipyard`/`defenses`, `fleetdispatch` (token `fleetSendingToken`), `galaxyContent` (AJAX), `fetchEventBox` y `movement`.
- Si Gameforge exige captcha en el login (HTTP 409), el bot lo indica en el log; haz un login manual en el navegador y reintenta.
- El parser de informes de espionaje es *best-effort* (Gameforge cambia el HTML con frecuencia); los ataques usan el botín informado con factor de saqueo del 50 %.
- Las credenciales se guardan en claro en la base de datos: protege el servidor.
