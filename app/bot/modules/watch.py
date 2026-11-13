import time

from ..base import Module


class WatchModule(Module):
    name = "watch"
    label = "Vigilancia"
    default_interval = 60
    default_enabled = False
    priority = 40

    def run(self):
        cfg = self.config
        notes = []
        if cfg.get("alert_hunted", True):
            notes += self._watch_hunted(cfg)
        if cfg.get("alert_inactive_recovered", True):
            notes += self._watch_inactive()
        return " | ".join(notes) if notes else "sin novedades"

    def _watch_hunted(self, cfg):
        window = int(cfg.get("hunted_online_minutes", 15)) * 60
        cooldown = int(cfg.get("repeat_cooldown", 3600))
        now = time.time()
        alerted = self.ctx.db.get_setting("watch_alerted", {})
        alerts = []
        for entry in self.ctx.db.recent_activity(limit=60):
            activity = entry["activity"]
            if not entry["player"] or activity is None:
                continue
            if now - entry["ts"] > window:
                continue
            last = float(alerted.get(entry["player"], 0))
            if now - last < cooldown:
                continue
            alerted[entry["player"]] = now
            when = "ahora mismo"
            if str(activity).isdigit():
                when = f"hace {activity} min"
            self.ctx.log(
                "alert",
                f"👁️ Vigilancia: {entry['player']} activo en {entry['galaxy']}:{entry['system']}:{entry['position']} ({when})",
                module="watch",
            )
            alerts.append(entry["player"])
        if alerts:
            self.ctx.db.set_setting("watch_alerted", alerted)
        return alerts

    def _watch_inactive(self):
        rows = self.ctx.db.galaxy_rows(limit=10000)
        previous = self.ctx.db.get_setting("watch_inactive", {})
        current = {}
        alerts = []
        for row in rows:
            key = f"{row['galaxy']}:{row['system']}:{row['position']}"
            if row["inactive"]:
                current[key] = True
                continue
            if row["player"] and key in previous:
                self.ctx.log(
                    "alert",
                    f"👁️ Vigilancia: {row['player']} en {key} ya no está inactivo",
                    module="watch",
                )
                alerts.append(key)
        self.ctx.db.set_setting("watch_inactive", current)
        return alerts
