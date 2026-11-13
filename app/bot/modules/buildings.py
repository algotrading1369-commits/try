import random

from ..base import Module, planets_only, queue_busy
from ...ogame import constants as c
from ...ogame.client import OGameError

MINE_IDS = [1, 2, 3]
RES_KEYS = {1: "metal", 2: "crystal", 3: "deuterium"}
STORE_FOR_MINE = {1: 22, 2: 23, 3: 24}
INFRA_ORDER = [14, 21, 31, 15, 36, 12]


class BuildingsModule(Module):
    name = "buildings"
    label = "Edificios"
    default_interval = 120
    default_enabled = True
    priority = 10

    DEFAULT_ORDER = [1, 2, 3, 4, 22, 23, 24, 14, 21, 31, 15, 12, 36]

    def _level(self, data, tech_id):
        return data.get(tech_id, {}).get("level", 0)

    def _below_cap(self, data, tech_id, max_levels):
        info = c.BUILDINGS.get(tech_id)
        if info is None:
            return False
        cap = int(max_levels.get(info["name"], 0))
        return not cap or self._level(data, tech_id) < cap

    def _affordable(self, tech_id, data, res, reserves):
        metal, crystal, deuterium = c.building_cost(tech_id, self._level(data, tech_id) + 1)
        return (
            res["metal"] - reserves.get("metal", 0) >= metal
            and res["crystal"] - reserves.get("crystal", 0) >= crystal
            and res["deuterium"] - reserves.get("deuterium", 0) >= deuterium
        )

    def _prod(self, mine_id, level):
        if level <= 0:
            return 0.0
        base = {1: 30.0, 2: 20.0, 3: 10.0}[mine_id]
        return base * level * 1.1 ** level

    def _roi_candidates(self, data, max_levels, ratio):
        weights = {
            1: 1.0,
            2: ratio[0] / ratio[1],
            3: ratio[0] / ratio[2],
        }
        scored = []
        for mine_id in MINE_IDS:
            if not self._below_cap(data, mine_id, max_levels):
                continue
            level = self._level(data, mine_id)
            gain = self._prod(mine_id, level + 1) - self._prod(mine_id, level)
            if gain <= 0:
                continue
            metal, crystal, deuterium = c.building_cost(mine_id, level + 1)
            cost_eq = metal + crystal * weights[2] + deuterium * weights[3]
            gain_eq = gain * weights[mine_id]
            if gain_eq <= 0:
                continue
            scored.append((cost_eq / gain_eq, mine_id))
        scored.sort()
        return [mine_id for _, mine_id in scored]

    def _candidates(self, data, res, max_levels, smart):
        if not smart:
            order = [int(t) for t in self.config.get("order", self.DEFAULT_ORDER)]
            return [t for t in order if self._below_cap(data, t, max_levels)]
        candidates = []
        if res.get("energy", 0) <= 0 and self._below_cap(data, 4, max_levels):
            candidates.append(4)
        storage = res.get("storage") or [0, 0, 0]
        for mine_id, store_id in STORE_FOR_MINE.items():
            idx = MINE_IDS.index(mine_id)
            cap = storage[idx] if idx < len(storage) else 0
            if cap > 0 and res[RES_KEYS[mine_id]] >= cap * 0.9 and self._below_cap(data, store_id, max_levels):
                candidates.append(store_id)
        roi_ratio = self.config.get("roi_ratio")
        if roi_ratio and len(roi_ratio) == 3:
            candidates.extend(self._roi_candidates(data, max_levels, [float(r) for r in roi_ratio]))
        else:
            balance = self.config.get("mine_balance", {"metal": 0, "crystal": -5, "deuterium": -3})
            metal_level = self._level(data, 1)

            def deficit(tech_id):
                offset = int(balance.get(RES_KEYS[tech_id], 0))
                return (metal_level + offset) - self._level(data, tech_id)

            mines = sorted(MINE_IDS, key=lambda t: -deficit(t))
            candidates.extend(t for t in mines if self._below_cap(data, t, max_levels))
        if self.config.get("facilities"):
            candidates.extend(t for t in INFRA_ORDER if self._below_cap(data, t, max_levels))
        seen = set()
        unique = []
        for t in candidates:
            if t not in seen:
                seen.add(t)
                unique.append(t)
        return unique

    def run(self):
        smart = self.config.get("smart", True)
        max_levels = self.config.get("max_levels", {})
        reserves = self.config.get("reserves", {"metal": 0, "crystal": 0, "deuterium": 0})
        built = []
        busy_lefts = []
        planets = planets_only(self.ctx)
        for planet in planets:
            cid = planet["id"]
            data = self.ctx.client.buildings(cid)
            queue = data.get("_queue", [])
            if queue_busy(queue):
                left = queue[0].get("time_left") if isinstance(queue[0], dict) else None
                if isinstance(left, (int, float)) and left > 0:
                    busy_lefts.append(left)
                continue
            res = self.ctx.client.resources(cid)
            for tech_id in self._candidates(data, res, max_levels, smart):
                if not self._affordable(tech_id, data, res, reserves):
                    continue
                current = self._level(data, tech_id)
                try:
                    ok = self.ctx.client.build(tech_id, cid)
                except OGameError as exc:
                    self.ctx.log("warning", f"{planet['name']}: construcción rechazada temporalmente ({exc})")
                    break
                if ok:
                    built.append(f"{planet['name']}: {c.BUILDINGS[tech_id]['name']} → {current + 1}")
                    break
        if built:
            self.ctx.log("info", " | ".join(built))
        elif busy_lefts and len(busy_lefts) == len(planets):
            wait = min(busy_lefts) + random.uniform(30, 90)
            self.next_delay = wait
            return f"colas ocupadas ({int(min(busy_lefts))}s restantes)"
        elif not built and smart:
            return "esperando recursos para minas (las instalaciones se construyen desde la cola manual)"
        return f"{len(built)} construcciones iniciadas"
