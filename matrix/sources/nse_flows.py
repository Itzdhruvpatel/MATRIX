"""FII/FPI and DII buying and selling in the cash market, from NSE's daily provisional figures.

NSE's report page sets the cookies its data API needs, so the page is opened first.
The API only returns the latest day; Matrix keeps every day it has seen.
"""
from datetime import datetime

import httpx

SOURCE = "nse_fii_dii"
PAGE = "https://www.nseindia.com/reports/fii-dii"
API = "https://www.nseindia.com/api/fiidiiTradeReact"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
                         " Chrome/124 Safari/537.36",
           "Accept": "application/json,text/html", "Accept-Language": "en-US,en;q=0.9", "Referer": PAGE}


def fetch() -> list[dict]:
    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as c:
        c.get(PAGE).raise_for_status()
        r = c.get(API)
        r.raise_for_status()
        return r.json()


def parse(items: list[dict]) -> list[dict]:
    """Rows of date, who (FII or DII), and Rs crore bought, sold and net."""
    out = []
    for it in items:
        who = "FII" if "FII" in it["category"].upper() else "DII" if "DII" in it["category"].upper() else None
        if not who:
            continue
        out.append({"date": datetime.strptime(it["date"], "%d-%b-%Y").date().isoformat(), "who": who,
                    "buy": float(it["buyValue"]), "sell": float(it["sellValue"]),
                    "net": float(it["netValue"])})
    return out
