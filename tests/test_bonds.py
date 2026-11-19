import pytest

from matrix import bonds


def test_par_bond_yields_its_coupon():
    r = bonds.analyse(0.07, 10, 100, per_year=2)
    assert r["ytm"] == pytest.approx(0.07, abs=1e-9) and r["current_yield"] == pytest.approx(0.07)
    assert r["payments"] == 20 and r["received"] == pytest.approx(170)


def test_discount_bond_and_rate_moves():
    r = bonds.analyse(0.06, 5, 95.0, per_year=1)
    # Price at the found yield must equal what was paid.
    assert bonds.price(bonds.cash_flows(0.06, 5, 1), r["ytm"], 1) == pytest.approx(95.0)
    assert r["ytm"] > 0.06
    assert r["rate_moves"]["+1%"] < 0 < r["rate_moves"]["-1%"]
    # Modified duration predicts the 1% move closely.
    assert r["rate_moves"]["+1%"] == pytest.approx(-r["modified_duration"] * 0.01, abs=0.003)


def test_zero_coupon_duration_is_its_life():
    assert bonds.analyse(0.0, 3, 80.0, per_year=1)["duration"] == pytest.approx(3)
    with pytest.raises(ValueError):
        bonds.analyse(0.07, 10, 100, per_year=3)


def test_bond_endpoint():
    from fastapi.testclient import TestClient
    from matrix import api, auth, db
    conn = db.connect(":memory:")
    auth.set_user(conn, "u", "correct-horse-battery")
    c = TestClient(api.create_app(conn, "s"))
    c.post("/api/login", json={"username": "u", "password": "correct-horse-battery"})
    assert c.get("/api/bond", params={"coupon": 0.071, "years": 10, "price": 100}).json()["ytm"] == pytest.approx(0.071)
    assert c.get("/api/bond", params={"coupon": 0.071, "years": 99, "price": 100}).status_code == 400
