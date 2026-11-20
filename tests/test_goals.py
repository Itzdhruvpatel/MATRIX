from datetime import date

import pytest
from fastapi.testclient import TestClient

from matrix import api, auth, db, goals

TODAY = date(2026, 11, 19)


def test_target_grows_with_inflation_and_ranges_are_ordered():
    r = goals.project(1e6, "2036-11-01", 0, 5000, 0.6, today=TODAY)
    assert r["months"] == 120 and r["need"] == pytest.approx(1e6 * 1.06 ** 10)
    assert r["low"] < r["middle"] < r["high"] and r["put_in"] == 600_000


def test_monthly_for_likely_really_gives_about_three_in_four():
    r = goals.project(2e6, "2041-01-01", 1e5, 2000, 0.7, today=TODAY, seed=7)
    again = goals.project(2e6, "2041-01-01", 1e5, r["monthly_for_likely"], 0.7, today=TODAY, seed=7)
    assert again["chance"] == pytest.approx(0.75, abs=0.01)
    more = goals.project(2e6, "2041-01-01", 1e5, r["monthly_for_likely"] * 2, 0.7, today=TODAY, seed=7)
    assert more["chance"] > again["chance"]
    assert goals.project(2e6, "2041-01-01", 1e5, 2000, 0.7, today=TODAY, seed=7) == r  # repeatable


def test_already_enough_needs_nothing_more():
    r = goals.project(1e5, "2028-01-01", 1e6, 0, 0.0, today=TODAY)
    assert r["chance"] == 1 and r["monthly_for_likely"] == 0
    with pytest.raises(ValueError):
        goals.project(1e5, "2026-11-30", 0, 0, 0.5, today=TODAY)


def test_goal_endpoints():
    conn = db.connect(":memory:")
    auth.set_user(conn, "u", "correct-horse-battery")
    c = TestClient(api.create_app(conn, "s"))
    c.post("/api/login", json={"username": "u", "password": "correct-horse-battery"})
    g = {"name": "House", "target": 5e6, "target_date": "2040-04-01", "saved": 1e5, "monthly": 20000}
    assert c.post("/api/goals", json={**g, "target_date": "2000-01-01"}).status_code == 400
    assert c.post("/api/goals", json={**g, "target_date": "soon"}).status_code == 400
    assert c.post("/api/goals", json={**g, "equity_share": 2}).status_code == 400
    assert c.post("/api/goals", json=g).status_code == 200
    [got] = c.get("/api/goals").json()
    assert got["name"] == "House" and 0 <= got["projection"]["chance"] <= 1
    assert c.delete(f"/api/goals/{got['id']}").status_code == 200 and c.get("/api/goals").json() == []


def test_allocation_follows_time_and_nerve():
    short = goals.allocation(2, 0.5)
    assert short["equity"] == 0.2 and short["limited_by"] == "time"
    nervous = goals.allocation(20, 0.10)
    assert nervous["equity"] == 0.25 and nervous["limited_by"] == "nerve"
    long = goals.allocation(20, 0.5)
    assert long["equity"] == 0.75 and long["gold"] == 0.10 and long["debt"] == 0.15
    assert long["crash"] < nervous["crash"] < 0 < nervous["mean"] and long["crash"] == -0.75 * 0.55
    for a in (short, nervous, long):
        assert abs(a["equity"] + a["debt"] + a["gold"] - 1) < 1e-9


def test_asset_classes_and_current_mix():
    assert goals.asset_class("fund", "SBI Gold Fund", "Other Scheme - FoF Domestic") == "gold"
    assert goals.asset_class("fund", "HDFC Liquid Fund", "Debt Scheme - Liquid Fund") == "debt"
    assert goals.asset_class("fund", "ICICI Balanced Advantage", "Hybrid Scheme - Dynamic") == "hybrid"
    assert goals.asset_class("fund", "PPFAS Flexi", "Equity Scheme - Flexi Cap Fund") == "equity"
    conn = db.connect(":memory:")
    conn.execute("INSERT INTO funds (scheme_code, name, category, source, fetched_at) VALUES"
                 " ('1', 'Balanced', 'Hybrid Scheme - Aggressive Hybrid Fund', 't', 't')")
    mix = goals.current_mix(conn, [{"kind": "stock", "code": "TCS", "name": "TCS", "value": 50},
                                   {"kind": "fund", "code": "1", "name": "Balanced", "value": 50}])
    assert mix == {"equity": 0.75, "debt": 0.25, "gold": 0.0, "other": 0.0}
