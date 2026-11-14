"""Full NAV history for one scheme from mfapi.in (a public mirror of AMFI data).

Official AMFI NAVs always win: history from here only fills dates AMFI rows don't cover,
and overlapping dates are cross-checked.
"""
from datetime import datetime

import httpx

SOURCE = "mfapi"
URL = "https://api.mfapi.in/mf/{code}"


def download(code: str) -> dict:
    r = httpx.get(URL.format(code=code), timeout=30)
    r.raise_for_status()
    return r.json()


def parse(payload: dict) -> list[dict]:
    rows = []
    for p in payload.get("data", []):
        try:
            nav = float(p["nav"])
        except (KeyError, ValueError):
            continue
        if nav > 0:
            rows.append({"date": datetime.strptime(p["date"], "%d-%m-%Y").date().isoformat(),
                         "nav": nav})
    return sorted(rows, key=lambda r: r["date"])
