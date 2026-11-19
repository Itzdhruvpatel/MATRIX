import io
import zipfile
from datetime import date

from matrix.sources import amfi, nse

NSE_HEADER = ("TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,"
              "FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,"
              "LastPric,PrvsClsgPric,UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,"
              "TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4")
NSE_ROWS = [
    "2026-11-13,2026-11-13,CM,NSE,STK,2885,INE002A01018,RELIANCE,EQ,,,,,RELIANCE INDUSTRIES LTD,"
    "1336.60,1350.70,1324.00,1339.70,1339.70,1320.00,,1339.70,,,13756247,18407210893.70,207960,F1,1,,,,,",
    "2026-11-13,2026-11-13,CM,NSE,STK,1,INE000000001,SOMEBOND,GS,,,,,SOME GOVT BOND,"
    "100,100,100,100,100,100,,100,,,10,1000,1,F1,1,,,,,",
]


def nse_zip(rows):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("bhav.csv", "\n".join([NSE_HEADER] + rows))
    return buf.getvalue()


def test_nse_parse_keeps_equity_and_converts_types():
    rows = nse.parse(nse_zip(NSE_ROWS))
    assert len(rows) == 1  # GS (govt security) series dropped
    r = rows[0]
    assert r["symbol"] == "RELIANCE"
    assert r["date"] == "2026-11-13"
    assert r["close"] == 1339.70 and r["prev_close"] == 1320.00
    assert r["volume"] == 13756247 and r["trades"] == 207960
    assert r["name"] == "RELIANCE INDUSTRIES LTD"


def test_nse_url_format():
    assert nse.url(date(2026, 11, 13)).endswith("BhavCopy_NSE_CM_0_0_0_20261113_F_0000.csv.zip")


AMFI_TEXT = """Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date

Open Ended Schemes(Equity Scheme - Large Cap Fund)

Axis Mutual Fund

120465;INF846K01DP8;-;Axis Large Cap Fund;Direct Plan;Growth Option;65.1200;13-Nov-2026
120466;INF846K01DQ6;INF846K01DR4;Axis Large Cap Fund;Direct Plan;IDCW Option;N.A.;13-Nov-2026

HDFC Mutual Fund

119018;INF179K01XQ0;-;HDFC Large Cap Fund;Regular Plan;Growth Option;1,102.5000;13-Nov-2026
"""


def test_amfi_parse_tracks_category_and_amc_and_skips_na():
    rows = amfi.parse(AMFI_TEXT)
    assert [r["scheme_code"] for r in rows] == ["120465", "119018"]
    a, h = rows
    assert a["amc"] == "Axis Mutual Fund" and h["amc"] == "HDFC Mutual Fund"
    assert a["category"] == "Equity Scheme - Large Cap Fund"
    assert a["plan"] == "Direct Plan" and a["option"] == "Growth Option"
    assert a["isin_growth"] == "INF846K01DP8" and a["isin_reinv"] is None
    assert h["nav"] == 1102.5
    assert a["date"] == "2026-11-13"


def test_amfi_parse_old_six_column_format():
    text = ("Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;"
            "Net Asset Value;Date\nOpen Ended Schemes(Debt Scheme - Liquid Fund)\n\nX Mutual Fund\n"
            "1;INF1;-;X Liquid Fund - Direct Plan - Growth;1000.5;13-Nov-2026\n")
    (r,) = amfi.parse(text)
    assert r["nav"] == 1000.5 and r["plan"] is None and r["amc"] == "X Mutual Fund"


OLD_CSV = """SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,
182D021123,TB,96.77,96.77,96.77,96.77,96.77,96.47,1000,96770,01-JUN-2023,1,IN002023Y052,
TCS,EQ,3314,3340,3297.5,3324,3325,3289.5,1177314,3915200315.1,01-JUN-2023,107605,INE467B01029,
"""


def test_nse_old_format_before_july_2024():
    assert nse.url(date(2023, 6, 1)).endswith("/historical/EQUITIES/2023/JUN/cm01JUN2023bhav.csv.zip")
    assert "BhavCopy_NSE_CM" in nse.url(date(2024, 7, 8))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("cm01JUN2023bhav.csv", OLD_CSV)
    [r] = nse.parse(buf.getvalue())
    assert r == {"date": "2023-06-01", "symbol": "TCS", "isin": "INE467B01029", "name": None, "series": "EQ",
                 "open": 3314.0, "high": 3340.0, "low": 3297.5, "close": 3324.0, "prev_close": 3289.5,
                 "volume": 1177314, "value": 3915200315.1, "trades": 107605}
