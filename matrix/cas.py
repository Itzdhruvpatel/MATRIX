"""Import every investment from a CAS (Consolidated Account Statement) PDF.

CAMS/KFintech CAS: every mutual fund under your PAN, whichever app you bought it through,
with the full list of purchases and sales. NSDL/CDSL CAS: what sits in your demat account
today (stocks and funds), without purchase prices.

The PDF password is used for one parse and is never stored or logged.
"""
import io
from collections import Counter
from datetime import datetime

from matrix import portfolio


class CasError(Exception):
    """A message that is safe to show the user."""


def read_pdf(pdf: bytes, password: str) -> dict:
    import casparser
    from casparser.exceptions import IncorrectPasswordError

    try:
        data = casparser.read_cas_pdf(io.BytesIO(pdf), password)
    except IncorrectPasswordError:
        raise CasError("That password did not open the PDF. For a CAS it is usually the one you"
                       " chose when you asked for the statement, or your PAN in capitals.") from None
    except Exception:
        raise CasError("Could not read this file as a CAS statement. Use the PDF from CAMS,"
                       " KFintech, NSDL or CDSL exactly as it was emailed to you.") from None
    return data.model_dump(by_alias=True)


def _day(value) -> str:
    """CAS dates come as dates or text like 13-Nov-2026 or 13/11/2026."""
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y", "%d/%b/%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date().isoformat()
        except ValueError:
            pass
    raise CasError(f"Unexpected date '{value}' in the statement")


def _fund_code(conn, amfi, isin) -> str | None:
    if amfi and conn.execute("SELECT 1 FROM funds WHERE scheme_code=?", (str(amfi),)).fetchone():
        return str(amfi)
    if isin:
        r = conn.execute("SELECT scheme_code FROM funds WHERE isin_growth=? OR isin_reinv=?",
                         (isin, isin)).fetchone()
        if r:
            return r[0]
    return None


def _stock_symbol(conn, isin) -> str | None:
    r = conn.execute("SELECT symbol FROM stock_prices WHERE isin=? AND date="
                     "(SELECT MAX(date) FROM stock_prices) LIMIT 1", (isin,)).fetchone()
    return r[0] if r else None


def to_transactions(conn, data: dict) -> dict:
    """Turn a parsed CAS into Matrix transactions. Nothing is saved here."""
    items, errors, skipped, holdings = [], [], [], []
    holdings_only = 0

    def add(label, kind, code, side, day, qty, price, source):
        items.append((label, {"kind": kind, "code": code, "side": side, "date": day,
                              "quantity": round(abs(float(qty)), 6), "price": float(price),
                              "note": source}))

    def holding(name, kind, code, source):
        if (kind, code, source) not in {(h["kind"], h["code"], h["source"]) for h in holdings}:
            holdings.append({"name": name, "kind": kind, "code": code, "source": source})

    for folio in data.get("folios") or []:
        for s in folio.get("schemes") or []:
            name = s["scheme"]
            source = f"{folio['amc']}, folio {folio['folio']}"
            if s.get("advisor"):
                source += f", advisor {s['advisor']}"
            close = float(s.get("close") or 0)
            code = _fund_code(conn, s.get("amfi"), s.get("isin"))
            if code is None:
                if close <= 1e-6:
                    skipped.append(f"{name} (fully sold and no longer in the fund list)")
                else:
                    errors.append(f"{name}: fund not found in Matrix's fund list")
                continue
            if float(s.get("open") or 0) > 1e-6:
                errors.append(f"{name}: this statement starts after your first purchase. Ask for"
                              " the CAS with the period from the start (for example from 1990)")
                continue
            txs = s.get("transactions") or []
            if not txs and close > 1e-6:  # summary CAS: balance only, no history
                v = s["valuation"]
                add(name, "fund", code, "buy", _day(v["date"]), close, v["nav"],
                    source + " (purchase price not in statement)")
                holdings_only += 1
            for t in txs:
                units, nav = t.get("units"), t.get("nav")
                if not units or not nav or float(nav) <= 0:
                    continue  # stamp duty, tax and dividend payout lines move no units
                add(name, "fund", code, "buy" if float(units) > 0 else "sell", _day(t["date"]),
                    units, nav, source)
            holding(name, "fund", code, source)

    for acc in data.get("accounts") or []:
        source = f"Demat at {acc['name']}"
        if acc.get("client_id"):
            source += f", client {acc['client_id']}"
        source += " (purchase price not in statement)"
        day = _day(data["statement_period"]["to"])
        for e in acc.get("equities") or []:
            if not float(e.get("num_shares") or 0):
                continue
            name = e.get("name") or e["isin"]
            sym = _stock_symbol(conn, e["isin"])
            if sym is None:
                errors.append(f"{name}: stock {e['isin']} not found on NSE in Matrix")
                continue
            add(name, "stock", sym, "buy", day, e["num_shares"], e["price"], source)
            holding(name, "stock", sym, source)
            holdings_only += 1
        for m in acc.get("mutual_funds") or []:
            if not float(m.get("balance") or 0):
                continue
            name = m.get("name") or m["isin"]
            code = _fund_code(conn, m.get("amfi"), m["isin"])
            if code is None:
                errors.append(f"{name}: fund not found in Matrix's fund list")
                continue
            add(name, "fund", code, "buy", day, m["balance"], m["nav"], source)
            holding(name, "fund", code, source)
            holdings_only += 1
        if acc.get("bonds"):
            skipped.append(f"{len(acc['bonds'])} bond(s) at {acc['name']} (Matrix does not track bonds)")

    if not items and not errors:
        errors.append("No holdings found in this statement")
    return {"items": items, "errors": errors, "skipped": skipped, "holdings": holdings,
            "holdings_only": holdings_only}


def import_cas(conn, username: str, data: dict) -> dict:
    """All-or-nothing import into the real book. Lines already saved earlier are skipped."""
    r = to_transactions(conn, data)
    out = {k: r[k] for k in ("skipped", "holdings", "holdings_only")}
    if r["errors"]:
        return {**out, "added": 0, "already": 0, "errors": r["errors"][:20]}
    have = Counter((t[0], t[1], t[2], t[3], round(t[4], 3)) for t in conn.execute(
        "SELECT kind, code, side, date, quantity FROM transactions WHERE username=? AND book='real'",
        (username,)))
    new = []
    for label, t in r["items"]:
        key = (t["kind"], t["code"], t["side"], t["date"], round(t["quantity"], 3))
        if have[key]:
            have[key] -= 1
        else:
            new.append((label, t))
    errors = portfolio.add_many(conn, username, new, "real") if new else []
    return {**out, "added": 0 if errors else len(new), "already": len(r["items"]) - len(new),
            "errors": errors}
