"""Market mood, what-if scenarios and a tax view for a portfolio.

These are estimates to help thinking, not predictions or tax advice.
"""
import math
from collections import defaultdict, deque
from datetime import date

from matrix import analytics, portfolio

MARKET = "NIFTYBEES"  # Nifty 50 ETF, used as "the market"

# Tax rules for listed equity and equity funds, from the July 2024 Union Budget.
# Rules change: the screen says which year they are from.
TAX_RULES_FROM = "Union Budget, July 2024"
LONG_TERM_DAYS = 365
STCG_RATE = 0.20
LTCG_RATE = 0.125
LTCG_EXEMPTION = 125000


def _series(conn, kind: str, code: str):
    if kind == "stock":
        rows = [dict(r) for r in conn.execute(
            "SELECT date, close, prev_close FROM stock_prices WHERE symbol=? ORDER BY date", (code,))]
        return analytics.adjusted_series(rows)
    return [(date.fromisoformat(r[0]), r[1]) for r in conn.execute(
        "SELECT date, nav FROM fund_navs WHERE scheme_code=? ORDER BY date", (code,))]


def beta(s, market, min_days: int = 40) -> float | None:
    """How much a series moves for each 1% move in the market (daily returns, matched dates)."""
    m = dict(market)
    pairs = []
    for i in range(1, len(s)):
        d, d0 = s[i][0], s[i - 1][0]
        if d in m and d0 in m and s[i - 1][1] > 0 and m[d0] > 0:
            pairs.append((s[i][1] / s[i - 1][1] - 1, m[d] / m[d0] - 1))
    pairs = pairs[-250:]
    if len(pairs) < min_days:
        return None
    xs, ys = [p[1] for p in pairs], [p[0] for p in pairs]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    var = sum((x - mx) ** 2 for x in xs)
    if var == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var


# ---------------------------------------------------------------- market mood
def mood_from(vol20: float | None, drawdown: float | None, breadth5: float | None) -> dict:
    points, reasons = 0, []
    if vol20 is not None:
        if vol20 >= 0.28:
            points += 2; reasons.append(f"Daily swings are very large ({vol20:.0%} a year).")
        elif vol20 >= 0.18:
            points += 1; reasons.append(f"Daily swings are bigger than usual ({vol20:.0%} a year).")
        else:
            reasons.append(f"Daily swings are small ({vol20:.0%} a year).")
    if drawdown is not None:
        if drawdown <= -0.15:
            points += 2; reasons.append(f"The Nifty is {abs(drawdown):.0%} below its high of the last year.")
        elif drawdown <= -0.08:
            points += 1; reasons.append(f"The Nifty is {abs(drawdown):.0%} below its recent high.")
        else:
            reasons.append(f"The Nifty is close to its high ({abs(drawdown):.0%} below).")
    if breadth5 is not None:
        if breadth5 < 0.4:
            points += 1; reasons.append(f"Over the last week only {breadth5:.0%} of stocks rose on a typical day.")
        else:
            reasons.append(f"Over the last week {breadth5:.0%} of stocks rose on a typical day.")
    level = "Calm" if points == 0 else "Nervous" if points <= 2 else "Stressed" if points <= 4 else "Panic"
    meaning = {
        "Calm": "Normal conditions. Good time to follow your plan, not to rush.",
        "Nervous": "Some worry in the market. Expect bigger ups and downs than usual.",
        "Stressed": "Prices are falling and swinging hard. Avoid big, quick decisions.",
        "Panic": "Fear is high. History shows panics pass, but losses can grow first. Do not borrow to buy.",
    }[level]
    return {"level": level, "points": points, "meaning": meaning, "reasons": reasons}


def market_mood(conn) -> dict:
    s = _series(conn, "stock", MARKET)
    if len(s) < 25:
        return {"level": None, "meaning": "Not enough market history yet.", "reasons": []}
    rets = analytics.daily_returns(s[-21:])
    m = sum(rets) / len(rets)
    vol20 = math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1)) * math.sqrt(analytics.TRADING_DAYS)
    peak = max(v for _, v in s[-250:])
    drawdown = s[-1][1] / peak - 1
    b = conn.execute(
        "SELECT AVG(share) FROM (SELECT SUM(close > prev_close) * 1.0 / COUNT(*) share FROM stock_prices"
        " WHERE series='EQ' AND date IN (SELECT DISTINCT date FROM stock_prices ORDER BY date DESC LIMIT 5)"
        " GROUP BY date)").fetchone()[0]
    out = mood_from(vol20, drawdown, b)
    out.update({"as_of": s[-1][0].isoformat(), "volatility": vol20, "drawdown": drawdown, "breadth5": b})
    return out


# ---------------------------------------------------------------- scenarios
def scenario(conn, username: str, market_move: float, book: str = "real") -> dict:
    """Estimated effect of the market moving by `market_move` (for example -0.2), using each
    holding's beta. A rough guide: real moves differ."""
    if not -0.9 <= market_move <= 1.0:
        raise ValueError("market move must be between -90% and +100%")
    p = portfolio.summary(conn, username, book)
    market = _series(conn, "stock", MARKET)
    rows, total_change = [], 0.0
    for h in p["holdings"]:
        b = beta(_series(conn, h["kind"], h["code"]), market)
        known = b is not None
        b = min(max(b if known else 1.0, 0.0), 2.5)
        change_pct = b * market_move
        change = h["value"] * change_pct
        total_change += change
        rows.append({"code": h["code"], "name": h["name"], "kind": h["kind"], "value": h["value"],
                     "beta": b, "beta_known": known, "change_pct": change_pct, "change": change,
                     "new_value": h["value"] + change})
    rows.sort(key=lambda r: r["change"])
    value = p["value"]
    return {"market_move": market_move, "value": value, "change": total_change,
            "change_pct": total_change / value if value else 0, "new_value": value + total_change,
            "holdings": rows}


# ---------------------------------------------------------------- tax
def _equity_like(conn, kind: str, code: str) -> bool:
    if kind == "stock":
        return True
    r = conn.execute("SELECT category FROM funds WHERE scheme_code=?", (code,)).fetchone()
    cat = (r[0] or "") if r else ""
    return cat.startswith("Equity") or "ELSS" in cat or "Arbitrage" in cat or "Aggressive Hybrid" in cat


def tax_view(conn, username: str, today: date | None = None) -> dict:
    """Tax if every holding were sold today. Lots are matched first-in, first-out, as Indian
    tax rules require. Only listed equity and equity-fund rules are calculated; other funds
    are taxed at your income slab, which Matrix does not know."""
    today = today or date.today()
    lots = defaultdict(deque)
    for t in conn.execute("SELECT kind, code, side, date, quantity, price FROM transactions"
                          " WHERE username=? AND book='real' ORDER BY date, id", (username,)):
        key = (t[0], t[1])
        if t[2] == "buy":
            lots[key].append([date.fromisoformat(t[3]), t[4], t[5]])
        else:
            left = t[4]
            while left > 1e-9 and lots[key]:
                lot = lots[key][0]
                used = min(lot[1], left)
                lot[1] -= used
                left -= used
                if lot[1] <= 1e-9:
                    lots[key].popleft()
    st_gain = lt_gain = slab_gain = 0.0
    rows = []
    for (kind, code), q in lots.items():
        lp = portfolio.latest_price(conn, kind, code)
        if not lp or not q:
            continue
        price, equity = lp[0], _equity_like(conn, kind, code)
        for bought, qty, cost in q:
            gain = (price - cost) * qty
            held = (today - bought).days
            term = "slab" if not equity else "long" if held > LONG_TERM_DAYS else "short"
            if term == "long":
                lt_gain += gain
            elif term == "short":
                st_gain += gain
            else:
                slab_gain += gain
            rows.append({"code": code, "kind": kind, "name": portfolio.name_of(conn, kind, code),
                         "bought": bought.isoformat(), "quantity": qty,
                         "cost": cost, "price": price, "gain": gain, "days_held": held, "term": term,
                         "long_term_on": None if term != "short" else
                         date.fromordinal(bought.toordinal() + LONG_TERM_DAYS + 1).isoformat()})
    lt_taxable = max(lt_gain - LTCG_EXEMPTION, 0)
    return {
        "rules_from": TAX_RULES_FROM,
        "short_term_gain": st_gain, "short_term_tax": max(st_gain, 0) * STCG_RATE,
        "long_term_gain": lt_gain, "long_term_tax": lt_taxable * LTCG_RATE,
        "slab_gain": slab_gain,
        "tax_free_room": max(LTCG_EXEMPTION - max(lt_gain, 0), 0),
        "lots": sorted(rows, key=lambda r: (r["code"], r["bought"])),
    }
