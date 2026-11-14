"""Password hashing and signed session tokens (stdlib only).

Create or reset a user:  python -m matrix.auth USERNAME
"""
import base64
import getpass
import hashlib
import hmac
import secrets
import sys
import time

ITERATIONS = 600_000
SESSION_SECONDS = 12 * 3600


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


def set_user(conn, username: str, password: str) -> None:
    if len(password) < 10:
        raise ValueError("password must be at least 10 characters")
    conn.execute("INSERT OR REPLACE INTO users (username, password_hash) VALUES (?, ?)",
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
