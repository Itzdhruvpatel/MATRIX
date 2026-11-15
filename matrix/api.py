"""Matrix web API. Run: python -m uvicorn matrix.api:app --port 8000"""
import json
import os
import secrets
import threading
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from matrix import analytics, auth, db, pipeline, portfolio, radar, score

ROOT = Path(__file__).resolve().parent.parent
COOKIE = "matrix_session"
MIN_TRADED_VALUE = 1e8  # Rs 10 crore: ignore thinly traded stocks in gainer/loser lists
STALE_DAYS = 4
LEVEL_ORDER = "CASE level WHEN 'danger' THEN 0 WHEN 'warning' THEN 1 WHEN 'watch' THEN 2 ELSE 3 END"
MAX_FAILS, LOCK_SECONDS = 5, 300


def load_secret() -> str:
    """MATRIX_SECRET from env or .env; created on first run so sessions survive restarts."""
    if os.environ.get("MATRIX_SECRET"):
        return os.environ["MATRIX_SECRET"]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("MATRIX_SECRET="):
                return line.split("=", 1)[1].strip()
    secret = secrets.token_hex(32)
    with env.open("a") as f:
        f.write(f"MATRIX_SECRET={secret}\n")
    return secret


class Login(BaseModel):
    username: str
    password: str


def create_app(conn, secret: str, scheduler: bool = False) -> FastAPI:
    app = FastAPI(title="Matrix", docs_url=None, redoc_url=None)
    app.state.conn = conn

    @app.middleware("http")
    async def fresh_pages(request: Request, call_next):
        # Browsers must re-check pages, styles and scripts so a new version shows at once.
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"
        return response
    lock = threading.Lock()
    fails: dict[str, list[float]] = defaultdict(list)

    def q(sql, args=()):
        with lock:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

    def user(request: Request) -> str:
        name = auth.read_token(request.cookies.get(COOKIE, ""), secret)
        if not name:
            raise HTTPException(401, "Not logged in")
        return name

    # ---------------------------------------------------------------- auth
    @app.post("/api/login")
    def login(body: Login, request: Request, response: Response):
        ip = request.client.host if request.client else "?"
        recent = [t for t in fails[ip] if time.time() - t < LOCK_SECONDS]
        fails[ip] = recent
        if len(recent) >= MAX_FAILS:
            raise HTTPException(429, "Too many attempts. Try again in 5 minutes.")
        rows = q("SELECT password_hash FROM users WHERE username=?", (body.username,))
        if not rows or not auth.verify_password(body.password, rows[0]["password_hash"]):
            fails[ip].append(time.time())
            raise HTTPException(401, "Wrong username or password")
        fails.pop(ip, None)
        response.set_cookie(COOKIE, auth.make_token(body.username, secret), httponly=True,
                            samesite="strict", max_age=auth.SESSION_SECONDS)
        return {"username": body.username}

    @app.post("/api/logout")
    def logout(response: Response):
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/me")
    def me(name: str = Depends(user)):
        return {"username": name}

    # ---------------------------------------------------------------- market
    @app.get("/api/market/summary")
    def market_summary(_: str = Depends(user)):
        latest = q("SELECT MAX(date) d FROM stock_prices")[0]["d"]
        if not latest:
            return {"date": None}
        base = ("SELECT symbol, name, close, prev_close, value, volume,"
                " ROUND((close / prev_close - 1) * 100, 2) AS change_pct"
                " FROM stock_prices WHERE date=? AND series='EQ' AND prev_close > 0")
        liquid = f"{base} AND value >= {MIN_TRADED_VALUE}"
        breadth = q("SELECT SUM(close > prev_close) adv, SUM(close < prev_close) dec,"
                    " SUM(close = prev_close) unch, SUM(value) turnover, COUNT(*) n"
                    " FROM stock_prices WHERE date=? AND series='EQ'", (latest,))[0]
        return {
            "date": latest,
            "stale": date.fromisoformat(latest) < pipeline.today_ist() - timedelta(days=STALE_DAYS),
            "breadth": breadth,
            "gainers": q(f"{liquid} ORDER BY change_pct DESC LIMIT 10", (latest,)),
            "losers": q(f"{liquid} ORDER BY change_pct ASC LIMIT 10", (latest,)),
            "most_active": q(f"{base} ORDER BY value DESC LIMIT 10", (latest,)),
            "heatmap": q(f"{liquid} ORDER BY value DESC LIMIT 120", (latest,)),
            # Share of stocks that rose on each of the last 20 trading days, oldest first.
            "history": q("SELECT date, SUM(close > prev_close) adv, SUM(close < prev_close) dec,"
                         " COUNT(*) total FROM stock_prices WHERE series='EQ' AND date IN"
                         " (SELECT DISTINCT date FROM stock_prices ORDER BY date DESC LIMIT 20)"
                         " GROUP BY date ORDER BY date"),
            "flags": q("SELECT key AS symbol, reason FROM data_issues WHERE date=?"
                       " AND severity='flagged' ORDER BY key LIMIT 50", (latest,)),
        }

    @app.get("/api/stocks/search")
    def stock_search(query: str, _: str = Depends(user)):
        like = f"%{query.upper()}%"
        return q("SELECT symbol, name, series FROM stock_prices WHERE date=(SELECT MAX(date)"
                 " FROM stock_prices) AND (symbol LIKE ? OR name LIKE ?)"
                 " ORDER BY symbol != ?, value DESC LIMIT 15", (like, like, query.upper()))

    def stock_payload(symbol: str) -> dict:
        hist = q("SELECT date, open, high, low, close, prev_close, volume, value FROM stock_prices"
                 " WHERE symbol=? ORDER BY date", (symbol,))
        if not hist:
            raise HTTPException(404, f"Stock {symbol} not found")
        info = q("SELECT symbol, name, series, isin, source, fetched_at FROM stock_prices"
                 " WHERE symbol=? ORDER BY date DESC LIMIT 1", (symbol,))[0]
        s = analytics.adjusted_series(hist)
        stats = analytics.summary(s)
        last = hist[-1]
        stats["change_1d"] = (last["close"] / last["prev_close"] - 1) if last["prev_close"] else None
        stats["year_high"] = max(v for d, v in s if d >= s[-1][0] - timedelta(days=365))
        stats["year_low"] = min(v for d, v in s if d >= s[-1][0] - timedelta(days=365))
        stats["traded_value"] = last["value"]
        sc = q("SELECT score, components, metrics, reasons, universe, date FROM stock_scores"
               " WHERE symbol=? ORDER BY date DESC LIMIT 1", (symbol,))
        if sc:
            sc = sc[0]
            for k in ("components", "metrics", "reasons"):
                sc[k] = json.loads(sc[k])
        return {"kind": "stock", "code": symbol, "info": info, "stats": stats,
                "score": sc or None, "history": hist}

    @app.get("/api/stocks/{symbol}")
    def stock_detail(symbol: str, name: str = Depends(user)):
        d = stock_payload(symbol.upper())
        d["alerts"] = q(f"SELECT date, rule, level, title, detail, link, source FROM alerts"
                        f" WHERE symbol=? ORDER BY {LEVEL_ORDER}, date DESC LIMIT 12", (symbol.upper(),))
        d["watched"] = bool(q("SELECT 1 FROM watchlist WHERE username=? AND kind='stock' AND code=?",
                              (name, symbol.upper())))
        d["flags"] = q("SELECT date, severity, reason FROM data_issues WHERE key=?"
                       " AND source='nse_bhavcopy' ORDER BY date DESC", (symbol.upper(),))
        return d

    @app.get("/api/scores")
    def scores(limit: int = 15, _: str = Depends(user)):
        latest = q("SELECT MAX(date) d FROM stock_scores")[0]["d"]
        if not latest:
            return {"date": None, "top": [], "bottom": []}
        base = ("SELECT s.symbol, s.score, s.reasons, p.name, p.close,"
                " ROUND((p.close / p.prev_close - 1) * 100, 2) change_pct FROM stock_scores s"
                " JOIN stock_prices p ON p.symbol=s.symbol AND p.date=s.date WHERE s.date=?")
        limit = max(1, min(limit, 50))

        def rows(order):
            out = q(f"{base} ORDER BY s.score {order}, s.symbol LIMIT {limit}", (latest,))
            for r in out:
                r["reasons"] = json.loads(r["reasons"])
            return out

        n = q("SELECT COUNT(*) n FROM stock_scores WHERE date=?", (latest,))[0]["n"]
        return {"date": latest, "universe": n, "top": rows("DESC"), "bottom": rows("ASC")}

    # ---------------------------------------------------------------- funds
    @app.get("/api/funds/search")
    def fund_search(query: str, direct_only: bool = True, _: str = Depends(user)):
        words = [w for w in query.split() if w][:6]
        if not words:
            return []
        where = " AND ".join("f.name LIKE ?" for _ in words)
        args = [f"%{w}%" for w in words]
        if direct_only:
            where += " AND (f.plan LIKE '%Direct%' OR f.name LIKE '%Direct%')"
        # Closed schemes stop reporting NAVs; hide anything silent for 30+ days.
        where += " AND n.date >= date((SELECT MAX(date) FROM fund_navs), '-30 day')"
        return q(f"SELECT f.scheme_code, f.name, f.amc, f.category, f.plan, f.option, n.nav,"
                 f" n.date FROM funds f JOIN fund_navs n ON n.scheme_code=f.scheme_code AND"
                 f" n.date=(SELECT MAX(date) FROM fund_navs WHERE scheme_code=f.scheme_code)"
                 f" WHERE {where} ORDER BY f.name LIMIT 30", args)

    def fund_payload(code: str) -> dict:
        info = q("SELECT * FROM funds WHERE scheme_code=?", (code,))
        if not info:
            raise HTTPException(404, f"Fund {code} not found")
        loaded = q("SELECT 1 FROM pipeline_runs WHERE source='mfapi' AND date=? AND status='ok'"
                   " AND started_at >= date('now', '-7 day')", (code,))
        if not loaded:  # fetch full history once a week per fund, on first view
            with lock:
                pipeline.load_fund_history(conn, code)
        navs = q("SELECT date, nav, source FROM fund_navs WHERE scheme_code=? ORDER BY date", (code,))
        s = [(date.fromisoformat(n["date"]), n["nav"]) for n in navs]
        stats = analytics.summary(s)
        stats["consistency_1y"] = analytics.rolling_consistency(s, 1)
        stats["consistency_3y"] = analytics.rolling_consistency(s, 3)
        return {"kind": "fund", "code": code, "info": info[0], "stats": stats,
                "navs": [{"date": n["date"], "nav": n["nav"]} for n in navs],
                "sources": sorted({n["source"] for n in navs})}

    @app.get("/api/funds/{code}")
    def fund_detail(code: str, _: str = Depends(user)):
        return fund_payload(code)

    # ---------------------------------------------------------------- compare
    @app.get("/api/compare")
    def compare(items: str, _: str = Depends(user)):
        """items: comma list like stock:TCS,fund:122639 (max 5)."""
        out = []
        for item in [i for i in items.split(",") if i][:5]:
            kind, _, code = item.partition(":")
            if kind == "stock":
                d = stock_payload(code.upper())
                adj = analytics.adjusted_series(d["history"])
                name, hist = d["info"]["name"], [{"date": dt.isoformat(), "value": v} for dt, v in adj]
            elif kind == "fund":
                d = fund_payload(code)
                name, hist = d["info"]["name"], [{"date": n["date"], "value": n["nav"]} for n in d["navs"]]
            else:
                raise HTTPException(400, f"Unknown item '{item}'. Use stock:SYMBOL or fund:CODE")
            out.append({"kind": kind, "code": d["code"], "name": name, "stats": d["stats"],
                        "score": d.get("score"), "history": hist[-800:]})
        return out

    # ---------------------------------------------------------------- portfolio
    class Tx(BaseModel):
        kind: str
        code: str
        side: str
        date: str
        quantity: float
        price: float
        note: str | None = None

    class CsvBody(BaseModel):
        csv: str

    @app.get("/api/portfolio")
    def get_portfolio(name: str = Depends(user)):
        with lock:
            return portfolio.summary(conn, name)

    @app.post("/api/portfolio/transactions")
    def add_tx(tx: Tx, name: str = Depends(user)):
        with lock:
            err = portfolio.add(conn, name, tx.model_dump())
        if err:
            raise HTTPException(400, err)
        return {"ok": True}

    @app.delete("/api/portfolio/transactions/{tx_id}")
    def delete_tx(tx_id: int, name: str = Depends(user)):
        with lock:
            n = conn.execute("DELETE FROM transactions WHERE id=? AND username=?",
                             (tx_id, name)).rowcount
            conn.commit()
        if not n:
            raise HTTPException(404, "Transaction not found")
        return {"ok": True}

    @app.post("/api/portfolio/import")
    def import_tx(body: CsvBody, name: str = Depends(user)):
        if len(body.csv) > 1_000_000:
            raise HTTPException(413, "File too large (1 MB max)")
        with lock:
            r = portfolio.import_csv(conn, name, body.csv)
        if r["errors"]:
            raise HTTPException(400, "; ".join(r["errors"]))
        return r

    # ---------------------------------------------------------------- alerts + watchlist
    class Watch(BaseModel):
        kind: str
        code: str

    @app.get("/api/alerts")
    def alerts(name: str = Depends(user)):
        with lock:
            held = {k[1] for k, v in portfolio.holdings_qty(conn, name).items()
                    if k[0] == "stock" and v > 1e-9}
        watch = q("SELECT w.kind, w.code, COALESCE((SELECT name FROM stock_prices WHERE symbol=w.code"
                  " ORDER BY date DESC LIMIT 1), (SELECT name FROM funds WHERE scheme_code=w.code),"
                  " w.code) AS name FROM watchlist w WHERE w.username=? ORDER BY w.added_at DESC", (name,))
        mine_syms = sorted(held | {w["code"] for w in watch if w["kind"] == "stock"})
        cols = ("a.symbol, a.date, a.rule, a.level, a.title, a.detail, a.link, a.source,"
                " (SELECT name FROM stock_prices WHERE symbol=a.symbol ORDER BY date DESC LIMIT 1) AS name")
        mine = []
        if mine_syms:
            marks = ",".join("?" * len(mine_syms))
            mine = q(f"SELECT {cols} FROM alerts a WHERE a.symbol IN ({marks})"
                     f" ORDER BY {LEVEL_ORDER}, a.date DESC", mine_syms)
            for m in mine:
                m["owned"] = m["symbol"] in held
        # Market-wide: the serious ones only, skipping the long surveillance list.
        market = q(f"SELECT {cols} FROM alerts a WHERE a.level IN ('danger', 'warning')"
                   f" AND a.rule NOT IN ('surveillance', 'fall_month')"
                   f" ORDER BY {LEVEL_ORDER}, a.date DESC LIMIT 40")
        counts = {r["level"]: r["n"] for r in q("SELECT level, COUNT(*) n FROM alerts GROUP BY level")}
        return {"mine": mine, "tracking": len(mine_syms), "market": market, "counts": counts,
                "watchlist": watch}

    @app.post("/api/watchlist")
    def watch_add(w: Watch, name: str = Depends(user)):
        code = w.code.strip().upper() if w.kind == "stock" else w.code.strip()
        with lock:
            if w.kind not in ("stock", "fund") or portfolio.latest_price(conn, w.kind, code) is None:
                raise HTTPException(400, f"Unknown {w.kind} '{w.code}'")
            conn.execute("INSERT OR IGNORE INTO watchlist (username, kind, code, added_at)"
                         " VALUES (?,?,?,datetime('now'))", (name, w.kind, code))
            conn.commit()
        return {"ok": True}

    @app.delete("/api/watchlist/{kind}/{code}")
    def watch_remove(kind: str, code: str, name: str = Depends(user)):
        with lock:
            conn.execute("DELETE FROM watchlist WHERE username=? AND kind=? AND code=?",
                         (name, kind, code.upper() if kind == "stock" else code))
            conn.commit()
        return {"ok": True}

    # ---------------------------------------------------------------- health
    @app.get("/api/health")
    def health(_: str = Depends(user)):
        today = pipeline.today_ist()
        out = {}
        for table, source in (("stock_prices", "nse_bhavcopy"), ("fund_navs", "amfi_navall")):
            latest = q(f"SELECT MAX(date) d, COUNT(DISTINCT date) days FROM {table}")[0]
            out[source] = {
                "latest_date": latest["d"], "days_stored": latest["days"],
                "stale": not latest["d"]
                or date.fromisoformat(latest["d"]) < today - timedelta(days=STALE_DAYS),
            }
        out["runs"] = q("SELECT source, date, status, rows, issues, message, finished_at"
                        " FROM pipeline_runs ORDER BY id DESC LIMIT 15")
        out["issues"] = q("SELECT severity, COUNT(*) n FROM data_issues GROUP BY severity")
        return out

    # ---------------------------------------------------------------- daily refresh
    if scheduler:
        def loop():
            # Separate connection: this thread writes while the API reads.
            c = db.connect(os.environ.get("MATRIX_DB"))
            while True:
                try:
                    now = pipeline.datetime.now(pipeline.IST)
                    today = now.date()
                    # NSE file appears around 18:00 IST, AMFI NAVs by about 23:00 IST.
                    if today.weekday() < 5 and now.hour >= 19 and not c.execute(
                            "SELECT 1 FROM pipeline_runs WHERE source='nse_bhavcopy' AND date=?"
                            " AND status IN ('ok','no_data')", (today.isoformat(),)).fetchone():
                        if pipeline.load_stocks(c, today)["status"] == "ok":
                            score.compute(c)
                    # Feeds only hold the newest filings, so read them every cycle.
                    if pipeline.load_feeds(c)["rows"]:
                        radar.compute(c)
                    if now.hour >= 23 and not c.execute(
                            "SELECT 1 FROM pipeline_runs WHERE source='amfi_navall' AND"
                            " status='ok' AND started_at LIKE ?", (f"{today}%",)).fetchone():
                        pipeline.load_funds(c)
                except Exception as e:  # keep the loop alive; the error is in pipeline_runs
                    print("scheduler error:", e)
                time.sleep(1800)

        threading.Thread(target=loop, daemon=True).start()

    app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
    return app


app = None
if os.environ.get("MATRIX_NO_APP") != "1":
    app = create_app(db.connect(), load_secret(), scheduler=os.environ.get("MATRIX_SCHEDULER", "1") == "1")
