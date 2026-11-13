from ..base import Module


class GalaxyMapperModule(Module):
    name = "mapper"
    label = "Mapeo galáctico"
    default_interval = 60
    default_enabled = False
    priority = 80

    def run(self):
        galaxies = [int(g) for g in self.config.get("galaxies", list(range(1, 10)))]
        if not galaxies:
            return "sin galaxias configuradas"
        system_start = int(self.config.get("system_start", 1))
        system_end = int(self.config.get("system_end", 499))
        per_run = max(1, int(self.config.get("systems_per_run", 3)))
        cursor = self.ctx.db.get_setting("mapper_cursor", {"g": galaxies[0], "s": system_start - 1})
        if cursor["g"] not in galaxies:
            cursor["g"] = galaxies[0]
        scanned = 0
        mapped = 0
        for _ in range(per_run):
            cursor["s"] += 1
            if cursor["s"] > system_end:
                cursor["s"] = system_start
                cursor["g"] = galaxies[(galaxies.index(cursor["g"]) + 1) % len(galaxies)]
            try:
                rows = self.ctx.client.galaxy(cursor["g"], cursor["s"])
            except Exception as exc:
                self.ctx.log("warning", f"Mapeo {cursor['g']}:{cursor['s']} falló: {exc}")
                continue
            for row in rows:
                if row.get("empty") or not row.get("player"):
                    continue
                self.ctx.db.upsert_galaxy_row(cursor["g"], cursor["s"], row)
                mapped += 1
            scanned += 1
        self.ctx.db.set_setting("mapper_cursor", cursor)
        return f"escaneados {scanned} sistemas → {cursor['g']}:{cursor['s']} ({mapped} posiciones)"


class HuntModule(Module):
    name = "hunt"
    label = "Caza"
    default_interval = 300
    default_enabled = False
    priority = 60

    def run(self):
        hunted = self.ctx.db.hunted_list()
        if not hunted:
            return "sin jugadores apuntados"
        rescan = max(1, int(self.config.get("rescan_per_run", 5)))
        positions = self.ctx.db.hunted_positions(rescan)
        if not positions:
            return "sin posiciones conocidas: activa el mapeo galáctico o escanea sus sistemas"
        systems = sorted({(pos["galaxy"], pos["system"]) for pos in positions})
        checked = 0
        active_seen = []
        for galaxy, system in systems:
            try:
                rows = self.ctx.client.galaxy(galaxy, system)
            except Exception as exc:
                self.ctx.log("warning", f"Caza: {galaxy}:{system} falló: {exc}")
                continue
            for row in rows:
                if row.get("empty") or not row.get("player"):
                    continue
                self.ctx.db.upsert_galaxy_row(galaxy, system, row)
                if row["player"] in hunted:
                    self.ctx.db.log_activity(
                        row["player"], row.get("player_id"), galaxy, system, row["position"], row.get("activity")
                    )
                    checked += 1
                    if row.get("activity"):
                        active_seen.append(f"{row['player']} en {galaxy}:{system}:{row['position']}")
        if active_seen:
            self.ctx.log("info", "🎯 Actividad detectada: " + " | ".join(active_seen[:3]))
        return f"{len(hunted)} cazados · {checked} planetas revisados en {len(systems)} sistemas"
