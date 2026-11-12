from ..base import Module, planets_only, queue_busy
from ...ogame import constants as c


class BuildingsModule(Module):
    name = "buildings"
    label = "Edificios"
    default_interval = 120
    default_enabled = True
    priority = 10

    DEFAULT_ORDER = [1, 2, 3, 4, 22, 23, 24, 14, 21, 31, 15, 12, 36]

    def run(self):
        order = self.config.get("order", self.DEFAULT_ORDER)
        max_levels = self.config.get("max_levels", {})
        reserves = self.config.get("reserves", {"metal": 0, "crystal": 0, "deuterium": 0})
        built = []
        for planet in planets_only(self.ctx):
            cid = planet["id"]
            data = self.ctx.client.buildings(cid)
            if queue_busy(data.get("_queue", [])):
                continue
            res = self.ctx.client.resources(cid)
            for tech_id in order:
                tech_id = int(tech_id)
                info = c.BUILDINGS.get(tech_id)
                if info is None:
                    continue
                current = data.get(tech_id, {}).get("level", 0)
                cap = int(max_levels.get(info["name"], 0))
                if cap and current >= cap:
                    continue
                metal, crystal, deuterium = c.building_cost(tech_id, current + 1)
                if (
                    res["metal"] - reserves.get("metal", 0) < metal
                    or res["crystal"] - reserves.get("crystal", 0) < crystal
                    or res["deuterium"] - reserves.get("deuterium", 0) < deuterium
                ):
                    continue
                if self.ctx.client.build(tech_id, cid):
                    built.append(f"{planet['name']}: {info['name']} → {current + 1}")
                    break
        if built:
            self.ctx.log("info", " | ".join(built))
        return f"{len(built)} construcciones iniciadas"
