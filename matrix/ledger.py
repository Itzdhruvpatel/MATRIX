"""Prediction Ledger: did high Matrix Scores actually lead to better results?

For past dates, the score is computed using only data known on that day. Then we look at
what each stock did over the next `horizon` trading days and compare it with the Nifty ETF.
Run: python -m matrix.ledger
"""
from collections import defaultdict

from matrix import db, score

MARKET = "NIFTYBEES"
HORIZON = 20       # about one month of trading days
STRONG, WEAK = 80, 20
MAX_SNAPSHOTS = 24


def trading_days(conn) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT date FROM stock_prices ORDER BY date")]


def backfill(conn, horizon: int = HORIZON) -> int:
    """Score past dates spaced `horizon` days apart, newest first, that are not scored yet."""
    days = trading_days(conn)
    done = {r[0] for r in conn.execute("SELECT DISTINCT date FROM stock_scores")}
    made = 0
    for i in range(len(days) - 1 - horizon, score.MIN_DAYS, -horizon):
        if days[i] not in done:
            score.compute(conn, as_of=days[i])
            made += 1
    return made


def _forward_returns(conn, start: str, end: str, symbols: list[str]) -> dict[str, float]:
    """Return from start to end, chained from each day's move (so splits do not distort it)."""
    growth = defaultdict(lambda: 1.0)
    marks = ",".join("?" * len(symbols))
    for sym, close, prev in conn.execute(
            f"SELECT symbol, close, prev_close FROM stock_prices WHERE date > ? AND date <= ?"
            f" AND symbol IN ({marks})", (start, end, *symbols)):
        if prev:
            growth[sym] *= close / prev
    return {s: g - 1 for s, g in growth.items()}


def track_record(conn, horizon: int = HORIZON) -> dict:
    days = trading_days(conn)
    index = {d: i for i, d in enumerate(days)}
    scored = [r[0] for r in conn.execute("SELECT DISTINCT date FROM stock_scores ORDER BY date DESC")]
    snaps, last = [], None
    for d in scored:  # newest first, spaced at least `horizon` apart, with a full month after
        i = index.get(d)
        if i is None or i + horizon >= len(days) or (last is not None and index[last] - i < horizon):
            continue
        snaps.append(d)
        last = d
        if len(snaps) >= MAX_SNAPSHOTS:
            break
    rows = []
    for d in snaps:
        end = days[index[d] + horizon]
        sc = dict(conn.execute("SELECT symbol, score FROM stock_scores WHERE date=?", (d,)))
        rets = _forward_returns(conn, d, end, [*sc, MARKET])
        market = rets.get(MARKET)
        if market is None:
            continue
        top = [rets[s] for s, v in sc.items() if v is not None and v >= STRONG and s in rets]
        low = [rets[s] for s, v in sc.items() if v is not None and v < WEAK and s in rets]
        if not top or not low:
            continue
        rows.append({
            "date": d, "until": end, "market": market,
            "strong_count": len(top), "strong_avg": sum(top) / len(top),
            "strong_beat_share": sum(r > market for r in top) / len(top),
            "weak_count": len(low), "weak_avg": sum(low) / len(low),
        })
    if not rows:
        return {"periods": [], "horizon": horizon}
    n = len(rows)
    return {
        "horizon": horizon, "periods": rows,
        "strong_avg": sum(r["strong_avg"] for r in rows) / n,
        "weak_avg": sum(r["weak_avg"] for r in rows) / n,
        "market_avg": sum(r["market"] for r in rows) / n,
        "strong_beat_share": sum(r["strong_beat_share"] for r in rows) / n,
        "strong_won_periods": sum(r["strong_avg"] > r["market"] for r in rows),
    }


if __name__ == "__main__":
    c = db.connect()
    print(f"Scored {backfill(c)} past dates")
    t = track_record(c)
    for r in t["periods"]:
        print(r)
