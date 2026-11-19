"""Forecast: the chance a stock beats the Nifty ETF over the next 20 trading days.

A plain logistic regression on the five Matrix Score parts, trained only on past scored days
whose 20-day outcome was already known on the forecast day (walk-forward). Every forecast is
saved once and never rewritten, so the Prediction Ledger can grade it honestly later.
The likely range is not a prediction: it is how far this stock moved over 20 trading days
in the past year (8 times out of 10).
Run: python -m matrix.forecast
"""
import json
import math
import statistics
from collections import defaultdict
from datetime import date, timedelta

from matrix import db, ledger, score

HORIZON = ledger.HORIZON
MODEL = "logit-v1"
MIN_TRAIN_DATES = 2
KILL_DAYS = 63          # about 3 months of trading days
KILL_MIN_DAYS = 3       # forecast days in that window needed to judge (backfill makes one a month)
KILL_MIN_GRADED = 300


def recent_record(conn, horizon: int = HORIZON) -> dict:
    """Forecasts made in the last 3 months whose result is already known."""
    days = ledger.trading_days(conn)
    since = days[-(KILL_DAYS + horizon)] if len(days) > KILL_DAYS + horizon else None
    return ledger.forecast_record(conn, horizon, since=since)


def paused(recent: dict) -> bool:
    """Kill switch: hide forecasts while, over the last 3 months, they lose to the simple guess."""
    return (recent.get("days", 0) >= KILL_MIN_DAYS and recent["graded"] >= KILL_MIN_GRADED
            and recent["hit_rate"] < recent["baseline"])
PARTS = [name for name, *_ in score.COMPONENTS]


def features(components: dict) -> list[float]:
    """Intercept plus each score part scaled to -1..1 (missing = middle)."""
    return [1.0] + [((components.get(p) if components.get(p) is not None else 50) - 50) / 50
                    for p in PARTS]


def predict(w: list[float], x: list[float]) -> float:
    z = sum(a * b for a, b in zip(w, x))
    return 1 / (1 + math.exp(-max(min(z, 35), -35)))


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting (the system is tiny: one row per feature)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        for r in range(c + 1, n):
            f = m[r][c] / m[c][c]
            for k in range(c, n + 1):
                m[r][k] -= f * m[c][k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][k] * x[k] for k in range(r + 1, n))) / m[r][r]
    return x


def fit(X: list[list[float]], y: list[int], l2: float = 1.0, iters: int = 25) -> list[float]:
    """Logistic regression by Newton steps, with a small L2 penalty to keep weights sane."""
    k = len(X[0])
    w = [0.0] * k
    for _ in range(iters):
        g = [l2 * wi for wi in w]
        h = [[l2 if i == j else 0.0 for j in range(k)] for i in range(k)]
        for x, t in zip(X, y):
            p = predict(w, x)
            s = p * (1 - p)
            for i in range(k):
                g[i] += (p - t) * x[i]
                for j in range(i, k):
                    h[i][j] += s * x[i] * x[j]
        for i in range(k):
            for j in range(i):
                h[i][j] = h[j][i]
        step = _solve(h, g)
        w = [wi - si for wi, si in zip(w, step)]
        if max(abs(si) for si in step) < 1e-6:
            break
    return w


def training_set(conn, until: str, horizon: int = HORIZON):
    X, y, used = [], [], 0
    for d, end in ledger.checked_dates(conn, horizon, until=until):
        comps = {s: json.loads(c) for s, c in conn.execute(
            "SELECT symbol, components FROM stock_scores WHERE date=? AND symbol != ?",
            (d, ledger.MARKET))}
        rets = ledger._forward_returns(conn, d, end, [*comps, ledger.MARKET])
        market = rets.get(ledger.MARKET)
        if market is None:
            continue
        used += 1
        for sym, c in comps.items():
            if sym in rets:
                X.append(features(c))
                y.append(1 if rets[sym] > market else 0)
    return X, y, used


def ranges(conn, as_of: str, symbols: set[str], horizon: int = HORIZON) -> dict[str, tuple]:
    """10th and 90th percentile of each stock's `horizon`-day moves over the past year."""
    start = (date.fromisoformat(as_of) - timedelta(days=400)).isoformat()
    growth = defaultdict(list)
    for sym, close, prev in conn.execute(
            "SELECT symbol, close, prev_close FROM stock_prices WHERE date > ? AND date <= ?"
            " ORDER BY date", (start, as_of)):
        if sym in symbols and prev:
            g = growth[sym]
            g.append((g[-1] if g else 1.0) * close / prev)
    out = {}
    for sym, g in growth.items():
        g = g[-(252 + horizon):]
        moves = [g[i] / g[i - horizon] - 1 for i in range(horizon, len(g))]
        if len(moves) >= 60:
            q = statistics.quantiles(moves, n=10)
            out[sym] = (q[0], q[-1])
    return out


def compute(conn, as_of: str | None = None, horizon: int = HORIZON, backfilled: bool = False) -> int:
    """Forecast every scored stock on `as_of` (default: latest scored day). Returns how many."""
    as_of = as_of or conn.execute("SELECT MAX(date) FROM stock_scores").fetchone()[0]
    if not as_of:
        return 0
    X, y, used = training_set(conn, as_of, horizon)
    if used < MIN_TRAIN_DATES or len(set(y)) < 2:
        return 0
    w = fit(X, y)
    comps = {s: json.loads(c) for s, c in conn.execute(
        "SELECT symbol, components FROM stock_scores WHERE date=? AND symbol != ?",
        (as_of, ledger.MARKET))}
    rng = ranges(conn, as_of, set(comps), horizon)
    rows = [(s, as_of, horizon, round(predict(w, features(c)), 4), *rng.get(s, (None, None)),
             MODEL, int(backfilled)) for s, c in comps.items()]
    # ON CONFLICT DO NOTHING: a forecast, once logged, is never changed.
    conn.executemany(
        "INSERT INTO forecasts (symbol, date, horizon, prob, low, high, model, backfilled, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING", rows)
    conn.commit()
    return len(rows)


def backfill(conn, horizon: int = HORIZON) -> int:
    """Walk forward through past scored days that have no forecast yet. Returns days forecast."""
    have = {r[0] for r in conn.execute("SELECT DISTINCT date FROM forecasts WHERE horizon=?", (horizon,))}
    made = 0
    for (d,) in conn.execute("SELECT DISTINCT date FROM stock_scores ORDER BY date").fetchall():
        if d not in have and compute(conn, d, horizon, backfilled=True):
            made += 1
    return made


def latest(conn, symbol: str) -> dict | None:
    r = conn.execute("SELECT symbol, date, horizon, prob, low, high, model FROM forecasts"
                     " WHERE symbol=? ORDER BY date DESC LIMIT 1", (symbol,)).fetchone()
    return dict(r) if r else None


if __name__ == "__main__":
    c = db.connect()
    print(f"Scored {ledger.backfill(c)} past dates")
    print(f"Forecast {backfill(c)} past days (walk-forward)")
