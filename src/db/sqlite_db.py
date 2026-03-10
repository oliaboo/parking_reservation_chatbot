"""SQLite database for dynamic data: users, reservations, availability, prices, working hours."""

import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "parking.db"


class SQLiteDB:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(DEFAULT_DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._seed_if_empty()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_schema(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (nickname TEXT PRIMARY KEY, plates TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reservations (nickname TEXT NOT NULL, date TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS working_hours (id INTEGER PRIMARY KEY, day_of_week INTEGER, open_time TEXT, close_time TEXT, description TEXT);
                CREATE TABLE IF NOT EXISTS prices (id INTEGER PRIMARY KEY, type TEXT, rate REAL, unit TEXT);
                CREATE TABLE IF NOT EXISTS availability (date TEXT PRIMARY KEY, free_spaces INTEGER NOT NULL);
            """)

    def _seed_if_empty(self):
        with self._get_conn() as conn:
            if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
                return
            users = [
                ("alice", "ABC-1234"),
                ("bob", "XYZ-5678"),
                ("charlie", "DEF-9012"),
                ("diana", "GHI-3456"),
                ("eve", "JKL-7890"),
                ("frank", "MNO-1111"),
                ("grace", "PQR-2222"),
                ("henry", "STU-3333"),
                ("iris", "VWX-4444"),
                ("jack", "YZA-5555"),
            ]
            conn.executemany("INSERT OR IGNORE INTO users (nickname, plates) VALUES (?, ?)", users)
            conn.executemany(
                "INSERT OR IGNORE INTO working_hours (id, day_of_week, open_time, close_time, description) VALUES (?, ?, ?, ?, ?)",
                [(1, 0, "00:00", "23:59", "24/7"), (2, 1, "08:00", "18:00", "Desk")],
            )
            conn.executemany(
                "INSERT OR IGNORE INTO prices (id, type, rate, unit) VALUES (?, ?, ?, ?)",
                [
                    (1, "standard_hour", 5.0, "hour"),
                    (2, "standard_day", 30.0, "day"),
                    (3, "premium_hour", 8.0, "hour"),
                    (4, "premium_day", 45.0, "day"),
                ],
            )
            conn.executemany(
                "INSERT OR REPLACE INTO availability (date, free_spaces) VALUES (?, ?)",
                [
                    ("2025-03-10", 50),
                    ("2025-03-11", 45),
                    ("2025-03-12", 30),
                    ("2025-03-13", 20),
                    ("2025-03-14", 60),
                    ("2025-03-15", 80),
                ],
            )
            conn.commit()

    def user_exists(self, nickname: str) -> bool:
        with self._get_conn() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM users WHERE nickname = ?", (nickname.strip(),)
                ).fetchone()
                is not None
            )

    def get_free_spaces(self, date: str) -> Optional[int]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT free_spaces FROM availability WHERE date = ?", (date.strip(),)
            ).fetchone()
            return row[0] if row else None

    def add_reservation(self, nickname: str, date: str) -> bool:
        nickname, date = nickname.strip(), date.strip()
        with self._get_conn() as conn:
            try:
                conn.execute(
                    "INSERT INTO reservations (nickname, date) VALUES (?, ?)", (nickname, date)
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def get_reservations_by_nickname(self, nickname: str) -> List[Tuple[str, ...]]:
        with self._get_conn() as conn:
            cur = conn.execute(
                "SELECT date FROM reservations WHERE nickname = ? ORDER BY date",
                (nickname.strip(),),
            )
            return [tuple(row) for row in cur.fetchall()]

    def get_prices(self) -> List[Tuple[str, float, str]]:
        with self._get_conn() as conn:
            return conn.execute("SELECT type, rate, unit FROM prices").fetchall()

    def get_working_hours(self) -> List[Tuple]:
        with self._get_conn() as conn:
            return conn.execute(
                "SELECT day_of_week, open_time, close_time, description FROM working_hours"
            ).fetchall()


_db: Optional[SQLiteDB] = None


def get_db(db_path: Optional[str] = None) -> SQLiteDB:
    global _db
    if _db is None:
        _db = SQLiteDB(db_path)
    return _db
