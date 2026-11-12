from ..base import Module, planets_only, queue_busy, human_pause
from ...ogame import constants as c


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
        for planet in planets_only(self.ctx):
            cid = planet["id"]
            ships = self.ctx.client.ships(cid)
            if not queue_busy(ships.get("_queue", [])):
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
                        if self.ctx.client.build(ship_id, cid, amount):
                            results.append(f"{planet['name']}: {amount}x {info['name']}")
                            human_pause(1, 2)
                            break
            defs = self.ctx.client.defenses(cid)
            if not queue_busy(defs.get("_queue", [])):
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
                        if self.ctx.client.build(def_id, cid, amount):
                            results.append(f"{planet['name']}: {amount}x {info['name']}")
                            human_pause(1, 2)
                            break
        if results:
            self.ctx.log("info", " | ".join(results))
        return f"{len(results)} pedidos de hangar"
