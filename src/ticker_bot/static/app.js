const state = {
  day: "",
  items: [],
  selectedTicker: null,
  interval: "5",
  activeCriteria: 0,
  chart: null,
  hoverIndex: null,
  preview: false,
};

const el = {
  botStatus: document.querySelector("#botStatus"),
  day: document.querySelector("#scanDate"),
  search: document.querySelector("#tickerSearch"),
  onlyMatches: document.querySelector("#onlyMatches"),
  tickerList: document.querySelector("#tickerList"),
  totalCount: document.querySelector("#totalCount"),
  matchedCount: document.querySelector("#matchedCount"),
  lastUpdated: document.querySelector("#lastUpdated"),
  selectedTicker: document.querySelector("#selectedTicker"),
  selectionMeta: document.querySelector("#selectionMeta"),
  price: document.querySelector("#selectedPrice"),
  change: document.querySelector("#selectedChange"),
  chart: document.querySelector("#priceChart"),
  chartEmpty: document.querySelector("#chartEmpty"),
  demoNotice: document.querySelector("#demoNotice"),
  legendOpen: document.querySelector("#legendOpen"),
  legendHigh: document.querySelector("#legendHigh"),
  legendLow: document.querySelector("#legendLow"),
  legendClose: document.querySelector("#legendClose"),
  legendVolume: document.querySelector("#legendVolume"),
  previousClose: document.querySelector("#previousClose"),
  metricVolume: document.querySelector("#metricVolume"),
  metricRvol: document.querySelector("#metricRvol"),
  metricFloat: document.querySelector("#metricFloat"),
  metricCap: document.querySelector("#metricCap"),
  rating: document.querySelector("#ratingRow"),
  notes: document.querySelector("#reviewNotes"),
  saveReview: document.querySelector("#saveReview"),
  reviewSaveState: document.querySelector("#reviewSaveState"),
  signalSource: document.querySelector("#signalSource"),
  matchBadge: document.querySelector("#matchBadge"),
  firstSeen: document.querySelector("#firstSeen"),
  lastSeen: document.querySelector("#lastSeen"),
  mentionCount: document.querySelector("#mentionCount"),
  criteriaDialog: document.querySelector("#criteriaDialog"),
  criteriaForm: document.querySelector("#criteriaForm"),
  toast: document.querySelector("#toast"),
};

const numberFormatter = new Intl.NumberFormat("uk-UA", { maximumFractionDigits: 2 });
const compactFormatter = new Intl.NumberFormat("uk-UA", {
  notation: "compact",
  maximumFractionDigits: 1,
});

function localDate() {
  const now = new Date();
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: "Europe/Kyiv",
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function money(value) {
  return value == null ? "—" : `$${numberFormatter.format(value)}`;
}

function percent(value) {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${numberFormatter.format(value)}%`;
}

function compact(value) {
  return value == null ? "—" : compactFormatter.format(value);
}

function dateTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("uk-UA", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Kyiv",
  }).format(new Date(value));
}

function showToast(message, kind = "success") {
  el.toast.textContent = message;
  el.toast.style.borderColor = kind === "error" ? "rgba(240, 91, 97, 0.55)" : "";
  el.toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => el.toast.classList.remove("visible"), 2600);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) {
    let detail = `Помилка ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch (_) {
      // The HTTP status is enough when a response has no JSON body.
    }
    throw new Error(detail);
  }
  return response.json();
}

async function loadHealth() {
  try {
    const result = await api("/healthz");
    el.botStatus.lastChild.textContent = result.bot_running ? "Бот підключений" : "Сканер працює";
    el.botStatus.classList.add("online");
    el.botStatus.classList.remove("offline");
  } catch (_) {
    el.botStatus.lastChild.textContent = "Немає зв’язку";
    el.botStatus.classList.add("offline");
    el.botStatus.classList.remove("online");
  }
}

async function loadCriteria() {
  const criteria = await api("/api/v1/scanner/criteria");
  state.activeCriteria = Object.values(criteria).filter((value) => value != null).length;
  for (const [key, value] of Object.entries(criteria)) {
    const input = el.criteriaForm.elements.namedItem(key);
    if (input) input.value = value ?? "";
  }
}

async function loadScanner({ quiet = false } = {}) {
  try {
    const previousSelection = state.selectedTicker;
    const params = new URLSearchParams({ day: state.day, preview_if_empty: "true" });
    const result = await api(`/api/v1/scanner?${params}`);
    state.items = result.items;
    state.preview = result.preview;
    state.activeCriteria = result.active_criteria;
    el.totalCount.textContent = String(result.total_count);
    el.matchedCount.textContent = String(result.matched_count);
    el.lastUpdated.textContent = new Intl.DateTimeFormat("uk-UA", {
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date());

    if (!state.selectedTicker || !result.items.some((item) => item.ticker === state.selectedTicker)) {
      state.selectedTicker = result.items[0]?.ticker || null;
    }
    renderList();
    renderDemoNotice();
    if (state.selectedTicker) {
      if (!quiet || state.selectedTicker !== previousSelection) {
        await selectTicker(state.selectedTicker, { keepList: true });
      }
    } else {
      clearDetails();
    }
  } catch (error) {
    if (!quiet) showToast(error.message, "error");
  }
}

function visibleItems() {
  const query = el.search.value.trim().toUpperCase();
  return state.items.filter(
    (item) =>
      (!query || item.ticker.includes(query)) && (!el.onlyMatches.checked || item.matches),
  );
}

function renderList() {
  el.tickerList.replaceChildren();
  const items = visibleItems();
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty-list";
    empty.textContent = state.items.length
      ? "За цим пошуком акцій немає."
      : "Додайте бота в Telegram-чат і надішліть тікер, наприклад $AAPL.";
    el.tickerList.append(empty);
    return;
  }

  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ticker-row";
    button.classList.toggle("active", item.ticker === state.selectedTicker);
    button.addEventListener("click", () => selectTicker(item.ticker));

    const main = document.createElement("span");
    main.className = "ticker-main";
    const dot = document.createElement("i");
    dot.className = `match-dot ${state.activeCriteria ? (item.matches ? "match" : "fail") : ""}`;
    const ticker = document.createElement("span");
    ticker.className = "ticker-symbol";
    ticker.textContent = item.ticker;
    main.append(dot, ticker);

    const price = document.createElement("span");
    price.className = "ticker-price";
    price.textContent = money(item.market.price);

    const meta = document.createElement("span");
    meta.className = "ticker-meta";
    meta.textContent = state.preview
      ? "приклад"
      : `${item.mentions} ${item.mentions === 1 ? "згадка" : "згадки"} · ${dateTime(item.first_seen_utc)}`;

    const rating = document.createElement("span");
    rating.className = "ticker-rating";
    rating.classList.add(item.market.change_percent >= 0 ? "positive" : "negative");
    rating.textContent = `${percent(item.market.change_percent)}${item.rating ? ` · ${item.rating}/5` : ""}`;
    button.append(main, price, meta, rating);
    el.tickerList.append(button);
  }
}

function renderDemoNotice() {
  el.demoNotice.replaceChildren();
  const strong = document.createElement("strong");
  strong.textContent = "Демонстраційні ринкові дані";
  const description = document.createElement("span");
  description.textContent = state.preview
    ? "Показані приклади. Реальні тікери з’являться після повідомлень у Telegram."
    : "Тікери реальні з Telegram; ціни й обсяги замінить Polygon.";
  el.demoNotice.append(strong, description);
}

async function selectTicker(ticker, { keepList = false } = {}) {
  state.selectedTicker = ticker;
  if (!keepList) renderList();
  const item = state.items.find((candidate) => candidate.ticker === ticker);
  if (!item) return;
  renderDetails(item);
  try {
    state.chart = await api(
      `/api/v1/scanner/chart/${encodeURIComponent(ticker)}?day=${state.day}&interval=${state.interval}`,
    );
    state.hoverIndex = null;
    drawChart();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function renderDetails(item) {
  el.selectedTicker.textContent = item.ticker;
  el.selectionMeta.textContent = state.preview
    ? "Приклад для перегляду інтерфейсу"
    : `Сигнал із Telegram · ${dateTime(item.first_seen_utc)}`;
  el.price.textContent = money(item.market.price);
  el.change.textContent = percent(item.market.change_percent);
  el.change.className = item.market.change_percent >= 0 ? "positive" : "negative";
  el.previousClose.textContent = money(item.market.previous_close);
  el.metricVolume.textContent = compact(item.market.volume);
  el.metricRvol.textContent = `${numberFormatter.format(item.market.relative_volume)}×`;
  el.metricFloat.textContent = `${numberFormatter.format(item.market.float_millions)} млн`;
  el.metricCap.textContent = `$${compact(item.market.market_cap_millions * 1_000_000)}`;
  el.notes.value = item.notes || "";
  el.reviewSaveState.textContent = item.rating || item.notes ? "збережено" : "—";
  renderRating(item.rating);

  el.signalSource.textContent = state.preview ? "демо-приклад" : "отримано ботом";
  el.firstSeen.textContent = state.preview ? "—" : dateTime(item.first_seen_utc);
  el.lastSeen.textContent = state.preview ? "—" : dateTime(item.last_seen_utc);
  el.mentionCount.textContent = state.preview ? "—" : String(item.mentions);
  if (!state.activeCriteria) {
    el.matchBadge.textContent = "Без критеріїв";
    el.matchBadge.className = "match-badge neutral";
  } else {
    el.matchBadge.textContent = item.matches ? "Підходить" : "Не підходить";
    el.matchBadge.className = `match-badge ${item.matches ? "match" : "fail"}`;
    el.matchBadge.title = item.failed_rules.length
      ? `Не пройдено: ${item.failed_rules.join(", ")}`
      : "Усі умови виконано";
  }
}

function renderRating(selected) {
  for (const button of el.rating.querySelectorAll("button")) {
    button.classList.toggle("active", Number(button.dataset.rating) === selected);
  }
}

async function saveReview(rating = currentRating(), notify = true) {
  if (!state.selectedTicker) return;
  try {
    el.reviewSaveState.textContent = "зберігаю…";
    const review = await api(
      `/api/v1/scanner/reviews/${encodeURIComponent(state.selectedTicker)}?day=${state.day}`,
      {
        method: "PUT",
        body: JSON.stringify({ rating, notes: el.notes.value.trim() }),
      },
    );
    const item = state.items.find((candidate) => candidate.ticker === state.selectedTicker);
    if (item) {
      item.rating = review.rating;
      item.notes = review.notes;
    }
    el.reviewSaveState.textContent = "збережено";
    renderRating(review.rating);
    renderList();
    if (notify) showToast("Оцінку й нотатку збережено");
  } catch (error) {
    el.reviewSaveState.textContent = "помилка";
    showToast(error.message, "error");
  }
}

function currentRating() {
  return state.items.find((item) => item.ticker === state.selectedTicker)?.rating ?? null;
}

function clearDetails() {
  el.selectedTicker.textContent = "—";
  el.selectionMeta.textContent = "Оберіть тікер";
  el.price.textContent = "—";
  el.change.textContent = "—";
  for (const metric of [el.previousClose, el.metricVolume, el.metricRvol, el.metricFloat, el.metricCap]) {
    metric.textContent = "—";
  }
  el.notes.value = "";
  renderRating(null);
  state.chart = null;
  drawChart();
}

async function saveCriteria() {
  const payload = {};
  for (const key of [
    "min_price",
    "max_price",
    "min_change_percent",
    "min_volume",
    "min_relative_volume",
    "max_float_millions",
  ]) {
    const raw = el.criteriaForm.elements.namedItem(key).value.trim();
    payload[key] = raw === "" ? null : Number(raw);
  }
  try {
    const result = await api("/api/v1/scanner/criteria", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    state.activeCriteria = Object.values(result).filter((value) => value != null).length;
    el.criteriaDialog.close();
    await loadScanner();
    showToast("Критерії збережено");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function chartDimensions(canvas) {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(300, rect.width);
  const height = Math.max(260, rect.height);
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { context, width, height };
}

function candlesWithVwap(candles) {
  let cumulativePriceVolume = 0;
  let cumulativeVolume = 0;
  return candles.map((candle) => {
    cumulativePriceVolume += ((candle.high + candle.low + candle.close) / 3) * candle.volume;
    cumulativeVolume += candle.volume;
    return { ...candle, vwap: cumulativePriceVolume / cumulativeVolume };
  });
}

function drawChart() {
  const { context: ctx, width, height } = chartDimensions(el.chart);
  ctx.clearRect(0, 0, width, height);
  const candles = candlesWithVwap(state.chart?.candles || []);
  el.chartEmpty.classList.toggle("hidden", candles.length > 0);
  if (!candles.length) return;

  const margin = { top: 22, right: 66, bottom: 36, left: 12 };
  const volumeHeight = Math.round(height * 0.18);
  const priceBottom = height - margin.bottom - volumeHeight - 14;
  const plotWidth = width - margin.left - margin.right;
  const priceHeight = priceBottom - margin.top;
  const minPrice = Math.min(...candles.map((candle) => candle.low));
  const maxPrice = Math.max(...candles.map((candle) => candle.high));
  const pricePad = Math.max((maxPrice - minPrice) * 0.08, maxPrice * 0.002);
  const lower = minPrice - pricePad;
  const upper = maxPrice + pricePad;
  const range = Math.max(upper - lower, 0.01);
  const maxVolume = Math.max(...candles.map((candle) => candle.volume), 1);
  const slot = plotWidth / candles.length;
  const candleWidth = Math.max(1, Math.min(9, slot * 0.62));
  const xAt = (index) => margin.left + slot * index + slot / 2;
  const yAt = (price) => margin.top + ((upper - price) / range) * priceHeight;

  ctx.font = "11px Inter, system-ui, sans-serif";
  ctx.lineWidth = 1;
  ctx.strokeStyle = "rgba(143, 159, 151, 0.14)";
  ctx.fillStyle = "#819087";
  ctx.textAlign = "left";
  for (let line = 0; line <= 4; line += 1) {
    const y = margin.top + (priceHeight / 4) * line;
    ctx.beginPath();
    ctx.moveTo(margin.left, y);
    ctx.lineTo(width - margin.right, y);
    ctx.stroke();
    ctx.fillText(money(upper - (range / 4) * line), width - margin.right + 8, y + 4);
  }

  candles.forEach((candle, index) => {
    const x = xAt(index);
    const color = candle.close >= candle.open ? "#e7b94e" : "#df6a5e";
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(x, yAt(candle.high));
    ctx.lineTo(x, yAt(candle.low));
    ctx.stroke();
    const bodyTop = Math.min(yAt(candle.open), yAt(candle.close));
    const bodyHeight = Math.max(1, Math.abs(yAt(candle.close) - yAt(candle.open)));
    ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
    const volumeTop = height - margin.bottom - (candle.volume / maxVolume) * volumeHeight;
    ctx.globalAlpha = 0.35;
    ctx.fillRect(x - candleWidth / 2, volumeTop, candleWidth, height - margin.bottom - volumeTop);
    ctx.globalAlpha = 1;
  });

  ctx.strokeStyle = "#c89436";
  ctx.lineWidth = 1.4;
  ctx.beginPath();
  candles.forEach((candle, index) => {
    const x = xAt(index);
    const y = yAt(candle.vwap);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  ctx.fillStyle = "#819087";
  ctx.textAlign = "center";
  for (let label = 0; label < 5; label += 1) {
    const index = Math.round((candles.length - 1) * (label / 4));
    const timestamp = new Date(candles[index].timestamp_utc);
    const text = state.interval === "1D"
      ? new Intl.DateTimeFormat("uk-UA", { day: "2-digit", month: "2-digit" }).format(timestamp)
      : new Intl.DateTimeFormat("uk-UA", {
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "America/New_York",
        }).format(timestamp);
    ctx.fillText(text, xAt(index), height - 12);
  }

  const item = state.items.find((candidate) => candidate.ticker === state.selectedTicker);
  if (item?.first_seen_utc && !state.preview && state.interval !== "1D") {
    const signalTime = new Date(item.first_seen_utc).getTime();
    let closest = 0;
    candles.forEach((candle, index) => {
      const currentDistance = Math.abs(new Date(candle.timestamp_utc).getTime() - signalTime);
      const closestDistance = Math.abs(new Date(candles[closest].timestamp_utc).getTime() - signalTime);
      if (currentDistance < closestDistance) closest = index;
    });
    const markerX = xAt(closest);
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = "rgba(231, 185, 78, 0.9)";
    ctx.beginPath();
    ctx.moveTo(markerX, margin.top);
    ctx.lineTo(markerX, height - margin.bottom);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "#e7b94e";
    ctx.fillText("Telegram", markerX, margin.top - 7);
  }

  if (state.hoverIndex != null && candles[state.hoverIndex]) {
    const hoverX = xAt(state.hoverIndex);
    ctx.strokeStyle = "rgba(220, 230, 224, 0.4)";
    ctx.beginPath();
    ctx.moveTo(hoverX, margin.top);
    ctx.lineTo(hoverX, height - margin.bottom);
    ctx.stroke();
  }
  updateLegend(candles[state.hoverIndex ?? candles.length - 1]);
}

function updateLegend(candle) {
  if (!candle) return;
  el.legendOpen.textContent = money(candle.open);
  el.legendHigh.textContent = money(candle.high);
  el.legendLow.textContent = money(candle.low);
  el.legendClose.textContent = money(candle.close);
  el.legendVolume.textContent = compact(candle.volume);
}

function handleChartHover(event) {
  const candles = state.chart?.candles || [];
  if (!candles.length) return;
  const rect = el.chart.getBoundingClientRect();
  const plotWidth = rect.width - 12 - 66;
  const x = event.clientX - rect.left - 12;
  state.hoverIndex = Math.max(
    0,
    Math.min(candles.length - 1, Math.floor((x / plotWidth) * candles.length)),
  );
  drawChart();
}

function bindEvents() {
  el.day.addEventListener("change", async () => {
    state.day = el.day.value;
    state.selectedTicker = null;
    await loadScanner();
  });
  el.search.addEventListener("input", renderList);
  el.onlyMatches.addEventListener("change", renderList);
  document.querySelector("#criteriaButton").addEventListener("click", () => el.criteriaDialog.showModal());
  document.querySelector("#clearCriteria").addEventListener("click", () => {
    for (const input of el.criteriaForm.querySelectorAll("input")) input.value = "";
  });
  document.querySelector("#saveCriteria").addEventListener("click", saveCriteria);
  el.criteriaForm.addEventListener("submit", (event) => {
    if (event.submitter?.value !== "cancel") event.preventDefault();
  });
  el.saveReview.addEventListener("click", () => saveReview());
  for (const button of el.rating.querySelectorAll("button")) {
    button.addEventListener("click", () => saveReview(Number(button.dataset.rating), false));
  }
  for (const button of document.querySelectorAll("[data-interval]")) {
    button.addEventListener("click", async () => {
      for (const candidate of document.querySelectorAll("[data-interval]")) {
        candidate.classList.remove("active");
      }
      button.classList.add("active");
      state.interval = button.dataset.interval;
      if (state.selectedTicker) await selectTicker(state.selectedTicker, { keepList: true });
    });
  }
  el.chart.addEventListener("mousemove", handleChartHover);
  el.chart.addEventListener("mouseleave", () => {
    state.hoverIndex = null;
    drawChart();
  });
  window.addEventListener("resize", drawChart);
}

async function start() {
  state.day = localDate();
  el.day.value = state.day;
  bindEvents();
  await loadHealth();
  try {
    await loadCriteria();
    await loadScanner();
  } catch (error) {
    showToast(error.message, "error");
  }
  window.setInterval(() => loadScanner({ quiet: true }), 15000);
}

start();
