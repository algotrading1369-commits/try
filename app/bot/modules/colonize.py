from ..base import Module, planets_only, total_ships
from ...ogame import constants as c

PREFERRED_POSITIONS = [7, 8, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15]


class ColonizeModule(Module):
    name = "colonize"
    label = "Auto-colonización"
    default_interval = 900
    default_enabled = False
    priority = 55

    def _find_auto_spot(self):
        galaxy = int(self.config.get("galaxy", 1))
        system_start = int(self.config.get("system_start", 1))
        system_end = int(self.config.get("system_end", 50))
        for system in range(system_start, system_end + 1):
            try:
                rows = self.ctx.client.galaxy(galaxy, system)
            except Exception:
                continue
            empty = {row["position"] for row in rows if row.get("empty")}
            if not empty:
                continue
            for position in PREFERRED_POSITIONS:
                if position in empty:
                    return (galaxy, system, position)
        return None

    def run(self):
        cfg = self.config
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

        targets = []
        if cfg.get("auto", True):
            spot = self._find_auto_spot()
            if spot:
                targets.append(spot)
        for coords in cfg.get("coords", []):
            targets.append((int(coords[0]), int(coords[1]), int(coords[2])))

        for coords in targets:
            key = f"{coords[0]}:{coords[1]}:{coords[2]}"
            if key in sent:
                continue
            destination = [coords[0], coords[1], coords[2], c.DEST_PLANET]
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
            return f"colonizando {key}"

        if cfg.get("auto", True) and not cfg.get("coords"):
            return "sin posiciones libres en el rango explorado"
        return "todas las coordenadas colonizadas"
