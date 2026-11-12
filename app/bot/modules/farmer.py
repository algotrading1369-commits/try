import time

from ..base import (
    Module,
    planets_only,
    total_ships,
    ships_for_cargo,
    human_pause,
)
from ...ogame import constants as c

LOOT_FACTOR = 0.5


class FarmerModule(Module):
    name = "farmer"
    label = "Farmer (ataques a inactivos)"
    default_interval = 240
    default_enabled = False
    priority = 40

    def __init__(self, ctx):
        super().__init__(ctx)
        self.scan_cursor = 0

    def run(self):
        cfg = self.config
        origin_id = int(cfg.get("origin_id", 0))
        planets = planets_only(self.ctx)
        if not planets:
            return "sin planetas"
        if not origin_id:
            origin_id = planets[0]["id"]
        galaxy_range = cfg.get("galaxies", [4])
        system_range = cfg.get("systems", [19, 40])
        max_rank = int(cfg.get("max_rank", 400))
        min_loot = int(cfg.get("min_loot", 50_000))
        max_probes = int(cfg.get("probes", 5))
        escorts = cfg.get("escorts", {"204": 30})
        cooldown = int(cfg.get("attack_cooldown", 3600))

        slots = self.ctx.client.fleet_slots()
        if slots["fleet"]["used"] >= slots["fleet"]["total"]:
            return "sin huecos de flota"

        self._collect_reports()

        targets = self.ctx.db.targets(only_inactive=True)
        now = time.time()

        fresh = [t for t in targets if t["last_spied"] and now - t["last_spied"] < 7200]
        pending_spy = [t for t in targets if not t["last_spied"] or now - t["last_spied"] > 14400]

        ready = [
            t for t in fresh
            if t["metal"] + t["crystal"] + t["deuterium"] >= min_loot
            and now - (t["last_attack"] or 0) > cooldown
        ]
        if ready:
            best = max(ready, key=lambda t: t["metal"] + t["crystal"] + t["deuterium"])
            return self._attack(best, origin_id, escorts)

        if pending_spy and slots["fleet"]["used"] < slots["fleet"]["total"]:
            sent = 0
            for target in pending_spy[:3]:
                if slots["fleet"]["used"] >= slots["fleet"]["total"]:
                    break
                probes = min(max_probes, total_ships(self.ctx, origin_id).get(210, 0))
                if probes <= 0:
                    return "sin sondas"
                dest = [target["galaxy"], target["system"], target["position"], c.DEST_PLANET]
                self.ctx.client.send_fleet(origin_id, c.MISSION_SPY, dest, {210: probes})
                self.ctx.db.upsert_target(
                    (target["galaxy"], target["system"], target["position"]),
                    last_spied=now,
                )
                self.ctx.log("info", f"Sonda enviada a [{target['galaxy']}:{target['system']}:{target['position']}]")
                sent += 1
                human_pause(2, 5)
            if sent:
                return f"{sent} espionajes enviados"

        return self._scan(galaxy_range, system_range, max_rank, origin_id)

    def _collect_reports(self):
        try:
            reports = self.ctx.client.spy_reports()
        except Exception as exc:
            self.ctx.log("warning", f"No se pudieron leer informes de espionaje: {exc}")
            return
        now = time.time()
        for report in reports:
            coords = tuple(report["coords"])
            total = report["metal"] + report["crystal"] + report["deuterium"]
            self.ctx.db.upsert_target(
                coords,
                metal=report["metal"],
                crystal=report["crystal"],
                deuterium=report["deuterium"],
                last_spied=now,
            )
            if total > 0:
                self.ctx.log(
                    "info",
                    f"Informe de espionaje [{coords[0]}:{coords[1]}:{coords[2]}]: "
                    f"botín {total:,}".replace(",", "."),
                )

    def _scan(self, galaxy_range, system_range, max_rank, origin_id):
        galaxies = [int(g) for g in galaxy_range]
        lo, hi = int(system_range[0]), int(system_range[1])
        g = galaxies[self.scan_cursor % len(galaxies)]
        system = lo + (self.scan_cursor // len(galaxies)) % (hi - lo + 1)
        self.scan_cursor += 1
        rows = self.ctx.client.galaxy(g, system)
        found = 0
        for row in rows:
            if row.get("empty") or not row.get("player_id"):
                continue
            inactive = "inactive" in row.get("status", [])
            rank = row.get("rank") or 0
            self.ctx.db.upsert_target(
                (g, system, row["position"]),
                player=row.get("player"),
                player_id=row.get("player_id"),
                inactive=1 if inactive else 0,
            )
            if inactive and (not rank or rank <= max_rank):
                found += 1
        self.ctx.log("info", f"Escaneada galaxia {g}:{system} — {found} inactivos nuevos")
        return f"escaneo {g}:{system} ({found} inactivos)"

    def _attack(self, target, origin_id, escorts):
        loot = (target["metal"] + target["crystal"] + target["deuterium"]) * LOOT_FACTOR
        ships = ships_for_cargo(int(loot))
        for ship_id, amount in (escorts or {}).items():
            ships[int(ship_id)] = ships.get(int(ship_id), 0) + int(amount)
        dest = [target["galaxy"], target["system"], target["position"], c.DEST_PLANET]
        try:
            resp = self.ctx.client.send_fleet(origin_id, c.MISSION_ATTACK, dest, ships)
        except Exception as exc:
            self.ctx.log("warning", f"Ataque a [{target['galaxy']}:{target['system']}:{target['position']}] falló: {exc}")
            return "ataque falló"
        self.ctx.db.upsert_target(
            (target["galaxy"], target["system"], target["position"]),
            last_attack=time.time(),
        )
        self.ctx.db.execute(
            "UPDATE targets SET attacks = attacks + 1 WHERE galaxy=? AND system=? AND position=?",
            (target["galaxy"], target["system"], target["position"]),
        )
        self.ctx.log(
            "attack",
            f"Ataque lanzado a [{target['galaxy']}:{target['system']}:{target['position']}] "
            f"botín estimado {int(loot):,} con {sum(ships.values())} naves".replace(",", "."),
        )
        return f"ataque a {target['galaxy']}:{target['system']}:{target['position']}"
