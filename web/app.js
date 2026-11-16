const $ = (id) => document.getElementById(id);
const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
const whole = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const rupees = (v) => `${v < 0 ? "-" : ""}Rs ${whole.format(Math.abs(v))}`;
const crore = (v) => `Rs ${whole.format(v / 1e7)} crore`;
const bigMoney = (v) => (v >= 1e12 ? `Rs ${inr.format(v / 1e12)} lakh cr` : `Rs ${whole.format(v / 1e7)} cr`);
const sign = (n) => (n > 0 ? "up" : n < 0 ? "down" : "");
const pctText = (n, digits = 2) => (n == null ? "n/a" : `${n > 0 ? "+" : ""}${n.toFixed(digits)}%`);
const fracText = (f, digits = 1) => (f == null ? "n/a" : pctText(f * 100, digits));
const plainPct = (f) => `${Math.abs(f * 100).toFixed(0)}%`;
const longDate = (d) => new Date(d + "T00:00:00").toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
const shortDate = (d) => new Date(d + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const SERIES_COLORS = ["#151515", "#0b8a5c", "#b8322a", "#c08a1e"];
const tip = (text) => `<button class="tip" type="button" aria-label="${esc(text)}" data-tip="${esc(text)}">?</button>`;

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (r.status === 401 && path !== "/api/login") { showLogin(); throw new Error("Please log in again."); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Something went wrong (${r.status})`);
  return r.json();
}
function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => (t.hidden = true), 2800);
}

/* ---------------------------------------------------------------- auth + tabs */
function showLogin() { $("app-view").hidden = true; $("login-view").hidden = false; }
let me = { ratings: true };
async function showApp() {
  me = await api("/api/me");
  // Ratings are private to the site owner when the site is shared.
  document.querySelector('[data-tab="ratings"]').hidden = !me.ratings;
  $("login-view").hidden = true; $("app-view").hidden = false;
  const want = location.hash.slice(1) || "today";
  switchTab(want === "ratings" && !me.ratings ? "today" : want);
}
let signupMode = false;
api("/api/config").then((c) => { $("signup-switch").hidden = !c.signup; }).catch(() => {});
$("mode-btn").addEventListener("click", () => {
  signupMode = !signupMode;
  $("login-submit").textContent = signupMode ? "Create account" : "Log in";
  $("mode-btn").textContent = signupMode ? "I already have an account" : "Create an account";
  $("signup-switch").firstChild.textContent = signupMode ? "" : "New here? ";
  $("login-form").password.autocomplete = signupMode ? "new-password" : "current-password";
  $("login-error").textContent = signupMode ? "Username: 3 to 30 letters, numbers or _. Password: at least 10 characters." : "";
});
$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault(); $("login-error").textContent = "";
  try { await api(signupMode ? "/api/signup" : "/api/login", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(e.target))) }); e.target.reset(); showApp(); }
  catch (err) { $("login-error").textContent = err.message; }
});
$("logout").addEventListener("click", async () => { await api("/api/logout", { method: "POST" }); showLogin(); });

const loaders = { today: loadToday, ratings: loadRatings, portfolio: loadPortfolio, alerts: loadAlerts, compare: loadCompare };
function switchTab(tab) {
  if (!loaders[tab]) tab = "today";
  document.querySelectorAll("[data-view]").forEach((v) => (v.hidden = v.dataset.view !== tab));
  document.querySelectorAll("[data-tab]").forEach((b) => (b.dataset.tab === tab ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current")));
  document.body.dataset.tab = tab;
  history.replaceState(null, "", `#${tab}`);
  loaders[tab]().catch((err) => toast(err.message));
}
document.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));
window.addEventListener("hashchange", () => { if (!$("app-view").hidden) switchTab(location.hash.slice(1)); });

setTimeout(() => document.body.classList.add("settled"), 2500);

// The story paragraph darkens word by word as it scrolls into view.
function splitStory() {
  const el = $("story");
  el.innerHTML = el.innerHTML.replace(/(<em>.*?<\/em>)|([^\s<]+)/g, (m, em, w) => (em ? em : `<span>${w}</span>`));
  revealStory();
}
function revealStory() {
  const el = $("story");
  if (!el || el.closest("[hidden]")) return;
  const words = el.querySelectorAll("span"), r = el.getBoundingClientRect();
  const p = Math.min(Math.max((innerHeight * 0.9 - r.top) / (r.height + innerHeight * 0.3), 0), 1);
  words.forEach((w, i) => w.classList.toggle("lit", i / words.length < p));
}
addEventListener("scroll", revealStory, { passive: true });

// Buttons that jump to another tab.
document.addEventListener("click", (e) => { const g = e.target.closest("[data-goto]"); if (g) { switchTab(g.dataset.goto); scrollTo({ top: 0 }); } });

// Bar chart: share of stocks that rose on each recent day.
function drawBreadth(history) {
  const svg = $("breadth-chart");
  if (!svg || !history?.length) return;
  const W = 1000, H = 170, pad = 22, n = history.length, slot = (W - pad) / n, bw = Math.min(slot * 0.62, 34);
  const bars = history.map((d, i) => {
    const share = d.adv / Math.max(d.total, 1), bh = Math.max(share * (H - 30), 2);
    const x = pad + i * slot + (slot - bw) / 2, y = H - 18 - bh;
    const color = share >= 0.5 ? "var(--gain)" : "var(--loss)";
    const label = `${shortDate(d.date)}: ${Math.round(share * 100)}% of stocks rose`;
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" rx="4" fill="${color}" opacity="${i === n - 1 ? 1 : 0.78}" style="animation-delay:${600 + i * 45}ms"><title>${label}</title></rect>` +
      (i === 0 || i === n - 1 || i === Math.floor(n / 2) ? `<text x="${(x + bw / 2).toFixed(1)}" y="${H - 2}" text-anchor="middle">${shortDate(d.date).replace(/ \d{4}$/, "")}</text>` : "");
  }).join("");
  const halfY = H - 18 - 0.5 * (H - 30);
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("preserveAspectRatio", "none");
  svg.innerHTML = `<line class="half" x1="${pad}" x2="${W}" y1="${halfY}" y2="${halfY}"/><text x="0" y="${halfY + 4}">50%</text>${bars}`;
}

/* ---------------------------------------------------------------- shared */
function scoreLevel(s) {
  return s >= 80 ? ["Strong", "--s5"] : s >= 60 ? ["Good", "--s4"] : s >= 40 ? ["Average", "--s3"] : s >= 20 ? ["Weak", "--s2"] : ["Very weak", "--s1"];
}
function scoreBadge(s, big = false) {
  if (s == null) return "";
  const [word, color] = scoreLevel(s);
  return `<span class="score ${big ? "big" : ""}" style="background:var(${color})" title="Matrix Score ${s} out of 100: ${word}"><b>${s}</b><small>${word}</small></span>`;
}
function stockRow(s) {
  return `<li><button class="row-btn" data-symbol="${esc(s.symbol)}">
    <span class="grow"><span class="sym">${esc(s.symbol)}</span><span class="nm">${esc(s.name)}</span></span>
    <span class="price">Rs ${inr.format(s.close)}</span>
    <span class="pill ${sign(s.change_pct)}">${pctText(s.change_pct)}</span></button></li>`;
}

// Numbers count up once; the final value is set first so nothing depends on animation running.
function countUp(el, end) {
  el.textContent = whole.format(end);
  if (matchMedia("(prefers-reduced-motion: reduce)").matches || el.dataset.done) return;
  el.dataset.done = "1";
  const t0 = performance.now();
  const tick = (t) => {
    const p = Math.min((t - t0) / 1100, 1);
    el.textContent = whole.format(Math.round(end * (1 - (1 - p) ** 3)));
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/* ---------------------------------------------------------------- market today */
async function loadToday() {
  const s = await api("/api/market/summary");
  if (!s.date) { $("mood-title").textContent = "No market data yet"; $("mood-text").textContent = "Run the data loader once, then come back."; return; }
  const b = s.breadth, total = b.adv + b.dec + b.unch;
  const fell = Math.round((b.dec / total) * 10), rose = Math.round((b.adv / total) * 10);
  $("hero-date").textContent = `The Indian market, ${longDate(s.date)}` + (s.stale ? " (old data: run the data loader)" : "");
  $("mood-title").innerHTML = fell > rose ? `${fell} in 10<br><span class="r">fell</span>` : rose > fell ? `${rose} in 10<br><span class="g">rose</span>` : `Half<br>and half`;
  $("mood-text").innerHTML = `${whole.format(b.adv)} rose, ${whole.format(b.dec)} fell, <b>${bigMoney(b.turnover)}</b> changed hands`;
  // Handwritten notes around the headline: today's biggest moves, like chess moves in the margin.
  const slots = [[6, 20, -6], [13, 58, 5], [22, 36, -3], [72, 20, 4], [66, 62, -5], [76, 44, 2]];
  const moves = [...s.gainers.slice(0, 3), ...s.losers.slice(0, 3)];
  $("notes").innerHTML = moves.map((m, i) => {
    const [x, y, a] = slots[i];
    return `<span class="hand ${m.change_pct < 0 ? "r" : ""}" style="left:${x}%;top:${y}%;--a:${a}deg">${esc(m.symbol)} ${m.change_pct > 0 ? "+" : ""}${m.change_pct.toFixed(1)}<b class="pc">%</b></span>`;
  }).join("");
  const top = s.gainers[0], low = s.losers[0];
  const note = (m) => m ? `<em>${esc(m.symbol)} ${m.change_pct > 0 ? "+" : ""}${m.change_pct.toFixed(1)}<b class="pc">%</b></em>` : "";
  $("story").innerHTML = (fell > rose ? "Most companies lost value today" : rose > fell ? "Most companies gained value today" : "The market was split down the middle today") +
    `, and ${bigMoney(b.turnover)} changed hands. The biggest jump was ${top ? esc(top.symbol) : "nobody"}${note(top)}, while ${low ? esc(low.symbol) : "nobody"}${note(low)} fell the hardest. One day is a move, not the whole game. Check what you own before you act.`;
  splitStory();
  drawBreadth(s.history);
  $("gainers").innerHTML = s.gainers.slice(0, 5).map(stockRow).join("") || `<li class="empty">No company passed the filter today.</li>`;
  $("losers").innerHTML = s.losers.slice(0, 5).map(stockRow).join("") || `<li class="empty">No company passed the filter today.</li>`;
  $("flags").innerHTML = s.flags.length
    ? s.flags.slice(0, 5).map((f) => `<li><button class="row-btn" data-symbol="${esc(f.symbol)}"><span class="grow"><span class="sym">${esc(f.symbol)}</span></span>
        <span class="pill ${f.reason.includes("+") ? "up" : "down"}">${esc(f.reason.replace("price jump ", "").replace(" in one day", ""))}</span></button></li>`).join("")
    : `<li class="empty">Nothing unusual today.</li>`;
  loadHealth();
  loadMood();
}
async function loadHealth() {
  const h = await api("/api/health");
  const stale = h.nse_bhavcopy.stale || h.amfi_navall.stale;
  const last = h.runs.find((r) => r.status === "ok");
  $("health").innerHTML = `<span class="dot ${stale ? "bad" : ""}"></span>` + (stale
    ? "Some data is out of date. Run the data loader."
    : `Data is up to date. Prices from NSE (${shortDate(h.nse_bhavcopy.latest_date)}) and mutual fund values from AMFI, checked automatically${last ? `. Last update ${esc(last.finished_at.replace("T", " ").slice(0, 16))}` : ""}.`);
}

/* ---------------------------------------------------------------- ratings */
async function loadRatings() {
  const r = await api("/api/scores?limit=15");
  if (!r.date) { $("top-rated").innerHTML = `<li class="empty">No ratings yet. They appear after the data loader runs.</li>`; return; }
  $("universe").textContent = `${whole.format(r.universe)} actively traded stocks`;
  const item = (s) => `<li><button class="row-btn" data-symbol="${esc(s.symbol)}">${scoreBadge(s.score)}
    <span class="grow"><span class="sym">${esc(s.symbol)}</span><span class="nm">${esc(s.name)}</span>
    <span class="why">${esc(s.reasons.slice(0, 2).map((x) => x.text).join(", ")) || "Average on every measure"}</span></span></button></li>`;
  $("top-rated").innerHTML = r.top.map(item).join("");
  $("bottom-rated").innerHTML = r.bottom.map(item).join("");
  loadLedger();
}

/* ---------------------------------------------------------------- portfolio */
let book = "real";
document.querySelectorAll('input[name="book"]').forEach((r) => r.addEventListener("change", () => { book = r.value; loadPortfolio(); }));
async function loadPortfolio() {
  const p = await api(`/api/portfolio?book=${book}`);
  $("pf-heading").textContent = book === "paper" ? "My practice money is worth" : "My portfolio is worth";
  document.querySelectorAll(".real-only").forEach((el) => (el.hidden = book !== "real"));
  loadWhatIf(currentMove);
  if (book === "real") { loadTax(); loadJournal(); }
  const has = p.holdings.length > 0;
  $("pf-value").textContent = rupees(p.value);
  $("pf-invested").textContent = rupees(p.invested);
  $("pf-gain").innerHTML = has ? `<span class="${sign(p.gain)}">${p.gain >= 0 ? "+" : ""}${rupees(p.gain)}</span>` : "-";
  $("pf-xirr").innerHTML = p.xirr == null ? "-" : `<span class="${sign(p.xirr)}">${fracText(p.xirr)}</span>`;
  $("pf-line").textContent = !has
    ? (book === "paper" ? "Practice with pretend money: add buys and sells below as if they were real, and see how your ideas would have done without risking a rupee." : "Nothing here yet. Add what you own below (one by one, or many at once with a file), and Matrix will track its value every day.")
    : `You put in ${rupees(p.invested)} and it is worth ${rupees(p.value)} today, a ${p.gain >= 0 ? "profit" : "loss"} of ${rupees(Math.abs(p.gain))} (${fracText(p.gain_pct)}).` +
      (p.xirr != null ? ` That works out to ${fracText(p.xirr)} a year.` : "") +
      (p.realised_gain ? ` From things you already sold, you ${p.realised_gain >= 0 ? "made" : "lost"} ${rupees(Math.abs(p.realised_gain))}.` : "");
  const a = p.allocation, st = a.stock || 0, fd = a.fund || 0;
  $("pf-alloc").innerHTML = has ? `<span class="kpi-label">How your money is split</span>
    <div class="alloc-bar"><span style="width:${st * 100}%;background:var(--green)"></span><span style="width:${fd * 100}%;background:var(--ink)"></span></div>
    <div class="alloc-legend"><span><i style="background:var(--green)"></i>Stocks ${Math.round(st * 100)}%</span><span><i style="background:var(--ink)"></i>Mutual funds ${Math.round(fd * 100)}%</span></div>` : "";
  $("pf-warnings").innerHTML = p.warnings.map((w) => `<div class="warn">${esc(w.text)} Too much in one company means one bad event can hurt a lot.</div>`).join("");
  $("pf-holdings").innerHTML = has
    ? `<div class="h-row head"><span>Holding</span><span class="num">Value</span><span class="num">Profit or loss</span><span class="num hide-sm">Yearly growth</span><span class="num hide-sm">Share of total</span></div>` +
      p.holdings.map((h) => `<button class="h-row" data-open="${h.kind}:${esc(h.code)}">
        <span><span class="sym">${esc(h.kind === "stock" ? h.code : h.name)}</span><span class="nm">${inr.format(h.quantity)} ${h.kind === "stock" ? "shares" : "units"} at Rs ${inr.format(h.avg_cost)} each</span>${h.sources?.length ? `<span class="nm">From ${esc(h.sources.join("; "))}</span>` : ""}</span>
        <span class="num">${rupees(h.value)}<small>Rs ${inr.format(h.price)} each</small></span>
        <span class="num ${sign(h.gain)}">${h.gain >= 0 ? "+" : ""}${rupees(h.gain)}<small>${fracText(h.gain_pct)}</small></span>
        <span class="num hide-sm ${sign(h.xirr)}">${fracText(h.xirr)}</span>
        <span class="num hide-sm">${(h.weight * 100).toFixed(1)}%</span></button>`).join("")
    : `<p class="empty">Your holdings will appear here.</p>`;
  $("pf-tx").innerHTML = p.transactions.length
    ? `<div class="h-row tx-row head"><span>Date</span><span>Holding</span><span>Action</span><span class="num">How many</span><span class="num hide-sm">Price</span><span></span></div>` +
      p.transactions.map((t) => `<div class="h-row tx-row"><span>${shortDate(t.date)}</span><span class="sym">${esc(t.code)}</span><span>${t.side === "buy" ? "Bought" : "Sold"}</span>
        <span class="num">${inr.format(t.quantity)}</span><span class="num hide-sm">Rs ${inr.format(t.price)}</span>
        <span class="num"><button class="link" data-delete="${t.id}">Delete</button></span></div>`).join("")
    : `<p class="empty">Every purchase and sale you add is listed here.</p>`;
}
$("tx-form").date.value = new Date().toISOString().slice(0, 10);
$("tx-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = Object.fromEntries(new FormData(e.target)), msg = $("tx-msg");
  msg.className = "error"; msg.textContent = "";
  try {
    await api("/api/portfolio/transactions", { method: "POST", body: JSON.stringify({ ...f, quantity: +f.quantity, price: +f.price, book }) });
    msg.className = "error ok"; msg.textContent = "Saved.";
    for (const k of ["code", "quantity", "price"]) e.target[k].value = "";
    loadPortfolio();
  } catch (err) { msg.textContent = err.message; }
});
$("csv-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("csv-msg"); msg.className = "error"; msg.textContent = "";
  try {
    const r = await api("/api/portfolio/import", { method: "POST", body: JSON.stringify({ csv: await $("csv-file").files[0].text(), book }) });
    msg.className = "error ok"; msg.textContent = `Added ${r.added} entries.`; e.target.reset(); loadPortfolio();
  } catch (err) { msg.textContent = err.message; }
});

$("cas-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("cas-msg"), btn = e.target.querySelector("button[type=submit]");
  msg.className = "error"; msg.textContent = "Reading the statement. This can take a minute..."; $("cas-result").innerHTML = "";
  btn.disabled = true;
  try {
    const pdf = await new Promise((ok, fail) => { const r = new FileReader(); r.onload = () => ok(r.result.split(",")[1]); r.onerror = fail; r.readAsDataURL($("cas-file").files[0]); });
    const r = await api("/api/portfolio/import-cas", { method: "POST", body: JSON.stringify({ pdf, password: $("cas-password").value }) });
    msg.className = "error ok";
    msg.textContent = `Added ${r.added} entries.` + (r.already ? ` ${r.already} were already saved, so they were skipped.` : "") +
      (r.holdings_only ? ` ${r.holdings_only} holding${r.holdings_only > 1 ? "s" : ""} came without a purchase history, so ${r.holdings_only > 1 ? "they are" : "it is"} counted from the statement date at that day's price.` : "");
    $("cas-result").innerHTML = r.holdings.map((h) => `<li><button class="row-btn" data-open="${h.kind}:${esc(h.code)}"><span class="grow"><span class="sym">${esc(h.kind === "stock" ? h.code : h.name)}</span><span class="nm">From ${esc(h.source)}</span></span></button></li>`).join("") +
      r.skipped.map((s) => `<li class="empty">Skipped: ${esc(s)}</li>`).join("");
    e.target.reset(); loadPortfolio();
  } catch (err) { msg.textContent = err.message; }
  finally { $("cas-password").value = ""; btn.disabled = false; }
});

/* ---------------------------------------------------------------- alerts */
const LEVEL_WORD = { danger: "Danger", warning: "Warning", watch: "Watch", info: "Info" };
function alertItem(a, showCompany = true) {
  const link = a.link && a.link.startsWith("https://") ? ` <a href="${esc(a.link)}" target="_blank" rel="noopener noreferrer">Open the filing</a>` : "";
  const who = showCompany ? `<button class="who" data-symbol="${esc(a.symbol)}">${esc(a.symbol)}${a.name ? ` <span class="muted">${esc(a.name)}</span>` : ""}${a.owned ? " (you own this)" : ""}</button>` : "";
  return `<li><div class="alert ${esc(a.level)}"><span class="tag">${LEVEL_WORD[a.level]}</span><div class="grow">
    ${who}<h3>${esc(a.title)}</h3><p>${esc(a.detail ?? "")}</p>
    <small>${esc(a.source ?? "")}${a.date ? `, ${shortDate(a.date)}` : ""}${link}</small></div></div></li>`;
}
async function loadAlerts() {
  const a = await api("/api/alerts");
  const serious = a.mine.filter((m) => m.level === "danger" || m.level === "warning").length;
  $("al-title").textContent = !a.tracking ? "Alerts" : serious ? `${serious} thing${serious > 1 ? "s" : ""} to look at.` : "All clear for your stocks.";
  $("al-sub").textContent = !a.tracking
    ? "You are not following any stocks yet. Add what you own in My portfolio, or follow a stock, and Matrix will warn you here."
    : `Matrix is watching ${a.tracking} stock${a.tracking > 1 ? "s" : ""} for you, using prices and official company filings.`;
  $("al-watch").innerHTML = a.watchlist.map((w) => `<span class="chip">${esc(w.kind === "stock" ? w.code : w.name)}<button data-unwatch="${esc(w.kind)}:${esc(w.code)}" aria-label="Stop following ${esc(w.name)}">Unfollow</button></span>`).join("");
  $("al-mine").innerHTML = a.mine.map((m) => alertItem(m)).join("") || `<li class="empty">${a.tracking ? "No alerts for your stocks right now." : "Nothing to show yet."}</li>`;
  $("al-market").innerHTML = a.market.map((m) => alertItem(m)).join("") || `<li class="empty">No serious alerts in the market right now.</li>`;
}
async function setWatch(kind, code, on) {
  if (on) await api("/api/watchlist", { method: "POST", body: JSON.stringify({ kind, code }) });
  else await api(`/api/watchlist/${kind}/${encodeURIComponent(code)}`, { method: "DELETE" });
}

/* ---------------------------------------------------------------- mood, ledger, what-if, tax, journal */
async function loadMood() {
  const m = await api("/api/insights/mood");
  $("mood-card").className = `card mood ${m.level ?? ""}`;
  $("mood-level").textContent = m.level ?? "not enough data";
  $("mood-meaning").textContent = m.meaning ?? "";
  $("mood-reasons").innerHTML = (m.reasons ?? []).map((r) => `<li>${esc(r)}</li>`).join("");
}

async function loadLedger() {
  const t = await api("/api/ledger");
  if (!t.periods.length) { $("ledger-line").textContent = "Not enough history yet. The first results appear once a full month has passed after a scored day."; $("ledger-table").innerHTML = ""; return; }
  const n = t.periods.length, beat = t.strong_avg > t.market_avg;
  $("ledger-line").innerHTML = `Over the last ${n} months, Strong stocks returned <b>${fracText(t.strong_avg)}</b> a month on average, Weak stocks <b>${fracText(t.weak_avg)}</b>, and the Nifty <b>${fracText(t.market_avg)}</b>. ` +
    (beat ? `Strong stocks beat the Nifty on average. ` : `So far the score has <b>not</b> beaten simply owning the Nifty. `) +
    `Strong stocks did better than the Nifty in ${t.strong_won_periods} of ${n} months.`;
  $("ledger-table").innerHTML = `<tr><th style="text-align:left">Month starting</th><th>Strong stocks</th><th>Weak stocks</th><th>Nifty</th><th>Strong ones that beat the Nifty</th></tr>` +
    t.periods.map((r) => `<tr><td>${shortDate(r.date)}</td><td class="${sign(r.strong_avg)}">${fracText(r.strong_avg)}</td><td class="${sign(r.weak_avg)}">${fracText(r.weak_avg)}</td><td class="${sign(r.market)}">${fracText(r.market)}</td><td>${Math.round(r.strong_beat_share * 100)} of 100</td></tr>`).join("");
}

let currentMove = -0.2;
document.getElementById("moves").addEventListener("click", (e) => { const b = e.target.closest("[data-move]"); if (b) loadWhatIf(+b.dataset.move); });
async function loadWhatIf(move) {
  currentMove = move;
  document.querySelectorAll("#moves button").forEach((b) => b.classList.toggle("on", +b.dataset.move === move));
  const s = await api(`/api/insights/scenario?move=${move}&book=${book}`);
  if (!s.holdings.length) { $("whatif-line").textContent = "Add holdings first, then see how they might react."; $("whatif-rows").innerHTML = ""; return; }
  $("whatif-line").innerHTML = `If the Nifty ${move < 0 ? "falls" : "rises"} ${plainPct(move)}, your ${rupees(s.value)} could become about <b>${rupees(s.new_value)}</b> (${s.change >= 0 ? "+" : ""}${rupees(s.change)}).`;
  $("whatif-rows").innerHTML = `<div class="h-row head"><span>Holding</span><span class="num">Moves with the Nifty</span><span class="num">Estimated change</span><span class="num hide-sm">Value after</span><span class="num hide-sm"></span></div>` +
    s.holdings.map((h) => `<div class="h-row"><span><span class="sym">${esc(h.kind === "stock" ? h.code : h.name)}</span><span class="nm">${h.beta_known ? `Moves about ${h.beta.toFixed(1)}x the market` : "Not enough history: assumed to move like the market"}</span></span>
      <span class="num">${h.beta.toFixed(2)}x</span><span class="num ${sign(h.change)}">${h.change >= 0 ? "+" : ""}${rupees(h.change)}<small>${fracText(h.change_pct)}</small></span>
      <span class="num hide-sm">${rupees(h.new_value)}</span><span class="num hide-sm"></span></div>`).join("");
}

async function loadTax() {
  const t = await api("/api/insights/tax");
  $("tax-rules").textContent = `Listed shares and equity funds, using the tax rules from the ${t.rules_from}: 20% on short-term gains, 12.5% on long-term gains above Rs 1.25 lakh a year. Rules change, so check with a tax adviser before selling. This is an estimate, not tax advice.`;
  $("tax-st").textContent = rupees(t.short_term_tax);
  $("tax-lt").textContent = rupees(t.long_term_tax);
  $("tax-room").textContent = rupees(t.tax_free_room);
  if (!t.lots.length) { $("tax-line").textContent = "Nothing to tax yet."; $("tax-rows").innerHTML = ""; return; }
  const soon = t.lots.filter((l) => l.term === "short" && l.gain > 0).sort((a, b) => a.long_term_on.localeCompare(b.long_term_on))[0];
  $("tax-line").innerHTML = `Gains if you sold today: short-term <b>${rupees(t.short_term_gain)}</b>, long-term <b>${rupees(t.long_term_gain)}</b>.` +
    (t.slab_gain ? ` Other funds (taxed at your income slab): ${rupees(t.slab_gain)}.` : "") +
    (soon ? ` Waiting helps: your ${esc(soon.code)} shares bought on ${shortDate(soon.bought)} turn long-term on ${shortDate(soon.long_term_on)}.` : "");
  const term = { short: "Short-term", long: "Long-term", slab: "Income slab" };
  $("tax-rows").innerHTML = `<div class="h-row head"><span>Holding and date bought</span><span class="num">Gain</span><span class="num">Type</span><span class="num hide-sm">Held</span><span class="num hide-sm"></span></div>` +
    t.lots.map((l) => `<div class="h-row"><span><span class="sym">${esc(l.kind === "stock" ? l.code : l.name)}</span><span class="nm">${inr.format(l.quantity)} bought ${shortDate(l.bought)} at Rs ${inr.format(l.cost)}</span></span>
      <span class="num ${sign(l.gain)}">${l.gain >= 0 ? "+" : ""}${rupees(l.gain)}</span><span class="num">${term[l.term]}</span><span class="num hide-sm">${whole.format(l.days_held)} days</span><span class="num hide-sm"></span></div>`).join("");
}

async function loadJournal() {
  const rows = await api("/api/journal");
  $("journal-list").innerHTML = rows.length ? rows.map((e) => `<li><div class="j-item ${e.due ? "due" : ""}">
      <span class="sym">${esc(e.code)}</span>${e.due ? `<span class="due-tag">time to review</span>` : e.reviewed ? `<span class="due-tag" style="color:var(--green)">reviewed</span>` : ""}
      <p>${esc(e.note)}</p>${e.sell_if ? `<small>Sell if: ${esc(e.sell_if)}</small><br>` : ""}<small>Review on ${shortDate(e.review_on)}</small>
      <div class="j-actions">${e.reviewed ? "" : `<button class="ghost small" data-jdone="${e.id}">Mark reviewed</button>`}<button class="link" data-jdel="${e.id}">Delete</button></div>
    </div></li>`).join("") : `<li class="empty">No entries yet. Writing down why you buy is the cheapest way to avoid panic selling later.</li>`;
}
(() => {
  const f = $("journal-form");
  const d = new Date(); d.setDate(d.getDate() + 90);
  f.review_on.value = d.toISOString().slice(0, 10);
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = $("journal-msg"); msg.className = "error"; msg.textContent = "";
    try {
      await api("/api/journal", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(f))) });
      msg.className = "error ok"; msg.textContent = "Saved."; f.code.value = ""; f.note.value = ""; f.sell_if.value = "";
      loadJournal();
    } catch (err) { msg.textContent = err.message; }
  });
  $("journal-list").addEventListener("click", async (e) => {
    const done = e.target.closest("[data-jdone]"), del = e.target.closest("[data-jdel]");
    try {
      if (done) { await api(`/api/journal/${done.dataset.jdone}/reviewed`, { method: "POST" }); loadJournal(); }
      if (del && confirm("Delete this journal entry? This cannot be undone.")) { await api(`/api/journal/${del.dataset.jdel}`, { method: "DELETE" }); loadJournal(); }
    } catch (err) { toast(err.message); }
  });
})();

/* ---------------------------------------------------------------- compare */
let compareItems = [];
try { compareItems = JSON.parse(localStorage.getItem("matrix.compare") || "[]"); } catch { compareItems = []; }
const saveCompare = () => { try { localStorage.setItem("matrix.compare", JSON.stringify(compareItems)); } catch {} };
function addCompare(item) {
  if (compareItems.includes(item)) return toast("Already in Compare");
  if (compareItems.length >= 4) return toast("Compare holds 4 at a time. Remove one first.");
  compareItems.push(item); saveCompare(); toast("Added to Compare");
}
let cmpChart;
async function loadCompare() {
  $("cmp-table").innerHTML = ""; if (cmpChart) { cmpChart.remove(); cmpChart = null; }
  if (!compareItems.length) {
    $("cmp-chips").innerHTML = `<p class="hint">Nothing added yet. Search for a stock or fund at the top, open it, and press "+ Add to compare".</p>`;
    return;
  }
  const data = await api(`/api/compare?items=${encodeURIComponent(compareItems.join(","))}`);
  $("cmp-chips").innerHTML = data.map((d, i) => `<span class="chip"><i style="background:${SERIES_COLORS[i]}"></i>${esc(d.kind === "stock" ? d.code : d.name)}<button data-uncompare="${i}" aria-label="Remove ${esc(d.name)}">Remove</button></span>`).join("");
  const start = data.map((d) => d.history[0]?.date).sort().at(-1);
  cmpChart = LightweightCharts.createChart($("cmp-chart"), chartOptions());
  data.forEach((d, i) => {
    const pts = d.history.filter((h) => h.date >= start);
    if (!pts.length) return;
    const base = pts[0].value;
    cmpChart.addLineSeries({ color: SERIES_COLORS[i], lineWidth: 3, priceFormat: { type: "custom", formatter: (v) => v.toFixed(0) } })
      .setData(pts.map((h) => ({ time: h.date, value: (h.value / base) * 100 })));
  });
  cmpChart.timeScale().fitContent();
  const rows = [
    ["Matrix Score", (d) => d.score ? `${d.score.score} (${scoreLevel(d.score.score)[0]})` : "Only for stocks"],
    ["Change in 1 month", (d) => fracText(d.stats.return_1m)], ["Change in 1 year", (d) => fracText(d.stats.return_1y)],
    ["Yearly growth over 3 years", (d) => fracText(d.stats.cagr_3y)], ["Yearly growth over 5 years", (d) => fracText(d.stats.cagr_5y)],
    ["How much it swings", (d) => fracText(d.stats.volatility)], ["Biggest drop in 1 year", (d) => fracText(d.stats.max_drawdown_1y)],
  ];
  $("cmp-table").innerHTML = `<tr><th></th>${data.map((d, i) => `<th style="color:${SERIES_COLORS[i]}">${esc(d.kind === "stock" ? d.code : d.name.slice(0, 30))}</th>`).join("")}</tr>` +
    rows.map(([label, f]) => `<tr><td>${label}</td>${data.map((d) => `<td>${f(d)}</td>`).join("")}</tr>`).join("");
}

/* ---------------------------------------------------------------- search */
let searchTimer;
$("search").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  const q = e.target.value.trim();
  if (q.length < 2) { $("search-results").hidden = true; return; }
  searchTimer = setTimeout(async () => {
    const [stocks, funds] = await Promise.all([api(`/api/stocks/search?query=${encodeURIComponent(q)}`), api(`/api/funds/search?query=${encodeURIComponent(q)}`)]);
    const out = [];
    if (stocks.length) out.push(`<li class="group">Stocks</li>`, ...stocks.map((s) => `<li><button data-symbol="${esc(s.symbol)}"><span><strong>${esc(s.symbol)}</strong> <span class="muted">${esc(s.name)}</span></span></button></li>`));
    if (funds.length) out.push(`<li class="group">Mutual funds (direct plans, lower fees)</li>`, ...funds.map((f) => `<li><button data-fund="${esc(f.scheme_code)}"><span>${esc(f.name)} <span class="muted">${esc(f.option ?? "")}</span></span><span class="kind">Rs ${inr.format(f.nav)}</span></button></li>`));
    $("search-results").innerHTML = out.length ? out.join("") : `<li class="group">Nothing found for "${esc(q)}". Try a company name like "tata" or a fund like "parag flexi".</li>`;
    $("search-results").hidden = false;
  }, 220);
});

/* ---------------------------------------------------------------- clicks */
document.addEventListener("click", async (e) => {
  if (!e.target.closest(".search")) $("search-results").hidden = true;
  if (e.target.closest(".tip")) return;
  const del = e.target.closest("[data-delete]");
  if (del) {
    if (confirm("Delete this entry? This cannot be undone.")) {
      try { await api(`/api/portfolio/transactions/${del.dataset.delete}`, { method: "DELETE" }); toast("Deleted"); loadPortfolio(); } catch (err) { toast(err.message); }
    }
    return;
  }
  const sym = e.target.closest("[data-symbol]"); if (sym) return openStock(sym.dataset.symbol);
  const fund = e.target.closest("[data-fund]"); if (fund) return openFund(fund.dataset.fund);
  const open = e.target.closest("[data-open]"); if (open) { const [k, c] = open.dataset.open.split(":"); return k === "stock" ? openStock(c) : openFund(c); }
  const uw = e.target.closest("[data-unwatch]");
  if (uw) { const [k, c] = uw.dataset.unwatch.split(":"); await setWatch(k, c, false); toast("Stopped following"); return loadAlerts(); }
  const un = e.target.closest("[data-uncompare]"); if (un) { compareItems.splice(+un.dataset.uncompare, 1); saveCompare(); loadCompare(); }
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeDrawer(); $("search-results").hidden = true; } });

/* ---------------------------------------------------------------- detail panel */
let chart, drawerItem;
function openDrawer() { $("drawer").classList.add("open"); $("drawer").setAttribute("aria-hidden", "false"); $("scrim").hidden = false; $("search-results").hidden = true; $("drawer-close").focus(); }
function closeDrawer() { $("drawer").classList.remove("open"); $("drawer").setAttribute("aria-hidden", "true"); $("scrim").hidden = true; }
$("drawer-close").addEventListener("click", closeDrawer);
$("scrim").addEventListener("click", closeDrawer);
$("drawer-compare").addEventListener("click", () => drawerItem && addCompare(drawerItem));
function paintWatch(on) { const b = $("drawer-watch"); b.hidden = false; b.dataset.on = on ? "1" : ""; b.textContent = on ? "Following" : "Follow"; b.classList.toggle("following", on); }
$("drawer-watch").addEventListener("click", async () => {
  const [kind, code] = drawerItem.split(":"), on = !$("drawer-watch").dataset.on;
  try { await setWatch(kind, code, on); paintWatch(on); toast(on ? "Following. Alerts will show in the Alerts tab." : "Stopped following"); }
  catch (err) { toast(err.message); }
});
function chartOptions() {
  return {
    autoSize: true,
    layout: { background: { color: "transparent" }, textColor: "#6d6d6a", fontFamily: "Inter Tight" },
    grid: { vertLines: { visible: false }, horzLines: { color: "rgba(0,0,0,0.07)" } },
    rightPriceScale: { borderVisible: false }, timeScale: { borderVisible: false, minBarSpacing: 0.001 },
    crosshair: { horzLine: { labelBackgroundColor: "#151515" }, vertLine: { labelBackgroundColor: "#151515" } },
  };
}
function newChart() { if (chart) chart.remove(); chart = LightweightCharts.createChart($("chart"), chartOptions()); return chart; }
const stat = (k, v, cls = "", help = "") => `<div><dt>${k}${help ? tip(help) : ""}</dt><dd class="${cls}">${v}</dd></div>`;
const LABELS = { momentum: "Momentum", trend: "Trend", volatility: "Calm", drawdown: "Worst fall", liquidity: "Easy to trade" };
function resetDrawer(title) {
  $("drawer-title").textContent = title;
  for (const id of ["drawer-kicker", "drawer-price", "drawer-score", "drawer-simple", "drawer-stats", "drawer-reasons", "drawer-flags", "drawer-source"]) $(id).innerHTML = "";
  if (chart) { chart.remove(); chart = null; }
  $("drawer-watch").hidden = true;
  openDrawer();
}

async function openStock(symbol) {
  resetDrawer("Loading...");
  const d = await api(`/api/stocks/${encodeURIComponent(symbol)}`).catch((err) => { toast(err.message); closeDrawer(); });
  if (!d) return;
  drawerItem = `stock:${d.info.symbol}`;
  const st = d.stats, sc = d.score, name = d.info.name;
  $("drawer-kicker").textContent = `${d.info.symbol} | Stock on NSE`;
  $("drawer-title").textContent = name;
  $("drawer-price").innerHTML = `Rs ${inr.format(st.last)}<small class="${sign(st.change_1d)}">${fracText(st.change_1d, 2)} today</small>`;
  $("drawer-score").innerHTML = sc ? scoreBadge(sc.score, true) : "";

  const lines = [];
  if (st.return_1y != null) lines.push(`Over the past year the price ${st.return_1y >= 0 ? "went up" : "went down"} by <b>${plainPct(st.return_1y)}</b>. Rs 10,000 put in a year ago would be about <b>${rupees(10000 * (1 + st.return_1y))}</b> today.`);
  else if (st.return_6m != null) lines.push(`Over the past 6 months the price ${st.return_6m >= 0 ? "went up" : "went down"} by <b>${plainPct(st.return_6m)}</b>.`);
  if (st.max_drawdown_1y != null) lines.push(`At its worst point this year it was <b>${plainPct(st.max_drawdown_1y)} below</b> its earlier high.`);
  if (sc?.components?.volatility != null) lines.push(sc.components.volatility >= 60 ? "Its price moves more calmly than most stocks." : sc.components.volatility <= 40 ? "Its price swings more than most stocks, so expect bigger ups and downs." : "Its price swings about as much as an average stock.");
  if (sc) lines.push(`Matrix rates it <b>${sc.score} out of 100 (${scoreLevel(sc.score)[0]})</b> for how its price behaved. This is not a buy or sell signal.`);
  $("drawer-simple").innerHTML = `<h3>In simple words</h3>${lines.map((l) => `<p>${l}</p>`).join("")}`;

  newChart().addCandlestickSeries({ upColor: "#0b8a5c", downColor: "#b8322a", wickUpColor: "#0b8a5c", wickDownColor: "#b8322a", borderVisible: false })
    .setData(d.history.map((h) => ({ time: h.date, open: h.open, high: h.high, low: h.low, close: h.close })));
  chart.timeScale().fitContent();
  $("drawer-stats").innerHTML =
    stat("1 month", fracText(st.return_1m), sign(st.return_1m)) + stat("6 months", fracText(st.return_6m), sign(st.return_6m)) + stat("1 year", fracText(st.return_1y), sign(st.return_1y)) +
    stat("Lowest and highest in 1 year", `${inr.format(st.year_low)} to ${inr.format(st.year_high)}`) +
    stat("How much it swings", fracText(st.volatility), "", "Called volatility. Higher means bigger daily ups and downs. Most large companies are between 20% and 35%.") +
    stat("Biggest drop in 1 year", fracText(st.max_drawdown_1y), "down", "The worst fall from a high point to a low point during the past year.");
  $("drawer-reasons").innerHTML = sc
    ? `<h3>Why it got ${sc.score}</h3><div class="bars">${Object.entries(sc.components).map(([k, v]) => v == null ? "" : `<div class="bar"><span>${LABELS[k]}</span><span class="track"><span class="fill" style="width:${v}%;background:var(${scoreLevel(Math.round(v))[1]})"></span></span><b>${Math.round(v)}</b></div>`).join("")}</div>` +
      sc.reasons.map((r) => `<p class="reason ${r.kind}">${esc(r.text[0].toUpperCase() + r.text.slice(1))}</p>`).join("") +
      `<p class="hint">Each bar compares this stock with ${whole.format(sc.universe)} others. 100 means best of all.</p>`
    : `<p class="hint">No Matrix Score yet. A stock needs about 6 months of trading and at least Rs 1 crore traded on a normal day.</p>`;
  paintWatch(d.watched);
  $("drawer-flags").innerHTML = d.alerts.length ? `<h3>Alerts for this stock</h3><ul class="list">${d.alerts.map((x) => alertItem(x, false)).join("")}</ul>` : "";
  $("drawer-source").textContent = `Source: NSE end-of-day prices, adjusted for splits and bonuses. Updated ${d.info.fetched_at.replace("T", " ").slice(0, 16)}. Not live.`;
}

async function openFund(code) {
  resetDrawer("Loading fund history...");
  const d = await api(`/api/funds/${encodeURIComponent(code)}`).catch((err) => { toast(err.message); closeDrawer(); });
  if (!d) return;
  drawerItem = `fund:${code}`;
  const f = d.info, st = d.stats, last = d.navs.at(-1);
  $("drawer-kicker").textContent = `Mutual fund | ${f.category ?? ""} | Code ${f.scheme_code}`;
  $("drawer-title").textContent = f.name;
  $("drawer-price").innerHTML = `Rs ${inr.format(last.nav)}<small class="muted">value of one unit on ${shortDate(last.date)}</small>`;

  const lines = [];
  for (const [yrs, r] of [[5, st.cagr_5y], [3, st.cagr_3y], [1, st.return_1y]]) {
    if (r == null) continue;
    const grown = yrs === 1 ? 10000 * (1 + r) : 10000 * (1 + r) ** yrs;
    lines.push(`Rs 10,000 put in <b>${yrs} year${yrs > 1 ? "s" : ""} ago</b> would be about <b>${rupees(grown)}</b> today${yrs > 1 ? `, growing about <b>${plainPct(r)} a year</b>` : ""}.`);
    break;
  }
  const c1 = st.consistency_1y;
  if (c1.windows) lines.push(`If you had stayed invested for any 1 year in its history, you would have made money <b>${Math.round(c1.positive_share * 100)} times out of 100</b>.`);
  if (st.max_drawdown_all != null) lines.push(`Its worst fall ever was <b>${plainPct(st.max_drawdown_all)}</b> from a high. Funds like this can drop that much again.`);
  $("drawer-simple").innerHTML = `<h3>In simple words</h3>${lines.map((l) => `<p>${l}</p>`).join("") || "<p>Not enough history yet to summarise.</p>"}`;

  newChart().addAreaSeries({ lineColor: "#0b8a5c", topColor: "rgba(11,138,92,.22)", bottomColor: "rgba(11,138,92,0)", lineWidth: 2 })
    .setData(d.navs.map((n) => ({ time: n.date, value: n.nav })));
  chart.timeScale().fitContent();
  $("drawer-stats").innerHTML =
    stat("1 year", fracText(st.return_1y), sign(st.return_1y)) +
    stat("3 years, per year", fracText(st.cagr_3y), sign(st.cagr_3y), "Average yearly growth over the last 3 years (CAGR).") +
    stat("5 years, per year", fracText(st.cagr_5y), sign(st.cagr_5y), "Average yearly growth over the last 5 years (CAGR).") +
    stat("How much it swings", fracText(st.volatility), "", "Called volatility. Higher means bigger ups and downs.") +
    stat("Worst fall ever", fracText(st.max_drawdown_all), "down") + stat("Fund house", esc(f.amc ?? "n/a"));
  $("drawer-source").textContent = `Sources: ${d.sources.join(", ")}. Official AMFI values come first; older history from mfapi.in is checked against them.`;
}

/* ---------------------------------------------------------------- start */
showApp().catch(() => showLogin());
