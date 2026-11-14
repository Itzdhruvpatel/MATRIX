"""Fetch -> validate -> store. Run: python -m matrix.pipeline [--days N]"""
import argparse
import sqlite3
from datetime import date, datetime, timedelta, timezone

from matrix import db, validate
from matrix.sources import amfi, nse

IST = timezone(timedelta(hours=5, minutes=30))


def now() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def today_ist() -> date:
    return datetime.now(IST).date()


def _log_run(conn, source, day, status, rows, issues, message, started):
    conn.execute(
        "INSERT INTO pipeline_runs (source, date, status, rows, issues, message, started_at,"
        " finished_at) VALUES (?,?,?,?,?,?,?,?)",
        (source, day, status, rows, issues, message, started, now()))
    conn.commit()
    return {"status": status, "rows": rows, "issues": issues}


def _issue(conn, source, key, day, severity, reason):
    conn.execute(
        "INSERT INTO data_issues (source, key, date, severity, reason, created_at)"
        " VALUES (?,?,?,?,?,?)", (source, key, day, severity, reason, now()))


def load_stocks(conn: sqlite3.Connection, day: date, fetch=nse.download) -> dict:
    started = now()
    try:
        raw = fetch(day)
        if raw is None:
            return _log_run(conn, nse.SOURCE, day.isoformat(), "no_data", 0, 0,
                            "no file (holiday or weekend)", started)
        rows = nse.parse(raw)
    except Exception as e:  # network or format change: record it, never crash the scheduler
        return _log_run(conn, nse.SOURCE, day.isoformat(), "error", 0, 0, repr(e), started)

    fetched = now()
    good, issues = [], 0
    conn.execute("DELETE FROM data_issues WHERE source=? AND date=?", (nse.SOURCE, day.isoformat()))
    for r in rows:
        ok, reason = validate.stock_row(r)
        if not ok:
            _issue(conn, nse.SOURCE, r["symbol"], r["date"], "quarantined", reason)
            issues += 1
            continue
        jump = validate.stock_jump(r)
        if jump:
            _issue(conn, nse.SOURCE, r["symbol"], r["date"], "flagged", jump)
            issues += 1
        good.append({**r, "source": nse.SOURCE, "fetched_at": fetched})

    conn.executemany(
        "INSERT OR REPLACE INTO stock_prices (symbol, date, isin, name, series, open, high, low,"
        " close, prev_close, volume, value, trades, source, fetched_at) VALUES (:symbol, :date,"
        " :isin, :name, :series, :open, :high, :low, :close, :prev_close, :volume, :value,"
        " :trades, :source, :fetched_at)", good)
    return _log_run(conn, nse.SOURCE, day.isoformat(), "ok", len(good), issues, None, started)


def load_funds(conn: sqlite3.Connection, fetch=amfi.download) -> dict:
    started = now()
    try:
        rows = amfi.parse(fetch())
    except Exception as e:
        return _log_run(conn, amfi.SOURCE, today_ist().isoformat(), "error", 0, 0, repr(e), started)

    fetched = now()
    good, issues = [], 0
    for r in rows:
        ok, reason = validate.fund_row(r)
        if not ok:
            _issue(conn, amfi.SOURCE, r["scheme_code"], r["date"], "quarantined", reason)
            issues += 1
            continue
        good.append({**r, "source": amfi.SOURCE, "fetched_at": fetched})

    conn.executemany(
        "INSERT OR REPLACE INTO funds (scheme_code, name, amc, category, plan, option,"
        " isin_growth, isin_reinv, source, fetched_at) VALUES (:scheme_code, :name, :amc,"
        " :category, :plan, :option, :isin_growth, :isin_reinv, :source, :fetched_at)", good)
    conn.executemany(
        "INSERT OR REPLACE INTO fund_navs (scheme_code, date, nav, source, fetched_at)"
        " VALUES (:scheme_code, :date, :nav, :source, :fetched_at)", good)
    nav_day = good[0]["date"] if good else today_ist().isoformat()
    return _log_run(conn, amfi.SOURCE, nav_day, "ok", len(good), issues, None, started)


def run(conn: sqlite3.Connection, days: int = 1) -> list[dict]:
    """Load the last `days` trading days of stocks (skipping holidays) plus today's fund NAVs."""
    results, day, loaded, tries = [], today_ist(), 0, 0
    while loaded < days and tries < days * 2 + 10:
        if day.weekday() < 5:
            s = {"source": nse.SOURCE, "date": day.isoformat(), **load_stocks(conn, day)}
            results.append(s)
            loaded += s["status"] == "ok"
        day -= timedelta(days=1)
        tries += 1
    results.append({"source": amfi.SOURCE, **load_funds(conn)})
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Load market data into Matrix")
    ap.add_argument("--days", type=int, default=1, help="trading days of stock data to load")
    args = ap.parse_args()
    for r in run(db.connect(), args.days):
        print(r)
