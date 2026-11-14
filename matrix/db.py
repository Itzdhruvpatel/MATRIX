"""SQLite storage. Plain SQL so it can move to PostgreSQL later."""
import os
import sqlite3
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "matrix.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS stock_prices (
    symbol TEXT NOT NULL, date TEXT NOT NULL, isin TEXT, name TEXT, series TEXT,
    open REAL, high REAL, low REAL, close REAL, prev_close REAL,
    volume INTEGER, value REAL, trades INTEGER,
    source TEXT NOT NULL, fetched_at TEXT NOT NULL,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS ix_stock_date ON stock_prices(date);

CREATE TABLE IF NOT EXISTS funds (
    scheme_code TEXT PRIMARY KEY, name TEXT, amc TEXT, category TEXT, plan TEXT, option TEXT,
    isin_growth TEXT, isin_reinv TEXT, source TEXT NOT NULL, fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fund_navs (
    scheme_code TEXT NOT NULL, date TEXT NOT NULL, nav REAL NOT NULL,
    source TEXT NOT NULL, fetched_at TEXT NOT NULL,
    PRIMARY KEY (scheme_code, date)
);

CREATE TABLE IF NOT EXISTS data_issues (
    id INTEGER PRIMARY KEY, source TEXT, key TEXT, date TEXT,
    severity TEXT CHECK (severity IN ('quarantined', 'flagged')), reason TEXT, created_at TEXT
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY, source TEXT, date TEXT, status TEXT, rows INTEGER, issues INTEGER,
    message TEXT, started_at TEXT, finished_at TEXT
);

CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL);
"""


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    path = path or os.environ.get("MATRIX_DB") or DEFAULT_PATH
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn
