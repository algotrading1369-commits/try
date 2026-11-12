import json
import os
import sqlite3
import threading
import time

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")


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
                """
            )

    def execute(self, sql, params=()):
        with self.lock, self._connect() as conn:
            return conn.execute(sql, params)

    def query(self, sql, params=()):
        with self.lock, self._connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def get_account(self):
        rows = self.query("SELECT * FROM accounts WHERE active = 1 ORDER BY id LIMIT 1")
        return rows[0] if rows else None

    def save_account(self, universe, language, username, password, demo):
        with self.lock, self._connect() as conn:
            conn.execute("UPDATE accounts SET active = 0")
            conn.execute(
                "INSERT INTO accounts (universe, language, username, password, demo, active, created_at) VALUES (?,?,?,?,?,1,?)",
                (universe, language, username, password, 1 if demo else 0, time.time()),
            )

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

    def targets(self, only_inactive=True):
        sql = "SELECT * FROM targets"
        if only_inactive:
            sql += " WHERE inactive = 1"
        sql += " ORDER BY metal + crystal + deuterium DESC LIMIT 500"
        return self.query(sql)
