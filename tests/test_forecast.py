from fastapi.testclient import TestClient

from matrix import api, auth, forecast, ledger, score
from tests.test_ledger import market  # noqa: F401  (fixture)


def test_fit_learns_a_simple_pattern():
    X = [[1.0, x / 10] for x in range(-10, 11)] * 5
    y = [1 if x[1] > 0 else 0 for x in X]
    w = forecast.fit(X, y)
    assert forecast.predict(w, [1.0, 0.8]) > 0.8
    assert forecast.predict(w, [1.0, -0.8]) < 0.2


def test_training_uses_only_outcomes_known_on_the_day(market):  # noqa: F811
    ledger.backfill(market, horizon=20)
    days = ledger.trading_days(market)
    for d in (days[159], days[179]):
        used = [s for s, _ in ledger.checked_dates(market, 20, until=d)]
        assert used and all(days[days.index(u) + 20] <= d for u in used)


def test_forecasts_logged_once_and_graded(market):  # noqa: F811
    ledger.backfill(market, horizon=20)
    made = forecast.backfill(market, horizon=20)
    assert made >= 1
    rows = [dict(r) for r in market.execute("SELECT * FROM forecasts")]
    assert all(r["backfilled"] == 1 and r["low"] <= r["high"] for r in rows)
    win = [r["prob"] for r in rows if r["symbol"].startswith("WIN")]
    lose = [r["prob"] for r in rows if r["symbol"].startswith("LOSE")]
    assert min(win) > 0.5 > max(lose)
    rec = ledger.forecast_record(market, horizon=20)
    assert rec["graded"] >= 10 and rec["live"] == 0
    assert rec["hit_rate"] == 1.0 and 0.5 <= rec["baseline"] <= 1
    # A logged forecast is never rewritten.
    d = rows[0]["date"]
    market.execute("UPDATE forecasts SET prob=0.123 WHERE date=? AND symbol=?", (d, rows[0]["symbol"]))
    forecast.compute(market, as_of=d, horizon=20)
    assert market.execute("SELECT prob FROM forecasts WHERE date=? AND symbol=?",
                          (d, rows[0]["symbol"])).fetchone()[0] == 0.123


def test_not_enough_history_means_no_forecast(market):  # noqa: F811
    days = ledger.trading_days(market)
    score.compute(market, as_of=days[150])
    assert forecast.compute(market, as_of=days[150], horizon=20) == 0
    assert ledger.forecast_record(market, horizon=20)["graded"] == 0


def test_forecast_endpoint_is_owner_only(market, monkeypatch):  # noqa: F811
    ledger.backfill(market, horizon=20)
    score.compute(market)
    forecast.backfill(market, horizon=20)
    auth.set_user(market, "owner", "correct-horse-battery")
    auth.set_user(market, "guest", "correct-horse-battery")
    c = TestClient(api.create_app(market, "s"))
    monkeypatch.setenv("MATRIX_OWNER", "owner")
    c.post("/api/login", json={"username": "guest", "password": "correct-horse-battery"})
    assert c.get("/api/forecast/WIN1").status_code == 403
    c.post("/api/login", json={"username": "owner", "password": "correct-horse-battery"})
    r = c.get("/api/forecast/WIN1").json()
    assert r["forecast"]["prob"] > 0.5 and "graded" in r["record"]
    assert c.get("/api/forecast/NOPE").json()["forecast"] is None



def test_kill_switch_needs_enough_days_and_a_losing_record():
    assert not forecast.paused({"graded": 0})
    assert not forecast.paused({"days": 2, "graded": 5000, "hit_rate": 0.3, "baseline": 0.6})  # too few
    assert not forecast.paused({"days": 3, "graded": 5000, "hit_rate": 0.62, "baseline": 0.6})
    assert forecast.paused({"days": 3, "graded": 5000, "hit_rate": 0.49, "baseline": 0.59})


def test_endpoint_hides_forecast_while_paused(market, monkeypatch):  # noqa: F811
    forecast.backfill(market, horizon=20)
    auth.set_user(market, "owner", "correct-horse-battery")
    c = TestClient(api.create_app(market, "s"))
    c.post("/api/login", json={"username": "owner", "password": "correct-horse-battery"})
    assert c.get("/api/forecast/WIN1").json()["paused"] is False
    monkeypatch.setattr(forecast, "paused", lambda recent: True)
    c = TestClient(api.create_app(market, "s"))  # fresh app: the record is cached per app
    c.post("/api/login", json={"username": "owner", "password": "correct-horse-battery"})
    r = c.get("/api/forecast/WIN1").json()
    assert r["paused"] is True and r["forecast"] is None and r["record"]["paused"] is True
