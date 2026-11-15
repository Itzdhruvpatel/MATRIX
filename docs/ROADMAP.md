# Matrix: what's left to build

Status as of 14 November 2026. Full plan: `docs/Matrix-Design.pdf`.

## 1. Done so far

- Daily data: NSE prices for every listed stock, AMFI NAVs for every mutual fund, with quality checks
- One year of stock history, adjusted for splits and bonuses
- Full fund history (from mfapi.in, checked against AMFI)
- Login with hashed passwords and lockout after wrong attempts
- Market today screen: summary, heatmap, gainers, losers, unusual moves
- Matrix Score v1 for about 1,500 stocks (price behaviour only)
- Portfolio: add or import buys and sells, profit, yearly growth (XIRR), over-10% warnings
- Compare up to 4 stocks or funds on one chart
- Danger Radar v1: price rules, official NSE filings (announcements, pledges, insider trades), big deals, follow list, Alerts screen

Effort key: S = a day or less, M = a few days, L = a week or more.

## 2. Still to build

### Phase 2: Danger Radar, news and company filings
- FII/DII money flows. Source: NSE. S
- Insider trade details (who, how many shares, buy or sell) by reading each filing's data file. M
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
- Macro dashboard: RBI rates, inflation, rupee, crude oil, bond yields. Source: RBI, MOSPI. M

### Phase 4: Forecast model, Prediction Ledger, paper portfolio
- Forecast card: chance of beating the index over 1, 3 and 12 months, with a likely range. Never a sure thing. Source: stored history. L
- Market mood detector (calm, nervous, stressed, crisis). S
- Prediction Ledger: every forecast saved and scored later against what really happened. This is how accuracy is measured honestly. M
- Testing on past years the model never saw, compared with simply buying a Nifty index fund. L
- Kill switch: hide forecasts if they do worse than the index fund for 3 months. S
- Paper portfolio: try ideas with pretend money. M
- Investment journal: write down why you bought, get reminded to review. S
- Cooling-off check before large or risky moves. S

### Phase 5: Paper trading period
- Run Phase 4 live with pretend money for at least 3 months. No real money yet. Fix what breaks. L (mostly waiting)

### Phase 6: More assets and tools
- IPO analyser: business quality, price vs similar companies, how much promoters are selling. Source: offer documents (DRHP/RHP). L
- Bond analyser: yield, rating, what happens if interest rates move. Source: RBI, CCIL, NSE debt segment. M
- Tax view: tax if you sell today, short vs long term, loss harvesting. S
- Scenario tester: "market falls 25%", "rates up 1%". M
- Backtester: test a rule on past years with costs and taxes. L
- Fund extras: expense ratio, direct vs regular cost, fund manager changes, portfolio overlap. Source: AMC monthly disclosures. M
- Goal tracker and allocation builder (with ranges of outcomes, not single numbers). M

## 3. Needs a decision from you

1. **Broker for live prices.** Which broker do you use (Zerodha, Upstox, Angel One, Dhan...)? Matrix connects read-only, so it can never place a trade. Some APIs are free, some charge monthly.
2. **Company financials source.** Free public filings (more work, sometimes messy) or a paid data vendor (cleaner, costs money).
3. **Personal only, or for others too?** Personal use is fine. Giving recommendations to other people needs SEBI registration.
4. **Where it runs.** Your own PC (free, but must stay on for daily updates) or a small cloud server in India (always on, small monthly cost).
5. **Claude API key** for the news reader, daily brief and AI chat. Cost depends on use; we can set a monthly limit.
6. **Telegram** for alerts? You'd create a bot (free) and share its token privately in `.env`.

## 4. Hardening before real money

- Two-step login (password + authenticator app)
- Daily encrypted backups, and a monthly test that restoring works
- Move from SQLite to PostgreSQL (needed if hosted or data grows)
- HTTPS if it runs on a server
- Alert you when a daily data job fails, so stale data never goes unnoticed
- Check the terms of use of every data source
- The 3-month paper trading rule (Phase 5) before any real money decision

## 5. Known gaps in what exists now

- Fund history loads only when you first open a fund, so new funds take a few seconds
- Matrix Score uses price behaviour only. No profits, debt or news yet
- Prices are end of day, not live
- CSV import uses Matrix's own format. No broker export or CAS statement import yet
- The `dev` test login should be removed once you create your own
- Daily updates run only while the server is running
- All data is in one SQLite file with no automatic backup yet

## 6. Recommended next 3 steps

1. **Danger Radar + filings (Phase 2).** Protecting money comes before finding returns, and it needs no paid data.
2. **Your broker's read-only API.** Live prices, and your real holdings import in one step instead of typing them.
3. **Company financials.** Turns the score from "how the price moved" into "how good the business is".

A reminder: no model predicts markets perfectly. Matrix shows chances and ranges, and the Prediction Ledger shows how often it was right.
