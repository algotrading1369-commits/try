from ..base import Module, planets_only, queue_busy
from ...ogame import constants as c


class ResearchModule(Module):
    name = "research"
    label = "Investigación"
    default_interval = 300
    default_enabled = True
    priority = 20

    DEFAULT_ORDER = [108, 106, 115, 113, 109, 110, 111, 120, 124, 117, 122, 121, 118, 123]

    def run(self):
        order = self.config.get("order", self.DEFAULT_ORDER)
        max_levels = self.config.get("max_levels", {})
        planets = planets_only(self.ctx)
        if not planets:
            return "sin planetas"
        lab_planet = planets[0]
        data = self.ctx.client.research(lab_planet["id"])
        if queue_busy(data.get("_queue", [])):
            return "cola ocupada"
        res = self.ctx.client.resources(lab_planet["id"])
        for tech_id in order:
            tech_id = int(tech_id)
            info = c.RESEARCHES.get(tech_id)
            if info is None:
                continue
            current = data.get(tech_id, {}).get("level", 0)
            cap = int(max_levels.get(info["name"], 0))
            if cap and current >= cap:
                continue
            metal, crystal, deuterium = c.building_cost(tech_id, current + 1)
            if res["metal"] < metal or res["crystal"] < crystal or res["deuterium"] < deuterium:
                continue
            if self.ctx.client.start_research(tech_id, lab_planet["id"]):
                self.ctx.log("info", f"Investigando {info['name']} → {current + 1}")
                return f"{info['name']} → {current + 1}"
        return "nada accesible"
