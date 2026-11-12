import asyncio
import json
import os
import queue

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .bot.engine import BotEngine, DEFAULT_CONFIG
from .db import Database
from .events import EventBus

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

app = FastAPI(title="OGame Bot Web")
db = Database()
bus = EventBus()
engine = BotEngine(db, bus)


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
    from .bot.engine import MODULE_CLASSES

    data["module_catalog"] = [
        {"name": cls.name, "label": cls.label, "default_interval": cls.default_interval}
        for cls in MODULE_CLASSES
    ]
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
        return {"planets": [], "resources": {}}
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


@app.get("/api/events")
def events(since: float = 0):
    return {"events": bus.history(since)}


@app.get("/api/stream")
async def stream():
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
