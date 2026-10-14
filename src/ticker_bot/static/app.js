const state = {
  day: "",
  items: [],
  preview: true,
  browserDemo: location.hostname.endsWith("github.io") || location.hostname === "raw.githack.com"
    || location.protocol === "file:"
    || new URLSearchParams(location.search).has("demo"),
  activeCriteria: 0,
  selectedTicker: null,
  interval: "5",
  chart: null,
  hoverIndex: null,
  notesDirty: false,
  saveTimer: null,
  backtests: [],
};

const el = Object.fromEntries(
  [
    "scanDate", "tickerSearch", "ratingFilter", "matchFilter", "trendFilter",
    "tickerChips", "scannerRows", "emptyState", "visibleCount", "feedTitle",
    "lastUpdated", "totalCount", "matchedCount", "averageRating", "summaryDate",
    "criteriaSummary", "criteriaCount", "activeRuleCount", "marketSource", "tickerSource",
    "criteriaDialog", "criteriaForm", "addTickerDialog", "addTickerForm", "manualTicker",
    "detailsDialog", "detailsTicker", "detailsMeta", "detailsPrice", "detailsChange",
    "priceChart", "chartEmpty", "legendOpen", "legendHigh", "legendLow", "legendClose",
    "legendVolume", "previousClose", "metricVolume", "metricRvol", "metricFloat",
    "metricCap", "ratingRow", "reviewNotes", "reviewSaveState", "signalSource",
    "matchBadge", "criteriaReasons", "firstSeen", "lastSeen", "mentionCount", "toast",
    "scannerView", "backtestView", "scannerActions", "backtestActions", "pageTitle",
    "pageSubtitle", "backtestDialog", "backtestForm", "backtestFormError", "backtestRows",
    "backtestEmpty", "backtestTotal", "backtestWinRate", "backtestAverageR", "backtestTotalR",
    "backtestVisibleCount", "backtestFrom", "backtestTo", "backtestTicker", "backtestOutcome",
    "backtestNavCount",
  ].map((id) => [id, document.querySelector(`#${id}`)]),
);

const numberFormatter = new Intl.NumberFormat("uk-UA", { maximumFractionDigits: 2 });
const compactFormatter = new Intl.NumberFormat("uk-UA", { notation: "compact", maximumFractionDigits: 1 });
const failedRuleLabels = {
  min_price: "ціна нижча за мінімум",
  max_price: "ціна вища за максимум",
  min_change_percent: "денна зміна замала",
  min_volume: "недостатній обсяг",
  min_relative_volume: "RVOL нижчий за мінімум",
  max_float_millions: "Float вищий за максимум",
};

function marketDate() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric", month: "2-digit", day: "2-digit", timeZone: "America/New_York",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function money(value) { return value == null ? "—" : `$${numberFormatter.format(value)}`; }
function percent(value) { return value == null ? "—" : `${value > 0 ? "+" : ""}${numberFormatter.format(value)}%`; }
function compact(value) { return value == null ? "—" : compactFormatter.format(value); }
function localTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("uk-UA", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Kyiv" }).format(new Date(value));
}
function localDateTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Kyiv" }).format(new Date(value));
}

function showToast(message, kind = "success") {
  el.toast.textContent = message;
  el.toast.style.borderColor = kind === "error" ? "rgba(240,109,97,.6)" : "";
  el.toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => el.toast.classList.remove("visible"), 2800);
}

const demoUniverse = [
  { ticker: "AAPL", price: 192.38, previous: 187.92, change: 2.37, volume: 7348200, rvol: 2.48, float: 15340, cap: 2980000 },
  { ticker: "NVDA", price: 138.21, previous: 133.57, change: 3.47, volume: 18350200, rvol: 3.12, float: 24100, cap: 3380000 },
  { ticker: "TSLA", price: 248.64, previous: 255.91, change: -2.84, volume: 9480100, rvol: 1.74, float: 2790, cap: 799000 },
  { ticker: "PLTR", price: 42.16, previous: 39.82, change: 5.88, volume: 12164000, rvol: 4.21, float: 1840, cap: 91200 },
  { ticker: "AMD", price: 167.45, previous: 164.88, change: 1.56, volume: 6470000, rvol: 2.03, float: 1610, cap: 271000 },
  { ticker: "SOFI", price: 10.82, previous: 11.09, change: -2.43, volume: 8890000, rvol: 1.39, float: 1060, cap: 11400 },
];

function readStore(key, fallback) {
  try {
    const value = localStorage.getItem(`bee-scanner:${key}`);
    return value ? JSON.parse(value) : fallback;
  } catch (_) { return fallback; }
}

function writeStore(key, value) {
  try { localStorage.setItem(`bee-scanner:${key}`, JSON.stringify(value)); } catch (_) { /* Private mode. */ }
}

function demoCriteria() {
  return readStore("criteria", {
    min_price: null, max_price: null, min_change_percent: null,
    min_volume: null, min_relative_volume: null, max_float_millions: null,
  });
}

function failedRules(market, criteria) {
  const failed = [];
  if (criteria.min_price != null && market.price < criteria.min_price) failed.push("min_price");
  if (criteria.max_price != null && market.price > criteria.max_price) failed.push("max_price");
  if (criteria.min_change_percent != null && market.change_percent < criteria.min_change_percent) failed.push("min_change_percent");
  if (criteria.min_volume != null && market.volume < criteria.min_volume) failed.push("min_volume");
  if (criteria.min_relative_volume != null && market.relative_volume < criteria.min_relative_volume) failed.push("min_relative_volume");
  if (criteria.max_float_millions != null && market.float_millions > criteria.max_float_millions) failed.push("max_float_millions");
  return failed;
}

function demoItem(source, day, criteria) {
  const reviews = readStore("reviews", {});
  const review = reviews[`${day}:${source.ticker}`] || {};
  const market = {
    price: source.price, previous_close: source.previous, change_percent: source.change,
    volume: source.volume, relative_volume: source.rvol, float_millions: source.float,
    market_cap_millions: source.cap,
  };
  const failed = failedRules(market, criteria);
  return {
    ticker: source.ticker, mentions: 1,
    first_seen_utc: `${day}T13:30:00Z`, last_seen_utc: `${day}T13:30:00Z`,
    matches: failed.length === 0, failed_rules: failed,
    rating: review.rating ?? null, notes: review.notes || "", market,
  };
}

function generatedDemoSource(ticker) {
  const seed = [...ticker].reduce((sum, letter) => sum + letter.charCodeAt(0), 0);
  const previous = 8 + (seed % 175) + (seed % 73) / 100;
  const change = ((seed % 1301) - 500) / 100;
  return {
    ticker, previous, change, price: previous * (1 + change / 100),
    volume: 400000 + seed * 9300, rvol: .7 + (seed % 390) / 100,
    float: 8 + (seed % 850), cap: 350 + seed * 17,
  };
}

function demoChart(ticker, day, interval) {
  const source = demoUniverse.find((item) => item.ticker === ticker) || generatedDemoSource(ticker);
  const seed = [...`${ticker}${day}${interval}`].reduce((sum, letter) => sum + letter.charCodeAt(0), 0);
  const candles = [];
  let close = source.previous;
  const count = interval === "1D" ? 45 : 78;
  for (let index = 0; index < count; index += 1) {
    const wave = Math.sin((index + seed) * .47) * .006 + Math.cos((index + seed) * .19) * .003;
    const drift = source.change / 100 / count;
    const open = close;
    close = Math.max(.1, open * (1 + drift + wave));
    const spread = Math.abs(Math.sin(seed + index)) * open * .004 + open * .0015;
    candles.push({
      timestamp: new Date(`${day}T13:30:00Z`).getTime() + index * 300000,
      open, high: Math.max(open, close) + spread, low: Math.min(open, close) - spread,
      close, volume: Math.round(source.volume / count * (.65 + Math.abs(Math.sin(index * .33)) * .9)),
    });
  }
  return { ticker, day, interval, candles };
}

async function demoApi(path, options = {}) {
  const url = new URL(path, location.href);
  const method = (options.method || "GET").toUpperCase();
  if (url.pathname.endsWith("/healthz")) return { market_data: "demo", bot_running: false };
  if (url.pathname.endsWith("/api/v1/scanner/criteria")) {
    if (method === "PUT") writeStore("criteria", JSON.parse(options.body));
    return demoCriteria();
  }
  if (url.pathname.endsWith("/api/v1/tickers/manual") && method === "POST") {
    const payload = JSON.parse(options.body);
    const manual = readStore("manual-tickers", {});
    manual[payload.day] = [...new Set([...(manual[payload.day] || []), payload.ticker.toUpperCase()])];
    writeStore("manual-tickers", manual);
    return { ticker: payload.ticker.toUpperCase(), day: payload.day };
  }
  if (url.pathname.includes("/api/v1/scanner/reviews/") && method === "PUT") {
    const ticker = decodeURIComponent(url.pathname.split("/").pop());
    const day = url.searchParams.get("day");
    const payload = JSON.parse(options.body);
    const reviews = readStore("reviews", {});
    reviews[`${day}:${ticker}`] = payload;
    writeStore("reviews", reviews);
    return { ticker, day, rating: payload.rating, notes: payload.notes };
  }
  if (url.pathname.includes("/api/v1/scanner/chart/")) {
    const ticker = decodeURIComponent(url.pathname.split("/").pop());
    return demoChart(ticker, url.searchParams.get("day"), url.searchParams.get("interval"));
  }
  if (url.pathname.endsWith("/api/v1/scanner")) {
    const day = url.searchParams.get("day") || marketDate();
    const criteria = demoCriteria();
    const manual = readStore("manual-tickers", {})[day] || [];
    const extra = manual
      .filter((ticker) => !demoUniverse.some((item) => item.ticker === ticker))
      .map(generatedDemoSource);
    const items = [...demoUniverse, ...extra].map((item) => demoItem(item, day, criteria));
    const active = Object.values(criteria).filter((value) => value != null).length;
    return {
      date: day, timezone: "America/New_York", data_mode: "demo", preview: true,
      active_criteria: active, total_count: items.length,
      matched_count: items.filter((item) => item.matches).length, items,
    };
  }
  throw new Error("Ця дія ще не доступна у демоверсії");
}

async function api(path, options = {}) {
  if (state.browserDemo) return demoApi(path, options);
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) {
    if ([404, 405].includes(response.status) && location.hostname.endsWith("github.io")) {
      state.browserDemo = true;
      return demoApi(path, options);
    }
    let detail = `Помилка ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      if (Array.isArray(body.detail)) detail = body.detail[0]?.msg || detail;
    } catch (_) { /* HTTP status is enough. */ }
    throw new Error(detail);
  }
  return response.json();
}

async function loadHealth() {
  try {
    const health = await api("/healthz");
    el.marketSource.textContent = health.market_data === "demo" ? "демо до Polygon" : "Polygon";
    el.tickerSource.textContent = health.bot_running ? "джерело підключено" : "демо / вручну";
  } catch (_) {
    el.marketSource.textContent = "немає зв’язку";
    el.tickerSource.textContent = "немає зв’язку";
  }
}

async function loadCriteria() {
  const criteria = await api("/api/v1/scanner/criteria");
  state.activeCriteria = Object.values(criteria).filter((value) => value != null).length;
  for (const [key, value] of Object.entries(criteria)) {
    const input = el.criteriaForm.elements.namedItem(key);
    if (input) input.value = value ?? "";
  }
  updateCriteriaLabels();
}

function updateCriteriaLabels() {
  el.criteriaCount.textContent = state.activeCriteria ? `· ${state.activeCriteria}` : "";
  el.activeRuleCount.textContent = String(state.activeCriteria);
  el.criteriaSummary.textContent = state.activeCriteria
    ? `${state.activeCriteria} правил зараз впливають на список`
    : "Критерії ще не задані";
  el.matchFilter.disabled = state.activeCriteria === 0;
  if (!state.activeCriteria) el.matchFilter.value = "all";
}

async function loadScanner({ quiet = false } = {}) {
  try {
    const params = new URLSearchParams({ day: state.day, preview_if_empty: "true" });
    const result = await api(`/api/v1/scanner?${params}`);
    state.items = result.items;
    state.preview = result.preview;
    state.activeCriteria = result.active_criteria;
    el.totalCount.textContent = String(result.total_count);
    el.matchedCount.textContent = state.activeCriteria ? String(result.matched_count) : "—";
    el.summaryDate.textContent = result.date;
    el.feedTitle.textContent = `${state.preview ? "Демонстраційний список" : "Потік сигналів"} · ${result.total_count} тікерів`;
    el.tickerSource.textContent = state.preview ? "демо / вручну" : "локальна база";
    el.lastUpdated.textContent = `оновлено ${new Intl.DateTimeFormat("uk-UA", { hour: "2-digit", minute: "2-digit" }).format(new Date())}`;
    const ratings = result.items.map((item) => item.rating).filter((rating) => rating != null);
    el.averageRating.textContent = ratings.length
      ? `${numberFormatter.format(ratings.reduce((sum, rating) => sum + rating, 0) / ratings.length)} / 5`
      : "—";
    updateCriteriaLabels();
    renderTickerChips();
    renderTable();
  } catch (error) {
    if (!quiet) showToast(error.message, "error");
  }
}

function visibleItems() {
  const query = el.tickerSearch.value.trim().toUpperCase();
  const minRating = Number(el.ratingFilter.value);
  return state.items.filter((item) => {
    if (query && !item.ticker.includes(query)) return false;
    if ((item.rating || 0) < minRating) return false;
    if (state.activeCriteria && el.matchFilter.value === "matched" && !item.matches) return false;
    if (state.activeCriteria && el.matchFilter.value === "failed" && item.matches) return false;
    if (el.trendFilter.value === "up" && item.market.change_percent < 0) return false;
    if (el.trendFilter.value === "down" && item.market.change_percent >= 0) return false;
    return true;
  });
}

function renderTickerChips() {
  el.tickerChips.replaceChildren();
  for (const item of state.items) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `ticker-chip ${item.market.change_percent >= 0 ? "positive" : "negative"}`;
    const symbol = document.createElement("b");
    symbol.textContent = item.ticker;
    const floatValue = document.createElement("span");
    floatValue.textContent = `${numberFormatter.format(item.market.float_millions)}M`;
    const move = document.createElement("em");
    move.textContent = percent(item.market.change_percent);
    button.append(symbol, floatValue, move);
    button.addEventListener("click", () => openDetails(item.ticker));
    el.tickerChips.append(button);
  }
}

function cell(className, ...children) {
  const td = document.createElement("td");
  if (className) td.className = className;
  td.append(...children);
  return td;
}

function textNode(tag, value, className = "") {
  const node = document.createElement(tag);
  node.textContent = value;
  if (className) node.className = className;
  return node;
}

function renderTable() {
  const items = visibleItems();
  el.scannerRows.replaceChildren();
  el.visibleCount.textContent = `${items.length} / ${state.items.length}`;
  el.emptyState.hidden = items.length > 0;

  for (const item of items) {
    const row = document.createElement("tr");
    row.addEventListener("click", () => openDetails(item.ticker));

    const tickerWrap = textNode("div", "", "ticker-cell");
    tickerWrap.append(textNode("b", item.ticker), textNode("small", "US EQUITY"));

    const rating = textNode("span", item.rating ? `${item.rating}.0` : "—", `rating-pill ${item.rating ? "rated" : ""}`);
    const source = textNode("span", state.preview ? "Демо" : localTime(item.first_seen_utc), "source-pill");
    const priceWrap = textNode("div", "", "price-cell");
    priceWrap.append(textNode("b", money(item.market.price)), textNode("small", `закр. ${money(item.market.previous_close)}`));
    const statusClass = !state.activeCriteria ? "neutral" : item.matches ? "pass" : "fail";
    const statusText = !state.activeCriteria ? "Без правил" : item.matches ? "Підходить" : "Не підходить";
    const status = textNode("span", statusText, `match-pill ${statusClass}`);
    const move = textNode("b", percent(item.market.change_percent), item.market.change_percent >= 0 ? "positive-text" : "negative-text");
    const open = textNode("button", "↗", "open-row");
    open.type = "button";
    open.title = "Відкрити графік і нотатку";

    row.append(
      cell("", tickerWrap), cell("", rating), cell("", source), cell("", priceWrap), cell("", move),
      cell("", document.createTextNode(`${numberFormatter.format(item.market.relative_volume)}×`)),
      cell("", document.createTextNode(`${numberFormatter.format(item.market.float_millions)}M`)),
      cell("", status), cell("", open),
    );
    el.scannerRows.append(row);
  }
}

async function openDetails(ticker) {
  state.selectedTicker = ticker;
  const item = state.items.find((candidate) => candidate.ticker === ticker);
  if (!item) return;
  renderDetails(item);
  if (!el.detailsDialog.open) el.detailsDialog.showModal();
  await loadChart();
}

function renderDetails(item) {
  el.detailsTicker.textContent = item.ticker;
  el.detailsMeta.textContent = state.preview ? "приклад інтерфейсу" : `сигнал · ${localDateTime(item.first_seen_utc)}`;
  el.detailsPrice.textContent = money(item.market.price);
  el.detailsChange.textContent = percent(item.market.change_percent);
  el.detailsChange.className = item.market.change_percent >= 0 ? "positive-text" : "negative-text";
  el.previousClose.textContent = money(item.market.previous_close);
  el.metricVolume.textContent = compact(item.market.volume);
  el.metricRvol.textContent = `${numberFormatter.format(item.market.relative_volume)}×`;
  el.metricFloat.textContent = `${numberFormatter.format(item.market.float_millions)} млн`;
  el.metricCap.textContent = `$${compact(item.market.market_cap_millions * 1_000_000)}`;
  el.reviewNotes.value = item.notes || "";
  el.reviewSaveState.textContent = item.rating || item.notes ? "збережено" : "—";
  state.notesDirty = false;
  renderRating(item.rating);
  el.signalSource.textContent = state.preview ? "демо-приклад" : "отримано зі джерела";
  el.firstSeen.textContent = state.preview ? "—" : localDateTime(item.first_seen_utc);
  el.lastSeen.textContent = state.preview ? "—" : localDateTime(item.last_seen_utc);
  el.mentionCount.textContent = state.preview ? "—" : String(item.mentions);
  if (!state.activeCriteria) {
    el.matchBadge.textContent = "Без правил";
    el.matchBadge.className = "match-badge";
    el.criteriaReasons.textContent = "Додайте власні критерії відбору.";
  } else if (item.matches) {
    el.matchBadge.textContent = "Підходить";
    el.matchBadge.className = "match-badge pass";
    el.criteriaReasons.textContent = "Акція пройшла всі активні критерії.";
  } else {
    el.matchBadge.textContent = "Не підходить";
    el.matchBadge.className = "match-badge fail";
    el.criteriaReasons.textContent = item.failed_rules.map((rule) => failedRuleLabels[rule] || rule).join(" · ");
  }
}

function renderRating(selected) {
  for (const button of el.ratingRow.querySelectorAll("button")) {
    button.classList.toggle("active", Number(button.dataset.rating) === selected);
  }
}

function currentItem() { return state.items.find((item) => item.ticker === state.selectedTicker); }

async function saveReview(rating = currentItem()?.rating ?? null, notify = true) {
  const item = currentItem();
  if (!item) return;
  window.clearTimeout(state.saveTimer);
  try {
    el.reviewSaveState.textContent = "зберігаю…";
    const review = await api(`/api/v1/scanner/reviews/${encodeURIComponent(item.ticker)}?day=${state.day}`, {
      method: "PUT", body: JSON.stringify({ rating, notes: el.reviewNotes.value.trim() }),
    });
    item.rating = review.rating;
    item.notes = review.notes;
    state.notesDirty = false;
    el.reviewSaveState.textContent = "збережено";
    renderRating(review.rating);
    renderTable();
    if (notify) showToast("Оцінку й нотатку збережено");
  } catch (error) {
    el.reviewSaveState.textContent = "помилка";
    showToast(error.message, "error");
  }
}

async function saveCriteria() {
  const payload = {};
  for (const key of ["min_price", "max_price", "min_change_percent", "min_volume", "min_relative_volume", "max_float_millions"]) {
    const raw = el.criteriaForm.elements.namedItem(key).value.trim();
    payload[key] = raw === "" ? null : Number(raw);
  }
  try {
    const result = await api("/api/v1/scanner/criteria", { method: "PUT", body: JSON.stringify(payload) });
    state.activeCriteria = Object.values(result).filter((value) => value != null).length;
    el.criteriaDialog.close();
    await loadScanner();
    showToast("Критерії застосовано");
  } catch (error) { showToast(error.message, "error"); }
}

async function addManualTicker() {
  const ticker = el.manualTicker.value.trim().toUpperCase();
  if (!ticker) return;
  try {
    await api("/api/v1/tickers/manual", { method: "POST", body: JSON.stringify({ ticker, day: state.day }) });
    el.addTickerDialog.close();
    el.manualTicker.value = "";
    await loadScanner();
    showToast(`${ticker} додано до сканера`);
  } catch (error) { showToast(error.message, "error"); }
}

async function loadChart() {
  if (!state.selectedTicker) return;
  try {
    state.chart = await api(`/api/v1/scanner/chart/${encodeURIComponent(state.selectedTicker)}?day=${state.day}&interval=${state.interval}`);
    state.hoverIndex = null;
    drawChart();
  } catch (error) { showToast(error.message, "error"); }
}

function chartDimensions(canvas) {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(320, rect.width);
  const height = Math.max(360, rect.height);
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { context, width, height };
}

function candlesWithVwap(candles) {
  let priceVolume = 0;
  let volume = 0;
  return candles.map((candle) => {
    priceVolume += ((candle.high + candle.low + candle.close) / 3) * candle.volume;
    volume += candle.volume;
    return { ...candle, vwap: priceVolume / volume };
  });
}

function drawChart() {
  const { context: ctx, width, height } = chartDimensions(el.priceChart);
  ctx.clearRect(0, 0, width, height);
  const candles = candlesWithVwap(state.chart?.candles || []);
  el.chartEmpty.hidden = candles.length > 0;
  if (!candles.length) return;
  const margin = { top: 18, right: 64, bottom: 31, left: 12 };
  const volumeHeight = height * .18;
  const priceBottom = height - margin.bottom - volumeHeight - 12;
  const plotWidth = width - margin.left - margin.right;
  const priceHeight = priceBottom - margin.top;
  const low = Math.min(...candles.map((c) => c.low));
  const high = Math.max(...candles.map((c) => c.high));
  const pad = Math.max((high - low) * .08, high * .002);
  const lower = low - pad;
  const upper = high + pad;
  const range = Math.max(upper - lower, .01);
  const maxVolume = Math.max(...candles.map((c) => c.volume), 1);
  const slot = plotWidth / candles.length;
  const candleWidth = Math.max(1, Math.min(8, slot * .62));
  const xAt = (index) => margin.left + slot * index + slot / 2;
  const yAt = (price) => margin.top + ((upper - price) / range) * priceHeight;

  ctx.font = "10px ui-monospace, monospace";
  ctx.strokeStyle = "rgba(115,130,136,.18)";
  ctx.fillStyle = "#77817c";
  for (let line = 0; line <= 4; line += 1) {
    const y = margin.top + (priceHeight / 4) * line;
    ctx.beginPath(); ctx.moveTo(margin.left, y); ctx.lineTo(width - margin.right, y); ctx.stroke();
    ctx.fillText(money(upper - (range / 4) * line), width - margin.right + 7, y + 4);
  }
  candles.forEach((candle, index) => {
    const x = xAt(index);
    const color = candle.close >= candle.open ? "#f0c84b" : "#f06d61";
    ctx.strokeStyle = color; ctx.fillStyle = color;
    ctx.beginPath(); ctx.moveTo(x, yAt(candle.high)); ctx.lineTo(x, yAt(candle.low)); ctx.stroke();
    const top = Math.min(yAt(candle.open), yAt(candle.close));
    ctx.fillRect(x - candleWidth / 2, top, candleWidth, Math.max(1, Math.abs(yAt(candle.close) - yAt(candle.open))));
    const volumeTop = height - margin.bottom - (candle.volume / maxVolume) * volumeHeight;
    ctx.globalAlpha = .3; ctx.fillRect(x - candleWidth / 2, volumeTop, candleWidth, height - margin.bottom - volumeTop); ctx.globalAlpha = 1;
  });
  ctx.strokeStyle = "#c99b25"; ctx.lineWidth = 1.4; ctx.beginPath();
  candles.forEach((candle, index) => index ? ctx.lineTo(xAt(index), yAt(candle.vwap)) : ctx.moveTo(xAt(index), yAt(candle.vwap))); ctx.stroke();
  updateLegend(candles[state.hoverIndex ?? candles.length - 1]);
}

function updateLegend(candle) {
  if (!candle) return;
  el.legendOpen.textContent = money(candle.open); el.legendHigh.textContent = money(candle.high);
  el.legendLow.textContent = money(candle.low); el.legendClose.textContent = money(candle.close);
  el.legendVolume.textContent = compact(candle.volume);
}

function switchView(view) {
  const backtest = view === "backtest";
  el.scannerView.hidden = backtest;
  el.backtestView.hidden = !backtest;
  el.scannerActions.hidden = backtest;
  el.backtestActions.hidden = !backtest;
  el.pageTitle.textContent = backtest ? "Лабораторія бектесту" : "Огляд тікерів";
  el.pageSubtitle.textContent = backtest
    ? "Перевірка минулих сетапів і статистика результатів"
    : "Швидкий відбір і розбір акцій за торговий день";
  for (const button of document.querySelectorAll(".nav-item[data-view]")) {
    button.classList.toggle("active", button.dataset.view === view);
  }
  if (backtest) renderBacktests();
}

function loadBacktests() {
  state.backtests = readStore("backtests", []);
  el.backtestNavCount.textContent = String(state.backtests.length);
}

function filteredBacktests() {
  const from = el.backtestFrom.value;
  const to = el.backtestTo.value;
  const ticker = el.backtestTicker.value.trim().toUpperCase();
  return state.backtests
    .filter((item) => !from || item.day >= from)
    .filter((item) => !to || item.day <= to)
    .filter((item) => !ticker || item.ticker.includes(ticker))
    .filter((item) => el.backtestOutcome.value === "all"
      || (el.backtestOutcome.value === "win" ? item.resultR > 0 : item.resultR <= 0))
    .sort((left, right) => right.day.localeCompare(left.day));
}

function formatR(value) {
  if (value == null || !Number.isFinite(value)) return "— R";
  return `${value > 0 ? "+" : ""}${numberFormatter.format(value)} R`;
}

function renderBacktests() {
  const items = filteredBacktests();
  const wins = items.filter((item) => item.resultR > 0).length;
  const totalR = items.reduce((sum, item) => sum + item.resultR, 0);
  el.backtestRows.replaceChildren();
  el.backtestVisibleCount.textContent = `${items.length} / ${state.backtests.length}`;
  el.backtestEmpty.hidden = items.length > 0;
  el.backtestTotal.textContent = String(items.length);
  el.backtestWinRate.textContent = items.length ? `${Math.round((wins / items.length) * 100)}%` : "—";
  el.backtestAverageR.textContent = items.length ? formatR(totalR / items.length) : "— R";
  el.backtestTotalR.textContent = items.length ? formatR(totalR) : "— R";
  el.backtestTotalR.className = totalR < 0 ? "negative-text" : "accent";

  for (const item of items) {
    const row = document.createElement("tr");
    const result = textNode("b", formatR(item.resultR), item.resultR > 0 ? "positive-text" : "negative-text");
    const side = textNode("span", item.side === "short" ? "SHORT" : "LONG", `side-pill ${item.side}`);
    const note = textNode("div", item.note || "—", "backtest-note");
    note.title = item.note || "";
    const remove = textNode("button", "×", "delete-row");
    remove.type = "button";
    remove.title = "Видалити запис";
    remove.addEventListener("click", (event) => {
      event.stopPropagation();
      state.backtests = state.backtests.filter((candidate) => candidate.id !== item.id);
      writeStore("backtests", state.backtests);
      el.backtestNavCount.textContent = String(state.backtests.length);
      renderBacktests();
      showToast("Запис видалено");
    });
    row.append(
      cell("", document.createTextNode(item.day)), cell("", textNode("b", item.ticker)),
      cell("", side), cell("", document.createTextNode(money(item.entry))),
      cell("", document.createTextNode(money(item.stop))), cell("", document.createTextNode(money(item.exit))),
      cell("", result), cell("", note), cell("", remove),
    );
    el.backtestRows.append(row);
  }
}

function openBacktestForm() {
  el.backtestForm.reset();
  el.backtestForm.elements.namedItem("day").value = state.day;
  el.backtestFormError.textContent = "";
  el.backtestDialog.showModal();
}

function saveBacktest() {
  const form = el.backtestForm;
  const day = form.elements.namedItem("day").value;
  const ticker = form.elements.namedItem("ticker").value.trim().toUpperCase();
  const side = form.elements.namedItem("side").value;
  const entry = Number(form.elements.namedItem("entry").value);
  const stop = Number(form.elements.namedItem("stop").value);
  const exitPrice = Number(form.elements.namedItem("exit").value);
  if (!day || !/^[A-Z][A-Z0-9.-]{0,8}$/.test(ticker) || !entry || !stop || !exitPrice) {
    el.backtestFormError.textContent = "Заповни дату, правильний тікер і всі три ціни.";
    return;
  }
  const risk = side === "long" ? entry - stop : stop - entry;
  if (risk <= 0) {
    el.backtestFormError.textContent = side === "long"
      ? "Для Long стоп має бути нижче входу."
      : "Для Short стоп має бути вище входу.";
    return;
  }
  const reward = side === "long" ? exitPrice - entry : entry - exitPrice;
  state.backtests.push({
    id: `${Date.now()}-${ticker}`, day, ticker, side, entry, stop, exit: exitPrice,
    resultR: Math.round((reward / risk) * 100) / 100,
    note: form.elements.namedItem("note").value.trim(),
  });
  writeStore("backtests", state.backtests);
  el.backtestNavCount.textContent = String(state.backtests.length);
  el.backtestDialog.close();
  renderBacktests();
  showToast(`${ticker}: результат тесту збережено`);
}

function bindEvents() {
  for (const input of [el.tickerSearch, el.ratingFilter, el.matchFilter, el.trendFilter]) input.addEventListener("input", renderTable);
  el.scanDate.addEventListener("change", async () => { state.day = el.scanDate.value; await loadScanner(); });
  document.querySelector("#analyzeButton").addEventListener("click", async () => { await loadScanner(); showToast("День проаналізовано"); });
  document.querySelector("#criteriaButton").addEventListener("click", () => el.criteriaDialog.showModal());
  document.querySelector("#criteriaNav").addEventListener("click", () => el.criteriaDialog.showModal());
  document.querySelector("#clearCriteria").addEventListener("click", () => { for (const input of el.criteriaForm.querySelectorAll("input")) input.value = ""; });
  document.querySelector("#saveCriteria").addEventListener("click", saveCriteria);
  document.querySelector("#addTickerButton").addEventListener("click", () => el.addTickerDialog.showModal());
  document.querySelector("#addTickerSubmit").addEventListener("click", addManualTicker);
  el.manualTicker.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); addManualTicker(); } });
  document.querySelector("#closeDetails").addEventListener("click", () => el.detailsDialog.close());
  document.querySelector("[data-view='scanner']").addEventListener("click", () => switchView("scanner"));
  document.querySelector("[data-view='backtest']").addEventListener("click", () => switchView("backtest"));
  document.querySelector("#addBacktestButton").addEventListener("click", openBacktestForm);
  document.querySelector("#saveBacktest").addEventListener("click", saveBacktest);
  for (const input of [el.backtestFrom, el.backtestTo, el.backtestTicker, el.backtestOutcome]) input.addEventListener("input", renderBacktests);
  document.querySelector("#resetBacktestFilters").addEventListener("click", () => {
    el.backtestFrom.value = ""; el.backtestTo.value = ""; el.backtestTicker.value = ""; el.backtestOutcome.value = "all"; renderBacktests();
  });
  document.querySelector("#saveReview").addEventListener("click", () => saveReview());
  el.reviewNotes.addEventListener("input", () => {
    state.notesDirty = true; el.reviewSaveState.textContent = "не збережено";
    window.clearTimeout(state.saveTimer); state.saveTimer = window.setTimeout(() => saveReview(currentItem()?.rating ?? null, false), 1200);
  });
  for (const button of el.ratingRow.querySelectorAll("button")) button.addEventListener("click", () => saveReview(Number(button.dataset.rating), false));
  for (const button of document.querySelectorAll("[data-interval]")) button.addEventListener("click", async () => {
    for (const candidate of document.querySelectorAll("[data-interval]")) candidate.classList.remove("active");
    button.classList.add("active"); state.interval = button.dataset.interval; await loadChart();
  });
  el.priceChart.addEventListener("mousemove", (event) => {
    const candles = state.chart?.candles || []; if (!candles.length) return;
    const rect = el.priceChart.getBoundingClientRect();
    state.hoverIndex = Math.max(0, Math.min(candles.length - 1, Math.floor(((event.clientX - rect.left - 12) / Math.max(rect.width - 76, 1)) * candles.length)));
    updateLegend(candlesWithVwap(candles)[state.hoverIndex]);
  });
  window.addEventListener("resize", () => { if (el.detailsDialog.open) drawChart(); });
}

async function start() {
  state.day = marketDate();
  el.scanDate.value = state.day;
  el.scanDate.max = state.day;
  loadBacktests();
  bindEvents();
  await loadHealth();
  try { await loadCriteria(); await loadScanner(); } catch (error) { showToast(error.message, "error"); }
  window.setInterval(() => loadScanner({ quiet: true }), 15000);
}

start();
