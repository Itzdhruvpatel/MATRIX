"""Shortlist to research: stocks that pass simple rules the user picks, with the reasons.

Ideas to research, not advice. The history check replays the same rules on past scored days
(using only what was known then) and compares the next month with simply owning the Nifty.
"""
import json

from pydantic import BaseModel

from matrix import ledger

MAX_ITEMS = 40


class Rules(BaseModel):
    min_score: int = 60
    no_danger: bool = True      # no Danger alert right now
    no_warning: bool = False    # no Warning alert either
    min_traded_cr: float = 10   # Rs crore traded on a normal day
    calm: bool = False          # moves more calmly than most stocks
    uptrend: bool = False       # above its long-term average price
    small_fall: bool = False    # smaller worst fall in the past year than most


def _passes(score, comps: dict, metrics: dict, rules: Rules) -> list[str] | None:
    """Plain reasons it passed, or None if any rule fails."""
    c = lambda k: comps.get(k) if comps.get(k) is not None else -1  # noqa: E731
    traded = (metrics.get("liquidity") or 0) / 1e7
    checks = [
        (score is not None and score >= rules.min_score, f"Matrix Score {score}"),
        (traded >= rules.min_traded_cr, f"about Rs {traded:,.0f} crore traded on a normal day"),
    ]
    if rules.calm:
        checks.append((c("volatility") >= 60, f"moves more calmly than {c('volatility'):.0f} of 100 stocks"))
    if rules.uptrend:
        checks.append((c("trend") >= 50, "trading above its long-term average price"))
    if rules.small_fall:
        checks.append((c("drawdown") >= 50, f"its worst fall this year was smaller than {c('drawdown'):.0f} of 100 stocks"))
    if not all(ok for ok, _ in checks):
        return None
    return [why for _, why in checks]


def shortlist(conn, rules: Rules) -> dict:
    latest = conn.execute("SELECT MAX(date) FROM stock_scores").fetchone()[0]
    if not latest:
        return {"date": None, "items": [], "count": 0}
    levels = ["danger"] * rules.no_danger + ["warning"] * rules.no_warning
    flagged = {r[0] for r in conn.execute(
        f"SELECT DISTINCT symbol FROM alerts WHERE level IN ({','.join('?' * len(levels))})",
        levels)} if levels else set()
    items = []
    for r in conn.execute(
            "SELECT s.symbol, s.score, s.components, s.metrics, p.name, p.close FROM stock_scores s"
            " JOIN stock_prices p ON p.symbol=s.symbol AND p.date=s.date WHERE s.date=? AND s.symbol != ?"
            " ORDER BY s.score DESC, s.symbol", (latest, ledger.MARKET)):
        if r["symbol"] in flagged:
            continue
        why = _passes(r["score"], json.loads(r["components"]), json.loads(r["metrics"]), rules)
        if why is None:
            continue
        if levels:
            why.append("no Danger or Warning alerts" if rules.no_warning else "no Danger alerts")
        items.append({"symbol": r["symbol"], "name": r["name"], "close": r["close"],
                      "score": r["score"], "why": why})
    return {"date": latest, "count": len(items), "items": items[:MAX_ITEMS]}


def history(conn, rules: Rules, horizon: int = ledger.HORIZON) -> dict:
    """Same rules on past scored days (alerts left out: Matrix keeps only today's) vs the Nifty."""
    rows, empty = [], 0
    for d, end in ledger.checked_dates(conn, horizon):
        picks = [s for s, sc, c, m in conn.execute(
            "SELECT symbol, score, components, metrics FROM stock_scores WHERE date=? AND symbol != ?",
            (d, ledger.MARKET)) if _passes(sc, json.loads(c), json.loads(m), rules) is not None]
        if not picks:
            empty += 1
            continue
        rets = ledger._forward_returns(conn, d, end, [*picks, ledger.MARKET])
        market = rets.pop(ledger.MARKET, None)
        if market is None or not rets:
            continue
        rows.append((sum(rets.values()) / len(rets), market))
    n = len(rows)
    if not n:
        return {"periods": 0, "empty": empty, "horizon": horizon}
    return {"periods": n, "empty": empty, "horizon": horizon,
            "avg": sum(a for a, _ in rows) / n, "market_avg": sum(m for _, m in rows) / n,
            "won": sum(a > m for a, m in rows)}
