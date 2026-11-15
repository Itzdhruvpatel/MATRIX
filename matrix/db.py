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

CREATE TABLE IF NOT EXISTS announcements (
    id TEXT PRIMARY KEY, feed TEXT NOT NULL, company TEXT, symbol TEXT, subject TEXT,
    description TEXT, link TEXT, published_at TEXT, source TEXT NOT NULL, fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ann_symbol ON announcements(symbol, published_at);

CREATE TABLE IF NOT EXISTS deals (
    date TEXT NOT NULL, symbol TEXT NOT NULL, client TEXT NOT NULL, side TEXT NOT NULL,
    quantity INTEGER NOT NULL, price REAL NOT NULL, kind TEXT NOT NULL,
    source TEXT NOT NULL, fetched_at TEXT NOT NULL,
    PRIMARY KEY (date, symbol, client, side, quantity, price, kind)
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, date TEXT NOT NULL, rule TEXT NOT NULL,
    level TEXT NOT NULL CHECK (level IN ('info', 'watch', 'warning', 'danger')),
    title TEXT NOT NULL, detail TEXT, link TEXT, source TEXT
);
CREATE INDEX IF NOT EXISTS ix_alert_symbol ON alerts(symbol);

CREATE TABLE IF NOT EXISTS watchlist (
    username TEXT NOT NULL, kind TEXT NOT NULL CHECK (kind IN ('stock', 'fund')),
    code TEXT NOT NULL, added_at TEXT, PRIMARY KEY (username, kind, code)
);

CREATE TABLE IF NOT EXISTS stock_scores (
    symbol TEXT NOT NULL, date TEXT NOT NULL, score INTEGER,
    components TEXT, metrics TEXT, reasons TEXT, universe INTEGER,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY, username TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('stock', 'fund')),
    code TEXT NOT NULL, side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    date TEXT NOT NULL, quantity REAL NOT NULL CHECK (quantity > 0),
    price REAL NOT NULL CHECK (price > 0), note TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_tx_user ON transactions(username);

CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY, username TEXT NOT NULL, kind TEXT NOT NULL, code TEXT NOT NULL,
    note TEXT NOT NULL, sell_if TEXT, review_on TEXT NOT NULL, reviewed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_journal_user ON journal(username, review_on);
"""


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    path = path or os.environ.get("MATRIX_DB") or DEFAULT_PATH
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    # Older databases: add the practice-money column to transactions.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(transactions)")}
    if "book" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN book TEXT NOT NULL DEFAULT 'real'")
        conn.commit()
    return conn
