from datetime import date, timedelta

import pytest

from matrix import db, ledger, score


def fill(conn, symbol, daily, n=200, start=100.0):
    price, d = start, date(2025, 1, 1)
    for i in range(n):
        prev = price
        price *= 1 + daily(i)
        conn.execute("INSERT INTO stock_prices (symbol, date, series, close, prev_close, value, source,"
                     " fetched_at) VALUES (?,?,?,?,?,?,?,?)", (symbol, d.isoformat(), "EQ", price, prev, 5e8, "t", "t"))
        d += timedelta(days=1)


@pytest.fixture
def market():
    conn = db.connect(":memory:")
    # Winners keep rising, losers keep falling, the market drifts slowly up.
    for k in range(5):
        fill(conn, f"WIN{k}", lambda i, k=k: 0.004 + 0.0005 * k)
        fill(conn, f"LOSE{k}", lambda i, k=k: -0.004 - 0.0005 * k)
    fill(conn, "NIFTYBEES", lambda i: 0.0005)
    return conn


def test_score_as_of_uses_only_past_data(market):
    days = ledger.trading_days(market)
    assert score.compute(market, as_of=days[150]) == 11
    dates = {r[0] for r in market.execute("SELECT DISTINCT date FROM stock_scores")}
    assert dates == {days[150]}


def test_backfill_and_track_record(market):
    made = ledger.backfill(market, horizon=20)
    assert made >= 2
    t = ledger.track_record(market, horizon=20)
    assert t["periods"], "expected at least one checked month"
    p = t["periods"][0]
    assert p["strong_avg"] > p["market"] > p["weak_avg"]
    assert t["strong_beat_share"] == 1.0
    # periods do not overlap
    starts = [r["date"] for r in t["periods"]]
    assert starts == sorted(starts, reverse=True)


def test_track_record_empty_without_history():
    assert ledger.track_record(db.connect(":memory:"))["periods"] == []
