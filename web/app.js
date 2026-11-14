const $ = (id) => document.getElementById(id);
const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
const whole = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const crore = (v) => `Rs ${whole.format(v / 1e7)} cr`;
const rupees = (v) => `${v < 0 ? "-" : ""}Rs ${whole.format(Math.abs(v))}`;
const sign = (n) => (n > 0 ? "up" : n < 0 ? "down" : "");
const pctText = (n, digits = 2) => (n == null ? "n/a" : `${n > 0 ? "+" : ""}${n.toFixed(digits)}%`);
const fracText = (f, digits = 1) => (f == null ? "n/a" : pctText(f * 100, digits));
const longDate = (d) => new Date(d + "T00:00:00").toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const SERIES_COLORS = ["#d9861a", "#3b82c4", "#a855c7", "#14a3a3"];

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (r.status === 401 && path !== "/api/login") { showLogin(); throw new Error("Not logged in"); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Request failed (${r.status})`);
  return r.json();
}

function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => (t.hidden = true), 2600);
}

/* ---------------------------------------------------------------- auth + tabs */
function showLogin() { $("app-view").hidden = true; $("login-view").hidden = false; }
function showApp() { $("login-view").hidden = true; $("app-view").hidden = false; switchTab(location.hash.slice(1) || "today"); }

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("login-error").textContent = "";
  try {
    await api("/api/login", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(e.target))) });
    e.target.reset(); showApp();
  } catch (err) { $("login-error").textContent = err.message; }
});
$("logout").addEventListener("click", async () => { await api("/api/logout", { method: "POST" }); showLogin(); });

const loaders = { today: loadToday, ratings: loadRatings, portfolio: loadPortfolio, compare: loadCompare };
function switchTab(tab) {
  if (!loaders[tab]) tab = "today";
  document.querySelectorAll("[data-view]").forEach((v) => (v.hidden = v.dataset.view !== tab));
  document.querySelectorAll("[data-tab]").forEach((b) => (b.dataset.tab === tab ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current")));
  history.replaceState(null, "", `#${tab}`);
  loaders[tab]().catch((err) => toast(err.message));
}
document.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));
window.addEventListener("hashchange", () => { if (!$("app-view").hidden) switchTab(location.hash.slice(1)); });

/* ---------------------------------------------------------------- shared pieces */
function scoreColor(s) { return s >= 70 ? cssVar("--gain") : s >= 40 ? cssVar("--saffron") : cssVar("--loss"); }
function scoreRing(s, size = "") {
  if (s == null) return "";
  return `<span class="score-ring ${size}" style="--s:${s};--c:${scoreColor(s)}" title="Matrix Score ${s} of 100"><b>${s}</b></span>`;
}
function heatColor(chg) {
  const t = Math.max(-1, Math.min(1, chg / 5));
  const base = t >= 0 ? cssVar("--gain") : cssVar("--loss");
  return `color-mix(in srgb, ${base} ${Math.round(25 + Math.abs(t) * 75)}%, ${cssVar("--flat")})`;
}
function moverRows(list) {
  if (!list.length) return `<tr><td class="muted">No stocks met the filter today.</td></tr>`;
  return list.map((s) => `
    <tr data-symbol="${esc(s.symbol)}" tabindex="0">
      <td><span class="sym">${esc(s.symbol)}</span><span class="nm">${esc(s.name)}</span></td>
      <td class="num">Rs ${inr.format(s.close)}</td>
      <td class="num ${sign(s.change_pct)}">${pctText(s.change_pct)}</td>
    </tr>`).join("");
}

/* ---------------------------------------------------------------- today */
async function loadToday() {
  const s = await api("/api/market/summary");
  if (!s.date) { $("hero-line").textContent = "No market data yet. Run the data pipeline to load it."; return; }
  const b = s.breadth;
  const mood = b.adv > b.dec * 1.5 ? "A strong day." : b.dec > b.adv * 1.5 ? "A weak day." : "A mixed day.";
  $("hero-date").textContent = longDate(s.date);
  $("asof").textContent = s.stale ? "Data is out of date" : "End-of-day data";
  $("asof").classList.toggle("stale", s.stale);
  $("hero-line").textContent = `${mood} ${whole.format(b.adv)} stocks rose, ${whole.format(b.dec)} fell, and ${crore(b.turnover)} changed hands.`;
  $("breadth-legend").innerHTML = `<span class="up">${whole.format(b.adv)} rose</span><span class="muted">${whole.format(b.unch)} unchanged</span><span class="down">${whole.format(b.dec)} fell</span>`;
  requestAnimationFrame(() => {
    const t = b.adv + b.dec + b.unch;
    for (const [cls, n] of [["adv", b.adv], ["unch", b.unch], ["dec", b.dec]]) $("breadth").querySelector(`.${cls}`).style.width = `${(n / t) * 100}%`;
  });
  $("heatmap").innerHTML = s.heatmap.map((h, i) => `
    <button class="tile" role="listitem" data-symbol="${esc(h.symbol)}" style="background:${heatColor(h.change_pct)};animation-delay:${Math.min(i * 6, 700)}ms"
      title="${esc(h.name)}: ${pctText(h.change_pct)}, ${crore(h.value)} traded">
      <span class="t-sym">${esc(h.symbol)}</span><span class="t-chg">${pctText(h.change_pct, 1)}</span>
    </button>`).join("");
  $("gainers").innerHTML = moverRows(s.gainers);
  $("losers").innerHTML = moverRows(s.losers);
  $("flags").innerHTML = s.flags.length
    ? s.flags.map((f) => `<li><button data-symbol="${esc(f.symbol)}"><strong>${esc(f.symbol)}</strong><span class="${f.reason.includes("+") ? "up" : "down"}">${esc(f.reason)}</span></button></li>`).join("")
    : `<li class="muted">No stock moved more than 20% today.</li>`;
  loadHealth();
}

async function loadHealth() {
  const h = await api("/api/health");
  const card = (label, x) => `<div class="src ${x.stale ? "stale" : ""}"><strong>${label}</strong>
    <span>Latest ${esc(x.latest_date ?? "none")}, ${whole.format(x.days_stored)} days stored${x.stale ? ", out of date" : ""}</span></div>`;
  const issues = Object.fromEntries(h.issues.map((i) => [i.severity, i.n]));
  const last = h.runs[0];
  $("health").innerHTML = card("NSE stock prices", h.nse_bhavcopy) + card("Mutual fund NAVs", h.amfi_navall) +
    `<div class="src"><strong>Quality checks</strong><span>${whole.format(issues.quarantined ?? 0)} bad rows blocked, ${whole.format(issues.flagged ?? 0)} items flagged</span></div>` +
    (last ? `<div class="src ${last.status === "error" ? "stale" : ""}"><strong>Last data run</strong><span>${esc(last.source)} ${esc(last.status)}, ${whole.format(last.rows)} rows, ${esc(last.finished_at.replace("T", " ").slice(0, 16))}</span></div>` : "");
}

/* ---------------------------------------------------------------- ratings */
async function loadRatings() {
  const r = await api("/api/scores?limit=15");
  if (!r.date) { $("top-rated").innerHTML = `<li class="muted">No scores yet. Run python -m matrix.score after loading data.</li>`; return; }
  $("universe").textContent = `${whole.format(r.universe)} liquid stocks`;
  const item = (s) => {
    const why = s.reasons.slice(0, 2).map((x) => x.text).join("; ");
    return `<li><button data-symbol="${esc(s.symbol)}">${scoreRing(s.score, "small")}
      <span class="grow"><span class="sym">${esc(s.symbol)}</span> <span class="muted">${esc(s.name)}</span><br><span class="why">${esc(why) || "Average on every measure"}</span></span>
      <span class="num ${sign(s.change_pct)}">${pctText(s.change_pct)}</span></button></li>`;
  };
  $("top-rated").innerHTML = r.top.map(item).join("");
  $("bottom-rated").innerHTML = r.bottom.map(item).join("");
}

/* ---------------------------------------------------------------- portfolio */
async function loadPortfolio() {
  const p = await api("/api/portfolio");
  $("pf-value").textContent = rupees(p.value);
  $("pf-line").innerHTML = p.holdings.length
    ? `<span class="${sign(p.gain)}">${p.gain >= 0 ? "+" : ""}${rupees(p.gain)} (${fracText(p.gain_pct)})</span> on ${rupees(p.invested)} invested.
       True yearly return (XIRR): <strong class="${sign(p.xirr)}">${fracText(p.xirr)}</strong>${p.realised_gain ? `. Booked gains: ${rupees(p.realised_gain)}` : ""}`
    : "Add your first transaction below, or import a CSV file.";
  drawRing(p.allocation);
  $("pf-warnings").innerHTML = p.warnings.map((w) => `<div class="warn">${esc(w.text)}</div>`).join("");
  $("pf-holdings").innerHTML = p.holdings.length ? `<tr><th>Holding</th><th class="num">Quantity</th><th class="num">Avg cost</th><th class="num">Price</th><th class="num">Value</th><th class="num">Gain</th><th class="num">XIRR</th><th class="num">Weight</th></tr>` +
    p.holdings.map((h) => `<tr data-open="${h.kind}:${esc(h.code)}" tabindex="0">
      <td><span class="sym">${esc(h.kind === "stock" ? h.code : h.name)}</span><span class="nm">${esc(h.kind === "stock" ? h.name : `Fund ${h.code}`)}</span></td>
      <td class="num">${inr.format(h.quantity)}</td><td class="num">${inr.format(h.avg_cost)}</td><td class="num">${inr.format(h.price)}</td>
      <td class="num">${rupees(h.value)}</td><td class="num ${sign(h.gain)}">${fracText(h.gain_pct)}</td>
      <td class="num ${sign(h.xirr)}">${fracText(h.xirr)}</td><td class="num">${(h.weight * 100).toFixed(1)}%</td></tr>`).join("")
    : `<tr><td class="muted">No holdings yet.</td></tr>`;
  $("pf-tx").innerHTML = p.transactions.length ? `<tr><th>Date</th><th>Holding</th><th>Side</th><th class="num">Quantity</th><th class="num">Price</th><th></th></tr>` +
    p.transactions.map((t) => `<tr><td>${esc(t.date)}</td><td>${esc(t.code)}</td><td>${esc(t.side)}</td><td class="num">${inr.format(t.quantity)}</td><td class="num">${inr.format(t.price)}</td>
      <td class="num"><button class="link" data-delete="${t.id}">Delete</button></td></tr>`).join("")
    : `<tr><td class="muted">No transactions yet.</td></tr>`;
}

function drawRing(alloc) {
  const parts = [["stock", "Stocks", cssVar("--saffron")], ["fund", "Funds", "#3b82c4"]].filter(([k]) => alloc[k]);
  const C = 2 * Math.PI * 48;
  let off = 0, svg = `<circle cx="60" cy="60" r="48" fill="none" stroke="${cssVar("--line")}" stroke-width="14"/>`;
  for (const [k, , color] of parts) {
    const len = alloc[k] * C;
    svg += `<circle cx="60" cy="60" r="48" fill="none" stroke="${color}" stroke-width="14" stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-off}" transform="rotate(-90 60 60)"/>`;
    off += len;
  }
  svg += parts.map(([k, label], i) => `<text x="60" y="${56 + i * 12}" text-anchor="middle">${label} ${Math.round(alloc[k] * 100)}%</text>`).join("");
  $("pf-ring").innerHTML = svg;
}

$("tx-form").date.value = new Date().toISOString().slice(0, 10);
$("tx-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = Object.fromEntries(new FormData(e.target));
  const msg = $("tx-msg"); msg.className = "error"; msg.textContent = "";
  try {
    await api("/api/portfolio/transactions", { method: "POST", body: JSON.stringify({ ...f, quantity: +f.quantity, price: +f.price }) });
    msg.className = "error ok"; msg.textContent = "Transaction added.";
    e.target.code.value = ""; e.target.quantity.value = ""; e.target.price.value = "";
    loadPortfolio();
  } catch (err) { msg.textContent = err.message; }
});
$("csv-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("csv-msg"); msg.className = "error"; msg.textContent = "";
  try {
    const text = await $("csv-file").files[0].text();
    const r = await api("/api/portfolio/import", { method: "POST", body: JSON.stringify({ csv: text }) });
    msg.className = "error ok"; msg.textContent = `Imported ${r.added} transactions.`;
    e.target.reset(); loadPortfolio();
  } catch (err) { msg.textContent = err.message; }
});

/* ---------------------------------------------------------------- compare */
let compareItems = [];
try { compareItems = JSON.parse(localStorage.getItem("matrix.compare") || "[]"); } catch { compareItems = []; }
function saveCompare() { try { localStorage.setItem("matrix.compare", JSON.stringify(compareItems)); } catch {} }
function addCompare(item) {
  if (compareItems.includes(item)) return toast("Already in compare");
  if (compareItems.length >= 4) return toast("Compare holds 4 at a time. Remove one first.");
  compareItems.push(item); saveCompare(); toast("Added to compare");
}

let cmpChart;
async function loadCompare() {
  $("cmp-chips").innerHTML = compareItems.length ? "" : `<span class="muted">Nothing added yet. Open any stock or fund and press "Add to compare".</span>`;
  $("cmp-table").innerHTML = ""; if (cmpChart) { cmpChart.remove(); cmpChart = null; }
  if (!compareItems.length) return;
  const data = await api(`/api/compare?items=${encodeURIComponent(compareItems.join(","))}`);
  $("cmp-chips").innerHTML = data.map((d, i) => `<span class="chip"><i style="background:${SERIES_COLORS[i]}"></i>${esc(d.kind === "stock" ? d.code : d.name)}<button data-uncompare="${i}" aria-label="Remove">x</button></span>`).join("");
  // Rebase all lines to 100 from the latest common start date.
  const start = data.map((d) => d.history[0]?.date).sort().at(-1);
  cmpChart = LightweightCharts.createChart($("cmp-chart"), chartOptions());
  data.forEach((d, i) => {
    const pts = d.history.filter((h) => h.date >= start);
    if (!pts.length) return;
    const base = pts[0].value;
    cmpChart.addLineSeries({ color: SERIES_COLORS[i], lineWidth: 2, priceFormat: { type: "custom", formatter: (v) => v.toFixed(1) } })
      .setData(pts.map((h) => ({ time: h.date, value: (h.value / base) * 100 })));
  });
  cmpChart.timeScale().fitContent();
  const rowsDef = [
    ["Matrix Score", (d) => d.score?.score ?? "n/a"],
    ["1 month", (d) => fracText(d.stats.return_1m)], ["6 months", (d) => fracText(d.stats.return_6m)],
    ["1 year", (d) => fracText(d.stats.return_1y)], ["3 years a year", (d) => fracText(d.stats.cagr_3y)],
    ["5 years a year", (d) => fracText(d.stats.cagr_5y)], ["Volatility", (d) => fracText(d.stats.volatility)],
    ["Worst fall, 1 year", (d) => fracText(d.stats.max_drawdown_1y)], ["History from", (d) => esc(d.stats.history_from)],
  ];
  $("cmp-table").innerHTML = `<tr><th></th>${data.map((d, i) => `<th class="num" style="color:${SERIES_COLORS[i]}">${esc(d.kind === "stock" ? d.code : d.name.slice(0, 32))}</th>`).join("")}</tr>` +
    rowsDef.map(([label, f]) => `<tr><td>${label}</td>${data.map((d) => `<td class="num">${f(d)}</td>`).join("")}</tr>`).join("");
}

/* ---------------------------------------------------------------- search */
let searchTimer;
$("search").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  const q = e.target.value.trim();
  if (q.length < 2) { $("search-results").hidden = true; return; }
  searchTimer = setTimeout(async () => {
    const [stocks, funds] = await Promise.all([
      api(`/api/stocks/search?query=${encodeURIComponent(q)}`),
      api(`/api/funds/search?query=${encodeURIComponent(q)}`),
    ]);
    const out = [];
    if (stocks.length) out.push(`<li class="group">Stocks</li>`, ...stocks.map((s) => `<li><button data-symbol="${esc(s.symbol)}"><span><strong>${esc(s.symbol)}</strong> ${esc(s.name)}</span><span class="kind">${esc(s.series)}</span></button></li>`));
    if (funds.length) out.push(`<li class="group">Mutual funds (direct plans)</li>`, ...funds.map((f) => `<li><button data-fund="${esc(f.scheme_code)}"><span>${esc(f.name)} <span class="muted">${esc(f.option ?? "")}</span></span><span class="kind">NAV ${inr.format(f.nav)}</span></button></li>`));
    $("search-results").innerHTML = out.length ? out.join("") : `<li class="group">Nothing matches "${esc(q)}". Try a symbol like TCS or a fund name like "parag flexi".</li>`;
    $("search-results").hidden = false;
  }, 220);
});

/* ---------------------------------------------------------------- clicks */
document.addEventListener("click", async (e) => {
  if (!e.target.closest(".search")) $("search-results").hidden = true;
  const sym = e.target.closest("[data-symbol]"); if (sym) return openStock(sym.dataset.symbol);
  const fund = e.target.closest("[data-fund]"); if (fund) return openFund(fund.dataset.fund);
  const open = e.target.closest("[data-open]");
  if (open && !e.target.closest("[data-delete]")) { const [k, c] = open.dataset.open.split(":"); return k === "stock" ? openStock(c) : openFund(c); }
  const del = e.target.closest("[data-delete]");
  if (del && confirm("Delete this transaction? This cannot be undone.")) {
    try { await api(`/api/portfolio/transactions/${del.dataset.delete}`, { method: "DELETE" }); toast("Transaction deleted"); loadPortfolio(); }
    catch (err) { toast(err.message); }
  }
  const un = e.target.closest("[data-uncompare]");
  if (un) { compareItems.splice(+un.dataset.uncompare, 1); saveCompare(); loadCompare(); }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closeDrawer(); $("search-results").hidden = true; }
  if (e.key === "Enter" && e.target.matches("tr[data-symbol]")) openStock(e.target.dataset.symbol);
  if (e.key === "Enter" && e.target.matches("tr[data-open]")) e.target.click();
});

/* ---------------------------------------------------------------- drawer */
let chart, drawerItem;
function openDrawer() { $("drawer").classList.add("open"); $("drawer").setAttribute("aria-hidden", "false"); $("scrim").hidden = false; $("search-results").hidden = true; $("drawer-close").focus(); }
function closeDrawer() { $("drawer").classList.remove("open"); $("drawer").setAttribute("aria-hidden", "true"); $("scrim").hidden = true; }
$("drawer-close").addEventListener("click", closeDrawer);
$("scrim").addEventListener("click", closeDrawer);
$("drawer-compare").addEventListener("click", () => drawerItem && addCompare(drawerItem));

function chartOptions() {
  return {
    autoSize: true,
    layout: { background: { color: "transparent" }, textColor: cssVar("--muted"), fontFamily: "Schibsted Grotesk" },
    grid: { vertLines: { visible: false }, horzLines: { color: cssVar("--line") } },
    rightPriceScale: { borderVisible: false }, timeScale: { borderVisible: false },
  };
}
function newChart() { if (chart) chart.remove(); chart = LightweightCharts.createChart($("chart"), chartOptions()); return chart; }
const stat = (k, v, cls = "") => `<div><dt>${k}</dt><dd class="${cls}">${v}</dd></div>`;
const LABELS = { momentum: "Momentum", trend: "Trend", volatility: "Calm", drawdown: "Worst fall", liquidity: "Ease of trading" };

async function openStock(symbol) {
  const d = await api(`/api/stocks/${encodeURIComponent(symbol)}`).catch((err) => toast(err.message));
  if (!d) return;
  drawerItem = `stock:${d.info.symbol}`;
  const st = d.stats, sc = d.score;
  $("drawer-kicker").textContent = `${d.info.symbol} on NSE, series ${d.info.series}`;
  $("drawer-title").textContent = d.info.name;
  $("drawer-price").innerHTML = `Rs ${inr.format(st.last)} <small class="${sign(st.change_1d)}">${fracText(st.change_1d, 2)} today</small>`;
  $("drawer-score").innerHTML = sc ? scoreRing(sc.score, "big") : "";
  openDrawer();
  newChart().addCandlestickSeries({ upColor: cssVar("--gain"), downColor: cssVar("--loss"), wickUpColor: cssVar("--gain"), wickDownColor: cssVar("--loss"), borderVisible: false })
    .setData(d.history.map((h) => ({ time: h.date, open: h.open, high: h.high, low: h.low, close: h.close })));
  chart.timeScale().fitContent();
  $("drawer-reasons").innerHTML = sc
    ? `<div class="bars">${Object.entries(sc.components).map(([k, v]) => v == null ? "" : `<div class="bar"><span>${LABELS[k]}</span><span class="track"><span class="fill" style="width:${v}%"></span></span><b>${Math.round(v)}</b></div>`).join("")}</div>` +
      sc.reasons.map((r) => `<p class="reason ${r.kind}">${esc(r.text)}</p>`).join("") +
      `<p class="note">Ranked against ${whole.format(sc.universe)} liquid stocks on ${esc(sc.date)}. 100 is best. Price behaviour only.</p>`
    : `<p class="note">No Matrix Score: needs about 6 months of history and Rs 1 crore traded on a typical day.</p>`;
  $("drawer-stats").innerHTML =
    stat("1 month", fracText(st.return_1m), sign(st.return_1m)) + stat("6 months", fracText(st.return_6m), sign(st.return_6m)) +
    stat("1 year", fracText(st.return_1y), sign(st.return_1y)) + stat("52-week range", `${inr.format(st.year_low)} to ${inr.format(st.year_high)}`) +
    stat("Yearly volatility", fracText(st.volatility)) + stat("Worst fall, 1 year", fracText(st.max_drawdown_1y), "down") +
    stat("Traded today", crore(st.traded_value));
  $("drawer-flags").innerHTML = d.flags.filter((f) => f.severity === "flagged").slice(0, 3).map((f) =>
    `<div class="flag-box"><strong>Unusual move on ${esc(f.date)}:</strong> ${esc(f.reason)}. Check company news and exchange filings for the reason.</div>`).join("");
  $("drawer-source").textContent = `Source: NSE daily bhavcopy, adjusted for splits and bonuses. Fetched ${d.info.fetched_at.replace("T", " ").slice(0, 16)} IST. End-of-day prices, not live.`;
}

async function openFund(code) {
  $("drawer-title").textContent = "Loading fund history...";
  $("drawer-reasons").innerHTML = $("drawer-stats").innerHTML = $("drawer-score").innerHTML = $("drawer-flags").innerHTML = "";
  openDrawer();
  const d = await api(`/api/funds/${encodeURIComponent(code)}`).catch((err) => toast(err.message));
  if (!d) return;
  drawerItem = `fund:${code}`;
  const f = d.info, st = d.stats, last = d.navs.at(-1);
  $("drawer-kicker").textContent = `${f.amc ?? ""} | ${f.category ?? "Mutual fund"}`;
  $("drawer-title").textContent = f.name;
  $("drawer-price").innerHTML = `NAV Rs ${inr.format(last.nav)} <small class="muted">on ${esc(last.date)}</small>`;
  newChart().addAreaSeries({ lineColor: cssVar("--saffron"), topColor: "rgba(217,134,26,.35)", bottomColor: "rgba(217,134,26,0)", lineWidth: 2 })
    .setData(d.navs.map((n) => ({ time: n.date, value: n.nav })));
  chart.timeScale().fitContent();
  const c1 = st.consistency_1y, c3 = st.consistency_3y;
  $("drawer-reasons").innerHTML = c1.windows
    ? `<p class="reason ${c1.positive_share >= 0.8 ? "strength" : c1.positive_share < 0.6 ? "weakness" : ""}">Made money in ${Math.round(c1.positive_share * 100)}% of all 1-year periods (worst ${fracText(c1.worst)}, best ${fracText(c1.best)})</p>` +
      (c3.windows ? `<p class="reason ${c3.positive_share >= 0.95 ? "strength" : ""}">Made money in ${Math.round(c3.positive_share * 100)}% of all 3-year periods (worst ${fracText(c3.worst)} a year)</p>` : "")
    : "";
  $("drawer-stats").innerHTML =
    stat("1 year", fracText(st.return_1y), sign(st.return_1y)) + stat("3 years, a year", fracText(st.cagr_3y), sign(st.cagr_3y)) +
    stat("5 years, a year", fracText(st.cagr_5y), sign(st.cagr_5y)) + stat("Volatility", fracText(st.volatility)) +
    stat("Worst fall ever", fracText(st.max_drawdown_all), "down") + stat("Plan", esc(f.plan ?? "n/a")) +
    stat("History from", esc(st.history_from)) + stat("Scheme code", esc(f.scheme_code));
  $("drawer-source").textContent = `Sources: ${d.sources.join(", ")}. Official AMFI NAVs take priority; history from mfapi.in is cross-checked against AMFI.`;
}

/* ---------------------------------------------------------------- start */
api("/api/me").then(showApp).catch(() => {});
