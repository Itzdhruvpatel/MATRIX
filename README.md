# Matrix

Personal investment research website for Indian markets. It loads NSE end-of-day stock prices and AMFI mutual fund NAVs every day, checks the data for errors, and shows the day's market in plain language.

This is a research tool. It does not give investment advice, place trades, or guarantee returns. The full design is in `docs/Matrix-Design.pdf`.

## What works today (Phase 0)

- Daily data pipeline: NSE bhavcopy (every listed stock) and AMFI NAVs (every mutual fund scheme)
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
python -m matrix.pipeline --days 30
python -m matrix.auth YOUR_NAME
python -m uvicorn matrix.api:app --port 8000
```

Then open http://localhost:8000 and log in.

`--days 30` loads the last 30 trading days of stock prices. Mutual fund NAV history builds up one day at a time from the first run.

## Tests

```bash
python -m pytest
```

## Layout

```
matrix/sources/   NSE and AMFI downloaders and parsers
matrix/validate.py  data quality rules
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
