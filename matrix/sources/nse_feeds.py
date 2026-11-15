"""NSE public feeds: official RSS (announcements, insider trades, pledges, corporate actions)
and the daily bulk and block deal files."""
import csv
import html
import io
import re
from datetime import datetime

import httpx

SOURCE = "nse_feeds"
RSS_URL = "https://nsearchives.nseindia.com/content/RSS/{feed}.xml"
DEALS_URL = "https://nsearchives.nseindia.com/content/equities/{kind}.csv"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# feed name -> what it carries
FEEDS = {
    "Online_announcements": "Company announcements",
    "Insider_Trading": "Insider trading disclosures",
    "Sast_Regulation31": "Promoter share pledges",
    "Sast_Regulation29": "Large shareholding changes",
    "Corporate_action": "Dividends, splits and bonuses",
}
DEAL_KINDS = ("bulk", "block")

ITEM = re.compile(r"<item>(.*?)</item>", re.S)
SUFFIXES = re.compile(r"\b(LIMITED|LTD|INDIA|THE|COMPANY|CO|CORPORATION|CORP)\b")


def fetch_rss(feed: str) -> str:
    r = httpx.get(RSS_URL.format(feed=feed), headers=HEADERS, timeout=40, follow_redirects=True)
    r.raise_for_status()
    return r.text


def fetch_deals(kind: str) -> str:
    r = httpx.get(DEALS_URL.format(kind=kind), headers=HEADERS, timeout=40, follow_redirects=True)
    r.raise_for_status()
    return r.text


def _tag(block: str, name: str) -> str:
    m = re.search(rf"<{name}>(.*?)</{name}>", block, re.S)
    text = m.group(1).strip() if m else ""
    if text.startswith("<![CDATA["):
        text = text[9:-3]
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def _when(text: str) -> str | None:
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, fmt).isoformat(timespec="seconds")
        except ValueError:
            pass
    return None


def parse_rss(xml: str) -> list[dict]:
    items = []
    for block in ITEM.findall(xml):
        title, desc = _tag(block, "title"), _tag(block, "description")
        company = title.split(" - Ex-Date")[0].strip()
        body, _, subject = desc.partition("|SUBJECT:")
        items.append({
            "company": company, "title": title, "subject": subject.strip() or None,
            "description": body.strip(), "link": _tag(block, "link"),
            "published_at": _when(_tag(block, "pubDate")),
        })
    return items


def parse_deals(text: str) -> list[dict]:
    deals = []
    for r in csv.DictReader(io.StringIO(text.strip())):
        try:
            deals.append({
                "date": datetime.strptime(r["Date"].strip().title(), "%d-%b-%Y").date().isoformat(),
                "symbol": r["Symbol"].strip(),
                "client": r["Client Name"].strip(),
                "side": r["Buy/Sell"].strip().lower(),
                "quantity": int(r["Quantity Traded"].replace(",", "")),
                "price": float(r["Trade Price / Wght. Avg. Price"].replace(",", "")),
            })
        except (KeyError, ValueError):
            continue  # "NO RECORDS" line on days without deals
    return deals


def name_key(name: str) -> str:
    """Normalise a company name so feed titles match price-file names."""
    s = re.sub(r"[^A-Z0-9 ]", " ", name.upper().replace("&", " AND "))
    return re.sub(r"\s+", "", SUFFIXES.sub(" ", s))


def match_symbol(company: str, index: dict[str, str]) -> str | None:
    """Symbol for a company name. `index` maps name_key -> symbol.

    The price file cuts long names short ("LLOYDS ENGINEERING WORKS L"), so when there is
    no exact match, accept a single candidate that shares a long common prefix.
    """
    key = name_key(company)
    if key in index:
        return index[key]
    hits = set()
    for other, symbol in index.items():
        n = min(len(key), len(other)) - 3
        if n >= 10 and key[:n] == other[:n]:
            hits.add(symbol)
    return hits.pop() if len(hits) == 1 else None
