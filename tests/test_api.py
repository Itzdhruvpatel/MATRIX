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
    assert client.get("/api/me").json() == {"username": "owner", "ratings": True, "totp": False}


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
    assert d["navs"][-1]["nav"] == 65.12


def test_health(client):
    login(client)
    h = client.get("/api/health").json()
    assert h["nse_bhavcopy"]["latest_date"] == "2026-11-13"
    assert h["runs"][0]["status"] == "ok"


@pytest.fixture(autouse=True)
def offline_history(monkeypatch):
    payload = {"data": [{"date": "13-11-2025", "nav": "52.00"}, {"date": "12-11-2026", "nav": "64.00"}]}
    monkeypatch.setattr(pipeline.mfapi, "download", lambda code: payload)


def test_fund_detail_loads_history_and_stats(client, offline_history):
    login(client)
    d = client.get("/api/funds/120465").json()
    assert [n["date"] for n in d["navs"]] == ["2025-11-13", "2026-11-12", "2026-11-13"]
    assert d["stats"]["return_1y"] == pytest.approx(65.12 / 52 - 1, abs=1e-3)
    assert d["sources"] == ["amfi_navall", "mfapi"]


def test_portfolio_endpoints(client):
    login(client)
    tx = {"kind": "stock", "code": "RELIANCE", "side": "buy", "date": "2026-01-02", "quantity": 10, "price": 1200}
    assert client.post("/api/portfolio/transactions", json=tx).status_code == 200
    bad = client.post("/api/portfolio/transactions", json={**tx, "code": "NOPE"})
    assert bad.status_code == 400 and "unknown" in bad.json()["detail"]
    p = client.get("/api/portfolio").json()
    assert p["value"] == pytest.approx(13397) and len(p["holdings"]) == 1
    tx_id = p["transactions"][0]["id"]
    assert client.delete(f"/api/portfolio/transactions/{tx_id}").status_code == 200
    assert client.get("/api/portfolio").json()["holdings"] == []
    r = client.post("/api/portfolio/import", json={"csv": "type,code,side,date,quantity,price\nstock,RELIANCE,buy,2026-01-02,1,1000"})
    assert r.json()["added"] == 1


def test_compare(client, offline_history):
    login(client)
    c = client.get("/api/compare", params={"items": "stock:RELIANCE,fund:120465"}).json()
    assert [x["code"] for x in c] == ["RELIANCE", "120465"]
    assert client.get("/api/compare", params={"items": "bond:X"}).status_code == 400


def test_compare_uses_split_adjusted_prices(client):
    login(client)
    c = client.get("/api/compare", params={"items": "stock:RELIANCE"}).json()
    assert c[0]["history"][-1]["value"] == pytest.approx(1339.70)


def test_watchlist_and_alerts(client):
    from matrix import radar
    login(client)
    assert client.post("/api/watchlist", json={"kind": "stock", "code": "nope"}).status_code == 400
    assert client.post("/api/watchlist", json={"kind": "stock", "code": "reliance"}).status_code == 200
    conn = client.app.state.conn
    conn.execute("INSERT INTO alerts (symbol, date, rule, level, title, detail) VALUES"
                 " ('RELIANCE', '2026-11-13', 'pledge', 'warning', 'Promoters pledged shares', 'why'),"
                 " ('RELIANCE', '2026-11-13', 'deal_buy', 'info', 'Large deal', 'why'),"
                 " ('OTHER', '2026-11-13', 'auditor_exit', 'danger', 'Auditor resigned', 'why')")
    conn.commit()
    a = client.get("/api/alerts").json()
    assert [m["rule"] for m in a["mine"]] == ["pledge", "deal_buy"]   # worst first, only watched
    assert a["tracking"] == 1 and a["watchlist"][0]["code"] == "RELIANCE"
    assert [m["symbol"] for m in a["market"]] == ["OTHER", "RELIANCE"]
    d = client.get("/api/stocks/RELIANCE").json()
    assert d["watched"] is True and d["alerts"][0]["level"] == "warning"
    assert client.delete("/api/watchlist/stock/RELIANCE").status_code == 200
    assert client.get("/api/alerts").json()["mine"] == []


def test_pages_are_not_cached_but_api_is_untouched(client):
    assert client.get("/").headers["cache-control"] == "no-cache"
    assert client.get("/style.css").headers["cache-control"] == "no-cache"
    assert "cache-control" not in client.get("/api/me").headers


def test_market_summary_has_daily_history(client):
    login(client)
    h = client.get("/api/market/summary").json()["history"]
    assert h == [{"date": "2026-11-13", "adv": 1, "dec": 0, "total": 1}]


def test_practice_book_endpoints(client):
    login(client)
    tx = {"kind": "stock", "code": "RELIANCE", "side": "buy", "date": "2026-01-02", "quantity": 3, "price": 1200, "book": "paper"}
    assert client.post("/api/portfolio/transactions", json=tx).status_code == 200
    assert client.get("/api/portfolio").json()["holdings"] == []
    assert client.get("/api/portfolio", params={"book": "paper"}).json()["holdings"][0]["quantity"] == 3
    assert client.get("/api/portfolio", params={"book": "fantasy"}).status_code == 400


def test_insight_endpoints(client):
    login(client)
    client.post("/api/portfolio/transactions", json={"kind": "stock", "code": "RELIANCE", "side": "buy", "date": "2026-01-02", "quantity": 10, "price": 1200})
    m = client.get("/api/insights/mood").json()
    assert "level" in m
    s = client.get("/api/insights/scenario", params={"move": -0.2}).json()
    assert s["holdings"][0]["beta_known"] is False  # not enough history in the test data
    assert s["change"] == pytest.approx(-0.2 * s["value"])
    assert client.get("/api/insights/scenario", params={"move": -2}).status_code == 400
    t = client.get("/api/insights/tax").json()
    assert t["short_term_gain"] == pytest.approx(10 * (1339.70 - 1200))
    assert client.get("/api/ledger").json()["periods"] == []


def test_journal_flow(client):
    login(client)
    bad = client.post("/api/journal", json={"code": "NOPE", "note": "x", "review_on": "2026-12-01"})
    assert bad.status_code == 400
    ok = client.post("/api/journal", json={"code": "reliance", "note": "Strong retail growth", "sell_if": "Debt doubles", "review_on": "2020-01-01"})
    assert ok.status_code == 200
    (e,) = client.get("/api/journal").json()
    assert e["code"] == "RELIANCE" and e["due"] is True
    assert client.post(f"/api/journal/{e['id']}/reviewed").status_code == 200
    assert client.get("/api/journal").json()[0]["due"] is False
    assert client.delete(f"/api/journal/{e['id']}").status_code == 200
    assert client.get("/api/journal").json() == []


def test_signup_disabled_by_default(client):
    assert client.get("/api/config").json() == {"signup": False}
    assert client.post("/api/signup", json={"username": "newbie", "password": "a-long-password"}).status_code == 403


def test_signup_and_owner_only_ratings(client, monkeypatch):
    monkeypatch.setenv("MATRIX_SIGNUP", "1")
    monkeypatch.setenv("MATRIX_OWNER", "owner")
    assert client.post("/api/signup", json={"username": "Bad Name!", "password": "a-long-password"}).status_code == 400
    assert client.post("/api/signup", json={"username": "newbie", "password": "short"}).status_code == 400
    r = client.post("/api/signup", json={"username": "Newbie", "password": "a-long-password"})
    assert r.status_code == 200 and r.json()["username"] == "newbie"
    assert client.get("/api/me").json() == {"username": "newbie", "ratings": False, "totp": False}
    assert client.get("/api/scores").status_code == 403
    assert client.get("/api/ledger").status_code == 403
    assert client.get("/api/stocks/RELIANCE").json()["score"] is None
    assert client.post("/api/signup", json={"username": "newbie", "password": "a-long-password"}).status_code == 409
    login(client)  # the owner still sees ratings
    assert client.get("/api/me").json()["ratings"] is True
    assert client.get("/api/scores").status_code == 200


def test_signup_rate_limit_per_visitor(client, monkeypatch):
    monkeypatch.setenv("MATRIX_SIGNUP", "1")
    monkeypatch.setenv("MATRIX_TRUST_PROXY", "1")
    for i in range(api.MAX_SIGNUPS_PER_HOUR):
        ok = client.post("/api/signup", json={"username": f"u{i}xx", "password": "a-long-password"},
                         headers={"x-forwarded-for": "1.1.1.1"})
        assert ok.status_code == 200
    blocked = client.post("/api/signup", json={"username": "u9xx", "password": "a-long-password"}, headers={"x-forwarded-for": "1.1.1.1"})
    assert blocked.status_code == 429
    other = client.post("/api/signup", json={"username": "u8xx", "password": "a-long-password"}, headers={"x-forwarded-for": "2.2.2.2"})
    assert other.status_code == 200
