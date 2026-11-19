"""Danger Radar: plain-language warnings from prices, official announcements and big deals.

Every alert says what happened, why it matters, and where it came from.
Run: python -m matrix.radar
"""
import re
import statistics
from collections import defaultdict
from datetime import date, timedelta

from matrix import analytics, db

LEVELS = ("danger", "warning", "watch", "info")
WINDOW_DAYS = 30            # how far back announcements stay on the radar
BIG_DEAL_VALUE = 1e8        # Rs 10 crore
PUMP_MAX_VALUE = 5e7        # "thin trading": under Rs 5 crore on a typical day

# (rule, level, title, why it matters, pattern over "subject | description")
ANNOUNCEMENT_RULES = [
    ("auditor_exit", "danger", "The company's auditor resigned",
     "Auditors check the accounts. When one quits mid-term, it can mean they found something "
     "they did not want to sign.", r"(?=.*auditor)(?=.*resign)"),
    ("default", "danger", "Missed a loan or interest payment",
     "A company that cannot pay its lenders on time is in financial trouble.",
     r"default(s)? (on|in) (payment|loan|interest|repayment)|disclosure of default"),
    ("insolvency", "danger", "Insolvency or bankruptcy proceedings",
     "Shareholders are paid last in a bankruptcy and often get nothing.",
     r"insolvency|\bCIRP\b|liquidation|winding[- ]up"),
    ("fraud", "danger", "Fraud, investigation or regulator action reported",
     "Regulator orders and fraud findings can wipe out a stock's value quickly.",
     r"\bfraud|forensic audit|search and seizure|\bSEBI order|show[- ]cause notice"),
    ("rating_down", "warning", "Credit rating was downgraded",
     "Rating agencies think the company is now less able to repay its debt.",
     r"(?=.*credit rating)(?=.*downgrad)"),
    ("key_exit", "warning", "A top executive resigned",
     "Sudden exits of the CEO, CFO or managing director can signal trouble inside.",
     r"(?=.*resign)(?=.*(chief financial|\bCFO\b|chief executive|\bCEO\b|managing director))"),
    ("rating", "info", "Credit rating update",
     "A rating agency reviewed the company's debt. Open the filing to see if it went up or down.",
     r"credit rating"),
]
FEED_RULES = {
    "Sast_Regulation31": ("pledge", "warning", "Promoters pledged or released pledged shares",
                          "Pledging means the owners borrowed money against their shares. If the "
                          "price falls, lenders can sell those shares and push it down further."),
    "Insider_Trading": ("insider", "info", "Company insiders bought or sold shares",
                        "Directors and promoters must report their trades. Buying can be a good "
                        "sign; heavy selling is worth a closer look."),
    "Sast_Regulation29": ("stake", "info", "A large shareholder changed their stake",
                          "Someone holding over 5% bought or sold a meaningful amount."),
}


def price_alerts(rows: list[dict]) -> list[dict]:
    """Alerts from one stock's rows (oldest first; date, close, prev_close, high, value, series)."""
    if not rows:
        return []
    last, out = rows[-1], []

    def add(rule, level, title, detail):
        out.append({"date": last["date"], "rule": rule, "level": level, "title": title,
                    "detail": detail, "link": None, "source": "NSE daily prices"})

    if last["series"] in ("BE", "BZ"):
        add("surveillance", "danger", "Under exchange surveillance",
            "NSE moved this stock to its trade-to-trade segment, where shares cannot be bought and "
            "sold on the same day. Exchanges do this when trading looks unusual or the company "
            "broke listing rules.")
    if last["prev_close"]:
        move = last["close"] / last["prev_close"] - 1
        if abs(move) > 0.20:
            add("big_day", "warning", f"Moved {move:+.0%} in one day",
                "A move this large usually has a reason: results, news, or a rumour. "
                "Find out which before acting.")
    s = analytics.adjusted_series(rows)
    if len(s) > 21 and s[-22][1] > 0:
        month = s[-1][1] / s[-22][1] - 1
        if month <= -0.20:
            add("fall_month", "warning", f"Fell {abs(month):.0%} in a month",
                "A steep, steady fall often means the market knows something negative.")
    recent = rows[-6:]
    if len(recent) == 6:
        locked = sum(1 for r in recent if r["prev_close"] and r["high"]
                     and r["close"] >= r["high"] * 0.999 and r["close"] / r["prev_close"] - 1 >= 0.045)
        typical = statistics.median(r["value"] or 0 for r in rows[-30:])
        if locked >= 4 and typical < PUMP_MAX_VALUE:
            add("pump", "danger", "Possible price manipulation",
                f"It closed at the day's top on {locked} of the last 6 days with very little "
                "trading. This pattern is common in pump-and-dump schemes, where the price is "
                "pushed up to trap buyers.")
    if len(s) >= 200:
        low = min(v for _, v in s[-250:])
        year = s[-1][1] / s[-min(len(s), 250)][1] - 1
        if s[-1][1] <= low * 1.03 and year <= -0.30:
            add("near_low", "watch", "Near its lowest price in a year",
                f"It is down {abs(year):.0%} over the year and still close to the bottom.")
    return out


PATTERNS = ("high_52w", "above_200", "below_200", "volume_surge", "gap_up", "gap_down")
PATTERN_MIN_VALUE = 1e7  # Rs 1 crore on a typical day; thinner stocks make noisy patterns


def pattern_alerts(rows: list[dict]) -> list[dict]:
    """Chart patterns on the latest day. Facts about the price, never a signal (level: info)."""
    if len(rows) < 51:
        return []
    last, out = rows[-1], []
    typical = statistics.median(r["value"] or 0 for r in rows[-51:-1])
    if typical < PATTERN_MIN_VALUE:
        return []

    def add(rule, title, detail):
        out.append({"date": last["date"], "rule": rule, "level": "info", "title": title,
                    "detail": detail, "link": None, "source": "NSE daily prices"})

    closes = [v for _, v in analytics.adjusted_series(rows)]
    if len(closes) >= 240 and closes[-1] > max(closes[-251:-1]):
        add("high_52w", "Closed at its highest price in a year",
            "Some investors read a new high as strength. It also means anyone buying now pays more "
            "than anyone did all year.")
    if len(closes) >= 201:
        now, before = sum(closes[-200:]) / 200, sum(closes[-201:-1]) / 200
        if closes[-1] > now and closes[-2] <= before:
            add("above_200", "Crossed above its 200-day average price",
                "Traders watch this line as a hint that the long-term direction may be turning up. "
                "Prices often cross back within weeks.")
        elif closes[-1] < now and closes[-2] >= before:
            add("below_200", "Fell below its 200-day average price",
                "Traders watch this line as a hint that the long-term direction may be turning down. "
                "Prices often cross back within weeks.")
    if (last["value"] or 0) >= 3 * typical:
        add("volume_surge", f"Trading jumped to {last['value'] / typical:.0f} times a normal day",
            "Far more money changed hands than usual. There is often news behind it; find out what.")
    if last.get("open") and last["prev_close"]:
        gap = last["open"] / last["prev_close"] - 1
        if abs(gap) >= 0.03:
            add("gap_up" if gap > 0 else "gap_down", f"Opened {gap:+.0%} away from the last close",
                "Something changed between the two sessions, often results or news. Check what "
                "before reading anything into it.")
    return out


def announcement_alert(a: dict) -> dict | None:
    """One alert for an announcement row, or None if it is routine."""
    day = (a["published_at"] or "")[:10]
    if a["feed"] in FEED_RULES:
        rule, level, title, why = FEED_RULES[a["feed"]]
        who = a["description"].split(":", 1)[-1].strip() if a["feed"] != "Insider_Trading" else ""
        return {"date": day, "rule": rule, "level": level, "title": title,
                "detail": f"{why}{f' Filed for: {who}.' if who else ''}", "link": a["link"],
                "source": "NSE filing"}
    if a["feed"] == "Corporate_action":
        m = re.search(r"PURPOSE:([^|]+)", a["description"] or "")
        purpose = m.group(1).strip() if m else ""
        if re.search(r"split|bonus", purpose, re.I):
            return {"date": day, "rule": "corp_action", "level": "info", "title": "Share split or bonus",
                    "detail": f"{purpose.capitalize()}. The share price drops on that day, but the "
                              "value of what you hold stays the same.", "link": a["link"],
                    "source": "NSE corporate actions"}
        return None
    text = f"{a['subject'] or ''} | {a['description'] or ''}"
    for rule, level, title, why, pattern in ANNOUNCEMENT_RULES:
        if re.search(pattern, text, re.I):
            return {"date": day, "rule": rule, "level": level, "title": title,
                    "detail": f"{why} Filing: {a['subject'] or a['description'][:120]}.",
                    "link": a["link"], "source": "NSE announcement"}
    return None


def deal_alerts(deals: list[dict]) -> list[dict]:
    out = []
    for d in deals:
        value = d["quantity"] * d["price"]
        if value < BIG_DEAL_VALUE:
            continue
        verb = "bought" if d["side"] == "buy" else "sold"
        out.append({"date": d["date"], "rule": f"deal_{d['side']}", "level": "info",
                    "title": f"Large {d['kind']} deal: Rs {value / 1e7:,.0f} crore {verb}",
                    "detail": f"{d['client'].title()} {verb} {d['quantity']:,} shares at "
                              f"Rs {d['price']:,.2f}. Big investors moving in or out is worth knowing.",
                    "link": None, "source": "NSE bulk and block deals"})
    return out


def compute(conn) -> int:
    latest = conn.execute("SELECT MAX(date) FROM stock_prices").fetchone()[0]
    if not latest:
        return 0
    alerts = []  # (symbol, alert)
    today_syms = {r[0] for r in conn.execute(
        "SELECT symbol FROM stock_prices WHERE date=? AND series IN ('EQ','BE','BZ')", (latest,))}
    by_symbol = defaultdict(list)
    for r in conn.execute(
            "SELECT symbol, date, open, close, prev_close, high, value, series FROM stock_prices"
            " WHERE series IN ('EQ','BE','BZ') AND date >= ? ORDER BY date",
            (_days_before(latest, 400),)):
        if r["symbol"] in today_syms:
            by_symbol[r["symbol"]].append(dict(r))
    for sym, rows in by_symbol.items():
        alerts += [(sym, a) for a in price_alerts(rows) + pattern_alerts(rows)]

    since = (date.fromisoformat(latest) - timedelta(days=WINDOW_DAYS)).isoformat()
    for r in conn.execute("SELECT * FROM announcements WHERE symbol IS NOT NULL AND"
                          " published_at >= ? ORDER BY published_at DESC", (since,)):
        a = announcement_alert(dict(r))
        if a:
            alerts.append((r["symbol"], a))
    deal_day = conn.execute("SELECT MAX(date) FROM deals").fetchone()[0]
    if deal_day:
        for r in conn.execute("SELECT * FROM deals WHERE date=?", (deal_day,)):
            alerts += [(r["symbol"], a) for a in deal_alerts([dict(r)])]

    conn.execute("DELETE FROM alerts")
    conn.executemany(
        "INSERT INTO alerts (symbol, date, rule, level, title, detail, link, source)"
        " VALUES (?,?,?,?,?,?,?,?)",
        [(s, a["date"], a["rule"], a["level"], a["title"], a["detail"], a["link"], a["source"])
         for s, a in alerts])
    conn.commit()
    return len(alerts)


if __name__ == "__main__":
    print(f"Radar raised {compute(db.connect())} alerts")


def _days_before(day: str, n: int) -> str:
    return (date.fromisoformat(day) - timedelta(days=n)).isoformat()
