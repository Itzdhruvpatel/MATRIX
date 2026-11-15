from matrix import db, pipeline
from matrix.sources import nse_feeds

RSS = """<?xml version="1.0"?><rss><channel><title>NSE News</title>
<item><title>Hindalco Industries Limited</title><link>https://nsearchives.nseindia.com/a.xml</link>
<description>HINDALCO INDUSTRIES LIMITED has informed the Exchange regarding Sale or disposal |SUBJECT: Sale or disposal-XBRL</description>
<pubDate>15-Nov-2026 10:22:10</pubDate></item>
<item><title>Shaky Corp Limited</title><link>https://nsearchives.nseindia.com/b.pdf</link>
<description>Shaky Corp Limited has informed the Exchange regarding Resignation of Statutory Auditor |SUBJECT: Change in Auditors</description>
<pubDate>14-Nov-2026 18:05</pubDate></item>
</channel></rss>"""

BULK = """Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Traded,Trade Price / Wght. Avg. Price,Remarks
13-NOV-2026,ALICON,Alicon Castalloy Limited,JUNOMONETA FINSOL PRIVATE LIMITED,BUY,95589,941.01,-
13-NOV-2026,ALICON,Alicon Castalloy Limited,SOME FUND,SELL,"1,20,000",940.00,-
"""


def test_parse_rss_extracts_subject_and_date():
    items = nse_feeds.parse_rss(RSS)
    assert len(items) == 2
    a = items[0]
    assert a["company"] == "Hindalco Industries Limited"
    assert a["subject"] == "Sale or disposal-XBRL"
    assert a["published_at"] == "2026-11-15T10:22:10"
    assert items[1]["published_at"] == "2026-11-14T18:05:00"  # seconds optional
    assert a["link"].endswith("a.xml")


def test_parse_deals_handles_indian_commas():
    deals = nse_feeds.parse_deals(BULK)
    assert deals[0] == {"date": "2026-11-13", "symbol": "ALICON", "client": "JUNOMONETA FINSOL PRIVATE LIMITED",
                        "side": "buy", "quantity": 95589, "price": 941.01}
    assert deals[1]["quantity"] == 120000 and deals[1]["side"] == "sell"


def test_name_key_matches_exchange_spellings():
    k = nse_feeds.name_key
    assert k("Hindalco Industries Limited") == k("HINDALCO INDUSTRIES LTD")
    assert k("K.P. Energy Limited") == k("K.P. ENERGY LIMITED")
    assert k("Tata Motors Ltd.") == k("TATA MOTORS LIMITED")


def test_load_feeds_maps_company_to_symbol_and_is_idempotent():
    conn = db.connect(":memory:")
    conn.execute("INSERT INTO stock_prices (symbol, date, name, series, close, prev_close, source, fetched_at)"
                 " VALUES ('HINDALCO', '2026-11-13', 'HINDALCO INDUSTRIES LTD', 'EQ', 700, 690, 't', 't')")
    fetch_rss = lambda feed: RSS if feed == "Online_announcements" else "<rss><channel></channel></rss>"
    fetch_deals = lambda kind: BULK if kind == "bulk" else BULK.split("\n")[0] + "\n"
    for _ in range(2):
        s = pipeline.load_feeds(conn, fetch_rss=fetch_rss, fetch_deals=fetch_deals)
    assert s["status"] == "ok"
    rows = conn.execute("SELECT company, symbol, feed FROM announcements ORDER BY company").fetchall()
    assert [tuple(r) for r in rows] == [("Hindalco Industries Limited", "HINDALCO", "Online_announcements"),
                                        ("Shaky Corp Limited", None, "Online_announcements")]
    assert conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0] == 2


def test_load_feeds_survives_one_feed_failing():
    def fetch_rss(feed):
        if feed == "Insider_Trading":
            raise ConnectionError("down")
        return RSS
    conn = db.connect(":memory:")
    s = pipeline.load_feeds(conn, fetch_rss=fetch_rss, fetch_deals=lambda k: BULK)
    assert s["status"] == "ok" and s["issues"] == 1
    assert conn.execute("SELECT COUNT(*) FROM announcements").fetchone()[0] > 0


def test_match_symbol_handles_truncated_names_and_refuses_ambiguity():
    index = {nse_feeds.name_key(n): s for n, s in [
        ("LLOYDS ENGINEERING WORKS L", "LLOYDSENGG"), ("HINDALCO INDUSTRIES LTD", "HINDALCO"),
        ("TATA MOTORS PASSENGER VEHIC", "TMPV"), ("TATA MOTORS PASSENGER VEHIX", "OTHER")]}
    m = nse_feeds.match_symbol
    assert m("Lloyds Engineering Works Limited", index) == "LLOYDSENGG"
    assert m("Hindalco Industries Limited", index) == "HINDALCO"
    assert m("Tata Motors Passenger Vehicles Limited", index) is None  # two candidates
    assert m("Unknown Company Limited", index) is None
