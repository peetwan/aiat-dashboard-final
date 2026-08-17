const state = {
  overview: null,
  sources: [],
  schema: null,
};

const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatNumber(value) {
  return new Intl.NumberFormat("th-TH").format(Number(value || 0));
}

function formatDate(value) {
  if (!value) return "ไม่ระบุ";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return String(value);
  return new Intl.DateTimeFormat("th-TH", {
    dateStyle: "medium",
    timeStyle: "medium",
    timeZone: "Asia/Bangkok",
  }).format(parsed);
}

function badgeClass(source) {
  if (source.cloud_policy === "restricted_local_only") return "restricted";
  if (source.cloud_policy === "metadata_only") return "metadata";
  return "public";
}

function connectionClass(status) {
  return {
    api_connected: "api",
    snapshot_connected: "snapshot",
    public_projection: "projection",
    catalog_only: "catalog",
    local_only: "local",
  }[status] || "neutral";
}

async function requestJson(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" }, cache: "no-store" });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

function renderOverview(data) {
  state.overview = data;
  $("#source-total").textContent = formatNumber(data.source_total);
  $("#public-total").textContent = formatNumber(data.public_candidate_sources);
  $("#metadata-total").textContent = formatNumber(data.metadata_only_sources);
  $("#restricted-total").textContent = formatNumber(data.restricted_sources);
  $("#artifact-total").textContent = formatNumber(data.public_artifact_total);
  $("#spatial-total").textContent = formatNumber(data.spatial_feature_total);
  $("#artifact-inline").textContent = formatNumber(data.public_artifact_total);
  $("#candidate-inline").textContent = formatNumber(data.operational_candidate_records);
  $("#checked-at").textContent = formatDate(data.checked_at);
  $("#backend-badge").textContent = `${data.database_backend.toUpperCase()} · connected`;
  $("#backend-badge").className = "status-pill connected";
  $("#live-dot").className = "live-dot online";
  $("#live-label").textContent = "เชื่อม PostgreSQL แล้ว · read-only live";
}

function sourceRow(source) {
  const targets = source.database_targets
    .map((target) => `<span class="target-chip">${escapeHtml(target)}</span>`)
    .join("");
  const candidateInfo = source.operational_candidate_records
    ? `<span class="cell-muted">staging ${formatNumber(source.operational_candidate_records)} rows</span>`
    : `<span class="cell-muted">ไม่มี staging rows</span>`;
  return `
    <tr data-source-id="${escapeHtml(source.source_id)}">
      <td><span class="ordinal">${String(source.ordinal).padStart(2, "0")}</span></td>
      <td>
        <strong class="source-name">${escapeHtml(source.name_th)}</strong>
        <span class="source-id">${escapeHtml(source.source_id)} · ${escapeHtml(source.group)}</span>
        <a class="source-link" href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">${escapeHtml(source.url)} ↗</a>
      </td>
      <td>${escapeHtml(source.what_we_use_th)}</td>
      <td>${escapeHtml(source.grain_th)}</td>
      <td>
        <div class="cell-stack">
          <span class="badge ${connectionClass(source.connection_status)}">${escapeHtml(source.connection_label)}</span>
          <span class="badge ${badgeClass(source)}">${escapeHtml(source.policy_label)}</span>
          <span class="cell-muted">${formatNumber(source.runtime_endpoint_count)}/${formatNumber(source.endpoint_count)} runtime endpoints</span>
          ${candidateInfo}
        </div>
      </td>
      <td><div class="target-list">${targets}</div></td>
      <td><button class="detail-button" data-detail="${escapeHtml(source.source_id)}">ดูรายละเอียด</button></td>
    </tr>
  `;
}

function filteredSources() {
  const query = $("#search-input").value.trim().toLowerCase();
  const group = $("#group-filter").value;
  const policy = $("#policy-filter").value;
  const connection = $("#connection-filter").value;
  return state.sources.filter((source) => {
    const searchable = [
      source.name_th,
      source.source_id,
      source.url,
      source.what_we_use_th,
      source.grain_th,
      source.group,
    ].join(" ").toLowerCase();
    return (!query || searchable.includes(query))
      && (!group || source.group === group)
      && (!policy || source.cloud_policy === policy)
      && (!connection || source.connection_status === connection);
  });
}

function renderSources() {
  const rows = filteredSources();
  $("#source-body").innerHTML = rows.map(sourceRow).join("");
  $("#empty-state").hidden = rows.length !== 0;
  $("#source-summary").textContent = `แสดง ${formatNumber(rows.length)} จาก ${formatNumber(state.sources.length)} แหล่ง`;
  document.querySelectorAll("[data-detail]").forEach((button) => {
    button.addEventListener("click", () => openSourceDialog(button.dataset.detail));
  });
}

function populateGroups() {
  const select = $("#group-filter");
  const current = select.value;
  const groups = [...new Set(state.sources.map((source) => source.group).filter(Boolean))];
  select.innerHTML = `<option value="">ทุกฝ่าย</option>${groups.map((group) => `<option value="${escapeHtml(group)}">${escapeHtml(group)}</option>`).join("")}`;
  select.value = current;
}

function renderSchema(data) {
  state.schema = data;
  $("#schema-cards").innerHTML = data.tables.map((table) => `
    <article class="schema-card">
      <div class="schema-card-header">
        <span class="schema-table-name">${escapeHtml(table.name)}</span>
        <span class="schema-count">${formatNumber(table.live_row_count)}</span>
      </div>
      <h3>${escapeHtml(table.meaning_th)}</h3>
      <p><strong>Grain:</strong> ${escapeHtml(table.grain_th)}</p>
      <div class="schema-meta">
        <span class="target-chip">PK ${escapeHtml(table.primary_key)}</span>
        <span class="target-chip">${escapeHtml(table.group)}</span>
        ${table.count_mode === "snapshot_contract" ? `<span class="target-chip">validated count</span>` : ""}
      </div>
    </article>
  `).join("");
  $("#relationship-list").innerHTML = data.relationships.map((relation) => `
    <article class="relation">
      <div class="relation-path"><span>${escapeHtml(relation.from)}</span><span>${escapeHtml(relation.cardinality)}</span><span>${escapeHtml(relation.to)}</span></div>
      <p>${escapeHtml(relation.label_th)}</p>
    </article>
  `).join("");
}

function openSourceDialog(sourceId) {
  const source = state.sources.find((item) => item.source_id === sourceId);
  if (!source) return;
  const endpointHtml = source.endpoints.length
    ? source.endpoints.map((endpoint) => `
      <div class="endpoint-row">
        <div class="endpoint-meta">
          <strong>${escapeHtml(endpoint.method)}</strong>
          <span class="mini-pill">${escapeHtml(endpoint.kind || "endpoint")}</span>
          <span class="mini-pill">${escapeHtml(endpoint.access_status || "ไม่ระบุ")}</span>
          ${endpoint.runtime_enabled ? `<span class="mini-pill">runtime enabled</span>` : ""}
          ${endpoint.restricted ? `<span class="mini-pill">restricted</span>` : ""}
        </div>
        <a href="${escapeHtml(endpoint.url)}" target="_blank" rel="noreferrer">${escapeHtml(endpoint.url)} ↗</a>
      </div>
    `).join("")
    : `<p class="cell-muted">ยังไม่มี endpoint ที่ sync เข้า Serving Database</p>`;
  const runHtml = source.latest_run ? `
    <div class="run-grid">
      <div><span>สถานะ</span><strong>${escapeHtml(source.latest_run.status)}</strong></div>
      <div><span>Strategy</span><strong>${escapeHtml(source.latest_run.strategy)}</strong></div>
      <div><span>Seen</span><strong>${formatNumber(source.latest_run.records_seen)}</strong></div>
      <div><span>Loaded</span><strong>${formatNumber(source.latest_run.records_loaded)}</strong></div>
    </div>
    <p class="cell-muted" style="margin-top:10px">${escapeHtml(source.latest_run.run_id)} · ${formatDate(source.latest_run.finished_at || source.latest_run.started_at)}</p>
  ` : `<p class="cell-muted">ยังไม่มี operational ingestion run ในฐานปัจจุบัน; Public projection อาจมาจาก validated snapshot/build</p>`;
  $("#dialog-content").innerHTML = `
    <header class="dialog-title">
      <span class="source-id">${escapeHtml(source.source_id)} · ${escapeHtml(source.group)}</span>
      <h2>${escapeHtml(source.name_th)}</h2>
      <a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">${escapeHtml(source.url)} ↗</a>
      <div class="dialog-badges">
        <span class="badge ${connectionClass(source.connection_status)}">${escapeHtml(source.connection_label)}</span>
        <span class="badge ${badgeClass(source)}">${escapeHtml(source.policy_label)}</span>
        <span class="badge neutral">${escapeHtml(source.acquisition_mode)}</span>
        <span class="badge neutral">${escapeHtml(source.readiness_status)}</span>
      </div>
    </header>
    <div class="detail-grid">
      <section class="detail-box"><h3>เราเอาอะไรมา</h3><p>${escapeHtml(source.what_we_use_th)}</p></section>
      <section class="detail-box"><h3>Grain — หนึ่งแถวแทนอะไร</h3><p>${escapeHtml(source.grain_th)}</p></section>
      <section class="detail-box"><h3>ใช้ตรงไหนใน Dashboard</h3><p>${escapeHtml(source.dashboard_use_th)}</p></section>
      <section class="detail-box"><h3>สิ่งที่ไม่เอามา/ข้อควรระวัง</h3><p>${escapeHtml(source.excluded_th)}</p></section>
      <section class="detail-box wide"><h3>ตารางที่เกี่ยวข้อง</h3><div class="target-list">${source.database_targets.map((target) => `<span class="target-chip">${escapeHtml(target)}</span>`).join("")}</div></section>
      <section class="detail-box wide"><h3>รอบดึงล่าสุดใน Operational Database</h3>${runHtml}</section>
      <section class="detail-box wide"><h3>Endpoints ในทะเบียน (${formatNumber(source.endpoint_count)})</h3><div class="endpoint-list">${endpointHtml}</div></section>
      <section class="detail-box wide"><h3>หมายเหตุจาก Source Catalog</h3><p>${escapeHtml(source.notes_th || "ไม่ระบุ")}</p></section>
    </div>
  `;
  $("#source-dialog").showModal();
}

async function refresh() {
  try {
    const [overview, sourceData, schema] = await Promise.all([
      requestJson("/api/overview"),
      requestJson("/api/sources"),
      requestJson("/api/schema"),
    ]);
    renderOverview(overview);
    state.sources = sourceData.sources;
    populateGroups();
    renderSources();
    renderSchema(schema);
    $("#footer-refresh").textContent = `อัปเดตล่าสุด ${formatDate(overview.checked_at)} · refresh ทุก ${window.EXPLORER_CONFIG.refreshSeconds} วินาที`;
  } catch (error) {
    console.error(error);
    $("#live-dot").className = "live-dot offline";
    $("#live-label").textContent = "เชื่อม Database ไม่สำเร็จ";
    $("#backend-badge").textContent = "disconnected";
    $("#backend-badge").className = "status-pill error";
  }
}

$("#dialog-close").addEventListener("click", () => $("#source-dialog").close());
$("#source-dialog").addEventListener("click", (event) => {
  if (event.target === $("#source-dialog")) $("#source-dialog").close();
});
["#search-input", "#group-filter", "#policy-filter", "#connection-filter"].forEach((selector) => {
  $(selector).addEventListener(selector === "#search-input" ? "input" : "change", renderSources);
});

refresh();
window.setInterval(refresh, Number(window.EXPLORER_CONFIG.refreshSeconds || 30) * 1000);

