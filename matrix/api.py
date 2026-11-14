"""Matrix web API. Run: python -m uvicorn matrix.api:app --port 8000"""
import math
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

from matrix import auth, db, pipeline

ROOT = Path(__file__).resolve().parent.parent
COOKIE = "matrix_session"
MIN_TRADED_VALUE = 1e8  # Rs 10 crore: ignore thinly traded stocks in gainer/loser lists
STALE_DAYS = 4
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


def pct(a, b):
    return round((a / b - 1) * 100, 2) if a and b else None


class Login(BaseModel):
    username: str
    password: str


def create_app(conn, secret: str, scheduler: bool = False) -> FastAPI:
    app = FastAPI(title="Matrix", docs_url=None, redoc_url=None)
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
            "flags": q("SELECT key AS symbol, reason FROM data_issues WHERE date=?"
                       " AND severity='flagged' ORDER BY key LIMIT 50", (latest,)),
        }

    @app.get("/api/stocks/search")
    def stock_search(query: str, _: str = Depends(user)):
        like = f"%{query.upper()}%"
        return q("SELECT symbol, name, series FROM stock_prices WHERE date=(SELECT MAX(date)"
                 " FROM stock_prices) AND (symbol LIKE ? OR name LIKE ?)"
                 " ORDER BY symbol != ?, value DESC LIMIT 15", (like, like, query.upper()))

    @app.get("/api/stocks/{symbol}")
    def stock_detail(symbol: str, _: str = Depends(user)):
        hist = q("SELECT date, open, high, low, close, volume, value FROM stock_prices"
                 " WHERE symbol=? ORDER BY date", (symbol.upper(),))
        if not hist:
            raise HTTPException(404, "Stock not found")
        info = q("SELECT symbol, name, series, isin, source, fetched_at FROM stock_prices"
                 " WHERE symbol=? ORDER BY date DESC LIMIT 1", (symbol.upper(),))[0]
        closes = [h["close"] for h in hist]
        rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
        vol = None
        if len(rets) >= 5:
            m = sum(rets) / len(rets)
            vol = round(math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1))
                        * math.sqrt(252) * 100, 1)
        peak = max(closes)
        stats = {
            "last": closes[-1], "as_of": hist[-1]["date"],
            "change_1d": pct(closes[-1], closes[-2]) if len(closes) > 1 else None,
            "change_1w": pct(closes[-1], closes[-6]) if len(closes) > 5 else None,
            "change_period": pct(closes[-1], closes[0]),
            "period_high": max(h["high"] for h in hist), "period_low": min(h["low"] for h in hist),
            "from_peak": pct(closes[-1], peak),
            "volatility_annual": vol, "days": len(hist),
        }
        flags = q("SELECT date, severity, reason FROM data_issues WHERE key=? ORDER BY date DESC",
                  (symbol.upper(),))
        return {"info": info, "stats": stats, "history": hist, "flags": flags}

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

    @app.get("/api/funds/{code}")
    def fund_detail(code: str, _: str = Depends(user)):
        info = q("SELECT * FROM funds WHERE scheme_code=?", (code,))
        if not info:
            raise HTTPException(404, "Fund not found")
        navs = q("SELECT date, nav FROM fund_navs WHERE scheme_code=? ORDER BY date", (code,))
        return {"info": info[0], "navs": navs}

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
                        pipeline.load_stocks(c, today)
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
