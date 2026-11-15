from datetime import date, timedelta

import pytest

from matrix import db, insights, portfolio


def add_prices(conn, symbol, closes, start=date(2025, 11, 10), series="EQ", name=None):
    prev = closes[0]
    for i, c in enumerate(closes):
        d = (start + timedelta(days=i)).isoformat()
        conn.execute("INSERT INTO stock_prices (symbol, date, name, series, close, prev_close, value, source,"
                     " fetched_at) VALUES (?,?,?,?,?,?,?,?,?)", (symbol, d, name or symbol, series, c, prev, 1e9, "t", "t"))
        prev = c


def wiggle(n, base=100.0, step=0.01, trend=0.0):
    out, p = [], base
    for i in range(n):
        p *= 1 + trend + (step if i % 2 else -step)
        out.append(p)
    return out


# ---------------------------------------------------------------- beta
def test_beta_of_a_stock_that_moves_twice_the_market():
    m = wiggle(60, step=0.01)
    s = [100.0]
    for i in range(1, 60):
        s.append(s[-1] * (1 + 2 * (m[i] / m[i - 1] - 1)))
    md = [(date(2026, 1, 1) + timedelta(days=i), v) for i, v in enumerate(m)]
    sd = [(date(2026, 1, 1) + timedelta(days=i), v) for i, v in enumerate(s)]
    assert insights.beta(sd, md) == pytest.approx(2.0, abs=0.01)
    assert insights.beta(sd[:10], md[:10]) is None  # too little overlap


# ---------------------------------------------------------------- mood
def test_mood_calm_vs_panic():
    calm = insights.mood_from(vol20=0.10, drawdown=-0.02, breadth5=0.55)
    panic = insights.mood_from(vol20=0.35, drawdown=-0.22, breadth5=0.25)
    assert calm["level"] == "Calm" and panic["level"] == "Panic"
    assert panic["reasons"] and calm["reasons"]


def test_market_mood_reads_niftybees():
    conn = db.connect(":memory:")
    add_prices(conn, "NIFTYBEES", wiggle(80, step=0.002, trend=0.001))
    m = insights.market_mood(conn)
    assert m["level"] == "Calm" and m["as_of"]


# ---------------------------------------------------------------- scenario
@pytest.fixture
def owned():
    conn = db.connect(":memory:")
    m = wiggle(80, step=0.01)
    add_prices(conn, "NIFTYBEES", m)
    hi = [100.0]
    for i in range(1, 80):
        hi.append(hi[-1] * (1 + 1.5 * (m[i] / m[i - 1] - 1)))
    add_prices(conn, "HIBETA", hi)
    portfolio.add(conn, "u", {"kind": "stock", "code": "HIBETA", "side": "buy", "date": "2025-11-12", "quantity": 10, "price": 90})
    return conn


def test_scenario_scales_by_beta(owned):
    s = insights.scenario(owned, "u", market_move=-0.20)
    (h,) = s["holdings"]
    assert h["beta"] == pytest.approx(1.5, abs=0.05)
    assert h["change_pct"] == pytest.approx(-0.30, abs=0.01)
    assert s["change"] == pytest.approx(s["value"] * -0.30, rel=0.02)


def test_scenario_limits_inputs(owned):
    with pytest.raises(ValueError):
        insights.scenario(owned, "u", market_move=-1.5)


# ---------------------------------------------------------------- tax
def test_tax_view_splits_short_and_long_term_with_fifo():
    conn = db.connect(":memory:")
    add_prices(conn, "TCS", [4000.0])  # current price 4000 on 2025-11-10
    tx = lambda d, q, p, side="buy": portfolio.add(conn, "u", {"kind": "stock", "code": "TCS", "side": side, "date": d, "quantity": q, "price": p})
    assert tx("2024-01-01", 10, 3000) is None   # long term lot
    assert tx("2025-09-01", 10, 3500) is None   # short term lot
    assert tx("2025-10-01", 4, 3900, "sell") is None  # FIFO: comes out of the 2024 lot
    t = insights.tax_view(conn, "u", today=date(2025, 11, 10))
    assert t["long_term_gain"] == pytest.approx(6 * 1000)   # 6 left from 2024 lot
    assert t["short_term_gain"] == pytest.approx(10 * 500)
    assert t["short_term_tax"] == pytest.approx(10 * 500 * 0.20)
    assert t["long_term_tax"] == 0  # 6,000 is under the 1.25 lakh yearly exemption
    assert t["tax_free_room"] == pytest.approx(125000 - 6000)


def test_tax_view_long_term_above_exemption():
    conn = db.connect(":memory:")
    add_prices(conn, "INFY", [2000.0])
    portfolio.add(conn, "u", {"kind": "stock", "code": "INFY", "side": "buy", "date": "2023-01-01", "quantity": 200, "price": 1000})
    t = insights.tax_view(conn, "u", today=date(2025, 11, 10))
    assert t["long_term_gain"] == 200000
    assert t["long_term_tax"] == pytest.approx((200000 - 125000) * 0.125)
