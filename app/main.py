import asyncio
import json
import logging
import os
import queue
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from .bot.engine import BotEngine, DEFAULT_CONFIG
from .db import Database
from .events import EventBus
from .notify import TelegramNotifier

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
PANEL_PASSWORD = os.environ.get("WEB_PASSWORD", "")

_auth_lock = threading.Lock()
_auth_fails = {}
MAX_AUTH_FAILS = 5
AUTH_BLOCK_SECONDS = 900


def _client_ip(request: Request):
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _auth_blocked(ip):
    with _auth_lock:
        fails = _auth_fails.get(ip)
        if not fails:
            return False
        count, last = fails
        if time.time() - last > AUTH_BLOCK_SECONDS:
            del _auth_fails[ip]
            return False
        return count >= MAX_AUTH_FAILS


def _register_auth_fail(ip):
    with _auth_lock:
        count, last = _auth_fails.get(ip, (0, 0))
        if time.time() - last > AUTH_BLOCK_SECONDS:
            count = 0
        _auth_fails[ip] = (count + 1, time.time())


def _auth_ok(request: Request):
    sent = request.headers.get("X-Panel-Password") or request.query_params.get("key")
    if sent == PANEL_PASSWORD:
        with _auth_lock:
            _auth_fails.pop(_client_ip(request), None)
        return True
    _register_auth_fail(_client_ip(request))
    return False

app = FastAPI(title="OGame Bot Web")
db = Database()
bus = EventBus()
engine = BotEngine(db, bus)
notifier = TelegramNotifier(db)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if PANEL_PASSWORD:
        path = request.url.path
        if (path.startswith("/api") or path == "/") and _auth_blocked(_client_ip(request)):
            return JSONResponse(status_code=429, content={"detail": "Demasiados intentos fallidos. Espera 15 minutos."})
        needs_auth = path.startswith("/api") or path == "/"
        if needs_auth and not _auth_ok(request):
            if path.startswith("/api"):
                return JSONResponse(status_code=401, content={"detail": "Contraseña incorrecta"})
    return await call_next(request)


class AccountIn(BaseModel):
    universe: str
    language: str = "es"
    username: str
    password: str = ""
    demo: bool = False
    session_token: str = ""
    game_cookies: str = ""


class ConfigIn(BaseModel):
    config: dict


class PauseIn(BaseModel):
    paused: bool


class NotifyIn(BaseModel):
    token: str = ""
    chat_id: str = ""
    enabled: bool = False


class BuildIn(BaseModel):
    planet_id: int
    tech_id: int
    amount: int = 1


class ScanIn(BaseModel):
    galaxy: int
    system: int


class FleetIn(BaseModel):
    origin_id: int
    mission: int
    galaxy: int
    system: int
    position: int
    dest_type: int = 1
    ships: dict
    metal: int = 0
    crystal: int = 0
    deuterium: int = 0
    speed: int = 10
    holding_time: int = 0


class HuntIn(BaseModel):
    player: str


@app.get("/api/universes")
def universes(language: str = "es"):
    import requests

    try:
        resp = requests.get(
            "https://lobby.ogame.gameforge.com/api/servers", timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        servers = resp.json()
    except Exception as exc:
        raise HTTPException(502, f"No se pudo consultar la lista de universos: {exc}")
    result = [
        {
            "number": s.get("number"),
            "name": s.get("name"),
            "language": s.get("language"),
        }
        for s in servers
        if s.get("name")
    ]
    result.sort(key=lambda s: (s["language"] != language, s["language"], str(s["name"])))
    return {"universes": result}


@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


@app.get("/static/{path}")
def static_files(path: str):
    full = os.path.join(WEB_DIR, "static", path)
    if not os.path.isfile(full):
        raise HTTPException(404)
    return FileResponse(full)


@app.get("/api/status")
def status():
    account = db.get_account()
    data = engine.snapshot()
    data["has_account"] = account is not None
    data["universe"] = account["universe"] if account else None
    data["auth_required"] = bool(PANEL_PASSWORD)
    from .bot.engine import MODULE_CLASSES

    data["module_catalog"] = [
        {"name": cls.name, "label": cls.label, "default_interval": cls.default_interval}
        for cls in MODULE_CLASSES
    ]
    data["stats"] = db.get_setting("stats", {})
    data["farmer_loot"] = db.get_setting("farmer_loot", 0)
    from .ogame import constants as c

    data["ships_catalog"] = [
        {"id": sid, "name": info["name"]} for sid, info in sorted(c.SHIPS.items())
    ]
    data["defenses_catalog"] = [
        {"id": did, "name": info["name"]} for did, info in sorted(c.DEFENSES.items())
    ]
    return data


@app.post("/api/account")
def save_account(payload: AccountIn):
    if engine.state["running"]:
        engine.stop()
    token = payload.session_token.strip().strip('"').strip("'")
    if token.lower().startswith("gf-token-production="):
        token = token.split("=", 1)[1].strip().strip('"').strip("'")
    game_cookies = payload.game_cookies.strip()
    saved_ua = ""
    if game_cookies.lower().startswith("cookie:"):
        game_cookies = game_cookies.split(":", 1)[1].strip()
    if game_cookies and not payload.demo:
        import requests as rq
        number = None
        try:
            servers = rq.get("https://lobby.ogame.gameforge.com/api/servers", timeout=20).json()
            for server in servers:
                if str(server.get("name", "")).lower() == payload.universe.lower() and server.get("language") == payload.language:
                    number = server["number"]
                    break
        except Exception:
            pass
        if number is None:
            raise HTTPException(400, f"No encontré el universo {payload.universe} ({payload.language}): revisa el nombre")
        game_url = f"https://s{number}-{payload.language}.ogame.gameforge.com/game/index.php?page=ingame"
        working_ua = None
        seen_status = None
        for ua in (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0",
        ):
            try:
                check = rq.get(game_url, headers={"Cookie": game_cookies, "User-Agent": ua}, timeout=20, allow_redirects=False)
            except rq.RequestException as exc:
                raise HTTPException(400, f"No pude conectar con el servidor del juego: {exc}")
            seen_status = check.status_code
            if check.status_code == 200 and "ogame-player-name" in check.text:
                working_ua = ua
                break
        if working_ua is None:
            detail = "el servidor te manda al lobby (sesión no válida o incompleta)" if seen_status in (301, 302, 303, 307) else f"el servidor respondió {seen_status}"
            raise HTTPException(400, f"La sesión de juego no es válida ({detail}). Copia TODAS las cookies del dominio del juego: F12 → Network → recarga la página del juego → clic en la primera petición (index.php) → en Request Headers copia el valor completo de 'Cookie:' y pégalo aquí")
        saved_ua = working_ua
    if token and not payload.demo:
        import requests as rq
        check = rq.get(
            "https://lobby.ogame.gameforge.com/api/users/me",
            headers={"Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        if check.status_code != 200:
            raise HTTPException(400, "La cookie no es válida o ha caducado: entra en lobby.ogame.gameforge.com, asegúrate de estar dentro, y cópiala de nuevo")
    db.save_account(payload.universe, payload.language, payload.username, payload.password, payload.demo, token, game_cookies, saved_ua)
    bus.publish("log", level="info", module="web", message="Cuenta guardada")
    return {"ok": True}


@app.get("/api/account")
def get_account():
    account = db.get_account()
    if account is None:
        return {"universe": "", "language": "es", "username": "", "demo": True}
    keys = account.keys()
    return {
        "universe": account["universe"],
        "language": account["language"],
        "username": account["username"],
        "demo": bool(account["demo"]),
        "session_token": account["session_token"] if "session_token" in keys else "",
        "game_cookies": account["game_cookies"] if "game_cookies" in keys else "",
        "user_agent": account["user_agent"] if "user_agent" in keys else "",
    }


@app.post("/api/bot/start")
def bot_start():
    try:
        engine.start()
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logging.getLogger("uvicorn.error").exception("Error al iniciar el bot")
        raise HTTPException(500, f"No se pudo iniciar: {exc}")
    return {"ok": True}


@app.post("/api/bot/stop")
def bot_stop():
    engine.stop()
    return {"ok": True}


@app.post("/api/bot/pause")
def bot_pause(payload: PauseIn):
    if not engine.state["running"]:
        raise HTTPException(400, "El bot no está en marcha")
    engine.pause(payload.paused)
    return {"ok": True}


@app.get("/api/config")
def get_config():
    engine.load_config()
    return engine.config


@app.put("/api/config")
def put_config(payload: ConfigIn):
    for module_name, data in payload.config.items():
        if module_name in DEFAULT_CONFIG:
            engine.set_module_config(module_name, data)
    return {"ok": True}


@app.get("/api/logs")
def logs(since: float = 0, limit: int = 300):
    return db.recent_logs(since, min(limit, 1000))


@app.get("/api/planets")
def planets():
    if engine.client is None:
        return {"planets": [], "resources": {}, "buildings": {}, "ships": {}, "research": {}}
    try:
        empire = engine.client.empire()
        resources = {p["id"]: engine.client.resources(p["id"]) for p in empire}
        buildings = {p["id"]: engine.client.buildings(p["id"]) for p in empire}
        ships = {p["id"]: engine.client.ships(p["id"]) for p in empire}
        research = engine.client.research(empire[0]["id"]) if empire else {}
    except Exception as exc:
        raise HTTPException(502, f"Error consultando el juego: {exc}")
    return {
        "planets": empire,
        "resources": resources,
        "buildings": buildings,
        "ships": ships,
        "research": research,
    }


@app.get("/api/fleets")
def fleets():
    if engine.client is None:
        return {"fleets": [], "slots": {}}
    try:
        return {
            "fleets": engine.client.fleets(),
            "slots": engine.client.fleet_slots(),
        }
    except Exception as exc:
        raise HTTPException(502, f"Error consultando flotas: {exc}")


@app.get("/api/targets")
def targets():
    return {"targets": db.targets(only_inactive=False)}


@app.get("/api/history")
def history(since: float = 0):
    return {"history": db.history(since)}


@app.get("/api/summary")
def summary():
    if engine.client is None:
        return {"totals": {"metal": 0, "crystal": 0, "deuterium": 0}, "planets": 0}
    try:
        empire = engine.client.empire()
        totals = {"metal": 0, "crystal": 0, "deuterium": 0}
        for p in empire:
            res = engine.client.resources(p["id"])
            for key in totals:
                totals[key] += res[key]
        return {"totals": totals, "planets": len(empire)}
    except Exception as exc:
        raise HTTPException(502, f"Error calculando resumen: {exc}")


@app.get("/api/notify")
def get_notify():
    cfg = notifier.config()
    return {"token": cfg.get("token", ""), "chat_id": cfg.get("chat_id", ""), "enabled": cfg.get("enabled", False)}


@app.post("/api/notify")
def set_notify(payload: NotifyIn):
    notifier.save_config(payload.token, payload.chat_id, payload.enabled)
    if payload.enabled:
        ok = notifier.send("✅ <b>OGame Bot</b> conectado. Te avisaré de ataques y eventos importantes.")
        if not ok:
            raise HTTPException(400, "No se pudo enviar el mensaje de prueba: revisa token y chat_id")
    return {"ok": True}


@app.post("/api/action/build")
def action_build(payload: BuildIn):
    if engine.client is None:
        raise HTTPException(400, "El bot no está iniciado")
    try:
        engine.client.build(payload.tech_id, payload.planet_id, payload.amount)
    except Exception as exc:
        raise HTTPException(502, f"No se pudo construir: {exc}")
    db.add_log("info", "manual", f"Construcción manual: tech {payload.tech_id} en {payload.planet_id}")
    return {"ok": True}


@app.post("/api/action/scan")
def action_scan(payload: ScanIn):
    if engine.client is None:
        raise HTTPException(400, "El bot no está iniciado")
    rows = engine.client.galaxy(payload.galaxy, payload.system)
    found = 0
    for row in rows:
        if row.get("empty") or not row.get("player_id"):
            continue
        inactive = "inactive" in row.get("status", [])
        db.upsert_target(
            (payload.galaxy, payload.system, row["position"]),
            player=row.get("player"),
            player_id=row.get("player_id"),
            inactive=1 if inactive else 0,
        )
        if inactive:
            found += 1
    bus.publish("log", level="info", module="manual", message=f"Escaneo manual {payload.galaxy}:{payload.system} — {found} inactivos")
    return {"ok": True, "found": found}


@app.get("/api/galaxy")
def galaxy_view(galaxy: int, system: int):
    if engine.client is None:
        raise HTTPException(400, "El bot no está iniciado")
    try:
        rows = engine.client.galaxy(galaxy, system)
    except Exception as exc:
        raise HTTPException(502, f"Error escaneando {galaxy}:{system}: {exc}")
    for row in rows:
        if row.get("empty") or not row.get("player"):
            continue
        db.upsert_galaxy_row(galaxy, system, row)
    return {
        "galaxy": galaxy,
        "system": system,
        "rows": [
            {
                "position": row.get("position"),
                "player": row.get("player"),
                "rank": row.get("rank"),
                "inactive": "inactive" in row.get("status", []),
                "moon": bool(row.get("moon")),
                "debris": bool(row.get("debris")),
                "activity": row.get("activity"),
            }
            for row in rows
            if not row.get("empty")
        ],
    }


@app.post("/api/action/fleet")
def action_fleet(payload: FleetIn):
    if engine.client is None:
        raise HTTPException(400, "El bot no está iniciado")
    allowed = {1, 2, 3, 4, 5, 6, 7, 8, 9, 15}
    if payload.mission not in allowed:
        raise HTTPException(400, "Misión no válida")
    ships = {}
    for sid, amount in payload.ships.items():
        try:
            count = int(amount)
        except (TypeError, ValueError):
            continue
        if count > 0:
            ships[int(sid)] = count
    if not ships:
        raise HTTPException(400, "Sin naves")
    destination = [payload.galaxy, payload.system, payload.position, payload.dest_type]
    try:
        result = engine.client.send_fleet(
            payload.origin_id,
            payload.mission,
            destination,
            ships,
            (payload.metal, payload.crystal, payload.deuterium),
            speed=max(1, min(10, payload.speed)),
            holding_time=max(0, payload.holding_time),
        )
    except Exception as exc:
        raise HTTPException(502, f"No se pudo enviar la flota: {exc}")
    if isinstance(result, dict) and not result.get("success", True):
        raise HTTPException(400, result.get("errorMessage", "Envío rechazado"))
    db.add_log(
        "info", "manual",
        f"Flota manual: misión {payload.mission} a {payload.galaxy}:{payload.system}:{payload.position}",
    )
    bus.publish("log", level="info", module="manual", message=f"Flota manual enviada a {payload.galaxy}:{payload.system}:{payload.position}")
    return {"ok": True}


@app.get("/api/map")
def map_rows(inactive: bool = False, search: str = "", limit: int = 500):
    return {
        "rows": db.galaxy_rows(inactive_only=inactive, search=search, limit=min(limit, 2000)),
        "stats": db.map_stats(),
    }


@app.get("/api/hunt")
def hunt_overview():
    return {"players": db.activity_summary(), "activity": db.recent_activity(100)}


@app.post("/api/hunt")
def hunt_add(payload: HuntIn):
    name = payload.player.strip()
    if not name:
        raise HTTPException(400, "Nick vacío")
    if not db.hunt_add(name):
        raise HTTPException(400, "Ya estás cazando a ese jugador")
    bus.publish("log", level="info", module="hunt", message=f"Ahora cazando a {name}")
    return {"ok": True}


@app.delete("/api/hunt/{player}")
def hunt_delete(player: str):
    db.hunt_remove(player)
    return {"ok": True}


@app.get("/api/events")
def events(since: float = 0):
    return {"events": bus.history(since)}


@app.get("/api/stream")
async def stream(request: Request):
    if PANEL_PASSWORD and request.headers.get("X-Panel-Password") != PANEL_PASSWORD and request.query_params.get("key") != PANEL_PASSWORD:
        raise HTTPException(401, "Contraseña incorrecta")
    q = bus.subscribe()

    async def generator():
        try:
            yield f"data: {json.dumps({'kind': 'hello', 'ts': 0})}\n\n"
            while True:
                try:
                    item = await asyncio.to_thread(q.get, True, 30)
                    yield f"data: {item}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(generator(), media_type="text/event-stream")
