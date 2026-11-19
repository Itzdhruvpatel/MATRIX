from pathlib import Path

from matrix import db, pipeline, radar
from matrix.sources import nse_insider

XML = """<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-capmkt="http://x">
<in-capmkt:NSESymbol contextRef="OneD">BAJAJFINSV</in-capmkt:NSESymbol>
<in-capmkt:CategoryOfPerson contextRef="T1">Promoters</in-capmkt:CategoryOfPerson>
<in-capmkt:NameOfThePerson contextRef="T1">Holding A</in-capmkt:NameOfThePerson>
<in-capmkt:SecuritiesAcquiredOrDisposedNumberOfSecurity contextRef="T1">2090050</in-capmkt:SecuritiesAcquiredOrDisposedNumberOfSecurity>
<in-capmkt:SecuritiesAcquiredOrDisposedValueOfSecurity contextRef="T1">3700224520</in-capmkt:SecuritiesAcquiredOrDisposedValueOfSecurity>
<in-capmkt:SecuritiesAcquiredOrDisposedTransactionType contextRef="T1">Buy</in-capmkt:SecuritiesAcquiredOrDisposedTransactionType>
<in-capmkt:ModeOfAcquisitionOrDisposal contextRef="T1">Market Purchase</in-capmkt:ModeOfAcquisitionOrDisposal>
<in-capmkt:CategoryOfPerson contextRef="T2">Promoter Group</in-capmkt:CategoryOfPerson>
<in-capmkt:NameOfThePerson contextRef="T2">Holding B</in-capmkt:NameOfThePerson>
<in-capmkt:SecuritiesAcquiredOrDisposedNumberOfSecurity contextRef="T2">2090050</in-capmkt:SecuritiesAcquiredOrDisposedNumberOfSecurity>
<in-capmkt:SecuritiesAcquiredOrDisposedValueOfSecurity contextRef="T2">3700779428</in-capmkt:SecuritiesAcquiredOrDisposedValueOfSecurity>
<in-capmkt:SecuritiesAcquiredOrDisposedTransactionType contextRef="T2">Sell</in-capmkt:SecuritiesAcquiredOrDisposedTransactionType>
<in-capmkt:SecuritiesHeldPostAcquistionOrDisposalPercentageOfShareholding contextRef="T2">0</in-capmkt:SecuritiesHeldPostAcquistionOrDisposalPercentageOfShareholding>
<in-capmkt:ModeOfAcquisitionOrDisposal contextRef="T2">Market Sale</in-capmkt:ModeOfAcquisitionOrDisposal>
</xbrli:xbrl>"""
ANN = {"published_at": "2026-04-28T10:00:00", "link": "https://x/IT_1.xml"}


def trade(side, category="Director", mode="Market Sale", value=5e7, shares=1000):
    return {"side": side, "category": category, "person": "A Person", "mode": mode, "value": value,
            "shares": shares, "traded_on": "2026-04-27", "held_after_pct": 1.5}


def test_parse_groups_trades_by_context():
    t = nse_insider.parse(XML)
    assert [(x["person"], x["side"], x["symbol"]) for x in t] == [
        ("Holding A", "buy", "BAJAJFINSV"), ("Holding B", "sell", "BAJAJFINSV")]
    assert t[1]["held_after_pct"] == 0 and t[0]["value"] == 3700224520


def test_alert_levels():
    sale = radar.insider_alerts(ANN, [trade("sell")])
    assert sale[0]["rule"] == "insider_sell" and sale[0]["level"] == "warning"
    assert "Rs 5.0 crore" in sale[0]["title"] and "Now holds 1.5%" in sale[0]["detail"]
    assert radar.insider_alerts(ANN, [trade("sell", mode="ESOP")])[0]["level"] == "info"
    assert radar.insider_alerts(ANN, [trade("sell", value=1e5)])[0]["rule"] == "insider"
    assert radar.insider_alerts(ANN, [trade("buy", category="Promoters")])[0]["rule"] == "insider_buy"
    # Bought and sold the same number of shares in one filing: a transfer, reported once as Info.
    moved = radar.insider_alerts(ANN, nse_insider.parse(XML))
    assert len(moved) == 1 and moved[0]["level"] == "info" and "promoter group" in moved[0]["title"]


def test_loader_reads_each_filing_once_and_radar_uses_details():
    conn = db.connect(":memory:")
    conn.execute("INSERT INTO stock_prices (symbol, date, series, close, prev_close, high, value, source,"
                 " fetched_at) VALUES ('BAJAJFINSV', '2026-04-28', 'EQ', 100, 100, 100, 1e9, 't', 't')")
    for i, link in enumerate(("https://x/IT_1.xml", "https://x/IT_2.xml")):
        conn.execute("INSERT INTO announcements (id, feed, company, symbol, subject, description, link,"
                     " published_at, source, fetched_at) VALUES (?, 'Insider_Trading', 'Bajaj Finserv',"
                     " 'BAJAJFINSV', NULL, 'TYPE OF SECURITY : Equity Shares', ?, '2026-04-28T10:00:00', 't', 't')",
                     (str(i), link))
    files = {"https://x/IT_1.xml": XML, "https://x/IT_2.xml": "<xbrl/>"}
    asked = []
    fetch = lambda link: asked.append(link) or files[link]  # noqa: E731
    assert pipeline.load_insider(conn, fetch, pause=0)["rows"] == 2
    assert pipeline.load_insider(conn, fetch, pause=0)["rows"] == 0 and len(asked) == 2  # not fetched again
    radar.compute(conn)
    got = [r[0] for r in conn.execute("SELECT title FROM alerts WHERE symbol='BAJAJFINSV' ORDER BY title")]
    # The detailed filing gives one transfer alert; the empty one falls back to the general alert.
    assert got == ["Company insiders bought or sold shares", "Shares moved within the promoter group"]


def test_pledge_and_small_amounts():
    p = radar.insider_alerts(ANN, [trade("pledge", value=2e5)])[0]
    assert p["level"] == "warning" and "pledged 1,000 shares worth Rs 2.0 lakh" in p["detail"]
