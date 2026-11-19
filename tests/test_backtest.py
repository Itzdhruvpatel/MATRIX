import pytest
from fastapi.testclient import TestClient

from matrix import api, auth, backtest, db
from tests.test_radar import rows


def insert(conn, sym, rs):
    for r in rs:
        conn.execute("INSERT INTO stock_prices (symbol, date, name, series, open, close, prev_close, high,"
                     " value, source, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,'t','t')",
                     (sym, r["date"], sym, "EQ", r.get("open"), r["close"], r["prev_close"], r["high"], r["value"]))


def test_after_costs():
    assert backtest.after_costs(0.103) == pytest.approx(0.08)   # 10% after costs, minus 20% tax
    assert backtest.after_costs(-0.05) == pytest.approx(-0.053)  # a loss pays costs, no tax


def test_gap_days_are_tested_against_the_nifty():
    conn = db.connect(":memory:")
    insert(conn, "NIFTYBEES", rows(120, 0.0))
    stock = rows(120, 0.002)
    for i in (60, 80):  # opens 5% above the last close on two days
        stock[i] = {**stock[i], "open": stock[i]["prev_close"] * 1.05}
    insert(conn, "GAPPY", stock)
    t = backtest.pattern_history(conn, horizon=20)
    g = t["patterns"]["gap_up"]
    assert g["events"] == 2 and g["avg"] == pytest.approx(1.002 ** 20 - 1) and g["beat_share"] == 1
    assert g["market_avg"] == 0 and t["patterns"]["any_day"]["events"] == 10
    assert t["patterns"]["gap_down"] == {"events": 0}

    auth.set_user(conn, "u", "correct-horse-battery")
    c = TestClient(api.create_app(conn, "s"))
    c.post("/api/login", json={"username": "u", "password": "correct-horse-battery"})
    assert c.get("/api/backtest/patterns").json()["patterns"]["gap_up"]["events"] == 2


def test_result_is_saved_per_price_day(monkeypatch):
    conn = db.connect(":memory:")
    insert(conn, "NIFTYBEES", rows(120, 0.0))
    calls = []
    real = backtest.pattern_history
    monkeypatch.setattr(backtest, "pattern_history", lambda c: calls.append(1) or real(c))
    first = backtest.cached(conn)
    assert backtest.cached(conn) == first and len(calls) == 1
    insert(conn, "NIFTYBEES", [{**rows(1, 0.0)[0], "date": "2030-01-01"}])  # a new price day
    backtest.cached(conn)
    assert len(calls) == 2
