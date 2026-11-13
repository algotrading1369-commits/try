import random
import threading
import time
import traceback

from ..events import EventBus
from ..notify import TelegramNotifier
from .base import Module
from .modules.buildings import BuildingsModule
from .modules.research import ResearchModule
from .modules.shipyard import ShipyardModule
from .modules.farmer import FarmerModule
from .modules.fleet import ExpeditionModule, FleetSaveModule, TransportModule
from .modules.sleep import SleepModule
from .modules.colonize import ColonizeModule
from .modules.mapper import GalaxyMapperModule, HuntModule

MODULE_CLASSES = [
    FleetSaveModule,
    SleepModule,
    BuildingsModule,
    ResearchModule,
    ShipyardModule,
    FarmerModule,
    ExpeditionModule,
    ColonizeModule,
    TransportModule,
    GalaxyMapperModule,
    HuntModule,
]

DEFAULT_CONFIG = {
    "buildings": {
        "enabled": True,
        "interval": 120,
        "smart": True,
        "order": [1, 2, 3, 4, 22, 23, 24, 14, 21, 31, 15, 12, 36],
        "mine_balance": {"metal": 0, "crystal": -5, "deuterium": -3},
        "roi_ratio": [2.5, 1.5, 1],
        "max_levels": {"metal_mine": 45, "crystal_mine": 42, "deuterium_mine": 40},
        "reserves": {"metal": 0, "crystal": 0, "deuterium": 0},
    },
    "research": {
        "enabled": True,
        "interval": 300,
        "order": [108, 106, 115, 113, 109, 110, 111, 120, 124, 117, 122, 121, 118, 123],
        "max_levels": {},
    },
    "shipyard": {
        "enabled": True,
        "interval": 180,
        "ship_quotas": {"202": 200, "203": 50, "204": 500, "210": 150},
        "defense_quotas": {"401": 300, "402": 150},
        "batch_size": 25,
    },
    "farmer": {
        "enabled": False,
        "interval": 240,
        "origin_id": 0,
        "galaxies": [4],
        "systems": [19, 40],
        "max_rank": 400,
        "min_loot": 50000,
        "probes": 5,
        "escorts": {"204": 30},
        "attack_cooldown": 3600,
    },
    "expedition": {
        "enabled": False,
        "interval": 600,
        "origin_id": 0,
        "fleet": {"204": 50, "202": 20, "210": 1, "219": 1},
        "holding_time": 1,
        "coords": [16, 16, 1],
    },
    "fleetsave": {
        "enabled": True,
        "interval": 60,
        "mode": "expedition",
        "origin_id": 0,
        "holding_time": 8,
        "cooldown": 900,
    },
    "transport": {
        "enabled": False,
        "interval": 900,
        "main_id": 0,
        "threshold": 1000000,
        "keep": 100000,
    },
    "colonize": {
        "enabled": False,
        "interval": 900,
        "origin_id": 0,
        "auto": True,
        "galaxy": 1,
        "system_start": 1,
        "system_end": 50,
        "coords": [],
    },
    "sleep": {
        "enabled": False,
        "interval": 60,
        "start_hour": 1,
        "end_hour": 8,
    },
    "mapper": {
        "enabled": False,
        "interval": 60,
        "galaxies": [1, 2, 3, 4, 5, 6, 7, 8, 9],
        "system_start": 1,
        "system_end": 499,
        "systems_per_run": 3,
    },
    "hunt": {
        "enabled": False,
        "interval": 300,
        "rescan_per_run": 5,
    },
}


class BotContext:
    def __init__(self, client, db, bus, config, log_fn):
        self.client = client
        self.db = db
        self.bus = bus
        self.config = config
        self._log = log_fn

    def config_for(self, module_name):
        base = dict(DEFAULT_CONFIG.get(module_name, {}))
        base.update(self.config.get(module_name, {}))
        return base

    def log(self, level, message, module="bot"):
        self._log(level, module, message)


class BotEngine:
    def __init__(self, db, bus=None):
        self.db = db
        self.bus = bus or EventBus()
        self.notifier = TelegramNotifier(db)
        self.state_lock = threading.Lock()
        self.state = {
            "running": False,
            "paused": False,
            "started_at": None,
            "current": None,
            "last_results": {},
            "next_runs": {},
            "ticks": 0,
            "account": None,
            "demo": False,
        }
        self.config = {}
        self.client = None
        self.ctx = None
        self.modules = {}
        self._thread = None
        self._stop = threading.Event()

    def load_config(self):
        stored = self.db.get_setting("bot_config", {})
        merged = {k: dict(v) if isinstance(v, dict) else v for k, v in DEFAULT_CONFIG.items()}
        for key, value in (stored or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
        self.config = merged

    def save_config(self):
        self.db.set_setting("bot_config", self.config)

    def set_module_config(self, module_name, data):
        self.load_config()
        current = self.config.setdefault(module_name, {})
        current.update(data)
        self.save_config()
        self.bus.publish("config", module=module_name)

    def _log(self, level, module, message):
        self.db.add_log(level, module, message)
        self.bus.publish("log", level=level, module=module, message=message)
        if level in ("attack", "alert", "error"):
            icon = {"attack": "\u2694\ufe0f", "alert": "\ud83d\udea8", "error": "\u274c"}.get(level, "\u2139\ufe0f")
            self.notifier.send(f"{icon} <b>OGame Bot</b> [{module}]\n{message}")

    def start(self):
        with self.state_lock:
            if self.state["running"]:
                return
            account = self.db.get_account()
            if account is None:
                raise RuntimeError("No hay cuenta configurada")
            self.load_config()
            self.client = self._build_client(account)
            self.ctx = BotContext(self.client, self.db, self.bus, self.config, self._log)
            self.modules = {cls.name: cls(self.ctx) for cls in MODULE_CLASSES}
            self._stop.clear()
            self.state.update(
                {
                    "running": True,
                    "paused": False,
                    "started_at": time.time(),
                    "ticks": 0,
                    "account": {
                        "universe": account["universe"],
                        "language": account["language"],
                        "username": account["username"],
                        "demo": bool(account["demo"]),
                    },
                    "demo": bool(account["demo"]),
                }
            )
            now = time.time()
            self.next_runs = {
                name: now + random.uniform(2, 10) for name in self.modules
            }
            self._thread = threading.Thread(target=self._loop, daemon=True, name="ogame-bot-engine")
            self._thread.start()
        self.bus.publish("status", state="running")

    def _build_client(self, account):
        if account["demo"]:
            from ..ogame.mock import MockClient

            return MockClient(universe=account["universe"], language=account["language"])
        from ..ogame.client import OGameClient

        client = OGameClient(
            account["universe"],
            account["language"],
            account["username"],
            account["password"],
        )
        client.login()
        return client

    def stop(self):
        self._stop.set()
        with self.state_lock:
            self.state["running"] = False
            self.state["paused"] = False
            self.state["current"] = None
        self.bus.publish("status", state="stopped")

    def pause(self, paused):
        with self.state_lock:
            self.state["paused"] = bool(paused)
        self.bus.publish("status", state="paused" if paused else "running")

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                err = traceback.format_exc(limit=3)
                self._log("error", "engine", f"Error en ciclo: {err}")
                time.sleep(10)
            self._stop.wait(3)

    def _tick(self):
        if self.state.get("paused"):
            return
        with self.state_lock:
            self.state["ticks"] += 1
        try:
            box = self.ctx.client.event_box()
            with self.state_lock:
                self.state["event_box"] = box
        except Exception as exc:
            self._log("warning", "engine", f"No se pudo leer el cuadro de eventos: {exc}")
            self._handle_client_error()
            return
        now = time.time()
        if box["hostile"] > 0:
            fleetsave = self.modules.get("fleetsave")
            if fleetsave and fleetsave.enabled() and now - getattr(self, "_last_fs_attempt", 0) > 120:
                self._last_fs_attempt = now
                self._run_module(fleetsave)
        due = [
            (self.next_runs.get(name, 0), module.priority, name, module)
            for name, module in self.modules.items()
            if module.enabled() and self.next_runs.get(name, 0) <= now
        ]
        due.sort()
        sleeping = False
        sleep_module = self.modules.get("sleep")
        if sleep_module and sleep_module.enabled() and sleep_module.in_sleep_window():
            sleeping = True
        with self.state_lock:
            self.state["sleeping"] = sleeping
        for _, _, name, module in due[:1]:
            if sleeping and name != "fleetsave":
                continue
            self._run_module(module)
        self._maybe_snapshot(now)

    def _maybe_snapshot(self, now):
        last = getattr(self, "_last_snapshot", 0)
        if now - last < 600:
            return
        self._last_snapshot = now
        try:
            for planet in self.ctx.client.empire():
                res = self.ctx.client.resources(planet["id"])
                self.db.add_snapshot(
                    planet["id"], planet["name"],
                    res["metal"], res["crystal"], res["deuterium"],
                )
            self.db.prune_snapshots()
        except Exception as exc:
            self._log("warning", "engine", f"Snapshot fall\u00f3: {exc}")

    def _run_module(self, module):
        started = time.time()
        with self.state_lock:
            self.state["current"] = module.name
        try:
            detail = module.run()
            status = "ok"
        except Exception as exc:
            detail = str(exc)
            status = "error"
            self._log("error", module.name, f"Fallo: {exc}")
            self._handle_client_error()
        self.db.execute(
            "INSERT INTO module_runs (module, started, finished, status, detail) VALUES (?,?,?,?,?)",
            (module.name, started, time.time(), status, detail),
        )
        jitter = random.uniform(0.85, 1.25)
        self.next_runs[module.name] = time.time() + module.interval() * jitter
        with self.state_lock:
            self.state["last_results"][module.name] = {
                "status": status,
                "detail": detail,
                "ts": time.time(),
            }
            self.state["next_runs"] = {k: v for k, v in self.next_runs.items()}
            self.state["current"] = None
        self.bus.publish(
            "module",
            module=module.name,
            status=status,
            detail=detail,
        )

    def _handle_client_error(self):
        if self.state.get("demo"):
            return
        try:
            if self.client and not self.client.is_logged_in():
                self._log("warning", "engine", "Sesión expirada, relogueando")
                self.client.relogin()
        except Exception as exc:
            self._log("error", "engine", f"Relogin falló: {exc}")

    def snapshot(self):
        with self.state_lock:
            data = dict(self.state)
            data["next_runs"] = {k: v for k, v in self.state.get("next_runs", {}).items()}
        return data
