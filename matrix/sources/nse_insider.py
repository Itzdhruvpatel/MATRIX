"""Insider trade details from the XBRL file linked in each NSE insider trading filing.

Who traded (name and role), buy or sell, how many shares, the value, and how (open market,
ESOP, gift...). One filing can hold several trades; they are grouped by the file's contexts.
"""
import xml.etree.ElementTree as ET
from collections import defaultdict

import httpx

SOURCE = "nse_insider"
HEADERS = {"User-Agent": "Mozilla/5.0"}
FIELDS = {
    "NSESymbol": "symbol", "CategoryOfPerson": "category", "NameOfThePerson": "person",
    "SecuritiesAcquiredOrDisposedNumberOfSecurity": "shares",
    "SecuritiesAcquiredOrDisposedValueOfSecurity": "value",
    "SecuritiesAcquiredOrDisposedTransactionType": "side",
    "SecuritiesHeldPostAcquistionOrDisposalPercentageOfShareholding": "held_after_pct",
    "DateOfAllotmentAdviceOrAcquisitionOfSharesOrSaleOfSharesSpecifyToDate": "traded_on",
    "ModeOfAcquisitionOrDisposal": "mode", "TypeOfInstrument": "instrument",
}
NUMBERS = {"shares", "value", "held_after_pct"}


def fetch(link: str) -> str:
    r = httpx.get(link, headers=HEADERS, timeout=30, follow_redirects=True)
    r.raise_for_status()
    return r.text


def parse(xml: str) -> list[dict]:
    root = ET.fromstring(xml)
    shared, by_context = {}, defaultdict(dict)
    for el in root.iter():
        name = el.tag.rsplit("}", 1)[-1]
        if name not in FIELDS or el.text is None:
            continue
        value = el.text.strip()
        if FIELDS[name] in NUMBERS:
            try:
                value = float(value)
            except ValueError:
                value = None
        by_context[el.get("contextRef")][FIELDS[name]] = value
    for ctx in list(by_context):  # facts that are the same for every trade (like the symbol)
        if "side" not in by_context[ctx]:
            shared.update(by_context.pop(ctx))
    trades = []
    for ctx, t in by_context.items():
        t = {**shared, **t}
        side = (t.get("side") or "").lower()
        t["side"] = "buy" if side.startswith(("buy", "acq")) else "sell" if side.startswith(("sell", "dis")) else side
        trades.append(t)
    return trades
