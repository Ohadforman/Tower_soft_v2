const app = document.getElementById("app");
let bootstrapData = null;
let partsManualIndexCache = null;
let partsManualIndexPromise = null;
let orderDrawFlash = null;
let maintenanceStageFlash = null;
let drawFinalizeFlash = null;
let globalPressFeedbackBound = false;
let consumablesLivePollTimer = null;
let consumablesLivePollInFlight = false;
const CONSUMABLES_LIVE_POLL_INTERVAL_MS = 10000;
const DEFAULT_HOME_PANEL = "draws";
const HOME_PANELS = [
  { key: "draws", title: "Draws", shortTitle: "Draws", eyebrow: "Live draw orders", detailLabel: "Active", position: "pos-a" },
  { key: "doneFailed", title: "Done + Failed", shortTitle: "Results", eyebrow: "Completed / failed", detailLabel: "Resolved", position: "pos-b" },
  { key: "schedule", title: "Schedule", shortTitle: "Schedule", eyebrow: "Tower events", detailLabel: "Upcoming", position: "pos-c" },
  { key: "maintenance", title: "Maintenance + Faults", shortTitle: "Maintenance", eyebrow: "Service readiness", detailLabel: "Watch", position: "pos-d" },
  { key: "parts", title: "Parts Orders", shortTitle: "Parts", eyebrow: "Supply pressure", detailLabel: "Orders", position: "pos-e" },
];

const NAV_GROUPS = [
  {
    title: "Home & Project Management",
    pages: [
      { route: "/home", key: "home", label: "Home", eyebrow: "Core" },
      { route: "/schedule", key: "schedule", label: "Schedule", eyebrow: "Plan" },
      { route: "/parts", key: "parts", label: "Tower Parts", eyebrow: "Supply" },
      { route: "/order-draw", key: "orderDraw", label: "Order Draw", eyebrow: "Queue" },
    ],
  },
  {
    title: "Operations",
    pages: [
      { route: "/consumables", key: "consumables", label: "Tower State - Consumables and Dies", eyebrow: "Tower" },
      { route: "/process-setup", key: "processSetup", label: "Process Setup", eyebrow: "Setup" },
      { route: "/maintenance", key: "maintenance", label: "Maintenance", eyebrow: "Service" },
      { route: "/dashboard", key: "dashboard", label: "Dashboard", eyebrow: "Overview" },
      { route: "/draw-finalize", key: "drawFinalize", label: "Draw Finalize", eyebrow: "Finish" },
      { route: "/parts", key: "parts", label: "Tower Parts", eyebrow: "Supply" },
      { route: "/data-diagnostics", key: "diagnostics", label: "Data Diagnostics", eyebrow: "Checks" },
      { route: "/report-center", key: "reportCenter", label: "Report Center", eyebrow: "Reports" },
    ],
  },
  {
    title: "Monitoring & Research",
    pages: [
      { route: "/sql-lab", key: "sqlLab", label: "SQL Lab", eyebrow: "Explore" },
      { route: "/development", key: "development", label: "Development Process", eyebrow: "Research" },
    ],
  },
];

const PAGE_REGISTRY = NAV_GROUPS.flatMap((group) => group.pages);

const MAINT_GROUPS = [
  { key: "maintenance", title: "Maintenance", sub: "Builder, prep, execute", tone: "info" },
  { key: "faults", title: "Faults", sub: "Incidents and closure", tone: "bad" },
];

const MAINT_VIEWS = [
  { key: "builder", title: "Builder", sub: "Tasks + BOM" },
  { key: "plan", title: "Plan", sub: "Prepare next batch" },
  { key: "execute", title: "Execute", sub: "Resolve blocks" },
];

function getCurrentRoute() {
  const hash = window.location.hash.replace(/^#/, "") || "/home";
  return hash.startsWith("/") ? hash : `/${hash}`;
}

function slugifyToken(value) {
  return String(value || "unknown")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "unknown";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function sanitizeAttachmentPath(value) {
  return String(value || "")
    .replace(/[\u200e\u200f\u202a-\u202e\u2066-\u2069]/g, "")
    .trim();
}

function toneForLabel(label) {
  const normalized = String(label || "").toLowerCase();
  if (/(management|manager|admin|coordination)/.test(normalized)) return "manage";
  if (/(done|received|closed|complete|completed|ready|ok|clear)/.test(normalized)) return "good";
  if (/(stop|fail|fault|critical|blocked|overdue|delay|low stock|low-stock|warning)/.test(normalized)) return "bad";
  if (/(maintenance|open|pending|in progress|active|watch)/.test(normalized)) return "warn";
  if (/(schedule|plan|draw|inventory|project|general)/.test(normalized)) return "info";
  return "neutral";
}

function metricMarkup(metrics) {
  return metrics
    .map(
      (item) => `
        <div class="metric-pill tone-${item.tone || toneForLabel(item.label)}">
          <span>${item.label}</span>
          <strong>${item.value}</strong>
        </div>
      `,
    )
    .join("");
}

function statusCount(statusCounts, label) {
  if (!statusCounts) return 0;
  return Number(
    statusCounts[label]
    ?? statusCounts[label.toLowerCase()]
    ?? statusCounts[label.replace(/\s+/g, "_").toLowerCase()]
    ?? 0,
  );
}

function orderProgressTimelineMarkup(statusCounts, options = {}) {
  const {
    eyebrow = "Order progress",
    title = "Pending to done",
    compact = false,
    sideMeta = [],
  } = options;
  const stages = [
    { key: "Pending", label: "Pending", tone: "warn" },
    { key: "Scheduled", label: "Scheduled", tone: "info" },
    { key: "In Progress", label: "In progress", tone: "warn" },
    { key: "Done", label: "Done", tone: "good" },
  ];
  const failed = statusCount(statusCounts, "Failed");
  const activeIndex = stages.findIndex((stage) => statusCount(statusCounts, stage.key) > 0);
  const progressIndex = activeIndex >= 0 ? activeIndex : stages.reduce((last, stage, index) => (statusCount(statusCounts, stage.key) > 0 ? index : last), 0);
  return `
    <section class="order-progress-timeline ${compact ? "is-compact" : ""}">
      <div class="chart-head">
        <span>${eyebrow}</span>
        <strong>${title}</strong>
      </div>
      <div class="order-progress-track-shell">
        <div class="order-progress-track">
          <i class="order-progress-fill" style="width:${(progressIndex / Math.max(1, stages.length - 1)) * 100}%"></i>
        </div>
        <div class="order-progress-stages">
          ${stages
            .map((stage, index) => {
              const value = statusCount(statusCounts, stage.key);
              const isActive = index === progressIndex && value > 0;
              const isPast = index < progressIndex || (index === progressIndex && value > 0);
              const hasSignal = stage.key === "Done" && value > 0;
              return `
                <div class="order-progress-stage tone-${stage.tone} ${isActive ? "is-active" : ""} ${isPast ? "is-past" : ""} ${hasSignal ? "has-signal" : ""}">
                  <i class="order-progress-dot"></i>
                  <span>${stage.label}</span>
                  <strong>${value}</strong>
                </div>
              `;
            })
            .join("")}
        </div>
      </div>
      <div class="order-progress-meta">
        ${failed ? `<div class="order-progress-side tone-bad"><span>Failed</span><strong>${failed}</strong></div>` : ``}
        ${sideMeta.map((item) => `<div class="order-progress-side tone-${item.tone || "info"}"><span>${item.label}</span><strong>${item.value}</strong></div>`).join("")}
      </div>
    </section>
  `;
}

function orderStatusTone(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "pending") return "warn";
  if (normalized === "scheduled") return "info";
  if (normalized === "in progress") return "good";
  if (normalized === "done") return "good";
  if (normalized === "failed") return "bad";
  return "neutral";
}

function orderMiniStatusRailMarkup(data) {
  const orders = [
    ...((data.pending_orders || []).slice(0, 3).map((item) => ({ ...item, status: "Pending" }))),
    ...((data.scheduled_orders || []).slice(0, 4).map((item) => ({ ...item, status: item.status || "Scheduled" }))),
    ...((data.completed_orders || []).slice(0, 3).map((item) => ({ ...item, status: item.status || "Done" }))),
  ].slice(0, 10);
  return `
    <section class="order-status-rail">
      <div class="chart-head">
        <span>Order flow</span>
        <strong>Queue by order</strong>
      </div>
      <div class="order-status-rail-track">
        <i style="width:${Math.min(100, Math.max(14, ((Number((data.status_counts || {}).Done || 0) + Number((data.status_counts || {})["In Progress"] || 0) + Number((data.status_counts || {}).Scheduled || 0)) / Math.max(1, orders.length || 1)) * 100))}%"></i>
      </div>
      <div class="order-status-list">
        ${orders.length ? orders.map((item) => `
          <article class="order-status-chip tone-${orderStatusTone(item.status)}">
            <div class="order-status-chip-head">
              <strong>${escapeHtml(item.project || item.preform || "Order")}</strong>
              <span class="order-status-badge tone-${orderStatusTone(item.status)}">${escapeHtml(item.status || "Unknown")}</span>
            </div>
            <div class="order-status-chip-meta">
              <span>${escapeHtml(item.preform || "No preform")}</span>
              <span>${escapeHtml(item.geometry || "No geometry")}</span>
            </div>
          </article>
        `).join("") : `<div class="chart-empty">No recent order states.</div>`}
      </div>
    </section>
  `;
}

function compactOrderFlowMarkup(data) {
  const stages = ["Pending", "Scheduled", "In Progress", "Done", "Failed"];
  const grouped = Object.fromEntries(stages.map((stage) => [stage, []]));
  (data.all_orders || []).slice(0, 18).forEach((item) => {
    const key = stages.includes(item.status) ? item.status : "Pending";
    grouped[key].push(item);
  });
  return `
    <section class="order-flow-compact">
      <div class="chart-head">
        <span>Order flow</span>
        <strong>Queue by order</strong>
      </div>
      <div class="order-flow-stage-line">
        <i class="order-flow-stage-line-track"></i>
        ${stages.map((stage) => `
          <div class="order-flow-stage-stop tone-${orderStatusTone(stage)}">
            <i></i>
            <span>${stage}</span>
            <strong>${statusCount(data.status_counts || {}, stage)}</strong>
          </div>
        `).join("")}
      </div>
      <div class="order-flow-stage-columns">
        ${stages.map((stage) => `
          <div class="order-flow-stage-column">
            <div class="order-flow-stage-stack">
              ${(grouped[stage] || []).length ? grouped[stage].map((item) => `
                <article class="order-flow-order-pill tone-${orderStatusTone(stage)}">
                  <strong>${escapeHtml(item.project || "Order")}</strong>
                  <span>${escapeHtml(item.preform || "No preform")} · ${escapeHtml(item.geometry || "No geometry")}</span>
                </article>
              `).join("") : `<div class="order-flow-stage-empty">No orders</div>`}
            </div>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

function sparklineMarkup(series, valueKey = "value") {
  if (!series || !series.length) {
    return `<div class="chart-empty">No signal</div>`;
  }
  const width = 320;
  const height = 120;
  const padding = 12;
  const values = series.map((item) => Number(item[valueKey] ?? 0));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = series.length > 1 ? (width - padding * 2) / (series.length - 1) : 0;
  const points = values
    .map((value, index) => {
      const x = padding + index * step;
      const y = height - padding - ((value - min) / span) * (height - padding * 2);
      return `${x},${y}`;
    })
    .join(" ");
  const area = `${padding},${height - padding} ${points} ${width - padding},${height - padding}`;
  return `
    <svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id="spark-stroke" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#72ffe8"></stop>
          <stop offset="100%" stop-color="#2bd8ff"></stop>
        </linearGradient>
        <linearGradient id="spark-fill" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stop-color="rgba(114,255,232,0.35)"></stop>
          <stop offset="100%" stop-color="rgba(114,255,232,0.02)"></stop>
        </linearGradient>
      </defs>
      <polygon points="${area}" fill="url(#spark-fill)"></polygon>
      <polyline points="${points}" fill="none" stroke="url(#spark-stroke)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline>
    </svg>
  `;
}

function barChartMarkup(series, valueKey = "value") {
  if (!series || !series.length) {
    return `<div class="chart-empty">No bars</div>`;
  }
  const max = Math.max(...series.map((item) => Number(item[valueKey] ?? 0)), 1);
  return `
    <div class="bar-chart">
      ${series
        .map((item) => {
          const value = Number(item[valueKey] ?? 0);
          const width = `${Math.max(8, (value / max) * 100)}%`;
          const tone = item.tone || toneForLabel(item.label);
          return `
            <div class="bar-row tone-${tone}">
              <span class="bar-label">${item.label}</span>
              <div class="bar-track"><div class="bar-fill tone-${tone}" style="width:${width}"></div></div>
              <strong>${value}${item.unit ? ` ${item.unit}` : ""}</strong>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function consumablesTemperatureMarkup(data) {
  const formatTemp = (value) => `${Number(value || 0).toFixed(1)}&deg;C`;
  const formatOffset = (value) => {
    const numeric = Number(value || 0);
    const prefix = numeric > 0 ? "+" : "";
    return `${prefix}${numeric.toFixed(1)}&deg;C`;
  };
  const sampledAt = data.temps_updated_at ? escapeHtml(data.temps_updated_at) : "No CSV sample yet";
  const stations = data.temp_stations || [];
  const holders = (data.temp_holders || [])
    .map(
      (item) => `
        <div class="consumables-temp-chip tone-${item.tone || "info"}" data-temp-group="${item.field}">
          <div class="consumables-temp-card-head">
            <span>${escapeHtml(item.label)}</span>
          </div>
          <div class="consumables-temp-edit-row">
            <label class="consumables-temp-setpoint">
              <span>Set value</span>
              <div class="consumables-temp-input-shell">
                <input
                  type="number"
                  name="${item.field}"
                  value="${Number(item.set_value || 0).toFixed(1)}"
                  step="0.1"
                  data-temp-field="${item.field}"
                  data-measured-value="${Number(item.measured_value || 0).toFixed(1)}"
                />
                <i>&deg;C</i>
              </div>
            </label>
            <div class="consumables-temp-measured">
              <span>Measured value</span>
              <b>${formatTemp(item.measured_value)}</b>
            </div>
          </div>
          <em class="consumables-temp-track" data-temp-track="${item.field}">Track ${formatOffset(item.offset)}</em>
        </div>
      `,
    )
    .join("");
  const stationMarkup = stations
    .map(
      (item) => `
        <div class="consumables-temp-station tone-${item.tone || "info"}">
          <div class="consumables-temp-card-head">
            <strong>Station ${escapeHtml(item.label)}</strong>
            <em>MV delta ${formatTemp(item.delta)}</em>
          </div>
          <div class="consumables-temp-pair">
            <label class="consumables-temp-setpoint">
              <span>Container set</span>
              <div class="consumables-temp-input-shell">
                <input
                  type="number"
                  name="${item.container_field}"
                  value="${Number(item.container_set_value || 0).toFixed(1)}"
                  step="0.1"
                  data-temp-field="${item.container_field}"
                  data-measured-value="${Number(item.container_measured_value || 0).toFixed(1)}"
                />
                <i>&deg;C</i>
              </div>
            </label>
            <div class="consumables-temp-measured">
              <span>Container MV</span>
              <b>${formatTemp(item.container_measured_value)}</b>
            </div>
          </div>
          <em class="consumables-temp-track" data-temp-track="${item.container_field}">Track ${formatOffset(item.container_offset)}</em>
          <div class="consumables-temp-pair">
            <label class="consumables-temp-setpoint">
              <span>Pipe set</span>
              <div class="consumables-temp-input-shell">
                <input
                  type="number"
                  name="${item.pipe_field}"
                  value="${Number(item.pipe_set_value || 0).toFixed(1)}"
                  step="0.1"
                  data-temp-field="${item.pipe_field}"
                  data-measured-value="${Number(item.pipe_measured_value || 0).toFixed(1)}"
                />
                <i>&deg;C</i>
              </div>
            </label>
            <div class="consumables-temp-measured">
              <span>Pipe MV</span>
              <b>${formatTemp(item.pipe_measured_value)}</b>
            </div>
          </div>
          <em class="consumables-temp-track" data-temp-track="${item.pipe_field}">Track ${formatOffset(item.pipe_offset)}</em>
        </div>
      `,
    )
    .join("");
  return `
    <form id="consumables-temp-form" class="consumables-temperature-board">
      <div class="consumables-temp-toolbar">
        <div class="micro-panel consumables-temp-source" data-sampled-at="${sampledAt}">Measured values are sampled from <strong>tower_temps.csv</strong> · Last sample ${sampledAt} · set values auto-save while you edit</div>
        <div class="order-builder-actions consumables-temp-actions">
          <button class="action-btn action-secondary" type="button" id="consumables-temp-refresh">Reload MV</button>
          <button class="action-btn action-primary" type="submit">Save set values</button>
        </div>
      </div>
      <div class="consumables-temp-holders">${holders}</div>
      <div class="consumables-temp-stations">${stationMarkup}</div>
    </form>
  `;
}

function consumablesCoatingGuideMarkup(rows) {
  if (!rows || !rows.length) {
    return `<div class="chart-empty">No coating guidance</div>`;
  }
  return `
    <div class="consumables-coating-guide">
      ${rows
        .map(
          (item) => `
            <article class="consumables-coating-card tone-${item.tone || "neutral"}">
              <header>
                <strong>${escapeHtml(item.label)}</strong>
                <span>${Number(item.stock_kg || 0).toFixed(1)} kg</span>
              </header>
              <p>${escapeHtml(item.description)}</p>
              <div class="consumables-coating-meta">
                ${item.density ? `<span>Density ${escapeHtml(item.density)}</span>` : ""}
                ${item.viscosity ? `<span>Viscosity ${escapeHtml(item.viscosity)}</span>` : ""}
                ${item.refractive_index ? `<span>RI ${escapeHtml(item.refractive_index)}</span>` : ""}
              </div>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function consumablesContainerEditorMarkup(data) {
  const rows = Array.isArray(data?.container_editor_rows) ? data.container_editor_rows : [];
  const sensorOptions = Array.isArray(data?.container_sensor_options) ? data.container_sensor_options : [];
  const coatingOptions = Array.isArray(data?.coating_type_options) ? data.coating_type_options : [];
  const sharedDiameter = Number(data?.container_shared_diameter_mm || rows?.[0]?.diameter_mm || 0);
  const loggerStatus = data?.container_logger || {};
  const loggerTone = String(loggerStatus.state || "").trim() === "running" ? "good" : "warn";
  const loggerMessage = String(loggerStatus.message || "").trim();
  if (!rows.length) {
    return `<div class="chart-empty">No live container setup rows.</div>`;
  }
  return `
    <form id="consumables-containers-form" class="consumables-container-form">
      <div class="micro-panel consumables-container-note">
        Point <strong>Tower Containers CSV</strong> from Data Diagnostics to the Arduino feed with columns <strong>timestamp</strong>, <strong>tank1</strong>, <strong>tank2</strong>, <strong>tank3</strong>, <strong>tank4</strong>. The app-managed logger writes the first real sample as soon as live tank data arrives, then keeps logging in the background while the app is running. This setup only maps the coating type, CSV source column, and shared container diameter.
        ${loggerMessage ? `<div class="consumables-container-status tone-${loggerTone}">${escapeHtml(loggerMessage)}</div>` : ""}
      </div>
      <datalist id="consumables-coating-type-list">
        ${coatingOptions.map((item) => `<option value="${escapeHtml(item)}"></option>`).join("")}
      </datalist>
      <div class="consumables-container-shared">
        <label class="field-block consumables-container-shared-field">
          <span>Shared container diameter (mm)</span>
          <input type="number" name="container_shared_diameter" value="${sharedDiameter > 0 ? sharedDiameter.toFixed(1) : ""}" step="0.1" />
        </label>
      </div>
      <div class="consumables-container-editor">
        ${rows
          .map(
            (item, index) => {
              const liveState = String(item.live_state || "live").trim() || "live";
              const isLive = liveState === "live";
              const liveHeadline = isLive ? `${Number(item.level_kg || 0).toFixed(1)} kg live` : liveState === "stale" ? "Feed stale" : "Disconnected";
              const liveDetail = isLive
                ? `${Number(item.fill_percent || 0).toFixed(1)}% fill · ${Number(item.volume_l || 0).toFixed(1)} L from ${escapeHtml(item.sensor_column || "")}`
                : `${escapeHtml(item.updated_at || "No live sample yet")} · waiting for ${escapeHtml(item.sensor_column || "tank feed")}`;
              return `
              <div class="consumables-container-row">
                <input type="hidden" name="container_label_${index}" value="${escapeHtml(item.label || "")}" />
                <div class="consumables-container-label">
                  <strong>Station ${escapeHtml(item.label || "")}</strong>
                  <span>${escapeHtml(item.updated_at || "No live sample yet")}</span>
                </div>
                <label class="field-block">
                  <span>Coating type in container</span>
                  <input type="text" name="container_type_${index}" value="${escapeHtml(item.type || "")}" list="consumables-coating-type-list" placeholder="DP-1032" />
                </label>
                <label class="field-block">
                  <span>CSV column</span>
                  <select name="container_sensor_${index}">
                    ${sensorOptions
                      .map(
                        (sensor) =>
                          `<option value="${escapeHtml(sensor)}" ${sensor === item.sensor_column ? "selected" : ""}>${escapeHtml(sensor)}</option>`,
                      )
                      .join("")}
                  </select>
                </label>
                <div class="micro-panel consumables-container-live">
                  <strong>${liveHeadline}</strong>
                  <p>${liveDetail}</p>
                </div>
              </div>
            `;
            },
          )
          .join("")}
      </div>
      <div class="order-builder-actions">
        <button class="action-btn action-primary" type="submit">Save live fill setup</button>
      </div>
    </form>
  `;
}

function consumablesCoatingEditorMarkup(rows) {
  const safeRows = Array.isArray(rows) ? rows : [];
  if (!safeRows.length) {
    return `<div class="chart-empty">No coating rows to edit.</div>`;
  }
  return `
    <form id="consumables-coatings-form" class="consumables-coating-form">
      <div class="micro-panel consumables-coating-note">
        Update the operator coating data here. This saves only the coating guide fields in <strong>config_coating.json</strong>: description, density, viscosity, and RI.
      </div>
      <div class="consumables-coating-editor">
        ${safeRows
          .map(
            (item, index) => `
              <div class="consumables-coating-edit-row tone-${item.tone || "neutral"}">
                <input type="hidden" name="coating_label_${index}" value="${escapeHtml(item.label || "")}" />
                <div class="consumables-coating-edit-meta">
                  <div class="consumables-coating-edit-head">
                    <strong>${escapeHtml(item.label || "Unnamed coating")}</strong>
                    <span>${item.in_config ? "Saved coating config" : "Will create coating config entry"}</span>
                  </div>
                  <div class="consumables-coating-edit-stock">
                    <b>${Number(item.stock_kg || 0).toFixed(1)} kg total</b>
                    <span>Warehouse ${Number(item.warehouse_kg || 0).toFixed(1)} kg</span>
                    <span>Loaded ${Number(item.loaded_kg || 0).toFixed(1)} kg</span>
                    <span>Min ${Number(item.min_stock_kg || 0).toFixed(1)} kg</span>
                  </div>
                </div>
                <label class="field-block consumables-coating-description">
                  <span>Description</span>
                  <textarea name="coating_description_${index}" rows="3" placeholder="Operator note, usage, or coating purpose">${escapeHtml(item.description || "")}</textarea>
                </label>
                <div class="consumables-coating-edit-fields">
                  <label class="field-block">
                    <span>Density</span>
                    <input type="text" name="coating_density_${index}" value="${escapeHtml(item.density ?? "")}" placeholder="e.g. 1.05e3" />
                  </label>
                  <label class="field-block">
                    <span>Viscosity</span>
                    <input type="text" name="coating_viscosity_${index}" value="${escapeHtml(item.viscosity ?? "")}" placeholder="e.g. 2.2" />
                  </label>
                  <label class="field-block">
                    <span>RI</span>
                    <input type="text" name="coating_ri_${index}" value="${escapeHtml(item.refractive_index ?? "")}" placeholder="e.g. 1.4" />
                  </label>
                </div>
              </div>
            `,
          )
          .join("")}
      </div>
      <div class="order-builder-actions">
        <button class="action-btn action-primary" type="submit">Save coating guide</button>
      </div>
    </form>
  `;
}

function consumablesStockEditorMarkup(rows) {
  const safeRows = Array.isArray(rows) ? rows : [];
  return `
    <form id="consumables-stock-form" class="consumables-stock-form">
      <div class="micro-panel consumables-stock-note">
        Total inventory here is <strong>warehouse + loaded containers</strong>. Update the warehouse kg, set a minimum stock threshold, or remove a warehouse line when it is no longer kept in storage.
      </div>
      <div class="consumables-stock-editor">
        ${safeRows
          .map(
            (item, index) => `
              <div class="consumables-stock-row tone-${item.tone || "neutral"}">
                <input type="hidden" name="stock_label_${index}" value="${escapeHtml(item.label || "")}" />
                <div class="consumables-stock-label">
                  <strong>${escapeHtml(item.label || "Unnamed coating")}</strong>
                  <span>${item.in_config ? "Known coating type" : "Custom live stock type"}</span>
                </div>
                <label class="field-block consumables-stock-value">
                  <span>Warehouse kg</span>
                  <input type="number" name="stock_value_${index}" value="${Number(item.value || 0).toFixed(1)}" step="0.1" />
                </label>
                <label class="field-block consumables-stock-value">
                  <span>Min stock kg</span>
                  <input type="number" name="stock_min_${index}" value="${Number(item.min_stock_kg || 0).toFixed(1)}" step="0.1" />
                </label>
                <div class="micro-panel consumables-stock-meta">
                  <strong>${Number(item.total_kg || 0).toFixed(1)} kg total inventory</strong>
                  <p>Warehouse ${Number(item.value || 0).toFixed(1)} kg · Loaded now ${Number(item.loaded_kg || 0).toFixed(1)} kg · Min ${Number(item.min_stock_kg || 0).toFixed(1)} kg</p>
                  <label class="consumables-stock-remove">
                    <input type="checkbox" name="stock_remove_${index}" />
                    <span>Remove from warehouse</span>
                  </label>
                </div>
              </div>
            `,
          )
          .join("")}
        <div class="consumables-stock-row is-add">
          <label class="field-block">
            <span>New coating type</span>
            <input type="text" name="new_stock_label" placeholder="Coating_XYZ" />
          </label>
          <label class="field-block consumables-stock-value">
            <span>Warehouse kg</span>
            <input type="number" name="new_stock_value" value="" step="0.1" placeholder="0.0" />
          </label>
          <label class="field-block consumables-stock-value">
            <span>Min stock kg</span>
            <input type="number" name="new_stock_min" value="1.0" step="0.1" />
          </label>
          <div class="micro-panel consumables-stock-meta">
            <strong>Add one extra live stock line</strong>
            <p>Leave this blank if you are only updating the existing coating amounts and thresholds.</p>
          </div>
        </div>
      </div>
      <div class="order-builder-actions">
        <button class="action-btn action-primary" type="submit">Save stock values</button>
      </div>
    </form>
  `;
}

function collapsibleSection(title, content, options = {}) {
  const {
    kind = "default",
    open = false,
    meta = "",
    tone = "neutral",
    className = "",
  } = options;
  return `
    <details class="${`fold-section fold-${kind} fold-tone-${tone} ${className}`.trim()}" ${open ? "open" : ""}>
      <summary class="fold-summary">
        <div class="fold-summary-copy">
          <span>${title}</span>
        </div>
        <div class="fold-summary-right">
          ${meta ? `<div class="fold-summary-meta">${meta}</div>` : ""}
          <div class="fold-summary-toggle">${open ? "Hide" : "Open"}</div>
        </div>
      </summary>
      <div class="fold-body">
        ${content}
      </div>
    </details>
  `;
}

function drawRowsMarkup(rows) {
  return rows
    .map(
      (item, index) => `
        <article class="flow-row">
          <div class="flow-id">Draw ${String(index + 1).padStart(2, "0")}</div>
          <div class="flow-main">
            <div>
              <h3>${item.preform || "Unknown preform"}</h3>
              <p>${item.project || "No project name"} · <span class="status-badge tone-${toneForLabel(item.status)}">${item.status}</span> · ${item.priority}</p>
            </div>
            <div class="flow-value tone-${toneForLabel(item.status)}">${item.length} m</div>
          </div>
        </article>
      `,
    )
    .join("");
}

function scheduleRowsMarkup(items) {
  return items
    .map(
      (item, index) => `
        <article class="event-row">
          <div class="event-index">${String(index + 1).padStart(2, "0")}</div>
          <div class="event-copy">
            <h3><span class="status-badge tone-${toneForLabel(item.event_type)}">${item.event_type}</span></h3>
            <p>${item.description || "No description supplied"}</p>
          </div>
          <div class="event-time">
            <strong>${item.start}</strong>
            <span>${item.duration_hours} h</span>
          </div>
        </article>
      `,
    )
    .join("");
}

function supplyRowsMarkup(items) {
  return items
    .map(
      (item) => `
        <article class="supply-row">
          <div>
            <h3>${item.part_name}</h3>
            <p>${item.details || item.component || "No details"}</p>
          </div>
          <div class="supply-meta">
            <strong class="status-badge tone-${toneForLabel(item.status ?? item.quantity)}">${item.status ?? item.quantity}</strong>
            <span>${item.project || item.company || item.location || "General"}</span>
          </div>
        </article>
      `,
    )
    .join("");
}

function partsFlowStateLabel(item) {
  const status = String(item.status || "").trim();
  const synced = String(item.inventory_synced || "").trim().toLowerCase();
  const receivedState = String(item.received_state || "").trim();
  if (status === "Opened") return "Request opened, not yet sent for approval";
  if (status === "Wait for Approval") return "Waiting for approval decision";
  if (status === "Approved") return "Approved and ready to order";
  if (status === "Ordered") return "Order placed, waiting to receive";
  if (status === "Received") {
    if (synced === "yes") return "Received and inventory-synced";
    if (receivedState === "Waiting for inventory action") return "Received, waiting inventory action";
    return "Received, inventory follow-up needed";
  }
  if (status === "Archived") return "Closed and archived";
  return "Review order state";
}

function partsOrderRowMarkup(item) {
  return `
    <article class="parts-order-row tone-${toneForLabel(item.status)}" data-parts-order-row="${item.index}">
      <div class="parts-order-main">
        <div class="parts-order-head">
          <strong>${item.part_name || "Unnamed part"}</strong>
          <span class="status-badge tone-${toneForLabel(item.status)}">${item.status}</span>
        </div>
        <p>${item.project || "General"}${item.serial_number ? ` · SN ${item.serial_number}` : ""}${item.company ? ` · ${item.company}` : ""}</p>
        <div class="parts-order-flow">${partsFlowStateLabel(item)}</div>
        <div class="parts-order-detail">${item.details || item.maintenance_task || item.maintenance_component || "No details recorded"}</div>
      </div>
      <div class="parts-order-side">
        <span>${item.origin || "General"}</span>
        <button class="mini-action" type="button" data-parts-edit="${item.index}">Edit</button>
      </div>
    </article>
  `;
}

function partsStageActionForOrder(stageKey, item) {
  if (stageKey === "received_pending") return { key: "advance", label: "Close out" };
  return { key: "advance", label: "Move forward" };
}

function partsTargetLabel(status) {
  if (status === "Received") return "Received pending";
  if (status === "Archived") return "Inventory complete";
  return status;
}

function partsStatusRank(status, statusOrder = []) {
  const index = statusOrder.indexOf(status);
  return index === -1 ? -1 : index;
}

function partsAdvanceTargetsForItem(item, stageKey, statusOrder = []) {
  const currentStatus = String(item?.status || "Opened").trim() || "Opened";
  const currentRank = partsStatusRank(currentStatus, statusOrder);
  if (currentRank === -1) return [];
  const laterStatuses = statusOrder.slice(currentRank + 1);
  if (stageKey === "received_pending") {
    return laterStatuses
      .filter((status) => status === "Archived")
      .map((status) => ({ value: status, label: partsTargetLabel(status) }));
  }
  return laterStatuses.map((status) => ({ value: status, label: partsTargetLabel(status) }));
}

function partsStageRowsMarkup(items, stageKey, selectedIds = []) {
  if (!items.length) {
    return `<div class="maintenance-prep-stagepanel-empty">No orders in this stage.</div>`;
  }
  return items
    .map((item) => {
      const action = partsStageActionForOrder(stageKey, item);
      const isSelected = selectedIds.includes(String(item.index));
      return `
        <div class="maintenance-prep-stagepanel-row">
          <div class="maintenance-prep-stagepanel-copy">
            <label class="maintenance-prep-stagepanel-pick">
              <input type="checkbox" data-parts-stage-select="${item.index}" ${isSelected ? "checked" : ""} />
              <span>Select</span>
            </label>
            <strong>${escapeHtml(item.part_name || "Unnamed part")}</strong>
            <span>${escapeHtml(item.project || item.maintenance_component || item.company || "General")}${item.serial_number ? ` · SN ${escapeHtml(item.serial_number)}` : ""}</span>
            <div class="maintenance-prep-stagepanel-rowmeta">
              ${item.maintenance_task ? `<span>${escapeHtml(item.maintenance_task)}</span>` : ""}
              ${item.company ? `<span>${escapeHtml(item.company)}</span>` : ""}
              ${item.received_state ? `<span>${escapeHtml(item.received_state)}</span>` : ""}
            </div>
          </div>
          <div class="maintenance-prep-stagepanel-actions parts-stagepanel-actions-only">
            <button class="maintenance-prep-stagepanel-action" type="button" data-parts-stage-action="${escapeHtml(action.key)}" data-parts-stage-order="${item.index}">${escapeHtml(action.label)}</button>
          </div>
        </div>
      `;
    })
    .join("");
}

function partsStageActionDrawerMarkup(stageKey, stageLabel, items, actionState, statusOrder = [], inventory = null, companyNames = []) {
  if (!actionState?.action || !actionState.orderIds?.length) return "";
  const drawerItems = items.filter((item) => actionState.orderIds.includes(String(item.index)));
  if (!drawerItems.length) return "";
  const first = drawerItems[0];
  const isBulk = actionState.mode === "bulk";
  const targetOptions = partsAdvanceTargetsForItem(first, stageKey, statusOrder);
  if (!targetOptions.length) return "";
  const defaultTarget = targetOptions[0].value;
  const locationOptions = (inventory?.location_names || []).filter(Boolean);
  const companyOptions = (companyNames || []).filter(Boolean);
  const groupedByCompany = drawerItems.reduce((acc, item) => {
    const key = item.company || "No company yet";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const config = {
    eyebrow: isBulk ? "Bulk stage move" : "Advance order",
    title: isBulk ? `Move ${drawerItems.length} orders forward` : `Move ${first.part_name} forward`,
    body: "Choose the target step. The drawer will collect the missing information for each step you skip through.",
    confirm: "Apply stage move",
  };
  return `
    <section class="maintenance-prep-actiondrawer tone-info" data-parts-current-status="${escapeHtml(first.status || "")}">
      <div class="maintenance-prep-actiondrawer-head">
        <div class="maintenance-prep-actiondrawer-copy">
          <span>${escapeHtml(config.eyebrow)}</span>
          <strong>${escapeHtml(config.title)}</strong>
          <p>${escapeHtml(config.body)}</p>
        </div>
        <button class="maintenance-prep-actiondrawer-close" type="button" data-parts-stage-cancel="1">Close</button>
      </div>
      <div class="maintenance-prep-actiondrawer-meta">
        <div class="micro-row"><span>Stage</span><strong>${escapeHtml(stageLabel)}</strong></div>
        <div class="micro-row"><span>Orders</span><strong>${drawerItems.length}</strong></div>
      </div>
      <div class="maintenance-prep-actiondrawer-detail">
        <div class="field-grid parts-drawer-target-grid">
          <label class="field-block">
            <span>Target step</span>
            <select name="targetStatus" data-parts-target-select>
              ${targetOptions.map((option) => `<option value="${escapeHtml(option.value)}"${option.value === defaultTarget ? " selected" : ""}>${escapeHtml(option.label)}</option>`).join("")}
            </select>
          </label>
        </div>
        <div class="field-grid field-grid-2" data-parts-drawer-section-group="wait-for-approval">
          <label class="field-block" data-parts-drawer-section="wait-for-approval">
            <span>Approval requested from</span>
            <input type="text" name="approvalRequestedFrom" value="${escapeHtml(first.approval_requested_from || "")}" placeholder="Manager / buyer / owner" />
          </label>
        </div>
        <div class="field-grid field-grid-2" data-parts-drawer-section="approved">
          <label class="field-block">
            <span>Approved by</span>
            <input type="text" name="approvedBy" value="${escapeHtml(first.approved_by || "")}" placeholder="Approved by" />
          </label>
          <label class="field-block">
            <span>Approval date</span>
            <input type="date" name="approvalDate" value="${escapeHtml(first.approval_date || todayIsoDate())}" />
          </label>
        </div>
        <div class="field-grid field-grid-3" data-parts-drawer-section="ordered">
          <label class="field-block">
            <span>Company</span>
            <input type="text" name="company" value="${escapeHtml(first.company || "")}" placeholder="Supplier company" list="parts-drawer-company-options" />
          </label>
          <label class="field-block">
            <span>Ordered by</span>
            <input type="text" name="orderedBy" value="${escapeHtml(first.ordered_by || "")}" placeholder="Buyer / operator" />
          </label>
          <label class="field-block">
            <span>Date ordered</span>
            <input type="date" name="dateOrdered" value="${escapeHtml(first.date_ordered || todayIsoDate())}" />
          </label>
        </div>
        <div class="field-grid field-grid-2" data-parts-drawer-section="received">
          <label class="field-block">
            <span>Received date</span>
            <input type="date" name="receivedDate" value="${escapeHtml(first.received_date || todayIsoDate())}" />
          </label>
          <div class="field-block" data-parts-drawer-section="archived">
            <span>Closeout</span>
            <p class="field-note">Choose storage or mounted result below.</p>
          </div>
        </div>
        <div class="parts-drawer-closeout-focus" data-parts-drawer-closeout hidden>
          <label class="field-block">
            <span>Inventory result</span>
            <select name="inventoryAction">
              <option value="">Choose inventory result</option>
              <option value="Locate in inventory"${first.received_state === "Located in inventory" ? " selected" : ""}>Locate in inventory</option>
              <option value="Mount on machine"${first.received_state === "Mounted on machine" ? " selected" : ""}>Mount on tower</option>
            </select>
          </label>
          <div class="field-grid field-grid-3">
            <label class="field-block" data-parts-drawer-location-wrap hidden>
              <span data-parts-drawer-location-label>Storage place</span>
              <input type="text" name="inventoryLocation" value="" list="parts-drawer-location-options" placeholder="Choose storage location" />
            </label>
            <label class="field-block" data-parts-drawer-closeout-extra hidden>
              <span>Quantity to close out</span>
              <input type="number" min="0.01" step="0.1" name="inventoryQuantity" value="1" />
            </label>
          </div>
          <div class="field-grid field-grid-3" data-parts-drawer-closeout-extra hidden>
            <label class="field-block">
              <span>Item type</span>
              <select name="inventoryItemType">
                <option value="Part">Part</option>
                <option value="Tool">Tool</option>
                <option value="Consumable">Consumable</option>
              </select>
            </label>
            <label class="field-block">
              <span>Inventory component</span>
              <input type="text" name="inventoryComponent" value="${escapeHtml(first.maintenance_component || "Tower Parts")}" placeholder="Inventory component" />
            </label>
            <label class="field-block">
              <span>Inventory note</span>
              <input type="text" name="inventoryNotes" value="" placeholder="Closeout note" />
            </label>
          </div>
          <input type="hidden" name="inventoryMatchIndex" value="" />
          <div class="parts-drawer-match-shell" data-parts-drawer-match-shell hidden>
            <div class="chart-head">
              <span>Existing inventory matches</span>
              <strong data-parts-drawer-match-summary>Choose an existing row to add stock there.</strong>
            </div>
            <div class="parts-drawer-match-list" data-parts-drawer-match-suggestions></div>
          </div>
        </div>
        ${isBulk ? `
        <div class="maintenance-prep-actiondrawer-groupbox">
          <span>Selected companies</span>
          <div class="token-strip">
            ${Object.entries(groupedByCompany).map(([label, count]) => `<span class="token-chip">${escapeHtml(label)} · ${count}</span>`).join("")}
          </div>
        </div>` : ""}
        ${isBulk ? `
        <div class="maintenance-prep-actiondrawer-tasklist">
          ${drawerItems.map((item) => `
            <div class="maintenance-prep-actiondrawer-taskrow">
              <strong>${escapeHtml(item.part_name || "Unnamed part")}</strong>
              <div class="maintenance-prep-actiondrawer-rowmeta">
                ${item.project ? `<span>${escapeHtml(item.project)}</span>` : ""}
                ${item.company ? `<span>${escapeHtml(item.company)}</span>` : ""}
                ${item.maintenance_task ? `<span>${escapeHtml(item.maintenance_task)}</span>` : ""}
              </div>
            </div>
          `).join("")}
        </div>` : ""}
        <datalist id="parts-drawer-location-options">${locationOptions.map((item) => `<option value="${escapeHtml(item)}"></option>`).join("")}</datalist>
        <datalist id="parts-drawer-company-options">${companyOptions.map((item) => `<option value="${escapeHtml(item)}"></option>`).join("")}</datalist>
      </div>
      <div class="maintenance-prep-actiondrawer-actions">
        <button class="action-btn action-secondary" type="button" data-parts-stage-cancel="1">Cancel</button>
        <button class="action-btn action-primary" type="button" data-parts-stage-confirm="advance">${escapeHtml(config.confirm)}</button>
      </div>
    </section>
  `;
}

function partsStageFlowMarkup(data, activeStageKey = "", actionState = null, stageFlash = null, selectedIds = []) {
  const stageDefs = [
    { key: "opened", label: "Opened", tone: "prep", count: Number(data.status_counts.Opened || 0), items: (data.all_orders || []).filter((item) => item.status === "Opened"), bulkAction: "advance-all" },
    { key: "approval", label: "Wait for approval", tone: "blocked", count: Number(data.queue_counts.approval || 0), items: data.queues?.approval || [], bulkAction: "advance-all" },
    { key: "approved", label: "Ready to order", tone: "execute", count: Number(data.queue_counts.approved || 0), items: data.queues?.approved || [], bulkAction: "advance-all" },
    { key: "ordered", label: "Ordered", tone: "schedule", count: Number(data.queue_counts.ordered || 0), items: data.queues?.ordered || [], bulkAction: "advance-all" },
    { key: "received_pending", label: "Received pending", tone: "warn", count: Number(data.queue_counts.received_pending || 0), items: data.queues?.received_pending || [], bulkAction: "advance-all" },
  ];
  const selectedStage = stageDefs.find((stage) => stage.key === activeStageKey) || null;
  const selectedStageKey = selectedStage?.key || "";
  const allStageIdList = selectedStage ? selectedStage.items.map((item) => String(item.index)) : [];
  const selectedStageIds = allStageIdList.filter((id) => selectedIds.includes(id));
  const allStageIds = allStageIdList.join(",");
  const allSelected = Boolean(allStageIdList.length) && selectedStageIds.length === allStageIdList.length;
  const hasPartialSelection = selectedStageIds.length > 0 && !allSelected;
  const rowsMarkup = selectedStage ? partsStageRowsMarkup(selectedStage.items, selectedStage.key, selectedIds) : "";
  return `
    <section class="parts-stage-shell">
      <div class="section-heading minimal">
        <span>Orders flow</span>
        <h3>One stage line, one action surface</h3>
      </div>
      <div class="maintenance-prep-stageflow">
        <div class="maintenance-prep-stageplot maintenance-prep-stageplot-parts">
          ${stageDefs.map((stage, index) => `
            <button
              class="maintenance-prep-stage-dot tone-${stage.tone} ${selectedStageKey === stage.key ? "is-active" : ""}"
              type="button"
              data-parts-stage="${escapeHtml(stage.key)}"
              aria-pressed="${selectedStageKey === stage.key ? "true" : "false"}"
            >
              <span class="maintenance-prep-stage-bullet">${stage.count}</span>
              <strong>${escapeHtml(stage.label)}</strong>
              ${index < stageDefs.length - 1 ? `<i class="maintenance-prep-stage-link"></i>` : ""}
            </button>
          `).join("")}
        </div>
        ${selectedStage ? `
        <section class="maintenance-prep-stagepanel tone-${selectedStage.tone}">
          <div class="maintenance-prep-stagepanel-head">
            <div class="maintenance-prep-stagepanel-head-copy">
              <span>${escapeHtml(selectedStage.label)}</span>
              <strong>${selectedStage.count ? `${selectedStage.count} orders in this stage` : "No orders in this stage"}</strong>
            </div>
            ${selectedStage.items.length ? `
            <div class="maintenance-prep-stagepanel-head-actions">
              <label class="maintenance-prep-stagepanel-pick maintenance-prep-stagepanel-pick-head">
                <input
                  type="checkbox"
                  data-parts-stage-select-all="1"
                  data-parts-stage-order-ids="${escapeHtml(allStageIds)}"
                  data-parts-stage-indeterminate="${hasPartialSelection ? "true" : "false"}"
                  ${allSelected ? "checked" : ""}
                />
                <span>Select all</span>
              </label>
              <button class="maintenance-prep-stagepanel-bulk" type="button" data-parts-stage-bulk="${escapeHtml(selectedStage.bulkAction)}" data-parts-stage-order-ids="${escapeHtml(selectedStageIds.length ? selectedStageIds.join(",") : allStageIds)}">${escapeHtml(partsStageActionForOrder(selectedStage.key, selectedStage.items[0]).label)} ${selectedStageIds.length ? "selected" : "all"}</button>
            </div>` : ""}
          </div>
          ${stageFlash?.message ? `<div class="maintenance-prep-stageflash tone-${escapeHtml(stageFlash.kind || "info")}">${escapeHtml(stageFlash.message)}</div>` : ""}
          <div class="maintenance-prep-stagepanel-body">
            ${rowsMarkup}
          </div>
        </section>` : ""}
        ${selectedStage ? partsStageActionDrawerMarkup(selectedStage.key, selectedStage.label, selectedStage.items, actionState, data.status_order || [], data.inventory, data.company_names || []) : ""}
      </div>
    </section>
  `;
}

function partsInventoryRowMarkup(item) {
  return `
    <article class="parts-inventory-row">
      <div>
        <strong>${item.part_name || "Unnamed part"}</strong>
        <p>${item.component || "General"} · ${item.location || "No location"}</p>
      </div>
      <div class="parts-inventory-side">
        <span class="status-badge tone-${toneForLabel(`low stock ${item.quantity}`)}">${item.quantity}/${item.min_level}</span>
      </div>
    </article>
  `;
}

function partsManualDisplayName(name) {
  return String(name || "")
    .replace(/\.pdf$/i, "")
    .replace(/_/g, " ")
    .trim() || "Manual";
}

function partsManualWorkbenchShellMarkup(data) {
  const manualLookup = data.manual_lookup || {};
  const manualCount = Number(manualLookup.manual_count ?? manualLookup.totals?.manual_count ?? 0);
  const indexedRowCount = Number(manualLookup.row_count ?? manualLookup.totals?.row_count ?? 0);
  return `
    <section class="parts-inventory-browser parts-manual-browser" id="parts-manual-browser">
      <div class="section-heading minimal">
        <span>Manual browser</span>
        <h3>Find part, manual page, and storage place</h3>
        <p>Search once, keep only the useful hits in view, then move page by page through the manual with the page-scoped parts list beside it.</p>
      </div>
      <div class="parts-manual-command-deck">
        <div class="parts-manual-browser-top">
          <div class="parts-manual-mode-cluster">
            <span class="parts-manual-control-kicker">Lookup flow</span>
            <div class="parts-manual-mode-strip" role="tablist" aria-label="Parts lookup mode">
              <button class="parts-manual-mode-btn is-active" type="button" data-parts-manual-mode="part">Part to manual</button>
              <button class="parts-manual-mode-btn" type="button" data-parts-manual-mode="manual">Manual to parts</button>
            </div>
          </div>
          <div class="metric-row compact parts-manual-metrics">
            <div class="metric-pill tone-info"><span>Tracked parts</span><strong>${data.inventory.tracked_parts}</strong></div>
            <div class="metric-pill tone-bad"><span>Low stock</span><strong>${data.inventory.low_stock_total || data.inventory.low_stock.length}</strong></div>
            <div class="metric-pill tone-info"><span>Manuals</span><strong id="parts-manual-metric-manuals">${manualCount}</strong></div>
            <div class="metric-pill tone-info"><span>Indexed rows</span><strong id="parts-manual-metric-rows">${indexedRowCount}</strong></div>
          </div>
        </div>
        <div class="parts-manual-toolbar">
          <label class="parts-manual-search-wrap parts-manual-control-card">
            <span>Smart search</span>
            <strong>Search the indexed manual layer</strong>
            <p>Use part names, numbers, serials, or component hints.</p>
            <input class="parts-search-input" id="parts-manual-search" placeholder="Search part / part number / serial / component / location..." />
          </label>
          <label class="parts-manual-select-wrap parts-manual-control-card" data-parts-manual-panel="manual-focus">
            <span>Manual focus</span>
            <strong>Lock the search to one document</strong>
            <p>Useful when you already know which system manual you want.</p>
            <select id="parts-manual-select">
              <option value="">All manuals</option>
            </select>
          </label>
        </div>
      </div>
      <div class="parts-manual-grid">
        <section class="parts-manual-viewer">
          <div class="parts-manual-viewer-head">
            <div class="parts-manual-viewer-copy">
              <span>Manual viewer</span>
              <strong id="parts-manual-viewer-title">Search or pick a page</strong>
              <p id="parts-manual-viewer-meta">Search a part, open the matching manual page, or move page by page through a manual without leaving the parts page.</p>
            </div>
            <div class="parts-manual-viewer-actions">
              <a class="mini-action" id="parts-manual-open-doc" href="#" target="_blank" rel="noopener noreferrer">Open PDF</a>
              <button class="mini-action" type="button" id="parts-manual-prev">Prev page</button>
              <span id="parts-manual-page-status">Page —</span>
              <button class="mini-action" type="button" id="parts-manual-next">Next page</button>
              <button class="mini-action" type="button" id="parts-manual-zoom-out" aria-label="Zoom out">-</button>
              <span id="parts-manual-zoom-status">100%</span>
              <button class="mini-action" type="button" id="parts-manual-zoom-in" aria-label="Zoom in">+</button>
              <button class="mini-action" type="button" id="parts-manual-zoom-reset">Reset</button>
            </div>
          </div>
          <div class="parts-manual-page-strip" id="parts-manual-page-strip">
            <div class="chart-empty">Indexed pages will appear here when a manual is open.</div>
          </div>
          <div class="parts-manual-viewer-stage">
            <div class="parts-manual-frame-shell" id="parts-manual-frame-shell">
              <div class="chart-empty">Search a part or pick a manual page to render the document here.</div>
            </div>
            <div class="parts-manual-page-shell">
              <div class="chart-head">
                <span>Page rows</span>
                <strong id="parts-manual-page-title">Rows on the selected page</strong>
              </div>
              <div class="parts-manual-results-list is-page-list" id="parts-manual-page-results">
                <div class="chart-empty">Page rows will appear here after you open a manual page.</div>
              </div>
            </div>
          </div>
        </section>
        <div class="parts-manual-support">
          <section class="parts-manual-card" data-parts-manual-panel="manual-hits">
            <div class="chart-head">
              <span id="parts-manual-results-kicker">Manual hits</span>
              <strong id="parts-manual-results-heading">Smart from manuals</strong>
            </div>
            <div class="parts-manual-results-list" id="parts-manual-match-results">
              <div class="chart-empty">Loading the manual index…</div>
            </div>
          </section>
          <section class="parts-manual-card" data-parts-manual-panel="inventory">
            <div class="chart-head">
              <span>Inventory hits</span>
              <strong>Storage + live stock match</strong>
            </div>
            <div class="parts-manual-results-list" id="parts-manual-inventory-results">
              <div class="chart-empty">Type a part, serial, component, or location to narrow inventory results.</div>
            </div>
          </section>
        </div>
      </div>
    </section>
  `;
}

function partsInventoryActionMarkup(locationOptions, supplierOptions, inventoryRows = []) {
  const inventoryEditOptions = inventoryRows
    .map((item, index) => {
      const quantity = Number(item.quantity || 0);
      const quantityLabel = Number.isInteger(quantity) ? String(quantity) : quantity.toFixed(1).replace(/\.0$/, "");
      const parts = [
        item.part_name || "Unnamed part",
        item.serial_number ? `SN ${item.serial_number}` : "",
        item.location || "No location",
        `Qty ${quantityLabel}`,
      ].filter(Boolean);
      return `<option value="${index}">${escapeHtml(parts.join(" · "))}</option>`;
    })
    .join("");
  return `
    <form class="parts-form-grid" id="parts-inventory-form">
      <label><span>Mode</span><select name="mode"><option value="add">Add Stock</option><option value="use">Use Stock</option><option value="new">New Part Row</option><option value="edit">Edit Part Row</option></select></label>
      <label class="parts-form-span is-hidden" data-parts-inventory-edit-pick>
        <span>Edit Inventory Row</span>
        <select name="inventoryEditIndex">
          <option value="">Choose inventory row...</option>
          ${inventoryEditOptions}
        </select>
      </label>
      <label class="parts-inventory-smart-field">
        <span>Part Name</span>
        <div class="parts-inventory-smart-shell">
          <input name="partName" autocomplete="off" placeholder="Search part / serial / component / tool / location..." data-parts-inventory-smart-input="1" required />
          <div class="maintenance-parts-suggestions parts-inventory-smart-results" data-parts-inventory-suggestions hidden></div>
        </div>
      </label>
      <label><span>Serial Number</span><input name="serialNumber" /></label>
      <label><span>Quantity</span><input name="quantity" type="number" min="0.01" step="0.1" value="1" /></label>
      <label class="parts-inventory-smart-field">
        <span>Component</span>
        <div class="parts-inventory-smart-shell">
          <input name="component" autocomplete="off" placeholder="Choose existing component..." data-parts-inventory-component-input="1" />
          <div class="maintenance-parts-suggestions parts-inventory-smart-results parts-inventory-component-results" data-parts-inventory-component-suggestions hidden></div>
        </div>
      </label>
      <label><span>Supplier</span><input name="supplier" list="parts-inventory-supplier-options" placeholder="Supplier / vendor" /></label>
      <label><span>Item Type</span><select name="itemType"><option>Part</option><option>Tool</option><option>Consumable</option></select></label>
      <label><span>Location</span><input name="location" list="parts-location-options" /></label>
      <label><span>Min Level</span><input name="minLevel" type="number" min="0" step="0.1" value="0" /></label>
      <label class="parts-form-span"><span>Notes</span><textarea name="notes" rows="3"></textarea></label>
      <div class="parts-form-actions parts-form-span">
        <button class="action-btn action-primary" type="submit">Apply Inventory Action</button>
      </div>
    </form>
  `;
}

function partsManageFormMarkup(data) {
  const projectOptions = data.project_names.map((item) => `<option value="${item}">${item}</option>`).join("");
  const companyOptions = data.company_names.map((item) => `<option value="${item}">${item}</option>`).join("");
  return `
    <section class="parts-manage-shell parts-workbench">
      <details class="fold-section fold-panel parts-manual-entry-fold" data-parts-manual-fold="1" data-fold-open-label="Open form" data-fold-close-label="Hide form">
        <summary class="fold-summary">
          <div class="fold-summary-copy">
            <span>Manual add</span>
            <strong>Create new part order</strong>
            <em>Fast entry for general requests and supplier orders.</em>
          </div>
          <div class="fold-summary-right">
            <span class="fold-summary-toggle">Open form</span>
          </div>
        </summary>
        <div class="fold-content">
          <form class="parts-form-grid parts-create-smart-form" id="parts-create-form">
            <label class="parts-form-span">
              <span>Start Status</span>
              <select name="status" data-parts-create-status>
                <option value="Opened">Opened</option>
                <option value="Wait for Approval">Wait for approval</option>
                <option value="Approved">Approved</option>
                <option value="Ordered">Ordered</option>
                <option value="Received">Received</option>
              </select>
            </label>
            <div class="parts-create-stage-note parts-form-span" data-parts-create-stage-note>
              <strong>Start at Opened</strong>
              <span>Save a basic request first, then move it through approval and purchasing when that data exists.</span>
            </div>
            <label><span>Part Name</span><input name="partName" required /></label>
            <label><span>Serial Number</span><input name="serialNumber" /></label>
            <label><span>Opened By</span><input name="openedBy" /></label>
            <label><span>Project</span><input name="project" list="parts-project-options" /></label>
            <label class="is-hidden" data-parts-create-stage="wait"><span>Approval Requested From</span><input name="approvalRequestedFrom" /></label>
            <label class="is-hidden" data-parts-create-stage="approved"><span>Approved By</span><input name="approvedBy" /></label>
            <label class="is-hidden" data-parts-create-stage="approved"><span>Approval Date</span><input name="approvalDate" type="date" value="${todayIsoDate()}" /></label>
            <label class="is-hidden" data-parts-create-stage="ordered"><span>Company</span><input name="company" list="parts-company-options" /></label>
            <label class="is-hidden" data-parts-create-stage="ordered"><span>Ordered By</span><input name="orderedBy" /></label>
            <label class="is-hidden" data-parts-create-stage="ordered"><span>Date Ordered</span><input name="dateOrdered" type="date" value="${todayIsoDate()}" /></label>
            <label class="is-hidden" data-parts-create-stage="received"><span>Received Date</span><input name="receivedDate" type="date" value="${todayIsoDate()}" /></label>
            <label class="parts-form-span"><span>Details</span><textarea name="details" rows="4"></textarea></label>
            <div class="parts-form-actions parts-form-span">
              <button class="action-btn action-primary" type="submit">Save Part Order</button>
            </div>
          </form>
          <datalist id="parts-project-options">${projectOptions}</datalist>
          <datalist id="parts-company-options">${companyOptions}</datalist>
        </div>
      </details>
    </section>
  `;
}

function partsQuickInventoryMarkup(data) {
  const locationOptions = (data.inventory.location_names || []).filter(Boolean);
  const supplierOptions = dedupeStrings([
    ...(data.company_names || []),
    ...((data.inventory.inventory_rows || []).map((item) => item.supplier)),
  ]);
  return `
    <section class="parts-inventory-wide-shell is-single-column">
      <div class="parts-manage-shell parts-inventory-main">
        <div class="section-heading minimal">
          <span>General inventory</span>
          <h3>Stock action workbench</h3>
          <p>Handle stock changes here, including new rows, inventory edits, and location updates.</p>
        </div>
        ${collapsibleSection(
          "Inventory action",
          partsInventoryActionMarkup(locationOptions, supplierOptions, data.inventory.inventory_rows || []),
          { kind: "panel", meta: "Add, edit, or use stock", open: false },
        )}
        <datalist id="parts-inventory-supplier-options">${supplierOptions.map((item) => `<option value="${escapeHtml(item)}"></option>`).join("")}</datalist>
        <datalist id="parts-location-options">${locationOptions.map((item) => `<option value="${item}"></option>`).join("")}</datalist>
      </div>
      ${partsManualWorkbenchShellMarkup(data)}
    </section>
  `;
}

function normalizeLookupText(value) {
  return String(value || "").toLowerCase().replace(/\s+/g, " ").trim();
}

function scoreLookupMatch(haystack, query) {
  if (!query) return 0;
  const source = normalizeLookupText(haystack);
  if (!source) return 0;
  if (source === query) return 120;
  if (source.startsWith(query)) return 90;
  if (source.includes(` ${query}`)) return 72;
  if (source.includes(query)) return 56;
  return 0;
}

function partsManualInventoryResultMarkup(item) {
  const locationBits = [item.component || "General", item.location || "No location", item.location_serial || ""].filter(Boolean);
  return `
    <button class="parts-manual-result is-inventory" type="button" data-parts-manual-fill-query="${escapeHtml(item.part_name || "")}">
      <div class="parts-manual-result-copy">
        <strong>${escapeHtml(item.part_name || "Unnamed part")}</strong>
        <p>${escapeHtml(locationBits.join(" · "))}</p>
        ${item.notes ? `<p>${escapeHtml(item.notes)}</p>` : ""}
      </div>
      <div class="parts-manual-result-side">
        <span class="status-badge tone-${item.quantity <= item.min_level ? "bad" : "good"}">Qty ${escapeHtml(String(item.quantity))}</span>
        ${item.serial_number ? `<span class="status-badge tone-info">SN ${escapeHtml(item.serial_number)}</span>` : ""}
      </div>
    </button>
  `;
}

function partsManualMatchResultMarkup(item, activeKey = "") {
  const key = `${item.manual}::${item.page}::${item.item || item.part_number || item.part}`;
  return `
    <button class="parts-manual-result is-manual ${key === activeKey ? "is-active" : ""}" type="button" data-parts-manual-open="${escapeHtml(key)}">
      <div class="parts-manual-result-copy">
        <strong>${escapeHtml(item.part || "Part row")}</strong>
        <p>${escapeHtml(partsManualDisplayName(item.manual))}</p>
        <p>${escapeHtml(item.part_number || "No part number")} ${item.qty_per_assembly ? `· Qty/Asm ${escapeHtml(String(item.qty_per_assembly))}` : ""}</p>
      </div>
      <div class="parts-manual-result-side">
        <span class="status-badge tone-info">p.${escapeHtml(String(item.page || 1))}</span>
        ${item.item ? `<span class="status-badge tone-neutral">Item ${escapeHtml(String(item.item))}</span>` : ""}
      </div>
    </button>
  `;
}

function partsManualPageSummaryMarkup(pageNumber, rows, currentPage, matchedCount = 0) {
  const preview = rows
    .slice(0, 3)
    .map((row) => row.part || row.part_number || row.raw_line || "")
    .filter(Boolean)
    .join(" · ");
  return `
    <button class="parts-manual-result is-page-summary ${currentPage === pageNumber ? "is-active" : ""}" type="button" data-parts-manual-page="${escapeHtml(String(pageNumber))}">
      <div class="parts-manual-result-copy">
        <strong>Page ${escapeHtml(String(pageNumber))}</strong>
        <p>${escapeHtml(String(rows.length))} indexed rows${matchedCount ? ` · ${escapeHtml(String(matchedCount))} matched` : ""}</p>
        <p>${escapeHtml(preview || "Indexed BOM rows on this page")}</p>
      </div>
      <div class="parts-manual-result-side">
        <span class="status-badge tone-info">${escapeHtml(String(pageNumber))}</span>
      </div>
    </button>
  `;
}

function partsManualDocumentItemMarkup(manual, active = false, matchedCount = 0) {
  return `
    <button class="parts-manual-result is-document ${active ? "is-active" : ""}" type="button" data-parts-manual-pick="${escapeHtml(manual.name || "")}">
      <div class="parts-manual-result-copy">
        <strong>${escapeHtml(partsManualDisplayName(manual.name))}</strong>
        <p>${escapeHtml(String(manual.pages || 0))} pages · ${escapeHtml(String(manual.row_count || 0))} indexed rows</p>
        <p>${escapeHtml(String((manual.bom_pages || []).length || 0))} BOM pages ${matchedCount ? `· ${escapeHtml(String(matchedCount))} matched` : ""}</p>
      </div>
      <div class="parts-manual-result-side">
        <span class="status-badge tone-info">${escapeHtml(String(manual.pages || 0))}p</span>
      </div>
    </button>
  `;
}

function partsManualPageChipMarkup(group, currentPage, viewMode) {
  const isCurrent = group.pageNumber === currentPage;
  const chipState = isCurrent ? (viewMode === "page" ? "is-active" : "is-context") : "";
  return `
    <button class="parts-manual-page-chip ${chipState} ${group.matchedCount ? "has-match" : ""}" type="button" data-parts-manual-page="${escapeHtml(String(group.pageNumber))}">
      <span>p.${escapeHtml(String(group.pageNumber))}</span>
      <strong>${escapeHtml(String(group.rows.length))}</strong>
    </button>
  `;
}

function partsManualPageRowMarkup(row, inventoryStatus = null) {
  const mountedLine = inventoryStatus?.mounted
    ? `<p class="parts-manual-page-context">Mounted on ${escapeHtml(inventoryStatus.mounted.componentLabel)} · Qty ${escapeHtml(inventoryStatus.mounted.quantityLabel)}</p>`
    : "";
  const storedLines = (inventoryStatus?.stored || [])
    .map((item) => `<p class="parts-manual-page-context">Stored in ${escapeHtml(item.locationLabel)} · Qty ${escapeHtml(item.quantityLabel)}</p>`)
    .join("");
  const overflowLine = inventoryStatus?.extraStoredCount
    ? `<p class="parts-manual-page-context">More stored locations · ${escapeHtml(String(inventoryStatus.extraStoredCount))}</p>`
    : "";
  return `
    <article class="parts-manual-page-row">
      <div class="parts-manual-result-copy">
        <strong>${escapeHtml(row.part || "Part row")}</strong>
        <p>${escapeHtml(row.part_number || "No part number")}</p>
        ${mountedLine}
        ${storedLines}
        ${overflowLine}
      </div>
      <div class="parts-manual-result-side">
        ${row.item ? `<span class="status-badge tone-info">Item ${escapeHtml(String(row.item))}</span>` : ""}
        ${row.qty_per_assembly ? `<span class="status-badge tone-good">Qty/Asm ${escapeHtml(String(row.qty_per_assembly))}</span>` : ""}
      </div>
    </article>
  `;
}

function maintenanceTaskRowMarkup(item) {
  return `
    <article class="maintenance-task-row tone-${toneForLabel(item.status)}" data-maint-task="${item.task_id}">
      <div class="maintenance-task-main">
        <div class="maintenance-task-head">
          <strong>${item.component}</strong>
          <span class="status-badge tone-${toneForLabel(item.status)}">${item.status}</span>
        </div>
        <h3>${item.task}</h3>
        <p>${item.task_group || "General"} · ${item.tracking_mode || "Unknown"} · ${item.task_id}</p>
        <div class="maintenance-task-flow">${item.flow_state}</div>
        ${item.wait_note ? `<div class="maintenance-task-note">${item.wait_note}</div>` : ""}
      </div>
      <div class="maintenance-task-side">
        <button class="mini-action" type="button" data-maint-select="${item.task_id}">Focus</button>
      </div>
    </article>
  `;
}

function maintenanceDetailMarkup(item) {
  if (!item) {
    return `<div class="chart-empty">Select a maintenance task to inspect and act on it.</div>`;
  }
  return `
    <div class="maintenance-detail-head">
      <span>${item.component}</span>
      <strong>${item.task}</strong>
      <em>${item.task_id}</em>
    </div>
    <div class="metric-row compact">
      <div class="metric-pill tone-${toneForLabel(item.status)}"><span>Status</span><strong>${item.status}</strong></div>
      <div class="metric-pill tone-${toneForLabel(item.flow_state)}"><span>Flow</span><strong>${item.flow_state}</strong></div>
      <div class="metric-pill tone-info"><span>Mode</span><strong>${item.tracking_mode || "—"}</strong></div>
      <div class="metric-pill tone-warn"><span>Linked Orders</span><strong>${item.linked_open_count || 0}</strong></div>
    </div>
    <div class="maintenance-detail-copy">
      <p>${item.procedure_summary || "No procedure summary stored for this task yet."}</p>
      <p>${item.safety_notes || "No safety notes stored."}</p>
      ${item.wait_note ? `<p>${item.wait_note}</p>` : ""}
    </div>
    <div class="metric-row compact">
      <div class="metric-pill tone-good"><span>Ready In Stock</span><strong>${(item.required_parts || []).length - (item.missing_parts || []).length}</strong></div>
      <div class="metric-pill tone-bad"><span>Missing</span><strong>${(item.missing_parts || []).length}</strong></div>
      <div class="metric-pill tone-info"><span>Received Pending Sync</span><strong>${item.linked_received_waiting_sync || 0}</strong></div>
      <div class="metric-pill tone-good"><span>Synced Ready</span><strong>${item.linked_ready_count || 0}</strong></div>
    </div>
    <div class="maintenance-parts-block">
      <span>Required Parts</span>
      <div class="token-strip">
        ${(item.required_parts || []).length
          ? item.required_parts.map((part) => `<span class="token-chip ${item.missing_parts.includes(part) ? "" : "is-accent"}">${part}</span>`).join("")
          : `<span class="token-chip">No required parts</span>`}
      </div>
    </div>
    <div class="maintenance-linked-orders">
      <span>Linked part orders</span>
      <div class="stack-list">
        ${(item.linked_orders || []).length
          ? item.linked_orders.map((order) => `<div class="micro-row"><span>${order.part_name}</span><strong>${order.status}</strong></div>`).join("")
          : `<div class="chart-empty">No linked part orders.</div>`}
      </div>
    </div>
  `;
}

function maintenanceTimelineMarkup(events, emptyMessage) {
  if (!events?.length) {
    return `<div class="chart-empty">${emptyMessage}</div>`;
  }
  return `
    <div class="maintenance-mini-timeline">
      ${events
        .map(
          (item) => `
            <div class="maintenance-mini-event">
              <span>${item.date_label || item.start_label || "Upcoming"}</span>
              <strong>${item.event_type || "Maintenance"}</strong>
              <em>${item.description || "No description"}</em>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function maintenancePrepHorizonMarkup(events, emptyMessage, data = null, selectedTaskId = "", cutoffProgress = "", prepProgress = "", focusLaneKey = "", horizonProgress = "", horizonFoldOpen = false, activeStageKey = "need-prep", actionState = null, selectedReadyTaskIds = []) {
  if (!events?.length) {
    return `<div class="chart-empty">${emptyMessage}</div>`;
  }
  return `
    <div class="maintenance-horizon-timeline">
      ${data ? maintenancePrepHorizonPlotMarkup(data, selectedTaskId, parseMaintenancePrepCutoffMap(cutoffProgress), parseMaintenancePrepCutoffMap(prepProgress), focusLaneKey, parseMaintenancePrepHorizonMap(horizonProgress), horizonFoldOpen, activeStageKey, actionState, selectedReadyTaskIds) : maintenanceTimelineMarkup(events.slice(0, 6), emptyMessage)}
    </div>
  `;
}

function maintenanceDueRowsMarkup(item) {
  if (!item) {
    return `<div class="micro-panel">Choose a task to see its due window.</div>`;
  }
  const rows = [];
  if (item.next_due_hours !== "" && item.next_due_hours !== null && item.next_due_hours !== undefined) {
    rows.push(`<div class="micro-row"><span>${item.hours_source || "Hours"}</span><strong>${item.next_due_hours}</strong></div>`);
  }
  if (item.next_due_draw) {
    rows.push(`<div class="micro-row"><span>Draw due</span><strong>${item.next_due_draw}</strong></div>`);
  }
  if (item.next_due_date) {
    rows.push(`<div class="micro-row"><span>Date due</span><strong>${item.next_due_date}</strong></div>`);
  }
  if (item.timing_status) {
    rows.push(`<div class="micro-row"><span>Status</span><strong>${item.timing_status}</strong></div>`);
  }
  return rows.length ? rows.join("") : `<div class="micro-panel">No due markers were found for this task yet.</div>`;
}

function maintenanceTextListMarkup(value, emptyMessage) {
  const lines = parseChecklistSeedItems(value, "view")
    .map((item) => String(item?.text || "").trim())
    .filter(Boolean);
  if (!lines.length) {
    return `<div class="micro-panel">${emptyMessage}</div>`;
  }
  return `
    <div class="maintenance-compact-list">
      ${lines.map((line, index) => `<div class="maintenance-compact-list-row"><span>${index + 1}</span><strong>${escapeHtml(line)}</strong></div>`).join("")}
    </div>
  `;
}

function maintenancePartsGateMarkup(item) {
  if (!item) {
    return `<div class="micro-panel">Choose a task to inspect parts readiness.</div>`;
  }
  return `
    <div class="maintenance-mini-grid">
      <div class="micro-panel blocky">
        <strong>Required</strong>
        <p>${(item.required_parts || []).length || 0} parts linked to this task.</p>
      </div>
      <div class="micro-panel blocky">
        <strong>Missing</strong>
        <p>${(item.missing_parts || []).length || 0} still not in stock.</p>
      </div>
      <div class="micro-panel blocky">
        <strong>Linked Orders</strong>
        <p>${item.linked_open_count || 0} open order rows are connected.</p>
      </div>
      <div class="micro-panel blocky">
        <strong>Ready</strong>
        <p>${item.linked_ready_count || 0} rows already synced back to inventory.</p>
      </div>
    </div>
    <div class="token-strip">
      ${(item.required_parts || []).length
        ? item.required_parts.map((part) => `<span class="token-chip ${item.missing_parts.includes(part) ? "" : "is-accent"}">${part}</span>`).join("")
        : `<span class="token-chip">No required parts</span>`}
    </div>
  `;
}

function maintenancePlanStageMarkup(task) {
  return `
    <div class="maintenance-lane-board">
      <div class="maintenance-lane-board-head">
        <span>Prep workspace</span>
        <strong>${task?.task || "No task selected"}</strong>
      </div>
      <div class="maintenance-lane-board-grid">
        <section class="maintenance-lane-card">
          <div class="chart-head">
            <span>Package readiness</span>
            <strong>${task?.work_package?.last_updated ? "Saved package" : "Package still needed"}</strong>
          </div>
          <div class="micro-list">
            <div class="micro-row"><span>Last update</span><strong>${task?.work_package?.last_updated || "Never"}</strong></div>
            <div class="micro-row"><span>Updated by</span><strong>${task?.work_package?.updated_by || "Unknown"}</strong></div>
            <div class="micro-row"><span>Estimated stop</span><strong>${task?.work_package?.est_stop_min || task?.est_duration_min || "—"} min</strong></div>
          </div>
        </section>
        <section class="maintenance-lane-card">
          <div class="chart-head">
            <span>Due window</span>
            <strong>${task?.component || "Selected task"}</strong>
          </div>
          <div class="micro-list">
            ${maintenanceDueRowsMarkup(task)}
          </div>
        </section>
      </div>
      <section class="maintenance-lane-card">
        <div class="chart-head">
          <span>Preparation checklist</span>
          <strong>What the shift should prepare next</strong>
        </div>
        ${maintenanceTextListMarkup(task?.work_package?.preparation_checklist, "No preparation checklist is saved yet for this task.")}
      </section>
      <section class="maintenance-lane-card">
        <div class="chart-head">
          <span>Parts gate</span>
          <strong>Inventory and linked orders</strong>
        </div>
        ${maintenancePartsGateMarkup(task)}
      </section>
    </div>
  `;
}

function maintenanceExecuteStageMarkup(task) {
  return `
    <div class="maintenance-lane-board maintenance-lane-board-execute">
      <div class="maintenance-lane-board-head">
        <span>Execution workspace</span>
        <strong>${task?.task || "No task selected"}</strong>
      </div>
      <div class="maintenance-execute-band">
        <div class="maintenance-focus-stat tone-${toneForLabel(task?.status)}">
          <span>Status</span>
          <strong>${task?.status || "Task state"}</strong>
        </div>
        <div class="maintenance-focus-stat tone-info">
          <span>Tracking mode</span>
          <strong>${task?.tracking_mode || "—"}</strong>
        </div>
        <div class="maintenance-focus-stat tone-warn">
          <span>Estimated stop</span>
          <strong>${task?.work_package?.est_stop_min || task?.est_duration_min || "—"} min</strong>
        </div>
        <div class="maintenance-focus-stat tone-${(task?.missing_parts || []).length ? "bad" : "good"}">
          <span>Missing parts</span>
          <strong>${(task?.missing_parts || []).length || 0}</strong>
        </div>
      </div>
      <div class="maintenance-lane-board-grid">
        <section class="maintenance-lane-card">
          <div class="chart-head">
            <span>Run now</span>
            <strong>What the operator should watch first</strong>
          </div>
          <div class="micro-list">
            <div class="micro-row"><span>Component</span><strong>${task?.component || "—"}</strong></div>
            <div class="micro-row"><span>Flow state</span><strong>${task?.flow_state || "—"}</strong></div>
            <div class="micro-row"><span>Task id</span><strong>${task?.task_id || "—"}</strong></div>
            <div class="micro-row"><span>Wait note</span><strong>${task?.wait_note || "None"}</strong></div>
          </div>
        </section>
        <section class="maintenance-lane-card">
          <div class="chart-head">
            <span>Safety gate</span>
            <strong>Risk and escort rules</strong>
          </div>
          <div class="micro-list">
            <div class="micro-row"><span>Fall risk</span><strong>${task?.work_package?.safety_fall_risk || "Low"}</strong></div>
            <div class="micro-row"><span>T&amp;M presence</span><strong>${task?.work_package?.safety_tnm_presence || "Allowed"}</strong></div>
            <div class="micro-row"><span>Last done</span><strong>${task?.last_done_date || "Not tracked"}</strong></div>
            <div class="micro-row"><span>Due window</span><strong>${task?.next_due_date || task?.next_due_draw || task?.next_due_hours || "—"}</strong></div>
          </div>
        </section>
      </div>
      <section class="maintenance-lane-card">
        <div class="chart-head">
          <span>Parts gate</span>
          <strong>Can this run now?</strong>
        </div>
        <div class="metric-row compact">
          <div class="metric-pill tone-good"><span>Ready in stock</span><strong>${Math.max(0, ((task?.required_parts || []).length - (task?.missing_parts || []).length))}</strong></div>
          <div class="metric-pill tone-bad"><span>Missing</span><strong>${(task?.missing_parts || []).length}</strong></div>
          <div class="metric-pill tone-info"><span>Linked orders</span><strong>${task?.linked_open_count || 0}</strong></div>
          <div class="metric-pill tone-good"><span>Synced ready</span><strong>${task?.linked_ready_count || 0}</strong></div>
        </div>
        ${maintenancePartsGateMarkup(task)}
      </section>
      <div class="maintenance-lane-board-grid">
        <section class="maintenance-lane-card">
          <div class="chart-head">
            <span>Procedure steps</span>
            <strong>Operator runbook</strong>
          </div>
          ${maintenanceTextListMarkup(task?.work_package?.procedure_steps || task?.procedure_summary, "No procedure steps are stored for this task yet.")}
        </section>
        <section class="maintenance-lane-card">
          <div class="chart-head">
            <span>Safety protocol</span>
            <strong>Before and during the stop</strong>
          </div>
          ${maintenanceTextListMarkup(task?.work_package?.safety_protocol || task?.safety_notes, "No safety protocol is saved for this task yet.")}
        </section>
      </div>
      <div class="maintenance-lane-board-grid">
        <section class="maintenance-lane-card">
          <div class="chart-head">
            <span>Procedure photos</span>
            <strong>Visual reference beside the task</strong>
          </div>
          ${maintenancePhotoGalleryMarkup(
            task?.work_package?.procedure_photos,
            task?.work_package?.preparation_checklist,
            task?.work_package?.procedure_steps || task?.procedure_summary,
          )}
        </section>
        <section class="maintenance-lane-card">
          <div class="chart-head">
            <span>Finish + sanity check</span>
            <strong>What must be true before closeout</strong>
          </div>
          ${maintenanceSanityGateMarkup(task)}
        </section>
      </div>
    </div>
  `;
}

function maintenanceBuilderMarkup(item) {
  if (!item) {
    return `<div class="chart-empty">Select a maintenance task to edit its work package.</div>`;
  }
  const builderMeta = collectMaintenanceBuilderMeta();
  const wp = item.work_package || {};
  const selectedParts = parseBuilderPartsValue(
    item.mandatory_parts_text || item.required_parts_text || (item.required_parts || []).join("; "),
  );
  const selectedTools = parseBuilderPartsValue(
    item.required_tools_text || (item.required_tools || []).join("; "),
  );
  const savedPhotoValue = String(wp.procedure_photos || "").trim();
  const fallRiskValue = normalizeFallRisk(wp.safety_fall_risk);
  const tnmValue = deriveMaintenanceTnmPresence(fallRiskValue, wp.safety_tnm_presence);
  const trackingModeValue = String(item.tracking_mode || "").trim();
  const intervalTypeValue = String(item.interval_type || "").trim();
  const intervalUnitValue = String(item.interval_unit || "").trim();
  const hoursSourceValue = String(item.hours_source || "").trim();
  const triggerHoursSourceValue = String(item.trigger_hours_source || hoursSourceValue).trim();
  const triggerCalendarUnitValue = String(item.trigger_calendar_unit || intervalUnitValue).trim();
  const autoOrderValue = String(item.auto_order_mandatory_parts || "").trim().toLowerCase();
  const autoOrderEnabled = ["1", "true", "yes", "y", "enabled"].includes(autoOrderValue);
  const testPresetValue = String(item.test_preset || "").trim();
  const optionMarkup = (options = [], selectedValue = "", blankLabel = "Select") => {
    const values = dedupeStrings(options.filter(Boolean));
    const rendered = values.map((option) => {
      const value = String(option || "").trim();
      return `<option value="${escapeHtml(value)}" ${value === String(selectedValue || "") ? "selected" : ""}>${escapeHtml(value)}</option>`;
    });
    return [`<option value="">${escapeHtml(blankLabel)}</option>`, ...rendered].join("");
  };
  return `
    <form id="maintenance-builder-form" class="maintenance-builder-form">
      <input type="hidden" name="taskId" value="${item.task_id}" />
      <input type="hidden" name="component" value="${item.component}" />
      <input type="hidden" name="originalTask" value="${escapeHtml(item.task)}" />
      <input type="hidden" name="sourceFile" value="${escapeHtml(item.source_file || "")}" />
      <div class="maintenance-builder-canvas">
        <section class="maintenance-builder-column maintenance-builder-column-unified">
          <div class="chart-head">
            <span>Package editor</span>
            <strong>Legacy builder data, package flow, and execution logic</strong>
          </div>
          <div class="maintenance-builder-section-grid">
            <div class="maintenance-builder-section maintenance-builder-section-primary">
              <div class="maintenance-builder-section-head">
                <span>Task profile</span>
                <strong>Task title, grouping, ownership, and trigger context</strong>
              </div>
              <div class="field-grid field-grid-2 maintenance-builder-row">
                <label class="field-block">
                  <span>Task name</span>
                  <input type="text" name="task" value="${escapeHtml(item.task)}" placeholder="Control the task title used across the app" />
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>Component</span>
                  <input type="text" value="${escapeHtml(item.component)}" readonly />
                </label>
              </div>
              <div class="field-grid field-grid-2 maintenance-builder-row">
                <label class="field-block maintenance-builder-field-compact">
                  <span>Primary task group</span>
                  <select name="taskGroup">
                    ${optionMarkup(builderMeta.taskGroups, item.task_group || "", "Select group")}
                  </select>
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>Linked task groups</span>
                  <input type="text" name="taskGroups" value="${escapeHtml(item.task_groups || item.task_group || "")}" placeholder="Routine, Hours, Safety..." />
                </label>
              </div>
              <div class="field-grid field-grid-2 maintenance-builder-row">
                <label class="field-block maintenance-builder-field-compact">
                  <span>Owner</span>
                  <input type="text" name="owner" value="${escapeHtml(item.owner || "")}" placeholder="Maintenance / operator / vendor owner" />
                </label>
                <label class="field-block">
                  <span>Trigger context</span>
                  <input type="text" name="triggerContext" value="${escapeHtml(item.trigger_context || "")}" placeholder="What makes the task relevant in the real process?" />
                </label>
              </div>
            </div>
            <div class="maintenance-builder-section">
              <div class="maintenance-builder-section-head">
                <span>Timing + triggers</span>
                <strong>Due logic, planning window, and reset inputs</strong>
              </div>
              <div class="field-grid field-grid-3 maintenance-builder-row">
                <label class="field-block maintenance-builder-field-compact">
                  <span>Tracking mode</span>
                  <select name="trackingMode">
                    ${optionMarkup(builderMeta.trackingModes, trackingModeValue, "Select mode")}
                  </select>
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>Hours source</span>
                  <select name="hoursSource">
                    ${optionMarkup(builderMeta.hoursSources, hoursSourceValue, "Select source")}
                  </select>
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>Interval type</span>
                  <select name="intervalType">
                    ${optionMarkup(builderMeta.intervalTypes, intervalTypeValue, "Select type")}
                  </select>
                </label>
              </div>
              <div class="field-grid field-grid-3 maintenance-builder-row">
                <label class="field-block maintenance-builder-field-compact">
                  <span>Interval value</span>
                  <input type="number" step="any" name="intervalValue" value="${escapeHtml(item.interval_value || "")}" />
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>Interval unit</span>
                  <select name="intervalUnit">
                    ${optionMarkup(builderMeta.intervalUnits, intervalUnitValue, "Select unit")}
                  </select>
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>Planning window (months)</span>
                  <input type="number" step="1" min="0" name="planningWindowMonths" value="${escapeHtml(item.planning_window_months || "")}" />
                </label>
              </div>
              <div class="field-grid field-grid-3 maintenance-builder-row">
                <label class="field-block maintenance-builder-field-compact">
                  <span>Due threshold (days)</span>
                  <input type="number" step="1" min="0" name="dueThresholdDays" value="${escapeHtml(item.due_threshold_days || "")}" />
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>Trigger modes</span>
                  <input type="text" name="triggerModes" value="${escapeHtml(item.trigger_modes || "")}" placeholder="hours, draws, calendar" />
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>Trigger hours source</span>
                  <select name="triggerHoursSource">
                    ${optionMarkup(builderMeta.hoursSources, triggerHoursSourceValue, "Select source")}
                  </select>
                </label>
              </div>
              <div class="field-grid field-grid-3 maintenance-builder-row">
                <label class="field-block maintenance-builder-field-compact">
                  <span>Trigger hours interval</span>
                  <input type="number" step="any" min="0" name="triggerHoursInterval" value="${escapeHtml(item.trigger_hours_interval || "")}" />
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>Trigger draws interval</span>
                  <input type="number" step="1" min="0" name="triggerDrawsInterval" value="${escapeHtml(item.trigger_draws_interval || "")}" />
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>Calendar rule</span>
                  <input type="text" name="calendarRule" value="${escapeHtml(item.calendar_rule || "")}" placeholder="Weekly / first Sunday / etc." />
                </label>
              </div>
              <div class="field-grid field-grid-3 maintenance-builder-row">
                <label class="field-block maintenance-builder-field-compact">
                  <span>Trigger calendar value</span>
                  <input type="number" step="1" min="0" name="triggerCalendarValue" value="${escapeHtml(item.trigger_calendar_value || "")}" />
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>Trigger calendar unit</span>
                  <select name="triggerCalendarUnit">
                    ${optionMarkup(builderMeta.calendarUnits, triggerCalendarUnitValue, "Select unit")}
                  </select>
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>Source tracker file</span>
                  <input type="text" value="${escapeHtml(item.source_file || "")}" readonly />
                </label>
              </div>
            </div>
            <div class="maintenance-builder-section maintenance-builder-section-primary">
              <div class="maintenance-builder-section-head">
                <span>Automatic parts flow</span>
                <strong>Mandatory parts, tools, conditional items, and prep timing</strong>
              </div>
              <div class="field-grid field-grid-2 maintenance-builder-row">
                <label class="field-block">
                  <span>Mandatory parts</span>
                  <input type="hidden" name="requiredParts" id="maintenance-required-parts-input" value="${escapeHtml(selectedParts.join("; "))}" />
                  <div class="maintenance-parts-picker" data-maint-parts-picker="1">
                    <div class="maintenance-parts-selected" id="maintenance-required-parts-selected">
                      ${selectedParts.length
                        ? selectedParts
                            .map(
                              (part) => `
                                <button class="maintenance-parts-chip" type="button" data-maint-part-chip="${escapeHtml(part)}">
                                  <span>${escapeHtml(part)}</span>
                                  <strong>×</strong>
                                </button>
                              `,
                            )
                            .join("")
                        : `<span class="maintenance-parts-placeholder">No parts linked yet</span>`}
                    </div>
                    <div class="maintenance-parts-controls">
                      <input
                        type="text"
                        class="maintenance-parts-search"
                        id="maintenance-required-parts-search"
                        placeholder="Filter relevant parts or type a new part..."
                        autocomplete="off"
                      />
                    </div>
                    <div class="maintenance-parts-suggestions" id="maintenance-required-parts-suggestions"></div>
                  </div>
                </label>
                <label class="field-block">
                  <span>Required tools</span>
                  <input type="hidden" name="requiredTools" id="maintenance-required-tools-input" value="${escapeHtml(selectedTools.join("; "))}" />
                  <div class="maintenance-parts-picker maintenance-tools-picker" data-maint-tools-picker="1">
                    <div class="maintenance-parts-selected" id="maintenance-required-tools-selected">
                      ${selectedTools.length
                        ? selectedTools
                            .map(
                              (tool) => `
                                <button class="maintenance-parts-chip maintenance-parts-chip-tool" type="button" data-maint-tool-chip="${escapeHtml(tool)}">
                                  <span>${escapeHtml(tool)}</span>
                                  <strong>×</strong>
                                </button>
                              `,
                            )
                            .join("")
                        : `<span class="maintenance-parts-placeholder">No tools linked yet</span>`}
                    </div>
                    <div class="maintenance-parts-controls">
                      <input
                        type="text"
                        class="maintenance-parts-search"
                        id="maintenance-required-tools-search"
                        placeholder="Filter relevant tools or type a new tool..."
                        autocomplete="off"
                      />
                    </div>
                    <div class="maintenance-parts-suggestions" id="maintenance-required-tools-suggestions"></div>
                  </div>
                </label>
              </div>
              <div class="field-grid maintenance-builder-row">
                <label class="field-block">
                  <span>Conditional parts</span>
                  <textarea name="conditionalParts" rows="5" placeholder="Visible for inspection and execution, but not auto-ordered.">${item.conditional_parts_text || ""}</textarea>
                </label>
              </div>
              <div class="field-grid field-grid-3 maintenance-builder-row">
                <label class="field-block maintenance-builder-field-compact">
                  <span>Preparation lead (days)</span>
                  <input type="number" step="1" min="0" name="preparationLeadDays" value="${escapeHtml(item.preparation_lead_days || "")}" />
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>Parts-check lead (days)</span>
                  <input type="number" step="1" min="0" name="partsCheckLeadDays" value="${escapeHtml(item.parts_check_lead_days || "")}" />
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>Auto-order mandatory parts</span>
                  <select name="autoOrderMandatoryParts">
                    <option value="yes" ${autoOrderEnabled ? "selected" : ""}>Enabled</option>
                    <option value="no" ${!autoOrderEnabled ? "selected" : ""}>Disabled</option>
                  </select>
                </label>
              </div>
            </div>
            <div class="maintenance-builder-section">
              <div class="maintenance-builder-section-head">
                <span>Procedure pack</span>
                <strong>Prep and live operator steps</strong>
              </div>
              <input type="hidden" name="procedurePhotos" id="maintenance-procedure-photos-input" value="${escapeHtml(savedPhotoValue)}" />
              <input type="file" id="maintenance-photo-file-input" class="maintenance-photo-file-input" accept="image/*" multiple />
              <div class="maintenance-procedure-grid maintenance-builder-row">
                <section class="maintenance-procedure-card">
                  <div class="maintenance-procedure-card-head">
                    <span>Preparation checklist</span>
                    <strong data-maint-checklist-count>0 items</strong>
                  </div>
                  <p class="maintenance-procedure-card-copy">Define what the operator must prepare before the task starts.</p>
                  <div class="maintenance-checklist-editor" data-maint-checklist-editor="preparationChecklist" data-maint-placeholder="Add prep check">
                    <input type="hidden" name="preparationChecklist" value="${escapeHtml(wp.preparation_checklist || "")}" />
                    <div class="maintenance-checklist-list" data-maint-checklist-list></div>
                    <button class="maintenance-checklist-add" type="button" data-maint-checklist-add>+ Prep item</button>
                  </div>
                </section>
                <section class="maintenance-procedure-card">
                  <div class="maintenance-procedure-card-head">
                    <span>Procedure steps</span>
                    <strong data-maint-checklist-count>0 steps</strong>
                  </div>
                  <p class="maintenance-procedure-card-copy">Keep the live operator sequence here. Source procedure text seeds this list automatically when the package is empty.</p>
                  <div class="maintenance-checklist-editor" data-maint-checklist-editor="procedureSteps" data-maint-placeholder="Add procedure step" data-maint-seed="${escapeHtml(item.procedure_summary || "")}">
                    <input type="hidden" name="procedureSteps" value="${escapeHtml(wp.procedure_steps || item.procedure_summary || "")}" />
                    <div class="maintenance-checklist-list" data-maint-checklist-list></div>
                    <button class="maintenance-checklist-add" type="button" data-maint-checklist-add>+ Procedure step</button>
                  </div>
                </section>
              </div>
            </div>
            <div class="maintenance-builder-section">
              <div class="maintenance-builder-section-head">
                <span>Manual context</span>
                <strong>Legacy manual linkage, pinned page, and task notes</strong>
              </div>
              <div class="field-grid field-grid-3 maintenance-builder-row">
                <label class="field-block maintenance-builder-field-compact">
                  <span>Manual name</span>
                  <input type="text" name="manualName" value="${escapeHtml(item.manual_name || "")}" placeholder="Manual file or display name" />
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>Manual page</span>
                  <input type="text" name="manualPage" value="${escapeHtml(item.manual_page || "")}" placeholder="33,34,35 or single page" />
                </label>
                <label class="field-block">
                  <span>Manual link / document</span>
                  <input type="text" name="manualLink" value="${escapeHtml(item.manual_link || "")}" placeholder="Document path or link" />
                </label>
              </div>
              <div class="maintenance-safety-copy-grid maintenance-builder-row">
                <label class="field-block maintenance-safety-field">
                  <span>Procedure summary (source)</span>
                  <small class="field-note">Legacy summary text saved back to the maintenance tracker source.</small>
                  <textarea name="procedureSummary" rows="5">${item.procedure_summary_text || item.procedure_summary || ""}</textarea>
                </label>
                <label class="field-block">
                  <span>Safety / notes (source)</span>
                  <small class="field-note">Base maintenance notes from the source tracker, separate from the live package protocol.</small>
                  <textarea name="safetyNotes" rows="5">${item.safety_notes_text || item.safety_notes || ""}</textarea>
                </label>
              </div>
            </div>
            <div class="maintenance-builder-section">
              <div class="maintenance-builder-section-head">
                <span>Safety section</span>
                <strong>Protocol, risk, and stop planning</strong>
              </div>
              <div class="field-grid field-grid-3 maintenance-builder-row maintenance-safety-control-strip">
                <label class="field-block maintenance-builder-field-compact">
                  <span>Fall risk</span>
                  <select name="safetyFallRisk" id="maintenance-fall-risk-select">
                    <option value="Low" ${fallRiskValue === "Low" ? "selected" : ""}>Low</option>
                    <option value="Medium" ${fallRiskValue === "Medium" ? "selected" : ""}>Medium</option>
                    <option value="High" ${fallRiskValue === "High" ? "selected" : ""}>High</option>
                  </select>
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>T&amp;M presence</span>
                  <input type="text" name="safetyTnmPresence" id="maintenance-tnm-presence-input" value="${escapeHtml(tnmValue)}" readonly />
                  <small class="field-note">Auto-set from fall risk.</small>
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>Estimated stop (min)</span>
                  <input type="number" name="estStopMin" value="${wp.est_stop_min || item.est_duration_min || ""}" />
                </label>
              </div>
              <div class="maintenance-safety-copy-grid maintenance-builder-row">
                <label class="field-block maintenance-safety-field">
                  <span>Safety protocol</span>
                  <small class="field-note">Store the exact operator wording that should be read during execution.</small>
                  <textarea name="safetyProtocol" rows="5">${wp.safety_protocol || item.safety_notes || ""}</textarea>
                </label>
                <label class="field-block">
                  <span>Draw stop plan</span>
                  <small class="field-note">Explain what to do if the draw must be paused, stopped, or handed over.</small>
                  <textarea name="drawStopPlan" rows="5">${wp.draw_stop_plan || ""}</textarea>
                </label>
              </div>
            </div>
            <div class="maintenance-builder-section">
              <div class="maintenance-builder-section-head">
                <span>After-task sanity</span>
                <strong>What must be checked before closeout</strong>
              </div>
              <div class="field-grid maintenance-builder-row">
                <div class="field-block">
                  <span>Input template generator</span>
                  <div class="maintenance-sanity-template-editor" data-maint-sanity-template-editor="sanityChecklist">
                    <input type="hidden" name="sanityChecklist" value="${escapeHtml(wp.sanity_checklist || "")}" />
                    <div class="maintenance-sanity-template-toolbar">
                      <div class="maintenance-sanity-template-intro">
                        <strong>Build the operator input format for closeout</strong>
                        <em>Choose if each input should be a checklist, a numeric reading with target or monitor mode, free text, or a pass/fail check.</em>
                      </div>
                      <button class="maintenance-sanity-template-add" type="button" data-maint-sanity-add>+ Add input</button>
                    </div>
                    <div class="maintenance-sanity-template-list" data-maint-sanity-list></div>
                  </div>
                </div>
              </div>
              <div class="field-grid maintenance-builder-row">
                <label class="field-block">
                  <span>Completion criteria</span>
                  <small class="field-note">Describe what must be true before the operator can close the task.</small>
                  <textarea name="completionCriteria" rows="4">${wp.completion_criteria || ""}</textarea>
                </label>
              </div>
            </div>
            <div class="maintenance-builder-section">
              <div class="maintenance-builder-section-head">
                <span>Test + condition capture</span>
                <strong>Measured values, thresholds, and follow-up action</strong>
              </div>
              <div class="field-grid field-grid-3 maintenance-builder-row">
                <label class="field-block maintenance-builder-field-compact">
                  <span>Test preset</span>
                  <select name="testPreset">
                    ${optionMarkup(builderMeta.testPresetOptions, testPresetValue, "Custom / none")}
                  </select>
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>Action if condition is met</span>
                  <input type="text" name="testAction" value="${escapeHtml(item.test_action || "")}" placeholder="Set prep needed / schedule replacement / etc." />
                </label>
                <label class="field-block maintenance-builder-field-compact">
                  <span>Trigger context note</span>
                  <input type="text" value="${escapeHtml(item.trigger_context || "")}" disabled />
                </label>
              </div>
              <div class="field-grid field-grid-2 maintenance-builder-row">
                <label class="field-block">
                  <span>Fields to capture</span>
                  <textarea name="testFields" rows="4" placeholder="Voltage (V); Temperature (degC); X offset (mm)">${item.test_fields || ""}</textarea>
                </label>
                <label class="field-block">
                  <span>Condition text</span>
                  <textarea name="testCondition" rows="4" placeholder="If measured values drift past expected range...">${item.test_condition || ""}</textarea>
                </label>
              </div>
              <div class="field-grid maintenance-builder-row">
                <label class="field-block">
                  <span>Thresholds JSON</span>
                  <small class="field-note">Keep the raw threshold rows here. The legacy builder stored this as JSON in the task source.</small>
                  <textarea name="testThresholds" rows="4" placeholder='[{"Field":"Voltage","Rule":">","Value":"25","Trigger Label":"High voltage"}]'>${item.test_thresholds || ""}</textarea>
                </label>
              </div>
            </div>
            <div class="maintenance-builder-section">
              <div class="maintenance-builder-section-head">
                <span>Outside support</span>
                <strong>Supplier and vendor details</strong>
              </div>
              <div class="field-grid field-grid-2 maintenance-builder-row">
                <label class="field-block maintenance-builder-field-compact">
                  <span>Supplier name</span>
                  <input type="text" name="supplierName" value="${escapeHtml(wp.supplier_name || "")}" placeholder="Only for outside job / vendor work" />
                </label>
                <label class="field-block">
                  <span>Supplier details / contact</span>
                  <input type="text" name="supplierDetails" value="${escapeHtml(wp.supplier_details || "")}" placeholder="Phone, email, company, contact person..." />
                </label>
              </div>
            </div>
          </div>
          <div class="maintenance-builder-meta">
            <div class="micro-row"><span>Updated</span><strong>${wp.last_updated || "Never"}</strong></div>
            <div class="micro-row"><span>Required parts</span><strong>${(item.required_parts || []).length}</strong></div>
            <div class="micro-row"><span>Required tools</span><strong>${(item.required_tools || []).length}</strong></div>
          </div>
          <div class="order-builder-actions">
            <button class="action-btn action-primary" type="submit">Save work package</button>
          </div>
        </section>
      </div>
    </form>
  `;
}

function parseMaintenanceBuilderSectionState(rawValue) {
  try {
    const parsed = JSON.parse(String(rawValue || "").trim() || "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_error) {
    return {};
  }
}

function bindMaintenanceBuilderSections(root, state = {}, onChange = () => {}) {
  Array.from(root.querySelectorAll(".maintenance-builder-section") || []).forEach((section, index) => {
    const head = section.querySelector(".maintenance-builder-section-head");
    if (!head) return;
    let copy = head.querySelector(".maintenance-builder-section-copy");
    if (!copy) {
      copy = document.createElement("div");
      copy.className = "maintenance-builder-section-copy";
      Array.from(head.childNodes).forEach((node) => {
        copy.appendChild(node);
      });
      head.appendChild(copy);
    }
    const label = String(copy.querySelector("span")?.textContent || copy.textContent || `section-${index + 1}`).trim();
    const key = slugifyToken(label) || `section-${index + 1}`;
    let body = section.querySelector(".maintenance-builder-section-body");
    if (!body) {
      body = document.createElement("div");
      body.className = "maintenance-builder-section-body";
      Array.from(section.children)
        .filter((node) => node !== head)
        .forEach((node) => body.appendChild(node));
      section.appendChild(body);
    }
    let toggle = head.querySelector(".maintenance-builder-section-toggle");
    if (!toggle) {
      toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "maintenance-builder-section-toggle";
      head.appendChild(toggle);
    }
    let isOpen = state[key] === true;
    const persist = () => {
      state[key] = isOpen;
      onChange({ ...state });
    };
    const applyState = () => {
      section.classList.toggle("is-collapsed", !isOpen);
      head.setAttribute("role", "button");
      head.setAttribute("tabindex", "0");
      head.setAttribute("aria-expanded", isOpen ? "true" : "false");
      toggle.textContent = isOpen ? "Hide" : "Open";
    };
    const flip = () => {
      isOpen = !isOpen;
      persist();
      applyState();
    };
    head.addEventListener("click", (event) => {
      if (event.target === toggle || !head.contains(event.target)) return;
      flip();
    });
    head.addEventListener("keydown", (event) => {
      if (!["Enter", " "].includes(event.key)) return;
      event.preventDefault();
      flip();
    });
    toggle.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      flip();
    });
    applyState();
  });
}

function parseBuilderPartsValue(value) {
  return dedupeStrings(
    String(value || "")
      .split(/[;,]/)
      .map((item) => item.trim())
      .filter(Boolean),
  );
}

function builderFileLabel(value) {
  return String(value || "")
    .split(/[\\/]/)
    .filter(Boolean)
    .pop() || String(value || "");
}

function maintenanceChecklistItemId(prefix = "item") {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function normalizeChecklistItem(item = {}, prefix = "item", index = 0) {
  const text = String(item?.text || item?.label || item || "").trim();
  return {
    id: String(item?.id || "").trim() || maintenanceChecklistItemId(`${prefix}-${index + 1}`),
    done: Boolean(item?.done),
    text,
  };
}

function buildMaintenancePhotoTargetOptions(preparationValue = "", procedureValue = "") {
  const prep = parseChecklistSeedItems(preparationValue, "prep")
    .map((item, index) => ({
      key: `prep:${item.id}`,
      label: String(item?.text || "").trim() || `Preparation item ${index + 1}`,
      scope: "Preparation checklist",
    }));
  const procedure = parseChecklistSeedItems(procedureValue, "step")
    .map((item, index) => ({
      key: `step:${item.id}`,
      label: String(item?.text || "").trim() || `Procedure step ${index + 1}`,
      scope: "Procedure step",
    }));
  return [...prep, ...procedure];
}

function normalizeBuilderPhotoItem(item = {}) {
  const rawPath = String(item.path || "").trim();
  const path = rawPath === "[]" ? "" : rawPath;
  const tempId = String(item.temp_id || item.tempId || "").trim();
  const rawName = String(item.name || "").trim();
  const name = (rawName === "[]" ? "" : rawName) || (path ? builderFileLabel(path) : tempId ? "Pending photo" : "");
  const stepKey = String(item.step_key || item.stepKey || "").trim();
  const stepLabel = String(item.step_label || item.stepLabel || "").trim();
  if (!path && !tempId && !name) return null;
  return {
    path,
    temp_id: tempId,
    name,
    step_key: stepKey,
    step_label: stepLabel,
    preview: String(item.preview || "").trim(),
  };
}

function parseBuilderPhotoItems(value) {
  const raw = String(value || "").trim();
  if (!raw) return [];
  let items = [];
  if (raw.startsWith("[")) {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) items = parsed;
    } catch (_error) {
      items = [];
    }
  }
  if (!items.length) {
    items = raw
      .split(/[;,]/)
      .map((item) => item.trim())
      .filter(Boolean)
      .map((path) => ({ path }));
  }
  const seen = new Set();
  return items
    .map(normalizeBuilderPhotoItem)
    .filter(Boolean)
    .filter((item) => {
      const key = item.path ? `saved:${item.path}` : `pending:${item.temp_id || item.name}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function serializeBuilderPhotoItems(items = []) {
  return JSON.stringify(
    items
      .map(normalizeBuilderPhotoItem)
      .filter(Boolean)
      .map((item) => ({
        ...(item.path ? { path: item.path } : {}),
        ...(item.temp_id ? { temp_id: item.temp_id } : {}),
        ...(item.name ? { name: item.name } : {}),
        ...(item.step_key ? { step_key: item.step_key } : {}),
        ...(item.step_label ? { step_label: item.step_label } : {}),
      })),
  );
}

function syncBuilderPhotoItemsToSteps(items = [], stepOptions = []) {
  return items.map((item) => {
    const normalized = normalizeBuilderPhotoItem(item);
    if (!normalized) return item;
    let matched = normalized.step_key ? stepOptions.find((option) => option.key === normalized.step_key) : null;
    if (!matched && normalized.step_label) {
      matched = stepOptions.find((option) => option.label === normalized.step_label);
    }
    return {
      ...normalized,
      step_key: matched?.key || "",
      step_label: matched?.label || normalized.step_label || "",
    };
  });
}

function maintenanceBuilderPhotoItemsMarkup(items = [], stepOptions = []) {
  if (!items.length) {
    return `<span class="maintenance-parts-placeholder">Saved photos will appear here</span>`;
  }
  return items
    .map((item) => {
      const photo = normalizeBuilderPhotoItem(item);
      const itemKey = photo.path ? `saved:${photo.path}` : `pending:${photo.temp_id || photo.name}`;
      const sourceLabel = photo.path ? "Saved photo" : "New upload";
      return `
        <div class="maintenance-photo-row">
          <div class="maintenance-photo-row-media">
            ${
              photo.path || photo.preview
                ? `<a class="maintenance-photo-link" href="${escapeHtml(photo.path || photo.preview)}" target="_blank" rel="noopener noreferrer"><img class="maintenance-photo-row-thumb" src="${escapeHtml(photo.path || photo.preview)}" alt="${escapeHtml(photo.name || builderFileLabel(photo.path || photo.preview))}" loading="lazy" /></a>`
                : `<div class="maintenance-photo-row-thumb is-placeholder">Photo</div>`
            }
          </div>
          <div class="maintenance-photo-row-copy">
            <strong>${escapeHtml(photo.name || builderFileLabel(photo.path || photo.preview))}</strong>
            <em>${escapeHtml(sourceLabel)}</em>
          </div>
          <label class="field-block maintenance-builder-field-compact">
            <span>Relevant step</span>
            <select data-maint-photo-step="${escapeHtml(itemKey)}">
              <option value="">General reference</option>
              ${stepOptions
                .map(
                  (option) => `
                    <option value="${escapeHtml(option.key)}" ${option.key === photo.step_key ? "selected" : ""}>
                      ${escapeHtml(option.label)}
                    </option>
                  `,
                )
                .join("")}
            </select>
          </label>
          <button class="maintenance-photo-remove" type="button" data-maint-photo-chip="${escapeHtml(itemKey)}">×</button>
        </div>
      `;
    })
    .join("");
}

function parseChecklistItems(value, prefix = "item") {
  const raw = String(value || "").trim();
  if (!raw) return [];
  if (raw.startsWith("[")) {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed
          .map((item, index) => normalizeChecklistItem(item, prefix, index))
          .filter((item) => item.text);
      }
    } catch (_error) {
      // Fall through to legacy checklist parsing.
    }
  }
  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      const markdownMatch = line.match(/^[-*]\s+\[( |x|X)\]\s+(.*)$/);
      if (markdownMatch) {
        return normalizeChecklistItem(
          { done: markdownMatch[1].toLowerCase() === "x", text: markdownMatch[2].trim() },
          prefix,
          index,
        );
      }
      return normalizeChecklistItem(
        { done: false, text: line.replace(/^[-*]\s+/, "").trim() },
        prefix,
        index,
      );
    })
    .filter((item) => item.text);
}

function parseChecklistSeedItems(value, prefix = "item") {
  const raw = String(value || "").trim();
  if (!raw) return [];
  if (raw.startsWith("[") || raw.includes("\n") || /^[-*]\s+\[( |x|X)\]/m.test(raw)) return parseChecklistItems(raw, prefix);
  return raw
    .split(/\s*;\s+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((text, index) => normalizeChecklistItem({ done: false, text }, prefix, index))
    .filter((item) => item.text);
}

function serializeChecklistItems(items) {
  return JSON.stringify(
    (items || [])
      .map((item, index) => normalizeChecklistItem(item, "item", index))
      .filter((item) => item.text)
      .map((item) => ({
        id: item.id,
        done: item.done,
        text: item.text,
      })),
  );
}

function normalizeFallRisk(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "high") return "High";
  if (normalized === "medium") return "Medium";
  return "Low";
}

function deriveMaintenanceTnmPresence(fallRiskValue, existingValue = "") {
  const normalized = String(existingValue || "").trim();
  if (normalized && !["Allowed", "Not allowed"].includes(normalized)) return normalized;
  return String(fallRiskValue || "").toLowerCase() === "high" ? "Not allowed" : "Allowed";
}

function isToolLikeInventoryName(value) {
  const lowered = String(value || "").trim().toLowerCase();
  if (!lowered) return false;
  return [
    "cleaning kit",
    "cleaning cloth",
    "tool",
    "wrench",
    "screwdriver",
    "hex key",
    "allen key",
    "spanner",
  ].some((token) => lowered.includes(token));
}

function collectMaintenanceBuilderMeta(rows = []) {
  const fallbackGroups = ["Routine", "Per-Draw/Startup", "On-Condition", "Weekly", "Monthly", "3-Month", "6-Month", "Yearly"];
  const fallbackTrackingModes = ["calendar", "hours", "draws"];
  const fallbackIntervalTypes = ["calendar", "hours", "draws", "fixed", "repeat"];
  const fallbackIntervalUnits = ["days", "weeks", "months", "hours", "draws"];
  const fallbackHoursSources = ["Furnace", "UV (both)", "UV1", "UV2"];
  const fallbackCalendarUnits = ["days", "weeks", "months"];
  const sourceRows = rows.length ? rows : ((bootstrapData?.maintenance?.tasks) || []);
  const inventoryRows = bootstrapData?.inventory?.inventory_rows || [];
  const taskGroups = dedupeStrings([...sourceRows.map((item) => item.task_group), ...fallbackGroups]);
  const inventoryPartNames = inventoryRows
    .filter((item) => !String(item?.item_type || "").trim().toLowerCase().includes("tool") && !isToolLikeInventoryName(item?.part_name))
    .map((item) => item.part_name);
  const inventoryToolNames = inventoryRows
    .filter((item) => String(item?.item_type || "").trim().toLowerCase() === "tool" || isToolLikeInventoryName(item?.part_name))
    .map((item) => item.part_name);
  const partOptions = dedupeStrings([
    ...sourceRows.flatMap((item) => item.required_parts || []),
    ...sourceRows.flatMap((item) => item.mandatory_parts || []),
    ...sourceRows.flatMap((item) => item.conditional_parts || []),
    ...inventoryPartNames,
    ...((bootstrapData?.parts?.all_orders || []).map((item) => item.part_name)),
  ]).sort((a, b) => a.localeCompare(b));
  const toolOptions = dedupeStrings([
    ...sourceRows.flatMap((item) => item.required_tools || []),
    ...((bootstrapData?.maintenance?.tool_options) || []),
    ...inventoryToolNames,
  ]).sort((a, b) => a.localeCompare(b));
  return {
    taskGroups: taskGroups.length ? taskGroups : fallbackGroups,
    partOptions,
    toolOptions,
    trackingModes: dedupeStrings([...sourceRows.map((item) => item.tracking_mode), ...fallbackTrackingModes]),
    intervalTypes: dedupeStrings([...sourceRows.map((item) => item.interval_type), ...fallbackIntervalTypes]),
    intervalUnits: dedupeStrings([
      ...sourceRows.map((item) => item.interval_unit),
      ...sourceRows.map((item) => item.trigger_calendar_unit),
      ...fallbackIntervalUnits,
    ]),
    hoursSources: dedupeStrings([
      ...sourceRows.map((item) => item.hours_source),
      ...sourceRows.map((item) => item.trigger_hours_source),
      ...fallbackHoursSources,
    ]),
    calendarUnits: dedupeStrings([...sourceRows.map((item) => item.trigger_calendar_unit), ...fallbackCalendarUnits]),
    testPresetOptions: dedupeStrings([
      ...sourceRows.map((item) => item.test_preset),
      ...((bootstrapData?.maintenance?.test_preset_options) || []),
    ]),
  };
}

function maintenanceBuilderFocusMarkup(item) {
  if (!item) {
    return `<div class="chart-empty">Select a maintenance task to open the builder lane.</div>`;
  }
  const progress = maintenanceBuilderProgress(item);
  const sourceLabel = builderFileLabel(item.source_file || "");
  return `
    <div class="maintenance-focus-hero">
      <div class="maintenance-focus-head">
        <div class="maintenance-focus-copy">
          <span>Selected task</span>
          <strong class="maintenance-focus-title">${item.task}</strong>
          <p class="maintenance-focus-meta-line">
            <strong>${item.component || "General task"}</strong>
            <span>${escapeHtml(item.task_group || "General")} · ${escapeHtml(sourceLabel || "No source file")}</span>
          </p>
        </div>
        <div class="maintenance-focus-actions">
          <button class="mini-action" type="button" data-maint-edit-task-name>Rename task</button>
          <button class="action-btn action-secondary" type="button" data-maint-open-picker>Browse tasks</button>
          <button class="action-btn action-primary" type="button" data-maint-create-toggle>New task</button>
        </div>
      </div>
      <div class="maintenance-focus-stats">
        <div class="maintenance-focus-stat tone-${progress.percent >= 75 ? "good" : progress.percent >= 35 ? "info" : "warn"}">
          <span>Builder progress</span>
          <strong>${progress.done} / ${progress.total}</strong>
        </div>
        <div class="maintenance-focus-stat tone-info">
          <span>Group</span>
          <strong>${item.task_group || "General"}</strong>
        </div>
        <div class="maintenance-focus-stat tone-${(item.missing_parts || []).length ? "bad" : "good"}">
          <span>Parts + tools</span>
          <strong>${((item.required_parts || []).length || 0) + ((item.required_tools || []).length || 0)}</strong>
        </div>
        <div class="maintenance-focus-stat tone-${item.manual_link ? "info" : "warn"}">
          <span>Manual</span>
          <strong>${item.manual_name || "Missing"}</strong>
        </div>
      </div>
    </div>
  `;
}

function maintenanceBuilderPickerMarkup(rows, selectedTaskId, filters = {}, allRows = rows) {
  const filteredRows = rows || [];
  const sourceRows = (allRows && allRows.length ? allRows : filteredRows) || [];
  const componentOptions = Array.from(new Set(sourceRows.map((item) => item.component).filter(Boolean))).sort();
  const groupOptions = Array.from(new Set(sourceRows.map((item) => item.task_group).filter(Boolean))).sort();
  const sourceOptions = Array.from(new Set(sourceRows.map((item) => item.source_file).filter(Boolean))).sort();
  const selectedTask = sourceRows.find((item) => item.task_id === selectedTaskId) || sourceRows[0] || {};
  const defaultSource = String(filters.newTaskSource || selectedTask.source_file || sourceOptions[0] || "").trim();
  const defaultComponent = String(filters.newTaskComponent || selectedTask.component || "General").trim() || "General";
  const defaultGroup = String(filters.newTaskGroup || selectedTask.task_group || groupOptions[0] || "General").trim() || "General";
  return `
    <details class="fold-section fold-tone-info maintenance-builder-picker" ${filters.open ? "open" : ""}>
      <summary class="fold-summary">
        <div class="fold-summary-copy">
          <span>Task selector</span>
          <strong>Choose maintenance task</strong>
        </div>
        <div class="fold-summary-right">
          <button class="mini-action maintenance-builder-create-launch" type="button" data-maint-create-toggle>${filters.createOpen ? "Hide new task" : "New task"}</button>
          <span class="fold-summary-meta">${filteredRows.length} tasks</span>
          <span class="fold-summary-toggle">Open</span>
        </div>
      </summary>
      <div class="fold-body maintenance-builder-picker-body">
        ${filters.createOpen ? `
          <section class="maintenance-builder-create-panel">
            <div class="chart-head compact">
              <span>New task</span>
              <strong>Add a component-linked or general maintenance task</strong>
            </div>
            <form id="maintenance-builder-create-form" class="maintenance-builder-create-form">
              <div class="maintenance-builder-create-grid">
                <label class="field-block">
                  <span>Source file</span>
                  <select name="sourceFile" ${sourceOptions.length ? "" : "disabled"}>
                    ${sourceOptions.length
                      ? sourceOptions
                          .map(
                            (option) => `<option value="${escapeHtml(option)}" ${option === defaultSource ? "selected" : ""}>${escapeHtml(option)}</option>`,
                          )
                          .join("")
                      : `<option value="">No maintenance source file</option>`}
                  </select>
                </label>
                <label class="field-block">
                  <span>Task group</span>
                  <select name="taskGroup">
                    <option value="General" ${defaultGroup === "General" ? "selected" : ""}>General</option>
                    ${groupOptions
                      .filter((option) => option !== "General")
                      .map(
                        (option) => `<option value="${escapeHtml(option)}" ${option === defaultGroup ? "selected" : ""}>${escapeHtml(option)}</option>`,
                      )
                      .join("")}
                  </select>
                </label>
                <label class="field-block">
                  <span>Component</span>
                  <input type="text" name="component" list="maintenance-builder-component-list" value="${escapeHtml(defaultComponent)}" placeholder="General or component name" />
                  <datalist id="maintenance-builder-component-list">
                    <option value="General"></option>
                    ${componentOptions.map((option) => `<option value="${escapeHtml(option)}"></option>`).join("")}
                  </datalist>
                </label>
                <label class="field-block">
                  <span>Task name</span>
                  <input type="text" name="task" placeholder="Describe the maintenance task" required />
                </label>
              </div>
              <div class="micro-panel maintenance-builder-create-note">Create the task in the selected maintenance tracker source, then continue editing the full package below.</div>
              <div class="maintenance-builder-create-actions">
                <button class="action-btn action-primary" type="submit" ${sourceOptions.length ? "" : "disabled"}>Create new task</button>
              </div>
            </form>
          </section>
        ` : ""}
        <div class="maintenance-builder-filter-row">
          <input
            class="parts-search-input maintenance-builder-search"
            id="maintenance-builder-search-input"
            placeholder="Search task / id..."
            value="${String(filters.search || "").replace(/"/g, "&quot;")}"
          />
          <select class="maintenance-builder-filter-select" id="maintenance-builder-component-filter">
            <option value="">All components</option>
            ${componentOptions
              .map(
                (option) => `<option value="${option.replace(/"/g, "&quot;")}" ${filters.component === option ? "selected" : ""}>${option}</option>`,
              )
              .join("")}
          </select>
          <select class="maintenance-builder-filter-select" id="maintenance-builder-package-filter">
            <option value="">All packages</option>
            <option value="needs" ${filters.package === "needs" ? "selected" : ""}>Needs package</option>
            <option value="saved" ${filters.package === "saved" ? "selected" : ""}>Saved package</option>
          </select>
        </div>
        <div class="maintenance-builder-picker-list">
          ${
            filteredRows.length
              ? filteredRows
                  .map(
                    (item) => {
                      const progress = maintenanceBuilderProgress(item);
                      return `
                        <article class="maintenance-builder-mini-card ${selectedTaskId === item.task_id ? "is-active" : ""}">
                          <button
                            class="maintenance-builder-mini-item ${selectedTaskId === item.task_id ? "is-active" : ""}"
                            type="button"
                            data-maint-select="${item.task_id}"
                          >
                            <div class="maintenance-builder-mini-top">
                              <strong>${item.component}</strong>
                              <span class="maintenance-builder-mini-badge tone-${progress.percent >= 75 ? "good" : progress.percent >= 35 ? "info" : "warn"}">${progress.done}/${progress.total}</span>
                            </div>
                            <span>${item.task}</span>
                            <em>${item.task_group || item.task_id || ""}</em>
                            <div class="maintenance-builder-mini-progress">
                              <span>${progress.percent}% package ready</span>
                              <strong>${item.work_package?.last_updated ? "Saved" : "Draft"}</strong>
                            </div>
                            <div class="maintenance-builder-mini-bar" aria-hidden="true">
                              <span style="width:${progress.percent}%"></span>
                            </div>
                          </button>
                          <button
                            class="maintenance-builder-mini-delete"
                            type="button"
                            data-maint-delete-task="${item.task_id}"
                            data-maint-delete-component="${escapeHtml(item.component || "")}"
                            data-maint-delete-label="${escapeHtml(item.task || "")}"
                            data-maint-delete-source="${escapeHtml(item.source_file || "")}"
                          >
                            Delete task
                          </button>
                        </article>
                      `;
                    },
                  )
                  .join("")
              : `<div class="chart-empty">No tasks match this filter.</div>`
          }
        </div>
      </div>
    </details>
  `;
}

function maintenanceBuilderWorkspaceMarkup(item, rows, selectedTaskId, filters, allRows = rows) {
  return `
    <div class="maintenance-builder-workspace-full">
      ${maintenanceBuilderPickerMarkup(rows, selectedTaskId, filters, allRows)}
      ${maintenanceBuilderFocusMarkup(item)}
      ${maintenanceBuilderMarkup(item)}
    </div>
  `;
}

function inferMaintenanceTimelineMode(item, index) {
  const mode = String(item?.tracking_mode || "").trim().toLowerCase();
  if (mode.includes("hour")) return "hours";
  if (mode.includes("draw")) return "draws";
  if (mode.includes("date") || mode.includes("calendar")) return "calendar";
  if (mode.includes("either")) {
    if (maintenanceFiniteDueNumber(item?.next_due_hours) != null) return "hours";
    if (maintenanceFiniteDueNumber(item?.next_due_draw) != null) return "draws";
    if (maintenanceParsedDueDate(item)) return "calendar";
  }
  if (mode.includes("event")) {
    if (maintenanceFiniteDueNumber(item?.next_due_draw) != null) return "draws";
    if (maintenanceFiniteDueNumber(item?.next_due_hours) != null) return "hours";
    if (maintenanceParsedDueDate(item)) return "calendar";
    return "draws";
  }
  if (maintenanceFiniteDueNumber(item?.next_due_hours) != null) return "hours";
  if (maintenanceFiniteDueNumber(item?.next_due_draw) != null) return "draws";
  if (maintenanceParsedDueDate(item)) return "calendar";
  if (index % 5 === 3) return "draws";
  if (index % 5 === 4) return "calendar";
  return "hours";
}

function inferMaintenanceHoursGroup(item, index) {
  const haystack = `${item?.hours_source || ""} ${item?.component || ""} ${item?.task || ""} ${item?.source_file || ""}`.toLowerCase();
  if (haystack.includes("uv1") || haystack.includes("uv 1")) return "uv1";
  if (haystack.includes("uv2") || haystack.includes("uv 2")) return "uv2";
  const rotation = ["furnace", "uv1", "uv2"];
  return rotation[index % rotation.length];
}

function maintenanceTimelineLaneForTask(item, index = 0) {
  const laneEntries = maintenanceTimelineLaneEntries(item, index);
  if (laneEntries.length) return laneEntries[0].laneKey;
  const mode = inferMaintenanceTimelineMode(item, index);
  if (mode === "calendar") return "calendar";
  if (mode === "draws") return "draws";
  return inferMaintenanceHoursGroup(item, index);
}

function formatMaintenanceTimelineValue(value, kind) {
  if (kind === "calendar") {
    const date = value instanceof Date ? value : new Date(value);
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }
  if (kind === "draws") return `D${Math.round(Number(value) || 0)}`;
  return `${Math.round(Number(value) || 0)}h`;
}

function numericOr(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function maintenanceFiniteDueNumber(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function maintenanceParsedDueDate(item) {
  const raw = String(item?.next_due_date || "").trim();
  if (!raw) return null;
  const parsedDate = new Date(raw);
  return Number.isNaN(parsedDate.getTime()) ? null : parsedDate;
}

function maintenanceTimelineLaneEntries(item, index = 0) {
  const entries = [];
  const seenLaneKeys = new Set();
  const pushEntry = (laneKey, dueValue) => {
    if (!laneKey || dueValue == null || seenLaneKeys.has(laneKey)) return;
    seenLaneKeys.add(laneKey);
    entries.push({ laneKey, dueValue });
  };
  const nextDueHours = maintenanceFiniteDueNumber(item?.next_due_hours);
  const nextDueDraw = maintenanceFiniteDueNumber(item?.next_due_draw);
  const nextDueDate = maintenanceParsedDueDate(item);
  if (nextDueHours != null) pushEntry(inferMaintenanceHoursGroup(item, index), nextDueHours);
  if (nextDueDraw != null) pushEntry("draws", nextDueDraw);
  if (nextDueDate) pushEntry("calendar", nextDueDate);
  return entries;
}

function maintenancePrepTimelineSourceTasks(data) {
  const prepRows = maintenanceUniqueTasks(data?.prep_queue || []);
  if (prepRows.length) return prepRows;
  return maintenanceUniqueTasks(
    (data?.tasks || []).filter((task) => {
      const status = String(task?.status || "").trim().toUpperCase();
      return ["PREP_READY", "PREP_DONE", "WAIT FOR PART"].includes(status);
    }),
  );
}

function maintenanceLaneActualItems(sourceRows = [], laneKey = "") {
  const items = [];
  sourceRows.forEach((item, index) => {
    maintenanceTimelineLaneEntries(item, index).forEach((entry) => {
      if (entry.laneKey !== laneKey) return;
      items.push({
        taskId: item?.task_id || "",
        component: item?.component || "",
        task: item?.task || "",
        title: item?.component || item?.task || "Task",
        note: item?.task || item?.task_group || item?.timing_status || item?.status || "Maintenance task",
        status: item?.timing_status || item?.status || "PREP_READY",
        dueValue: entry.dueValue,
        taskData: item,
      });
    });
  });
  return items;
}

function maintenanceLaneRangeFieldMax(lane, sourceRows = []) {
  const current = lane.kind === "calendar" ? lane.current.getTime() : Number(lane.current);
  const dueValues = maintenanceLaneActualItems(sourceRows, lane.key)
    .map((item) => (lane.kind === "calendar" ? item.dueValue.getTime() : Number(item.dueValue)))
    .filter((value) => Number.isFinite(value) && value >= current);
  if (!dueValues.length) {
    return lane.kind === "calendar" ? 30 : lane.kind === "draws" ? 40 : 200;
  }
  const furthestDue = Math.max(...dueValues);
  if (lane.kind === "calendar") {
    const daySpan = Math.ceil((furthestDue - current) / (24 * 60 * 60 * 1000)) + 2;
    return Math.max(30, Math.min(3650, daySpan));
  }
  if (lane.kind === "draws") {
    return Math.max(40, Math.min(5000, Math.ceil(furthestDue - current) + 2));
  }
  return Math.max(200, Math.min(10000, Math.ceil(furthestDue - current) + 12));
}

function maintenanceDemoItemsForLane(lane, now, sourceRows = []) {
  const fallbackLabels = lane.kind === "calendar"
    ? ["Weekend PM", "Midweek check", "Window clean"]
    : lane.kind === "draws"
      ? ["Draw check", "Coating clean", "Inspection"]
      : [`${lane.title} quick check`, `${lane.title} service`, `${lane.title} alignment`];
  const previewBases = sourceRows.slice(0, 3);
  return fallbackLabels.map((label, index) => {
    const source = previewBases[index] || previewBases[0] || {};
    const demoTaskId = source.task_id ? `demo-${lane.key}-${source.task_id}-${index}` : `demo-${lane.key}-${index}`;
    let dueValue;
    if (lane.kind === "calendar") {
      dueValue = new Date(now.getFullYear(), now.getMonth(), now.getDate() + (index < 2 ? 2 : 7));
    } else if (lane.kind === "draws") {
      dueValue = Number(lane.current) + [1, 2, 4][index];
    } else {
      dueValue = Number(lane.current) + [2, 5, 9][index];
    }
    const missingParts = index === 0 ? ["Demo part"] : [];
    const linkedOpenCount = index === 1 ? 1 : 0;
    const linkedReceivedWaitingSync = 0;
    const workPackage = {
      ...(source.work_package || {}),
      preparation_checklist: index === 0 ? "" : (source.work_package?.preparation_checklist || "Demo prep checklist"),
      procedure_steps: index === 0 ? "" : (source.work_package?.procedure_steps || "Demo procedure step"),
      safety_protocol: source.work_package?.safety_protocol || "Demo safety protocol",
      last_updated: index === 0 ? "" : (source.work_package?.last_updated || "Demo package"),
      est_stop_min: source.work_package?.est_stop_min || "20",
    };
    const demoTaskData = {
      ...source,
      source_task_id: source.task_id || "",
      task_id: demoTaskId,
      component: source.component || label,
      task: source.task || `${label} preview`,
      status: index === 0 ? "BLOCKED_PARTS" : "PREP_READY",
      flow_state: index === 0
        ? "Missing parts, no linked order yet"
        : index === 1
          ? "Wait for order"
          : "Ready for preparation",
      missing_parts: missingParts,
      linked_open_count: linkedOpenCount,
      linked_received_waiting_sync: linkedReceivedWaitingSync,
      linked_ready_count: index === 2 ? 1 : 0,
      work_package: workPackage,
    };
    return {
      taskId: demoTaskId,
      component: demoTaskData.component,
      task: demoTaskData.task,
      title: demoTaskData.component,
      note: demoTaskData.task,
      status: "PREVIEW",
      dueValue,
      taskData: demoTaskData,
    };
  });
}

function parseMaintenancePrepCutoffMap(value) {
  if (!value) return {};
  try {
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed)
        .map(([key, entryValue]) => [key, Math.max(0, Math.min(0.98, Number(entryValue)))])
        .filter(([, entryValue]) => Number.isFinite(entryValue)),
    );
  } catch (_error) {
    return {};
  }
}

function parseMaintenancePrepHorizonMap(value) {
  if (!value) return {};
  try {
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed)
        .map(([key, entryValue]) => [key, Math.max(1, Number(entryValue))])
        .filter(([, entryValue]) => Number.isFinite(entryValue)),
    );
  } catch (_error) {
    return {};
  }
}

const MAINT_PREP_HORIZON_STORAGE_KEY = "tower_rebuild_maintenance_prep_horizon_v1";
const MAINT_PREP_HORIZON_FOLD_STORAGE_KEY = "tower_rebuild_maintenance_prep_horizon_fold_v1";

function buildMaintenanceTimelineLanes(data, options = {}) {
  const now = new Date();
  const runtime = data.timeline_runtime || {};
  const sourceTasks = options.sourceTasks || data.tasks || [];
  const horizonMap = options.horizonMap || {};
  const lanes = [
    { key: "furnace", title: "Furnace", subtitle: "Hours", kind: "hours", tone: "maintenance", current: numericOr(runtime.furnace_hours, 0), items: [] },
    { key: "uv1", title: "UV1", subtitle: "Hours", kind: "hours", tone: "info", current: numericOr(runtime.uv1_hours, 0), items: [] },
    { key: "uv2", title: "UV2", subtitle: "Hours", kind: "hours", tone: "info", current: numericOr(runtime.uv2_hours, 0), items: [] },
    { key: "draws", title: "Draws", subtitle: "Count", kind: "draws", tone: "prep", current: numericOr(runtime.draw_count, 0), items: [] },
    { key: "calendar", title: "Calendar", subtitle: "Date", kind: "calendar", tone: "warn", current: now, items: [] },
  ];
  const laneMap = new Map(lanes.map((lane) => [lane.key, lane]));
  const tasks = sourceTasks.slice();

  tasks.forEach((item, index) => {
    maintenanceTimelineLaneEntries(item, index).forEach(({ laneKey, dueValue }) => {
      const lane = laneMap.get(laneKey) || laneMap.get("furnace");
      if (!lane) return;
      lane.items.push({
        taskId: item.task_id || "",
        component: item.component || "",
        task: item.task || "",
        title: item.component || item.task || `Task ${index + 1}`,
        note: item.task || item.task_group || item.timing_status || item.status || "Maintenance task",
        status: item.timing_status || item.status || "PREP_READY",
        dueValue,
        taskData: item,
      });
    });
  });

  lanes.forEach((lane) => {
    const visibleItems = lane.items.length
      ? lane.items
      : maintenanceDemoItemsForLane(lane, now, data.tasks || sourceTasks).slice(0, 3);
    const currentValue = lane.kind === "calendar" ? lane.current.getTime() : Number(lane.current);
    const dueValues = visibleItems
      .map((item) => (lane.kind === "calendar" ? item.dueValue.getTime() : Number(item.dueValue)))
      .filter((value) => Number.isFinite(value))
      .sort((a, b) => a - b);
    const upcomingValues = dueValues.filter((value) => value >= currentValue);
    if (lane.kind === "calendar") {
      const defaultEnd = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 14).getTime();
      const focusEnd = upcomingValues[Math.min(4, upcomingValues.length - 1)] || dueValues[dueValues.length - 1] || defaultEnd;
      lane.min = now;
      const overrideDays = Number(horizonMap[lane.key]);
      lane.max = Number.isFinite(overrideDays)
        ? new Date(now.getTime() + overrideDays * 24 * 60 * 60 * 1000)
        : new Date(Math.max(defaultEnd, focusEnd + 2 * 24 * 60 * 60 * 1000));
    } else if (lane.kind === "draws") {
      const focusEnd = upcomingValues[Math.min(4, upcomingValues.length - 1)] || dueValues[dueValues.length - 1] || (currentValue + 12);
      lane.min = currentValue;
      const overrideDraws = Number(horizonMap[lane.key]);
      lane.max = Number.isFinite(overrideDraws)
        ? currentValue + overrideDraws
        : (lane.items.length ? Math.max(currentValue + 12, focusEnd + 2) : Math.max(currentValue + 6, focusEnd + 1));
      lane.items = lane.items.filter((item) => Number(item.dueValue) <= lane.max && Number(item.dueValue) >= currentValue - 1);
    } else {
      const focusEnd = upcomingValues[Math.min(4, upcomingValues.length - 1)] || dueValues[dueValues.length - 1] || (currentValue + 80);
      lane.min = currentValue;
      const overrideHours = Number(horizonMap[lane.key]);
      lane.max = Number.isFinite(overrideHours)
        ? currentValue + overrideHours
        : (lane.items.length ? Math.max(currentValue + 80, focusEnd + 12) : Math.max(currentValue + 18, focusEnd + 3));
      lane.items = lane.items.filter((item) => Number(item.dueValue) <= lane.max && Number(item.dueValue) >= currentValue - 5);
    }
  });

  return lanes;
}

function maintenanceTaskHasPackage(task) {
  const wp = task?.work_package || {};
  const hasChecklist = Boolean(String(wp.preparation_checklist || "").trim());
  const hasProcedure = Boolean(String(wp.procedure_steps || "").trim());
  const hasSafety = Boolean(String(wp.safety_protocol || "").trim());
  const hasSavedStamp = Boolean(String(wp.last_updated || "").trim());
  const hasStopPlan = Boolean(String(wp.draw_stop_plan || "").trim());
  return hasSavedStamp || (hasStopPlan && hasProcedure) || ((hasChecklist || hasSafety) && hasProcedure);
}

function maintenanceTaskNeedsPrep(task) {
  const status = String(task?.status || "").trim().toUpperCase();
  if (["PREP_DONE", "SCHEDULED", "IN_PROGRESS", "DONE_NOW"].includes(status)) return false;
  return status === "PREP_READY" || status === "";
}

function maintenanceTaskWaitsForPart(task) {
  const status = String(task?.status || "").trim().toUpperCase();
  if (status === "WAIT FOR PART") return true;
  return Number(task?.linked_open_count || 0) > 0
    || Number(task?.linked_received_waiting_sync || 0) > 0;
}

function maintenanceBuilderProgress(task) {
  const wp = task?.work_package || {};
  const sections = [
    Boolean(String(task?.task_group || "").trim() || String(task?.owner || "").trim() || String(task?.trigger_context || "").trim()),
    Boolean(
      String(task?.tracking_mode || "").trim()
      && (
        String(task?.interval_value || "").trim()
        || String(task?.trigger_hours_interval || "").trim()
        || String(task?.trigger_draws_interval || "").trim()
        || String(task?.trigger_calendar_value || "").trim()
      ),
    ),
    Boolean(
      (task?.required_parts || []).length
      || (task?.required_tools || []).length
      || (task?.conditional_parts || []).length
      || String(task?.preparation_lead_days || "").trim()
      || String(task?.parts_check_lead_days || "").trim()
    ),
    Boolean(String(wp.preparation_checklist || "").trim() || String(wp.procedure_steps || "").trim()),
    Boolean(
      String(task?.manual_name || "").trim()
      || String(task?.manual_link || "").trim()
      || String(task?.manual_page || "").trim()
      || String(task?.procedure_summary || "").trim()
      || String(task?.safety_notes || "").trim()
    ),
    Boolean(
      String(wp.safety_protocol || "").trim()
      || String(wp.draw_stop_plan || "").trim()
      || String(wp.est_stop_min || "").trim()
      || String(wp.safety_fall_risk || "").trim()
    ),
    Boolean(String(wp.sanity_checklist || "").trim() || String(wp.completion_criteria || "").trim()),
    Boolean(
      String(task?.test_preset || "").trim()
      || String(task?.test_fields || "").trim()
      || String(task?.test_thresholds || "").trim()
      || String(task?.test_condition || "").trim()
      || String(task?.test_action || "").trim()
    ),
    Boolean(String(wp.supplier_name || "").trim() || String(wp.supplier_details || "").trim()),
  ];
  const total = sections.length;
  const done = sections.filter(Boolean).length;
  const percent = Math.max(0, Math.min(100, Math.round((done / total) * 100)));
  return { done, total, percent };
}

function maintenanceTaskHasPartsBlocker(task) {
  return Number(task?.linked_open_count || 0) > 0
    || Number(task?.linked_received_waiting_sync || 0) > 0
    || ((task?.missing_parts || []).length > 0);
}

function maintenanceTaskOrderableParts(task) {
  const unorderedParts = task?.missing_parts_unordered || [];
  if (unorderedParts.length) return unorderedParts;
  if ((task?.missing_parts_ordered || []).length) {
    const orderedParts = new Set((task?.missing_parts_ordered || []).map((part) => String(part || "").trim().toLowerCase()).filter(Boolean));
    return (task?.missing_parts || []).filter((part) => !orderedParts.has(String(part || "").trim().toLowerCase()));
  }
  return task?.missing_parts || [];
}

function maintenanceTaskHasOrderedParts(task) {
  return Number(task?.linked_open_count || 0) > 0
    || Number(task?.linked_received_waiting_sync || 0) > 0
    || Number(task?.linked_ready_count || 0) > 0;
}

function maintenanceTaskOrderStatusBadges(task) {
  const badges = [];
  if (Number(task?.linked_open_count || 0) > 0) {
    badges.push(`<em class="tone-prep">${escapeHtml(Number(task.linked_open_count) > 1 ? `${Number(task.linked_open_count)} parts ordered` : "Parts ordered")}</em>`);
  }
  if (Number(task?.linked_received_waiting_sync || 0) > 0) {
    badges.push(`<em class="tone-execute">${escapeHtml(Number(task.linked_received_waiting_sync) > 1 ? `${Number(task.linked_received_waiting_sync)} received · sync inventory` : "Received · sync inventory")}</em>`);
  }
  if (Number(task?.linked_ready_count || 0) > 0) {
    badges.push(`<em class="tone-schedule">${escapeHtml(Number(task.linked_ready_count) > 1 ? `${Number(task.linked_ready_count)} synced in inventory` : "Inventory synced")}</em>`);
  }
  return badges.join("");
}

function maintenanceTaskLinkedOrders(task) {
  if (!Array.isArray(task?.linked_orders)) return [];
  return task.linked_orders
    .filter((item) => item && typeof item === "object")
    .map((item) => ({
      partName: String(item.part_name || item.partName || "").trim(),
      status: String(item.status || "").trim() || "Unknown",
      details: String(item.details || "").trim(),
    }))
    .filter((item) => item.partName || item.status || item.details);
}

function maintenanceOrderStatusTone(status = "") {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "opened") return "is-opened";
  if (normalized === "wait for approval") return "is-wait";
  if (normalized === "approved") return "is-approved";
  if (normalized === "ordered") return "is-ordered";
  if (normalized === "received") return "is-received";
  if (normalized === "archived" || normalized === "closed") return "is-closed";
  return "is-neutral";
}

function maintenanceTaskLinkedOrderStatusCounts(task) {
  const linkedOrders = maintenanceTaskLinkedOrders(task);
  const counts = new Map();
  linkedOrders.forEach((item) => {
    const key = item.status || "Unknown";
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  const order = ["Opened", "Wait for Approval", "Approved", "Ordered", "Received", "Archived", "Closed", "Unknown"];
  return Array.from(counts.entries())
    .sort((a, b) => {
      const aIndex = order.indexOf(a[0]);
      const bIndex = order.indexOf(b[0]);
      return (aIndex === -1 ? order.length : aIndex) - (bIndex === -1 ? order.length : bIndex);
    })
    .map(([status, count]) => ({ status, count }));
}

function maintenanceTaskIsPrepDone(task) {
  return String(task?.status || "").trim().toUpperCase() === "PREP_DONE";
}

function maintenanceTaskExecuteBlocked(task) {
  if (maintenanceTaskIsPrepDone(task)) return false;
  const status = String(task?.status || "").trim().toUpperCase();
  return maintenanceTaskNeedsPrep(task)
    || maintenanceTaskWaitsForPart(task)
    || status === "WAIT FOR PART";
}

function maintenanceTaskCanSchedule(task) {
  const status = String(task?.status || "").trim().toUpperCase();
  return status === "PREP_DONE";
}

function maintenanceTaskCanPrepDone(task) {
  const status = String(task?.status || "").trim().toUpperCase();
  if (["PREP_DONE", "SCHEDULED", "IN_PROGRESS", "DONE_NOW"].includes(status)) return false;
  return maintenanceTaskNeedsPrep(task)
    || maintenanceTaskWaitsForPart(task)
    || status === "WAIT FOR PART";
}

function maintenanceCanonicalTaskId(taskOrId, fallbackTask = null) {
  const rawValue = typeof taskOrId === "string"
    ? taskOrId
    : String(taskOrId?.task_id || "");
  const sourceTaskId = typeof taskOrId === "string"
    ? String(fallbackTask?.source_task_id || "")
    : String(taskOrId?.source_task_id || fallbackTask?.source_task_id || "");
  const sourceClean = sourceTaskId.trim();
  if (sourceClean) return sourceClean;
  const raw = String(rawValue || "").trim();
  if (!raw) return "";
  const embeddedTaskId = raw.match(/([A-Za-z0-9]+-MNT-\d+)/i);
  if (embeddedTaskId?.[1]) return embeddedTaskId[1];
  if (raw.startsWith("demo-")) {
    return raw.replace(/^demo-[^-]+-/i, "").replace(/-\d+$/, "");
  }
  return raw;
}

function maintenanceUniqueTasks(tasks = []) {
  const seen = new Set();
  return tasks.filter((task, index) => {
    const rawTaskId = String(task?.task_id || "");
    const key = maintenanceCanonicalTaskId(task)
      || rawTaskId
      || `${task?.component || ""}::${task?.task || ""}::${index}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function maintenancePrepActionLabel(task) {
  if (Number(task?.linked_received_waiting_sync || 0) > 0) return "Sync inventory";
  if (maintenanceTaskOrderableParts(task).length) return "Order parts";
  if (Number(task?.linked_open_count || 0) > 0) return "Wait for part";
  if (maintenanceTaskCanPrepDone(task)) return "Mark ready";
  return "Need prep";
}

function maintenanceScheduleWindowLabels(data) {
  return (data?.maintenance_events || [])
    .slice(0, 2)
    .map((item) => item.date_label || item.start_label || "")
    .filter(Boolean);
}

function maintenancePrepStageAction(stageKey, task) {
  if (stageKey === "scheduled") return { key: "open-execute", label: "Open execute" };
  if (stageKey === "ready" && maintenanceTaskCanSchedule(task)) return { key: "schedule", label: "Schedule" };
  if (Number(task?.linked_received_waiting_sync || 0) > 0) return { key: "parts", label: "Sync inv." };
  if (maintenanceTaskOrderableParts(task).length) return { key: "order-parts", label: "Order parts" };
  if (Number(task?.linked_open_count || 0) > 0) return null;
  return { key: "prep-done", label: "Mark ready" };
}

function maintenancePrepStageExtraActions(stageKey, task) {
  if (stageKey === "scheduled" || stageKey === "wait-part") return [];
  if (!maintenanceTaskCanPrepDone(task)) return [];
  const stageAction = maintenancePrepStageAction(stageKey, task);
  if (!stageAction || stageAction.key === "prep-done") return [];
  return [{ key: "prep-done", label: "Mark ready" }];
}

function maintenancePrepStageState(data, executeTasksBefore = [], prepTasksBefore = []) {
  const scheduledTasks = maintenanceUniqueTasks(
    (data?.execute_queue || []).filter((task) => String(task?.status || "").trim().toUpperCase() === "SCHEDULED"),
  );
  const scheduledTaskKeys = new Set(
    scheduledTasks
      .map((task) => maintenanceCanonicalTaskId(task) || String(task?.task_id || "").trim())
      .filter(Boolean),
  );
  const executeWindowTasks = maintenanceUniqueTasks(
    executeTasksBefore.filter((task) => {
      const taskKey = maintenanceCanonicalTaskId(task) || String(task?.task_id || "").trim();
      return !scheduledTaskKeys.has(taskKey);
    }),
  );
  const executeWindowTaskKeys = new Set(
    executeWindowTasks
      .map((task) => maintenanceCanonicalTaskId(task) || String(task?.task_id || "").trim())
      .filter(Boolean),
  );
  const prepDoneTasks = maintenanceUniqueTasks(
    prepTasksBefore.filter((task) => {
      const taskKey = maintenanceCanonicalTaskId(task) || String(task?.task_id || "").trim();
      return maintenanceTaskIsPrepDone(task) && !scheduledTaskKeys.has(taskKey);
    }),
  );
  const readyTasks = maintenanceUniqueTasks(
    executeWindowTasks.filter((task) => maintenanceTaskCanSchedule(task)),
  );
  const readyTaskKeys = new Set(
    readyTasks
      .map((task) => maintenanceCanonicalTaskId(task) || String(task?.task_id || "").trim())
      .filter(Boolean),
  );
  const readyStageTasks = maintenanceUniqueTasks(readyTasks);
  const waitForPartTasks = maintenanceUniqueTasks(
    prepTasksBefore.filter((task) => {
      const taskKey = maintenanceCanonicalTaskId(task) || String(task?.task_id || "").trim();
      if (scheduledTaskKeys.has(taskKey) || readyTaskKeys.has(taskKey)) return false;
      return maintenanceTaskWaitsForPart(task);
    }),
  );
  const needPrepTasks = maintenanceUniqueTasks(
    prepTasksBefore.filter((task) => {
      const status = String(task?.status || "").trim().toUpperCase();
      const taskKey = maintenanceCanonicalTaskId(task) || String(task?.task_id || "").trim();
      if (scheduledTaskKeys.has(taskKey) || readyTaskKeys.has(taskKey)) return false;
      if (status === "PREP_DONE" || maintenanceTaskWaitsForPart(task)) return false;
      return status === "PREP_READY" || status === "";
    }),
  );
  const overdueNeedPrepCount = needPrepTasks.filter((task) => maintenanceTaskLooksOverdue(task)).length;
  const upcomingNeedPrepCount = Math.max(0, needPrepTasks.length - overdueNeedPrepCount);
  const waitForPartOrderedCount = waitForPartTasks.filter((task) => Number(task?.linked_open_count || 0) > 0).length;
  const waitForPartSyncCount = waitForPartTasks.filter((task) => Number(task?.linked_received_waiting_sync || 0) > 0).length;
  const executeBlockedTasks = maintenanceUniqueTasks(
    executeWindowTasks.filter((task) => !readyTaskKeys.has(maintenanceCanonicalTaskId(task) || String(task?.task_id || "").trim())),
  );
  return {
    scheduledTasks,
    scheduledTaskKeys,
    executeWindowTasks,
    executeWindowTaskKeys,
    prepDoneTasks,
    waitForPartTasks,
    readyStageTasks,
    readyTasks,
    readyTaskKeys,
    executeBlockedTasks,
    executeBlockedCount: executeBlockedTasks.length,
    needPrepTasks,
    overdueNeedPrepCount,
    upcomingNeedPrepCount,
    waitForPartOrderedCount,
    waitForPartSyncCount,
  };
}

function parseMaintenanceStageActionState(rawValue = "") {
  if (!rawValue) return null;
  try {
    const parsed = JSON.parse(rawValue);
    if (!parsed || typeof parsed !== "object") return null;
    const action = String(parsed.action || "").trim();
    const taskIds = Array.isArray(parsed.taskIds)
      ? parsed.taskIds.map((item) => String(item || "").trim()).filter(Boolean)
      : [];
    const confirmAction = String(parsed.confirmAction || action).trim() || action;
    if (!action || !taskIds.length) return null;
    return {
      action,
      confirmAction,
      mode: String(parsed.mode || "single").trim() || "single",
      taskIds,
    };
  } catch (error) {
    return null;
  }
}

function parseMaintenanceTaskIdList(rawValue = "") {
  if (!rawValue) return [];
  try {
    const parsed = JSON.parse(rawValue);
    if (Array.isArray(parsed)) {
      return dedupeStrings(parsed.map((item) => String(item || "").trim()).filter(Boolean));
    }
  } catch (error) {
    // Fall back to comma-separated values for older state payloads.
  }
  return dedupeStrings(String(rawValue || "").split(",").map((item) => item.trim()).filter(Boolean));
}

function parsePartsStageActionState(rawValue = "") {
  if (!rawValue) return null;
  try {
    const parsed = JSON.parse(rawValue);
    if (!parsed || typeof parsed !== "object") return null;
    const action = String(parsed.action || "").trim();
    const orderIds = Array.isArray(parsed.orderIds)
      ? parsed.orderIds.map((item) => String(item || "").trim()).filter(Boolean)
      : [];
    if (!action || !orderIds.length) return null;
    return {
      action,
      orderIds,
      mode: String(parsed.mode || "single").trim() || "single",
    };
  } catch (error) {
    return null;
  }
}

function parsePartsStageFlashState(rawValue = "") {
  if (!rawValue) return null;
  try {
    const parsed = JSON.parse(rawValue);
    if (!parsed || typeof parsed !== "object") return null;
    return {
      kind: String(parsed.kind || "info"),
      message: String(parsed.message || "").trim(),
    };
  } catch (error) {
    return null;
  }
}

function buildMaintenanceStageTaskLookup(data, horizonMap = {}) {
  const lookup = new Map();
  const sourceRows = maintenanceUniqueTasks([...(data?.tasks || []), ...(data?.prep_queue || [])]);
  [...(data?.tasks || []), ...(data?.prep_queue || []), ...sourceRows].forEach((item) => {
    const key = String(item?.task_id || "").trim();
    if (key) lookup.set(key, item);
    const canonicalKey = maintenanceCanonicalTaskId(item);
    if (canonicalKey) lookup.set(canonicalKey, item);
  });
  const lanes = buildMaintenanceTimelineLanes(data || {}, {
    sourceTasks: sourceRows,
    limit: 24,
    horizonMap,
  });
  const demoNow = new Date();
  lanes.forEach((lane) => {
    lane.items.forEach((item) => {
      const key = String(item?.taskId || item?.taskData?.task_id || "").trim();
      if (key && item?.taskData) lookup.set(key, item.taskData);
      const canonicalKey = maintenanceCanonicalTaskId(item?.taskData || item?.taskId || "");
      if (canonicalKey && item?.taskData) lookup.set(canonicalKey, item.taskData);
    });
    maintenanceDemoItemsForLane(lane, demoNow, sourceRows).forEach((item) => {
      const key = String(item?.taskId || item?.taskData?.task_id || "").trim();
      if (key && item?.taskData) lookup.set(key, item.taskData);
      const canonicalKey = maintenanceCanonicalTaskId(item?.taskData || item?.taskId || "");
      if (canonicalKey && item?.taskData) lookup.set(canonicalKey, item.taskData);
    });
  });
  return lookup;
}

function maintenancePrepActionPanelMarkup(data, actionState, taskLookup = null) {
  if (!actionState?.action || !actionState.taskIds?.length) return "";
  const taskMap = taskLookup || buildMaintenanceStageTaskLookup(data);
  const tasks = actionState.taskIds.map((taskId) => taskMap.get(taskId)).filter(Boolean);
  if (!tasks.length) return "";
  const firstTask = tasks[0];
  const scheduleWindow = (data?.maintenance_events || [])[0] || null;
  const scheduleWindows = (data?.maintenance_events || []).filter((item) => item?.start && item?.end);
  const missingParts = dedupeStrings(tasks.flatMap((task) => maintenanceTaskOrderableParts(task)));
  const linkedOrders = tasks.reduce((sum, task) => sum + Number(task?.linked_open_count || 0), 0);
  const receivedWaiting = tasks.reduce((sum, task) => sum + Number(task?.linked_received_waiting_sync || 0), 0);
  const isBulk = actionState.mode === "bulk";

  const config = (() => {
    if (actionState.action === "order-parts" || actionState.action === "order-all") {
      return {
        tone: "prep",
        eyebrow: isBulk ? "Bulk order parts" : "Order parts",
        title: isBulk ? `Create part orders for ${tasks.length} tasks` : `Create part orders for ${firstTask.component}`,
        body: missingParts.length
          ? `${missingParts.length} missing parts will be ordered from this action panel.`
          : "No missing parts were found for this task set.",
        meta: [
          `<span>Tasks</span><strong>${tasks.length}</strong>`,
          `<span>Missing parts</span><strong>${missingParts.length}</strong>`,
        ],
        detail: missingParts.length
          ? `
            <div class="maintenance-prep-actiondrawer-tasklist">
              ${tasks.map((task) => `
                <div class="maintenance-prep-actiondrawer-taskrow">
                  <strong>${escapeHtml(task.component || task.task || "Task")}</strong>
                  <div class="token-strip">
                    ${maintenanceTaskOrderableParts(task).map((part) => `<span class="token-chip">${escapeHtml(part)}</span>`).join("") || `<span class="token-chip">No missing parts</span>`}
                  </div>
                </div>
              `).join("")}
            </div>
          `
          : `<div class="micro-panel">No missing parts are in this selection.</div>`,
        confirmLabel: isBulk ? "Order all together" : "Create order",
      };
    }
    if (actionState.action === "parts") {
      return {
        tone: "prep",
        eyebrow: "Sync inventory",
        title: `Open inventory sync for ${firstTask.component}`,
        body: "Jump to Tower Parts with this task in mind so received items can be synced into inventory.",
        meta: [
          `<span>Waiting sync</span><strong>${receivedWaiting}</strong>`,
        ],
        detail: `<div class="micro-panel">${escapeHtml(firstTask.task || "")}</div>`,
        confirmLabel: "Open tower parts",
      };
    }
    if (actionState.action === "schedule" || actionState.action === "schedule-all") {
      const scheduleSeed = scheduleWindows[0] || { start: "", end: "", label: "" };
      return {
        tone: "schedule",
        eyebrow: isBulk ? "Schedule all" : "Schedule",
        title: isBulk ? `Schedule ${tasks.length} ready tasks` : `Schedule ${firstTask.component}`,
        body: isBulk
          ? "Choose the start and end of the interval. The selected tasks will be spread through it and written into the app calendar."
          : "Choose the exact start and end time for this task in the app calendar.",
        meta: [
          `<span>Tasks</span><strong>${tasks.length}</strong>`,
          `<span>Mode</span><strong>${isBulk ? "Spread interval" : "Exact window"}</strong>`,
        ],
        detail: `
          <div class="maintenance-prep-actiondrawer-slot">
            <div class="maintenance-prep-actiondrawer-slothead">
              <strong>${isBulk ? "Schedule interval" : "Schedule window"}</strong>
              <span>${escapeHtml(scheduleSeed.label || "Custom maintenance window")}</span>
            </div>
            <div class="maintenance-prep-actiondrawer-slotfields">
              <label>
                <span>Start</span>
                <input
                  type="datetime-local"
                  data-maint-stage-slot-start="0"
                  value="${escapeHtml(formatDateTimeLocalValue(scheduleSeed.start || ""))}"
                />
              </label>
              <label>
                <span>End</span>
                <input
                  type="datetime-local"
                  data-maint-stage-slot-end="0"
                  value="${escapeHtml(formatDateTimeLocalValue(scheduleSeed.end || ""))}"
                />
              </label>
            </div>
          </div>
          ${scheduleWindows.length
            ? `<div class="micro-panel">${isBulk ? "The next maintenance window is prefilled here. Edit it and the selected ready tasks will be spread across that interval in the real maintenance calendar." : "The next maintenance window is prefilled here. Edit it before confirming and the task will be written into the real maintenance calendar."}</div>`
            : `<div class="micro-panel">${isBulk ? "Set the start and end time for the interval. The selected tasks will be spread across it and moved into Execute." : "Set the exact start and end time for this task. Scheduling here also writes to the app calendar."}</div>`}
        `,
        confirmLabel: isBulk ? "Schedule tasks" : "Schedule task",
      };
    }
    return {
      tone: "execute",
      eyebrow: "Open execute",
      title: isBulk ? `Open execute for ${tasks.length} scheduled tasks` : `Open execute for ${firstTask.component}`,
      body: "Switch into the execute lane with the selected task set.",
      meta: [
        `<span>Tasks</span><strong>${tasks.length}</strong>`,
      ],
      detail: `<div class="micro-panel">${escapeHtml(firstTask.task || "")}</div>`,
      confirmLabel: "Open execute",
    };
  })();

  if (actionState.action === "blocked") return "";

  return `
    <section class="maintenance-prep-actiondrawer tone-${config.tone}">
      <div class="maintenance-prep-actiondrawer-head">
        <div class="maintenance-prep-actiondrawer-copy">
          <span>${config.eyebrow}</span>
          <strong>${config.title}</strong>
          <p>${config.body}</p>
        </div>
        <button class="maintenance-prep-actiondrawer-close" type="button" data-maint-stage-draft-cancel="1">Close</button>
      </div>
      <div class="maintenance-prep-actiondrawer-meta">
        ${config.meta.map((item) => `<div class="micro-row">${item}</div>`).join("")}
      </div>
      <div class="maintenance-prep-actiondrawer-detail">${config.detail}</div>
      <div class="maintenance-prep-actiondrawer-actions">
        <button class="action-btn action-secondary" type="button" data-maint-stage-draft-cancel="1">Cancel</button>
        <button class="action-btn action-primary" type="button" data-maint-stage-draft-confirm="${escapeHtml(actionState.confirmAction || actionState.action)}">${config.confirmLabel}</button>
      </div>
    </section>
  `;
}

function formatDateTimeLocalValue(rawValue = "") {
  const raw = String(rawValue || "").trim();
  if (!raw) return "";
  if (raw.includes("T")) return raw.slice(0, 16);
  return raw.replace(" ", "T").slice(0, 16);
}

function normalizeDateTimeLocalValue(rawValue = "") {
  const raw = String(rawValue || "").trim();
  if (!raw) return "";
  return raw.includes("T") ? `${raw}:00` : raw;
}

function parseDateTimeLocalValue(rawValue = "") {
  const normalized = normalizeDateTimeLocalValue(rawValue);
  if (!normalized) return null;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatScheduleDateTimeValue(dateValue) {
  if (!(dateValue instanceof Date) || Number.isNaN(dateValue.getTime())) return "";
  const pad = (value) => String(value).padStart(2, "0");
  return `${dateValue.getFullYear()}-${pad(dateValue.getMonth() + 1)}-${pad(dateValue.getDate())}T${pad(dateValue.getHours())}:${pad(dateValue.getMinutes())}:${pad(dateValue.getSeconds())}`;
}

function maintenanceTaskScheduleMinutes(task) {
  const rawValue = Number(task?.work_package?.est_stop_min || task?.est_duration_min || 0);
  if (!Number.isFinite(rawValue) || rawValue <= 0) return 30;
  return Math.max(1, Math.round(rawValue));
}

function buildMaintenanceScheduleWindows(tasks = [], selectedWindow = null) {
  if (!tasks.length) return [];
  const startDate = parseDateTimeLocalValue(selectedWindow?.start || "");
  const endDate = parseDateTimeLocalValue(selectedWindow?.end || "");
  if (!startDate || !endDate || endDate.getTime() <= startDate.getTime()) return [];
  const label = String(selectedWindow?.label || "").trim();
  if (tasks.length === 1) {
    return [{
      start: formatScheduleDateTimeValue(startDate),
      end: formatScheduleDateTimeValue(endDate),
      label,
    }];
  }
  const totalMs = endDate.getTime() - startDate.getTime();
  const slotMs = totalMs / tasks.length;
  const minimumWindowMs = 60 * 1000;
  return tasks.map((task, index) => {
    const slotStart = new Date(startDate.getTime() + Math.round(slotMs * index));
    const slotBoundary = index === tasks.length - 1
      ? endDate
      : new Date(startDate.getTime() + Math.round(slotMs * (index + 1)));
    const preferredEnd = new Date(slotStart.getTime() + (maintenanceTaskScheduleMinutes(task) * 60 * 1000));
    let finalEnd = preferredEnd.getTime() <= slotBoundary.getTime() ? preferredEnd : slotBoundary;
    if (finalEnd.getTime() <= slotStart.getTime()) {
      finalEnd = new Date(Math.min(endDate.getTime(), slotStart.getTime() + Math.max(minimumWindowMs, Math.floor(slotMs))));
    }
    if (finalEnd.getTime() <= slotStart.getTime()) {
      finalEnd = new Date(slotStart.getTime() + minimumWindowMs);
    }
    return {
      start: formatScheduleDateTimeValue(slotStart),
      end: formatScheduleDateTimeValue(finalEnd),
      label,
    };
  });
}

function maintenancePrepStageRowDetails(task, stageKey) {
  const parts = dedupeStrings(task?.missing_parts || []).slice(0, 4);
  const bits = [];
  if (parts.length && (stageKey === "need-prep" || stageKey === "wait-part" || stageKey === "blocked" || stageKey === "ready")) {
    bits.push(`<div class="maintenance-prep-stagepanel-rowparts">${parts.map((part) => `<span class="token-chip">${escapeHtml(part)}</span>`).join("")}</div>`);
  }
  if (stageKey === "wait-part" && maintenanceTaskHasOrderedParts(task)) {
    const orderedCount = Number(task?.linked_open_count || 0);
    const waitingSyncCount = Number(task?.linked_received_waiting_sync || 0);
    const syncedCount = Number(task?.linked_ready_count || 0);
    const linkedOrders = maintenanceTaskLinkedOrders(task);
    const statusCounts = maintenanceTaskLinkedOrderStatusCounts(task);
    const liveStateSummary = statusCounts.map((item) => `${item.status}${item.count > 1 ? ` · ${item.count}` : ""}`).join(" · ");
    let headline = "Linked parts order status";
    let body = "Live states from the connected parts orders for this task.";
    if (waitingSyncCount > 0) {
      headline = waitingSyncCount > 1 ? `${waitingSyncCount} parts received` : "Part received";
      body = "Parts arrived. Sync them into inventory to move this task forward.";
    } else if (orderedCount > 0) {
      headline = orderedCount > 1 ? `${orderedCount} linked orders active` : "Linked order active";
      body = "These orders are still active, so the task stays in wait for part.";
    } else if (syncedCount > 0) {
      headline = syncedCount > 1 ? `${syncedCount} parts synced in inventory` : "Part synced in inventory";
      body = "Inventory is updated for this task.";
    }
    bits.push(`
      <div class="maintenance-prep-stagepanel-statuscopy is-order-status">
        <div class="maintenance-prep-stagepanel-orderstatus-summary">
          <div class="maintenance-prep-stagepanel-orderstatus-copy">
            <strong>${escapeHtml(headline)}</strong>
            <span>${escapeHtml(body)}</span>
          </div>
          ${statusCounts.length ? `
            <div class="maintenance-prep-stagepanel-orderstatus-strip" aria-label="Linked order statuses">
              ${statusCounts.map((item) => `
                <span class="maintenance-prep-stagepanel-orderstatus-pill ${maintenanceOrderStatusTone(item.status)}">
                  <b>${escapeHtml(item.status)}</b>
                  <em>${item.count}</em>
                </span>
              `).join("")}
            </div>
          ` : ""}
        </div>
        ${liveStateSummary ? `<div class="maintenance-prep-stagepanel-orderstatus-line">${escapeHtml(liveStateSummary)}</div>` : ""}
        ${linkedOrders.length ? `
          <div class="maintenance-prep-stagepanel-orderlist">
            ${linkedOrders.map((item) => `
              <div class="maintenance-prep-stagepanel-orderitem">
                <div class="maintenance-prep-stagepanel-orderitem-copy">
                  <strong>${escapeHtml(item.partName || item.details || "Linked order")}</strong>
                  <span>${escapeHtml(item.details || "Linked maintenance parts order")}</span>
                </div>
                <span class="maintenance-prep-stagepanel-orderitem-status ${maintenanceOrderStatusTone(item.status)}">${escapeHtml(item.status)}</span>
              </div>
            `).join("")}
          </div>
        ` : ""}
      </div>
    `);
  }
  if (stageKey !== "wait-part" && (Number(task?.linked_open_count || 0) > 0 || Number(task?.linked_received_waiting_sync || 0) > 0 || Number(task?.linked_ready_count || 0) > 0)) {
    bits.push(
      `<div class="maintenance-prep-stagepanel-rowmeta">` +
      `${Number(task?.linked_open_count || 0) > 0 ? `<span>${Number(task.linked_open_count)} open order</span>` : ""}` +
      `${Number(task?.linked_received_waiting_sync || 0) > 0 ? `<span>${Number(task.linked_received_waiting_sync)} waiting sync</span>` : ""}` +
      `${Number(task?.linked_ready_count || 0) > 0 ? `<span>${Number(task.linked_ready_count)} synced in inventory</span>` : ""}` +
      `</div>`,
    );
  }
  return bits.join("");
}

function maintenanceResolvedPrepStageKey(stageDefs = [], activeStageKey = "need-prep") {
  const activeStage = stageDefs.find((stage) => stage.key === activeStageKey) || null;
  if (activeStage?.count) return activeStage.key;
  return (stageDefs.find((stage) => stage.count) || activeStage || stageDefs[0] || { key: activeStageKey }).key;
}

function maintenancePrepStagePlotMarkup(data, executeTasksBefore = [], prepTasksBefore = [], activeStageKey = "need-prep", stageFlash = null, actionState = null, selectedReadyTaskIds = []) {
  const stageState = maintenancePrepStageState(data, executeTasksBefore, prepTasksBefore);
  const {
    scheduledTasks,
    executeWindowTasks,
    executeWindowTaskKeys,
    prepDoneTasks,
    waitForPartTasks,
    readyStageTasks,
    readyTasks,
    readyTaskKeys,
    executeBlockedTasks,
    needPrepTasks,
    overdueNeedPrepCount,
    upcomingNeedPrepCount,
    waitForPartOrderedCount,
    waitForPartSyncCount,
  } = stageState;
  const readyTaskIds = new Set(readyStageTasks.map((task) => String(task?.task_id || "")));
  const executeReadyIds = new Set(readyTasks.map((task) => String(task?.task_id || "")));
  const scheduleLabels = maintenanceScheduleWindowLabels(data);
  const selectedTaskSet = new Set(
    dedupeStrings(selectedReadyTaskIds.map((item) => String(item || "").trim()).filter(Boolean)),
  );
  const prepDoneWaitingCount = prepDoneTasks.filter(
    (task) => !executeWindowTaskKeys.has(maintenanceCanonicalTaskId(task) || String(task?.task_id || "").trim()),
  ).length;
  const stageDefs = [
    {
      key: "need-prep",
      label: "Need prep",
      tone: "prep",
      count: needPrepTasks.length,
      tasks: needPrepTasks,
      detail: `${overdueNeedPrepCount ? `${overdueNeedPrepCount} overdue` : "No overdue prep"}${upcomingNeedPrepCount ? ` · ${upcomingNeedPrepCount} upcoming in band` : ""}`,
      empty: "No tasks need prep in the current prep window.",
    },
    {
      key: "wait-part",
      label: "Wait for part",
      tone: "prep",
      count: waitForPartTasks.length,
      tasks: waitForPartTasks,
      detail: `${waitForPartOrderedCount ? `${waitForPartOrderedCount} ordered` : "No open orders"}${waitForPartSyncCount ? ` · ${waitForPartSyncCount} waiting sync` : ""}`,
      empty: "No tasks are waiting for parts right now.",
    },
    {
      key: "ready",
      label: "Ready to execute",
      tone: "execute",
      count: readyStageTasks.length,
      tasks: readyStageTasks,
      detail: readyStageTasks.length
        ? `${readyStageTasks.length} ready${prepDoneWaitingCount ? ` · ${prepDoneWaitingCount} waiting marker` : ""}`
        : (prepDoneWaitingCount ? `${prepDoneWaitingCount} ready waiting for execute marker` : "Nothing inside the execute window yet"),
      empty: prepDoneWaitingCount
        ? `${prepDoneWaitingCount} ready tasks are waiting for the execute marker.`
        : "No tasks are ready to execute yet.",
    },
    {
      key: "scheduled",
      label: "Scheduled",
      tone: "schedule",
      count: scheduledTasks.length,
      tasks: scheduledTasks,
      detail: `${scheduleLabels.length ? scheduleLabels.join(" · ") : "Waiting for stop window"}`,
      empty: "No ready tasks are waiting for a stop window.",
    },
  ];
  const selectedStageKey = maintenanceResolvedPrepStageKey(stageDefs, activeStageKey);
  const selectedStage = stageDefs.find((stage) => stage.key === selectedStageKey) || stageDefs[0];
  const selectedStageTaskIds = selectedStage.tasks.map((task) => String(task?.task_id || "")).filter(Boolean).join(",");
  const allReadyTaskIds = readyStageTasks.map((task) => String(task?.task_id || "").trim()).filter(Boolean);
  const selectedReadyStageTaskIds = readyStageTasks
    .filter((task) => selectedTaskSet.has(String(task?.task_id || "").trim()))
    .map((task) => String(task?.task_id || "").trim())
    .filter(Boolean);
  const stageTaskLookup = new Map(
    stageDefs
      .flatMap((stage) => stage.tasks)
      .map((task) => [String(task?.task_id || "").trim(), task])
      .filter(([taskId]) => Boolean(taskId)),
  );
  const stageBulkMarkup = (() => {
    if (!selectedStage.tasks.length) return "";
    if (selectedStage.key === "need-prep" || selectedStage.key === "blocked") {
      const orderableStageTaskIds = selectedStage.tasks
        .filter((task) => maintenanceTaskOrderableParts(task).length)
        .map((task) => String(task?.task_id || "").trim())
        .filter(Boolean);
      const selectedOrderableTaskIds = orderableStageTaskIds.filter((taskId) => selectedTaskSet.has(taskId));
      if (!orderableStageTaskIds.length) return "";
      return `
        ${selectedOrderableTaskIds.length ? `
          <button class="maintenance-prep-stagepanel-bulk" type="button" data-maint-stage-bulk="order-all" data-maint-stage-task-ids="${escapeHtml(selectedOrderableTaskIds.join(","))}">
            Order selected (${selectedOrderableTaskIds.length})
          </button>
          <button class="maintenance-prep-stagepanel-bulk" type="button" data-maint-stage-clear-selection="1">
            Clear
          </button>
        ` : ""}
        <button class="maintenance-prep-stagepanel-bulk" type="button" data-maint-stage-bulk="order-all" data-maint-stage-task-ids="${escapeHtml(orderableStageTaskIds.join(","))}">
          Order all missing (${orderableStageTaskIds.length})
        </button>
      `;
    }
    if (selectedStage.key === "ready") {
      if (!allReadyTaskIds.length) return "";
      const schedulableTaskIds = allReadyTaskIds.join(",");
      const selectedSchedulableTaskIds = selectedReadyStageTaskIds.join(",");
      return `
        ${selectedReadyStageTaskIds.length ? `
          <button class="maintenance-prep-stagepanel-bulk" type="button" data-maint-stage-bulk="schedule-all" data-maint-stage-task-ids="${escapeHtml(selectedSchedulableTaskIds)}">
            Schedule selected (${selectedReadyStageTaskIds.length})
          </button>
          <button class="maintenance-prep-stagepanel-bulk" type="button" data-maint-stage-clear-selection="1">
            Clear
          </button>
        ` : ""}
        <button class="maintenance-prep-stagepanel-bulk" type="button" data-maint-stage-bulk="schedule-all" data-maint-stage-task-ids="${escapeHtml(schedulableTaskIds)}">
          Schedule all (${allReadyTaskIds.length})
        </button>
      `;
    }
    if (selectedStage.key === "scheduled") {
      return `
        <button class="maintenance-prep-stagepanel-bulk" type="button" data-maint-stage-bulk="open-execute-all" data-maint-stage-task-ids="${escapeHtml(selectedStageTaskIds)}">
          Open execute
        </button>
      `;
    }
    return "";
  })();
  return `
    <div class="maintenance-prep-stageflow">
      <div class="maintenance-prep-stageplot">
        ${stageDefs.map((stage, index) => `
          <button
            class="maintenance-prep-stage-dot tone-${stage.tone} ${selectedStage.key === stage.key ? "is-active" : ""}"
            type="button"
            data-maint-prep-stage="${escapeHtml(stage.key)}"
            aria-pressed="${selectedStage.key === stage.key ? "true" : "false"}"
          >
            <span class="maintenance-prep-stage-bullet">${stage.count}</span>
            <strong>${escapeHtml(stage.label)}</strong>
            ${stage.detail ? `<small>${escapeHtml(stage.detail)}</small>` : ""}
            ${index < stageDefs.length - 1 ? `<i class="maintenance-prep-stage-link"></i>` : ""}
          </button>
        `).join("")}
      </div>
      <section class="maintenance-prep-stagepanel tone-${selectedStage.tone}">
        <div class="maintenance-prep-stagepanel-head">
          <div class="maintenance-prep-stagepanel-head-copy">
            <span>${escapeHtml(selectedStage.label)}</span>
            <strong>${selectedStage.count ? `${selectedStage.count} tasks in this stage` : selectedStage.empty}</strong>
            ${selectedStage.detail ? `<p>${escapeHtml(selectedStage.detail)}</p>` : ""}
          </div>
          ${stageBulkMarkup ? `<div class="maintenance-prep-stagepanel-head-actions">${stageBulkMarkup}</div>` : ""}
        </div>
        ${stageFlash?.message ? `<div class="maintenance-prep-stageflash tone-${escapeHtml(stageFlash.kind || "info")}">${escapeHtml(stageFlash.message)}</div>` : ""}
        <div class="maintenance-prep-stagepanel-body">
          ${selectedStage.tasks.length
            ? selectedStage.tasks.map((task) => `
                ${(() => {
                  const stageAction = maintenancePrepStageAction(selectedStage.key, task);
                  const extraStageActions = maintenancePrepStageExtraActions(selectedStage.key, task);
                  const rawTaskId = String(task?.task_id || "").trim();
                  const isScheduleReady = selectedStage.key === "ready" && maintenanceTaskCanSchedule(task);
                  const isOrderPick = selectedStage.key === "need-prep" && maintenanceTaskOrderableParts(task).length > 0;
                  const showsPicker = Boolean(isScheduleReady || isOrderPick);
                  const actionTagsMarkup = `
                    ${maintenanceTaskHasOrderedParts(task) && selectedStage.key !== "wait-part" ? `<div class="maintenance-prep-stagepanel-tags">${maintenanceTaskOrderStatusBadges(task)}</div>` : ""}
                    ${maintenanceTaskIsPrepDone(task) && selectedStage.key === "ready"
                      ? `<div class="maintenance-prep-stagepanel-tags"><em class="tone-schedule">Ready</em></div>`
                      : ""}
                    ${!maintenanceTaskIsPrepDone(task) && executeReadyIds.has(String(task?.task_id || "")) && selectedStage.key === "ready"
                      ? `<div class="maintenance-prep-stagepanel-tags"><em class="tone-schedule">Ready</em></div>`
                      : ""}
                    ${!executeReadyIds.has(String(task?.task_id || "")) && executeWindowTaskKeys.has(maintenanceCanonicalTaskId(task) || String(task?.task_id || "").trim()) && selectedStage.key === "ready"
                      ? `<div class="maintenance-prep-stagepanel-tags"><em class="tone-prep">${escapeHtml(maintenancePrepActionLabel(task))}</em></div>`
                      : ""}
                    ${selectedStage.key === "need-prep" && executeWindowTaskKeys.has(maintenanceCanonicalTaskId(task) || String(task?.task_id || "").trim())
                      ? `<div class="maintenance-prep-stagepanel-tags"><em class="tone-execute">In execute window</em></div>`
                      : ""}
                    ${readyTaskIds.has(String(task?.task_id || "")) && selectedStage.key === "need-prep"
                      ? `<div class="maintenance-prep-stagepanel-tags"><em class="is-priority">High priority</em></div>`
                      : ""}
                  `.trim();
                  const buttonMarkup = `
                    ${extraStageActions.map((action) => `
                      <button class="maintenance-prep-stagepanel-action" type="button" data-maint-stage-action="${escapeHtml(action.key)}" data-maint-stage-task="${escapeHtml(task.task_id || "")}">${escapeHtml(action.label)}</button>
                    `).join("")}
                    ${stageAction ? `<button class="maintenance-prep-stagepanel-action" type="button" data-maint-stage-action="${escapeHtml(stageAction.key)}" data-maint-stage-task="${escapeHtml(task.task_id || "")}">${escapeHtml(stageAction.label)}</button>` : ""}
                  `.trim();
                  const hasActions = Boolean(actionTagsMarkup || buttonMarkup);
                  return `
                <div class="maintenance-prep-stagepanel-row${showsPicker && selectedTaskSet.has(rawTaskId) ? " is-selected" : ""}${!showsPicker ? " is-wide-copy" : ""}${!hasActions ? " is-copy-only" : ""}">
                  ${showsPicker ? `
                    <label class="maintenance-prep-stagepanel-pick">
                      <input type="checkbox" data-maint-stage-select="${escapeHtml(rawTaskId)}" ${selectedTaskSet.has(rawTaskId) ? "checked" : ""} />
                      <span>Mark</span>
                    </label>
                  ` : ""}
                  <div class="maintenance-prep-stagepanel-copy">
                    <strong>${escapeHtml(task.component || task.task || "Task")}</strong>
                    <span>${escapeHtml(task.task || task.task_id || "")}</span>
                    ${maintenancePrepStageRowDetails(task, selectedStage.key)}
                  </div>
                  ${hasActions ? `<div class="maintenance-prep-stagepanel-actions">${actionTagsMarkup}${buttonMarkup}</div>` : ""}
                </div>
              `; })()}
              `).join("")
            : `<div class="maintenance-prep-stagepanel-empty">${escapeHtml(selectedStage.empty)}</div>`}
        </div>
      </section>
      ${maintenancePrepActionPanelMarkup(data, actionState, stageTaskLookup)}
    </div>
  `;
}

function maintenancePrepLiveShellMarkup(data, executeTasksBefore = [], prepTasksBefore = [], activeStageKey = "need-prep", stageFlash = null, actionState = null, selectedReadyTaskIds = []) {
  const stageState = maintenancePrepStageState(data, executeTasksBefore, prepTasksBefore);
  const prepPoolTotal = maintenanceUniqueTasks(
    (data?.prep_queue || []).filter((task) => !maintenanceTaskIsPrepDone(task)),
  ).length;
  const executeBlockedCount = stageState.executeBlockedCount;
  const prepDoneOutsideExecuteCount = stageState.prepDoneTasks.filter(
    (task) => !stageState.executeWindowTaskKeys.has(maintenanceCanonicalTaskId(task) || String(task?.task_id || "").trim()),
  ).length;
  const executeWindowCount = stageState.executeWindowTasks.length;
  const executeReadyCount = stageState.readyTasks.length;
  const prepNeedCount = stageState.needPrepTasks.length;
  const waitForPartCount = stageState.waitForPartTasks.length;
  const prepOverdueCount = stageState.overdueNeedPrepCount;
  const prepUpcomingCount = stageState.upcomingNeedPrepCount;
  const readyLeadLabels = stageState.readyStageTasks
    .slice(0, 2)
    .map((task) => task.component || task.task || "Task")
    .filter(Boolean)
    .join(" · ");
  return `
    <div class="maintenance-prep-live-shell" data-maint-prep-live-shell="1">
      <div class="maintenance-horizon-actionbar">
        <div class="maintenance-horizon-stepcards">
          <div class="maintenance-horizon-stepcard is-execute">
            <span>Execute step</span>
            <strong><span class="is-good">${executeWindowCount} in execute window</span></strong>
            <em>${executeWindowCount ? `${executeReadyCount} ready${executeBlockedCount ? ` · ${executeBlockedCount} blocked` : ""}${readyLeadLabels ? ` · ${escapeHtml(readyLeadLabels)}` : ""}${prepDoneOutsideExecuteCount ? ` · ${prepDoneOutsideExecuteCount} ready waiting` : ""}` : (prepDoneOutsideExecuteCount ? `${prepDoneOutsideExecuteCount} ready waiting for execute band` : "No actual tasks inside the execute band")}</em>
          </div>
          <div class="maintenance-horizon-stepcard is-prep">
            <span>Preparation step</span>
            <strong><span class="is-prep">${prepNeedCount} need prep${waitForPartCount ? ` · ${waitForPartCount} wait for part` : ""}</span></strong>
            <em>${prepTasksBefore.length ? `${prepOverdueCount ? `${prepOverdueCount} overdue` : "No overdue prep"}${prepUpcomingCount ? ` · ${prepUpcomingCount} upcoming in band` : ""}${waitForPartCount ? ` · ${waitForPartCount} waiting on parts` : ""} · ${prepNeedCount + waitForPartCount} of ${prepPoolTotal} prep-pool tasks in band` : "No actual tasks inside the preparation band"}</em>
          </div>
        </div>
      <div class="maintenance-horizon-legend">
        <span class="maintenance-horizon-legend-line"></span>
        <span>Execute band</span>
        <span class="maintenance-horizon-legend-line is-prep"></span>
        <span class="is-prep">Preparation band</span>
      </div>
    </div>
      ${maintenancePrepStagePlotMarkup(data, executeTasksBefore, prepTasksBefore, activeStageKey, stageFlash, actionState, selectedReadyTaskIds)}
    </div>
  `;
}

function maintenancePlottedTasksBeforeMarker(lanes, progressMap = {}, options = {}) {
  const plottedTasks = [];
  lanes.forEach((lane) => {
    const progressLimit = progressMap?.[lane.key];
    if (!Number.isFinite(progressLimit)) return;
    if (progressLimit <= 0.0001) return;
    const min = lane.kind === "calendar" ? lane.min.getTime() : Number(lane.min);
    const max = lane.kind === "calendar" ? lane.max.getTime() : Number(lane.max);
    const range = Math.max(1, max - min);
    lane.items
      .filter((item) => item.taskData)
      .forEach((item) => {
        const due = lane.kind === "calendar" ? item.dueValue.getTime() : Number(item.dueValue);
        const itemProgress = (due - min) / range;
        if (itemProgress > progressLimit + 0.0001) return;
        plottedTasks.push(item.taskData);
      });
  });
  return plottedTasks;
}

function maintenanceSelectedTimelineLaneItem(lanes = [], selectedTaskId = "") {
  return lanes
    .flatMap((lane) => lane.items)
    .find((item) => item.taskId && item.taskId === selectedTaskId)
    || lanes.flatMap((lane) => lane.items).find((item) => item.taskId)
    || null;
}

function maintenanceExecuteProgressMapForLanes(lanes = [], selectedTaskId = "", cutoffMap = {}) {
  return Object.fromEntries(
    lanes.map((lane) => {
      const explicitValue = cutoffMap?.[lane.key];
      if (Number.isFinite(explicitValue)) return [lane.key, explicitValue];
      return [lane.key, 0];
    }),
  );
}

function maintenancePrepProgressMapForLanes(lanes = [], prepMap = {}) {
  return Object.fromEntries(
    lanes.map((lane) => {
      const explicitValue = prepMap?.[lane.key];
      if (Number.isFinite(explicitValue)) return [lane.key, explicitValue];
      return [lane.key, 0.98];
    }),
  );
}

function maintenanceLaneTicksMarkup(lane) {
  const tickCount = 6;
  return Array.from({ length: tickCount }, (_, index) => {
    const progress = index / (tickCount - 1);
    const value = lane.kind === "calendar"
      ? new Date(lane.min.getTime() + (lane.max.getTime() - lane.min.getTime()) * progress)
      : lane.min + (lane.max - lane.min) * progress;
    return `<span>${escapeHtml(formatMaintenanceTimelineValue(value, lane.kind))}</span>`;
  }).join("");
}

function maintenanceLaneItemsMarkup(lane, options = {}) {
  const demoNow = options.demoNow || new Date();
  const demoSourceRows = options.demoSourceRows || [];
  const showPreviewItems = options.showPreviewItems !== false;
  const min = lane.kind === "calendar" ? lane.min.getTime() : Number(lane.min);
  const max = lane.kind === "calendar" ? lane.max.getTime() : Number(lane.max);
  const range = Math.max(1, max - min);
  const current = lane.kind === "calendar" ? lane.current.getTime() : Number(lane.current);
  const currentLeft = ((current - min) / range) * 100;
  const selectedTaskId = options.selectedTaskId || "";
  const selectedProgress = options.selectedProgress ?? null;
  const realItems = lane.items.filter((item) => item.taskId);
  const previewItems = showPreviewItems ? maintenanceDemoItemsForLane(lane, demoNow, demoSourceRows).slice(0, 3) : [];
  const previewClusters = [];
  previewItems.forEach((item) => {
    const due = lane.kind === "calendar" ? item.dueValue.getTime() : Number(item.dueValue);
    const left = ((due - min) / range) * 100;
    const normalizedLeft = Math.max(1, Math.min(99, left));
    const bucket = Math.round(normalizedLeft / 3);
    const existing = previewClusters.find((cluster) => cluster.bucket === bucket);
    if (existing) {
      existing.items.push(item);
      existing.left = (existing.left * (existing.items.length - 1) + normalizedLeft) / existing.items.length;
    } else {
      previewClusters.push({ bucket, left: normalizedLeft, items: [item] });
    }
  });
  if (!lane.items.length && !previewClusters.length) {
    return `
      ${selectedProgress != null ? `<div class="maintenance-horizon-cutoff-line" style="left:${selectedProgress * 100}%;"><span>Execute line</span></div>` : ""}
      <div class="maintenance-header-now-line" style="left:${Math.max(0, Math.min(100, currentLeft))}%;">
        <span>Now</span>
      </div>
      <div class="maintenance-header-lane-empty">No tasks in view</div>
    `;
  }

  const clusters = [];
  realItems.forEach((item) => {
    const due = lane.kind === "calendar" ? item.dueValue.getTime() : Number(item.dueValue);
    const left = ((due - min) / range) * 100;
    const normalizedLeft = Math.max(1, Math.min(99, left));
    const bucket = Math.round(normalizedLeft / 3);
    const existing = clusters.find((cluster) => cluster.bucket === bucket);
    if (existing) {
      existing.items.push(item);
      existing.left = (existing.left * (existing.items.length - 1) + normalizedLeft) / existing.items.length;
    } else {
      clusters.push({ bucket, left: normalizedLeft, items: [item] });
    }
  });

  return `
    ${selectedProgress != null ? `<div class="maintenance-horizon-cutoff-line" style="left:${selectedProgress * 100}%;"><span>Execute line</span></div>` : ""}
    <div class="maintenance-header-now-line" style="left:${Math.max(0, Math.min(100, currentLeft))}%;">
      <span>Now</span>
    </div>
    ${previewClusters
      .map((cluster, index) => {
        const item = cluster.items[0];
        const clusterProgress = cluster.left / 100;
        const beforeCutoff = selectedProgress != null && clusterProgress <= selectedProgress + 0.0001;
        return `
          <button
            class="maintenance-header-pin maintenance-horizon-demo-task tone-${lane.tone} level-${index % 2} ${beforeCutoff ? "is-before-cutoff" : ""}"
            type="button"
            style="left:${Math.max(2, Math.min(98, cluster.left))}%"
            aria-label="${escapeHtml(cluster.items.map((previewItem) => `${previewItem.title} | ${previewItem.note}`).join("\n"))}"
            title="${escapeHtml(cluster.items.map((previewItem) => `${previewItem.title} | ${previewItem.note}`).join("\n"))}"
          >
            <span class="maintenance-header-pin-dot"></span>
            ${cluster.items.length > 1 ? `<span class="maintenance-header-pin-count">${cluster.items.length}</span>` : ""}
            <span class="maintenance-header-tooltip">
              <strong>${escapeHtml(`${formatMaintenanceTimelineValue(item.dueValue, lane.kind)} · ${cluster.items.length > 1 ? `${cluster.items.length} demo tasks` : "Demo task"}`)}</strong>
              ${cluster.items.map((previewItem) => `<span>${escapeHtml(previewItem.title)} · ${escapeHtml(previewItem.note)}</span>`).join("")}
            </span>
          </button>
        `;
      })
      .join("")}
    ${clusters
      .map((cluster, index) => {
        const level = index % 2;
        const realTask = cluster.items.find((item) => item.taskId) || cluster.items[0];
        const clusterProgress = cluster.left / 100;
        const beforeCutoff = selectedProgress != null && clusterProgress <= selectedProgress + 0.0001;
        const dueLabel = formatMaintenanceTimelineValue(cluster.items[0].dueValue, lane.kind);
        const title = cluster.items
          .map((item) => `${item.title} | ${item.note} | Due ${formatMaintenanceTimelineValue(item.dueValue, lane.kind)}`)
          .join("\n");
        const tooltipTitle = cluster.items.length > 1 ? `${dueLabel} · ${cluster.items.length} tasks` : `${dueLabel} · ${cluster.items[0].title}`;
        return `
          <button
            class="maintenance-header-pin tone-${lane.tone} level-${level} ${(realTask.taskId && realTask.taskId === selectedTaskId) ? "is-active" : ""} ${beforeCutoff ? "is-before-cutoff" : ""}"
            type="button"
            style="left:${cluster.left}%;"
            title="${escapeHtml(title)}"
            aria-label="${escapeHtml(title)}"
          >
            <span class="maintenance-header-pin-dot"></span>
            ${cluster.items.length > 1 ? `<span class="maintenance-header-pin-count">${cluster.items.length}</span>` : ""}
            <span class="maintenance-header-tooltip">
              <strong>${escapeHtml(tooltipTitle)}</strong>
              ${cluster.items
                .slice(0, 6)
                .map((item) => `<span>${escapeHtml(item.title)} · ${escapeHtml(item.note)}</span>`)
                .join("")}
              ${cluster.items.length > 6 ? `<em>+${cluster.items.length - 6} more</em>` : ""}
            </span>
          </button>
        `;
      })
      .join("")}
  `;
}

function maintenancePrepHorizonPlotMarkup(data, selectedTaskId, cutoffMap = {}, prepMap = {}, focusLaneKey = "", horizonMap = {}, horizonFoldOpen = false, activeStageKey = "need-prep", actionState = null, selectedReadyTaskIds = []) {
  const sourceRows = maintenancePrepTimelineSourceTasks(data);
  const lanes = buildMaintenanceTimelineLanes(data, {
    sourceTasks: sourceRows,
    limit: 24,
    horizonMap,
  });
  const demoNow = new Date();
  const demoSourceRows = sourceRows;
  const laneProgressMap = maintenanceExecuteProgressMapForLanes(lanes, selectedTaskId, cutoffMap);
  const lanePrepMap = maintenancePrepProgressMapForLanes(lanes, prepMap);
  const focusLane = lanes.find((lane) => lane.key === focusLaneKey)
    || lanes.find((lane) => lane.items.some((item) => item.taskId && item.taskId === selectedTaskId))
    || lanes.find((lane) => lane.items.some((item) => item.taskId))
    || lanes[0];
  const executeTasksBefore = maintenanceUniqueTasks(
    maintenancePlottedTasksBeforeMarker(lanes, laneProgressMap, { demoNow, demoSourceRows }),
  );
  const prepTasksBefore = maintenanceUniqueTasks(
    maintenancePlottedTasksBeforeMarker(lanes, lanePrepMap, { demoNow, demoSourceRows }),
  );
  return `
    <details class="maintenance-horizon-rangefold" ${horizonFoldOpen ? "open" : ""}>
      <summary class="maintenance-horizon-rangefold-summary">
        <span>Horizon range</span>
        <strong>Now to X by lane</strong>
      </summary>
      <div class="maintenance-horizon-rangebar">
        ${lanes.map((lane) => {
          const currentRange = lane.kind === "calendar"
            ? Math.max(1, Math.round((lane.max.getTime() - lane.min.getTime()) / (24 * 60 * 60 * 1000)))
            : Math.max(1, Math.round(Number(lane.max) - Number(lane.min)));
          const unit = lane.kind === "calendar" ? "d" : lane.kind === "draws" ? "draws" : "h";
          const sliderMax = Math.max(currentRange, maintenanceLaneRangeFieldMax(lane, sourceRows));
          return `
            <label class="maintenance-horizon-rangefield">
              <span>${escapeHtml(lane.title)}</span>
              <input type="range" min="1" max="${sliderMax}" step="1" value="${currentRange}" data-maint-horizon-range-slider="${escapeHtml(lane.key)}" aria-label="Horizon slider for ${escapeHtml(lane.title)}" />
              <input type="number" min="1" max="${sliderMax}" step="1" value="${currentRange}" data-maint-horizon-range="${escapeHtml(lane.key)}" aria-label="Horizon length for ${escapeHtml(lane.title)}" />
              <em>${unit}</em>
            </label>
          `;
        }).join("")}
      </div>
    </details>
    <div class="maintenance-horizon-plot">
      ${lanes
        .map((lane) => {
          const effectiveProgress = laneProgressMap[lane.key];
          const prepProgress = lanePrepMap[lane.key];
          const min = lane.kind === "calendar" ? lane.min.getTime() : Number(lane.min);
          const max = lane.kind === "calendar" ? lane.max.getTime() : Number(lane.max);
          const range = Math.max(1, max - min);
          const current = lane.kind === "calendar" ? lane.current.getTime() : Number(lane.current);
          const currentLeft = ((current - min) / range) * 100;
          const allActualItems = maintenanceLaneActualItems(sourceRows, lane.key);
          const realItems = lane.items.filter((item) => item.status !== "PREVIEW");
          const clusters = [];
          realItems.forEach((item) => {
            const due = lane.kind === "calendar" ? item.dueValue.getTime() : Number(item.dueValue);
            const left = ((due - min) / range) * 100;
            const normalizedLeft = Math.max(1, Math.min(99, left));
            const bucket = Math.round(normalizedLeft / 4);
            const existing = clusters.find((cluster) => cluster.bucket === bucket);
            if (existing) {
              existing.items.push(item);
              existing.left = (existing.left * (existing.items.length - 1) + normalizedLeft) / existing.items.length;
            } else {
              clusters.push({ bucket, left: normalizedLeft, items: [item] });
            }
          });
          const nextActualItem = allActualItems
            .filter((item) => {
              const due = lane.kind === "calendar" ? item.dueValue.getTime() : Number(item.dueValue);
              return Number.isFinite(due) && due > max;
            })
            .sort((a, b) => {
              const left = lane.kind === "calendar" ? a.dueValue.getTime() : Number(a.dueValue);
              const right = lane.kind === "calendar" ? b.dueValue.getTime() : Number(b.dueValue);
              return left - right;
            })[0] || null;
          return `
            <div class="maintenance-horizon-plot-lane">
              <div class="maintenance-horizon-plot-label">
                <span>${lane.title}</span>
                <strong>${lane.subtitle}</strong>
                <em>Current ${escapeHtml(formatMaintenanceTimelineValue(lane.current, lane.kind))}</em>
              </div>
              <div class="maintenance-horizon-plot-stack">
                <div class="maintenance-header-axis">${maintenanceLaneTicksMarkup(lane)}</div>
                <div class="maintenance-header-lane-track maintenance-horizon-plot-track">
                  <div class="maintenance-header-grid">
                    ${Array.from({ length: 6 }, () => `<span class="maintenance-header-grid-line"></span>`).join("")}
                  </div>
                  ${prepProgress != null ? `<div class="maintenance-horizon-prep-band" style="width:${prepProgress * 100}%;" data-maint-horizon-prep-band="${escapeHtml(lane.key)}" aria-hidden="true"></div>` : ""}
                  ${effectiveProgress != null ? `<div class="maintenance-horizon-cutoff-band" style="width:${effectiveProgress * 100}%;" data-maint-horizon-cutoff-band="${escapeHtml(lane.key)}" aria-hidden="true"></div>` : ""}
                  ${prepProgress != null ? `<button class="maintenance-horizon-prep-line" type="button" style="left:${prepProgress * 100}%;" data-maint-horizon-prep="${escapeHtml(lane.key)}" aria-label="Adjust preparation marker for ${escapeHtml(lane.title)}"></button>` : ""}
                  ${effectiveProgress != null ? `<button class="maintenance-horizon-cutoff-line" type="button" style="left:${effectiveProgress * 100}%;" data-maint-horizon-cutoff="${escapeHtml(lane.key)}" aria-label="Adjust execute line for ${escapeHtml(lane.title)}"></button>` : ""}
                  <div class="maintenance-header-now-line" style="left:${Math.max(0, Math.min(100, currentLeft))}%;">
                    <span>Now</span>
                  </div>
                  ${clusters
                    .map((cluster, index) => {
                      const level = index % 2;
                      const realTask = cluster.items.find((item) => item.taskId) || cluster.items[0];
                      const tooltipTitle = cluster.items.length > 1
                        ? `${formatMaintenanceTimelineValue(cluster.items[0].dueValue, lane.kind)} · ${cluster.items.length} tasks`
                        : `${formatMaintenanceTimelineValue(cluster.items[0].dueValue, lane.kind)} · ${realTask.title}`;
                      const clusterProgress = cluster.left / 100;
                      const beforeCutoff = effectiveProgress != null && clusterProgress <= effectiveProgress + 0.0001;
                      return `
                        <button
                          class="maintenance-header-pin maintenance-horizon-plot-pin tone-${lane.tone} level-${level} ${(realTask.taskId && realTask.taskId === selectedTaskId) ? "is-active" : ""} ${beforeCutoff ? "is-before-cutoff" : ""}"
                          type="button"
                          style="left:${cluster.left}%;"
                          data-maint-horizon-progress="${clusterProgress}"
                          data-maint-horizon-task="${escapeHtml(realTask.taskId || "")}"
                          aria-disabled="${realTask.taskId ? "false" : "true"}"
                          title="${escapeHtml(cluster.items.map((item) => `${item.title} | ${item.note}`).join("\n"))}"
                        >
                          <span class="maintenance-header-pin-dot"></span>
                          ${cluster.items.length > 1 ? `<span class="maintenance-header-pin-count">${cluster.items.length}</span>` : ""}
                          <span class="maintenance-header-tooltip">
                            <strong>${escapeHtml(tooltipTitle)}</strong>
                            ${cluster.items.slice(0, 6).map((item) => `<span>${escapeHtml(item.title)} · ${escapeHtml(item.note)}</span>`).join("")}
                            ${cluster.items.length > 6 ? `<em>+${cluster.items.length - 6} more</em>` : ""}
                          </span>
                        </button>
                        `;
                    })
                    .join("")}
                  ${!realItems.length ? `
                    <div class="maintenance-header-lane-empty maintenance-horizon-lane-empty">
                      <strong>No actual tasks in this horizon</strong>
                      <span>${nextActualItem ? `Next due at ${escapeHtml(formatMaintenanceTimelineValue(nextActualItem.dueValue, lane.kind))}` : "No due task on this lane yet"}</span>
                    </div>
                  ` : ""}
                </div>
              </div>
            </div>
          `;
        })
        .join("")}
    </div>
    ${maintenancePrepLiveShellMarkup(data, executeTasksBefore, prepTasksBefore, activeStageKey, maintenanceStageFlash, actionState, selectedReadyTaskIds)}
  `;
}

function maintenanceHeaderTimelineMarkup(data, horizonMap = {}, options = {}) {
  const sourceRows = options.sourceTasks || maintenanceUniqueTasks([...(data?.tasks || []), ...(data?.prep_queue || [])]);
  const showPreviewItems = options.showPreviewItems !== false;
  const lanes = buildMaintenanceTimelineLanes(data, {
    sourceTasks: sourceRows,
    limit: 24,
    horizonMap,
  });
  const dueTaskCount = maintenanceUniqueTasks(
    lanes.flatMap((lane) => lane.items.map((item) => item.taskData).filter(Boolean)),
  ).length;
  const demoSourceRows = sourceRows;
  const demoNow = new Date();
  const runtime = data.timeline_runtime || {};
  const runtimeSummary = `Furnace ${Math.round(numericOr(runtime.furnace_hours, 0))}h · UV1 ${Math.round(numericOr(runtime.uv1_hours, 0))}h · UV2 ${Math.round(numericOr(runtime.uv2_hours, 0))}h · Draw ${Math.round(numericOr(runtime.draw_count, 0))}`;
  const previewCount = lanes.reduce((sum, lane) => sum + lane.items.filter((item) => item.status === "PREVIEW").length, 0);
  return `
    <section class="maintenance-header-timeline">
      <div class="maintenance-header-timeline-top">
        <div class="maintenance-header-timeline-copy">
          <span>Maintenance timeline</span>
          <strong>Original Tower logic lanes</strong>
          <p>Due positions use the saved maintenance runtime for hours, while draw count is derived from the live <code>data_set_csv</code> workspace. ${escapeHtml(runtimeSummary)}${previewCount ? ` · ${previewCount} preview markers fill empty lanes.` : ""}</p>
        </div>
        <div class="maintenance-header-timeline-tools">
          <div class="maintenance-header-timeline-note">${dueTaskCount} due tasks</div>
          <details class="maintenance-runtime-fold">
            <summary>Update hours</summary>
            <form class="maintenance-runtime-form" id="maintenance-runtime-form">
              <label>
                <span>Furnace</span>
                <input type="number" step="0.1" name="furnaceHours" value="${escapeHtml(String(numericOr(runtime.furnace_hours, 0)))}" />
              </label>
              <label>
                <span>UV1</span>
                <input type="number" step="0.1" name="uv1Hours" value="${escapeHtml(String(numericOr(runtime.uv1_hours, 0)))}" />
              </label>
              <label>
                <span>UV2</span>
                <input type="number" step="0.1" name="uv2Hours" value="${escapeHtml(String(numericOr(runtime.uv2_hours, 0)))}" />
              </label>
              <label>
                <span>Draw</span>
                <input type="number" step="1" name="drawCount" value="${escapeHtml(String(numericOr(runtime.draw_count, 0)))}" readonly title="Auto-derived from the number of draw dataset CSV files in data_set_csv." />
              </label>
              <button class="mini-action" id="maintenance-runtime-save" type="button">Save</button>
            </form>
          </details>
        </div>
      </div>
      <div class="maintenance-header-lanes is-roadmap">
        ${lanes
          .map(
            (lane) => `
              <div class="maintenance-header-lane is-roadmap">
                <div class="maintenance-header-lane-label">
                  <span>${lane.title}</span>
                  <strong>${lane.subtitle}</strong>
                  <em>Current ${escapeHtml(formatMaintenanceTimelineValue(lane.current, lane.kind))}</em>
                </div>
                <div class="maintenance-header-lane-stack">
                  <div class="maintenance-header-axis">${maintenanceLaneTicksMarkup(lane)}</div>
                  <div class="maintenance-header-lane-track">
                    <div class="maintenance-header-grid">
                      ${Array.from({ length: 6 }, () => `<span class="maintenance-header-grid-line"></span>`).join("")}
                    </div>
                    ${maintenanceLaneItemsMarkup(lane, { demoSourceRows, demoNow, showPreviewItems })}
                  </div>
                </div>
              </div>
            `,
          )
          .join("")}
      </div>
    </section>
  `;
}

function maintenanceModeLeadMarkup(mode, data, task) {
  if (mode === "builder") {
    return `
      <div class="maintenance-lead">
        <div class="maintenance-lead-copy">
          <span>Builder flow</span>
          <strong>Build one maintenance package with the manual beside it</strong>
          <p>Choose a task, edit the package, and keep the source document in the same working surface.</p>
        </div>
      </div>
    `;
  }
  if (mode === "plan") {
    const scheduledCount = (data.execute_queue || []).filter((item) => String(item?.status || "").trim().toUpperCase() === "SCHEDULED").length;
    const prepPoolTasks = maintenanceUniqueTasks(
      (data.prep_queue || []).filter((item) => !maintenanceTaskIsPrepDone(item)),
    );
    const overduePrepPoolCount = prepPoolTasks.filter((item) => maintenanceTaskLooksOverdue(item)).length;
    return `
      <div class="maintenance-lead">
        <div class="maintenance-lead-copy">
          <span>Preparation flow</span>
          <strong>Use the next prep batch as the operating lane</strong>
          <p>This step is about what the shift should prepare next, not every maintenance task in the system. ${scheduledCount} scheduled${prepPoolTasks.length ? ` · ${prepPoolTasks.length} in prep pool` : ""}${overduePrepPoolCount ? ` · ${overduePrepPoolCount} overdue overall` : ""}.</p>
        </div>
      </div>
    `;
  }
  if (mode === "execute") {
    return `
      <div class="maintenance-lead">
        <div class="maintenance-lead-copy">
          <span>Execution flow</span>
          <strong>Start with the mode, not the full lane</strong>
          <p>Pick whether execution should come from the plan step or start manually, then we open only the tools that matter.</p>
        </div>
      </div>
    `;
  }
  if (mode === "blocked") {
    return `
      <div class="maintenance-lead">
        <div class="maintenance-lead-copy">
          <span>Blocked flow</span>
          <strong>See the blockers before they turn into stop-time surprises</strong>
          <p>Use this lane for missing parts, linked order gaps, and the tasks that still need preparation work before a stop window.</p>
        </div>
        <div class="token-strip">
          <span class="token-chip">${(data.blocked_tracker || []).length} blocked rows</span>
          <span class="token-chip is-accent">${(data.smart_todo || []).length} urgent items</span>
        </div>
      </div>
    `;
  }
  return `
    <div class="maintenance-lead">
      <div class="maintenance-lead-copy">
        <span>History flow</span>
        <strong>Recent actions and completion record</strong>
        <p>Use this lane for a tight review of what was already done instead of mixing history into live preparation.</p>
      </div>
      <div class="token-strip">
        <span class="token-chip is-accent">${(data.recent_actions || []).length} actions</span>
        <span class="token-chip">${(data.completed_ids || []).length} completed ids</span>
      </div>
    </div>
  `;
}

function maintenanceTaskRailMarkup(rows, selectedTaskId, options = {}) {
  const { empty = "No maintenance rows in this lane.", variant = "default" } = options;
  if (!rows?.length) {
    return `<div class="chart-empty">${empty}</div>`;
  }
  if (variant === "plan") {
    return rows
      .map(
        (item) => `
          <button class="maintenance-rail-item maintenance-rail-item-plan ${selectedTaskId === item.task_id ? "is-active" : ""}" type="button" data-maint-select="${item.task_id}">
            <div class="maintenance-rail-item-plan-main">
              <span class="maintenance-rail-top">
                <em>${item.component}</em>
                <i class="status-badge tone-${toneForLabel(item.status || item.severity)}">${item.status || item.severity || "Info"}</i>
              </span>
              <strong>${item.task || item.title || "Task"}</strong>
              <small>${item.task_group || item.flow_state || item.ts || item.task_id || ""}</small>
            </div>
            <div class="maintenance-rail-item-plan-meta">
              <span>${item.work_package?.last_updated ? "Package saved" : "Needs package"}</span>
              <strong>${(item.missing_parts || []).length ? `${item.missing_parts.length} missing` : "Parts ready"}</strong>
            </div>
          </button>
        `,
      )
      .join("");
  }
  return rows
    .map(
      (item) => `
        <button class="maintenance-rail-item ${selectedTaskId === item.task_id ? "is-active" : ""}" type="button" data-maint-select="${item.task_id}">
          <span class="maintenance-rail-top">
            <em>${item.component}</em>
            <i class="status-badge tone-${toneForLabel(item.status || item.severity)}">${item.status || item.severity || "Info"}</i>
          </span>
          <strong>${item.task || item.title || "Task"}</strong>
          <small>${item.task_group || item.flow_state || item.ts || item.task_id || ""}</small>
        </button>
      `,
    )
    .join("");
}

function maintenanceManualPreviewMarkup(task) {
  if (!task?.manual_link) {
    return `<div class="chart-empty">No manual or document is linked to this task yet.</div>`;
  }
  const manualUrl = `/api/maintenance/manual?path=${encodeURIComponent(task.manual_link)}`;
  const lower = String(task.manual_link).toLowerCase();
  const pageSuffix = task.manual_page ? `#page=${task.manual_page}` : "";
  if (lower.endsWith(".pdf")) {
    return `
      <div class="maintenance-manual-preview">
        <div class="micro-row"><span>Manual</span><strong>${task.manual_name || "PDF manual"}</strong></div>
        <iframe class="maintenance-manual-frame" src="${manualUrl}${pageSuffix}" title="${task.manual_name || "Manual PDF"}"></iframe>
      </div>
    `;
  }
  if (/\.(png|jpg|jpeg|webp|gif|bmp)$/i.test(lower)) {
    return `
      <div class="maintenance-manual-preview">
        <div class="micro-row"><span>Manual image</span><strong>${task.manual_name || "Linked image"}</strong></div>
        <img class="maintenance-manual-image" src="${manualUrl}" alt="${task.manual_name || "Manual preview"}" />
      </div>
    `;
  }
  return `
    <div class="maintenance-manual-preview">
      <div class="micro-row"><span>Document</span><strong>${task.manual_name || task.manual_link}</strong></div>
      <a class="action-btn action-secondary" href="${manualUrl}" target="_blank" rel="noopener noreferrer">Open linked document</a>
    </div>
  `;
}

function maintenancePhotoGalleryMarkup(value, preparationValue = "", stepsValue = "") {
  const stepOptions = buildMaintenancePhotoTargetOptions(preparationValue, stepsValue);
  const photos = syncBuilderPhotoItemsToSteps(parseBuilderPhotoItems(value), stepOptions);
  if (!photos.length) {
    return `<div class="chart-empty">No procedure photos are saved for this task yet.</div>`;
  }
  const groups = stepOptions
    .map((option) => ({
      ...option,
      items: photos.filter((photo) => photo.step_key === option.key),
    }))
    .filter((group) => group.items.length);
  const general = photos.filter((photo) => !photo.step_key);
  return `
    <div class="maintenance-photo-groups">
      ${groups
        .map(
          (group) => `
            <section class="maintenance-photo-group">
              <div class="chart-head">
                <span>${escapeHtml(group.scope)}</span>
                <strong>${escapeHtml(group.label)}</strong>
              </div>
              <div class="maintenance-photo-grid">
                ${group.items
                  .map(
                    (photo) => `
                      <figure class="maintenance-photo-thumb">
                        <a class="maintenance-photo-link" href="${escapeHtml(photo.path)}" target="_blank" rel="noopener noreferrer">
                          <img src="${escapeHtml(photo.path)}" alt="${escapeHtml(photo.name || builderFileLabel(photo.path))}" loading="lazy" />
                        </a>
                        <figcaption>${escapeHtml(photo.name || builderFileLabel(photo.path))}</figcaption>
                      </figure>
                    `,
                  )
                  .join("")}
              </div>
            </section>
          `,
        )
        .join("")}
      ${
        general.length
          ? `
            <section class="maintenance-photo-group">
              <div class="chart-head">
                <span>General reference</span>
                <strong>Not tied to one step</strong>
              </div>
              <div class="maintenance-photo-grid">
                ${general
                  .map(
                    (photo) => `
                      <figure class="maintenance-photo-thumb">
                        <a class="maintenance-photo-link" href="${escapeHtml(photo.path)}" target="_blank" rel="noopener noreferrer">
                          <img src="${escapeHtml(photo.path)}" alt="${escapeHtml(photo.name || builderFileLabel(photo.path))}" loading="lazy" />
                        </a>
                        <figcaption>${escapeHtml(photo.name || builderFileLabel(photo.path))}</figcaption>
                      </figure>
                    `,
                  )
                  .join("")}
              </div>
            </section>
          `
          : ""
      }
    </div>
  `;
}

function maintenanceLinkedChecklistMarkup(title, value, prefix, photoValue, emptyMessage) {
  const items = parseChecklistSeedItems(value, prefix).filter((item) => String(item?.text || "").trim());
  const targetOptions = prefix === "prep"
    ? buildMaintenancePhotoTargetOptions(value, "")
    : buildMaintenancePhotoTargetOptions("", value);
  const photos = syncBuilderPhotoItemsToSteps(parseBuilderPhotoItems(photoValue), targetOptions);
  if (!items.length) {
    return `
      <section class="maintenance-linked-checklist">
        <div class="chart-head">
          <span>${escapeHtml(title)}</span>
          <strong>0 rows</strong>
        </div>
        <div class="micro-panel">${escapeHtml(emptyMessage)}</div>
      </section>
    `;
  }
  return `
    <section class="maintenance-linked-checklist">
      <div class="chart-head">
        <span>${escapeHtml(title)}</span>
        <strong>${items.length} row${items.length === 1 ? "" : "s"}</strong>
      </div>
      <div class="maintenance-linked-checklist-list">
        ${items
          .map((item, index) => {
            const targetKey = `${prefix}:${item.id}`;
            const linkedPhotos = photos.filter((photo) => photo.step_key === targetKey);
            return `
              <div class="maintenance-linked-checklist-row">
                <div class="maintenance-linked-checklist-copy">
                  <span>${index + 1}</span>
                  <strong>${escapeHtml(item.text)}</strong>
                </div>
                ${
                  linkedPhotos.length
                    ? `
                      <div class="maintenance-linked-checklist-photos">
                        ${linkedPhotos
                          .map(
                            (photo) => `
                              <figure class="maintenance-photo-thumb">
                                <a class="maintenance-photo-link" href="${escapeHtml(photo.path || photo.preview)}" target="_blank" rel="noopener noreferrer">
                                  <img src="${escapeHtml(photo.path || photo.preview)}" alt="${escapeHtml(photo.name || builderFileLabel(photo.path || photo.preview))}" loading="lazy" />
                                </a>
                                <figcaption>${escapeHtml(photo.name || builderFileLabel(photo.path || photo.preview))}</figcaption>
                              </figure>
                            `,
                          )
                          .join("")}
                      </div>
                    `
                    : ""
                }
              </div>
            `;
          })
          .join("")}
      </div>
    </section>
  `;
}

function normalizeSanityTemplateItem(item = {}, fallbackLabel = "") {
  const kind = ["check", "number", "text", "passfail"].includes(String(item.kind || "").trim())
    ? String(item.kind || "").trim()
    : "check";
  const mode = kind === "number" && ["target", "monitor"].includes(String(item.mode || "").trim())
    ? String(item.mode || "").trim()
    : "target";
  return {
    kind,
    mode,
    label: String(item.label || fallbackLabel || "").trim(),
    unit: String(item.unit || "").trim(),
    sample: String(item.sample || "").trim(),
    placeholder: String(item.placeholder || "").trim(),
  };
}

function parseSanityTemplateItems(value) {
  const raw = String(value || "").trim();
  if (!raw) return [];
  if (raw.startsWith("[")) {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed
          .map((item) => normalizeSanityTemplateItem(item))
          .filter((item) => item.label);
      }
    } catch (error) {
      // Fall back to legacy checklist parsing below.
    }
  }
  return parseChecklistItems(raw)
    .map((item) => normalizeSanityTemplateItem({ kind: "check", label: item.text }))
    .filter((item) => item.label);
}

function serializeSanityTemplateItems(items) {
  return JSON.stringify(
    items
      .map((item) => normalizeSanityTemplateItem(item))
      .filter((item) => item.label),
  );
}

function sanityTemplateKindLabel(kindOrItem, maybeMode = "") {
  const kind = typeof kindOrItem === "object" ? String(kindOrItem.kind || "").trim() : String(kindOrItem || "").trim();
  const mode = typeof kindOrItem === "object" ? String(kindOrItem.mode || "").trim() : String(maybeMode || "").trim();
  if (kind === "number") return mode === "monitor" ? "Monitor reading" : "Target reading";
  if (kind === "text") return "Text";
  if (kind === "passfail") return "Pass / fail";
  return "Checklist";
}

function sanityTemplatePreviewNote(item = {}) {
  if (item.kind === "number") {
    if (item.mode === "monitor") {
      return item.sample || [item.unit && `Monitor (${item.unit})`, "No target value"].filter(Boolean).join(" · ") || "Monitor reading";
    }
    return [item.sample || "Target", item.unit].filter(Boolean).join(" ");
  }
  if (item.kind === "text") return item.placeholder || "Free operator note";
  if (item.kind === "passfail") return item.sample || "Pass / fail check";
  return item.sample || "Checklist confirmation";
}

function maintenanceSanityTemplateSummaryMarkup(value, emptyMessage) {
  const items = parseSanityTemplateItems(value);
  if (!items.length) {
    return `<div class="chart-empty">${escapeHtml(emptyMessage || "No sanity template saved yet.")}</div>`;
  }
  const counts = items.reduce((acc, item) => {
    const key = String(item.kind || "check").trim().toLowerCase() || "check";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const parts = [];
  if (counts.check) parts.push(`${counts.check} checklist`);
  if (counts.passfail) parts.push(`${counts.passfail} pass / fail`);
  if (counts.number) parts.push(`${counts.number} reading`);
  if (counts.text) parts.push(`${counts.text} note`);
  return `
    <div class="maintenance-execute-readblock">
      <span>Closeout flow</span>
      <p>${escapeHtml(`${items.length} operator input${items.length === 1 ? "" : "s"} continue below${parts.length ? ` · ${parts.join(" · ")}` : ""}.`)}</p>
    </div>
  `;
}

function parseSanityResultItems(value) {
  const raw = String(value || "").trim();
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    return [];
  }
}

function maintenanceSanityRuntimeMarkup(value, resultsValue = "") {
  const items = parseSanityTemplateItems(value);
  const results = parseSanityResultItems(resultsValue);
  if (!items.length) {
    return `<div class="chart-empty">No closeout inputs were defined in the builder yet.</div>`;
  }
  return `
    <div class="maintenance-sanity-runtime-list">
      ${items
        .map((item, index) => {
          const result = results[index] || {};
          const doneChecked = Boolean(result.checked);
          const runtimeLabel = escapeHtml(item.label || `Input ${index + 1}`);
          const runtimeType = escapeHtml(sanityTemplateKindLabel(item));
          const helper = escapeHtml(sanityTemplatePreviewNote(item));
          if (item.kind === "check") {
            return `
              <article class="maintenance-sanity-runtime-card tone-good" data-maint-sanity-runtime-item="${index}" data-kind="${escapeHtml(item.kind)}" data-mode="${escapeHtml(item.mode)}" data-label="${runtimeLabel}">
                <div class="maintenance-sanity-runtime-head">
                  <span>${runtimeType}</span>
                  <strong>${runtimeLabel}</strong>
                </div>
                <p>${helper}</p>
                <label class="maintenance-sanity-runtime-box maintenance-sanity-runtime-check">
                  <input type="checkbox" data-maint-sanity-runtime-check="${index}" ${doneChecked ? "checked" : ""} />
                  <span>Checked / done</span>
                </label>
              </article>
            `;
          }
          if (item.kind === "number") {
            return `
              <article class="maintenance-sanity-runtime-card tone-info" data-maint-sanity-runtime-item="${index}" data-kind="${escapeHtml(item.kind)}" data-mode="${escapeHtml(item.mode)}" data-label="${runtimeLabel}" data-unit="${escapeHtml(item.unit)}" data-sample="${escapeHtml(item.sample)}">
                <div class="maintenance-sanity-runtime-head">
                  <span>${runtimeType}</span>
                  <strong>${runtimeLabel}</strong>
                </div>
                <div class="maintenance-sanity-runtime-metrics">
                  <div class="maintenance-sanity-runtime-box is-ghost">
                    <small>${item.mode === "monitor" ? "Monitor" : "Target"}</small>
                    <strong>${escapeHtml(item.mode === "monitor" ? (item.unit ? `${item.unit} reading` : "Live reading") : [item.sample || "Target", item.unit].filter(Boolean).join(" "))}</strong>
                  </div>
                  <label class="maintenance-sanity-runtime-box">
                    <small>Measured value</small>
                    <input type="number" step="any" value="${escapeHtml(String(result.value || ""))}" placeholder="${escapeHtml(item.mode === "monitor" ? "Enter observed value" : "Enter result against target")}" data-maint-sanity-runtime-value="${index}" />
                  </label>
                </div>
              </article>
            `;
          }
          if (item.kind === "passfail") {
            return `
              <article class="maintenance-sanity-runtime-card tone-warn" data-maint-sanity-runtime-item="${index}" data-kind="${escapeHtml(item.kind)}" data-mode="${escapeHtml(item.mode)}" data-label="${runtimeLabel}" data-sample="${escapeHtml(item.sample)}">
                <div class="maintenance-sanity-runtime-head">
                  <span>${runtimeType}</span>
                  <strong>${runtimeLabel}</strong>
                </div>
                <p>${helper}</p>
                <label class="maintenance-sanity-runtime-box">
                  <small>Result</small>
                  <select data-maint-sanity-runtime-status="${index}">
                    <option value="">Choose</option>
                    <option value="pass" ${result.status === "pass" ? "selected" : ""}>Pass</option>
                    <option value="fail" ${result.status === "fail" ? "selected" : ""}>Fail</option>
                    <option value="monitor" ${result.status === "monitor" ? "selected" : ""}>Monitor only</option>
                  </select>
                </label>
              </article>
            `;
          }
          return `
            <article class="maintenance-sanity-runtime-card tone-good" data-maint-sanity-runtime-item="${index}" data-kind="${escapeHtml(item.kind)}" data-mode="${escapeHtml(item.mode)}" data-label="${runtimeLabel}">
              <div class="maintenance-sanity-runtime-head">
                <span>${runtimeType}</span>
                <strong>${runtimeLabel}</strong>
              </div>
              <label class="maintenance-sanity-runtime-box">
                <small>Operator note</small>
                <textarea rows="3" placeholder="${escapeHtml(item.placeholder || "Type the operator note here")}" data-maint-sanity-runtime-text="${index}">${escapeHtml(String(result.value || ""))}</textarea>
              </label>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function maintenanceSanityGateMarkup(task) {
  return `
    <div class="maintenance-execute-close-grid">
      <div class="maintenance-execute-close-block">
        <span>After-task sanity checklist</span>
        ${maintenanceSanityTemplateSummaryMarkup(task?.work_package?.sanity_checklist, "No sanity template is saved yet for this task.")}
      </div>
      <div class="maintenance-execute-close-block">
        <span>Closeout acceptance</span>
        <p>${escapeHtml(task?.work_package?.completion_criteria || "No acceptance criteria is saved yet.")}</p>
        <span>Stop / pause plan</span>
        <p>${escapeHtml(task?.work_package?.draw_stop_plan || "No stop plan is saved yet.")}</p>
      </div>
    </div>
  `;
}

function maintenanceExecutePlanRows(data) {
  return maintenanceUniqueTasks(
    ([...(data.execute_queue || []), ...(data.execute_plan_queue || [])].filter((item) => {
      const status = String(item?.status || "").trim().toUpperCase();
      return ["SCHEDULED", "IN_PROGRESS"].includes(status)
        && (Boolean(item?.plan_forwarded) || status === "SCHEDULED");
    })),
  ).sort((a, b) => {
    const rank = { IN_PROGRESS: 0, SCHEDULED: 1 };
    return (
      (rank[String(a?.status || "").trim().toUpperCase()] ?? 9) -
        (rank[String(b?.status || "").trim().toUpperCase()] ?? 9) ||
      String(a?.component || "").localeCompare(String(b?.component || "")) ||
      String(a?.task || "").localeCompare(String(b?.task || ""))
    );
  });
}

function maintenanceExecuteLauncherMarkup(data, activeMode = "", openTaskId = "", manualSearch = "", manualComponent = "") {
  const executeRows = (data.execute_queue || [])
    .filter((item) => ["SCHEDULED", "IN_PROGRESS"].includes(String(item?.status || "").trim().toUpperCase()))
    .sort((a, b) => {
      const rank = { IN_PROGRESS: 0, SCHEDULED: 1 };
      return (
        (rank[String(a?.status || "").trim().toUpperCase()] ?? 9) -
          (rank[String(b?.status || "").trim().toUpperCase()] ?? 9) ||
        String(a?.component || "").localeCompare(String(b?.component || "")) ||
        String(a?.task || "").localeCompare(String(b?.task || ""))
      );
    });
  const planRows = maintenanceExecutePlanRows(data);
  const scheduledCount = executeRows.filter((item) => String(item?.status || "").trim().toUpperCase() === "SCHEDULED").length;
  const inProgressCount = executeRows.filter((item) => String(item?.status || "").trim().toUpperCase() === "IN_PROGRESS").length;
  const options = [
    {
      key: "plan",
      eyebrow: "From plan",
      title: "Make tasks from plan step",
      body: "Use only the tasks that were actually passed forward from the plan lane into execution.",
      note: planRows.length
        ? `${planRows.length} task${planRows.length === 1 ? "" : "s"} passed forward from plan`
        : "Nothing has been passed forward from plan yet",
    },
    {
      key: "manual",
      eyebrow: "Manual start",
      title: "Execute manually",
      body: "Start a manual execution lane for work that needs to begin directly from the floor.",
      note: executeRows.length
        ? `${inProgressCount} active · ${scheduledCount} scheduled in execute`
        : "Best for urgent or operator-led execution",
    },
  ];
  const selected = options.find((option) => option.key === activeMode);
  const plannedRows = planRows.slice(0, 10);
  const manualRowsSource = data.tasks || [];
  const manualComponentOptions = Array.from(new Set(manualRowsSource.map((item) => item.component).filter(Boolean))).sort((a, b) => a.localeCompare(b));
  const manualNeedle = String(manualSearch || "").trim().toLowerCase();
  const manualRows = manualRowsSource
    .filter((item) => {
      if (manualComponent && String(item.component || "") !== manualComponent) return false;
      if (!manualNeedle) return true;
      const blob = JSON.stringify([
        item.component,
        item.task,
        item.task_id,
        item.task_group,
        ...(item.required_parts || []),
      ]).toLowerCase();
      return blob.includes(manualNeedle);
    })
    .slice(0, 12);
  const planListMarkup = plannedRows.length
    ? `
        <div class="maintenance-execute-plan-list">
          ${plannedRows
            .map(
              (item) => {
                const scheduleNote = (item.scheduled_window_labels || []).filter(Boolean)[0] || "";
                return `
                <div class="maintenance-execute-plan-row ${openTaskId === item.task_id ? "is-open" : ""}">
                  <button class="maintenance-execute-plan-item ${openTaskId === item.task_id ? "is-active" : ""}" type="button" data-maint-execute-task="${item.task_id}">
                    <div class="maintenance-execute-plan-item-copy">
                      <span>${escapeHtml(item.component || "Task")}</span>
                      <strong>${escapeHtml(item.task || item.title || "Planned maintenance task")}</strong>
                      <p>${escapeHtml(item.task_group || item.flow_state || item.task_id || "")}</p>
                    </div>
                    <div class="maintenance-execute-plan-item-meta">
                      <em>${escapeHtml(scheduleNote || ((item.missing_parts || []).length ? `${item.missing_parts.length} missing` : "Passed from plan"))}</em>
                      <i class="status-badge tone-${toneForLabel(item.status || item.severity)}">${escapeHtml(item.status || item.severity || "Planned")}</i>
                    </div>
                  </button>
                  ${openTaskId === item.task_id ? `<div class="maintenance-execute-inline-detail">${maintenanceExecuteManualDetailMarkup(item)}</div>` : ""}
                </div>
              `;
              },
            )
            .join("")}
        </div>
      `
    : `<div class="chart-empty">No tasks have been passed forward from the plan lane yet.</div>`;
  const manualListMarkup = manualRows.length
    ? `
        <div class="maintenance-execute-plan-list">
          ${manualRows
            .map(
              (item) => `
                <div class="maintenance-execute-plan-row ${openTaskId === item.task_id ? "is-open" : ""}">
                  <button class="maintenance-execute-plan-item ${openTaskId === item.task_id ? "is-active" : ""}" type="button" data-maint-execute-task="${item.task_id}">
                    <div class="maintenance-execute-plan-item-copy">
                      <span>${escapeHtml(item.component || "Task")}</span>
                      <strong>${escapeHtml(item.task || item.title || "Manual maintenance task")}</strong>
                      <p>${escapeHtml(item.task_group || item.flow_state || item.task_id || "")}</p>
                    </div>
                    <div class="maintenance-execute-plan-item-meta">
                      <em>${(item.missing_parts || []).length ? `${item.missing_parts.length} missing` : "Ready to start"}</em>
                      <i class="status-badge tone-${toneForLabel(item.status || item.severity)}">${escapeHtml(item.status || item.severity || "Task")}</i>
                    </div>
                  </button>
                  ${openTaskId === item.task_id ? `<div class="maintenance-execute-inline-detail">${maintenanceExecuteManualDetailMarkup(item)}</div>` : ""}
                </div>
              `,
            )
            .join("")}
        </div>
      `
    : `<div class="chart-empty">No maintenance task matches this manual search right now.</div>`;
  return `
    <section class="maintenance-execute-launcher">
      <div class="maintenance-execute-launcher-head">
        <span>Execution modes</span>
        <strong>Choose how to start this maintenance action</strong>
      </div>
      <div class="maintenance-execute-launch-grid">
        ${options
          .map(
            (option) => `
              <button class="maintenance-execute-launch-card ${activeMode === option.key ? "is-active" : ""}" type="button" data-maint-execute-mode="${option.key}">
                <span>${option.eyebrow}</span>
                <strong>${option.title}</strong>
                <p>${option.body}</p>
                <em>${option.note}</em>
              </button>
            `,
          )
          .join("")}
      </div>
      ${
        activeMode === "plan"
          ? `
              <div class="maintenance-execute-plan-panel">
                <div class="maintenance-execute-plan-panel-head">
                  <span>Planned task list</span>
                  <strong>Compact handoff from the plan lane</strong>
                </div>
                ${planListMarkup}
              </div>
          `
          : activeMode === "manual"
            ? `
              <div class="maintenance-execute-plan-panel">
                <div class="maintenance-execute-plan-panel-head">
                  <span>Manual execution start</span>
                  <strong>Smart task finder</strong>
                  <p>Search by task, task id, part name, or component, then pick the task you want to start manually.</p>
                </div>
                <div class="maintenance-execute-manual-tools">
                  <input class="parts-search-input" id="maintenance-execute-manual-search" placeholder="Search task / task id / part / component..." value="${escapeHtml(manualSearch)}" />
                  <select class="maintenance-execute-manual-filter" id="maintenance-execute-manual-component">
                    <option value="">All components</option>
                    ${manualComponentOptions
                      .map((item) => `<option value="${escapeHtml(item)}" ${manualComponent === item ? "selected" : ""}>${escapeHtml(item)}</option>`)
                      .join("")}
                  </select>
                </div>
                ${manualListMarkup}
              </div>
            `
            : ""
      }
    </section>
  `;
}

function maintenanceExecuteMissingInputFields(task) {
  const wp = task?.work_package || {};
  const fields = [];
  if (!String(wp.est_stop_min || task?.est_duration_min || "").trim()) {
    fields.push({
      name: "estStopMin",
      label: "Estimated stop (min)",
      type: "number",
      placeholder: "Minutes",
      value: wp.est_stop_min || task?.est_duration_min || "",
    });
  }
  if (!String(wp.completion_criteria || "").trim()) {
    fields.push({
      name: "completionCriteria",
      label: "Acceptance criteria",
      type: "textarea",
      rows: 5,
      placeholder: "What must be true before the task is accepted as complete?",
      value: wp.completion_criteria || "",
    });
  }
  return fields;
}

function maintenanceExecuteManualInputFormMarkup(task) {
  const wp = task?.work_package || {};
  const fields = maintenanceExecuteMissingInputFields(task);
  const hiddenField = (name, value) => `<input type="hidden" name="${name}" value="${escapeHtml(String(value || ""))}" />`;
  const sanityRuntimeMarkup = maintenanceSanityRuntimeMarkup(wp.sanity_checklist, wp.sanity_results || "");
  const completionMarkup = `
    <input type="hidden" name="trackingMode" value="${escapeHtml(task?.tracking_mode || "")}" />
    ${hiddenField("sanityResults", wp.sanity_results || "")}
    <p class="maintenance-execute-manual-note">Saving here will also mark this task done and move it into the next maintenance interval.</p>
    <div class="order-builder-actions">
      <button class="action-btn action-primary" type="submit">${fields.length ? "Save operator fields + mark task done" : "Mark task done"}</button>
    </div>
  `;
  if (!fields.length) {
    return `
      <section class="maintenance-execute-manual-detail-card is-complete">
        <div class="chart-head">
          <span>Operator closeout</span>
          <strong>Run the closeout checks below</strong>
        </div>
        <p class="maintenance-execute-manual-note">Package setup is already complete. Execute only needs the operator closeout checks below before you mark this task done.</p>
        <form class="maintenance-execute-manual-form" id="maintenance-execute-manual-form">
          <input type="hidden" name="taskId" value="${escapeHtml(task.task_id || "")}" />
          <input type="hidden" name="component" value="${escapeHtml(task.component || "")}" />
          <input type="hidden" name="task" value="${escapeHtml(task.task || "")}" />
          <section class="maintenance-execute-manual-closeout">
            ${sanityRuntimeMarkup}
          </section>
          ${completionMarkup}
        </form>
      </section>
    `;
  }
  return `
    <section class="maintenance-execute-manual-detail-card">
      <div class="chart-head">
        <span>Operator closeout</span>
        <strong>Complete the remaining runtime values and closeout checks</strong>
      </div>
      <p class="maintenance-execute-manual-note">Builder owns the package setup. Execute only asks for the remaining runtime values needed before this task can be closed.</p>
      <form class="maintenance-execute-manual-form" id="maintenance-execute-manual-form">
        <input type="hidden" name="taskId" value="${escapeHtml(task.task_id || "")}" />
        <input type="hidden" name="component" value="${escapeHtml(task.component || "")}" />
        <input type="hidden" name="task" value="${escapeHtml(task.task || "")}" />
        ${hiddenField("taskGroup", task.task_group || "")}
        ${hiddenField("requiredParts", (task.required_parts || []).join("; "))}
        ${hiddenField("preparationChecklist", wp.preparation_checklist || "")}
        ${hiddenField("procedureSteps", wp.procedure_steps || "")}
        ${hiddenField("procedurePhotos", wp.procedure_photos || "")}
        ${hiddenField("sanityChecklist", wp.sanity_checklist || "")}
        ${hiddenField("safetyFallRisk", wp.safety_fall_risk || "Low")}
        ${hiddenField("safetyTnmPresence", wp.safety_tnm_presence || "Allowed")}
        ${hiddenField("supplierName", wp.supplier_name || "")}
        ${hiddenField("supplierDetails", wp.supplier_details || "")}
        <div class="maintenance-execute-manual-form-grid">
          ${fields
            .map((field) =>
              field.type === "textarea"
                ? `
                    <label class="field-block">
                      <span>${field.label}</span>
                      <textarea name="${field.name}" rows="${field.rows || 4}" placeholder="${escapeHtml(field.placeholder || "")}">${escapeHtml(field.value || "")}</textarea>
                    </label>
                  `
                : `
                    <label class="field-block maintenance-builder-field-compact">
                      <span>${field.label}</span>
                      <input type="${field.type}" name="${field.name}" value="${escapeHtml(field.value || "")}" placeholder="${escapeHtml(field.placeholder || "")}" />
                    </label>
                  `,
            )
            .join("")}
        </div>
        <section class="maintenance-execute-manual-closeout">
          ${sanityRuntimeMarkup}
        </section>
        ${completionMarkup}
      </form>
    </section>
  `;
}

function maintenanceExecuteManualDetailMarkup(task) {
  if (!task) {
    return `
      <div class="maintenance-execute-manual-detail-empty">
        <span>Selected task</span>
        <strong>Pick a task from the list above</strong>
        <p>When you press a manual task, its builder package and any missing operator inputs will open here.</p>
      </div>
    `;
  }
  const wp = task.work_package || {};
  const statusLabel = String(task.status || "").trim() || "Task";
  const statusUpper = statusLabel.toUpperCase();
  const isInProgress = statusUpper === "IN_PROGRESS";
  const canStart = statusUpper !== "DONE_NOW" && !isInProgress;
  const dueWindow = task.next_due_date || task.next_due_draw || task.next_due_hours || "—";
  const safetyProtocol = escapeHtml(wp.safety_protocol || task.safety_notes || "No safety protocol is stored yet.");
  const drawStopPlan = escapeHtml(wp.draw_stop_plan || "No draw stop plan is stored yet.");
  const completionCriteria = escapeHtml(wp.completion_criteria || "No acceptance criteria is stored yet.");
  const manualLink = String(task.manual_link || "").trim();
  const manualPageNumber = Number(task.manual_page || 0);
  const manualOpenUrl = manualLink
    ? `/api/maintenance/manual?path=${encodeURIComponent(manualLink)}${manualPageNumber > 0 ? `#page=${manualPageNumber}` : ""}`
    : "";
  const manualPagePdfUrl = manualLink && /\.pdf$/i.test(manualLink) && manualPageNumber > 0
    ? `/api/maintenance/manual-page-pdf?path=${encodeURIComponent(manualLink)}&page=${manualPageNumber}`
    : "";
  const liveStatusLabel = isInProgress ? "Maintenance in progress" : "Ready to start";
  const liveStatusNote = isInProgress
    ? "This task is currently active on the tower."
    : `Press Start task to make this live${statusLabel ? ` · queue state ${statusLabel}` : ""}.`;
  return `
    <div class="maintenance-execute-manual-detail">
      <section class="maintenance-execute-manual-detail-card is-hero">
        <div class="maintenance-execute-manual-detail-head">
          <span>Selected task</span>
          <strong>${escapeHtml(task.task || task.component || "Task")}</strong>
          <p>${escapeHtml(task.component ? `${task.component}${task.task_group ? ` · ${task.task_group}` : ""}` : "Manual execution task")}</p>
        </div>
        <div class="maintenance-execute-manual-detail-stats">
          <div class="maintenance-focus-stat tone-${wp.last_updated ? "good" : "warn"}">
            <span>Package</span>
            <strong>${wp.last_updated ? "Saved" : "Needs builder"}</strong>
          </div>
          <div class="maintenance-focus-stat tone-info">
            <span>Group</span>
            <strong>${escapeHtml(task.task_group || "General")}</strong>
          </div>
          <div class="maintenance-focus-stat tone-${(task.missing_parts || []).length ? "bad" : "good"}">
            <span>Parts</span>
            <strong>${(task.missing_parts || []).length ? `${task.missing_parts.length} missing` : "Ready"}</strong>
          </div>
          <div class="maintenance-focus-stat tone-info">
            <span>Stop time</span>
            <strong>${escapeHtml(String(wp.est_stop_min || task.est_duration_min || "—"))} min</strong>
          </div>
        </div>
        <div class="maintenance-execute-manual-actions">
          ${
            canStart
              ? `<button
                  class="action-btn action-primary"
                  type="button"
                  data-maint-execute-start="${escapeHtml(task.task_id || "")}"
                  data-maint-execute-component="${escapeHtml(task.component || "")}"
                  data-maint-execute-tasklabel="${escapeHtml(task.task || "")}"
                >Start task</button>`
              : ""
          }
          <div class="maintenance-execute-manual-liveflag ${isInProgress ? "is-live" : ""}">
            <span>Tower status</span>
            <strong>${escapeHtml(liveStatusLabel)}</strong>
            <em>${escapeHtml(liveStatusNote)}</em>
          </div>
        </div>
        ${
          manualOpenUrl || manualPagePdfUrl
            ? `
              <div class="maintenance-execute-manual-resource-actions">
                ${manualOpenUrl ? `<a class="action-btn action-secondary" href="${manualOpenUrl}" target="_blank" rel="noopener noreferrer">Open linked manual</a>` : ""}
                ${manualPagePdfUrl ? `<a class="action-btn action-secondary" href="${manualPagePdfUrl}" target="_blank" rel="noopener noreferrer">Create task PDF${manualPageNumber > 0 ? ` · p.${escapeHtml(String(manualPageNumber))}` : ""}</a>` : ""}
              </div>
            `
            : ""
        }
      </section>
      <section class="maintenance-execute-manual-detail-card is-wide">
        <div class="chart-head">
          <span>Run conditions</span>
          <strong>Safety and stop logic from the builder package</strong>
        </div>
        <div class="maintenance-execute-manual-safety-grid">
          <div class="maintenance-focus-stat tone-warn">
            <span>Fall risk</span>
            <strong>${escapeHtml(wp.safety_fall_risk || "Low")}</strong>
          </div>
          <div class="maintenance-focus-stat tone-info">
            <span>T&amp;M presence</span>
            <strong>${escapeHtml(wp.safety_tnm_presence || "Allowed")}</strong>
          </div>
          <div class="maintenance-focus-stat tone-info">
            <span>Stop time</span>
            <strong>${escapeHtml(String(wp.est_stop_min || task.est_duration_min || "—"))} min</strong>
          </div>
          <div class="maintenance-focus-stat tone-info">
            <span>Due window</span>
            <strong>${escapeHtml(String(dueWindow))}</strong>
          </div>
        </div>
        <div class="maintenance-execute-manual-readstack">
          <div class="maintenance-execute-readblock">
            <span>Safety protocol</span>
            <p>${safetyProtocol}</p>
          </div>
          <div class="maintenance-execute-readblock">
            <span>Draw stop plan</span>
            <p>${drawStopPlan}</p>
          </div>
        </div>
      </section>
      <section class="maintenance-execute-manual-detail-card is-wide">
        <div class="chart-head">
          <span>Procedure pack</span>
          <strong>Prep and operator steps</strong>
        </div>
        ${maintenanceLinkedChecklistMarkup(
          "Preparation checklist",
          wp.preparation_checklist,
          "prep",
          wp.procedure_photos,
          "No preparation checklist is stored yet.",
        )}
        ${maintenanceLinkedChecklistMarkup(
          "Procedure steps",
          wp.procedure_steps || task.procedure_summary,
          "step",
          wp.procedure_photos,
          "No procedure steps are stored yet.",
        )}
      </section>
      <section class="maintenance-execute-manual-detail-card is-wide">
        <div class="chart-head">
          <span>Finish + sanity</span>
          <strong>Closeout checks</strong>
        </div>
        ${maintenanceSanityTemplateSummaryMarkup(wp.sanity_checklist, "No sanity template is stored yet.")}
        <div class="maintenance-execute-readblock">
          <span>Acceptance criteria</span>
          <p>${completionCriteria}</p>
        </div>
      </section>
      ${maintenanceExecuteManualInputFormMarkup(task)}
    </div>
  `;
}

function maintenanceSourceQaMarkup(task) {
  if (!task) {
    return `<div class="chart-empty">Choose a task to see its source and package quality checks.</div>`;
  }
  return `
    <div class="micro-list">
      <div class="micro-row"><span>Source file</span><strong>${task.source_file || "Unknown"}</strong></div>
      <div class="micro-row"><span>Task id</span><strong>${task.task_id || "—"}</strong></div>
      <div class="micro-row"><span>Last done</span><strong>${task.last_done_date || "Not tracked"}</strong></div>
      <div class="micro-row"><span>Package updated</span><strong>${task.work_package?.last_updated || "Never"}</strong></div>
    </div>
    <div class="token-strip">
      ${(task.required_parts || []).length
        ? task.required_parts.map((part) => `<span class="token-chip ${(task.missing_parts || []).includes(part) ? "" : "is-accent"}">${part}</span>`).join("")
        : `<span class="token-chip">No mandatory parts</span>`}
    </div>
  `;
}

function maintenanceBuilderToolsMarkup(task) {
  if (!task) {
    return `<div class="chart-empty">Choose a task to see builder tools.</div>`;
  }
  return `
    ${collapsibleSection("Manual preview", maintenanceManualPreviewMarkup(task), {
      kind: "panel",
      tone: "info",
      meta: task.manual_name || "manual",
      open: true,
    })}
    ${collapsibleSection("Source QA", maintenanceSourceQaMarkup(task), {
      kind: "panel",
      tone: "warn",
      meta: task.source_file || "source",
      open: false,
    })}
  `;
}

function maintenanceSidePanelMarkup(mode, data, task) {
  if (mode === "builder") {
    return `
      <div class="maintenance-side-stack">
        ${maintenanceBuilderToolsMarkup(task)}
      </div>
    `;
  }
  if (mode === "plan") {
    return `
      ${collapsibleSection("Next preparation batch", maintenanceTimelineMarkup(data.prep_events, "No preparation batch scheduled yet."), {
        kind: "panel",
        tone: "good",
        meta: `${(data.prep_events || []).length} events`,
        open: true,
      })}
      ${collapsibleSection("Selected due window", `
        <div class="micro-list">
          ${maintenanceDueRowsMarkup(task)}
        </div>
      `, {
        kind: "panel",
        tone: "info",
        meta: task?.timing_status || "timing",
        open: true,
      })}
      ${collapsibleSection("Smart TODO", `
        <div class="stack-list">
          ${(data.smart_todo || []).length
            ? data.smart_todo.map((item) => `<div class="micro-row"><span>${item.component} — ${item.task}</span><strong>${item.flow_state}</strong></div>`).join("")
            : `<div class="chart-empty">No urgent prep items right now.</div>`}
        </div>
      `, {
        kind: "panel",
        tone: "warn",
        meta: `${(data.smart_todo || []).length} items`,
        open: false,
      })}
    `;
  }
  if (mode === "execute") {
    return `
      ${collapsibleSection("Closeout watch", `
        <div class="micro-list">
          <div class="micro-row"><span>Due / window</span><strong>${task?.next_due_date || task?.next_due_draw || task?.next_due_hours || "—"}</strong></div>
          <div class="micro-row"><span>Linked orders</span><strong>${task?.linked_open_count || 0}</strong></div>
          <div class="micro-row"><span>Received waiting sync</span><strong>${task?.linked_received_waiting_sync || 0}</strong></div>
          <div class="micro-row"><span>Synced ready</span><strong>${task?.linked_ready_count || 0}</strong></div>
        </div>
      `, {
        kind: "panel",
        tone: "info",
        meta: task?.tracking_mode || "task",
        open: true,
      })}
    `;
  }
  if (mode === "blocked") {
    return `
      ${collapsibleSection("Missing parts", `
        <div class="token-strip">
          ${(task?.missing_parts || []).length
            ? task.missing_parts.map((part) => `<span class="token-chip">${part}</span>`).join("")
            : `<span class="token-chip is-accent">No missing parts</span>`}
        </div>
      `, {
        kind: "panel",
        tone: "bad",
        meta: `${(task?.missing_parts || []).length} missing`,
        open: true,
      })}
      ${collapsibleSection("Preparation lane", maintenanceTimelineMarkup(data.prep_events, "No preparation events scheduled."), {
        kind: "panel",
        tone: "warn",
        meta: `${(data.prep_events || []).length} events`,
        open: false,
      })}
    `;
  }
  if (mode === "history") {
    return `
      ${collapsibleSection("Recent maintenance windows", maintenanceTimelineMarkup(data.maintenance_events, "No maintenance windows scheduled right now."), {
        kind: "panel",
        tone: "info",
        meta: `${(data.maintenance_events || []).length} windows`,
        open: true,
      })}
      ${collapsibleSection("Latest actions", `
        <div class="stack-list">
          ${(data.recent_actions || []).length
            ? data.recent_actions.map((item) => `<div class="micro-row"><span>${item.component} — ${item.task}</span><strong>${item.done_date || item.task_id}</strong></div>`).join("")
            : `<div class="chart-empty">No recent actions logged.</div>`}
        </div>
      `, {
        kind: "panel",
        tone: "good",
        meta: `${(data.recent_actions || []).length} actions`,
        open: false,
      })}
    `;
  }
  return "";
}

function maintenanceTaskLooksOverdue(task) {
  const status = String(task?.timing_status || task?.status || "").trim().toLowerCase();
  if (/(overdue|late|past due|due now)/i.test(status)) return true;
  const nextDueDate = String(task?.next_due_date || "").trim();
  if (!nextDueDate) return false;
  const parsed = Date.parse(nextDueDate);
  if (Number.isNaN(parsed)) return false;
  return parsed < Date.now();
}

function maintenanceStageMarkup(mode, data, task) {
  if (mode === "builder") {
    return `
      <div class="maintenance-builder-summary">
        ${maintenanceBuilderFocusMarkup(task)}
      </div>
    `;
  }
  if (mode === "plan") {
    return `
      ${maintenanceDetailMarkup(task)}
      ${maintenancePlanStageMarkup(task)}
    `;
  }
  if (mode === "execute") {
    return `
      <div class="maintenance-detail-head">
        <span>${task?.component || "No component selected"}</span>
        <strong>${task?.task || "No task selected"}</strong>
        <em>${task?.task_id || "—"}</em>
      </div>
      ${maintenanceExecuteStageMarkup(task)}
    `;
  }
  if (mode === "blocked") {
    return `
      ${maintenanceDetailMarkup(task)}
      ${collapsibleSection("Blocker snapshot", `
        <div class="metric-row compact">
          <div class="metric-pill tone-bad"><span>Missing</span><strong>${(task?.missing_parts || []).length}</strong></div>
          <div class="metric-pill tone-warn"><span>Linked open</span><strong>${task?.linked_open_count || 0}</strong></div>
          <div class="metric-pill tone-good"><span>Synced ready</span><strong>${task?.linked_ready_count || 0}</strong></div>
        </div>
      `, {
        kind: "panel",
        tone: "bad",
        meta: task?.flow_state || "blocker",
        open: true,
      })}
    `;
  }
  return `
    ${maintenanceDetailMarkup(task)}
    ${collapsibleSection("Action history", `
      <div class="stack-list">
        ${(data.recent_actions || []).length
          ? data.recent_actions.map((item) => `<div class="micro-row"><span>${item.component} — ${item.task}</span><strong>${item.done_date || item.task_id}</strong></div>`).join("")
          : `<div class="chart-empty">No recent actions logged.</div>`}
      </div>
    `, {
      kind: "panel",
      tone: "good",
      meta: `${(data.recent_actions || []).length} actions`,
      open: false,
    })}
  `;
}

function maintenanceModeContextMarkup(mode, data, selected, prepCutoffProgress = "", prepReadyProgress = "", prepFocusLaneKey = "", prepHorizonProgress = "", prepHorizonFoldOpen = false, prepStageKey = "need-prep", prepActionState = null, prepSelectedTaskIds = []) {
  if (mode === "builder") {
    return ``;
  }
  if (mode === "execute") {
    return ``;
  }
  if (mode === "blocked") {
    return `
      <div class="maintenance-top-grid">
        <section class="chart-card maintenance-top-card">
          <div class="chart-head">
            <span>Blocked tracker</span>
            <strong>Tasks waiting on parts or prep</strong>
          </div>
          <div class="micro-list">
            <div class="micro-row"><span>Blocked tasks</span><strong>${(data.blocked_tracker || []).length}</strong></div>
            <div class="micro-row"><span>With missing parts</span><strong>${(data.blocked_tracker || []).filter((item) => (item.missing_parts || []).length).length}</strong></div>
            <div class="micro-row"><span>With linked orders</span><strong>${(data.blocked_tracker || []).filter((item) => item.linked_open_count).length}</strong></div>
          </div>
        </section>
        <section class="chart-card maintenance-top-card">
          <div class="chart-head">
            <span>Preparation lane</span>
            <strong>Checks before the next stop</strong>
          </div>
          ${maintenanceTimelineMarkup(data.prep_events, "No preparation or parts-check events are scheduled yet.")}
        </section>
        <section class="chart-card maintenance-top-card">
          <div class="chart-head">
            <span>Smart TODO</span>
            <strong>Urgent blockers</strong>
          </div>
          <div class="stack-list">
            ${(data.smart_todo || []).length
              ? data.smart_todo.map((item) => `<div class="micro-row"><span>${item.component} — ${item.task}</span><strong>${item.flow_state}</strong></div>`).join("")
              : `<div class="chart-empty">No urgent maintenance TODO items right now.</div>`}
          </div>
        </section>
      </div>
    `;
  }
  if (mode === "history") {
    return `
      <div class="maintenance-top-grid">
        <section class="chart-card maintenance-top-card">
          <div class="chart-head">
            <span>History lane</span>
            <strong>Recent maintenance actions</strong>
          </div>
          <div class="micro-list">
            <div class="micro-row"><span>Recent actions</span><strong>${(data.recent_actions || []).length}</strong></div>
            <div class="micro-row"><span>Completed ids tracked</span><strong>${(data.completed_ids || []).length}</strong></div>
          </div>
        </section>
        <section class="chart-card maintenance-top-card">
          <div class="chart-head">
            <span>Recent windows</span>
            <strong>Maintenance activity context</strong>
          </div>
          ${maintenanceTimelineMarkup(data.maintenance_events, "No maintenance windows scheduled right now.")}
        </section>
        <section class="chart-card maintenance-top-card">
          <div class="chart-head">
            <span>Selected history</span>
            <strong>${selected?.task || "Pick a recent action"}</strong>
          </div>
          <div class="micro-panel">${selected?.component ? `${selected.component} · ${selected.done_date || "Done"}` : "Choose a recent action to inspect it."}</div>
        </section>
      </div>
    `;
  }
  return `
    <div class="maintenance-top-grid">
      <section class="chart-card maintenance-top-card maintenance-top-card-wide">
        <div class="chart-head">
          <span>Prep horizon</span>
          <strong>Prep timing map</strong>
        </div>
        ${maintenancePrepHorizonMarkup(data.maintenance_events, "No maintenance windows scheduled right now.", data, selected?.task_id || "", prepCutoffProgress, prepReadyProgress, prepFocusLaneKey || (selected ? maintenanceTimelineLaneForTask(selected) : ""), prepHorizonProgress, prepHorizonFoldOpen, prepStageKey, prepActionState, prepSelectedTaskIds)}
      </section>
    </div>
  `;
}

function maintenanceFaultsWorkspaceMarkup(data, editorState = "") {
  const openFaults = data.faults_open || [];
  const closedFaults = data.faults_closed || [];
  const componentOptions = dedupeStrings([
    ...(data.tasks || []).map((item) => item.component),
    ...openFaults.map((item) => item.component),
    ...closedFaults.map((item) => item.component),
  ]).sort((left, right) => left.localeCompare(right));
  const componentOptionsMarkup = componentOptions
    .map((item) => `<option value="${escapeHtml(item)}"></option>`)
    .join("");
  const faultMetaLine = (fault) =>
    [
      String(fault.ts || "").trim(),
      fault.related_draw ? `Draw ${fault.related_draw}` : "",
      fault.source_file ? builderFileLabel(fault.source_file) : "",
    ]
      .filter(Boolean)
      .map((item) => escapeHtml(item))
      .join(" · ");
  const faultLastActionLine = (fault) =>
    [
      fault.last_action_type ? `Last ${fault.last_action_type}` : "",
      fault.last_action_ts || "",
      fault.last_action_actor || "",
    ]
      .filter(Boolean)
      .map((item) => escapeHtml(item))
      .join(" · ");
  const faultEditorMarkup = (fault, editorState) => {
    const faultId = String(fault.fault_id || "").trim();
    if (!faultId) return "";
    const editKey = `edit:${faultId}`;
    const noteKey = `note:${faultId}`;
    const closeKey = `close:${faultId}`;
    const reopenKey = `reopen:${faultId}`;
    if (editorState === editKey) {
      return `
        <form class="maintenance-fault-inline-form" data-maint-fault-form="1">
          <input type="hidden" name="action" value="edit" />
          <input type="hidden" name="faultId" value="${escapeHtml(faultId)}" />
          <div class="field-grid field-grid-2">
            <label class="field-block">
              <span>Component</span>
              <input type="text" name="component" list="maintenance-fault-component-list" value="${escapeHtml(fault.component || "")}" required />
            </label>
            <label class="field-block">
              <span>Severity</span>
              <select name="severity">
                ${["low", "medium", "high", "critical"]
                  .map((item) => `<option value="${item}" ${String(fault.severity || "").toLowerCase() === item ? "selected" : ""}>${item}</option>`)
                  .join("")}
              </select>
            </label>
          </div>
          <div class="field-grid field-grid-2">
            <label class="field-block">
              <span>Fault title</span>
              <input type="text" name="title" value="${escapeHtml(fault.title || "")}" />
            </label>
            <label class="field-block">
              <span>Related draw</span>
              <input type="text" name="relatedDraw" value="${escapeHtml(fault.related_draw || "")}" />
            </label>
          </div>
          <label class="field-block">
            <span>Source file</span>
            <input type="text" name="sourceFile" value="${escapeHtml(fault.source_file || "")}" />
          </label>
          <label class="field-block">
            <span>Description</span>
            <textarea name="description" rows="4">${escapeHtml(fault.description || "")}</textarea>
          </label>
          <div class="maintenance-fault-actions">
            <button class="action-btn action-primary" type="submit">Save fault</button>
            <button class="action-btn action-secondary" type="button" data-maint-fault-toggle="${escapeHtml(editKey)}">Cancel</button>
          </div>
        </form>
      `;
    }
    if (editorState === noteKey) {
      return `
        <form class="maintenance-fault-inline-form" data-maint-fault-form="1">
          <input type="hidden" name="action" value="note" />
          <input type="hidden" name="faultId" value="${escapeHtml(faultId)}" />
          <label class="field-block">
            <span>Action note</span>
            <textarea name="note" rows="4" placeholder="What was checked, what was found, what is next?"></textarea>
          </label>
          <div class="maintenance-fault-actions">
            <button class="action-btn action-primary" type="submit">Save note</button>
            <button class="action-btn action-secondary" type="button" data-maint-fault-toggle="${escapeHtml(noteKey)}">Cancel</button>
          </div>
        </form>
      `;
    }
    if (editorState === closeKey) {
      return `
        <form class="maintenance-fault-inline-form" data-maint-fault-form="1">
          <input type="hidden" name="action" value="close" />
          <input type="hidden" name="faultId" value="${escapeHtml(faultId)}" />
          <div class="field-grid field-grid-2">
            <label class="field-block">
              <span>Fix summary</span>
              <input type="text" name="fixSummary" placeholder="Short closure summary" />
            </label>
            <label class="field-block">
              <span>Close note</span>
              <input type="text" name="note" placeholder="Why is this safe to close?" />
            </label>
          </div>
          <div class="maintenance-fault-actions">
            <button class="action-btn action-primary" type="submit">Close fault</button>
            <button class="action-btn action-secondary" type="button" data-maint-fault-toggle="${escapeHtml(closeKey)}">Cancel</button>
          </div>
        </form>
      `;
    }
    if (editorState === reopenKey) {
      return `
        <form class="maintenance-fault-inline-form" data-maint-fault-form="1">
          <input type="hidden" name="action" value="reopen" />
          <input type="hidden" name="faultId" value="${escapeHtml(faultId)}" />
          <label class="field-block">
            <span>Reopen note</span>
            <textarea name="note" rows="3" placeholder="Why is the fault being reopened?"></textarea>
          </label>
          <div class="maintenance-fault-actions">
            <button class="action-btn action-primary" type="submit">Reopen fault</button>
            <button class="action-btn action-secondary" type="button" data-maint-fault-toggle="${escapeHtml(reopenKey)}">Cancel</button>
          </div>
        </form>
      `;
    }
    return "";
  };
  const faultRowMarkup = (fault, editorState, { closed = false } = {}) => {
    const faultId = String(fault.fault_id || "").trim();
    const tone = toneForLabel(fault.severity || "medium");
    return `
      <article class="maintenance-task-row maintenance-fault-card tone-${tone}">
        <div class="maintenance-task-main">
          <div class="maintenance-task-head">
            <strong>${escapeHtml(fault.component || "Unknown component")}</strong>
            <span class="status-badge tone-${tone}">${escapeHtml(fault.severity || "medium")}</span>
          </div>
          <h3>${escapeHtml(fault.title || "Fault")}</h3>
          ${fault.description ? `<p class="maintenance-fault-description">${escapeHtml(fault.description)}</p>` : ""}
          ${faultMetaLine(fault) ? `<p class="maintenance-fault-meta">${faultMetaLine(fault)}</p>` : ""}
          ${faultLastActionLine(fault) ? `<div class="maintenance-fault-lastaction">${faultLastActionLine(fault)}</div>` : ""}
          ${(fault.last_fix || fault.last_note)
            ? `
              <div class="maintenance-fault-note">
                ${fault.last_fix ? `<strong>${escapeHtml(fault.last_fix)}</strong>` : ""}
                ${fault.last_note ? `<span>${escapeHtml(fault.last_note)}</span>` : ""}
              </div>
            `
            : ""}
        </div>
        <div class="maintenance-fault-actions">
          <button class="action-btn action-secondary" type="button" data-maint-fault-toggle="edit:${escapeHtml(faultId)}">Edit</button>
          ${
            closed
              ? `<button class="action-btn action-secondary" type="button" data-maint-fault-toggle="reopen:${escapeHtml(faultId)}">Reopen</button>`
              : `
                <button class="action-btn action-secondary" type="button" data-maint-fault-toggle="note:${escapeHtml(faultId)}">Add note</button>
                <button class="action-btn action-primary" type="button" data-maint-fault-toggle="close:${escapeHtml(faultId)}">Close</button>
              `
          }
        </div>
        ${faultEditorMarkup(fault, editorState)}
      </article>
    `;
  };
  return `
    <datalist id="maintenance-fault-component-list">
      ${componentOptionsMarkup}
    </datalist>
    <div class="maintenance-top-grid maintenance-faults-top-grid">
      <section class="chart-card maintenance-top-card">
        <div class="chart-head">
          <span>Fault monitor</span>
          <strong>Open faults</strong>
        </div>
        <div class="metric-row compact">
          <div class="metric-pill tone-bad"><span>Open faults</span><strong>${data.fault_open_total || 0}</strong></div>
          <div class="metric-pill tone-bad"><span>Critical open</span><strong>${data.fault_open_critical_total || 0}</strong></div>
          <div class="metric-pill tone-info"><span>Actions logged</span><strong>${data.fault_actions_total || 0}</strong></div>
        </div>
        <div class="stack-list">
          ${openFaults.length
            ? openFaults.slice(0, 8).map((item) => `<div class="micro-row"><span>${escapeHtml(item.component)} — ${escapeHtml(item.title)}</span><strong>${escapeHtml(item.severity)}</strong></div>`).join("")
            : `<div class="chart-empty">No open faults right now.</div>`}
        </div>
      </section>
      <section class="chart-card maintenance-top-card">
        <div class="chart-head">
          <span>Fault intake</span>
          <strong>Log and update incidents directly here</strong>
        </div>
        <form id="maintenance-fault-create-form" class="maintenance-fault-inline-form maintenance-fault-create-form">
          <div class="field-grid field-grid-2">
            <label class="field-block">
              <span>Component</span>
              <input type="text" name="component" list="maintenance-fault-component-list" placeholder="Furnace / guide pulley / UV..." required />
            </label>
            <label class="field-block">
              <span>Severity</span>
              <select name="severity">
                <option value="low">low</option>
                <option value="medium" selected>medium</option>
                <option value="high">high</option>
                <option value="critical">critical</option>
              </select>
            </label>
          </div>
          <div class="field-grid field-grid-2">
            <label class="field-block">
              <span>Fault title</span>
              <input type="text" name="title" placeholder="Short fault title" />
            </label>
            <label class="field-block">
              <span>Related draw</span>
              <input type="text" name="relatedDraw" placeholder="Optional draw ref" />
            </label>
          </div>
          <label class="field-block">
            <span>Source file</span>
            <input type="text" name="sourceFile" placeholder="Optional source file / note origin" />
          </label>
          <label class="field-block">
            <span>Description</span>
            <textarea name="description" rows="4" placeholder="What happened, what was observed, and what should be checked next?"></textarea>
          </label>
          <div class="maintenance-fault-actions">
            <button class="action-btn action-primary" type="submit">Log open fault</button>
          </div>
        </form>
      </section>
    </div>
    <section class="maintenance-workspace maintenance-faults-workspace">
      <div class="maintenance-list-shell">
        <div class="chart-head">
          <span>Open fault list</span>
          <strong>Incidents waiting for action</strong>
        </div>
        <div class="stack-list">
          ${openFaults.length
            ? openFaults.map((item) => faultRowMarkup(item, editorState)).join("")
            : `<div class="chart-empty">No open faults right now.</div>`}
        </div>
        ${closedFaults.length
          ? collapsibleSection(
              "Closed faults",
              `
                <div class="stack-list">
                  ${closedFaults.map((item) => faultRowMarkup(item, editorState, { closed: true })).join("")}
                </div>
              `,
              {
                kind: "list",
                tone: "neutral",
                open: false,
                meta: `${closedFaults.length} closed`,
                className: "maintenance-fault-closed-fold",
              },
            )
          : ""}
      </div>
    </section>
  `;
}

function orderQueueMarkup(items, options = {}) {
  const { empty = "No orders in this group.", selectable = false } = options;
  if (!items || !items.length) {
    return `<div class="chart-empty">${empty}</div>`;
  }
  return items
    .map(
      (item) => `
        <article class="order-queue-row tone-${toneForLabel(item.status)}">
          <div class="order-queue-copy">
            <div class="order-queue-head">
              <strong>${item.preform || "No preform yet"}</strong>
              <span class="status-badge tone-${toneForLabel(item.status)}">${item.status}</span>
            </div>
            <p>${item.project || "No project"} · ${item.geometry || "No geometry"} · ${item.priority || "Normal"}</p>
            <div class="order-queue-meta">
              <span>Length ${item.length || "0"} m</span>
              <span>Zones ${item.good_zones || "0"}</span>
              ${item.next_draw ? `<span>Target ${item.next_draw}</span>` : ""}
            </div>
          </div>
          <div class="order-queue-side">
            <span>${item.timestamp || item.desired_date || "Unplanned"}</span>
            ${selectable ? `<button class="mini-action" type="button" data-order-select="${item.index}">Schedule</button>` : ""}
          </div>
        </article>
      `,
    )
    .join("");
}

function orderDrawProjectChips(projects, templateProjects) {
  return projects
    .map((project) => {
      const hasTemplate = templateProjects.includes(project);
      return `<span class="token-chip ${hasTemplate ? "is-accent" : ""}">${project}${hasTemplate ? " · tpl" : ""}</span>`;
    })
    .join("");
}

function orderDrawNoticeMarkup() {
  if (!orderDrawFlash) return "";
  return `
    <div class="order-draw-notice tone-${orderDrawFlash.kind || "info"}">
      <strong>${orderDrawFlash.title || "Order Draw"}</strong>
      <span>${orderDrawFlash.message}</span>
    </div>
  `;
}

function drawFinalizeNoticeMarkup() {
  if (!drawFinalizeFlash) return "";
  return `
    <div class="order-draw-notice tone-${drawFinalizeFlash.kind || "info"}">
      <strong>${drawFinalizeFlash.title || "Draw Finalize"}</strong>
      <span>${drawFinalizeFlash.message}</span>
    </div>
  `;
}

function getHomeMaintenanceSnapshot(data) {
  const maintenance = data.maintenance || {};
  const tasks = maintenance.tasks || [];
  const executeQueue = maintenance.execute_queue || [];
  const faults = maintenance.faults_recent || [];
  const overdueTasks = tasks.filter((item) => /overdue/i.test(String(item.timing_status || "")));
  const inProgressTasks = executeQueue.filter((item) => String(item?.status || "").trim().toUpperCase() === "IN_PROGRESS");
  const criticalFaults = faults.filter((item) => {
    const severity = String(item.severity || "").toLowerCase();
    return severity.includes("critical") || severity.includes("high");
  });
  return {
    overdueTasks,
    inProgressTasks,
    activeTask: inProgressTasks[0] || null,
    criticalFaults,
    activeCount: inProgressTasks.length,
    overdueCount: overdueTasks.length,
    criticalCount: criticalFaults.length,
  };
}

function getHomePanelMeta(panelKey, data) {
  const maintenanceEvents = Number(data.schedule.type_counts.Maintenance ?? 0);
  const lowStockCount = data.inventory.low_stock.length;
  const openMaintenanceOrders = data.parts.maintenance_open;
  const maintenanceSnapshot = getHomeMaintenanceSnapshot(data);
  const waitForApproval = statusCount(data.parts.status_counts, "Wait for Approval");
  const readyToOrder = Number(data.parts.queue_counts?.approved || 0);
  const ordered = Number(data.parts.queue_counts?.ordered || 0);
  const receivedPending = Number(data.parts.queue_counts?.received_pending || 0);

  const lookup = {
    draws: {
      title: "Draws Monitor",
      eyebrow: "Live draw orders",
      value: `${data.draws.in_progress || 0} drawing now`,
      detail: `${data.draws.scheduled || 0} scheduled · ${data.draws.pending || 0} pending · ${data.draws.total} tracked`,
      lines: [
        `${data.draws.in_progress || 0} currently in progress`,
        `${data.draws.scheduled || 0} scheduled next`,
        `${data.draws.pending || 0} still pending`,
        `${data.draws.done} completed`,
        data.draws.recent[0] ? `Latest: ${data.draws.recent[0].preform || "Unknown"}` : "No recent draw",
      ],
    },
    doneFailed: {
      title: "Done + Failed",
      eyebrow: "Completion state",
      value: `${data.draws.done} done`,
      detail: `${data.draws.failed} failed`,
      lines: [
        `${data.draws.done} cleared clean`,
        `${data.draws.failed} need review`,
        "Keep only the clean closeout signal here.",
      ],
    },
    schedule: {
      title: "Schedule",
      eyebrow: "Tower timeline",
      value: `${data.schedule.total} events`,
      detail: data.schedule.upcoming[0] ? `Next: ${data.schedule.upcoming[0].event_type}` : "No upcoming events",
      lines: [
        data.schedule.upcoming[0] ? data.schedule.upcoming[0].start : "No immediate event",
        `${maintenanceEvents} maintenance windows`,
        `${Object.keys(data.schedule.type_counts).length} event types tracked`,
      ],
    },
    maintenance: {
      title: "Maintenance + Faults",
      eyebrow: "Service readiness",
      value: maintenanceSnapshot.activeCount ? `${maintenanceSnapshot.activeCount} active now` : `${maintenanceSnapshot.overdueCount} overdue`,
      detail: `${maintenanceSnapshot.overdueCount} overdue · ${maintenanceSnapshot.criticalCount} critical faults`,
      lines: [
        maintenanceSnapshot.activeTask
          ? `Now: ${maintenanceSnapshot.activeTask.component || "Task"} · ${maintenanceSnapshot.activeTask.task || "Maintenance in progress"}`
          : "Now: no maintenance task is actively running",
        `${maintenanceSnapshot.overdueCount} overdue maintenance tasks`,
        `${maintenanceSnapshot.criticalCount} open critical or high faults`,
        "Home shows the live tower maintenance state here.",
      ],
    },
    parts: {
      title: "Parts Orders",
      eyebrow: "Supply pressure",
      value: `${data.parts.total} orders`,
      detail: `${statusCount(data.parts.status_counts, "Opened")} opened · ${receivedPending} received pending`,
      lines: [
        `${statusCount(data.parts.status_counts, "Opened")} opened`,
        `${waitForApproval} wait approval · ${readyToOrder} ready`,
        `${ordered} ordered · ${receivedPending} received pending`,
      ],
    },
  };

  return lookup[panelKey] ?? lookup.draws;
}

function addDaysToIsoDate(isoDate, days) {
  const date = new Date(`${isoDate}T00:00:00`);
  date.setDate(date.getDate() + days);
  return formatLocalIsoDate(date);
}

function addMonthsToIsoDate(isoDate, months) {
  const date = new Date(`${isoDate}T00:00:00`);
  date.setMonth(date.getMonth() + months);
  return formatLocalIsoDate(date);
}

function formatLocalIsoDate(date) {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function formatIsoDate(isoDate, options = { month: "short", day: "numeric" }) {
  return new Intl.DateTimeFormat("en-US", options).format(new Date(`${isoDate}T00:00:00`));
}

function getScheduleViewModel(data, view = "week", anchor = data.timeline_anchor, weekStartsOn = "monday") {
  const events = (data.expanded_events || []).map((item) => ({
    ...item,
    startDate: new Date(item.start),
    endDate: new Date(item.end),
  }));
  const anchorDate = new Date(`${anchor}T00:00:00`);

  if (view === "month") {
    const days = [];
    for (let day = 0; day < 35; day += 1) {
      const dt = new Date(anchorDate);
      dt.setDate(anchorDate.getDate() + day);
      const key = formatLocalIsoDate(dt);
      const dayEvents = events.filter((event) => event.day_key === key);
      days.push({
        key,
        label: dt.toLocaleDateString("en-US", { weekday: "short" }),
        dateLabel: dt.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
        events: dayEvents,
      });
    }
    const title = `${formatIsoDate(days[0].key)} - ${formatIsoDate(days[days.length - 1].key)}`;
    return { view, title, columns: days };
  }

  const weekStart = new Date(anchorDate);
  const columns = [];
  for (let index = 0; index < 7; index += 1) {
    const dt = new Date(weekStart);
    dt.setDate(weekStart.getDate() + index);
    const key = formatLocalIsoDate(dt);
    const dayEvents = events.filter((event) => event.day_key === key);
    columns.push({
      key,
      label: dt.toLocaleDateString("en-US", { weekday: "short" }),
      dateLabel: dt.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      events: dayEvents,
    });
  }
  const title = `${formatIsoDate(columns[0].key)} - ${formatIsoDate(columns[6].key)}`;
  return { view, title, columns };
}

function renderScheduleCanvas(data, view = "week", anchor = data.timeline_anchor, extraClass = "", weekStartsOn = "monday") {
  const model = getScheduleViewModel(data, view, anchor, weekStartsOn);
  const visibleStartKey = model.columns[0]?.key;
  const visibleEndKey = model.columns[model.columns.length - 1]?.key;
  const typeOrder = ["Maintenance", "Drawing", "Management Event", "Stop"];
  const typeRank = (label) => {
    const index = typeOrder.indexOf(label || "");
    return index === -1 ? typeOrder.length : index;
  };
  const expandedEvents = (data.expanded_events || [])
    .map((item) => ({
      ...item,
      startKey: formatLocalIsoDate(new Date(item.start)),
      endKey: formatLocalIsoDate(new Date(item.end)),
    }))
    .filter((item) => item.endKey >= visibleStartKey && item.startKey <= visibleEndKey);
  const activeEventsByDay = new Map();
  expandedEvents.forEach((item) => {
    let dayKey = item.startKey < visibleStartKey ? visibleStartKey : item.startKey;
    const lastDayKey = item.endKey > visibleEndKey ? visibleEndKey : item.endKey;
    while (dayKey <= lastDayKey) {
      const current = activeEventsByDay.get(dayKey) || [];
      current.push({
        ...item,
        continuesPrev: dayKey > item.startKey,
        continuesNext: dayKey < item.endKey,
      });
      activeEventsByDay.set(dayKey, current);
      dayKey = addDaysToIsoDate(dayKey, 1);
    }
  });
  const rowCount = Math.ceil(model.columns.length / 7);
  const indexByKey = Object.fromEntries(model.columns.map((column, index) => [column.key, index]));
  const spanRows = Array.from({ length: rowCount }, () => []);
  expandedEvents
    .filter((item) => item.startKey !== item.endKey)
    .forEach((item) => {
      const startIndex = item.startKey < visibleStartKey ? 0 : (indexByKey[item.startKey] ?? 0);
      const endIndex = item.endKey > visibleEndKey ? model.columns.length - 1 : (indexByKey[item.endKey] ?? model.columns.length - 1);
      let cursor = startIndex;
      while (cursor <= endIndex) {
        const row = Math.floor(cursor / 7);
        const rowStart = row * 7;
        const rowEnd = rowStart + 6;
        const segmentEnd = Math.min(endIndex, rowEnd);
        spanRows[row].push({
          lane: typeRank(item.event_type) + 1,
          startCol: cursor - rowStart + 1,
          span: segmentEnd - cursor + 1,
          tone: toneForLabel(item.event_type),
          startsHere: cursor === startIndex && item.startKey >= visibleStartKey,
          endsHere: segmentEnd === endIndex && item.endKey <= visibleEndKey,
        });
        cursor = segmentEnd + 1;
      }
    });
  const detailTip = (column) => {
    const activeEvents = activeEventsByDay.get(column.key) || [];
    if (!activeEvents.length) return `${column.dateLabel}\nNo events`;
    return `${column.dateLabel}\n${activeEvents.map((item) => `${item.event_type || "Event"} · ${item.description || "Scheduled event"}`).join("\n")}`;
  };
  const detailTitle = (column) => column.label;
  const detailBodyHtml = (column) => {
    const activeEvents = activeEventsByDay.get(column.key) || [];
    if (!activeEvents.length) {
      return `<div class="schedule-micro-detail-empty">No scheduled events in this window.</div>`;
    }
    return activeEvents
      .map((item) => {
        const startTime = item.start_label || item.start || "";
        const endTime = item.end_label || item.end || "";
        return `
          <div class="schedule-micro-detail-item tone-${toneForLabel(item.event_type)}">
            <strong>${escapeHtml(item.event_type || "Event")}</strong>
            <span>${escapeHtml(item.description || "Scheduled event")}</span>
            ${startTime || endTime ? `
              <em class="schedule-micro-detail-time">
                ${startTime ? `<i class="time-start"><b>Start</b><span>${escapeHtml(startTime)}</span></i>` : ""}
                ${endTime ? `<i class="time-end"><b>End</b><span>${escapeHtml(endTime)}</span></i>` : ""}
              </em>
            ` : ""}
          </div>
        `;
      })
      .join("");
  };
  const columnsMarkup = model.columns
    .map((column) => {
      const activeEvents = activeEventsByDay.get(column.key) || [];
      const groupedEvents = Object.entries(
        activeEvents.reduce((acc, event) => {
          const key = event.event_type || "Event";
          if (!acc[key]) {
            acc[key] = {
              items: [],
              continuesPrev: false,
              continuesNext: false,
            };
          }
          acc[key].items.push(event);
          acc[key].continuesPrev = acc[key].continuesPrev || Boolean(event.continuesPrev);
          acc[key].continuesNext = acc[key].continuesNext || Boolean(event.continuesNext);
          return acc;
        }, {}),
      ).sort(([labelA], [labelB]) => typeRank(labelA) - typeRank(labelB) || String(labelA).localeCompare(String(labelB)));
      const dotLayoutClass = groupedEvents.length ? "is-vertical" : "";
      return `
        <button
          class="schedule-micro-stop ${activeEvents.length ? "has-events" : "is-empty"} ${dotLayoutClass}"
          type="button"
          data-tip="${escapeHtml(detailTip(column))}"
          data-detail-title="${escapeHtml(detailTitle(column))}"
          data-detail-body-html="${escapeHtml(detailBodyHtml(column))}"
        >
          <span class="schedule-micro-stop-day">${column.label}</span>
          <strong class="schedule-micro-stop-date">${column.dateLabel}</strong>
          <span class="schedule-micro-stop-dots">
            ${
              groupedEvents.length
                ? groupedEvents
                    .map(([label, meta]) => `
                      <span
                        class="schedule-micro-eventdot tone-${toneForLabel(label)} lane-${Math.min(typeRank(label) + 1, 5)}"
                        aria-label="${escapeHtml(`${column.dateLabel} · ${label}`)}"
                      >
                        <i></i>
                        ${meta.items.length > 1 ? `<strong>${meta.items.length}</strong>` : ""}
                      </span>
                    `)
                    .join("")
                : `<span class="schedule-micro-stop-empty"></span>`
            }
          </span>
        </button>
      `;
    })
    .join("");
  const spanRowsMarkup = spanRows
    .map((segments) => `
      <div class="schedule-span-overlay-row ${model.view === "month" ? "is-month" : "is-week"}">
        ${
          segments
            .map((segment) => `
              <span
                class="schedule-span-overlay-segment tone-${segment.tone} lane-${Math.min(segment.lane, 5)}"
                style="grid-column:${segment.startCol} / span ${segment.span}; --segment-start-inset:${segment.startsHere ? "calc(50% - 4px)" : "0px"}; --segment-end-inset:${segment.endsHere ? "calc(50% - 4px)" : "0px"};"
              ></span>
            `)
            .join("")
        }
      </div>
    `)
    .join("");

  return `
    <div class="schedule-canvas schedule-canvas-minimal ${extraClass}" id="schedule-canvas">
      <div class="schedule-canvas-head">
        <div>
          <span>Timeline</span>
          <strong>${model.title}</strong>
        </div>
        <div class="schedule-canvas-note">${model.view === "week" ? "Week view" : "Month view"}</div>
      </div>
      <div class="schedule-micro-shell">
        <div class="schedule-span-overlay ${model.view === "month" ? "is-month" : "is-week"}">
          ${spanRowsMarkup}
        </div>
        <div class="schedule-micro-track ${model.view === "month" ? "is-month" : "is-week"}">
          <i class="schedule-micro-track-line"></i>
          ${columnsMarkup}
        </div>
      </div>
      <div class="schedule-micro-detail" id="schedule-micro-detail" aria-live="polite">
        <div class="schedule-micro-detail-head">
          <span>Hover detail</span>
          <strong>Move over a day</strong>
        </div>
        <div class="schedule-micro-detail-body">Event details will appear here.</div>
      </div>
      <div class="schedule-line-legend schedule-line-legend-minimal">
        ${Object.entries(data.type_counts || {})
          .map(([label, value]) => `
            <span class="schedule-line-legend-chip tone-${toneForLabel(label)}">
              <i></i>
              ${escapeHtml(label)}
              <strong>${value}</strong>
            </span>
          `)
          .join("")}
      </div>
    </div>
  `;
}

function homeScheduleDotRailMarkup(data, view = "week") {
  const now = new Date();
  const todayIso = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const events = (data.schedule?.expanded_events || []).map((item) => ({
    ...item,
    day_key: String(item.day_key || ""),
  }));
  const dayCount = view === "month" ? 35 : 7;
  const columns = Array.from({ length: dayCount }, (_, index) => {
    const key = addDaysToIsoDate(todayIso, index);
    const dt = new Date(`${key}T00:00:00`);
    return {
      key,
      label: dt.toLocaleDateString("en-US", { weekday: "short" }),
      dateLabel: dt.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      events: events.filter((event) => event.day_key === key),
    };
  });
  const rows = view === "month"
    ? Array.from({ length: 5 }, (_, rowIndex) => columns.slice(rowIndex * 7, rowIndex * 7 + 7))
    : [columns];

  const eventTitleForDay = (column) => {
    if (!column.events.length) return `${column.dateLabel} · no events`;
    return `${column.dateLabel} · ${column.events.map((event) => event.event_type || "Event").join(" / ")}`;
  };
  const renderDay = (column) => `
    <div class="home-schedule-dotrail-day ${column.events.length ? "has-events" : "is-empty"}" title="${escapeHtml(eventTitleForDay(column))}">
      <span>${column.label.slice(0, 3)}</span>
      <em>${escapeHtml(column.dateLabel)}</em>
      <div class="home-schedule-dotrail-track">
        <div class="home-schedule-dotrail-dots">
          ${
            column.events.length
              ? Object.entries(
                  column.events.reduce((acc, event) => {
                    const key = event.event_type || "Event";
                    if (!acc[key]) acc[key] = [];
                    acc[key].push(event);
                    return acc;
                  }, {}),
                )
                  .map(
                    ([label, items]) => `
                      <i
                        class="home-schedule-dotrail-dot tone-${toneForLabel(label)}"
                        tabindex="0"
                        role="img"
                        aria-label="${escapeHtml(`${column.dateLabel} · ${label}`)}"
                        data-tip="${escapeHtml(`${column.dateLabel} · ${label} · ${items.map((item) => item.description || item.event_type || "Scheduled event").join(" / ")}`)}"
                      ></i>
                    `,
                  )
                  .join("")
              : `<i class="home-schedule-dotrail-empty"></i>`
          }
        </div>
      </div>
      <strong>${column.events.length}</strong>
    </div>
  `;
  return `
    <div class="home-schedule-dotrail-wrap ${view === "month" ? "is-month" : "is-week"}">
      ${rows.map((row) => `<div class="home-schedule-dotrail">${row.map((column) => renderDay(column)).join("")}</div>`).join("")}
    </div>
  `;
}

function homeCompletionSummaryMarkup(data) {
  const recentDone = (data.draws.recent || []).filter((item) => String(item.status || "").toLowerCase() === "done").slice(0, 3);
  const recentFailed = (data.draws.recent || []).filter((item) => String(item.status || "").toLowerCase() === "failed").slice(0, 2);
  const doneTotal = Number(data.draws.done || 0);
  const failedTotal = Number(data.draws.failed || 0);

  const renderDoneRow = (item) => {
    const title = item.preform || item.project || "Run";
    const projectContext = [item.project, item.geometry].filter(Boolean).join(" · ") || "No project context";
    const zones = Number(item.good_zones || 0);
    const endDescription = String(item.done_description || item.description || item.notes || item.geometry || "No end description").trim();
    return `
      <div class="home-completion-entry tone-good">
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(projectContext)}</span>
        <span>${zones} zones · ${escapeHtml(endDescription)}</span>
      </div>
    `;
  };

  const renderFailedRow = (item) => {
    const title = item.preform || item.project || "Run";
    const failDescription = String(item.failed_description || item.description || item.notes || item.geometry || "Needs review").trim();
    return `
      <div class="home-completion-entry tone-bad">
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(failDescription)}</span>
      </div>
    `;
  };

  const doneRows = recentDone.length
    ? recentDone.map((item) => renderDoneRow(item)).join("")
    : `<div class="home-completion-entry tone-info"><strong>No recent clean closeouts</strong><span>Waiting for the next completed draw.</span></div>`;

  const failedRows = recentFailed.length
    ? recentFailed.map((item) => renderFailedRow(item)).join("")
    : `<div class="home-completion-entry tone-good"><strong>No failed closeouts</strong><span>No open failures in this recent window.</span></div>`;

  return `
    <div class="home-completion-strip">
      <div class="home-completion-summary">
        <div class="home-completion-stat tone-good">
          <span class="home-completion-stat-label">Done</span>
          <strong>${doneTotal}</strong>
          <small>Clean closeouts</small>
        </div>
        <div class="home-completion-stat tone-bad">
          <span class="home-completion-stat-label">Failed</span>
          <strong>${failedTotal}</strong>
          <small>Need review</small>
        </div>
      </div>
      <div class="home-completion-detail">
        <div class="home-completion-summaryline tone-info">
          <span>Done recently</span>
          <div class="home-completion-list">${doneRows}</div>
        </div>
        <div class="home-completion-summaryline tone-bad">
          <span>Failed / review queue</span>
          <div class="home-completion-list">${failedRows}</div>
        </div>
      </div>
    </div>
  `;
}

function homeMaintenanceFocusMarkup(data) {
  const snapshot = getHomeMaintenanceSnapshot(data);
  const active = snapshot.inProgressTasks.slice(0, 3);
  const overdue = snapshot.overdueTasks.slice(0, 3);
  const critical = snapshot.criticalFaults.slice(0, 3);
  const upcomingMaintenance = (data.schedule?.upcoming || [])
    .filter((item) => String(item.event_type || "").toLowerCase().includes("maintenance"))
    .slice(0, 4);
  return `
    <div class="home-maintenance-focus-stack">
      <div class="home-focus-signal-grid">
        <section class="home-focus-signal tone-warn">
          <span>Overdue maintenance</span>
          <strong>${snapshot.overdueCount}</strong>
          <div class="home-focus-signal-list">
            ${overdue.length
              ? overdue.map((item) => `<em>${escapeHtml(item.component || "Task")} · ${escapeHtml(item.task || "Maintenance task")}</em>`).join("")
              : `<em>No overdue maintenance in view.</em>`}
          </div>
        </section>
        <section class="home-focus-signal tone-bad">
          <span>Critical faults</span>
          <strong>${snapshot.criticalCount}</strong>
          <div class="home-focus-signal-list">
            ${critical.length
              ? critical.map((item) => `<em>${escapeHtml(item.component || "Fault")} · ${escapeHtml(item.title || "Critical fault")}</em>`).join("")
              : `<em>No critical faults open right now.</em>`}
          </div>
        </section>
      </div>
      <section class="home-maintenance-upcoming">
        <div class="home-maintenance-upcoming-head">
          <span>Next maintenance</span>
          <strong>${upcomingMaintenance.length ? `${upcomingMaintenance.length} planned` : "No planned events"}</strong>
        </div>
        <div class="home-maintenance-upcoming-list">
          ${upcomingMaintenance.length
            ? upcomingMaintenance.map((event) => `
                <div class="home-maintenance-upcoming-item">
                  <span>${escapeHtml(event.date_label || event.day_key || "Planned")}</span>
                  <strong>${escapeHtml(event.description || event.event_type || "Maintenance event")}</strong>
                </div>
              `).join("")
            : `<div class="home-maintenance-upcoming-item is-empty"><strong>No upcoming maintenance in the visible schedule window.</strong></div>`}
        </div>
      </section>
    </div>
  `;
}

function homePartsStageLineMarkup(data) {
  const normalizeParts = (items) => (items || [])
    .map((item) => String(item.part_name || item.part || item.component || "").trim())
    .filter(Boolean);
  const openOrders = data.parts?.open_orders || [];
  const allOrders = data.parts?.all_orders || openOrders;
  const queues = data.parts?.queues || {};
  const openedParts = normalizeParts(allOrders.filter((item) => String(item.status || "").trim() === "Opened"));
  const waitParts = normalizeParts(queues.approval || allOrders.filter((item) => String(item.status || "").trim() === "Wait for Approval"));
  const readyParts = normalizeParts(queues.approved || allOrders.filter((item) => String(item.status || "").trim() === "Approved"));
  const orderedParts = normalizeParts(queues.ordered || allOrders.filter((item) => String(item.status || "").trim() === "Ordered"));
  const recvParts = normalizeParts(queues.received_pending || allOrders.filter((item) => String(item.status || "").trim() === "Received"));
  const tooltipText = (names) => {
    if (!names.length) return "No parts in this stage";
    const preview = names.slice(0, 7);
    const rest = names.length - preview.length;
    return `${preview.join("\n")}${rest > 0 ? `\n+${rest} more` : ""}`;
  };
  const stages = [
    { key: "opened", label: "Opened", value: statusCount(data.parts.status_counts, "Opened"), tone: "info", parts: openedParts },
    { key: "wait", label: "Wait", value: statusCount(data.parts.status_counts, "Wait for Approval"), tone: "bad", parts: waitParts },
    { key: "ready", label: "Ready", value: Number(data.parts.queue_counts?.approved || 0), tone: "warn", parts: readyParts },
    { key: "ordered", label: "Ordered", value: Number(data.parts.queue_counts?.ordered || 0), tone: "accent", parts: orderedParts },
    { key: "recv", label: "Recv.", value: Number(data.parts.queue_counts?.received_pending || 0), tone: "good", parts: recvParts },
  ];
  const detailMarkup = (stage) => {
    const preview = stage.parts.slice(0, 7);
    const rest = stage.parts.length - preview.length;
    return `
      <div class="home-mini-stage-inline stage-${stage.key} tone-${stage.tone}" aria-hidden="true">
        <div class="home-mini-stage-inline-head">
          <span>${stage.label}</span>
          <strong>${stage.value} items</strong>
        </div>
        <div class="home-mini-stage-inline-list">
          ${
            preview.length
              ? `${preview.map((name) => `<em>${escapeHtml(name)}</em>`).join("")}${rest > 0 ? `<span>+${rest} more</span>` : ""}`
              : `<span>No parts in this stage</span>`
          }
        </div>
      </div>
    `;
  };
  return `
    <div class="home-mini-stage-line">
      <i class="home-mini-stage-line-track"></i>
      ${stages
        .map(
          (stage) => `
            <div
              class="home-mini-stage stage-${stage.key} tone-${stage.tone} ${stage.value > 0 && (stage.label === "Opened" || stage.label === "Recv.") ? "is-alert" : ""}"
              tabindex="0"
              role="img"
              aria-label="${escapeHtml(`${stage.label} parts`)}"
            >
              <i
                class="home-mini-stage-dot"
                aria-hidden="true"
              ></i>
              <span>${stage.label}</span>
              <strong>${stage.value}</strong>
            </div>
          `,
        )
        .join("")}
      <div class="home-mini-stage-inline home-mini-stage-inline-empty" aria-hidden="true"></div>
      ${stages.map((stage) => detailMarkup(stage)).join("")}
    </div>
  `;
}

function homeDetailDockMarkup(panelKey, data, scheduleView = "week") {
  const meta = getHomePanelMeta(panelKey, data);

  if (panelKey === "schedule") {
    const legendTypes = Object.keys(data.schedule?.type_counts || {}).filter((label) => Number(data.schedule.type_counts[label]) > 0);
    const legendOrder = ["Maintenance", "Drawing", "Management Event", "Stop"];
    const sortedLegend = [
      ...legendOrder.filter((label) => legendTypes.includes(label)),
      ...legendTypes.filter((label) => !legendOrder.includes(label)),
    ].slice(0, 4);
    return `
      <div class="home-detail-head home-detail-head-quiet">
        <span>${meta.eyebrow}</span>
        <strong>Planned next</strong>
      </div>
      <div class="home-schedule-dock-controls">
        <div class="home-schedule-dock-toggle" role="tablist" aria-label="Home schedule view">
          <button class="home-schedule-dock-toggle-btn ${scheduleView === "week" ? "is-active" : ""}" type="button" data-home-schedule-view="week">Week</button>
          <button class="home-schedule-dock-toggle-btn ${scheduleView === "month" ? "is-active" : ""}" type="button" data-home-schedule-view="month">Month</button>
        </div>
        <div class="home-schedule-dock-legend" aria-label="Event type color legend">
          ${sortedLegend
            .map((label) => `
              <span class="home-schedule-dock-legend-item">
                <i class="tone-${toneForLabel(label)}"></i>
                <em>${escapeHtml(label)}</em>
              </span>
            `)
            .join("")}
        </div>
      </div>
      ${homeScheduleDotRailMarkup(data, scheduleView)}
    `;
  }

  return ``;
}

function homeSelectorButton(panel, data) {
  const meta = getHomePanelMeta(panel.key, data);
  return `
    <button class="home-selector-btn home-selector-btn-rail" type="button" data-home-panel="${panel.key}">
      <span>${panel.eyebrow}</span>
      <strong>${panel.title}</strong>
      <div class="home-selector-meta">${meta.value}</div>
    </button>
  `;
}

function homeHeroCoreMarkup(panelKey, data, previewOnly = false) {
  const meta = getHomePanelMeta(panelKey, data);
  const hideHeroValueCopy = ["draws", "schedule", "doneFailed", "maintenance", "parts"].includes(panelKey);
  return `
    <div class="home-core-kicker">${meta.eyebrow}</div>
    <strong class="home-core-title">${meta.title}</strong>
    ${hideHeroValueCopy ? "" : `<div class="home-core-value">${meta.value}</div>`}
    ${hideHeroValueCopy ? "" : `<p class="home-core-copy">${meta.detail}</p>`}
    ${panelKey === "draws"
        ? orderProgressTimelineMarkup(data.draws.status_counts, {
          eyebrow: "Draw order flow",
          title: "Pending to done",
          compact: true,
        })
      : panelKey === "doneFailed"
        ? homeCompletionSummaryMarkup(data)
        : panelKey === "maintenance"
          ? homeMaintenanceFocusMarkup(data)
        : panelKey === "parts"
            ? homePartsStageLineMarkup(data)
            : hideHeroValueCopy
              ? ``
            : `
              <div class="home-schedule-hero-copy">
                <strong>Next maintenance</strong>
                <span>${(data.schedule.upcoming || [])[0] ? escapeHtml(data.schedule.upcoming[0].date_label || data.schedule.upcoming[0].day_key || "Planned next") : "No upcoming event"}</span>
              </div>
            `}
  `;
}

function getPrimaryLiveDraw(data) {
  const recent = data.draws.recent || [];
  return recent.find((item) => item.status === "In Progress")
    || recent.find((item) => item.status === "Scheduled")
    || recent[0]
    || null;
}

function getCurrentScheduleEvent(data, typeFilter = null) {
  const events = data.schedule?.expanded_events || [];
  const now = new Date();
  const filtered = typeFilter
    ? events.filter((item) => String(item?.event_type || "").trim().toLowerCase() === String(typeFilter).trim().toLowerCase())
    : events;
  return filtered.find((item) => {
    const start = item?.start ? new Date(item.start) : null;
    const end = item?.end ? new Date(item.end) : null;
    if (!(start instanceof Date) || Number.isNaN(start?.getTime?.())) return false;
    if (!(end instanceof Date) || Number.isNaN(end?.getTime?.())) return false;
    return start <= now && now <= end;
  }) || null;
}

function getTowerStatusSummary(data) {
  const liveDraw = getPrimaryLiveDraw(data);
  const maintenanceSnapshot = getHomeMaintenanceSnapshot(data);
  const currentStopEvent = getCurrentScheduleEvent(data, "Stop");
  const openedOrders = Number((data.parts.status_counts || {}).Opened || 0);
  const lowStock = Number((data.inventory.low_stock || []).length || 0);

  if ((data.draws.in_progress || 0) > 0 && liveDraw) {
    return {
      label: "Draw",
      tone: "warn",
      primary: liveDraw.preform || "Unknown preform",
      secondary: `${liveDraw.project || "No project"} · ${liveDraw.geometry || "No geometry"}`,
      facts: [
        { label: "Scheduled", value: data.draws.scheduled || 0, tone: "info" },
        { label: "Failed", value: data.draws.failed || 0, tone: (data.draws.failed || 0) ? "bad" : "good" },
        { label: "Pending", value: data.draws.pending || 0, tone: "warn" },
      ],
    };
  }

  if (maintenanceSnapshot.activeCount > 0 && maintenanceSnapshot.activeTask) {
    const activeTask = maintenanceSnapshot.activeTask;
    return {
      label: "Maintenance",
      tone: "bad",
      primary: activeTask.task || activeTask.component || "Maintenance in progress",
      secondary: [activeTask.component, activeTask.task_group].filter(Boolean).join(" · ") || "Execute lane active",
      facts: [
        { label: "Opened orders", value: openedOrders, tone: openedOrders ? "bad" : "good" },
        { label: "Low stock", value: lowStock, tone: lowStock ? "bad" : "good" },
        { label: "Active", value: maintenanceSnapshot.activeCount, tone: "bad" },
      ],
    };
  }

  if (currentStopEvent) {
    return {
      label: "Stop",
      tone: "bad",
      primary: currentStopEvent.description || "Tower stop in progress",
      secondary: `${currentStopEvent.date_label || ""}${currentStopEvent.end_label ? ` · until ${currentStopEvent.end_label}` : ""}`.trim(),
      facts: [
        { label: "Opened orders", value: openedOrders, tone: openedOrders ? "bad" : "good" },
        { label: "Low stock", value: lowStock, tone: lowStock ? "bad" : "good" },
        { label: "Duration", value: `${Math.round(Number(currentStopEvent.duration_hours || 0) * 10) / 10}h`, tone: "bad" },
      ],
    };
  }

  return {
    label: "No activity",
    tone: "good",
    primary: "No activity",
    secondary: `${data.draws.scheduled || 0} scheduled draws · ${maintenanceSnapshot.overdueCount || 0} overdue maintenance`,
    facts: [
      { label: "Opened orders", value: openedOrders, tone: openedOrders ? "bad" : "good" },
      { label: "Pending", value: data.draws.pending || 0, tone: "warn" },
      { label: "Low stock", value: lowStock, tone: lowStock ? "bad" : "good" },
    ],
  };
}

function homeStatusIndicatorMarkup(data) {
  const status = getTowerStatusSummary(data);
  return `
    <aside class="home-status-indicator tone-${status.tone}">
      <div class="home-status-head">
        <span>Tower status</span>
        <strong>${status.label}</strong>
      </div>
      <div class="home-status-main">
        <div class="home-status-signal">
          <i class="home-status-light tone-${status.tone}"></i>
          <span>${status.label === "Draw" ? "Running now" : status.label === "Maintenance" ? "Service active" : status.label === "Stop" ? "Tower stopped" : "No activity"}</span>
        </div>
        <div class="home-status-primary">${status.primary}</div>
        ${status.secondary ? `<div class="home-status-secondary">${status.secondary}</div>` : ``}
      </div>
    </aside>
  `;
}

function homeFloatingMarksMarkup(panelKey, data) {
  return "";
}

function actionButtonsMarkup() {
  return `
    <div class="action-row">
      <a class="action-btn action-primary" href="#/schedule">Open schedule layer</a>
      <a class="action-btn action-secondary" href="#/parts">Inspect parts flow</a>
    </div>
  `;
}

function renderShell(activeRoute) {
  const groupedNav = NAV_GROUPS.map((group) => {
    const hasActive = group.pages.some((page) => page.route === activeRoute);
    const items = group.pages
      .map(
        (page) => `
          <a
            class="nav-link ${page.route === activeRoute ? "is-active" : ""}"
            href="#${page.route}"
            data-nav-label="${page.label.toLowerCase()}"
            data-nav-eyebrow="${page.eyebrow.toLowerCase()}"
          >
            <span>${page.eyebrow}</span>
            <strong>${page.label}</strong>
          </a>
        `,
      )
      .join("");

    return `
      <section class="nav-group" data-nav-group>
        <button class="nav-group-title ${hasActive ? "is-open" : ""}" type="button" data-nav-group-toggle>
          <span>${group.title}</span>
        </button>
        <div class="nav-group-items">${items}</div>
      </section>
    `;
  }).join("");

  return `
    <div class="app-shell">
      <div class="layout-grid">
        <aside class="sidebar">
          <div class="sidebar-copy">
            <span class="sidebar-kicker">Navigation</span>
            <h1>App map</h1>
          </div>
          <nav class="sidebar-nav grouped-nav">${groupedNav}</nav>
        </aside>
        <main id="page-root" class="page-root"></main>
      </div>
    </div>
  `;
}

function bindSidebarMap() {
  const groups = Array.from(document.querySelectorAll("[data-nav-group]"));

  groups.forEach((group) => {
    const toggle = group.querySelector("[data-nav-group-toggle]");
    if (!toggle) return;
    const setOpen = (open) => {
      group.classList.toggle("is-collapsed", !open);
      toggle.classList.toggle("is-open", open);
    };
    setOpen(toggle.classList.contains("is-open"));
    toggle.addEventListener("click", () => {
      setOpen(group.classList.contains("is-collapsed"));
    });
  });
}

function renderHomeCategoryPanel(panelKey, data) {
  const statusSeries = Object.entries(data.draws.status_counts).map(([label, value]) => ({ label, value }));
  const doneFailedSeries = [
    { label: "Done", value: data.draws.done },
    { label: "Failed", value: data.draws.failed },
    { label: "Active", value: data.draws.active },
  ];
  const maintenanceRows = [
    ...data.inventory.low_stock.slice(0, 4).map((item) => ({
      part_name: item.part_name,
      status: `${item.quantity}/${item.min_level}`,
      company: item.location,
      project: "Inventory",
      details: `${item.component || "General"} below minimum stock`,
    })),
    ...data.parts.open_orders
      .filter((item) => item.project === "Maintenance")
      .slice(0, 4)
      .map((item) => ({
        part_name: item.part_name,
        status: item.status,
        company: item.company,
        project: item.project,
        details: item.details || "Maintenance order still open",
      })),
  ].slice(0, 6);

  if (panelKey === "draws") {
    const liveDraw = getPrimaryLiveDraw(data);
    return `
      <div class="home-panel-body">
        <div class="section-heading compact-head">
          <span>Live draws</span>
          <h3>Now on tower</h3>
        </div>
        <div class="home-now-layout">
          <div class="chart-card home-now-plot-card">
            <div class="chart-head">
              <span>Live movement</span>
              <strong>Draw activity and order state</strong>
            </div>
            <div class="home-large-plot">
              ${sparklineMarkup(data.draws.activity_series)}
            </div>
          </div>
          <div class="chart-card home-now-summary-card">
            <div class="chart-head">
              <span>Immediate context</span>
              <strong>${liveDraw ? (liveDraw.project || "No project") : "No live draw selected"}</strong>
            </div>
            ${liveDraw ? `
              <div class="home-now-facts">
                <div class="home-now-fact"><span>Preform</span><strong>${liveDraw.preform || "Unknown"}</strong></div>
                <div class="home-now-fact"><span>Status</span><strong>${liveDraw.status}</strong></div>
                <div class="home-now-fact"><span>Geometry</span><strong>${liveDraw.geometry || "No geometry"}</strong></div>
                <div class="home-now-fact"><span>Priority</span><strong>${liveDraw.priority || "Normal"}</strong></div>
                <div class="home-now-fact"><span>Opener</span><strong>${liveDraw.opener || "Unknown"}</strong></div>
                <div class="home-now-fact"><span>Length</span><strong>${liveDraw.length || "0"} m</strong></div>
              </div>
              <div class="micro-panel">${liveDraw.notes || "No special notes on the current highlighted draw."}</div>
            ` : `<div class="micro-panel">No current in-progress draw was found. The dashboard is showing the most recent available order instead.</div>`}
            <div class="metric-row compact">
              <div class="metric-pill tone-warn"><span>Now</span><strong>${data.draws.in_progress || 0}</strong></div>
              <div class="metric-pill tone-info"><span>Sched.</span><strong>${data.draws.scheduled || 0}</strong></div>
              <div class="metric-pill tone-good"><span>Done</span><strong>${data.draws.done || 0}</strong></div>
            </div>
          </div>
        </div>
        ${collapsibleSection("Recent order stream", `<div class="flow-list">${drawRowsMarkup(data.draws.recent)}</div>`, {
          kind: "list",
          meta: `${data.draws.recent.length} rows`,
        })}
      </div>
    `;
  }

  if (panelKey === "doneFailed") {
    return `
      <div class="home-panel-body">
        <div class="section-heading compact-head">
          <span>Done + failed</span>
          <h3>Resolution pulse</h3>
        </div>
        <div class="visual-grid compact-grid home-panel-slim-grid">
          <div class="chart-card">
            <div class="chart-head">
              <span>Closeout</span>
              <strong>Done vs failed</strong>
            </div>
            ${homeCompletionSummaryMarkup(data)}
          </div>
          <div class="chart-card">
            <div class="chart-head">
              <span>Recent activity</span>
              <strong>Completion movement</strong>
            </div>
            ${sparklineMarkup(data.draws.activity_series)}
          </div>
        </div>
        ${collapsibleSection("Resolved order list", `<div class="flow-list">${drawRowsMarkup(data.draws.recent.filter((item) => item.status === "Done" || item.status === "Failed"))}</div>`, {
          kind: "list",
          meta: `${data.draws.recent.filter((item) => item.status === "Done" || item.status === "Failed").length} rows`,
        })}
      </div>
    `;
  }

  if (panelKey === "schedule") {
    return `
      <div class="home-panel-body">
        <div class="section-heading compact-head">
          <span>Schedule</span>
          <h3>Timeline pressure</h3>
        </div>
        <div class="chart-card home-schedule-compact-card">
          <div class="chart-head">
            <span>Tower timeline</span>
            <strong>Sunday start week</strong>
          </div>
          ${homeScheduleDotRailMarkup(data)}
        </div>
        <div class="chart-card home-schedule-upcoming-card">
          <div class="chart-head">
            <span>Next windows</span>
            <strong>${data.schedule.upcoming.length} scheduled touches</strong>
          </div>
          <div class="home-schedule-chip-row home-schedule-chip-row-compact">
            ${(data.schedule.upcoming || []).slice(0, 6).map((event) => `
              <div class="home-schedule-chip tone-${toneForLabel(event.event_type)}">
                <span>${event.event_type}</span>
                <strong>${event.date_label || event.day_key || "Planned"}</strong>
              </div>
            `).join("")}
          </div>
        </div>
      </div>
    `;
  }

  if (panelKey === "maintenance") {
    const maintenanceSnapshot = getHomeMaintenanceSnapshot(data);
    const overdueRows = maintenanceSnapshot.overdueTasks.slice(0, 8).map((item) => ({
      part_name: item.component || "Maintenance",
      status: item.timing_status || "Overdue",
      company: item.task_group || item.tracking_mode || "Maintenance",
      project: "Overdue",
      details: item.task || "Overdue maintenance task",
    }));
    const criticalRows = maintenanceSnapshot.criticalFaults.slice(0, 8).map((item) => ({
      part_name: item.component || "Fault",
      status: item.severity || "Critical",
      company: item.ts || "Open",
      project: "Fault",
      details: item.title || "Critical fault",
    }));
    return `
      <div class="home-panel-body">
        <div class="section-heading compact-head">
          <span>Maintenance + faults</span>
          <h3>Service readiness</h3>
        </div>
        <div class="visual-grid compact-grid home-panel-slim-grid">
          <div class="chart-card">
            <div class="chart-head">
              <span>Overdue maintenance</span>
              <strong>${maintenanceSnapshot.overdueCount} overdue tasks</strong>
            </div>
            <div class="stack-list">${supplyRowsMarkup(overdueRows)}</div>
          </div>
          <div class="chart-card">
            <div class="chart-head">
              <span>Critical faults</span>
              <strong>${maintenanceSnapshot.criticalCount} open urgent faults</strong>
            </div>
            <div class="stack-list">${supplyRowsMarkup(criticalRows)}</div>
          </div>
        </div>
      </div>
    `;
  }

  if (panelKey === "parts") {
    return `
      <div class="home-panel-body">
        <div class="section-heading compact-head">
          <span>Parts</span>
          <h3>Orders and supply pressure</h3>
        </div>
        <div class="chart-card home-parts-hero-card">
          <div class="chart-head">
            <span>Supply pressure</span>
            <strong>Order flow snapshot</strong>
          </div>
          ${homePartsStageLineMarkup(data)}
        </div>
        <div class="visual-grid compact-grid home-panel-slim-grid">
          <div class="chart-card">
            <div class="chart-head">
              <span>Open orders</span>
              <strong>${data.parts.open_orders.length} surfaced now</strong>
            </div>
            <div class="stack-list">${supplyRowsMarkup(data.parts.open_orders)}</div>
          </div>
          <div class="chart-card">
            <div class="chart-head">
              <span>Low stock</span>
              <strong>${data.inventory.low_stock.length} watch items</strong>
            </div>
            <div class="stack-list">${supplyRowsMarkup(data.inventory.low_stock.slice(0, 8).map((item) => ({
              part_name: item.part_name,
              status: `${item.quantity}/${item.min_level}`,
              company: item.location || "Inventory",
              project: item.component || "Stock",
              details: `${item.component || "General"} below minimum level`,
            })))}</div>
          </div>
        </div>
      </div>
    `;
  }

  return `
    <div class="home-panel-placeholder-text">Select a home category.</div>
  `;
}

function homeOrbitButton(panel, data) {
  const meta = getHomePanelMeta(panel.key, data);
  return `
    <button class="orbit-chip ${panel.position}" type="button" data-home-panel="${panel.key}">
      <span>${panel.eyebrow}</span>
      <strong>${panel.title}</strong>
      <div class="orbit-chip-meta">${meta.value}</div>
    </button>
  `;
}

async function renderHomePage(data) {
  return `
    <section class="home-command-surface home-command-surface-flat home-command-surface-flagship home-command-surface-redesign">
      <section class="home-homeframe home-homeframe-redesign">
        <section class="home-cinematic-stage" id="home-cinematic-stage">
          <div id="home-health-toast-root"></div>
          <div class="home-stage-grid"></div>
          <div class="home-stage-vignette"></div>
          <div class="home-stage-scan home-stage-scan-x"></div>
          <div class="home-stage-scan home-stage-scan-y"></div>
          <div class="home-stage-beam"></div>
          <div class="home-stage-glow"></div>

          <header class="home-title-block">
            <div class="eyebrow">Tower command system</div>
            <h1>Tower software</h1>
          </header>

          ${homeStatusIndicatorMarkup(data)}

          <div class="home-focus-headline" id="home-active-core">
            <div class="home-focus-core-body" id="home-focus-core-body">
              ${homeHeroCoreMarkup(DEFAULT_HOME_PANEL, data)}
            </div>
            <div class="home-focus-detail ${DEFAULT_HOME_PANEL === "schedule" ? "is-visible" : ""}" id="home-detail-dock">
              ${homeDetailDockMarkup(DEFAULT_HOME_PANEL, data)}
            </div>
          </div>

          <aside class="home-command-rail home-command-rail-side">
            <div class="home-command-rail-label">Command layer</div>
            <div class="home-command-rail-list home-command-rail-list-side">
              ${HOME_PANELS.map((panel) => homeSelectorButton(panel, data)).join("")}
            </div>
          </aside>
        </section>
      </section>
    </section>
  `;
}

async function renderSchedulePage(data) {
  const initialAnchor = todayIsoDate();
  return `
    <section class="page-panel schedule-page" id="schedule-page" data-schedule-anchor="${initialAnchor}">
      <div class="section-heading" ${titleBandStyle("title-photo-a.jpg", "36% center")}>
        <span>Schedule</span>
        <h2>Operations timeline</h2>
        <p>Move between week and month views and inspect the actual recurring schedule on one shared timeline surface.</p>
      </div>
      <div class="schedule-toolbar">
        <div class="schedule-toggle-group">
          <button class="schedule-toggle is-active" type="button" data-schedule-view="week">Week</button>
          <button class="schedule-toggle" type="button" data-schedule-view="month">Month</button>
        </div>
        <div class="schedule-nav-group">
          <button class="schedule-nav-btn" type="button" data-schedule-nav="prev">Prev</button>
          <button class="schedule-nav-btn" type="button" data-schedule-nav="today">Today</button>
          <button class="schedule-nav-btn" type="button" data-schedule-nav="next">Next</button>
        </div>
      </div>
      <div id="schedule-canvas-root">
        ${renderScheduleCanvas(data, "week", initialAnchor)}
      </div>
      <div class="visual-grid visual-grid-wide schedule-manage-wide">
        <div class="chart-card">
          <div class="chart-head">
            <span>Manage schedule</span>
            <strong>Add and maintain master events</strong>
          </div>
          <div class="schedule-manage-grid">
            ${collapsibleSection("Add new event", `
              <form id="schedule-add-form" class="stack-form">
                <div class="field-grid field-grid-2">
                  <label class="field-block">
                    <span>Event type</span>
                    <select name="eventType">
                      <option>Maintenance</option>
                      <option>Drawing</option>
                      <option>Stop</option>
                      <option>Management Event</option>
                    </select>
                  </label>
                  <label class="field-block">
                    <span>Recurrence</span>
                    <select name="recurrence">
                      <option value="none">None</option>
                      <option value="weekly">Weekly</option>
                      <option value="monthly">Monthly</option>
                      <option value="every 3 months">Every 3 Months</option>
                      <option value="every 6 months">Every 6 Months</option>
                      <option value="yearly">Yearly</option>
                    </select>
                  </label>
                </div>
                <label class="field-block">
                  <span>Description</span>
                  <textarea name="description" rows="3" placeholder="Short event description"></textarea>
                </label>
                <div class="field-grid field-grid-2">
                  <label class="field-block">
                    <span>Start</span>
                    <input type="datetime-local" name="start" />
                  </label>
                  <label class="field-block">
                    <span>End</span>
                    <input type="datetime-local" name="end" />
                  </label>
                </div>
                <div class="parts-form-actions">
                  <button class="action-btn action-primary" type="submit">Add event</button>
                </div>
              </form>
            `, { kind: "panel", tone: "good", meta: "create" })}
            ${collapsibleSection("Delete event", `
              <form id="schedule-delete-form" class="stack-form">
                <label class="field-block">
                  <span>Select event</span>
                  <select name="index">
                    ${(data.master_rows || []).map((item) => `
                      <option value="${item.index}">
                        ${item.event_type} | ${item.start || "No start"} | ${String(item.description || "").slice(0, 48)}
                      </option>
                    `).join("")}
                  </select>
                </label>
                <div class="parts-form-actions">
                  <button class="action-btn action-secondary" type="submit">Delete selected event</button>
                </div>
              </form>
            `, { kind: "panel", tone: "bad", meta: `${(data.master_rows || []).length} rows`, open: false })}
          </div>
        </div>
      </div>
    </section>
  `;
}

async function renderPartsPage(data) {
  return `
    <section class="page-panel parts-page" id="parts-page">
      <div class="section-heading" ${titleBandStyle("title-photo-b.jpeg", "54% center")}>
        <span>Supply</span>
        <h2>Tower parts control</h2>
        <p>Run the order flow from one compact status line, then open the exact action you need without bouncing between duplicate boards.</p>
      </div>
      ${partsManageFormMarkup(data)}
      ${partsStageFlowMarkup(data)}

      ${collapsibleSection(
        "Inventory Center",
        `
          ${partsQuickInventoryMarkup(data)}
        `,
        { kind: "list", meta: `${data.inventory.low_stock_total || data.inventory.low_stock.length} low stock items`, open: false },
      )}
    </section>
  `;
}

async function renderMaintenancePage(data) {
  return `
    <section class="page-panel maintenance-page" id="maintenance-page">
      <div class="section-heading" ${titleBandStyle("title-photo-c.jpg", "44% center")}>
        <span>Maintenance</span>
        <h2>Service flow studio</h2>
        <p>Builder first, then plan and prepare, then execute. Manuals, package logic, blockers, and linked parts stay inside the same maintenance surface.</p>
      </div>
      <div class="maintenance-group-strip">
        ${MAINT_GROUPS.map((group) => `
          <button class="maintenance-group-btn ${group.key === "maintenance" ? "is-active" : ""} tone-${group.tone}" type="button" data-maint-group="${group.key}">
            <span>${group.title}</span>
            <strong>${group.sub}</strong>
          </button>
        `).join("")}
      </div>
      <div id="maintenance-group-root">
        <div class="maintenance-mode-strip">
          ${MAINT_VIEWS.map((view) => `
            <button class="maintenance-mode-btn ${view.key === "builder" ? "is-active" : ""}" type="button" data-maint-view="${view.key}">
              <span>${view.title}</span>
              <strong>${view.sub}</strong>
            </button>
          `).join("")}
        </div>
        <div id="maintenance-context-root"></div>

        <section class="maintenance-workspace">
          <div class="maintenance-list-shell">
            <div class="chart-head">
              <span id="maintenance-list-eyebrow">Builder queue</span>
              <strong id="maintenance-list-title">Maintenance tasks</strong>
            </div>
            <div class="maintenance-toolbar">
              <input class="parts-search-input" id="maintenance-search-input" placeholder="Search task / task id / component..." />
            </div>
            <div class="maintenance-list" id="maintenance-list"></div>
          </div>
          <aside class="maintenance-detail-shell">
            <div class="chart-head">
              <span id="maintenance-detail-eyebrow">Task focus</span>
              <strong id="maintenance-detail-title">Selected task workspace</strong>
            </div>
            <div id="maintenance-detail-panel">${maintenanceDetailMarkup(data.prep_queue[0] || data.tasks[0])}</div>
            <div class="maintenance-action-panel" id="maintenance-action-panel"></div>
          </aside>
        </section>
      </div>
    </section>
  `;
}

async function renderOrderDrawPage(data) {
  return `
    <section class="page-panel order-draw-page" id="order-draw-page">
        <div class="section-heading" ${titleBandStyle("title-photo-d.jpg", "56% center")}>
          <span>Order Draw</span>
          <h2>Draw order intake</h2>
          <p>This rebuild mirrors the real page flow: existing orders first, pending-to-schedule quick action, then a four-step new order builder.</p>
        </div>
        ${orderDrawNoticeMarkup()}
        ${compactOrderFlowMarkup(data)}
        <div class="order-builder-shell">
          <div class="section-heading minimal">
            <span>Create new order</span>
            <h3>Four-step builder</h3>
          </div>
          <div class="order-builder-topline">Choose project first, then move through Required, Targets, Materials, and Template. This page stays dedicated to order intake only.</div>
          <div class="order-builder-progress" id="order-builder-progress">
            <div class="order-builder-progress-line"><i id="order-builder-progress-fill"></i></div>
            <div class="order-builder-progress-steps">
              <button class="builder-progress-step is-active" type="button" data-builder-progress-step="required">
                <span>Required</span>
                <strong>0 / 7</strong>
              </button>
              <button class="builder-progress-step" type="button" data-builder-progress-step="targets">
                <span>Targets</span>
                <strong>0 / 9</strong>
              </button>
              <button class="builder-progress-step" type="button" data-builder-progress-step="materials">
                <span>Materials</span>
                <strong>0 / 4</strong>
              </button>
              <button class="builder-progress-step" type="button" data-builder-progress-step="template">
                <span>Template</span>
                <strong>Pending</strong>
              </button>
            </div>
          </div>
          <form id="order-builder-form" class="order-builder-form">
            <div class="field-grid field-grid-project">
              <label class="field-block field-required">
                <span>Fiber project</span>
                <select name="project" id="order-project-select" required>
                  <option value="">Select project...</option>
                  ${data.project_names.map((project) => `<option value="${project}">${project}</option>`).join("")}
                </select>
              </label>
              <label class="field-block">
                <span>New project name</span>
                <input type="text" name="newProjectName" placeholder="Optional, adds project on submit" />
              </label>
              <div class="micro-panel template-status" id="order-template-status">Select a project to auto-load its saved template defaults.</div>
            </div>
            <div class="builder-tabs" role="tablist" aria-label="Order builder tabs">
              <button class="builder-tab is-active" type="button" data-order-tab="required">1. Required</button>
              <button class="builder-tab" type="button" data-order-tab="targets">2. Targets</button>
              <button class="builder-tab" type="button" data-order-tab="materials">3. Materials</button>
              <button class="builder-tab" type="button" data-order-tab="template">4. Template</button>
            </div>
            <div class="builder-panel is-active" data-order-panel="required">
              <div class="field-grid field-grid-4">
                <label class="field-block field-required">
                  <span>Preform number</span>
                  <input type="text" name="preformNumber" placeholder="0 if it does not exist yet" required />
                </label>
                <label class="field-block field-required">
                  <span>Priority</span>
                  <select name="priority" required>
                    <option value="Low">Low</option>
                    <option value="Normal" selected>Normal</option>
                    <option value="High">High</option>
                  </select>
                </label>
                <label class="field-block field-required">
                  <span>Geometry</span>
                  <select name="geometry" id="order-geometry-select" required>
                    ${data.form_config.geometry_options.map((option) => `<option value="${option}">${option || "Select geometry..."}</option>`).join("")}
                  </select>
                </label>
                <label class="field-block field-required">
                  <span>Order opened by</span>
                  <input type="text" name="opener" placeholder="Name or initials" required />
                </label>
              </div>
              <div class="field-grid field-grid-3">
                <label class="field-block field-required">
                  <span>Required length (m)</span>
                  <input type="number" name="requiredLength" min="0" step="0.01" required />
                </label>
                <label class="field-block">
                  <span>Good zones count</span>
                  <input type="number" name="goodZones" min="1" step="1" value="1" />
                </label>
                <label class="field-block field-required">
                  <span>Preform diameter (mm)</span>
                  <input type="number" name="preformDiameterMm" min="0" step="0.01" required />
                </label>
              </div>
              <div class="field-grid field-grid-3 conditional-geometry">
                <label class="field-block is-hidden" id="field-tiger-cut">
                  <span>Tiger cut (%)</span>
                  <input type="number" name="tigerCut" min="0" max="100" step="0.5" />
                </label>
                <label class="field-block is-hidden" id="field-oct-f2f">
                  <span>Octagonal F2F (mm)</span>
                  <input type="number" name="octF2f" min="0" step="0.01" />
                </label>
                <div class="micro-panel is-hidden" id="field-sap-banner"></div>
              </div>
              <label class="field-block">
                <span>Notes</span>
                <textarea name="notes" rows="5" placeholder="Special instructions, customer notes, risks, coating remarks..."></textarea>
              </label>
            </div>
            <div class="builder-panel" data-order-panel="targets">
              <div class="field-grid field-grid-3">
                <label class="field-block field-required">
                  <span>Fiber diameter (um)</span>
                  <input type="number" name="fiberDiameter" min="0" step="0.01" />
                </label>
                <label class="field-block field-required">
                  <span>Main coating diameter (um)</span>
                  <input type="number" name="mainCoatingDiameter" min="0" step="0.01" />
                </label>
                <label class="field-block field-required">
                  <span>Secondary coating diameter (um)</span>
                  <input type="number" name="secondaryCoatingDiameter" min="0" step="0.01" />
                </label>
              </div>
              <div class="field-grid field-grid-3">
                <label class="field-block field-required">
                  <span>Fiber tolerance (± um)</span>
                  <input type="number" name="fiberTol" min="0" step="0.01" />
                </label>
                <label class="field-block field-required">
                  <span>Main tolerance (± um)</span>
                  <input type="number" name="mainTol" min="0" step="0.01" />
                </label>
                <label class="field-block field-required">
                  <span>Secondary tolerance (± um)</span>
                  <input type="number" name="secondaryTol" min="0" step="0.01" />
                </label>
              </div>
              <div class="field-grid field-grid-3">
                <label class="field-block field-required">
                  <span>Tension (g)</span>
                  <input type="number" name="tension" min="0" step="0.1" />
                </label>
                <label class="field-block field-required">
                  <span>Draw speed (m/min)</span>
                  <input type="number" name="drawSpeed" min="0" step="0.1" />
                </label>
                <label class="field-block field-required">
                  <span>Furnace temperature (°C)</span>
                  <input type="number" name="furnaceTemp" min="0" step="0.1" />
                </label>
              </div>
            </div>
            <div class="builder-panel" data-order-panel="materials">
              <div class="field-grid field-grid-2">
                <label class="field-block field-required">
                  <span>Main coating</span>
                  <select name="mainCoating">
                    <option value="">Select coating...</option>
                    ${data.coating_options.map((item) => `<option value="${item}">${item}</option>`).join("")}
                  </select>
                </label>
                <label class="field-block field-required">
                  <span>Secondary coating</span>
                  <select name="secondaryCoating">
                    <option value="">Select coating...</option>
                    ${data.coating_options.map((item) => `<option value="${item}">${item}</option>`).join("")}
                  </select>
                </label>
              </div>
              <div class="field-grid field-grid-2">
                <label class="field-block field-required">
                  <span>Main coating temperature (°C)</span>
                  <input type="number" name="mainCoatingTemp" min="0" step="0.5" value="25" />
                </label>
                <label class="field-block field-required">
                  <span>Secondary coating temperature (°C)</span>
                  <input type="number" name="secondaryCoatingTemp" min="0" step="0.5" value="25" />
                </label>
              </div>
            </div>
            <div class="builder-panel" data-order-panel="template">
              <div class="micro-panel">
                Saving a template updates the defaults for the selected project only. This belongs here because it is part of the order intake workflow.
              </div>
              <div class="builder-template-status" id="order-template-progress-note">Choose a project and save its template defaults when this setup is ready.</div>
              <div class="metric-row compact">
                <div class="metric-pill tone-info"><span>Projects with templates</span><strong>${data.template_project_names.length}</strong></div>
                <div class="metric-pill tone-warn"><span>Current library</span><strong>${data.template_count}</strong></div>
              </div>
              <button class="action-btn action-secondary" type="button" id="order-save-template-btn">Save / Update Template</button>
            </div>
            <label class="toggle-row">
              <input type="checkbox" name="scheduleNow" id="order-schedule-now-toggle" />
              <span>Schedule immediately after submit</span>
            </label>
            <div class="builder-schedule-panel is-hidden" id="order-builder-schedule-panel">
              <div class="field-grid field-grid-4">
                <label class="field-block field-required">
                  <span>Schedule date</span>
                  <input type="date" name="scheduleDate" />
                </label>
                <label class="field-block field-required">
                  <span>Start time</span>
                  <input type="time" name="scheduleStartTime" value="08:00" />
                </label>
                <label class="field-block field-required">
                  <span>Duration (min)</span>
                  <input type="number" name="scheduleDurationMin" min="5" step="5" value="480" />
                </label>
                <label class="field-block field-required">
                  <span>Scheduling password</span>
                  <input type="password" name="schedulePassword" />
                </label>
              </div>
            </div>
            <div class="order-builder-actions">
              <button class="action-btn action-primary" type="submit">Submit Draw Order</button>
            </div>
          </form>
        </div>
        <div class="order-draw-layout order-draw-layout-compact">
          <aside class="order-draw-side">
            <details class="fold-section fold-panel fold-tone-info order-side-fold">
              <summary class="fold-summary">
                <div class="fold-summary-copy">
                  <span>Pending to schedule</span>
                  <strong>Quick operator action</strong>
                </div>
                <div class="fold-summary-right">
                  <div class="fold-summary-meta">${data.pending_orders.length} pending</div>
                  <div class="fold-summary-toggle">Open</div>
                </div>
              </summary>
              <div class="fold-body">
                <form id="order-schedule-form" class="order-stack-form">
                  <label class="field-block field-required">
                    <span>Select pending order</span>
                    <select id="order-schedule-select" name="orderIndex" ${data.pending_orders.length ? "" : "disabled"} required>
                      <option value="">Choose pending order...</option>
                      ${data.pending_orders.map((item) => `<option value="${item.index}">${item.project} · ${item.preform || "No preform"} · ${item.priority}</option>`).join("")}
                    </select>
                  </label>
                  <div id="order-schedule-preview" class="micro-panel">
                    ${data.pending_orders.length ? "Choose an order to preview its details here." : "No pending orders available for quick scheduling."}
                  </div>
                  <label class="field-block">
                    <span>Preform number override</span>
                    <input type="text" name="preformNumber" placeholder="Needed if current preform is 0 or blank" />
                  </label>
                  <div class="field-grid field-grid-3">
                    <label class="field-block field-required">
                      <span>Schedule date</span>
                      <input type="date" name="date" required />
                    </label>
                    <label class="field-block field-required">
                      <span>Start time</span>
                      <input type="time" name="startTime" value="08:00" required />
                    </label>
                    <label class="field-block field-required">
                      <span>Duration (min)</span>
                      <input type="number" name="durationMin" min="5" step="5" value="480" required />
                    </label>
                  </div>
                  <label class="field-block field-required">
                    <span>Scheduling password</span>
                    <input type="password" name="password" placeholder="Required for scheduling" required />
                  </label>
                  <button class="action-btn action-primary" type="submit" ${data.pending_orders.length ? "" : "disabled"}>Schedule Selected Order</button>
                </form>
              </div>
            </details>
          </aside>
        </div>
    </section>
  `;
}

function dashboardPlotMarkup(logData, yColumns) {
  if (!logData?.rows?.length || !yColumns.length) {
    return `<div class="chart-empty">Choose one or more signals to draw the plot.</div>`;
  }
  return `
    <div class="dashboard-canvas-shell">
      <canvas id="dashboard-plot-canvas" class="dashboard-plot-canvas"></canvas>
    </div>
  `;
}

function dashboardMathPlotMarkup() {
  return `
    <div class="dashboard-plot-shell dashboard-math-plot-shell">
      <div class="dashboard-canvas-shell dashboard-canvas-shell-math">
        <canvas id="dashboard-math-canvas" class="dashboard-plot-canvas dashboard-plot-canvas-passive"></canvas>
      </div>
    </div>
  `;
}

async function renderDashboardRebuildPage(data) {
  return `
    <section class="page-panel dashboard-rebuild-page" id="dashboard-page">
      <div class="section-heading" ${titleBandStyle("title-photo-b.jpeg", "50% center")}>
        <span>Dashboard</span>
        <h2>Draw tower logs workspace</h2>
        <p>The rebuild keeps the dashboard in its own lane: pick a log, set the signals, and inspect the line behavior before we rebuild zone tools and exports on top.</p>
      </div>
      <div class="dashboard-workspace dashboard-workspace-expanded">
        <div class="dashboard-main-stage dashboard-main-stage-expanded">
          <div class="chart-card dashboard-plot-card dashboard-plot-card-hero dashboard-plot-card-dominant">
            <div class="chart-head dashboard-plot-head">
              <div>
                <span>Plot</span>
                <strong id="dashboard-plot-title">Loading latest tower log...</strong>
              </div>
              <div id="dashboard-selected-signals" class="token-list dashboard-token-list"></div>
            </div>
            <div id="dashboard-plot-shell" class="dashboard-plot-shell">Loading log surface...</div>
          </div>
          <div class="dashboard-bottom-grid">
            <div class="dashboard-control-grid dashboard-control-grid-wide">
              <div class="dashboard-plot-tools-grid">
                <div class="chart-card dashboard-control-card dashboard-control-card-wide">
                  <div class="chart-head">
                    <span>Signal setup</span>
                    <strong>Choose file and axes</strong>
                  </div>
                  <div class="field-grid-3">
                    <div class="field-block">
                      <span>Log file</span>
                      <select id="dashboard-log-select">
                        ${data.available_logs.map((name) => `<option value="${name}" ${name === data.latest_log ? "selected" : ""}>${name === data.latest_log ? `${name} - latest` : name}</option>`).join("")}
                      </select>
                    </div>
                    <div class="field-block">
                      <span>X axis</span>
                      <select id="dashboard-x-select"></select>
                    </div>
                    <div class="field-block">
                      <span>Scale mode</span>
                      <select id="dashboard-scale-mode-select">
                        <option value="independent" selected>Independent</option>
                        <option value="shared">Shared</option>
                      </select>
                    </div>
                  </div>
                  <label class="field-block">
                    <span>Parameter search</span>
                    <input id="dashboard-signal-search" type="text" placeholder="Search signals by name" autocomplete="off" />
                  </label>
                  <div class="dashboard-signal-grid" id="dashboard-signal-grid"></div>
                </div>
                <div class="chart-card dashboard-control-card dashboard-zone-card">
                  <div class="chart-head">
                    <span>Zone marker</span>
                    <strong>Mark a few zones, then save</strong>
                  </div>
                  <div id="dashboard-zone-preview" class="micro-panel"></div>
                  <div class="order-builder-actions">
                    <button class="action-btn action-primary" type="button" id="dashboard-save-preview-btn">Save Marked Zone</button>
                    <button class="action-btn action-secondary" type="button" id="dashboard-undo-zone-btn">Undo Last</button>
                    <button class="action-btn action-secondary" type="button" id="dashboard-clear-zones-btn">Clear All</button>
                  </div>
                  <div id="dashboard-zone-status" class="micro-panel">Saved: 0 | Current mark: no</div>
                  <div id="dashboard-zone-saved-list" class="micro-list"></div>
                </div>
              </div>
              <div class="chart-card dashboard-control-card">
                <div class="chart-head">
                  <span>Dataset export</span>
                  <strong>Export saved zones</strong>
                </div>
                <label class="field-block">
                  <span>Dataset CSV</span>
                  <select id="dashboard-dataset-select">
                    ${data.dataset_csvs.map((name) => `<option value="${name}" ${name === data.latest_dataset ? "selected" : ""}>${name === data.latest_dataset ? `${name} - most recent` : name}</option>`).join("")}
                  </select>
                </label>
                <div class="micro-panel">Most recent dataset: <strong>${data.latest_dataset || "None"}</strong></div>
                <div class="order-builder-actions">
                  <button class="action-btn action-primary" type="button" id="dashboard-save-zones-latest-btn">Save To Most Recent</button>
                  <button class="action-btn action-secondary" type="button" id="dashboard-save-zones-btn">Save To Selected</button>
                </div>
              </div>
            </div>
          </div>
          ${collapsibleSection("Math Lab", `
            <div class="field-grid field-grid-3">
              <label class="field-block">
                <span>Parameter A</span>
                <select id="dashboard-math-x-select"></select>
              </label>
              <label class="field-block">
                <span>Parameter B</span>
                <select id="dashboard-math-y-select"></select>
              </label>
              <label class="field-block">
                <span>Expression</span>
                <input id="dashboard-math-expr" type="text" value="A" placeholder="A, A*B, Math.log(A), A+B" />
              </label>
            </div>
            <div class="token-strip" id="dashboard-math-presets">
              <button class="parts-filter-chip" type="button" data-math-preset="A">Use A</button>
              <button class="parts-filter-chip" type="button" data-math-preset="A*B">A * B</button>
              <button class="parts-filter-chip" type="button" data-math-preset="A/B">A / B</button>
              <button class="parts-filter-chip" type="button" data-math-preset="A-B">A - B</button>
              <button class="parts-filter-chip" type="button" data-math-preset="(A+B)/2">(A + B) / 2</button>
              <button class="parts-filter-chip" type="button" data-math-preset="((A-B)/B)*100">A vs B %</button>
              <button class="parts-filter-chip" type="button" data-math-preset="Math.abs(A-B)">abs(A-B)</button>
              <button class="parts-filter-chip" type="button" data-math-preset="Math.max(A,B)">max(A,B)</button>
              <button class="parts-filter-chip" type="button" data-math-preset="Math.min(A,B)">min(A,B)</button>
              <button class="parts-filter-chip" type="button" data-math-preset="Math.log(A)">log(A)</button>
              <button class="parts-filter-chip" type="button" data-math-preset="Math.sqrt(A+B)">sqrt(A+B)</button>
            </div>
            <div class="micro-panel">Use <code>A</code>, optional <code>B</code>, and <code>Math</code>. Example: <code>A*B</code> or <code>Math.sqrt(A+B)</code></div>
            <div class="parts-form-actions">
              <button class="action-btn action-secondary" type="button" id="dashboard-math-run-btn">Run Math Plot</button>
            </div>
            <div id="dashboard-math-shell" class="micro-panel">Math plot will appear here.</div>
          `, { kind: "panel", meta: "advanced", open: false })}
        </div>
      </div>
    </section>
  `;
}

async function renderDiagnosticsPage(data) {
  const runtimeModeLabel = data.runtime_mode === "local-first" ? "Local-first runtime" : "Direct root runtime";
  const healthRows = (data.health_checks || [])
    .map(
      (item) => `
        <article class="diag-check-card tone-${item.ok ? "good" : "bad"}">
          <div class="diag-check-copy">
            <span>${item.label}</span>
            <strong>${item.ok ? "Ready" : "Needs check"}</strong>
            <p>${item.detail}</p>
          </div>
          <div class="diag-check-state">${item.ok ? "PASS" : "CHECK"}</div>
        </article>
      `,
    )
    .join("");
  const pathRows = data.path_rows
    .map(
      (item) => {
        const localTone = item.status === "BLOCKED" ? "bad" : "good";
        const globalTone = ["READY", "SYNCED", "LOCAL ONLY"].includes(item.global_status)
          ? "good"
          : ["SYNCING", "CONFIG ONLY", "WAITING"].includes(item.global_status)
            ? "warn"
            : "bad";
        return `
        <article class="diag-row tone-${localTone}">
          <div class="diag-row-copy">
            <h3>${escapeHtml(item.label || item.key)}</h3>
            <p><strong>Local</strong> · ${escapeHtml(item.path)}</p>
            <p class="diag-row-substate tone-${localTone}">${escapeHtml(item.status || "READY")} · ${escapeHtml(item.local_detail || "")}</p>
            <p><strong>Global</strong> · ${item.global_enabled ? escapeHtml(item.global_path || "Not set") : "Local only"}</p>
            <p class="diag-row-substate tone-${globalTone}">${escapeHtml(item.global_status || "LOCAL ONLY")} · ${escapeHtml(item.global_detail || "No global mirror configured.")}</p>
          </div>
          <div class="diag-row-meta">
            <strong>${item.status}</strong>
            <span>${item.is_override ? "Custom override" : "Tower default"} · ${escapeHtml(item.modified)}</span>
            <span>${escapeHtml(item.global_enabled ? `Mirror ${item.global_status}` : "Mirror off")}</span>
          </div>
        </article>
      `;
      },
    )
    .join("");
  const pathEditorRows = data.path_rows
    .map(
      (item) => {
        const localTone = item.status === "BLOCKED" ? "bad" : "good";
        const globalTone = ["READY", "SYNCED", "LOCAL ONLY"].includes(item.global_status) ? "good" : item.global_status === "SYNCING" ? "warn" : "bad";
        const backupTools =
          item.key === "backups_dir"
            ? `
              <div class="diag-path-backup-tools">
                <small>Full backup captures live app-generated data from data, datasets, logs, reports, maintenance, state, config, development media, and app uploads.</small>
                <small>App-managed weekly backup: ${escapeHtml(data.full_backup_policy_label || "Runs inside the app")}${data.latest_full_backup ? ` · Latest full backup: ${escapeHtml(data.latest_full_backup.name)} (${escapeHtml(data.latest_full_backup.modified)})` : " · No full backup snapshot yet."}</small>
                <div class="diag-path-backup-actions">
                  <button class="action-btn action-secondary" type="button" id="diagnostics-full-backup-btn">Create full backup now</button>
                  <span class="diag-path-backup-stat">${Number(data.full_backup_count || 0)} full snapshot${Number(data.full_backup_count || 0) === 1 ? "" : "s"}</span>
                </div>
              </div>
            `
            : "";
        return `
        <label class="field-block diag-path-field ${item.key === "backups_dir" ? "is-backup" : ""}">
          <span>${escapeHtml(item.label || item.key)} · Local runtime</span>
          <input type="text" name="${escapeHtml(item.key)}" value="${escapeHtml(item.path)}" placeholder="${escapeHtml(item.default_path || "")}" />
          <small>${item.is_override ? `Override active. Default: ${escapeHtml(item.default_path || "")}` : `Default path. ${escapeHtml(item.kind === "dir" ? "Folder" : "File")} target.`}</small>
          <em class="diag-path-inline-state tone-${localTone}">${item.status} · ${escapeHtml(item.kind === "dir" ? "folder" : "file")}</em>
          <small>${escapeHtml(item.local_detail || "")}</small>
          <span class="diag-path-subhead">Global mirror (optional)</span>
          <input type="text" name="global__${escapeHtml(item.key)}" value="${escapeHtml(item.global_path || "")}" placeholder="Leave blank to keep this lane local only" />
          <small>${item.global_enabled ? escapeHtml(item.global_detail || "Global mirror configured.") : "If the global target is unavailable, the app still saves locally first and retries in the background."}</small>
          <em class="diag-path-inline-state tone-${globalTone}">${escapeHtml(item.global_status || "LOCAL ONLY")}${item.global_pending_count ? ` · ${item.global_pending_count} queued` : ""}</em>
          ${backupTools}
        </label>
      `;
      },
    )
    .join("");
  const schemaRows = data.schema_rows
    .map(
      (item) => `
        <article class="diag-row tone-${item.ok ? "good" : "bad"}">
          <div>
            <h3>${item.csv}</h3>
            <p>${item.missing_columns || "Schema is present"}</p>
          </div>
          <div class="diag-row-meta">
            <strong>${item.ok ? "OK" : "CHECK"}</strong>
            <span>${item.rows} rows</span>
          </div>
        </article>
      `,
    )
    .join("");

  return `
    <section class="page-panel diagnostics-page">
      <div>
        <div class="section-heading" ${titleBandStyle("title-photo-d.jpg", "58% center")}>
          <span>Data Diagnostics</span>
          <h2>Path and schema health</h2>
          <p>This rebuild version mirrors the real page’s core role: check filesystem readiness, CSV shape, backups, and report output availability.</p>
        </div>
        <section class="diag-hero-card tone-${data.overall_ok ? "good" : "warn"}">
          <div class="diag-hero-copy">
            <span>Overall diagnostics</span>
            <strong>${data.overall_label}</strong>
            <p>${data.overall_detail}</p>
          </div>
          <div class="diag-hero-score">
            <strong>${data.passed_checks}/${data.total_checks}</strong>
            <span>checks passed</span>
          </div>
        </section>
        <div class="metric-row">
          <div class="metric-pill tone-${data.overall_ok ? "good" : "warn"}"><span>Checks passed</span><strong>${data.passed_checks}</strong></div>
          <div class="metric-pill tone-good"><span>Ready paths</span><strong>${data.ready_count}</strong></div>
          <div class="metric-pill tone-info"><span>Path manager</span><strong>${data.tracked_count}</strong></div>
          <div class="metric-pill tone-info"><span>Global mirrors</span><strong>${data.global_mirror_count || 0}</strong></div>
          <div class="metric-pill tone-${Number(data.global_mirror_pending_count || 0) ? "warn" : "good"}"><span>Pending sync</span><strong>${data.global_mirror_pending_count || 0}</strong></div>
          <div class="metric-pill tone-${Number(data.global_mirror_issue_count || 0) ? "bad" : "good"}"><span>Global issues</span><strong>${data.global_mirror_issue_count || 0}</strong></div>
          <div class="metric-pill tone-info"><span>Dataset CSVs</span><strong>${data.dataset_count}</strong></div>
          <div class="metric-pill tone-info"><span>Log CSVs</span><strong>${data.log_count}</strong></div>
          <div class="metric-pill tone-warn"><span>Backup snapshots</span><strong>${data.backup_snapshots}</strong></div>
          <div class="metric-pill tone-info"><span>Report files</span><strong>${data.report_file_count}</strong></div>
        </div>
        ${collapsibleSection("Coverage summary", `<div class="diag-check-grid">${healthRows}</div>`, {
          kind: "list",
          meta: `${data.passed_checks}/${data.total_checks} ready`,
          tone: data.overall_ok ? "good" : "warn",
          open: true,
        })}
        ${collapsibleSection("Full path manager", `
          <div class="diag-path-editor-shell">
            <div class="micro-panel diag-path-editor-note">
              <strong>What to set</strong>: in the real deployment the shared global mirror is usually already set once for everyone. On each machine, the important part is the local runtime for that OS user.
              <br />
              <strong>How local works</strong>: the app takes the current OS user, enters that user’s <code>Documents</code> folder, and uses <code>documents-cache_tower</code> as the local runtime root. On Windows that means a path like <code>C:/Users/&lt;user&gt;/Documents/documents-cache_tower</code>. If the folder is missing, the app creates it automatically on first run, then adds the normal folders after it like <code>data</code>, <code>maintenance</code>, <code>logs</code>, <code>reports</code>, and <code>state</code>.
              <br />
              <strong>What to do on a new computer</strong>: 1. Open this page on that machine. 2. Check that the local runtime paths point to the correct local user area. 3. Click <code>Save path changes</code> only if you changed the local paths. Touch <code>Global mirror root</code> only when the shared deployment location itself has changed.
              <br />
              <strong>Use the per-path global fields only</strong> when one lane must mirror somewhere different from the normal shared Tower tree. Local runtime overrides stay per OS user, while the global mirror settings stay shared for the deployment.
            </div>
            <form id="diagnostics-path-form" class="diag-path-editor">
              <div class="diag-root-grid">
                <label class="field-block diag-root-field">
                  <span>Resolved local runtime root</span>
                  <input type="text" value="${escapeHtml(data.runtime_root || "")}" readonly />
                  <small>${escapeHtml(runtimeModeLabel)}. Auto local default on this machine: ${escapeHtml(data.default_local_root || "")}</small>
                </label>
                <label class="field-block diag-root-field">
                  <span>Global mirror root (optional)</span>
                  <input type="text" name="globalRoot" value="${escapeHtml(data.global_root || "")}" placeholder="Example: Z:\\TowerWork or /mnt/tower/Tower_work" />
                  <small>If set, matching runtime folders like <code>data</code>, <code>maintenance</code>, <code>logs</code>, <code>reports</code>, and <code>state</code> mirror under this one parent path automatically. This shared setting is common for everyone using the deployment.</small>
                </label>
              </div>
              <div class="diag-path-editor-grid">${pathEditorRows}</div>
              <div class="parts-form-actions diag-path-actions">
                <button class="action-btn action-primary" type="submit">Save path changes</button>
                <button class="action-btn action-secondary" type="button" id="diagnostics-path-reset-btn">Reset defaults</button>
              </div>
            </form>
            <div class="diag-list">${pathRows}</div>
          </div>
        `, {
          kind: "list",
          meta: data.override_count ? `${data.path_rows.length} live paths · ${data.override_count} custom` : `${data.path_rows.length} live paths`,
          tone: data.ready_count === data.tracked_count ? "good" : "warn",
          open: false,
        })}
      </div>
      <div>
        <div class="section-heading minimal">
          <span>CSV schema</span>
          <h3>Required structure checks</h3>
        </div>
        ${collapsibleSection("Schema checks", `<div class="diag-list">${schemaRows}</div>`, {
          kind: "list",
          meta: `${data.schema_rows.length} CSVs`,
          tone: data.schema_rows.every((item) => item.ok) ? "good" : "warn",
          open: true,
        })}
      </div>
    </section>
  `;
}

function bindDiagnosticsPage() {
  const form = document.getElementById("diagnostics-path-form");
  const resetButton = document.getElementById("diagnostics-path-reset-btn");
  const fullBackupButton = document.getElementById("diagnostics-full-backup-btn");
  if (!form) return;
  const actions = form.querySelector(".parts-form-actions");
  const clearError = () => {
    if (actions) delete actions.dataset.error;
  };
  Array.from(form.querySelectorAll("input")).forEach((input) => {
    input.addEventListener("input", clearError);
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    try {
      const payload = Object.fromEntries(new FormData(form).entries());
      const result = await postJson("/api/data-diagnostics/paths", payload);
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      if (actions) actions.dataset.error = error.message;
    }
  });
  resetButton?.addEventListener("click", async () => {
    const confirmed = window.confirm("Reset all local runtime paths and clear all global mirror paths back to the Tower defaults?");
    if (!confirmed) return;
    clearError();
    try {
      const result = await postJson("/api/data-diagnostics/paths", { resetDefaults: true });
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      if (actions) actions.dataset.error = error.message;
    }
  });
  fullBackupButton?.addEventListener("click", async () => {
    clearError();
    fullBackupButton.disabled = true;
    try {
      const result = await postJson("/api/data-diagnostics/full-backup", {});
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      if (actions) actions.dataset.error = error.message;
    } finally {
      fullBackupButton.disabled = false;
    }
  });
}

function exportFileRowsMarkup(files) {
  if (!files?.length) {
    return `<div class="micro-panel">No exports yet.</div>`;
  }
  return `
    <div class="micro-list export-list">
      ${files
        .map(
          (item) => `
            <div class="micro-row export-row">
              <div class="export-row-copy">
                <span>${item.name}</span>
                <strong>${item.modified}</strong>
              </div>
              <div class="export-row-actions">
                ${String(item.name || "").toLowerCase().endsWith(".md") ? `<button class="action-btn action-secondary export-row-btn" type="button" data-report-preview="${item.name}">Preview</button>` : ""}
                <a class="action-btn action-secondary export-row-btn" href="/api/report-center/file?name=${encodeURIComponent(item.name || "")}&mode=inline" target="_blank" rel="noopener noreferrer">Open file</a>
              </div>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function basenameSafe(path) {
  return String(path || "").split(/[\\/]/).pop() || String(path || "");
}

function renderMiniMarkdown(source) {
  const lines = String(source || "")
    .replace(/\r\n?/g, "\n")
    .split("\n");
  const blocks = [];
  let paragraph = [];
  let listType = "";
  let listItems = [];

  const renderMathInline = (expression) => {
    let html = escapeHtml(expression || "");
    html = html.replace(/([A-Za-z0-9)\]])\^([A-Za-z0-9+\-]+)/g, "$1<sup>$2</sup>");
    html = html.replace(/([A-Za-z0-9)\]])_([A-Za-z0-9+\-]+)/g, "$1<sub>$2</sub>");
    return `<span class="development-math-inline">${html}</span>`;
  };

  const renderInlineMarkdown = (text) => {
    const mathTokens = [];
    let prepared = String(text || "").replace(/\$([^$]+)\$/g, (_, expression) => {
      const token = `@@DEV_MATH_${mathTokens.length}@@`;
      mathTokens.push(renderMathInline(expression.trim()));
      return token;
    });
    let html = escapeHtml(prepared);
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    mathTokens.forEach((markup, index) => {
      html = html.replace(`@@DEV_MATH_${index}@@`, markup);
    });
    return html;
  };

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(`<p>${renderInlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  };

  const flushList = () => {
    if (!listType || !listItems.length) {
      listType = "";
      listItems = [];
      return;
    }
    blocks.push(`<${listType}>${listItems.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</${listType}>`);
    listType = "";
    listItems = [];
  };

  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushList();
      return;
    }

    const headingMatch = trimmed.match(/^(#{1,4})\s+(.*)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      const level = Math.min(headingMatch[1].length + 2, 6);
      blocks.push(`<h${level}>${renderInlineMarkdown(headingMatch[2])}</h${level}>`);
      return;
    }

    const orderedMatch = trimmed.match(/^\d+\.\s+(.*)$/);
    if (orderedMatch) {
      flushParagraph();
      if (listType && listType !== "ol") flushList();
      listType = "ol";
      listItems.push(orderedMatch[1]);
      return;
    }

    const bulletMatch = trimmed.match(/^[-*]\s+(.*)$/);
    if (bulletMatch) {
      flushParagraph();
      if (listType && listType !== "ul") flushList();
      listType = "ul";
      listItems.push(bulletMatch[1]);
      return;
    }

    const quoteMatch = trimmed.match(/^>\s?(.*)$/);
    if (quoteMatch) {
      flushParagraph();
      flushList();
      blocks.push(`<blockquote><p>${renderInlineMarkdown(quoteMatch[1])}</p></blockquote>`);
      return;
    }

    paragraph.push(trimmed);
  });

  flushParagraph();
  flushList();
  return blocks.join("");
}

function attachmentListMarkup(raw) {
  const items = String(raw || "")
    .split(";")
    .map((item) => sanitizeAttachmentPath(item))
    .filter(Boolean);
  if (!items.length) return "";
  const attachmentTypeLabel = (item) => {
    const lower = item.toLowerCase();
    if (/\.(png|jpg|jpeg|gif|webp|bmp)$/i.test(lower)) return "Image attachment";
    if (lower.endsWith(".pdf")) return "PDF document";
    if (lower.endsWith(".ipynb")) return "Notebook";
    if (lower.endsWith(".csv")) return "CSV dataset";
    if (/\.(doc|docx|txt|md)$/i.test(lower)) return "Document";
    return "Saved file";
  };
  const attachmentBadge = (item) => {
    const name = basenameSafe(item);
    const dotIndex = name.lastIndexOf(".");
    if (dotIndex < 0) return "FILE";
    return name.slice(dotIndex + 1).slice(0, 5).toUpperCase();
  };
  return `
    <div class="development-attachment-grid is-gallery">
      ${items
        .map((item) => {
          const safeItem = sanitizeAttachmentPath(item);
          const safeName = basenameSafe(safeItem);
          const href = `/api/development/media?path=${encodeURIComponent(safeItem)}`;
          const previewHref = `/api/development/media-preview?path=${encodeURIComponent(safeItem)}`;
          const lower = safeItem.toLowerCase();
          const isImage = /\.(png|jpg|jpeg|gif|webp|bmp)$/i.test(lower);
          const isPdf = lower.endsWith(".pdf");
          return `
            <div class="development-attachment-card ${isImage ? "is-image" : isPdf ? "is-pdf" : "is-doc"}">
              ${isImage ? `
                <a class="development-attachment-media development-attachment-thumb" href="${previewHref}" rel="noopener noreferrer">
                  <img src="${previewHref}" alt="${safeName}" loading="lazy" />
                </a>
              ` : isPdf ? `
                <a class="development-attachment-media development-attachment-pdf-media" href="${previewHref}" rel="noopener noreferrer">
                  <img
                    class="development-attachment-pdf-preview"
                    src="${previewHref}"
                    alt="${safeName}"
                    loading="lazy"
                  />
                  <div class="development-attachment-pdf-overlay">
                    <span class="development-attachment-badge">PDF</span>
                    <strong>Inline preview</strong>
                  </div>
                </a>
              ` : `
                <div class="development-attachment-doc-head">
                  <div class="development-attachment-badge">${attachmentBadge(item)}</div>
                </div>
              `}
              <div class="development-attachment-copy">
                <strong>${safeName}</strong>
                <span>${attachmentTypeLabel(safeItem)}</span>
              </div>
              <div class="development-attachment-actions">
                ${(isImage || isPdf) ? `<a class="action-btn action-secondary" href="${previewHref}" rel="noopener noreferrer">Preview</a>` : ""}
                <a class="action-btn action-secondary" href="${href}" rel="noopener noreferrer">Open file</a>
              </div>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function attachmentInlineLinksMarkup(raw) {
  const items = String(raw || "")
    .split(";")
    .map((item) => sanitizeAttachmentPath(item))
    .filter(Boolean);
  if (!items.length) return "";
  return `
    <div class="development-inline-attachments">
      ${items
        .slice(0, 8)
        .map(
          (item) =>
            `<a class="file-link development-inline-file" href="/api/development/media?path=${encodeURIComponent(item)}" rel="noopener noreferrer">${basenameSafe(item)}</a>`,
        )
        .join("")}
    </div>
  `;
}

function developmentFacetMarkup(label, value) {
  const text = String(value || "").trim();
  if (!text) return "";
  return `
    <div class="development-entry-facet">
      <span>${label}</span>
      <div class="development-entry-facet-copy">${renderMiniMarkdown(text)}</div>
    </div>
  `;
}

function developmentTimelineEntries(details) {
  const datedItems = [];
  let order = 0;
  (details.experiments || [])
    .slice()
    .reverse()
    .forEach((item) => {
      datedItems.push({
        kind: "experiment",
        order: order++,
        date: String(item.Date || "").trim(),
        item,
      });
    });
  (details.updates || []).forEach((item) => {
    datedItems.push({
      kind: "update",
      order: order++,
      date: String(item["Update Date"] || "").trim(),
      item,
    });
  });
  const summaryNotes = String(details?.project?.["Summary Notes"] || "").trim();
  const summaryDate = String(details?.project?.["Summary Date"] || "").trim();
  const summaryTitle = String(details?.project?.["Summary Title"] || "").trim();
  const summaryResearcher = String(details?.project?.["Summary Researcher"] || "").trim();
  if (details?.project?.["Project Name"] && (summaryNotes || summaryTitle || summaryDate || summaryResearcher)) {
    datedItems.push({
      kind: "summary",
      order: order++,
      date: summaryDate || String(details.latest_update || "").trim(),
      item: {
        title: summaryTitle || "Project summary",
        status: details.archived ? "Archived" : "Active",
        drawings: details.drawing_experiment_count || 0,
        researchers: (details.researchers || []).join(", ") || "Not listed",
        target: details.project.Target || "Not set",
        notes: summaryNotes,
        researcher: summaryResearcher,
        latestActivity:
          summaryDate
          || (datedItems.length && datedItems[datedItems.length - 1].date)
          || String(details.latest_update || "").trim()
          || "No activity yet",
      },
    });
  }
  return datedItems.sort((left, right) => {
    const leftDate = left.date || "9999-99-99";
    const rightDate = right.date || "9999-99-99";
    if (leftDate !== rightDate) return leftDate < rightDate ? -1 : 1;
    return left.order - right.order;
  });
}

function developmentTimelineItemMarkup(entry, index) {
  const item = entry.item || {};
  const dateLabel = escapeHtml(entry.date || "No date");
  const nodeLabelMap = { experiment: "EX", update: "UP", summary: "SM" };
  const isDrawing = entry.kind === "experiment" && String(item["Is Drawing"] || "").trim().toLowerCase() === "true";
  const nodeLabel = isDrawing ? "DR" : nodeLabelMap[entry.kind] || String(index + 1).padStart(2, "0");
  const actionLabel =
    entry.kind === "summary"
      ? "Summary"
      : entry.kind === "update"
        ? "Update"
        : isDrawing
          ? "Draw experiment"
          : "Experiment";
  const summaryTitle =
    entry.kind === "summary"
      ? `${actionLabel} - ${item.title || "Project"}`
      : `${actionLabel} - ${entry.kind === "update" ? String(item["Experiment Title"] || "").trim() || "Quick update" : String(item["Experiment Title"] || "").trim() || "Untitled experiment"}`;

  if (entry.kind === "summary") {
    const summaryFacets = [
      developmentFacetMarkup("Status", item.status),
      developmentFacetMarkup("Draws", String(item.drawings || 0)),
      developmentFacetMarkup("Researchers", item.researchers),
      developmentFacetMarkup("Target", item.target),
      developmentFacetMarkup("Latest activity", item.latestActivity),
      developmentFacetMarkup("Summary author", item.researcher),
    ]
      .filter(Boolean)
      .join("");
    return `
      <article class="development-timeline-item is-summary">
        <div class="development-timeline-rail">
          <span class="development-timeline-node">${nodeLabel}</span>
        </div>
        <details class="development-timeline-card development-timeline-fold">
          <summary class="development-timeline-summary">
            <div class="development-timeline-summary-copy">
              <span class="development-entry-kind">${actionLabel}</span>
              <strong>${escapeHtml(summaryTitle)}</strong>
            </div>
            <div class="development-entry-meta">${dateLabel}${item.researcher ? ` · ${escapeHtml(item.researcher)}` : ""}</div>
          </summary>
          <div class="development-timeline-body">
            ${summaryFacets ? `<div class="development-entry-grid">${summaryFacets}</div>` : ""}
            ${item.notes ? `<div class="development-note-markdown development-entry-markdown">${renderMiniMarkdown(item.notes)}</div>` : `<p class="development-entry-summary">No project summary was written yet.</p>`}
          </div>
        </details>
      </article>
    `;
  }

  if (entry.kind === "update") {
    const updateTitle = String(item["Experiment Title"] || "").trim() || "Project update";
    const researcher = String(item.Researcher || "").trim();
    return `
      <article class="development-timeline-item is-update">
        <div class="development-timeline-rail">
          <span class="development-timeline-node">${nodeLabel}</span>
        </div>
        <details class="development-timeline-card development-timeline-fold">
          <summary class="development-timeline-summary">
            <div class="development-timeline-summary-copy">
              <span class="development-entry-kind">${actionLabel}</span>
              <strong>${escapeHtml(`${actionLabel} - ${updateTitle}`)}</strong>
            </div>
            <div class="development-entry-meta">${dateLabel}${researcher ? ` · ${escapeHtml(researcher)}` : ""}</div>
          </summary>
          <div class="development-timeline-body">
            <div class="development-note-markdown development-entry-markdown">${renderMiniMarkdown(item["Update Notes"] || "No update notes saved.")}</div>
          </div>
        </details>
      </article>
    `;
  }

  const title = String(item["Experiment Title"] || "").trim() || "Untitled experiment";
  const researcher = String(item.Researcher || "").trim();
  const notes = String(item["Markdown Notes"] || "").trim();
  const drawCsv = String(item["Draw CSV"] || "").trim();
  const drawingDetails = String(item["Drawing Details"] || "").trim();
  const facets = [
    developmentFacetMarkup("Purpose", item.Purpose),
    developmentFacetMarkup("Methods", item.Methods),
    developmentFacetMarkup("Observations", item.Observations),
    developmentFacetMarkup("Results", item.Results),
  ]
    .filter(Boolean)
    .join("");
  return `
    <article class="development-timeline-item is-experiment">
      <div class="development-timeline-rail">
        <span class="development-timeline-node">${nodeLabel}</span>
      </div>
      <details class="development-timeline-card development-timeline-fold">
        <summary class="development-timeline-summary">
          <div class="development-timeline-summary-copy">
            <span class="development-entry-kind">${actionLabel}</span>
            <strong>${escapeHtml(summaryTitle)}</strong>
          </div>
          <div class="development-entry-meta">${dateLabel}${researcher ? ` · ${escapeHtml(researcher)}` : ""}</div>
        </summary>
        <div class="development-timeline-body">
          ${facets ? `<div class="development-entry-grid">${facets}</div>` : `<p class="development-entry-summary">No experiment detail was written yet.</p>`}
          ${isDrawing ? `
            <div class="development-entry-linkage">
              <span>Linked draw</span>
              <strong>${escapeHtml(drawCsv || "Manual drawing note")}</strong>
              ${drawingDetails ? `<em>${escapeHtml(drawingDetails)}</em>` : ""}
            </div>
          ` : ""}
          ${notes ? `<div class="development-note-markdown development-entry-markdown">${renderMiniMarkdown(notes)}</div>` : ""}
          ${attachmentListMarkup(item.Attachments || "")}
        </div>
      </details>
    </article>
  `;
}

function reportProjectDetailMarkup(details) {
  if (!details?.project) {
    return `<div class="micro-panel">Choose a project to load the development summary.</div>`;
  }
  const projectName = details.project["Project Name"] || "Untitled project";
  const archivedTone = details.archived ? "tone-warn" : "tone-good";
  const archivedLabel = details.archived ? "Archived" : "Active";
  const timeline = developmentTimelineEntries(details);
  const latestActivity = timeline.length ? timeline[timeline.length - 1].date || "Pending" : "No activity yet";
  return `
    <div class="report-project-detail development-project-detail-shell">
      <div class="metric-row compact">
        <div class="metric-pill tone-info"><span>Experiments</span><strong>${details.experiment_count}</strong></div>
        <div class="metric-pill tone-warn"><span>Updates</span><strong>${details.update_count}</strong></div>
        <div class="metric-pill tone-info"><span>Drawing runs</span><strong>${details.drawing_experiment_count || 0}</strong></div>
        <div class="metric-pill ${archivedTone}"><span>Status</span><strong>${archivedLabel}</strong></div>
      </div>
      <div class="development-project-stage">
        <div class="micro-panel blocky development-project-hero">
          <span>Project description</span>
          <strong>${projectName}</strong>
          <div class="development-note-markdown development-project-purpose">${renderMiniMarkdown(details.project["Project Purpose"] || "No project description saved yet.")}</div>
          <div class="development-project-target">
            <span>Target</span>
            <strong>${details.project.Target || "Not set"}</strong>
          </div>
        </div>
        <div class="development-project-facts-row development-project-stage-metrics">
          <div class="development-fact-card">
            <span>Latest activity</span>
            <strong>${latestActivity}</strong>
          </div>
          <div class="development-fact-card">
            <span>Researchers</span>
            <strong>${details.researchers?.join(", ") || "Not listed"}</strong>
          </div>
          <div class="development-fact-card">
            <span>Status</span>
            <strong>${archivedLabel}</strong>
          </div>
        </div>
      </div>
      <section class="chart-card development-progress-board">
        <div class="chart-head">
          <span>Project progress</span>
          <strong>Append lab work in one timeline</strong>
        </div>
        ${timeline.length
          ? `<div class="development-timeline">${timeline.map((entry, index) => developmentTimelineItemMarkup(entry, index)).join("")}</div>`
          : `
            <div class="micro-panel blocky development-project-latest">
              <span>Project timeline</span>
              <strong>No experiments or updates yet</strong>
              <p>Create the first experiment or add a quick update to start the project story.</p>
            </div>
          `}
      </section>
    </div>
  `;
}

async function renderReportCenterPage(data) {
  const reportModes = (data.modes || []).filter((mode) => mode !== "Development Process");
  return `
    <section class="page-panel report-center-page" id="report-center-page">
      <div class="section-heading" ${titleBandStyle("title-photo-a.jpg", "34% center")}>
        <span>Report Center</span>
        <h2>Export workspace</h2>
        <p>Build and save clean operations exports here, then review the recent handoff files already written into the report center.</p>
      </div>
      <div class="sql-help-band sql-help-band-main">
        <span>Export flow</span>
        <strong>Build the report window, keep only what matters, and save clean handoff documents into the real report center without leaving the rebuild.</strong>
      </div>
      <div class="report-mode-strip">
        ${reportModes
          .map(
            (mode, index) => `<button class="report-mode-btn ${index === 0 ? "is-active" : ""}" type="button" data-report-mode="${mode}">${mode}</button>`,
          )
          .join("")}
      </div>
      <div class="report-mode-panel is-active" data-report-panel="Operations Report">
        <div class="report-workspace">
          <section class="report-main-panel report-main-panel-wide">
            <div class="section-heading minimal">
              <span>Operations Report</span>
              <h3>Build an export window</h3>
              <p>Choose the time window, keep only the sections you want, and save a markdown handover export in the real report center folder.</p>
            </div>
            <form id="report-operations-form" class="stack-form">
              <div class="field-grid field-grid-3">
                <label class="field-block">
                  <span>Report title</span>
                  <input type="text" name="title" value="Tower Operations Report" />
                </label>
                <label class="field-block">
                  <span>Start date</span>
                  <input type="date" name="startDate" value="${todayIsoDate()}" />
                </label>
                <label class="field-block">
                  <span>End date</span>
                  <input type="date" name="endDate" value="${todayIsoDate()}" />
                </label>
              </div>
              <label class="field-block">
                <span>Export filename</span>
                <input type="text" name="filename" value="operations_report_${todayIsoDate()}.md" />
              </label>
              <div class="report-section-grid">
                ${data.sections
                  .map(
                    (section) => `
                      <label class="check-tile">
                        <input type="checkbox" name="sections" value="${section}" checked />
                        <span>${section}</span>
                      </label>
                    `,
                  )
                  .join("")}
              </div>
              <div class="order-builder-actions">
                <button class="action-btn action-primary" type="submit">Generate Operations Export</button>
              </div>
            </form>
          </section>
        </div>
      </div>
      <div class="report-mode-panel" data-report-panel="Recent Exports">
        <div class="report-export-grid report-export-grid-single">
          <section class="chart-card">
            <div class="chart-head">
              <span>Recent exports</span>
              <strong>Rebuild output</strong>
            </div>
            ${exportFileRowsMarkup(data.recent_md_exports)}
          </section>
        </div>
        <section class="chart-card" id="report-markdown-preview-card" hidden>
          <div class="chart-head">
            <span>Markdown preview</span>
            <strong id="report-markdown-preview-title">Selected export</strong>
          </div>
          <div id="report-markdown-preview-root" class="development-note-markdown"></div>
        </section>
      </div>
    </section>
  `;
}

function sqlPreviewRowsMarkup(rows) {
  if (!rows?.length) {
    return `<div class="micro-panel">No dataset rows in view.</div>`;
  }
  return `
    <div class="sql-preview-table">
      <div class="sql-preview-head">
        <span>Parameter</span><span>Value</span><span>Units</span>
      </div>
      ${rows
        .map(
          (item) => `
            <div class="sql-preview-row">
              <span>${item.parameter_name}</span>
              <strong>${item.value || "—"}</strong>
              <em>${item.units || "—"}</em>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function sqlConditionRowsMarkup(conditions) {
  if (!conditions?.length) {
    return `<div class="micro-panel">No conditions added yet.</div>`;
  }
  return `
    <div class="micro-list">
      ${conditions
        .map(
          (item, index) => `
            <div class="micro-row blocky ${sqlConditionToneClass(item)}">
              <span>${index === 0 ? "Base rule" : item.joiner || "AND"}</span>
              <strong>${item.groupName || `${item.params.length} parameter group`}</strong>
              <em>${item.human}</em>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function sqlConditionToneClass(item) {
  if (item?.negate) return "sql-condition-tone-bad";
  if (item?.op === "between") return "sql-condition-tone-warn";
  if (item?.op === "contains") return "sql-condition-tone-violet";
  if (["=", "!=", ">", ">=", "<", "<="].includes(item?.op)) return "sql-condition-tone-good";
  return "sql-condition-tone-info";
}

function sqlConditionOperatorLabel(item) {
  const operatorMap = {
    any: "Any",
    "=": "Equals",
    "!=": "Not equal",
    ">": "Above",
    ">=": "At least",
    "<": "Below",
    "<=": "At most",
    between: "Between",
    contains: "Contains",
  };
  return operatorMap[item?.op] || "Rule";
}

function sqlFilterRibbonMarkup(conditions) {
  if (!conditions?.length) {
    return `<div class="micro-panel">No filter set yet. Build one grouped rule and it will stay visible here while you move across the steps.</div>`;
  }
  return `
    <div class="sql-filter-ribbon-list">
      ${conditions
        .map(
          (item, index) => `
            <button class="sql-filter-ribbon-chip ${sqlConditionToneClass(item)}" type="button" data-sql-filter-condition="${index}">
              <span>${index === 0 ? "Base" : item.joiner || "AND"} · ${sqlConditionOperatorLabel(item)}</span>
              <strong>${item.groupName || `${item.params.length} parameter group`}</strong>
              <em>${item.params.length} params · ${item.human}</em>
            </button>
          `,
        )
        .join("")}
    </div>
  `;
}

function sqlToggleTileMarkup({ id, title, copy = "", checked = false }) {
  return `
    <label class="sql-toggle-tile">
      <input type="checkbox" id="${id}" ${checked ? "checked" : ""} />
      <div class="sql-toggle-copy">
        <span>${title}</span>
        ${copy ? `<strong>${copy}</strong>` : ``}
      </div>
    </label>
  `;
}

function sqlMatchedDrawsMarkup(rows) {
  if (!rows?.length) {
    return `<div class="micro-panel">No matched draws yet.</div>`;
  }
  return `
    <div class="micro-list">
      ${rows
        .map(
          (item) => `
            <div class="micro-row blocky">
              <span>${item.event_ts || "No time"}</span>
              <strong>${item._draw}</strong>
              <em>${item.filename || ""}</em>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function sqlEventRowsMarkup(rows, kind = "events") {
  if (!rows?.length) {
    return `<div class="micro-panel">No ${kind} in scope.</div>`;
  }
  return `
    <div class="micro-list">
      ${rows
        .map(
          (item) => `
            <div class="micro-row blocky">
              <span>${item.event_ts || "No time"}</span>
              <strong>${item.title || item.component || "Event"}</strong>
              <em>${item.component || ""}${item.severity ? ` · ${item.severity}` : ""}${item.note ? ` · ${item.note}` : item.description ? ` · ${item.description}` : ""}</em>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function sqlResultTableMarkup(result) {
  if (!result?.columns?.length) {
    return `<div class="micro-panel">Run a query to inspect matching rows here.</div>`;
  }
  return `
    <div class="sql-result-shell">
      <div class="sql-result-meta">Rows returned: ${result.row_count}</div>
      <div class="sql-result-table-wrap">
        <table class="sql-result-table">
          <thead>
            <tr>${result.columns.map((column) => `<th>${column}</th>`).join("")}</tr>
          </thead>
          <tbody>
            ${result.rows
              .map(
                (row) => `
                  <tr>${result.columns.map((column) => `<td>${row[column] ?? ""}</td>`).join("")}</tr>
                `,
              )
              .join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function sqlInterpretationMarkup(result) {
  if (!result?.summary) {
    return `<div class="micro-panel">Run a filter to get an interpreted read of the draw scope and event overlap.</div>`;
  }
  const summary = result.summary;
  return `
    <div class="micro-panel blocky">
      <strong>Result reading</strong>
      <p>${summary.matched_draws ? `${summary.matched_draws} draw files matched.` : `No draw files matched.`}</p>
      <p>${summary.matched_values ? `${summary.matched_values} matching values were found inside those draws.` : `No values matched the current rule.`}</p>
      <p>${summary.maintenance_events ? `${summary.maintenance_events} maintenance events overlap the chosen time scope.` : `No maintenance overlap in the chosen scope.`}</p>
      <p>${summary.fault_events ? `${summary.fault_events} fault events overlap the chosen time scope.` : `No fault overlap in the chosen scope.`}</p>
    </div>
  `;
}

function titleBandStyle(photoFile, position = "center center") {
  return `style="--title-photo-url:url('/assets/${photoFile}'); --title-photo-pos:${position};"`;
}

function aggregateValues(values, mode = "avg") {
  const nums = (values || []).map((item) => Number(item)).filter((item) => Number.isFinite(item));
  if (!nums.length) return null;
  if (mode === "min") return Math.min(...nums);
  if (mode === "max") return Math.max(...nums);
  if (mode === "median") {
    const sorted = [...nums].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  }
  return nums.reduce((sum, value) => sum + value, 0) / nums.length;
}

async function renderSqlLabPage(data) {
  return `
    <section class="page-panel sql-lab-page" id="sql-lab-page">
      <div class="section-heading" ${titleBandStyle("title-photo-c.jpg", "42% center")}>
        <span>SQL Lab</span>
        <h2>Condition studio</h2>
        <p>Build grouped parameter conditions, scope the run, and inspect matched Draws, Maintenance, and Faults from one SQL workflow.</p>
      </div>
      <div class="sql-help-band sql-help-band-main">
        <span>Recommended flow</span>
        <strong>Pick a parameter group, define one clear rule, then run it against Draws first. Add Maintenance and Faults only when you want event context.</strong>
      </div>
      <div class="sql-step-strip">
        <button class="report-mode-btn sql-step-btn is-active" type="button" data-sql-step="1" title="Step 1 · Group / Parameters">Step 1 · Parameters</button>
        <button class="report-mode-btn sql-step-btn" type="button" data-sql-step="2" title="Step 2 · Scope + Filter">Step 2 · Scope + Filter</button>
        <button class="report-mode-btn sql-step-btn" type="button" data-sql-step="3" title="Step 3 · Inspect Results">Step 3 · Results</button>
      </div>
      <div class="sql-lab-layout sql-lab-layout-deep">
        <section class="sql-lab-main">
          <div class="chart-card sql-query-card sql-step-panel is-active" data-sql-step-panel="1">
            <div class="sql-panel-intro sql-panel-intro-compact">
              <span>Step 1 · Parameter group</span>
              <strong>Build the parameter set</strong>
              <p>Start broad, then narrow. Search by words like "zone", "tension", or "furnace", then select the parameters you want checked together.</p>
            </div>
            <section class="sql-subsection sql-subsection-plain">
              <div class="field-grid sql-step1-scope-grid">
                <label class="field-block">
                  <span>Parameter search</span>
                  <input type="text" id="sql-filter-input" placeholder="zone avg diameter / tension / furnace..." />
                </label>
                <label class="field-block">
                  <span>Family</span>
                  <select id="sql-family-filter">
                    <option value="All">All</option>
                    <option value="Zones">Zones</option>
                    <option value="Order">Order</option>
                    <option value="Process">Process</option>
                    <option value="Winder + T&M">Winder + T&M</option>
                    <option value="General">General</option>
                  </select>
                </label>
              </div>
            </section>
            <section class="sql-subsection">
              <div class="sql-subsection-head">
                <span>Metric mode</span>
                <strong>Trim the list to the metric family you want to compare</strong>
              </div>
              <div class="sql-quick-row">
                ${sqlToggleTileMarkup({ id: "sql-only-avg", title: "Only Avg", copy: "Average metrics only" })}
                ${sqlToggleTileMarkup({ id: "sql-only-min", title: "Only Min", copy: "Minimum metrics only" })}
                ${sqlToggleTileMarkup({ id: "sql-only-max", title: "Only Max", copy: "Maximum metrics only" })}
              </div>
            </section>
            <section class="sql-subsection">
              <div class="sql-subsection-head">
                <span>Matched parameters</span>
                <strong>Pick directly from the filtered parameter board</strong>
              </div>
              <div class="sql-match-panel sql-match-panel-wide">
                <div class="sql-match-toolbar">
                  <div class="sql-match-copy">
                    <div class="sql-match-head">Available matched parameters</div>
                    <div id="sql-selection-summary" class="sql-selection-caption">Choose one or more parameters to build a group.</div>
                  </div>
                  <div class="sql-match-toolbar-side">
                    <strong id="sql-selection-count" class="sql-selection-count">0 selected</strong>
                    <div class="order-builder-actions sql-match-actions">
                      <button class="action-btn action-secondary" type="button" id="sql-use-all-filtered">Use all filtered</button>
                      <button class="action-btn action-secondary" type="button" id="sql-clear-selection">Clear selection</button>
                    </div>
                  </div>
                </div>
                <div id="sql-match-scroll" class="sql-match-scroll sql-match-scroll-wide"></div>
              </div>
            </section>
          </div>

          <div class="chart-card sql-query-card sql-step-panel" data-sql-step-panel="2">
            <div class="chart-head">
              <span>Scope + filter</span>
              <strong>Define the rule, included timelines, and run the filter</strong>
            </div>
            <div class="sql-help-band">
              <span>Step 2 help</span>
              <strong>Use <code>contains</code> for text, <code>between</code> for ranges, then stack the conditions and run the filter from this same step.</strong>
            </div>
            <section class="sql-subsection">
              <div class="sql-subsection-head">
                <span>Rule</span>
                <strong>Set the comparison logic for the selected group</strong>
              </div>
              <div class="field-grid field-grid-3 sql-rule-grid is-single-value" id="sql-rule-grid">
                <label class="field-block">
                  <span>Operator</span>
                  <select id="sql-operator-select">
                    ${data.operators.map((item) => `<option value="${item}">${item}</option>`).join("")}
                  </select>
                </label>
                <label class="field-block">
                  <span>Value</span>
                  <input type="text" id="sql-value-1" placeholder="42 / text / threshold..." />
                </label>
                <label class="field-block" id="sql-value-2-block" hidden>
                  <span>Second value</span>
                  <input type="text" id="sql-value-2" placeholder="between upper bound" />
                </label>
              </div>
              <div class="field-grid field-grid-2 sql-rule-join-grid">
                <label class="field-block">
                  <span>Join</span>
                  <select id="sql-joiner-select">
                    <option value="AND">AND</option>
                    <option value="OR">OR</option>
                  </select>
                </label>
                <label class="sql-inline-toggle sql-inline-toggle-compact">
                  <input type="checkbox" id="sql-negate-toggle" />
                  <span>NOT</span>
                  <em>Flip the selected rule</em>
                </label>
              </div>
            </section>
            <section class="sql-subsection">
              <div class="sql-subsection-head">
                <span>Time window</span>
                <strong>Limit the draw universe before event correlation</strong>
              </div>
              <div class="sql-scope-grid">
                ${sqlToggleTileMarkup({ id: "sql-time-enabled", title: "Time filter", copy: "Limit by date range" })}
                <label class="field-block">
                  <span>From</span>
                  <input type="date" id="sql-time-from" />
                </label>
                <label class="field-block">
                  <span>To</span>
                  <input type="date" id="sql-time-to" />
                </label>
              </div>
            </section>
            <section class="sql-subsection">
              <div class="sql-subsection-head">
                <span>Included lanes</span>
                <strong>Choose which result streams should respond to this run</strong>
              </div>
              <div class="sql-include-strip">
                ${sqlToggleTileMarkup({ id: "sql-include-draws", title: "Draws", copy: "Main filtered draw universe", checked: true })}
                ${sqlToggleTileMarkup({ id: "sql-include-maintenance", title: "Maintenance", copy: "Overlay service actions" })}
                ${sqlToggleTileMarkup({ id: "sql-include-faults", title: "Faults", copy: "Overlay fault events" })}
              </div>
              <div class="field-grid field-grid-2">
                <label class="field-block">
                  <span>Event scope</span>
                  <select id="sql-event-scope">
                    ${data.event_scope_modes.map((item) => `<option value="${item}">${item}</option>`).join("")}
                  </select>
                </label>
                <div class="sql-sub-note">Use matched draws window for the closest behavior to the real app.</div>
              </div>
            </section>
            <div id="sql-maintenance-filters-shell" hidden>
              ${collapsibleSection("Maintenance filters", `
                <div class="sql-optional-filter-body">
                  <div class="sql-subsection-head">
                    <span>Maintenance lane</span>
                    <strong>Narrow service actions only when you need extra context</strong>
                  </div>
                  <div class="field-grid field-grid-2">
                    <label class="field-block">
                      <span>Maintenance text contains</span>
                      <input type="text" id="sql-maintenance-text" placeholder="task / note / source file" />
                    </label>
                    <label class="field-block">
                      <span>Maintenance component</span>
                      <select id="sql-maintenance-component">
                        <option value="">All</option>
                        ${data.maintenance_components.map((item) => `<option value="${item}">${item}</option>`).join("")}
                      </select>
                    </label>
                  </div>
                </div>
              `, { kind: "workspace", tone: "warn", open: false, meta: "lane" })}
            </div>
            <div id="sql-fault-filters-shell" hidden>
              ${collapsibleSection("Fault filters", `
                <div class="sql-optional-filter-body">
                  <div class="sql-subsection-head">
                    <span>Fault lane</span>
                    <strong>Use severity and component filters only when troubleshooting</strong>
                  </div>
                  <div class="field-grid field-grid-3">
                    <label class="field-block">
                      <span>Fault text contains</span>
                      <input type="text" id="sql-fault-text" placeholder="title / description / source file" />
                    </label>
                    <label class="field-block">
                      <span>Fault component</span>
                      <select id="sql-fault-component">
                        <option value="">All</option>
                        ${data.fault_components.map((item) => `<option value="${item}">${item}</option>`).join("")}
                      </select>
                    </label>
                    <label class="field-block">
                      <span>Fault severity</span>
                      <select id="sql-fault-severity">
                        <option value="">All</option>
                        <option value="low">low</option>
                        <option value="medium">medium</option>
                        <option value="high">high</option>
                        <option value="critical">critical</option>
                      </select>
                    </label>
                  </div>
                </div>
              `, { kind: "workspace", tone: "bad", open: false, meta: "lane" })}
            </div>
            <section class="sql-subsection">
              <div class="sql-subsection-head">
                <span>Condition stack</span>
                <strong>Assemble the filter logic before running</strong>
              </div>
              <div class="order-builder-actions">
                <button class="action-btn action-secondary" type="button" id="sql-add-group-condition">Add selected parameters as condition</button>
                <button class="action-btn action-secondary" type="button" id="sql-remove-last-condition">Remove last</button>
                <button class="action-btn action-secondary" type="button" id="sql-clear-conditions">Clear</button>
                <button class="action-btn action-primary" type="button" id="sql-run-filter-btn">Run filter</button>
              </div>
              <div id="sql-conditions-root">${sqlConditionRowsMarkup([])}</div>
            </section>
          </div>
        </section>
        <aside class="sql-lab-side">
          ${collapsibleSection("Run summary", `
          <div class="chart-card chart-card-nested sql-run-summary-card">
            <div class="chart-head">
              <span>Run summary</span>
              <strong>Live build and counters</strong>
            </div>
            <div id="sql-run-draft-root" class="sql-run-draft-root"></div>
            <div id="sql-filter-summary-root" class="sql-filter-ribbon-root">${sqlFilterRibbonMarkup([])}</div>
            <div id="sql-run-summary-root" class="metric-row compact"></div>
            <div id="sql-interpretation-root">${sqlInterpretationMarkup(null)}</div>
          </div>`, { kind: "workspace", tone: "good", open: true })}
        </aside>
      </div>
      <div class="chart-card sql-query-card sql-step-panel" data-sql-step-panel="3">
        <div class="chart-head">
          <span>Inspect results</span>
          <strong>Read the matched rows, events, and plots from one lane</strong>
        </div>
        <div class="sql-help-band">
          <span>Step 3 help</span>
          <strong>Read the live command summary in Run summary first, then inspect matched draws and values. Open analysis or math only when you want trend comparison.</strong>
        </div>
        ${collapsibleSection("Analysis studio", `
        <div id="sql-analysis-hero" class="sql-analysis-hero">
        <div class="order-builder-actions sql-analysis-actions">
          <button class="action-btn action-secondary" type="button" id="sql-plot-all-matched">Set plot = all matched params</button>
          <button class="action-btn action-secondary" type="button" id="sql-plot-clear">Clear plot selection</button>
          <button class="action-btn action-secondary" type="button" id="sql-plot-restore-hidden" disabled>Restore hidden outliers</button>
          <label class="field-block sql-analysis-reducer">
            <span>Group reducer</span>
            <select id="sql-analysis-reducer">
              <option value="avg">Average</option>
              <option value="median">Median</option>
              <option value="min">Minimum</option>
              <option value="max">Maximum</option>
            </select>
          </label>
        </div>
        <div class="sql-analysis-resource-strip">
          <button class="parts-filter-chip is-active" type="button" data-sql-analysis-source="filter">Use filter-hit values</button>
          <button class="parts-filter-chip" type="button" data-sql-analysis-source="draws">Use all rows from matched draws</button>
        </div>
        <div class="sql-analysis-browser">
          <label class="field-block sql-analysis-search">
            <span>Plot search</span>
            <input id="sql-analysis-search" type="text" placeholder="Search matched draw parameters before showing the plot board..." />
          </label>
          <div id="sql-analysis-search-note" class="sql-analysis-search-note">Ready to browse grouped parameters.</div>
        </div>
        <div class="sql-analysis-hero-top">
          <div id="sql-analysis-series-root" class="token-list"></div>
          <div id="sql-analysis-math-root" class="metric-row compact"></div>
        </div>
        <div id="sql-analysis-hover-root" class="micro-panel sql-analysis-hover">Hover a point to inspect the draw, parameter, and value.</div>
        <div class="sql-analysis-shell sql-analysis-shell-dominant">
          <canvas id="sql-analysis-canvas" class="sql-analysis-canvas sql-analysis-canvas-large"></canvas>
          <div id="sql-analysis-tooltip" class="sql-analysis-tooltip"></div>
        </div>
        <div id="sql-analysis-detail-root" class="sql-analysis-detail-root">
          <div class="micro-panel">Click a point or event to inspect the related draw and CSV rows here.</div>
        </div>
        </div>
      `, { kind: "workspace", meta: "grouped parameter plot", tone: "info", open: false })}
        ${collapsibleSection("Math lab", `
        <div id="sql-math-lab" class="sql-math-lab">
          <div class="sql-help-band sql-help-band-soft">
            <span>Math workflow</span>
            <strong>Choose one or two grouped traces, then build a derived signal like spread, ratio, rolling average, delta, or a custom <code>f(A,B)</code> formula. Click the derived curve to inspect the related draw below.</strong>
          </div>
          <div class="field-grid field-grid-4 sql-math-controls">
            <label class="field-block">
              <span>Source A</span>
              <select id="sql-math-source-a"></select>
            </label>
            <label class="field-block">
              <span>Source B</span>
              <select id="sql-math-source-b"></select>
            </label>
            <label class="field-block">
              <span>Math mode</span>
              <select id="sql-math-operation">
                <option value="identity">Source A</option>
                <option value="delta_prev">Delta vs previous</option>
                <option value="rolling_avg">Rolling average</option>
                <option value="spread_ab">A - B spread</option>
                <option value="ratio_ab">A / B ratio</option>
                <option value="percent_ab">A vs B %</option>
                <option value="normalize">Normalize A</option>
                <option value="zscore">Z-score A</option>
                <option value="custom_ab">Custom f(A,B)</option>
              </select>
            </label>
            <label class="field-block">
              <span>Formula f(A,B)</span>
              <input id="sql-math-expression" type="text" value="A" placeholder="np.sqrt(np.abs(A-B))" />
            </label>
          </div>
          <div class="sql-math-formula-note">
            <span>NumPy-style examples</span>
            <button class="parts-filter-chip" type="button" data-sql-math-expression-example="np.sqrt(np.abs(A-B))">np.sqrt(np.abs(A-B))</button>
            <button class="parts-filter-chip" type="button" data-sql-math-expression-example="np.power(A,2)">np.power(A,2)</button>
            <button class="parts-filter-chip" type="button" data-sql-math-expression-example="np.log(np.abs(A)+1)">np.log(np.abs(A)+1)</button>
            <button class="parts-filter-chip" type="button" data-sql-math-expression-example="np.maximum(A,B)-np.minimum(A,B)">np.maximum(A,B)-np.minimum(A,B)</button>
            <button class="parts-filter-chip" type="button" data-sql-math-expression-example="np.exp((A-B)/100)">np.exp((A-B)/100)</button>
            <em>Supports np.abs, np.sqrt, np.power, np.log, np.exp, np.minimum, np.maximum. Rolling avg uses a fixed 5-point window.</em>
          </div>
          <div class="token-strip sql-math-preset-strip" id="sql-math-presets">
            <button class="parts-filter-chip" type="button" data-sql-math-preset="identity">Use A</button>
            <button class="parts-filter-chip" type="button" data-sql-math-preset="delta_prev">Delta</button>
            <button class="parts-filter-chip" type="button" data-sql-math-preset="rolling_avg">Rolling avg</button>
            <button class="parts-filter-chip" type="button" data-sql-math-preset="spread_ab">A - B</button>
            <button class="parts-filter-chip" type="button" data-sql-math-preset="ratio_ab">A / B</button>
            <button class="parts-filter-chip" type="button" data-sql-math-preset="percent_ab">A vs B %</button>
            <button class="parts-filter-chip" type="button" data-sql-math-preset="normalize">Normalize</button>
            <button class="parts-filter-chip" type="button" data-sql-math-preset="zscore">Z-score</button>
            <button class="parts-filter-chip" type="button" data-sql-math-preset="custom_ab">Custom f(A,B)</button>
          </div>
          <div class="order-builder-actions sql-math-actions">
            <button class="action-btn action-secondary" type="button" id="sql-math-save-recipe">Add current recipe</button>
            <button class="action-btn action-secondary" type="button" id="sql-math-clear-recipes">Clear saved recipes</button>
          </div>
          <div id="sql-math-recipes-root" class="sql-math-recipes-root"></div>
          <div id="sql-math-summary-root" class="metric-row compact"></div>
          <div id="sql-math-hover-root" class="micro-panel sql-analysis-hover sql-math-hover">Build a derived trace to compare families, detect drift, and inspect the same draw through a math lens.</div>
          <div class="sql-analysis-shell sql-math-shell">
            <canvas id="sql-math-canvas" class="sql-analysis-canvas sql-math-canvas"></canvas>
            <div id="sql-math-tooltip" class="sql-analysis-tooltip sql-math-tooltip"></div>
          </div>
        </div>
      `, { kind: "workspace", meta: "derived trace studio", tone: "info", open: false })}
        ${collapsibleSection("Dataset rows preview", `<div id="sql-preview-root">${sqlPreviewRowsMarkup([])}</div>`, { kind: "list", meta: "dataset", tone: "info", open: false })}
        ${collapsibleSection("Matched draws", `<div id="sql-matched-draws-root">${sqlMatchedDrawsMarkup([])}</div>`, { kind: "list", meta: "draws", tone: "good", open: false })}
        ${collapsibleSection("Matched values", `<div id="sql-matched-values-root">${sqlPreviewRowsMarkup([])}</div>`, { kind: "list", meta: "values", tone: "info", open: false })}
        ${collapsibleSection("Maintenance events", `<div id="sql-maintenance-results-root">${sqlEventRowsMarkup([], "maintenance events")}</div>`, { kind: "list", meta: "maintenance", tone: "warn", open: false })}
        ${collapsibleSection("Fault events", `<div id="sql-fault-results-root">${sqlEventRowsMarkup([], "fault events")}</div>`, { kind: "list", meta: "faults", tone: "bad", open: false })}
        <div class="order-builder-actions sql-results-export-bar sql-results-export-bar-end">
          <button class="action-btn action-secondary" type="button" id="sql-export-results-btn">Download matched results CSV</button>
          <div id="sql-export-status" class="sql-export-status">Run a filter, then export the matched draw set and condition parameters as a CSV.</div>
        </div>
      </div>
    </section>
  `;
}

async function renderConsumablesPage(data) {
  return `
    <section class="page-panel consumables-page" id="consumables-page">
      <div class="section-heading" ${titleBandStyle("title-photo-d.jpg", "60% center")}>
        <span>Consumables</span>
        <h2>Containers, stock, temperatures</h2>
        <p>This operator view stays on the real consumables lane: container levels, coating stock, temperature signals, die setup, and coating guidance.</p>
      </div>
      <div class="metric-row">${metricMarkup(data.metrics)}</div>
      <div class="consumables-grid">
        <section class="chart-card">
          <div class="chart-head">
            <span>Containers</span>
            <strong>Live fill status</strong>
          </div>
          <div class="consumable-tank-grid">
            ${(data.containers || [])
              .map((item) => {
                const liveState = String(item.live_state || "live").trim() || "live";
                const isLive = liveState === "live";
                const isStale = liveState === "stale";
                const fillPercent = Number(item.fill_percent || 0);
                const fillState = !isLive ? (isStale ? "stale" : "offline") : fillPercent <= 10 ? "alert" : fillPercent <= 20 ? "warn" : "good";
                const statusText = isLive ? "Live signal" : isStale ? "Stale feed" : "Not connected";
                const primaryText = isLive ? `${fillPercent.toFixed(1)}%` : isStale ? "STALE" : "OFFLINE";
                const readingText = isLive
                  ? `${Number(item.level || 0).toFixed(1)} kg · ${Number(item.volume_l || 0).toFixed(1)} L`
                  : isStale
                    ? "Last tank sample is too old"
                    : "Waiting for feeder / logger signal";
                const metaText = isLive
                  ? `${escapeHtml(item.sensor_column || "")} · ${escapeHtml(item.updated_at || "No sample yet")}`
                  : item.updated_at
                    ? `${escapeHtml(item.sensor_column || "")} · last ${escapeHtml(item.updated_at)}`
                    : `${escapeHtml(item.sensor_column || "")} · no sample yet`;
                return `
                  <div class="consumable-tank is-${fillState}">
                    <span>${item.label}</span>
                    <small class="consumable-tank-badge">${statusText}</small>
                    <strong class="consumable-tank-primary">${primaryText}</strong>
                    <small class="consumable-tank-reading">${readingText}</small>
                    <em>${item.type}</em>
                    <small class="consumable-tank-meta">${metaText}</small>
                  </div>
                `;
              })
              .join("")}
          </div>
          ${collapsibleSection(
            "Update live fill setup",
            consumablesContainerEditorMarkup(data),
            {
              kind: "list",
              meta: `${(data.container_editor_rows || []).length} stations`,
              tone: "info",
              open: false,
              className: "consumables-container-fold",
            },
          )}
        </section>
        <section class="chart-card">
          <div class="chart-head">
            <span>Inventory by type</span>
            <strong>Warehouse + loaded containers (kg)</strong>
          </div>
          ${barChartMarkup(data.stock_rows || [])}
          ${collapsibleSection(
            "Update warehouse + minimum stock",
            consumablesStockEditorMarkup(data.stock_editor_rows || data.stock_rows || []),
            {
              kind: "list",
              meta: `${(data.stock_editor_rows || data.stock_rows || []).length} types`,
              tone: "info",
              open: false,
              className: "consumables-stock-fold",
            },
          )}
        </section>
      </div>
      <section class="chart-card consumables-temperature-card">
        <div class="chart-head">
          <span>Temperatures</span>
          <strong>Set values + CSV measurements</strong>
        </div>
        ${consumablesTemperatureMarkup(data)}
      </section>
      ${collapsibleSection("Coating guide", `
        <div class="micro-panel">Use this as a quick operator guide for what each coating is, what it is used for, and whether stock is getting low.</div>
        ${consumablesCoatingGuideMarkup(data.coating_rows || [])}
        ${consumablesCoatingEditorMarkup(data.coating_rows || [])}
      `, { kind: "list", meta: `${(data.coating_rows || []).length} coatings`, tone: "info", open: false })}
      ${collapsibleSection("Dies setup", `
        <form id="consumables-dies-form" class="stack-form">
          <div class="micro-panel">Set the live station names and die sizes here in <strong>um</strong>. This uses the same real dies config as the app and saves the station label plus the real die fields: <strong>Entry</strong> and <strong>Primary</strong>.</div>
          <div class="micro-list consumables-dies-editor">
            ${(data.dies_rows || [])
              .map((item, index) => `
                <div class="consumables-die-row">
                  <input type="hidden" name="original_station_${index}" value="${escapeHtml(item.station_key || item.station)}" />
                  <label class="field-block consumables-die-station-field">
                    <span>Station</span>
                    <input type="text" name="station_name_${index}" value="${escapeHtml(item.station)}" />
                  </label>
                  <label class="field-block">
                    <span>Entry (um)</span>
                    <input type="number" name="entry_die_um_${index}" value="${item.entry_die_um}" step="0.1" />
                  </label>
                  <label class="field-block">
                    <span>Primary (um)</span>
                    <input type="number" name="primary_die_um_${index}" value="${item.primary_die_um}" step="0.1" />
                  </label>
                </div>
              `)
              .join("")}
          </div>
          <div class="order-builder-actions">
            <button class="action-btn action-primary" type="submit">Save die setup</button>
          </div>
        </form>
      `, { kind: "list", meta: `${(data.dies_rows || []).length} stations`, open: false })}
    </section>
  `;
}

function processSetupText(map, key, fallback = "") {
  if (!map || typeof map !== "object") return fallback;
  const value = map[key];
  return value == null ? fallback : String(value);
}

function processSetupNumber(map, key, fallback = "") {
  const raw = processSetupText(map, key, "");
  return raw === "" ? fallback : raw;
}

const PROCESS_SETUP_IRIS_TARGET_GAP_MM2 = 200;
const PROCESS_SETUP_IRIS_OPTIONS_MM = Array.from({ length: 45 }, (_, index) => 18 + (index * 0.5));

function normalizeProcessSetupIrisShape(value) {
  const text = String(value || "").trim().toLowerCase();
  if (!text) return "Circular";
  if (text === "tiger cut" || text.includes("tiger")) return "Tiger Cut";
  if (text === "octagonal" || text.includes("oct")) return "Octagonal";
  if (text === "panda - pm" || text.includes("panda")) return "PANDA - PM";
  return "Circular";
}

function processSetupTempMeasuredMarkup(label, value, sampledAt = "") {
  const numeric = Number(value);
  const hasValue = Number.isFinite(numeric);
  const title = sampledAt ? `Measured from consumables at ${sampledAt}` : "Measured from consumables live CSV";
  return `
    <div class="process-setup-temp-meter" title="${title}">
      <span>${label}</span>
      <strong>${hasValue ? `${numeric.toFixed(1)}°C` : "—"}</strong>
    </div>
  `;
}

async function renderProcessSetupPage(data) {
  const datasetInfo = data.dataset_info || {};
  const orderMap = datasetInfo.order_map || {};
  const processMap = datasetInfo.process_map || {};
  const setupOptions = data.setup_options || {};
  const tempContext = data.temp_context || {};
  const scheduledCount = Number((data.metrics || {}).scheduled ?? (data.scheduled_orders || []).length ?? 0);
  const currentIrisShape = normalizeProcessSetupIrisShape(
    processSetupText(processMap, "Preform Shape", processSetupText(orderMap, "Fiber Geometry Type", "Circular")) || "Circular",
  );
  const currentPmIris = processSetupText(processMap, "PM Iris System", "") === "1" || currentIrisShape === "PANDA - PM";
  return `
    <section class="page-panel process-setup-page" id="process-setup-page">
      <div class="section-heading" ${titleBandStyle("title-photo-b.jpeg", "52% center")}>
        <span>Process Setup</span>
        <h2>Quick start and setup context</h2>
        <p>Enter from Order Draw or a scheduled order, then finish setup here.</p>
      </div>
      <div class="sql-help-band sql-help-band-main process-setup-flow-band">
        <div class="process-setup-flow-copy">
          <span>Setup flow</span>
          <strong>Use Order Draw as the entry lane, then continue setup here.</strong>
        </div>
        <div class="process-setup-flow-status">
          <span>Scheduled orders</span>
          <strong>${scheduledCount}</strong>
          <em>${scheduledCount === 1 ? "waiting to launch" : "waiting to launch"}</em>
        </div>
      </div>
      <div class="process-setup-workspace">
        ${collapsibleSection("Quick start", `
        <section class="chart-card chart-card-nested process-setup-main">
          <div class="chart-head">
            <span>Quick start</span>
            <strong>Start from Order Draw or a scheduled order.</strong>
          </div>
          <div class="order-builder-actions process-setup-quick-actions">
            <button class="action-btn action-secondary" type="button" data-process-order-draw="1">Go To Order Draw</button>
          </div>
          <div class="process-setup-launch-grid">
            <div class="chart-card tight stack-form">
              <div class="chart-head">
                <span>Scheduled orders</span>
                <strong>Or start a scheduled order that has not begun yet</strong>
              </div>
              <div class="micro-panel">Start only scheduled orders that still need their first setup launch.</div>
              <div class="order-queue-list process-setup-queue">
                ${(data.scheduled_orders || []).map((item) => `
                  <article class="order-queue-item process-setup-order-card">
                    <div class="process-setup-order-head">
                      <div class="process-setup-order-title">
                        <strong>${item.project || "No project"}</strong>
                        <span>${item.preform || "No preform"} · ${item.geometry || "No geometry"}</span>
                      </div>
                      <span class="status-badge tone-${orderStatusTone(item.status || "Scheduled")}">${item.status || "Scheduled"}</span>
                    </div>
                    <div class="process-setup-order-coatings">
                      <span>${item.main_coating || "-"}</span>
                      <em>${item.secondary_coating || "-"}</em>
                    </div>
                    <div class="process-setup-order-stats">
                      <div class="process-setup-order-stat">
                        <span>Scheduled</span>
                        <strong>${item.next_draw || item.desired_date || "No date"}</strong>
                      </div>
                      <div class="process-setup-order-stat">
                        <span>Length</span>
                        <strong>${item.length || "0"} m</strong>
                      </div>
                      <div class="process-setup-order-stat">
                        <span>Priority</span>
                        <strong>${item.priority || "Normal"}</strong>
                      </div>
                      <div class="process-setup-order-stat">
                        <span>Good zones</span>
                        <strong>${item.good_zones || "0"} zones</strong>
                      </div>
                    </div>
                    ${String(item.notes || "").trim() ? `
                      <div class="process-setup-order-notes">
                        <span>Draw notes</span>
                        <p>${escapeHtml(String(item.notes || "").trim()).replace(/\n+/g, "<br>")}</p>
                      </div>
                    ` : ""}
                    <div class="order-builder-actions process-setup-order-actions">
                      <button class="action-btn action-primary" type="button" data-process-start="${item.index}">Start From Scheduled Order</button>
                    </div>
                  </article>
                `).join("") || `
                  <div class="chart-empty">No scheduled orders are waiting to start.</div>
                `}
              </div>
            </div>
          </div>
        </section>`, { kind: "workspace", meta: "entry flow", tone: "good", open: false })}
      </div>
      ${collapsibleSection("Setup values", `
      <section class="chart-card chart-card-nested process-setup-sections-shell">
        <div class="chart-head">
          <span>Setup values</span>
          <strong>Order-driven coating, iris, and PID defaults</strong>
        </div>
        <div class="process-setup-sections">
          <section class="chart-card tight stack-form">
            <div class="chart-head">
              <span>Coating</span>
              <strong>Core coating setup values</strong>
            </div>
            <div class="field-grid field-grid-3">
              <label class="field-block">
                <span>Entry fiber diameter (µm)</span>
                <input type="number" id="ps-entry-fiber" value="${processSetupNumber(processMap, "Entry Fiber Diameter", processSetupNumber(orderMap, "Fiber Diameter (µm)", ""))}" step="0.1" />
              </label>
              <label class="field-block">
                <span>Furnace temperature (°C)</span>
                <input type="number" id="ps-furnace-temp" value="${processSetupNumber(processMap, "Furnace Temperature", processSetupNumber(orderMap, "Furnace Temperature (°C)", ""))}" step="0.1" />
              </label>
              <label class="field-block">
                <span>Draw speed (m/min)</span>
                <input type="number" id="ps-draw-speed" value="${processSetupNumber(processMap, "Draw Speed", processSetupNumber(orderMap, "Draw Speed (m/min)", ""))}" step="0.1" />
              </label>
            </div>
            <div class="field-grid field-grid-2">
              <label class="field-block">
                <span>Target first coating diameter (µm)</span>
                <input type="number" id="ps-target-first" value="${processSetupNumber(processMap, "Target First Coating Diameter", processSetupNumber(orderMap, "Main Coating Diameter (µm)", ""))}" step="0.1" />
              </label>
              <label class="field-block">
                <span>Target second coating diameter (µm)</span>
                <input type="number" id="ps-target-second" value="${processSetupNumber(processMap, "Target Second Coating Diameter", processSetupNumber(orderMap, "Secondary Coating Diameter (µm)", ""))}" step="0.1" />
              </label>
            </div>
            <div class="field-grid field-grid-2">
              <label class="field-block">
                <span>Primary coating</span>
                <select id="ps-primary-coating">
                  <option value="">Choose primary coating...</option>
                  ${(setupOptions.coatings || []).map((item) => `<option value="${item}" ${item === processSetupText(processMap, "Primary Coating", processSetupText(orderMap, "Main Coating", "")) ? "selected" : ""}>${item}</option>`).join("")}
                </select>
              </label>
              <label class="field-block">
                <span>Secondary coating</span>
                <select id="ps-secondary-coating">
                  <option value="">Choose secondary coating...</option>
                  ${(setupOptions.coatings || []).map((item) => `<option value="${item}" ${item === processSetupText(processMap, "Secondary Coating", processSetupText(orderMap, "Secondary Coating", "")) ? "selected" : ""}>${item}</option>`).join("")}
                </select>
      </label>
            </div>
            <div class="field-grid field-grid-2">
              <label class="field-block">
                <span>Primary temperature (°C)</span>
                <div class="process-setup-temp-row">
                  <input type="number" id="ps-primary-temp" value="${processSetupNumber(processMap, "Primary Coating Temperature", processSetupNumber(orderMap, "Main Coating Temperature (°C)", ""))}" step="0.1" />
                  ${processSetupTempMeasuredMarkup("MV now", tempContext.primary_holder_mv_c, tempContext.sampled_at)}
                </div>
              </label>
              <label class="field-block">
                <span>Secondary temperature (°C)</span>
                <div class="process-setup-temp-row">
                  <input type="number" id="ps-secondary-temp" value="${processSetupNumber(processMap, "Secondary Coating Temperature", processSetupNumber(orderMap, "Secondary Coating Temperature (°C)", ""))}" step="0.1" />
                  ${processSetupTempMeasuredMarkup("MV now", tempContext.secondary_holder_mv_c, tempContext.sampled_at)}
                </div>
              </label>
            </div>
            <div class="field-grid field-grid-3">
              <label class="field-block">
                <span>Die mode</span>
                <select id="ps-die-mode">
                  ${["Manual", "Auto"].map((item) => `<option value="${item}" ${item === processSetupText(processMap, "Coating Die Selection Mode", "Auto") ? "selected" : ""}>${item}</option>`).join("")}
                </select>
              </label>
              <label class="field-block">
                <span>Primary die</span>
                <select id="ps-primary-die">
                  <option value="">Choose die...</option>
                  ${(setupOptions.dies || []).map((item) => `<option value="${item}" ${item === processSetupText(processMap, "Primary Die Name", "") ? "selected" : ""}>${item}</option>`).join("")}
                </select>
              </label>
              <label class="field-block">
                <span>Secondary die</span>
                <select id="ps-secondary-die">
                  <option value="">Choose die...</option>
                  ${(setupOptions.dies || []).map((item) => `<option value="${item}" ${item === processSetupText(processMap, "Secondary Die Name", "") ? "selected" : ""}>${item}</option>`).join("")}
                </select>
              </label>
            </div>
            <div id="ps-die-auto-summary" class="micro-panel blocky"></div>
          </section>

          <section class="chart-card tight stack-form">
            <div class="chart-head">
              <span>Iris</span>
              <strong>Gap logic and preform interpretation</strong>
            </div>
            <div class="field-grid field-grid-2">
              <label class="field-block">
                <span>Preform shape</span>
                <select id="ps-iris-shape">
                  ${["Circular", "Tiger Cut", "Octagonal", "PANDA - PM"].map((item) => {
                    return `<option value="${item}" ${item === currentIrisShape ? "selected" : ""}>${item}</option>`;
                  }).join("")}
                </select>
              </label>
              <label class="field-block">
                <span>Calculated iris diameter (mm)</span>
                <input type="number" id="ps-iris-selected" value="${processSetupNumber(processMap, "Selected Iris Diameter", "")}" step="0.5" readonly />
              </label>
            </div>
            <div class="field-grid field-grid-3">
              <label class="field-block field-required">
                <span>Preform diameter (mm)</span>
                <input type="number" id="ps-iris-preform" value="${processSetupNumber(processMap, "Preform Diameter", processSetupNumber(orderMap, "Preform Diameter (mm)", ""))}" step="0.1" />
              </label>
              <label class="field-block">
                <span>Octagonal F2F (mm)</span>
                <input type="number" id="ps-iris-oct" value="${processSetupNumber(processMap, "Octagonal F2F", processSetupNumber(orderMap, "Octagonal F2F (mm)", ""))}" step="0.1" />
              </label>
              <label class="field-block">
                <span>Tiger cut (%)</span>
                <input type="number" id="ps-iris-tiger" value="${processSetupNumber(processMap, "Tiger Cut", processSetupNumber(orderMap, "Tiger Cut (%)", ""))}" step="0.1" />
              </label>
            </div>
            <label class="toggle-row"><input type="checkbox" id="ps-iris-pm" ${currentPmIris ? "checked" : ""} /><span>PM iris system</span></label>
            <div class="micro-panel">Auto-picks the nearest live iris in 0.5 mm steps to a target gap of about 200 mm².</div>
            <div id="ps-iris-summary" class="metric-row compact"></div>
          </section>

          <section class="chart-card tight stack-form">
            <div class="chart-head">
              <span>PID + TF</span>
              <strong>Diameter control defaults</strong>
            </div>
            <div class="field-grid field-grid-2">
              <label class="field-block">
                <span>P gain</span>
                <input type="number" id="ps-pid-p" value="${processSetupNumber(processMap, "P Gain (Diameter Control)", String((setupOptions.pid_defaults || {}).p_gain ?? 1))}" step="0.1" />
              </label>
              <label class="field-block">
                <span>I gain</span>
                <input type="number" id="ps-pid-i" value="${processSetupNumber(processMap, "I Gain (Diameter Control)", String((setupOptions.pid_defaults || {}).i_gain ?? 1))}" step="0.1" />
              </label>
            </div>
            <div class="field-grid field-grid-2">
              <label class="field-block">
                <span>TF mode</span>
                <select id="ps-pid-mode">
                  ${["Winder", "Straight Mode"].map((item) => `<option value="${item}" ${item === processSetupText(processMap, "TF Mode", (setupOptions.pid_defaults || {}).winder_mode || "Winder") ? "selected" : ""}>${item}</option>`).join("")}
                </select>
              </label>
              <label class="field-block">
                <span>Increment value (mm)</span>
                <input type="number" id="ps-pid-inc" value="${processSetupNumber(processMap, "Increment TF Value", String((setupOptions.pid_defaults || {}).increment_value ?? 0.5))}" step="0.1" />
              </label>
            </div>
          </section>
        </div>
      </section>`, { kind: "workspace", meta: "order driven", tone: "violet", open: false })}

      ${collapsibleSection("Operator actions", `
      <section class="chart-card chart-card-nested process-setup-sections-shell process-setup-final-shell">
        <div class="chart-head">
          <span>Operator actions</span>
          <strong>Drum, holder sync, readiness, and one-click save</strong>
        </div>
        <div class="process-setup-final-grid">
          <section class="chart-card tight stack-form">
            <div class="chart-head">
              <span>Drum + save</span>
              <strong>Always-used operator finish lane</strong>
            </div>
            <label class="field-block">
              <span>Selected drum</span>
              <select id="ps-drum-select">
                ${(setupOptions.drums || []).map((item) => `<option value="${item}" ${item === processSetupText(processMap, "Selected Drum", (setupOptions.drums || [])[0] || "") ? "selected" : ""}>${item}</option>`).join("")}
              </select>
            </label>
            <div id="ps-readiness-summary" class="micro-panel">Setup readiness will appear here as you fill the sections.</div>
            <div class="order-builder-actions">
              <button class="action-btn action-primary" type="button" id="ps-save-all-btn" ${!data.selected_csv ? "disabled" : ""}>Save All To Active Dataset</button>
            </div>
            <div id="ps-save-summary" class="micro-panel">${data.selected_csv ? `Active target: <strong>${data.selected_csv}</strong>` : "Choose or create a dataset first."}</div>
          </section>
        </div>
      </section>`, { kind: "workspace", meta: "operator setup", tone: "violet", open: false })}
    </section>
  `;
}

function drawFinalizeOrderMarkup(order) {
  if (!order || !order.project) {
    return `<div class="micro-panel">No matching draw order was found for the selected dataset yet.</div>`;
  }
  return `
    <div class="draw-finalize-order-card">
      <div class="draw-finalize-order-copy">
        <span>Matched order</span>
        <strong>${order.project}</strong>
        <p>${order.preform || "No preform"} · ${order.geometry || "No geometry"} · <span class="status-badge tone-${toneForLabel(order.status)}">${order.status}</span></p>
      </div>
      <div class="metric-row compact">
        <div class="metric-pill tone-info"><span>Main coating</span><strong>${order.main_coating || "-"}</strong></div>
        <div class="metric-pill tone-info"><span>Secondary</span><strong>${order.secondary_coating || "-"}</strong></div>
        <div class="metric-pill tone-warn"><span>Priority</span><strong>${order.priority || "Normal"}</strong></div>
      </div>
    </div>
  `;
}

async function renderDrawFinalizePage(data) {
  const latestDataset = data.latest_dataset || data.dataset_files?.[0] || "";
  const datasetFiles = data.dataset_files || [];
  const datasetOptions = datasetFiles.length
    ? datasetFiles
        .map((name) => {
          const label = name === latestDataset ? `${name} - newest in progress` : name;
          return `<option value="${name}" ${name === data.selected_csv ? "selected" : ""}>${label}</option>`;
        })
        .join("")
    : `<option value="">No in-progress draw datasets</option>`;
  return `
    <section class="page-panel draw-finalize-page" id="draw-finalize-page">
      <div class="section-heading" ${titleBandStyle("title-photo-a.jpg", "34% center")}>
        <span>Draw Finalize</span>
        <h2>Mark done or failed</h2>
        <p>This rebuild keeps the page close to the real purpose: pick the dataset CSV, match the draw, then close it as done or failed with the right notes and optional fault logging.</p>
      </div>
      ${drawFinalizeNoticeMarkup()}
      <div class="draw-finalize-guide">
        <div class="draw-finalize-step is-active">
          <span>1</span>
          <strong>Choose active dataset</strong>
          <p>Pick the in-progress draw CSV you want to close.</p>
        </div>
        <div class="draw-finalize-step">
          <span>2</span>
          <strong>Close the draw</strong>
          <p>Use the done or failed lane with the minimum real notes you need.</p>
        </div>
        <div class="draw-finalize-step">
          <span>3</span>
          <strong>Recover if failed</strong>
          <p>Move it to next day or back to pending without manual cleanup.</p>
        </div>
      </div>
      <div class="draw-finalize-layout">
        <section class="chart-card draw-finalize-context-card">
          <div class="chart-head">
            <span>Dataset target</span>
            <strong>Finalize context</strong>
          </div>
          <label class="field-block">
            <span>In-progress dataset CSV</span>
            <select id="finalize-dataset-select" ${datasetFiles.length ? "" : "disabled"}>
              ${datasetOptions}
            </select>
          </label>
        </section>
        <section class="draw-finalize-actions draw-finalize-actions-primary">
          <div class="chart-card draw-finalize-done-card">
            <div class="chart-head">
              <span>Done</span>
              <strong>Close successful draw</strong>
            </div>
            <form id="finalize-done-form" class="stack-form">
              <label class="field-block">
                <span>Done description</span>
                <textarea name="doneDescription" rows="4"></textarea>
              </label>
              <label class="field-block">
                <span>Preform length after draw (cm)</span>
                <input type="number" name="preformLengthCm" min="0" step="0.1" />
              </label>
              <button class="action-btn action-primary" type="submit" ${data.selected_csv ? "" : "disabled"}>Mark Done</button>
            </form>
          </div>
        </section>
        <section class="draw-finalize-actions draw-finalize-actions-secondary">
          ${collapsibleSection("Failed draw lane", `
            <div class="chart-card draw-finalize-failed-card">
              <div class="chart-head">
                <span>Failed</span>
                <strong>Close failed draw</strong>
              </div>
              <form id="finalize-failed-form" class="stack-form">
                <label class="field-block">
                  <span>Failed description</span>
                  <textarea name="failedDescription" rows="3"></textarea>
                </label>
                <div class="field-grid field-grid-2">
                  <label class="field-block">
                    <span>Reason</span>
                    <input type="text" name="failedReason" />
                  </label>
                  <label class="field-block">
                    <span>Preform left (cm)</span>
                    <input type="number" name="preformLeftCm" min="0" step="0.1" />
                  </label>
                </div>
                <label class="toggle-row"><input type="checkbox" name="logFault" /><span>Also log as fault</span></label>
                <div class="field-grid field-grid-2">
                  <label class="field-block">
                    <span>Component</span>
                    <select name="faultComponent">${(data.components || []).map((item) => `<option value="${item}">${item}</option>`).join("")}</select>
                  </label>
                  <label class="field-block">
                    <span>Severity</span>
                    <select name="faultSeverity"><option value="low">low</option><option value="medium" selected>medium</option><option value="critical">critical</option></select>
                  </label>
                </div>
                <label class="field-block">
                  <span>Fault title</span>
                  <input type="text" name="faultTitle" />
                </label>
                <label class="field-block">
                  <span>Fault description</span>
                  <textarea name="faultDescription" rows="3"></textarea>
                </label>
                <button class="action-btn action-primary" type="submit" ${data.selected_csv ? "" : "disabled"}>Mark Failed</button>
              </form>
              ${collapsibleSection("Failure recovery", `
                <div class="micro-panel">After a failed draw, move the order forward cleanly instead of manually repairing it in another page.</div>
                <div class="parts-form-actions">
                  <button class="action-btn action-secondary" type="button" id="finalize-reset-nextday-btn">Draw next day</button>
                  <button class="action-btn action-secondary" type="button" id="finalize-reset-pending-btn">Return to Pending</button>
                </div>
              `, { kind: "panel", tone: "warn", meta: "next step", open: true })}
            </div>
          `, { kind: "panel", tone: "warn", meta: "open only if failed", open: false })}
        </section>
      </div>
    </section>
  `;
}

async function renderDevelopmentPage(data) {
  const allProjectNames = Array.from(new Set([...(data.project_names || []), ...(data.archived_project_names || [])]));
  const projectOptions = data.project_names.map((name) => `<option value="${name}" ${name === data.default_project ? "selected" : ""}>${name}</option>`).join("");
  const latestDataset = (data.dataset_files || [])[0] || "";
  const latestDatasetLabel = latestDataset ? `Recent draw - ${latestDataset}` : "No linked draw";
  const drawCsvOptions = [
    `<option value="">No linked draw</option>`,
    ...(data.dataset_files || []).map((name, index) => `<option value="${name}" ${index === 0 ? "selected" : ""}>${index === 0 ? latestDatasetLabel : name}</option>`),
  ].join("");
  return `
    <section class="page-panel development-page" id="development-page">
      <div class="section-heading" ${titleBandStyle("title-photo-c.jpg", "46% center")}>
        <span>Development</span>
        <h2>Projects, experiments, and updates</h2>
        <p>This lane now follows the real flow more closely: choose the project, log experiments, track research updates, and manage project state without mixing it with production pages.</p>
      </div>
      <div class="metric-row">${metricMarkup(data.metrics)}</div>
      <div class="report-workspace development-workspace">
        <div class="development-utility-actions">
          <button class="action-btn action-secondary" type="button" data-dev-open="create-project">Create project</button>
          <button class="action-btn action-secondary" type="button" data-dev-open="project-manage">Project actions</button>
        </div>
        ${collapsibleSection("Create project", `
          <div class="chart-card chart-card-nested">
            <div class="development-tool-anchor" id="development-tool-create-project"></div>
            <div class="chart-head">
              <span>Create project</span>
              <strong>Open a new development line</strong>
            </div>
            <form id="development-project-form" class="stack-form">
              <label class="field-block"><span>Project name</span><input type="text" name="projectName" /></label>
              <label class="field-block"><span>Purpose</span><textarea name="purpose" rows="3"></textarea></label>
              <label class="field-block"><span>Target</span><input type="text" name="target" /></label>
              <button class="action-btn action-primary" type="submit">Create Project</button>
            </form>
          </div>`, { kind: "workspace", meta: "new line", tone: "violet", open: false, className: "development-utility-fold" })}
        ${collapsibleSection("Project actions", `
          <div class="chart-card chart-card-nested development-manage-card">
            <div class="development-tool-anchor" id="development-tool-project-manage"></div>
            <div class="chart-head">
              <span>Project actions</span>
              <strong>Archive, restore, or remove</strong>
            </div>
            <form id="development-manage-form" class="stack-form">
              <label class="field-block"><span>Project</span><select name="projectName">${allProjectNames.map((name) => `<option value="${name}" ${name === data.default_project ? "selected" : ""}>${name}</option>`).join("")}</select></label>
              <div class="development-manage-actions">
                <button class="action-btn action-secondary" type="submit" name="action" value="archive">Archive</button>
                <button class="action-btn action-secondary" type="submit" name="action" value="restore">Restore</button>
                <button class="action-btn action-danger" type="submit" name="action" value="delete">Delete</button>
              </div>
            </form>
            <div class="micro-panel">
              <strong>When to use each</strong>
              <p>Archive hides the project from active work. Restore brings it back. Delete removes the project and its saved history.</p>
            </div>
          </div>`, { kind: "workspace", meta: "project state", tone: "warn", open: false, className: "development-utility-fold" })}
        ${collapsibleSection("Project workspace", `
        <section class="report-main-panel">
          <div class="development-project-toolbar">
            <div class="development-top-actions-panel">
              <label class="field-block development-project-picker">
                <span>Project</span>
                <select id="development-project-select">
                  <option value="">Choose project...</option>
                  ${data.project_names.map((name) => `<option value="${name}" ${name === data.default_project ? "selected" : ""}>${name}</option>`).join("")}
                </select>
              </label>
              <div class="development-top-actions-head">
                <span>Workspace tools</span>
                <strong>Choose the next research action</strong>
              </div>
              <div class="development-top-actions">
                <button class="action-btn action-secondary" type="button" data-dev-open="project-summary">Project summary</button>
                <button class="action-btn action-secondary" type="button" data-dev-open="quick-update">Quick update</button>
                <button class="action-btn action-secondary" type="button" data-dev-open="experiment-form">Add experiment</button>
                <button class="action-btn action-secondary" type="button" data-dev-open="experiment-editor">Edit experiment</button>
              </div>
              <div class="development-paper-actions">
                <div class="development-paper-actions-head">
                  <span>Export options</span>
                </div>
                <button class="action-btn action-primary" type="button" data-dev-export="html">Export project paper</button>
                <button class="action-btn action-secondary" type="button" data-dev-export="md">Export markdown</button>
              </div>
              <div class="development-export-status" id="development-export-status" hidden></div>
            </div>
          </div>
          <div class="development-project-shell">
            <div id="development-project-root">${reportProjectDetailMarkup(null)}</div>
          </div>
          <div class="development-lab-grid">
            ${collapsibleSection("Project summary", `
            <div class="chart-card chart-card-nested">
              <div class="development-tool-anchor" id="development-tool-project-summary"></div>
              <div class="chart-head">
                <span>Project summary</span>
                <strong>Save the current summary in one project note</strong>
              </div>
              <form id="development-summary-form" class="stack-form">
                <label class="field-block"><span>Project</span><select name="projectName">${projectOptions}</select></label>
                <div class="field-grid field-grid-2">
                  <label class="field-block"><span>Summary title</span><input type="text" name="summaryTitle" placeholder="Current lab summary" /></label>
                  <label class="field-block development-date-field"><span>Summary date</span><input type="date" name="summaryDate" value="${todayIsoDate()}" /></label>
                </div>
                <label class="field-block"><span>Researcher</span><input type="text" name="summaryResearcher" /></label>
                <label class="field-block"><span>Summary notes</span><textarea name="summaryNotes" rows="5" placeholder="Write the current summary, direction, conclusion, or next decision for this project."></textarea></label>
                <button class="action-btn action-primary" type="submit">Save Summary</button>
              </form>
            </div>`, { kind: "workspace", meta: "project note", tone: "good", open: false, className: "development-utility-fold" })}
            ${collapsibleSection("Quick update", `
            <div class="chart-card chart-card-nested">
              <div class="development-tool-anchor" id="development-tool-quick-update"></div>
              <div class="chart-head">
                <span>Quick update</span>
                <strong>Add a short progress note to the current project</strong>
              </div>
              <form id="development-update-form" class="stack-form">
                <label class="field-block"><span>Project</span><select name="projectName">${projectOptions}</select></label>
                <label class="field-block"><span>Update title</span><input type="text" name="updateTitle" placeholder="Short update headline" /></label>
                <label class="field-block"><span>Researcher</span><input type="text" name="researcher" /></label>
                <label class="field-block development-date-field"><span>Update date</span><input type="date" name="updateDate" value="${todayIsoDate()}" /></label>
                <label class="field-block"><span>Update notes</span><textarea name="updateNotes" rows="4"></textarea></label>
                <button class="action-btn action-primary" type="submit">Save Update</button>
              </form>
            </div>`, { kind: "workspace", meta: "progress note", tone: "info", open: false, className: "development-utility-fold" })}
            ${collapsibleSection("Add experiment", `
            <div class="chart-card chart-card-nested">
              <div class="development-tool-anchor" id="development-tool-experiment-form"></div>
              <div class="chart-head">
                <span>Experiment log</span>
                <strong>Add experiment</strong>
              </div>
              <form id="development-experiment-form" class="stack-form">
                <div class="field-grid field-grid-2">
                  <label class="field-block"><span>Project</span><select name="projectName">${projectOptions}</select></label>
                  <label class="field-block development-date-field"><span>Date</span><input type="date" name="date" value="${todayIsoDate()}" /></label>
                </div>
                <div class="field-grid field-grid-2">
                  <label class="field-block"><span>Experiment title</span><input type="text" name="experimentTitle" /></label>
                  <label class="field-block"><span>Researcher</span><input type="text" name="researcher" /></label>
                </div>
                <label class="field-block"><span>Purpose</span><textarea name="purpose" rows="2"></textarea></label>
                <label class="field-block"><span>Methods</span><textarea name="methods" rows="2"></textarea></label>
                <div class="field-grid field-grid-2">
                  <label class="field-block"><span>Observations</span><textarea name="observations" rows="3"></textarea></label>
                  <label class="field-block"><span>Results</span><textarea name="results" rows="3"></textarea></label>
                </div>
                <label class="toggle-row"><input type="checkbox" name="isDrawing" /><span>This experiment is a drawing run</span></label>
                <div class="field-grid field-grid-2">
                  <label class="field-block"><span>Drawing details</span><input type="text" name="drawingDetails" placeholder="Short draw note" /></label>
                  <label class="field-block"><span>Draw CSV</span><select name="drawCsv">${drawCsvOptions}</select></label>
                </div>
                <label class="field-block"><span>Markdown notes</span><textarea name="markdownNotes" rows="4" placeholder="Use short markdown notes here for conclusions, formulas, or next steps."></textarea></label>
                <label class="field-block development-file-drop-field">
                  <span>Files</span>
                  <input type="file" name="attachmentsUpload" id="development-experiment-files" class="development-file-input" multiple />
                  <div class="development-file-dropzone" id="development-experiment-dropzone" tabindex="0" role="button" aria-controls="development-experiment-files">
                    <strong>Drop files here</strong>
                    <span>or click to choose files from your computer</span>
                    <em id="development-experiment-file-summary">No files chosen yet.</em>
                  </div>
                </label>
                <button class="action-btn action-primary" type="submit">Save Experiment</button>
              </form>
            </div>`, { kind: "workspace", meta: "new record", tone: "good", open: false, className: "development-utility-fold" })}
            ${collapsibleSection("Edit experiment", `
            <div class="chart-card chart-card-nested">
              <div class="development-tool-anchor" id="development-tool-experiment-editor"></div>
              <div class="chart-head">
                <span>Experiment editor</span>
                <strong>Refine the saved record</strong>
              </div>
              <form id="development-experiment-edit-form" class="stack-form">
                <label class="field-block"><span>Saved experiment</span><select id="development-experiment-select" name="experimentKey"><option value="">Choose experiment...</option></select></label>
                <input type="hidden" name="projectName" />
                <input type="hidden" name="originalTitle" />
                <input type="hidden" name="originalDate" />
                <div class="field-grid field-grid-2">
                  <label class="field-block"><span>Researcher</span><input type="text" name="researcher" /></label>
                  <label class="toggle-row"><input type="checkbox" name="isDrawing" /><span>This experiment is a drawing run</span></label>
                </div>
                <label class="field-block"><span>Purpose</span><textarea name="purpose" rows="2"></textarea></label>
                <label class="field-block"><span>Methods</span><textarea name="methods" rows="2"></textarea></label>
                <div class="field-grid field-grid-2">
                  <label class="field-block"><span>Observations</span><textarea name="observations" rows="3"></textarea></label>
                  <label class="field-block"><span>Results</span><textarea name="results" rows="3"></textarea></label>
                </div>
                <div class="field-grid field-grid-2">
                  <label class="field-block"><span>Drawing details</span><input type="text" name="drawingDetails" /></label>
                  <label class="field-block"><span>Draw CSV</span><select name="drawCsv"><option value="">No linked draw</option>${(data.dataset_files || []).map((name) => `<option value="${name}">${name}</option>`).join("")}</select></label>
                </div>
                <label class="field-block"><span>Markdown notes</span><textarea name="markdownNotes" rows="4"></textarea></label>
                <button class="action-btn action-primary" type="submit">Save Experiment Edits</button>
              </form>
            </div>`, { kind: "workspace", meta: "saved record", tone: "info", open: false, className: "development-utility-fold" })}
          </div>
        </section>`, { kind: "workspace", tone: "good", open: false })}
      </div>
    </section>
  `;
}

async function renderPlaceholderPage(title, detail) {
  return `
    <section class="page-panel placeholder-panel">
      <div class="section-heading">
        <span>Coming next</span>
        <h2>${title}</h2>
        <p>${detail}</p>
      </div>
    </section>
  `;
}

const PAGE_RENDERERS = {
  home: renderHomePage,
  schedule: renderSchedulePage,
  parts: renderPartsPage,
  maintenance: renderMaintenancePage,
  consumables: renderConsumablesPage,
  processSetup: renderProcessSetupPage,
  orderDraw: renderOrderDrawPage,
  dashboard: renderDashboardRebuildPage,
  drawFinalize: renderDrawFinalizePage,
  diagnostics: renderDiagnosticsPage,
  reportCenter: renderReportCenterPage,
  sqlLab: renderSqlLabPage,
  development: renderDevelopmentPage,
};

function getPage(route) {
  return PAGE_REGISTRY.find((page) => page.route === route) || PAGE_REGISTRY[0];
}

async function ensureBootstrapData() {
  if (bootstrapData) return bootstrapData;
  const response = await fetch("/api/bootstrap");
  if (!response.ok) {
    throw new Error(`Bootstrap failed with status ${response.status}`);
  }
  bootstrapData = await response.json();
  return bootstrapData;
}

function bindHomePanels(homeData) {
  const diagnostics = bootstrapData?.diagnostics || null;
  const panelRoot = document.getElementById("home-focus-panel");
  const cards = Array.from(document.querySelectorAll("[data-home-panel]"));
  const detailDock = document.getElementById("home-detail-dock");
  const focusShell = document.getElementById("home-focus-shell");
  const focusCoreBody = document.getElementById("home-focus-core-body");
  const toastRoot = document.getElementById("home-health-toast-root");
  const railList = document.querySelector(".home-command-rail-list-side");
  if (!cards.length) return;
  let activePanelKey = DEFAULT_HOME_PANEL;
  let scheduleDockView = "week";

  const syncDetailDock = (panelKey) => {
    if (!detailDock) return;
    const markup = homeDetailDockMarkup(panelKey, homeData, scheduleDockView);
    detailDock.innerHTML = markup;
    detailDock.classList.toggle("is-visible", panelKey === "schedule" && Boolean(markup));
    if (panelKey === "schedule") {
      Array.from(detailDock.querySelectorAll("[data-home-schedule-view]")).forEach((btn) => {
        btn.addEventListener("click", () => {
          const next = btn.dataset.homeScheduleView;
          if (!next || next === scheduleDockView) return;
          scheduleDockView = next;
          syncDetailDock("schedule");
        });
      });
    }
  };

  const setActive = (panelKey) => {
    activePanelKey = panelKey;
    cards.forEach((card) => {
      card.classList.toggle("is-active", card.dataset.homePanel === panelKey);
    });
    if (panelRoot) {
      panelRoot.innerHTML = renderHomeCategoryPanel(panelKey, homeData);
    }
    if (focusShell) {
      focusShell.classList.remove("is-idle");
    }
    syncDetailDock(panelKey);
    if (focusCoreBody) {
      focusCoreBody.innerHTML = homeHeroCoreMarkup(panelKey, homeData, false);
    }
  };

  const setHoverPreview = (panelKey) => {
    if (!focusCoreBody) return;
    focusCoreBody.innerHTML = homeHeroCoreMarkup(panelKey, homeData, false);
  };

  cards.forEach((card) => {
    const panelKey = card.dataset.homePanel;
    card.addEventListener("mouseenter", () => {
      syncDetailDock(panelKey);
      setHoverPreview(panelKey);
    });
    card.addEventListener("focus", () => {
      syncDetailDock(panelKey);
      setHoverPreview(panelKey);
    });
    card.addEventListener("blur", () => {
      syncDetailDock(activePanelKey);
      setHoverPreview(activePanelKey);
    });
    card.addEventListener("click", () => setActive(panelKey));
  });
  railList?.addEventListener("mouseleave", () => {
    syncDetailDock(activePanelKey);
    setHoverPreview(activePanelKey);
  });
  setActive(DEFAULT_HOME_PANEL);
  if (toastRoot && diagnostics?.overall_ok && !window.__towerHealthToastShown) {
    window.__towerHealthToastShown = true;
    toastRoot.innerHTML = `
      <div class="home-health-toast is-visible" role="status" aria-live="polite">
        <span>Startup check</span>
        <strong>All core diagnostics are good</strong>
        <p>${diagnostics.passed_checks}/${diagnostics.total_checks} system checks passed. ${escapeHtml(diagnostics.overall_detail || "All diagnostic lanes are ready.")}</p>
      </div>
    `;
    const toast = toastRoot.querySelector(".home-health-toast");
    window.setTimeout(() => toast?.classList.add("is-fading"), 2600);
    window.setTimeout(() => {
      if (toast) toast.remove();
      toastRoot.innerHTML = "";
    }, 3800);
  }
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok || body.ok === false) {
    throw new Error(body.message || `Request failed with status ${response.status}`);
  }
  return body;
}

async function getJson(url) {
  const response = await fetch(url);
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.message || `Request failed with status ${response.status}`);
  }
  return body;
}

async function ensurePartsManualIndex() {
  if (partsManualIndexCache) return partsManualIndexCache;
  if (partsManualIndexPromise) return partsManualIndexPromise;
  partsManualIndexPromise = getJson("/api/parts/manual-index")
    .then((body) => {
      partsManualIndexCache = body;
      return body;
    })
    .finally(() => {
      partsManualIndexPromise = null;
    });
  return partsManualIndexPromise;
}

function todayIsoDate() {
  return formatLocalIsoDate(new Date());
}

function collectOrderBuilderDraft(form) {
  const formData = new FormData(form);
  const newProjectName = String(formData.get("newProjectName") || "").trim();
  return {
    project: newProjectName || String(formData.get("project") || "").trim(),
    preformNumber: String(formData.get("preformNumber") || "").trim(),
    priority: String(formData.get("priority") || "Normal").trim(),
    geometry: String(formData.get("geometry") || "").trim(),
    opener: String(formData.get("opener") || "").trim(),
    requiredLength: formData.get("requiredLength"),
    goodZones: formData.get("goodZones"),
    preformDiameterMm: formData.get("preformDiameterMm"),
    tigerCut: formData.get("tigerCut"),
    octF2f: formData.get("octF2f"),
    notes: String(formData.get("notes") || "").trim(),
    fiberDiameter: formData.get("fiberDiameter"),
    mainCoatingDiameter: formData.get("mainCoatingDiameter"),
    secondaryCoatingDiameter: formData.get("secondaryCoatingDiameter"),
    fiberTol: formData.get("fiberTol"),
    mainTol: formData.get("mainTol"),
    secondaryTol: formData.get("secondaryTol"),
    tension: formData.get("tension"),
    drawSpeed: formData.get("drawSpeed"),
    furnaceTemp: formData.get("furnaceTemp"),
    mainCoating: String(formData.get("mainCoating") || "").trim(),
    secondaryCoating: String(formData.get("secondaryCoating") || "").trim(),
    mainCoatingTemp: formData.get("mainCoatingTemp"),
    secondaryCoatingTemp: formData.get("secondaryCoatingTemp"),
  };
}

function applyTemplateToBuilder(form, template = {}) {
  const fieldMap = {
    geometry: "Fiber Geometry Type",
    preformDiameterMm: "Preform Diameter (mm)",
    tigerCut: "Tiger Cut (%)",
    octF2f: "Octagonal F2F (mm)",
    fiberDiameter: "Fiber Diameter (µm)",
    fiberTol: "Fiber Diameter Tol (± µm)",
    mainCoatingDiameter: "Main Coating Diameter (µm)",
    mainTol: "Main Coating Diameter Tol (± µm)",
    secondaryCoatingDiameter: "Secondary Coating Diameter (µm)",
    secondaryTol: "Secondary Coating Diameter Tol (± µm)",
    tension: "Tension (g)",
    drawSpeed: "Draw Speed (m/min)",
    furnaceTemp: "Furnace Temperature (°C)",
    mainCoating: "Main Coating",
    secondaryCoating: "Secondary Coating",
    mainCoatingTemp: "Main Coating Temperature (°C)",
    secondaryCoatingTemp: "Secondary Coating Temperature (°C)",
    notes: "Notes Default",
  };
  Object.entries(fieldMap).forEach(([inputName, templateKey]) => {
    const field = form.elements.namedItem(inputName);
    if (!field) return;
    field.value = template?.[templateKey] ?? "";
  });
}

function bindOrderDrawPage(orderData) {
  const page = document.getElementById("order-draw-page");
  if (!page) return;

  const pendingOrdersById = new Map((orderData.pending_orders || []).map((item) => [String(item.index), item]));
  const tabButtons = Array.from(page.querySelectorAll("[data-order-tab]"));
  const tabPanels = Array.from(page.querySelectorAll("[data-order-panel]"));
  const scheduleForm = document.getElementById("order-schedule-form");
  const scheduleSelect = document.getElementById("order-schedule-select");
  const schedulePreview = document.getElementById("order-schedule-preview");
  const builderForm = document.getElementById("order-builder-form");
  const projectSelect = document.getElementById("order-project-select");
  const templateStatus = document.getElementById("order-template-status");
  const geometrySelect = document.getElementById("order-geometry-select");
  const tigerField = document.getElementById("field-tiger-cut");
  const octField = document.getElementById("field-oct-f2f");
  const sapBanner = document.getElementById("field-sap-banner");
  const scheduleNowToggle = document.getElementById("order-schedule-now-toggle");
  const schedulePanel = document.getElementById("order-builder-schedule-panel");
  const saveTemplateButton = document.getElementById("order-save-template-btn");
  const progressFill = document.getElementById("order-builder-progress-fill");
  const progressSteps = Array.from(page.querySelectorAll("[data-builder-progress-step]"));
  const templateProgressNote = document.getElementById("order-template-progress-note");

  const builderStepFields = {
    required: ["project", "preformNumber", "priority", "geometry", "opener", "requiredLength", "preformDiameterMm"],
    targets: ["fiberDiameter", "mainCoatingDiameter", "secondaryCoatingDiameter", "fiberTol", "mainTol", "secondaryTol", "tension", "drawSpeed", "furnaceTemp"],
    materials: ["mainCoating", "secondaryCoating", "mainCoatingTemp", "secondaryCoatingTemp"],
  };

  const hasValue = (field) => {
    if (!field) return false;
    if (field.type === "checkbox" || field.type === "radio") return field.checked;
    return String(field.value || "").trim() !== "";
  };

  const syncRequiredFieldState = (form) => {
    if (!form) return;
    Array.from(form.querySelectorAll(".field-block.field-required")).forEach((label) => {
      const control = label.querySelector("input, select, textarea");
      const isHidden = label.classList.contains("is-hidden") || Boolean(label.closest(".is-hidden"));
      const complete = !isHidden && hasValue(control);
      label.classList.toggle("is-complete", complete);
    });
  };

  const updateBuilderProgress = () => {
    if (!builderForm) return;
    const states = {
      required: { filled: 0, total: builderStepFields.required.length, complete: false },
      targets: { filled: 0, total: builderStepFields.targets.length, complete: false },
      materials: { filled: 0, total: builderStepFields.materials.length, complete: false },
      template: { filled: 0, total: 1, complete: false },
    };

    Object.entries(builderStepFields).forEach(([key, names]) => {
      states[key].filled = names.filter((name) => hasValue(builderForm.elements.namedItem(name))).length;
      states[key].complete = states[key].filled === states[key].total;
    });

    const currentProject = String(projectSelect?.value || "").trim();
    const hasTemplate = Boolean(currentProject && orderData.templates_by_project?.[currentProject]);
    states.template.filled = hasTemplate ? 1 : 0;
    states.template.complete = hasTemplate;

    progressSteps.forEach((stepButton) => {
      const key = stepButton.dataset.builderProgressStep;
      const state = states[key];
      if (!state) return;
      const countNode = stepButton.querySelector("strong");
      if (countNode) {
        countNode.textContent = key === "template"
          ? (state.complete ? "Ready" : "Pending")
          : `${state.filled} / ${state.total}`;
      }
      stepButton.classList.toggle("is-complete", state.complete);
      stepButton.classList.toggle("needs-attention", !state.complete);
      stepButton.classList.toggle("is-active", tabButtons.some((button) => button.dataset.orderTab === key && button.classList.contains("is-active")));
    });

    tabButtons.forEach((button) => {
      const state = states[button.dataset.orderTab];
      if (!state) return;
      button.classList.toggle("is-complete", state.complete);
      button.classList.toggle("needs-attention", !state.complete);
    });

    const completeCount = Object.values(states).filter((state) => state.complete).length;
    if (progressFill) {
      progressFill.style.width = `${(completeCount / 4) * 100}%`;
    }
    if (templateProgressNote) {
      templateProgressNote.textContent = currentProject
        ? (hasTemplate ? `Template defaults are already saved for ${currentProject}.` : `No template saved yet for ${currentProject}. Save this setup when you want it reusable.`)
        : "Choose a project and save its template defaults when this setup is ready.";
      templateProgressNote.classList.toggle("is-ready", hasTemplate);
    }

    syncRequiredFieldState(builderForm);
  };

  const setTab = (key) => {
    tabButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.orderTab === key));
    tabPanels.forEach((panel) => panel.classList.toggle("is-active", panel.dataset.orderPanel === key));
    progressSteps.forEach((stepButton) => stepButton.classList.toggle("is-active", stepButton.dataset.builderProgressStep === key));
    updateBuilderProgress();
  };

  const updateSchedulePreview = () => {
    if (!schedulePreview) return;
    const selected = pendingOrdersById.get(String(scheduleSelect?.value || ""));
    if (!selected) {
      schedulePreview.textContent = orderData.pending_orders.length
        ? "Choose an order to preview its details here."
        : "No pending orders available for quick scheduling.";
      return;
    }
    schedulePreview.innerHTML = `
      <strong>${selected.project || "No project"}</strong>
      <span>${selected.preform || "No preform"} · ${selected.geometry || "No geometry"} · ${selected.priority || "Normal"}</span>
      <span>Required ${selected.length || "0"} m · Zones ${selected.good_zones || "0"}</span>
    `;
    const preformField = scheduleForm?.elements.namedItem("preformNumber");
    if (preformField && (!preformField.value || preformField.value === "0")) {
      preformField.value = selected.preform || "";
    }
  };

  const syncTemplateStatus = () => {
    if (!templateStatus || !builderForm) return;
    const draft = collectOrderBuilderDraft(builderForm);
    const template = orderData.templates_by_project?.[draft.project];
    templateStatus.textContent = draft.project
      ? (template ? `Template found for ${draft.project}. Selecting the project auto-loads saved defaults.` : `No saved template yet for ${draft.project}. You can save one in the Template step.`)
      : "Select a project to auto-load its saved template defaults.";
  };

  const syncGeometryFields = () => {
    const geometry = String(geometrySelect?.value || "").trim();
    tigerField?.classList.toggle("is-hidden", geometry !== "TIGER - PM");
    octField?.classList.toggle("is-hidden", geometry !== "Octagonal");
    if (sapBanner) {
      const showSap = geometry === "PANDA - PM";
      sapBanner.classList.toggle("is-hidden", !showSap);
      sapBanner.classList.toggle("sap-stock-banner", showSap);
      sapBanner.classList.toggle("is-low", Boolean(showSap && orderData.sap_summary.low));
      if (showSap) {
        const sapCount = Number(orderData.sap_summary.count || 0);
        const sapCountLabel = Number.isFinite(sapCount) ? (Number.isInteger(sapCount) ? String(sapCount) : sapCount.toFixed(1)) : "0";
        sapBanner.innerHTML = orderData.sap_summary.low
          ? `
            <strong>SAP rods empty</strong>
            <span>${sapCountLabel} ${escapeHtml(orderData.sap_summary.units || "sets")} left in stock. PM draw cannot start until this is refilled.</span>
          `
          : `
            <strong>${escapeHtml(orderData.sap_summary.item || "SAP Rods Set")}</strong>
            <span>${sapCountLabel} ${escapeHtml(orderData.sap_summary.units || "sets")} available for PM orders.</span>
          `;
      } else {
        sapBanner.innerHTML = "";
      }
    }
  };

  const syncSchedulePanel = () => {
    schedulePanel?.classList.toggle("is-hidden", !scheduleNowToggle?.checked);
  };

  tabButtons.forEach((button) => {
    button.addEventListener("click", () => setTab(button.dataset.orderTab));
  });
  setTab("required");

  if (scheduleForm && scheduleSelect) {
    scheduleForm.elements.namedItem("date").value = todayIsoDate();
    scheduleSelect.addEventListener("change", updateSchedulePreview);
    scheduleForm.addEventListener("input", () => syncRequiredFieldState(scheduleForm));
    scheduleForm.addEventListener("change", () => syncRequiredFieldState(scheduleForm));
    updateSchedulePreview();
    syncRequiredFieldState(scheduleForm);
    scheduleForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const payload = Object.fromEntries(new FormData(scheduleForm).entries());
        const result = await postJson("/api/order-draw/schedule", payload);
        bootstrapData = result.bootstrap || null;
        orderDrawFlash = { kind: "good", title: "Pending Scheduled", message: result.message || "Pending order scheduled." };
        await renderRoute();
      } catch (error) {
        orderDrawFlash = { kind: "bad", title: "Schedule Blocked", message: error.message };
        await renderRoute();
      }
    });
  }

  Array.from(page.querySelectorAll("[data-order-select]")).forEach((button) => {
    button.addEventListener("click", () => {
      if (!scheduleSelect) return;
      scheduleSelect.value = button.dataset.orderSelect;
      updateSchedulePreview();
      scheduleForm?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  });

  if (builderForm) {
    builderForm.elements.namedItem("scheduleDate").value = todayIsoDate();
    builderForm.addEventListener("input", updateBuilderProgress);
    builderForm.addEventListener("change", updateBuilderProgress);
    builderForm.addEventListener("reset", () => {
      window.setTimeout(() => {
        syncTemplateStatus();
        syncGeometryFields();
        syncSchedulePanel();
        setTab("required");
        updateBuilderProgress();
      }, 0);
    });
    builderForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const order = collectOrderBuilderDraft(builderForm);
        const payload = {
          order,
          saveTemplate: false,
          scheduleNow: Boolean(scheduleNowToggle?.checked),
          schedule: {
            date: builderForm.elements.namedItem("scheduleDate").value,
            startTime: builderForm.elements.namedItem("scheduleStartTime").value,
            durationMin: builderForm.elements.namedItem("scheduleDurationMin").value,
            password: builderForm.elements.namedItem("schedulePassword").value,
          },
        };
        const result = await postJson("/api/order-draw/create", payload);
        bootstrapData = result.bootstrap || null;
        orderDrawFlash = { kind: "good", title: "Order Saved", message: result.message || "Draw order saved." };
        await renderRoute();
      } catch (error) {
        orderDrawFlash = { kind: "bad", title: "Submit Blocked", message: error.message };
        await renderRoute();
      }
    });
  }

  if (projectSelect && builderForm) {
    projectSelect.addEventListener("change", () => {
      const template = orderData.templates_by_project?.[projectSelect.value];
      if (template) {
        applyTemplateToBuilder(builderForm, template);
      }
      syncTemplateStatus();
      syncGeometryFields();
      updateBuilderProgress();
    });
  }

  geometrySelect?.addEventListener("change", syncGeometryFields);
  scheduleNowToggle?.addEventListener("change", syncSchedulePanel);
  progressSteps.forEach((stepButton) => {
    stepButton.addEventListener("click", () => setTab(stepButton.dataset.builderProgressStep));
  });
  saveTemplateButton?.addEventListener("click", async () => {
    if (!builderForm) return;
    try {
      const payload = collectOrderBuilderDraft(builderForm);
      const result = await postJson("/api/order-draw/template", payload);
      bootstrapData = result.bootstrap || null;
      orderDrawFlash = { kind: "good", title: "Template Saved", message: result.message || "Template saved." };
      await renderRoute();
    } catch (error) {
      orderDrawFlash = { kind: "bad", title: "Template Blocked", message: error.message };
      await renderRoute();
    }
  });

  syncTemplateStatus();
  syncGeometryFields();
  syncSchedulePanel();
  updateBuilderProgress();
}

function bindPartsPage(partsData) {
  const page = document.getElementById("parts-page");
  if (!page) return;
  const orders = partsData.all_orders || [];
  const modeButtons = Array.from(page.querySelectorAll("[data-parts-mode]"));
  const modePanels = Array.from(page.querySelectorAll("[data-parts-panel]"));
  const createForm = document.getElementById("parts-create-form");
  const updateForm = document.getElementById("parts-update-form");
  const updateSelect = document.getElementById("parts-update-select");
  const targetStatusSelect = document.getElementById("parts-target-status");
  const currentStatusLabel = document.getElementById("parts-current-status");
  const stepGoal = document.getElementById("parts-step-goal");
  const inventoryActionSelect = document.getElementById("parts-inventory-action");
  const deleteOrderButton = document.getElementById("parts-delete-order-btn");
  const inventoryForm = document.getElementById("parts-inventory-form");
  const unmountForm = document.getElementById("parts-unmount-form");
  const inventoryRows = (partsData.inventory?.inventory_rows || []).map((item, index) => ({
    ...item,
    _inventoryIndex: String(index),
  }));
  let activeStage = page.dataset.partsStage || "";
  let stageActionState = parsePartsStageActionState(page.dataset.partsStageAction || "");
  let stageFlash = parsePartsStageFlashState(page.dataset.partsStageFlash || "");
  const stageStatusOrder = partsData.status_order || [];
  const stageSelectionMap = {};
  const manualLookupRows = Array.isArray(partsData.manual_index_rows) ? partsData.manual_index_rows : [];

  const stepGoalMap = {
    "Wait for Approval": "Ask for approval and record who needs to approve this order.",
    Approved: "Confirm approval so the order becomes ready for purchasing.",
    Ordered: "Record supplier and ordering details so the order moves into real purchasing.",
    Received: "Capture the receive date first, then finish inventory action once the item is physically handled.",
    Archived: "Close the order after the received item has been handled and no more PM action is needed.",
  };

  const statusRank = (status) => {
    const order = partsData.status_order || [];
    const index = order.indexOf(status);
    return index === -1 ? 0 : index;
  };

  const getStageDefs = () => ([
    { key: "opened", label: "Opened", items: orders.filter((item) => item.status === "Opened") },
    { key: "approval", label: "Wait for Approval", items: partsData.queues?.approval || [] },
    { key: "approved", label: "Ready to order", items: partsData.queues?.approved || [] },
    { key: "ordered", label: "Ordered", items: partsData.queues?.ordered || [] },
    { key: "received_pending", label: "Received pending", items: partsData.queues?.received_pending || [] },
  ]);

  const getStageByKey = (key) => getStageDefs().find((stage) => stage.key === key) || getStageDefs()[0];
  const createStageCopy = {
    Opened: {
      title: "Start at Opened",
      body: "Save a basic request first, then move it through approval and purchasing when that data exists.",
    },
    "Wait for Approval": {
      title: "Start at Wait for approval",
      body: "Open the request already aimed at approval and record who needs to respond.",
    },
    Approved: {
      title: "Start at Approved",
      body: "Use this when approval already happened and the order is ready for purchasing.",
    },
    Ordered: {
      title: "Start at Ordered",
      body: "Use this only when supplier, buyer, and order date are already known.",
    },
    Received: {
      title: "Start at Received",
      body: "Use this only when the part has physically arrived and is waiting for inventory handling.",
    },
  };

  const detectManualComponentMatch = (orderItem) => {
    if (!orderItem) return "";
    const existingComponent = String(orderItem.maintenance_component || "").trim();
    if (existingComponent) return existingComponent;
    const partName = normalizeLookupText(orderItem.part_name);
    const serial = normalizeLookupText(orderItem.serial_number);
    if (!partName && !serial) return "";
    const matchedRow = manualLookupRows.find((row) => {
      const part = normalizeLookupText(row.part);
      const partNumber = normalizeLookupText(row.part_number);
      return (partName && (part === partName || scoreLookupMatch(row.part, partName) > 80))
        || (serial && partNumber && partNumber === serial);
    });
    if (!matchedRow) return "";
    return String(matchedRow.manual || "")
      .replace(/\.pdf$/i, "")
      .replace(/[_-]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  };

  const buildCloseoutInventoryMatch = (inventoryRow, orderItem) => {
    if (!inventoryRow || !orderItem) return null;
    const partName = normalizeLookupText(orderItem.part_name);
    const serial = normalizeLookupText(orderItem.serial_number);
    const manualComponent = detectManualComponentMatch(orderItem);
    const rawComponent = String(orderItem.maintenance_component || manualComponent || "").trim();
    const component = normalizeLookupText(rawComponent);
    const inventoryPart = normalizeLookupText(inventoryRow.part_name);
    const inventorySerial = normalizeLookupText(inventoryRow.serial_number);
    const inventoryComponent = normalizeLookupText(inventoryRow.component);
    let score = 0;
    const reasons = [];
    let hasIdentityMatch = false;
    if (partName && inventoryPart === partName) {
      score += 120;
      reasons.push("Same part name");
      hasIdentityMatch = true;
    }
    if (serial && inventorySerial === serial) {
      score += 140;
      reasons.push("Same serial");
      hasIdentityMatch = true;
    }
    if (!hasIdentityMatch) return null;
    if (component && inventoryComponent === component) {
      score += 24;
      reasons.push(manualComponent && !orderItem.maintenance_component ? `Manual component: ${rawComponent}` : `Same component: ${rawComponent}`);
    }
    if (score <= 0) return null;
    return {
      row: inventoryRow,
      score,
      reasons,
      matchedComponent: rawComponent,
    };
  };

  const findCloseoutInventoryMatches = (orderItem, inventoryAction) => {
    if (!orderItem || inventoryAction !== "Locate in inventory") return [];
    return inventoryRows
      .map((row) => buildCloseoutInventoryMatch(row, orderItem))
      .filter(Boolean)
      .sort((a, b) => b.score - a.score || String(a.row.part_name || "").localeCompare(String(b.row.part_name || "")))
      .slice(0, 6);
  };

  const applyCloseoutInventoryMatch = (drawer, matchRow) => {
    if (!drawer || !matchRow) return;
    const matchIndexField = drawer.querySelector('input[name="inventoryMatchIndex"]');
    const locationField = drawer.querySelector('input[name="inventoryLocation"]');
    const itemTypeField = drawer.querySelector('select[name="inventoryItemType"]');
    const componentField = drawer.querySelector('input[name="inventoryComponent"]');
    const notesField = drawer.querySelector('input[name="inventoryNotes"]');
    if (matchIndexField) matchIndexField.value = matchRow._inventoryIndex || "";
    if (locationField) locationField.value = matchRow.location || "";
    if (itemTypeField) itemTypeField.value = matchRow.item_type || "Part";
    if (componentField) componentField.value = matchRow.component || detectManualComponentMatch(getCloseoutDrawerOrder()) || "Tower Parts";
    if (notesField && !String(notesField.value || "").trim()) {
      notesField.value = matchRow.notes || `Add to existing inventory row at ${matchRow.location || "selected place"}`;
    }
  };

  const clearCloseoutInventoryMatch = (drawer) => {
    const matchIndexField = drawer?.querySelector('input[name="inventoryMatchIndex"]');
    if (matchIndexField) matchIndexField.value = "";
  };

  const getCloseoutDrawerOrder = () => {
    const activeOrderId = stageActionState?.orderIds?.[0];
    return orders.find((item) => String(item.index) === String(activeOrderId)) || null;
  };

  const renderCloseoutInventoryMatches = () => {
    const drawer = page.querySelector(".maintenance-prep-actiondrawer");
    if (!drawer) return;
    const matchShell = drawer.querySelector("[data-parts-drawer-match-shell]");
    const matchRoot = drawer.querySelector("[data-parts-drawer-match-suggestions]");
    const matchSummary = drawer.querySelector("[data-parts-drawer-match-summary]");
    const matchIndexField = drawer.querySelector('input[name="inventoryMatchIndex"]');
    const inventoryActionField = drawer.querySelector('select[name="inventoryAction"]');
    const targetSelect = drawer.querySelector('[data-parts-target-select]');
    const componentField = drawer.querySelector('input[name="inventoryComponent"]');
    if (!matchShell || !matchRoot || !inventoryActionField || !targetSelect) return;
    const targetStatus = String(targetSelect.value || "").trim();
    const inventoryAction = String(inventoryActionField.value || "").trim();
    const targetRank = partsStatusRank(targetStatus, stageStatusOrder);
    const orderItem = getCloseoutDrawerOrder();
    if (componentField && !String(componentField.value || "").trim()) {
      componentField.value = detectManualComponentMatch(orderItem) || "Tower Parts";
    }
    if (
      stageActionState?.mode === "bulk"
      || targetRank < partsStatusRank("Archived", stageStatusOrder)
      || inventoryAction !== "Locate in inventory"
    ) {
      matchShell.hidden = true;
      matchRoot.innerHTML = "";
      return;
    }
    const matches = findCloseoutInventoryMatches(orderItem, inventoryAction);
    if (!matches.length) {
      matchShell.hidden = false;
      matchRoot.innerHTML = `<div class="chart-empty">No existing inventory row matched this part yet. The closeout will create or update a row from the fields below.</div>`;
      if (matchSummary) matchSummary.textContent = "No exact serial or part-name inventory row matched yet.";
      return;
    }
    const selectedIndex = String(matchIndexField?.value || "");
    matchShell.hidden = false;
    if (matchSummary) {
      matchSummary.textContent = `${matches.length} exact inventory row${matches.length === 1 ? "" : "s"} matched by serial or part name. Pick one to add quantity there.`;
    }
    matchRoot.innerHTML = matches
      .map(({ row, reasons }) => {
        const isActive = String(row._inventoryIndex) === selectedIndex;
        const matchWhy = reasons?.length ? `Matched by: ${reasons.join(" · ")}` : "";
        return `
          <button
            class="parts-drawer-match-option ${isActive ? "is-active" : ""}"
            type="button"
            data-parts-drawer-match="${escapeHtml(row._inventoryIndex)}"
          >
            <span class="parts-drawer-match-copy">
              <strong>${escapeHtml(row.part_name || "Unnamed part")}</strong>
              <span>${escapeHtml([row.component || "Tower Parts", row.location || "No location", row.item_type || "Part"].filter(Boolean).join(" · "))}</span>
              ${
                matchWhy
                  ? `<span class="parts-drawer-match-why">${escapeHtml(matchWhy)}</span><span class="parts-drawer-match-reasons">${reasons.map((reason) => `<i>${escapeHtml(reason)}</i>`).join("")}</span>`
                  : ""
              }
            </span>
            <em>Qty ${escapeHtml(formatInventoryFormQuantity(row.quantity))}</em>
          </button>
        `;
      })
      .join("");
  };

  const syncStageDrawerFields = () => {
    const drawer = page.querySelector(".maintenance-prep-actiondrawer");
    if (!drawer) return;
    const targetSelect = drawer.querySelector('[data-parts-target-select]');
    const targetStatus = targetSelect?.value || "";
    const currentStatus = drawer.dataset.partsCurrentStatus || "Opened";
    const targetRank = partsStatusRank(targetStatus, stageStatusOrder);
    const currentRank = partsStatusRank(currentStatus, stageStatusOrder);
    const waitSection = drawer.querySelectorAll('[data-parts-drawer-section="wait-for-approval"]');
    const waitGroups = drawer.querySelectorAll('[data-parts-drawer-section-group="wait-for-approval"]');
    const approvedSection = drawer.querySelectorAll('[data-parts-drawer-section="approved"]');
    const orderedSection = drawer.querySelectorAll('[data-parts-drawer-section="ordered"]');
    const receivedSection = drawer.querySelectorAll('[data-parts-drawer-section="received"]');
    const archivedSection = drawer.querySelectorAll('[data-parts-drawer-section="archived"]');
    const closeoutFocus = drawer.querySelector('[data-parts-drawer-closeout]');
    const closeoutLocationWrap = drawer.querySelector('[data-parts-drawer-location-wrap]');
    const closeoutLocationLabel = drawer.querySelector('[data-parts-drawer-location-label]');
    const closeoutExtra = drawer.querySelectorAll('[data-parts-drawer-closeout-extra]');
    const inventoryActionField = drawer.querySelector('select[name="inventoryAction"]');
    const inventoryAction = inventoryActionField?.value || "";
    const toggle = (nodes, visible) => nodes.forEach((node) => {
      node.hidden = !visible;
      node.style.display = visible ? "" : "none";
    });
    toggle(waitGroups, currentRank < partsStatusRank("Wait for Approval", stageStatusOrder) && targetRank >= partsStatusRank("Wait for Approval", stageStatusOrder));
    toggle(waitSection, currentRank < partsStatusRank("Wait for Approval", stageStatusOrder) && targetRank >= partsStatusRank("Wait for Approval", stageStatusOrder));
    toggle(approvedSection, currentRank < partsStatusRank("Approved", stageStatusOrder) && targetRank >= partsStatusRank("Approved", stageStatusOrder));
    toggle(orderedSection, currentRank < partsStatusRank("Ordered", stageStatusOrder) && targetRank >= partsStatusRank("Ordered", stageStatusOrder));
    toggle(receivedSection, currentRank < partsStatusRank("Received", stageStatusOrder) && targetRank >= partsStatusRank("Received", stageStatusOrder));
    toggle(archivedSection, targetRank >= partsStatusRank("Archived", stageStatusOrder));
    toggle(closeoutFocus ? [closeoutFocus] : [], targetRank >= partsStatusRank("Archived", stageStatusOrder));
    toggle(closeoutLocationWrap ? [closeoutLocationWrap] : [], targetRank >= partsStatusRank("Archived", stageStatusOrder));
    if (closeoutLocationLabel) closeoutLocationLabel.textContent = inventoryAction === "Mount on machine" ? "Mounted place" : "Storage place";
    toggle(closeoutExtra, targetRank >= partsStatusRank("Archived", stageStatusOrder));
    renderCloseoutInventoryMatches();
  };

  const persistStageUiState = () => {
    page.dataset.partsStage = activeStage || "";
    page.dataset.partsStageAction = stageActionState ? JSON.stringify(stageActionState) : "";
    page.dataset.partsStageFlash = stageFlash ? JSON.stringify(stageFlash) : "";
  };

  const rerenderStageFlow = () => {
    const shell = page.querySelector(".parts-stage-shell");
    if (!shell) return;
    shell.outerHTML = partsStageFlowMarkup(
      partsData,
      activeStage,
      stageActionState,
      stageFlash,
      stageSelectionMap[activeStage] || [],
    );
    bindStageFlow();
  };

  const openStageAction = (action, orderIds, mode = "single") => {
    stageActionState = { action, orderIds: orderIds.map((item) => String(item)), mode };
    stageFlash = null;
    persistStageUiState();
    rerenderStageFlow();
  };

  const closeStageAction = () => {
    stageActionState = null;
    persistStageUiState();
    rerenderStageFlow();
  };

  const parseDrawerPayload = (drawer) => {
    const payload = {};
    Array.from(drawer.querySelectorAll("input[name], select[name], textarea[name]") || []).forEach((field) => {
      payload[field.name] = field.value;
    });
    return payload;
  };

  const validateStageAdvancePayload = (targetStatus, drawerPayload) => {
    const targetRank = partsStatusRank(targetStatus, stageStatusOrder);
    if (targetRank >= partsStatusRank("Wait for Approval", stageStatusOrder) && !drawerPayload.approvalRequestedFrom) {
      throw new Error("Add who the order should be sent to for approval.");
    }
    if (targetRank >= partsStatusRank("Approved", stageStatusOrder) && (!drawerPayload.approvedBy || !drawerPayload.approvalDate)) {
      throw new Error("Fill the approval owner and approval date.");
    }
    if (targetRank >= partsStatusRank("Ordered", stageStatusOrder) && (!drawerPayload.company || !drawerPayload.orderedBy || !drawerPayload.dateOrdered)) {
      throw new Error("Fill supplier, ordered by, and ordered date.");
    }
    if (targetRank >= partsStatusRank("Received", stageStatusOrder) && !drawerPayload.receivedDate) {
      throw new Error("Fill the received date.");
    }
    if (targetRank >= partsStatusRank("Archived", stageStatusOrder) && !drawerPayload.inventoryAction) {
      throw new Error("Choose if the part goes to inventory or is mounted on tower.");
    }
    if (targetStatus === "Archived" && drawerPayload.inventoryAction === "Locate in inventory" && !drawerPayload.inventoryLocation) {
      throw new Error("Choose the storage place for the inventory closeout.");
    }
  };

  const buildStageAdvancePayload = (item, drawerPayload) => {
    const targetStatus = String(drawerPayload.targetStatus || "").trim() || item.status || "Opened";
    validateStageAdvancePayload(targetStatus, drawerPayload);
    return {
      index: item.index,
      partName: item.part_name,
      serialNumber: item.serial_number,
      project: item.project,
      details: item.details,
      openedBy: item.opened_by,
      approvalRequestedFrom: drawerPayload.approvalRequestedFrom || item.approval_requested_from || "",
      approvedBy: drawerPayload.approvedBy || item.approved_by || "",
      approvalDate: drawerPayload.approvalDate || item.approval_date || "",
      receivedDate: drawerPayload.receivedDate || item.received_date || "",
      receivedState: item.received_state,
      orderedBy: drawerPayload.orderedBy || item.ordered_by || "",
      dateOrdered: drawerPayload.dateOrdered || item.date_ordered || "",
      company: drawerPayload.company || item.company || "",
      inventorySynced: item.inventory_synced,
      maintenanceComponent: item.maintenance_component,
      maintenanceTask: item.maintenance_task,
      maintenanceTaskId: item.maintenance_task_id,
      waitId: item.wait_id,
      status: targetStatus,
      inventoryAction: targetStatus === "Archived" ? drawerPayload.inventoryAction : "",
      inventoryLocation: targetStatus === "Archived" ? drawerPayload.inventoryLocation || "" : "",
      inventoryQuantity: targetStatus === "Archived" ? drawerPayload.inventoryQuantity || "1" : "",
      inventoryItemType: targetStatus === "Archived" ? drawerPayload.inventoryItemType || "Part" : "",
      inventoryComponent: targetStatus === "Archived" ? drawerPayload.inventoryComponent || item.maintenance_component || "Tower Parts" : "",
      inventoryNotes: targetStatus === "Archived" ? drawerPayload.inventoryNotes || "" : "",
      inventoryMatchIndex: targetStatus === "Archived" ? drawerPayload.inventoryMatchIndex || "" : "",
    };
  };

  const bindStageFlow = () => {
    Array.from(page.querySelectorAll("[data-parts-stage]") || []).forEach((button) => {
      button.addEventListener("click", () => {
        const nextStage = button.dataset.partsStage || "opened";
        activeStage = nextStage === activeStage ? "" : nextStage;
        stageActionState = null;
        stageFlash = null;
        persistStageUiState();
        rerenderStageFlow();
      });
    });
    Array.from(page.querySelectorAll("[data-parts-stage-action]") || []).forEach((button) => {
      button.addEventListener("click", () => {
        const action = button.dataset.partsStageAction || "";
        const orderId = button.dataset.partsStageOrder || "";
        if (!action || !orderId) return;
        openStageAction(action, [orderId], "single");
      });
    });
    Array.from(page.querySelectorAll("[data-parts-stage-select]") || []).forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        const picked = String(checkbox.dataset.partsStageSelect || "");
        const current = new Set(stageSelectionMap[activeStage] || []);
        if (checkbox.checked) current.add(picked);
        else current.delete(picked);
        stageSelectionMap[activeStage] = Array.from(current);
        persistStageUiState();
        rerenderStageFlow();
      });
    });
    Array.from(page.querySelectorAll("[data-parts-stage-select-all]") || []).forEach((checkbox) => {
      checkbox.indeterminate = checkbox.dataset.partsStageIndeterminate === "true";
      checkbox.addEventListener("change", () => {
        const orderIds = String(checkbox.dataset.partsStageOrderIds || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
        stageSelectionMap[activeStage] = checkbox.checked ? orderIds : [];
        persistStageUiState();
        rerenderStageFlow();
      });
    });
    Array.from(page.querySelectorAll("[data-parts-stage-bulk]") || []).forEach((button) => {
      button.addEventListener("click", () => {
        const action = String(button.dataset.partsStageBulk || "").replace(/-all$/, "");
        const orderIds = String(button.dataset.partsStageOrderIds || "").split(",").map((item) => item.trim()).filter(Boolean);
        if (!action || !orderIds.length) return;
        openStageAction(action, orderIds, "bulk");
      });
    });
    Array.from(page.querySelectorAll("[data-parts-stage-cancel]") || []).forEach((button) => {
      button.addEventListener("click", closeStageAction);
    });
    Array.from(page.querySelectorAll("[data-parts-target-select]") || []).forEach((select) => {
      select.addEventListener("change", syncStageDrawerFields);
    });
    Array.from(page.querySelectorAll('.maintenance-prep-actiondrawer select[name="inventoryAction"]') || []).forEach((select) => {
      select.addEventListener("change", syncStageDrawerFields);
    });
    Array.from(page.querySelectorAll('.maintenance-prep-actiondrawer input[name="inventoryLocation"], .maintenance-prep-actiondrawer input[name="inventoryComponent"], .maintenance-prep-actiondrawer select[name="inventoryItemType"]') || []).forEach((field) => {
      const refreshMatches = () => {
        const drawer = field.closest(".maintenance-prep-actiondrawer");
        if (!drawer) return;
        clearCloseoutInventoryMatch(drawer);
        renderCloseoutInventoryMatches();
      };
      field.addEventListener("input", refreshMatches);
      field.addEventListener("change", refreshMatches);
    });
    Array.from(page.querySelectorAll("[data-parts-drawer-match-suggestions]") || []).forEach((root) => {
      root.addEventListener("click", (event) => {
        const button = event.target instanceof Element ? event.target.closest("[data-parts-drawer-match]") : null;
        if (!button) return;
        const drawer = button.closest(".maintenance-prep-actiondrawer");
        if (!drawer) return;
        const matchRow = inventoryRows.find((row) => String(row._inventoryIndex) === String(button.dataset.partsDrawerMatch || ""));
        if (!matchRow) return;
        applyCloseoutInventoryMatch(drawer, matchRow);
        renderCloseoutInventoryMatches();
      });
    });
    Array.from(page.querySelectorAll("[data-parts-stage-confirm]") || []).forEach((button) => {
      button.addEventListener("click", async () => {
        if (!stageActionState?.orderIds?.length) return;
        const drawer = page.querySelector(".maintenance-prep-actiondrawer");
        const drawerPayload = parseDrawerPayload(drawer);
        const selectedItems = orders.filter((item) => stageActionState.orderIds.includes(String(item.index)));
        try {
          for (const item of selectedItems) {
            const updatePayload = buildStageAdvancePayload(item, drawerPayload);
            const result = await postJson("/api/parts/update", updatePayload);
            bootstrapData = result.bootstrap || null;
          }
          stageFlash = { kind: "good", message: `${selectedItems.length} order${selectedItems.length === 1 ? "" : "s"} updated.` };
          stageActionState = null;
          persistStageUiState();
          await renderRoute();
        } catch (error) {
          stageFlash = { kind: "bad", message: error.message };
          persistStageUiState();
          rerenderStageFlow();
        }
      });
    });
    syncStageDrawerFields();
  };

  const getCurrentItem = () => orders.find((row) => String(row.index) === String(updateSelect?.value || ""));

  const syncUpdateStepFields = () => {
    const currentItem = getCurrentItem();
    if (!currentItem || !updateForm || !targetStatusSelect) return;
    const currentStatus = String(currentItem.status || "Opened");
    const order = partsData.status_order || [];
    const allowed = order.slice(Math.max(order.indexOf(currentStatus), 0) + 1);
    const options = (allowed.length ? allowed : [currentStatus])
      .map((item) => `<option value="${item}">${item}</option>`)
      .join("");
    targetStatusSelect.innerHTML = options;
    const targetStatus = targetStatusSelect.value || (allowed[0] || currentStatus);
    if (!targetStatusSelect.value) targetStatusSelect.value = targetStatus;
    if (currentStatusLabel) currentStatusLabel.textContent = currentStatus;
    if (stepGoal) stepGoal.textContent = stepGoalMap[targetStatus] || "Move this order to the next workflow step.";

    const needsApprovalRequest = statusRank(targetStatus) >= statusRank("Wait for Approval")
      && (!currentItem.approval_requested_from || statusRank(currentStatus) < statusRank("Wait for Approval"));
    const needsApprovalConfirm = statusRank(targetStatus) >= statusRank("Approved")
      && ((!currentItem.approved_by || !currentItem.approval_date) || statusRank(currentStatus) < statusRank("Approved"));
    const needsOrderData = statusRank(targetStatus) >= statusRank("Ordered")
      && ((!currentItem.company || !currentItem.ordered_by || !currentItem.date_ordered) || statusRank(currentStatus) < statusRank("Ordered"));
    const needsReceivedDate = statusRank(targetStatus) >= statusRank("Received")
      && ((!currentItem.received_date) || statusRank(currentStatus) < statusRank("Received"));
    const showReceivedPanel = currentStatus === "Received" || currentStatus === "Archived" || targetStatus === "Received" || targetStatus === "Archived";

    Array.from(updateForm.querySelectorAll("[data-parts-step-field]")).forEach((node) => {
      const fieldKey = node.dataset.partsStepField;
      let show = false;
      if (fieldKey === "approvalRequest") show = needsApprovalRequest;
      if (fieldKey === "approvalConfirm") show = needsApprovalConfirm;
      if (fieldKey === "orderData") show = needsOrderData;
      if (fieldKey === "receivedDate") show = needsReceivedDate;
      if (fieldKey === "receivedPanel") show = showReceivedPanel;
      node.classList.toggle("is-hidden", !show);
    });
  };

  const fillUpdateForm = (indexValue) => {
    if (!updateForm) return;
    const item = orders.find((row) => String(row.index) === String(indexValue));
    if (!item) return;
    const values = {
      index: item.index,
      status: item.status,
      partName: item.part_name,
      serialNumber: item.serial_number,
      project: item.project,
      details: item.details,
      openedBy: item.opened_by,
      approvalRequestedFrom: item.approval_requested_from,
      approvedBy: item.approved_by,
      approvalDate: item.approval_date,
      receivedDate: item.received_date,
      receivedState: item.received_state,
      orderedBy: item.ordered_by,
      dateOrdered: item.date_ordered,
      company: item.company,
      inventorySynced: item.inventory_synced,
      maintenanceComponent: item.maintenance_component,
      maintenanceTask: item.maintenance_task,
      maintenanceTaskId: item.maintenance_task_id,
      waitId: item.wait_id,
      inventoryAction: item.received_state === "Located in inventory"
        ? "Locate in inventory"
        : item.received_state === "Mounted on machine"
          ? "Mount on machine"
          : "No inventory action",
    };
    Object.entries(values).forEach(([key, value]) => {
      const field = updateForm.elements.namedItem(key);
      if (field) field.value = value || "";
    });
    syncUpdateStepFields();
  };

  const setMode = (mode) => {
    modeButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.partsMode === mode));
    modePanels.forEach((panel) => panel.classList.toggle("is-active", panel.dataset.partsPanel === mode));
  };

  modeButtons.forEach((button) => {
    button.addEventListener("click", () => setMode(button.dataset.partsMode));
  });
  updateSelect?.addEventListener("change", () => fillUpdateForm(updateSelect.value));
  targetStatusSelect?.addEventListener("change", syncUpdateStepFields);
  inventoryActionSelect?.addEventListener("change", () => {
    const receivedStateField = updateForm?.elements.namedItem("receivedState");
    const inventorySyncedField = updateForm?.elements.namedItem("inventorySynced");
    if (!receivedStateField || !inventorySyncedField) return;
    if (inventoryActionSelect.value === "Locate in inventory") {
      receivedStateField.value = "Located in inventory";
      inventorySyncedField.value = "Yes";
    } else if (inventoryActionSelect.value === "Mount on machine") {
      receivedStateField.value = "Mounted on machine";
      inventorySyncedField.value = "Yes";
    } else {
      receivedStateField.value = "Waiting for inventory action";
      inventorySyncedField.value = "Pending";
    }
  });

  const createStatusField = createForm?.querySelector("[data-parts-create-status]");
  const createStageNote = createForm?.querySelector("[data-parts-create-stage-note]");
  const syncCreateStepFields = () => {
    if (!createForm || !createStatusField) return;
    const targetStatus = String(createStatusField.value || "Opened").trim() || "Opened";
    const targetRank = statusRank(targetStatus);
    const toggle = (selector, visible) => {
      Array.from(createForm.querySelectorAll(selector) || []).forEach((node) => {
        node.classList.toggle("is-hidden", !visible);
      });
    };
    toggle('[data-parts-create-stage="wait"]', targetRank >= statusRank("Wait for Approval"));
    toggle('[data-parts-create-stage="approved"]', targetRank >= statusRank("Approved"));
    toggle('[data-parts-create-stage="ordered"]', targetRank >= statusRank("Ordered"));
    toggle('[data-parts-create-stage="received"]', targetRank >= statusRank("Received"));
    const copy = createStageCopy[targetStatus] || createStageCopy.Opened;
    if (createStageNote) {
      const titleNode = createStageNote.querySelector("strong");
      const bodyNode = createStageNote.querySelector("span");
      if (titleNode) titleNode.textContent = copy.title;
      if (bodyNode) bodyNode.textContent = copy.body;
    }
  };

  const validateCreatePayload = (payload) => {
    const targetStatus = String(payload.status || "Opened").trim() || "Opened";
    const targetRank = statusRank(targetStatus);
    if (!payload.partName) {
      throw new Error("Part name is required.");
    }
    if (targetRank >= statusRank("Wait for Approval") && !String(payload.approvalRequestedFrom || "").trim()) {
      throw new Error("Fill who the request should be sent to for approval.");
    }
    if (targetRank >= statusRank("Approved") && (!String(payload.approvedBy || "").trim() || !String(payload.approvalDate || "").trim())) {
      throw new Error("Fill the approval owner and approval date.");
    }
    if (targetRank >= statusRank("Ordered") && (!String(payload.company || "").trim() || !String(payload.orderedBy || "").trim() || !String(payload.dateOrdered || "").trim())) {
      throw new Error("Fill supplier, ordered by, and ordered date.");
    }
    if (targetRank >= statusRank("Received") && !String(payload.receivedDate || "").trim()) {
      throw new Error("Fill the received date.");
    }
  };

  createStatusField?.addEventListener("change", syncCreateStepFields);
  syncCreateStepFields();

  createForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = Object.fromEntries(new FormData(createForm).entries());
      validateCreatePayload(payload);
      const result = await postJson("/api/parts/create", payload);
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      const actions = createForm.querySelector(".parts-form-actions");
      if (actions) actions.dataset.error = error.message;
    }
  });

  updateForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = Object.fromEntries(new FormData(updateForm).entries());
      const result = await postJson("/api/parts/update", payload);
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      const actions = updateForm.querySelector(".parts-form-actions");
      if (actions) actions.dataset.error = error.message;
    }
  });

  deleteOrderButton?.addEventListener("click", async () => {
    const currentItem = getCurrentItem();
    if (!currentItem) return;
    const confirmed = window.confirm(`Delete part order for "${currentItem.part_name}"?`);
    if (!confirmed) return;
    try {
      const result = await postJson("/api/parts/delete", { index: currentItem.index });
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      const actions = updateForm.querySelector(".parts-form-actions");
      if (actions) actions.dataset.error = error.message;
    }
  });

  const inventoryModeField = inventoryForm?.elements.namedItem("mode");
  const inventoryEditIndexField = inventoryForm?.elements.namedItem("inventoryEditIndex");
  const inventorySubmitButton = inventoryForm?.querySelector('button[type="submit"]');
  const inventoryEditPick = inventoryForm?.querySelector("[data-parts-inventory-edit-pick]");
  const inventorySmartInput = inventoryForm?.querySelector("[data-parts-inventory-smart-input]");
  const inventoryComponentInput = inventoryForm?.querySelector("[data-parts-inventory-component-input]");
  const inventorySuggestionRoot = inventoryForm?.querySelector("[data-parts-inventory-suggestions]");
  const inventoryComponentSuggestionRoot = inventoryForm?.querySelector("[data-parts-inventory-component-suggestions]");
  const inventorySuggestionMap = new Map();
  const inventoryComponentSuggestionMap = new Map();
  let inventorySuggestionHideTimer = null;
  let inventoryComponentSuggestionHideTimer = null;
  const setInventoryFieldValue = (name, value) => {
    const field = inventoryForm?.elements.namedItem(name);
    if (field) field.value = value ?? "";
  };
  const formatInventoryFormQuantity = (value) => {
    const numeric = Number(value || 0);
    if (!Number.isFinite(numeric)) return "0";
    return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(1).replace(/\.0$/, "");
  };
  const clearInventorySuggestionHideTimer = () => {
    if (inventorySuggestionHideTimer) {
      window.clearTimeout(inventorySuggestionHideTimer);
      inventorySuggestionHideTimer = null;
    }
  };
  const clearInventoryComponentSuggestionHideTimer = () => {
    if (inventoryComponentSuggestionHideTimer) {
      window.clearTimeout(inventoryComponentSuggestionHideTimer);
      inventoryComponentSuggestionHideTimer = null;
    }
  };
  const hideInventorySuggestions = () => {
    clearInventorySuggestionHideTimer();
    if (!inventorySuggestionRoot) return;
    inventorySuggestionRoot.hidden = true;
    inventorySuggestionRoot.innerHTML = "";
    inventorySuggestionMap.clear();
  };
  const hideInventoryComponentSuggestions = () => {
    clearInventoryComponentSuggestionHideTimer();
    if (!inventoryComponentSuggestionRoot) return;
    inventoryComponentSuggestionRoot.hidden = true;
    inventoryComponentSuggestionRoot.innerHTML = "";
    inventoryComponentSuggestionMap.clear();
  };
  const queueHideInventorySuggestions = () => {
    clearInventorySuggestionHideTimer();
    inventorySuggestionHideTimer = window.setTimeout(() => {
      inventorySuggestionHideTimer = null;
      hideInventorySuggestions();
    }, 120);
  };
  const queueHideInventoryComponentSuggestions = () => {
    clearInventoryComponentSuggestionHideTimer();
    inventoryComponentSuggestionHideTimer = window.setTimeout(() => {
      inventoryComponentSuggestionHideTimer = null;
      hideInventoryComponentSuggestions();
    }, 120);
  };
  const inventorySuggestionPool = [
    ...inventoryRows.map((item) => ({
      key: `inventory-${item._inventoryIndex}`,
      source: "inventory",
      sourceLabel: item.item_type ? String(item.item_type).toLowerCase() : "inventory",
      inventoryIndex: item._inventoryIndex,
      partName: item.part_name || "",
      serialNumber: item.serial_number || "",
      component: item.component || "Tower Parts",
      supplier: item.supplier || "",
      itemType: item.item_type || "Part",
      location: item.location || "",
      minLevel: formatInventoryFormQuantity(item.min_level),
      quantity: formatInventoryFormQuantity(item.quantity),
      notes: item.notes || "",
      meta: [item.item_type || "Part", item.component || "Tower Parts", item.supplier || "", item.location || "No location", item.serial_number ? `SN ${item.serial_number}` : ""].filter(Boolean).join(" · "),
    })),
    ...orders.map((item, index) => ({
      key: `order-${index}`,
      source: "order",
      sourceLabel: "order",
      inventoryIndex: "",
      partName: item.part_name || "",
      serialNumber: item.serial_number || "",
      component: item.maintenance_component || item.project || item.company || "Tower Parts",
      supplier: item.company || "",
      itemType: "Part",
      location: "",
      minLevel: "0",
      quantity: "1",
      notes: item.details || item.maintenance_task || "",
      meta: ["Part", item.maintenance_component || item.project || item.company || "General", item.company || "", item.serial_number ? `SN ${item.serial_number}` : "", item.status || "Part order"].filter(Boolean).join(" · "),
    })),
  ];
  const inventoryComponentPool = Array.from(
    new Set(
      [
        ...inventoryRows.map((item) => item.component),
        ...orders.map((item) => item.maintenance_component || item.project || item.company),
        ...((partsData.inventory?.pressure_series || []).map((item) => item.label)),
        "Tower Parts",
        "General Tools",
        "Consumables",
      ].filter(Boolean),
    ),
  )
    .sort((a, b) => String(a).localeCompare(String(b)))
    .map((label) => {
      const normalizedLabel = normalizeLookupText(label);
      const inventoryCount = inventoryRows.filter((item) => normalizeLookupText(item.component) === normalizedLabel).length;
      const orderCount = orders.filter((item) => normalizeLookupText(item.maintenance_component || item.project || item.company) === normalizedLabel).length;
      const meta = [
        "Component",
        inventoryCount ? `${inventoryCount} stock row${inventoryCount === 1 ? "" : "s"}` : "",
        orderCount ? `${orderCount} order ref${orderCount === 1 ? "" : "s"}` : "",
      ].filter(Boolean).join(" · ");
      return {
        key: `component-${normalizedLabel || label}`,
        label,
        meta,
      };
    });
  const scoreInventorySuggestion = (entry, query) => Math.max(
    scoreLookupMatch(entry.partName, query) + 28,
    scoreLookupMatch(entry.serialNumber, query) + 22,
    scoreLookupMatch(entry.component, query) + 24,
    scoreLookupMatch(entry.supplier, query) + 20,
    scoreLookupMatch(entry.itemType, query) + 20,
    scoreLookupMatch(entry.location, query) + 18,
    scoreLookupMatch(entry.meta, query) + 16,
    scoreLookupMatch(entry.notes, query) + 10,
  );
  const applyInventorySuggestion = (entry) => {
    if (!entry) return;
    clearInventorySuggestionHideTimer();
    const mode = inventoryModeField?.value || "add";
    if (mode === "edit" && entry.inventoryIndex) {
      setInventoryFieldValue("inventoryEditIndex", entry.inventoryIndex);
      fillInventoryEditRow(entry.inventoryIndex);
      hideInventorySuggestions();
      return;
    }
    setInventoryFieldValue("partName", entry.partName);
    if (entry.serialNumber) setInventoryFieldValue("serialNumber", entry.serialNumber);
    if (entry.component) setInventoryFieldValue("component", entry.component);
    if (entry.supplier) setInventoryFieldValue("supplier", entry.supplier);
    if (entry.itemType) setInventoryFieldValue("itemType", entry.itemType);
    if (entry.location) setInventoryFieldValue("location", entry.location);
    if (entry.minLevel) setInventoryFieldValue("minLevel", entry.minLevel);
    const notesField = inventoryForm?.elements.namedItem("notes");
    if (notesField && !String(notesField.value || "").trim() && entry.notes) {
      setInventoryFieldValue("notes", entry.notes);
    }
    hideInventorySuggestions();
  };
  const applyInventoryComponentSuggestion = (entry) => {
    if (!entry) return;
    clearInventoryComponentSuggestionHideTimer();
    setInventoryFieldValue("component", entry.label || "");
    hideInventoryComponentSuggestions();
    if ((inventoryModeField?.value || "add") !== "new" && inventorySmartInput && normalizeLookupText(inventorySmartInput.value)) {
      renderInventorySuggestions();
    }
  };
  const renderInventorySuggestions = () => {
    if (!inventorySmartInput || !inventorySuggestionRoot) return;
    const mode = inventoryModeField?.value || "add";
    if (mode === "new") {
      hideInventorySuggestions();
      return;
    }
    const query = normalizeLookupText(inventorySmartInput.value);
    const componentFilter = normalizeLookupText(inventoryComponentInput?.value);
    const filteredPool = inventorySuggestionPool.filter((entry) => {
      if (mode === "edit" && entry.source !== "inventory") return false;
      if (!componentFilter) return true;
      return normalizeLookupText(entry.component).includes(componentFilter);
    });
    if (!query && !componentFilter) {
      hideInventorySuggestions();
      return;
    }
    const matches = (query
      ? filteredPool
          .map((entry) => ({ entry, score: scoreInventorySuggestion(entry, query) }))
          .filter((item) => item.score > 0)
          .sort((a, b) => b.score - a.score || a.entry.partName.localeCompare(b.entry.partName))
      : filteredPool
          .map((entry) => ({ entry, score: 0 }))
          .sort((a, b) => a.entry.partName.localeCompare(b.entry.partName)))
      .slice(0, 7);
    if (!matches.length) {
      hideInventorySuggestions();
      return;
    }
    inventorySuggestionMap.clear();
    inventorySuggestionRoot.hidden = false;
    inventorySuggestionRoot.innerHTML = matches
      .map(({ entry }, index) => {
        const token = `${entry.key}-${index}`;
        inventorySuggestionMap.set(token, entry);
        return `
          <button class="maintenance-parts-suggestion" type="button" data-parts-inventory-suggestion="${escapeHtml(token)}">
            <span class="maintenance-parts-suggestion-copy">
              <strong>${escapeHtml(entry.partName || "Unnamed part")}</strong>
              <span>${escapeHtml(entry.meta || "No extra details")}</span>
            </span>
            <em>${escapeHtml(entry.sourceLabel)}</em>
          </button>
        `;
      })
      .join("");
  };
  const renderInventoryComponentSuggestions = () => {
    if (!inventoryComponentInput || !inventoryComponentSuggestionRoot) return;
    const mode = inventoryModeField?.value || "add";
    if (mode !== "new") {
      hideInventoryComponentSuggestions();
      return;
    }
    const query = normalizeLookupText(inventoryComponentInput.value);
    const matches = (query
      ? inventoryComponentPool
          .map((entry) => ({ entry, score: scoreLookupMatch(entry.label, query) }))
          .filter((item) => item.score > 0)
          .sort((a, b) => b.score - a.score || a.entry.label.localeCompare(b.entry.label))
      : inventoryComponentPool
          .map((entry) => ({ entry, score: 0 }))
          .sort((a, b) => a.entry.label.localeCompare(b.entry.label)))
      .slice(0, 10);
    if (!matches.length) {
      hideInventoryComponentSuggestions();
      return;
    }
    inventoryComponentSuggestionMap.clear();
    inventoryComponentSuggestionRoot.hidden = false;
    inventoryComponentSuggestionRoot.innerHTML = matches
      .map(({ entry }, index) => {
        const token = `${entry.key}-${index}`;
        inventoryComponentSuggestionMap.set(token, entry);
        return `
          <button class="maintenance-parts-suggestion parts-inventory-component-suggestion" type="button" data-parts-inventory-component-suggestion="${escapeHtml(token)}">
            <span class="maintenance-parts-suggestion-copy">
              <strong>${escapeHtml(entry.label || "Unnamed component")}</strong>
              <span>${escapeHtml(entry.meta || "Component")}</span>
            </span>
          </button>
        `;
      })
      .join("");
  };
  const fillInventoryEditRow = (indexValue) => {
    const row = inventoryRows.find((item) => item._inventoryIndex === String(indexValue));
    if (!row) return;
    setInventoryFieldValue("partName", row.part_name || "");
    setInventoryFieldValue("serialNumber", row.serial_number || "");
    setInventoryFieldValue("quantity", formatInventoryFormQuantity(row.quantity));
    setInventoryFieldValue("component", row.component || "Tower Parts");
    setInventoryFieldValue("supplier", row.supplier || "");
    setInventoryFieldValue("itemType", row.item_type || "Part");
    setInventoryFieldValue("location", row.location || "");
    setInventoryFieldValue("minLevel", formatInventoryFormQuantity(row.min_level));
    setInventoryFieldValue("notes", row.notes || "");
  };
  const syncInventoryWorkbench = () => {
    if (!inventoryForm) return;
    const mode = inventoryModeField?.value || "add";
    inventoryEditPick?.classList.toggle("is-hidden", mode !== "edit");
    if (inventorySmartInput) {
      inventorySmartInput.placeholder = mode === "new"
        ? "Enter new part name..."
        : "Search part / serial / component / tool / location...";
    }
    if (inventoryComponentInput) {
      inventoryComponentInput.placeholder = mode === "new"
        ? "Choose existing component..."
        : "Component";
    }
    if (inventorySubmitButton) {
      inventorySubmitButton.textContent = mode === "edit"
        ? "Save Inventory Row"
        : mode === "new"
          ? "Create Inventory Row"
          : mode === "use"
            ? "Use Stock"
            : "Add Stock";
    }
    const quantityField = inventoryForm.elements.namedItem("quantity");
    if (quantityField) quantityField.min = mode === "edit" ? "0" : "0.01";
    if (mode === "edit") {
      if (!inventoryEditIndexField?.value && inventoryRows.length) {
        setInventoryFieldValue("inventoryEditIndex", inventoryRows[0]._inventoryIndex);
      }
      if (inventoryEditIndexField?.value) fillInventoryEditRow(inventoryEditIndexField.value);
    } else if (mode === "new") {
      setInventoryFieldValue("partName", "");
      setInventoryFieldValue("serialNumber", "");
      setInventoryFieldValue("quantity", "1");
      setInventoryFieldValue("component", "");
      setInventoryFieldValue("supplier", "");
      setInventoryFieldValue("itemType", "Part");
      setInventoryFieldValue("location", "");
      setInventoryFieldValue("minLevel", "0");
      setInventoryFieldValue("notes", "");
      setInventoryFieldValue("inventoryEditIndex", "");
    }
    hideInventorySuggestions();
    hideInventoryComponentSuggestions();
  };
  inventoryModeField?.addEventListener("change", syncInventoryWorkbench);
  inventoryEditIndexField?.addEventListener("change", () => {
    if (inventoryEditIndexField.value) fillInventoryEditRow(inventoryEditIndexField.value);
  });
  inventorySmartInput?.addEventListener("input", renderInventorySuggestions);
  inventorySmartInput?.addEventListener("focus", renderInventorySuggestions);
  inventorySmartInput?.addEventListener("blur", queueHideInventorySuggestions);
  inventoryComponentInput?.addEventListener("input", () => {
    renderInventoryComponentSuggestions();
    if ((document.activeElement === inventorySmartInput) || normalizeLookupText(inventorySmartInput?.value)) {
      renderInventorySuggestions();
    } else {
      hideInventorySuggestions();
    }
  });
  inventoryComponentInput?.addEventListener("focus", renderInventoryComponentSuggestions);
  inventoryComponentInput?.addEventListener("blur", queueHideInventoryComponentSuggestions);
  inventorySuggestionRoot?.addEventListener("mouseenter", clearInventorySuggestionHideTimer);
  inventorySuggestionRoot?.addEventListener("mouseleave", queueHideInventorySuggestions);
  inventorySuggestionRoot?.addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest("[data-parts-inventory-suggestion]") : null;
    if (!button) return;
    const entry = inventorySuggestionMap.get(button.dataset.partsInventorySuggestion || "");
    applyInventorySuggestion(entry || null);
  });
  inventoryComponentSuggestionRoot?.addEventListener("mouseenter", clearInventoryComponentSuggestionHideTimer);
  inventoryComponentSuggestionRoot?.addEventListener("mouseleave", queueHideInventoryComponentSuggestions);
  inventoryComponentSuggestionRoot?.addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest("[data-parts-inventory-component-suggestion]") : null;
    if (!button) return;
    const entry = inventoryComponentSuggestionMap.get(button.dataset.partsInventoryComponentSuggestion || "");
    applyInventoryComponentSuggestion(entry || null);
  });
  syncInventoryWorkbench();

  inventoryForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = Object.fromEntries(new FormData(inventoryForm).entries());
      const result = await postJson("/api/parts/inventory-stock", payload);
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      const actions = inventoryForm.querySelector(".parts-form-actions");
      if (actions) actions.dataset.error = error.message;
    }
  });

  unmountForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const formData = new FormData(unmountForm);
      const [partName = "", serialNumber = ""] = String(formData.get("mountedPick") || "").split("||");
      const result = await postJson("/api/parts/unmount", {
        partName,
        serialNumber,
        quantity: formData.get("quantity"),
      });
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      const actions = unmountForm.querySelector(".parts-form-actions");
      if (actions) actions.dataset.error = error.message;
    }
  });

  const manualBrowser = document.getElementById("parts-manual-browser");
  if (manualBrowser) {
    const inventoryRows = (partsData.inventory?.inventory_rows || []).map((item, index) => ({
      ...item,
      _lookupKey: `inventory-${index}`,
      _lookupText: normalizeLookupText([
        item.part_name,
        item.serial_number,
        item.component,
        item.location,
        item.location_serial,
        item.notes,
      ].join(" ")),
    }));
    const inventoryRowsByPartName = new Map();
    const inventoryRowsBySerial = new Map();
    const addInventoryLookupEntry = (lookupMap, key, row) => {
      if (!key) return;
      const current = lookupMap.get(key) || [];
      current.push(row);
      lookupMap.set(key, current);
    };
    const formatInventoryQuantity = (value) => {
      const numeric = Number(value || 0);
      if (!Number.isFinite(numeric)) return "0";
      return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(1).replace(/\.0$/, "");
    };
    inventoryRows.forEach((row) => {
      addInventoryLookupEntry(inventoryRowsByPartName, normalizeLookupText(row.part_name), row);
      addInventoryLookupEntry(inventoryRowsBySerial, normalizeLookupText(row.serial_number), row);
    });
    const summarizeManualRowInventoryStatus = (row) => {
      const candidateKeys = [normalizeLookupText(row.part), normalizeLookupText(row.part_number)].filter(Boolean);
      const seen = new Set();
      const matches = [];
      candidateKeys.forEach((key) => {
        [...(inventoryRowsByPartName.get(key) || []), ...(inventoryRowsBySerial.get(key) || [])].forEach((item) => {
          if (seen.has(item._lookupKey)) return;
          seen.add(item._lookupKey);
          matches.push(item);
        });
      });
      const mountedRows = matches.filter((item) => normalizeLookupText(item.location) === "mounted" && Number(item.quantity || 0) > 0);
      const storedRows = matches.filter((item) => normalizeLookupText(item.location) !== "mounted" && Number(item.quantity || 0) > 0 && normalizeLookupText(item.location));
      const mountedQuantity = mountedRows.reduce((sum, item) => sum + Number(item.quantity || 0), 0);
      const mountedComponents = Array.from(new Set(mountedRows.map((item) => item.component).filter(Boolean)));
      return {
        mounted: mountedRows.length
          ? {
            quantityLabel: formatInventoryQuantity(mountedQuantity),
            componentLabel: mountedComponents.join(" · ") || "tower",
          }
          : null,
        stored: storedRows.slice(0, 2).map((item) => ({
          locationLabel: [item.location, item.location_serial].filter(Boolean).join(" · "),
          quantityLabel: formatInventoryQuantity(item.quantity),
        })),
        extraStoredCount: Math.max(0, storedRows.length - 2),
      };
    };
    const defaultManualRenderMode = String(partsData.manual_lookup?.render_mode || "image");
    const manualSupportsPageImage = () => String(manualState.index?.render_mode || defaultManualRenderMode || "image") === "image";
    const preferredManualViewMode = () => (manualSupportsPageImage() ? "page" : "full");
    const manualState = {
      loading: true,
      error: "",
      mode: "part",
      query: "",
      manual: "",
      page: 1,
      viewMode: defaultManualRenderMode === "image" ? "page" : "full",
      zoom: 1,
      panX: 0,
      panY: 0,
      pageViewKey: "",
      dragPointerId: null,
      dragOriginX: 0,
      dragOriginY: 0,
      dragStartPanX: 0,
      dragStartPanY: 0,
      activeMatchKey: "",
      index: null,
      queuedPagePrefetches: new Set(),
      priorityQueuedPagePrefetches: new Set(),
      prefetchRequestsInFlight: new Set(),
    };
    const modeButtonsRoot = Array.from(manualBrowser.querySelectorAll("[data-parts-manual-mode]"));
    const searchInput = manualBrowser.querySelector("#parts-manual-search");
    const searchWrap = manualBrowser.querySelector(".parts-manual-search-wrap");
    const manualSelect = manualBrowser.querySelector("#parts-manual-select");
    const inventoryResultsRoot = manualBrowser.querySelector("#parts-manual-inventory-results");
    const manualResultsRoot = manualBrowser.querySelector("#parts-manual-match-results");
    const manualListRoot = manualBrowser.querySelector("#parts-manual-list");
    const supportRoot = manualBrowser.querySelector(".parts-manual-support");
    const inventoryPanel = manualBrowser.querySelector('[data-parts-manual-panel="inventory"]');
    const manualHitsPanel = manualBrowser.querySelector('[data-parts-manual-panel="manual-hits"]');
    const catalogPanel = manualBrowser.querySelector('[data-parts-manual-panel="catalog"]');
    const manualFocusWrap = manualBrowser.querySelector('[data-parts-manual-panel="manual-focus"]');
    const resultsKicker = manualBrowser.querySelector("#parts-manual-results-kicker");
    const resultsHeading = manualBrowser.querySelector("#parts-manual-results-heading");
    const viewerTitle = manualBrowser.querySelector("#parts-manual-viewer-title");
    const viewerMeta = manualBrowser.querySelector("#parts-manual-viewer-meta");
    const pageStatus = manualBrowser.querySelector("#parts-manual-page-status");
    const viewerSection = manualBrowser.querySelector(".parts-manual-viewer");
    const viewerFrameShell = manualBrowser.querySelector("#parts-manual-frame-shell");
    const pageShell = manualBrowser.querySelector(".parts-manual-page-shell");
    const pageTitle = manualBrowser.querySelector("#parts-manual-page-title");
    const pageResultsRoot = manualBrowser.querySelector("#parts-manual-page-results");
    const prevButton = manualBrowser.querySelector("#parts-manual-prev");
    const nextButton = manualBrowser.querySelector("#parts-manual-next");
    const zoomOutButton = manualBrowser.querySelector("#parts-manual-zoom-out");
    const zoomInButton = manualBrowser.querySelector("#parts-manual-zoom-in");
    const zoomResetButton = manualBrowser.querySelector("#parts-manual-zoom-reset");
    const zoomStatus = manualBrowser.querySelector("#parts-manual-zoom-status");
    const openDocLink = manualBrowser.querySelector("#parts-manual-open-doc");
    const pageStripRoot = manualBrowser.querySelector("#parts-manual-page-strip");
    const manualsMetric = manualBrowser.querySelector("#parts-manual-metric-manuals");
    const indexedRowsMetric = manualBrowser.querySelector("#parts-manual-metric-rows");
    const MANUAL_ZOOM_BUTTON_STEP = 0.12;
    const clampManualZoom = (value) => Math.min(2.4, Math.max(0.7, Number(value || 1)));
    const canDragManualPage = () => manualState.viewMode === "page" && clampManualZoom(manualState.zoom) > 1.02;
    const clampManualPan = () => {
      if (!viewerFrameShell) return;
      const maxPanX = Math.max(0, viewerFrameShell.scrollWidth - viewerFrameShell.clientWidth);
      const maxPanY = Math.max(0, viewerFrameShell.scrollHeight - viewerFrameShell.clientHeight);
      manualState.panX = Math.min(maxPanX, Math.max(0, Number(manualState.panX || 0)));
      manualState.panY = Math.min(maxPanY, Math.max(0, Number(manualState.panY || 0)));
    };
    const syncManualPanFromShell = () => {
      if (!viewerFrameShell || manualState.viewMode !== "page") return;
      manualState.panX = viewerFrameShell.scrollLeft;
      manualState.panY = viewerFrameShell.scrollTop;
    };
    const applyManualPanToShell = () => {
      if (!viewerFrameShell || manualState.viewMode !== "page") return;
      clampManualPan();
      viewerFrameShell.scrollLeft = manualState.panX;
      viewerFrameShell.scrollTop = manualState.panY;
    };
    const endManualPageDrag = () => {
      if (viewerFrameShell && manualState.dragPointerId != null) {
        try {
          viewerFrameShell.releasePointerCapture(manualState.dragPointerId);
        } catch (error) {
          // Ignore pointer capture release errors if the pointer is already gone.
        }
      }
      manualState.dragPointerId = null;
    };
    const refreshManualPanAffordance = () => {
      if (!viewerFrameShell) return;
      const canPan = canDragManualPage()
        && (viewerFrameShell.scrollWidth - viewerFrameShell.clientWidth > 8
          || viewerFrameShell.scrollHeight - viewerFrameShell.clientHeight > 8);
      viewerFrameShell.classList.toggle("can-pan", canPan);
      viewerFrameShell.classList.toggle("is-dragging", manualState.dragPointerId != null);
    };
    const buildManualPageImageUrl = (manual, pageNumber) => {
      if (!manual) return "";
      return `/api/maintenance/manual-page?path=${encodeURIComponent(manual.file_name || manual.name)}&page=${Number(pageNumber || 1)}`;
    };
    const buildManualPagePrefetchKey = (manual, pageNumber) => {
      if (!manual) return "";
      return `${manual.file_name || manual.name}::${Number(pageNumber || 1)}`;
    };
    const buildManualPagePrefetchPlan = (indexedPages, currentPage) => {
      const current = Number(currentPage || 1);
      const prioritizedIndexedPages = Array.from(new Set(indexedPages.map((pageNumber) => Number(pageNumber || 0)).filter((pageNumber) => pageNumber > 0)))
        .sort((left, right) => {
          const distanceGap = Math.abs(left - current) - Math.abs(right - current);
          if (distanceGap !== 0) return distanceGap;
          return left - right;
        });
      return Array.from(new Set([current, current - 1, current + 1, ...prioritizedIndexedPages].filter((pageNumber) => pageNumber > 0)));
    };
    const queueManualPagePrefetch = (manual, pageNumbers, { immediate = false, priority = false } = {}) => {
      if (!manual) return;
      const queuedKeys = priority ? manualState.priorityQueuedPagePrefetches : manualState.queuedPagePrefetches;
      const uniquePages = Array.from(
        new Set(
          (pageNumbers || [])
            .map((pageNumber) => Number(pageNumber || 0))
            .filter((pageNumber) => pageNumber > 0),
        ),
      ).slice(0, 24);
      const pendingPages = uniquePages.filter((pageNumber) => {
        const key = buildManualPagePrefetchKey(manual, pageNumber);
        return key && !queuedKeys.has(key);
      });
      if (!pendingPages.length) return;
      const pendingKeys = pendingPages.map((pageNumber) => buildManualPagePrefetchKey(manual, pageNumber)).filter(Boolean);
      pendingKeys.forEach((key) => queuedKeys.add(key));
      const requestKey = `${priority ? "priority" : "normal"}::${manual.file_name || manual.name}::${pendingPages.join(",")}`;
      if (manualState.prefetchRequestsInFlight.has(requestKey)) return;
      manualState.prefetchRequestsInFlight.add(requestKey);
      const requestUrl = `/api/maintenance/manual-prefetch?path=${encodeURIComponent(manual.file_name || manual.name)}&pages=${pendingPages.join(",")}${priority ? "&priority=1" : ""}`;
      const runRequest = () => {
        void fetch(requestUrl, { cache: "no-store", keepalive: true })
          .catch(() => {
            pendingKeys.forEach((key) => queuedKeys.delete(key));
          })
          .finally(() => {
            manualState.prefetchRequestsInFlight.delete(requestKey);
          });
      };
      if (immediate) {
        runRequest();
        return;
      }
      if ("requestIdleCallback" in window) {
        window.requestIdleCallback(runRequest, { timeout: 350 });
      } else {
        window.setTimeout(runRequest, 60);
      }
    };

    const manualMatchKey = (item) => `${item.manual}::${item.page}::${item.item || item.part_number || item.part}`;
    const getManuals = () => manualState.index?.manuals || [];
    const getRows = () => manualState.index?.rows || [];

    const getManualByName = (name) => getManuals().find((item) => item.name === name) || null;
    const getManualIndexedPages = (manualName) => Array.from(
      new Set(
        getRows()
          .filter((row) => row.manual === manualName)
          .map((row) => Number(row.page || 0))
          .filter((page) => page > 0),
      ),
    ).sort((left, right) => left - right);
    const getDefaultManualPage = (manualName) => {
      const manual = getManualByName(manualName);
      const indexedPages = getManualIndexedPages(manual?.name || "");
      return Number(indexedPages[0] || manual?.bom_pages?.[0] || 1);
    };
    const scrollViewerIntoView = () => {
      viewerSection?.scrollIntoView({ behavior: "smooth", block: "start" });
    };

    const getManualMatchScore = (row, query) => {
      if (!query) return 0;
      return Math.max(
        scoreLookupMatch(row.part, query),
        scoreLookupMatch(row.part_number, query),
        scoreLookupMatch(row.raw_line, query),
        scoreLookupMatch(partsManualDisplayName(row.manual), query),
      );
    };

    const getInventoryMatchScore = (row, query) => {
      if (!query) return 0;
      return Math.max(
        scoreLookupMatch(row.part_name, query),
        scoreLookupMatch(row.serial_number, query),
        scoreLookupMatch(row.component, query),
        scoreLookupMatch(row.location, query),
        scoreLookupMatch(row.location_serial, query),
        scoreLookupMatch(row.notes, query),
      );
    };

    const deriveManualBrowserState = () => {
      const manuals = getManuals();
      const rows = getRows();
      const query = normalizeLookupText(manualState.query);
      const isManualMode = manualState.mode === "manual";
      const manualRows = isManualMode && manualState.manual ? rows.filter((row) => row.manual === manualState.manual) : rows;
      const inventoryMatches = query
        ? inventoryRows
          .map((row) => ({ row, score: getInventoryMatchScore(row, query) }))
          .filter((item) => item.score > 0)
          .sort((left, right) => right.score - left.score || String(left.row.part_name || "").localeCompare(String(right.row.part_name || "")))
          .slice(0, 8)
        : [];
      const manualMatches = query
        ? manualRows
          .map((row) => ({ row, score: getManualMatchScore(row, query) }))
          .filter((item) => item.score > 0)
          .sort((left, right) => right.score - left.score || Number(left.row.page || 0) - Number(right.row.page || 0))
          .slice(0, 12)
        : [];
      const matchedCountByManual = new Map();
      if (query) {
        rows.forEach((row) => {
          if (getManualMatchScore(row, query) > 0) {
            matchedCountByManual.set(row.manual, (matchedCountByManual.get(row.manual) || 0) + 1);
          }
        });
      }
      const selectedManual = getManualByName(manualState.manual) || (isManualMode ? manuals[0] || null : null);
      const maxPages = Math.max(1, Number(selectedManual?.pages || 1));
      const defaultPage = selectedManual ? getDefaultManualPage(selectedManual.name) : 1;
      const currentPage = Math.min(maxPages, Math.max(1, Number(manualState.page || defaultPage)));
      const selectedManualRows = selectedManual ? rows.filter((row) => row.manual === selectedManual.name) : [];
      const pageRows = selectedManual
        ? selectedManualRows.filter((row) => Number(row.page || 0) === currentPage)
        : [];
      const indexedPages = selectedManual ? getManualIndexedPages(selectedManual.name) : [];
      const pageGroups = indexedPages.map((pageNumber) => {
        const rowsOnPage = selectedManualRows.filter((row) => Number(row.page || 0) === Number(pageNumber));
        const matchedCount = query ? rowsOnPage.filter((row) => getManualMatchScore(row, query) > 0).length : 0;
        return { pageNumber, rows: rowsOnPage, matchedCount };
      });
      return {
        query,
        manuals,
        selectedManual,
        currentPage,
        inventoryMatches,
        manualMatches,
        matchedCountByManual,
        pageRows,
        indexedPages,
        pageGroups,
        };
    };

    const applyManualSelection = (manualName, page = null, activeMatchKey = "", revealViewer = false) => {
      const manual = getManualByName(manualName) || (manualState.mode === "manual" ? getManuals()[0] || null : null);
      manualState.manual = manual?.name || "";
      manualState.page = manual ? Number(page || getDefaultManualPage(manual.name || "")) : 1;
      manualState.viewMode = preferredManualViewMode();
      manualState.activeMatchKey = activeMatchKey || "";
      renderManualBrowser();
      if (revealViewer) scrollViewerIntoView();
    };

    const openManualMatch = (row) => {
      if (!row) return;
      manualState.manual = row.manual;
      manualState.page = Number(row.page || 1);
      manualState.viewMode = preferredManualViewMode();
      manualState.activeMatchKey = manualMatchKey(row);
      renderManualBrowser();
      scrollViewerIntoView();
    };

    const renderManualBrowser = () => {
      const derived = deriveManualBrowserState();
      const { query, manuals, selectedManual, currentPage, inventoryMatches, manualMatches, matchedCountByManual, pageRows, indexedPages, pageGroups } = derived;
      const isPartMode = manualState.mode === "part";
      const hasManualSelection = Boolean(selectedManual);
      const currentPageViewKey = selectedManual && manualState.viewMode === "page"
        ? `${selectedManual.file_name || selectedManual.name}::${currentPage}`
        : "";
      if (currentPageViewKey !== manualState.pageViewKey) {
        manualState.pageViewKey = currentPageViewKey;
        manualState.panX = 0;
        manualState.panY = 0;
        endManualPageDrag();
      }
      manualState.manual = selectedManual?.name || "";
      manualState.page = currentPage;
      manualBrowser.classList.toggle("is-part-mode", isPartMode);
      manualBrowser.classList.toggle("is-manual-mode", !isPartMode);
      manualBrowser.classList.toggle("has-manual-selection", hasManualSelection);
      manualBrowser.classList.toggle("is-page-view", hasManualSelection && manualState.viewMode === "page");
      manualBrowser.classList.toggle("is-full-view", hasManualSelection && manualState.viewMode !== "page");
      modeButtonsRoot.forEach((button) => {
        button.classList.toggle("is-active", button.dataset.partsManualMode === manualState.mode);
      });
      if (manualsMetric) manualsMetric.textContent = String(manualState.index?.totals?.manual_count || manuals.length || 0);
      if (indexedRowsMetric) indexedRowsMetric.textContent = String(manualState.index?.totals?.row_count || getRows().length || 0);
      if (searchInput && searchInput.value !== manualState.query) searchInput.value = manualState.query;
      if (searchInput) {
        searchInput.placeholder = isPartMode
          ? "Search part / part number / serial / component / location..."
          : "Search indexed part names or numbers inside the selected manual...";
      }
      if (supportRoot) supportRoot.hidden = !isPartMode;
      if (manualHitsPanel) manualHitsPanel.hidden = !isPartMode;
      if (inventoryPanel) inventoryPanel.hidden = !isPartMode;
      if (searchWrap) searchWrap.hidden = !isPartMode;
      if (manualFocusWrap) manualFocusWrap.hidden = isPartMode;
      if (catalogPanel) catalogPanel.hidden = isPartMode;
      if (resultsKicker) resultsKicker.textContent = isPartMode ? "Filtered parts" : "Indexed pages";
      if (resultsHeading) resultsHeading.textContent = isPartMode ? "Pick a result to open its page" : "Pages with parts";
      if (manualSelect) {
        manualSelect.innerHTML = [
          `<option value="">All manuals</option>`,
          ...manuals.map((manual) => `<option value="${escapeHtml(manual.name || "")}">${escapeHtml(partsManualDisplayName(manual.name))}</option>`),
        ].join("");
        manualSelect.value = manualState.manual || "";
      }
      if (inventoryResultsRoot) {
        inventoryResultsRoot.innerHTML = query
          ? (inventoryMatches.length
            ? inventoryMatches.map((item) => partsManualInventoryResultMarkup(item.row)).join("")
            : `<div class="chart-empty">No live inventory hits for this search yet.</div>`)
          : `<div class="chart-empty">Search a part first, then use the live inventory hit when you want the storage place or stock detail beside the manual match.</div>`;
      }
      if (manualResultsRoot) {
        if (manualState.loading) {
          manualResultsRoot.innerHTML = `<div class="chart-empty">Loading the manual index…</div>`;
        } else if (manualState.error) {
          manualResultsRoot.innerHTML = `<div class="chart-empty">${escapeHtml(manualState.error)}</div>`;
        } else if (manualState.mode === "part") {
          manualResultsRoot.innerHTML = query
            ? (manualMatches.length
              ? manualMatches.map((item) => partsManualMatchResultMarkup(item.row, manualState.activeMatchKey)).join("")
              : `<div class="chart-empty">No manual rows matched this part search.</div>`)
            : `<div class="chart-empty">Search a part name, number, serial, or component, then choose a filtered result to open its PDF page.</div>`;
        } else {
          const visiblePageGroups = query
            ? pageGroups.filter((group) => group.matchedCount > 0)
            : pageGroups;
          manualResultsRoot.innerHTML = visiblePageGroups.length
            ? visiblePageGroups.map((group) => partsManualPageSummaryMarkup(group.pageNumber, group.rows, currentPage, group.matchedCount)).join("")
            : `<div class="chart-empty">No indexed pages matched this manual search. Try a part number or switch back to part mode.</div>`;
        }
      }
      if (manualListRoot) {
        if (manualState.loading) {
          manualListRoot.innerHTML = `<div class="chart-empty">Loading manuals…</div>`;
        } else if (!manuals.length) {
          manualListRoot.innerHTML = `<div class="chart-empty">No manual PDFs were found for this tower workspace.</div>`;
        } else {
          manualListRoot.innerHTML = manuals
            .map((manual) => partsManualDocumentItemMarkup(manual, manual.name === manualState.manual, matchedCountByManual.get(manual.name) || 0))
            .join("");
        }
      }
      if (viewerTitle) {
        viewerTitle.textContent = selectedManual
          ? partsManualDisplayName(selectedManual.name)
          : (isPartMode ? "Search a part, then open its manual page" : "Choose a manual to browse");
      }
      if (viewerMeta) {
        viewerMeta.textContent = selectedManual
          ? `${selectedManual.row_count || 0} indexed rows · ${indexedPages.length} indexed pages · ${selectedManual.pages || 0} pages${query ? ` · ${manualMatches.length} smart hits` : ""}${manualSupportsPageImage() ? "" : " · PDF viewer mode"}`
          : (isPartMode
            ? "Part to manual starts with search. Open a matching manual hit and the exact indexed page will take the full viewer width here."
            : "Manual to parts keeps the document in focus. Move page by page through indexed pages and read the rows under the current page.");
      }
      if (openDocLink) {
        if (selectedManual) {
          openDocLink.href = `/api/maintenance/manual?path=${encodeURIComponent(selectedManual.file_name || selectedManual.name)}#page=${currentPage}`;
          openDocLink.removeAttribute("aria-disabled");
        } else {
          openDocLink.href = "#";
          openDocLink.setAttribute("aria-disabled", "true");
        }
      }
      if (pageStatus) {
        pageStatus.textContent = selectedManual
          ? (manualState.viewMode === "page"
            ? `Page ${currentPage} / ${selectedManual.pages}`
            : `Full manual · p.${currentPage} focus`)
          : "Page —";
      }
      if (zoomStatus) {
        zoomStatus.textContent = `${Math.round(clampManualZoom(manualState.zoom) * 100)}%`;
      }
      if (prevButton) prevButton.disabled = !selectedManual || currentPage <= 1;
      if (nextButton) nextButton.disabled = !selectedManual || currentPage >= Number(selectedManual?.pages || 1);
      if (zoomOutButton) zoomOutButton.disabled = !selectedManual || manualState.viewMode !== "page" || clampManualZoom(manualState.zoom) <= 0.7;
      if (zoomInButton) zoomInButton.disabled = !selectedManual || manualState.viewMode !== "page" || clampManualZoom(manualState.zoom) >= 2.4;
      if (zoomResetButton) zoomResetButton.disabled = !selectedManual || manualState.viewMode !== "page" || Math.abs(clampManualZoom(manualState.zoom) - 1) < 0.01;
      if (pageStripRoot) {
        pageStripRoot.hidden = !selectedManual;
        pageStripRoot.innerHTML = selectedManual
          ? pageGroups.map((group) => partsManualPageChipMarkup(group, currentPage, manualState.viewMode)).join("")
          : `<div class="chart-empty">Indexed pages will appear here when a manual is open.</div>`;
      }
      if (viewerFrameShell) {
        viewerFrameShell.classList.toggle("is-page-mode", Boolean(selectedManual) && manualState.viewMode === "page");
        viewerFrameShell.classList.toggle("is-empty", !selectedManual);
        if (!selectedManual) {
          endManualPageDrag();
          viewerFrameShell.innerHTML = `<div class="chart-empty">${isPartMode ? "Search a part and press a manual hit to render its exact page here." : "Pick a manual or an indexed page to open the viewer here."}</div>`;
        } else if (manualState.viewMode === "page") {
          viewerFrameShell.innerHTML = `<div class="parts-manual-page-canvas"><img class="parts-manual-page-image" draggable="false" style="width:${Math.round(clampManualZoom(manualState.zoom) * 100)}%;" src="${buildManualPageImageUrl(selectedManual, currentPage)}" alt="${escapeHtml(partsManualDisplayName(selectedManual.name))} page ${escapeHtml(String(currentPage))}" /></div>`;
          const pageImage = viewerFrameShell.querySelector(".parts-manual-page-image");
          const finalizePageImage = () => {
            applyManualPanToShell();
            refreshManualPanAffordance();
          };
          if (pageImage) {
            if (pageImage.complete) {
              finalizePageImage();
            } else {
              pageImage.addEventListener("load", finalizePageImage, { once: true });
              pageImage.addEventListener("error", refreshManualPanAffordance, { once: true });
            }
          }
        } else {
          endManualPageDrag();
          viewerFrameShell.innerHTML = `<iframe class="parts-manual-frame" src="/api/maintenance/manual?path=${encodeURIComponent(selectedManual.file_name || selectedManual.name)}#page=${currentPage}&zoom=page-width&pagemode=none&navpanes=0&toolbar=0" title="${escapeHtml(partsManualDisplayName(selectedManual.name))}"></iframe>`;
        }
        if (manualState.viewMode !== "page") {
          manualState.panX = 0;
          manualState.panY = 0;
          refreshManualPanAffordance();
        }
      }
      if (pageTitle) {
        pageTitle.textContent = selectedManual
          ? `${partsManualDisplayName(selectedManual.name)} · page ${currentPage}${pageRows.length ? ` · ${pageRows.length} indexed rows` : ""}`
          : "Rows on the selected page";
      }
      if (pageShell) pageShell.hidden = !selectedManual;
      if (pageResultsRoot) {
        pageResultsRoot.innerHTML = selectedManual
          ? (pageRows.length
            ? pageRows.map((row) => partsManualPageRowMarkup(row, summarizeManualRowInventoryStatus(row))).join("")
            : `<div class="chart-empty">No indexed rows on this manual page yet. Move pages and keep scanning.</div>`)
          : `<div class="chart-empty">Page rows will appear here after you open a manual page.</div>`;
      }
      if (selectedManual && manualState.viewMode === "page") {
        queueManualPagePrefetch(selectedManual, buildManualPagePrefetchPlan(indexedPages, currentPage));
      }
    };

    modeButtonsRoot.forEach((button) => {
      button.addEventListener("click", () => {
        manualState.mode = button.dataset.partsManualMode || "part";
        manualState.activeMatchKey = "";
        if (manualState.mode === "manual" && !manualState.manual) {
          manualState.query = "";
          applyManualSelection("", null, "", false);
          return;
        }
        if (manualState.mode === "part") {
          manualState.manual = "";
          manualState.page = 1;
          manualState.viewMode = preferredManualViewMode();
        } else {
          manualState.query = "";
        }
        renderManualBrowser();
      });
    });

    searchInput?.addEventListener("input", () => {
      manualState.query = searchInput.value || "";
      manualState.activeMatchKey = "";
      if (manualState.mode === "part") {
        manualState.manual = "";
        manualState.page = 1;
        manualState.viewMode = preferredManualViewMode();
      }
      renderManualBrowser();
    });

    manualSelect?.addEventListener("change", () => {
      applyManualSelection(manualSelect.value || "");
    });

    prevButton?.addEventListener("click", () => {
      if (!manualState.manual) return;
      manualState.page = Math.max(1, Number(manualState.page || 1) - 1);
      manualState.viewMode = preferredManualViewMode();
      manualState.activeMatchKey = "";
      renderManualBrowser();
    });

    nextButton?.addEventListener("click", () => {
      const currentManual = getManualByName(manualState.manual);
      if (!currentManual) return;
      manualState.page = Math.min(Number(currentManual.pages || 1), Number(manualState.page || 1) + 1);
      manualState.viewMode = preferredManualViewMode();
      manualState.activeMatchKey = "";
      renderManualBrowser();
    });

    zoomOutButton?.addEventListener("click", () => {
      if (!manualState.manual || manualState.viewMode !== "page") return;
      manualState.zoom = clampManualZoom(clampManualZoom(manualState.zoom) - MANUAL_ZOOM_BUTTON_STEP);
      renderManualBrowser();
    });

    zoomInButton?.addEventListener("click", () => {
      if (!manualState.manual || manualState.viewMode !== "page") return;
      manualState.zoom = clampManualZoom(clampManualZoom(manualState.zoom) + MANUAL_ZOOM_BUTTON_STEP);
      renderManualBrowser();
    });

    zoomResetButton?.addEventListener("click", () => {
      if (!manualState.manual || manualState.viewMode !== "page") return;
      manualState.zoom = 1;
      renderManualBrowser();
    });

    viewerFrameShell?.addEventListener("scroll", () => {
      syncManualPanFromShell();
      refreshManualPanAffordance();
    });

    viewerFrameShell?.addEventListener("pointerdown", (event) => {
      const target = event.target.closest(".parts-manual-page-image, .parts-manual-page-canvas");
      if (!target || event.button !== 0 || !canDragManualPage()) return;
      manualState.dragPointerId = event.pointerId;
      manualState.dragOriginX = event.clientX;
      manualState.dragOriginY = event.clientY;
      manualState.dragStartPanX = viewerFrameShell.scrollLeft;
      manualState.dragStartPanY = viewerFrameShell.scrollTop;
      viewerFrameShell.setPointerCapture(event.pointerId);
      refreshManualPanAffordance();
      event.preventDefault();
    });

    viewerFrameShell?.addEventListener("pointermove", (event) => {
      if (manualState.dragPointerId !== event.pointerId) return;
      manualState.panX = manualState.dragStartPanX - (event.clientX - manualState.dragOriginX);
      manualState.panY = manualState.dragStartPanY - (event.clientY - manualState.dragOriginY);
      applyManualPanToShell();
      refreshManualPanAffordance();
      event.preventDefault();
    });

    viewerFrameShell?.addEventListener("pointerup", (event) => {
      if (manualState.dragPointerId !== event.pointerId) return;
      syncManualPanFromShell();
      endManualPageDrag();
      refreshManualPanAffordance();
    });

    viewerFrameShell?.addEventListener("pointercancel", (event) => {
      if (manualState.dragPointerId !== event.pointerId) return;
      syncManualPanFromShell();
      endManualPageDrag();
      refreshManualPanAffordance();
    });

    viewerFrameShell?.addEventListener("wheel", (event) => {
      const target = event.target.closest(".parts-manual-page-image, .parts-manual-page-canvas");
      if (!target || manualState.viewMode !== "page" || !event.shiftKey) return;
      const currentZoom = clampManualZoom(manualState.zoom);
      const rawDelta = Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX;
      const zoomDelta = Math.max(-0.06, Math.min(0.06, -rawDelta * 0.001));
      const nextZoom = clampManualZoom(currentZoom * (1 + zoomDelta));
      if (Math.abs(nextZoom - currentZoom) < 0.003) return;
      const shellRect = viewerFrameShell.getBoundingClientRect();
      const anchorX = event.clientX - shellRect.left;
      const anchorY = event.clientY - shellRect.top;
      manualState.panX = (viewerFrameShell.scrollLeft + anchorX) * (nextZoom / currentZoom) - anchorX;
      manualState.panY = (viewerFrameShell.scrollTop + anchorY) * (nextZoom / currentZoom) - anchorY;
      manualState.zoom = nextZoom;
      renderManualBrowser();
      event.preventDefault();
    }, { passive: false });

    manualBrowser.addEventListener("click", (event) => {
      const target = event.target.closest("[data-parts-manual-open], [data-parts-manual-pick], [data-parts-manual-fill-query], [data-parts-manual-page]");
      if (!target) return;
      if (target.dataset.partsManualOpen) {
        const key = target.dataset.partsManualOpen;
        const row = getRows().find((item) => manualMatchKey(item) === key);
        if (row) openManualMatch(row);
        return;
      }
      if (target.dataset.partsManualPage) {
        const nextPage = Number(target.dataset.partsManualPage || manualState.page || 1);
        if (!manualSupportsPageImage()) {
          manualState.page = nextPage;
          manualState.viewMode = "full";
        } else if (nextPage === Number(manualState.page || 1) && manualState.viewMode === "page") {
          manualState.viewMode = "full";
        } else {
          manualState.page = nextPage;
          manualState.viewMode = "page";
        }
        manualState.activeMatchKey = "";
        renderManualBrowser();
        scrollViewerIntoView();
        return;
      }
      if (target.dataset.partsManualPick) {
        applyManualSelection(target.dataset.partsManualPick || "", null, "", true);
        return;
      }
      if (target.dataset.partsManualFillQuery) {
        manualState.mode = "part";
        manualState.query = target.dataset.partsManualFillQuery || "";
        manualState.manual = "";
        manualState.page = 1;
        manualState.viewMode = preferredManualViewMode();
        manualState.activeMatchKey = "";
        renderManualBrowser();
      }
    });

    manualBrowser.addEventListener("pointerenter", (event) => {
      const target = event.target.closest("[data-parts-manual-page]");
      const currentManual = getManualByName(manualState.manual);
      if (!target || !currentManual) return;
      queueManualPagePrefetch(currentManual, [target.dataset.partsManualPage], { immediate: true, priority: true });
    }, true);

    manualBrowser.addEventListener("focusin", (event) => {
      const target = event.target.closest("[data-parts-manual-page]");
      const currentManual = getManualByName(manualState.manual);
      if (!target || !currentManual) return;
      queueManualPagePrefetch(currentManual, [target.dataset.partsManualPage], { immediate: true, priority: true });
    });

    renderManualBrowser();
    ensurePartsManualIndex()
      .then((manualIndex) => {
        manualState.index = manualIndex;
        manualState.loading = false;
        manualState.error = "";
        const firstManual = manualIndex.manuals?.[0] || null;
        if (manualState.mode === "manual" && firstManual && !manualState.manual) {
          manualState.manual = firstManual.name;
          manualState.page = getDefaultManualPage(firstManual.name);
          manualState.viewMode = preferredManualViewMode();
        } else if (manualState.mode === "manual" && manualState.manual && !manualState.activeMatchKey && !normalizeLookupText(manualState.query)) {
          manualState.page = getDefaultManualPage(manualState.manual);
          manualState.viewMode = preferredManualViewMode();
        }
        renderManualBrowser();
      })
      .catch((error) => {
        manualState.loading = false;
        manualState.error = error.message || "Manual index failed to load.";
        renderManualBrowser();
      });
  }

  setMode("add");
  if (updateSelect?.value) fillUpdateForm(updateSelect.value);
  persistStageUiState();
  bindStageFlow();
}

function getDashboardXValues(logData, xColumn) {
  const rowCount = logData?.rows?.length || 0;
  const rawSeries = Array.isArray(logData?.x_series?.[xColumn]) ? logData.x_series[xColumn] : [];
  if (rawSeries.length !== rowCount) {
    return Array.from({ length: rowCount }, (_, index) => index);
  }
  const finiteSeries = rawSeries.map((value, index) => Number.isFinite(Number(value)) ? Number(value) : index);
  const min = Math.min(...finiteSeries);
  const max = Math.max(...finiteSeries);
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) {
    return Array.from({ length: rowCount }, (_, index) => index);
  }
  return finiteSeries;
}

function getDashboardCanvasGeometry(logData, canvas, xColumn, axisCount = 1, scaleMode = "independent") {
  const cssWidth = Math.max(320, canvas.clientWidth || canvas.parentElement?.clientWidth || 980);
  const cssHeight = Math.max(320, canvas.clientHeight || 460);
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(cssHeight * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const leftAxisCount = scaleMode === "shared" ? 1 : Math.max(1, Math.ceil(axisCount / 2));
  const rightAxisCount = scaleMode === "shared" ? 0 : Math.max(0, axisCount - leftAxisCount);
  const padding = {
    top: 48,
    right: 24 + rightAxisCount * 74,
    bottom: 44,
    left: 24 + leftAxisCount * 74,
  };
  const plotWidth = cssWidth - padding.left - padding.right;
  const plotHeight = cssHeight - padding.top - padding.bottom;
  const plotLeft = padding.left;
  const plotRight = padding.left + plotWidth;
  const plotTop = padding.top;
  const plotBottom = padding.top + plotHeight;
  const rowCount = logData.rows.length;
  const xValues = getDashboardXValues(logData, xColumn);
  const xMin = Math.min(...xValues);
  const xMax = Math.max(...xValues);
  const xSpan = xMax - xMin || 1;
  const xPixels = xValues.map((value) => plotLeft + ((value - xMin) / xSpan) * plotWidth);
  const leftEdges = xPixels.map((pixel, index) => {
    if (index === 0) return plotLeft;
    return (xPixels[index - 1] + pixel) / 2;
  });
  const rightEdges = xPixels.map((pixel, index) => {
    if (index === rowCount - 1) return plotRight;
    return (pixel + xPixels[index + 1]) / 2;
  });
  return {
    ctx,
    cssWidth,
    cssHeight,
    padding,
    plotWidth,
    plotHeight,
    plotLeft,
    plotRight,
    plotTop,
    plotBottom,
    rowCount,
    xValues,
    xPixels,
    leftEdges,
    rightEdges,
    leftAxisCount,
    rightAxisCount,
  };
}

function dashboardZonePixelBounds(zone, geometry) {
  if (!zone || geometry.rowCount <= 0) return null;
  const a = Math.max(0, Math.min(zone.startIndex, zone.endIndex));
  const b = Math.min(geometry.rowCount - 1, Math.max(zone.startIndex, zone.endIndex));
  const left = geometry.leftEdges[a];
  const right = geometry.rightEdges[b];
  return {
    left,
    width: Math.max(4, right - left),
  };
}

function drawDashboardCanvas(logData, yColumns, zones, canvas, transientBrush = null, xColumn = null, scaleMode = "independent") {
  if (!canvas || !logData?.rows?.length || !yColumns.length) return;
  const geometry = getDashboardCanvasGeometry(logData, canvas, xColumn || logData.suggested_x, yColumns.length, scaleMode);
  canvas.__dashboardGeometry = geometry;
  const { ctx, cssWidth, cssHeight, padding, plotWidth, plotHeight, xPixels } = geometry;
  ctx.clearRect(0, 0, cssWidth, cssHeight);

  const stageGradient = ctx.createLinearGradient(0, 0, 0, cssHeight);
  stageGradient.addColorStop(0, "rgba(6, 18, 30, 0.98)");
  stageGradient.addColorStop(0.55, "rgba(5, 14, 24, 0.95)");
  stageGradient.addColorStop(1, "rgba(3, 8, 14, 0.98)");
  ctx.fillStyle = stageGradient;
  ctx.fillRect(0, 0, cssWidth, cssHeight);

  const axisStroke = "rgba(140, 214, 255, 0.22)";
  const gridStroke = "rgba(114,255,232,0.08)";
  const labelColor = "rgba(223, 248, 255, 0.76)";
  const colors = ["#72ffe8", "#2bd8ff", "#ffd56f", "#ff8c6b", "#9f7bff", "#9afc7a"];
  const displayLabelFor = (column) => logData?.display_labels?.[column] || column;
  const seriesStats = yColumns.map((column) => {
    const seriesValues = logData.rows.map((row) => Number(row[column] ?? 0));
    const min = Math.min(...seriesValues);
    const max = Math.max(...seriesValues);
    return { column, min, max, span: max - min || 1 };
  });
  const allValues = seriesStats.flatMap(({ column }) => logData.rows.map((row) => Number(row[column] ?? 0)));
  const sharedMin = Math.min(...allValues);
  const sharedMax = Math.max(...allValues);
  const sharedSpan = sharedMax - sharedMin || 1;
  const yFor = (value, column) => {
    if (scaleMode === "shared") {
      return padding.top + plotHeight - ((value - sharedMin) / sharedSpan) * plotHeight;
    }
    const stat = seriesStats.find((item) => item.column === column) || { min: 0, span: 1 };
    return padding.top + plotHeight - ((value - stat.min) / stat.span) * plotHeight;
  };
  const xFor = (index) => xPixels[index] ?? padding.left;

  ctx.save();
  for (let i = 0; i <= 4; i += 1) {
    const y = padding.top + (plotHeight / 4) * i;
    ctx.strokeStyle = gridStroke;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(padding.left + plotWidth, y);
    ctx.stroke();
  }
  const verticalStep = Math.max(1, Math.floor(xPixels.length / 8));
  for (let i = 0; i < xPixels.length; i += verticalStep) {
    const x = xPixels[i];
    ctx.beginPath();
    ctx.moveTo(x, padding.top);
    ctx.lineTo(x, padding.top + plotHeight);
    ctx.stroke();
  }
  ctx.restore();

  ctx.save();
  ctx.strokeStyle = axisStroke;
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.moveTo(padding.left, padding.top);
  ctx.lineTo(padding.left, padding.top + plotHeight);
  ctx.lineTo(padding.left + plotWidth, padding.top + plotHeight);
  if (scaleMode !== "shared") {
    ctx.moveTo(padding.left + plotWidth, padding.top);
    ctx.lineTo(padding.left + plotWidth, padding.top + plotHeight);
  }
  ctx.stroke();
  ctx.restore();

  ctx.save();
  ctx.font = '12px "Space Grotesk", sans-serif';
  ctx.textBaseline = 'middle';
  if (scaleMode === 'shared') {
    ctx.fillStyle = labelColor;
    ctx.textAlign = 'right';
    for (let i = 0; i <= 4; i += 1) {
      const y = padding.top + plotHeight - (plotHeight / 4) * i;
      const tickValue = sharedMin + (sharedSpan * i) / 4;
      const tickLabel = Math.abs(tickValue) >= 1000 ? tickValue.toFixed(0) : tickValue.toFixed(1);
      ctx.fillText(tickLabel, padding.left - 12, y);
    }
    ctx.textAlign = 'left';
    ctx.fillText('Shared scale', padding.left, padding.top - 18);
  } else {
    const leftSeries = seriesStats.filter((_, index) => index % 2 === 0);
    const rightSeries = seriesStats.filter((_, index) => index % 2 === 1);
    leftSeries.forEach((stat, lane) => {
      const axisX = padding.left - 14 - lane * 74;
      ctx.strokeStyle = colors[(lane * 2) % colors.length];
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(axisX + 6, padding.top);
      ctx.lineTo(axisX + 6, padding.top + plotHeight);
      ctx.stroke();
      ctx.fillStyle = colors[(lane * 2) % colors.length];
      ctx.textAlign = 'right';
      for (let i = 0; i <= 4; i += 1) {
        const y = padding.top + plotHeight - (plotHeight / 4) * i;
        const tickValue = stat.min + (stat.span * i) / 4;
        const tickLabel = Math.abs(tickValue) >= 1000 ? tickValue.toFixed(0) : tickValue.toFixed(1);
        ctx.fillText(tickLabel, axisX, y);
      }
      ctx.save();
      ctx.translate(axisX - 48, padding.top + plotHeight / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.textAlign = 'center';
      ctx.fillText(displayLabelFor(stat.column), 0, 0);
      ctx.restore();
    });
    rightSeries.forEach((stat, lane) => {
      const axisX = padding.left + plotWidth + 14 + lane * 74;
      ctx.strokeStyle = colors[(lane * 2 + 1) % colors.length];
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(axisX - 6, padding.top);
      ctx.lineTo(axisX - 6, padding.top + plotHeight);
      ctx.stroke();
      ctx.fillStyle = colors[(lane * 2 + 1) % colors.length];
      ctx.textAlign = 'left';
      for (let i = 0; i <= 4; i += 1) {
        const y = padding.top + plotHeight - (plotHeight / 4) * i;
        const tickValue = stat.min + (stat.span * i) / 4;
        const tickLabel = Math.abs(tickValue) >= 1000 ? tickValue.toFixed(0) : tickValue.toFixed(1);
        ctx.fillText(tickLabel, axisX, y);
      }
      ctx.save();
      ctx.translate(axisX + 48, padding.top + plotHeight / 2);
      ctx.rotate(Math.PI / 2);
      ctx.textAlign = 'center';
      ctx.fillText(displayLabelFor(stat.column), 0, 0);
      ctx.restore();
    });
    ctx.fillStyle = labelColor;
    ctx.textAlign = 'left';
    ctx.fillText('Independent multi-axis view', padding.left, padding.top - 18);
  }
  ctx.restore();

  const drawZone = (zone, stroke, fill, dashed = false) => {
    const bounds = dashboardZonePixelBounds(zone, geometry);
    if (!bounds) return;
    ctx.save();
    ctx.setLineDash(dashed ? [8, 6] : []);
    ctx.fillStyle = fill;
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 1.25;
    ctx.fillRect(bounds.left, padding.top, bounds.width, plotHeight);
    ctx.strokeRect(bounds.left, padding.top, bounds.width, plotHeight);
    ctx.restore();
  };

  (zones.saved || []).forEach((zone) => drawZone(zone, "rgba(114,255,232,0.92)", "rgba(114,255,232,0.14)"));
  (zones.queued || []).forEach((zone) => drawZone(zone, "rgba(255,213,111,0.88)", "rgba(255,213,111,0.16)"));
  if (zones.preview) {
    drawZone(zones.preview, "rgba(43,216,255,0.95)", "rgba(43,216,255,0.14)", true);
  }
  if (transientBrush) {
    drawZone(transientBrush, "rgba(43,216,255,0.95)", "rgba(43,216,255,0.12)", true);
  }

  yColumns.forEach((column, index) => {
    ctx.beginPath();
    ctx.lineWidth = 2.2;
    ctx.strokeStyle = colors[index % colors.length];
    logData.rows.forEach((row, rowIndex) => {
      const x = xFor(rowIndex);
      const y = yFor(Number(row[column] ?? 0), column);
      if (rowIndex === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  });

  ctx.save();
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.font = '11px "Space Grotesk", sans-serif';
  seriesStats.slice(0, 6).forEach((stat, index) => {
    const x = padding.left + 10 + (index % 2) * 300;
    const y = padding.top + 6 + Math.floor(index / 2) * 18;
    ctx.fillStyle = colors[index % colors.length];
    ctx.fillRect(x, y + 4, 10, 10);
    ctx.fillStyle = 'rgba(230, 249, 255, 0.82)';
    const rangeLabel = `${displayLabelFor(stat.column)}: ${stat.min.toFixed(1)} - ${stat.max.toFixed(1)}`;
    ctx.fillText(rangeLabel, x + 16, y);
  });
  ctx.restore();

  if (logData?.export_meta) {
    const metaLines = [
      logData.export_meta.log_name ? `Log: ${logData.export_meta.log_name}` : "",
      logData.export_meta.expression ? `f(A,B): ${logData.export_meta.expression}` : "",
      logData.export_meta.a_label ? `A: ${logData.export_meta.a_label}` : "",
      logData.export_meta.b_label ? `B: ${logData.export_meta.b_label}` : "B: None",
    ].filter(Boolean);
    const boxWidth = Math.min(420, plotWidth * 0.48);
    const lineHeight = 16;
    const boxHeight = 14 + metaLines.length * lineHeight;
    const boxX = padding.left + plotWidth - boxWidth - 10;
    const boxY = 10;
    ctx.save();
    ctx.fillStyle = "rgba(5, 12, 20, 0.78)";
    ctx.strokeStyle = "rgba(114,255,232,0.16)";
    ctx.lineWidth = 1;
    ctx.fillRect(boxX, boxY, boxWidth, boxHeight);
    ctx.strokeRect(boxX, boxY, boxWidth, boxHeight);
    ctx.font = '12px "Space Grotesk", sans-serif';
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    metaLines.forEach((line, index) => {
      ctx.fillStyle = index === 1 ? "rgba(114,255,232,0.92)" : "rgba(223, 248, 255, 0.78)";
      ctx.fillText(line, boxX + 12, boxY + 8 + index * lineHeight);
    });
    ctx.restore();
  }

  return geometry;
}

function getSqlAnalysisGeometry(canvas, axisCount = 1) {
  const cssWidth = Math.max(320, canvas.clientWidth || canvas.parentElement?.clientWidth || 720);
  const cssHeight = Math.max(240, canvas.clientHeight || 280);
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(cssHeight * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const safeAxisCount = Math.max(0, Number(axisCount) || 0);
  const leftAxisCount = safeAxisCount > 0 ? Math.ceil(safeAxisCount / 2) : 0;
  const rightAxisCount = Math.max(0, safeAxisCount - leftAxisCount);
  const padding = {
    top: 22,
    right: 16 + rightAxisCount * 72,
    bottom: 34,
    left: 20 + leftAxisCount * 72,
  };
  return {
    ctx,
    cssWidth,
    cssHeight,
    padding,
    plotWidth: cssWidth - padding.left - padding.right,
    plotHeight: cssHeight - padding.top - padding.bottom,
    leftAxisCount,
    rightAxisCount,
  };
}

function drawSqlAnalysisCanvas(analysisData, canvas, overlays = {}, selectedTarget = null) {
  if (!canvas) return;
  const numericSeries = Array.isArray(analysisData) ? analysisData : (analysisData?.numericSeries || []);
  const textSeries = Array.isArray(analysisData) ? [] : (analysisData?.textSeries || []);
  const geometry = getSqlAnalysisGeometry(canvas, numericSeries.length);
  const { ctx, cssWidth, cssHeight, padding, plotWidth, plotHeight } = geometry;
  ctx.clearRect(0, 0, cssWidth, cssHeight);

  const bg = ctx.createLinearGradient(0, 0, 0, cssHeight);
  bg.addColorStop(0, "rgba(7, 18, 30, 0.94)");
  bg.addColorStop(1, "rgba(4, 10, 16, 0.98)");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, cssWidth, cssHeight);

  if (!numericSeries.length && !textSeries.length) {
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "rgba(214, 228, 231, 0.6)";
    ctx.fillText("Run a filter with matched values to see the analysis plot.", cssWidth / 2, cssHeight / 2);
    return [];
  }

  const colors = ["#72ffe8", "#2bd8ff", "#ffd56f", "#ff9ca6", "#cbbff7", "#95efb1"];
  const overlayEventCount = (overlays.maintenance || []).length + (overlays.faults || []).length;
  const sectionGap = overlayEventCount ? 14 : 8;
  const eventHeight = overlayEventCount ? Math.max(48, plotHeight * 0.11) : 24;
  const hasNumeric = numericSeries.length > 0;
  const hasText = textSeries.length > 0;
  const isMixedPlot = hasNumeric && hasText;
  const textSectionGap = isMixedPlot ? 6 : 12;
  const textSectionHeadHeight = isMixedPlot && textSeries.length === 1 ? 0 : (isMixedPlot ? 14 : 22);
  const textSectionPadBottom = isMixedPlot ? 4 : 8;
  const textSeriesMeta = hasText
    ? textSeries.map((series) => ({
        categories: dedupeStrings(series.categories?.length ? series.categories : series.points.map((point) => point.displayValue || point.value)).slice(0, 50),
      }))
    : [];
  let textLaneHeight = hasText ? (isMixedPlot ? 24 : 28) : 0;
  const computeTextHeight = (laneHeight) => textSeriesMeta.reduce(
    (sum, meta, index) => sum + textSectionHeadHeight + textSectionPadBottom + Math.max(1, meta.categories.length) * laneHeight + (index ? textSectionGap : 0),
    0,
  );
  const totalTextRows = textSeriesMeta.reduce((sum, meta) => sum + Math.max(1, meta.categories.length), 0);
  let textHeight = hasText ? computeTextHeight(textLaneHeight) : 0;
  let numericHeight = hasNumeric
    ? plotHeight - eventHeight - textHeight - (hasText ? 10 : 0) - sectionGap
    : 0;
  if (hasNumeric && hasText && numericHeight < 120) {
    const minimumTextHeight = computeTextHeight(isMixedPlot ? 18 : 20);
    const reducible = Math.max(0, textHeight - minimumTextHeight);
    const needed = 120 - numericHeight;
    const reduceBy = Math.min(reducible, needed);
    if (reduceBy > 0) {
      textLaneHeight = Math.max(isMixedPlot ? 18 : 20, textLaneHeight - reduceBy / Math.max(1, textSeries.length));
      textHeight = computeTextHeight(textLaneHeight);
      numericHeight = plotHeight - eventHeight - textHeight - 10 - sectionGap;
    }
  }
  if (hasText && !hasNumeric) {
    const availableTextHeight = Math.max(0, plotHeight - eventHeight - sectionGap);
    const extraHeight = Math.max(0, availableTextHeight - textHeight);
    if (extraHeight > 0 && totalTextRows > 0) {
      textLaneHeight += Math.min(14, extraHeight / totalTextRows);
      textHeight = computeTextHeight(textLaneHeight);
    }
  }
  numericHeight = Math.max(0, numericHeight);
  const numericTop = padding.top;
  const textTop = numericTop + numericHeight + (hasNumeric && hasText ? 10 : 0);
  const eventTop = padding.top + numericHeight + textHeight + ((hasNumeric || hasText) ? sectionGap : 0);
  const textSections = [];
  if (hasText) {
    let cursor = textTop;
    textSeriesMeta.forEach((meta) => {
      const rowCount = Math.max(1, meta.categories.length);
      const height = textSectionHeadHeight + textSectionPadBottom + rowCount * textLaneHeight;
      textSections.push({
        categories: meta.categories,
        top: cursor,
        bodyTop: cursor + textSectionHeadHeight,
        height,
        rowCount,
      });
      cursor += height + textSectionGap;
    });
  }
  const timelineLeft = hasText
    ? Math.min(padding.left + 174, padding.left + plotWidth * 0.22)
    : padding.left;
  const timelineRight = padding.left + plotWidth;
  const categoryLabelRight = hasText ? Math.max(padding.left + 126, timelineLeft - 12) : timelineLeft;

  if (numericHeight > 0) {
    ctx.strokeStyle = "rgba(147, 220, 229, 0.10)";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i += 1) {
      const y = numericTop + (numericHeight / 4) * i;
      ctx.beginPath();
      ctx.moveTo(timelineLeft, y);
      ctx.lineTo(timelineRight, y);
      ctx.stroke();
    }
  }

  ctx.strokeStyle = "rgba(147, 220, 229, 0.18)";
  ctx.strokeRect(padding.left, padding.top, plotWidth, plotHeight);
  ctx.beginPath();
  ctx.moveTo(timelineLeft, padding.top);
  ctx.lineTo(timelineLeft, eventTop + eventHeight);
  if (hasNumeric && hasText) {
    ctx.moveTo(padding.left, textTop - 4);
    ctx.lineTo(timelineRight, textTop - 4);
  }
  if (overlayEventCount) {
    ctx.moveTo(padding.left, eventTop - 4);
    ctx.lineTo(timelineRight, eventTop - 4);
  }
  if (hasText) {
    ctx.moveTo(categoryLabelRight, textTop);
    ctx.lineTo(categoryLabelRight, textTop + textHeight);
  }
  ctx.stroke();

  const stats = numericSeries.map((series) => {
    const values = series.points.map((p) => p.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    return { min, max, span: max - min || 1 };
  });
  const timelineKeys = [];
  [...numericSeries, ...textSeries].forEach((series) => {
    series.points.forEach((point) => {
      const key = `${point.ts || ""}|${point.draw || ""}`;
      if (!timelineKeys.includes(key)) timelineKeys.push(key);
    });
  });
  (overlays.maintenance || []).forEach((item) => {
    const key = `${item.event_ts || ""}|maintenance:${item.event_id || item.title || ""}`;
    if (!timelineKeys.includes(key)) timelineKeys.push(key);
  });
  (overlays.faults || []).forEach((item) => {
    const key = `${item.event_ts || ""}|fault:${item.event_id || item.title || ""}`;
    if (!timelineKeys.includes(key)) timelineKeys.push(key);
  });
  timelineKeys.sort((a, b) => a.localeCompare(b));
  const xMap = new Map(
    timelineKeys.map((key, index) => [
      key,
      timelineLeft + ((timelineRight - timelineLeft) * index) / Math.max(1, timelineKeys.length - 1),
    ]),
  );
  const xForPoint = (point) => xMap.get(`${point.ts || ""}|${point.draw || ""}`) ?? padding.left;
  const yForNumericPoint = (value, stat) => numericTop + numericHeight - ((value - stat.min) / stat.span) * numericHeight;
  const timelineEntries = timelineKeys.map((key) => ({
    key,
    ts: key.split("|")[0] || "",
    x: xMap.get(key) ?? timelineLeft,
  }));
  const formatTickLabel = (timestamp) => {
    const raw = String(timestamp || "").trim();
    if (!raw) return "";
    const normalized = raw.replace("T", " ");
    const [datePart] = normalized.split(" ");
    if (!datePart) return raw;
    if (datePart.includes("-")) {
      const parts = datePart.split("-");
      if (parts.length === 3) {
        const [year, month, day] = parts;
        return `${month}/${day}/${String(year || "").slice(-2)}`;
      }
    }
    if (datePart.includes("/")) {
      const parts = datePart.split("/");
      if (parts.length === 3) {
        const [first, second, year] = parts;
        const firstNum = Number(first);
        const yearShort = String(year || "").slice(-2);
        if (first.length === 4) {
          const [yearIso, monthIso, dayIso] = parts;
          return `${monthIso}/${dayIso}/${String(yearIso || "").slice(-2)}`;
        }
        if (firstNum > 12 && Number.isFinite(firstNum)) {
          return `${first}/${second}/${yearShort}`;
        }
        return `${first}/${second}/${yearShort}`;
      }
    }
    return datePart;
  };
  const tickTargetCount = Math.min(6, Math.max(3, Math.round((timelineRight - timelineLeft) / 170)));
  const tickCandidates = timelineEntries.length
    ? Array.from(new Set(
      Array.from({ length: tickTargetCount }, (_, index) => {
        if (tickTargetCount <= 1) return 0;
        return Math.round((index * (timelineEntries.length - 1)) / (tickTargetCount - 1));
      }),
    ))
    : [];

  ctx.font = '12px "Space Grotesk", sans-serif';
  ctx.textBaseline = "middle";
  numericSeries.forEach((series, index) => {
    const stat = stats[index];
    const color = colors[index % colors.length];
    const isLeft = index % 2 === 0;
    const lane = isLeft ? Math.floor(index / 2) : Math.floor(index / 2);
    const axisX = isLeft ? padding.left - 14 - lane * 74 : padding.left + plotWidth + 14 + lane * 74;

    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    if (numericHeight > 0) {
      ctx.beginPath();
      ctx.moveTo(axisX + (isLeft ? 6 : -6), numericTop);
      ctx.lineTo(axisX + (isLeft ? 6 : -6), numericTop + numericHeight);
      ctx.stroke();
    }

    ctx.fillStyle = color;
    ctx.textAlign = isLeft ? "right" : "left";
    for (let i = 0; i <= 4; i += 1) {
      const y = numericTop + numericHeight - (numericHeight / 4) * i;
      const tickValue = stat.min + (stat.span * i) / 4;
      const tickLabel = Math.abs(tickValue) >= 1000 ? tickValue.toFixed(0) : tickValue.toFixed(2);
      ctx.fillText(tickLabel, axisX, y);
    }

    ctx.save();
    ctx.translate(axisX + (isLeft ? -48 : 48), numericTop + numericHeight / 2);
    ctx.rotate(isLeft ? -Math.PI / 2 : Math.PI / 2);
    ctx.textAlign = "center";
    ctx.fillText(series.label, 0, 0);
    ctx.restore();
  });

  const drawBands = new Map();
  const hitTargets = [];
  numericSeries.forEach((series, index) => {
    const stat = stats[index];
    series.points.forEach((point) => {
      const x = xForPoint(point);
      const y = yForNumericPoint(point.value, stat);
      const key = `${point.ts || ""}|${point.draw || ""}`;
      if (!drawBands.has(key)) drawBands.set(key, []);
      drawBands.get(key).push({ x, y });
    });
  });
  ctx.save();
  ctx.setLineDash([4, 6]);
  ctx.strokeStyle = "rgba(180, 232, 238, 0.18)";
  ctx.lineWidth = 1;
  drawBands.forEach((points) => {
    if (points.length < 2) return;
    const x = points[0].x;
    const ys = points.map((p) => p.y);
    ctx.beginPath();
    ctx.moveTo(x, Math.min(...ys));
    ctx.lineTo(x, Math.max(...ys));
    ctx.stroke();
  });
  ctx.restore();

  if (selectedTarget?.draw) {
    const selectedPoints = [];
    drawBands.forEach((points, key) => {
      if (key.endsWith(`|${selectedTarget.draw}`)) {
        selectedPoints.push(...points);
      }
    });
    if (selectedPoints.length) {
      const x = selectedPoints[0].x;
      const ys = selectedPoints.map((p) => p.y);
      ctx.save();
      ctx.fillStyle = "rgba(143, 221, 227, 0.08)";
      ctx.strokeStyle = "rgba(143, 221, 227, 0.42)";
      ctx.setLineDash([6, 6]);
      ctx.fillRect(x - 12, padding.top, 24, plotHeight);
      ctx.beginPath();
      ctx.moveTo(x, padding.top);
      ctx.lineTo(x, eventTop + eventHeight);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(x, Math.min(...ys));
      ctx.lineTo(x, Math.max(...ys));
      ctx.stroke();
      ctx.restore();
    }
  }

  numericSeries.forEach((series, index) => {
    const stat = stats[index];
    const isFocusedSeries = !selectedTarget || selectedTarget.type !== "series" || selectedTarget.label === series.label;
    ctx.beginPath();
    ctx.lineWidth = 2.2;
    ctx.strokeStyle = isFocusedSeries ? colors[index % colors.length] : "rgba(133, 162, 166, 0.26)";
    let previousX = null;
    series.points.forEach((point, pointIndex) => {
      const x = xForPoint(point);
      const y = yForNumericPoint(point.value, stat);
      const sharesColumnWithPrevious = pointIndex > 0 && previousX != null && Math.abs(x - previousX) < 0.5;
      if (pointIndex === 0 || sharesColumnWithPrevious) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
      previousX = x;
    });
    ctx.stroke();
    series.points.forEach((point) => {
      const x = xForPoint(point);
      const y = yForNumericPoint(point.value, stat);
      ctx.fillStyle = isFocusedSeries ? colors[index % colors.length] : "rgba(133, 162, 166, 0.3)";
      ctx.beginPath();
      const isSelected = selectedTarget?.type === "series" && selectedTarget.draw === point.draw && selectedTarget.label === series.label && selectedTarget.ts === point.ts;
      ctx.arc(x, y, isSelected ? 5 : 2.8, 0, Math.PI * 2);
      ctx.fill();
      hitTargets.push({
        type: "series",
        label: series.label,
        draw: point.draw,
        ts: point.ts,
        value: point.value,
        displayValue: point.value,
        x,
        y,
        radius: 10,
      });
    });
  });

  const truncateText = (value, max = 26) => {
    const text = String(value || "").trim();
    if (text.length <= max) return text;
    return `${text.slice(0, Math.max(0, max - 1))}\u2026`;
  };

  if (textSeries.length) {
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    textSeries.forEach((series, index) => {
      const section = textSections[index];
      if (!section) return;
      const color = colors[(numericSeries.length + index) % colors.length];
      if (textSectionHeadHeight > 0) {
        ctx.fillStyle = color;
        ctx.font = '11px "Orbitron", sans-serif';
        ctx.textBaseline = "top";
        ctx.fillText(series.label, padding.left + 10, section.top + 4);
        ctx.fillStyle = "rgba(178, 208, 211, 0.62)";
        ctx.font = '10px "Space Grotesk", sans-serif';
        ctx.textAlign = "right";
        ctx.fillText(`${section.categories.length} categories · ${series.points.length} draws`, timelineRight - 10, section.top + 5);
        ctx.textAlign = "left";
      }
      ctx.font = '11px "Space Grotesk", sans-serif';
      ctx.textBaseline = "middle";
      section.categories.forEach((category, categoryIndex) => {
        const rowTop = section.bodyTop + categoryIndex * textLaneHeight;
        const rowY = rowTop + textLaneHeight / 2;
        if (categoryIndex % 2 === 0) {
          ctx.fillStyle = "rgba(255, 255, 255, 0.015)";
          ctx.fillRect(padding.left + 1, rowTop, plotWidth - 2, textLaneHeight);
        }
        ctx.strokeStyle = "rgba(147, 220, 229, 0.08)";
        ctx.beginPath();
        ctx.moveTo(timelineLeft, rowY);
        ctx.lineTo(timelineRight, rowY);
        ctx.stroke();
        ctx.fillStyle = category === "Unspecified"
          ? "rgba(255, 196, 130, 0.88)"
          : (categoryIndex % 2 === 0 ? "rgba(188, 215, 220, 0.9)" : "rgba(167, 198, 202, 0.76)");
        ctx.fillText(truncateText(category, 30), padding.left + 10, rowY);
      });
      series.points.forEach((point, pointIndex) => {
        const x = xForPoint(point);
        const categoryValue = point.displayValue || point.value;
        const categoryIndex = Math.max(0, section.categories.indexOf(categoryValue));
        const y = section.bodyTop + categoryIndex * textLaneHeight + textLaneHeight / 2;
        const key = `${point.ts || ""}|${point.draw || ""}`;
        if (!drawBands.has(key)) drawBands.set(key, []);
        drawBands.get(key).push({ x, y });
        const isSelected = selectedTarget?.type === "series"
          && selectedTarget.draw === point.draw
          && selectedTarget.label === series.label
          && selectedTarget.ts === point.ts;
        ctx.fillStyle = color;
        ctx.shadowBlur = isSelected ? 8 : 4.5;
        ctx.shadowColor = color;
        ctx.beginPath();
        ctx.arc(x, y, isSelected ? 4.2 : 2.6, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;
        if (isSelected) {
          ctx.strokeStyle = "rgba(235, 249, 251, 0.92)";
          ctx.lineWidth = 1.1;
          ctx.beginPath();
          ctx.arc(x, y, 6, 0, Math.PI * 2);
          ctx.stroke();
        }
        hitTargets.push({
          type: "series",
          label: series.label,
          draw: point.draw,
          ts: point.ts,
          value: point.value,
          displayValue: point.displayValue || point.value,
          isText: true,
          x,
          y,
          radius: 12,
        });
      });
    });
  }

  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  const legendVisibleSeries = numericSeries.slice(0, 12);
  legendVisibleSeries.forEach((series, index) => {
    const x = padding.left + 8 + (index % 3) * 188;
    const y = 6 + Math.floor(index / 3) * 16;
    ctx.fillStyle = colors[index % colors.length];
    ctx.fillRect(x, y + 3, 10, 10);
    ctx.fillStyle = "rgba(230, 249, 255, 0.82)";
    ctx.fillText(series.label, x + 16, y);
  });
  if (numericSeries.length > legendVisibleSeries.length) {
    const x = padding.left + 8;
    const y = 6 + Math.ceil(legendVisibleSeries.length / 3) * 16;
    ctx.fillStyle = "rgba(191, 219, 222, 0.68)";
    ctx.fillText(`+${numericSeries.length - legendVisibleSeries.length} more`, x, y);
  }
  if (textSeries.length && numericSeries.length) {
    const x = padding.left + 8;
    const y = 6 + Math.max(1, Math.ceil(legendVisibleSeries.length / 3)) * 16;
    ctx.fillStyle = colors[(numericSeries.length) % colors.length];
    ctx.fillRect(x, y + 3, 10, 10);
    ctx.fillStyle = "rgba(191, 219, 222, 0.68)";
    ctx.fillText(textSeries.length === 1 ? textSeries[0].label : `${textSeries.length} categorical lanes`, x + 16, y);
  }

  const drawEventMarkers = (items, y, color, shape = "circle") => {
    items.forEach((item) => {
      const key = `${item.event_ts || ""}|${shape}:${item.event_id || item.title || ""}`;
      const x = xMap.get(key);
      if (x == null) return;
      ctx.fillStyle = color;
      ctx.strokeStyle = color;
      if (shape === "triangle") {
        ctx.beginPath();
        ctx.moveTo(x, y - 8);
        ctx.lineTo(x - 7, y + 6);
        ctx.lineTo(x + 7, y + 6);
        ctx.closePath();
        ctx.fill();
      } else {
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fill();
      }
      hitTargets.push({
        type: shape === "triangle" ? "maintenance" : "fault",
        title: item.title || "",
        draw: "",
        ts: item.event_ts || "",
        value: "",
        x,
        y,
        radius: 11,
      });
    });
  };

  const maintY = eventTop + eventHeight * 0.34;
  const faultY = eventTop + eventHeight * 0.72;
  if (overlayEventCount) {
    ctx.textAlign = "left";
    ctx.fillStyle = "rgba(191, 219, 222, 0.62)";
    ctx.fillText("Event lane", padding.left, eventTop - 14);
    ctx.fillStyle = "rgba(196, 227, 229, 0.68)";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    ctx.fillText("Maint", timelineLeft - 8, maintY);
    ctx.fillText("Fault", timelineLeft - 8, faultY);
    drawEventMarkers(overlays.maintenance || [], maintY, "#ffd56f", "triangle");
    drawEventMarkers(overlays.faults || [], faultY, "#ff9ca6", "circle");
  }

  if (timelineEntries.length) {
    const axisY = eventTop + eventHeight - 16;
    ctx.strokeStyle = "rgba(147, 220, 229, 0.18)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(timelineLeft, axisY);
    ctx.lineTo(timelineRight, axisY);
    ctx.stroke();
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.font = '10px "Space Grotesk", sans-serif';
    tickCandidates.forEach((tickIndex) => {
      const tick = timelineEntries[tickIndex];
      if (!tick) return;
      ctx.strokeStyle = "rgba(147, 220, 229, 0.22)";
      ctx.beginPath();
      ctx.moveTo(tick.x, axisY);
      ctx.lineTo(tick.x, axisY + 6);
      ctx.stroke();
      ctx.fillStyle = "rgba(191, 219, 222, 0.68)";
      ctx.fillText(formatTickLabel(tick.ts), tick.x, axisY + 8);
    });
  }
  return hitTargets;
}

function sqlAnalysisGroupLabel(parameterName) {
  const raw = String(parameterName || "").trim();
  if (!raw) return "";
  return raw
    .replace(/^Zone\s+\d+\s*\|\s*/i, "")
    .replace(/^Marked\s+Zone\s+\d+\s*\|\s*/i, "")
    .replace(/\s+/g, " ")
    .trim();
}

function sqlConditionGroupName(params) {
  const labels = Array.from(new Set((params || []).map((item) => sqlAnalysisGroupLabel(item)).filter(Boolean)));
  if (!labels.length) return "Unnamed parameter group";
  if (labels.length === 1) return labels[0];
  const short = labels.slice(0, 2).join(" + ");
  return labels.length <= 2 ? short : `${short} + ${labels.length - 2} more`;
}

function sqlFamilyLabel(parameterName) {
  const raw = String(parameterName || "");
  const lower = raw.toLowerCase();
  if (lower.startsWith("order__")) return "Order";
  if (lower.startsWith("process__")) return "Process";
  if (lower.includes("zone ")) return "Zones";
  if (lower.includes("t&m") || lower.includes("good zone") || lower.includes("cut/save") || lower.includes("fiber length") || lower.includes("drum |")) return "Winder + T&M";
  return "General";
}

function sqlMathOperationLabel(operation) {
  return {
    identity: "Source A",
    delta_prev: "Delta vs previous",
    rolling_avg: "Rolling average",
    spread_ab: "A - B spread",
    ratio_ab: "A / B ratio",
    percent_ab: "A vs B %",
    normalize: "Normalized A",
    zscore: "Z-score A",
    custom_ab: "Custom f(A,B)",
  }[operation] || "Derived trace";
}

const SQL_MATH_FIXED_WINDOW = 5;
const SQL_MATH_ALLOWED_FUNCTIONS = {
  abs: Math.abs,
  ceil: Math.ceil,
  floor: Math.floor,
  round: Math.round,
  sqrt: Math.sqrt,
  min: Math.min,
  max: Math.max,
  pow: Math.pow,
  log: Math.log,
  exp: Math.exp,
};
const SQL_MATH_FUNCTION_ALIASES = {
  power: "pow",
  absolute: "abs",
  minimum: "min",
  maximum: "max",
};

function sqlMathSeriesLabel(operation, expression = "") {
  if (operation === "custom_ab") {
    const raw = String(expression || "A").trim() || "A";
    return `f(A,B) = ${raw}`;
  }
  return sqlMathOperationLabel(operation);
}

function sqlCompileMathExpression(expression) {
  const raw = String(expression || "A").trim() || "A";
  if (/[^0-9A-Za-z_+\-*/%^().,\s]/.test(raw)) {
    return { error: "Formula has unsupported characters." };
  }
  let normalized = raw.replace(/\b(?:np|math)\s*\.\s*/gi, "");
  Object.entries(SQL_MATH_FUNCTION_ALIASES).forEach(([alias, canonical]) => {
    normalized = normalized.replace(new RegExp(`\\b${alias}\\s*\\(`, "gi"), `${canonical}(`);
  });
  const identifiers = Array.from(new Set(normalized.match(/[A-Za-z_][A-Za-z0-9_]*/g) || []));
  const allowed = new Set(["A", "B", ...Object.keys(SQL_MATH_ALLOWED_FUNCTIONS)]);
  const invalid = identifiers.find((item) => !allowed.has(item));
  if (invalid) {
    return { error: `Unsupported token "${invalid}".` };
  }
  const rewritten = normalized.replace(/\^/g, "**");
  let compiled = null;
  try {
    compiled = new Function(
      "A",
      "B",
      "Fns",
      `"use strict"; const { ${Object.keys(SQL_MATH_ALLOWED_FUNCTIONS).join(", ")} } = Fns; return (${rewritten});`,
    );
  } catch (error) {
    return { error: "Formula syntax is invalid." };
  }
  return {
    expression: raw,
    usesB: identifiers.includes("B"),
    run(A, B) {
      try {
        const value = compiled(Number(A), Number(B), SQL_MATH_ALLOWED_FUNCTIONS);
        return Number.isFinite(value) ? value : null;
      } catch (error) {
        return null;
      }
    },
  };
}

function dedupeStrings(values) {
  const seen = new Set();
  const output = [];
  (values || []).forEach((value) => {
    const item = String(value || "").trim();
    if (!item || seen.has(item)) return;
    seen.add(item);
    output.push(item);
  });
  return output;
}

function sqlAnalysisPointKey(label, draw, ts) {
  return `${String(label || "")}||${String(draw || "")}||${String(ts || "")}`;
}

function buildSqlMathSeries(seriesList, config = {}) {
  const sourceA = String(config.sourceA || "");
  const sourceB = String(config.sourceB || "");
  const operation = String(config.operation || "identity");
  const expression = String(config.expression || "A").trim() || "A";
  const hiddenPointKeys = Array.isArray(config.hiddenPointKeys) ? config.hiddenPointKeys : [];
  const windowSize = SQL_MATH_FIXED_WINDOW;
  const seriesA = seriesList.find((item) => item.label === sourceA);
  const seriesB = seriesList.find((item) => item.label === sourceB);
  const derivedLabel = sqlMathSeriesLabel(operation, expression);
  if (!seriesA) return { label: derivedLabel, points: [], meta: [] };
  const customFormula = operation === "custom_ab" ? sqlCompileMathExpression(expression) : null;
  if (customFormula?.error) {
    return {
      label: derivedLabel,
      points: [],
      meta: [],
      sourceA,
      sourceB,
      operation,
      expression,
      windowSize,
      error: customFormula.error,
    };
  }
  const requiresB = ["spread_ab", "ratio_ab", "percent_ab"].includes(operation) || (operation === "custom_ab" && customFormula?.usesB);
  if (requiresB && !seriesB) {
    return {
      label: derivedLabel,
      points: [],
      meta: [],
      sourceA,
      sourceB,
      operation,
      expression,
      windowSize,
      error: "Choose Source B for this math mode.",
    };
  }

  const mapA = new Map(seriesA.points.map((point) => [`${point.ts || ""}|${point.draw || ""}`, point]));
  const mapB = new Map((seriesB?.points || []).map((point) => [`${point.ts || ""}|${point.draw || ""}`, point]));
  const keys = Array.from(
    new Set([
      ...mapA.keys(),
      ...(requiresB ? mapB.keys() : []),
    ]),
  )
    .filter((key) => {
      if (requiresB) {
        return mapA.has(key) && mapB.has(key);
      }
      return mapA.has(key);
    })
    .sort((a, b) => a.localeCompare(b));

  const baseValues = seriesA.points.map((point) => Number(point.value)).filter((value) => Number.isFinite(value));
  const baseMin = Math.min(...baseValues);
  const baseMax = Math.max(...baseValues);
  const baseMean = baseValues.reduce((sum, value) => sum + value, 0) / Math.max(1, baseValues.length);
  const baseVariance = baseValues.reduce((sum, value) => sum + (value - baseMean) ** 2, 0) / Math.max(1, baseValues.length);
  const baseStd = Math.sqrt(baseVariance) || 1;

  const points = [];
  const meta = [];
  keys.forEach((key, index) => {
    const pointA = mapA.get(key);
    const pointB = mapB.get(key);
    let value = null;
    if (operation === "identity") {
      value = Number(pointA?.value);
    } else if (operation === "delta_prev") {
      const prev = index > 0 ? Number(mapA.get(keys[index - 1])?.value) : null;
      value = Number.isFinite(prev) ? Number(pointA?.value) - prev : null;
    } else if (operation === "rolling_avg") {
      const sliceKeys = keys.slice(Math.max(0, index - windowSize + 1), index + 1);
      const sliceValues = sliceKeys.map((sliceKey) => Number(mapA.get(sliceKey)?.value)).filter((item) => Number.isFinite(item));
      value = sliceValues.length ? sliceValues.reduce((sum, item) => sum + item, 0) / sliceValues.length : null;
    } else if (operation === "spread_ab") {
      value = Number(pointA?.value) - Number(pointB?.value);
    } else if (operation === "ratio_ab") {
      const denominator = Number(pointB?.value);
      value = denominator ? Number(pointA?.value) / denominator : null;
    } else if (operation === "percent_ab") {
      const denominator = Number(pointB?.value);
      value = denominator ? (Number(pointA?.value) / denominator) * 100 : null;
    } else if (operation === "normalize") {
      value = baseMax === baseMin ? 0 : ((Number(pointA?.value) - baseMin) / (baseMax - baseMin)) * 100;
    } else if (operation === "zscore") {
      value = (Number(pointA?.value) - baseMean) / baseStd;
    } else if (operation === "custom_ab") {
      value = customFormula?.run(pointA?.value, pointB?.value ?? 0);
    }
    if (!Number.isFinite(value)) return;
    const point = {
      draw: pointA?.draw || pointB?.draw || "",
      ts: pointA?.ts || pointB?.ts || "",
      value,
    };
    const pointKey = sqlAnalysisPointKey(derivedLabel, point.draw, point.ts);
    if (hiddenPointKeys.includes(pointKey)) return;
    points.push(point);
    meta.push({
      ...point,
      sourceA: pointA?.value,
      sourceB: pointB?.value,
    });
  });

  return {
    label: derivedLabel,
    points,
    meta,
    sourceA,
    sourceB,
    operation,
    expression,
    windowSize,
  };
}

function sqlMathRecipeKey(config = {}) {
  return [
    config.sourceA || "",
    config.sourceB || "",
    config.operation || "identity",
    String(config.expression || "A").trim() || "A",
  ].join("|");
}

function drawSqlMathCanvas(mathSeriesList, canvas, overlays = {}, selectedTarget = null) {
  if (!canvas) return [];
  const geometry = getSqlAnalysisGeometry(canvas, 1);
  const axisCount = Math.max(1, mathSeriesList?.length || 1);
  const adjusted = getSqlAnalysisGeometry(canvas, axisCount);
  const { ctx, cssWidth, cssHeight, padding, plotWidth, plotHeight, leftAxisCount } = adjusted;
  ctx.clearRect(0, 0, cssWidth, cssHeight);

  const bg = ctx.createLinearGradient(0, 0, 0, cssHeight);
  bg.addColorStop(0, "rgba(8, 18, 29, 0.96)");
  bg.addColorStop(1, "rgba(4, 10, 16, 0.99)");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, cssWidth, cssHeight);

  const activeSeries = (mathSeriesList || []).filter((item) => item?.points?.length);
  if (!activeSeries.length) {
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "rgba(214, 228, 231, 0.6)";
    ctx.fillText("Choose source series and a math mode to generate a derived trace.", cssWidth / 2, cssHeight / 2);
    return [];
  }

  const mainHeight = plotHeight * 0.78;
  const eventTop = padding.top + mainHeight + 18;
  const eventHeight = plotHeight - mainHeight - 18;
  const colors = ["#cbbff7", "#72ffe8", "#2bd8ff", "#ffd56f", "#ff9ca6", "#95efb1"];

  const timelineKeys = [];
  activeSeries.forEach((series) => {
    series.points.forEach((point) => {
      const key = `${point.ts || ""}|${point.draw || ""}`;
      if (!timelineKeys.includes(key)) timelineKeys.push(key);
    });
  });
  (overlays.maintenance || []).forEach((item) => {
    const key = `${item.event_ts || ""}|maintenance:${item.event_id || item.title || ""}`;
    if (!timelineKeys.includes(key)) timelineKeys.push(key);
  });
  (overlays.faults || []).forEach((item) => {
    const key = `${item.event_ts || ""}|fault:${item.event_id || item.title || ""}`;
    if (!timelineKeys.includes(key)) timelineKeys.push(key);
  });
  timelineKeys.sort((a, b) => a.localeCompare(b));
  const xMap = new Map(timelineKeys.map((key, index) => [key, padding.left + (plotWidth * index) / Math.max(1, timelineKeys.length - 1)]));
  const xForIndex = (key) => xMap.get(key) ?? padding.left;

  ctx.strokeStyle = "rgba(147, 220, 229, 0.10)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i += 1) {
    const y = padding.top + (mainHeight / 4) * i;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(padding.left + plotWidth, y);
    ctx.stroke();
  }

  ctx.strokeStyle = "rgba(147, 220, 229, 0.18)";
  ctx.beginPath();
  ctx.moveTo(padding.left, padding.top);
  ctx.lineTo(padding.left, padding.top + mainHeight);
  ctx.lineTo(padding.left + plotWidth, padding.top + mainHeight);
  ctx.moveTo(padding.left, eventTop);
  ctx.lineTo(padding.left, eventTop + eventHeight);
  ctx.lineTo(padding.left + plotWidth, eventTop + eventHeight);
  ctx.stroke();

  ctx.font = '12px "Space Grotesk", sans-serif';
  const targets = [];
  activeSeries.forEach((series, index) => {
    const values = series.points.map((point) => Number(point.value)).filter((value) => Number.isFinite(value));
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const isLeft = index < leftAxisCount;
    const lane = isLeft ? index : index - leftAxisCount;
    const axisX = isLeft ? padding.left - 12 - lane * 74 : padding.left + plotWidth + 12 + lane * 74;
    const yFor = (value) => padding.top + mainHeight - ((value - min) / span) * mainHeight;
    const color = colors[index % colors.length];

    const zeroY = min <= 0 && max >= 0 ? yFor(0) : null;
    if (zeroY != null) {
      ctx.save();
      ctx.setLineDash([8, 6]);
      ctx.strokeStyle = `${color}55`;
      ctx.beginPath();
      ctx.moveTo(padding.left, zeroY);
      ctx.lineTo(padding.left + plotWidth, zeroY);
      ctx.stroke();
      ctx.restore();
    }

    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(axisX + (isLeft ? 6 : -6), padding.top);
    ctx.lineTo(axisX + (isLeft ? 6 : -6), padding.top + mainHeight);
    ctx.stroke();

    ctx.fillStyle = color;
    ctx.textAlign = isLeft ? "right" : "left";
    ctx.textBaseline = "middle";
    for (let i = 0; i <= 4; i += 1) {
      const y = padding.top + mainHeight - (mainHeight / 4) * i;
      const tickValue = min + (span * i) / 4;
      ctx.fillText(Math.abs(tickValue) >= 1000 ? tickValue.toFixed(0) : tickValue.toFixed(2), axisX, y);
    }

    ctx.save();
    ctx.translate(axisX + (isLeft ? -46 : 46), padding.top + mainHeight / 2);
    ctx.rotate(isLeft ? -Math.PI / 2 : Math.PI / 2);
    ctx.textAlign = "center";
    ctx.fillText(series.label, 0, 0);
    ctx.restore();

    const area = ctx.createLinearGradient(0, padding.top, 0, padding.top + mainHeight);
    area.addColorStop(0, `${color}35`);
    area.addColorStop(1, `${color}05`);
    ctx.beginPath();
    series.points.forEach((point, pointIndex) => {
      const key = `${point.ts || ""}|${point.draw || ""}`;
      const x = xForIndex(key);
      const y = yFor(point.value);
      if (pointIndex === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.lineTo(padding.left + plotWidth, padding.top + mainHeight);
    ctx.lineTo(padding.left, padding.top + mainHeight);
    ctx.closePath();
    ctx.fillStyle = area;
    ctx.fill();

    ctx.beginPath();
    ctx.lineWidth = 2.3;
    ctx.strokeStyle = color;
    series.points.forEach((point, pointIndex) => {
      const key = `${point.ts || ""}|${point.draw || ""}`;
      const x = xForIndex(key);
      const y = yFor(point.value);
      if (pointIndex === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    series.points.forEach((point) => {
      const key = `${point.ts || ""}|${point.draw || ""}`;
      const x = xForIndex(key);
      const y = yFor(point.value);
      const selected = selectedTarget?.type === "math" && selectedTarget.draw === point.draw && selectedTarget.ts === point.ts && selectedTarget.label === series.label;
      ctx.fillStyle = selected ? "#fff3c8" : color;
      ctx.beginPath();
      ctx.arc(x, y, selected ? 4.8 : 3.1, 0, Math.PI * 2);
      ctx.fill();
      targets.push({
        type: "math",
        label: series.label,
        draw: point.draw,
        ts: point.ts,
        value: point.value,
        x,
        y,
        radius: 10,
      });
    });
  });

  ctx.fillStyle = "rgba(191, 219, 222, 0.62)";
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  ctx.fillText("Derived event lane", padding.left, eventTop - 14);

  const drawEventMarkers = (items, y, color, shape = "circle") => {
    items.forEach((item) => {
      const key = `${item.event_ts || ""}|${shape}:${item.event_id || item.title || ""}`;
      const x = xMap.get(key);
      if (x == null) return;
      ctx.fillStyle = color;
      ctx.strokeStyle = color;
      if (shape === "triangle") {
        ctx.beginPath();
        ctx.moveTo(x, y - 8);
        ctx.lineTo(x - 7, y + 6);
        ctx.lineTo(x + 7, y + 6);
        ctx.closePath();
        ctx.fill();
      } else {
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fill();
      }
      targets.push({
        type: shape === "triangle" ? "maintenance" : "fault",
        title: item.title || "",
        draw: "",
        ts: item.event_ts || "",
        value: "",
        x,
        y,
        radius: 11,
      });
    });
  };

  const maintY = eventTop + eventHeight * 0.34;
  const faultY = eventTop + eventHeight * 0.72;
  ctx.fillStyle = "rgba(196, 227, 229, 0.68)";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  ctx.fillText("Maint", padding.left - 8, maintY);
  ctx.fillText("Fault", padding.left - 8, faultY);
  drawEventMarkers(overlays.maintenance || [], maintY, "#ffd56f", "triangle");
  drawEventMarkers(overlays.faults || [], faultY, "#ff9ca6", "circle");

  return targets;
}

function bindDashboardPage(dashboardData) {
  const page = document.getElementById("dashboard-page");
  if (!page) return;
  const logSelect = document.getElementById("dashboard-log-select");
  const xSelect = document.getElementById("dashboard-x-select");
  const scaleModeSelect = document.getElementById("dashboard-scale-mode-select");
  const signalSearch = document.getElementById("dashboard-signal-search");
  const signalGrid = document.getElementById("dashboard-signal-grid");
  const plotShell = document.getElementById("dashboard-plot-shell");
  const plotTitle = document.getElementById("dashboard-plot-title");
  const selectedSignals = document.getElementById("dashboard-selected-signals");
  const zonePreview = document.getElementById("dashboard-zone-preview");
  const zoneStatus = document.getElementById("dashboard-zone-status");
  const savedList = document.getElementById("dashboard-zone-saved-list");
  const datasetSelect = document.getElementById("dashboard-dataset-select");
  const savePreviewBtn = document.getElementById("dashboard-save-preview-btn");
  const undoZoneBtn = document.getElementById("dashboard-undo-zone-btn");
  const clearZonesBtn = document.getElementById("dashboard-clear-zones-btn");
  const saveZonesBtn = document.getElementById("dashboard-save-zones-btn");
  const saveZonesLatestBtn = document.getElementById("dashboard-save-zones-latest-btn");
  const mathXSelect = document.getElementById("dashboard-math-x-select");
  const mathYSelect = document.getElementById("dashboard-math-y-select");
  const mathExpr = document.getElementById("dashboard-math-expr");
  const mathRunBtn = document.getElementById("dashboard-math-run-btn");
  const mathShell = document.getElementById("dashboard-math-shell");
  const mathPresetButtons = Array.from(page.querySelectorAll("[data-math-preset]"));
  let currentLog = null;
  let selectedY = [];
  let signalFilter = "";
  let previewZone = null;
  let savedZones = [];
  let anchorIndex = null;
  let transientBrush = null;

  const zoneKey = (zone) => `${zone.startIndex}:${zone.endIndex}`;

  const currentXColumn = () => xSelect?.value || currentLog?.suggested_x;

  const formatZoneLabel = (value) => {
    const text = String(value ?? "").trim();
    if (!text) return "—";
    const parts = text.split(" ");
    const tail = parts[parts.length - 1] || text;
    const compact = tail.replace(/\.\d+$/, "");
    return compact || text;
  };

  const zoneSummary = (zone) => {
    if (!currentLog) return "No zone";
    const xColumn = currentXColumn();
    const startLabel = currentLog?.x_display?.[xColumn]?.[zone.startIndex] || currentLog.rows[zone.startIndex]?.__x || zone.startIndex;
    const endLabel = currentLog?.x_display?.[xColumn]?.[zone.endIndex] || currentLog.rows[zone.endIndex]?.__x || zone.endIndex;
    return {
      start: formatZoneLabel(startLabel),
      end: formatZoneLabel(endLabel),
    };
  };

  const formatZoneMetric = (value) => {
    const num = Number(value);
    if (!Number.isFinite(num)) return "—";
    if (Math.abs(num) >= 100) return num.toFixed(1);
    if (Math.abs(num) >= 10) return num.toFixed(2);
    return num.toFixed(3);
  };

  const zoneSignalStats = (zone) => {
    if (!currentLog || !selectedY.length) return [];
    let startIndex = Number(zone.startIndex || 0);
    let endIndex = Number(zone.endIndex || 0);
    if (endIndex < startIndex) [startIndex, endIndex] = [endIndex, startIndex];
    const rows = currentLog.rows.slice(startIndex, endIndex + 1);
    return selectedY
      .map((column) => {
        const values = rows
          .map((row) => Number(row?.[column]))
          .filter((value) => Number.isFinite(value));
        if (!values.length) return null;
        const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
        return {
          column,
          avg,
          min: Math.min(...values),
          max: Math.max(...values),
        };
      })
      .filter(Boolean);
  };

  const syncZoneUi = ({ render = true } = {}) => {
    if (!zoneStatus || !savedList) return;
    zoneStatus.textContent = `Saved: ${savedZones.length} | Current mark: ${previewZone ? "ready" : "no"}`;
    savedList.innerHTML = savedZones.length
      ? savedZones.map((zone, index) => {
        const summary = zoneSummary(zone);
        const stats = zoneSignalStats(zone);
        return `
          <div class="dashboard-zone-item">
            <span>Zone ${index + 1}</span>
            <strong>${summary.start} -> ${summary.end}</strong>
            ${stats.length
              ? `<div class="dashboard-zone-stats">${stats
                .map((item) => `
                  <div class="dashboard-zone-stat">
                    <span>${item.column}</span>
                    <em>avg ${formatZoneMetric(item.avg)} · min ${formatZoneMetric(item.min)} · max ${formatZoneMetric(item.max)}</em>
                  </div>
                `)
                .join("")}</div>`
              : `<em>Choose plotted signals to see avg / min / max.</em>`}
          </div>
        `;
      }).join("")
      : `<div class="chart-empty">No saved zones yet.</div>`;
    if (render) {
      renderPlot();
    }
  };

  const rebuildPreview = () => {
    if (!currentLog || !zonePreview || !previewZone) {
      if (zonePreview) {
        zonePreview.textContent = "";
      }
      syncZoneUi({ render: false });
      return;
    }
    let startIndex = Number(previewZone.startIndex || 0);
    let endIndex = Number(previewZone.endIndex || 0);
    if (endIndex < startIndex) [startIndex, endIndex] = [endIndex, startIndex];
    previewZone = { startIndex, endIndex };
    const xColumn = currentXColumn();
    const startLabel = currentLog?.x_display?.[xColumn]?.[startIndex] || currentLog.rows[startIndex]?.__x || startIndex;
    const endLabel = currentLog?.x_display?.[xColumn]?.[endIndex] || currentLog.rows[endIndex]?.__x || endIndex;
    zonePreview.innerHTML = `
      <strong>${startLabel}</strong>
      <span>to</span>
      <strong>${endLabel}</strong>
      <span>${endIndex - startIndex + 1} points selected</span>
    `;
    syncZoneUi({ render: false });
  };

  const attachPlotInteraction = () => {
    const canvas = plotShell?.querySelector("#dashboard-plot-canvas");
    if (!canvas || !currentLog) return;
    const getGeometry = () => canvas.__dashboardGeometry || null;
    if (!getGeometry()) return;
    const clampIndex = (value, rowCount) => Math.max(0, Math.min(rowCount - 1, value));
      const xToIndex = (clientX) => {
        const geometry = getGeometry();
        if (!geometry?.rowCount) return 0;
        const rowCount = geometry.rowCount;
        const rect = canvas.getBoundingClientRect();
        const localX = clientX - rect.left;
        const plotLeft = geometry.plotLeft;
        const plotRight = geometry.plotRight;
        const plotX = Math.max(plotLeft, Math.min(plotRight, localX));
        if (plotX <= geometry.leftEdges[0]) {
          return 0;
        }
        if (plotX >= geometry.rightEdges[rowCount - 1]) {
          return rowCount - 1;
        }
        const hitIndex = geometry.leftEdges.findIndex((left, index) => plotX >= left && plotX <= geometry.rightEdges[index]);
        if (hitIndex !== -1) {
          return clampIndex(hitIndex, rowCount);
        }
        let nearestIndex = 0;
        let nearestDistance = Number.POSITIVE_INFINITY;
        geometry.xPixels.forEach((pixel, index) => {
          const distance = Math.abs(plotX - pixel);
          if (distance < nearestDistance) {
            nearestDistance = distance;
            nearestIndex = index;
          }
        });
      return clampIndex(nearestIndex, rowCount);
    };
    const redraw = () => {
      drawDashboardCanvas(currentLog, selectedY, {
        preview: previewZone,
        queued: [],
        saved: savedZones,
      }, canvas, transientBrush, currentXColumn(), scaleModeSelect?.value || "independent");
    };
    canvas.onmousemove = (event) => {
      if (anchorIndex === null) return;
      const hoverIndex = xToIndex(event.clientX);
      previewZone = {
        startIndex: anchorIndex,
        endIndex: hoverIndex,
      };
      transientBrush = { startIndex: anchorIndex, endIndex: hoverIndex };
      redraw();
      rebuildPreview();
    };
    canvas.onclick = (event) => {
      const hitIndex = xToIndex(event.clientX);
      if (anchorIndex === null) {
        anchorIndex = hitIndex;
        previewZone = { startIndex: hitIndex, endIndex: hitIndex };
        transientBrush = { startIndex: hitIndex, endIndex: hitIndex };
        redraw();
        rebuildPreview();
        return;
      }
      previewZone = { startIndex: anchorIndex, endIndex: hitIndex };
      const key = zoneKey(previewZone);
      if (!savedZones.some((zone) => zoneKey(zone) === key)) {
        savedZones = [...savedZones, { ...previewZone }];
      }
      anchorIndex = null;
      transientBrush = null;
      previewZone = null;
      redraw();
      rebuildPreview();
    };
    canvas.onmouseleave = () => {
      if (anchorIndex !== null) return;
      transientBrush = null;
      redraw();
    };
  };

  const renderSignalGrid = () => {
    if (!currentLog || !signalGrid) return;
    const visibleColumns = currentLog.numeric_columns.filter((column) =>
      !signalFilter || String(column).toLowerCase().includes(signalFilter),
    );
    signalGrid.innerHTML = visibleColumns.length
      ? visibleColumns.map((column) => `
        <label class="signal-toggle ${selectedY.includes(column) ? "is-active" : ""}">
          <input type="checkbox" value="${column}" ${selectedY.includes(column) ? "checked" : ""} />
          <span>${column}</span>
        </label>
      `)
      .join("")
      : `<div class="chart-empty">No signals match this search.</div>`;
    Array.from(signalGrid.querySelectorAll('input[type="checkbox"]')).forEach((input) => {
      input.addEventListener("change", () => {
        selectedY = Array.from(signalGrid.querySelectorAll('input[type="checkbox"]:checked')).map((item) => item.value).slice(0, 6);
        renderPlot();
        renderSignalGrid();
      });
    });
  };

  const renderPlot = () => {
    if (!currentLog) return;
    const yColumns = selectedY;
    const scaleMode = scaleModeSelect?.value || "independent";
    plotTitle.textContent = `${currentLog.selected_file} · ${currentLog.sample_count}/${currentLog.total_rows} rows`;
    plotShell.innerHTML = dashboardPlotMarkup(currentLog, yColumns);
    const canvas = plotShell.querySelector("#dashboard-plot-canvas");
    drawDashboardCanvas(currentLog, yColumns, {
      preview: previewZone,
      queued: [],
      saved: savedZones,
    }, canvas, transientBrush, currentXColumn(), scaleMode);
    attachPlotInteraction();
    selectedSignals.innerHTML = yColumns.length
      ? yColumns.map((column) => `<span class="token-chip is-accent">${column}</span>`).join("")
      : `<div class="chart-empty">No selected signals yet.</div>`;
  };

  const renderMathOptions = () => {
    if (!currentLog || !mathXSelect || !mathYSelect) return;
    const numeric = currentLog.numeric_columns || [];
    mathXSelect.innerHTML = numeric.map((column) => `<option value="${column}">${column}</option>`).join("");
    mathYSelect.innerHTML = [`<option value="">None</option>`, ...numeric.map((column) => `<option value="${column}">${column}</option>`)].join("");
    if (mathExpr && !String(mathExpr.value || "").trim()) {
      mathExpr.value = "A";
    }
  };

  const renderMathPlot = () => {
    if (!currentLog || !mathShell || !mathXSelect) return;
    const xCol = mathXSelect.value;
    const yCol = mathYSelect?.value || "";
    const timeCol = currentXColumn();
    const expr = String(mathExpr?.value || "A").trim() || "A";
    const displayExpr = expr
      .replace(/\bx\b/g, "A")
      .replace(/\by\b/g, "B");
    const xValues = currentLog.rows.map((row) => Number(row[xCol] ?? NaN));
    const yValues = yCol ? currentLog.rows.map((row) => Number(row[yCol] ?? NaN)) : [];
    let result = [];
    try {
      result = xValues.map((a, index) => {
        const b = yCol ? yValues[index] : undefined;
        return Function("A", "B", "x", "y", "Math", `return (${expr});`)(a, b, a, b, Math);
      });
    } catch (error) {
      mathShell.innerHTML = `<div class="chart-empty">${error.message}</div>`;
      return;
    }
    const rows = result
      .map((value, index) => ({ __x: currentLog.rows[index]?.__x ?? index, __math: Number(value) }))
      .filter((row) => Number.isFinite(row.__math));
    if (!rows.length) {
      mathShell.innerHTML = `<div class="chart-empty">Math expression did not return usable numeric values.</div>`;
      return;
    }
    const timeSeries = Array.isArray(currentLog?.x_series?.[timeCol]) ? currentLog.x_series[timeCol] : [];
    const timeDisplay = Array.isArray(currentLog?.x_display?.[timeCol]) ? currentLog.x_display[timeCol] : [];
    const mathRows = [];
    const mathXSeries = [];
    const mathXDisplay = [];
    result.forEach((value, index) => {
      if (!Number.isFinite(value)) return;
      mathRows.push({
        __x: currentLog.rows[index]?.__x ?? index,
        __math: Number(value),
      });
      mathXSeries.push(timeSeries[index] ?? index);
      mathXDisplay.push(timeDisplay[index] ?? currentLog.rows[index]?.__x ?? index);
    });
    const mathLog = {
      rows: mathRows,
      x_series: { [timeCol]: mathXSeries },
      x_display: { [timeCol]: mathXDisplay },
      suggested_x: timeCol,
      display_labels: { "__math": displayExpr },
      export_meta: {
        log_name: currentLog?.selected_file || "",
        expression: displayExpr,
        a_label: xCol,
        b_label: yCol || "",
      },
    };
    mathShell.innerHTML = `
      <div class="chart-head">
        <span>Math result</span>
        <strong>${displayExpr}</strong>
        <button class="action-btn action-secondary" type="button" id="dashboard-math-download-btn">Download Plot</button>
      </div>
      ${dashboardMathPlotMarkup()}
    `;
    const mathCanvas = mathShell.querySelector("#dashboard-math-canvas");
    drawDashboardCanvas(mathLog, ["__math"], { preview: null, queued: [], saved: [] }, mathCanvas, null, timeCol, "shared");
    const downloadBtn = mathShell.querySelector("#dashboard-math-download-btn");
    downloadBtn?.addEventListener("click", async () => {
      const safeExpr = displayExpr.replace(/[^a-z0-9]+/gi, "_").replace(/^_+|_+$/g, "").slice(0, 48) || "math_plot";
      const filename = `tower_math_${safeExpr}.png`;
      downloadBtn.disabled = true;
      downloadBtn.textContent = "Preparing...";
      try {
        const response = await fetch("/api/dashboard/math-plot-export", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            filename,
            content: mathCanvas.toDataURL("image/png"),
          }),
        });
        const payload = await response.json();
        if (!response.ok || !payload?.ok || !payload?.saved_path) {
          throw new Error(payload?.message || "Plot export failed.");
        }
        alert(`Saved plot to:\n${payload.saved_path}`);
      } catch (error) {
        alert(error.message || "Plot export failed.");
      } finally {
        downloadBtn.disabled = false;
        downloadBtn.textContent = "Download Plot";
      }
    });
  };

  const loadLog = async (logName) => {
    plotShell.innerHTML = `<div class="loading-state">Loading ${logName}...</div>`;
    const response = await fetch(`/api/dashboard/log?name=${encodeURIComponent(logName)}`);
    currentLog = await response.json();
    xSelect.innerHTML = currentLog.x_options.map((column) => `<option value="${column}" ${column === currentLog.suggested_x ? "selected" : ""}>${column}</option>`).join("");
    selectedY = [];
    signalFilter = "";
    if (signalSearch) {
      signalSearch.value = "";
    }
    anchorIndex = null;
    transientBrush = null;
    previewZone = null;
    savedZones = [];
    renderSignalGrid();
    renderMathOptions();
    renderPlot();
    rebuildPreview();
  };

  logSelect?.addEventListener("change", () => {
    loadLog(logSelect.value);
  });

  signalSearch?.addEventListener("input", () => {
    signalFilter = String(signalSearch.value || "").trim().toLowerCase();
    renderSignalGrid();
  });

  xSelect?.addEventListener("change", () => {
    anchorIndex = null;
    transientBrush = null;
    previewZone = null;
    renderPlot();
    rebuildPreview();
  });

  scaleModeSelect?.addEventListener("change", () => {
    renderPlot();
  });

  savePreviewBtn?.addEventListener("click", () => {
    if (!previewZone) return;
    const key = zoneKey(previewZone);
    if (!savedZones.some((zone) => zoneKey(zone) === key)) {
      savedZones = [...savedZones, { ...previewZone }];
    }
    previewZone = null;
    anchorIndex = null;
    transientBrush = null;
    syncZoneUi();
  });
  undoZoneBtn?.addEventListener("click", () => {
    savedZones = savedZones.slice(0, -1);
    syncZoneUi();
  });
  clearZonesBtn?.addEventListener("click", () => {
    anchorIndex = null;
    transientBrush = null;
    previewZone = null;
    savedZones = [];
    rebuildPreview();
  });
  const saveZones = async (datasetCsv) => {
    if (!savedZones.length) return;
    try {
      const result = await postJson("/api/dashboard/save-zones", {
        logName: currentLog?.selected_file,
        datasetCsv,
        zones: savedZones,
      });
      selectedSignals.innerHTML = `<span class="token-chip is-accent">${result.message}</span>` + selectedSignals.innerHTML;
      savedList.innerHTML = `<div class="micro-panel">Saved ${savedZones.length} zone(s) into <strong>${datasetCsv || dashboardData.latest_dataset || "dataset"}</strong>.</div>` + savedList.innerHTML;
    } catch (error) {
      selectedSignals.innerHTML = `<span class="token-chip">${error.message}</span>` + selectedSignals.innerHTML;
    }
  };
  saveZonesBtn?.addEventListener("click", async () => saveZones(datasetSelect?.value));
  saveZonesLatestBtn?.addEventListener("click", async () => saveZones(dashboardData.latest_dataset || datasetSelect?.value));
  mathRunBtn?.addEventListener("click", renderMathPlot);
  mathPresetButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (mathExpr) {
        mathExpr.value = button.dataset.mathPreset || "x";
      }
      renderMathPlot();
    });
  });

  loadLog(dashboardData.latest_log || dashboardData.available_logs[0] || "");
}

function bindSchedulePage(scheduleData) {
  const page = document.getElementById("schedule-page");
  const root = document.getElementById("schedule-canvas-root");
  if (!page || !root) return;

  let currentView = "week";
  let currentAnchor = page.dataset.scheduleAnchor || todayIsoDate();
  const toggleButtons = Array.from(page.querySelectorAll("[data-schedule-view]"));
  const navButtons = Array.from(page.querySelectorAll("[data-schedule-nav]"));
  const addForm = document.getElementById("schedule-add-form");
  const deleteForm = document.getElementById("schedule-delete-form");
  const saveMasterBtn = document.getElementById("schedule-save-master-btn");
  const reloadMasterBtn = document.getElementById("schedule-reload-master-btn");

  const render = () => {
    root.innerHTML = renderScheduleCanvas(scheduleData, currentView, currentAnchor);
    const canvas = root.querySelector("#schedule-canvas");
    const detailCard = root.querySelector("#schedule-micro-detail");
    const detailHead = detailCard?.querySelector(".schedule-micro-detail-head strong");
    const detailBody = detailCard?.querySelector(".schedule-micro-detail-body");
    const stops = Array.from(root.querySelectorAll(".schedule-micro-stop"));
    let detailHideTimer = null;
    const clearDetailHideTimer = () => {
      if (detailHideTimer) {
        window.clearTimeout(detailHideTimer);
        detailHideTimer = null;
      }
    };
    const positionDetail = (stop, pointerEvent = null) => {
      if (!canvas || !detailCard || !stop) return;
      const canvasRect = canvas.getBoundingClientRect();
      const stopRect = stop.getBoundingClientRect();
      const cardWidth = detailCard.offsetWidth || 360;
      const cardHeight = detailCard.offsetHeight || 260;
      const pointerX = pointerEvent ? pointerEvent.clientX - canvasRect.left : stopRect.left - canvasRect.left + (stopRect.width / 2);
      const belowTop = stopRect.bottom - canvasRect.top + 8;
      const aboveTop = stopRect.top - canvasRect.top - cardHeight - 14;
      const maxLeft = Math.max(12, canvasRect.width - cardWidth - 12);
      const desiredLeft = Math.min(Math.max(pointerX - (cardWidth / 2), 12), maxLeft);
      const maxTop = Math.max(12, canvasRect.height - cardHeight - 12);
      const desiredTop = belowTop > maxTop && aboveTop >= 52
        ? aboveTop
        : Math.min(Math.max(belowTop, 52), maxTop);
      detailCard.style.setProperty("--schedule-detail-left", `${desiredLeft}px`);
      detailCard.style.setProperty("--schedule-detail-top", `${desiredTop}px`);
      detailCard.classList.toggle("is-above", desiredTop === aboveTop && aboveTop >= 52);
    };
    const resetDetail = () => {
      clearDetailHideTimer();
      detailCard?.classList.remove("is-visible");
      if (detailHead) detailHead.textContent = "Move over a day";
      if (detailBody) detailBody.textContent = "Event details will appear here.";
    };
    const queueResetDetail = () => {
      clearDetailHideTimer();
      detailHideTimer = window.setTimeout(() => {
        detailHideTimer = null;
        resetDetail();
      }, 140);
    };
    const setDetail = (stop, pointerEvent = null) => {
      if (!stop || !detailHead || !detailBody) return;
      clearDetailHideTimer();
      detailHead.textContent = stop.dataset.detailTitle || "Day detail";
      detailBody.innerHTML = stop.dataset.detailBodyHtml || "No scheduled events in this window.";
      positionDetail(stop, pointerEvent);
      detailCard?.classList.add("is-visible");
    };
    stops.forEach((stop) => {
      stop.addEventListener("mouseenter", (event) => setDetail(stop, event));
      stop.addEventListener("mousemove", (event) => setDetail(stop, event));
      stop.addEventListener("focus", () => setDetail(stop));
      stop.addEventListener("mouseleave", (event) => {
        const nextTarget = event.relatedTarget;
        if (nextTarget instanceof Element && (detailCard?.contains(nextTarget) || nextTarget.closest(".schedule-micro-stop"))) {
          return;
        }
        queueResetDetail();
      });
      stop.addEventListener("blur", resetDetail);
    });
    detailCard?.addEventListener("mouseenter", clearDetailHideTimer);
    detailCard?.addEventListener("mouseleave", (event) => {
      const nextTarget = event.relatedTarget;
      if (nextTarget instanceof Element && nextTarget.closest(".schedule-micro-stop")) {
        return;
      }
      queueResetDetail();
    });
    toggleButtons.forEach((button) => {
      button.classList.toggle("is-active", button.dataset.scheduleView === currentView);
    });
  };

  toggleButtons.forEach((button) => {
    button.addEventListener("click", () => {
      currentView = button.dataset.scheduleView;
      render();
    });
  });

  navButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.dataset.scheduleNav;
      if (action === "today") {
        currentAnchor = todayIsoDate();
      } else if (action === "prev") {
        currentAnchor = currentView === "week" ? addDaysToIsoDate(currentAnchor, -7) : addDaysToIsoDate(currentAnchor, -35);
      } else if (action === "next") {
        currentAnchor = currentView === "week" ? addDaysToIsoDate(currentAnchor, 7) : addDaysToIsoDate(currentAnchor, 35);
      }
      render();
    });
  });

  addForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(addForm).entries());
    const result = await postJson("/api/schedule/add", payload);
    bootstrapData = result.bootstrap || null;
    await renderRoute();
  });

  deleteForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(deleteForm).entries());
    const result = await postJson("/api/schedule/delete", payload);
    bootstrapData = result.bootstrap || null;
    await renderRoute();
  });

  saveMasterBtn?.addEventListener("click", async () => {
    const rows = Array.from(page.querySelectorAll(".schedule-master-row")).map((row) => ({
      event_type: row.querySelector('[data-schedule-field="event_type"]')?.value || "",
      start: row.querySelector('[data-schedule-field="start"]')?.value || "",
      end: row.querySelector('[data-schedule-field="end"]')?.value || "",
      description: row.querySelector('[data-schedule-field="description"]')?.value || "",
      recurrence: row.querySelector('[data-schedule-field="recurrence"]')?.value || "",
    }));
    const result = await postJson("/api/schedule/save-master", { rows });
    bootstrapData = result.bootstrap || null;
    await renderRoute();
  });

  reloadMasterBtn?.addEventListener("click", async () => {
    await renderRoute();
  });

  render();
}

function bindMaintenancePage(maintenanceData) {
  const page = document.getElementById("maintenance-page");
  if (!page) return;
  const currentUrl = new URL(window.location.href);
  const runtimeQueryKeys = ["furnaceHours", "uv1Hours", "uv2Hours", "drawCount"];
  if (runtimeQueryKeys.some((key) => currentUrl.searchParams.has(key))) {
    runtimeQueryKeys.forEach((key) => currentUrl.searchParams.delete(key));
    history.replaceState(null, "", currentUrl.toString());
  }
  const groupRoot = document.getElementById("maintenance-group-root");
  const groupButtons = Array.from(page.querySelectorAll("[data-maint-group]"));
  let activeGroup = page.dataset.maintGroup || "maintenance";
  if (!MAINT_GROUPS.some((group) => group.key === activeGroup)) {
    activeGroup = "maintenance";
    page.dataset.maintGroup = activeGroup;
  }
  let activeView = page.dataset.maintView || "builder";
  if (!MAINT_VIEWS.some((view) => view.key === activeView)) activeView = "builder";
  let searchValue = page.dataset.maintSearch || "";
  let componentFilter = page.dataset.maintComponent || "";
  let packageFilter = page.dataset.maintPackage || "";
  let pickerOpen = page.dataset.maintPickerOpen === "1";
  let createTaskOpen = page.dataset.maintCreateTaskOpen === "1";
  let runtimeFoldOpen = page.dataset.maintRuntimeOpen === "1";
  let selectedTaskId = page.dataset.maintTaskId || (maintenanceData.tasks[0] || maintenanceData.prep_queue[0] || {}).task_id || "";
  let prepCutoffProgress = page.dataset.maintPrepCutoff || "";
  let prepCutoffMap = parseMaintenancePrepCutoffMap(prepCutoffProgress);
  let prepReadyProgress = page.dataset.maintPrepReady || "";
  let prepReadyMap = parseMaintenancePrepCutoffMap(prepReadyProgress);
  let prepFocusLaneKey = page.dataset.maintPrepFocusLane || "";
  let executeEntryMode = page.dataset.maintExecuteMode || "";
  let executeOpenTaskId = page.dataset.maintExecuteTaskId || "";
  let executeManualSearch = page.dataset.maintExecuteManualSearch || "";
  let executeManualComponent = page.dataset.maintExecuteManualComponent || "";
  let prepHorizonProgress = page.dataset.maintPrepHorizon || localStorage.getItem(MAINT_PREP_HORIZON_STORAGE_KEY) || "";
  let prepHorizonMap = parseMaintenancePrepHorizonMap(prepHorizonProgress);
  let prepHorizonFoldOpen = localStorage.getItem(MAINT_PREP_HORIZON_FOLD_STORAGE_KEY) === "1";
  let prepStageKey = page.dataset.maintPrepStage || "need-prep";
  let prepActionState = parseMaintenanceStageActionState(page.dataset.maintPrepAction || "");
  let prepSelectedTaskIds = parseMaintenanceTaskIdList(page.dataset.maintPrepSelected || "");
  let builderSectionState = parseMaintenanceBuilderSectionState(page.dataset.maintBuilderSections || "");
  let faultEditorState = page.dataset.maintFaultEditor || "";
  page.dataset.maintPrepHorizon = prepHorizonProgress;
  const taskLookup = () => buildMaintenanceStageTaskLookup(maintenanceData, prepHorizonMap);

  const selectedTask = () => taskLookup().get(selectedTaskId);
  const setPrepSelectedTaskIds = (taskIds = []) => {
    prepSelectedTaskIds = dedupeStrings(taskIds.map((item) => String(item || "").trim()).filter(Boolean));
    if (prepSelectedTaskIds.length) {
      page.dataset.maintPrepSelected = JSON.stringify(prepSelectedTaskIds);
    } else {
      delete page.dataset.maintPrepSelected;
    }
  };
  const placeMaintenancePartsOrders = async (tasks = [], clearTaskIds = []) => {
    const orderableTasks = tasks
      .filter((task) => maintenanceTaskOrderableParts(task).length)
      .map((task) => ({
        taskId: task.task_id,
        component: task.component,
        task: task.task,
        parts: maintenanceTaskOrderableParts(task),
      }));
    if (!orderableTasks.length) {
      maintenanceStageFlash = { kind: "warn", message: "No missing parts in this selection." };
      prepActionState = null;
      delete page.dataset.maintPrepAction;
      renderMaintenanceWorkspace();
      return;
    }
    const result = await postJson("/api/maintenance/create-parts-orders", { tasks: orderableTasks });
    const orderedTaskCount = orderableTasks.length;
    const orderedPartCount = orderableTasks.reduce((sum, task) => sum + (task.parts || []).length, 0);
    maintenanceStageFlash = {
      kind: "good",
      message: result.message || `${orderedPartCount} part order${orderedPartCount === 1 ? "" : "s"} placed for ${orderedTaskCount} task${orderedTaskCount === 1 ? "" : "s"}. Waiting for parts now.`,
    };
    prepActionState = null;
    delete page.dataset.maintPrepAction;
    bootstrapData = result.bootstrap || bootstrapData;
    maintenanceData = bootstrapData?.maintenance || maintenanceData;
    activeView = "plan";
    page.dataset.maintView = activeView;
    prepStageKey = "need-prep";
    page.dataset.maintPrepStage = prepStageKey;
    if (clearTaskIds.length) {
      setPrepSelectedTaskIds(prepSelectedTaskIds.filter((item) => !clearTaskIds.includes(item)));
    } else {
      setPrepSelectedTaskIds([]);
    }
    selectedTaskId = orderableTasks[0]?.taskId || selectedTaskId;
    page.dataset.maintTaskId = selectedTaskId;
    renderMaintenanceWorkspace();
  };

  const renderMaintenanceGroupRoot = () => `
    ${activeView === "plan"
      ? ""
      : `
        <div class="maintenance-shared-timeline">
          ${maintenanceHeaderTimelineMarkup(maintenanceData, prepHorizonMap, {
            sourceTasks: activeView === "builder" ? maintenancePrepTimelineSourceTasks(maintenanceData) : undefined,
            showPreviewItems: activeView !== "builder",
          })}
        </div>
      `}
    <div class="maintenance-mode-strip">
      ${MAINT_VIEWS.map((view) => `
        <button class="maintenance-mode-btn ${activeView === view.key ? "is-active" : ""}" type="button" data-maint-view="${view.key}">
          <span>${view.title}</span>
          <strong>${view.sub}</strong>
        </button>
      `).join("")}
    </div>
    <div id="maintenance-context-root"></div>
    ${activeView === "builder"
      ? `
        <section class="maintenance-flow-shell maintenance-flow-${activeView}">
          <div class="maintenance-builder-shell maintenance-stage-shell-wide">
            <div id="maintenance-builder-root"></div>
          </div>
        </section>
      `
      : activeView === "plan"
        ? `
          <section class="maintenance-flow-shell maintenance-flow-${activeView} maintenance-flow-plan-wide">
            <div id="maintenance-plan-primary" class="maintenance-plan-primary"></div>
          </section>
        `
        : activeView === "execute"
          ? `
            <section class="maintenance-flow-shell maintenance-flow-${activeView} maintenance-flow-execute-launch">
              <div id="maintenance-execute-launcher-root" class="maintenance-stage-shell maintenance-stage-shell-wide"></div>
            </section>
          `
        : `
          <section class="maintenance-flow-shell maintenance-flow-${activeView}">
            <aside class="maintenance-pick-shell">
              <div class="chart-head">
                <span id="maintenance-list-eyebrow">Builder queue</span>
                <strong id="maintenance-list-title">Maintenance tasks</strong>
              </div>
              <div class="maintenance-toolbar">
                <input class="parts-search-input" id="maintenance-search-input" placeholder="Search task / task id / component..." value="${searchValue.replace(/"/g, "&quot;")}" />
              </div>
              <div class="maintenance-list" id="maintenance-list"></div>
            </aside>
            <div class="maintenance-stage-shell">
              <div class="chart-head">
                <span id="maintenance-detail-eyebrow">Task focus</span>
                <strong id="maintenance-detail-title">Selected task workspace</strong>
              </div>
              <div id="maintenance-detail-panel"></div>
              <div class="maintenance-action-panel" id="maintenance-action-panel"></div>
            </div>
            <aside class="maintenance-side-shell" id="maintenance-side-panel"></aside>
          </section>
        `}
  `;

  const modeMeta = () => {
    if (activeView === "builder") return {
      listEyebrow: "Builder queue",
      listTitle: "Maintenance tasks",
      detailEyebrow: "Work package",
      detailTitle: "Builder workspace",
    };
    if (activeView === "plan") return {
      listEyebrow: "Plan + Prepare",
      listTitle: "Preparation queue",
      detailEyebrow: "Prep focus",
      detailTitle: "Preparation workspace",
    };
    if (activeView === "execute") return {
      listEyebrow: "Execute",
      listTitle: "Execution queue",
      detailEyebrow: "Execution focus",
      detailTitle: "Task action workspace",
    };
    if (activeView === "blocked") return {
      listEyebrow: "Blocked + Parts",
      listTitle: "Blocked task tracker",
      detailEyebrow: "Blocker focus",
      detailTitle: "Resolve blocker",
    };
    return {
      listEyebrow: "History",
      listTitle: "Recent maintenance actions",
      detailEyebrow: "History focus",
      detailTitle: "Action detail",
    };
  };

  const currentRows = () => {
    if (activeView === "builder") return maintenanceData.tasks || [];
    if (activeView === "execute") return maintenanceData.execute_queue || [];
    if (activeView === "blocked") return maintenanceData.blocked_tracker || [];
    if (activeView === "history") return maintenanceData.recent_actions || [];
    return maintenanceData.prep_queue || [];
  };

  const renderMaintenanceWorkspace = () => {
    if (!groupRoot) return;
    groupRoot.innerHTML = renderMaintenanceGroupRoot();
    const builderRoot = document.getElementById("maintenance-builder-root");
    const listRoot = document.getElementById("maintenance-list");
    const detailRoot = document.getElementById("maintenance-detail-panel");
    const actionRoot = document.getElementById("maintenance-action-panel");
    const contextRoot = document.getElementById("maintenance-context-root");
    const planPrimaryRoot = document.getElementById("maintenance-plan-primary");
    const executeLauncherRoot = document.getElementById("maintenance-execute-launcher-root");
    const sideRoot = document.getElementById("maintenance-side-panel");
    const listEyebrow = document.getElementById("maintenance-list-eyebrow");
    const listTitle = document.getElementById("maintenance-list-title");
    const detailEyebrow = document.getElementById("maintenance-detail-eyebrow");
    const detailTitle = document.getElementById("maintenance-detail-title");
    const searchInput = document.getElementById("maintenance-search-input");

    const renderActionPanel = (task) => {
      if (activeView === "builder") {
        if (!task || !builderRoot) return;
        builderRoot.innerHTML = maintenanceBuilderWorkspaceMarkup(task, rows, selectedTaskId, {
          search: searchValue,
          component: componentFilter,
          package: packageFilter,
          open: pickerOpen,
          createOpen: createTaskOpen,
        }, maintenanceData.tasks || []);
        bindMaintenanceBuilderSections(builderRoot, builderSectionState, (nextState) => {
          builderSectionState = nextState;
          page.dataset.maintBuilderSections = JSON.stringify(builderSectionState);
        });
        const builderPicker = builderRoot.querySelector(".maintenance-builder-picker");
        const createToggles = Array.from(builderRoot.querySelectorAll("[data-maint-create-toggle]") || []);
        const pickerLaunchers = Array.from(builderRoot.querySelectorAll("[data-maint-open-picker]") || []);
        const editTaskButtons = Array.from(builderRoot.querySelectorAll("[data-maint-edit-task-name]") || []);
        const createForm = builderRoot.querySelector("#maintenance-builder-create-form");
        const builderSearchInput = builderRoot.querySelector("#maintenance-builder-search-input");
        const builderComponentFilter = builderRoot.querySelector("#maintenance-builder-component-filter");
        const builderPackageFilter = builderRoot.querySelector("#maintenance-builder-package-filter");
        builderPicker?.addEventListener("toggle", () => {
          pickerOpen = builderPicker.open;
          page.dataset.maintPickerOpen = pickerOpen ? "1" : "0";
        });
        createToggles.forEach((createToggle) => {
          createToggle.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            pickerOpen = true;
            createTaskOpen = !createTaskOpen;
            page.dataset.maintPickerOpen = "1";
            page.dataset.maintCreateTaskOpen = createTaskOpen ? "1" : "0";
            renderMaintenanceWorkspace();
          });
        });
        pickerLaunchers.forEach((launcher) => {
          launcher.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            pickerOpen = true;
            page.dataset.maintPickerOpen = "1";
            page.dataset.maintCreateTaskOpen = createTaskOpen ? "1" : "0";
            renderMaintenanceWorkspace();
          });
        });
        editTaskButtons.forEach((button) => {
          button.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            const taskProfileSection = Array.from(builderRoot.querySelectorAll(".maintenance-builder-section") || []).find((section) => {
              const label = String(section.querySelector(".maintenance-builder-section-head span")?.textContent || "").trim().toLowerCase();
              return label === "task profile";
            });
            const taskProfileHead = taskProfileSection?.querySelector(".maintenance-builder-section-head");
            if (taskProfileSection?.classList.contains("is-collapsed")) {
              taskProfileHead?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
            }
            window.requestAnimationFrame(() => {
              const taskInput = builderRoot.querySelector('#maintenance-builder-form input[name="task"]');
              taskInput?.scrollIntoView({ block: "center", behavior: "smooth" });
              taskInput?.focus();
              taskInput?.select?.();
            });
          });
        });
        createForm?.addEventListener("submit", async (event) => {
          event.preventDefault();
          const formData = new FormData(createForm);
          const payload = {
            sourceFile: String(formData.get("sourceFile") || "").trim(),
            component: String(formData.get("component") || "").trim() || "General",
            task: String(formData.get("task") || "").trim(),
            taskGroup: String(formData.get("taskGroup") || "").trim() || "General",
          };
          if (!payload.task) {
            window.alert("Task name is required.");
            return;
          }
          try {
            const result = await postJson("/api/maintenance/create-task", payload);
            bootstrapData = result.bootstrap || null;
            selectedTaskId = String(result.taskId || "").trim();
            searchValue = "";
            componentFilter = "";
            packageFilter = "";
            pickerOpen = true;
            createTaskOpen = false;
            page.dataset.maintTaskId = selectedTaskId;
            page.dataset.maintSearch = "";
            page.dataset.maintComponent = "";
            page.dataset.maintPackage = "";
            page.dataset.maintPickerOpen = "1";
            page.dataset.maintCreateTaskOpen = "0";
            await renderRoute();
          } catch (error) {
            window.alert(error?.message || "Failed to create maintenance task.");
          }
        });
        builderSearchInput?.addEventListener("input", () => {
          pickerOpen = true;
          page.dataset.maintPickerOpen = "1";
          searchValue = builderSearchInput.value || "";
          page.dataset.maintSearch = searchValue;
          renderMaintenanceWorkspace();
        });
        builderComponentFilter?.addEventListener("change", () => {
          pickerOpen = true;
          page.dataset.maintPickerOpen = "1";
          componentFilter = builderComponentFilter.value || "";
          page.dataset.maintComponent = componentFilter;
          renderMaintenanceWorkspace();
        });
        builderPackageFilter?.addEventListener("change", () => {
          pickerOpen = true;
          page.dataset.maintPickerOpen = "1";
          packageFilter = builderPackageFilter.value || "";
          page.dataset.maintPackage = packageFilter;
          renderMaintenanceWorkspace();
        });
        Array.from(builderRoot.querySelectorAll("[data-maint-select]") || []).forEach((button) => {
          button.addEventListener("click", () => {
            pickerOpen = true;
            page.dataset.maintPickerOpen = "1";
            selectedTaskId = button.dataset.maintSelect;
            page.dataset.maintTaskId = selectedTaskId;
            renderMaintenanceWorkspace();
          });
        });
        Array.from(builderRoot.querySelectorAll("[data-maint-delete-task]") || []).forEach((button) => {
          button.addEventListener("click", async () => {
            const taskId = String(button.dataset.maintDeleteTask || "").trim();
            const component = String(button.dataset.maintDeleteComponent || "").trim();
            const taskLabel = String(button.dataset.maintDeleteLabel || "").trim();
            const sourceFile = String(button.dataset.maintDeleteSource || "").trim();
            const confirmed = window.confirm(`Delete maintenance task "${component} — ${taskLabel}" from the builder source?`);
            if (!confirmed) return;
            const result = await postJson("/api/maintenance/delete-task", {
              taskId,
              component,
              task: taskLabel,
              sourceFile,
            });
            bootstrapData = result.bootstrap || null;
            if (selectedTaskId === taskId) {
              selectedTaskId = "";
              page.dataset.maintTaskId = "";
            }
            await renderRoute();
          });
        });
        const form = builderRoot.querySelector("#maintenance-builder-form");
        const fallRiskSelect = builderRoot.querySelector("#maintenance-fall-risk-select");
        const tnmPresenceInput = builderRoot.querySelector("#maintenance-tnm-presence-input");
        const requiredPartsInput = builderRoot.querySelector("#maintenance-required-parts-input");
        const requiredPartsSearch = builderRoot.querySelector("#maintenance-required-parts-search");
        const requiredPartsSelected = builderRoot.querySelector("#maintenance-required-parts-selected");
        const requiredPartsSuggestions = builderRoot.querySelector("#maintenance-required-parts-suggestions");
        const requiredToolsInput = builderRoot.querySelector("#maintenance-required-tools-input");
        const requiredToolsSearch = builderRoot.querySelector("#maintenance-required-tools-search");
        const requiredToolsSelected = builderRoot.querySelector("#maintenance-required-tools-selected");
        const requiredToolsSuggestions = builderRoot.querySelector("#maintenance-required-tools-suggestions");
        const photoInput = builderRoot.querySelector("#maintenance-photo-file-input");
        const photoValueInput = builderRoot.querySelector("#maintenance-procedure-photos-input");
        const checklistEditors = Array.from(builderRoot.querySelectorAll("[data-maint-checklist-editor]") || []);
        const builderMeta = collectMaintenanceBuilderMeta(rows);
        let selectedParts = parseBuilderPartsValue(requiredPartsInput?.value || "");
        let selectedTools = parseBuilderPartsValue(requiredToolsInput?.value || "");
        let photoItems = parseBuilderPhotoItems(photoValueInput?.value || "");
        let pendingPhotoUploads = [];
        let pendingPhotoTarget = null;
        const builderContextNeedle = [task?.component, task?.task, task?.manual_name, task?.manual_link]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        const preparationChecklistInput = form?.querySelector('input[name="preparationChecklist"]');
        const procedureStepsInput = form?.querySelector('input[name="procedureSteps"]');
        const getPhotoTargetOptions = () =>
          buildMaintenancePhotoTargetOptions(
            preparationChecklistInput?.value || "",
            procedureStepsInput?.value || task?.procedure_summary || "",
          );

        const syncTnmField = () => {
          if (!fallRiskSelect || !tnmPresenceInput) return;
          tnmPresenceInput.value = deriveMaintenanceTnmPresence(fallRiskSelect.value, tnmPresenceInput.value);
        };

        const syncRequiredPartsField = () => {
          if (!requiredPartsInput || !requiredPartsSelected) return;
          requiredPartsInput.value = selectedParts.join("; ");
          requiredPartsSelected.innerHTML = selectedParts.length
            ? selectedParts
                .map(
                  (part) => `
                    <button class="maintenance-parts-chip" type="button" data-maint-part-chip="${escapeHtml(part)}">
                      <span>${escapeHtml(part)}</span>
                      <strong>×</strong>
                    </button>
                  `,
                )
                .join("")
            : `<span class="maintenance-parts-placeholder">Add inventory parts</span>`;
          Array.from(requiredPartsSelected.querySelectorAll("[data-maint-part-chip]")).forEach((button) => {
            button.addEventListener("click", () => {
              selectedParts = selectedParts.filter((item) => item !== button.dataset.maintPartChip);
              syncRequiredPartsField();
              renderPartSuggestions(requiredPartsSearch?.value || "");
            });
          });
        };

        const syncRequiredToolsField = () => {
          if (!requiredToolsInput || !requiredToolsSelected) return;
          requiredToolsInput.value = selectedTools.join("; ");
          requiredToolsSelected.innerHTML = selectedTools.length
            ? selectedTools
                .map(
                  (tool) => `
                    <button class="maintenance-parts-chip maintenance-parts-chip-tool" type="button" data-maint-tool-chip="${escapeHtml(tool)}">
                      <span>${escapeHtml(tool)}</span>
                      <strong>×</strong>
                    </button>
                  `,
                )
                .join("")
            : `<span class="maintenance-parts-placeholder">Add inventory tools</span>`;
          Array.from(requiredToolsSelected.querySelectorAll("[data-maint-tool-chip]")).forEach((button) => {
            button.addEventListener("click", () => {
              selectedTools = selectedTools.filter((item) => item !== button.dataset.maintToolChip);
              syncRequiredToolsField();
              renderToolSuggestions(requiredToolsSearch?.value || "");
            });
          });
        };

        const scorePartSuggestion = (part, needle) => {
          const lowered = String(part || "").toLowerCase();
          let score = 0;
          if (needle && lowered.startsWith(needle)) score += 6;
          if (needle && lowered.includes(needle)) score += 3;
          if (builderContextNeedle && builderContextNeedle.includes(lowered)) score += 4;
          if (task?.required_parts?.includes(part)) score += 2;
          if (task?.missing_parts?.includes(part)) score += 5;
          return score;
        };

        const renderPartSuggestions = (query = "") => {
          if (!requiredPartsSuggestions) return;
          const needle = String(query || "").trim().toLowerCase();
          if (!needle) {
            requiredPartsSuggestions.innerHTML = "";
            return;
          }
          const suggestions = builderMeta.partOptions
            .filter((item) => !selectedParts.includes(item))
            .filter((item) => !needle || item.toLowerCase().includes(needle))
            .sort((left, right) => scorePartSuggestion(right, needle) - scorePartSuggestion(left, needle) || left.localeCompare(right))
            .slice(0, 10);
          requiredPartsSuggestions.innerHTML = suggestions.length
            ? suggestions
                .map(
                  (part) => `
                    <div class="maintenance-parts-suggestion" role="button" tabindex="0" data-maint-part-option="${escapeHtml(part)}">
                      <div class="maintenance-parts-suggestion-copy">
                        <strong>${escapeHtml(part)}</strong>
                        <span>${task?.missing_parts?.includes(part) ? "Missing on this task" : "Relevant match"}</span>
                      </div>
                      <em>Add</em>
                    </div>
                  `,
                )
                .join("")
            : `<span class="maintenance-parts-empty">No relevant part match</span>`;
          const bindSuggestion = (node) => {
            node.addEventListener("click", () => {
              const option = node.dataset.maintPartOption;
              if (!option) return;
              selectedParts = dedupeStrings([...selectedParts, option]);
              if (requiredPartsSearch) requiredPartsSearch.value = "";
              syncRequiredPartsField();
              renderPartSuggestions("");
            });
            node.addEventListener("keydown", (event) => {
              if (!["Enter", " "].includes(event.key)) return;
              event.preventDefault();
              node.click();
            });
          };
          Array.from(requiredPartsSuggestions.querySelectorAll("[data-maint-part-option]")).forEach(bindSuggestion);
        };

        const scoreToolSuggestion = (tool, needle) => {
          const lowered = String(tool || "").toLowerCase();
          let score = 0;
          if (needle && lowered.startsWith(needle)) score += 6;
          if (needle && lowered.includes(needle)) score += 3;
          if (builderContextNeedle && builderContextNeedle.includes(lowered)) score += 4;
          if (task?.required_tools?.includes(tool)) score += 2;
          return score;
        };

        const renderToolSuggestions = (query = "") => {
          if (!requiredToolsSuggestions) return;
          const needle = String(query || "").trim().toLowerCase();
          if (!needle) {
            requiredToolsSuggestions.innerHTML = "";
            return;
          }
          const suggestions = builderMeta.toolOptions
            .filter((item) => !selectedTools.includes(item))
            .filter((item) => !needle || item.toLowerCase().includes(needle))
            .sort((left, right) => scoreToolSuggestion(right, needle) - scoreToolSuggestion(left, needle) || left.localeCompare(right))
            .slice(0, 10);
          requiredToolsSuggestions.innerHTML = suggestions.length
            ? suggestions
                .map(
                  (tool) => `
                    <div class="maintenance-parts-suggestion" role="button" tabindex="0" data-maint-tool-option="${escapeHtml(tool)}">
                      <div class="maintenance-parts-suggestion-copy">
                        <strong>${escapeHtml(tool)}</strong>
                        <span>Relevant tool match</span>
                      </div>
                      <em>Add</em>
                    </div>
                  `,
                )
                .join("")
            : `<span class="maintenance-parts-empty">No relevant tool match</span>`;
          const bindSuggestion = (node) => {
            node.addEventListener("click", () => {
              const option = node.dataset.maintToolOption;
              if (!option) return;
              selectedTools = dedupeStrings([...selectedTools, option]);
              if (requiredToolsSearch) requiredToolsSearch.value = "";
              syncRequiredToolsField();
              renderToolSuggestions("");
            });
            node.addEventListener("keydown", (event) => {
              if (!["Enter", " "].includes(event.key)) return;
              event.preventDefault();
              node.click();
            });
          };
          Array.from(requiredToolsSuggestions.querySelectorAll("[data-maint-tool-option]")).forEach(bindSuggestion);
        };

        const releasePhotoPreview = (photo) => {
          if (!photo?.preview) return;
          try {
            URL.revokeObjectURL(photo.preview);
          } catch (_error) {
            // ignore
          }
        };

        const photoItemKey = (photo) => (photo?.path ? `saved:${photo.path}` : `pending:${photo?.temp_id || photo?.name || ""}`);

        const syncPhotoField = () => {
          if (!photoValueInput) return;
          photoItems = syncBuilderPhotoItemsToSteps(photoItems, getPhotoTargetOptions());
          photoValueInput.value = serializeBuilderPhotoItems(photoItems);
        };

        const readFilesAsPayload = async (files = []) =>
          Promise.all(
            files.map(
              (file, index) =>
                new Promise((resolve) => {
                  const reader = new FileReader();
                  reader.onload = () => {
                    const result = String(reader.result || "");
                    const content = result.includes(",") ? result.split(",").pop() : result;
                    resolve({
                      temp_id: `tmp-${Date.now()}-${index}-${Math.random().toString(36).slice(2, 8)}`,
                      name: file.name,
                      content,
                      preview: URL.createObjectURL(file),
                    });
                  };
                  reader.onerror = () => resolve(null);
                  reader.readAsDataURL(file);
                }),
            ),
          ).then((items) => items.filter(Boolean));

        const addPendingUploads = async (files = []) => {
          const validFiles = files.filter((file) => file && file.type && file.type.startsWith("image/"));
          if (!validFiles.length || !pendingPhotoTarget) return;
          const items = await readFilesAsPayload(validFiles);
          pendingPhotoUploads = [...pendingPhotoUploads, ...items];
          photoItems = [
            ...photoItems,
            ...items.map((item) => ({
              temp_id: item.temp_id,
              name: item.name,
              preview: item.preview,
              step_key: pendingPhotoTarget.key,
              step_label: pendingPhotoTarget.label,
            })),
          ];
          pendingPhotoTarget = null;
          syncPhotoField();
          checklistEditors.forEach((editor) => editor.__renderChecklist?.());
        };

        const promptPhotoForTarget = (target) => {
          if (!photoInput || !target?.key) return;
          pendingPhotoTarget = target;
          checklistEditors.forEach((editor) => editor.__renderChecklist?.());
          photoInput.click();
        };

        const bindChecklistEditor = (editor) => {
          const hiddenInput = editor.querySelector('input[type="hidden"]');
          const list = editor.querySelector("[data-maint-checklist-list]");
          const addButton = editor.querySelector("[data-maint-checklist-add]");
          const countLabel = editor.closest(".maintenance-procedure-card")?.querySelector("[data-maint-checklist-count]");
          const placeholder = editor.dataset.maintPlaceholder || "Add item";
          const seedValue = editor.dataset.maintSeed || "";
          const editorName = hiddenInput?.name || "";
          const prefix = editorName === "preparationChecklist" ? "prep" : "step";
          const fallbackLabelBase = prefix === "prep" ? "Preparation item" : "Procedure step";
          const scopeLabel = prefix === "prep" ? "Preparation checklist" : "Procedure step";
          let items = parseChecklistSeedItems(hiddenInput?.value || "");
          if (!items.length && seedValue) items = parseChecklistSeedItems(seedValue);
          const sync = () => {
            if (hiddenInput) {
              hiddenInput.value = serializeChecklistItems(items);
            }
            syncPhotoField();
          };
          const render = (focusIndex = null) => {
            if (!list) return;
            if (countLabel) {
              const itemWord = /step/i.test(countLabel.textContent || "") ? "steps" : "items";
              countLabel.textContent = `${items.length} ${itemWord}`;
            }
            list.innerHTML = items.length
              ? items
                  .map(
                    (item, index) => {
                      const targetKey = `${prefix}:${item.id}`;
                      const targetLabel = String(item.text || "").trim() || `${fallbackLabelBase} ${index + 1}`;
                      const rowPhotos = photoItems.filter((photo) => photo.step_key === targetKey);
                      const isPhotoTarget = pendingPhotoTarget?.key === targetKey;
                      return `
                        <div class="maintenance-checklist-row ${isPhotoTarget ? "is-photo-target" : ""}" data-maint-check-row="${index}">
                          <div class="maintenance-checklist-row-main">
                            <input class="maintenance-checklist-text" type="text" value="${escapeHtml(item.text)}" placeholder="${escapeHtml(placeholder)}" data-maint-check-text="${index}" />
                            <div class="maintenance-checklist-row-actions">
                              <button class="maintenance-checklist-photo-action" type="button" data-maint-check-photo="${index}">+ Photo</button>
                              <button class="maintenance-checklist-remove" type="button" data-maint-check-remove="${index}">×</button>
                            </div>
                          </div>
                          <div class="maintenance-checklist-photo-strip ${rowPhotos.length ? "" : "is-empty"} ${isPhotoTarget ? "is-photo-target" : ""}">
                            ${
                              rowPhotos.length
                                ? rowPhotos
                                    .map(
                                      (photo) => `
                                        <div class="maintenance-checklist-photo-pill">
                                          ${
                                            photo.path || photo.preview
                                              ? `<img src="${escapeHtml(photo.path || photo.preview)}" alt="${escapeHtml(photo.name || targetLabel)}" loading="lazy" />`
                                              : ""
                                          }
                                          <div class="maintenance-checklist-photo-copy">
                                            <span>${escapeHtml(scopeLabel)}</span>
                                            <strong>${escapeHtml(photo.name || targetLabel)}</strong>
                                          </div>
                                          <button type="button" data-maint-photo-chip="${escapeHtml(photoItemKey(photo))}">×</button>
                                        </div>
                                      `,
                                    )
                                    .join("")
                                : `<span class="maintenance-checklist-photo-empty">${
                                    isPhotoTarget
                                      ? "Photo picker is opening for this row. If it closes, press + Photo to attach the reference."
                                      : "No linked photos for this row yet."
                                  }</span>`
                            }
                          </div>
                        </div>
                      `;
                    },
                  )
                  .join("")
              : `<span class="maintenance-checklist-placeholder">No items added yet.</span>`;
            Array.from(list.querySelectorAll("[data-maint-check-text]") || []).forEach((node) => {
              node.addEventListener("input", () => {
                const index = Number(node.dataset.maintCheckText);
                if (!items[index]) return;
                items[index].text = node.value;
                const targetKey = `${prefix}:${items[index].id}`;
                const targetLabel = String(node.value || "").trim() || `${fallbackLabelBase} ${index + 1}`;
                if (pendingPhotoTarget?.key === targetKey) {
                  pendingPhotoTarget = { ...pendingPhotoTarget, label: targetLabel };
                }
                photoItems = photoItems.map((photo) => (photo.step_key === targetKey ? { ...photo, step_label: targetLabel } : photo));
                sync();
                render();
              });
              node.addEventListener("keydown", (event) => {
                if (event.key !== "Enter") return;
                event.preventDefault();
                const nextIndex = Number(node.dataset.maintCheckText) + 1;
                const newItem = normalizeChecklistItem({}, prefix, nextIndex);
                items.splice(nextIndex, 0, newItem);
                sync();
                render(nextIndex);
                promptPhotoForTarget({
                  key: `${prefix}:${newItem.id}`,
                  label: `${fallbackLabelBase} ${nextIndex + 1}`,
                });
              });
            });
            Array.from(list.querySelectorAll("[data-maint-check-photo]") || []).forEach((node) => {
              node.addEventListener("click", () => {
                const index = Number(node.dataset.maintCheckPhoto);
                const item = items[index];
                if (!item) return;
                promptPhotoForTarget({
                  key: `${prefix}:${item.id}`,
                  label: String(item.text || "").trim() || `${fallbackLabelBase} ${index + 1}`,
                });
              });
            });
            Array.from(list.querySelectorAll("[data-maint-check-remove]") || []).forEach((node) => {
              node.addEventListener("click", () => {
                const index = Number(node.dataset.maintCheckRemove);
                const removed = items[index];
                if (removed) {
                  const targetKey = `${prefix}:${removed.id}`;
                  const removedPhotos = photoItems.filter((photo) => photo.step_key === targetKey);
                  removedPhotos.forEach(releasePhotoPreview);
                  pendingPhotoUploads = pendingPhotoUploads.filter((item) => !removedPhotos.some((photo) => photo.temp_id && photo.temp_id === item.temp_id));
                  photoItems = photoItems.filter((photo) => photo.step_key !== targetKey);
                }
                items.splice(index, 1);
                sync();
                render();
              });
            });
            Array.from(list.querySelectorAll("[data-maint-photo-chip]") || []).forEach((node) => {
              node.addEventListener("click", () => {
                const key = String(node.dataset.maintPhotoChip || "");
                const removed = photoItems.find((photo) => photoItemKey(photo) === key);
                if (removed?.temp_id) {
                  pendingPhotoUploads = pendingPhotoUploads.filter((item) => item.temp_id !== removed.temp_id);
                }
                releasePhotoPreview(removed);
                photoItems = photoItems.filter((photo) => photoItemKey(photo) !== key);
                sync();
                render();
              });
            });
            Array.from(list.querySelectorAll("[data-maint-checklist-add]") || []).forEach((node) => {
              node.addEventListener("click", () => {
                const newItem = normalizeChecklistItem({}, prefix, items.length);
                items.push(newItem);
                sync();
                render(items.length - 1);
                promptPhotoForTarget({
                  key: `${prefix}:${newItem.id}`,
                  label: `${fallbackLabelBase} ${items.length}`,
                });
              });
            });
            if (focusIndex !== null) {
              const focusNode = list.querySelector(`[data-maint-check-text="${focusIndex}"]`);
              focusNode?.focus();
            }
          };
          editor.__renderChecklist = render;
          addButton?.addEventListener("click", () => {
            const newItem = normalizeChecklistItem({}, prefix, items.length);
            items.push(newItem);
            sync();
            render(items.length - 1);
            promptPhotoForTarget({
              key: `${prefix}:${newItem.id}`,
              label: `${fallbackLabelBase} ${items.length}`,
            });
          });
          sync();
          render();
        };

        const bindSanityTemplateEditor = (editor) => {
          const hiddenInput = editor.querySelector('input[type="hidden"]');
          const list = editor.querySelector("[data-maint-sanity-list]");
          const addButton = editor.querySelector("[data-maint-sanity-add]");
          let items = parseSanityTemplateItems(hiddenInput?.value || "");
          const sync = () => {
            if (hiddenInput) hiddenInput.value = serializeSanityTemplateItems(items);
          };
          const updateRowPreview = (row, item) => {
            if (!row || !item) return;
            const metaLabel = row.querySelector("[data-maint-sanity-meta-label]");
            const metaInput = row.querySelector(`[data-maint-sanity-meta="${row.dataset.maintSanityRow || ""}"]`);
            const unitField = row.querySelector("[data-maint-sanity-unit-wrap]");
            const modeField = row.querySelector("[data-maint-sanity-mode-wrap]");
            const previewKind = row.querySelector("[data-maint-sanity-preview-kind]");
            const previewLabel = row.querySelector("[data-maint-sanity-preview-label]");
            const previewMeta = row.querySelector("[data-maint-sanity-preview-meta]");
            if (metaLabel) {
              metaLabel.textContent = item.kind === "text"
                ? "Placeholder"
                : item.kind === "number"
                  ? item.mode === "monitor"
                    ? "Monitor note"
                    : "Target value"
                  : item.kind === "passfail"
                    ? "Pass sample"
                    : "Checklist note";
            }
            if (metaInput) {
              metaInput.placeholder = item.kind === "text"
                ? "Short helper text for the operator"
                : item.kind === "number"
                  ? item.mode === "monitor"
                    ? "Example: Observe and record pressure"
                    : "Example: 25.0"
                  : item.kind === "passfail"
                    ? "Example: Surface is clean and dry"
                    : "Optional helper note";
            }
            if (unitField) unitField.classList.toggle("is-muted", item.kind !== "number");
            if (modeField) modeField.classList.toggle("is-muted", item.kind !== "number");
            if (previewKind) previewKind.textContent = sanityTemplateKindLabel(item);
            if (previewLabel) previewLabel.textContent = item.label || "Unnamed input";
            if (previewMeta) previewMeta.textContent = sanityTemplatePreviewNote(item);
          };
          const render = () => {
            if (!list) return;
            list.innerHTML = items.length
              ? items
                  .map(
                    (item, index) => `
                      <article class="maintenance-sanity-template-row" data-maint-sanity-row="${index}">
                        <div class="maintenance-sanity-template-head">
                          <strong>Input ${index + 1}</strong>
                          <button class="maintenance-sanity-template-remove" type="button" data-maint-sanity-remove="${index}">×</button>
                        </div>
                        <div class="maintenance-sanity-template-grid">
                          <label class="field-block maintenance-builder-field-compact">
                            <span>Input kind</span>
                            <select data-maint-sanity-kind="${index}">
                              <option value="check" ${item.kind === "check" ? "selected" : ""}>Checklist item</option>
                              <option value="number" ${item.kind === "number" ? "selected" : ""}>Numeric value</option>
                              <option value="text" ${item.kind === "text" ? "selected" : ""}>Free text</option>
                              <option value="passfail" ${item.kind === "passfail" ? "selected" : ""}>Pass / fail sample</option>
                            </select>
                          </label>
                          <label class="field-block">
                            <span>Operator prompt</span>
                            <input type="text" value="${escapeHtml(item.label)}" placeholder="What should the operator fill or check?" data-maint-sanity-label="${index}" />
                          </label>
                          <label class="field-block maintenance-builder-field-compact ${item.kind === "number" ? "" : "is-muted"}" data-maint-sanity-mode-wrap>
                            <span>Reading mode</span>
                            <select data-maint-sanity-mode="${index}">
                              <option value="target" ${item.mode === "target" ? "selected" : ""}>Target value</option>
                              <option value="monitor" ${item.mode === "monitor" ? "selected" : ""}>Monitor only</option>
                            </select>
                          </label>
                          <label class="field-block maintenance-builder-field-compact ${item.kind === "number" ? "" : "is-muted"}" data-maint-sanity-unit-wrap>
                            <span>Unit</span>
                            <input type="text" value="${escapeHtml(item.unit)}" placeholder="°C / mm / bar" data-maint-sanity-unit="${index}" />
                          </label>
                          <label class="field-block">
                            <span data-maint-sanity-meta-label>${item.kind === "text" ? "Placeholder" : item.kind === "number" ? item.mode === "monitor" ? "Monitor note" : "Target value" : item.kind === "passfail" ? "Pass sample" : "Checklist note"}</span>
                            <input type="text" value="${escapeHtml(item.kind === "text" ? item.placeholder : item.sample)}" placeholder="${escapeHtml(item.kind === "text" ? "Short helper text for the operator" : item.kind === "number" ? item.mode === "monitor" ? "Example: Observe and record pressure" : "Example: 25.0" : item.kind === "passfail" ? "Example: Surface is clean and dry" : "Optional helper note")} " data-maint-sanity-meta="${index}" />
                          </label>
                        </div>
                        <div class="maintenance-sanity-template-preview">
                          <span data-maint-sanity-preview-kind>${escapeHtml(sanityTemplateKindLabel(item))}</span>
                          <strong data-maint-sanity-preview-label>${escapeHtml(item.label || "Unnamed input")}</strong>
                          <em data-maint-sanity-preview-meta>${escapeHtml(sanityTemplatePreviewNote(item))}</em>
                        </div>
                      </article>
                    `,
                  )
                  .join("")
              : `
                  <button class="maintenance-sanity-template-empty" type="button" data-maint-sanity-add>
                    Create the first closeout input
                  </button>
                `;
            Array.from(list.querySelectorAll("[data-maint-sanity-remove]") || []).forEach((node) => {
              node.addEventListener("click", () => {
                items.splice(Number(node.dataset.maintSanityRemove), 1);
                sync();
                render();
              });
            });
            Array.from(list.querySelectorAll("[data-maint-sanity-kind]") || []).forEach((node) => {
              node.addEventListener("change", () => {
                const index = Number(node.dataset.maintSanityKind);
                if (!items[index]) return;
                items[index].kind = node.value || "check";
                if (items[index].kind !== "number") items[index].mode = "target";
                sync();
                render();
              });
            });
            Array.from(list.querySelectorAll("[data-maint-sanity-mode]") || []).forEach((node) => {
              node.addEventListener("change", () => {
                const index = Number(node.dataset.maintSanityMode);
                if (!items[index]) return;
                items[index].mode = node.value || "target";
                sync();
                render();
              });
            });
            Array.from(list.querySelectorAll("[data-maint-sanity-label]") || []).forEach((node) => {
              node.addEventListener("input", () => {
                const index = Number(node.dataset.maintSanityLabel);
                if (!items[index]) return;
                items[index].label = node.value;
                sync();
                updateRowPreview(node.closest("[data-maint-sanity-row]"), items[index]);
              });
            });
            Array.from(list.querySelectorAll("[data-maint-sanity-unit]") || []).forEach((node) => {
              node.addEventListener("input", () => {
                const index = Number(node.dataset.maintSanityUnit);
                if (!items[index]) return;
                items[index].unit = node.value;
                sync();
                updateRowPreview(node.closest("[data-maint-sanity-row]"), items[index]);
              });
            });
            Array.from(list.querySelectorAll("[data-maint-sanity-meta]") || []).forEach((node) => {
              node.addEventListener("input", () => {
                const index = Number(node.dataset.maintSanityMeta);
                if (!items[index]) return;
                if (items[index].kind === "text") {
                  items[index].placeholder = node.value;
                } else {
                  items[index].sample = node.value;
                }
                sync();
                updateRowPreview(node.closest("[data-maint-sanity-row]"), items[index]);
              });
            });
            Array.from(list.querySelectorAll("[data-maint-sanity-add]") || []).forEach((node) => {
              node.addEventListener("click", () => {
                items.push({ kind: "check", label: "", unit: "", sample: "", placeholder: "" });
                sync();
                render();
              });
            });
          };
          addButton?.addEventListener("click", () => {
            items.push({ kind: "check", label: "", unit: "", sample: "", placeholder: "" });
            sync();
            render();
          });
          sync();
          render();
        };

        fallRiskSelect?.addEventListener("change", syncTnmField);
        requiredPartsSearch?.addEventListener("input", () => renderPartSuggestions(requiredPartsSearch.value || ""));
        requiredPartsSearch?.addEventListener("keydown", (event) => {
          if (event.key !== "Enter") return;
          event.preventDefault();
          const typedValue = String(requiredPartsSearch.value || "").trim();
          if (!typedValue) return;
          selectedParts = dedupeStrings([...selectedParts, typedValue]);
          requiredPartsSearch.value = "";
          syncRequiredPartsField();
          renderPartSuggestions("");
        });
        requiredToolsSearch?.addEventListener("input", () => renderToolSuggestions(requiredToolsSearch.value || ""));
        requiredToolsSearch?.addEventListener("keydown", (event) => {
          if (event.key !== "Enter") return;
          event.preventDefault();
          const typedValue = String(requiredToolsSearch.value || "").trim();
          if (!typedValue) return;
          selectedTools = dedupeStrings([...selectedTools, typedValue]);
          requiredToolsSearch.value = "";
          syncRequiredToolsField();
          renderToolSuggestions("");
        });
        photoInput?.addEventListener("change", async () => {
          const files = Array.from(photoInput.files || []);
          if (!files.length) {
            pendingPhotoTarget = null;
            checklistEditors.forEach((editor) => editor.__renderChecklist?.());
          }
          await addPendingUploads(files);
          photoInput.value = "";
        });
        syncTnmField();
        syncRequiredPartsField();
        syncRequiredToolsField();
        renderPartSuggestions("");
        renderToolSuggestions("");
        checklistEditors.forEach((editor) => {
          if (editor.dataset.maintSanityTemplateEditor) return;
          bindChecklistEditor(editor);
        });
        Array.from(form?.querySelectorAll("[data-maint-sanity-template-editor]") || []).forEach(bindSanityTemplateEditor);
        form?.addEventListener("submit", async (event) => {
          event.preventDefault();
          const formData = new FormData(form);
          const payload = Object.fromEntries(formData.entries());
          payload.photoUploads = pendingPhotoUploads.map((item) => ({
            temp_id: item.temp_id,
            name: item.name,
            content: item.content,
          }));
          const result = await postJson("/api/maintenance/work-package", payload);
          bootstrapData = result.bootstrap || null;
          await renderRoute();
        });
        return;
      }
      if (!task || !actionRoot) return;
      if (activeView === "history") {
        actionRoot.innerHTML = `
          <div class="chart-card tight">
            <div class="chart-head"><span>History</span><strong>Recent maintenance actions</strong></div>
            <div class="stack-list">
              ${(maintenanceData.recent_actions || []).map((item) => `<div class="micro-row"><span>${item.component} — ${item.task}</span><strong>${item.done_date || item.task_id}</strong></div>`).join("")}
            </div>
          </div>
        `;
        return;
      }
      const laneActionMarkup = (() => {
        if (activeView === "plan") {
          const planState = String(task?.status || "").trim().toUpperCase();
          return `
            <div class="maintenance-lane-actions-head">
              <span>Preparation actions</span>
              <strong>Move this task into the next ready state</strong>
            </div>
            <label class="field-block">
              <span>Readiness note</span>
              <textarea id="maintenance-note-input" rows="3" placeholder="Prep note / part check / what still needs to happen">${task.wait_note || ""}</textarea>
            </label>
            <div class="maintenance-state-actions">
              <button class="action-btn action-secondary" type="button" data-maint-state="PREP_READY">Need prep</button>
              <button class="action-btn action-secondary" type="button" data-maint-state="WAIT FOR PART">Wait for part</button>
              <button class="action-btn action-secondary" type="button" data-maint-state="PREP_DONE">Ready</button>
              ${planState === "PREP_DONE"
                ? `<button class="action-btn action-primary" type="button" data-maint-state="SCHEDULED">Queue for execute</button>`
                : ""}
            </div>
          `;
        }
        if (activeView === "execute") {
          return `
            <div class="maintenance-lane-actions-head">
              <span>Execution actions</span>
              <strong>Run, block, or close the live task</strong>
            </div>
            <label class="field-block">
              <span>Execution note</span>
              <textarea id="maintenance-note-input" rows="3" placeholder="Live action note / stop result / issue found">${task.wait_note || ""}</textarea>
            </label>
            <div class="maintenance-state-actions">
              <button class="action-btn action-secondary" type="button" data-maint-state="IN_PROGRESS">Start / resume</button>
              <button class="action-btn action-secondary" type="button" data-maint-state="WAIT FOR PART">Wait for part</button>
              <button class="action-btn action-primary" type="button" data-maint-complete="1">Mark done</button>
            </div>
          `;
        }
        return `
          <div class="maintenance-lane-actions-head">
            <span>Blocker actions</span>
            <strong>Clear waits and move the task forward</strong>
          </div>
          <label class="field-block">
            <span>Blocker note</span>
            <textarea id="maintenance-note-input" rows="3" placeholder="Blocked reason / what is still missing">${task.wait_note || ""}</textarea>
          </label>
          <div class="maintenance-state-actions">
            <button class="action-btn action-secondary" type="button" data-maint-state="PREP_READY">Back to prep</button>
            <button class="action-btn action-secondary" type="button" data-maint-state="IN_PROGRESS">Resume task</button>
            <button class="action-btn action-primary" type="button" data-maint-complete="1">Mark done</button>
          </div>
        `;
      })();
      actionRoot.innerHTML = `
        ${laneActionMarkup}
        ${(task.missing_parts || []).length ? `
          <div class="chart-card tight">
            <div class="chart-head"><span>Parts action</span><strong>Create linked part orders</strong></div>
            <div class="token-strip">${task.missing_parts.map((part) => `<span class="token-chip">${part}</span>`).join("")}</div>
            <div class="parts-form-actions">
              <button class="action-btn action-secondary" type="button" data-maint-create-orders="1">Create missing part orders</button>
            </div>
          </div>
        ` : ""}
      `;
      const noteValue = () => String(document.getElementById("maintenance-note-input")?.value || "");
      Array.from(actionRoot.querySelectorAll("[data-maint-state]")).forEach((button) => {
        button.addEventListener("click", async () => {
          const result = await postJson("/api/maintenance/state", {
            taskId: task.task_id,
            component: task.component,
            task: task.task,
            state: button.dataset.maintState,
            note: noteValue(),
          });
          bootstrapData = result.bootstrap || null;
          await renderRoute();
        });
      });
      actionRoot.querySelector("[data-maint-complete]")?.addEventListener("click", async () => {
        const result = await postJson("/api/maintenance/complete", {
          taskId: task.task_id,
          component: task.component,
          task: task.task,
          trackingMode: task.tracking_mode,
          note: noteValue(),
        });
        bootstrapData = result.bootstrap || null;
        await renderRoute();
      });
      actionRoot.querySelector("[data-maint-create-orders]")?.addEventListener("click", async () => {
        const result = await postJson("/api/maintenance/create-parts-orders", {
          taskId: task.task_id,
          component: task.component,
          task: task.task,
          parts: task.missing_parts || [],
        });
        bootstrapData = result.bootstrap || null;
        await renderRoute();
      });
    };

    const rows = currentRows().filter((item) => {
      const blob = JSON.stringify(item).toLowerCase();
      if (searchValue && !blob.includes(searchValue.toLowerCase())) return false;
      if (componentFilter && String(item.component || "") !== componentFilter) return false;
      if (packageFilter === "saved" && !item.work_package?.last_updated) return false;
      if (packageFilter === "needs" && item.work_package?.last_updated) return false;
      return true;
    });
    const meta = modeMeta();
    if (listEyebrow) listEyebrow.textContent = meta.listEyebrow;
    if (listTitle) listTitle.textContent = meta.listTitle;
    if (detailEyebrow) detailEyebrow.textContent = meta.detailEyebrow;
    if (detailTitle) detailTitle.textContent = meta.detailTitle;
    if (activeView === "execute") {
      const task = selectedTask() || rows[0] || maintenanceData.tasks[0];
      const contextMarkup = `
        ${maintenanceModeLeadMarkup(activeView, maintenanceData, task)}
        ${maintenanceModeContextMarkup(activeView, maintenanceData, task, prepCutoffProgress, prepReadyProgress, prepFocusLaneKey, prepHorizonProgress, prepHorizonFoldOpen, prepStageKey, prepActionState, prepSelectedTaskIds)}
      `;
      if (contextRoot) contextRoot.innerHTML = contextMarkup;
      if (executeLauncherRoot) {
        executeLauncherRoot.innerHTML = maintenanceExecuteLauncherMarkup(
          maintenanceData,
          executeEntryMode,
          executeOpenTaskId,
          executeManualSearch,
          executeManualComponent,
        );
        Array.from(executeLauncherRoot.querySelectorAll("[data-maint-execute-mode]") || []).forEach((button) => {
          button.addEventListener("click", () => {
            executeEntryMode = button.dataset.maintExecuteMode || "";
            page.dataset.maintExecuteMode = executeEntryMode;
            executeOpenTaskId = "";
            page.dataset.maintExecuteTaskId = "";
            renderMaintenanceWorkspace();
          });
        });
        executeLauncherRoot.querySelector("#maintenance-execute-manual-search")?.addEventListener("input", (event) => {
          executeManualSearch = event.target.value || "";
          page.dataset.maintExecuteManualSearch = executeManualSearch;
          renderMaintenanceWorkspace();
        });
        executeLauncherRoot.querySelector("#maintenance-execute-manual-component")?.addEventListener("change", (event) => {
          executeManualComponent = event.target.value || "";
          page.dataset.maintExecuteManualComponent = executeManualComponent;
          renderMaintenanceWorkspace();
        });
        Array.from(executeLauncherRoot.querySelectorAll("[data-maint-execute-start]") || []).forEach((button) => {
          button.addEventListener("click", async () => {
            const taskId = button.dataset.maintExecuteStart || "";
            if (!taskId) return;
            const executeTask = (maintenanceData.execute_queue || []).find((item) => item.task_id === taskId);
            const task = executeTask || (maintenanceData.tasks || []).find((item) => item.task_id === taskId) || {};
            const result = await postJson("/api/maintenance/state", {
              taskId,
              component: button.dataset.maintExecuteComponent || task.component || "",
              task: button.dataset.maintExecuteTasklabel || task.task || "",
              state: "IN_PROGRESS",
              note: "Started from execute.",
            });
            bootstrapData = result.bootstrap || bootstrapData;
            selectedTaskId = taskId;
            page.dataset.maintTaskId = selectedTaskId;
            executeOpenTaskId = taskId;
            page.dataset.maintExecuteTaskId = executeOpenTaskId;
            renderMaintenanceWorkspace();
          });
        });
        Array.from(executeLauncherRoot.querySelectorAll("[data-maint-execute-task]") || []).forEach((button) => {
          button.addEventListener("click", () => {
            const nextTaskId = button.dataset.maintExecuteTask || "";
            executeOpenTaskId = executeOpenTaskId === nextTaskId ? "" : nextTaskId;
            page.dataset.maintExecuteTaskId = executeOpenTaskId;
            selectedTaskId = nextTaskId;
            page.dataset.maintTaskId = selectedTaskId;
            renderMaintenanceWorkspace();
          });
        });
        executeLauncherRoot.querySelector("#maintenance-execute-manual-form")?.addEventListener("submit", async (event) => {
          event.preventDefault();
          const form = event.currentTarget;
          const sanityResultsInput = form.querySelector('input[name="sanityResults"]');
          if (sanityResultsInput) {
            const sanityResults = Array.from(form.querySelectorAll("[data-maint-sanity-runtime-item]") || []).map((node) => {
              const index = Number(node.dataset.maintSanityRuntimeItem || 0);
              const kind = String(node.dataset.kind || "").trim();
              const mode = String(node.dataset.mode || "").trim();
              const label = String(node.dataset.label || "").trim();
              if (kind === "check") {
                return { index, kind, mode, label, checked: Boolean(node.querySelector("[data-maint-sanity-runtime-check]")?.checked) };
              }
              if (kind === "number") {
                return {
                  index,
                  kind,
                  mode,
                  label,
                  unit: String(node.dataset.unit || "").trim(),
                  target: String(node.dataset.sample || "").trim(),
                  value: String(node.querySelector("[data-maint-sanity-runtime-value]")?.value || "").trim(),
                };
              }
              if (kind === "passfail") {
                return {
                  index,
                  kind,
                  mode,
                  label,
                  sample: String(node.dataset.sample || "").trim(),
                  status: String(node.querySelector("[data-maint-sanity-runtime-status]")?.value || "").trim(),
                };
              }
              return {
                index,
                kind,
                mode,
                label,
                value: String(node.querySelector("[data-maint-sanity-runtime-text]")?.value || "").trim(),
              };
            });
            sanityResultsInput.value = JSON.stringify(sanityResults);
          }
          const payload = Object.fromEntries(new FormData(form).entries());
          const saveResult = await postJson("/api/maintenance/work-package", payload);
          bootstrapData = saveResult.bootstrap || bootstrapData;
          const completeResult = await postJson("/api/maintenance/complete", {
            taskId: payload.taskId,
            component: payload.component,
            task: payload.task,
            trackingMode: payload.trackingMode || "",
            note: "Completed from execute after operator fields were saved.",
          });
          bootstrapData = completeResult.bootstrap || bootstrapData;
          selectedTaskId = "";
          page.dataset.maintTaskId = "";
          executeOpenTaskId = "";
          page.dataset.maintExecuteTaskId = "";
          await renderRoute();
        });
      }
      Array.from(groupRoot.querySelectorAll("[data-maint-view]")).forEach((button) => {
        button.addEventListener("click", () => {
          activeView = button.dataset.maintView;
          page.dataset.maintView = activeView;
          selectedTaskId = (currentRows()[0] || maintenanceData.tasks[0] || {}).task_id || "";
          page.dataset.maintTaskId = selectedTaskId;
          renderMaintenanceWorkspace();
        });
      });
      return;
    }
    if (listRoot) {
      listRoot.innerHTML = maintenanceTaskRailMarkup(rows, selectedTaskId, {
        empty: "No maintenance rows match this view.",
        variant: activeView === "plan" ? "plan" : "default",
      });
    }
    Array.from(listRoot?.querySelectorAll("[data-maint-select]") || []).forEach((button) => {
      button.addEventListener("click", () => {
        selectedTaskId = button.dataset.maintSelect;
        page.dataset.maintTaskId = selectedTaskId;
        renderMaintenanceWorkspace();
      });
    });
    const runtimeFold = page.querySelector(".maintenance-runtime-fold");
    if (runtimeFold) {
      runtimeFold.open = runtimeFoldOpen;
      runtimeFold.addEventListener("toggle", () => {
        runtimeFoldOpen = runtimeFold.open;
        page.dataset.maintRuntimeOpen = runtimeFoldOpen ? "1" : "0";
      });
    }
    const runtimeForm = page.querySelector("#maintenance-runtime-form");
    const saveRuntime = async () => {
      if (!runtimeForm) return;
      const payload = Object.fromEntries(new FormData(runtimeForm).entries());
      const result = await postJson("/api/maintenance/runtime", payload);
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    };
    runtimeForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      await saveRuntime();
    });
    page.querySelector("#maintenance-runtime-save")?.addEventListener("click", async () => {
      await saveRuntime();
    });
    const task = selectedTask() || rows[0] || maintenanceData.tasks[0];
    const contextMarkup = `
        ${maintenanceModeLeadMarkup(activeView, maintenanceData, task)}
        ${maintenanceModeContextMarkup(activeView, maintenanceData, task, prepCutoffProgress, prepReadyProgress, prepFocusLaneKey, prepHorizonProgress, prepHorizonFoldOpen, prepStageKey, prepActionState, prepSelectedTaskIds)}
      `;
    if (activeView === "plan" && planPrimaryRoot) {
      planPrimaryRoot.innerHTML = contextMarkup;
    } else if (contextRoot) {
      contextRoot.innerHTML = contextMarkup;
    }
    const refreshPrepHorizonLiveShell = () => {
      if (activeView !== "plan") return;
      const liveShell = groupRoot.querySelector('[data-maint-prep-live-shell="1"]');
      if (!liveShell) return;
      const sourceRows = maintenancePrepTimelineSourceTasks(maintenanceData);
      const lanes = buildMaintenanceTimelineLanes(maintenanceData, {
        sourceTasks: sourceRows,
        limit: 24,
        horizonMap: prepHorizonMap,
      });
      const demoNow = new Date();
      const laneProgressMap = maintenanceExecuteProgressMapForLanes(lanes, selectedTaskId, prepCutoffMap);
      const lanePrepMap = maintenancePrepProgressMapForLanes(lanes, prepReadyMap);
      const executeTasksBefore = maintenanceUniqueTasks(
        maintenancePlottedTasksBeforeMarker(lanes, laneProgressMap, { demoNow, demoSourceRows: sourceRows }),
      );
      const prepTasksBefore = maintenanceUniqueTasks(
        maintenancePlottedTasksBeforeMarker(lanes, lanePrepMap, { demoNow, demoSourceRows: sourceRows }),
      );
      liveShell.outerHTML = maintenancePrepLiveShellMarkup(
        maintenanceData,
        executeTasksBefore,
        prepTasksBefore,
        prepStageKey,
        maintenanceStageFlash,
        prepActionState,
        prepSelectedTaskIds,
      );
    };
    searchInput?.addEventListener("input", () => {
      searchValue = searchInput.value || "";
      page.dataset.maintSearch = searchValue;
      renderMaintenanceWorkspace();
    });
    Array.from(groupRoot.querySelectorAll("[data-maint-view]")).forEach((button) => {
      button.addEventListener("click", () => {
        activeView = button.dataset.maintView;
        page.dataset.maintView = activeView;
        selectedTaskId = (currentRows()[0] || maintenanceData.tasks[0] || {}).task_id || "";
        page.dataset.maintTaskId = selectedTaskId;
        renderMaintenanceWorkspace();
      });
    });
    Array.from(groupRoot.querySelectorAll("[data-maint-horizon-task]")).forEach((button) => {
      button.addEventListener("click", () => {
        const taskId = button.dataset.maintHorizonTask;
        if (!taskId) return;
        selectedTaskId = taskId;
        page.dataset.maintTaskId = selectedTaskId;
        if (activeView === "plan") {
          const task = taskLookup().get(taskId);
          if (task) {
            const laneKind = maintenanceTimelineLaneForTask(task);
            prepFocusLaneKey = laneKind;
            page.dataset.maintPrepFocusLane = prepFocusLaneKey;
          }
        }
        renderMaintenanceWorkspace();
      });
    });
    Array.from(groupRoot.querySelectorAll("[data-maint-prep-stage]")).forEach((button) => {
      button.addEventListener("click", () => {
        prepStageKey = button.dataset.maintPrepStage || "need-prep";
        page.dataset.maintPrepStage = prepStageKey;
        renderMaintenanceWorkspace();
      });
    });
    Array.from(groupRoot.querySelectorAll("[data-maint-stage-select]")).forEach((input) => {
      input.addEventListener("change", () => {
        const taskId = String(input.dataset.maintStageSelect || "").trim();
        if (!taskId) return;
        if (input.checked) {
          setPrepSelectedTaskIds([...prepSelectedTaskIds, taskId]);
        } else {
          setPrepSelectedTaskIds(prepSelectedTaskIds.filter((item) => item !== taskId));
        }
        renderMaintenanceWorkspace();
      });
    });
    Array.from(groupRoot.querySelectorAll("[data-maint-stage-clear-selection]")).forEach((button) => {
      button.addEventListener("click", () => {
        setPrepSelectedTaskIds([]);
        renderMaintenanceWorkspace();
      });
    });
    Array.from(groupRoot.querySelectorAll("[data-maint-stage-action]")).forEach((button) => {
      button.addEventListener("click", async () => {
        const action = button.dataset.maintStageAction || "";
        const taskId = button.dataset.maintStageTask || "";
        const taskForAction = taskLookup().get(taskId);
        if (!action || !taskForAction) return;
        if (action === "prep-done") {
          const sourceRows = maintenancePrepTimelineSourceTasks(maintenanceData);
          const lanes = buildMaintenanceTimelineLanes(maintenanceData, {
            sourceTasks: sourceRows,
            limit: 24,
            horizonMap: prepHorizonMap,
          });
          const laneProgressMap = maintenanceExecuteProgressMapForLanes(lanes, selectedTaskId, prepCutoffMap);
          const executeTasksBefore = maintenanceUniqueTasks(
            maintenancePlottedTasksBeforeMarker(lanes, laneProgressMap, { demoNow: new Date(), demoSourceRows: sourceRows }),
          );
          const taskIsInExecuteWindow = new Set(
            executeTasksBefore
              .map((item) => maintenanceCanonicalTaskId(item) || String(item?.task_id || "").trim())
              .filter(Boolean),
          ).has(maintenanceCanonicalTaskId(taskForAction) || String(taskForAction?.task_id || "").trim());
          const overrideNote = "Marked ready from plan.";
          const existingNote = String(taskForAction.wait_note || "").trim();
          const mergedNote = existingNote
            ? (existingNote.includes(overrideNote) ? existingNote : `${existingNote} | ${overrideNote}`)
            : overrideNote;
          try {
            const result = await postJson("/api/maintenance/state", {
              taskId,
              component: taskForAction.component,
              task: taskForAction.task,
              state: "PREP_DONE",
              note: mergedNote,
            });
            maintenanceStageFlash = {
              kind: "good",
              message: taskIsInExecuteWindow
                ? `${taskForAction.component || "Task"} is now ready to execute.`
                : `${taskForAction.component || "Task"} is marked ready. It will show in ready to execute after the execute marker reaches it.`,
            };
            prepActionState = null;
            delete page.dataset.maintPrepAction;
            bootstrapData = result.bootstrap || bootstrapData;
            maintenanceData = bootstrapData?.maintenance || maintenanceData;
            activeView = "plan";
            page.dataset.maintView = activeView;
            prepStageKey = taskIsInExecuteWindow ? "ready" : "need-prep";
            page.dataset.maintPrepStage = prepStageKey;
            setPrepSelectedTaskIds([]);
            selectedTaskId = taskId;
            page.dataset.maintTaskId = selectedTaskId;
            renderMaintenanceWorkspace();
            return;
          } catch (error) {
            maintenanceStageFlash = { kind: "bad", message: error.message };
            renderMaintenanceWorkspace();
            return;
          }
        }
        if (action === "order-parts") {
          try {
            await placeMaintenancePartsOrders([taskForAction], [taskId]);
            return;
          } catch (error) {
            maintenanceStageFlash = { kind: "bad", message: error.message };
            renderMaintenanceWorkspace();
            return;
          }
        }
        selectedTaskId = taskId;
        page.dataset.maintTaskId = selectedTaskId;
        prepActionState = { action, confirmAction: action, mode: "single", taskIds: [taskId] };
        page.dataset.maintPrepAction = JSON.stringify(prepActionState);
        renderMaintenanceWorkspace();
      });
    });
    Array.from(groupRoot.querySelectorAll("[data-maint-stage-bulk]")).forEach((button) => {
      button.addEventListener("click", async () => {
        const action = button.dataset.maintStageBulk || "";
        const taskIds = String(button.dataset.maintStageTaskIds || "").split(",").map((item) => item.trim()).filter(Boolean);
        const tasks = taskIds.map((taskId) => taskLookup().get(taskId)).filter(Boolean);
        if (!action || !tasks.length) return;
        if (action === "order-all") {
          try {
            await placeMaintenancePartsOrders(tasks, taskIds);
            return;
          } catch (error) {
            maintenanceStageFlash = { kind: "bad", message: error.message };
            renderMaintenanceWorkspace();
            return;
          }
        }
        prepActionState = { action, confirmAction: action, mode: "bulk", taskIds };
        page.dataset.maintPrepAction = JSON.stringify(prepActionState);
        renderMaintenanceWorkspace();
      });
    });
    Array.from(groupRoot.querySelectorAll("[data-maint-stage-draft-cancel]")).forEach((button) => {
      button.addEventListener("click", () => {
        prepActionState = null;
        delete page.dataset.maintPrepAction;
        renderMaintenanceWorkspace();
      });
    });
    Array.from(groupRoot.querySelectorAll("[data-maint-stage-draft-confirm]")).forEach((button) => {
      button.addEventListener("click", async () => {
        const action = button.dataset.maintStageDraftConfirm || prepActionState?.confirmAction || prepActionState?.action || "";
        const state = prepActionState;
        const taskIds = state?.taskIds || [];
        const tasks = taskIds.map((taskId) => taskLookup().get(taskId)).filter(Boolean);
        const firstTask = tasks[0];
        const scheduleWindow = (maintenanceData.maintenance_events || [])[0];
        const startInput = groupRoot.querySelector('[data-maint-stage-slot-start="0"]');
        const endInput = groupRoot.querySelector('[data-maint-stage-slot-end="0"]');
        const selectedWindow = {
          start: normalizeDateTimeLocalValue(startInput?.value || ""),
          end: normalizeDateTimeLocalValue(endInput?.value || ""),
          label: "",
        };
        if (!action || !tasks.length || !firstTask) return;

        try {
          if (action === "order-parts" || action === "order-all") {
            const orderableTasks = tasks
              .filter((task) => maintenanceTaskOrderableParts(task).length)
              .map((task) => ({
                taskId: task.task_id,
                component: task.component,
                task: task.task,
                parts: maintenanceTaskOrderableParts(task),
              }));
            if (!orderableTasks.length) {
              maintenanceStageFlash = { kind: "warn", message: "No missing parts in this selection." };
              prepActionState = null;
              delete page.dataset.maintPrepAction;
              renderMaintenanceWorkspace();
              return;
            }
            const result = await postJson("/api/maintenance/create-parts-orders", { tasks: orderableTasks });
            maintenanceStageFlash = { kind: "good", message: result.message || "Part orders created." };
            prepActionState = null;
            delete page.dataset.maintPrepAction;
            bootstrapData = result.bootstrap || null;
            await renderRoute();
            return;
          }

          if (action === "parts") {
            prepActionState = null;
            delete page.dataset.maintPrepAction;
            maintenanceStageFlash = { kind: "info", message: "Opening Tower Parts." };
            window.location.hash = "#/parts";
            return;
          }

          if (action === "schedule" || action === "schedule-all") {
            const windowSeed = (selectedWindow.start && selectedWindow.end)
              ? selectedWindow
              : (scheduleWindow?.start && scheduleWindow?.end
                ? {
                    start: scheduleWindow.start,
                    end: scheduleWindow.end,
                    label: scheduleWindow.date_label || scheduleWindow.start_label || "",
                  }
                : null);
            const windows = buildMaintenanceScheduleWindows(tasks, windowSeed);
            if (!windows.length) {
              maintenanceStageFlash = { kind: "bad", message: "Choose a valid start and end time for scheduling." };
              renderMaintenanceWorkspace();
              return;
            }
            const result = await postJson("/api/maintenance/schedule", {
              tasks: tasks.map((task) => ({
                taskId: maintenanceCanonicalTaskId(task),
                component: task.component,
                task: task.task,
              })),
              windows,
              eventType: "Maintenance",
            });
            maintenanceStageFlash = {
              kind: "good",
              message: tasks.length > 1
                ? `${result.message || "Maintenance scheduled."} Tasks were spread across the chosen interval and added to the app calendar.`
                : `${result.message || "Maintenance scheduled."} The task was added to the app calendar.`,
            };
            prepActionState = null;
            delete page.dataset.maintPrepAction;
            bootstrapData = result.bootstrap || bootstrapData;
            maintenanceData = bootstrapData?.maintenance || maintenanceData;
            activeView = "plan";
            page.dataset.maintView = activeView;
            prepStageKey = "scheduled";
            page.dataset.maintPrepStage = prepStageKey;
            setPrepSelectedTaskIds(prepSelectedTaskIds.filter((item) => !taskIds.includes(item)));
            const scheduledAfter = (maintenanceData.execute_queue || []).filter((item) => String(item?.status || "").trim().toUpperCase() === "SCHEDULED");
            const firstCanonicalTaskId = maintenanceCanonicalTaskId(firstTask);
            selectedTaskId = (
              scheduledAfter.find((item) => maintenanceCanonicalTaskId(item) === firstCanonicalTaskId)
              || scheduledAfter[0]
              || firstTask
              || {}
            ).task_id || firstCanonicalTaskId || "";
            page.dataset.maintTaskId = selectedTaskId;
            renderMaintenanceWorkspace();
            return;
          }

          if (action === "open-execute" || action === "open-execute-all") {
            selectedTaskId = firstTask.task_id;
            page.dataset.maintTaskId = selectedTaskId;
            prepActionState = null;
            delete page.dataset.maintPrepAction;
            maintenanceStageFlash = { kind: "good", message: `Opened execute for ${firstTask.component}.` };
            activeView = "execute";
            page.dataset.maintView = activeView;
            renderMaintenanceWorkspace();
          }
        } catch (error) {
          maintenanceStageFlash = { kind: "bad", message: error.message };
          renderMaintenanceWorkspace();
        }
      });
    });
    Array.from(groupRoot.querySelectorAll("[data-maint-open-execute]")).forEach((button) => {
      button.addEventListener("click", () => {
        const taskId = button.dataset.maintOpenExecute || selectedTaskId;
        if (!taskId) return;
        selectedTaskId = taskId;
        page.dataset.maintTaskId = selectedTaskId;
        executeOpenTaskId = taskId;
        page.dataset.maintExecuteTaskId = executeOpenTaskId;
        activeView = "execute";
        page.dataset.maintView = activeView;
        renderMaintenanceWorkspace();
      });
    });
    Array.from(groupRoot.querySelectorAll("[data-maint-horizon-cutoff]")).forEach((handle) => {
      handle.addEventListener("mousedown", (event) => {
        const track = handle.closest(".maintenance-horizon-plot-track");
        const laneKey = handle.dataset.maintHorizonCutoff;
        if (!track) return;
        event.preventDefault();
        const dragStartX = event.clientX;
        const currentLeftPercent = Number.parseFloat(handle.style.left || "0");
        const currentValue = Number.isFinite(currentLeftPercent) ? currentLeftPercent / 100 : 0;
        const initialRect = track.getBoundingClientRect();
        const initialHandleX = initialRect.left + (currentValue * initialRect.width);
        const dragOffset = event.clientX - initialHandleX;
        let didDrag = false;
        const updateCutoff = (clientX) => {
          const rect = track.getBoundingClientRect();
          if (!rect.width || !laneKey) return;
          prepFocusLaneKey = laneKey;
          page.dataset.maintPrepFocusLane = prepFocusLaneKey;
          const markerX = clientX - dragOffset;
          const rawValue = Math.max(0, Math.min(0.98, (markerX - rect.left) / rect.width));
          const nextValue = rawValue <= 0.01 ? 0 : (rawValue >= 0.97 ? 0.98 : rawValue);
          prepCutoffMap = {
            ...prepCutoffMap,
            [laneKey]: nextValue,
          };
          prepCutoffProgress = JSON.stringify(prepCutoffMap);
          page.dataset.maintPrepCutoff = prepCutoffProgress;
          Array.from(groupRoot.querySelectorAll(`[data-maint-horizon-cutoff="${laneKey}"]`)).forEach((line) => {
            line.style.left = `${nextValue * 100}%`;
          });
          Array.from(groupRoot.querySelectorAll(`[data-maint-horizon-cutoff-band="${laneKey}"]`)).forEach((band) => {
            band.style.width = `${nextValue * 100}%`;
          });
          Array.from(track.querySelectorAll("[data-maint-horizon-progress]")).forEach((pin) => {
            const pinProgress = Number(pin.dataset.maintHorizonProgress || 0);
            pin.classList.toggle("is-before-cutoff", pinProgress <= nextValue + 0.0001);
          });
          refreshPrepHorizonLiveShell();
        };
        const onMove = (moveEvent) => {
          if (!didDrag && Math.abs(moveEvent.clientX - dragStartX) < 3) return;
          if (!didDrag) {
            didDrag = true;
            document.body.classList.add("is-maint-dragging-cutoff");
          }
          updateCutoff(moveEvent.clientX);
        };
        const onUp = (upEvent) => {
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
          document.body.classList.remove("is-maint-dragging-cutoff");
          if (!didDrag) return;
          updateCutoff(upEvent.clientX);
          renderMaintenanceWorkspace();
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
      });
    });
    Array.from(groupRoot.querySelectorAll("[data-maint-horizon-prep]")).forEach((handle) => {
      handle.addEventListener("mousedown", (event) => {
        const track = handle.closest(".maintenance-horizon-plot-track");
        const laneKey = handle.dataset.maintHorizonPrep;
        if (!track) return;
        event.preventDefault();
        const dragStartX = event.clientX;
        const currentLeftPercent = Number.parseFloat(handle.style.left || "0");
        const currentValue = Number.isFinite(currentLeftPercent) ? currentLeftPercent / 100 : 0;
        const initialRect = track.getBoundingClientRect();
        const initialHandleX = initialRect.left + (currentValue * initialRect.width);
        const dragOffset = event.clientX - initialHandleX;
        let didDrag = false;
        const updatePrep = (clientX) => {
          const rect = track.getBoundingClientRect();
          if (!rect.width || !laneKey) return;
          prepFocusLaneKey = laneKey;
          page.dataset.maintPrepFocusLane = prepFocusLaneKey;
          const markerX = clientX - dragOffset;
          const rawValue = Math.max(0, Math.min(0.98, (markerX - rect.left) / rect.width));
          const nextValue = rawValue <= 0.01 ? 0 : (rawValue >= 0.97 ? 0.98 : rawValue);
          prepReadyMap = {
            ...prepReadyMap,
            [laneKey]: nextValue,
          };
          prepReadyProgress = JSON.stringify(prepReadyMap);
          page.dataset.maintPrepReady = prepReadyProgress;
          Array.from(groupRoot.querySelectorAll(`[data-maint-horizon-prep="${laneKey}"]`)).forEach((line) => {
            line.style.left = `${nextValue * 100}%`;
          });
          Array.from(groupRoot.querySelectorAll(`[data-maint-horizon-prep-band="${laneKey}"]`)).forEach((band) => {
            band.style.width = `${nextValue * 100}%`;
          });
          refreshPrepHorizonLiveShell();
        };
        const onMove = (moveEvent) => {
          if (!didDrag && Math.abs(moveEvent.clientX - dragStartX) < 3) return;
          if (!didDrag) {
            didDrag = true;
            document.body.classList.add("is-maint-dragging-cutoff");
          }
          updatePrep(moveEvent.clientX);
        };
        const onUp = (upEvent) => {
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
          document.body.classList.remove("is-maint-dragging-cutoff");
          if (!didDrag) return;
          updatePrep(upEvent.clientX);
          renderMaintenanceWorkspace();
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
      });
    });
    const horizonFold = groupRoot.querySelector(".maintenance-horizon-rangefold");
    horizonFold?.addEventListener("toggle", () => {
      prepHorizonFoldOpen = horizonFold.open;
      localStorage.setItem(MAINT_PREP_HORIZON_FOLD_STORAGE_KEY, prepHorizonFoldOpen ? "1" : "0");
    });
    const persistHorizonMap = () => {
      prepHorizonProgress = JSON.stringify(prepHorizonMap);
      page.dataset.maintPrepHorizon = prepHorizonProgress;
      localStorage.setItem(MAINT_PREP_HORIZON_STORAGE_KEY, prepHorizonProgress);
    };
    Array.from(groupRoot.querySelectorAll("[data-maint-horizon-range]")).forEach((input) => {
      const laneKey = input.dataset.maintHorizonRange;
      const slider = groupRoot.querySelector(`[data-maint-horizon-range-slider="${laneKey}"]`);
      const syncRange = (rawValue) => {
        const nextValue = Math.max(1, Number(rawValue || 1));
        if (!laneKey || !Number.isFinite(nextValue)) return;
        input.value = String(nextValue);
        if (slider) slider.value = String(nextValue);
        prepHorizonMap = {
          ...prepHorizonMap,
          [laneKey]: nextValue,
        };
        persistHorizonMap();
        renderMaintenanceWorkspace();
      };
      input.addEventListener("change", () => syncRange(input.value));
      input.addEventListener("blur", () => syncRange(input.value));
      slider?.addEventListener("input", () => {
        input.value = slider.value;
      });
      slider?.addEventListener("change", () => syncRange(slider.value));
    });
    if (activeView === "builder") {
      renderActionPanel(task);
      return;
    }
    if (task && detailRoot) {
      detailRoot.innerHTML = maintenanceStageMarkup(activeView, maintenanceData, task);
      renderActionPanel(task);
      if (sideRoot) {
        sideRoot.innerHTML = maintenanceSidePanelMarkup(activeView, maintenanceData, task);
      }
    }
    if (sideRoot && !task) {
      sideRoot.innerHTML = maintenanceSidePanelMarkup(activeView, maintenanceData, null);
    }
  };

  const renderFaultWorkspace = () => {
    groupRoot.innerHTML = maintenanceFaultsWorkspaceMarkup(maintenanceData, faultEditorState);
    const createForm = groupRoot.querySelector("#maintenance-fault-create-form");
    createForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = {
        action: "create",
        ...Object.fromEntries(new FormData(createForm).entries()),
      };
      const result = await postJson("/api/maintenance/fault", payload);
      bootstrapData = result.bootstrap || null;
      faultEditorState = "";
      page.dataset.maintFaultEditor = "";
      await renderRoute();
    });
    Array.from(groupRoot.querySelectorAll("[data-maint-fault-toggle]") || []).forEach((button) => {
      button.addEventListener("click", () => {
        const nextState = String(button.dataset.maintFaultToggle || "").trim();
        faultEditorState = faultEditorState === nextState ? "" : nextState;
        page.dataset.maintFaultEditor = faultEditorState;
        renderGroup();
      });
    });
    Array.from(groupRoot.querySelectorAll("[data-maint-fault-form]") || []).forEach((form) => {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const payload = Object.fromEntries(new FormData(form).entries());
        const result = await postJson("/api/maintenance/fault", payload);
        bootstrapData = result.bootstrap || null;
        faultEditorState = "";
        page.dataset.maintFaultEditor = "";
        await renderRoute();
      });
    });
  };

  const renderGroup = () => {
    if (!groupRoot) return;
    if (activeGroup === "faults") {
      renderFaultWorkspace();
      return;
    }
    renderMaintenanceWorkspace();
  };

  groupButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.maintGroup === activeGroup);
    button.addEventListener("click", () => {
      activeGroup = button.dataset.maintGroup;
      page.dataset.maintGroup = activeGroup;
      groupButtons.forEach((item) => item.classList.toggle("is-active", item === button));
      renderGroup();
    });
  });

  renderGroup();
}

function bindProcessSetupPage(processData) {
  const page = document.getElementById("process-setup-page");
  if (!page) return;

  const openOrderDrawButtons = Array.from(page.querySelectorAll("[data-process-order-draw]"));
  const startButtons = Array.from(page.querySelectorAll("[data-process-start]"));
  const saveButton = document.getElementById("ps-save-all-btn");
  const saveSummary = document.getElementById("ps-save-summary");
  const irisSummary = document.getElementById("ps-iris-summary");
  const readinessRoot = document.getElementById("ps-readiness-summary");
  const dieAutoSummary = document.getElementById("ps-die-auto-summary");

  const irisShape = document.getElementById("ps-iris-shape");
  const irisPreform = document.getElementById("ps-iris-preform");
  const irisOct = document.getElementById("ps-iris-oct");
  const irisTiger = document.getElementById("ps-iris-tiger");
  const irisSelected = document.getElementById("ps-iris-selected");
  const irisPm = document.getElementById("ps-iris-pm");
  const dieMode = document.getElementById("ps-die-mode");
  const primaryDie = document.getElementById("ps-primary-die");
  const secondaryDie = document.getElementById("ps-secondary-die");
  const entryFiber = document.getElementById("ps-entry-fiber");
  const targetFirst = document.getElementById("ps-target-first");
  const targetSecond = document.getElementById("ps-target-second");
  const primaryCoating = document.getElementById("ps-primary-coating");
  const secondaryCoating = document.getElementById("ps-secondary-coating");
  const furnaceTemp = document.getElementById("ps-furnace-temp");
  const primaryTemp = document.getElementById("ps-primary-temp");
  const secondaryTemp = document.getElementById("ps-secondary-temp");
  const drawSpeed = document.getElementById("ps-draw-speed");

  const isFilled = (value) => String(value ?? "").trim() !== "";
  let autoDieState = {
    ready: false,
    message: "",
    auto_dies: null,
    error: false,
  };
  let autoDieRequestId = 0;
  let autoDieTimer = 0;

  const renderAutoDieSummary = () => {
    if (!dieAutoSummary) return;
    const autoMode = String(dieMode?.value || "Auto") === "Auto";
    if (!autoMode) {
      dieAutoSummary.innerHTML = `
        <strong>Manual die mode</strong>
        <p>Choose the primary and secondary dies yourself. Switch back to <strong>Auto</strong> to let the background calculator pick the best pair.</p>
      `;
      return;
    }
    const summary = autoDieState.auto_dies || {};
    if (!autoDieState.ready || !summary.primary_die || !summary.secondary_die) {
      dieAutoSummary.innerHTML = `
        <strong>Auto die pick</strong>
        <p>${escapeHtml(autoDieState.message || "Fill the coating targets, coatings, temperatures, and draw speed to auto-pick the best die pair.")}</p>
      `;
      return;
    }
    dieAutoSummary.innerHTML = `
      <strong>Auto die pick</strong>
      <p>${escapeHtml(autoDieState.message || "")}</p>
      <div class="metric-row compact">
        <div class="metric-pill tone-good"><span>Primary</span><strong>${escapeHtml(summary.primary_die || "—")}</strong></div>
        <div class="metric-pill tone-good"><span>Secondary</span><strong>${escapeHtml(summary.secondary_die || "—")}</strong></div>
        <div class="metric-pill tone-info"><span>Pred FC</span><strong>${summary.predicted_first_um != null ? `${Number(summary.predicted_first_um).toFixed(2)} µm` : "—"}</strong></div>
        <div class="metric-pill tone-info"><span>Pred SC</span><strong>${summary.predicted_second_um != null ? `${Number(summary.predicted_second_um).toFixed(2)} µm` : "—"}</strong></div>
        <div class="metric-pill tone-${Math.abs(Number(summary.error_first_um || 0)) <= 2 && Math.abs(Number(summary.error_second_um || 0)) <= 2 ? "good" : "warn"}"><span>Fit</span><strong>Δ1 ${Number(summary.error_first_um || 0).toFixed(2)} · Δ2 ${Number(summary.error_second_um || 0).toFixed(2)}</strong></div>
      </div>
    `;
  };

  const syncDieModeUi = () => {
    const autoMode = String(dieMode?.value || "Auto") === "Auto";
    if (primaryDie) primaryDie.disabled = autoMode;
    if (secondaryDie) secondaryDie.disabled = autoMode;
    renderAutoDieSummary();
  };

  const buildAutoDiePayload = () => ({
    entry_fiber_diameter_um: entryFiber?.value || "",
    target_first_coating_diameter_um: targetFirst?.value || "",
    target_second_coating_diameter_um: targetSecond?.value || "",
    primary_coating: primaryCoating?.value || "",
    secondary_coating: secondaryCoating?.value || "",
    primary_temp_c: primaryTemp?.value || "",
    secondary_temp_c: secondaryTemp?.value || "",
    draw_speed_m_min: drawSpeed?.value || "",
  });

  const requestAutoDies = async () => {
    const autoMode = String(dieMode?.value || "Auto") === "Auto";
    if (!autoMode) {
      autoDieState = { ready: false, message: "", auto_dies: null, error: false };
      syncDieModeUi();
      renderReadiness();
      return;
    }
    const requestId = ++autoDieRequestId;
    try {
      const result = await postJson("/api/process-setup/auto-dies", { coating: buildAutoDiePayload() });
      if (requestId !== autoDieRequestId) return;
      autoDieState = {
        ready: Boolean(result.ready && result.auto_dies),
        message: String(result.message || ""),
        auto_dies: result.auto_dies || null,
        error: false,
      };
      if (autoDieState.ready && autoDieState.auto_dies) {
        if (primaryDie) primaryDie.value = String(autoDieState.auto_dies.primary_die || "");
        if (secondaryDie) secondaryDie.value = String(autoDieState.auto_dies.secondary_die || "");
      }
    } catch (error) {
      if (requestId !== autoDieRequestId) return;
      autoDieState = {
        ready: false,
        message: error.message || "Could not auto-pick dies.",
        auto_dies: null,
        error: true,
      };
    }
    syncDieModeUi();
    renderReadiness();
  };

  const queueAutoDieRefresh = () => {
    window.clearTimeout(autoDieTimer);
    autoDieTimer = window.setTimeout(() => {
      requestAutoDies();
    }, 120);
  };

  const buildIrisState = () => {
    const shape = normalizeProcessSetupIrisShape(String(irisShape?.value || "Circular"));
    const preform = Number(irisPreform?.value || 0);
    const octF2f = Number(irisOct?.value || 0);
    const tigerCut = Number(irisTiger?.value || 0);
    const pmSystem = shape === "PANDA - PM"
      ? true
      : (shape === "Tiger Cut" || shape === "Octagonal")
        ? false
        : Boolean(irisPm?.checked);

    let baseArea = 0;
    let adjustedArea = 0;
    let effectiveDiameter = 0;
    let selectedIris = 0;
    let irisArea = 0;
    let gapArea = 0;

    if (shape === "Octagonal" && octF2f > 0) {
      const a = octF2f / (1 + Math.sqrt(2));
      baseArea = 2 * (1 + Math.sqrt(2)) * Math.pow(a, 2);
      adjustedArea = baseArea;
    } else if (preform > 0) {
      baseArea = Math.PI * Math.pow(preform / 2, 2);
      adjustedArea = shape === "Tiger Cut" ? baseArea * Math.max(0, 1 - tigerCut / 100) : baseArea;
    }
    if (adjustedArea > 0) {
      effectiveDiameter = 2 * Math.sqrt(adjustedArea / Math.PI);
    }

    if (adjustedArea > 0) {
      if (pmSystem) {
        selectedIris = 37.0;
      } else {
        let bestDiameter = 0;
        let bestError = Number.POSITIVE_INFINITY;
        PROCESS_SETUP_IRIS_OPTIONS_MM.forEach((diameter) => {
          const candidateGap = Math.PI * Math.pow(diameter / 2, 2) - adjustedArea;
          const candidateError = Math.abs(candidateGap - PROCESS_SETUP_IRIS_TARGET_GAP_MM2);
          if (candidateError < bestError) {
            bestError = candidateError;
            bestDiameter = diameter;
          }
        });
        selectedIris = bestDiameter;
      }
    }

    irisArea = selectedIris > 0 ? Math.PI * Math.pow(selectedIris / 2, 2) : 0;
    gapArea = irisArea > 0 ? irisArea - adjustedArea : 0;

    return {
      shape,
      preform,
      octF2f,
      tigerCut,
      selectedIris,
      pmSystem,
      targetGap: PROCESS_SETUP_IRIS_TARGET_GAP_MM2,
      baseArea,
      adjustedArea,
      effectiveDiameter,
      irisArea,
      gapArea,
    };
  };

  const renderIrisSummary = () => {
    if (!irisSummary) return;
    const state = buildIrisState();
    if (irisSelected) {
      irisSelected.value = state.selectedIris ? state.selectedIris.toFixed(1) : "";
    }
    if (irisPm) {
      irisPm.checked = state.pmSystem;
      irisPm.disabled = state.shape === "Tiger Cut" || state.shape === "Octagonal" || state.shape === "PANDA - PM";
    }
    if (irisTiger) {
      irisTiger.disabled = state.shape !== "Tiger Cut";
    }
    if (irisOct) {
      irisOct.disabled = state.shape !== "Octagonal";
    }
    irisSummary.innerHTML = `
      <div class="metric-pill tone-info"><span>Shape</span><strong>${state.shape}</strong></div>
      <div class="metric-pill tone-info"><span>Base area</span><strong>${state.baseArea ? state.baseArea.toFixed(1) : "—"}</strong></div>
      <div class="metric-pill tone-warn"><span>Adjusted</span><strong>${state.adjustedArea ? state.adjustedArea.toFixed(1) : "—"}</strong></div>
      <div class="metric-pill tone-info"><span>Effective Ø</span><strong>${state.effectiveDiameter ? state.effectiveDiameter.toFixed(2) : "—"}</strong></div>
      <div class="metric-pill tone-info"><span>Target gap</span><strong>${state.targetGap.toFixed(0)}</strong></div>
      <div class="metric-pill tone-info"><span>Iris Ø</span><strong>${state.selectedIris ? state.selectedIris.toFixed(1) : "—"}</strong></div>
      <div class="metric-pill tone-${state.selectedIris ? (Math.abs(state.gapArea - state.targetGap) <= 10 ? "good" : "warn") : "bad"}"><span>Gap area</span><strong>${state.selectedIris ? state.gapArea.toFixed(1) : "—"}</strong></div>
    `;
    renderReadiness();
  };

  const buildHolderSetpointState = () => {
    const primaryValue = Number(document.getElementById("ps-primary-temp")?.value || NaN);
    const secondaryValue = Number(document.getElementById("ps-secondary-temp")?.value || NaN);
    return {
      primaryValue,
      secondaryValue,
      primaryValid: Number.isFinite(primaryValue),
      secondaryValid: Number.isFinite(secondaryValue),
      primaryCurrent: Number(processData.temp_context?.primary_holder_sp_c ?? NaN),
      secondaryCurrent: Number(processData.temp_context?.secondary_holder_sp_c ?? NaN),
    };
  };

  const applyHolderSetpoints = async ({ ask = true, intro = "Set holder setpoints from the setup temperatures?" } = {}) => {
    const state = buildHolderSetpointState();
    if (!state.primaryValid || !state.secondaryValid) {
      window.alert("Primary and secondary coating temperatures must both be filled before sending holder setpoints.");
      return { applied: false };
    }
    if (ask) {
      const currentPrimaryText = Number.isFinite(state.primaryCurrent) ? `${state.primaryCurrent.toFixed(1)}°C` : "—";
      const currentSecondaryText = Number.isFinite(state.secondaryCurrent) ? `${state.secondaryCurrent.toFixed(1)}°C` : "—";
      const shouldApply = window.confirm(
        `${intro}\n\nPrimary holder: ${state.primaryValue.toFixed(1)}°C (current SP ${currentPrimaryText})\nSecondary holder: ${state.secondaryValue.toFixed(1)}°C (current SP ${currentSecondaryText})`
      );
      if (!shouldApply) {
        return { applied: false };
      }
    }
    const result = await postJson("/api/consumables/temps-save", {
      setpoints: {
        die_holder_primary_c: state.primaryValue,
        die_holder_secondary_c: state.secondaryValue,
      },
    });
    processData.temp_context = {
      ...(processData.temp_context || {}),
      ...(result?.bootstrap?.processSetup?.temp_context || {}),
      primary_holder_sp_c: state.primaryValue,
      secondary_holder_sp_c: state.secondaryValue,
    };
    if (saveSummary) {
      saveSummary.innerHTML = `${result.message} Holder setpoints updated from process setup.`;
    }
    return { applied: true, result };
  };

  const buildReadinessState = () => {
    const irisState = buildIrisState();
    const selectedCsv = processData.selected_csv || "";
    const datasetContext = processData.dataset_context || {};
    const datasetLatestFile = String(datasetContext.latest_file || "");
    const datasetLinked = datasetContext.linked_order_index != null;
    const datasetHasRows = Number(datasetContext.row_count || 0) > 0;
    const datasetIsLatest = Boolean(selectedCsv && datasetLatestFile && selectedCsv === datasetLatestFile);
    const datasetAvailable = Boolean(selectedCsv && datasetHasRows);
    const datasetSummary = !selectedCsv
      ? "No active dataset"
      : datasetIsLatest
        ? `${selectedCsv} · latest in data_set_csv`
        : `${selectedCsv}${datasetLatestFile ? ` · latest ${datasetLatestFile}` : ""}`;
    const fieldDefs = [
      { key: "entryFiber", label: "Entry fiber", id: "ps-entry-fiber", value: document.getElementById("ps-entry-fiber")?.value || "" },
      { key: "furnaceTemp", label: "Furnace temperature", id: "ps-furnace-temp", value: document.getElementById("ps-furnace-temp")?.value || "" },
      { key: "drawSpeed", label: "Draw speed", id: "ps-draw-speed", value: document.getElementById("ps-draw-speed")?.value || "" },
      { key: "targetFirst", label: "Target first coating", id: "ps-target-first", value: document.getElementById("ps-target-first")?.value || "" },
      { key: "targetSecond", label: "Target second coating", id: "ps-target-second", value: document.getElementById("ps-target-second")?.value || "" },
      { key: "primaryCoating", label: "Primary coating", id: "ps-primary-coating", value: document.getElementById("ps-primary-coating")?.value || "" },
      { key: "secondaryCoating", label: "Secondary coating", id: "ps-secondary-coating", value: document.getElementById("ps-secondary-coating")?.value || "" },
      { key: "primaryTemp", label: "Primary temperature", id: "ps-primary-temp", value: document.getElementById("ps-primary-temp")?.value || "" },
      { key: "secondaryTemp", label: "Secondary temperature", id: "ps-secondary-temp", value: document.getElementById("ps-secondary-temp")?.value || "" },
      { key: "primaryDie", label: "Primary die", id: "ps-primary-die", value: document.getElementById("ps-primary-die")?.value || "" },
      { key: "secondaryDie", label: "Secondary die", id: "ps-secondary-die", value: document.getElementById("ps-secondary-die")?.value || "" },
      { key: "selectedIris", label: "Calculated iris", id: "ps-iris-selected", value: irisState.selectedIris ? irisState.selectedIris.toFixed(1) : "" },
      { key: "preformDiameter", label: "Preform diameter", id: "ps-iris-preform", value: document.getElementById("ps-iris-preform")?.value || "" },
      { key: "octF2f", label: "Octagonal F2F", id: "ps-iris-oct", value: document.getElementById("ps-iris-oct")?.value || "" },
      { key: "tigerCut", label: "Tiger cut", id: "ps-iris-tiger", value: document.getElementById("ps-iris-tiger")?.value || "" },
      { key: "pidP", label: "P gain", id: "ps-pid-p", value: document.getElementById("ps-pid-p")?.value || "" },
      { key: "pidI", label: "I gain", id: "ps-pid-i", value: document.getElementById("ps-pid-i")?.value || "" },
      { key: "pidMode", label: "TF mode", id: "ps-pid-mode", value: document.getElementById("ps-pid-mode")?.value || "" },
      { key: "pidInc", label: "Increment value", id: "ps-pid-inc", value: document.getElementById("ps-pid-inc")?.value || "" },
      { key: "drum", label: "Selected drum", id: "ps-drum-select", value: document.getElementById("ps-drum-select")?.value || "" },
    ];
    const fieldMap = Object.fromEntries(fieldDefs.map((field) => [field.key, field]));
    const resolveMissingItems = (keys) => keys
      .map((key) => fieldMap[key])
      .filter((field) => !isFilled(field?.value))
      .map((field) => ({ label: field.label, id: field.id }));
    const readinessBlocks = [
      {
        label: "Dataset",
        summary: datasetAvailable
          ? `${datasetSummary}${datasetLinked ? "" : " · folder visible"}`
          : datasetSummary,
        missingItems: [
          ...(selectedCsv ? [] : [{ label: "Open from Order Draw or scheduled start", id: "" }]),
          ...(selectedCsv && !datasetHasRows ? [{ label: "Dataset has no rows", id: "" }] : []),
        ],
      },
      {
        label: "Coating",
        summary: "Diameters, temperatures, and coating pair",
        missingItems: resolveMissingItems(["entryFiber", "furnaceTemp", "drawSpeed", "targetFirst", "targetSecond", "primaryCoating", "secondaryCoating", "primaryTemp", "secondaryTemp"]),
      },
      {
        label: "Dies",
        summary: "Primary and secondary die selection",
        missingItems: resolveMissingItems(["primaryDie", "secondaryDie"]),
      },
      {
        label: "Iris",
        summary: `${irisState.shape} setup with selected iris`,
        missingItems: [
          ...resolveMissingItems(["preformDiameter"]),
          ...(irisState.shape === "Octagonal" ? resolveMissingItems(["octF2f"]) : []),
          ...(irisState.shape === "Tiger Cut" ? resolveMissingItems(["tigerCut"]) : []),
          ...resolveMissingItems(["selectedIris"]),
        ],
      },
      {
        label: "PID + TF",
        summary: "Diameter control defaults",
        missingItems: resolveMissingItems(["pidP", "pidI", "pidMode", "pidInc"]),
      },
      {
        label: "Drum",
        summary: "Final save target",
        missingItems: resolveMissingItems(["drum"]),
      },
    ].map((block) => ({
      ...block,
      missing: block.missingItems.map((item) => item.label),
      ready: block.missingItems.length === 0,
    }));
    const missingFieldLabels = [...new Set(readinessBlocks.flatMap((block) => block.missingItems.map((item) => item.label)))];
    const missingFieldIds = [...new Set(
      readinessBlocks.flatMap((block) => block.missingItems.map((item) => item.id).filter(Boolean))
    )];
    const readyCount = readinessBlocks.filter((block) => block.ready).length;
    const tone = readyCount === readinessBlocks.length ? "good" : readyCount >= Math.ceil(readinessBlocks.length / 2) ? "warn" : "bad";
    const overallText = readyCount === readinessBlocks.length
      ? "All required setup blocks are ready to save."
      : `Missing ${missingFieldLabels.length} required input${missingFieldLabels.length === 1 ? "" : "s"}.`;
    return {
      fieldDefs,
      readinessBlocks,
      missingFieldLabels,
      missingFieldIds,
      readyCount,
      tone,
      overallText,
      holderSync: {
        primaryValue: Number.isFinite(Number(document.getElementById("ps-primary-temp")?.value || NaN))
          ? Number(document.getElementById("ps-primary-temp")?.value || NaN)
          : null,
        secondaryValue: Number.isFinite(Number(document.getElementById("ps-secondary-temp")?.value || NaN))
          ? Number(document.getElementById("ps-secondary-temp")?.value || NaN)
          : null,
        primaryCurrent: Number.isFinite(Number(processData.temp_context?.primary_holder_sp_c ?? NaN))
          ? Number(processData.temp_context?.primary_holder_sp_c ?? NaN)
          : null,
        secondaryCurrent: Number.isFinite(Number(processData.temp_context?.secondary_holder_sp_c ?? NaN))
          ? Number(processData.temp_context?.secondary_holder_sp_c ?? NaN)
          : null,
        primaryMeasured: Number.isFinite(Number(processData.temp_context?.primary_holder_mv_c ?? NaN))
          ? Number(processData.temp_context?.primary_holder_mv_c ?? NaN)
          : null,
        secondaryMeasured: Number.isFinite(Number(processData.temp_context?.secondary_holder_mv_c ?? NaN))
          ? Number(processData.temp_context?.secondary_holder_mv_c ?? NaN)
          : null,
      },
    };
  };

  const renderReadiness = () => {
    if (!readinessRoot) return;
    const readiness = buildReadinessState();
    const holderSync = readiness.holderSync || {};
    const canSyncTemps = holderSync.primaryValue != null && holderSync.secondaryValue != null;
    readiness.fieldDefs.forEach((field) => document.getElementById(field.id)?.classList.remove("is-missing-input"));
    readiness.missingFieldIds.forEach((id) => document.getElementById(id)?.classList.add("is-missing-input"));
    readinessRoot.innerHTML = `
      <div class="ps-readiness-board tone-${readiness.tone}">
        <div class="ps-readiness-board-head">
          <div>
            <span>Setup readiness</span>
            <strong>${readiness.readyCount}/${readiness.readinessBlocks.length} blocks ready</strong>
          </div>
          <em>${readiness.overallText}</em>
        </div>
        <div class="ps-readiness-grid">
          ${readiness.readinessBlocks.map((block) => `
            <article class="ps-readiness-card ${block.ready ? "is-ready" : "is-missing"}">
              <div class="ps-readiness-card-head">
                <span>${block.label}</span>
                <strong>${block.ready ? "Ready" : "Missing"}</strong>
              </div>
              <p>${block.summary}</p>
              ${block.missing.length ? `
                <div class="ps-readiness-tags">
                  ${block.missing.map((item) => `<span class="ps-readiness-tag is-missing">${item}</span>`).join("")}
                </div>
              ` : `<div class="ps-readiness-tags"><span class="ps-readiness-tag is-ready">Ready</span></div>`}
            </article>
          `).join("")}
        </div>
        <div class="ps-readiness-sync">
          <div class="ps-readiness-sync-copy">
            <span>Holder setpoint match</span>
            <strong>Setup temp is the target you want for this draw. Current SP may still be different, and MV now is the live holder temperature from Consumables.</strong>
            <p>${canSyncTemps
              ? "If you want the real controller to move toward the setup values, make the holder setpoints match the setup temp. After that, MV should start moving toward those setpoints."
              : "Fill both coating temperature fields first, then you can make the holder setpoints match the setup temp."}</p>
          </div>
          <div class="ps-readiness-sync-grid">
            <article class="ps-readiness-sync-card">
              <span>Primary holder</span>
              <div class="ps-readiness-sync-values">
                <div><em>Setup temp</em><strong>${holderSync.primaryValue != null ? `${holderSync.primaryValue.toFixed(1)}°C` : "—"}</strong></div>
                <div><em>Current SP</em><strong>${holderSync.primaryCurrent != null ? `${holderSync.primaryCurrent.toFixed(1)}°C` : "—"}</strong></div>
                <div><em>MV now</em><strong>${holderSync.primaryMeasured != null ? `${holderSync.primaryMeasured.toFixed(1)}°C` : "—"}</strong></div>
              </div>
            </article>
            <article class="ps-readiness-sync-card">
              <span>Secondary holder</span>
              <div class="ps-readiness-sync-values">
                <div><em>Setup temp</em><strong>${holderSync.secondaryValue != null ? `${holderSync.secondaryValue.toFixed(1)}°C` : "—"}</strong></div>
                <div><em>Current SP</em><strong>${holderSync.secondaryCurrent != null ? `${holderSync.secondaryCurrent.toFixed(1)}°C` : "—"}</strong></div>
                <div><em>MV now</em><strong>${holderSync.secondaryMeasured != null ? `${holderSync.secondaryMeasured.toFixed(1)}°C` : "—"}</strong></div>
              </div>
            </article>
          </div>
          <div class="ps-readiness-sync-actions">
            <button class="action-btn action-secondary" type="button" id="ps-readiness-sync-temp" ${canSyncTemps ? "" : "disabled"}>Match Holder Setpoints To Setup Temp</button>
          </div>
        </div>
      </div>
    `;
    const readinessSyncButton = document.getElementById("ps-readiness-sync-temp");
    readinessSyncButton?.addEventListener("click", async () => {
      const holderResult = await applyHolderSetpoints({
        ask: true,
        intro: "Make the holder setpoints match the current setup temperatures in Consumables?",
      });
      if (!holderResult.applied) return;
      renderReadiness();
    });
  };

  openOrderDrawButtons.forEach((button) => {
    button.addEventListener("click", () => {
      window.location.hash = "#/order-draw";
    });
  });

  startButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const orderIndex = Number(button.dataset.processStart);
      const order = (processData.scheduled_orders || []).find((item) => Number(item.index) === orderIndex) || {};
      const result = await postJson("/api/process-setup/scheduled-start", {
        orderIndex,
        preformNumber: order.preform || "",
      });
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    });
  });

  [irisShape, irisPreform, irisOct, irisTiger, irisPm].forEach((element) => {
    element?.addEventListener("input", renderIrisSummary);
    element?.addEventListener("change", renderIrisSummary);
  });

  [
    "ps-primary-coating",
    "ps-secondary-coating",
    "ps-primary-die",
    "ps-secondary-die",
    "ps-drum-select",
    "ps-entry-fiber",
    "ps-furnace-temp",
    "ps-target-first",
    "ps-target-second",
    "ps-primary-temp",
    "ps-secondary-temp",
    "ps-draw-speed",
  ].forEach((id) => {
    const node = document.getElementById(id);
    node?.addEventListener("input", renderReadiness);
    node?.addEventListener("change", renderReadiness);
  });

  [
    dieMode,
    entryFiber,
    furnaceTemp,
    targetFirst,
    targetSecond,
    primaryCoating,
    secondaryCoating,
    primaryTemp,
    secondaryTemp,
    drawSpeed,
  ].forEach((node) => {
    node?.addEventListener("input", queueAutoDieRefresh);
    node?.addEventListener("change", queueAutoDieRefresh);
  });

  saveButton?.addEventListener("click", async () => {
    const readiness = buildReadinessState();
    if (readiness.missingFieldLabels.length) {
      const previewItems = readiness.missingFieldLabels
        .slice(0, 8)
        .map((label) => `- ${label}`)
        .join("\n");
      const moreText = readiness.missingFieldLabels.length > 8
        ? `\n- ...and ${readiness.missingFieldLabels.length - 8} more`
        : "";
      const shouldSave = window.confirm(
        `Save setup with missing inputs?\n\n${previewItems}${moreText}`
      );
      if (!shouldSave) {
        return;
      }
    }
    const irisState = buildIrisState();
    const payload = {
      selectedCsv: processData.selected_csv || "",
      iris: {
        shape: irisState.shape,
        preform_diameter_mm: irisState.preform || "",
        oct_f2f_mm: irisState.shape === "Octagonal" ? (irisState.octF2f || "") : "",
        tiger_cut_pct: irisState.shape === "Tiger Cut" ? (irisState.tigerCut || "") : "",
        pm_system: irisState.pmSystem,
        iris_mode: irisState.pmSystem ? "PM Auto" : "Manual",
        selected_iris_diameter_mm: irisState.selectedIris || "",
        base_area_mm2: irisState.baseArea ? irisState.baseArea.toFixed(3) : "",
        adjusted_area_mm2: irisState.adjustedArea ? irisState.adjustedArea.toFixed(3) : "",
        effective_preform_diameter_mm: irisState.effectiveDiameter ? irisState.effectiveDiameter.toFixed(3) : "",
        gap_area_mm2: irisState.selectedIris ? irisState.gapArea.toFixed(3) : "",
      },
      coating: {
        entry_fiber_diameter_um: document.getElementById("ps-entry-fiber")?.value || "",
        furnace_temp_c: document.getElementById("ps-furnace-temp")?.value || "",
        target_first_coating_diameter_um: document.getElementById("ps-target-first")?.value || "",
        target_second_coating_diameter_um: document.getElementById("ps-target-second")?.value || "",
        primary_coating: document.getElementById("ps-primary-coating")?.value || "",
        secondary_coating: document.getElementById("ps-secondary-coating")?.value || "",
        primary_temp_c: document.getElementById("ps-primary-temp")?.value || "",
        secondary_temp_c: document.getElementById("ps-secondary-temp")?.value || "",
        die_mode: document.getElementById("ps-die-mode")?.value || "Auto",
        primary_die: document.getElementById("ps-primary-die")?.value || "",
        secondary_die: document.getElementById("ps-secondary-die")?.value || "",
        predicted_first_coating_diameter_um: autoDieState.ready && autoDieState.auto_dies ? autoDieState.auto_dies.predicted_first_um || "" : "",
        predicted_second_coating_diameter_um: autoDieState.ready && autoDieState.auto_dies ? autoDieState.auto_dies.predicted_second_um || "" : "",
        ideal_primary_die_um: autoDieState.ready && autoDieState.auto_dies ? autoDieState.auto_dies.ideal_primary_die_um || "" : "",
        ideal_secondary_die_um: autoDieState.ready && autoDieState.auto_dies ? autoDieState.auto_dies.ideal_secondary_die_um || "" : "",
        draw_speed_m_min: document.getElementById("ps-draw-speed")?.value || "",
      },
      pid: {
        p_gain: document.getElementById("ps-pid-p")?.value || "",
        i_gain: document.getElementById("ps-pid-i")?.value || "",
        tf_mode: document.getElementById("ps-pid-mode")?.value || "",
        increment_value_mm: document.getElementById("ps-pid-inc")?.value || "",
      },
      drum: {
        selected_drum: document.getElementById("ps-drum-select")?.value || "",
      },
    };
    const result = await postJson("/api/process-setup/save-all", payload);
    let nextBootstrap = result.bootstrap || null;
    if (saveSummary) {
      saveSummary.innerHTML = result.message;
    }
    const holderState = buildHolderSetpointState();
    if (holderState.primaryValid && holderState.secondaryValid) {
      const shouldSyncTemps = window.confirm(
        `Setup saved to ${processData.selected_csv || "the active dataset"}.\n\nApply these setup temperatures as holder setpoints too?\nPrimary holder setpoint: ${holderState.primaryValue.toFixed(1)}°C\nSecondary holder setpoint: ${holderState.secondaryValue.toFixed(1)}°C`
      );
      if (shouldSyncTemps) {
        const holderResult = await applyHolderSetpoints({
          ask: false,
          intro: "",
        });
        if (holderResult.applied) {
          nextBootstrap = holderResult.result?.bootstrap || nextBootstrap;
        }
      }
    }
    bootstrapData = nextBootstrap;
    await renderRoute();
  });

  renderIrisSummary();
  syncDieModeUi();
  queueAutoDieRefresh();
  renderReadiness();
}

function bindConsumablesPage() {
  const page = document.getElementById("consumables-page");
  if (!page) return;
  if (consumablesLivePollTimer) {
    window.clearInterval(consumablesLivePollTimer);
    consumablesLivePollTimer = null;
  }
  consumablesLivePollInFlight = false;
  const tempsForm = document.getElementById("consumables-temp-form");
  const containersForm = document.getElementById("consumables-containers-form");
  const stockForm = document.getElementById("consumables-stock-form");
  const coatingsForm = document.getElementById("consumables-coatings-form");
  const diesForm = document.getElementById("consumables-dies-form");
  const refreshTempsButton = document.getElementById("consumables-temp-refresh");
  const tempsSourcePanel = tempsForm?.querySelector(".consumables-temp-source");
  let tempsSaveTimer = null;
  let tempsSaveInFlight = false;
  let tempsSaveQueued = false;
  const sourceBaseMarkup = (statusText = "set values auto-save while you edit") => {
    const sampledAt = tempsSourcePanel?.dataset.sampledAt || "No CSV sample yet";
    return `Measured values are sampled from <strong>tower_temps.csv</strong> · Last sample ${sampledAt} · ${statusText}`;
  };
  const setTempsSourceStatus = (statusText) => {
    if (!tempsSourcePanel) return;
    tempsSourcePanel.innerHTML = sourceBaseMarkup(statusText);
  };
  const syncTempLiveView = () => {
    if (!tempsForm) return;
    Array.from(tempsForm.querySelectorAll("[data-temp-field]")).forEach((input) => {
      const field = input.dataset.tempField;
      const measuredValue = Number(input.dataset.measuredValue || 0);
      const setValue = Number(input.value || 0);
      const delta = measuredValue - setValue;
      const prefix = delta > 0 ? "+" : "";
      const tempText = `${setValue.toFixed(1)}°C`;
      const trackText = `${prefix}${delta.toFixed(1)}°C`;
      tempsForm.querySelectorAll(`[data-temp-track="${field}"]`).forEach((node) => {
        node.textContent = `Track ${trackText}`;
      });
    });
  };
  const collectTempSetpoints = () =>
    Object.fromEntries(Array.from(new FormData(tempsForm).entries()).map(([key, value]) => [key, value]));
  const saveTempSetpoints = async (mode = "manual") => {
    if (!tempsForm) return;
    if (tempsSaveInFlight) {
      tempsSaveQueued = true;
      return;
    }
    tempsSaveInFlight = true;
    setTempsSourceStatus(mode === "auto" ? "saving set values..." : "saving set values...");
    try {
      const result = await postJson("/api/consumables/temps-save", { setpoints: collectTempSetpoints() });
      bootstrapData = result.bootstrap || bootstrapData;
      setTempsSourceStatus(mode === "auto" ? "set values saved" : "set values saved");
    } catch (error) {
      setTempsSourceStatus("set values save failed");
      const host = tempsForm;
      host.insertAdjacentHTML("beforebegin", `<div class="micro-panel">${error.message}</div>`);
    } finally {
      tempsSaveInFlight = false;
      if (tempsSaveQueued) {
        tempsSaveQueued = false;
        clearTimeout(tempsSaveTimer);
        tempsSaveTimer = setTimeout(() => saveTempSetpoints("auto"), 300);
      }
    }
  };
  refreshTempsButton?.addEventListener("click", async () => {
    clearTimeout(tempsSaveTimer);
    bootstrapData = null;
    await renderRoute();
  });
  tempsForm?.addEventListener("input", (event) => {
    if (!(event.target instanceof HTMLInputElement) || !event.target.dataset.tempField) return;
    syncTempLiveView();
    clearTimeout(tempsSaveTimer);
    tempsSaveTimer = setTimeout(() => saveTempSetpoints("auto"), 650);
  });
  syncTempLiveView();
  tempsForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearTimeout(tempsSaveTimer);
    await saveTempSetpoints("manual");
  });
  stockForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const rows = Array.from(stockForm.querySelectorAll(".consumables-stock-row:not(.is-add)")).map((row, index) => ({
      label: row.querySelector(`input[name="stock_label_${index}"]`)?.value || "",
      value: row.querySelector(`input[name="stock_value_${index}"]`)?.value || "",
      min_stock_kg: row.querySelector(`input[name="stock_min_${index}"]`)?.value || "",
      remove: row.querySelector(`input[name="stock_remove_${index}"]`)?.checked ? "1" : "",
    }));
    const custom = {
      label: stockForm.querySelector('input[name="new_stock_label"]')?.value || "",
      value: stockForm.querySelector('input[name="new_stock_value"]')?.value || "",
      min_stock_kg: stockForm.querySelector('input[name="new_stock_min"]')?.value || "",
    };
    try {
      const result = await postJson("/api/consumables/stock-save", { rows, custom });
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      const host = stockForm.closest(".chart-card") || stockForm;
      host.insertAdjacentHTML("beforeend", `<div class="micro-panel consumables-stock-message">${escapeHtml(error.message || "Could not save stock values.")}</div>`);
    }
  });
  containersForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const sharedDiameterMm = containersForm.querySelector('input[name="container_shared_diameter"]')?.value || "";
    const rows = Array.from(containersForm.querySelectorAll(".consumables-container-row")).map((row, index) => ({
      label: row.querySelector(`input[name="container_label_${index}"]`)?.value || "",
      type: row.querySelector(`input[name="container_type_${index}"]`)?.value || "",
      sensor_column: row.querySelector(`select[name="container_sensor_${index}"]`)?.value || "",
    }));
    try {
      const result = await postJson("/api/consumables/containers-save", { rows, shared_diameter_mm: sharedDiameterMm });
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      const host = containersForm.closest(".chart-card") || containersForm;
      host.insertAdjacentHTML("beforeend", `<div class="micro-panel consumables-stock-message">${escapeHtml(error.message || "Could not save live fill setup.")}</div>`);
    }
  });
  coatingsForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const rows = Array.from(coatingsForm.querySelectorAll(".consumables-coating-edit-row")).map((row, index) => ({
      label: row.querySelector(`input[name="coating_label_${index}"]`)?.value || "",
      description: row.querySelector(`textarea[name="coating_description_${index}"]`)?.value || "",
      density: row.querySelector(`input[name="coating_density_${index}"]`)?.value || "",
      viscosity: row.querySelector(`input[name="coating_viscosity_${index}"]`)?.value || "",
      refractive_index: row.querySelector(`input[name="coating_ri_${index}"]`)?.value || "",
    }));
    try {
      const result = await postJson("/api/consumables/coatings-save", { rows });
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      const host = coatingsForm.closest(".fold-body") || coatingsForm;
      host.insertAdjacentHTML("beforeend", `<div class="micro-panel consumables-stock-message">${escapeHtml(error.message || "Could not save coating guide.")}</div>`);
    }
  });
  diesForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const stations = Array.from(diesForm.querySelectorAll(".consumables-die-row")).map((row, index) => ({
      original_station: row.querySelector(`input[name="original_station_${index}"]`)?.value || "",
      station: row.querySelector(`input[name="station_name_${index}"]`)?.value || "",
      entry_die_um: row.querySelector(`input[name="entry_die_um_${index}"]`)?.value || "",
      primary_die_um: row.querySelector(`input[name="primary_die_um_${index}"]`)?.value || "",
    }));
    try {
      const result = await postJson("/api/consumables/dies-save", { stations });
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      const host = diesForm.closest(".fold-body") || diesForm;
      host.insertAdjacentHTML("afterbegin", `<div class="micro-panel">${error.message}</div>`);
    }
  });
  const pageRoot = document.getElementById("page-root");
  const refreshConsumablesLive = async () => {
    if (getCurrentRoute() !== "/consumables") {
      if (consumablesLivePollTimer) {
        window.clearInterval(consumablesLivePollTimer);
        consumablesLivePollTimer = null;
      }
      consumablesLivePollInFlight = false;
      return;
    }
    if (!pageRoot || consumablesLivePollInFlight) return;
    const activeElement = document.activeElement;
    if (activeElement && page.contains(activeElement) && activeElement.closest("form")) {
      return;
    }
    consumablesLivePollInFlight = true;
    try {
      const openFoldTitles = new Set(
        Array.from(page.querySelectorAll("details.fold-section[open] .fold-summary-copy span"))
          .map((node) => node.textContent.trim())
          .filter(Boolean),
      );
      const freshData = await getJson("/api/consumables");
      bootstrapData = { ...(bootstrapData || {}), consumables: freshData };
      pageRoot.innerHTML = await renderConsumablesPage(freshData);
      bindConsumablesPage();
      bindFoldSections(pageRoot);
      Array.from(pageRoot.querySelectorAll("details.fold-section .fold-summary-copy span")).forEach((node) => {
        const title = node.textContent.trim();
        if (!title || !openFoldTitles.has(title)) return;
        const details = node.closest("details.fold-section");
        if (details instanceof HTMLDetailsElement) details.open = true;
      });
    } catch (error) {
      console.error(error);
    } finally {
      consumablesLivePollInFlight = false;
    }
  };
  consumablesLivePollTimer = window.setInterval(refreshConsumablesLive, CONSUMABLES_LIVE_POLL_INTERVAL_MS);
}

function bindReportCenterPage(reportData) {
  const page = document.getElementById("report-center-page");
  if (!page) return;

  const modeButtons = Array.from(page.querySelectorAll("[data-report-mode]"));
  const panels = Array.from(page.querySelectorAll("[data-report-panel]"));
  const operationsForm = document.getElementById("report-operations-form");
  const markdownPreviewCard = document.getElementById("report-markdown-preview-card");
  const markdownPreviewTitle = document.getElementById("report-markdown-preview-title");
  const markdownPreviewRoot = document.getElementById("report-markdown-preview-root");

  const setMode = (mode) => {
    modeButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.reportMode === mode));
    panels.forEach((panel) => panel.classList.toggle("is-active", panel.dataset.reportPanel === mode));
  };

  modeButtons.forEach((button) => {
    button.addEventListener("click", () => setMode(button.dataset.reportMode));
  });

  operationsForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const formData = new FormData(operationsForm);
      const payload = {
        title: String(formData.get("title") || ""),
        startDate: String(formData.get("startDate") || ""),
        endDate: String(formData.get("endDate") || ""),
        filename: String(formData.get("filename") || ""),
        sections: formData.getAll("sections"),
      };
      const result = await postJson("/api/report-center/operations-export", payload);
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      const message = page.querySelector(".section-heading p");
      if (message) message.textContent = error.message;
    }
  });

  Array.from(page.querySelectorAll("[data-report-preview]")).forEach((button) => {
    button.addEventListener("click", async () => {
      const fileName = button.getAttribute("data-report-preview") || "";
      if (!fileName || !markdownPreviewCard || !markdownPreviewRoot || !markdownPreviewTitle) return;
      markdownPreviewCard.hidden = false;
      markdownPreviewTitle.textContent = fileName;
      markdownPreviewRoot.innerHTML = `Loading ${escapeHtml(fileName)}...`;
      try {
        const response = await fetch(`/api/report-center/file?name=${encodeURIComponent(fileName)}`);
        if (!response.ok) {
          throw new Error(`Could not load ${fileName}`);
        }
        const text = await response.text();
        markdownPreviewRoot.innerHTML = escapeHtml(text).replace(/\n/g, "<br/>");
        markdownPreviewCard.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (error) {
        markdownPreviewRoot.innerHTML = `<div class="micro-panel">${escapeHtml(error.message || `Could not load ${fileName}`)}</div>`;
      }
    });
  });

  setMode("Operations Report");
}

function bindSqlLabPage(sqlData) {
  const page = document.getElementById("sql-lab-page");
  if (!page) return;

  const datasetSelect = document.getElementById("sql-dataset-select");
  const filterInput = document.getElementById("sql-filter-input");
  const familyFilter = document.getElementById("sql-family-filter");
  const onlyAvg = document.getElementById("sql-only-avg");
  const onlyMin = document.getElementById("sql-only-min");
  const onlyMax = document.getElementById("sql-only-max");
  const selectionCount = document.getElementById("sql-selection-count");
  const selectionSummary = document.getElementById("sql-selection-summary");
  const matchScroll = document.getElementById("sql-match-scroll");
  const useAllFiltered = document.getElementById("sql-use-all-filtered");
  const clearSelection = document.getElementById("sql-clear-selection");
  const stepButtons = Array.from(page.querySelectorAll("[data-sql-step]"));
  const stepPanels = Array.from(page.querySelectorAll("[data-sql-step-panel]"));
  const operatorSelect = document.getElementById("sql-operator-select");
  const value1Input = document.getElementById("sql-value-1");
  const value2Input = document.getElementById("sql-value-2");
  const joinerSelect = document.getElementById("sql-joiner-select");
  const negateToggle = document.getElementById("sql-negate-toggle");
  const timeEnabled = document.getElementById("sql-time-enabled");
  const timeFrom = document.getElementById("sql-time-from");
  const timeTo = document.getElementById("sql-time-to");
  const includeDraws = document.getElementById("sql-include-draws");
  const includeMaintenance = document.getElementById("sql-include-maintenance");
  const includeFaults = document.getElementById("sql-include-faults");
  const maintenanceFiltersShell = document.getElementById("sql-maintenance-filters-shell");
  const faultFiltersShell = document.getElementById("sql-fault-filters-shell");
  const eventScope = document.getElementById("sql-event-scope");
  const maintenanceText = document.getElementById("sql-maintenance-text");
  const maintenanceComponent = document.getElementById("sql-maintenance-component");
  const faultText = document.getElementById("sql-fault-text");
  const faultComponent = document.getElementById("sql-fault-component");
  const faultSeverity = document.getElementById("sql-fault-severity");
  const ruleGrid = document.getElementById("sql-rule-grid");
  const value2Block = document.getElementById("sql-value-2-block");
  const addGroupCondition = document.getElementById("sql-add-group-condition");
  const removeLastCondition = document.getElementById("sql-remove-last-condition");
  const clearConditions = document.getElementById("sql-clear-conditions");
  const runFilterButton = document.getElementById("sql-run-filter-btn");
  const conditionsRoot = document.getElementById("sql-conditions-root");
  const filterSummaryRoot = document.getElementById("sql-filter-summary-root");
  const previewRoot = document.getElementById("sql-preview-root");
  const groupRoot = document.getElementById("sql-group-list-root");
  const datasetSummaryRoot = document.getElementById("sql-dataset-summary-root");
  const datasetTitle = document.getElementById("sql-dataset-title");
  const runDraftRoot = document.getElementById("sql-run-draft-root");
  const runSummaryRoot = document.getElementById("sql-run-summary-root");
  const interpretationRoot = document.getElementById("sql-interpretation-root");
  const exportResultsButton = document.getElementById("sql-export-results-btn");
  const exportStatusRoot = document.getElementById("sql-export-status");
  const analysisSeriesRoot = document.getElementById("sql-analysis-series-root");
  const analysisMathRoot = document.getElementById("sql-analysis-math-root");
  const analysisHoverRoot = document.getElementById("sql-analysis-hover-root");
  const analysisDetailRoot = document.getElementById("sql-analysis-detail-root");
  const analysisCanvas = document.getElementById("sql-analysis-canvas");
  const analysisTooltip = document.getElementById("sql-analysis-tooltip");
  const analysisHero = document.getElementById("sql-analysis-hero");
  const analysisReducer = document.getElementById("sql-analysis-reducer");
  const restoreHiddenPointsButton = document.getElementById("sql-plot-restore-hidden");
  const analysisSourceButtons = Array.from(page.querySelectorAll("[data-sql-analysis-source]"));
  const analysisSearchInput = document.getElementById("sql-analysis-search");
  const analysisSearchNote = document.getElementById("sql-analysis-search-note");
  const mathSourceA = document.getElementById("sql-math-source-a");
  const mathSourceB = document.getElementById("sql-math-source-b");
  const mathOperation = document.getElementById("sql-math-operation");
  const mathExpression = document.getElementById("sql-math-expression");
  const mathSummaryRoot = document.getElementById("sql-math-summary-root");
  const mathHoverRoot = document.getElementById("sql-math-hover-root");
  const mathCanvas = document.getElementById("sql-math-canvas");
  const mathTooltip = document.getElementById("sql-math-tooltip");
  const mathPresetButtons = Array.from(page.querySelectorAll("[data-sql-math-preset]"));
  const mathExpressionExamples = Array.from(page.querySelectorAll("[data-sql-math-expression-example]"));
  const mathRecipesRoot = document.getElementById("sql-math-recipes-root");
  const mathSaveRecipeButton = document.getElementById("sql-math-save-recipe");
  const mathClearRecipesButton = document.getElementById("sql-math-clear-recipes");
  const plotAllMatchedButton = document.getElementById("sql-plot-all-matched");
  const plotClearButton = document.getElementById("sql-plot-clear");
  const matchedDrawsRoot = document.getElementById("sql-matched-draws-root");
  const matchedValuesRoot = document.getElementById("sql-matched-values-root");
  const maintenanceResultsRoot = document.getElementById("sql-maintenance-results-root");
  const faultResultsRoot = document.getElementById("sql-fault-results-root");
  const queryInput = document.getElementById("sql-query-input");
  const queryResultRoot = document.getElementById("sql-query-result-root");
  const templateButtons = Array.from(page.querySelectorAll("[data-sql-template]"));
  const runButton = document.getElementById("sql-run-btn");

  let datasetDetails = null;
  let activeGroup = "All";
  let currentStep = "1";
  let currentConditions = [];
  let selectedParameterNames = [];
  let lastFilterResult = null;
  let lastFilterPayload = null;
  let activeAnalysisParams = [];
  let hiddenAnalysisParams = [];
  let currentAnalysisTargets = [];
  let selectedAnalysisTarget = null;
  let lastAnalysisCanvasModel = null;
  let lastAnalysisCanvasOverlays = null;
  let analysisCanvasFrame = 0;
  let currentMathTargets = [];
  let analysisScopeCacheKey = "";
  let analysisScopeData = { records: [], draw_count: 0, row_count: 0 };
  let analysisResourceMode = "filter";
  let analysisPlotMode = "filter";
  let analysisReduceMode = "avg";
  let detailExpanded = false;
  let detailTab = "overview";
  let hoveredAnalysisKey = "";
  let hoveredMathKey = "";
  let hoveredAnalysisTarget = null;
  let hoveredMathTarget = null;
  let hiddenAnalysisPointKeys = [];
  let mathConfig = {
    sourceA: "",
    sourceB: "",
    operation: "identity",
    expression: "A",
    window: SQL_MATH_FIXED_WINDOW,
    reducer: "avg",
  };
  let savedMathRecipes = [];

  const redrawSqlAnalysisCanvas = () => {
    if (!analysisCanvas || !lastAnalysisCanvasModel) return;
    currentAnalysisTargets = drawSqlAnalysisCanvas(
      lastAnalysisCanvasModel,
      analysisCanvas,
      lastAnalysisCanvasOverlays || {},
      selectedAnalysisTarget,
    );
  };

  const scheduleSqlAnalysisCanvasRedraw = () => {
    if (!analysisCanvas) return;
    if (analysisCanvasFrame) window.cancelAnimationFrame(analysisCanvasFrame);
    analysisCanvasFrame = window.requestAnimationFrame(() => {
      analysisCanvasFrame = 0;
      redrawSqlAnalysisCanvas();
    });
  };

  const setStep = (step) => {
    currentStep = String(step);
    stepButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.sqlStep === currentStep));
    stepPanels.forEach((panel) => panel.classList.toggle("is-active", panel.dataset.sqlStepPanel === currentStep));
  };

  const findFoldSectionByTitle = (title) => Array.from(page.querySelectorAll(".fold-section")).find((section) => {
    const label = section.querySelector(".fold-summary-copy span");
    return String(label?.textContent || "").trim() === String(title || "").trim();
  });

  const revealSqlResultsStep = ({
    scrollTarget = null,
    openAnalysisStudio = false,
    openMatchedDraws = false,
  } = {}) => {
    setStep("3");
    if (openAnalysisStudio) {
      const analysisSection = findFoldSectionByTitle("Analysis studio");
      if (analysisSection) analysisSection.open = true;
    }
    const drawsSection = findFoldSectionByTitle("Matched draws");
    if (drawsSection) {
      drawsSection.open = Boolean(openMatchedDraws);
    }
    bindFoldSections(page);
    if (scrollTarget) {
      window.requestAnimationFrame(() => {
        scrollTarget.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  };

  const buildSqlFilterPayload = () => ({
    dataset: datasetSelect?.value || "__ALL__",
    conditions: currentConditions.map((item) => ({
      params: item.params,
      op: item.op,
      v1: item.v1,
      v2: item.v2,
      negate: item.negate,
      joiner: item.joiner === "BASE" ? "AND" : item.joiner,
      groupLogic: item.groupLogic,
    })),
    timeEnabled: Boolean(timeEnabled?.checked),
    timeFrom: String(timeFrom?.value || ""),
    timeTo: String(timeTo?.value || ""),
    includeDraws: Boolean(includeDraws?.checked),
    includeMaintenance: Boolean(includeMaintenance?.checked),
    includeFaults: Boolean(includeFaults?.checked),
    eventScope: String(eventScope?.value || "Only within matched draws window"),
    maintenanceText: String(maintenanceText?.value || ""),
    maintenanceComponent: String(maintenanceComponent?.value || ""),
    faultText: String(faultText?.value || ""),
    faultComponent: String(faultComponent?.value || ""),
    faultSeverity: String(faultSeverity?.value || ""),
  });

  const renderSqlExportStatus = (payload = null) => {
    if (!exportStatusRoot) return;
    if (!payload) {
      exportStatusRoot.innerHTML = `Run a filter, then export the matched draw set and condition parameters as a CSV.`;
      return;
    }
    exportStatusRoot.innerHTML = `<span>${escapeHtml(payload.message || "Matched results CSV ready.")}</span>`;
  };

  const filteredParameterNames = ({ ignoreMetricMode = false } = {}) => {
    if (!datasetDetails) return [];
    const needle = String(filterInput?.value || "").trim().toLowerCase();
    const family = String(familyFilter?.value || "All");
    let list = [...(datasetDetails.parameter_names || [])];
    if (needle) {
      list = list.filter((item) => item.toLowerCase().includes(needle));
    }
    if (family !== "All") {
      list = list.filter((item) => {
        const info = `${item}`.toLowerCase();
        if (family === "Zones") return info.includes("zone ");
        if (family === "Order") return info.startsWith("order__");
        if (family === "Process") return info.startsWith("process__");
        if (family === "Winder + T&M") {
          return (
            info.includes("t&m")
            || info.includes("good zone")
            || info.includes("cut/save")
            || info.includes("fiber length")
            || info.includes("fibre length")
            || info.includes("drum |")
          );
        }
        return !info.startsWith("order__") && !info.startsWith("process__") && !info.includes("zone ");
      });
    }
    if (!ignoreMetricMode) {
      if (onlyAvg?.checked) list = list.filter((item) => item.toLowerCase().includes("avg"));
      if (onlyMin?.checked) list = list.filter((item) => item.toLowerCase().includes("min"));
      if (onlyMax?.checked) list = list.filter((item) => item.toLowerCase().includes("max"));
    }
    return list.slice(0, 500);
  };

  const renderSelectionSummary = () => {
    const selected = [...selectedParameterNames];
    const groupedLabels = Array.from(new Set(selected.map((item) => sqlAnalysisGroupLabel(item)).filter(Boolean)));
    if (selectionCount) {
      selectionCount.textContent = `${selected.length} selected`;
    }
    if (selectionSummary) {
      selectionSummary.innerHTML = selected.length
        ? `
          <div class="sql-selection-inline">
            <span>Current rule group</span>
            <strong>${escapeHtml(sqlConditionGroupName(selected))}</strong>
            <span>${selected.length} parameter${selected.length === 1 ? "" : "s"}</span>
            ${groupedLabels.length > 1 ? `<span>${groupedLabels.length} grouped labels</span>` : ""}
          </div>
        `
        : `Choose one or more parameters to build a group.`;
    }
  };

  const currentFilteredParameterNames = () => {
    const strict = filteredParameterNames();
    const metricModeActive = Boolean(onlyAvg?.checked || onlyMin?.checked || onlyMax?.checked);
    const relaxed = metricModeActive && !strict.length ? filteredParameterNames({ ignoreMetricMode: true }) : [];
    return {
      strict,
      relaxed,
      metricModeActive,
      display: strict.length ? strict : relaxed,
    };
  };

  const toggleSelectedParameter = (parameterName) => {
    if (!parameterName) return;
    if (selectedParameterNames.includes(parameterName)) {
      selectedParameterNames = selectedParameterNames.filter((item) => item !== parameterName);
    } else {
      selectedParameterNames = [...selectedParameterNames, parameterName];
    }
    renderDatasetMeta();
  };

  const renderPreview = () => {
    if (!datasetDetails || !previewRoot) return;
    const needle = String(filterInput?.value || "").trim().toLowerCase();
    const rows = (datasetDetails.preview_rows || []).filter((item) => {
      const matchesGroup = activeGroup === "All" || item.group_name === activeGroup;
      const haystack = `${item.parameter_name} ${item.group_name} ${item.section} ${item.value}`.toLowerCase();
      return matchesGroup && (!needle || haystack.includes(needle));
    });
    previewRoot.innerHTML = sqlPreviewRowsMarkup(rows);
  };

  const renderDatasetMeta = () => {
    if (!datasetDetails) return;
    const allParameterNames = new Set(datasetDetails.parameter_names || []);
    selectedParameterNames = dedupeStrings(selectedParameterNames.filter((item) => allParameterNames.has(item)));
    if (datasetTitle) {
      datasetTitle.textContent = datasetDetails.selected_file === "__ALL__" ? "All draw CSVs" : (datasetDetails.selected_file || "No dataset");
    }
    if (datasetSummaryRoot) {
      datasetSummaryRoot.innerHTML = `
        <div class="metric-pill tone-info"><span>Rows</span><strong>${datasetDetails.row_count}</strong></div>
        <div class="metric-pill tone-warn"><span>Numeric</span><strong>${datasetDetails.numeric_count}</strong></div>
        <div class="metric-pill tone-info"><span>Groups</span><strong>${datasetDetails.groups.length}</strong></div>
      `;
    }
    if (groupRoot) {
      const groupButtons = [{ label: "All", value: datasetDetails.row_count }, ...(datasetDetails.groups || [])];
      groupRoot.innerHTML = groupButtons
        .map(
          (item) => `<button class="parts-filter-chip ${activeGroup === item.label ? "is-active" : ""}" type="button" data-sql-group="${item.label}">${item.label} <strong>${item.value}</strong></button>`,
        )
        .join("");
      Array.from(groupRoot.querySelectorAll("[data-sql-group]")).forEach((button) => {
        button.addEventListener("click", () => {
          activeGroup = button.dataset.sqlGroup;
          renderDatasetMeta();
          renderPreview();
        });
      });
    }
    const parameterMatches = currentFilteredParameterNames();
    const filtered = parameterMatches.strict;
    const displayFiltered = parameterMatches.display;
    if (matchScroll) {
      matchScroll.innerHTML = displayFiltered.length
        ? `
          ${filtered.length ? "" : `<div class="sql-match-empty">No parameters matched the current metric mode, so the base matches are shown below.</div>`}
          ${displayFiltered
          .map((item) => `
            <button
              class="sql-match-chip ${selectedParameterNames.includes(item) ? "is-selected" : ""}"
              type="button"
              data-sql-match-param="${escapeHtml(item)}"
            >${escapeHtml(item)}</button>
          `)
          .join("")}
        `
        : `<div class="sql-match-empty">No parameters match the current search and family filter.</div>`;
      Array.from(matchScroll.querySelectorAll("[data-sql-match-param]")).forEach((button) => {
        button.addEventListener("click", () => toggleSelectedParameter(button.dataset.sqlMatchParam || ""));
      });
    }
    renderSelectionSummary();
    renderPreview();
    renderRunSummary();
  };

  const renderConditions = () => {
    if (conditionsRoot) conditionsRoot.innerHTML = sqlConditionRowsMarkup(currentConditions);
    renderRunSummary();
  };

  const syncRuleAndLaneFields = () => {
    const op = String(operatorSelect?.value || "any");
    const needsSecondValue = op === "between";
    value2Block?.toggleAttribute("hidden", !needsSecondValue);
    if (value2Block) value2Block.style.display = needsSecondValue ? "" : "none";
    if (value2Input) value2Input.disabled = !needsSecondValue;
    ruleGrid?.classList.toggle("is-single-value", !needsSecondValue);
    if (maintenanceFiltersShell) {
      const showMaintenance = Boolean(includeMaintenance?.checked);
      maintenanceFiltersShell.toggleAttribute("hidden", !showMaintenance);
      maintenanceFiltersShell.style.display = showMaintenance ? "" : "none";
      if (!showMaintenance) {
        maintenanceFiltersShell.querySelector(".fold-section")?.removeAttribute("open");
      }
    }
    if (faultFiltersShell) {
      const showFaults = Boolean(includeFaults?.checked);
      faultFiltersShell.toggleAttribute("hidden", !showFaults);
      faultFiltersShell.style.display = showFaults ? "" : "none";
      if (!showFaults) {
        faultFiltersShell.querySelector(".fold-section")?.removeAttribute("open");
      }
    }
  };

  const liveScopeSummary = () => {
    const activeLanes = [
      includeDraws?.checked ? "Draws" : "",
      includeMaintenance?.checked ? "Maintenance" : "",
      includeFaults?.checked ? "Faults" : "",
    ].filter(Boolean);
    return {
      lanes: activeLanes.length ? activeLanes.join(" · ") : "None",
      timeScope: timeEnabled?.checked ? `${timeFrom?.value || "start"} → ${timeTo?.value || "end"}` : "Off",
      eventScope: String(eventScope?.value || "Only within matched draws window"),
      maintenanceScope: maintenanceText?.value?.trim() || maintenanceComponent?.value ? "Maintenance narrowed" : "Maintenance open",
      faultScope: faultText?.value?.trim() || faultComponent?.value || faultSeverity?.value ? "Faults narrowed" : "Faults open",
    };
  };

  const liveDraftRule = () => {
    const op = String(operatorSelect?.value || "any");
    const value1 = String(value1Input?.value || "").trim();
    const value2 = String(value2Input?.value || "").trim();
    return {
      joiner: currentConditions.length ? String(joinerSelect?.value || "AND") : "BASE",
      operatorLabel: sqlConditionOperatorLabel({ op }),
      valueLabel: op === "between"
        ? (value1 || value2 ? `${value1 || "?"} → ${value2 || "?"}` : "Set lower and upper bound")
        : value1 || (op === "any" ? "Any value" : "Set the comparison value"),
      negate: Boolean(negateToggle?.checked),
      selectedGroup: selectedParameterNames.length ? sqlConditionGroupName(selectedParameterNames) : "No parameter set yet",
    };
  };

  const renderRunDraft = () => {
    if (!runDraftRoot) return;
    const draft = liveDraftRule();
    const scope = liveScopeSummary();
    runDraftRoot.innerHTML = `
      <div class="sql-run-draft-grid">
        <div class="micro-panel blocky sql-run-draft-card">
          <strong>Parameter set</strong>
          <p>${selectedParameterNames.length ? `${selectedParameterNames.length} selected · ${escapeHtml(draft.selectedGroup)}` : `No parameters selected`}</p>
        </div>
        <div class="micro-panel blocky sql-run-draft-card">
          <strong>Draft condition</strong>
          <p>${draft.joiner} · ${draft.operatorLabel}${draft.negate ? ` · NOT` : ``} · ${escapeHtml(draft.valueLabel)}${currentConditions.length ? ` · ${currentConditions.length} stacked` : ``}</p>
        </div>
        <div class="micro-panel blocky sql-run-draft-card">
          <strong>Scope + lanes</strong>
          <p>Time ${escapeHtml(scope.timeScope)} · ${escapeHtml(scope.lanes)} · ${escapeHtml(scope.eventScope)}</p>
        </div>
      </div>
    `;
  };

  const renderRunSummary = () => {
    if (!runSummaryRoot) return;
    renderRunDraft();
    if (filterSummaryRoot) {
      filterSummaryRoot.innerHTML = sqlFilterRibbonMarkup(currentConditions);
      Array.from(filterSummaryRoot.querySelectorAll("[data-sql-filter-condition]")).forEach((button) => {
        button.addEventListener("click", () => {
          setStep("2");
          conditionsRoot?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        });
      });
    }
    const summary = lastFilterResult?.summary;
    runSummaryRoot.innerHTML = summary
      ? `
        <div class="metric-pill tone-info"><span>Draws</span><strong>${summary.matched_draws}</strong></div>
        <div class="metric-pill tone-warn"><span>Values</span><strong>${summary.matched_values}</strong></div>
        <div class="metric-pill tone-warn"><span>Maintenance</span><strong>${summary.maintenance_events}</strong></div>
        <div class="metric-pill tone-bad"><span>Faults</span><strong>${summary.fault_events}</strong></div>
        <div class="micro-panel blocky">
          <strong>Investigation read</strong>
          <p>${summary.matched_draws ? `${summary.matched_draws} matched draws in scope.` : `No draws matched yet.`} ${summary.maintenance_events ? `${summary.maintenance_events} maintenance events overlap.` : `No maintenance overlap.`} ${summary.fault_events ? `${summary.fault_events} fault events overlap.` : `No faults overlap.`}</p>
        </div>
      `
      : `
        <div class="metric-pill tone-info"><span>Params</span><strong>${selectedParameterNames.length}</strong></div>
        <div class="metric-pill tone-info"><span>Rules</span><strong>${currentConditions.length}</strong></div>
        <div class="metric-pill tone-${timeEnabled?.checked ? "warn" : "good"}"><span>Time scope</span><strong>${timeEnabled?.checked ? "On" : "Off"}</strong></div>
        <div class="metric-pill tone-info"><span>Lanes</span><strong>${[includeDraws?.checked, includeMaintenance?.checked, includeFaults?.checked].filter(Boolean).length}</strong></div>
      `;
    if (interpretationRoot) {
      interpretationRoot.innerHTML = summary
        ? sqlInterpretationMarkup(lastFilterResult)
        : ``;
    }
  };

  function sqlStrictNumericValue(raw) {
    const text = String(raw ?? "").trim();
    if (!text) return null;
    const normalized = text.replace(/,/g, "");
    if (!/^[-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?$/i.test(normalized)) {
      return null;
    }
    const numeric = Number(normalized);
    return Number.isFinite(numeric) ? numeric : null;
  }

  const analysisSourceRows = (sourceMode = analysisResourceMode) => {
    if (sourceMode === "draws") {
      return analysisScopeData.records || [];
    }
    return (lastFilterResult?.matched_values || []).map((item) => ({
      parameter_name: String(item.parameter_name || ""),
      value: String(item.value || ""),
      units: String(item.units || ""),
      value_num: sqlStrictNumericValue(item.value),
      _draw: String(item._draw || ""),
      event_ts: String(item.event_ts || ""),
      filename: String(item.filename || ""),
    }));
  };

  const syncAnalysisSourceButtons = () => {
    analysisSourceButtons.forEach((button) => {
      button.classList.toggle("is-active", button.dataset.sqlAnalysisSource === analysisResourceMode);
    });
  };

  const ensureAnalysisScopeData = async () => {
    const filenames = dedupeStrings((lastFilterResult?.matched_draws || []).map((item) => item.filename).filter(Boolean));
    const key = filenames.join("|");
    if (!filenames.length) {
      analysisScopeCacheKey = "";
      analysisScopeData = { records: [], draw_count: 0, row_count: 0 };
      return;
    }
    if (key === analysisScopeCacheKey && analysisScopeData.records.length) {
      return;
    }
    analysisScopeData = await postJson("/api/sql-lab/analysis-scope", { filenames });
    analysisScopeCacheKey = key;
  };

  const renderAnalysisDetail = async (target) => {
    if (!analysisDetailRoot) return;
    if (!target) {
      analysisDetailRoot.innerHTML = `<div class="micro-panel">Click a point or event to inspect the related draw and CSV rows here.</div>`;
      return;
    }
    if (target.type !== "series" || !target.draw) {
      const nearestDraw = (lastFilterResult?.matched_draws || [])
        .map((item) => ({
          ...item,
          diff: Math.abs(new Date(item.event_ts || 0).getTime() - new Date(target.ts || 0).getTime()),
        }))
        .sort((a, b) => a.diff - b.diff)[0];
      analysisDetailRoot.innerHTML = `
        <div class="chart-card chart-card-nested">
          <div class="chart-head">
            <span>Clicked event</span>
            <strong>${target.title || target.type}</strong>
          </div>
          <div class="metric-row compact">
            <div class="metric-pill tone-${target.type === "maintenance" ? "warn" : "bad"}"><span>Type</span><strong>${target.type}</strong></div>
            <div class="metric-pill tone-info"><span>Time</span><strong>${target.ts || "Unknown"}</strong></div>
            <div class="metric-pill tone-info"><span>Closest draw</span><strong>${nearestDraw?._draw || "None"}</strong></div>
          </div>
          <div class="micro-panel blocky">
            <strong>Correlation note</strong>
            <p>${nearestDraw ? `Closest matched draw is ${nearestDraw._draw} (${nearestDraw.filename || ""}).` : `No nearby matched draw found.`}</p>
          </div>
        </div>
      `;
      return;
    }
    const drawMeta = (lastFilterResult?.matched_draws || []).find((item) => String(item._draw || "") === String(target.draw));
    const filename = drawMeta?.filename || `${target.draw}.csv`;
    analysisDetailRoot.innerHTML = `<div class="loading-state">Loading draw ${target.draw}...</div>`;
    try {
      const detail = await getJson(`/api/sql-lab/dataset?name=${encodeURIComponent(filename)}`);
      const rows = detailExpanded ? (detail.preview_rows || []) : (detail.preview_rows || []).slice(0, 20);
      const groupedRows = rows.reduce((acc, row) => {
        const family = sqlFamilyLabel(row.parameter_name);
        if (!acc[family]) acc[family] = [];
        acc[family].push(row);
        return acc;
      }, {});
      const drawTs = new Date(target.ts || 0).getTime();
      const nearestMaintenance = (lastFilterResult?.maintenance_events || [])
        .map((item) => ({ ...item, diff: Math.abs(new Date(item.event_ts || 0).getTime() - drawTs) }))
        .sort((a, b) => a.diff - b.diff)
        .slice(0, 6);
      const nearestFaults = (lastFilterResult?.fault_events || [])
        .map((item) => ({ ...item, diff: Math.abs(new Date(item.event_ts || 0).getTime() - drawTs) }))
        .sort((a, b) => a.diff - b.diff)
        .slice(0, 6);
      const mathRows = (lastFilterResult?.matched_values || [])
        .filter((item) => String(item._draw || "") === String(target.draw))
        .map((item) => ({
          label: sqlAnalysisGroupLabel(item.parameter_name),
          raw: item.parameter_name,
          value: item.value,
          units: item.units,
        }));
      const uniqueMath = [];
      const seenMath = new Set();
      mathRows.forEach((item) => {
        const key = `${item.label}|${item.value}|${item.units}`;
        if (!seenMath.has(key)) {
          seenMath.add(key);
          uniqueMath.push(item);
        }
      });
      const tabButtons = [
        ["overview", "Overview"],
        ["csv", "CSV"],
        ["events", "Events"],
        ["math", "Math"],
      ].map(([key, label]) => `<button class="report-mode-btn sql-detail-tab ${detailTab === key ? "is-active" : ""}" type="button" data-sql-detail-tab="${key}">${label}</button>`).join("");
      const selectedPointKey = sqlAnalysisPointKey(target.label, target.draw, target.ts);
      const pointHidden = hiddenAnalysisPointKeys.includes(selectedPointKey);
      let bodyMarkup = "";
      if (detailTab === "csv") {
        bodyMarkup = `
          <div class="order-builder-actions">
            <button class="action-btn action-secondary" type="button" id="sql-detail-toggle">${detailExpanded ? "Show compact rows" : "Show full CSV rows"}</button>
          </div>
          <div class="sql-detail-groups">
            ${rows.length
              ? Object.entries(groupedRows).map(([family, familyRows]) => `
                <div class="sql-detail-group">
                  <div class="sql-detail-group-head">${family}</div>
                  <div class="micro-list">
                    ${familyRows.map((row) => `<div class="micro-row"><span>${row.parameter_name}</span><strong>${row.value || "—"}</strong></div>`).join("")}
                  </div>
                </div>
              `).join("")
              : `<div class="micro-panel">No dataset rows found for this draw.</div>`}
          </div>
        `;
      } else if (detailTab === "events") {
        bodyMarkup = `
          <div class="report-grid two-col">
            <div class="sql-detail-group">
              <div class="sql-detail-group-head">Nearest maintenance</div>
              <div class="micro-list">
                ${nearestMaintenance.length ? nearestMaintenance.map((item) => `<div class="micro-row"><span>${item.title || "Maintenance"}</span><strong>${item.event_ts || "Unknown"}</strong></div>`).join("") : `<div class="micro-panel">No nearby maintenance events.</div>`}
              </div>
            </div>
            <div class="sql-detail-group">
              <div class="sql-detail-group-head">Nearest faults</div>
              <div class="micro-list">
                ${nearestFaults.length ? nearestFaults.map((item) => `<div class="micro-row"><span>${item.title || "Fault"}</span><strong>${item.event_ts || "Unknown"}</strong></div>`).join("") : `<div class="micro-panel">No nearby fault events.</div>`}
              </div>
            </div>
          </div>
        `;
      } else if (detailTab === "math") {
        bodyMarkup = `
          <div class="micro-list">
            ${uniqueMath.length ? uniqueMath.map((item) => `<div class="micro-row"><span>${item.label}</span><strong>${item.value || "—"} ${item.units || ""}</strong></div>`).join("") : `<div class="micro-panel">No matched numeric values for this draw.</div>`}
          </div>
        `;
      } else {
        bodyMarkup = `
          <div class="metric-row compact">
            <div class="metric-pill tone-info"><span>Family</span><strong>${target.label}</strong></div>
            <div class="metric-pill tone-good"><span>Value</span><strong>${sqlFormatAnalysisValue(target)}</strong></div>
            <div class="metric-pill tone-info"><span>Time</span><strong>${target.ts || "Unknown"}</strong></div>
          <div class="metric-pill tone-warn"><span>File</span><strong>${filename}</strong></div>
        </div>
          <div class="report-grid two-col">
            <div class="sql-detail-group sql-detail-group-rich">
              <div class="sql-detail-group-head">Order + file context</div>
              <div class="micro-list">
                <div class="micro-row"><span>Draw</span><strong>${target.draw}</strong></div>
                <div class="micro-row"><span>Filename</span><strong>${filename}</strong></div>
                <div class="micro-row"><span>Rows in preview</span><strong>${detail.preview_rows?.length || 0}</strong></div>
                <div class="micro-row"><span>Reducer</span><strong>${analysisReduceMode}</strong></div>
                <div class="micro-row"><span>Plot source</span><strong>${analysisPlotMode}</strong></div>
                <div class="micro-row"><span>Browser source</span><strong>${analysisResourceMode}</strong></div>
              </div>
            </div>
            <div class="sql-detail-group sql-detail-group-rich">
              <div class="sql-detail-group-head">Closest event context</div>
              <div class="micro-list">
                <div class="micro-row"><span>Maintenance</span><strong>${nearestMaintenance[0]?.title || "None"}</strong></div>
                <div class="micro-row"><span>Fault</span><strong>${nearestFaults[0]?.title || "None"}</strong></div>
                <div class="micro-row"><span>Math values</span><strong>${uniqueMath.length}</strong></div>
                <div class="micro-row"><span>CSV families</span><strong>${Object.keys(groupedRows).length}</strong></div>
              </div>
            </div>
          </div>
        `;
      }
      analysisDetailRoot.innerHTML = `
        <div class="chart-card chart-card-nested">
          <div class="chart-head">
            <span>Clicked draw</span>
            <strong>${target.draw}</strong>
          </div>
          <div class="sql-detail-tabs">${tabButtons}</div>
          <div class="order-builder-actions">
            ${detailTab === "overview"
              ? `<button class="action-btn action-secondary" type="button" id="sql-detail-hide-point">${pointHidden ? "Point hidden in current visual" : "Hide point from current visual"}</button>`
              : ``}
            <button class="action-btn action-secondary" type="button" id="sql-detail-clear">Clear selection</button>
          </div>
          <div class="sql-detail-body">${bodyMarkup}</div>
        </div>
      `;
      Array.from(analysisDetailRoot.querySelectorAll("[data-sql-detail-tab]")).forEach((button) => {
        button.addEventListener("click", async () => {
          detailTab = button.dataset.sqlDetailTab;
          await renderAnalysisDetail(selectedAnalysisTarget);
        });
      });
      const hidePointBtn = document.getElementById("sql-detail-hide-point");
      const toggleBtn = document.getElementById("sql-detail-toggle");
      const clearBtn = document.getElementById("sql-detail-clear");
      hidePointBtn?.addEventListener("click", async () => {
        if (!pointHidden) {
          hiddenAnalysisPointKeys = dedupeStrings([...hiddenAnalysisPointKeys, selectedPointKey]);
        }
        selectedAnalysisTarget = null;
        detailExpanded = false;
        renderSqlAnalysis();
        await renderAnalysisDetail(null);
      });
      toggleBtn?.addEventListener("click", async () => {
        detailExpanded = !detailExpanded;
        await renderAnalysisDetail(selectedAnalysisTarget);
      });
      clearBtn?.addEventListener("click", async () => {
        selectedAnalysisTarget = null;
        detailExpanded = false;
        renderSqlAnalysis();
        await renderAnalysisDetail(null);
      });
    } catch (error) {
      analysisDetailRoot.innerHTML = `<div class="micro-panel">${error.message}</div>`;
    }
  };

  const sqlNumericValue = (item) => sqlStrictNumericValue(item?.value);

  const sqlCleanTextValue = (value) => String(value ?? "").replace(/\s+/g, " ").trim();

  const sqlParameterLooksCategorical = (parameterName) => {
    const lower = String(parameterName || "").trim().toLowerCase();
    if (!lower) return false;
    if (/(project|geometry|operator|priority|shape|main coating|secondary coating|preform number|mode|title|purpose|methods|observations|results)/.test(lower)) {
      return true;
    }
    if (/(diameter|tolerance|temperature|tension|speed|length|count|f2f|cut|degc|viscosity|density|\bri\b|gain|increment|hours|kg|percent|%|avg|min|max)/.test(lower)) {
      return false;
    }
    return false;
  };

  const sqlFormatAnalysisValue = (target) => {
    const raw = target?.displayValue ?? target?.value;
    const numeric = Number(raw);
    if (!target?.isText && Number.isFinite(numeric)) {
      return Math.abs(numeric) >= 1000 ? numeric.toFixed(0) : numeric.toFixed(2);
    }
    return String(raw || "—");
  };

  const sqlCategoricalValue = (values) => {
    const counts = new Map();
    values.forEach((value) => {
      counts.set(value, (counts.get(value) || 0) + 1);
    });
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1] || values.indexOf(a[0]) - values.indexOf(b[0]))[0]?.[0] || values[0] || "";
  };

  const buildSqlAnalysisModel = ({
    labelsOverride = null,
    limitDefault = true,
    sourceMode = analysisPlotMode,
    applyActiveSelection = true,
    applyHiddenFilter = true,
  } = {}) => {
    const values = analysisSourceRows(sourceMode);
    if (!values.length) {
      return { labelsMeta: [], numericSeries: [], textSeries: [] };
    }
    const grouped = new Map();
    values.forEach((item) => {
      const label = sqlAnalysisGroupLabel(item.parameter_name);
      if (!label) return;
      if (!grouped.has(label)) grouped.set(label, []);
      grouped.get(label).push(item);
    });
    let labels = Array.from(grouped.keys());
    if (Array.isArray(labelsOverride)) {
      labels = labels.filter((label) => labelsOverride.includes(label));
    } else if (applyActiveSelection && activeAnalysisParams.length) {
      labels = labels.filter((label) => activeAnalysisParams.includes(label));
    }
    if (applyHiddenFilter) {
      labels = labels.filter((label) => !hiddenAnalysisParams.includes(label));
    }
    if (!labelsOverride && !(applyActiveSelection && activeAnalysisParams.length) && limitDefault) {
      labels = labels.slice(0, 4);
    }
    const labelsMeta = [];
    const numericSeries = [];
    const textSeries = [];
    labels.forEach((label) => {
      const rows = grouped.get(label) || [];
      const parameterLooksCategorical = sqlParameterLooksCategorical(label);
      const byDraw = new Map();
      rows.forEach((item) => {
        const draw = String(item._draw || item.filename || item.event_ts || "").trim();
        if (!draw) return;
        if (!byDraw.has(draw)) byDraw.set(draw, []);
        byDraw.get(draw).push(item);
      });
      const numericPoints = [];
      const textPoints = [];
      Array.from(byDraw.entries()).forEach(([draw, drawRows]) => {
        const ts = String(drawRows.find((row) => String(row.event_ts || "").trim())?.event_ts || "");
        const filename = String(drawRows.find((row) => String(row.filename || "").trim())?.filename || "");
        const textValues = drawRows.map((row) => sqlCleanTextValue(row.value)).filter(Boolean);
        const hasCategoricalText = textValues.some((value) => !Number.isFinite(Number(value)));
      const numericValues = drawRows.map(sqlNumericValue).filter((value) => Number.isFinite(value));
      if (!parameterLooksCategorical && !hasCategoricalText && numericValues.length) {
          const pointKey = sqlAnalysisPointKey(label, draw, ts);
          if (hiddenAnalysisPointKeys.includes(pointKey)) return;
          numericPoints.push({
            draw,
            ts,
            value: aggregateValues(numericValues, analysisReduceMode),
            filename,
          });
          return;
        }
        if (!textValues.length) {
          if (!parameterLooksCategorical) return;
          const pointKey = sqlAnalysisPointKey(label, draw, ts);
          if (hiddenAnalysisPointKeys.includes(pointKey)) return;
          textPoints.push({
            draw,
            ts,
            value: "Unspecified",
            displayValue: "Unspecified",
            filename,
          });
          return;
        }
        const displayValue = sqlCategoricalValue(textValues);
        const pointKey = sqlAnalysisPointKey(label, draw, ts);
        if (hiddenAnalysisPointKeys.includes(pointKey)) return;
        textPoints.push({
          draw,
          ts,
          value: displayValue,
          displayValue,
          filename,
        });
      });
      numericPoints.sort((a, b) => String(a.ts).localeCompare(String(b.ts)));
      textPoints.sort((a, b) => String(a.ts).localeCompare(String(b.ts)));
      if (numericPoints.length) {
        labelsMeta.push({ label, kind: "numeric", count: numericPoints.length });
        numericSeries.push({ label, points: numericPoints });
      } else if (textPoints.length) {
        labelsMeta.push({ label, kind: "text", count: textPoints.length });
        textSeries.push({
          label,
          points: textPoints,
          categories: dedupeStrings(textPoints.map((point) => point.displayValue || point.value)),
        });
      }
    });
    return { labelsMeta, numericSeries, textSeries };
  };

  const renderSqlMathLab = (allSeries, selectedTargetForMath = selectedAnalysisTarget) => {
    const labels = allSeries.map((item) => item.label);
    if (mathSourceA) {
      if (!mathConfig.sourceA || !labels.includes(mathConfig.sourceA)) {
        mathConfig.sourceA = labels[0] || "";
      }
      mathSourceA.innerHTML = labels.length
        ? labels.map((label) => `<option value="${label}" ${label === mathConfig.sourceA ? "selected" : ""}>${label}</option>`).join("")
        : `<option value="">No grouped traces</option>`;
    }
    if (mathSourceB) {
      if (!mathConfig.sourceB || !labels.includes(mathConfig.sourceB)) {
        mathConfig.sourceB = labels[1] || labels[0] || "";
      }
      mathSourceB.innerHTML = [`<option value="">None</option>`, ...labels.map((label) => `<option value="${label}" ${label === mathConfig.sourceB ? "selected" : ""}>${label}</option>`)].join("");
    }
    mathConfig.reducer = analysisReduceMode;
    if (mathOperation) mathOperation.value = mathConfig.operation;
    if (mathExpression) mathExpression.value = mathConfig.expression || "A";

    const currentMathPreview = buildSqlMathSeries(allSeries, {
      ...mathConfig,
      hiddenPointKeys: hiddenAnalysisPointKeys,
    });
    const recipeConfigs = [
      { ...mathConfig, recipeKey: "__current__", recipeName: "Current recipe" },
      ...savedMathRecipes,
    ];
    const mathSeriesList = recipeConfigs
      .map((config, index) => ({
        ...buildSqlMathSeries(allSeries, {
          ...config,
          hiddenPointKeys: hiddenAnalysisPointKeys,
        }),
        recipeKey: config.recipeKey || `saved-${index}`,
        recipeName: config.recipeName || sqlMathSeriesLabel(config.operation, config.expression),
      }))
      .filter((item) => item.points.length);
    currentMathTargets = drawSqlMathCanvas(mathSeriesList, mathCanvas, {
      maintenance: lastFilterResult?.maintenance_events || [],
      faults: lastFilterResult?.fault_events || [],
    }, selectedTargetForMath);

    if (mathRecipesRoot) {
      mathRecipesRoot.innerHTML = savedMathRecipes.length
        ? `
          <div class="sql-subsection-head sql-math-recipes-head">
            <span>Saved recipes</span>
            <strong>Keep a few derived comparisons live on the same canvas</strong>
          </div>
          <div class="token-list">
            ${savedMathRecipes.map((recipe) => `
              <button class="sql-filter-ribbon-chip sql-condition-tone-violet" type="button" data-sql-math-recipe="${recipe.recipeKey}">
                <span>${recipe.recipeName}</span>
                <strong>${recipe.sourceA}${recipe.sourceB ? ` · ${recipe.sourceB}` : ""}</strong>
                <em>${recipe.operation === "custom_ab" ? `${escapeHtml(recipe.expression || "A")} · ${recipe.reducer || "avg"}` : `${sqlMathOperationLabel(recipe.operation)} · ${recipe.reducer || "avg"}`}</em>
              </button>
              <button class="parts-filter-chip" type="button" data-sql-math-remove="${recipe.recipeKey}">Remove</button>
            `).join("")}
          </div>
        `
        : "";
      Array.from(mathRecipesRoot.querySelectorAll("[data-sql-math-recipe]")).forEach((button) => {
        button.addEventListener("click", () => {
          const recipe = savedMathRecipes.find((item) => item.recipeKey === button.dataset.sqlMathRecipe);
          if (!recipe) return;
          mathConfig = {
            ...recipe,
            expression: String(recipe.expression || "A").trim() || "A",
            window: SQL_MATH_FIXED_WINDOW,
          };
          hoveredMathKey = "";
          renderSqlAnalysis();
        });
      });
      Array.from(mathRecipesRoot.querySelectorAll("[data-sql-math-remove]")).forEach((button) => {
        button.addEventListener("click", () => {
          savedMathRecipes = savedMathRecipes.filter((item) => item.recipeKey !== button.dataset.sqlMathRemove);
          renderSqlAnalysis();
        });
      });
    }

    if (mathSummaryRoot) {
      if (!mathSeriesList.length) {
        mathSummaryRoot.innerHTML = `<div class="micro-panel">Pick source traces from the grouped analysis to generate a derived math curve.</div>`;
      } else {
        mathSummaryRoot.innerHTML = mathSeriesList.slice(0, 8).map((mathSeries, index) => {
          const values = mathSeries.points.map((item) => item.value);
          const latest = values.at(-1);
          const min = Math.min(...values);
          const max = Math.max(...values);
          const avg = values.reduce((sum, value) => sum + value, 0) / Math.max(1, values.length);
          const tone = ["violet", "good", "info", "warn"][index % 4];
          return `
            <div class="metric-pill tone-${tone}">
              <span>${mathSeries.recipeName || mathSeries.label}</span>
              <strong>${latest.toFixed(2)}</strong>
              <em>avg ${avg.toFixed(2)} · ${min.toFixed(2)} .. ${max.toFixed(2)}</em>
            </div>
          `;
        }).join("");
      }
    }
    if (mathHoverRoot && !hoveredMathKey) {
      const leadMath = mathSeriesList[0];
      mathHoverRoot.innerHTML = currentMathPreview?.error
        ? `<strong>Formula issue</strong> · ${escapeHtml(currentMathPreview.error)} · Try examples like <code>np.sqrt(np.abs(A-B))</code> or <code>np.power(A,2)</code>.`
        : leadMath
        ? `<strong>${leadMath.label}</strong> · ${leadMath.sourceA}${leadMath.sourceB ? ` with ${leadMath.sourceB}` : ""} · ${leadMath.points.length} aligned draw points${mathSeriesList.length > 1 ? ` · +${mathSeriesList.length - 1} more recipes live` : ""}`
        : `Build a derived trace to compare families, detect drift, and inspect the same draw through a math lens.`;
    }
  };

  const renderSqlAnalysis = () => {
    syncAnalysisSourceButtons();
    if (restoreHiddenPointsButton) {
      restoreHiddenPointsButton.disabled = !hiddenAnalysisPointKeys.length;
      restoreHiddenPointsButton.textContent = hiddenAnalysisPointKeys.length
        ? `Restore hidden outliers (${hiddenAnalysisPointKeys.length})`
        : "Restore hidden outliers";
    }
    const analysisModel = buildSqlAnalysisModel({ sourceMode: analysisPlotMode });
    const fullPlotModel = buildSqlAnalysisModel({ limitDefault: false, sourceMode: analysisPlotMode });
    const browserAnalysisModel = buildSqlAnalysisModel({
      limitDefault: false,
      sourceMode: analysisResourceMode,
      applyActiveSelection: false,
      applyHiddenFilter: false,
    });
    const seriesList = analysisModel.numericSeries;
    const allSeries = fullPlotModel.numericSeries;
    if (analysisSeriesRoot) {
      const allLabels = browserAnalysisModel.labelsMeta;
      const plottedLabels = new Set(
        activeAnalysisParams.length
          ? activeAnalysisParams
          : fullPlotModel.labelsMeta.map((item) => item.label),
      );
      const analysisQuery = String(analysisSearchInput?.value || "").trim().toLowerCase();
      const searchRequired = analysisResourceMode === "draws" && allLabels.length > 24 && !analysisQuery;
      let visibleLabels = searchRequired
        ? []
        : allLabels.filter((meta) => {
          if (!analysisQuery) return true;
          const haystack = `${meta.label} ${meta.kind || ""}`.toLowerCase();
          return haystack.includes(analysisQuery);
        });
      if (!searchRequired && analysisResourceMode === "draws" && plottedLabels.size) {
        const pinnedLabels = allLabels.filter((meta) => plottedLabels.has(meta.label));
        const seenLabels = new Set();
        visibleLabels = [...pinnedLabels, ...visibleLabels].filter((meta) => {
          if (seenLabels.has(meta.label)) return false;
          seenLabels.add(meta.label);
          return true;
        });
      }
      if (analysisSearchNote) {
        analysisSearchNote.innerHTML = searchRequired
          ? `<span class="sql-analysis-note-chip">${allLabels.length} params</span><span>Type to browse matched-draw traces.</span>`
          : visibleLabels.length
            ? `
              <span class="sql-analysis-note-chip">${visibleLabels.length} / ${allLabels.length}</span>
              <span>matched parameters${analysisQuery ? ` for "${escapeHtml(analysisQuery)}"` : " ready to add"}</span>
              ${hiddenAnalysisPointKeys.length ? `<span class="sql-analysis-note-chip">Hidden points ${hiddenAnalysisPointKeys.length}</span>` : ``}
            `
            : `<span class="sql-analysis-note-chip is-empty">0 / ${allLabels.length}</span><span>No grouped parameters match "${escapeHtml(analysisQuery)}".</span>${hiddenAnalysisPointKeys.length ? `<span class="sql-analysis-note-chip">Hidden points ${hiddenAnalysisPointKeys.length}</span>` : ``}`;
      }
      analysisSeriesRoot.innerHTML = searchRequired
        ? `<div class="micro-panel sql-analysis-search-empty">Search the matched-draw parameter board to browse grouped traces. The current plot can still stay active while the list stays collapsed.</div>`
        : visibleLabels.length
          ? `
          <div class="sql-analysis-series-list">
            ${visibleLabels.map((meta) => {
          const label = meta.label;
          const isActive = activeAnalysisParams.includes(label) || (!activeAnalysisParams.length && plottedLabels.has(label));
          const isHidden = hiddenAnalysisParams.includes(label);
          return `
            <div class="sql-analysis-series-row ${isActive ? "is-active" : ""} ${isHidden ? "is-hidden" : ""}">
              <button class="sql-analysis-series-chip ${isActive ? "is-active" : ""}" type="button" data-sql-analysis-param="${label}">
                ${label}
              </button>
              <div class="sql-analysis-series-meta">
                <span>${meta.count || 0} draws</span>
                <em>${meta.kind === "text" ? "text lane" : "numeric trace"}</em>
              </div>
              <div class="sql-trace-mini-actions">
                <button class="sql-trace-mini" type="button" data-sql-analysis-focus="${label}">Focus</button>
                <button class="sql-trace-mini" type="button" data-sql-analysis-toggle="${label}">${isHidden ? "Show" : "Hide"}</button>
              </div>
            </div>
          `;
        }).join("")}
          </div>
        `
          : `<div class="micro-panel">No matched parameters are ready to plot yet.</div>`;
      Array.from(analysisSeriesRoot.querySelectorAll("[data-sql-analysis-param]")).forEach((button) => {
        button.addEventListener("click", () => {
          analysisPlotMode = analysisResourceMode;
          const label = button.dataset.sqlAnalysisParam;
          const seededActiveLabels = activeAnalysisParams.length
            ? [...activeAnalysisParams]
            : [...plottedLabels];
          if (activeAnalysisParams.includes(label)) {
            activeAnalysisParams = activeAnalysisParams.filter((item) => item !== label);
          } else if (!activeAnalysisParams.length && plottedLabels.has(label)) {
            activeAnalysisParams = seededActiveLabels.filter((item) => item !== label);
          } else {
            activeAnalysisParams = dedupeStrings([...seededActiveLabels, label]);
          }
          renderSqlAnalysis();
        });
      });
      Array.from(analysisSeriesRoot.querySelectorAll("[data-sql-analysis-focus]")).forEach((button) => {
        button.addEventListener("click", () => {
          analysisPlotMode = analysisResourceMode;
          activeAnalysisParams = [button.dataset.sqlAnalysisFocus];
          hiddenAnalysisParams = hiddenAnalysisParams.filter((item) => item !== button.dataset.sqlAnalysisFocus);
          renderSqlAnalysis();
        });
      });
      Array.from(analysisSeriesRoot.querySelectorAll("[data-sql-analysis-toggle]")).forEach((button) => {
        button.addEventListener("click", () => {
          analysisPlotMode = analysisResourceMode;
          const label = button.dataset.sqlAnalysisToggle;
          if (hiddenAnalysisParams.includes(label)) {
            hiddenAnalysisParams = hiddenAnalysisParams.filter((item) => item !== label);
          } else {
            hiddenAnalysisParams = [...hiddenAnalysisParams, label];
            activeAnalysisParams = activeAnalysisParams.filter((item) => item !== label);
          }
          renderSqlAnalysis();
        });
      });
    }

    lastAnalysisCanvasModel = analysisModel;
    lastAnalysisCanvasOverlays = {
      maintenance: lastFilterResult?.maintenance_events || [],
      faults: lastFilterResult?.fault_events || [],
    };
    currentAnalysisTargets = drawSqlAnalysisCanvas(
      lastAnalysisCanvasModel,
      analysisCanvas,
      lastAnalysisCanvasOverlays,
      selectedAnalysisTarget,
    );
    scheduleSqlAnalysisCanvasRedraw();

    if (analysisMathRoot) {
      analysisMathRoot.innerHTML = seriesList.length
        ? seriesList.map((series, index) => {
          const values = series.points.map((p) => p.value);
          const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
          const min = Math.min(...values);
          const max = Math.max(...values);
          const tone = ["info", "good", "warn", "bad"][index % 4];
          return `
            <div class="metric-pill tone-${tone}">
              <span>${series.label}</span>
              <strong>${avg.toFixed(2)}</strong>
              <em>min ${min.toFixed(2)} · max ${max.toFixed(2)}</em>
            </div>
          `;
        }).join("")
        : fullPlotModel.textSeries.length
          ? `<div class="micro-panel">Categorical lanes are active. Add a numeric parameter if you want quick math cards too.</div>`
          : `<div class="micro-panel">Run a filter with matched results to unlock the plot and quick math read.</div>`;
    }
    renderSqlMathLab(allSeries);
  };

  const loadDataset = async (datasetName) => {
    if (!datasetName) return;
    previewRoot.innerHTML = `<div class="loading-state">Loading ${datasetName}...</div>`;
    datasetDetails = await getJson(`/api/sql-lab/dataset?name=${encodeURIComponent(datasetName)}`);
    activeGroup = "All";
    selectedParameterNames = [];
    renderDatasetMeta();
  };

  datasetSelect?.addEventListener("change", () => loadDataset(datasetSelect.value));
  filterInput?.addEventListener("input", renderDatasetMeta);
  familyFilter?.addEventListener("change", renderDatasetMeta);
  onlyAvg?.addEventListener("change", renderDatasetMeta);
  onlyMin?.addEventListener("change", renderDatasetMeta);
  onlyMax?.addEventListener("change", renderDatasetMeta);
  [
    operatorSelect,
    value1Input,
    value2Input,
    joinerSelect,
    negateToggle,
    timeEnabled,
    timeFrom,
    timeTo,
    includeDraws,
    includeMaintenance,
    includeFaults,
    eventScope,
    maintenanceText,
    maintenanceComponent,
    faultText,
    faultComponent,
    faultSeverity,
  ].forEach((control) => {
    if (!control) return;
    const eventName = control.tagName === "SELECT" ? "change" : "input";
    control.addEventListener(eventName, renderRunSummary);
    if (eventName === "input") {
      control.addEventListener("change", renderRunSummary);
    }
  });
  operatorSelect?.addEventListener("change", syncRuleAndLaneFields);
  includeMaintenance?.addEventListener("change", syncRuleAndLaneFields);
  includeFaults?.addEventListener("change", syncRuleAndLaneFields);
  useAllFiltered?.addEventListener("click", () => {
    selectedParameterNames = dedupeStrings([...selectedParameterNames, ...currentFilteredParameterNames().display]);
    renderDatasetMeta();
  });
  clearSelection?.addEventListener("click", () => {
    selectedParameterNames = [];
    renderDatasetMeta();
  });

  plotAllMatchedButton?.addEventListener("click", () => {
    analysisPlotMode = analysisResourceMode;
    const allLabels = Array.from(new Set(analysisSourceRows(analysisPlotMode)
      .map((item) => sqlAnalysisGroupLabel(item.parameter_name))
      .filter(Boolean)));
    hiddenAnalysisParams = [];
    activeAnalysisParams = allLabels;
    renderSqlAnalysis();
  });

  plotClearButton?.addEventListener("click", () => {
    activeAnalysisParams = [];
    hiddenAnalysisParams = [];
    renderSqlAnalysis();
  });

  restoreHiddenPointsButton?.addEventListener("click", async () => {
    hiddenAnalysisPointKeys = [];
    if (selectedAnalysisTarget) {
      await renderAnalysisDetail(selectedAnalysisTarget);
    }
    renderSqlAnalysis();
  });

  analysisSourceButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      analysisResourceMode = button.dataset.sqlAnalysisSource || "filter";
      if (analysisResourceMode === "draws") {
        await ensureAnalysisScopeData();
      }
      renderSqlAnalysis();
    });
  });

  analysisReducer?.addEventListener("change", () => {
    analysisReduceMode = analysisReducer.value || "avg";
    renderSqlAnalysis();
  });
  analysisSearchInput?.addEventListener("input", () => {
    renderSqlAnalysis();
  });

  if (analysisCanvas?.parentElement && window.ResizeObserver) {
    const analysisResizeObserver = new ResizeObserver(() => {
      scheduleSqlAnalysisCanvasRedraw();
    });
    analysisResizeObserver.observe(analysisCanvas.parentElement);
  } else {
    window.addEventListener("resize", scheduleSqlAnalysisCanvasRedraw);
  }

  const updateMathConfig = () => {
    const nextOperation = String(mathOperation?.value || "identity");
    const nextExpression = String(mathExpression?.value || "A").trim() || "A";
    mathConfig = {
      sourceA: String(mathSourceA?.value || ""),
      sourceB: String(mathSourceB?.value || ""),
      operation: nextOperation,
      expression: nextExpression,
      window: SQL_MATH_FIXED_WINDOW,
      reducer: analysisReduceMode,
    };
    hoveredMathKey = "";
    renderSqlAnalysis();
  };

  mathSourceA?.addEventListener("change", updateMathConfig);
  mathSourceB?.addEventListener("change", updateMathConfig);
  mathOperation?.addEventListener("change", updateMathConfig);
  mathExpression?.addEventListener("input", () => {
    if (mathOperation) mathOperation.value = "custom_ab";
    updateMathConfig();
  });
  mathExpression?.addEventListener("change", () => {
    if (mathOperation) mathOperation.value = "custom_ab";
    updateMathConfig();
  });
  mathPresetButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (mathOperation) mathOperation.value = button.dataset.sqlMathPreset;
      updateMathConfig();
    });
  });
  mathExpressionExamples.forEach((button) => {
    button.addEventListener("click", () => {
      const example = String(button.dataset.sqlMathExpressionExample || "A").trim() || "A";
      if (mathExpression) mathExpression.value = example;
      if (mathOperation) mathOperation.value = "custom_ab";
      updateMathConfig();
    });
  });
  mathSaveRecipeButton?.addEventListener("click", () => {
    if (!mathConfig.sourceA) return;
    const expression = String(mathConfig.expression || "A").trim() || "A";
    const recipe = {
      ...mathConfig,
      expression,
      window: SQL_MATH_FIXED_WINDOW,
      recipeKey: sqlMathRecipeKey(mathConfig),
      recipeName: `${sqlMathSeriesLabel(mathConfig.operation, expression)} · ${mathConfig.sourceA}${mathConfig.sourceB ? ` / ${mathConfig.sourceB}` : ""}`,
    };
    savedMathRecipes = [recipe, ...savedMathRecipes.filter((item) => item.recipeKey !== recipe.recipeKey)].slice(0, 3);
    renderSqlAnalysis();
  });
  mathClearRecipesButton?.addEventListener("click", () => {
    savedMathRecipes = [];
    renderSqlAnalysis();
  });

  const findSqlCanvasTarget = (event, canvas, targets, mode = "hover") => {
    if (!canvas || !targets.length) return null;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    let best = null;
    let bestDist = Infinity;
    targets.forEach((target) => {
      const dx = target.x - x;
      const dy = target.y - y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist <= target.radius && dist < bestDist) {
        best = target;
        bestDist = dist;
      }
    });
    if (best) return best;

    const uniqueXs = Array.from(new Set(
      targets
        .map((target) => Number(target.x))
        .filter((value) => Number.isFinite(value)),
    )).sort((a, b) => a - b);
    const spacings = [];
    for (let index = 1; index < uniqueXs.length; index += 1) {
      const gap = uniqueXs[index] - uniqueXs[index - 1];
      if (gap > 0.5) spacings.push(gap);
    }
    const medianSpacing = spacings.length
      ? spacings.sort((a, b) => a - b)[Math.floor(spacings.length / 2)]
      : 18;
    const xBandThreshold = Math.min(34, Math.max(14, medianSpacing * 0.7));

    let xBandMatch = null;
    let bestXDist = Infinity;
    targets.forEach((target) => {
      const xDist = Math.abs(target.x - x);
      if (xDist > xBandThreshold) return;
      const yDist = Math.abs(target.y - y);
      const score = xDist * 2 + yDist;
      if (score < bestXDist) {
        xBandMatch = target;
        bestXDist = score;
      }
    });
    if (xBandMatch) return xBandMatch;
    if (mode !== "click") return null;

    const xOnlyThreshold = Math.min(72, Math.max(20, medianSpacing * 1.8));
    let xOnlyMatch = null;
    let xOnlyScore = Infinity;
    targets.forEach((target) => {
      const xDist = Math.abs(target.x - x);
      if (xDist > xOnlyThreshold) return;
      const yDist = Math.abs(target.y - y);
      const score = xDist * 3 + yDist * 0.25;
      if (score < xOnlyScore) {
        xOnlyMatch = target;
        xOnlyScore = score;
      }
    });
    if (xOnlyMatch) return xOnlyMatch;

    if (mode === "click") {
      let nearestByX = null;
      let nearestByXDist = Infinity;
      targets.forEach((target) => {
        const xDist = Math.abs(target.x - x);
        if (xDist < nearestByXDist) {
          nearestByX = target;
          nearestByXDist = xDist;
        }
      });
      if (nearestByX) return nearestByX;
    }

    let nearest = null;
    let nearestScore = Infinity;
    targets.forEach((target) => {
      const xDist = Math.abs(target.x - x);
      const yDist = Math.abs(target.y - y);
      const score = xDist * 4 + yDist;
      if (score < nearestScore) {
        nearest = target;
        nearestScore = score;
      }
    });
    return nearestScore <= 96 ? nearest : null;
  };

  const findAnalysisTarget = (event, mode = "hover") => findSqlCanvasTarget(event, analysisCanvas, currentAnalysisTargets, mode);

  let lastAnalysisSelectionStamp = 0;
  let lastAnalysisSelectionSignature = "";
  let lastMathSelectionStamp = 0;
  let lastMathSelectionSignature = "";

  const shouldSkipSqlSelection = (kind, event, stampRef, signatureRef) => {
    const x = Math.round(Number(event?.clientX || 0));
    const y = Math.round(Number(event?.clientY || 0));
    const signature = `${kind}|${x}|${y}`;
    const now = Date.now();
    const previousStamp = kind === "analysis" ? lastAnalysisSelectionStamp : lastMathSelectionStamp;
    const previousSignature = kind === "analysis" ? lastAnalysisSelectionSignature : lastMathSelectionSignature;
    const isDuplicate = previousSignature === signature && (now - previousStamp) < 260;
    if (kind === "analysis") {
      lastAnalysisSelectionStamp = now;
      lastAnalysisSelectionSignature = signature;
    } else {
      lastMathSelectionStamp = now;
      lastMathSelectionSignature = signature;
    }
    return isDuplicate;
  };

  const positionSqlTooltip = (tooltip, shellRect, desiredLeft, desiredTop) => {
    if (!tooltip) return;
    tooltip.style.left = "0px";
    tooltip.style.top = "0px";
    tooltip.classList.add("is-visible");
    const width = tooltip.offsetWidth || 240;
    const height = tooltip.offsetHeight || 88;
    const padding = 10;
    const clampedLeft = Math.min(
      Math.max(padding, desiredLeft),
      Math.max(padding, shellRect.width - width - padding),
    );
    const clampedTop = Math.min(
      Math.max(padding, desiredTop),
      Math.max(padding, shellRect.height - height - padding),
    );
    tooltip.style.left = `${clampedLeft}px`;
    tooltip.style.top = `${clampedTop}px`;
  };

  analysisCanvas?.addEventListener("mousemove", (event) => {
    const target = findAnalysisTarget(event);
    if (!analysisHoverRoot) return;
    if (!target) {
      hoveredAnalysisKey = "";
      hoveredAnalysisTarget = null;
      analysisHoverRoot.innerHTML = `Hover a point to inspect the draw, parameter, and value.`;
      if (analysisTooltip) {
        analysisTooltip.classList.remove("is-visible");
      }
      return;
    }
    hoveredAnalysisTarget = target;
    const targetKey = target.type === "series"
      ? `${target.type}|${target.draw}|${target.label}|${target.ts}`
      : `${target.type}|${target.title}|${target.ts}`;
    if (targetKey !== hoveredAnalysisKey) {
      hoveredAnalysisKey = targetKey;
      analysisHoverRoot.innerHTML = target.type === "series"
        ? `<strong>${target.draw}</strong> · ${target.label} · <strong>${sqlFormatAnalysisValue(target)}</strong> · ${target.ts || "Unknown time"}`
        : `<strong>${target.type === "maintenance" ? "Maintenance" : "Fault"}</strong> · ${target.title || "Event"} · ${target.ts || "Unknown time"}`;
    }
    if (analysisTooltip && analysisCanvas) {
      const drawMeta = target.type === "series"
        ? (lastFilterResult?.matched_draws || []).find((item) => String(item._draw || "") === String(target.draw || ""))
        : null;
      const shellRect = analysisCanvas.parentElement?.getBoundingClientRect() || analysisCanvas.getBoundingClientRect();
      analysisTooltip.innerHTML = target.type === "series"
        ? `<strong>${target.draw}</strong><span>${target.label}</span><em>${sqlFormatAnalysisValue(target)} · ${target.ts || "Unknown time"} · ${drawMeta?.filename || "matched draw"}</em>`
        : `<strong>${target.type === "maintenance" ? "Maintenance" : "Fault"}</strong><span>${target.title || "Event"}</span><em>${target.ts || "Unknown time"} · event lane</em>`;
      positionSqlTooltip(
        analysisTooltip,
        shellRect,
        event.clientX - shellRect.left + 14,
        event.clientY - shellRect.top - 12,
      );
    }
  });

  analysisCanvas?.addEventListener("mouseleave", () => {
    if (analysisHoverRoot) {
      hoveredAnalysisKey = "";
      hoveredAnalysisTarget = null;
      analysisHoverRoot.innerHTML = `Hover a point to inspect the draw, parameter, and value.`;
    }
    if (analysisTooltip) {
      analysisTooltip.classList.remove("is-visible");
    }
  });

  const handleAnalysisCanvasSelection = async (event) => {
    const target = findAnalysisTarget(event, "click") || hoveredAnalysisTarget;
    if (!target) {
      if (event?.type === "pointerup") return;
      selectedAnalysisTarget = null;
      detailExpanded = false;
      detailTab = "overview";
      await renderAnalysisDetail(null);
      return;
    }
    if (shouldSkipSqlSelection("analysis", event)) return;
    selectedAnalysisTarget = target;
    detailExpanded = false;
    detailTab = "overview";
    revealSqlResultsStep({ openAnalysisStudio: true });
    renderSqlAnalysis();
    await renderAnalysisDetail(target);
  };

  analysisCanvas?.addEventListener("pointerup", handleAnalysisCanvasSelection);
  analysisCanvas?.addEventListener("click", handleAnalysisCanvasSelection);

  const findMathTarget = (event, mode = "hover") => findSqlCanvasTarget(event, mathCanvas, currentMathTargets, mode);

  mathCanvas?.addEventListener("mousemove", (event) => {
    const target = findMathTarget(event);
    if (!mathHoverRoot) return;
    if (!target) {
      hoveredMathKey = "";
      hoveredMathTarget = null;
      mathHoverRoot.innerHTML = `Build a derived trace to compare families, detect drift, and inspect the same draw through a math lens.`;
      mathTooltip?.classList.remove("is-visible");
      return;
    }
    hoveredMathTarget = target;
    const targetKey = `${target.draw}|${target.label}|${target.ts}`;
    if (targetKey !== hoveredMathKey) {
      hoveredMathKey = targetKey;
      mathHoverRoot.innerHTML = `<strong>${target.draw}</strong> · ${target.label} · <strong>${Number(target.value).toFixed(2)}</strong> · ${target.ts || "Unknown time"}`;
    }
    if (mathTooltip && mathCanvas) {
      const shellRect = mathCanvas.parentElement?.getBoundingClientRect() || mathCanvas.getBoundingClientRect();
      mathTooltip.innerHTML = `<strong>${target.draw}</strong><span>${target.label}</span><em>${Number(target.value).toFixed(2)} · ${target.ts || "Unknown time"} · derived signal</em>`;
      positionSqlTooltip(
        mathTooltip,
        shellRect,
        event.clientX - shellRect.left + 14,
        event.clientY - shellRect.top - 12,
      );
    }
  });

  mathCanvas?.addEventListener("mouseleave", () => {
    hoveredMathKey = "";
    hoveredMathTarget = null;
    if (mathHoverRoot) {
      mathHoverRoot.innerHTML = `Build a derived trace to compare families, detect drift, and inspect the same draw through a math lens.`;
    }
    mathTooltip?.classList.remove("is-visible");
  });

  const handleMathCanvasSelection = async (event) => {
    const target = findMathTarget(event, "click") || hoveredMathTarget;
    if (!target) {
      if (event?.type === "pointerup") return;
      selectedAnalysisTarget = null;
      detailExpanded = false;
      detailTab = "overview";
      await renderAnalysisDetail(null);
      return;
    }
    if (shouldSkipSqlSelection("math", event)) return;
    selectedAnalysisTarget = target;
    detailExpanded = false;
    detailTab = "overview";
    revealSqlResultsStep({ openAnalysisStudio: true });
    renderSqlAnalysis();
    await renderAnalysisDetail(target ? { ...target, type: "series" } : null);
  };

  mathCanvas?.addEventListener("pointerup", handleMathCanvasSelection);
  mathCanvas?.addEventListener("click", handleMathCanvasSelection);

  stepButtons.forEach((button) => {
    button.addEventListener("click", () => setStep(button.dataset.sqlStep));
  });

  syncRuleAndLaneFields();

  templateButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const template = (sqlData.query_templates || []).find((item) => item.key === button.dataset.sqlTemplate);
      if (template && queryInput) {
        queryInput.value = template.sql;
      }
    });
  });

  addGroupCondition?.addEventListener("click", () => {
    const params = [...selectedParameterNames];
    const op = String(operatorSelect?.value || "any");
    const value1 = String(value1Input?.value || "");
    const value2 = String(value2Input?.value || "");
    const groupLogic = "ANY (OR)";
    const groupName = sqlConditionGroupName(params);
    if (!params.length) {
      if (filterSummaryRoot) filterSummaryRoot.innerHTML = `<div class="micro-panel">Select at least one parameter first.</div>`;
      return;
    }
    if (!["any"].includes(op) && !value1.trim()) {
      if (filterSummaryRoot) filterSummaryRoot.innerHTML = `<div class="micro-panel">Set the condition value before adding the rule.</div>`;
      return;
    }
    if (op === "between" && !value2.trim()) {
      if (filterSummaryRoot) filterSummaryRoot.innerHTML = `<div class="micro-panel">Set the second value for the between rule.</div>`;
      return;
    }
    currentConditions.push({
      params,
      op,
      v1: value1,
      v2: value2,
      negate: Boolean(negateToggle?.checked),
      joiner: currentConditions.length ? String(joinerSelect?.value || "AND") : "BASE",
      groupLogic,
      groupName,
      human: `${groupLogic} · ${params.length} parameter${params.length === 1 ? "" : "s"} · ${op}${value1 ? ` ${value1}` : ""}${op === "between" && value2 ? ` .. ${value2}` : ""}${negateToggle?.checked ? " · NOT" : ""}`,
    });
    selectedParameterNames = [];
    renderDatasetMeta();
    renderConditions();
    setStep("2");
  });

  removeLastCondition?.addEventListener("click", () => {
    currentConditions.pop();
    renderConditions();
  });

  clearConditions?.addEventListener("click", () => {
    currentConditions = [];
    renderConditions();
  });

  runFilterButton?.addEventListener("click", async () => {
    try {
      const payload = buildSqlFilterPayload();
      lastFilterResult = await postJson("/api/sql-lab/filter", payload);
      lastFilterPayload = payload;
      analysisScopeCacheKey = "";
      analysisScopeData = { records: [], draw_count: 0, row_count: 0 };
      renderSqlExportStatus(null);
      const inspectPanel = page.querySelector('[data-sql-step-panel="3"]');
      revealSqlResultsStep({
        scrollTarget: inspectPanel,
        openAnalysisStudio: true,
        openMatchedDraws: false,
      });
      renderRunSummary();
      if (matchedDrawsRoot) matchedDrawsRoot.innerHTML = sqlMatchedDrawsMarkup(lastFilterResult.matched_draws || []);
      if (matchedValuesRoot) matchedValuesRoot.innerHTML = sqlPreviewRowsMarkup((lastFilterResult.matched_values || []).map((item) => ({
        parameter_name: `${item._draw} · ${item.parameter_name}`,
        value: item.value,
        units: item.units,
      })));
      if (maintenanceResultsRoot) maintenanceResultsRoot.innerHTML = sqlEventRowsMarkup(lastFilterResult.maintenance_events || [], "maintenance events");
      if (faultResultsRoot) faultResultsRoot.innerHTML = sqlEventRowsMarkup(lastFilterResult.fault_events || [], "fault events");
      if (analysisResourceMode === "draws" || analysisPlotMode === "draws") {
        await ensureAnalysisScopeData();
      }
      renderSqlAnalysis();
    } catch (error) {
      if (runSummaryRoot) runSummaryRoot.innerHTML = `<div class="micro-panel">${error.message}</div>`;
    }
  });

  exportResultsButton?.addEventListener("click", async () => {
    if (!lastFilterPayload) {
      if (exportStatusRoot) {
        exportStatusRoot.innerHTML = `<span>Run a filter first so the export matches the current Step 3 results.</span>`;
      }
      return;
    }
    const originalLabel = exportResultsButton.textContent;
    exportResultsButton.disabled = true;
    exportResultsButton.textContent = "Building CSV...";
    if (exportStatusRoot) {
      exportStatusRoot.innerHTML = `<span>Building matched results CSV from the current Step 3 filter...</span>`;
    }
    try {
      const result = await postJson("/api/sql-lab/export-results", lastFilterPayload);
      renderSqlExportStatus(result);
      const downloadUrl = String(result?.downloadUrl || "").trim();
      if (downloadUrl) {
        const link = document.createElement("a");
        link.href = downloadUrl;
        link.download = String(result?.fileName || "").trim();
        link.rel = "noopener";
        link.style.display = "none";
        document.body.appendChild(link);
        link.click();
        link.remove();
      }
    } catch (error) {
      if (exportStatusRoot) {
        exportStatusRoot.innerHTML = `<span>${escapeHtml(error.message || "Could not export matched results CSV.")}</span>`;
      }
    } finally {
      exportResultsButton.disabled = false;
      exportResultsButton.textContent = originalLabel || "Download matched results CSV";
    }
  });

  runButton?.addEventListener("click", async () => {
    try {
      const result = await postJson("/api/sql-lab/query", {
        dataset: datasetSelect?.value,
        sql: queryInput?.value || "",
      });
      queryResultRoot.innerHTML = sqlResultTableMarkup(result);
    } catch (error) {
      queryResultRoot.innerHTML = `<div class="micro-panel">${error.message}</div>`;
    }
  });

  setStep("1");
  renderConditions();
  renderRunSummary();
  renderSqlAnalysis();
  renderAnalysisDetail(null);
  renderSqlExportStatus(null);
  loadDataset("__ALL__");
}

function bindDrawFinalizePage(finalizeData) {
  const page = document.getElementById("draw-finalize-page");
  if (!page) return;
  const datasetSelect = document.getElementById("finalize-dataset-select");
  const orderRoot = document.getElementById("finalize-order-root");
  const doneForm = document.getElementById("finalize-done-form");
  const failedForm = document.getElementById("finalize-failed-form");
  const resetNextdayBtn = document.getElementById("finalize-reset-nextday-btn");
  const resetPendingBtn = document.getElementById("finalize-reset-pending-btn");

  const loadDataset = async (datasetName) => {
    const matched = await getJson(`/api/draw-finalize?name=${encodeURIComponent(datasetName)}`);
    bootstrapData = { ...(bootstrapData || {}), drawFinalize: matched };
    orderRoot.innerHTML = drawFinalizeOrderMarkup(matched.matched_order);
  };

  datasetSelect?.addEventListener("change", () => loadDataset(datasetSelect.value));

  doneForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(doneForm);
    try {
      const result = await postJson("/api/draw-finalize/done", {
        dataset: datasetSelect?.value,
        doneDescription: String(formData.get("doneDescription") || ""),
        preformLengthCm: formData.get("preformLengthCm"),
      });
      drawFinalizeFlash = {
        kind: result.print_ok ? "good" : (result.done_snapshot_path ? "warn" : "bad"),
        title: result.print_ok ? "Draw Closed + Printed" : (result.done_snapshot_path ? "Draw Closed + Print Warning" : "Draw Closed"),
        message: result.message || "Draw marked as done.",
      };
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      orderRoot.innerHTML = `<div class="micro-panel">${error.message}</div>`;
    }
  });

  failedForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(failedForm);
    try {
      const result = await postJson("/api/draw-finalize/failed", {
        dataset: datasetSelect?.value,
        failedDescription: String(formData.get("failedDescription") || ""),
        failedReason: String(formData.get("failedReason") || ""),
        preformLeftCm: formData.get("preformLeftCm"),
        logFault: formData.get("logFault") === "on",
        faultComponent: String(formData.get("faultComponent") || ""),
        faultSeverity: String(formData.get("faultSeverity") || ""),
        faultTitle: String(formData.get("faultTitle") || ""),
        faultDescription: String(formData.get("faultDescription") || ""),
      });
      drawFinalizeFlash = {
        kind: "warn",
        title: "Draw Marked Failed",
        message: result.message || "Draw marked as failed.",
      };
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      orderRoot.innerHTML = `<div class="micro-panel">${error.message}</div>`;
    }
  });

  resetNextdayBtn?.addEventListener("click", async () => {
    try {
      const result = await postJson("/api/draw-finalize/reset", {
        dataset: datasetSelect?.value,
        mode: "next-day",
      });
      drawFinalizeFlash = {
        kind: "good",
        title: "Failed Draw Reset",
        message: result.message || "Draw moved to next day.",
      };
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      orderRoot.innerHTML = `<div class="micro-panel">${error.message}</div>`;
    }
  });

  resetPendingBtn?.addEventListener("click", async () => {
    try {
      const result = await postJson("/api/draw-finalize/reset", {
        dataset: datasetSelect?.value,
        mode: "pending",
      });
      drawFinalizeFlash = {
        kind: "good",
        title: "Failed Draw Reset",
        message: result.message || "Draw moved back to pending.",
      };
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      orderRoot.innerHTML = `<div class="micro-panel">${error.message}</div>`;
    }
  });
}

function bindDevelopmentPage(developmentData) {
  const page = document.getElementById("development-page");
  if (!page) return;
  const projectSelect = document.getElementById("development-project-select");
  const projectRoot = document.getElementById("development-project-root");
  const projectForm = document.getElementById("development-project-form");
  const summaryForm = document.getElementById("development-summary-form");
  const experimentForm = document.getElementById("development-experiment-form");
  const experimentFilesInput = document.getElementById("development-experiment-files");
  const experimentDropzone = document.getElementById("development-experiment-dropzone");
  const experimentFileSummary = document.getElementById("development-experiment-file-summary");
  const experimentEditForm = document.getElementById("development-experiment-edit-form");
  const experimentSelect = document.getElementById("development-experiment-select");
  const updateForm = document.getElementById("development-update-form");
  const manageForm = document.getElementById("development-manage-form");
  const exportStatus = document.getElementById("development-export-status");
  let selectedProject = developmentData.default_project || "";
  let currentProjectDetails = null;

  const fileToBase64 = (file) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || "");
        const marker = "base64,";
        const index = result.indexOf(marker);
        resolve(index >= 0 ? result.slice(index + marker.length) : result);
      };
      reader.onerror = () => reject(new Error(`Could not read ${file.name}`));
      reader.readAsDataURL(file);
    });

  const renderExperimentFileSummary = () => {
    if (!experimentFileSummary) return;
    const files = Array.from(experimentFilesInput?.files || []);
    if (!files.length) {
      experimentFileSummary.textContent = "No files chosen yet.";
      return;
    }
    if (files.length <= 3) {
      experimentFileSummary.textContent = files.map((file) => file.name).join(" · ");
      return;
    }
    const head = files.slice(0, 3).map((file) => file.name).join(" · ");
    experimentFileSummary.textContent = `${head} · +${files.length - 3} more`;
  };

  const setExperimentDropFiles = (files) => {
    if (!experimentFilesInput || !files?.length) return;
    const transfer = new DataTransfer();
    Array.from(files).forEach((file) => transfer.items.add(file));
    experimentFilesInput.files = transfer.files;
    renderExperimentFileSummary();
  };

  renderExperimentFileSummary();
  experimentFilesInput?.addEventListener("change", renderExperimentFileSummary);
  if (experimentDropzone && experimentFilesInput) {
    let dragDepth = 0;
    const setDragState = (active) => {
      experimentDropzone.classList.toggle("is-dragover", Boolean(active));
    };
    experimentDropzone.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      experimentFilesInput.click();
    });
    experimentDropzone.addEventListener("dragenter", (event) => {
      event.preventDefault();
      dragDepth += 1;
      setDragState(true);
    });
    experimentDropzone.addEventListener("dragover", (event) => {
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
      setDragState(true);
    });
    experimentDropzone.addEventListener("dragleave", (event) => {
      event.preventDefault();
      dragDepth = Math.max(0, dragDepth - 1);
      if (!dragDepth) setDragState(false);
    });
    experimentDropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      dragDepth = 0;
      setDragState(false);
      if (event.dataTransfer?.files?.length) {
        setExperimentDropFiles(event.dataTransfer.files);
      }
    });
  }

  const syncProjectForms = (projectName) => {
    if (!projectName) return;
    [
      summaryForm?.elements.namedItem("projectName"),
      experimentForm?.elements.namedItem("projectName"),
      experimentEditForm?.elements.namedItem("projectName"),
      updateForm?.elements.namedItem("projectName"),
      manageForm?.elements.namedItem("projectName"),
    ].forEach((field) => {
      if (field) field.value = projectName;
    });
  };

  const syncSummaryForm = () => {
    if (!summaryForm) return;
    const project = currentProjectDetails?.project || {};
    const researcherHint = currentProjectDetails?.researchers?.[0] || "";
    const summaryTitleField = summaryForm.elements.namedItem("summaryTitle");
    const summaryDateField = summaryForm.elements.namedItem("summaryDate");
    const summaryResearcherField = summaryForm.elements.namedItem("summaryResearcher");
    const summaryNotesField = summaryForm.elements.namedItem("summaryNotes");
    if (summaryTitleField) summaryTitleField.value = project["Summary Title"] || "";
    if (summaryDateField) summaryDateField.value = project["Summary Date"] || todayIsoDate();
    if (summaryResearcherField) summaryResearcherField.value = project["Summary Researcher"] || researcherHint;
    if (summaryNotesField) summaryNotesField.value = project["Summary Notes"] || "";
  };

  const openDevelopmentTool = (toolKey) => {
    const anchor = page.querySelector(`#development-tool-${toolKey}`);
    if (!anchor) return;
    const fold = anchor.closest(".fold-section");
    if (fold) {
      fold.open = true;
      const toggle = fold.querySelector(".fold-summary-toggle");
      if (toggle) toggle.textContent = "Hide";
    }
    anchor.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const clearExportStatus = () => {
    if (!exportStatus) return;
    exportStatus.hidden = true;
    exportStatus.innerHTML = "";
  };

  const setExportStatus = ({ message = "", fileName = "", fileUrl = "", viewUrl = "", downloadUrl = "", format = "" } = {}) => {
    if (!exportStatus) return;
    const formatLabel = format === "html" ? "project paper" : "markdown export";
    const openHref = viewUrl || fileUrl || "";
    const downloadHref = downloadUrl || fileUrl || "";
    const statusMessage = message || "Project export created.";
    const htmlHint = format === "html"
      ? " Open the paper view for the live browser render, then use Print / Save PDF from there when you want the PDF copy."
      : "";
    exportStatus.hidden = false;
    exportStatus.innerHTML = `
      <strong>${fileName ? escapeHtml(fileName) : "Export ready"}</strong>
      <p>${escapeHtml(statusMessage)}${htmlHint}</p>
      ${(openHref || downloadHref) ? `
        <div class="development-export-status-links">
          ${openHref ? `<a class="action-btn action-secondary" href="${escapeHtml(openHref)}" target="_blank" rel="noopener noreferrer">Open ${escapeHtml(formatLabel)}</a>` : ""}
          ${downloadHref ? `<a class="action-btn action-secondary" href="${escapeHtml(downloadHref)}" rel="noopener noreferrer">Download file</a>` : ""}
        </div>
      ` : ""}
    `;
  };

  Array.from(page.querySelectorAll("[data-dev-open]")).forEach((button) => {
    button.addEventListener("click", () => openDevelopmentTool(button.getAttribute("data-dev-open")));
  });

  Array.from(page.querySelectorAll("[data-dev-export]")).forEach((button) => {
    button.addEventListener("click", async () => {
      const format = String(button.getAttribute("data-dev-export") || "").trim();
      if (!selectedProject) {
        setExportStatus({ message: "Choose a project first so the app knows what to export." });
        return;
      }
      const originalText = button.textContent;
      button.disabled = true;
      button.textContent = format === "html" ? "Exporting paper..." : "Exporting markdown...";
      try {
        const result = await postJson("/api/report-center/development-export", {
          projectName: selectedProject,
          format,
        });
        bootstrapData = result.bootstrap || null;
        setExportStatus(result);
      } catch (error) {
        setExportStatus({ message: error.message || "Could not export the project." });
      } finally {
        button.disabled = false;
        button.textContent = originalText;
      }
    });
  });

  const syncExperimentEditor = () => {
    if (!experimentSelect || !experimentEditForm) return;
    const experiments = currentProjectDetails?.experiments || [];
    experimentSelect.innerHTML = `<option value="">Choose experiment...</option>${experiments
      .map((item) => {
        const value = `${item["Experiment Title"] || ""}||${item.Date || ""}`;
        return `<option value="${value}">${item["Experiment Title"] || "Untitled"} · ${item.Date || ""}</option>`;
      })
      .join("")}`;
    const selectedValue = experimentSelect.value;
    const selected = experiments.find((item) => `${item["Experiment Title"] || ""}||${item.Date || ""}` === selectedValue) || experiments[0];
    if (selected) {
      experimentSelect.value = `${selected["Experiment Title"] || ""}||${selected.Date || ""}`;
      experimentEditForm.elements.namedItem("originalTitle").value = selected["Experiment Title"] || "";
      experimentEditForm.elements.namedItem("originalDate").value = selected.Date || "";
      experimentEditForm.elements.namedItem("researcher").value = selected.Researcher || "";
      experimentEditForm.elements.namedItem("purpose").value = selected.Purpose || "";
      experimentEditForm.elements.namedItem("methods").value = selected.Methods || "";
      experimentEditForm.elements.namedItem("observations").value = selected.Observations || "";
      experimentEditForm.elements.namedItem("results").value = selected.Results || "";
      experimentEditForm.elements.namedItem("drawingDetails").value = selected["Drawing Details"] || "";
      experimentEditForm.elements.namedItem("drawCsv").value = selected["Draw CSV"] || "";
      experimentEditForm.elements.namedItem("markdownNotes").value = selected["Markdown Notes"] || "";
      experimentEditForm.elements.namedItem("isDrawing").checked = String(selected["Is Drawing"] || "").toLowerCase() === "true";
    }
  };

  const loadProject = async (projectName) => {
    selectedProject = projectName || "";
    syncProjectForms(selectedProject);
    clearExportStatus();
    if (!projectName) {
      projectRoot.innerHTML = reportProjectDetailMarkup(null);
      currentProjectDetails = null;
      syncSummaryForm();
      syncExperimentEditor();
      return;
    }
    projectRoot.innerHTML = `<div class="loading-state">Loading ${projectName}...</div>`;
    try {
      const details = await getJson(`/api/development/project?name=${encodeURIComponent(projectName)}`);
      currentProjectDetails = details;
      projectRoot.innerHTML = reportProjectDetailMarkup(details);
      bindFoldSections(projectRoot);
      syncSummaryForm();
      syncExperimentEditor();
    } catch (error) {
      projectRoot.innerHTML = `<div class="micro-panel">${error.message}</div>`;
    }
  };

  projectSelect?.addEventListener("change", () => loadProject(projectSelect.value));

  projectForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const result = await postJson("/api/development/project", Object.fromEntries(new FormData(projectForm).entries()));
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      projectRoot.innerHTML = `<div class="micro-panel">${error.message}</div>`;
    }
  });

  summaryForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const result = await postJson("/api/development/summary", Object.fromEntries(new FormData(summaryForm).entries()));
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      projectRoot.innerHTML = `<div class="micro-panel">${error.message}</div>`;
    }
  });

  experimentForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const formData = new FormData(experimentForm);
      const files = Array.from(experimentForm.querySelector("#development-experiment-files")?.files || []);
      const attachmentUploads = await Promise.all(
        files.map(async (file) => ({
          name: file.name,
          content: await fileToBase64(file),
        })),
      );
      const payload = Object.fromEntries(formData.entries());
      payload.isDrawing = formData.get("isDrawing") === "on";
      payload.attachmentUploads = attachmentUploads;
      const result = await postJson("/api/development/experiment", payload);
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      projectRoot.innerHTML = `<div class="micro-panel">${error.message}</div>`;
    }
  });

  experimentSelect?.addEventListener("change", syncExperimentEditor);

  experimentEditForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const formData = new FormData(experimentEditForm);
      const payload = Object.fromEntries(formData.entries());
      payload.isDrawing = formData.get("isDrawing") === "on";
      const result = await postJson("/api/development/experiment-update", payload);
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      projectRoot.innerHTML = `<div class="micro-panel">${error.message}</div>`;
    }
  });

  updateForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const result = await postJson("/api/development/update", Object.fromEntries(new FormData(updateForm).entries()));
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      projectRoot.innerHTML = `<div class="micro-panel">${error.message}</div>`;
    }
  });

  manageForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    const action = submitter?.value || "";
    const formData = new FormData(manageForm);
    const projectName = String(formData.get("projectName") || "").trim();
    if (action === "delete" && projectName) {
      const confirmed = window.confirm(`Delete "${projectName}" and all its experiments/updates?`);
      if (!confirmed) return;
    }
    try {
      const result = await postJson("/api/development/manage", {
        projectName,
        action,
      });
      bootstrapData = result.bootstrap || null;
      await renderRoute();
    } catch (error) {
      projectRoot.innerHTML = `<div class="micro-panel">${error.message}</div>`;
    }
  });

  if (selectedProject) {
    loadProject(selectedProject);
  }
}

function bindFoldSections(root = document) {
  Array.from(root.querySelectorAll(".fold-section")).forEach((section) => {
    const toggle = section.querySelector(".fold-summary-toggle");
    if (!toggle) return;
    const sync = () => {
      const openLabel = section.dataset.foldOpenLabel || "Open";
      const closeLabel = section.dataset.foldCloseLabel || "Hide";
      toggle.textContent = section.open ? closeLabel : openLabel;
    };
    sync();
    section.addEventListener("toggle", sync);
  });
}

function bindGlobalPressFeedback() {
  if (globalPressFeedbackBound) return;
  globalPressFeedbackBound = true;

  const selector = "button, .action-btn, summary.fold-summary, .nav-group-title";
  const holdMs = 160;
  const dragTolerancePx = 6;
  let activeElement = null;
  let releaseTimer = 0;
  let startX = 0;
  let startY = 0;
  let dragged = false;

  const resolvePressable = (target) => (
    target instanceof Element ? target.closest(selector) : null
  );

  const clearActive = (element = activeElement, immediate = false) => {
    if (!element) return;
    window.clearTimeout(releaseTimer);
    const finish = () => {
      element.classList.remove("is-pressing");
      if (activeElement === element) activeElement = null;
    };
    if (immediate) {
      finish();
      return;
    }
    releaseTimer = window.setTimeout(finish, holdMs);
  };

  const setActive = (element, clientX = null, clientY = null) => {
    if (!element) return;
    if (element.matches(":disabled, [aria-disabled='true']")) return;
    if (activeElement && activeElement !== element) {
      activeElement.classList.remove("is-pressing");
    }
    window.clearTimeout(releaseTimer);
    activeElement = element;
    dragged = false;
    if (typeof clientX === "number") startX = clientX;
    if (typeof clientY === "number") startY = clientY;
    element.classList.add("is-pressing");
  };

  document.addEventListener("pointerdown", (event) => {
    const element = resolvePressable(event.target);
    if (!element) return;
    setActive(element, event.clientX, event.clientY);
  }, true);

  document.addEventListener("pointermove", (event) => {
    if (!activeElement) return;
    const moved = Math.hypot(event.clientX - startX, event.clientY - startY);
    if (moved <= dragTolerancePx || dragged) return;
    dragged = true;
    activeElement.classList.remove("is-pressing");
  }, true);

  document.addEventListener("pointerup", (event) => {
    const element = resolvePressable(event.target) || activeElement;
    if (!element) return;
    clearActive(element, dragged);
    dragged = false;
  }, true);

  document.addEventListener("pointercancel", () => {
    clearActive(activeElement, true);
    dragged = false;
  }, true);

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const element = resolvePressable(document.activeElement);
    if (!element) return;
    setActive(element);
  }, true);

  document.addEventListener("keyup", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const element = resolvePressable(document.activeElement) || activeElement;
    if (!element) return;
    clearActive(element);
  }, true);
}

async function renderRoute() {
  const route = getCurrentRoute();
  const page = getPage(route);
  if (page.key !== "consumables" && consumablesLivePollTimer) {
    window.clearInterval(consumablesLivePollTimer);
    consumablesLivePollTimer = null;
    consumablesLivePollInFlight = false;
  }
  app.innerHTML = renderShell(page.route);
  bindSidebarMap();
  const pageRoot = document.getElementById("page-root");
  pageRoot.innerHTML = bootstrapData
    ? `<div class="loading-state">Opening ${page.label}...</div>`
    : `<div class="loading-state">Loading Tower data...</div>`;

  try {
    const data = await ensureBootstrapData();
    const renderer = PAGE_RENDERERS[page.key];
    const html = await renderer(data[page.key]);
    pageRoot.innerHTML = html;
    if (page.key === "home") {
      bindHomePanels(data.home);
    } else if (page.key === "consumables") {
      bindConsumablesPage();
    } else if (page.key === "processSetup") {
      bindProcessSetupPage(data.processSetup);
    } else if (page.key === "parts") {
      bindPartsPage(data.parts);
    } else if (page.key === "orderDraw") {
      bindOrderDrawPage(data.orderDraw);
    } else if (page.key === "dashboard") {
      bindDashboardPage(data.dashboard);
    } else if (page.key === "schedule") {
      bindSchedulePage(data.schedule);
    } else if (page.key === "maintenance") {
      bindMaintenancePage(data.maintenance);
    } else if (page.key === "reportCenter") {
      bindReportCenterPage(data.reportCenter);
    } else if (page.key === "sqlLab") {
      bindSqlLabPage(data.sqlLab);
    } else if (page.key === "drawFinalize") {
      bindDrawFinalizePage(data.drawFinalize);
    } else if (page.key === "development") {
      bindDevelopmentPage(data.development);
    } else if (page.key === "diagnostics") {
      bindDiagnosticsPage(data.diagnostics);
    }
    bindFoldSections(pageRoot);
  } catch (error) {
    console.error(error);
    pageRoot.innerHTML = `
      <section class="page-panel">
        <div class="section-heading">
          <span>Error</span>
          <h2>Page failed to load</h2>
          <p>${error.message}</p>
        </div>
      </section>
    `;
  }
}

window.addEventListener("hashchange", renderRoute);
bindGlobalPressFeedback();
renderRoute();
