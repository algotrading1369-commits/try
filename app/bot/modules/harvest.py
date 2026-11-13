import time

from ..base import Module, available_ships
from ...ogame import constants as c


class HarvestModule(Module):
    name = "harvest"
    label = "Recolección de escombros"
    default_interval = 900
    default_enabled = False
    priority = 55

    def run(self):
        cfg = self.config
        origin_id = int(cfg.get("origin_id", 0))
        recyclers_max = int(cfg.get("recyclers_max", 50))
        cooldown = int(cfg.get("cooldown", 21600))
        max_targets = int(cfg.get("max_targets", 3))

        targets = self.ctx.db.debris_positions(40)
        if not targets:
            return "sin campos de escombros conocidos"
        now = time.time()
        harvested = self.ctx.db.get_setting("harvested", {})
        pending = []
        for row in targets:
            key = f"{row['galaxy']}:{row['system']}:{row['position']}"
            if now - float(harvested.get(key, 0)) >= cooldown:
                pending.append((key, row))
        if not pending:
            return "todos en cooldown"
        if not origin_id:
            planets = [p for p in self.ctx.client.empire() if p["type"] == "planet"]
            if not planets:
                return "sin planetas"
            origin_id = planets[0]["id"]

        slots = self.ctx.client.fleet_slots()
        if slots["fleet"]["used"] >= slots["fleet"]["total"]:
            return "sin huecos de flota"

        recyclers = available_ships(self.ctx, origin_id, {209: recyclers_max}).get(209, 0)
        if recyclers <= 0:
            return "sin recicladores disponibles"

        sent = []
        for key, row in pending:
            if recyclers <= 0 or len(sent) >= max_targets:
                break
            if slots["fleet"]["used"] + len(sent) >= slots["fleet"]["total"]:
                break
            dest = [row["galaxy"], row["system"], row["position"], c.DEST_DEBRIS]
            try:
                result = self.ctx.client.send_fleet(
                    origin_id, c.MISSION_RECYCLE, dest, {209: recyclers}, speed=10
                )
            except Exception as exc:
                self.ctx.log("warning", f"Recolección a {key} falló: {exc}", module="harvest")
                harvested[key] = now
                continue
            if isinstance(result, dict) and not result.get("success", True):
                harvested[key] = now
                continue
            harvested[key] = now
            sent.append(f"{key} ({recyclers} recicladores)")
            recyclers = 0
        if not sent:
            self.ctx.db.set_setting("harvested", harvested)
            return "sin envíos"
        self.ctx.db.set_setting("harvested", harvested)
        self.ctx.log("info", "♻️ Recolección enviada: " + " | ".join(sent), module="harvest")
        return f"{len(sent)} recolecciones"
