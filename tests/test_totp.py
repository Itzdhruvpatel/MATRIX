import base64
import time

import pytest
from fastapi.testclient import TestClient

from matrix import api, auth, db

# RFC 6238 appendix B: (time, SHA1, SHA256, SHA512), 8 digits, 30 second steps.
VECTORS = [
    (59, "94287082", "46119246", "90693936"),
    (1111111109, "07081804", "68084774", "25091201"),
    (1111111111, "14050471", "67062674", "99943326"),
    (1234567890, "89005924", "91819424", "93441116"),
    (2000000000, "69279037", "90698825", "38618901"),
    (20000000000, "65353130", "77737706", "47863826"),
]
KEYS = {"sha1": b"12345678901234567890", "sha256": b"12345678901234567890123456789012",
        "sha512": b"1234567890123456789012345678901234567890123456789012345678901234"}


@pytest.mark.parametrize("t,sha1,sha256,sha512", VECTORS)
def test_rfc6238_vectors(t, sha1, sha256, sha512):
    for algo, want in (("sha1", sha1), ("sha256", sha256), ("sha512", sha512)):
        assert auth.totp(KEYS[algo], t, digits=8, digest=algo) == want


def test_verify_allows_one_step_of_clock_drift_and_blocks_replay():
    secret = auth.new_totp_secret()
    key = base64.b32decode(secret)
    now = 1_700_000_000
    code = auth.totp(key, now - 30)
    step = auth.check_totp(secret, code, now=now)
    assert step == (now - 30) // 30
    assert auth.check_totp(secret, code, now=now, after=step) is None  # same code twice
    assert auth.check_totp(secret, auth.totp(key, now - 90), now=now) is None  # too old
    assert auth.check_totp(secret, "abc", now=now) is None


def test_two_step_login_flow(monkeypatch):
    clock = [1_700_000_000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    conn = db.connect(":memory:")
    auth.set_user(conn, "owner", "correct-horse-battery")
    c = TestClient(api.create_app(conn, "s"))
    creds = {"username": "owner", "password": "correct-horse-battery"}
    c.post("/api/login", json=creds)
    assert c.get("/api/me").json()["totp"] is False

    setup = c.post("/api/totp/setup").json()
    assert setup["uri"].startswith("otpauth://totp/Matrix:owner?secret=") and "<svg" in setup["qr"]
    key = base64.b32decode(setup["secret"])
    assert c.post("/api/totp/enable", json={"code": "000000"}).status_code == 400
    assert c.post("/api/totp/enable", json={"code": auth.totp(key, clock[0])}).status_code == 200
    assert c.get("/api/me").json()["totp"] is True

    c.post("/api/logout")
    r = c.post("/api/login", json=creds)
    assert r.status_code == 200 and r.json() == {"need_code": True}
    assert c.get("/api/me").status_code == 401  # password alone is not enough
    assert c.post("/api/login", json={**creds, "code": "123456"}).status_code == 401
    # The code used to switch it on cannot be used again; the next one works.
    assert c.post("/api/login", json={**creds, "code": auth.totp(key, clock[0])}).status_code == 401
    clock[0] += 30
    assert c.post("/api/login", json={**creds, "code": auth.totp(key, clock[0])}).status_code == 200
    assert c.get("/api/me").json()["username"] == "owner"

    clock[0] += 30
    bad = c.post("/api/totp/disable", json={"password": "wrong-password", "code": auth.totp(key, clock[0])})
    assert bad.status_code == 400
    ok = c.post("/api/totp/disable", json={"password": creds["password"], "code": auth.totp(key, clock[0])})
    assert ok.status_code == 200 and c.get("/api/me").json()["totp"] is False
    c.post("/api/logout")
    assert c.post("/api/login", json=creds).json() == {"username": "owner"}
