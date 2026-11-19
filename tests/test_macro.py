from fastapi.testclient import TestClient

from matrix import api, auth, db, pipeline
from matrix.sources import macro

PAGE = """<div>Policy Repo Rate : 5.50% Standing Deposit Facility Rate : 5.25%</div><td>CRR : 3.00%</td>
<td>SLR : 18.00%</td> INR / 1 USD : 93.3461 INR / 1 GBP : 122.6577 INR / 1 EUR : 102.3770
Savings Deposit Rate : 2.50% Term Deposit Rate &gt; 1 Year : 6.00% - 6.80%
6.94% GS 2036 : 7.2795% # 7.06% GS 2041 : 7.4488% 91 day T-bills : 5.8602%* 364 day T-bills : 6.6300%*"""


def test_parse_rbi_current_rates():
    v = macro.parse_rbi(PAGE)
    assert v == {"repo": 5.5, "crr": 3.0, "slr": 18.0, "usd_inr": 93.3461, "eur_inr": 102.377,
                 "gbp_inr": 122.6577, "fd_low": 6.0, "fd_high": 6.8, "savings": 2.5, "tbill_91": 5.8602,
                 "tbill_364": 6.63, "gsec_2036": 7.2795, "gsec_2041": 7.4488}


def test_load_and_compare_with_a_month_ago(monkeypatch):
    conn = db.connect(":memory:")

    def broken():
        raise OSError("NSE blocked")
    r = pipeline.load_macro(conn, lambda: PAGE, broken)
    assert r["status"] == "ok" and r["issues"] == 1  # RBI worked, VIX failed: keep what came in
    conn.execute("UPDATE macro SET date='2026-01-01'")
    conn.execute("INSERT INTO macro VALUES ('2026-02-15', 'repo', 5.25, 't', 't')")
    auth.set_user(conn, "u", "correct-horse-battery")
    c = TestClient(api.create_app(conn, "s"))
    c.post("/api/login", json={"username": "u", "password": "correct-horse-battery"})
    m = c.get("/api/macro").json()
    assert m["date"] == "2026-02-15" and m["values"]["repo"] == {"now": 5.25, "month_ago": 5.5}
    assert m["values"]["usd_inr"] == {"now": 93.3461, "month_ago": 93.3461}
