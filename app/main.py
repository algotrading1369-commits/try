import asyncio
import json
import os
import queue

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from .bot.engine import BotEngine, DEFAULT_CONFIG
from .db import Database
from .events import EventBus
from .notify import TelegramNotifier

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
PANEL_PASSWORD = os.environ.get("WEB_PASSWORD", "")

app = FastAPI(title="OGame Bot Web")
db = Database()
bus = EventBus()
engine = BotEngine(db, bus)
notifier = TelegramNotifier(db)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if PANEL_PASSWORD:
        path = request.url.path
        needs_auth = path.startswith("/api") or path == "/"
        sent = request.headers.get("X-Panel-Password") or request.query_params.get("key")
        if needs_auth and sent != PANEL_PASSWORD:
            if path.startswith("/api"):
                return JSONResponse(status_code=401, content={"detail": "Contraseña incorrecta"})
    return await call_next(request)


class AccountIn(BaseModel):
    universe: str
    language: str = "es"
    username: str
    password: str
    demo: bool = False


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
    return data


@app.post("/api/account")
def save_account(payload: AccountIn):
    if engine.state["running"]:
        engine.stop()
    db.save_account(payload.universe, payload.language, payload.username, payload.password, payload.demo)
    bus.publish("log", level="info", module="web", message="Cuenta guardada")
    return {"ok": True}


@app.get("/api/account")
def get_account():
    account = db.get_account()
    if account is None:
        return {"universe": "", "language": "es", "username": "", "demo": True}
    return {
        "universe": account["universe"],
        "language": account["language"],
        "username": account["username"],
        "demo": bool(account["demo"]),
    }


@app.post("/api/bot/start")
def bot_start():
    try:
        engine.start()
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
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
