from fastapi.testclient import TestClient

from matrix import api, auth, db, pipeline
from matrix.sources import nse_flows

SAMPLE = [{"buyValue": "17651.5", "category": "DII", "date": "19-Nov-2026", "netValue": "-1356.57", "sellValue": "19008.07"},
          {"buyValue": "20706.95", "category": "FII/FPI", "date": "19-Nov-2026", "netValue": "7411.41", "sellValue": "13295.54"}]


def test_parse():
    rows = nse_flows.parse(SAMPLE)
    assert rows[1] == {"date": "2026-11-19", "who": "FII", "buy": 20706.95, "sell": 13295.54, "net": 7411.41}
    assert rows[0]["who"] == "DII" and nse_flows.parse([{**SAMPLE[0], "category": "Other"}]) == []


def test_load_keeps_each_day_and_logs_failures():
    conn = db.connect(":memory:")
    assert pipeline.load_flows(conn, lambda: SAMPLE)["rows"] == 2
    assert pipeline.load_flows(conn, lambda: SAMPLE)["rows"] == 2  # same day again: updated, not doubled
    older = [{**s, "date": "18-Nov-2026", "netValue": "100"} for s in SAMPLE]
    pipeline.load_flows(conn, lambda: older)
    assert conn.execute("SELECT COUNT(*) FROM fii_dii").fetchone()[0] == 4

    def broken():
        raise OSError("blocked")
    assert pipeline.load_flows(conn, broken)["status"] == "error"

    auth.set_user(conn, "u", "correct-horse-battery")
    c = TestClient(api.create_app(conn, "s"))
    c.post("/api/login", json={"username": "u", "password": "correct-horse-battery"})
    f = c.get("/api/flows").json()
    assert [d["date"] for d in f["days"]] == ["2026-11-19", "2026-11-18"]
    assert f["days"][0]["FII"]["net"] == 7411.41 and f["total"]["FII"] == 7511.41
