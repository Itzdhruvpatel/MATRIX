import json

from fastapi.testclient import TestClient

from matrix import api, auth, db, ledger, screener
from tests.test_ledger import market  # noqa: F401  (fixture)


def add(conn, sym, sc, comps, liquidity=5e8, day="2026-11-13"):
    conn.execute("INSERT INTO stock_prices (symbol, date, name, series, close, prev_close, source,"
                 " fetched_at) VALUES (?,?,?,'EQ',100,100,'t','t')", (sym, day, f"{sym} LTD"))
    conn.execute("INSERT INTO stock_scores (symbol, date, score, components, metrics, reasons, universe)"
                 " VALUES (?,?,?,?,?,'[]',4)", (sym, day, sc, json.dumps(comps),
                                               json.dumps({"liquidity": liquidity})))


def calm(v):
    return {"momentum": 50, "trend": 60, "volatility": v, "drawdown": 60, "liquidity": 50}


def test_rules_filter_and_explain():
    c = db.connect(":memory:")
    add(c, "GOOD", 85, calm(80))
    add(c, "WILD", 82, calm(10))
    add(c, "RISKY", 90, calm(90))
    add(c, "THIN", 88, calm(90), liquidity=2e6)
    add(c, "LOW", 30, calm(90))
    c.execute("INSERT INTO alerts (symbol, date, rule, level, title) VALUES"
              " ('RISKY', '2026-11-13', 'pump', 'danger', 'x')")
    r = screener.shortlist(c, screener.Rules(min_score=60, no_danger=True, min_traded_cr=1, calm=True))
    assert [s["symbol"] for s in r["items"]] == ["GOOD"]
    assert any("calmly" in why for why in r["items"][0]["why"])
    r = screener.shortlist(c, screener.Rules(min_score=60, no_danger=False, min_traded_cr=1))
    assert [s["symbol"] for s in r["items"]] == ["RISKY", "GOOD", "WILD"]


def test_history_compares_with_nifty(market):  # noqa: F811
    ledger.backfill(market, horizon=20)
    h = screener.history(market, screener.Rules(min_score=60, min_traded_cr=1), horizon=20)
    assert h["periods"] >= 1 and h["avg"] > h["market_avg"] and h["won"] == h["periods"]


def test_shortlist_endpoint_owner_only(market, monkeypatch):  # noqa: F811
    ledger.backfill(market, horizon=20)
    auth.set_user(market, "owner", "correct-horse-battery")
    auth.set_user(market, "guest", "correct-horse-battery")
    c = TestClient(api.create_app(market, "s"))
    monkeypatch.setenv("MATRIX_OWNER", "owner")
    c.post("/api/login", json={"username": "guest", "password": "correct-horse-battery"})
    assert c.get("/api/shortlist").status_code == 403
    c.post("/api/login", json={"username": "owner", "password": "correct-horse-battery"})
    r = c.get("/api/shortlist", params={"min_score": 60, "min_traded_cr": 1}).json()
    assert {s["symbol"] for s in r["items"]} <= {f"WIN{k}" for k in range(5)} and r["items"]
    assert r["history"]["periods"] >= 1


def test_history_pays_costs_and_tax_and_compounds(market):  # noqa: F811
    from matrix import backtest
    ledger.backfill(market, horizon=20)
    h = screener.history(market, screener.Rules(min_score=60, min_traded_cr=1), horizon=20)
    grown = 1e5
    for r in sorted(h["rows"], key=lambda r: r["date"]):
        assert r["after"] == backtest.after_costs(r["avg"], 0.20)
        grown *= 1 + r["after"]
    assert h["growth"] == grown and h["avg_after_costs"] < h["avg"] and h["tax"] == 0.20
    assert backtest.tax_for(252) == 0.125


def test_shortlist_rejects_odd_holding_periods(market, monkeypatch):  # noqa: F811
    auth.set_user(market, "owner", "correct-horse-battery")
    c = TestClient(api.create_app(market, "s"))
    c.post("/api/login", json={"username": "owner", "password": "correct-horse-battery"})
    assert c.get("/api/shortlist", params={"horizon": 30}).status_code == 400
    assert c.get("/api/shortlist", params={"horizon": 63}).json()["history"]["horizon"] == 63
