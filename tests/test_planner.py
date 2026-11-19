import pytest
from fastapi.testclient import TestClient

from matrix import api, auth, db, planner
from tests.test_ledger import fill


def wavy(i):
    return 0.02 if i % 2 else -0.0195  # swings 2% a day, almost no trend


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    fill(c, "SWING", wavy, n=260)
    fill(c, "RISE", lambda i: 0.01, n=260)
    return c


def test_first_hit():
    assert planner.first_hit([101, 95, 120], 100, 96, 110) == ("stop", pytest.approx(-0.05))
    assert planner.first_hit([101, 111], 100, 96, 110)[0] == "target"
    assert planner.first_hit([101, 102], 100, 96, 110) == ("neither", pytest.approx(0.02))


def test_size_from_most_you_can_lose(conn):
    p = planner.plan(conn, "SWING", entry=100, stop=95, target=110, risk=1000, capital=100_000)
    assert p["shares"] == 200 and p["money"] == 20_000 and p["loss"] == 1000 and p["gain"] == 2000
    assert p["reward_risk"] == 2 and p["share_of_capital"] == 0.2


def test_defaults_put_stop_two_typical_moves_below(conn):
    p = planner.plan(conn, "SWING")
    assert p["typical_move"] == pytest.approx(0.02, abs=0.001)
    assert p["stop"] == pytest.approx(p["entry"] * 0.96, rel=0.01)
    assert p["target"] - p["entry"] == pytest.approx(2 * (p["entry"] - p["stop"]), abs=0.02)


def test_time_machine_odds_add_up_and_are_repeatable(conn):
    a = planner.plan(conn, "SWING", entry=100, stop=97, target=106)
    s = a["simulated"]
    assert s["runs"] == planner.PATHS
    assert s["target"] + s["stop"] + s["neither"] == pytest.approx(1)
    assert s["stop"] > s["target"]  # the stop is closer, so it is reached more often
    assert planner.plan(conn, "SWING", entry=100, stop=97, target=106)["simulated"] == s
    # A stock that only went up: on its real past, the target always came first.
    h = planner.plan(conn, "RISE", stop=1, target=1e9)["history"]
    assert h["neither"] == 1
    h = planner.plan(conn, "RISE")["history"]
    assert h["target"] == 1


def test_bad_levels_and_unknown_stock(conn):
    with pytest.raises(ValueError):
        planner.plan(conn, "SWING", entry=100, stop=101)
    with pytest.raises(LookupError):
        planner.plan(conn, "NOPE")


def test_plan_endpoint_and_saved_levels(conn, monkeypatch):
    auth.set_user(conn, "owner", "correct-horse-battery")
    auth.set_user(conn, "guest", "correct-horse-battery")
    c = TestClient(api.create_app(conn, "s"))
    monkeypatch.setenv("MATRIX_OWNER", "owner")
    c.post("/api/login", json={"username": "guest", "password": "correct-horse-battery"})
    p = c.get("/api/plan/swing", params={"risk": 500}).json()
    assert p["shares"] > 0 and "simulated" not in p  # sizing yes, odds only for the owner
    assert c.get("/api/plan/SWING", params={"stop": 1e6}).status_code == 400
    assert c.get("/api/plan/NOPE").status_code == 404
    assert c.put("/api/levels/SWING", json={"stop": 90, "target": 80}).status_code == 400
    assert c.put("/api/levels/SWING", json={"stop": 90, "target": 120}).status_code == 200
    assert c.put("/api/levels/SWING", json={"stop": 91, "target": 121}).status_code == 200
    p = c.get("/api/plan/SWING").json()
    assert (p["stop"], p["target"]) == (91, 121) and p["saved"] == {"stop": 91, "target": 121}
    c.delete("/api/levels/SWING")
    assert c.get("/api/plan/SWING").json()["saved"] is None
    c.post("/api/login", json={"username": "owner", "password": "correct-horse-battery"})
    assert "simulated" in c.get("/api/plan/SWING").json()
