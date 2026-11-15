import pytest

from matrix import db, portfolio


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    for sym, close in (("TCS", 4000.0), ("INFY", 1500.0)):
        c.execute("INSERT INTO stock_prices (symbol, date, name, series, close, prev_close, source,"
                  " fetched_at) VALUES (?, '2026-11-13', ?, 'EQ', ?, ?, 't', 't')",
                  (sym, f"{sym} LTD", close, close))
    c.execute("INSERT INTO funds (scheme_code, name, source, fetched_at) VALUES ('122639',"
              " 'Parag Parikh Flexi Cap', 't', 't')")
    c.execute("INSERT INTO fund_navs VALUES ('122639', '2026-11-13', 100.0, 't', 't')")
    return c


def buy(code, qty, price, d="2025-11-13", kind="stock", side="buy"):
    return {"kind": kind, "code": code, "side": side, "date": d, "quantity": qty, "price": price}


def test_add_validates(conn):
    assert portfolio.add(conn, "u", buy("NOPE", 1, 10)) == "unknown stock 'NOPE'"
    assert "only 0 held" in portfolio.add(conn, "u", buy("TCS", 1, 10, side="sell"))
    assert "future" in portfolio.add(conn, "u", buy("TCS", 1, 10, d="2999-01-01"))
    assert portfolio.add(conn, "u", buy("tcs", 1, 3000)) is None  # lower case accepted


def test_summary_gains_xirr_and_concentration(conn):
    portfolio.add(conn, "u", buy("TCS", 10, 3200))                 # 32,000 -> 40,000
    portfolio.add(conn, "u", buy("122639", 100, 80, kind="fund"))  # 8,000 -> 10,000
    s = portfolio.summary(conn, "u")
    assert s["invested"] == 40000 and s["value"] == 50000
    assert s["gain_pct"] == pytest.approx(0.25)
    assert s["xirr"] == pytest.approx(0.25, abs=0.01)  # exactly one year
    assert s["allocation"] == {"stock": 0.8, "fund": 0.2}
    assert "TCS is 80.0%" in s["warnings"][0]["text"]
    assert s["holdings"][0]["name"] == "TCS LTD"


def test_partial_sell_uses_average_cost(conn):
    portfolio.add(conn, "u", buy("INFY", 10, 1000, d="2025-01-01"))
    portfolio.add(conn, "u", buy("INFY", 10, 1400, d="2025-06-01"))   # avg 1200
    portfolio.add(conn, "u", buy("INFY", 5, 1600, d="2025-09-01", side="sell"))
    s = portfolio.summary(conn, "u")
    (h,) = s["holdings"]
    assert h["quantity"] == 15 and h["avg_cost"] == pytest.approx(1200)
    assert s["realised_gain"] == pytest.approx(2000)  # 5 x (1600 - 1200)


def test_users_are_separate(conn):
    portfolio.add(conn, "a", buy("TCS", 1, 3000))
    assert portfolio.summary(conn, "b")["holdings"] == []


def test_import_csv_all_or_nothing(conn):
    good = "type,code,side,date,quantity,price\nstock,TCS,buy,2025-01-01,2,3000\nfund,122639,buy,2025-02-01,10,90\n"
    assert portfolio.import_csv(conn, "u", good) == {"added": 2, "errors": []}
    bad = "type,code,side,date,quantity,price\nstock,INFY,buy,2025-01-01,1,1000\nstock,XYZ,buy,2025-01-01,1,10\n"
    r = portfolio.import_csv(conn, "u", bad)
    assert r["added"] == 0 and "line 3" in r["errors"][0]
    assert len(portfolio.summary(conn, "u")["holdings"]) == 2  # INFY not added
    assert "header" in portfolio.import_csv(conn, "u", "a,b\n1,2")["errors"][0]


def test_paper_book_is_separate_from_real(conn):
    portfolio.add(conn, "u", buy("TCS", 5, 3000))
    assert portfolio.add(conn, "u", {**buy("TCS", 2, 3500), "book": "paper"}) is None
    assert portfolio.summary(conn, "u")["holdings"][0]["quantity"] == 5
    assert portfolio.summary(conn, "u", "paper")["holdings"][0]["quantity"] == 2
    # cannot sell practice shares you do not hold in the practice book
    assert "only 2 held" in portfolio.add(conn, "u", {**buy("TCS", 3, 4000, side="sell"), "book": "paper"})
    assert "book must be" in portfolio.add(conn, "u", {**buy("TCS", 1, 1), "book": "fantasy"})


def test_old_database_gets_book_column(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE transactions (id INTEGER PRIMARY KEY, username TEXT NOT NULL, kind TEXT NOT NULL,"
                " code TEXT NOT NULL, side TEXT NOT NULL, date TEXT NOT NULL, quantity REAL NOT NULL,"
                " price REAL NOT NULL, note TEXT, created_at TEXT)")
    old.execute("INSERT INTO transactions (username, kind, code, side, date, quantity, price) VALUES"
                " ('u','stock','TCS','buy','2025-01-01',1,100)")
    old.commit(); old.close()
    c = db.connect(path)
    assert c.execute("SELECT book FROM transactions").fetchone()[0] == "real"
