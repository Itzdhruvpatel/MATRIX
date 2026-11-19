"""The economy in a few numbers: RBI's "Current Rates" box (policy rates, rupee, deposit rates,
government bond yields) and India VIX from NSE.

RBI publishes these on its home page; Matrix keeps one snapshot a day.
"""
import html
import re

import httpx

SOURCE = "rbi_nse_macro"
RBI = "https://www.rbi.org.in/"
NSE_PAGE = "https://www.nseindia.com/market-data/live-market-indices"
NSE_API = "https://www.nseindia.com/api/allIndices"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
                         " Chrome/124 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}
NUM = r"([\d.]+)"
PATTERNS = {
    "repo": rf"Policy Repo Rate : {NUM}%",
    "crr": rf"CRR : {NUM}%",
    "slr": rf"SLR : {NUM}%",
    "usd_inr": rf"INR / 1 USD : {NUM}",
    "eur_inr": rf"INR / 1 EUR : {NUM}",
    "gbp_inr": rf"INR / 1 GBP : {NUM}",
    "fd_low": rf"Term Deposit Rate > 1 Year : {NUM}% - {NUM}%",
    "savings": rf"Savings Deposit Rate : {NUM}%",
    "tbill_91": rf"91 day T-bills : {NUM}%",
    "tbill_364": rf"364 day T-bills : {NUM}%",
}


def fetch_rbi() -> str:
    r = httpx.get(RBI, headers=HEADERS, timeout=30, follow_redirects=True)
    r.raise_for_status()
    return r.text


def fetch_vix() -> float | None:
    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as c:
        c.get(NSE_PAGE).raise_for_status()
        r = c.get(NSE_API)
        r.raise_for_status()
    return next((float(d["last"]) for d in r.json()["data"] if d["index"] == "INDIA VIX"), None)


def parse_rbi(page: str) -> dict[str, float]:
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
    out = {}
    for key, pattern in PATTERNS.items():
        m = re.search(pattern, text)
        if m:
            out[key] = float(m.group(1))
            if key == "fd_low":
                out["fd_high"] = float(m.group(2))
    # Government bond yields by the year each bond ends, like "6.94% GS 2036 : 7.2795%".
    for year, yld in re.findall(r"[\d.]+% GS (\d{4}) : ([\d.]+)%", text):
        out[f"gsec_{year}"] = float(yld)
    return out
