import pytest
from cryptography.fernet import Fernet

from matrix import auth, backup, db


def test_backup_restores_every_row_and_needs_the_key(tmp_path):
    conn = db.connect(":memory:")
    auth.set_user(conn, "owner", "correct-horse-battery")
    conn.execute("INSERT INTO watchlist VALUES ('owner', 'stock', 'TCS', 'now')")
    conn.execute("INSERT INTO levels (username, symbol, stop, target) VALUES ('owner', 'TCS', 1.5, NULL)")
    conn.commit()
    key = Fernet.generate_key()
    path = backup.make(conn, tmp_path, key)
    assert b"owner" not in path.read_bytes()  # encrypted, not just compressed
    got = backup.restore(path, str(tmp_path / "out.db"), key)
    assert got["users"] == 1 and got["watchlist"] == 1 and set(got) == set(backup.TABLES)
    out = db.connect(str(tmp_path / "out.db"))
    assert out.execute("SELECT stop, target FROM levels").fetchone()[:] == (1.5, None)
    out.close()
    with pytest.raises(ValueError, match="does not open"):
        backup.restore(path, str(tmp_path / "other.db"), Fernet.generate_key())
    with pytest.raises(ValueError, match="already has data"):
        backup.restore(path, str(tmp_path / "out.db"), key)
    t = backup.test(tmp_path, key)
    assert t["ok"] and t["rows"] == 3 and t["integrity"] == "ok"


def test_keeps_the_newest_and_reports_no_backup(tmp_path):
    conn = db.connect(":memory:")
    key = Fernet.generate_key()
    for i in range(backup.KEEP + 3):
        (tmp_path / f"matrix-2026-01-{i:02d}-000000.backup").write_bytes(b"x")
    backup.make(conn, tmp_path, key)
    assert len(list(tmp_path.glob("*.backup"))) == backup.KEEP
    assert backup.test(tmp_path / "empty", key) == {"ok": False, "problem": "No backup yet"}
    (tmp_path / "matrix-2099-01-01-000000.backup").write_bytes(b"broken")
    assert not backup.test(tmp_path, key)["ok"]


def test_nightly_logs_and_a_failure_shows_in_the_banner(tmp_path, monkeypatch):
    from matrix import pipeline
    conn = db.connect(":memory:")
    key = Fernet.generate_key()
    assert backup.nightly(conn, tmp_path, key)["status"] == "ok"
    assert not [p for p in pipeline.data_problems(conn) if p["what"] == "backup"]
    monkeypatch.setattr(backup, "dump", lambda c: (_ for _ in ()).throw(OSError("disk full")))
    assert backup.nightly(conn, tmp_path, key) == {"status": "error", "message": "disk full"}
    probs = [p for p in pipeline.data_problems(conn) if p["what"] == "backup"]
    assert probs and probs[0]["detail"] == "disk full"
