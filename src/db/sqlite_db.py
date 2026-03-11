"""SQLite database for dynamic data: users, reservations, availability, prices, working hours."""

import json
import sqlite3
from pathlib import Path
from typing import Any, List, Optional, Tuple

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "parking.db"


class SQLiteDB:
    """SQLite backend for users, reservations, availability, prices, working hours."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        seed_path: Optional[str] = None,
    ) -> None:
        """Open or create DB at db_path; seed from seed_path if table is empty."""
        self.db_path = db_path or str(DEFAULT_DB_PATH)
        self._seed_path = seed_path or str(Path(self.db_path).parent / "seed_data.json")
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

    def _seed_if_empty(self) -> None:
        with self._get_conn() as conn:
            if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
                return
            seed_path = Path(self._seed_path)
            if not seed_path.is_file():
                return
            data: Any = json.loads(seed_path.read_text(encoding="utf-8"))
            if data.get("users"):
                conn.executemany(
                    "INSERT OR IGNORE INTO users (nickname, plates) VALUES (?, ?)",
                    [tuple(row) for row in data["users"]],
                )
            if data.get("working_hours"):
                conn.executemany(
                    "INSERT OR IGNORE INTO working_hours (id, day_of_week, open_time, close_time, description) VALUES (?, ?, ?, ?, ?)",
                    [tuple(row) for row in data["working_hours"]],
                )
            if data.get("prices"):
                conn.executemany(
                    "INSERT OR IGNORE INTO prices (id, type, rate, unit) VALUES (?, ?, ?, ?)",
                    [tuple(row) for row in data["prices"]],
                )
            if data.get("availability"):
                conn.executemany(
                    "INSERT OR REPLACE INTO availability (date, free_spaces) VALUES (?, ?)",
                    [tuple(row) for row in data["availability"]],
                )
            conn.commit()

    def user_exists(self, nickname: str) -> bool:
        """Return True if nickname exists in users table."""
        with self._get_conn() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM users WHERE nickname = ?", (nickname.strip(),)
                ).fetchone()
                is not None
            )

    def get_free_spaces(self, date: str) -> Optional[int]:
        """Return free_spaces for date, or None if not in availability table."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT free_spaces FROM availability WHERE date = ?", (date.strip(),)
            ).fetchone()
            return row[0] if row else None

    def add_reservation(self, nickname: str, date: str) -> bool:
        """Insert one reservation row; return True on success, False on integrity error."""
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
        """Return list of (date,) tuples for the given nickname, ordered by date."""
        with self._get_conn() as conn:
            cur = conn.execute(
                "SELECT date FROM reservations WHERE nickname = ? ORDER BY date",
                (nickname.strip(),),
            )
            return [tuple(row) for row in cur.fetchall()]

    def get_prices(self) -> List[Tuple[str, float, str]]:
        """Return all rows from prices as (type, rate, unit)."""
        with self._get_conn() as conn:
            return conn.execute("SELECT type, rate, unit FROM prices").fetchall()

    def get_working_hours(self) -> List[Tuple]:
        """Return all rows from working_hours (day_of_week, open_time, close_time, description)."""
        with self._get_conn() as conn:
            return conn.execute(
                "SELECT day_of_week, open_time, close_time, description FROM working_hours"
            ).fetchall()


_db: Optional[SQLiteDB] = None


def get_db(db_path: Optional[str] = None) -> SQLiteDB:
    """Return the singleton SQLiteDB instance; create with optional db_path if first call."""
    global _db
    if _db is None:
        _db = SQLiteDB(db_path)
    return _db
