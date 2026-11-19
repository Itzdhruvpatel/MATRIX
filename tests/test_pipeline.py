from datetime import date

from matrix import db, pipeline, validate
from tests.test_sources import AMFI_TEXT, NSE_ROWS, nse_zip


def stock(**kw):
    r = dict(date="2026-11-13", symbol="ABC", isin="I", name="ABC LTD", series="EQ", open=100,
             high=110, low=95, close=105, prev_close=100, volume=1000, value=1e5, trades=10)
    r.update(kw)
    return r


def test_validate_stock_good_row():
    assert validate.stock_row(stock()) == (True, None)


def test_validate_stock_rejects_broken_rows():
    assert validate.stock_row(stock(close=0))[0] is False
    assert validate.stock_row(stock(high=90))[0] is False          # high below low
    assert validate.stock_row(stock(close=120))[0] is False        # close above high
    assert validate.stock_row(stock(volume=-1))[0] is False


def test_validate_flags_big_jump_but_keeps_row():
    assert validate.stock_jump(stock(close=105)) is None
    assert "jump" in validate.stock_jump(stock(close=108, high=130, prev_close=80))


def test_validate_fund_row():
    assert validate.fund_row({"nav": 10.0})[0] is True
    assert validate.fund_row({"nav": 0})[0] is False


def test_load_stocks_stores_rows_with_source_and_logs_run():
    conn = db.connect(":memory:")
    s = pipeline.load_stocks(conn, date(2026, 11, 13), fetch=lambda d: nse_zip(NSE_ROWS))
    assert s == {"status": "ok", "rows": 1, "issues": 0}
    row = conn.execute("SELECT symbol, close, source, fetched_at FROM stock_prices").fetchone()
    assert row["symbol"] == "RELIANCE" and row["close"] == 1339.70
    assert row["source"] == "nse_bhavcopy" and row["fetched_at"]
    run = conn.execute("SELECT * FROM pipeline_runs").fetchone()
    assert run["status"] == "ok" and run["rows"] == 1


def test_load_stocks_quarantines_bad_rows():
    bad = NSE_ROWS[0].replace("1339.70,1339.70,1320.00", "0,0,1320.00", 1)
    conn = db.connect(":memory:")
    s = pipeline.load_stocks(conn, date(2026, 11, 13), fetch=lambda d: nse_zip([bad]))
    assert s["rows"] == 0 and s["issues"] == 1
    assert conn.execute("SELECT COUNT(*) FROM stock_prices").fetchone()[0] == 0
    issue = conn.execute("SELECT * FROM data_issues").fetchone()
    assert issue["severity"] == "quarantined" and issue["key"] == "RELIANCE"


def test_load_stocks_holiday_and_rerun_is_idempotent():
    conn = db.connect(":memory:")
    assert pipeline.load_stocks(conn, date(2026, 11, 14), fetch=lambda d: None)["status"] == "no_data"
    jumpy = NSE_ROWS[0].replace("1339.70,1339.70,1320.00", "1339.70,1339.70,1000.00", 1)
    for _ in range(2):
        pipeline.load_stocks(conn, date(2026, 11, 13), fetch=lambda d: nse_zip([jumpy]))
    assert conn.execute("SELECT COUNT(*) FROM stock_prices").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM data_issues").fetchone()[0] == 1


def test_load_stocks_records_download_failure():
    def boom(d):
        raise ConnectionError("network down")
    conn = db.connect(":memory:")
    s = pipeline.load_stocks(conn, date(2026, 11, 13), fetch=boom)
    assert s["status"] == "error"
    assert "network down" in conn.execute("SELECT message FROM pipeline_runs").fetchone()[0]


def test_load_funds_stores_schemes_and_navs():
    conn = db.connect(":memory:")
    s = pipeline.load_funds(conn, fetch=lambda: AMFI_TEXT)
    assert s["rows"] == 2
    f = conn.execute("SELECT * FROM funds WHERE scheme_code='120465'").fetchone()
    assert f["amc"] == "Axis Mutual Fund" and f["category"] == "Equity Scheme - Large Cap Fund"
    assert conn.execute("SELECT COUNT(*) FROM fund_navs").fetchone()[0] == 2


def test_load_fund_history_keeps_official_and_flags_mismatch():
    conn = db.connect(":memory:")
    pipeline.load_funds(conn, fetch=lambda: AMFI_TEXT)  # AMFI: 120465 = 65.12 on 2026-11-13
    payload = {"data": [{"date": "13-11-2026", "nav": "70.00000"},   # disagrees with AMFI
                        {"date": "12-11-2026", "nav": "64.90000"},
                        {"date": "11-11-2026", "nav": "N.A."}]}
    s = pipeline.load_fund_history(conn, "120465", fetch=lambda c: payload)
    assert s["status"] == "ok" and s["issues"] == 1
    navs = dict(conn.execute("SELECT date, nav FROM fund_navs WHERE scheme_code='120465'"))
    assert navs == {"2026-11-13": 65.12, "2026-11-12": 64.9}  # official value kept


def test_data_problems_spots_failed_and_late_updates():
    from datetime import datetime
    conn = db.connect(":memory:")
    run = lambda src, day, status, started, msg=None: conn.execute(  # noqa: E731
        "INSERT INTO pipeline_runs (source, date, status, message, started_at) VALUES (?,?,?,?,?)",
        (src, day, status, msg, started))
    monday_noon = datetime(2026, 11, 16, 12, 0, tzinfo=pipeline.IST)
    friday_night = datetime(2026, 11, 13, 22, 0, tzinfo=pipeline.IST)
    assert {p["what"] for p in pipeline.data_problems(conn, monday_noon)} == {"prices", "navs"}

    # Friday's prices loaded, NAVs loaded last night: all fine on Monday at noon.
    run("nse_bhavcopy", "2026-11-13", "ok", "2026-11-13T19:05:00+05:30")
    run("amfi_navall", "2026-11-14", "ok", "2026-11-15T23:15:00+05:30")
    assert pipeline.data_problems(conn, monday_noon) == []
    assert pipeline.data_problems(conn, friday_night) == []

    # Monday after 9 PM: Monday's prices should be in. A failed try is reported with its reason.
    monday_night = datetime(2026, 11, 16, 21, 30, tzinfo=pipeline.IST)
    late = pipeline.data_problems(conn, monday_night)
    assert [p["what"] for p in late] == ["prices"] and "not loaded yet" in late[0]["text"]
    run("nse_bhavcopy", "2026-11-16", "error", "2026-11-16T19:05:00+05:30", "HTTPError 403")
    failed = pipeline.data_problems(conn, monday_night)
    assert "failed" in failed[0]["text"] and failed[0]["detail"] == "HTTPError 403"

    # NAVs: a newer failed run, or no success for 36 hours, is a problem.
    run("amfi_navall", "2026-11-16", "error", "2026-11-16T23:15:00+05:30", "timeout")
    later = datetime(2026, 11, 16, 23, 30, tzinfo=pipeline.IST)
    assert "failed" in [p for p in pipeline.data_problems(conn, later) if p["what"] == "navs"][0]["text"]
    run("amfi_navall", "2026-11-17", "ok", "2026-11-17T23:15:00+05:30")
    assert not [p for p in pipeline.data_problems(conn, datetime(2026, 11, 18, 12, 0, tzinfo=pipeline.IST))
                if p["what"] == "navs"]
    assert [p for p in pipeline.data_problems(conn, datetime(2026, 11, 19, 12, 0, tzinfo=pipeline.IST))
            if p["what"] == "navs"]


def test_load_history_fills_only_missing_days(monkeypatch):
    conn = db.connect(":memory:")
    asked = []
    monkeypatch.setattr(pipeline, "today_ist", lambda: date(2026, 11, 13))

    def fetch(d):
        asked.append(d)
        return None  # a holiday each time is enough to test the bookkeeping

    r = pipeline.load_history(conn, date(2026, 11, 2), fetch, pause=0)
    assert r == {"ok": 0, "no_data": 10, "error": 0} and len(asked) == 10  # weekdays only
    asked.clear()
    assert pipeline.load_history(conn, date(2026, 11, 2), fetch, pause=0)["no_data"] == 0 and not asked
