"""Encrypted backups of every table, and a restore test.

Run: python -m matrix.backup            make a backup now (keeps the newest 7)
     python -m matrix.backup --test     restore the newest backup into a temporary file and check it
     python -m matrix.backup --restore FILE OUT.db   rebuild a SQLite database from a backup

Works the same on SQLite and PostgreSQL. The key is MATRIX_BACKUP_KEY (from the environment or
.env, made on first run). Keep a copy of it somewhere other than this computer: without the key
a backup cannot be opened.
"""
import gzip
import io
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from matrix import db

DIR = db.DEFAULT_PATH.parent / "backups"
KEEP = 7  # about 50 MB each with one year of prices
SOURCE = "backup"
ENV = Path(__file__).resolve().parent.parent / ".env"
TABLES = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", db.SCHEMA)
BATCH = 5000
NL = b"\n"


def load_key() -> bytes:
    from cryptography.fernet import Fernet
    key = os.environ.get("MATRIX_BACKUP_KEY")
    if not key and ENV.exists():
        key = next((line.split("=", 1)[1].strip() for line in ENV.read_text().splitlines()
                    if line.startswith("MATRIX_BACKUP_KEY=")), None)
    if not key:
        key = Fernet.generate_key().decode()
        with ENV.open("a") as f:
            f.write(f"\nMATRIX_BACKUP_KEY={key}\n")
        print(f"Made a new backup key and saved it in {ENV}. Copy it somewhere safe too.")
    return key.encode()


def dump(conn) -> bytes:
    """Every table as gzip-compressed JSON lines: a header line per table, then one line per row,
    and a last line with the row counts so a restore can prove nothing went missing."""
    buf, counts = io.BytesIO(), {}
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        for table in TABLES:
            cur = conn.execute(f"SELECT * FROM {table}")
            cols = [c[0] for c in cur.description]
            gz.write(json.dumps({"table": table, "columns": cols}).encode() + NL)
            counts[table] = 0
            for row in cur:
                gz.write(json.dumps(list(row)).encode() + NL)
                counts[table] += 1
        gz.write(json.dumps({"counts": counts}).encode() + NL)
    return buf.getvalue()


def load(data: bytes, conn) -> dict[str, int]:
    """Rows from dump() into an empty database with the Matrix schema. Returns rows per table."""
    counts, table, sql, batch, expected = {}, None, None, [], None

    def flush():
        if batch:
            conn.executemany(sql, batch)
            batch.clear()

    for line in gzip.decompress(data).splitlines():
        item = json.loads(line)
        if isinstance(item, dict) and "counts" in item:
            expected = item["counts"]
        elif isinstance(item, dict):
            flush()
            table, cols = item["table"], item["columns"]
            sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
            counts[table] = 0
        else:
            batch.append(item)
            counts[table] += 1
            if len(batch) >= BATCH:
                flush()
    flush()
    conn.commit()
    if counts != expected:
        raise ValueError("The backup is incomplete: row counts do not match")
    return counts


def make(conn, folder: Path = DIR, key: bytes | None = None) -> Path:
    from cryptography.fernet import Fernet
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"matrix-{datetime.now():%Y-%m-%d-%H%M%S}.backup"
    path.write_bytes(Fernet(key or load_key()).encrypt(dump(conn)))
    for old in sorted(folder.glob("matrix-*.backup"))[:-KEEP]:
        old.unlink()
    return path


def restore(path: Path, out: str, key: bytes | None = None) -> dict[str, int]:
    from cryptography.fernet import Fernet, InvalidToken
    try:
        data = Fernet(key or load_key()).decrypt(path.read_bytes())
    except InvalidToken:
        raise ValueError("This backup does not open with this key") from None
    conn = db.connect(out)
    try:
        if any(conn.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone() for t in TABLES):
            raise ValueError(f"{out} already has data; restore into a new file")
        return load(data, conn)
    finally:
        conn.close()


def latest(folder: Path = DIR) -> Path | None:
    files = sorted(folder.glob("matrix-*.backup"))
    return files[-1] if files else None


def test(folder: Path = DIR, key: bytes | None = None) -> dict:
    """Restore the newest backup into a temporary file and check every table came back whole."""
    path = latest(folder)
    if not path:
        return {"ok": False, "problem": "No backup yet"}
    with tempfile.TemporaryDirectory() as tmp:
        out = str(Path(tmp) / "restored.db")
        try:
            got = restore(path, out, key)
        except ValueError as e:
            return {"ok": False, "file": path.name, "problem": str(e)}
        check = db.connect(out)
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        check.close()
    missing = sorted(set(TABLES) - set(got))
    ok = integrity == "ok" and not missing
    return {"ok": ok, "file": path.name, "rows": sum(got.values()), "integrity": integrity,
            "problem": None if ok else f"integrity {integrity}, missing tables {missing}"}


def nightly(conn, folder: Path = DIR, key: bytes | None = None) -> dict:
    """Back up, then prove the backup restores. Logged like any data job, so failures show."""
    from matrix import pipeline
    started = pipeline.now()
    try:
        path = make(conn, folder, key)
        t = test(folder, key)
        status = "ok" if t["ok"] else "error"
        message = f"{path.name}, {t['rows']:,} rows restored" if t["ok"] else t["problem"]
    except Exception as e:  # any failure must reach the banner, not stop the daily loop
        status, message = "error", str(e)
    pipeline._log_run(conn, SOURCE, pipeline.today_ist().isoformat(), status, 0, 0, message, started)
    return {"status": status, "message": message}


if __name__ == "__main__":
    if "--restore" in sys.argv:
        src, out = sys.argv[sys.argv.index("--restore") + 1:][:2]
        print(f"Restored {sum(restore(Path(src), out).values()):,} rows into {out}")
    elif "--test" in sys.argv:
        print(test())
    else:
        print(nightly(db.connect()))
