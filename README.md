# Matrix

Personal investment research website for Indian markets. It loads NSE end-of-day stock prices and AMFI mutual fund NAVs every day, checks the data for errors, and shows the day's market in plain language.

This is a research tool. It does not give investment advice, place trades, or guarantee returns. The full design is in `docs/Matrix-Design.pdf`.

## What works today

**Market (Today tab)**
- Plain-language summary of the day, rising vs falling stocks, and a heatmap of the 120 most traded stocks
- Gainers, losers, unusual moves over 20%, and a data health panel

**Matrix Score (Ratings tab)**
- 0 to 100 score for every liquid NSE stock (about 1,500), ranked on momentum, trend, calm, worst fall and ease of trading
- Each score lists its reasons. Stocks in the exchange's surveillance segment are capped at 30
- Price behaviour only for now. It describes the past year and does not predict returns

**Portfolio**
- Add buys and sells by hand or import a CSV (all-or-nothing, every line checked)
- Value, gain, booked gains, and true yearly return (XIRR) per holding and overall
- Warns when one stock is over 10% of the portfolio

**Alerts (Danger Radar)**
- Follow any stock; alerts for stocks you own or follow appear in the Alerts tab
- Price rules: exchange surveillance, falls over 20% in a month, one-day moves over 20%, pump-and-dump patterns, near a one-year low
- Official NSE filings: auditor resignations, defaults, insolvency, fraud or regulator action, rating downgrades, top executive exits, promoter pledges, insider trades
- Large bulk and block deals
- Every alert says what happened, why it matters, and links to the filing

**Market mood**
- Calm, Nervous, Stressed or Panic, from how much the Nifty swings, how far it is below its high, and how many stocks are rising

**Prediction Ledger (Ratings tab)**
- Re-scores past months using only what was known then, and checks how Strong and Weak stocks did over the next month against the Nifty
- Every month stays on the record, good or bad

**What if, tax and journal (Portfolio tab)**
- What if the market falls or rises: estimated effect on each holding, based on how it moved with the Nifty over the past year
- Tax if you sold today: short-term and long-term gains matched first-in, first-out, with the yearly tax-free limit (rules from the July 2024 Budget)
- Investment journal: why you bought, when you would sell, and a review date
- Practice money: a separate pretend portfolio for trying ideas

**Compare**
- Up to 4 stocks or funds on one chart, all starting at 100, with returns and risk side by side

**Data**
- Daily data pipeline: NSE bhavcopy (every listed stock) and AMFI NAVs (every mutual fund scheme)
- Stock prices adjusted for splits and bonuses using the exchange's own previous-close figures
- Full fund NAV history from mfapi.in on first view, cross-checked against official AMFI NAVs
- Quality checks: broken rows are blocked, moves over 20% in a day are flagged
- Every stored number keeps its source and fetch time
- Login with hashed passwords, signed session cookies, and lockout after 5 wrong attempts
- Dashboard: market breadth, gainers, losers, most traded, unusual moves, data health
- Search across stocks and mutual funds, with a chart and stats for each
- Automatic refresh: stocks after 19:00 IST on weekdays, NAVs after 23:00 IST, while the server runs

## Setup

Needs Python 3.12 or newer.

```bash
pip install -r requirements.txt
python -m matrix.pipeline --days 250
python -m matrix.auth YOUR_NAME
python -m uvicorn matrix.api:app --port 8000
```

Then open http://localhost:8000 and log in.

`--days 250` loads about one year of stock prices and computes Matrix Scores (takes a few minutes). Fund history downloads the first time you open each fund.

## Tests

```bash
python -m pytest
```

## Layout

```
matrix/sources/   NSE prices, NSE feeds, AMFI and fund history loaders
matrix/validate.py  data quality rules
matrix/analytics.py returns, risk, XIRR, split adjustment
matrix/score.py   Matrix Score
matrix/portfolio.py holdings and returns
matrix/radar.py   Danger Radar rules and alerts
matrix/insights.py market mood, what-if scenarios, tax view
matrix/ledger.py  Prediction Ledger (score track record)
matrix/pipeline.py  fetch, validate, store
matrix/db.py      SQLite schema
matrix/auth.py    passwords and sessions
matrix/api.py     web API and daily refresh
web/              dashboard (HTML, CSS, JS)
docs/             design document
```

## Notes

- Storage is SQLite for now. The SQL is plain, so moving to PostgreSQL later needs no app changes.
- Data comes from public NSE and AMFI files for personal use. Check their terms before any wider use.
