# Matrix

Personal investment research website for Indian markets. It loads NSE end-of-day stock prices and AMFI mutual fund NAVs every day, checks the data for errors, and shows the day's market in plain language.

This is a research tool. It does not give investment advice, place trades, or guarantee returns. The full design is in `docs/Matrix-Design.pdf`.

## What works today

**Market (Today tab)**
- Plain-language summary of the day, rising vs falling stocks, and a heatmap of the 120 most traded stocks
- Gainers, losers, unusual moves over 20%, and a data health panel
- A red banner when the daily price or NAV update fails or runs late, with the reason
- Chart patterns from the last trading day: new 1-year high, crossing the 200-day average up or down, trading at 3 times a normal day, and opening 3% or more away from the last close. Facts about the price, not signals
- Pattern backtest: every past day of every liquid stock is checked with the same rules, and the next 20 trading days are compared with the Nifty and with a random stock on a random day, after 0.3% costs and 20% short-term tax
- Interest rates and the rupee: RBI repo rate, 10-year government bond yield, 3-month T-bill, big-bank FD rate, the dollar and India VIX, each with a line on why it matters
- Big investors today: FII and DII buying and selling in the cash market, kept day by day

**Matrix Score (Ratings tab)**
- 0 to 100 score for every liquid NSE stock (about 1,500), ranked on momentum, trend, calm, worst fall and ease of trading
- Each score lists its reasons. Stocks in the exchange's surveillance segment are capped at 30
- Price behaviour only for now. It describes the past year and does not predict returns

**Portfolio**
- Add buys and sells by hand or import a CSV (all-or-nothing, every line checked)
- Import everything at once from a CAS PDF: CAMS or KFintech for mutual funds bought through any app, NSDL or CDSL for demat stocks. You type the PDF password in the page; Matrix uses it for that one read and never saves it. Each holding shows the folio, fund house or demat broker it came from. Uploading a newer statement skips entries you already have
- A demat CAS lists holdings without purchase prices, so those count from the statement date at that day's price
- Value, gain, booked gains, and true yearly return (XIRR) per holding and overall
- Warns when one stock is over 10% of the portfolio
- Notes every Regular fund plan you hold; the fund page shows how much more its Direct plan grew a year

**Alerts (Danger Radar)**
- Follow any stock; alerts for stocks you own or follow appear in the Alerts tab
- Price rules: exchange surveillance, falls over 20% in a month, one-day moves over 20%, pump-and-dump patterns, near a one-year low
- Official NSE filings: auditor resignations, defaults, insolvency, fraud or regulator action, rating downgrades, top executive exits, promoter pledges, insider trades
- Insider trade details read from each filing's data file: who, role, shares, value and how. Market sales of Rs 1 crore or more by promoters or directors are a Warning; moves between promoter companies are shown once as Info
- Large bulk and block deals
- Chart patterns as Info alerts on the stocks you own or follow
- Your own stops and targets: a Warning when a stock closes below the stop you saved, Info when it closes above your target
- Every alert says what happened, why it matters, and links to the filing

**Market mood**
- Calm, Nervous, Stressed or Panic, from how much the Nifty swings, how far it is below its high, and how many stocks are rising

**Prediction Ledger (Ratings tab)**
- Re-scores past months using only what was known then, and checks how Strong and Weak stocks did over the next month against the Nifty
- Every month stays on the record, good or bad
- So far Strong stocks have not beaten simply owning the Nifty

**Forecast (stock detail, owner only)**
- Chance the stock beats the Nifty ETF (NIFTYBEES) over the next 20 trading days, 3 months and 12 months, from a logistic regression on the five score parts (one model per length)
- Kill switch: a length that did worse than the simple guess over the last 3 months is hidden until it does better. Forecasts are still made and graded meanwhile
- Trained walk-forward: a forecast for a day uses only past days whose 20-day result was known by then
- Likely range: how far the stock moved over any 20 trading days in the past year, 8 times out of 10
- Matrix saves each forecast once and never changes it. The Ratings tab grades them against what happened, next to the simple guess the model has to beat. As of 16 November 2026, on 6,079 graded forecasts (all re-created from past data) the model was right 49 times in 100; always guessing "will not beat the Nifty" was right 59 times in 100

**Trade planner and Time Machine (stock detail)**
- Type the price, a stop and a target (or take the defaults: stop two typical daily moves below, target twice as far above) and the most you will lose. Matrix works out how many shares fit, and warns when that is over 10% of your money
- Time Machine (owner only): 10,000 made-up runs of the next 20 trading days from the stock's own daily moves over the past year, with the trend taken out, show how often the target or the stop came first. The same plan is also replayed on every past day
- Matrix only has closing prices, so a run counts the close that went through the level, which is often worse than the stop itself. Costs and tax are left out
- Save the stop and target to get alerts and to unlock practice buys

**Shortlist (owner only)**
- Pick plain rules (minimum score, no Danger or Warning alerts, daily trading, calm price, uptrend, small worst fall) and see which stocks pass, with the reasons
- Replays the same rules on past months and compares the next month with owning the Nifty
- Ideas to research, not advice

**What if, tax and journal (Portfolio tab)**
- What if the market falls or rises: estimated effect on each holding, based on how it moved with the Nifty over the past year
- Tax if you sold today: short-term and long-term gains matched first-in, first-out, with the yearly tax-free limit (rules from the July 2024 Budget)
- Investment journal: why you bought, when you would sell, and a review date
- Practice money: a separate pretend portfolio for trying ideas
- Practice rules: set starting practice money, the most in one stock and the most lost per trade. Matrix then refuses any practice buy that costs more than the cash left, breaks the one-stock limit, has no stop saved, or would lose more than the limit at the stop
- Cooling-off: a practice buy of a stock that moved 10% or more in 5 days, or has a Danger or Warning alert, waits until its plan is a day old

**Planning tab**
- Goals in today's rupees with a target date: 2,000 simulated paths show the chance of getting there, the range of likely values, and the monthly amount that makes it likely (3 times in 4). Assumptions are shown on the page
- Bond calculator: yield to maturity, current yield, total received, and the price change if interest rates move 1% or 2%

**Compare**
- Up to 4 stocks or funds on one chart, all starting at 100, with returns and risk side by side

**Data**
- Daily data pipeline: NSE bhavcopy (every listed stock) and AMFI NAVs (every mutual fund scheme)
- Stock prices adjusted for splits and bonuses using the exchange's own previous-close figures
- Full fund NAV history from mfapi.in on first view, cross-checked against official AMFI NAVs
- Quality checks: broken rows are blocked, moves over 20% in a day are flagged
- Reads NSE's older price file too (before July 2024), so `--since` can load several years of history
- Nightly encrypted backup of every table, restored into a temporary file and checked each night; a failure shows in the Market today banner
- Every stored number keeps its source and fetch time
- Login with hashed passwords, signed session cookies, and lockout after 5 wrong attempts
- Optional two-step login (Account page): scan a QR code with any authenticator app, then each login needs the 6-digit code. Codes follow RFC 6238, work once, and allow 30 seconds of clock drift
- Dashboard: market breadth, gainers, losers, most traded, unusual moves, data health
- Search across stocks and mutual funds, with a chart and stats for each
- Automatic refresh: stocks after 19:00 IST on weekdays, NAVs after 23:00 IST, while the server runs

## Setup

Needs Python 3.12 or newer.

```bash
pip install -r requirements.txt
python -m matrix.pipeline --days 250
python -m matrix.forecast
python -m matrix.auth YOUR_NAME
python -m uvicorn matrix.api:app --port 8000
```

Then open http://localhost:8000 and log in.

`--days 250` loads about one year of stock prices and computes Matrix Scores (takes a few minutes). For more history, run `python -m matrix.pipeline --since 2021-11-01` once (about half an hour; safe to stop and rerun), then `python -m matrix.forecast` again.

Backups: `python -m matrix.backup` makes one now, `--test` checks the newest restores, `--restore FILE OUT.db` rebuilds a database. The first run creates `MATRIX_BACKUP_KEY` in `.env`. Copy that key somewhere off this computer: without it a backup cannot be opened. `python -m matrix.forecast` scores past months and builds the first forecasts from them; after that the daily update adds a forecast each day. Fund history downloads the first time you open each fund.

## Tests

```bash
python -m pytest
```

## Layout

```
matrix/sources/   NSE prices, feeds, insider files, FII/DII, RBI rates, AMFI and fund history
matrix/validate.py  data quality rules
matrix/analytics.py returns, risk, XIRR, split adjustment
matrix/score.py   Matrix Score
matrix/portfolio.py holdings and returns
matrix/cas.py     CAS statement import
matrix/radar.py   Danger Radar rules and alerts
matrix/insights.py market mood, what-if scenarios, tax view
matrix/ledger.py  Prediction Ledger (score and forecast track record)
matrix/forecast.py forecast models (20, 63 and 252 trading days) and kill switch
matrix/backtest.py chart pattern backtest
matrix/goals.py   goal tracker
matrix/bonds.py   bond calculator
matrix/backup.py  encrypted backups and restore test
matrix/screener.py Shortlist rules
matrix/planner.py trade planner, Time Machine, stop and target alerts
matrix/pipeline.py  fetch, validate, store
matrix/db.py      schema (SQLite or PostgreSQL)
matrix/auth.py    passwords, sessions, two-step codes
matrix/api.py     web API and daily refresh
web/              dashboard (HTML, CSS, JS)
docs/             design document
```

## Notes

- Storage is SQLite on your own computer, or PostgreSQL when `DATABASE_URL` is set (see `docs/DEPLOY.md`).
- The daily GitHub Action stops with "Add the DATABASE_URL secret first" until you add that secret.
- Data comes from public NSE and AMFI files for personal use. Check their terms before any wider use.
