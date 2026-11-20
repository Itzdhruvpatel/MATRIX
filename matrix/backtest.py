"""Backtest of the chart patterns: what happened in the 20 trading days after each one.

Every past day of every liquid stock is checked with the same pattern rules the radar uses
today (only data up to that day). Each pattern is compared with the Nifty over the same days and
with "any day" (buying a random liquid stock on a random day), after trading costs and tax.
Run: python -m matrix.backtest
"""
import json
import statistics
from itertools import groupby

from matrix import analytics, db, ledger, radar

COST = 0.003  # brokerage, STT, stamp duty and slippage for a buy and a sell together (rough)
TAX = 0.20    # short-term capital gains tax on listed shares held under a year (from July 2024)
LONG_TAX = 0.125  # long-term rate, held over a year (the yearly Rs 1.25 lakh tax-free limit is left out)
ANY = "any_day"


def after_costs(ret: float, tax: float = TAX) -> float:
    r = ret - COST
    return r * (1 - tax) if r > 0 else r  # a loss pays no tax (setting it off is left out)


def tax_for(horizon: int) -> float:
    return LONG_TAX if horizon >= 250 else TAX


def pattern_history(conn, horizon: int = ledger.HORIZON) -> dict:
    nifty = [dict(r) for r in conn.execute("SELECT date, close, prev_close FROM stock_prices"
                                           " WHERE symbol=? ORDER BY date", (ledger.MARKET,))]
    market = {d.isoformat(): v for d, v in analytics.adjusted_series(nifty)}
    events = {k: [] for k in (*radar.PATTERNS, ANY)}  # (return, Nifty return) per event
    cur = conn.execute("SELECT symbol, date, open, close, prev_close, value FROM stock_prices"
                       " WHERE series='EQ' AND symbol != ? ORDER BY symbol, date", (ledger.MARKET,))
    for _, group in groupby((dict(r) for r in cur), key=lambda r: r["symbol"]):
        rows = list(group)
        closes = [v for _, v in analytics.adjusted_series(rows)]
        for i in range(50, len(rows) - horizon):
            start, end = rows[i]["date"], rows[i + horizon]["date"]
            if start not in market or end not in market:
                continue
            found = list(radar.patterns_at(rows, closes, i))
            # "Any day" samples every 5th liquid day: plenty, and five times faster.
            if i % 5 == 0 and statistics.median(
                    r["value"] or 0 for r in rows[i - 50:i]) >= radar.PATTERN_MIN_VALUE:
                found.append(ANY)
            if not found:
                continue
            ret, mkt = closes[i + horizon] / closes[i] - 1, market[end] / market[start] - 1
            for rule in found:
                events[rule].append((ret, mkt))
    out = {}
    for rule, ev in events.items():
        n = len(ev)
        # The median shows the usual case; a few huge winners can pull the average far up.
        out[rule] = {"events": n} if not n else {
            "events": n, "avg": sum(r for r, _ in ev) / n, "median": statistics.median(r for r, _ in ev),
            "market_avg": sum(m for _, m in ev) / n, "beat_share": sum(r > m for r, m in ev) / n,
            "avg_after_costs": sum(after_costs(r) for r, _ in ev) / n}
    days = ledger.trading_days(conn)
    return {"horizon": horizon, "cost": COST, "tax": TAX, "patterns": out,
            "from": days[0] if days else None, "to": days[-1] if days else None}


def cached(conn) -> dict:
    """The saved result for the latest price day, worked out and saved if it is missing.
    The daily job calls this, so the web page only reads the saved copy."""
    key = conn.execute("SELECT MAX(date) FROM stock_prices").fetchone()[0] or ""
    r = conn.execute("SELECT key, body FROM reports WHERE name='pattern_backtest'").fetchone()
    if r and r[0] == key:
        return json.loads(r[1])
    result = pattern_history(conn)
    conn.execute("INSERT INTO reports (name, key, body, created_at) VALUES ('pattern_backtest', ?, ?,"
                 " CURRENT_TIMESTAMP) ON CONFLICT (name) DO UPDATE SET key=excluded.key,"
                 " body=excluded.body, created_at=excluded.created_at", (key, json.dumps(result)))
    conn.commit()
    return result


if __name__ == "__main__":
    for rule, r in pattern_history(db.connect())["patterns"].items():
        print(rule, r)
