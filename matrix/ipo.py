"""IPOs: issues open now (with how many times they are subscribed) and how recent IPOs did after
listing, from Matrix's own prices. Facts to research with, not a reason to apply.
"""
import re
import statistics
from datetime import datetime

import httpx

from matrix.sources.nse_flows import HEADERS

PAGE = "https://www.nseindia.com/market-data/all-upcoming-issues-ipo"
CURRENT = "https://www.nseindia.com/api/ipo-current-issue"
PAST = "https://www.nseindia.com/api/public-past-issues"
PAST_SHOWN = 40


def fetch() -> tuple[list[dict], list[dict]]:
    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as c:
        c.get(PAGE).raise_for_status()
        cur, past = c.get(CURRENT), c.get(PAST)
        cur.raise_for_status()
        past.raise_for_status()
        return cur.json(), past.json()


def _day(text: str | None) -> str | None:
    try:
        return datetime.strptime(text.strip().title(), "%d-%b-%Y").date().isoformat()
    except (AttributeError, ValueError):
        return None


def _num(text) -> float | None:
    m = re.findall(r"\d+(?:\.\d+)?", str(text or "").replace(",", ""))
    return float(m[-1]) if m else None  # a price band's top, like "Rs.259 to Rs.272"


def current(items: list[dict]) -> list[dict]:
    out = []
    for it in items:
        if (it.get("category") or "Total") != "Total":
            continue
        out.append({"name": it["companyName"], "symbol": it.get("symbol"), "opens": _day(it.get("issueStartDate")),
                    "closes": _day(it.get("issueEndDate")), "price": it.get("issuePrice"),
                    "subscribed": float(it["noOfTime"]) if it.get("noOfTime") else None,
                    "sme": (it.get("series") or "").upper() == "SME"})
    return out


def past(conn, items: list[dict]) -> dict:
    """Listing-day and latest close against the issue price, for recent IPOs Matrix has prices for."""
    rows = []
    for it in items[:PAST_SHOWN]:
        sym, price, listed = it.get("symbol"), _num(it.get("issuePrice")), _day(it.get("listingDate"))
        if not (sym and price and listed):
            continue
        first = conn.execute("SELECT close FROM stock_prices WHERE symbol=? AND date>=? ORDER BY date LIMIT 1",
                             (sym, listed)).fetchone()
        last = conn.execute("SELECT close, date FROM stock_prices WHERE symbol=? ORDER BY date DESC LIMIT 1",
                            (sym,)).fetchone()
        if not (first and last):
            continue
        rows.append({"name": it.get("companyName") or it.get("company"), "symbol": sym, "listed": listed,
                     "issue_price": price, "sme": (it.get("securityType") or "").upper() == "SME",
                     "listing_day": first[0] / price - 1, "since": last[0] / price - 1, "as_of": last[1]})
    since = [r["since"] for r in rows]
    return {"rows": rows, "count": len(rows),
            "below_issue": sum(x < 0 for x in since) / len(since) if since else None,
            "median_since": statistics.median(since) if since else None,
            "median_listing_day": statistics.median(r["listing_day"] for r in rows) if rows else None}
