import os

import pytest

from matrix import db


def test_to_pg_converts_placeholders_and_escapes_percent():
    assert db.to_pg("SELECT * FROM t WHERE a=? AND b LIKE '%Direct%'") == \
        "SELECT * FROM t WHERE a=%s AND b LIKE '%%Direct%%'"
    assert db.to_pg("INSERT INTO t (a, b) VALUES (:symbol, :date)") == \
        "INSERT INTO t (a, b) VALUES (%(symbol)s, %(date)s)"
    assert db.to_pg("SELECT '10:30'::text") == "SELECT '10:30'::text"  # casts left alone


def test_pg_schema_uses_postgres_types():
    stmts = db.pg_schema()
    joined = " ".join(stmts)
    assert "BIGSERIAL PRIMARY KEY" in joined and "DOUBLE PRECISION" in joined
    assert " REAL" not in joined and "INTEGER" not in joined
    assert all(not s.endswith(";") for s in stmts)


def test_row_behaves_like_sqlite_row():
    r = db.Row((1, "TCS"), ["id", "code"])
    assert r[0] == 1 and r["code"] == "TCS"
    assert dict(r) == {"id": 1, "code": "TCS"}
    a, b = r
    assert (a, b) == (1, "TCS")
    assert dict([db.Row(("x", 2), ["k", "v"])]) == {"x": 2}


def test_sqlite_used_when_no_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db.connect(":memory:").execute("SELECT 1").fetchone()[0] == 1


@pytest.mark.skipif(not os.environ.get("MATRIX_TEST_PG"), reason="set MATRIX_TEST_PG to a PostgreSQL URL")
def test_postgres_round_trip(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["MATRIX_TEST_PG"])
    c = db.connect()
    c.execute("DELETE FROM watchlist WHERE username='__test__'")
    c.execute("INSERT INTO watchlist (username, kind, code, added_at) VALUES (?,?,?,CURRENT_TIMESTAMP)"
              " ON CONFLICT DO NOTHING", ("__test__", "stock", "TCS"))
    row = c.execute("SELECT username, code FROM watchlist WHERE username=?", ("__test__",)).fetchone()
    assert row["code"] == "TCS" and dict(row)["username"] == "__test__"
    c.execute("DELETE FROM watchlist WHERE username='__test__'")
