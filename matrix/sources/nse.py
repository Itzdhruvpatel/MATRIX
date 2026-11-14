"""NSE daily bhavcopy (end-of-day prices for every listed security)."""
import csv
import io
import zipfile
from datetime import date

import httpx

SOURCE = "nse_bhavcopy"
URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130 Safari/537.36"}

# EQ = normal equity, BE/BZ = trade-to-trade (surveillance), SM/ST = SME board.
EQUITY_SERIES = {"EQ", "BE", "BZ", "SM", "ST"}


def url(d: date) -> str:
    return URL.format(d=d)


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
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
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
