"""Return and risk maths. Series are lists of (date, value) sorted by date."""
import math
from bisect import bisect_right
from datetime import date, timedelta

Series = list[tuple[date, float]]
TRADING_DAYS = 252


def value_on_or_before(s: Series, d: date) -> float | None:
    i = bisect_right(s, (d, math.inf))
    return s[i - 1][1] if i else None


def trailing_return(s: Series, years: float) -> float | None:
    """CAGR for 1+ years, absolute return below 1 year. None if history is too short."""
    if len(s) < 2:
        return None
    end_d, end_v = s[-1]
    start_d = end_d - timedelta(days=round(365.25 * years))
    if s[0][0] > start_d + timedelta(days=7):  # allow a week of slack for holidays
        return None
    start_v = value_on_or_before(s, start_d) or s[0][1]
    if start_v <= 0:
        return None
    growth = end_v / start_v
    return growth ** (1 / years) - 1 if years >= 1 else growth - 1


def adjusted_series(rows: list[dict]) -> Series:
    """Split/bonus-adjusted closes from exchange rows (date, close, prev_close), oldest first.

    NSE adjusts prev_close on the ex-date, so close/prev_close is the true daily move.
    Chaining those moves backwards from the latest close removes split and bonus jumps.
    """
    if not rows:
        return []
    out = [(date.fromisoformat(rows[-1]["date"]), rows[-1]["close"])]
    level = rows[-1]["close"]
    for i in range(len(rows) - 1, 0, -1):
        r = rows[i]
        if r["prev_close"] and r["prev_close"] > 0:
            level = level / (r["close"] / r["prev_close"])
        out.append((date.fromisoformat(rows[i - 1]["date"]), level))
    return out[::-1]


def daily_returns(s: Series) -> list[float]:
    return [s[i][1] / s[i - 1][1] - 1 for i in range(1, len(s)) if s[i - 1][1] > 0]


def volatility(s: Series) -> float | None:
    """Annualised standard deviation of daily returns."""
    r = daily_returns(s)
    if len(r) < 20:
        return None
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(TRADING_DAYS)


def max_drawdown(s: Series) -> float | None:
    """Worst fall from a previous peak, as a negative fraction."""
    if not s:
        return None
    peak, worst = s[0][1], 0.0
    for _, v in s:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst


def rolling_consistency(s: Series, years: int = 1, step_days: int = 30) -> dict:
    """Share of rolling windows with a positive return, plus worst and best window."""
    if not s:
        return {"windows": 0}
    out = []
    d = s[0][0] + timedelta(days=round(365.25 * years))
    while d <= s[-1][0]:
        start = value_on_or_before(s, d - timedelta(days=round(365.25 * years)))
        end = value_on_or_before(s, d)
        if start and end:
            out.append((end / start) ** (1 / years) - 1)
        d += timedelta(days=step_days)
    if not out:
        return {"windows": 0}
    return {"windows": len(out), "positive_share": sum(r > 0 for r in out) / len(out),
            "worst": min(out), "best": max(out)}


def xirr(flows: list[tuple[date, float]]) -> float | None:
    """Annual return for dated cash flows (money out negative, money in positive).

    Bisection on NPV: slower than Newton but never diverges.
    """
    if not any(cf < 0 for _, cf in flows) or not any(cf > 0 for _, cf in flows):
        return None
    t0 = min(d for d, _ in flows)

    def npv(rate):
        return sum(cf / (1 + rate) ** ((d - t0).days / 365) for d, cf in flows)

    lo, hi = -0.9999, 100.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1e-9:
            break
    return (lo + hi) / 2


def summary(s: Series) -> dict:
    """Standard return and risk numbers for any price or NAV series."""
    return {
        "as_of": s[-1][0].isoformat() if s else None,
        "last": s[-1][1] if s else None,
        "return_1m": trailing_return(s, 1 / 12),
        "return_3m": trailing_return(s, 0.25),
        "return_6m": trailing_return(s, 0.5),
        "return_1y": trailing_return(s, 1),
        "cagr_3y": trailing_return(s, 3),
        "cagr_5y": trailing_return(s, 5),
        "volatility": volatility(s[-TRADING_DAYS:]),
        "max_drawdown_1y": max_drawdown([p for p in s if p[0] >= s[-1][0] - timedelta(days=365)]) if s else None,
        "max_drawdown_all": max_drawdown(s),
        "history_from": s[0][0].isoformat() if s else None,
    }
