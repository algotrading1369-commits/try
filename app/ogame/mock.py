import random
import threading
import time

from . import constants as c


class MockFleet:
    def __init__(self, fleet_id, mission, origin, destination, ships, arrival, return_flight=False):
        self.id = fleet_id
        self.mission = mission
        self.origin = origin
        self.destination = destination
        self.ship_store = dict(ships)
        self.arrival = arrival
        self.return_flight = return_flight


class MockClient:
    def __init__(self, universe="demo", language="es", username="demo", password="demo", seed=None):
        self.universe = universe
        self.language = language
        self.username = username
        self.password = password
        self.lock = threading.RLock()
        self.player = "ComandanteDemo"
        self.player_id = 100001
        self.server_version = "11.16.27-demo"
        self.universe_speed = 6
        self.fleet_speed = 4
        self.index_php = "mock://game/index.php?"
        rnd = random.Random(seed)
        self._rnd = rnd
        self.planets = [
            {
                "id": 33616111,
                "name": "Colonia Prime",
                "coords": [4, 21, 6],
                "type": "planet",
            },
            {
                "id": 33616122,
                "name": "Nova Terminus",
                "coords": [4, 24, 9],
                "type": "planet",
            },
            {
                "id": 33616133,
                "name": "Kronos III",
                "coords": [4, 27, 3],
                "type": "planet",
            },
        ]
        self.levels = {}
        for planet in self.planets:
            base = rnd.randint(28, 40)
            self.levels[planet["id"]] = {
                1: base,
                2: base - rnd.randint(1, 4),
                3: base - rnd.randint(3, 8),
                4: base - rnd.randint(2, 6),
                22: 8,
                23: 8,
                24: 6,
                14: 10,
                21: 10,
                31: 8,
                15: 2,
            }
        self.research_levels = {
            106: 10, 108: 12, 109: 12, 110: 11, 111: 12, 113: 11,
            115: 12, 117: 7, 120: 12, 121: 5, 122: 6, 124: 6,
        }
        self.res_store = {
            planet["id"]: {
                "metal": rnd.randint(80_000, 900_000),
                "crystal": rnd.randint(60_000, 500_000),
                "deuterium": rnd.randint(20_000, 200_000),
                "darkmatter": rnd.randint(2_000, 40_000),
                "energy": rnd.randint(-500, 2_000),
                "storage": [2_000_000, 2_000_000, 1_500_000],
            }
            for planet in self.planets
        }
        self.ship_store = {
            self.planets[0]["id"]: {202: 120, 203: 60, 204: 800, 206: 90, 207: 40, 210: 200, 209: 20},
            self.planets[1]["id"]: {202: 70, 204: 300, 210: 90, 206: 25},
            self.planets[2]["id"]: {202: 40, 204: 150, 210: 60},
        }
        self.defense_store = {
            planet["id"]: {401: 200, 402: 100, 403: 30, 404: 10, 407: 1}
            for planet in self.planets
        }
        self.queues = {planet["id"]: [] for planet in self.planets}
        self.research_queue = []
        self.fleet_list = []
        self._fleet_seq = 1
        self.galaxy_cache = {}
        self.spy_report_store = []
        self.attack_alert_until = 0
        self.attack_tick = rnd.randint(60, 120)

    def _now(self):
        return time.time()

    def _galaxy_key(self, g, s):
        return f"{g}:{s}"

    def login(self):
        pass

    def logout(self):
        pass

    def relogin(self):
        pass

    def is_logged_in(self):
        return True

    def server_info(self):
        return {"name": "Universo Demo", "speed": self.universe_speed, "version": self.server_version}

    def empire(self):
        with self.lock:
            return [dict(p) for p in self.planets]

    def resources(self, celestial_id):
        with self.lock:
            data = self.res_store.get(celestial_id, {"metal": 0, "crystal": 0, "deuterium": 0, "darkmatter": 0, "energy": 0, "storage": [0, 0, 0]})
            return dict(data)

    def _tick_queues(self):
        now = self._now()
        for cid, queue in self.queues.items():
            while queue and queue[0]["end"] <= now:
                item = queue.pop(0)
                tech = item["tech"]
                if tech in c.BUILDINGS:
                    self.levels.setdefault(cid, {})
                    self.levels[cid][tech] = self.levels[cid].get(tech, 0) + item.get("amount", 1)
                elif tech in c.SHIPS:
                    ships = self.ship_store.setdefault(cid, {})
                    ships[tech] = ships.get(tech, 0) + item.get("amount", 1)
                elif tech in c.DEFENSES:
                    defs_ = self.defense_store.setdefault(cid, {})
                    defs_[tech] = defs_.get(tech, 0) + item.get("amount", 1)
        while self.research_queue and self.research_queue[0]["end"] <= now:
            item = self.research_queue.pop(0)
            self.research_levels[item["tech"]] = self.research_levels.get(item["tech"], 0) + 1

    def _produce(self):
        for planet in self.planets:
            cid = planet["id"]
            levels = self.levels[cid]
            res = self.res_store[cid]
            mult = self.universe_speed
            metal_rate = 30 * levels.get(1, 0) * 1.1 ** levels.get(1, 0) * mult / 3600
            crystal_rate = 20 * levels.get(2, 0) * 1.1 ** levels.get(2, 0) * mult / 3600
            deut_rate = 10 * levels.get(3, 0) * 1.1 ** levels.get(3, 0) * mult / 3600
            res["metal"] = min(res["metal"] + metal_rate, res["storage"][0])
            res["crystal"] = min(res["crystal"] + crystal_rate, res["storage"][1])
            res["deuterium"] = min(res["deuterium"] + deut_rate, res["storage"][2])

    def _maybe_attack(self):
        self.attack_tick -= 1
        if self.attack_tick <= 0:
            self.attack_tick = self._rnd.randint(90, 200)
            self.attack_alert_until = self._now() + self._rnd.randint(120, 240)

    def build(self, tech_id, celestial_id, amount=1):
        with self.lock:
            self._tick_queues()
            queue = self.queues.setdefault(celestial_id, [])
            if queue:
                return False
            res = self.res_store[celestial_id]
            if tech_id in c.BUILDINGS:
                level = self.levels[celestial_id].get(tech_id, 0) + 1
                metal, crystal, deuterium = c.building_cost(tech_id, level)
                duration = max(30, int((metal + crystal) / 1000 / self.universe_speed) * 12)
            elif tech_id in c.SHIPS or tech_id in c.DEFENSES:
                metal, crystal, deuterium = c.unit_cost(tech_id, amount)
                duration = max(20, int((metal + crystal) / 2000 / self.universe_speed) * 10)
            else:
                return False
            if res["metal"] < metal or res["crystal"] < crystal or res["deuterium"] < deuterium:
                return False
            res["metal"] -= metal
            res["crystal"] -= crystal
            res["deuterium"] -= deuterium
            queue.append({"tech": tech_id, "amount": amount, "end": self._now() + duration})
            return True

    def research(self, celestial_id=None):
        with self.lock:
            return {**{k: {"id": k, "name": v["name"], "level": self.research_levels.get(k, 0), "status": "on"} for k, v in c.RESEARCHES.items()}, "_queue": list(self.research_queue)}

    def start_research(self, tech_id, celestial_id):
        with self.lock:
            if self.research_queue:
                return False
            level = self.research_levels.get(tech_id, 0) + 1
            metal, crystal, deuterium = c.building_cost(tech_id, level)
            res = self.res_store[celestial_id]
            if res["metal"] < metal or res["crystal"] < crystal or res["deuterium"] < deuterium:
                return False
            res["metal"] -= metal
            res["crystal"] -= crystal
            res["deuterium"] -= deuterium
            duration = max(60, int((metal + crystal) / 1500 / self.universe_speed) * 20)
            self.research_queue.append({"tech": tech_id, "end": self._now() + duration})
            return True

    def buildings(self, celestial_id):
        with self.lock:
            self._tick_queues()
            data = {}
            for tech_id, info in c.BUILDINGS.items():
                level = self.levels.get(celestial_id, {}).get(tech_id, 0)
                data[tech_id] = {"id": tech_id, "name": info["name"], "level": level, "status": "on"}
            data["_queue"] = [
                {"tech": q["tech"], "time_left": max(0, int(q["end"] - self._now()))} for q in self.queues.get(celestial_id, [])
            ]
            return data

    def ships(self, celestial_id):
        with self.lock:
            self._tick_queues()
            data = {}
            for tech_id, info in c.SHIPS.items():
                amount = self.ship_store.get(celestial_id, {}).get(tech_id, 0)
                data[tech_id] = {"id": tech_id, "name": info["name"], "amount": amount, "status": "on"}
            data["_queue"] = [
                {"tech": q["tech"], "time_left": max(0, int(q["end"] - self._now()))} for q in self.queues.get(celestial_id, [])
            ]
            return data

    def defenses(self, celestial_id):
        with self.lock:
            self._tick_queues()
            data = {}
            for tech_id, info in c.DEFENSES.items():
                amount = self.defense_store.get(celestial_id, {}).get(tech_id, 0)
                data[tech_id] = {"id": tech_id, "name": info["name"], "amount": amount, "status": "on"}
            data["_queue"] = []
            return data

    def event_box(self):
        with self.lock:
            self._tick_queues()
            self._produce()
            self._maybe_attack()
            hostile = 1 if self._now() < self.attack_alert_until else 0
            friendly = len([f for f in self.fleet_list if not f.return_flight])
            return {"hostile": hostile, "neutral": 0, "friendly": friendly}

    def fleet_slots(self):
        with self.lock:
            self._tick_queues()
            active = len([f for f in self.fleet_list if not f.return_flight])
            return {
                "fleet": {"used": active, "total": 9},
                "expedition": {"used": 0, "total": 3},
            }

    def fleets(self):
        with self.lock:
            self._tick_queues()
            now = self._now()
            for fleet in list(self.fleet_list):
                if fleet.arrival <= now and not fleet.return_flight:
                    if fleet.mission == c.MISSION_TRANSPORT:
                        dest_id = self._celestial_by_coords(fleet.destination)
                        if dest_id:
                            res = self.res_store[dest_id]
                            res["metal"] += fleet.cargo.get("metal", 0)
                            res["crystal"] += fleet.cargo.get("crystal", 0)
                            res["deuterium"] += fleet.cargo.get("deuterium", 0)
                    fleet.return_flight = True
                    fleet.arrival = now + random.randint(60, 180)
                elif fleet.return_flight and fleet.arrival <= now:
                    self.fleet_list.remove(fleet)
            return [
                {
                    "id": f.id,
                    "mission": f.mission,
                    "return_flight": f.return_flight,
                    "arrival": int(f.arrival),
                    "origin": f.origin,
                    "destination": f.destination,
                    "ships": dict(f.ship_store),
                    "cargo": dict(getattr(f, "cargo", {})),
                }
                for f in self.fleet_list
            ]

    def _celestial_by_coords(self, coords):
        for planet in self.planets:
            if planet["coords"] == list(coords[:3]):
                return planet["id"]
        return None

    def galaxy(self, galaxy, system):
        with self.lock:
            key = self._galaxy_key(galaxy, system)
            if key not in self.galaxy_cache:
                rnd = random.Random(f"{key}-seed")
                rows = []
                for position in range(1, 16):
                    roll = rnd.random()
                    if roll < 0.25:
                        rows.append({"position": position, "empty": True})
                        continue
                    inactive = roll < 0.5
                    player_id = rnd.randint(100000, 999999)
                    rows.append(
                        {
                            "position": position,
                            "empty": False,
                            "name": f"Planeta {galaxy}:{system}:{position}",
                            "player": f"{('Inactivo_' if inactive else 'Jugador_')}{player_id % 1000:03d}",
                            "player_id": player_id,
                            "rank": rnd.randint(1, 1500),
                            "moon": rnd.random() < 0.2,
                            "debris": rnd.random() < 0.3,
                            "status": ["inactive"] if inactive else [],
                        }
                    )
                self.galaxy_cache[key] = rows
            return [dict(r) for r in self.galaxy_cache[key]]

    def send_fleet(self, origin_id, mission, destination, ships, resources=(0, 0, 0), speed=10, holding_time=0):
        with self.lock:
            self._tick_queues()
            available = self.ship_store.get(origin_id, {})
            for ship_id, amount in ships.items():
                if available.get(ship_id, 0) < amount:
                    return {"success": False, "errorMessage": "Sin naves suficientes"}
            total_fuel = sum(c.SHIPS[sid]["fuel"] * amount for sid, amount in ships.items())
            if self.res_store[origin_id]["deuterium"] < total_fuel:
                return {"success": False, "errorMessage": "Deuterio insuficiente"}
            self.res_store[origin_id]["deuterium"] -= total_fuel
            for ship_id, amount in ships.items():
                available[ship_id] -= amount
            distance = sum((a - b) ** 2 for a, b in zip(self._coords_of(origin_id), destination[:3])) or 1
            duration = max(30, int(distance * 30 / speed / self.fleet_speed))
            if mission == c.MISSION_SPY:
                self._generate_spy_report(list(destination[:3]))
            fleet = MockFleet(
                self._fleet_seq,
                mission,
                self._coords_of(origin_id),
                list(destination[:3]),
                ships,
                self._now() + duration,
            )
            fleet.cargo = {"metal": resources[0], "crystal": resources[1], "deuterium": resources[2]}
            self._fleet_seq += 1
            if mission == c.MISSION_ATTACK and self._rnd.random() < 0.65:
                loot = {
                    "metal": self._rnd.randint(10_000, 400_000),
                    "crystal": self._rnd.randint(5_000, 200_000),
                    "deuterium": self._rnd.randint(0, 60_000),
                }
                fleet.cargo = loot
            self.fleet_list.append(fleet)
            return {"success": True, "fleetId": fleet.id, "arrival": int(fleet.arrival)}

    def _coords_of(self, celestial_id):
        for planet in self.planets:
            if planet["id"] == celestial_id:
                return planet["coords"]
        return [1, 1, 1]

    def return_fleet(self, fleet_id):
        with self.lock:
            for fleet in self.fleet_list:
                if fleet.id == fleet_id and not fleet.return_flight:
                    fleet.return_flight = True
                    fleet.arrival = self._now() + random.randint(30, 120)
                    return True
            return False

    def _generate_spy_report(self, coords):
        self.spy_report_store = [r for r in self.spy_report_store if r["coords"] != coords]
        self.spy_report_store.insert(
            0,
            {
                "coords": coords,
                "metal": self._rnd.randint(20_000, 900_000),
                "crystal": self._rnd.randint(10_000, 500_000),
                "deuterium": self._rnd.randint(0, 120_000),
            },
        )
        self.spy_report_store = self.spy_report_store[:30]

    def spy_reports(self, max_pages=1):
        with self.lock:
            return list(self.spy_report_store)
