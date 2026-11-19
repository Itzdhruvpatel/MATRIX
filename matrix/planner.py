"""Trade planner and Time Machine for one stock, on end-of-day prices.

A practice and research tool, not advice. The planner works out how many shares fit the most
you are willing to lose. The Time Machine replays the stock's own past daily moves to show how
often the price reached the stop or the target first.
"""
import math
import random

from matrix import analytics

HORIZON = 20        # trading days to hold at most
PATHS = 10_000
LOOKBACK = 252      # daily moves used: about one year
MIN_MOVES = 60
STOP_MOVES = 2      # default stop: 2 typical daily moves below the price
REWARD = 2          # default target: twice as far above as the stop is below


def closes(conn, symbol: str) -> list[float]:
    rows = [dict(r) for r in conn.execute(
        "SELECT date, close, prev_close FROM stock_prices WHERE symbol=? ORDER BY date", (symbol,))]
    return [v for _, v in analytics.adjusted_series(rows)]


def first_hit(path, entry: float, stop: float, target: float) -> tuple[str, float]:
    """Which level a run of closing prices reached first, and the result as a fraction.

    Out at the close that went through the level: with end-of-day prices that is the first
    price you could act on, often worse than the stop itself.
    """
    for p in path:
        if p <= stop:
            return "stop", p / entry - 1
        if p >= target:
            return "target", p / entry - 1
    return "neither", path[-1] / entry - 1 if path else 0.0


def _odds(results: list[tuple[str, float]]) -> dict:
    n = len(results)
    share = {k: sum(r == k for r, _ in results) / n for k in ("target", "stop", "neither")}
    return {**share, "runs": n, "avg_result": sum(x for _, x in results) / n}


def simulate(moves: list[float], entry: float, stop: float, target: float,
             horizon: int = HORIZON, paths: int = PATHS, seed=0) -> dict:
    """Random runs built from past daily moves with their average taken out (no trend assumed)."""
    mean = sum(moves) / len(moves)
    moves = [m - mean for m in moves]
    rng = random.Random(seed)
    results = []
    for _ in range(paths):
        p, path = entry, []
        for m in rng.choices(moves, k=horizon):
            p *= 1 + m
            path.append(p)
        results.append(first_hit(path, entry, stop, target))
    return _odds(results)


def replay(prices: list[float], stop_pct: float, target_pct: float, horizon: int = HORIZON) -> dict | None:
    """The same plan started on every past day: how it really went over the next `horizon` days."""
    results = [first_hit(prices[i + 1:i + 1 + horizon], prices[i], prices[i] * (1 - stop_pct),
                         prices[i] * (1 + target_pct)) for i in range(len(prices) - horizon)]
    return _odds(results) if results else None


def plan(conn, symbol: str, entry=None, stop=None, target=None, risk=None, capital=None,
         odds: bool = True) -> dict:
    prices = closes(conn, symbol)
    if not prices:
        raise LookupError(f"Stock {symbol} not found")
    moves = analytics.daily_returns([(i, v) for i, v in enumerate(prices[-LOOKBACK - 1:])])
    typical = sum(abs(m) for m in moves[-60:]) / len(moves[-60:]) if moves else 0.02
    entry = entry or prices[-1]
    stop = stop or round(entry * (1 - STOP_MOVES * typical), 2)
    target = target or round(entry + REWARD * (entry - stop), 2)
    if not 0 < stop < entry < target:
        raise ValueError("The stop must be below the price, and the target above it")
    out = {"symbol": symbol, "last": prices[-1], "entry": entry, "stop": stop, "target": target,
           "typical_move": typical, "reward_risk": (target - entry) / (entry - stop),
           "horizon": HORIZON, "risk": risk, "capital": capital}
    if risk:
        shares = math.floor(risk / (entry - stop))
        out.update(shares=shares, money=shares * entry, loss=shares * (entry - stop),
                   gain=shares * (target - entry),
                   share_of_capital=shares * entry / capital if capital else None)
    if odds and len(moves) >= MIN_MOVES:
        seed = f"{symbol}|{entry}|{stop}|{target}"  # same inputs, same answer
        out["simulated"] = simulate(moves, entry, stop, target, seed=seed)
        out["history"] = replay(prices[-LOOKBACK - 1:], 1 - stop / entry, target / entry - 1)
    return out

