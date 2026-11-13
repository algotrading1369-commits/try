import random

from ..base import Module, planets_only, queue_busy
from ...ogame import constants as c
from ...ogame.client import OGameError


class ManualQueueModule(Module):
    name = "manual"
    label = "Cola manual"
    default_interval = 30
    default_enabled = True
    priority = 5

    def _label(self, tech_id):
        for catalog in (c.BUILDINGS, c.RESEARCHES, c.SHIPS, c.DEFENSES):
            if tech_id in catalog:
                return catalog[tech_id]["name"]
        return None

    def _free_planet(self, planets, wanted, queue_fn):
        lefts = []
        for planet in planets:
            if wanted and planet["id"] != wanted:
                continue
            try:
                queue = queue_fn(planet["id"]).get("_queue", [])
            except OGameError:
                queue = ["busy"]
            if queue_busy(queue):
                left = queue[0].get("time_left") if isinstance(queue[0], dict) else None
                if isinstance(left, (int, float)) and left > 0:
                    lefts.append(left)
                continue
            return planet, None
        return None, (min(lefts) if lefts else None)

    def _attempt(self, tech_id, amount, wanted, planets):
        if tech_id in c.RESEARCHES:
            lab = planets[0]["id"]
            try:
                queue = self.ctx.client.research(lab).get("_queue", [])
            except OGameError as exc:
                return False, None, f"investigación: {exc}", None
            if queue_busy(queue):
                left = queue[0].get("time_left") if isinstance(queue[0], dict) else None
                left = left if isinstance(left, (int, float)) and left > 0 else None
                return False, None, "laboratorio ocupado", left
            try:
                ok = self.ctx.client.start_research(tech_id, lab)
            except OGameError as exc:
                return False, None, str(exc), None
            return bool(ok), planets[0]["name"], "recursos insuficientes", None
        if tech_id in c.SHIPS or tech_id in c.DEFENSES:
            queue_fn = self.ctx.client.ships
            kind = "hangar"
        else:
            queue_fn = self.ctx.client.buildings
            kind = "edificios"
        planet, busy_left = self._free_planet(planets, wanted, queue_fn)
        if planet is None:
            reason = f"cola de {kind} ocupada en todos los planetas"
            if busy_left:
                reason += f" ({int(busy_left)}s restantes)"
            return False, None, reason, busy_left
        try:
            ok = self.ctx.client.build(tech_id, planet["id"], amount)
        except OGameError as exc:
            return False, None, str(exc), None
        return bool(ok), planet["name"], "recursos insuficientes", None

    def run(self):
        queue = self.ctx.db.get_setting("manual_queue", [])
        if not queue:
            return "sin pedidos"
        planets = planets_only(self.ctx)
        if not planets:
            return "sin planetas"
        drop = set()
        built_index = None
        built_msg = None
        waiting = None
        busy_lefts = []
        other_block = False
        for idx, item in enumerate(queue):
            try:
                tech_id = int(item.get("tech_id", 0))
                amount = max(1, int(item.get("amount", 1) or 1))
                wanted = int(item.get("planet_id", 0) or 0)
            except (TypeError, ValueError):
                drop.add(idx)
                continue
            label = self._label(tech_id)
            if label is None:
                drop.add(idx)
                continue
            ok, where, reason, busy_left = self._attempt(tech_id, amount, wanted, planets)
            if ok:
                built_index = idx
                built_msg = f"{label} en {where}"
                break
            waiting = reason
            if busy_left:
                busy_lefts.append(busy_left)
            else:
                other_block = True
        if built_index is not None:
            drop.add(built_index)
        if drop:
            queue = [item for i, item in enumerate(queue) if i not in drop]
            self.ctx.db.set_setting("manual_queue", queue)
        if built_msg:
            self.ctx.log("info", f"Cola manual: {built_msg}")
            return f"pedido en marcha: {built_msg} | {len(queue)} pendientes"
        if busy_lefts and not other_block:
            self.next_delay = min(busy_lefts) + random.uniform(30, 90)
        if waiting:
            return f"esperando: {waiting}"
        return "sin pedidos válidos"
