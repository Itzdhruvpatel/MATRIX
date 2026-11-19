"""Matrix web API. Run: python -m uvicorn matrix.api:app --port 8000"""
import base64
import binascii
import json
import os
import re
import secrets
import threading
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from matrix import (analytics, auth, backup, cas, db, forecast, insights, ledger, pipeline,
                    planner, portfolio, radar, score, screener)

ROOT = Path(__file__).resolve().parent.parent
COOKIE = "matrix_session"
MIN_TRADED_VALUE = 1e8  # Rs 10 crore: ignore thinly traded stocks in gainer/loser lists
STALE_DAYS = 4
LEVEL_ORDER = "CASE level WHEN 'danger' THEN 0 WHEN 'warning' THEN 1 WHEN 'watch' THEN 2 ELSE 3 END"
MAX_FAILS, LOCK_SECONDS = 5, 300
MAX_SIGNUPS_PER_HOUR = 3
USERNAME = re.compile(r"^[a-z0-9_]{3,30}$")


def settings() -> dict:
    """Deployment settings from environment variables.

    MATRIX_OWNER: the one username that sees stock ratings (empty = everyone, for personal use)
    MATRIX_SIGNUP=1: allow new people to create accounts
    MATRIX_SECURE_COOKIE=1: send the login cookie over HTTPS only
    MATRIX_TRUST_PROXY=1: read the visitor's address from X-Forwarded-For (behind Vercel/Render)
    """
    return {
        "owner": os.environ.get("MATRIX_OWNER", "").strip(),
        "signup": os.environ.get("MATRIX_SIGNUP") == "1",
        "secure": os.environ.get("MATRIX_SECURE_COOKIE") == "1",
        "proxy": os.environ.get("MATRIX_TRUST_PROXY") == "1",
    }


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
    code: str | None = None  # 6-digit code, for users with two-step login on


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

    def sees_ratings(name: str) -> bool:
        owner = settings()["owner"]
        return not owner or name == owner

    def owner_only(name: str = Depends(user)) -> str:
        if not sees_ratings(name):
            raise HTTPException(403, "Ratings are private on this site")
        return name

    def client_ip(request: Request) -> str:
        if settings()["proxy"]:
            fwd = request.headers.get("x-forwarded-for", "")
            if fwd:
                return fwd.split(",")[0].strip()
        return request.client.host if request.client else "?"

    def start_session(response: Response, name: str) -> None:
        response.set_cookie(COOKIE, auth.make_token(name, secret), httponly=True, samesite="strict",
                            max_age=auth.SESSION_SECONDS, secure=settings()["secure"])

    # ---------------------------------------------------------------- auth
    @app.post("/api/login")
    def login(body: Login, request: Request, response: Response):
        ip = client_ip(request)
        recent = [t for t in fails[ip] if time.time() - t < LOCK_SECONDS]
        fails[ip] = recent
        if len(recent) >= MAX_FAILS:
            raise HTTPException(429, "Too many attempts. Try again in 5 minutes.")
        rows = q("SELECT password_hash, totp_secret FROM users WHERE username=?", (body.username,))
        if not rows or not auth.verify_password(body.password, rows[0]["password_hash"]):
            fails[ip].append(time.time())
            raise HTTPException(401, "Wrong username or password")
        if rows[0]["totp_secret"]:
            if not body.code:
                return {"need_code": True}  # password right; now ask for the app's code
            with lock:
                last = conn.execute("SELECT totp_last FROM users WHERE username=?",
                                    (body.username,)).fetchone()[0]
                step = auth.check_totp(rows[0]["totp_secret"], body.code, after=last)
                if step is not None:
                    conn.execute("UPDATE users SET totp_last=? WHERE username=?", (step, body.username))
                    conn.commit()
            if step is None:
                fails[ip].append(time.time())
                raise HTTPException(401, "Wrong or expired code. Wait for the next code and try again.")
        fails.pop(ip, None)
        start_session(response, body.username)
        return {"username": body.username}

    signups: dict[str, list[float]] = defaultdict(list)

    @app.get("/api/config")
    def config():
        return {"signup": settings()["signup"]}

    @app.post("/api/signup")
    def signup(body: Login, request: Request, response: Response):
        if not settings()["signup"]:
            raise HTTPException(403, "New accounts are closed")
        ip = client_ip(request)
        signups[ip] = [t for t in signups[ip] if time.time() - t < 3600]
        if len(signups[ip]) >= MAX_SIGNUPS_PER_HOUR:
            raise HTTPException(429, "Too many new accounts from here. Try again later.")
        name = body.username.strip().lower()
        if not USERNAME.match(name):
            raise HTTPException(400, "Username: 3 to 30 characters, only a-z, 0-9 and _")
        if len(body.password) < 10:
            raise HTTPException(400, "Password must be at least 10 characters")
        with lock:
            if conn.execute("SELECT 1 FROM users WHERE username=?", (name,)).fetchone():
                raise HTTPException(409, "That username is taken")
            auth.set_user(conn, name, body.password)
        signups[ip].append(time.time())
        start_session(response, name)
        return {"username": name}

    @app.post("/api/logout")
    def logout(response: Response):
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/me")
    def me(name: str = Depends(user)):
        on = q("SELECT totp_secret FROM users WHERE username=?", (name,))
        return {"username": name, "ratings": sees_ratings(name), "totp": bool(on and on[0]["totp_secret"])}

    # ---------------------------------------------------------------- two-step login
    pending_totp: dict[str, str] = {}  # secret shown but not yet confirmed with a code

    class Code(BaseModel):
        code: str

    class TurnOff(BaseModel):
        password: str
        code: str

    @app.post("/api/totp/setup")
    def totp_setup(name: str = Depends(user)):
        import segno
        secret = pending_totp[name] = auth.new_totp_secret()
        uri = auth.totp_uri(name, secret)
        return {"secret": secret, "uri": uri, "qr": segno.make(uri, error="m").svg_inline(scale=5, light="#fff")}

    @app.post("/api/totp/enable")
    def totp_enable(body: Code, name: str = Depends(user)):
        secret = pending_totp.get(name)
        if not secret:
            raise HTTPException(400, "Start again: press Turn on")
        step = auth.check_totp(secret, body.code)
        if step is None:
            raise HTTPException(400, "That code did not match. Check that your phone's clock is right"
                                     " and type the newest code.")
        with lock:
            conn.execute("UPDATE users SET totp_secret=?, totp_last=? WHERE username=?", (secret, step, name))
            conn.commit()
        pending_totp.pop(name, None)
        return {"ok": True}

    @app.post("/api/totp/disable")
    def totp_disable(body: TurnOff, name: str = Depends(user)):
        row = q("SELECT password_hash, totp_secret FROM users WHERE username=?", (name,))
        if not row or not auth.verify_password(body.password, row[0]["password_hash"]):
            raise HTTPException(400, "Wrong password")
        with lock:
            last = conn.execute("SELECT totp_last FROM users WHERE username=?", (name,)).fetchone()[0]
            if row[0]["totp_secret"] and auth.check_totp(row[0]["totp_secret"], body.code, after=last) is None:
                raise HTTPException(400, "Wrong or expired code")
            conn.execute("UPDATE users SET totp_secret=NULL, totp_last=NULL WHERE username=?", (name,))
            conn.commit()
        return {"ok": True}

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
        breadth = q("SELECT SUM(CASE WHEN close > prev_close THEN 1 ELSE 0 END) AS adv,"
                    " SUM(CASE WHEN close < prev_close THEN 1 ELSE 0 END) AS dec,"
                    " SUM(CASE WHEN close = prev_close THEN 1 ELSE 0 END) AS unch,"
                    " SUM(value) AS turnover, COUNT(*) AS n"
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
            "history": q("SELECT date, SUM(CASE WHEN close > prev_close THEN 1 ELSE 0 END) AS adv,"
                         " SUM(CASE WHEN close < prev_close THEN 1 ELSE 0 END) AS dec,"
                         " COUNT(*) AS total FROM stock_prices WHERE series='EQ' AND date IN"
                         " (SELECT DISTINCT date FROM stock_prices ORDER BY date DESC LIMIT 20)"
                         " GROUP BY date ORDER BY date"),
            "flags": q("SELECT key AS symbol, reason FROM data_issues WHERE date=?"
                       " AND severity='flagged' ORDER BY key LIMIT 50", (latest,)),
        }

    @app.get("/api/scanner")
    def scanner(min_traded_cr: float = 10, _: str = Depends(user)):
        """Today's chart patterns, grouped, busiest stocks first (the radar finds them each day)."""
        marks = ",".join("?" * len(radar.PATTERNS))
        rows = q(f"SELECT a.rule, a.symbol, a.title, p.name, p.close, p.value,"
                 f" ROUND((p.close / p.prev_close - 1) * 100, 2) AS change_pct FROM alerts a"
                 f" JOIN stock_prices p ON p.symbol=a.symbol AND p.date=a.date"
                 f" WHERE a.rule IN ({marks}) AND p.value >= ? ORDER BY p.value DESC",
                 (*radar.PATTERNS, min_traded_cr * 1e7))
        groups = {rule: [r for r in rows if r["rule"] == rule] for rule in radar.PATTERNS}
        return {"date": q("SELECT MAX(date) d FROM stock_prices")[0]["d"],
                "groups": {k: v[:12] for k, v in groups.items()},
                "counts": {k: len(v) for k, v in groups.items()}}

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
        if not sees_ratings(name):
            d["score"] = None
        d["alerts"] = q(f"SELECT date, rule, level, title, detail, link, source FROM alerts"
                        f" WHERE symbol=? ORDER BY {LEVEL_ORDER}, date DESC LIMIT 12", (symbol.upper(),))
        d["watched"] = bool(q("SELECT 1 FROM watchlist WHERE username=? AND kind='stock' AND code=?",
                              (name, symbol.upper())))
        d["flags"] = q("SELECT date, severity, reason FROM data_issues WHERE key=?"
                       " AND source='nse_bhavcopy' ORDER BY date DESC", (symbol.upper(),))
        return d

    @app.get("/api/scores")
    def scores(limit: int = 15, _: str = Depends(owner_only)):
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
        where = " AND ".join("LOWER(f.name) LIKE ?" for _ in words)
        args = [f"%{w.lower()}%" for w in words]
        if direct_only:
            where += " AND (f.plan LIKE '%Direct%' OR f.name LIKE '%Direct%')"
        # Closed schemes stop reporting NAVs; hide anything silent for 30+ days.
        newest = q("SELECT MAX(date) AS d FROM fund_navs")[0]["d"]
        if newest:
            where += f" AND n.date >= '{(date.fromisoformat(newest) - timedelta(days=30)).isoformat()}'"
        return q(f"SELECT f.scheme_code, f.name, f.amc, f.category, f.plan, f.option, n.nav,"
                 f" n.date FROM funds f JOIN fund_navs n ON n.scheme_code=f.scheme_code AND"
                 f" n.date=(SELECT MAX(date) FROM fund_navs WHERE scheme_code=f.scheme_code)"
                 f" WHERE {where} ORDER BY f.name LIMIT 30", args)

    def fund_payload(code: str) -> dict:
        info = q("SELECT * FROM funds WHERE scheme_code=?", (code,))
        if not info:
            raise HTTPException(404, f"Fund {code} not found")
        loaded = q("SELECT 1 FROM pipeline_runs WHERE source='mfapi' AND date=? AND status='ok'"
                   " AND started_at >= ?", (code, (pipeline.today_ist() - timedelta(days=7)).isoformat()))
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
    def compare(items: str, viewer: str = Depends(user)):
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
                        "score": d.get("score") if sees_ratings(viewer) else None, "history": hist[-800:]})
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
        book: str = "real"

    class CsvBody(BaseModel):
        csv: str
        book: str = "real"

    def check_book(book: str) -> str:
        if book not in portfolio.BOOKS:
            raise HTTPException(400, "book must be 'real' or 'paper'")
        return book

    @app.get("/api/portfolio")
    def get_portfolio(book: str = "real", name: str = Depends(user)):
        with lock:
            out = portfolio.summary(conn, name, check_book(book))
            if book == "paper":
                out["limits"] = lim = portfolio.get_limits(conn, name)
                out["cash"] = portfolio.practice_cash(conn, name, lim["capital"]) if lim else None
        return out

    class Limits(BaseModel):
        capital: float
        max_stock_pct: float = portfolio.MAX_SINGLE_STOCK
        max_loss_pct: float = 0.01

    @app.put("/api/practice-limits")
    def set_limits(body: Limits, name: str = Depends(user)):
        if body.capital <= 0 or not 0 < body.max_stock_pct <= 1 or not 0 < body.max_loss_pct <= 0.2:
            raise HTTPException(400, "Money must be above zero, the limit per stock 1 to 100%,"
                                     " and the loss per trade 0.1 to 20%")
        with lock:
            conn.execute("INSERT INTO practice_limits (username, capital, max_stock_pct, max_loss_pct)"
                         " VALUES (?,?,?,?) ON CONFLICT (username) DO UPDATE SET capital=excluded.capital,"
                         " max_stock_pct=excluded.max_stock_pct, max_loss_pct=excluded.max_loss_pct",
                         (name, body.capital, body.max_stock_pct, body.max_loss_pct))
            conn.commit()
        return {"ok": True}

    @app.delete("/api/practice-limits")
    def remove_limits(name: str = Depends(user)):
        with lock:
            conn.execute("DELETE FROM practice_limits WHERE username=?", (name,))
            conn.commit()
        return {"ok": True}

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
            r = portfolio.import_csv(conn, name, body.csv, check_book(body.book))
        if r["errors"]:
            raise HTTPException(400, "; ".join(r["errors"]))
        return r

    class CasBody(BaseModel):
        pdf: str  # base64
        password: str

    @app.post("/api/portfolio/import-cas")
    def import_cas(body: CasBody, name: str = Depends(user)):
        """The password opens the PDF for this one parse; it is never stored or logged."""
        if len(body.pdf) > 14_000_000:
            raise HTTPException(413, "File too large (10 MB max)")
        try:
            pdf = base64.b64decode(body.pdf, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(400, "The file did not arrive correctly. Try again.")
        try:
            data = cas.read_pdf(pdf, body.password)
        except cas.CasError as e:
            raise HTTPException(400, str(e))
        with lock:
            r = cas.import_cas(conn, name, data)
        if r["errors"]:
            raise HTTPException(400, "; ".join(r["errors"]))
        return r

    # ---------------------------------------------------------------- insights
    @app.get("/api/insights/mood")
    def mood(_: str = Depends(user)):
        with lock:
            return insights.market_mood(conn)

    @app.get("/api/insights/scenario")
    def what_if(move: float, book: str = "real", name: str = Depends(user)):
        if not -0.9 <= move <= 1.0:
            raise HTTPException(400, "move must be between -0.9 and 1.0")
        with lock:
            return insights.scenario(conn, name, move, check_book(book))

    @app.get("/api/insights/tax")
    def tax(name: str = Depends(user)):
        with lock:
            return insights.tax_view(conn, name)

    graded: dict = {}

    def forecast_record() -> dict:
        """Grading is slow-ish, so redo it only when forecasts or prices change."""
        with lock:
            key = tuple(conn.execute("SELECT (SELECT MAX(date) FROM forecasts),"
                                     " (SELECT MAX(date) FROM stock_prices)").fetchone())
            if graded.get("key") != key:
                recent = forecast.recent_record(conn)
                graded.update(key=key, record={**ledger.forecast_record(conn), "recent": recent,
                                               "paused": forecast.paused(recent)})
            return graded["record"]

    @app.get("/api/ledger")
    def track_record(_: str = Depends(owner_only)):
        with lock:
            out = ledger.track_record(conn)
        out["forecasts"] = forecast_record()
        return out

    @app.get("/api/shortlist")
    def shortlist(rules: screener.Rules = Depends(), _: str = Depends(owner_only)):
        with lock:
            return {**screener.shortlist(conn, rules), "history": screener.history(conn, rules)}

    @app.get("/api/forecast/{symbol}")
    def stock_forecast(symbol: str, _: str = Depends(owner_only)):
        record = forecast_record()
        if record["paused"]:
            return {"forecast": None, "paused": True, "record": record}
        with lock:
            fc = forecast.latest(conn, symbol.upper())
        return {"forecast": fc, "paused": False, "record": record}

    # ---------------------------------------------------------------- trade planner
    class Levels(BaseModel):
        stop: float
        target: float | None = None

    @app.get("/api/plan/{symbol}")
    def trade_plan(symbol: str, entry: float | None = None, stop: float | None = None,
                   target: float | None = None, risk: float | None = None,
                   capital: float | None = None, name: str = Depends(user)):
        """Position size for everyone; the Time Machine odds only for whoever sees ratings."""
        symbol = symbol.upper()
        saved = q("SELECT stop, target FROM levels WHERE username=? AND symbol=?", (name, symbol))
        if not (stop or target) and saved:
            stop, target = saved[0]["stop"], saved[0]["target"]
        with lock:
            lim = portfolio.get_limits(conn, name)
            if lim and not (risk or capital):  # size to the practice rules by default
                capital, risk = lim["capital"], lim["capital"] * lim["max_loss_pct"]
            try:
                out = planner.plan(conn, symbol, entry, stop, target, risk, capital, odds=sees_ratings(name))
            except LookupError as e:
                raise HTTPException(404, str(e))
            except ValueError as e:
                raise HTTPException(400, str(e))
        out["saved"] = saved[0] if saved else None
        return out

    @app.put("/api/levels/{symbol}")
    def set_levels(symbol: str, body: Levels, name: str = Depends(user)):
        symbol = symbol.upper()
        if body.stop <= 0 or (body.target is not None and body.target <= body.stop):
            raise HTTPException(400, "The stop must be above zero, and the target above the stop")
        with lock:
            if portfolio.latest_price(conn, "stock", symbol) is None:
                raise HTTPException(400, f"Unknown stock '{symbol}'")
            conn.execute("INSERT INTO levels (username, symbol, stop, target, set_at)"
                         " VALUES (?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT (username, symbol) DO UPDATE"
                         " SET stop=excluded.stop, target=excluded.target, set_at=excluded.set_at",
                         (name, symbol, body.stop, body.target))
            conn.commit()
        return {"ok": True}

    @app.delete("/api/levels/{symbol}")
    def remove_levels(symbol: str, name: str = Depends(user)):
        with lock:
            conn.execute("DELETE FROM levels WHERE username=? AND symbol=?", (name, symbol.upper()))
            conn.commit()
        return {"ok": True}

    # ---------------------------------------------------------------- journal
    class Entry(BaseModel):
        kind: str = "stock"
        code: str
        note: str
        sell_if: str | None = None
        review_on: str

    @app.get("/api/journal")
    def journal(name: str = Depends(user)):
        rows = q("SELECT id, kind, code, note, sell_if, review_on, reviewed, created_at FROM journal"
                 " WHERE username=? ORDER BY reviewed, review_on", (name,))
        today = pipeline.today_ist().isoformat()
        for r in rows:
            r["due"] = not r["reviewed"] and r["review_on"] <= today
        return rows

    @app.post("/api/journal")
    def journal_add(e: Entry, name: str = Depends(user)):
        code = e.code.strip().upper() if e.kind == "stock" else e.code.strip()
        note = e.note.strip()
        if not note or len(note) > 2000 or len(e.sell_if or "") > 1000:
            raise HTTPException(400, "Write why you bought (up to 2,000 characters)")
        try:
            date.fromisoformat(e.review_on)
        except ValueError:
            raise HTTPException(400, "Review date must look like 2026-12-31")
        with lock:
            if e.kind not in ("stock", "fund") or portfolio.latest_price(conn, e.kind, code) is None:
                raise HTTPException(400, f"Unknown {e.kind} '{e.code}'")
            conn.execute("INSERT INTO journal (username, kind, code, note, sell_if, review_on, created_at)"
                         " VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                         (name, e.kind, code, note, (e.sell_if or "").strip() or None, e.review_on))
            conn.commit()
        return {"ok": True}

    @app.post("/api/journal/{entry_id}/reviewed")
    def journal_reviewed(entry_id: int, name: str = Depends(user)):
        with lock:
            n = conn.execute("UPDATE journal SET reviewed=1 WHERE id=? AND username=?", (entry_id, name)).rowcount
            conn.commit()
        if not n:
            raise HTTPException(404, "Entry not found")
        return {"ok": True}

    @app.delete("/api/journal/{entry_id}")
    def journal_delete(entry_id: int, name: str = Depends(user)):
        with lock:
            n = conn.execute("DELETE FROM journal WHERE id=? AND username=?", (entry_id, name)).rowcount
            conn.commit()
        if not n:
            raise HTTPException(404, "Entry not found")
        return {"ok": True}

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
        with lock:
            mine = planner.level_alerts(conn, name) + mine
        for m in mine:
            m["owned"] = m["symbol"] in held
        # Market-wide: the serious ones only, skipping the long surveillance list.
        market = q(f"SELECT {cols} FROM alerts a WHERE a.level IN ('danger', 'warning')"
                   f" AND a.rule NOT IN ('surveillance', 'fall_month')"
                   f" ORDER BY {LEVEL_ORDER}, a.date DESC LIMIT 40")
        counts = {r["level"]: r["n"] for r in q("SELECT level, COUNT(*) n FROM alerts GROUP BY level")}
        levels = q("SELECT symbol, stop, target FROM levels WHERE username=? ORDER BY symbol", (name,))
        tracking = len(set(mine_syms) | {lv["symbol"] for lv in levels})
        return {"mine": mine, "tracking": tracking, "market": market, "counts": counts,
                "watchlist": watch, "levels": levels}

    @app.post("/api/watchlist")
    def watch_add(w: Watch, name: str = Depends(user)):
        code = w.code.strip().upper() if w.kind == "stock" else w.code.strip()
        with lock:
            if w.kind not in ("stock", "fund") or portfolio.latest_price(conn, w.kind, code) is None:
                raise HTTPException(400, f"Unknown {w.kind} '{w.code}'")
            conn.execute("INSERT INTO watchlist (username, kind, code, added_at)"
                         " VALUES (?,?,?,CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING", (name, w.kind, code))
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
        with lock:
            out["problems"] = pipeline.data_problems(conn)
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
                            forecast.compute(c)
                            radar.compute(c)  # price alerts and chart patterns for the new day
                    # Feeds only hold the newest filings, so read them every cycle.
                    if pipeline.load_feeds(c)["rows"]:
                        radar.compute(c)
                    if now.hour >= 23 and not c.execute(
                            "SELECT 1 FROM pipeline_runs WHERE source='amfi_navall' AND"
                            " status='ok' AND started_at LIKE ?", (f"{today}%",)).fetchone():
                        pipeline.load_funds(c)
                    if now.hour >= 23 and not c.execute(
                            "SELECT 1 FROM pipeline_runs WHERE source='backup' AND date=?",
                            (today.isoformat(),)).fetchone():
                        backup.nightly(c)
                except Exception as e:  # keep the loop alive; the error is in pipeline_runs
                    print("scheduler error:", e)
                time.sleep(1800)

        threading.Thread(target=loop, daemon=True).start()

    app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
    return app


app = None
if os.environ.get("MATRIX_NO_APP") != "1":
    app = create_app(db.connect(), load_secret(), scheduler=os.environ.get("MATRIX_SCHEDULER", "1") == "1")
