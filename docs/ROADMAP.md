# Matrix: what's left to build

Status as of 19 November 2026. Full plan: `docs/Matrix-Design.pdf`.

## 1. Done so far

- Daily data: NSE prices for every listed stock, AMFI NAVs for every mutual fund, with quality checks
- One year of stock history, adjusted for splits and bonuses
- Full fund history (from mfapi.in, checked against AMFI)
- Login with hashed passwords and lockout after wrong attempts
- Market today screen: summary, heatmap, gainers, losers, unusual moves
- Matrix Score v1 for about 1,500 stocks (price behaviour only)
- Portfolio: add or import buys and sells, profit, yearly growth (XIRR), over-10% warnings
- Compare up to 4 stocks or funds on one chart
- Market mood, what-if scenarios, tax view, investment journal, practice money
- Prediction Ledger: past scores checked against what really happened
- Danger Radar v1: price rules, official NSE filings (announcements, pledges, insider trades), big deals, follow list, Alerts screen
- CAS import: every mutual fund (CAMS, KFintech) and demat holding (NSDL, CDSL) from one PDF, with the folio or broker it came from
- Forecast card: chance of beating the Nifty over 20 trading days, likely range, every forecast saved and graded in the Prediction Ledger
- Shortlist to research: plain rules, reasons per stock, past months compared with owning the Nifty
- Two-step login with an authenticator app
- Banner on Market today when the daily price or NAV update fails or runs late
- The GitHub Action stops with a clear message until the `DATABASE_URL` secret exists
- Trade planner on each stock: position size from the most you will lose, default stop and target
- Time Machine: 10,000 runs from the stock's own past moves plus a replay on its real past, showing how often the stop or target came first
- Daily chart patterns (1-year high, 200-day average crosses, trading jumps, price gaps) on Market today and as Info alerts
- Practice money rules that block practice buys over your cash, one-stock or loss-per-trade limits, or with no stop
- Alerts when a stock closes through a stop or target you saved
- Forecast kill switch: a forecast length is hidden while it loses to the simple guess over 3 months
- 3-month and 12-month forecasts next to the 20-day one, each graded on its own
- Older NSE price files (before July 2024) and `--since` to load years of history
- Pattern backtest against the Nifty, after costs and tax
- Nightly encrypted backups with an automatic restore test
- Goal tracker with ranges of outcomes, and a bond calculator (Planning tab)
- FII/DII daily flows, RBI rates, the rupee, bond yields and India VIX on Market today
- Insider trade details from each filing's data file
- Cooling-off check on practice buys of stocks that moved fast or have serious alerts
- Direct vs Regular plan cost for funds

Effort key: S = a day or less, M = a few days, L = a week or more.

## 2. Still to build

### Phase 2: Danger Radar, news and company filings
- Credit rating changes direct from agencies. Source: CRISIL, ICRA, CARE press releases. M
- News reader: tag each article to companies, mark it good or bad news. Source: news RSS feeds + Claude API. L
- Remaining Danger Radar rules that need company financials (debt, cash flow, receivables) and fund data (manager change, underperformance). L
- Alerts on Telegram or email when something you own gets a Warning or Danger flag. S
- Company financials (profit, debt, cash flow, 10 years) so the score covers business quality, not just price. Source: needs a decision (see section 3). L

### Phase 3: Daily brief and AI analyst
- Morning brief at 8:30 AM: what changed overnight and what matters for your holdings. Source: global market data + news + Claude API. M
- Evening digest at 9 PM: what happened today and why. M
- Ask AI: chat that answers only from Matrix's own data and shows the source for every number. Source: Claude API. L
- "Explain like I'm new" mode and Hindi text. M
- Macro extras: inflation (CPI) and crude oil. RBI rates, rupee, bond yields and VIX are done. Source: MOSPI, a commodity price source. S

### Phase 4: Forecast model, Prediction Ledger, paper portfolio
- Load more years of prices on your own database (`python -m matrix.pipeline --since 2021-11-01`, then `python -m matrix.forecast`) so the models have more to learn from. S (mostly waiting)
- Testing on past years the model never saw, compared with simply buying a Nifty index fund. L

### Phase 5: Paper trading period
- Run Phase 4 live with pretend money for at least 3 months. No real money yet. Fix what breaks. L (mostly waiting)

### Phase 6: More assets and tools
- IPO analyser: business quality, price vs similar companies, how much promoters are selling. Source: offer documents (DRHP/RHP). L
- Bond analyser extras: live bond prices and ratings. The calculator is done. Source: RBI Retail Direct, NSE debt segment, rating agencies. M
- Backtester for your own rules (any score, pattern and holding period). The chart pattern backtest is done. M
- Fund extras: expense ratio, fund manager changes, portfolio overlap. Direct vs Regular cost is done. Source: AMC monthly disclosures. M
- Allocation builder (the goal tracker is done). M

## 3. Needs a decision from you

1. **Broker for live prices.** Which broker do you use (Zerodha, Upstox, Angel One, Dhan...)? Matrix connects read-only, so it can never place a trade. Some APIs are free, some charge monthly.
2. **Company financials source.** Free public filings (more work, sometimes messy) or a paid data vendor (cleaner, costs money).
3. **Personal only, or for others too?** Personal use is fine. Giving recommendations to other people needs SEBI registration.
4. **Where it runs.** Your own PC (free, but must stay on for daily updates) or a small cloud server in India (always on, small monthly cost).
5. **Claude API key** for the news reader, daily brief and AI chat. Cost depends on use; we can set a monthly limit.
6. **Telegram** for alerts? You'd create a bot (free) and share its token privately in `.env`.
7. **GitHub secret.** Add `DATABASE_URL` in the repository settings so the daily data job can run (see `docs/DEPLOY.md`).
8. **`MATRIX_OWNER`** on the hosted site, so only you see ratings, forecasts and the shortlist.

## 4. Hardening before real money

- Two-step login (password + authenticator app): done, turn it on in Account
- Daily encrypted backups with a restore test: done (runs each night while the server runs; keep a copy of `MATRIX_BACKUP_KEY` off the computer)
- Move from SQLite to PostgreSQL (needed if hosted or data grows)
- HTTPS if it runs on a server
- Alert you when a daily data job fails: done inside the app (banner on Market today). Telegram or email alerts still need item 6 in section 3
- Check the terms of use of every data source
- The 3-month paper trading rule (Phase 5) before any real money decision

## 5. Known gaps in what exists now

- Fund history loads only when you first open a fund, so new funds take a few seconds
- Matrix Score uses price behaviour only. No profits, debt or news yet
- Prices are end of day, not live
- A demat CAS (NSDL, CDSL) has no purchase prices, so those holdings count from the statement date. A mutual fund CAS must cover the period from your first purchase
- The forecast model is not better than a simple guess yet (see the Ratings tab)
- The `dev` test login should be removed once you create your own
- Saved stops and targets are in rupees; after a split or bonus they need to be set again
- Chart patterns and the Time Machine use one year of prices; more history would make both more reliable
- Daily updates run only while the server is running
- Backups run only from the server's nightly loop, not from the GitHub Action; on Supabase use its own daily backups
- FII/DII figures start from the day Matrix first runs; NSE's API gives only the latest day

## 6. Recommended next 3 steps

1. **Danger Radar + filings (Phase 2).** Protecting money comes before finding returns, and it needs no paid data.
2. **Your broker's read-only API.** Live prices, and your real holdings import in one step instead of typing them.
3. **Company financials.** Turns the score from "how the price moved" into "how good the business is".

A reminder: no model predicts markets perfectly. Matrix shows chances and ranges, and the Prediction Ledger shows how often it was right.
