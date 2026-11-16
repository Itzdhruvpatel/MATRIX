import base64

import pytest
from fastapi.testclient import TestClient

from matrix import api, auth, cas, db, portfolio


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    c.execute("INSERT INTO stock_prices (symbol, date, isin, name, series, close, prev_close, source,"
              " fetched_at) VALUES ('TCS', '2026-11-13', 'INE467B01029', 'TCS LTD', 'EQ', 4000, 4000,"
              " 't', 't')")
    c.execute("INSERT INTO funds (scheme_code, name, isin_growth, source, fetched_at) VALUES"
              " ('122639', 'Parag Parikh Flexi Cap', 'INF879O01027', 't', 't')")
    c.execute("INSERT INTO fund_navs VALUES ('122639', '2026-11-13', 100.0, 't', 't')")
    return c


def tx(d, units, nav, amount=None):
    return {"date": d, "description": "x", "units": units, "nav": nav, "amount": amount,
            "type": "PURCHASE"}


def scheme(amfi="122639", isin="INF879O01027", open_=0, close=15, txs=None, advisor="ARN-1234"):
    return {"scheme": "Parag Parikh Flexi Cap Fund - Direct Growth", "advisor": advisor,
            "isin": isin, "amfi": amfi, "open": open_, "close": close,
            "valuation": {"date": "2026-11-13", "nav": 100, "value": close * 100},
            "transactions": txs if txs is not None else [
                tx("2025-01-10", 10, 80.0, 800.0),
                {"date": "2025-01-10", "description": "Stamp Duty", "units": None, "nav": None,
                 "amount": 0.04, "type": "STAMP_DUTY_TAX"},
                tx("2025-02-10", 10, 85.0, 850.0),
                tx("2025-06-10", -5, 90.0, -450.0)]}


def mf_cas(*schemes):
    return {"statement_period": {"from": "01-Jan-1990", "to": "13-Nov-2026"}, "file_type": "CAMS",
            "folios": [{"folio": "123/45", "amc": "PPFAS Mutual Fund", "schemes": list(schemes)}]}


def demat_cas(isin="INE467B01029"):
    return {"statement_period": {"from": "01-Oct-2026", "to": "31-Oct-2026"}, "file_type": "NSDL",
            "accounts": [{"name": "ZERODHA BROKING LIMITED", "type": "CDSL", "client_id": "1234",
                          "equities": [{"name": "TCS", "isin": isin, "num_shares": 3,
                                        "price": 3900, "value": 11700}],
                          "mutual_funds": []}]}


def test_mutual_fund_transactions_imported_with_folio(conn):
    r = cas.import_cas(conn, "u", mf_cas(scheme()))
    assert r["errors"] == [] and r["added"] == 3
    held = portfolio.holdings_qty(conn, "u")
    assert held[("fund", "122639")] == pytest.approx(15)
    notes = {t[0] for t in conn.execute("SELECT note FROM transactions")}
    assert notes == {"PPFAS Mutual Fund, folio 123/45, advisor ARN-1234"}
    sell = conn.execute("SELECT side, quantity, price FROM transactions WHERE side='sell'").fetchone()
    assert tuple(sell) == ("sell", 5, 90.0)
    assert r["holdings"][0]["source"].startswith("PPFAS Mutual Fund")


def test_fund_found_by_isin_when_amfi_code_missing(conn):
    r = cas.import_cas(conn, "u", mf_cas(scheme(amfi=None)))
    assert r["errors"] == [] and r["added"] == 3


def test_demat_stock_matched_by_isin_at_statement_date(conn):
    r = cas.import_cas(conn, "u", demat_cas())
    assert r["errors"] == [] and r["added"] == 1
    t = dict(conn.execute("SELECT code, side, date, quantity, price, note FROM transactions").fetchone())
    assert t == {"code": "TCS", "side": "buy", "date": "2026-10-31", "quantity": 3, "price": 3900,
                 "note": "Demat at ZERODHA BROKING LIMITED, client 1234 (purchase price not in statement)"}
    assert r["holdings_only"] == 1


def test_unknown_holding_blocks_everything_but_closed_unknown_is_skipped(conn):
    gone = scheme(amfi="999999", isin="INF000000000", close=0, txs=[tx("2020-01-01", 1, 10.0)])
    r = cas.import_cas(conn, "u", mf_cas(scheme(), gone))
    assert r["errors"] == [] and r["added"] == 3 and len(r["skipped"]) == 1
    conn.execute("DELETE FROM transactions")
    r = cas.import_cas(conn, "u", demat_cas(isin="INE000000000"))
    assert r["added"] == 0 and "not found" in r["errors"][0]
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0


def test_opening_balance_needs_full_history(conn):
    r = cas.import_cas(conn, "u", mf_cas(scheme(open_=4)))
    assert r["added"] == 0 and "from the start" in r["errors"][0]


def test_importing_twice_does_not_double(conn):
    cas.import_cas(conn, "u", mf_cas(scheme()))
    r = cas.import_cas(conn, "u", mf_cas(scheme()))
    assert r["added"] == 0 and r["already"] == 3 and r["errors"] == []
    assert portfolio.holdings_qty(conn, "u")[("fund", "122639")] == pytest.approx(15)


def test_api_cas_upload_never_echoes_password(conn, monkeypatch):
    auth.set_user(conn, "owner", "correct-horse-battery")
    c = TestClient(api.create_app(conn, "s"))
    c.post("/api/login", json={"username": "owner", "password": "correct-horse-battery"})
    seen = {}

    def fake_read(pdf, password):
        seen["args"] = (pdf, password)
        if password != "ABCDE1234F":
            raise cas.CasError("That password did not open the PDF.")
        return mf_cas(scheme())
    monkeypatch.setattr(cas, "read_pdf", fake_read)
    body = {"pdf": base64.b64encode(b"%PDF-fake").decode(), "password": "WRONG99999"}
    r = c.post("/api/portfolio/import-cas", json=body)
    assert r.status_code == 400 and "WRONG99999" not in r.text
    r = c.post("/api/portfolio/import-cas", json={**body, "password": "ABCDE1234F"})
    assert r.status_code == 200 and r.json()["added"] == 3
    assert seen["args"] == (b"%PDF-fake", "ABCDE1234F")
    assert "ABCDE1234F" not in str(list(conn.execute("SELECT * FROM transactions")))
