import random
import time

from ..base import Module, total_ships
from ...ogame import constants as c


class ExpeditionModule(Module):
    name = "expedition"
    label = "Expediciones"
    default_interval = 600
    default_enabled = False
    priority = 50

    def run(self):
        cfg = self.config
        origin_id = int(cfg.get("origin_id", 0))
        planets = planets_only(self.ctx)
        if not planets:
            return "sin planetas"
        if not origin_id:
            origin_id = planets[0]["id"]
        fleet_template = cfg.get("fleet", {"204": 50, "202": 20, "210": 1, "219": 1})
        holding_time = int(cfg.get("holding_time", 1))
        coords = cfg.get("coords", [16, 16, 1])

        slots = self.ctx.client.fleet_slots()
        if slots["fleet"]["used"] >= slots["fleet"]["total"]:
            return "sin huecos de flota"
        if slots["expedition"]["used"] >= slots["expedition"]["total"]:
            return "sin huecos de expedición"

        available = total_ships(self.ctx, origin_id)
        ships = {}
        for ship_id, amount in fleet_template.items():
            take = min(int(amount), available.get(int(ship_id), 0))
            if take > 0:
                ships[int(ship_id)] = take
        if not ships:
            return "sin naves para expedición"
        if 210 not in ships and 219 not in ships:
            return "se necesita al menos una sonda o pathfinder"

        destination = [int(coords[0]), int(coords[1]), 16, c.DEST_PLANET]
        try:
            self.ctx.client.send_fleet(
                origin_id,
                c.MISSION_EXPEDITION,
                destination,
                ships,
                holding_time=holding_time,
            )
        except Exception as exc:
            self.ctx.log("warning", f"Expedición fallida: {exc}")
            return "expedición fallida"
        self.ctx.log("info", f"Expedición enviada a {destination[0]}:{destination[1]}:16 por {holding_time}h")
        return "expedición enviada"


class FleetSaveModule(Module):
    name = "fleetsave"
    label = "Fleet-save automático"
    default_interval = 60
    default_enabled = True
    priority = 1

    def __init__(self, ctx):
        super().__init__(ctx)
        self.last_save = 0

    def run(self):
        cfg = self.config
        cooldown = int(cfg.get("cooldown", 900))
        if time.time() - self.last_save < cooldown:
            return "en cooldown"
        box = self.ctx.client.event_box()
        if box["hostile"] <= 0:
            return "sin ataques"
        self.last_save = time.time()
        mode = cfg.get("mode", "expedition")
        origin_id = int(cfg.get("origin_id", 0))
        planets = planets_only(self.ctx)
        if not planets:
            return "sin planetas"
        if not origin_id:
            origin_id = planets[0]["id"]
        ships = total_ships(self.ctx, origin_id)
        ships = {sid: amount for sid, amount in ships.items() if sid not in (210,) and amount > 0}
        if not ships:
            return "sin flota que salvar"
        res = self.ctx.client.resources(origin_id)
        cargo = (
            int(res["metal"] * 0.9),
            int(res["crystal"] * 0.9),
            int(res["deuterium"] * 0.9),
        )
        try:
            if mode == "expedition":
                dest = [planets[0]["coords"][0], planets[0]["coords"][1], 16, c.DEST_PLANET]
                self.ctx.client.send_fleet(
                    origin_id, c.MISSION_EXPEDITION, dest, ships, cargo,
                    speed=10, holding_time=int(cfg.get("holding_time", 8)),
                )
            else:
                dest = [planets[0]["coords"][0], planets[0]["coords"][1], 15, c.DEST_DEBRIS]
                self.ctx.client.send_fleet(
                    origin_id, c.MISSION_RECYCLE, dest, ships, (0, 0, 0), speed=10
                )
        except Exception as exc:
            self.ctx.log("warning", f"Fleet-save falló: {exc}")
            return "fleet-save falló"
        self.ctx.log("alert", f"¡ATAQUE DETECTADO! Flota y recursos puestos a salvo desde {origin_id}")
        self.ctx.bus.publish("attack", message="Ataque detectado, flota salvada")
        return "flota salvada"


class TransportModule(Module):
    name = "transport"
    label = "Transportes entre planetas"
    default_interval = 900
    default_enabled = False
    priority = 60

    def run(self):
        cfg = self.config
        main_id = int(cfg.get("main_id", 0))
        threshold = int(cfg.get("threshold", 1_000_000))
        keep = int(cfg.get("keep", 100_000))
        include_moons = bool(cfg.get("include_moons", True))
        empire = self.ctx.client.empire()
        planets = [p for p in empire if p["type"] == "planet"]
        if not planets:
            return "sin planetas"
        if not main_id:
            main_id = planets[0]["id"]
        origins = list(planets)
        if include_moons:
            origins += [p for p in empire if p["type"] == "moon"]
        slots = self.ctx.client.fleet_slots()
        moved = []
        for planet in origins:
            if planet["id"] == main_id:
                continue
            if slots["fleet"]["used"] >= slots["fleet"]["total"]:
                break
            surplus = 0
            res = self.ctx.client.resources(planet["id"])
            for key in ("metal", "crystal", "deuterium"):
                if res[key] > threshold:
                    surplus += res[key] - keep
            if surplus <= 0:
                continue
            ships = total_ships(self.ctx, planet["id"])
            transport = {}
            for sid in (203, 202):
                cap = c.SHIPS[sid]["cargo"]
                count = min(ships.get(sid, 0), int(-(-surplus // cap)))
                if count > 0:
                    transport[sid] = count
                    surplus -= count * cap
                    if surplus <= 0:
                        break
            if not transport:
                continue
            capacity = sum(c.SHIPS[sid]["cargo"] * n for sid, n in transport.items())
            send = (int(res["metal"] * 0.9), int(res["crystal"] * 0.9), int(res["deuterium"] * 0.9))
            total = sum(send)
            if total > capacity:
                scale = capacity / total
                send = (int(send[0] * scale), int(send[1] * scale), int(send[2] * scale))
            try:
                self.ctx.client.send_fleet(
                    planet["id"], c.MISSION_TRANSPORT,
                    [planets[0]["coords"][0], planets[0]["coords"][1], planets[0]["coords"][2], c.DEST_PLANET],
                    transport, send,
                )
            except Exception as exc:
                self.ctx.log("warning", f"Transporte desde {planet['name']} falló: {exc}")
                continue
            moved.append(f"{planet['name']} → principal ({total:,})".replace(",", "."))
            random_pause = random.uniform(2, 5)
            time.sleep(random_pause)
        if moved:
            self.ctx.log("info", " | ".join(moved))
        return f"{len(moved)} transportes"
