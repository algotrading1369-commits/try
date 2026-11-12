from ..base import Module


class SleepModule(Module):
    name = "sleep"
    label = "Modo noche"
    default_interval = 60
    default_enabled = False
    priority = 0

    def in_sleep_window(self):
        cfg = self.config
        if not cfg.get("enabled"):
            return False
        start = int(cfg.get("start_hour", 1))
        end = int(cfg.get("end_hour", 8))
        if start == end:
            return False
        hour = __import__("time").localtime().tm_hour
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end

    def run(self):
        return "durmiendo"
