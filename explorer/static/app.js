const state = {
  overview: null,
  sources: [],
  schema: null,
  selectedTable: null,
  previewSourceId: "",
  artifacts: [],
  artifactVisibleLimit: 36,
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

function policyLabel(policy) {
  return {
    team_approved_public: "มีข้อมูลสาธารณะ · ยังต้องอ่านคำเตือน",
    metadata_only: "มีเฉพาะรายละเอียดแหล่ง",
    restricted_local_only: "เก็บค่าข้อมูลในเครื่องเท่านั้น",
  }[policy] || "ยังไม่ระบุ";
}

function connectionLabel(status) {
  return {
    api_connected: "เชื่อม API แล้ว",
    snapshot_connected: "ใช้ไฟล์ที่บันทึกไว้",
    public_projection: "มีข้อมูลที่คัดและตรวจแล้ว",
    catalog_only: "มีเฉพาะรายชื่อแหล่ง",
    local_only: "เก็บข้อมูลในเครื่อง",
  }[status] || "ยังไม่ทราบวิธีเชื่อม";
}

function artifactGroupLabel(group) {
  return {
    catalog: "รายการข้อมูลหลัก",
    source_insights: "สรุปข้อมูลแต่ละแหล่ง",
    source_coverage: "สถานะทั้ง 28 แหล่ง",
    unmapped_records: "ข้อมูลที่ยังจับคู่จังหวัดไม่ได้",
    housing_spatial_summary: "สรุปข้อมูลแผนที่ที่อยู่อาศัย",
    housing_demand_summary: "สรุปความต้องการที่อยู่อาศัย",
    source_dataset: "ชุดข้อมูลสำหรับหน้าเรียนรู้",
    map: "ข้อมูลแผนที่",
    provincial_briefing: "ข้อมูลสรุปรายจังหวัด",
    executive_summary: "สรุปสำหรับผู้บริหาร",
  }[group] || group;
}

function plainLanguage(value) {
  let text = String(value ?? "");
  const replacements = [
    [/Public snapshot/gi, "ไฟล์ข้อมูลสาธารณะที่บันทึกไว้"],
    [/public aggregate APIs?/gi, "API สาธารณะที่ให้ข้อมูลสรุป"],
    [/public APIs?/gi, "API สาธารณะ"],
    [/Serving Database/gi, "ฐานข้อมูลของ Dashboard"],
    [/Source Insights/gi, "หน้าสรุปข้อมูลต้นทาง"],
    [/Source Coverage/gi, "หน้ารายชื่อแหล่งข้อมูล"],
    [/value dataset/gi, "ชุดข้อมูลที่นำมาแสดงได้"],
    [/local lane/gi, "เครื่องของเรา"],
    [/accepted KPI/gi, "ตัวเลขที่รับรองแล้ว"],
    [/non-geo/gi, "ข้อมูลที่ยังผูกกับพื้นที่ไม่ได้"],
    [/record type/gi, "ประเภทข้อมูล"],
    [/needs_review/gi, "ยังรอตรวจ"],
    [/\bcandidate\b/gi, "ข้อมูลที่ยังรอตรวจ"],
    [/\baggregate\b/gi, "ข้อมูลสรุป"],
    [/\bsnapshot\b/gi, "ไฟล์ที่บันทึกไว้"],
    [/\bmetadata\b/gi, "รายละเอียดของแหล่งข้อมูล"],
    [/\brestricted\b/gi, "เก็บในเครื่อง"],
    [/\brecords?\b/gi, "รายการ"],
    [/\bendpoints?\b/gi, "ช่องทางข้อมูล"],
    [/\bfields?\b/gi, "ช่องข้อมูล"],
    [/\bcontract\b/gi, "รูปแบบข้อมูล"],
    [/\bvalues?\b/gi, "ค่าข้อมูล"],
    [/\bCloud\b/gi, "เว็บไซต์ออนไลน์"],
    [/\bauth\b/gi, "หน้าล็อกอิน"],
    [/\bnull\b/gi, "ค่าว่าง"],
    [/\bKPI\b/gi, "ตัวเลขที่รับรองแล้ว"],
  ];
  replacements.forEach(([pattern, replacement]) => {
    text = text.replace(pattern, replacement);
  });
  return text;
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
  $("#backend-badge").textContent = `${data.database_backend.toUpperCase()} · เชื่อมต่อแล้ว`;
  $("#backend-badge").className = "status-pill connected";
  $("#live-dot").className = "live-dot online";
  $("#live-label").textContent = "เชื่อมฐานข้อมูลแล้ว · แสดงข้อมูลล่าสุด";
}

function sourceRow(source) {
  const targets = source.database_targets
    .map((target) => `<span class="target-chip">${escapeHtml(target)}</span>`)
    .join("");
  const waitingRows = source.operational_candidate_records
    ? `<span class="cell-muted">มี ${formatNumber(source.operational_candidate_records)} แถวที่ยังรอตรวจ</span>`
    : "";
  const endpointInfo = source.endpoint_count
    ? `ช่องทางดึง ${formatNumber(source.endpoint_count)} แห่ง · ใช้งานอัตโนมัติ ${formatNumber(source.runtime_endpoint_count)}`
    : "ยังไม่มีช่องทางดึงข้อมูลในฐานนี้";
  return `
    <tr data-source-id="${escapeHtml(source.source_id)}">
      <td><span class="ordinal">${String(source.ordinal).padStart(2, "0")}</span></td>
      <td>
        <strong class="source-name">${escapeHtml(source.name_th)}</strong>
        <span class="source-id">${escapeHtml(source.source_id)} · ${escapeHtml(source.group)}</span>
        <a class="source-link" href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">${escapeHtml(source.url)} ↗</a>
      </td>
      <td>${escapeHtml(plainLanguage(source.what_we_use_th))}</td>
      <td>${escapeHtml(plainLanguage(source.grain_th))}</td>
      <td>
        <div class="cell-stack">
          <span class="badge ${connectionClass(source.connection_status)}">${escapeHtml(connectionLabel(source.connection_status))}</span>
          <span class="badge ${badgeClass(source)}">${escapeHtml(policyLabel(source.cloud_policy))}</span>
          <span class="cell-muted">${endpointInfo}</span>
          ${waitingRows}
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
    <option value="">ทุกแหล่งข้อมูล</option>
    ${state.sources.map((source) => `<option value="${escapeHtml(source.source_id)}">${String(source.ordinal).padStart(2, "0")} · ${escapeHtml(source.name_th)} — ${escapeHtml(source.url)}</option>`).join("")}
  `;
  select.value = current;
  updatePreviewFilterLabel();
}

function updatePreviewFilterLabel() {
  const source = state.sources.find((item) => item.source_id === state.previewSourceId);
  $("#preview-filter-label").textContent = source
    ? `${source.source_id} · ${source.name_th}`
    : `รวม ${formatNumber(state.sources.length)} แหล่งข้อมูล`;
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
  const countLabel = table.count_mode === "snapshot_contract" ? "รายการที่ตรวจแล้ว" : "แถวในตาราง";
  return `
    <button class="preview-block ${previewTone(table.group)}" type="button" data-preview-table="${escapeHtml(table.name)}">
      <span class="preview-block-head">
        <span><strong>${escapeHtml(table.name)}</strong><small>${escapeHtml(table.role_th)}</small></span>
        <span class="preview-count">${formatNumber(table.live_row_count)}<span>${countLabel}</span></span>
      </span>
      <span class="preview-field-list">${table.key_fields.map((field) => `<span>${escapeHtml(field)}</span>`).join("")}</span>
      <span class="preview-block-foot"><span>${relationCount ? `เชื่อมกับ ${formatNumber(relationCount)} ตาราง` : "ตารางส่วนกลาง"}</span><b>ดูตัวอย่าง →</b></span>
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
  if (value === null || value === undefined) return `<span class="data-null">ไม่มีค่า</span>`;
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
  content.innerHTML = `<div class="preview-empty">กำลังอ่านแถวตัวอย่าง…</div>`;
  dialog.showModal();
  try {
    const query = new URLSearchParams({ limit: "6" });
    if (state.previewSourceId) query.set("source_id", state.previewSourceId);
    const data = await requestJson(`/api/data-preview/${encodeURIComponent(tableName)}?${query}`);
    const rowsHtml = data.rows.length
      ? `<div class="data-sample-wrap"><table class="data-sample-table"><thead><tr>${data.columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead><tbody>${data.rows.map((row) => `<tr>${data.columns.map((column) => `<td>${previewCell(row[column])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
      : `<div class="preview-empty">ตารางนี้ยังไม่มีแถวข้อมูล${data.source_filter_applied ? "สำหรับแหล่งที่เลือก" : ""}</div>`;
    const filterLabel = data.source_filter_applied && selectedSource
      ? `${selectedSource.source_id} · ${selectedSource.name_th}`
      : data.source_filter_requested && !data.source_filter_supported
        ? "ตารางส่วนกลาง · ไม่ได้ผูกกับแหล่งใดแหล่งหนึ่ง"
        : "ทุกแหล่งข้อมูล";
    content.innerHTML = `
      <header class="preview-dialog-head">
        <span class="kicker">ตัวอย่างจากฐานข้อมูล · ดูอย่างเดียว</span>
        <h2>${escapeHtml(data.table)}</h2>
        <p>${escapeHtml(data.meaning_th)}</p>
        <div class="preview-dialog-meta">
          <span>มีในตาราง ${formatNumber(data.physical_row_count)} แถว</span>
          <span>แสดง ${formatNumber(data.sample_size)} แถว</span>
          <span>${escapeHtml(filterLabel)}</span>
          ${data.count_mode === "snapshot_contract" ? `<span>ชุดที่ตรวจแล้วมี ${formatNumber(data.serving_or_contract_count)} รายการ</span>` : ""}
        </div>
      </header>
      ${rowsHtml}
      <p class="preview-safety-note">แสดงเฉพาะช่องที่ปลอดภัย และไม่แสดงชื่อ เบอร์โทร อีเมล หรือข้อมูลก้อนใหญ่</p>
    `;
  } catch (error) {
    console.error(error);
    content.innerHTML = `<div class="preview-empty">อ่านตัวอย่างข้อมูลไม่สำเร็จ</div>`;
  }
}

function artifactBlock(artifact) {
  const province = artifact.province_code ? `จังหวัด ${artifact.province_code}` : "ข้อมูลระดับประเทศ";
  return `
    <button class="artifact-block" type="button" data-artifact-key="${escapeHtml(artifact.artifact_key)}">
      <span class="artifact-block-top">
        <span class="json-file-icon">{ }</span>
        <span class="artifact-group">${escapeHtml(artifactGroupLabel(artifact.artifact_group))}</span>
        <span class="artifact-items">${formatNumber(artifact.item_count)}<small>รายการ</small></span>
      </span>
      <strong>${escapeHtml(artifact.file_name)}</strong>
      <span class="artifact-key">รหัส: ${escapeHtml(artifact.artifact_key)}</span>
      <span class="artifact-source-path">${escapeHtml(artifact.source_path)}</span>
      <span class="artifact-location"><i>DB</i><span>ตาราง public_artifacts <b>→</b> ช่อง payload</span></span>
      <span class="artifact-block-foot"><span>${escapeHtml(province)}</span><b>ดู JSON →</b></span>
    </button>
  `;
}

function filteredArtifacts() {
  const query = $("#artifact-search-input").value.trim().toLowerCase();
  const group = $("#artifact-group-filter").value;
  return state.artifacts.filter((artifact) => {
    const searchable = [
      artifact.file_name,
      artifact.source_path,
      artifact.artifact_key,
      artifact.artifact_group,
      artifact.province_code,
    ].join(" ").toLowerCase();
    return (!query || searchable.includes(query))
      && (!group || artifact.artifact_group === group);
  });
}

function renderArtifacts() {
  const filtered = filteredArtifacts();
  const visible = filtered.slice(0, state.artifactVisibleLimit);
  $("#artifact-blocks").innerHTML = visible.length
    ? visible.map(artifactBlock).join("")
    : `<div class="preview-loading">ไม่พบไฟล์ JSON ที่ตรงกับตัวกรอง</div>`;
  $("#artifact-summary").textContent = `แสดง ${formatNumber(visible.length)} จาก ${formatNumber(filtered.length)} ไฟล์ · ทั้งหมด ${formatNumber(state.artifacts.length)}`;
  $("#artifact-show-more").hidden = visible.length >= filtered.length;
  document.querySelectorAll("[data-artifact-key]").forEach((button) => {
    button.addEventListener("click", () => openArtifactPreview(button.dataset.artifactKey));
  });
}

function populateArtifactGroups() {
  const select = $("#artifact-group-filter");
  const current = select.value;
  const groups = [...new Set(state.artifacts.map((artifact) => artifact.artifact_group).filter(Boolean))];
  select.innerHTML = `<option value="">ทุกกลุ่ม JSON</option>${groups.map((group) => `<option value="${escapeHtml(group)}">${escapeHtml(artifactGroupLabel(group))}</option>`).join("")}`;
  select.value = current;
}

async function openArtifactPreview(artifactKey) {
  const dialog = $("#artifact-preview-dialog");
  const content = $("#artifact-preview-content");
  content.innerHTML = `<div class="preview-empty">กำลังอ่านตัวอย่าง JSON…</div>`;
  dialog.showModal();
  try {
    const query = new URLSearchParams({ artifact_key: artifactKey });
    const data = await requestJson(`/api/artifact-preview?${query}`);
    const prettyJson = JSON.stringify(data.payload_preview, null, 2);
    content.innerHTML = `
      <header class="preview-dialog-head artifact-dialog-head">
        <span class="kicker">ตัวอย่าง JSON จากฐานข้อมูล</span>
        <h2>${escapeHtml(data.file_name)}</h2>
        <p>${escapeHtml(data.source_path)}</p>
        <div class="preview-dialog-meta">
          <span>รหัส: ${escapeHtml(data.artifact_key)}</span>
          <span>${escapeHtml(artifactGroupLabel(data.artifact_group))}</span>
          <span>${formatNumber(data.item_count)} รายการ</span>
          ${data.province_code ? `<span>รหัสจังหวัด ${escapeHtml(data.province_code)}</span>` : `<span>ข้อมูลส่วนกลาง</span>`}
        </div>
      </header>
      <div class="artifact-db-address">
        <span>เก็บอยู่ที่</span>
        <strong>PostgreSQL</strong><b>→</b><strong>${escapeHtml(data.database_table)}</strong><b>→</b><strong>${escapeHtml(data.database_column)}</strong>
        <small>รูปแบบ JSON</small>
      </div>
      <div class="json-preview-wrap"><pre><code>${escapeHtml(prettyJson)}</code></pre></div>
      <p class="preview-safety-note">${data.truncated ? "แสดงเพียงบางส่วนเพื่อให้เปิดได้เร็ว · " : ""}ซ่อนช่องข้อมูลที่ใช้ติดต่อหรือระบุตัวบุคคลแล้ว</p>
    `;
  } catch (error) {
    console.error(error);
    content.innerHTML = `<div class="preview-empty">อ่าน JSON ตัวอย่างไม่สำเร็จ</div>`;
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
    ? relations.map((relation) => relation.label_th).join(" · ")
    : "ตารางนี้ไม่ได้เชื่อมกับตารางอื่นโดยตรง";
  $("#map-inspector").innerHTML = `
    <span class="inspector-kicker">${escapeHtml(table.role_th)}</span>
    <strong>${escapeHtml(table.name)} · ${escapeHtml(table.meaning_th)}</strong>
    <small>${escapeHtml(table.grain_th)}</small>
    <span class="inspector-count">${formatNumber(table.live_row_count)}<span>จำนวนแถว</span></span>
    <span class="inspector-relations">รหัสหลัก: ${escapeHtml(table.primary_key)} · ${escapeHtml(relationText)}</span>
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

function endpointKindLabel(kind) {
  const value = String(kind || "").toLowerCase();
  if (value.includes("ckan")) return "CKAN · คลังชุดข้อมูล";
  if (value.includes("api")) return "API · ขอข้อมูลแบบเป็นระเบียบ";
  if (value.includes("pdf")) return "ไฟล์ PDF";
  if (value.includes("auth") || value.includes("login")) return "ช่องทางที่ต้องล็อกอิน";
  return "หน้าเว็บ";
}

function endpointAccessLabel(status) {
  const value = String(status || "").toLowerCase();
  if (value.includes("200") || value === "public") return "เปิดได้";
  if (value.includes("401") || value.includes("login") || value.includes("auth")) return "ต้องล็อกอิน";
  if (value.includes("error")) return "เปิดไม่สำเร็จในรอบล่าสุด";
  if (value.includes("candidate")) return "พบแล้ว · ยังรอตรวจ";
  return "ยังไม่ระบุ";
}

function runStatusLabel(status) {
  return { complete: "สำเร็จ", failed: "ไม่สำเร็จ" }[status] || status;
}

function openSourceDialog(sourceId) {
  const source = state.sources.find((item) => item.source_id === sourceId);
  if (!source) return;
  const endpointHtml = source.endpoints.length
    ? source.endpoints.map((endpoint) => `
      <div class="endpoint-row">
        <div class="endpoint-meta">
          <strong>${escapeHtml(endpoint.method)}</strong>
          <span class="mini-pill">${escapeHtml(endpointKindLabel(endpoint.kind))}</span>
          <span class="mini-pill">${escapeHtml(endpointAccessLabel(endpoint.access_status))}</span>
          ${endpoint.runtime_enabled ? `<span class="mini-pill">ระบบดึงอัตโนมัติ</span>` : ""}
          ${endpoint.restricted ? `<span class="mini-pill">เก็บในเครื่อง</span>` : ""}
        </div>
        <a href="${escapeHtml(endpoint.url)}" target="_blank" rel="noreferrer">${escapeHtml(endpoint.url)} ↗</a>
      </div>
    `).join("")
    : `<p class="cell-muted">ยังไม่มีช่องทางดึงข้อมูลบันทึกอยู่ในฐานนี้</p>`;
  const runHtml = source.latest_run ? `
    <div class="run-grid">
      <div><span>สถานะ</span><strong>${escapeHtml(runStatusLabel(source.latest_run.status))}</strong></div>
      <div><span>วิธีดึง</span><strong>${escapeHtml(source.latest_run.strategy === "api" ? "API" : plainLanguage(source.latest_run.strategy))}</strong></div>
      <div><span>พบ</span><strong>${formatNumber(source.latest_run.records_seen)}</strong></div>
      <div><span>บันทึก</span><strong>${formatNumber(source.latest_run.records_loaded)}</strong></div>
    </div>
    <p class="cell-muted" style="margin-top:10px">เสร็จเมื่อ ${formatDate(source.latest_run.finished_at || source.latest_run.started_at)}</p>
  ` : `<p class="cell-muted">ยังไม่มีประวัติการดึงในฐานนี้ ข้อมูลที่แสดงอาจมาจากไฟล์ที่บันทึกและตรวจไว้แล้ว</p>`;
  $("#dialog-content").innerHTML = `
    <header class="dialog-title">
      <span class="source-id">${escapeHtml(source.source_id)} · ${escapeHtml(source.group)}</span>
      <h2>${escapeHtml(source.name_th)}</h2>
      <a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">${escapeHtml(source.url)} ↗</a>
      <div class="dialog-badges">
        <span class="badge ${connectionClass(source.connection_status)}">${escapeHtml(connectionLabel(source.connection_status))}</span>
        <span class="badge ${badgeClass(source)}">${escapeHtml(policyLabel(source.cloud_policy))}</span>
      </div>
    </header>
    <div class="detail-grid">
      <section class="detail-box"><h3>ข้อมูลที่เราดึง</h3><p>${escapeHtml(plainLanguage(source.what_we_use_th))}</p></section>
      <section class="detail-box"><h3>1 แถวหมายถึงอะไร</h3><p>${escapeHtml(plainLanguage(source.grain_th))}</p></section>
      <section class="detail-box"><h3>Dashboard นำไปใช้อย่างไร</h3><p>${escapeHtml(plainLanguage(source.dashboard_use_th))}</p></section>
      <section class="detail-box"><h3>ข้อมูลที่ไม่แสดงและข้อควรระวัง</h3><p>${escapeHtml(plainLanguage(source.excluded_th))}</p></section>
      <section class="detail-box wide"><h3>เก็บในตารางใด</h3><div class="target-list">${source.database_targets.map((target) => `<span class="target-chip">${escapeHtml(target)}</span>`).join("")}</div></section>
      <section class="detail-box wide"><h3>ดึงข้อมูลครั้งล่าสุด</h3>${runHtml}</section>
      <section class="detail-box wide"><h3>ช่องทางที่ใช้ดึงข้อมูล (${formatNumber(source.endpoint_count)})</h3><div class="endpoint-list">${endpointHtml}</div></section>
    </div>
  `;
  $("#source-dialog").showModal();
}

async function refresh() {
  try {
    const [overview, sourceData, schema, artifactData] = await Promise.all([
      requestJson("/api/overview"),
      requestJson("/api/sources"),
      requestJson("/api/schema"),
      requestJson("/api/artifacts"),
    ]);
    renderOverview(overview);
    state.sources = sourceData.sources;
    populateGroups();
    populatePreviewSources();
    renderSources();
    renderSchema(schema);
    state.artifacts = artifactData.artifacts;
    populateArtifactGroups();
    renderArtifacts();
    $("#footer-refresh").textContent = `อัปเดตล่าสุด ${formatDate(overview.checked_at)} · ตรวจข้อมูลใหม่ทุก ${window.EXPLORER_CONFIG.refreshSeconds} วินาที`;
  } catch (error) {
    console.error(error);
    $("#live-dot").className = "live-dot offline";
    $("#live-label").textContent = "เชื่อมฐานข้อมูลไม่สำเร็จ";
    $("#backend-badge").textContent = "ไม่ได้เชื่อมต่อ";
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
$("#artifact-preview-close").addEventListener("click", () => $("#artifact-preview-dialog").close());
$("#artifact-preview-dialog").addEventListener("click", (event) => {
  if (event.target === $("#artifact-preview-dialog")) $("#artifact-preview-dialog").close();
});
$("#preview-source-filter").addEventListener("change", (event) => {
  state.previewSourceId = event.target.value;
  updatePreviewFilterLabel();
  if (state.schema) renderPreviewBlocks(state.schema);
});
["#search-input", "#group-filter", "#policy-filter", "#connection-filter"].forEach((selector) => {
  $(selector).addEventListener(selector === "#search-input" ? "input" : "change", renderSources);
});
$("#artifact-search-input").addEventListener("input", () => {
  state.artifactVisibleLimit = 36;
  renderArtifacts();
});
$("#artifact-group-filter").addEventListener("change", () => {
  state.artifactVisibleLimit = 36;
  renderArtifacts();
});
$("#artifact-show-more").addEventListener("click", () => {
  state.artifactVisibleLimit += 36;
  renderArtifacts();
});

refresh();
window.setInterval(refresh, Number(window.EXPLORER_CONFIG.refreshSeconds || 30) * 1000);
