"""Build docs/Matrix-Design.pdf. Run: python docs/build_design_pdf.py"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

OUT = Path(__file__).with_name("Matrix-Design.pdf")

INK = colors.HexColor("#14213d")
ACCENT = colors.HexColor("#0f766e")
RED = colors.HexColor("#b91c1c")
AMBER = colors.HexColor("#b45309")
GREEN = colors.HexColor("#15803d")
LIGHT = colors.HexColor("#eef2f7")
LINE = colors.HexColor("#cbd5e1")

ss = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=ss["Normal"], fontName="Helvetica", fontSize=10,
                      leading=14.5, textColor=INK, spaceAfter=6)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8.5, leading=11.5, spaceAfter=0)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8.8, leading=11.8, spaceAfter=0)
CELLB = ParagraphStyle("cellb", parent=CELL, fontName="Helvetica-Bold")
H1 = ParagraphStyle("h1", parent=BODY, fontName="Helvetica-Bold", fontSize=18, leading=23,
                    textColor=INK, spaceBefore=4, spaceAfter=10)
H2 = ParagraphStyle("h2", parent=BODY, fontName="Helvetica-Bold", fontSize=12.5, leading=16,
                    textColor=ACCENT, spaceBefore=10, spaceAfter=5)
H3 = ParagraphStyle("h3", parent=BODY, fontName="Helvetica-Bold", fontSize=10.5, leading=14,
                    spaceBefore=6, spaceAfter=3)
BUL = ParagraphStyle("bul", parent=BODY, leftIndent=14, bulletIndent=3, spaceAfter=2.5)
TITLE = ParagraphStyle("title", parent=BODY, fontName="Helvetica-Bold", fontSize=40, leading=46,
                       alignment=TA_CENTER, textColor=INK)
SUB = ParagraphStyle("sub", parent=BODY, fontSize=14, leading=19, alignment=TA_CENTER,
                     textColor=ACCENT)
CENTER = ParagraphStyle("center", parent=BODY, alignment=TA_CENTER)

story = []


def h1(t):
    story.append(Paragraph(t, H1))


def h2(t):
    story.append(Paragraph(t, H2))


def h3(t):
    story.append(Paragraph(t, H3))


def p(t):
    story.append(Paragraph(t, BODY))


def bullets(items):
    for it in items:
        story.append(Paragraph(it, BUL, bulletText="•"))
    story.append(Spacer(1, 4))


def table(rows, widths, head=True, style=CELL):
    data = [[Paragraph(str(c), CELLB if (head and i == 0) else style) for c in r]
            for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if head else 0)
    cmds = [("GRID", (0, 0), (-1, -1), 0.4, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]
    if head:
        cmds.append(("BACKGROUND", (0, 0), (-1, 0), LIGHT))
    t.setStyle(TableStyle(cmds))
    story.append(t)
    story.append(Spacer(1, 8))


def callout(title, text, color=ACCENT):
    inner = [Paragraph(f'<font color="{color.hexval()}"><b>{title}</b></font>', BODY),
             Paragraph(text, BODY)]
    t = Table([[inner]], colWidths=[170 * mm])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1.2, color),
                           ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(KeepTogether(t))
    story.append(Spacer(1, 8))


def flow(steps):
    """Vertical box-and-arrow workflow."""
    rows = []
    for i, (name, desc) in enumerate(steps):
        rows.append([Paragraph(f"<b>{name}</b>", CELL), Paragraph(desc, CELL)])
        if i < len(steps) - 1:
            rows.append([Paragraph('<font color="#0f766e"><b>v</b></font>', CENTER), ""])
    t = Table(rows, colWidths=[45 * mm, 125 * mm])
    cmds = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6)]
    for r in range(0, len(rows), 2):
        cmds += [("BOX", (0, r), (-1, r), 0.8, ACCENT), ("BACKGROUND", (0, r), (0, r), LIGHT)]
    for r in range(1, len(rows), 2):
        cmds += [("SPAN", (0, r), (-1, r)), ("TOPPADDING", (0, r), (-1, r), 0),
                 ("BOTTOMPADDING", (0, r), (-1, r), 0)]
    t.setStyle(TableStyle(cmds))
    story.append(t)
    story.append(Spacer(1, 10))


# ---------------------------------------------------------------- cover
story += [Spacer(1, 55 * mm), Paragraph("MATRIX", TITLE), Spacer(1, 6 * mm),
          Paragraph("Personal Investment Intelligence Platform", SUB), Spacer(1, 4 * mm),
          Paragraph("Full product and system design: features, workflows, AI model, "
                    "danger warnings, architecture and build plan", CENTER),
          Spacer(1, 40 * mm),
          Paragraph("Design document v1.0  |  14 November 2026  |  Market focus: India", CENTER),
          Spacer(1, 3 * mm),
          Paragraph("Personal use tool. Not investment advice. Read Section 1 before anything else.",
                    CENTER),
          PageBreak()]

# ---------------------------------------------------------------- contents
h1("Contents")
toc = ["1. The honest foundation: what \"accurate\" means here",
       "2. Goals and non-goals", "3. Feature map (40 features in 10 modules)",
       "4. Daily system workflow", "5. User workflow: from money to decision",
       "6. Data sources", "7. The Matrix model: how the analysis engine works",
       "8. How we prove the model works (validation)", "9. Danger Radar: the warning system",
       "10. The AI analyst (chat)", "11. Screens and navigation",
       "12. System architecture and tech stack", "13. Security and privacy",
       "14. Legal and compliance", "15. Build roadmap",
       "16. Testing and success metrics", "17. Risks and how we handle them",
       "18. Rules for using Matrix with real money"]
bullets(toc)
story.append(PageBreak())

# ---------------------------------------------------------------- 1
h1("1. The honest foundation")
p("You asked for a model that makes 100% perfect predictions. The design starts by being "
  "straight with you about that, because you are putting real money behind it.")
callout("No system predicts markets perfectly",
        "Prices move on events that have not happened yet: a war, an RBI surprise, a fraud "
        "uncovered, a global crash. Perfect analysis of everything known today still cannot "
        "see tomorrow's news. The best hedge funds in the world, with thousands of PhDs and "
        "billions in data spend, are right on direction only a little more than half the time. "
        "They win by managing risk and sizing bets well, not by being always right. Any tool "
        "claiming 90%+ accuracy is either testing on data it already saw (a bug called "
        "look-ahead leakage) or lying.", RED)
p("So Matrix aims for something that actually makes money over time and protects it:")
table([["Instead of...", "Matrix gives you..."],
       ["\"This stock will go up\"",
        "\"62% probability of beating the Nifty over 3 months, likely range -8% to +14%, "
        "confidence: medium, here are the 4 reasons\""],
       ["One perfect pick", "Ranked options across all asset classes, each with risk, cost, tax "
        "and lock-in shown side by side"],
       ["Blind trust", "Every claim linked to its source: the filing, the news article, the number"],
       ["Hidden mistakes", "A Prediction Ledger: every forecast the model ever made, scored "
        "against what really happened, visible to you at all times"],
       ["Max profit at any cost", "Max return for the risk you choose, plus early warnings when "
        "danger shows up"]],
      [55, 115])
p("<b>Design principle:</b> the analysis should be as complete and correct as possible "
  "(right data, no stale numbers, every source covered). The predictions built on top of it "
  "are probabilities, measured honestly, and you see how good they really are.")
story.append(PageBreak())

# ---------------------------------------------------------------- 2
h1("2. Goals and non-goals")
h2("Goals")
bullets(["One place to see and compare every investment option available to an Indian investor.",
         "Daily automatic analysis of market data, news, company filings and the economy.",
         "Warn early and loudly when something you own or are watching turns dangerous.",
         "Explain everything in plain language (English or Hindi), with sources.",
         "Show probabilities and ranges, and prove accuracy with a public track record.",
         "Very easy to use: the most important thing is on the home screen, "
         "anything else within 3 clicks."])
h2("Non-goals (v1)")
bullets(["<b>No automatic trading.</b> Matrix never places orders. You decide and act through your "
         "broker. This protects you from a model bug emptying your account.",
         "<b>No intraday or F&amp;O trading signals.</b> SEBI's own studies found about 9 in 10 "
         "individual F&amp;O traders lose money. Matrix focuses on investing (weeks to years).",
         "<b>No non-public information.</b> Public data only (see Section 14).",
         "<b>No serving the public.</b> Personal tool. Opening it to others needs SEBI registration."])
story.append(PageBreak())

# ---------------------------------------------------------------- 3
h1("3. Feature map")
p("40 features grouped into 10 modules. Priority: <b>P1</b> = build first, <b>P2</b> = second "
  "release, <b>P3</b> = later.")

modules = [
    ("A. Investor profile", [
        ("1", "Risk profile quiz", "10 questions: age, income stability, horizon, how you react to "
         "a 30% fall. Sets your risk level 1 to 5.", "P1"),
        ("2", "Goals", "Retirement, house, child education: target amount and date per goal.", "P1"),
        ("3", "Constraints", "Emergency fund, liquidity needs, tax bracket, assets to avoid.", "P1"),
        ("4", "Comfort limits", "Max loss you can stomach, max % in one stock or sector.", "P1")]),
    ("B. Universe explorer", [
        ("5", "All asset classes", "Stocks, mutual funds, ETFs, IPOs, government and corporate "
         "bonds, T-bills, FDs, REITs, InvITs, gold (ETF, existing SGBs), PPF, NPS, "
         "international funds.", "P1"),
        ("6", "Side-by-side compare", "Return history, risk, fees, lock-in, tax, liquidity in "
         "one table for any mix of options.", "P1"),
        ("7", "Smart screener", "Filters in plain words: \"profitable midcaps, low debt, "
         "promoters buying\".", "P2"),
        ("8", "Watchlists", "Any number of lists; each item gets daily analysis.", "P1")]),
    ("C. Daily intelligence", [
        ("9", "Morning brief (8:30 AM)", "Global cues, what moved overnight, what matters for your "
         "holdings today. 2-minute read.", "P1"),
        ("10", "Evening digest (9 PM)", "What happened, why, what changed in your scores.", "P1"),
        ("11", "News engine", "Every article tagged to companies, sectors and event type, scored "
         "for sentiment and importance. Duplicates merged.", "P1"),
        ("12", "Filings tracker", "Results, announcements, credit rating changes, auditor "
         "resignations, from NSE/BSE.", "P1"),
        ("13", "Smart money tracker", "Insider and promoter trade disclosures, bulk and block "
         "deals, FII/DII flows, mutual fund buying and selling.", "P2"),
        ("14", "Macro dashboard", "RBI rates, inflation, rupee, crude oil, bond yields, "
         "US Fed, with what each means for each asset class.", "P2")]),
    ("D. Analysis per asset", [
        ("15", "Matrix Score", "0 to 100 score from quality, valuation, momentum, risk and "
         "sentiment, with the reasons listed.", "P1"),
        ("16", "Stock deep dive", "10 years of financials, peers, valuation vs history, "
         "cash flow quality, management track record.", "P1"),
        ("17", "Mutual fund analyser", "Rolling returns, consistency, expense ratio, direct vs "
         "regular cost, manager changes, portfolio overlap.", "P1"),
        ("18", "IPO analyser", "Financials, fresh issue vs promoter selling (OFS), valuation vs "
         "listed peers, subscription data, red flags.", "P2"),
        ("19", "Bond analyser", "Yield to maturity, credit rating and its trend, duration, "
         "what happens if rates move 1%.", "P2"),
        ("20", "Forecast card", "Probability of beating benchmark at 1, 3, 12 months, "
         "likely range, confidence.", "P2")]),
    ("E. Danger Radar", [
        ("21", "Red flag engine", "30+ rules (Section 9) on every holding and watchlist item.", "P1"),
        ("22", "Severity levels", "Info, Watch, Warning, Danger, with clear next steps.", "P1"),
        ("23", "Portfolio risk", "Concentration, sector bets, correlation, worst likely loss.", "P1"),
        ("24", "Market regime alert", "Calm, Nervous, Stressed, Crisis: based on volatility, "
         "breadth and trend.", "P2")]),
    ("F. Portfolio", [
        ("25", "Import holdings", "CAS statement (CAMS/KFintech/NSDL/CDSL), broker CSV, "
         "read-only broker API.", "P1"),
        ("26", "True returns", "XIRR per holding and overall, vs benchmark.", "P1"),
        ("27", "Hidden cost finder", "Commissions in regular plans, high-fee funds, idle cash.", "P1"),
        ("28", "Rebalance helper", "Shows drift from your target mix and options to fix it.", "P2")]),
    ("G. Planning and testing", [
        ("29", "Allocation builder", "Suggests a mix range for your risk level, shown as "
         "educational output, with Monte Carlo outcomes.", "P2"),
        ("30", "Scenario tester", "\"Market falls 25%\", \"rates up 1%\", \"rupee falls 10%\": "
         "impact on your portfolio.", "P2"),
        ("31", "Backtester", "Test any rule on 15+ years of history, with costs and taxes.", "P3"),
        ("32", "Goal tracker", "Chance of hitting each goal at current pace.", "P2")]),
    ("H. AI analyst", [
        ("33", "Ask anything", "Chat in English or Hindi. Answers use only Matrix data and "
         "always cite sources.", "P1"),
        ("34", "Explain like I'm new", "Toggle on every screen for simple language.", "P1")]),
    ("I. Tax", [
        ("35", "Tax view", "Short and long term gains, tax if you sell today, "
         "loss harvesting chances.", "P2")]),
    ("J. Discipline", [
        ("36", "Investment journal", "Record why you bought. Matrix reminds you to review it "
         "later.", "P1"),
        ("37", "Prediction Ledger", "Every forecast scored against reality. Shows real model "
         "accuracy.", "P1"),
        ("38", "Paper portfolio", "Try ideas with fake money first.", "P1"),
        ("39", "Alerts", "Telegram, email and browser push. Quiet hours.", "P1"),
        ("40", "Cooling-off check", "Large or high-risk moves trigger a 24-hour checklist "
         "before you act.", "P2")]),
]
for name, feats in modules:
    h3(name)
    table([["#", "Feature", "What it does", "Pri"]] + [list(f) for f in feats], [8, 38, 112, 12])
story.append(PageBreak())

# ---------------------------------------------------------------- 4
h1("4. Daily system workflow")
p("Times in IST. Everything runs automatically on a scheduler.")
table([["Time", "Job", "Output"],
       ["06:00", "Global cues: US/Europe/Asia close, crude, dollar, US yields, GIFT Nifty",
        "Overnight summary"],
       ["07:00", "Overnight news and filings pulled, tagged, scored", "Event list"],
       ["08:30", "Morning brief built for your holdings and watchlist", "Brief + alerts"],
       ["09:15 to 15:30", "Price checks every 15 minutes on your holdings; Danger Radar rules "
        "that need live prices", "Live alerts (Danger only)"],
       ["16:00", "End-of-day prices, volumes, delivery %, bulk/block deals", "Market data stored"],
       ["17:00 to 19:00", "Filings, insider disclosures, FII/DII data, mutual fund NAVs (AMFI)",
        "Data stored"],
       ["20:00", "Feature build, model scoring, Matrix Scores updated, Prediction Ledger "
        "graded", "New scores"],
       ["21:00", "Evening digest sent", "Digest"],
       ["Weekly (Sun)", "Model health check: accuracy vs baseline, data quality report",
        "Health report"],
       ["Monthly", "Model retraining on newest data (walk-forward)", "New model version"]],
      [28, 100, 42])
h2("Data pipeline per run")
flow([("1. Fetch", "Pull from each source. Retry 3 times. Record source and timestamp."),
      ("2. Validate", "Check for missing days, price jumps over 20% without a corporate action, "
       "stale data. Bad data is quarantined, never used."),
      ("3. Clean", "Adjust for splits, bonuses, dividends. Map every name to one company ID."),
      ("4. Store", "Raw copy kept forever (for audits) plus clean tables."),
      ("5. Features", "Compute ratios, momentum, volatility, sentiment, event flags."),
      ("6. Score", "Run rules, factor scores, ML forecasts, risk model. Combine."),
      ("7. Explain", "AI writes plain-language reasons from the numbers, with sources."),
      ("8. Alert", "Compare with yesterday. Send only what changed and matters.")])
story.append(PageBreak())

# ---------------------------------------------------------------- 5
h1("5. User workflow: from money to decision")
flow([("Onboard (once)", "Risk quiz, goals, comfort limits, import existing holdings."),
      ("See your picture", "Home shows net worth, mix, returns, today's top 3 things and any "
       "danger flags."),
      ("Read the brief", "2-minute morning brief: what changed and why it matters to you."),
      ("Explore options", "\"I have Rs 10 lakh to invest\": Matrix shows options across asset "
       "classes ranked for your profile, each with return range, risk, cost, tax, lock-in."),
      ("Deep dive", "Open any option: score, reasons, forecast card, red flags, sources. "
       "Ask the AI questions."),
      ("Stress test", "See how the new portfolio behaves in a crash, a rate hike, a rupee fall."),
      ("Decide", "You choose. Large moves go through the cooling-off checklist."),
      ("Record", "Journal entry: why you bought, what would make you sell."),
      ("Act", "Place the order with your own broker. Matrix never trades."),
      ("Monitor", "Danger Radar watches 24/7. Monthly review compares results to your "
       "journal reasons.")])
callout("Example: Rs 10 lakh, risk level 3, 5-year horizon",
        "Matrix shows: a range for equity vs debt vs gold suited to level 3; top-scored index and "
        "active funds with costs; high-quality bond options with current yields; two stocks "
        "scoring above 80 with their reasons; one IPO flagged Warning because 90% of it is "
        "promoters selling at a valuation 2x listed peers. Each option shows what you could "
        "lose in a bad year. You pick.", ACCENT)
story.append(PageBreak())

# ---------------------------------------------------------------- 6
h1("6. Data sources")
p("Public and licensed sources only. Prefer official sources; use paid vendors where "
  "terms of use forbid scraping.")
table([["Data", "Source", "Frequency"],
       ["Stock prices, volumes, delivery", "NSE/BSE end-of-day files, or broker API "
        "(Kite Connect, Upstox, etc.)", "Daily / 15 min"],
       ["Corporate announcements, results", "NSE/BSE corporate filings", "Continuous"],
       ["Insider and promoter trades, pledges", "NSE/BSE disclosures under SEBI rules",
        "Daily"],
       ["Bulk and block deals", "NSE/BSE", "Daily"],
       ["FII/DII flows", "NSE, NSDL", "Daily"],
       ["Mutual fund NAVs, schemes", "AMFI", "Daily"],
       ["Mutual fund portfolios", "Monthly AMC disclosures", "Monthly"],
       ["Company financials (10 years)", "Filings, or licensed data vendor", "Quarterly"],
       ["Bond yields, government securities", "RBI, CCIL, NSE debt segment", "Daily"],
       ["Credit ratings", "CRISIL, ICRA, CARE, India Ratings press releases", "Continuous"],
       ["Macro: rates, inflation, GDP", "RBI database, MOSPI", "As released"],
       ["Global markets, crude, dollar", "Market data API", "Daily"],
       ["News", "RSS feeds from financial news outlets, licensed news API", "Continuous"],
       ["Your holdings", "CAS PDF, broker CSV, read-only broker API", "On import / daily"]],
      [50, 85, 35])
callout("Rule: no number without a source",
        "Every stored value carries its source, fetch time and \"as of\" date. If data is older "
        "than expected, the screen shows a STALE badge and scores using it are marked lower "
        "confidence.", AMBER)
story.append(PageBreak())

# ---------------------------------------------------------------- 7
h1("7. The Matrix model")
p("No single model is reliable. Matrix stacks six layers. Each one is simple enough to check, "
  "and each covers a weakness of the others.")
table([["Layer", "What it does", "Method", "Why it's here"],
       ["1. Rules", "Hard red flags and filters", "Deterministic rules (Section 9)",
        "Catches known disasters. Never wrong about what it checks."],
       ["2. Factors", "Quality, value, momentum, low volatility, size",
        "Percentile ranks vs sector peers", "Decades of research show these factors are linked "
        "to long-run returns."],
       ["3. ML forecast", "Probability of beating benchmark at 1/3/12 months, plus range",
        "Gradient boosted trees (LightGBM) + quantile regression",
        "Finds combinations of signals humans miss."],
       ["4. Text intelligence", "Reads news and filings: event type, sentiment, importance",
        "LLM extraction + finance sentiment model, event-study impact",
        "News moves prices. Turns text into numbers."],
       ["5. Regime", "Is the market calm, nervous, stressed or in crisis?",
        "Volatility, breadth and trend rules; hidden Markov model later",
        "Signals that work in calm markets often fail in crashes."],
       ["6. Risk", "How much could this lose?",
        "Volatility, drawdown, VaR/CVaR, correlation, Monte Carlo",
        "Profit means nothing without knowing the downside."]],
      [24, 42, 50, 54])
h2("How the layers combine")
flow([("Inputs", "Prices, financials, filings, news, flows, macro"),
      ("Layer 1 gate", "Any Danger flag caps the Matrix Score at 30, whatever else says."),
      ("Layers 2 to 4", "Factor score, ML probability and text sentiment each give a 0-100 view."),
      ("Regime weight", "Layer 5 shifts weights: in Stressed/Crisis, quality and low volatility "
       "count more, momentum less."),
      ("Confidence", "High when layers agree and data is fresh; low when they disagree."),
      ("Output", "Matrix Score 0-100 + confidence + forecast range + top reasons + sources")])
h2("Model details")
h3("ML forecast (Layer 3)")
bullets(["<b>Target:</b> will this asset beat its benchmark over the next N days? "
         "Predicting relative performance is more stable than predicting raw price.",
         "<b>Features (about 150):</b> returns over many windows, volatility, volume changes, "
         "valuation vs own history and peers, profit growth, debt, cash flow quality, "
         "promoter and FII holding changes, news sentiment trend, sector momentum, regime.",
         "<b>Model:</b> LightGBM classifier for probability, quantile regression for the "
         "10th to 90th percentile range. Probabilities calibrated so \"60%\" really means 60%.",
         "<b>Training:</b> walk-forward on 15+ years, retrained monthly, only data available at "
         "that date (point-in-time). Includes companies that later delisted, so the model "
         "doesn't learn only from survivors."])
h3("Text intelligence (Layer 4)")
bullets(["LLM reads each article or filing and returns structured data: companies, event type "
         "(results, order win, fraud allegation, management exit, rating change...), "
         "sentiment, and whether it is new or a repeat.",
         "Event study: for each event type, measure the average price move in past cases. "
         "This tells you which kinds of news actually matter.",
         "Rumours and unverified social media are tagged LOW TRUST and never trigger "
         "alerts alone."])
h3("Mutual funds, bonds and IPOs")
bullets(["<b>Funds:</b> rolling return consistency, downside capture, cost, manager stability, "
         "holdings quality (scores of the stocks the fund holds).",
         "<b>Bonds:</b> yield vs risk-free rate, rating and rating trend, issuer financial "
         "health, sensitivity to rate changes.",
         "<b>IPOs:</b> rule-based scorecard: business quality, valuation vs peers, use of "
         "money raised, promoter selling, red flags in the offer document. Grey market "
         "premium shown only as an unofficial, unreliable signal."])
story.append(PageBreak())

# ---------------------------------------------------------------- 8
h1("8. How we prove the model works")
p("A model that looks great on past data can fail with real money. These checks stop that.")
table([["Check", "What it means", "Pass rule"],
       ["Walk-forward test", "Train on years 1-5, test on year 6; train on 1-6, test on 7; and so on",
        "Must beat baseline in most test years, not just on average"],
       ["Baseline comparison", "Compare against simply buying a Nifty 50 index fund",
        "If Matrix can't beat the index after costs, it says so"],
       ["Costs and taxes", "Include brokerage, STT, slippage and capital gains tax",
        "Returns reported after all costs"],
       ["Calibration", "Of all \"70% likely\" calls, did about 70% happen?",
        "Brier score better than baseline; calibration chart shown in app"],
       ["Leakage audit", "No future data in any feature (e.g. results used before release date)",
        "Automated test on every feature"],
       ["Paper trading", "Run live with fake money before trusting with real money",
        "Minimum 3 months live before any real-money use"],
       ["Kill switch", "Live accuracy drops below baseline for 3 months running",
        "Forecasts hidden, rules and data still shown, model retrained"]],
      [32, 78, 60])
callout("What \"good\" looks like",
        "In real markets, a model that is right on direction 55 to 58% of the time, with "
        "well-sized positions and strict risk control, is excellent. If a backtest shows "
        "80%+, assume a bug until proven otherwise.", AMBER)
story.append(PageBreak())

# ---------------------------------------------------------------- 9
h1("9. Danger Radar")
p("Rules run daily on every holding and watchlist item. Each flag shows what triggered it, "
  "the source, and what you can do.")
table([["Level", "Meaning", "Delivery"],
       ['<font color="#15803d"><b>Info</b></font>', "Worth knowing", "Daily digest"],
       ['<font color="#b45309"><b>Watch</b></font>', "Early warning sign", "Daily digest, highlighted"],
       ['<font color="#b45309"><b>Warning</b></font>', "Real risk building", "Same-day alert"],
       ['<font color="#b91c1c"><b>Danger</b></font>', "Serious, act-now risk", "Instant alert"]],
      [30, 80, 60])
table([["Area", "Red flag", "Level"],
       ["Governance", "Auditor resigns mid-term", "Danger"],
       ["Governance", "Promoter pledges more than 50% of holding, or pledge rising fast", "Danger"],
       ["Governance", "Key management exits (CEO/CFO) within short period", "Warning"],
       ["Governance", "SEBI order, fraud allegation, forensic audit announced", "Danger"],
       ["Governance", "Promoters selling steadily over several quarters", "Warning"],
       ["Financial", "Profits rising but operating cash flow negative for 2+ years", "Warning"],
       ["Financial", "Debt to equity above 2 (non-financial companies) and rising", "Warning"],
       ["Financial", "Interest coverage below 1.5", "Danger"],
       ["Financial", "Receivables growing much faster than sales", "Watch"],
       ["Financial", "Related-party transactions growing sharply", "Watch"],
       ["Credit", "Credit rating downgrade, or placed on watch negative", "Warning"],
       ["Credit", "Rating downgrade to below investment grade", "Danger"],
       ["Price", "Falls 20%+ in a month with no clear news", "Warning"],
       ["Price", "Repeated upper circuits on low volume in small stock (possible pump)", "Danger"],
       ["Price", "Moved to trade-to-trade or added to SEBI surveillance list (ASM/GSM)", "Danger"],
       ["Valuation", "Valuation at extreme vs own 10-year history and peers", "Watch"],
       ["Fund", "Fund manager change", "Watch"],
       ["Fund", "Underperforms benchmark on 3-year rolling basis", "Warning"],
       ["Fund", "Holds downgraded or defaulting bonds (debt funds)", "Danger"],
       ["IPO", "Mostly promoter selling (OFS) at high valuation vs peers", "Warning"],
       ["IPO", "Loss-making with no clear path to profit, priced at a premium", "Warning"],
       ["Scam", "Tip from Telegram/WhatsApp promising guaranteed returns", "Danger"],
       ["Portfolio", "One stock over your comfort limit (default 10%)", "Warning"],
       ["Portfolio", "One sector over 30%", "Watch"],
       ["Portfolio", "Worst likely 1-year loss exceeds your stated max loss", "Warning"],
       ["Market", "Regime moves to Stressed or Crisis", "Warning"]],
      [26, 116, 28])
story.append(PageBreak())

# ---------------------------------------------------------------- 10
h1("10. The AI analyst")
p("Chat that knows your portfolio and all the data Matrix holds.")
bullets(["<b>Grounded answers:</b> the AI gets data from Matrix's own database through tools "
         "(look up price, financials, news, scores). It is told never to invent numbers.",
         "<b>Citations:</b> every fact links to its source and \"as of\" date.",
         "<b>Says \"I don't know\":</b> when data is missing or stale, it says so.",
         "<b>Shows confidence:</b> uses the model's probabilities and ranges, never \"sure shot\".",
         "<b>Languages:</b> English and Hindi; \"explain like I'm new\" mode.",
         "<b>Model:</b> Claude (latest Sonnet for chat, Haiku for bulk news tagging) via API. "
         "Bulk jobs use batch processing to cut cost."])
h2("Example questions")
bullets(["\"Why did my portfolio fall 3% today?\"",
         "\"Compare these three large-cap funds for me in simple words.\"",
         "\"Is this IPO worth looking at? What are the risks?\"",
         "\"What happens to my bond fund if RBI cuts rates?\"",
         "\"Show me every Danger flag in my holdings and what triggered it.\""])

# ---------------------------------------------------------------- 11
h1("11. Screens and navigation")
p("Seven main screens. Bottom bar on mobile, left sidebar on desktop.")
table([["Screen", "What's on it"],
       ["Home", "Net worth, today's change, Danger flags, morning brief, top 3 actions to review"],
       ["Explore", "All asset classes, screener, compare tool, \"I have X to invest\" helper"],
       ["Asset page", "Score dial, reasons, forecast card, chart, financials, news, red flags, "
        "sources"],
       ["Portfolio", "Holdings, XIRR, mix, risk, hidden costs, scenario tester, tax view"],
       ["Alerts", "All flags by severity, with history"],
       ["Ask AI", "Chat with citations"],
       ["Journal", "Your reasons, paper portfolio, Prediction Ledger"]],
      [30, 140])
h2("Ease of use rules")
bullets(["Traffic-light colours everywhere: green, amber, red. Never colour alone; always a "
         "label too (for colour-blind users).",
         "Every number has a one-line plain-language tooltip.",
         "Most important thing first. No screen needs scrolling to see its key answer.",
         "Works on phone and desktop. Dark mode.",
         "Hindi and English toggle."])
story.append(PageBreak())

# ---------------------------------------------------------------- 12
h1("12. System architecture and tech stack")
p("Start as one simple app plus a scheduler. Split into services only when load demands it.")
flow([("Sources", "NSE/BSE, AMFI, RBI, news feeds, broker API, your CAS uploads"),
      ("Ingestion jobs", "Python workers on a scheduler (APScheduler, later Prefect)"),
      ("Database", "PostgreSQL with TimescaleDB for price history; raw files in object storage"),
      ("Analysis engine", "Python: pandas, LightGBM, scikit-learn; Claude API for text"),
      ("API", "FastAPI: serves scores, data, chat; login and permissions"),
      ("Web app", "Next.js (React) + Tailwind; charts with TradingView Lightweight Charts"),
      ("Alerts", "Telegram bot, email, browser push")])
table([["Part", "Choice", "Reason"],
       ["Backend", "Python 3.12+, FastAPI", "Best finance and ML libraries"],
       ["Database", "PostgreSQL + TimescaleDB", "Fast time-series queries, one database"],
       ["ML", "LightGBM, scikit-learn, statsmodels", "Proven on tabular financial data"],
       ["LLM", "Claude API (Sonnet for chat, Haiku for tagging)", "Strong reasoning, tool use, "
        "citations"],
       ["Frontend", "Next.js, Tailwind CSS", "Fast, mobile-friendly"],
       ["Charts", "Lightweight Charts, Recharts", "Free, built for markets"],
       ["Hosting", "One cloud VM in India region (or home server) + managed Postgres",
        "Cheap; data stays in India"],
       ["Jobs", "APScheduler first, Prefect later", "Simple to start"],
       ["Monitoring", "Logs + health page + Telegram alert on job failure",
        "Know immediately when data stops"]],
      [26, 68, 76])
story.append(PageBreak())

# ---------------------------------------------------------------- 13, 14
h1("13. Security and privacy")
bullets(["Login with strong password and two-factor authentication (authenticator app).",
         "Broker API keys are <b>read-only</b>. No trading permission is ever requested.",
         "All secrets in environment variables or a secrets manager. Never in code or git.",
         "Database encrypted at rest; HTTPS everywhere.",
         "Your PAN, account numbers and holdings never sent to the AI in raw form; "
         "the AI sees masked IDs.",
         "Daily encrypted backups, tested monthly by restoring.",
         "Audit log of every login and data export."])
h1("14. Legal and compliance (India)")
table([["Topic", "Position"],
       ["Insider trading", "SEBI's insider trading rules forbid trading on unpublished price-"
        "sensitive information. Matrix uses only public data. Public insider trade "
        "<i>disclosures</i> are fine and used."],
       ["Personal vs public use", "Using Matrix for your own money is fine. Giving buy/sell "
        "recommendations to others needs SEBI registration as an Investment Adviser or "
        "Research Analyst."],
       ["Data licensing", "Exchange data and news have terms of use. Scraping can break them. "
        "Use official files, broker APIs or paid vendors."],
       ["Disclaimer", "Every screen footer: analysis is informational, past performance does "
        "not guarantee future results, decisions are yours."],
       ["Professional advice", "For large sums, review major decisions with a SEBI-registered "
        "Investment Adviser (fee-only)."]],
      [38, 132])
story.append(PageBreak())

# ---------------------------------------------------------------- 15
h1("15. Build roadmap")
table([["Phase", "Weeks", "Delivers", "Done when"],
       ["0. Foundation", "1-2", "Repo, database, login, data pipeline skeleton, "
        "stock + MF daily data", "Prices and NAVs load daily with quality checks"],
       ["1. See everything", "3-6", "Portfolio import, XIRR, explorer, compare, asset pages, "
        "factor-based Matrix Score v1", "Your real holdings show correct returns"],
       ["2. Danger Radar", "7-9", "News + filings ingestion, LLM tagging, 30 red-flag rules, "
        "alerts on Telegram", "Rules tested on past cases (e.g. known collapses flagged early)"],
       ["3. Daily brief + AI", "10-12", "Morning brief, evening digest, AI analyst with "
        "citations", "Brief arrives 8:30 AM daily for 2 weeks without fail"],
       ["4. Forecast model", "13-18", "ML forecasts, regime, calibration, Prediction Ledger, "
        "paper portfolio", "Walk-forward beats baseline after costs"],
       ["5. Paper trading", "19-30", "Run live on paper. Fix what breaks. No real money yet.",
        "3+ months of live results, honestly measured"],
       ["6. More assets", "Ongoing", "IPO, bond, tax view, scenarios, backtester, Hindi",
        "Feature by feature"]],
      [30, 16, 70, 54])

# ---------------------------------------------------------------- 16
h1("16. Testing and success metrics")
table([["Area", "Test", "Target"],
       ["Data", "Daily checks: no missing days, prices match exchange closing", "99.5% complete"],
       ["Calculations", "XIRR, ratios, tax against hand-computed examples", "Exact match"],
       ["Rules", "Each red flag tested on known past cases", "All past cases flagged"],
       ["Model", "Walk-forward, calibration, leakage audit", "Beats baseline after costs"],
       ["AI analyst", "100 test questions; check every number against database",
        "Zero invented numbers"],
       ["Reliability", "Brief and digest delivery", "On time 99% of days"],
       ["Usability", "Key answer visible on each screen without scrolling", "All 7 screens"]],
      [28, 92, 50])
story.append(PageBreak())

# ---------------------------------------------------------------- 17
h1("17. Risks and how we handle them")
table([["Risk", "Handling"],
       ["Overconfidence in the model", "Prediction Ledger, confidence levels, kill switch, "
        "cooling-off checks"],
       ["Bad or stale data", "Validation step, STALE badges, quarantine, source on every number"],
       ["AI makes up facts", "Tool-based answers only, citations, automated number checks"],
       ["Black swan crash", "Regime alerts, stress tests, diversification limits; no model "
        "prevents all losses"],
       ["Model stops working (market changes)", "Monthly retrain, weekly health check, "
        "fall back to rules + factors"],
       ["Data source blocks access", "Multiple sources per data type; paid vendor fallback"],
       ["Security breach", "Read-only keys, 2FA, encryption, masked data to AI"],
       ["Legal", "Personal use only, public data only, disclaimers"]],
      [55, 115])

# ---------------------------------------------------------------- 18
h1("18. Rules for using Matrix with real money")
callout("Read this before investing large amounts",
        "These rules matter more than any model.", RED)
bullets(["<b>Paper trade first.</b> At least 3 months of live paper results before real money.",
         "<b>Start small.</b> Begin with a small slice; increase only if live results hold up.",
         "<b>Keep an emergency fund</b> of 6 to 12 months of expenses outside the market.",
         "<b>Diversify.</b> No single stock over 10%, no sector over 30%, across asset classes.",
         "<b>Never act on one signal.</b> Wait for the score, the reasons and the risk to agree.",
         "<b>Never act on tips</b> from Telegram, WhatsApp or \"insider\" sources. Most are scams; "
         "real insider information is illegal to use.",
         "<b>Know your max loss</b> before you buy, and write it in the journal.",
         "<b>Get a second opinion</b> from a SEBI-registered fee-only adviser for big decisions.",
         "<b>Review monthly,</b> not hourly. Long horizons beat constant reaction."])
story.append(Spacer(1, 10))
p("<i>Matrix is a personal research tool. It does not provide investment advice and does not "
  "guarantee returns. All investments carry risk, including loss of capital.</i>")


def footer(canvas, doc):
    if doc.page == 1:
        return
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(20 * mm, 10 * mm, "Matrix - Design Document v1.0")
    canvas.drawRightString(190 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                  topMargin=18 * mm, bottomMargin=18 * mm, title="Matrix Design Document",
                  author="Matrix").build(story, onFirstPage=footer, onLaterPages=footer)
print(f"Wrote {OUT}")
