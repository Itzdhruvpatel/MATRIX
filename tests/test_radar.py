from datetime import date, timedelta

from matrix import db, radar


def rows(n, daily=0.0, series="EQ", value=5e8, start=100.0, lock=False):
    out, price, d = [], start, date(2025, 6, 1)
    for _ in range(n):
        prev = price
        price *= 1 + daily
        out.append({"date": d.isoformat(), "close": price, "prev_close": prev,
                    "high": price if lock else price * 1.01, "value": value, "series": series})
        d += timedelta(days=1)
    return out


def rules(alerts):
    return {a["rule"]: a["level"] for a in alerts}


def test_quiet_stock_raises_nothing():
    assert radar.price_alerts(rows(260, 0.0005)) == []


def test_surveillance_series_is_danger():
    assert rules(radar.price_alerts(rows(30, series="BE"))) == {"surveillance": "danger"}


def test_big_one_day_move_and_monthly_fall():
    r = rows(60, 0.0)
    r[-1]["close"] = r[-1]["prev_close"] * 0.70          # -30% today
    got = rules(radar.price_alerts(r))
    assert got["big_day"] == "warning" and got["fall_month"] == "warning"


def test_pump_pattern_needs_thin_trading():
    thin = rows(40, 0.0, value=1e6) + []
    for r in thin[-5:]:
        r["close"] = r["prev_close"] * 1.05
        r["high"] = r["close"]
    assert rules(radar.price_alerts(thin)).get("pump") == "danger"
    busy = [dict(r, value=5e9) for r in thin]
    assert "pump" not in rules(radar.price_alerts(busy))


def test_near_year_low():
    assert rules(radar.price_alerts(rows(260, -0.003))).get("near_low") == "watch"


def ann(subject, desc="X has informed the Exchange", feed="Online_announcements"):
    return {"feed": feed, "subject": subject, "description": desc, "link": "http://x",
            "published_at": "2026-11-10T10:00:00"}


def test_announcement_rules():
    f = radar.announcement_alert
    assert f(ann("Change in Auditors", "regarding Resignation of Statutory Auditor"))["rule"] == "auditor_exit"
    assert f(ann("Credit Rating", "rating downgraded to BBB"))["level"] == "warning"
    assert f(ann("Credit Rating"))["level"] == "info"
    assert f(ann("Resignation", "Resignation of Chief Financial Officer"))["rule"] == "key_exit"
    assert f(ann("Disclosure of defaults on payment of interest"))["level"] == "danger"
    assert f(ann("Investor Presentation")) is None            # routine
    assert f(ann("Press Release", "appoints new auditor")) is None  # no resignation


def test_feed_and_corporate_action_alerts():
    p = radar.announcement_alert(ann(None, "NAME OF PROMOTER(S) OR PACS WITH HIM : ABC TRUST", "Sast_Regulation31"))
    assert p["rule"] == "pledge" and "ABC TRUST" in p["detail"]
    split = ann(None, "SERIES:EQ |PURPOSE:FACE VALUE SPLIT (SUB-DIVISION) - FROM RS 10 TO RE 1 |FACE VALUE:10", "Corporate_action")
    assert radar.announcement_alert(split)["rule"] == "corp_action"
    div = ann(None, "SERIES:EQ |PURPOSE:INTERIM DIVIDEND - RE 1 PER SHARE", "Corporate_action")
    assert radar.announcement_alert(div) is None


def test_deal_alerts_only_for_large_deals():
    big = {"date": "2026-11-13", "symbol": "A", "client": "BIG FUND", "side": "sell",
           "quantity": 1_000_000, "price": 500.0, "kind": "block"}
    small = dict(big, quantity=100)
    (a,) = radar.deal_alerts([big, small])
    assert a["rule"] == "deal_sell" and "50 crore sold" in a["title"]


def test_compute_stores_alerts_and_replaces_old_ones():
    conn = db.connect(":memory:")
    for r in rows(30, series="BZ"):
        conn.execute("INSERT INTO stock_prices (symbol, date, series, close, prev_close, high, value,"
                     " source, fetched_at) VALUES ('RISKY',?,?,?,?,?,?,'t','t')",
                     (r["date"], r["series"], r["close"], r["prev_close"], r["high"], r["value"]))
    last = rows(30)[-1]["date"]
    conn.execute("INSERT INTO announcements (id, feed, company, symbol, subject, description, link,"
                 " published_at, source, fetched_at) VALUES ('1','Online_announcements','Risky',"
                 "'RISKY','Change in Auditors','Resignation of Statutory Auditor','http://x',?,'t','t')",
                 (last + "T09:00:00",))
    for _ in range(2):
        n = radar.compute(conn)
    assert n == 2
    got = {r["rule"] for r in conn.execute("SELECT rule FROM alerts WHERE symbol='RISKY'")}
    assert got == {"surveillance", "auditor_exit"}


def test_patterns_new_high_cross_volume_and_gap():
    assert "high_52w" in rules(radar.pattern_alerts(rows(260, 0.001)))
    assert radar.pattern_alerts(rows(260, 0.001, value=1e6)) == []  # too thinly traded
    # Falls for 230 days, then jumps above the 200-day average on the last day.
    r = rows(230, -0.002) + rows(30, 0.0, start=rows(230, -0.002)[-1]["close"])
    r[-1] = {**r[-1], "close": r[-2]["close"] * 1.2, "value": 2e9, "open": r[-2]["close"] * 1.05}
    got = rules(radar.pattern_alerts(r))
    assert {"above_200", "volume_surge", "gap_up"} <= set(got) and set(got.values()) == {"info"}
    r = rows(260, 0.001)
    r[-1] = {**r[-1], "close": r[-2]["close"] * 0.8}
    assert "below_200" in rules(radar.pattern_alerts(r))


def test_scanner_endpoint_groups_todays_patterns():
    from fastapi.testclient import TestClient
    from matrix import api, auth
    conn = db.connect(":memory:")
    for sym, value in (("BUSY", 5e8), ("SMALL", 2e7)):
        for r in rows(260, 0.001, value=value):
            conn.execute("INSERT INTO stock_prices (symbol, date, name, series, close, prev_close, high,"
                         " value, source, fetched_at) VALUES (?,?,?,?,?,?,?,?,'t','t')",
                         (sym, r["date"], sym, r["series"], r["close"], r["prev_close"], r["high"], r["value"]))
    radar.compute(conn)
    auth.set_user(conn, "owner", "correct-horse-battery")
    c = TestClient(api.create_app(conn, "s"))
    c.post("/api/login", json={"username": "owner", "password": "correct-horse-battery"})
    s = c.get("/api/scanner").json()
    assert [x["symbol"] for x in s["groups"]["high_52w"]] == ["BUSY"] and s["counts"]["high_52w"] == 1
    s = c.get("/api/scanner", params={"min_traded_cr": 1}).json()
    assert s["counts"]["high_52w"] == 2
