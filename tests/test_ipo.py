import pytest

from matrix import db, ipo

CURRENT = [{"companyName": "Crystal Crop", "issueEndDate": "20-Nov-2026", "issuePrice": "Rs.259 to Rs.272",
            "issueStartDate": "18-Nov-2026", "series": "Equity", "symbol": "CRYSTALCP", "category": "Total",
            "noOfTime": "1.63"},
           {"companyName": "Crystal Crop", "category": "Retail", "noOfTime": "3.0"},
           {"companyName": "Watrana", "issueEndDate": "23-Nov-2026", "issuePrice": "Rs.232 to Rs.245",
            "issueStartDate": "19-Nov-2026", "series": "SME", "symbol": "WATRANA", "noOfTime": None}]
PAST = [{"companyName": "Up Ltd", "issuePrice": "100", "listingDate": "09-NOV-2026", "symbol": "UP",
         "securityType": "EQ"},
        {"companyName": "Down Ltd", "issuePrice": "Rs.90 to Rs.100", "listingDate": "06-NOV-2026", "symbol": "DOWN",
         "securityType": "SME"},
        {"companyName": "Unknown", "issuePrice": "50", "listingDate": "01-NOV-2026", "symbol": "NOPE"}]


def test_current_issues():
    got = ipo.current(CURRENT)
    assert [g["symbol"] for g in got] == ["CRYSTALCP", "WATRANA"]  # category rows other than Total skipped
    assert got[0]["opens"] == "2026-11-18" and got[0]["subscribed"] == 1.63 and not got[0]["sme"]
    assert got[1]["sme"] and got[1]["subscribed"] is None


def test_past_issues_measured_with_own_prices():
    conn = db.connect(":memory:")
    for sym, day, close in (("UP", "2026-11-09", 120), ("UP", "2026-11-19", 150),
                            ("DOWN", "2026-11-06", 95), ("DOWN", "2026-11-19", 80)):
        conn.execute("INSERT INTO stock_prices (symbol, date, series, close, prev_close, source, fetched_at)"
                     " VALUES (?,?,'EQ',?,?,'t','t')", (sym, day, close, close))
    p = ipo.past(conn, PAST)
    assert p["count"] == 2 and p["below_issue"] == 0.5
    up, down = p["rows"]
    assert up["listing_day"] == pytest.approx(0.2) and up["since"] == pytest.approx(0.5)
    assert down["issue_price"] == 100 and down["since"] == pytest.approx(-0.2) and down["sme"]
