# OGame Bot — Panel de control web

Aplicación web autocontenida que opera una cuenta de OGame de forma autónoma: gestiona edificios, investigación, hangar y defensas, escanea galaxias, espía y ataca inactivos, envía expediciones, transporta recursos entre planetas y pone la flota a salvo cuando detecta un ataque.

Inspirado en proyectos como [r4fek/ogame-bot](https://github.com/r4fek/ogame-bot), [alaingilbert/pyogame](https://github.com/alaingilbert/pyogame) y [ogame-tbot/TBot](https://github.com/ogame-tbot/TBot).

> ⚠️ **Aviso**: usar bots viola las reglas de OGame y puede suponer el baneo de la cuenta. Úsalo bajo tu responsabilidad, idealmente en universos de prueba. El **modo demo** incluye un universo simulado completo para probar todo sin cuenta real.

## Características

- **Login real** vía lobby de Gameforge (sesión con token Bearer, relogin automático si expira, throttling aleatorio entre peticiones).
- **Modo demo**: universo simulado con 3 planetas, producción, colas, galaxia, espionaje, ataques entrantes y botín, para probar el bot de extremo a extremo.
- **7 módulos autónomos** con planificador propio, intervalos configurables y jitter aleatorio:
  | Módulo | Función |
  |---|---|
  | Fleet-save | Detecta ataques (event box) y despacha flota + recursos en expedición o reciclaje |
  | Edificios | Cola por planeta con orden de prioridad, niveles máximos y reservas de recursos |
  | Investigación | Cola única con orden de prioridad y niveles máximos |
  | Hangar y defensas | Cuotas de naves y defensas por planeta, construcción por lotes |
  | Farmer | Escaneo rotativo de galaxias → espionaje de inactivos → informes → ataques con cargas calculadas |
  | Expediciones | Envío periódico con plantilla de flota y tiempo de retención |
  | Transportes | Equilibra excedentes de recursos hacia el planeta principal |
- **Panel web en tiempo real** (SSE): estado del bot, alertas de ataque, módulos con último resultado y próxima ejecución, imperio con recursos/almacenes/colas/naves, flotas en vuelo, tabla de objetivos, configuración editable y registros filtrables.
- **Persistencia SQLite**: cuenta, configuración, logs, objetivos de farming y ejecuciones de módulos.

## Instalación y arranque

```bash
pip install -r requirements.txt
python run.py
```

Abre `http://127.0.0.1:8300` (variables `HOST` y `PORT` configurables).

1. Pestaña **Cuenta**: introduce universo, comunidad, usuario y contraseña, o marca **Modo demo**.
2. Pulsa **Iniciar**.
3. Ajusta los módulos en **Configuración** (activar farmer, expediciones, transportes, cuotas, etc.).

## Estructura

```
app/
├── main.py              API FastAPI (REST + SSE) y panel estático
├── db.py                SQLite (cuenta, config, logs, objetivos)
├── events.py            Bus de eventos para SSE
├── ogame/
│   ├── client.py        Cliente real: login lobby, parsing de páginas, acciones
│   ├── mock.py          Universo simulado (modo demo)
│   └── constants.py     IDs, costes, misiones y estadísticas de naves
├── bot/
│   ├── engine.py        Planificador, ciclo principal, reconexión
│   ├── base.py          Clase Module y utilidades de flota/carga
│   └── modules/         buildings, research, shipyard, farmer, fleet (expedición/fleet-save/transporte)
└── web/                 index.html + app.js + style.css
```

## Notas técnicas

- El cliente real replica los endpoints del juego: `page=ingame`, `resourceSettings`, `supplies`/`facilities`/`research`/`shipyard`/`defenses`, `fleetdispatch` (token `fleetSendingToken`), `galaxyContent` (AJAX), `fetchEventBox` y `movement`.
- Si Gameforge exige captcha en el login (HTTP 409), el bot lo indica en el log; haz un login manual en el navegador y reintenta.
- El parser de informes de espionaje es *best-effort* (Gameforge cambia el HTML con frecuencia); los ataques usan el botín informado con factor de saqueo del 50 %.
- Las contraseñas se guardan en claro en `data/ogamebot.db`: protege ese archivo.
