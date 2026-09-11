/* JK-PB BMS MQTT web dashboard — topics from IRIV IOC CircuitPython firmware */
const PLACEHOLDER = "—";
const SOC_R = 50;
const SOC_CIRC = 2 * Math.PI * SOC_R;
const SOC_ARC = SOC_CIRC * 0.75;
const BATT_PWR_MAX_W = 3500;
const BATT_PWR_SEGS = 10;
/* Pack series — uncomment exactly one (must match IRIV settings.toml JK_CELLS). */
// const CELL_COUNT = 4;   // 4S  (~12 V)
const CELL_COUNT = 8;      // 8S  (~24 V) — lab research pack (active)
// const CELL_COUNT = 16;  // 16S (~48–51.2 V ESS)
const CELL_V_MIN = 2.5;
const CELL_V_MAX = 3.65;
const STORAGE_KEY = "jk-pb-mqtt-web";
const DEFAULT_URL = "ws://172.16.10.40:9001";
const DEFAULT_PREFIX = "iriv/jkbms";

/* staleMs only dims the UI — IRIV publishMode=1 often skips unchanged values. */
const METRICS = {
  "pack/voltage": { staleMs: 90000, kind: "v3" },
  "pack/current": { staleMs: 90000, kind: "a3" },
  "pack/power": { staleMs: 90000, kind: "w" },
  "pack/soc": { staleMs: 90000, kind: "soc" },
  "pack/balance_current": { staleMs: 90000, kind: "a3" },
  "pack/remain_ah": { staleMs: 180000, kind: "ah" },
  "pack/full_ah": { staleMs: 180000, kind: "ah" },
  "pack/cycles": { staleMs: 180000, kind: "int" },
  "pack/soh": { staleMs: 180000, kind: "soc" },
  "pack/alarm": { staleMs: 120000, kind: "alarm" },
  "pack/runtime_s": { staleMs: 120000, kind: "runtime" },
  "cells/average": { staleMs: 120000, kind: "v3" },
  "cells/delta_max": { staleMs: 120000, kind: "v3" },
  "temp/mos": { staleMs: 120000, kind: "c" },
  "temp/battery1": { staleMs: 120000, kind: "c" },
  "temp/battery2": { staleMs: 120000, kind: "c" },
};

for (let i = 1; i <= CELL_COUNT; i++) {
  METRICS[`cells/${i}`] = { staleMs: 180000, kind: "v3" };
}

const samples = {};
let client = null;
let mqttOk = false;
let prefix = DEFAULT_PREFIX;
let balanceState = null;
let lastLiveAt = 0;
let lastMsgAt = 0;
let liveCount = 0;
let retainOnlyCount = 0;

function defaultUrl() {
  return DEFAULT_URL;
}

function loadSettings() {
  let saved = {};
  try {
    saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
  } catch {
    saved = {};
  }
  return {
    url: saved.url || defaultUrl(),
    user: saved.user || "",
    pass: saved.pass || "",
    prefix: saved.prefix || DEFAULT_PREFIX,
  };
}

function saveSettings(cfg) {
  const prev = loadSettings();
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...prev, ...cfg }));
}

function isLive(key) {
  const s = samples[key];
  return !!(s && s.valid && s.live);
}

function isFresh(key) {
  const spec = METRICS[key];
  const s = samples[key];
  if (!spec || !s || !s.valid) {
    return false;
  }
  // Broker retain on subscribe is not proof IRIV is still polling.
  if (!s.live) {
    return false;
  }
  return Date.now() - s.at <= spec.staleMs;
}

/** Last sample — keep showing after IRIV skips an unchanged publish (publishMode=1). */
function valueOf(key) {
  const s = samples[key];
  if (!s || !s.valid) {
    return null;
  }
  return s.value;
}

function ageClass(key) {
  if (valueOf(key) === null) {
    return "muted";
  }
  if (!isLive(key)) {
    return "stale retain";
  }
  return isFresh(key) ? "" : "stale";
}

function formatAge(ms) {
  if (ms < 1000) {
    return "<1s";
  }
  if (ms < 60000) {
    return `${Math.floor(ms / 1000)}s`;
  }
  if (ms < 3600000) {
    return `${Math.floor(ms / 60000)}m`;
  }
  return `${Math.floor(ms / 3600000)}h`;
}

function feedStatus() {
  if (!mqttOk) {
    return { text: "Feed —", cls: "muted" };
  }
  if (!lastMsgAt) {
    return { text: "Feed waiting", cls: "muted" };
  }
  if (!lastLiveAt) {
    return {
      text: `Retain only · ${retainOnlyCount} topic`,
      cls: "warn",
    };
  }
  const age = Date.now() - lastLiveAt;
  if (age <= 15000) {
    return { text: `Live ${formatAge(age)} · ${liveCount} topic`, cls: "ok" };
  }
  if (age <= 90000) {
    return { text: `Live ${formatAge(age)} ago`, cls: "warn" };
  }
  return { text: `No live ${formatAge(age)} · retain?`, cls: "danger" };
}

function fmtNum(v, digits, unit) {
  return `${v.toFixed(digits)} ${unit}`;
}

function formatWatts(v) {
  if (v === null || v === undefined) {
    return PLACEHOLDER;
  }
  return `${v >= 0 ? "+" : ""}${v.toFixed(0)} W`;
}

function formatRuntime(sec) {
  if (sec === null || sec === undefined) {
    return PLACEHOLDER;
  }
  const s = Math.max(0, Math.floor(sec));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) {
    return `${d}d ${h}h`;
  }
  if (h > 0) {
    return `${h}h ${m}m`;
  }
  return `${m}m`;
}

function decodeSoc(raw) {
  if (raw === null || raw === undefined || !Number.isFinite(raw)) {
    return { soc: null, balance: null };
  }
  const n = Math.round(raw);
  if (n > 100) {
    return { soc: n & 0xff, balance: (n >> 8) & 0xff };
  }
  return { soc: n, balance: balanceState };
}

function formatMetric(key, signed) {
  const spec = METRICS[key];
  if (key === "pack/soc") {
    const v = valueOf(key);
    if (v === null) {
      return PLACEHOLDER;
    }
    const { soc } = decodeSoc(v);
    return soc === null ? PLACEHOLDER : `${soc.toFixed(0)}%`;
  }
  if (key === "pack/soh") {
    const v = valueOf(key);
    return v === null ? PLACEHOLDER : `SOH ${v.toFixed(0)}%`;
  }
  if (key === "pack/cycles") {
    const v = valueOf(key);
    return v === null ? PLACEHOLDER : `${v.toFixed(0)} cycles`;
  }
  if (key === "pack/alarm") {
    const v = valueOf(key);
    if (v === null) {
      return PLACEHOLDER;
    }
    const n = v | 0;
    return n === 0 ? "OK" : `0x${n.toString(16).toUpperCase()}`;
  }
  if (key === "pack/runtime_s") {
    return formatRuntime(valueOf(key));
  }

  const v = valueOf(key);
  if (v === null) {
    return PLACEHOLDER;
  }
  if (spec.kind === "w") {
    return formatWatts(v);
  }
  const sign = signed && v >= 0 ? "+" : "";
  switch (spec.kind) {
    case "v3":
      return fmtNum(v, 3, "V");
    case "a3":
      return `${sign}${v.toFixed(3)} A`;
    case "c":
      return fmtNum(v, 1, "°C");
    case "ah":
      return fmtNum(v, 2, "Ah");
    case "int":
      return `${v.toFixed(0)}`;
    default:
      return String(v);
  }
}

function formatClock() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Ho_Chi_Minh",
    weekday: "short",
    month: "short",
    day: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(new Date());
  const g = {};
  parts.forEach((p) => {
    if (p.type !== "literal") {
      g[p.type] = p.value;
    }
  });
  return `${g.weekday}, ${g.month} ${g.day}, ${g.year}  ${g.hour}:${g.minute}:${g.second}`;
}

function batteryState() {
  const v = valueOf("pack/power");
  const i = valueOf("pack/current");
  const n = v !== null ? v : i;
  if (n === null) {
    return "unknown";
  }
  const thr = v !== null ? 0.5 : 0.05;
  if (n > thr) {
    return "charging";
  }
  if (n < -thr) {
    return "discharging";
  }
  return "idle";
}

function signedColor(key) {
  const v = valueOf(key);
  if (v === null) {
    return "muted";
  }
  const stale = !isLive(key) ? "stale retain" : isFresh(key) ? "" : "stale";
  if (key === "pack/power" || key === "pack/current") {
    const thr = key === "pack/power" ? 0.5 : 0.05;
    if (v < -thr) {
      return `pos ${stale}`.trim();
    }
    if (v > thr) {
      return `neg-batt ${stale}`.trim();
    }
    return stale;
  }
  return stale;
}

function socColor(soc) {
  if (soc < 20) {
    return "#f85149";
  }
  if (soc < 40) {
    return "#e3b341";
  }
  return "#3fb950";
}

function cellBarPct(v) {
  if (v === null) {
    return 0;
  }
  return Math.max(0, Math.min(100, ((v - CELL_V_MIN) / (CELL_V_MAX - CELL_V_MIN)) * 100));
}

function cellBarColor(v, isMin, isMax) {
  if (v === null) {
    return "#8b949e";
  }
  if (isMin) {
    return "var(--danger)";
  }
  if (isMax) {
    return "var(--pos)";
  }
  if (v < 2.8 || v > 3.55) {
    return "var(--neg)";
  }
  return "var(--accent)";
}

function setText(id, text, extraClass) {
  const el = document.getElementById(id);
  if (!el) {
    return;
  }
  el.textContent = text;
  if (el.dataset.baseClass !== undefined) {
    el.className = `${el.dataset.baseClass} ${extraClass || ""}`.trim();
  }
}

function paintSegs() {
  const segs = document.querySelectorAll("#batt-segs span");
  const v = valueOf("pack/power");
  let lit = 0;
  let color = "var(--pos)";
  if (v !== null) {
    const mag = Math.abs(v);
    if (mag > 0.5) {
      lit = Math.ceil((mag / BATT_PWR_MAX_W) * BATT_PWR_SEGS);
      lit = Math.min(BATT_PWR_SEGS, Math.max(1, lit));
      color = v < 0 ? "var(--pos)" : "var(--danger)";
    }
  }
  segs.forEach((el, i) => {
    el.style.background = i < lit ? color : "var(--seg-off)";
  });
}

function paintSocRing() {
  const raw = valueOf("pack/soc");
  const { soc } = decodeSoc(raw);
  const ind = document.getElementById("soc-ind");
  const label = document.getElementById("home-soc");
  if (!ind || !label) {
    return;
  }
  const pct = soc === null ? 0 : Math.max(0, Math.min(100, soc));
  const col = soc === null ? "#8b949e" : socColor(pct);
  ind.style.stroke = col;
  ind.style.strokeDasharray = `${SOC_ARC} ${SOC_CIRC}`;
  ind.style.strokeDashoffset = String(SOC_ARC * (1 - pct / 100));
  label.textContent = soc === null ? PLACEHOLDER : `${pct.toFixed(0)}%`;
  label.style.color = col;
  label.className = `soc-val ${ageClass("pack/soc")}`.trim();
}

function derivedCellStats(voltages) {
  const valid = voltages.filter((v) => v !== null);
  if (!valid.length) {
    return { avg: null, delta: null };
  }
  const avg = valid.reduce((a, b) => a + b, 0) / valid.length;
  return { avg, delta: Math.max(...valid) - Math.min(...valid) };
}

function paintCells() {
  let avg = valueOf("cells/average");
  const voltages = [];
  for (let i = 1; i <= CELL_COUNT; i++) {
    voltages.push(valueOf(`cells/${i}`));
  }
  const derived = derivedCellStats(voltages);
  if (avg === null) {
    avg = derived.avg;
  }
  const valid = voltages
    .map((v, i) => ({ v, i }))
    .filter((x) => x.v !== null);
  let minIdx = -1;
  let maxIdx = -1;
  if (valid.length) {
    minIdx = valid.reduce((a, b) => (b.v < a.v ? b : a)).i;
    maxIdx = valid.reduce((a, b) => (b.v > a.v ? b : a)).i;
  }

  const summary = document.getElementById("cells-summary");
  if (summary) {
    if (minIdx < 0) {
      summary.textContent = `${CELL_COUNT}S · min/max —`;
    } else {
      const dMin = voltages[minIdx];
      const dMax = voltages[maxIdx];
      const liveN = voltages.filter((_, i) => isLive(`cells/${i + 1}`)).length;
      const tag = liveN ? `${liveN} live` : "retain";
      summary.textContent = `${CELL_COUNT}S · min C${minIdx + 1} ${dMin.toFixed(3)} V · max C${maxIdx + 1} ${dMax.toFixed(3)} V · ${tag}`;
    }
  }

  for (let i = 1; i <= CELL_COUNT; i++) {
    const idx = i - 1;
    const v = voltages[idx];
    const card = document.getElementById(`cell-${i}`);
    const valEl = document.getElementById(`cell-v-${i}`);
    const bar = document.getElementById(`cell-bar-${i}`);
    const deltaEl = document.getElementById(`cell-delta-${i}`);
    if (!card || !valEl || !bar || !deltaEl) {
      continue;
    }
    const isMin = idx === minIdx && minIdx !== maxIdx;
    const isMax = idx === maxIdx && minIdx !== maxIdx;
    card.classList.toggle("min", isMin);
    card.classList.toggle("max", isMax);
    valEl.textContent = v === null ? PLACEHOLDER : `${v.toFixed(3)} V`;
    valEl.className = `cell-v ${ageClass(`cells/${i}`)}`.trim();
    valEl.title = sampleTitle(`cells/${i}`);
    card.classList.toggle("stale", v !== null && !isFresh(`cells/${i}`));
    card.classList.toggle("retain", v !== null && !isLive(`cells/${i}`));
    card.title = sampleTitle(`cells/${i}`);
    const pct = cellBarPct(v);
    bar.style.width = `${pct}%`;
    bar.style.background = cellBarColor(v, isMin, isMax);
    if (v !== null && avg !== null) {
      const dMv = (v - avg) * 1000;
      deltaEl.textContent = `${dMv >= 0 ? "+" : ""}${dMv.toFixed(1)} mV`;
    } else {
      deltaEl.textContent = "Δ —";
    }
  }
}

function paint() {
  const mqttEl = document.getElementById("sb-mqtt");
  mqttEl.textContent = mqttOk ? "MQTT OK" : "MQTT --";
  mqttEl.className = `sb-item ${mqttOk ? "ok" : "muted"}`;

  const feed = feedStatus();
  setText("sb-feed", feed.text, feed.cls);

  const bState = batteryState();
  let stateText = PLACEHOLDER;
  let stateCls = "muted";
  if (bState === "charging") {
    stateText = "Charging";
    stateCls = "ok";
  } else if (bState === "discharging") {
    stateText = "Discharging";
    stateCls = "danger";
  } else if (bState === "idle") {
    stateText = "Idle";
    stateCls = "info";
  }
  setText("sb-state", stateText, stateCls);

  const mos = valueOf("temp/mos");
  setText(
    "sb-mos",
    mos === null ? "MOS —" : `MOS ${mos.toFixed(1)} °C`,
    ageClass("temp/mos")
  );

  const balI = valueOf("pack/balance_current");
  let balText = "Bal —";
  if (balanceState !== null && balanceState > 0) {
    balText = `Bal state ${balanceState}`;
  } else if (balI !== null) {
    balText = `Bal ${balI.toFixed(3)} A`;
  }
  setText(
    "sb-balance",
    balText,
    balI === null && balanceState === null ? "muted" : ageClass("pack/balance_current")
  );

  document.getElementById("sb-clock").textContent = formatClock();

  const battP = document.getElementById("home-batt-p");
  battP.textContent = formatMetric("pack/power", true);
  battP.className = `hero ${signedColor("pack/power") || ""}`;

  setText("home-batt-dir", stateText, stateCls);

  const remain = valueOf("pack/remain_ah");
  const full = valueOf("pack/full_ah");
  let capText = PLACEHOLDER;
  if (remain !== null && full !== null) {
    capText = `${remain.toFixed(2)} / ${full.toFixed(2)} Ah`;
  } else if (remain !== null) {
    capText = `${remain.toFixed(2)} Ah`;
  }
  const capAge =
    remain === null
      ? "muted"
      : !isLive("pack/remain_ah") || (full !== null && !isLive("pack/full_ah"))
        ? "stale retain"
        : !isFresh("pack/remain_ah") || (full !== null && !isFresh("pack/full_ah"))
          ? "stale"
          : "";
  setText("home-capacity", capText, capAge);

  setText("home-runtime", formatMetric("pack/runtime_s"), ageClass("pack/runtime_s"));
  const alarmV = valueOf("pack/alarm");
  let alarmCls = ageClass("pack/alarm");
  if (alarmV !== null) {
    const age = !isLive("pack/alarm") ? "stale retain" : isFresh("pack/alarm") ? "" : "stale";
    alarmCls = `${alarmV === 0 ? "pos" : "danger"} ${age}`.trim();
  }
  setText("home-alarm", formatMetric("pack/alarm"), alarmCls);

  document.querySelectorAll("[data-m]").forEach((el) => {
    const key = el.dataset.m;
    const signed = el.hasAttribute("data-signed");
    let text = formatMetric(key, signed);
    // Prefer BMS topics; if missing, show avg/Δ derived from cells we have.
    if (key === "cells/average" && valueOf(key) === null) {
      const voltages = [];
      for (let i = 1; i <= CELL_COUNT; i++) {
        voltages.push(valueOf(`cells/${i}`));
      }
      const { avg } = derivedCellStats(voltages);
      text = avg === null ? PLACEHOLDER : fmtNum(avg, 3, "V");
    }
    if (key === "cells/delta_max" && valueOf(key) === null) {
      const voltages = [];
      for (let i = 1; i <= CELL_COUNT; i++) {
        voltages.push(valueOf(`cells/${i}`));
      }
      const { delta } = derivedCellStats(voltages);
      text = delta === null ? PLACEHOLDER : fmtNum(delta, 3, "V");
    }
    const extra = signed ? signedColor(key) : ageClass(key);
    el.textContent = text;
    el.className = `${el.dataset.baseClass} ${extra}`.trim();
    el.title = sampleTitle(key);
  });

  paintSocRing();
  paintSegs();
  paintCells();
}

function sampleTitle(key) {
  const s = samples[key];
  if (!s || !s.valid) {
    return "No MQTT message for this topic (not even broker retain).";
  }
  const age = formatAge(Date.now() - s.at);
  if (!s.live) {
    return `Broker retain only — received on subscribe, no live publish yet (${age} on screen).`;
  }
  return `Last live MQTT ${age} ago.`;
}

function ingest(topic, payload, retained) {
  if (!topic.startsWith(`${prefix}/`)) {
    return;
  }
  const key = topic.slice(prefix.length + 1);
  if (!METRICS[key]) {
    return;
  }
  let value;
  try {
    const parsed = JSON.parse(payload);
    value = Number(parsed.value);
  } catch {
    return;
  }
  if (!Number.isFinite(value)) {
    return;
  }
  const now = Date.now();
  lastMsgAt = now;
  const prev = samples[key];
  const live = !retained;
  if (live) {
    lastLiveAt = now;
    if (!prev || !prev.live) {
      liveCount += 1;
      if (prev && !prev.live) {
        retainOnlyCount = Math.max(0, retainOnlyCount - 1);
      }
    }
  } else if (!prev) {
    retainOnlyCount += 1;
  }
  if (key === "pack/soc") {
    const decoded = decodeSoc(value);
    if (decoded.balance !== null) {
      balanceState = decoded.balance;
    }
  }
  samples[key] = {
    value,
    at: now,
    valid: true,
    live: live || !!(prev && prev.live),
    retainSeen: retained || !!(prev && prev.retainSeen),
  };
}

function resetFeedCounters() {
  lastLiveAt = 0;
  lastMsgAt = 0;
  liveCount = 0;
  retainOnlyCount = 0;
  Object.keys(samples).forEach((k) => {
    delete samples[k];
  });
  balanceState = null;
}

function disconnect() {
  if (client) {
    client.end(true);
    client = null;
  }
  mqttOk = false;
  paint();
}

function connect() {
  if (typeof mqtt === "undefined") {
    alert("mqtt.js failed to load. Keep vendor/mqtt.min.js next to this page.");
    return;
  }
  const cfg = loadSettings();
  prefix = (cfg.prefix || DEFAULT_PREFIX).replace(/\/+$/, "");
  disconnect();
  resetFeedCounters();
  const opts = {
    clientId: `jk-pb-web-${Math.random().toString(16).slice(2, 10)}`,
    keepalive: 30,
    reconnectPeriod: 4000,
    clean: true,
  };
  if (cfg.user) {
    opts.username = cfg.user;
  }
  if (cfg.pass) {
    opts.password = cfg.pass;
  }
  client = mqtt.connect(cfg.url, opts);
  client.on("connect", () => {
    mqttOk = true;
    client.subscribe(`${prefix}/#`, { qos: 1 });
    paint();
  });
  client.on("reconnect", () => {
    mqttOk = false;
    paint();
  });
  client.on("close", () => {
    mqttOk = false;
    paint();
  });
  client.on("error", () => {
    mqttOk = false;
    paint();
  });
  client.on("message", (topic, payload, packet) => {
    ingest(topic, payload.toString(), !!(packet && packet.retain));
    paint();
  });
}

function fillSettingsForm() {
  const cfg = loadSettings();
  document.getElementById("cfg-url").value = cfg.url;
  document.getElementById("cfg-user").value = cfg.user;
  document.getElementById("cfg-pass").value = cfg.pass;
  document.getElementById("cfg-prefix").value = cfg.prefix;
}

function fillSegs() {
  const root = document.getElementById("batt-segs");
  root.innerHTML = "";
  for (let i = 0; i < BATT_PWR_SEGS; i++) {
    root.appendChild(document.createElement("span"));
  }
}

function buildCells() {
  const grid = document.getElementById("cells-grid");
  grid.innerHTML = "";
  for (let i = 1; i <= CELL_COUNT; i++) {
    const article = document.createElement("article");
    article.className = "cell";
    article.id = `cell-${i}`;
    article.innerHTML = `
      <div class="cell-top"><span>Cell ${i}</span><span id="cell-tag-${i}"></span></div>
      <div id="cell-v-${i}" class="cell-v muted">—</div>
      <div class="cell-bar"><span id="cell-bar-${i}"></span></div>
      <div id="cell-delta-${i}" class="cell-delta">Δ —</div>
    `;
    grid.appendChild(article);
  }
}

function initUi() {
  fillSegs();
  buildCells();
  document.querySelectorAll("[data-m], .hero, .soc-val, .metric, .sub").forEach((el) => {
    el.dataset.baseClass = el.className;
  });
  ["home-capacity", "home-runtime", "home-alarm", "sb-state", "sb-mos", "sb-balance", "sb-feed"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.dataset.baseClass = el.className;
    }
  });

  const dlg = document.getElementById("settings");
  document.getElementById("btn-settings").addEventListener("click", () => {
    fillSettingsForm();
    dlg.showModal();
  });
  document.getElementById("btn-close").addEventListener("click", () => dlg.close());
  document.getElementById("btn-disconnect").addEventListener("click", () => {
    disconnect();
    dlg.close();
  });
  document.getElementById("settings-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const cfg = {
      url: document.getElementById("cfg-url").value.trim() || DEFAULT_URL,
      user: document.getElementById("cfg-user").value.trim(),
      pass: document.getElementById("cfg-pass").value,
      prefix: document.getElementById("cfg-prefix").value.trim() || DEFAULT_PREFIX,
    };
    saveSettings(cfg);
    dlg.close();
    connect();
  });
}

initUi();
fillSettingsForm();
connect();
setInterval(paint, 250);
paint();
