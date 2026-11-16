"""Holdings, gains and true returns (XIRR) from a user's transactions."""
import csv
import io
from collections import defaultdict
from datetime import date

from matrix import analytics

MAX_SINGLE_STOCK = 0.10  # design rule: no single stock over 10% of the portfolio
MAX_IMPORT_ROWS = 5000


def latest_price(conn, kind: str, code: str) -> tuple[float, str] | None:
    if kind == "stock":
        r = conn.execute("SELECT close, date FROM stock_prices WHERE symbol=? ORDER BY date DESC"
                         " LIMIT 1", (code,)).fetchone()
    else:
        r = conn.execute("SELECT nav, date FROM fund_navs WHERE scheme_code=? ORDER BY date DESC"
                         " LIMIT 1", (code,)).fetchone()
    return (r[0], r[1]) if r else None


def name_of(conn, kind: str, code: str) -> str:
    sql = ("SELECT name FROM stock_prices WHERE symbol=? ORDER BY date DESC LIMIT 1"
           if kind == "stock" else "SELECT name FROM funds WHERE scheme_code=?")
    r = conn.execute(sql, (code,)).fetchone()
    return r[0] if r else code


def validate_tx(conn, tx: dict, held: dict) -> str | None:
    """Error text, or None if the transaction is acceptable."""
    if tx["kind"] not in ("stock", "fund"):
        return "type must be 'stock' or 'fund'"
    if tx["side"] not in ("buy", "sell"):
        return "side must be 'buy' or 'sell'"
    try:
        d = date.fromisoformat(tx["date"])
    except (TypeError, ValueError):
        return "date must look like 2026-11-13"
    if d > date.today():
        return "date is in the future"
    if not (tx["quantity"] > 0 and tx["price"] > 0):
        return "quantity and price must be above zero"
    if latest_price(conn, tx["kind"], tx["code"]) is None:
        return f"unknown {tx['kind']} '{tx['code']}'"
    key = (tx["kind"], tx["code"])
    if tx["side"] == "sell" and tx["quantity"] > held.get(key, 0) + 1e-9:
        return f"selling {tx['quantity']} but only {held.get(key, 0):g} held"
    return None


BOOKS = ("real", "paper")  # paper = practice money


def holdings_qty(conn, username: str, book: str = "real") -> dict:
    held = defaultdict(float)
    for r in conn.execute("SELECT kind, code, side, quantity FROM transactions WHERE username=?"
                          " AND book=?", (username, book)):
        held[(r[0], r[1])] += r[3] if r[2] == "buy" else -r[3]
    return held


def add(conn, username: str, tx: dict) -> str | None:
    tx = {**tx, "code": str(tx["code"]).strip().upper() if tx["kind"] == "stock"
          else str(tx["code"]).strip()}
    book = tx.get("book") or "real"
    if book not in BOOKS:
        return "book must be 'real' or 'paper'"
    err = validate_tx(conn, tx, holdings_qty(conn, username, book))
    if err:
        return err
    conn.execute(
        "INSERT INTO transactions (username, kind, code, side, date, quantity, price, note,"
        " book, created_at) VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
        (username, tx["kind"], tx["code"], tx["side"], tx["date"], tx["quantity"], tx["price"],
         tx.get("note"), book))
    conn.commit()
    return None


def import_csv(conn, username: str, text: str, book: str = "real") -> dict:
    """All-or-nothing import. Columns: type,code,side,date,quantity,price"""
    reader = csv.DictReader(io.StringIO(text.strip()))
    need = {"type", "code", "side", "date", "quantity", "price"}
    if not reader.fieldnames or not need <= {f.strip().lower() for f in reader.fieldnames}:
        return {"added": 0, "errors": [f"header must include: {', '.join(sorted(need))}"]}
    rows = []
    for line, raw in enumerate(reader, start=2):
        r = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        kind = r["type"].lower()
        try:
            rows.append((f"line {line}", {
                "kind": kind, "code": r["code"].upper() if kind == "stock" else r["code"],
                "side": r["side"].lower(), "date": r["date"], "quantity": float(r["quantity"]),
                "price": float(r["price"])}))
        except ValueError:
            return {"added": 0, "errors": [f"line {line}: quantity and price must be numbers"]}
        if len(rows) > MAX_IMPORT_ROWS:
            return {"added": 0, "errors": [f"more than {MAX_IMPORT_ROWS} rows"]}
    if book not in BOOKS:
        return {"added": 0, "errors": ["book must be 'real' or 'paper'"]}
    errors = add_many(conn, username, rows, book)
    return {"added": 0 if errors else len(rows), "errors": errors}


def add_many(conn, username: str, items: list[tuple[str, dict]], book: str = "real") -> list[str]:
    """All-or-nothing: check every (label, tx) in date order; save all only if none fail."""
    held = holdings_qty(conn, username, book)
    errors = []
    for label, tx in sorted(items, key=lambda x: x[1]["date"]):
        err = validate_tx(conn, tx, held)
        if err:
            errors.append(f"{label}: {err}")
            continue
        held[(tx["kind"], tx["code"])] += tx["quantity"] if tx["side"] == "buy" else -tx["quantity"]
    if errors:
        return errors[:20]
    conn.executemany(
        "INSERT INTO transactions (username, kind, code, side, date, quantity, price, note, book,"
        " created_at) VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
        [(username, t["kind"], t["code"], t["side"], t["date"], t["quantity"], t["price"],
          t.get("note"), book) for _, t in items])
    conn.commit()
    return []


def summary(conn, username: str, book: str = "real") -> dict:
    txs = [dict(r) for r in conn.execute(
        "SELECT * FROM transactions WHERE username=? AND book=? ORDER BY date, id", (username, book))]
    groups = defaultdict(list)
    for t in txs:
        groups[(t["kind"], t["code"])].append(t)

    holdings, all_flows, warnings = [], [], []
    total_value = total_cost = realised = 0.0
    for (kind, code), ts in groups.items():
        qty = cost = gain_booked = 0.0
        flows = []
        for t in ts:
            amount = t["quantity"] * t["price"]
            d = date.fromisoformat(t["date"])
            if t["side"] == "buy":
                qty += t["quantity"]
                cost += amount
                flows.append((d, -amount))
            else:
                avg = cost / qty if qty else 0
                gain_booked += (t["price"] - avg) * t["quantity"]
                cost -= avg * t["quantity"]
                qty -= t["quantity"]
                flows.append((d, amount))
        lp = latest_price(conn, kind, code)
        price, as_of = lp if lp else (None, None)
        value = qty * price if price else 0.0
        if qty > 1e-9 and as_of:
            flows.append((date.fromisoformat(as_of), value))
        all_flows += flows
        realised += gain_booked
        if qty <= 1e-9:
            continue
        total_value += value
        total_cost += cost
        holdings.append({
            "kind": kind, "code": code, "name": name_of(conn, kind, code), "quantity": qty,
            "avg_cost": cost / qty, "price": price, "price_date": as_of, "invested": cost,
            "value": value, "gain": value - cost, "gain_pct": (value / cost - 1) if cost else None,
            "xirr": analytics.xirr(flows),
            "sources": sorted({t["note"] for t in ts if t["note"]}),
        })

    for h in holdings:
        h["weight"] = h["value"] / total_value if total_value else 0
        if h["kind"] == "stock" and h["weight"] > MAX_SINGLE_STOCK:
            warnings.append({"level": "warning", "text": f"{h['code']} is {h['weight']:.1%} of your "
                             f"portfolio, above the {MAX_SINGLE_STOCK:.0%} single-stock limit."})
    holdings.sort(key=lambda h: -h["value"])
    by_kind = defaultdict(float)
    for h in holdings:
        by_kind[h["kind"]] += h["value"]
    return {
        "value": total_value, "invested": total_cost, "gain": total_value - total_cost,
        "gain_pct": (total_value / total_cost - 1) if total_cost else None,
        "realised_gain": realised, "xirr": analytics.xirr(all_flows) if all_flows else None,
        "allocation": {k: v / total_value for k, v in by_kind.items()} if total_value else {},
        "holdings": holdings, "warnings": warnings, "transactions": txs[::-1][:200],
    }
