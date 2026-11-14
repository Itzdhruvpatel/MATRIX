from datetime import date

import pytest
from fastapi.testclient import TestClient

from matrix import api, auth, db, pipeline
from tests.test_sources import AMFI_TEXT, NSE_ROWS, nse_zip

SECRET = "test-secret"


@pytest.fixture
def client():
    conn = db.connect(":memory:")
    pipeline.load_stocks(conn, date(2026, 11, 13), fetch=lambda d: nse_zip(NSE_ROWS))
    pipeline.load_funds(conn, fetch=lambda: AMFI_TEXT)
    auth.set_user(conn, "owner", "correct-horse-battery")
    return TestClient(api.create_app(conn, SECRET))


def login(c, pw="correct-horse-battery"):
    return c.post("/api/login", json={"username": "owner", "password": pw})


def test_password_hash_roundtrip():
    h = auth.hash_password("abcdefghijk")
    assert auth.verify_password("abcdefghijk", h)
    assert not auth.verify_password("wrong", h)


def test_token_rejects_tampering_and_expiry():
    t = auth.make_token("owner", SECRET, now=1000)
    assert auth.read_token(t, SECRET, now=1001) == "owner"
    assert auth.read_token(t, "other-secret", now=1001) is None
    assert auth.read_token(t, SECRET, now=1000 + auth.SESSION_SECONDS + 1) is None
    assert auth.read_token("garbage", SECRET) is None


def test_short_password_rejected():
    with pytest.raises(ValueError):
        auth.set_user(db.connect(":memory:"), "x", "short")


def test_api_requires_login(client):
    assert client.get("/api/market/summary").status_code == 401
    assert login(client, "wrong").status_code == 401
    assert login(client).status_code == 200
    assert client.get("/api/me").json() == {"username": "owner"}


def test_login_lockout_after_repeated_failures(client):
    for _ in range(api.MAX_FAILS):
        login(client, "wrong")
    assert login(client).status_code == 429


def test_market_summary(client):
    login(client)
    s = client.get("/api/market/summary").json()
    assert s["date"] == "2026-11-13"
    assert s["breadth"]["adv"] == 1
    assert s["gainers"][0]["symbol"] == "RELIANCE"
    assert s["gainers"][0]["change_pct"] == pytest.approx(1.49, abs=0.01)


def test_stock_detail_and_search(client):
    login(client)
    d = client.get("/api/stocks/reliance").json()
    assert d["info"]["source"] == "nse_bhavcopy" and d["stats"]["last"] == 1339.70
    assert client.get("/api/stocks/NOPE").status_code == 404
    assert client.get("/api/stocks/search", params={"query": "relia"}).json()[0]["symbol"] == "RELIANCE"


def test_fund_search_and_detail(client):
    login(client)
    res = client.get("/api/funds/search", params={"query": "large cap"}).json()
    assert [r["scheme_code"] for r in res] == ["120465"]  # Direct only by default
    res = client.get("/api/funds/search", params={"query": "large cap", "direct_only": False}).json()
    assert len(res) == 2
    d = client.get("/api/funds/120465").json()
    assert d["navs"][0]["nav"] == 65.12


def test_health(client):
    login(client)
    h = client.get("/api/health").json()
    assert h["nse_bhavcopy"]["latest_date"] == "2026-11-13"
    assert h["runs"][0]["status"] == "ok"
