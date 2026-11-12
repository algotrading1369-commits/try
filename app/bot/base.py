import random
import time

import app.ogame.constants as c


class Module:
    name = "base"
    label = "Base"
    default_interval = 300
    default_enabled = False
    priority = 100

    def __init__(self, ctx):
        self.ctx = ctx

    @property
    def config(self):
        return self.ctx.config_for(self.name)

    def enabled(self):
        return bool(self.config.get("enabled", self.default_enabled))

    def interval(self):
        base = int(self.config.get("interval", self.default_interval))
        return max(15, base)

    def run(self):
        raise NotImplementedError


def planet_by_id(ctx, celestial_id):
    for planet in ctx.client.empire():
        if planet["id"] == celestial_id:
            return planet
    return None


def planets_only(ctx):
    return [p for p in ctx.client.empire() if p["type"] == "planet"]


def queue_busy(queue):
    return bool(queue)


def total_ships(ctx, celestial_id):
    ships = ctx.client.ships(celestial_id)
    return {tech: info["amount"] for tech, info in ships.items() if tech != "_queue"}


def human_pause(low=1.5, high=4.0):
    time.sleep(random.uniform(low, high))


def available_ships(ctx, celestial_id, wanted):
    have = total_ships(ctx, celestial_id)
    result = {}
    for ship_id, amount in wanted.items():
        take = min(amount, have.get(ship_id, 0))
        if take > 0:
            result[ship_id] = take
    return result


def cargo_capacity(ships):
    return sum(c.SHIPS[sid]["cargo"] * amount for sid, amount in ships.items())


def ships_for_cargo(needed, ship_ids=(202, 203)):
    result = {}
    for sid in ship_ids:
        cap = c.SHIPS[sid]["cargo"]
        if cap <= 0:
            continue
        count = int(-(-needed // cap))
        if count > 0:
            result[sid] = count
            needed = 0
    return result
