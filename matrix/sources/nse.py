"""NSE daily bhavcopy (end-of-day prices for every listed security)."""
import csv
import io
import zipfile
from datetime import date, datetime

import httpx

SOURCE = "nse_bhavcopy"
URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
# Before 8 July 2024 NSE published an older file with different columns (and no company names).
OLD_URL = "https://nsearchives.nseindia.com/content/historical/EQUITIES/{y}/{mon}/cm{dd}{mon}{y}bhav.csv.zip"
NEW_FORMAT_FROM = date(2024, 7, 8)
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130 Safari/537.36"}

# EQ = normal equity, BE/BZ = trade-to-trade (surveillance), SM/ST = SME board.
EQUITY_SERIES = {"EQ", "BE", "BZ", "SM", "ST"}


def url(d: date) -> str:
    if d >= NEW_FORMAT_FROM:
        return URL.format(d=d)
    return OLD_URL.format(y=d.year, mon=d.strftime("%b").upper(), dd=f"{d.day:02d}")


def download(d: date) -> bytes | None:
    """Zip bytes for a trading day, or None when NSE has no file (holiday/weekend)."""
    r = httpx.get(url(d), headers=HEADERS, timeout=30, follow_redirects=True)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.content


def parse(zip_bytes: bytes) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        text = z.read(z.namelist()[0]).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if "SYMBOL" in (reader.fieldnames or []):
        return _parse_old(reader)
    rows = []
    for r in reader:
        if r["SctySrs"] not in EQUITY_SERIES:
            continue
        rows.append({
            "date": r["TradDt"],
            "symbol": r["TckrSymb"],
            "isin": r["ISIN"],
            "name": r["FinInstrmNm"],
            "series": r["SctySrs"],
            "open": float(r["OpnPric"]),
            "high": float(r["HghPric"]),
            "low": float(r["LwPric"]),
            "close": float(r["ClsPric"]),
            "prev_close": float(r["PrvsClsgPric"]),
            "volume": int(r["TtlTradgVol"]),
            "value": float(r["TtlTrfVal"]),
            "trades": int(r["TtlNbOfTxsExctd"] or 0),
        })
    return rows


def _parse_old(reader) -> list[dict]:
    rows = []
    for r in reader:
        r = {k.strip(): (v or "").strip() for k, v in r.items() if k}
        if r["SERIES"] not in EQUITY_SERIES:
            continue
        rows.append({
            "date": datetime.strptime(r["TIMESTAMP"], "%d-%b-%Y").date().isoformat(),
            "symbol": r["SYMBOL"], "isin": r["ISIN"], "name": None, "series": r["SERIES"],
            "open": float(r["OPEN"]), "high": float(r["HIGH"]), "low": float(r["LOW"]),
            "close": float(r["CLOSE"]), "prev_close": float(r["PREVCLOSE"]),
            "volume": int(float(r["TOTTRDQTY"])), "value": float(r["TOTTRDVAL"]),
            "trades": int(r.get("TOTALTRADES") or 0),
        })
    return rows
