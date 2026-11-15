"""Matrix Score v1 for stocks: price behaviour only, ranked against all liquid NSE stocks.

Fundamentals (profits, debt, cash flow) and news join the score in later phases.
Run: python -m matrix.score
"""
import json
import statistics
from collections import defaultdict

from matrix import analytics, db

MIN_DAYS = 120               # need about 6 months of trading history
MIN_MEDIAN_VALUE = 1e7       # Rs 1 crore traded on a typical day
SURVEILLANCE = {"BE", "BZ"}  # trade-to-trade segments: exchange is watching these
SURVEILLANCE_CAP = 30

# (component, weight, higher_is_better, strength text, weakness text)
COMPONENTS = [
    ("momentum", 30, True, "strong price momentum over the past year",
     "weak price momentum over the past year"),
    ("trend", 20, True, "trading above its long-term average price",
     "trading below its long-term average price"),
    ("volatility", 20, False, "calmer than most stocks", "more volatile than most stocks"),
    ("drawdown", 20, True, "small worst fall in the past year", "deep fall from its peak in the past year"),
    ("liquidity", 10, True, "easy to buy and sell (high daily trading)",
     "thinly traded, harder to buy and sell"),
]


def metrics(rows: list[dict]) -> dict | None:
    """Raw component values from one stock's rows (oldest first)."""
    s = analytics.adjusted_series(rows)
    if len(s) < MIN_DAYS:
        return None
    closes = [v for _, v in s]
    lookback = min(len(closes) - 1, 252)
    # 12-1 momentum: skip the latest month, which tends to reverse.
    momentum = closes[-22] / closes[-lookback - 1] - 1 if lookback > 22 else None
    avg = sum(closes[-200:]) / len(closes[-200:])
    values = [r["value"] for r in rows[-60:]]
    return {
        "momentum": momentum,
        "trend": closes[-1] / avg - 1,
        "volatility": analytics.volatility(s[-252:]),
        "drawdown": analytics.max_drawdown(s[-252:]),
        "liquidity": statistics.median(values),
        "days": len(s),
    }


def percentile_ranks(values: dict[str, float], higher_is_better: bool) -> dict[str, float]:
    """0-100 rank per key; ties share the average rank."""
    ordered = sorted(values.items(), key=lambda kv: kv[1], reverse=not higher_is_better)
    n = len(ordered)
    ranks, i = {}, 0
    while i < n:
        j = i
        while j + 1 < n and ordered[j + 1][1] == ordered[i][1]:
            j += 1
        r = 100.0 if n == 1 else ((i + j) / 2) / (n - 1) * 100
        for k in range(i, j + 1):
            ranks[ordered[k][0]] = r
        i = j + 1
    return ranks


def score_universe(stocks: dict[str, dict]) -> dict[str, dict]:
    """stocks: symbol -> {"metrics": {...}, "series": "EQ"}. Returns symbol -> result."""
    ranks = {}
    for name, _, better, _, _ in COMPONENTS:
        vals = {s: d["metrics"][name] for s, d in stocks.items() if d["metrics"][name] is not None}
        ranks[name] = percentile_ranks(vals, better)
    out = {}
    for sym, d in stocks.items():
        parts = {name: ranks[name].get(sym) for name, *_ in COMPONENTS}
        have = [(name, w) for name, w, *_ in COMPONENTS if parts[name] is not None]
        total_w = sum(w for _, w in have)
        score = sum(parts[n] * w for n, w in have) / total_w if total_w else None
        reasons = []
        for name, _, _, good, bad in COMPONENTS:
            if parts[name] is None:
                continue
            if parts[name] >= 75:
                reasons.append({"kind": "strength", "text": good, "rank": parts[name]})
            elif parts[name] <= 25:
                reasons.append({"kind": "weakness", "text": bad, "rank": parts[name]})
        if d["series"] in SURVEILLANCE and score is not None:
            score = min(score, SURVEILLANCE_CAP)
            reasons.insert(0, {"kind": "danger", "text": "in the exchange's trade-to-trade "
                               "(surveillance) segment: score capped at 30"})
        out[sym] = {"score": None if score is None else round(score), "components": parts,
                    "reasons": reasons}
    return out


def compute(conn, as_of: str | None = None) -> int:
    """Score every liquid stock on `as_of` (default: the latest trading day), using only data
    available on that day."""
    latest = as_of or conn.execute("SELECT MAX(date) FROM stock_prices").fetchone()[0]
    if not latest:
        return 0
    series_today = dict(conn.execute(
        "SELECT symbol, series FROM stock_prices WHERE date=? AND series IN ('EQ','BE','BZ')",
        (latest,)))
    by_symbol = defaultdict(list)
    for r in conn.execute(
            "SELECT symbol, date, close, prev_close, value FROM stock_prices"
            " WHERE series IN ('EQ','BE','BZ') AND date >= date(?, '-400 day') AND date <= ?"
            " ORDER BY date", (latest, latest)):
        if r["symbol"] in series_today:
            by_symbol[r["symbol"]].append(dict(r))
    stocks = {}
    for sym, rows in by_symbol.items():
        m = metrics(rows)
        if m and m["liquidity"] >= MIN_MEDIAN_VALUE:
            stocks[sym] = {"metrics": m, "series": series_today[sym]}
    results = score_universe(stocks)
    conn.execute("DELETE FROM stock_scores WHERE date=?", (latest,))
    conn.executemany(
        "INSERT INTO stock_scores (symbol, date, score, components, metrics, reasons, universe)"
        " VALUES (?,?,?,?,?,?,?)",
        [(s, latest, r["score"], json.dumps(r["components"]), json.dumps(stocks[s]["metrics"]),
          json.dumps(r["reasons"]), len(stocks)) for s, r in results.items()])
    conn.commit()
    return len(results)


if __name__ == "__main__":
    print(f"Scored {compute(db.connect())} stocks")
