import random

from ..base import Module, planets_only, queue_busy, human_pause
from ...ogame import constants as c
from ...ogame.client import OGameError


class ShipyardModule(Module):
    name = "shipyard"
    label = "Hangar y defensas"
    default_interval = 180
    default_enabled = True
    priority = 30

    def run(self):
        ship_quotas = self.config.get("ship_quotas", {"202": 200, "203": 50, "204": 500, "210": 150})
        defense_quotas = self.config.get("defense_quotas", {"401": 300, "402": 150})
        batch = int(self.config.get("batch_size", 25))
        results = []
        busy_lefts = []
        planets = planets_only(self.ctx)
        for planet in planets:
            cid = planet["id"]
            ships = self.ctx.client.ships(cid)
            ship_queue = ships.get("_queue", [])
            defs = self.ctx.client.defenses(cid)
            def_queue = defs.get("_queue", [])
            for q in (ship_queue, def_queue):
                left = q[0].get("time_left") if q and isinstance(q[0], dict) else None
                if isinstance(left, (int, float)) and left > 0:
                    busy_lefts.append(left)
            if not queue_busy(ship_queue):
                for ship_id, quota in ship_quotas.items():
                    ship_id = int(ship_id)
                    info = c.SHIPS.get(ship_id)
                    if info is None:
                        continue
                    current = ships.get(ship_id, {}).get("amount", 0)
                    missing = int(quota) - current
                    if missing <= 0:
                        continue
                    amount = min(missing, batch)
                    metal, crystal, deuterium = c.unit_cost(ship_id, amount)
                    res = self.ctx.client.resources(cid)
                    if res["metal"] >= metal and res["crystal"] >= crystal and res["deuterium"] >= deuterium:
                        try:
                            ok = self.ctx.client.build(ship_id, cid, amount)
                        except OGameError as exc:
                            self.ctx.log("warning", f"{planet['name']}: hangar rechazó temporalmente ({exc})")
                            break
                        if ok:
                            results.append(f"{planet['name']}: {amount}x {info['name']}")
                            human_pause(1, 2)
                            break
            if not queue_busy(def_queue):
                for def_id, quota in defense_quotas.items():
                    def_id = int(def_id)
                    info = c.DEFENSES.get(def_id)
                    if info is None:
                        continue
                    current = defs.get(def_id, {}).get("amount", 0)
                    missing = int(quota) - current
                    if missing <= 0:
                        continue
                    amount = min(missing, batch)
                    metal, crystal, deuterium = c.unit_cost(def_id, amount)
                    res = self.ctx.client.resources(cid)
                    if res["metal"] >= metal and res["crystal"] >= crystal and res["deuterium"] >= deuterium:
                        try:
                            ok = self.ctx.client.build(def_id, cid, amount)
                        except OGameError as exc:
                            self.ctx.log("warning", f"{planet['name']}: hangar rechazó temporalmente ({exc})")
                            break
                        if ok:
                            results.append(f"{planet['name']}: {amount}x {info['name']}")
                            human_pause(1, 2)
                            break
        if results:
            self.ctx.log("info", " | ".join(results))
        elif busy_lefts and len(busy_lefts) >= len(planets):
            wait = min(busy_lefts) + random.uniform(30, 90)
            self.next_delay = wait
            return f"colas de hangar ocupadas ({int(min(busy_lefts))}s restantes)"
        return f"{len(results)} pedidos de hangar"
