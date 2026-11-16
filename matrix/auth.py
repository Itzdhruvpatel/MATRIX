"""Password hashing, signed session tokens and two-step login codes (stdlib only).

Create or reset a user:  python -m matrix.auth USERNAME
"""
import base64
import getpass
import hashlib
import hmac
import secrets
import struct
import sys
import time
from urllib.parse import quote

ITERATIONS = 600_000
SESSION_SECONDS = 12 * 3600
TOTP_STEP = 30


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
    except ValueError:
        return False
    test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
    return hmac.compare_digest(test.hex(), digest)


def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_token(username: str, secret: str, now: float | None = None) -> str:
    expires = int((now or time.time()) + SESSION_SECONDS)
    payload = base64.urlsafe_b64encode(f"{username}|{expires}".encode()).decode()
    return f"{payload}.{_sign(payload, secret)}"


def read_token(token: str, secret: str, now: float | None = None) -> str | None:
    """Username if the token is genuine and unexpired, else None."""
    try:
        payload, sig = token.split(".")
        if not hmac.compare_digest(sig, _sign(payload, secret)):
            return None
        username, expires = base64.urlsafe_b64decode(payload).decode().rsplit("|", 1)
    except (ValueError, UnicodeDecodeError):
        return None
    return username if int(expires) > (now or time.time()) else None


# ---------------------------------------------------------------- two-step login (RFC 6238 TOTP)
def totp(key: bytes, t: float, digits: int = 6, step: int = TOTP_STEP, digest: str = "sha1") -> str:
    """The code an authenticator app shows at time t (RFC 6238, built on RFC 4226 HOTP)."""
    mac = hmac.new(key, struct.pack(">Q", int(t // step)), digest).digest()
    offset = mac[-1] & 0x0F
    number = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10 ** digits).zfill(digits)


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode()


def totp_uri(username: str, secret: str) -> str:
    return f"otpauth://totp/Matrix:{quote(username)}?secret={secret}&issuer=Matrix"


def check_totp(secret: str, code: str, now: float | None = None, after: int | None = None) -> int | None:
    """The time step `code` belongs to, allowing one step of clock drift either way, or None.
    `after` is the last step already used: a code works only once."""
    code = str(code or "").strip()
    if len(code) != 6 or not code.isdigit():
        return None
    now = time.time() if now is None else now
    key = base64.b32decode(secret)
    for drift in (0, -1, 1):
        step = int(now // TOTP_STEP) + drift
        if hmac.compare_digest(totp(key, step * TOTP_STEP), code) and (after is None or step > after):
            return step
    return None


def set_user(conn, username: str, password: str) -> None:
    if len(password) < 10:
        raise ValueError("password must be at least 10 characters")
    conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?) ON CONFLICT (username)"
                 " DO UPDATE SET password_hash=excluded.password_hash",
                 (username, hash_password(password)))
    conn.commit()


if __name__ == "__main__":
    from matrix import db
    if len(sys.argv) != 2:
        sys.exit("usage: python -m matrix.auth USERNAME")
    pw = getpass.getpass("New password (10+ characters): ")
    if pw != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    set_user(db.connect(), sys.argv[1], pw)
    print(f"User '{sys.argv[1]}' saved.")
