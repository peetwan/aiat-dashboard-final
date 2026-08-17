const state = {
  overview: null,
  sources: [],
  schema: null,
  selectedTable: null,
  previewSourceId: "",
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

function populatePreviewSources() {
  const select = $("#preview-source-filter");
  const current = state.previewSourceId;
  select.innerHTML = `
    <option value="">ทุก Source — ดูภาพรวม Database</option>
    ${state.sources.map((source) => `<option value="${escapeHtml(source.source_id)}">${String(source.ordinal).padStart(2, "0")} · ${escapeHtml(source.name_th)} — ${escapeHtml(source.url)}</option>`).join("")}
  `;
  select.value = current;
  updatePreviewFilterLabel();
}

function updatePreviewFilterLabel() {
  const source = state.sources.find((item) => item.source_id === state.previewSourceId);
  $("#preview-filter-label").textContent = source
    ? `${source.source_id} · ${source.name_th}`
    : `ทุก Source · ${formatNumber(state.sources.length)} URL`;
}

function mapField(field) {
  const isPrimary = field.includes("(PK)");
  const isForeign = field.includes("(FK)");
  const marker = isPrimary ? "PK" : isForeign ? "FK" : "·";
  const className = isPrimary ? "primary" : isForeign ? "foreign" : "";
  return `<span class="map-field ${className}"><i>${marker}</i><span>${escapeHtml(field.replace(" (PK)", "").replace(" (FK)", ""))}</span></span>`;
}

function mapTableCard(table) {
  return `
    <button class="map-table-card" type="button" data-map-table="${escapeHtml(table.name)}" aria-label="ดูรายละเอียดตาราง ${escapeHtml(table.name)}">
      <span class="map-card-head">
        <span><strong>${escapeHtml(table.name)}</strong><small>${escapeHtml(table.role_th)}</small></span>
        <span class="map-row-count">${formatNumber(table.live_row_count)}</span>
      </span>
      <span class="map-field-list">${table.key_fields.map(mapField).join("")}</span>
    </button>
  `;
}

function previewTone(group) {
  return {
    Operational: "tone-operational",
    "Candidate staging": "tone-candidate",
    "Public serving": "tone-public",
    "Spatial serving": "tone-spatial",
    "Housing serving": "tone-housing",
  }[group] || "tone-control";
}

function previewBlock(table) {
  const relationCount = state.schema.relationships.filter((relation) => relation.from === table.name || relation.to === table.name).length;
  return `
    <button class="preview-block ${previewTone(table.group)}" type="button" data-preview-table="${escapeHtml(table.name)}">
      <span class="preview-block-head">
        <span><strong>${escapeHtml(table.name)}</strong><small>${escapeHtml(table.role_th)}</small></span>
        <span class="preview-count">${formatNumber(table.live_row_count)}<span>${table.count_mode === "snapshot_contract" ? "VALIDATED COUNT" : "SERVING ROWS"}</span></span>
      </span>
      <span class="preview-field-list">${table.key_fields.map((field) => `<span>${escapeHtml(field)}</span>`).join("")}</span>
      <span class="preview-block-foot"><span>${relationCount ? `${formatNumber(relationCount)} relationships` : "global serving table"}</span><b>กดดู DATA →</b></span>
    </button>
  `;
}

function renderPreviewBlocks(data) {
  $("#preview-blocks").innerHTML = data.tables.map(previewBlock).join("");
  document.querySelectorAll("[data-preview-table]").forEach((button) => {
    button.addEventListener("click", () => openDataPreview(button.dataset.previewTable));
  });
}

function previewCell(value) {
  if (value === null || value === undefined) return `<span class="data-null">NULL</span>`;
  if (typeof value === "boolean") return `<span class="data-boolean-${value}">${value}</span>`;
  const text = String(value);
  if (/^https?:\/\//i.test(text)) {
    return `<a href="${escapeHtml(text)}" target="_blank" rel="noreferrer" title="${escapeHtml(text)}">${escapeHtml(text)} ↗</a>`;
  }
  return `<span title="${escapeHtml(text)}">${escapeHtml(text)}</span>`;
}

async function openDataPreview(tableName) {
  const dialog = $("#data-preview-dialog");
  const content = $("#data-preview-content");
  const selectedSource = state.sources.find((item) => item.source_id === state.previewSourceId);
  content.innerHTML = `<div class="preview-empty">กำลังอ่านตัวอย่างจาก PostgreSQL…</div>`;
  dialog.showModal();
  try {
    const query = new URLSearchParams({ limit: "6" });
    if (state.previewSourceId) query.set("source_id", state.previewSourceId);
    const data = await requestJson(`/api/data-preview/${encodeURIComponent(tableName)}?${query}`);
    const rowsHtml = data.rows.length
      ? `<div class="data-sample-wrap"><table class="data-sample-table"><thead><tr>${data.columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead><tbody>${data.rows.map((row) => `<tr>${data.columns.map((column) => `<td>${previewCell(row[column])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
      : `<div class="preview-empty">ยังไม่มี physical rows ในตารางนี้${data.source_filter_applied ? "สำหรับ Source ที่เลือก" : ""}</div>`;
    const filterLabel = data.source_filter_applied && selectedSource
      ? `${selectedSource.source_id} · ${selectedSource.name_th}`
      : data.source_filter_requested && !data.source_filter_supported
        ? "Global table · ตารางนี้ไม่มี source_id โดยตรง"
        : "ทุก Source";
    content.innerHTML = `
      <header class="preview-dialog-head">
        <span class="kicker">LIVE POSTGRESQL · READ ONLY</span>
        <h2>${escapeHtml(data.table)}</h2>
        <p>${escapeHtml(data.meaning_th)}</p>
        <div class="preview-dialog-meta">
          <span>${formatNumber(data.physical_row_count)} physical rows</span>
          <span>แสดง ${formatNumber(data.sample_size)} แถว</span>
          <span>${escapeHtml(filterLabel)}</span>
          ${data.count_mode === "snapshot_contract" ? `<span>${formatNumber(data.serving_or_contract_count)} validated count</span>` : ""}
        </div>
      </header>
      ${rowsHtml}
      <p class="preview-safety-note">Safe preview: ไม่ส่ง payload, request template, geometry, evidence path, hash หรือข้อมูลติดต่อออกจาก API นี้</p>
    `;
  } catch (error) {
    console.error(error);
    content.innerHTML = `<div class="preview-empty">อ่านตัวอย่างข้อมูลไม่สำเร็จ</div>`;
  }
}

function selectMapTable(tableName) {
  if (!state.schema) return;
  const table = state.schema.tables.find((item) => item.name === tableName);
  if (!table) return;
  state.selectedTable = tableName;
  const relations = state.schema.relationships.filter((relation) => relation.from === tableName || relation.to === tableName);
  const relatedNames = new Set(relations.flatMap((relation) => [relation.from, relation.to]));
  document.querySelectorAll("[data-map-table]").forEach((card) => {
    const name = card.dataset.mapTable;
    card.classList.toggle("is-selected", name === tableName);
    card.classList.toggle("is-related", name !== tableName && relatedNames.has(name));
  });
  const relationText = relations.length
    ? relations.map((relation) => `${relation.from} ${relation.cardinality} ${relation.to}`).join(" · ")
    : "ไม่มี foreign-key path โดยตรงใน serving map";
  $("#map-inspector").innerHTML = `
    <span class="inspector-kicker">${escapeHtml(table.role_th)}</span>
    <strong>${escapeHtml(table.name)} · ${escapeHtml(table.meaning_th)}</strong>
    <small>${escapeHtml(table.grain_th)}</small>
    <span class="inspector-count">${formatNumber(table.live_row_count)}<span>LIVE ROWS</span></span>
    <span class="inspector-relations">PK ${escapeHtml(table.primary_key)} · ${escapeHtml(relationText)}</span>
  `;
}

function renderSchema(data) {
  state.schema = data;
  const byGroup = (group) => data.tables.filter((table) => table.group === group);
  const renderStack = (selector, tables) => {
    $(selector).innerHTML = tables.map(mapTableCard).join("");
  };
  const renderFlow = (selector, tables) => {
    $(selector).innerHTML = tables.map((table, index) => `${index ? `<span class="map-flow-link" aria-hidden="true"><span>1 : N</span></span>` : ""}${mapTableCard(table)}`).join("");
  };

  renderStack("#map-control", byGroup("Control plane"));
  renderStack("#map-operational", byGroup("Operational"));
  renderStack("#map-candidate", byGroup("Candidate staging"));
  renderStack("#map-public", byGroup("Public serving"));
  renderFlow("#map-spatial", byGroup("Spatial serving"));
  renderFlow("#map-housing", byGroup("Housing serving"));
  renderPreviewBlocks(data);
  $("#map-table-total").textContent = formatNumber(data.tables.length);

  document.querySelectorAll("[data-map-table]").forEach((card) => {
    card.addEventListener("click", () => selectMapTable(card.dataset.mapTable));
  });
  selectMapTable(state.selectedTable || "sources");
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
    populatePreviewSources();
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
$("#data-preview-close").addEventListener("click", () => $("#data-preview-dialog").close());
$("#data-preview-dialog").addEventListener("click", (event) => {
  if (event.target === $("#data-preview-dialog")) $("#data-preview-dialog").close();
});
$("#preview-source-filter").addEventListener("change", (event) => {
  state.previewSourceId = event.target.value;
  updatePreviewFilterLabel();
  if (state.schema) renderPreviewBlocks(state.schema);
});
["#search-input", "#group-filter", "#policy-filter", "#connection-filter"].forEach((selector) => {
  $(selector).addEventListener(selector === "#search-input" ? "input" : "change", renderSources);
});

refresh();
window.setInterval(refresh, Number(window.EXPLORER_CONFIG.refreshSeconds || 30) * 1000);
