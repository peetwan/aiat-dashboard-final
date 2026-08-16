const dashboardState = {
  summary: null,
  sources: [],
  runs: [],
  connectivity: [],
  sourceFilter: "all",
  sourceSearch: "",
  endpoints: [],
  activeSource: null,
};

const routeMeta = {
  api_first: { label: "API-first", detail: "Live endpoint + snapshot fallback", css: "api" },
  snapshot_only: { label: "Raw snapshot", detail: "Immutable CSV / JSON replay", css: "snapshot" },
  blocked: { label: "Local-only", detail: "ไม่ส่งขึ้น cloud", css: "blocked" },
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function number(value, compact = false) {
  const options = compact ? { notation: "compact", maximumFractionDigits: 1 } : {};
  return new Intl.NumberFormat("th-TH", options).format(Number(value) || 0);
}

function percent(value, total) {
  return total ? Math.round((Number(value) / Number(total)) * 100) : 0;
}

function formatDate(value) {
  if (!value) return "ยังไม่มี ingestion";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("th-TH", {
    day: "numeric",
    month: "short",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function routeBadge(mode) {
  const meta = routeMeta[mode] || routeMeta.blocked;
  return (
    '<span class="route-badge ' +
    meta.css +
    '"><i></i><span><b>' +
    escapeHtml(meta.label) +
    "</b><small>" +
    escapeHtml(meta.detail) +
    "</small></span></span>"
  );
}

function statusBadge(run) {
  if (!run) return '<span class="status-badge pending"><i></i>Waiting for first run</span>';
  const labels = { complete: "Synced", running: "Running", failed: "Failed", blocked: "Blocked" };
  const status = ["complete", "running", "failed", "blocked"].includes(run.status) ? run.status : "pending";
  return (
    '<span class="status-badge ' +
    status +
    '"><i></i>' +
    escapeHtml(labels[status] || run.status) +
    "</span>"
  );
}

function renderSummary() {
  const data = dashboardState.summary;
  const connectorCoverage = percent(data.configured_connectors, data.sources);
  const cards = [
    {
      icon: "◫",
      label: "Public sources",
      value: number(data.production_approved_sources),
      detail: "จาก " + number(data.sources) + " แหล่งใน catalog",
      tone: "violet",
    },
    {
      icon: "⌘",
      label: "Runtime endpoints",
      value: number(data.safe_runtime_endpoints),
      detail: "จาก " + number(data.endpoints_catalogued) + " endpoints",
      tone: "blue",
    },
    {
      icon: "↯",
      label: "Connector coverage",
      value: connectorCoverage + "%",
      detail: number(data.configured_connectors) + " เส้นทางพร้อม deploy",
      tone: "mint",
    },
    {
      icon: "▤",
      label: "Rows in database",
      value: number(data.candidate_records_loaded, true),
      detail: number(data.expected_candidate_records, true) + " reference rows",
      tone: "orange",
    },
  ];
  document.querySelector("#summary").innerHTML = cards
    .map(
      (card) =>
        '<article class="stat-card"><div class="stat-icon ' +
        card.tone +
        '">' +
        card.icon +
        '</div><div class="stat-card-copy"><span>' +
        escapeHtml(card.label) +
        "</span><strong>" +
        escapeHtml(card.value) +
        "</strong><small>" +
        escapeHtml(card.detail) +
        "</small></div></article>",
    )
    .join("");

  document.querySelector("#navSourceCount").textContent = number(data.sources);
  document.querySelector("#connectorPercent").textContent = connectorCoverage + "%";
  document.querySelector("#connectorProgress").style.width = connectorCoverage + "%";
  document.querySelector("#connectorCopy").textContent =
    number(data.configured_connectors) +
    " public connectors พร้อมใช้งาน · " +
    number(data.blocked_sources) +
    " local-only";
  document.querySelector("#databaseBackend").textContent =
    "Database · " + String(data.database_backend || "unknown").toUpperCase();
  document.querySelector("#lastSync").textContent = formatDate(data.latest_run_at);
}

function renderCoverage() {
  const data = dashboardState.summary;
  const routes = [
    ["api_first", data.api_first_sources],
    ["snapshot_only", data.snapshot_sources],
    ["blocked", data.blocked_sources],
  ];
  document.querySelector("#routeBars").innerHTML = routes
    .map(([mode, count]) => {
      const meta = routeMeta[mode];
      const width = percent(count, data.sources);
      return (
        '<article class="route-row"><div class="route-label"><span class="route-dot ' +
        meta.css +
        '"></span><div><b>' +
        meta.label +
        "</b><small>" +
        meta.detail +
        '</small></div></div><div class="route-value"><div class="bar-track"><i class="' +
        meta.css +
        '" style="width:' +
        width +
        '%"></i></div><b>' +
        number(count) +
        "</b></div></article>"
      );
    })
    .join("");

  const total = data.endpoints_catalogued || 1;
  const safe = data.safe_runtime_endpoints;
  const restricted = dashboardState.sources.reduce(
    (sum, source) => sum + Number(source.restricted_endpoint_count || 0),
    0,
  );
  const review = Math.max(0, total - safe - restricted);
  const stackData = [
    { label: "Runtime safe", count: safe, css: "safe" },
    { label: "Needs review", count: review, css: "review" },
    { label: "Restricted", count: restricted, css: "restricted" },
  ];
  document.querySelector("#endpointTotal").textContent = number(total) + " routes";
  document.querySelector("#endpointStack").innerHTML = stackData
    .map(
      (item) =>
        '<i class="' +
        item.css +
        '" style="width:' +
        percent(item.count, total) +
        '%" title="' +
        escapeHtml(item.label) +
        " " +
        number(item.count) +
        '"></i>',
    )
    .join("");
  document.querySelector("#endpointLegend").innerHTML = stackData
    .map(
      (item) =>
        '<span><i class="' +
        item.css +
        '"></i><b>' +
        escapeHtml(item.label) +
        "</b><em>" +
        number(item.count) +
        "</em></span>",
    )
    .join("");

  const safePercent = percent(safe, total);
  document.querySelector("#healthRing").style.setProperty("--health", safePercent + "%");
  document.querySelector("#healthPercent").textContent = safePercent + "%";
  document.querySelector("#healthList").innerHTML = [
    ["Database", String(data.database_backend || "—").toUpperCase(), "ok"],
    ["Completed runs", number(data.complete_runs), "ok"],
    ["Failed runs", number(data.failed_runs), data.failed_runs ? "warn" : "ok"],
  ]
    .map(
      ([label, value, state]) =>
        '<div><span><i class="' +
        state +
        '"></i>' +
        escapeHtml(label) +
        "</span><b>" +
        escapeHtml(value) +
        "</b></div>",
    )
    .join("");
}

function sourceMatches(source) {
  const filterMatch =
    dashboardState.sourceFilter === "all" || source.acquisition_mode === dashboardState.sourceFilter;
  const query = dashboardState.sourceSearch.trim().toLocaleLowerCase("th");
  if (!query) return filterMatch;
  const haystack = [source.name_th, source.source_id, source.url].join(" ").toLocaleLowerCase("th");
  return filterMatch && haystack.includes(query);
}

function renderSources() {
  const sources = dashboardState.sources.filter(sourceMatches);
  const root = document.querySelector("#sourceRows");
  if (!sources.length) {
    root.innerHTML = '<tr><td colspan="7"><div class="empty-state"><b>ไม่พบ source ที่ตรงกับตัวกรอง</b><span>ลองค้นหาด้วยชื่อระบบหรือ source id</span></div></td></tr>';
  } else {
    root.innerHTML = sources
      .map((source) => {
        const progress = Math.min(100, percent(source.loaded_records, source.expected_record_count));
        const initial = String(source.name_th || source.source_id).trim().slice(0, 1).toUpperCase();
        return (
          "<tr>" +
          '<td><div class="source-name"><span class="source-avatar">' +
          escapeHtml(initial) +
          '</span><div><a href="' +
          escapeHtml(source.url) +
          '" target="_blank" rel="noreferrer">' +
          escapeHtml(source.name_th) +
          '</a><small><span class="ordinal">#' +
          String(source.ordinal).padStart(2, "0") +
          "</span>" +
          escapeHtml(source.source_id) +
          "</small></div></div></td>" +
          "<td>" +
          routeBadge(source.acquisition_mode) +
          "</td>" +
          '<td><div class="endpoint-count"><b>' +
          number(source.runtime_endpoint_count) +
          "</b><span>/ " +
          number(source.endpoint_count) +
          " safe</span></div></td>" +
          "<td><b>" +
          number(source.expected_record_count, true) +
          '</b><small class="cell-note">candidate reference</small></td>' +
          '<td><div class="loaded-cell"><div><b>' +
          number(source.loaded_records, true) +
          "</b><span>" +
          progress +
          '%</span></div><div class="row-progress"><i style="width:' +
          progress +
          '%"></i></div></div></td>' +
          "<td>" +
          statusBadge(source.latest_run) +
          (source.latest_run
            ? '<small class="cell-note">' + escapeHtml(formatDate(source.latest_run.started_at)) + "</small>"
            : "") +
          "</td>" +
          '<td><button class="detail-button endpoint-button" type="button" data-source="' +
          escapeHtml(source.source_id) +
          '">รายละเอียด <span>›</span></button></td>' +
          "</tr>"
        );
      })
      .join("");
  }
  document.querySelector("#tableResultCount").textContent =
    "แสดง " + number(sources.length) + " จาก " + number(dashboardState.sources.length) + " sources";
  document.querySelectorAll(".endpoint-button").forEach((button) => {
    button.addEventListener("click", () => openEndpoints(button.dataset.source));
  });
}

function renderRuns() {
  const root = document.querySelector("#runs");
  if (!dashboardState.runs.length) {
    root.innerHTML =
      '<div class="empty-runs"><span>↻</span><b>ยังไม่มี ingestion run</b><p>Catalog พร้อมแล้ว ระบบจะบันทึก timeline หลัง worker เริ่มดึง API หรือ replay snapshot</p></div>';
    return;
  }
  root.innerHTML = dashboardState.runs
    .map(
      (run) =>
        '<article class="run"><span class="run-status ' +
        escapeHtml(run.status) +
        '"></span><div><div><strong>' +
        escapeHtml(run.source_id) +
        '<em class="run-strategy">' +
        escapeHtml(run.strategy) +
        "</em></strong><time>" +
        escapeHtml(formatDate(run.started_at)) +
        "</time></div><small>" +
        escapeHtml(run.run_id) +
        "</small></div><b>" +
        number(run.records_loaded, true) +
        " rows</b></article>",
    )
    .join("");
}

function renderEndpoints() {
  const query = document.querySelector("#endpointSearch").value.trim().toLocaleLowerCase("th");
  const endpoints = dashboardState.endpoints.filter((endpoint) =>
    [endpoint.url, endpoint.kind, endpoint.access, endpoint.team_action]
      .join(" ")
      .toLocaleLowerCase("th")
      .includes(query),
  );
  const root = document.querySelector("#endpointList");
  if (!endpoints.length) {
    root.innerHTML = '<div class="empty-state"><b>ไม่พบ endpoint</b><span>ลองเปลี่ยนคำค้นหา</span></div>';
    return;
  }
  root.innerHTML = endpoints
    .map((endpoint) => {
      const state = endpoint.restricted ? "blocked" : endpoint.runtime_enabled ? "safe" : "review";
      const label = state === "safe" ? "Runtime safe" : state === "blocked" ? "Restricted" : "Review";
      return (
        '<article class="endpoint"><span class="method">' +
        escapeHtml(endpoint.method) +
        '</span><div class="endpoint-copy"><code>' +
        escapeHtml(endpoint.url) +
        "</code><small>" +
        escapeHtml(endpoint.kind || endpoint.access || "ไม่ระบุ") +
        (endpoint.notes_th ? " · " + escapeHtml(endpoint.notes_th) : "") +
        '</small></div><span class="endpoint-state ' +
        state +
        '"><i></i>' +
        label +
        "</span></article>"
      );
    })
    .join("");
}

async function openEndpoints(sourceId) {
  const source = dashboardState.sources.find((item) => item.source_id === sourceId);
  const response = await fetch("/api/sources/" + encodeURIComponent(sourceId) + "/endpoints");
  if (!response.ok) throw new Error("โหลด endpoint ไม่สำเร็จ");
  dashboardState.endpoints = await response.json();
  dashboardState.activeSource = sourceId;
  document.querySelector("#endpointSearch").value = "";
  document.querySelector("#endpointTitle").textContent = source ? source.name_th : sourceId;
  document.querySelector("#endpointSubtitle").textContent =
    sourceId + " · " + number(dashboardState.endpoints.length) + " endpoints";
  const safeCount = dashboardState.endpoints.filter(
    (endpoint) => endpoint.runtime_enabled && !endpoint.restricted,
  ).length;
  document.querySelector("#endpointSafeCount").textContent =
    number(safeCount) + " runtime safe · " + number(dashboardState.endpoints.length - safeCount) + " gated";
  renderEndpoints();
  document.querySelector("#endpointDialog").showModal();
}

function showToast(message, tone = "ok") {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.className = "toast show " + tone;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.className = "toast";
  }, 3200);
}

async function loadDashboard({ announce = false } = {}) {
  const button = document.querySelector("#refreshDashboard");
  button.classList.add("loading");
  button.disabled = true;
  try {
    const [summaryResponse, sourcesResponse, runsResponse, connectivityResponse] = await Promise.all([
      fetch("/api/summary"),
      fetch("/api/sources"),
      fetch("/api/runs?limit=12"),
      fetch("/api/connectivity"),
    ]);
    if (![summaryResponse, sourcesResponse, runsResponse, connectivityResponse].every((item) => item.ok)) {
      throw new Error("API ตอบกลับไม่สมบูรณ์");
    }
    dashboardState.summary = await summaryResponse.json();
    dashboardState.sources = await sourcesResponse.json();
    dashboardState.runs = await runsResponse.json();
    dashboardState.connectivity = await connectivityResponse.json();
    renderSummary();
    renderCoverage();
    renderSources();
    renderRuns();
    if (announce) showToast("อัปเดตมุมมองจาก database แล้ว");
  } catch (error) {
    showToast("โหลด dashboard ไม่สำเร็จ: " + error.message, "error");
  } finally {
    button.classList.remove("loading");
    button.disabled = false;
  }
}

document.querySelector("#sourceSearch").addEventListener("input", (event) => {
  dashboardState.sourceSearch = event.target.value;
  renderSources();
});

document.querySelectorAll(".filter-button").forEach((button) => {
  button.addEventListener("click", () => {
    dashboardState.sourceFilter = button.dataset.filter;
    document.querySelectorAll(".filter-button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    renderSources();
  });
});

document.querySelector("#refreshDashboard").addEventListener("click", () => loadDashboard({ announce: true }));
document.querySelector("#endpointSearch").addEventListener("input", renderEndpoints);
document.querySelector("#closeDialog").addEventListener("click", () => {
  document.querySelector("#endpointDialog").close();
});
document.querySelector("#endpointDialog").addEventListener("click", (event) => {
  if (event.target === event.currentTarget) event.currentTarget.close();
});
document.querySelector("#openApiExplorer").addEventListener("click", () => {
  const source = dashboardState.sources.find((item) => item.endpoint_count > 0);
  if (source) openEndpoints(source.source_id).catch((error) => showToast(error.message, "error"));
});

loadDashboard();
