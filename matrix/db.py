"""Storage. SQLite on your own computer; PostgreSQL (for example Supabase) when DATABASE_URL is set.

All SQL in Matrix is written to run on both. The PostgreSQL wrapper below only converts
placeholders and returns rows that behave like sqlite3.Row.
"""
import os
import re
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

CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, totp_secret TEXT, totp_last INTEGER
);

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
    price REAL NOT NULL CHECK (price > 0), note TEXT, created_at TEXT,
    book TEXT NOT NULL DEFAULT 'real'
);
CREATE INDEX IF NOT EXISTS ix_tx_user ON transactions(username);

CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY, username TEXT NOT NULL, kind TEXT NOT NULL, code TEXT NOT NULL,
    note TEXT NOT NULL, sell_if TEXT, review_on TEXT NOT NULL, reviewed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_journal_user ON journal(username, review_on);

CREATE TABLE IF NOT EXISTS forecasts (
    symbol TEXT NOT NULL, date TEXT NOT NULL, horizon INTEGER NOT NULL, prob REAL NOT NULL,
    low REAL, high REAL, model TEXT NOT NULL, backfilled INTEGER NOT NULL DEFAULT 0, created_at TEXT,
    PRIMARY KEY (symbol, date, horizon)
);
CREATE INDEX IF NOT EXISTS ix_forecast_date ON forecasts(date);

CREATE TABLE IF NOT EXISTS levels (
    username TEXT NOT NULL, symbol TEXT NOT NULL, stop REAL NOT NULL, target REAL, set_at TEXT,
    PRIMARY KEY (username, symbol)
);
"""

# Columns added after a table first shipped: (table, column, type). Old databases get them on connect.
ADDED_COLUMNS = [
    ("transactions", "book", "TEXT NOT NULL DEFAULT 'real'"),
    ("users", "totp_secret", "TEXT"),
    ("users", "totp_last", "INTEGER"),
]


def connect(path: str | Path | None = None):
    """PostgreSQL when DATABASE_URL is set (and no path is given), otherwise SQLite."""
    url = os.environ.get("DATABASE_URL") if path is None else None
    if url:
        return PgConnection(url)
    path = path or os.environ.get("MATRIX_DB") or DEFAULT_PATH
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    for table, col, kind in ADDED_COLUMNS:
        if col not in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {kind}")
            conn.commit()
    return conn


# ---------------------------------------------------------------- PostgreSQL
_NAMED = re.compile(r"(?<![:\w]):([A-Za-z_]\w*)")


def to_pg(sql: str) -> str:
    """SQLite-style placeholders (? and :name) to psycopg style (%s and %(name)s).

    A literal % (as in LIKE '%Direct%') must be doubled for psycopg.
    """
    sql = sql.replace("%", "%%")
    sql = sql.replace("?", "%s")
    return _NAMED.sub(r"%(\1)s", sql)


def pg_schema() -> list[str]:
    s = SCHEMA.replace("id INTEGER PRIMARY KEY", "id BIGSERIAL PRIMARY KEY")
    s = re.sub(r"\bINTEGER\b", "BIGINT", s)
    s = re.sub(r"\bREAL\b", "DOUBLE PRECISION", s)
    return [stmt.strip() for stmt in s.split(";") if stmt.strip()]


class Row(tuple):
    """A row you can read by position, by column name, or turn into a dict (like sqlite3.Row)."""

    def __new__(cls, values, keys):
        row = super().__new__(cls, values)
        row._keys = keys
        return row

    def __getitem__(self, key):
        if isinstance(key, str):
            return tuple.__getitem__(self, self._keys.index(key))
        return tuple.__getitem__(self, key)

    def keys(self):
        return list(self._keys)


def _row_factory(cursor):
    keys = [c.name for c in cursor.description] if cursor.description else []
    return lambda values: Row(values, keys)


class PgConnection:
    """The small part of sqlite3.Connection that Matrix uses, on top of psycopg."""

    def __init__(self, url: str):
        import psycopg
        # autocommit: each statement saves at once, like Matrix's SQLite usage with commit().
        # prepare_threshold=None: works through Supabase's connection pooler.
        self._c = psycopg.connect(url, autocommit=True, row_factory=_row_factory,
                                  prepare_threshold=None)
        for stmt in pg_schema():
            self._c.execute(stmt)
        for table, col, kind in ADDED_COLUMNS:
            kind = kind.replace("INTEGER", "BIGINT")
            self._c.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {kind}")

    def execute(self, sql: str, params=()):
        return self._c.execute(to_pg(sql), params or None)

    def executemany(self, sql: str, seq):
        cur = self._c.cursor()
        cur.executemany(to_pg(sql), list(seq))
        return cur

    def commit(self):
        pass  # autocommit

    def close(self):
        self._c.close()
