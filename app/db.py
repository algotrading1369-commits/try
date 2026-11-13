import json
import os
import sqlite3
import threading
import time

DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data"
)


class Database:
    def __init__(self, path=None):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.path = path or os.path.join(DATA_DIR, "ogamebot.db")
        self.lock = threading.Lock()
        self._init_schema()

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        with self.lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    universe TEXT NOT NULL,
                    language TEXT NOT NULL DEFAULT 'es',
                    username TEXT NOT NULL,
                    password TEXT NOT NULL,
                    demo INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS galaxy_map (
                    galaxy INTEGER NOT NULL,
                    system INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    player TEXT,
                    player_id INTEGER,
                    rank INTEGER,
                    inactive INTEGER NOT NULL DEFAULT 0,
                    moon INTEGER NOT NULL DEFAULT 0,
                    debris INTEGER NOT NULL DEFAULT 0,
                    activity TEXT,
                    seen_at REAL NOT NULL,
                    PRIMARY KEY (galaxy, system, position)
                );
                CREATE INDEX IF NOT EXISTS idx_galaxy_map_player ON galaxy_map(player);
                CREATE TABLE IF NOT EXISTS activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player TEXT NOT NULL,
                    player_id INTEGER,
                    galaxy INTEGER NOT NULL,
                    system INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    activity TEXT,
                    ts REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_activity_log_player ON activity_log(player, ts);
                CREATE TABLE IF NOT EXISTS hunted (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player TEXT UNIQUE NOT NULL
                );
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    level TEXT NOT NULL,
                    module TEXT NOT NULL,
                    message TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(ts);
                CREATE TABLE IF NOT EXISTS targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    galaxy INTEGER NOT NULL,
                    system INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    player TEXT,
                    player_id INTEGER,
                    inactive INTEGER NOT NULL DEFAULT 0,
                    metal INTEGER DEFAULT 0,
                    crystal INTEGER DEFAULT 0,
                    deuterium INTEGER DEFAULT 0,
                    defense_score INTEGER DEFAULT 0,
                    last_spied REAL,
                    last_attack REAL,
                    attacks INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(galaxy, system, position)
                );
                CREATE TABLE IF NOT EXISTS module_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    module TEXT NOT NULL,
                    started REAL NOT NULL,
                    finished REAL,
                    status TEXT,
                    detail TEXT
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    celestial_id INTEGER NOT NULL,
                    name TEXT,
                    metal REAL NOT NULL,
                    crystal REAL NOT NULL,
                    deuterium REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts);
                """
            )
            self._migrate_schema(conn)

    def execute(self, sql, params=()):
        with self.lock, self._connect() as conn:
            return conn.execute(sql, params)

    def query(self, sql, params=()):
        with self.lock, self._connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def get_account(self):
        rows = self.query("SELECT * FROM accounts WHERE active = 1 ORDER BY id LIMIT 1")
        return rows[0] if rows else None

    def save_account(self, universe, language, username, password, demo, session_token="", game_cookies=""):
        with self.lock, self._connect() as conn:
            conn.execute("UPDATE accounts SET active = 0")
            conn.execute(
                "INSERT INTO accounts (universe, language, username, password, demo, session_token, game_cookies, active, created_at) VALUES (?,?,?,?,?,?,?,1,?)",
                (universe, language, username, password, 1 if demo else 0, session_token or "", game_cookies or "", time.time()),
            )

    def _migrate_schema(self, conn):
        cols = {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
        if "session_token" not in cols:
            conn.execute("ALTER TABLE accounts ADD COLUMN session_token TEXT NOT NULL DEFAULT ''")
        if "game_cookies" not in cols:
            conn.execute("ALTER TABLE accounts ADD COLUMN game_cookies TEXT NOT NULL DEFAULT ''")

    def get_setting(self, key, default=None):
        rows = self.query("SELECT value FROM settings WHERE key = ?", (key,))
        if not rows:
            return default
        return json.loads(rows[0]["value"])

    def set_setting(self, key, value):
        self.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )

    def add_log(self, level, module, message):
        self.execute(
            "INSERT INTO logs (ts, level, module, message) VALUES (?,?,?,?)",
            (time.time(), level, module, message),
        )

    def recent_logs(self, since=0, limit=300):
        return self.query(
            "SELECT * FROM logs WHERE ts > ? ORDER BY ts DESC LIMIT ?",
            (since, limit),
        )

    def upsert_target(self, coords, **fields):
        with self.lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO targets (galaxy, system, position) VALUES (?,?,?)
                ON CONFLICT(galaxy, system, position) DO NOTHING
                """,
                coords,
            )
            assignments = ", ".join(f"{key} = ?" for key in fields)
            values = list(fields.values()) + list(coords)
            if assignments:
                conn.execute(f"UPDATE targets SET {assignments} WHERE galaxy = ? AND system = ? AND position = ?", values)

    def add_snapshot(self, celestial_id, name, metal, crystal, deuterium):
        self.execute(
            "INSERT INTO snapshots (ts, celestial_id, name, metal, crystal, deuterium) VALUES (?,?,?,?,?,?)",
            (time.time(), celestial_id, name, metal, crystal, deuterium),
        )

    def history(self, since=0):
        return self.query(
            "SELECT * FROM snapshots WHERE ts > ? ORDER BY ts ASC LIMIT 5000",
            (since,),
        )

    def prune_snapshots(self, keep_seconds=7 * 86400):
        self.execute("DELETE FROM snapshots WHERE ts < ?", (time.time() - keep_seconds,))

    def bump_stat(self, key, amount=1):
        stats = self.get_setting("stats", {})
        stats[key] = stats.get(key, 0) + amount
        self.set_setting("stats", stats)
        return stats

    def targets(self, only_inactive=True):
        sql = "SELECT * FROM targets"
        if only_inactive:
            sql += " WHERE inactive = 1"
        sql += " ORDER BY metal + crystal + deuterium DESC LIMIT 500"
        return self.query(sql)

    def upsert_galaxy_row(self, galaxy, system, row):
        self.execute(
            """
            INSERT INTO galaxy_map (galaxy, system, position, player, player_id, rank, inactive, moon, debris, activity, seen_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(galaxy, system, position) DO UPDATE SET
                player = excluded.player, player_id = excluded.player_id, rank = excluded.rank,
                inactive = excluded.inactive, moon = excluded.moon, debris = excluded.debris,
                activity = excluded.activity, seen_at = excluded.seen_at
            """,
            (
                galaxy,
                system,
                row.get("position", 0),
                row.get("player"),
                row.get("player_id"),
                row.get("rank"),
                1 if "inactive" in row.get("status", []) else 0,
                1 if row.get("moon") else 0,
                1 if row.get("debris") else 0,
                str(row["activity"]) if row.get("activity") is not None else None,
                time.time(),
            ),
        )

    def map_stats(self):
        return {
            "positions": self.query("SELECT COUNT(*) AS n FROM galaxy_map")[0]["n"],
            "inactive": self.query("SELECT COUNT(*) AS n FROM galaxy_map WHERE inactive = 1")[0]["n"],
            "systems": self.query("SELECT COUNT(DISTINCT galaxy || ':' || system) AS n FROM galaxy_map")[0]["n"],
            "players": self.query("SELECT COUNT(DISTINCT player_id) AS n FROM galaxy_map WHERE player_id IS NOT NULL")[0]["n"],
            "hunted": self.query("SELECT COUNT(*) AS n FROM hunted")[0]["n"],
        }

    def galaxy_rows(self, inactive_only=False, search="", limit=500):
        sql = "SELECT * FROM galaxy_map"
        conditions = []
        params = []
        if inactive_only:
            conditions.append("inactive = 1")
        if search:
            conditions.append("player LIKE ?")
            params.append(f"%{search}%")
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY galaxy, system, position LIMIT ?"
        params.append(limit)
        return self.query(sql, params)

    def debris_positions(self, limit=40):
        return self.query(
            "SELECT galaxy, system, position FROM galaxy_map WHERE debris = 1 ORDER BY seen_at DESC LIMIT ?",
            (limit,),
        )

    def hunted_list(self):
        return [r["player"] for r in self.query("SELECT player FROM hunted ORDER BY player")]

    def hunt_add(self, player):
        with self.lock, self._connect() as conn:
            cur = conn.execute("INSERT OR IGNORE INTO hunted (player) VALUES (?)", (player,))
            return cur.rowcount > 0

    def hunt_remove(self, player):
        self.execute("DELETE FROM hunted WHERE player = ?", (player,))

    def hunted_positions(self, rescan_limit):
        return self.query(
            """
            SELECT g.galaxy, g.system, g.position, g.player, g.seen_at FROM galaxy_map g
            JOIN hunted h ON h.player = g.player
            ORDER BY g.seen_at ASC LIMIT ?
            """,
            (rescan_limit,),
        )

    def log_activity(self, player, player_id, galaxy, system, position, activity):
        self.execute(
            "INSERT INTO activity_log (player, player_id, galaxy, system, position, activity, ts) VALUES (?,?,?,?,?,?,?)",
            (player, player_id, galaxy, system, position, str(activity) if activity is not None else None, time.time()),
        )

    def recent_activity(self, limit=100):
        return self.query("SELECT * FROM activity_log ORDER BY ts DESC LIMIT ?", (limit,))

    def activity_summary(self):
        return self.query(
            """
            SELECT a.player,
                   MAX(a.ts) AS last_seen,
                   SUM(CASE WHEN a.activity IS NOT NULL THEN 1 ELSE 0 END) AS active_count,
                   COUNT(*) AS checks
            FROM activity_log a
            JOIN hunted h ON h.player = a.player
            GROUP BY a.player
            ORDER BY last_seen DESC
            """
        )
