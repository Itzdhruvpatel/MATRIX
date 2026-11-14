const $ = (id) => document.getElementById(id);
const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
const whole = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const crore = (v) => `Rs ${whole.format(v / 1e7)} cr`;
const sign = (n) => (n > 0 ? "up" : n < 0 ? "down" : "");
const pctText = (n) => (n == null ? "n/a" : `${n > 0 ? "+" : ""}${inr.format(n)}%`);
const longDate = (d) => new Date(d + "T00:00:00").toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (r.status === 401 && path !== "/api/login") { showLogin(); throw new Error("Not logged in"); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Request failed (${r.status})`);
  return r.json();
}

function showLogin() { $("app-view").hidden = true; $("login-view").hidden = false; }
function showApp() { $("login-view").hidden = true; $("app-view").hidden = false; loadDashboard(); }

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  $("login-error").textContent = "";
  try {
    await api("/api/login", { method: "POST", body: JSON.stringify(Object.fromEntries(f)) });
    e.target.reset();
    showApp();
  } catch (err) { $("login-error").textContent = err.message; }
});
$("logout").addEventListener("click", async () => { await api("/api/logout", { method: "POST" }); showLogin(); });

/* ---------------------------------------------------------------- dashboard */
function moverRows(list, field = "change") {
  if (!list.length) return `<tr><td class="muted">No stocks met the filter today.</td></tr>`;
  return list.map((s) => `
    <tr data-symbol="${esc(s.symbol)}" tabindex="0">
      <td><span class="sym">${esc(s.symbol)}</span><span class="nm">${esc(s.name)}</span></td>
      <td class="num">Rs ${inr.format(s.close)}</td>
      <td class="num ${field === "change" ? sign(s.change_pct) : ""}">${field === "change" ? pctText(s.change_pct) : crore(s.value)}</td>
    </tr>`).join("");
}

async function loadDashboard() {
  const s = await api("/api/market/summary");
  if (!s.date) {
    $("hero-line").textContent = "No market data yet. Run the data pipeline to load it.";
    return;
  }
  const b = s.breadth;
  const mood = b.adv > b.dec * 1.5 ? "A strong day." : b.dec > b.adv * 1.5 ? "A weak day." : "A mixed day.";
  $("hero-date").textContent = longDate(s.date);
  $("hero-line").textContent = `${mood} ${whole.format(b.adv)} stocks rose, ${whole.format(b.dec)} fell, and ${crore(b.turnover)} changed hands.`;
  $("breadth-legend").innerHTML = `<span class="up">${whole.format(b.adv)} rose</span><span class="muted">${whole.format(b.unch)} unchanged</span><span class="down">${whole.format(b.dec)} fell</span>`;
  requestAnimationFrame(() => {
    const t = b.adv + b.dec + b.unch;
    $("breadth").querySelector(".adv").style.width = `${(b.adv / t) * 100}%`;
    $("breadth").querySelector(".unch").style.width = `${(b.unch / t) * 100}%`;
    $("breadth").querySelector(".dec").style.width = `${(b.dec / t) * 100}%`;
  });
  const asof = $("asof");
  asof.textContent = s.stale ? `Data is old: last update ${s.date}` : `End-of-day data for ${s.date}`;
  asof.classList.toggle("stale", s.stale);

  $("gainers").innerHTML = moverRows(s.gainers);
  $("losers").innerHTML = moverRows(s.losers);
  $("active").innerHTML = moverRows(s.most_active, "value");
  $("flags").innerHTML = s.flags.length
    ? s.flags.map((f) => `<li><button data-symbol="${esc(f.symbol)}"><strong>${esc(f.symbol)}</strong><span class="${f.reason.includes("+") ? "up" : "down"}">${esc(f.reason)}</span></button></li>`).join("")
    : `<li class="muted">No stock moved more than 20% today.</li>`;
  loadHealth();
}

async function loadHealth() {
  const h = await api("/api/health");
  const card = (label, x) => `<div class="src ${x.stale ? "stale" : ""}"><strong>${label}</strong>
    <span>Latest: ${esc(x.latest_date ?? "none")} &middot; ${whole.format(x.days_stored)} days stored${x.stale ? " &middot; out of date" : ""}</span></div>`;
  const issues = Object.fromEntries(h.issues.map((i) => [i.severity, i.n]));
  const lastRun = h.runs[0];
  $("health").innerHTML = card("NSE stock prices", h.nse_bhavcopy) + card("AMFI mutual fund NAVs", h.amfi_navall) +
    `<div class="src"><strong>Quality checks</strong><span>${whole.format(issues.quarantined ?? 0)} bad rows blocked, ${whole.format(issues.flagged ?? 0)} unusual moves flagged</span></div>` +
    (lastRun ? `<div class="src ${lastRun.status === "error" ? "stale" : ""}"><strong>Last data run</strong><span>${esc(lastRun.source)}: ${esc(lastRun.status)}, ${whole.format(lastRun.rows)} rows, ${esc(lastRun.finished_at.replace("T", " ").slice(0, 16))}</span></div>` : "");
}

document.addEventListener("click", (e) => {
  const row = e.target.closest("[data-symbol]");
  if (row) openStock(row.dataset.symbol);
  const fund = e.target.closest("[data-fund]");
  if (fund) openFund(fund.dataset.fund);
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closeDrawer(); $("search-results").hidden = true; }
  if (e.key === "Enter" && e.target.matches("tr[data-symbol]")) openStock(e.target.dataset.symbol);
});

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
document.addEventListener("click", (e) => { if (!e.target.closest(".search")) $("search-results").hidden = true; });

/* ---------------------------------------------------------------- drawer */
let chart;
function openDrawer() {
  $("drawer").classList.add("open"); $("drawer").setAttribute("aria-hidden", "false");
  $("scrim").hidden = false; $("search-results").hidden = true; $("drawer-close").focus();
}
function closeDrawer() {
  $("drawer").classList.remove("open"); $("drawer").setAttribute("aria-hidden", "true"); $("scrim").hidden = true;
}
$("drawer-close").addEventListener("click", closeDrawer);
$("scrim").addEventListener("click", closeDrawer);

function makeChart() {
  if (chart) chart.remove();
  const css = getComputedStyle(document.documentElement);
  chart = LightweightCharts.createChart($("chart"), {
    autoSize: true,
    layout: { background: { color: "transparent" }, textColor: css.getPropertyValue("--muted").trim(), fontFamily: "Schibsted Grotesk" },
    grid: { vertLines: { visible: false }, horzLines: { color: css.getPropertyValue("--line").trim() } },
    rightPriceScale: { borderVisible: false }, timeScale: { borderVisible: false },
  });
  return css;
}
const stat = (k, v, cls = "") => `<div><dt>${k}</dt><dd class="${cls}">${v}</dd></div>`;

async function openStock(symbol) {
  const d = await api(`/api/stocks/${encodeURIComponent(symbol)}`);
  const st = d.stats;
  $("drawer-kicker").textContent = `${d.info.symbol} on NSE, series ${d.info.series}`;
  $("drawer-title").textContent = d.info.name;
  $("drawer-price").innerHTML = `Rs ${inr.format(st.last)} <small class="${sign(st.change_1d)}">${pctText(st.change_1d)} today</small>`;
  openDrawer();
  const css = makeChart();
  chart.addCandlestickSeries({
    upColor: css.getPropertyValue("--gain").trim(), downColor: css.getPropertyValue("--loss").trim(),
    wickUpColor: css.getPropertyValue("--gain").trim(), wickDownColor: css.getPropertyValue("--loss").trim(), borderVisible: false,
  }).setData(d.history.map((h) => ({ time: h.date, open: h.open, high: h.high, low: h.low, close: h.close })));
  chart.timeScale().fitContent();
  $("drawer-stats").innerHTML =
    stat("1 week", pctText(st.change_1w), sign(st.change_1w)) +
    stat(`Over ${st.days} trading days`, pctText(st.change_period), sign(st.change_period)) +
    stat("Range in this period", `Rs ${inr.format(st.period_low)} to ${inr.format(st.period_high)}`) +
    stat("Below its high by", pctText(st.from_peak), sign(st.from_peak)) +
    stat("Yearly volatility", st.volatility_annual == null ? "Needs more data" : `${inr.format(st.volatility_annual)}%`) +
    stat("Traded today", crore(d.history.at(-1).value));
  $("drawer-flags").innerHTML = d.flags.filter((f) => f.severity === "flagged").map((f) =>
    `<div class="flag-box"><strong>Unusual move on ${esc(f.date)}:</strong> ${esc(f.reason)}. Check company news and exchange filings for the reason.</div>`).join("");
  $("drawer-source").textContent = `Source: NSE daily bhavcopy. Fetched ${d.info.fetched_at.replace("T", " ").slice(0, 16)} IST. End-of-day prices, not live.`;
}

async function openFund(code) {
  const d = await api(`/api/funds/${encodeURIComponent(code)}`);
  const f = d.info, navs = d.navs, last = navs.at(-1);
  $("drawer-kicker").textContent = `${f.amc ?? ""} | ${f.category ?? "Mutual fund"}`;
  $("drawer-title").textContent = f.name;
  $("drawer-price").innerHTML = `NAV Rs ${inr.format(last.nav)} <small class="muted">on ${esc(last.date)}</small>`;
  openDrawer();
  const css = makeChart();
  chart.addLineSeries({ color: css.getPropertyValue("--saffron").trim(), lineWidth: 2 })
    .setData(navs.map((n) => ({ time: n.date, value: n.nav })));
  chart.timeScale().fitContent();
  $("drawer-stats").innerHTML =
    stat("Plan", esc(f.plan ?? "n/a")) + stat("Option", esc(f.option ?? "n/a")) +
    stat("Scheme code", esc(f.scheme_code)) + stat("ISIN", esc(f.isin_growth ?? "n/a")) +
    stat("NAV history stored", `${navs.length} day${navs.length === 1 ? "" : "s"}`);
  $("drawer-flags").innerHTML = navs.length < 2
    ? `<div class="flag-box">Matrix started collecting NAVs today. The chart and returns fill in as each day's NAV arrives.</div>` : "";
  $("drawer-source").textContent = `Source: AMFI daily NAV file. Fetched ${f.fetched_at.replace("T", " ").slice(0, 16)} IST.`;
}

/* ---------------------------------------------------------------- start */
api("/api/me").then(showApp).catch(() => {});
