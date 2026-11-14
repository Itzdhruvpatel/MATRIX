"""AMFI daily NAV file for every mutual fund scheme in India."""
import re
from datetime import datetime

import httpx

SOURCE = "amfi_navall"
URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
CATEGORY = re.compile(r"^(?:Open|Close|Interval)[^(]*\((.*)\)\s*$")


def download() -> str:
    r = httpx.get(URL, timeout=60, follow_redirects=True)
    r.raise_for_status()
    return r.text


def _num(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None  # "N.A." and similar


def parse(text: str) -> list[dict]:
    """File layout: a category line, then an AMC name line, then scheme rows (';' separated)."""
    lines = text.splitlines()
    eight_cols = "Plan;Option" in lines[0]
    category = amc = None
    rows = []
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        if ";" not in line:
            m = CATEGORY.match(line)
            if m:
                category = m.group(1).strip()
            else:
                amc = line
            continue
        f = [x.strip() for x in line.split(";")]
        if eight_cols:
            code, isin_g, isin_r, name, plan, option, nav, day = f[:8]
        else:
            code, isin_g, isin_r, name, nav, day = f[:6]
            plan = option = None
        nav = _num(nav)
        if nav is None:
            continue
        rows.append({
            "scheme_code": code,
            "isin_growth": None if isin_g in ("-", "") else isin_g,
            "isin_reinv": None if isin_r in ("-", "") else isin_r,
            "name": name,
            "plan": plan or None,
            "option": option or None,
            "nav": nav,
            "date": datetime.strptime(day, "%d-%b-%Y").date().isoformat(),
            "amc": amc,
            "category": category,
        })
    return rows
