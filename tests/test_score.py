from datetime import date, timedelta

from matrix import db, score


def rows(n, daily, value=5e7, start=100.0):
    out, price, d = [], start, date(2025, 1, 1)
    for _ in range(n):
        prev = price
        price = price * (1 + daily)
        out.append({"date": d.isoformat(), "close": price, "prev_close": prev, "value": value})
        d += timedelta(days=1)
    return out


def test_percentile_ranks_order_and_ties():
    r = score.percentile_ranks({"a": 1, "b": 2, "c": 2, "d": 3}, higher_is_better=True)
    assert r["d"] == 100 and r["a"] == 0 and r["b"] == r["c"]
    low = score.percentile_ranks({"a": 1, "b": 3}, higher_is_better=False)
    assert low["a"] == 100


def test_metrics_need_enough_history():
    assert score.metrics(rows(50, 0.001)) is None
    m = score.metrics(rows(300, 0.001))
    assert m["momentum"] > 0 and m["trend"] > 0 and m["drawdown"] == 0


def test_rising_stock_beats_falling_stock_and_surveillance_is_capped():
    stocks = {
        "UP": {"metrics": score.metrics(rows(300, 0.002)), "series": "EQ"},
        "DOWN": {"metrics": score.metrics(rows(300, -0.002)), "series": "EQ"},
        "WATCH": {"metrics": score.metrics(rows(300, 0.003)), "series": "BE"},
    }
    res = score.score_universe(stocks)
    assert res["UP"]["score"] > res["DOWN"]["score"]
    assert res["WATCH"]["score"] <= score.SURVEILLANCE_CAP
    assert res["WATCH"]["reasons"][0]["kind"] == "danger"
    assert any(r["kind"] == "weakness" for r in res["DOWN"]["reasons"])


def test_compute_writes_scores():
    conn = db.connect(":memory:")
    for sym, daily in (("AAA", 0.002), ("BBB", -0.001)):
        for r in rows(200, daily):
            conn.execute(
                "INSERT INTO stock_prices (symbol, date, series, close, prev_close, value, source,"
                " fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                (sym, r["date"], "EQ", r["close"], r["prev_close"], r["value"], "t", "t"))
    assert score.compute(conn) == 2
    got = dict(conn.execute("SELECT symbol, score FROM stock_scores"))
    assert got["AAA"] > got["BBB"]
