from ..base import Module, planets_only, total_ships, human_pause
from ...ogame import constants as c


class ColonizeModule(Module):
    name = "colonize"
    label = "Auto-colonización"
    default_interval = 900
    default_enabled = False
    priority = 55

    def run(self):
        cfg = self.config
        coords_list = cfg.get("coords", [])
        if not coords_list:
            return "sin coordenadas configuradas"
        origin_id = int(cfg.get("origin_id", 0))
        planets = planets_only(self.ctx)
        if not planets:
            return "sin planetas"
        if not origin_id:
            origin_id = planets[0]["id"]

        slots = self.ctx.client.fleet_slots()
        if slots["fleet"]["used"] >= slots["fleet"]["total"]:
            return "sin huecos de flota"

        sent = self.ctx.db.get_setting("colonized", [])
        ships = total_ships(self.ctx, origin_id)
        colony_ships = ships.get(208, 0)
        probes = ships.get(210, 0)
        if colony_ships <= 0:
            return "sin naves colonizadoras"
        for coords in coords_list:
            key = f"{int(coords[0])}:{int(coords[1])}:{int(coords[2])}"
            if key in sent:
                continue
            destination = [int(coords[0]), int(coords[1]), int(coords[2]), c.DEST_PLANET]
            fleet = {208: 1}
            if probes > 0:
                fleet[210] = 1
            try:
                self.ctx.client.send_fleet(origin_id, c.MISSION_COLONIZE, destination, fleet)
            except Exception as exc:
                self.ctx.log("warning", f"Colonización a {key} falló: {exc}")
                return "colonización falló"
            sent.append(key)
            self.ctx.db.set_setting("colonized", sent)
            self.ctx.log("info", f"Nave colonizadora enviada a {key}")
            human_pause(2, 5)
            return f"colonizando {key}"
        return "todas las coordenadas colonizadas"
