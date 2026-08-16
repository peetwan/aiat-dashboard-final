const detailState = {
  summary: null,
  briefing: null,
  operations: null,
  peopleSections: [],
  visibleBySection: {},
  query: "",
};

const SECTION_ORDER = [
  "area_based",
  "sra",
  "pppconnext",
  "learning_dashboard",
  "apptech_mtr",
  "culture",
  "tourism",
  "city_capital",
  "housing",
];

const FIELD_LABELS = {
  project_group_id: "รหัสกลุ่มโครงการ",
  official_project_id: "Project ID ทางการ",
  project_name: "ชื่อโครงการ",
  fiscal_year: "ปีงบประมาณ",
  research_unit: "หน่วยวิจัย",
  grouping_method: "วิธีจัดกลุ่ม",
  definition_status: "สถานะนิยาม",
  project_status: "สถานะโครงการ",
  budget_status: "สถานะงบประมาณ",
  participant_record_count: "ระเบียนผู้เข้าร่วม",
  business_count: "กลุ่ม/ธุรกิจ",
  businesses: "กลุ่ม/ธุรกิจที่เชื่อมได้",
  geography: "พื้นที่ดำเนินงาน",
  participants: "ผู้เข้าร่วม",
  latest_source_update: "อัปเดตล่าสุดจากต้นทาง",
  record_id: "รหัสระเบียน",
  record_code: "รหัสข้อมูล",
  title: "ชื่อรายการ",
  title_th: "ชื่อรายการ",
  title_en: "ชื่อภาษาอังกฤษ",
  business_name: "ชื่อกลุ่ม/ธุรกิจ",
  district: "อำเภอ/เขต",
  amphoe: "อำเภอ/เขต",
  subdistrict: "ตำบล/แขวง",
  tambon: "ตำบล/แขวง",
  province_name_th: "จังหวัด",
  category: "หมวด",
  cultural_type: "ลักษณะทุนวัฒนธรรม",
  owner_affiliation_name: "หน่วยงานเจ้าของผลงาน",
  description: "รายละเอียด",
  knowledge_technology: "องค์ความรู้/เทคโนโลยี",
  innovation_type: "ประเภทนวัตกรรม",
  trl_level: "TRL",
  srl_level: "SRL",
  innovation_value_baht: "มูลค่านวัตกรรม",
  funding: "แหล่งทุนที่ต้นทางระบุ",
  roi_indicator: "ROI",
  roi_unit: "หน่วย ROI",
  sroi_indicator: "SROI",
  sroi_unit: "หน่วย SROI",
  target_groups: "กลุ่มเป้าหมาย",
  highlights: "จุดเด่น",
  research_leads: "หัวหน้างานวิจัย/ผู้พัฒนา",
  co_researcher_count: "ผู้ร่วมวิจัย",
  ip: "ทรัพย์สินทางปัญญา",
  views_count: "จำนวนเข้าชม",
  areas: "พื้นที่ใช้งาน",
  linked_province_count: "จำนวนจังหวัดที่เชื่อม",
  registered_users: "ผู้ใช้ลงทะเบียน",
  interactions: "การปฏิสัมพันธ์",
  institutes: "สถาบัน",
  metric_label_th: "ตัวชี้วัด",
  value: "ค่า",
  unit: "หน่วย",
  as_of: "ข้อมูล ณ วันที่",
  scope_warning_th: "ขอบเขตการใช้",
  updated_at: "อัปเดตจากต้นทาง",
  fetched_at: "ดึงข้อมูลเมื่อ",
  quality_status: "สถานะคุณภาพ",
  provenance: "ที่มาและร่องรอยข้อมูล",
};

const STATUS_LABELS = {
  available: "มีข้อมูล",
  limited: "มีบางส่วน",
  not_available: "ยังไม่มีข้อมูล",
  source_has_no_record_for_province: "ไม่พบระเบียนของจังหวัดนี้",
  not_province_scoped: "ไม่ใช่ข้อมูลระดับจังหวัด",
  metadata_only: "มีเฉพาะ metadata",
  blocked: "ไม่เผยแพร่ค่า",
  candidate_needs_review: "Candidate / Needs review",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatNumber(value, digits = 0) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return new Intl.NumberFormat("th-TH", { maximumFractionDigits: digits }).format(number);
}

function formatMoney(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${formatNumber(number)} บาท` : "ไม่ระบุ";
}

function formatDate(value) {
  if (!value) return "ไม่ระบุ";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("th-TH", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function safeExternalUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function fieldLabel(key) {
  return FIELD_LABELS[key] || key.replaceAll("_", " ");
}

function scalarText(value) {
  if (value === null || value === undefined || value === "") return "ไม่ระบุ";
  if (typeof value === "boolean") return value ? "ใช่" : "ไม่ใช่";
  if (typeof value === "number") return formatNumber(value, 2);
  if (Array.isArray(value)) {
    if (!value.length) return "ไม่ระบุ";
    return value.map((entry) => scalarText(entry)).join(" · ");
  }
  if (typeof value === "object") {
    return Object.entries(value)
      .filter(([, nested]) => nested !== null && nested !== "" && nested !== undefined)
      .map(([key, nested]) => `${fieldLabel(key)}: ${scalarText(nested)}`)
      .join(" · ") || "ไม่ระบุ";
  }
  return String(value);
}

function searchableText(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return Object.values(value).map(searchableText).join(" ");
  return String(value);
}

async function fetchJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  return response.json();
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

function renderKpis(summary, briefing) {
  const portfolio = summary.research_portfolio || {};
  const culture = briefing.sections?.culture?.total_records || 0;
  const cards = [
    [portfolio.project_count, "กลุ่มโครงการที่เชื่อมได้", "จัดกลุ่มชั่วคราว · ยังไม่มี Project ID ทางการ"],
    [portfolio.participant_record_count, "ระเบียนผู้เข้าร่วม", "เป็น participant/business grain ไม่ใช่จำนวนโครงการ"],
    [portfolio.innovation_count, "นวัตกรรมพร้อมใช้", "ผลงานที่ทะเบียนเชื่อมกับจังหวัด"],
    [culture, "ทุนวัฒนธรรม", "จำนวนระเบียนที่บันทึกในพื้นที่"],
  ];
  document.getElementById("executiveKpis").innerHTML = cards.map(([value, label, note]) => `
    <article class="kpi-card"><span>${escapeHtml(label)}</span><strong>${formatNumber(value || 0)}</strong><small>${escapeHtml(note)}</small></article>
  `).join("");
}

function renderAnswerBoard(summary) {
  const observations = summary.readout?.observations || [];
  const availableStages = (summary.decision_chain || []).filter((row) => row.status === "available");
  const known = [
    ...observations.map((row) => `<p><strong>${escapeHtml(row.label_th)}</strong>${escapeHtml(row.text_th)}</p>`),
    ...availableStages.map((row) => `<p><strong>${escapeHtml(row.label_th)}</strong>${escapeHtml(row.note_th || "มีหลักฐานเชื่อมระดับจังหวัด")}</p>`),
  ];
  const gaps = [
    ...(summary.research_portfolio?.data_gaps_th || []).map((text) => `<p>${escapeHtml(text)}</p>`),
    ...(summary.missing_dimensions || []).map((row) => `<p><strong>${escapeHtml(row.label_th)}</strong>ยังไม่มีข้อมูลสาธารณะที่เชื่อมจังหวัดนี้</p>`),
  ];
  document.getElementById("knownAnswers").innerHTML = known.length ? known.join("") : "<p>ยังไม่มีข้อสรุประดับจังหวัดที่ผ่านเงื่อนไข</p>";
  document.getElementById("missingAnswers").innerHTML = gaps.length ? gaps.join("") : "<p>ไม่พบช่องว่างที่ระบบระบุ</p>";
}

function renderDecisionChain(summary) {
  document.getElementById("detailDecisionChain").innerHTML = (summary.decision_chain || []).map((stage, index) => {
    const metric = stage.metrics?.[0]?.display_value || "—";
    return `<article class="chain-stage ${escapeHtml(stage.status || "not_available")}"><small>${String(index + 1).padStart(2, "0")}</small><strong>${escapeHtml(stage.label_th)}</strong><b>${escapeHtml(metric)}</b><p>${escapeHtml(stage.note_th || "")}</p></article>`;
  }).join("");
}

function renderExecutiveReadout(summary) {
  const observations = summary.readout?.observations || [];
  const rules = summary.data_quality_overview?.rules_th || [];
  document.getElementById("executiveReadout").innerHTML = `
    <article class="readout-card"><span>ข้อค้นพบจากข้อมูล</span>${observations.length ? observations.map((row) => `<p><strong>${escapeHtml(row.label_th)}</strong>${escapeHtml(row.text_th)}</p>`).join("") : "<p>ยังไม่มี observation</p>"}</article>
    <article class="readout-card"><span>กติกาการอ่านตัวเลข</span>${rules.map((rule) => `<p>${escapeHtml(rule)}</p>`).join("")}</article>
  `;
}

function renderResearchSummary(summary) {
  const portfolio = summary.research_portfolio || {};
  const funding = portfolio.funding || {};
  const stats = [
    [portfolio.project_count, "กลุ่มโครงการ"],
    [portfolio.university_count, "มหาวิทยาลัย"],
    [portfolio.district_count, "อำเภอที่เชื่อม"],
    [portfolio.business_count, "กลุ่ม/ธุรกิจ"],
    [portfolio.innovation_count, "นวัตกรรม"],
  ];
  document.getElementById("researchSummary").innerHTML = `
    <div class="summary-grid">${stats.map(([value, label]) => `<article><span>${escapeHtml(label)}</span><strong>${formatNumber(value || 0)}</strong><small>Candidate</small></article>`).join("")}</div>
    <div class="funding-panel">
      <article><span>ทุนที่ระบุในนวัตกรรมซึ่งเชื่อมจังหวัด</span><strong>${formatMoney(funding.pmua_amount_baht)}</strong><small>${formatNumber(funding.pmua_funded_innovation_count || 0)} นวัตกรรม · ${formatNumber(funding.pmua_funding_entry_count || 0)} รายการทุน</small></article>
      <article><span>มูลค่านวัตกรรมที่ระบุ</span><strong>${formatMoney(funding.innovation_value_baht_total)}</strong><small>${formatNumber(funding.innovation_value_known_entries || 0)} รายการที่มีตัวเลข</small></article>
    </div>
    <p class="warning-note">${escapeHtml(funding.note_th || "ตัวเลขทุนนี้ไม่ใช่งบจัดสรรหรือยอดเบิกจ่ายของจังหวัด")}</p>
    <details class="gap-list"><summary>ช่องว่างข้อมูลโครงการและงบ ${formatNumber(portfolio.data_gaps_th?.length || 0)} ข้อ</summary><ul>${(portfolio.data_gaps_th || []).map((text) => `<li>${escapeHtml(text)}</li>`).join("")}</ul></details>
  `;
}

function recordTitle(item, fallback) {
  return item.business_name || item.title || item.title_th || item.project_name || item.metric_label_th || item.name_th || item.record_code || fallback;
}

function recordMeta(item) {
  return [item.fiscal_year, item.research_unit, item.category, item.innovation_type, item.district || item.amphoe, item.subdistrict || item.tambon]
    .filter((value) => value !== null && value !== undefined && value !== "")
    .slice(0, 4);
}

function recordDescription(item) {
  const value = item.description || item.scope_warning_th || item.knowledge_technology || item.owner_affiliation_name || "";
  return value.length > 240 ? `${value.slice(0, 237).trim()}…` : value;
}

function renderFieldList(item) {
  const hiddenKeys = new Set(["title", "title_th", "source_url"]);
  const fields = Object.entries(item).filter(([key]) => !hiddenKeys.has(key));
  return `<div class="field-list">${fields.map(([key, value]) => `<p><span>${escapeHtml(fieldLabel(key))}</span><strong>${escapeHtml(scalarText(value))}</strong></p>`).join("")}</div>`;
}

function renderRecordCard(item, fallback = "รายการข้อมูล") {
  const sourceUrl = safeExternalUrl(item.source_url || item.endpoint_url || item.provenance?.endpoint_url);
  return `<article class="record-card">
    <h4>${escapeHtml(recordTitle(item, fallback))}</h4>
    <div class="record-meta">${recordMeta(item).map((value) => `<span>${escapeHtml(value)}</span>`).join("")}</div>
    ${recordDescription(item) ? `<p>${escapeHtml(recordDescription(item))}</p>` : ""}
    <details><summary>ดูทุก field ของรายการนี้</summary>${renderFieldList(item)}</details>
    ${sourceUrl ? `<a class="record-source" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noreferrer">เปิดหลักฐานต้นทาง ↗</a>` : ""}
  </article>`;
}

function renderResearchSection(targetId, section, emptyText) {
  const target = document.getElementById(targetId);
  const items = section?.items || [];
  target.innerHTML = `<div class="subsection-head"><h3>${escapeHtml(section?.title_th || emptyText)}</h3><span>${formatNumber(section?.total_records || items.length)} รายการ</span></div>
    ${items.length ? `<div class="record-grid">${items.map((item) => renderRecordCard(item, emptyText)).join("")}</div>` : `<p class="empty-block">${escapeHtml(emptyText)} — ต้นทางยังไม่มีระเบียนที่เชื่อมจังหวัดนี้</p>`}`;
}

function renderResearch(briefing, summary) {
  renderResearchSummary(summary);
  renderResearchSection("projectRecords", briefing.sections?.project_master, "โครงการ");
  renderResearchSection("innovationRecords", briefing.sections?.innovation, "นวัตกรรม");
  renderResearchSection("requirementRecords", briefing.sections?.requirements, "โจทย์หรือความต้องการจากพื้นที่");
}

function renderPeopleSections() {
  const container = document.getElementById("peopleSections");
  const query = detailState.query.trim().toLocaleLowerCase("th-TH");
  container.innerHTML = detailState.peopleSections.map(([key, section]) => {
    const items = section.items || [];
    const filtered = query ? items.filter((item) => searchableText(item).toLocaleLowerCase("th-TH").includes(query)) : items;
    const visible = detailState.visibleBySection[key] || 12;
    const shown = filtered.slice(0, visible);
    const remaining = Math.max(0, filtered.length - shown.length);
    return `<section class="data-block" data-section="${escapeHtml(key)}">
      <header><h3>${escapeHtml(section.title_th || key)}</h3><span>${query ? `พบ ${formatNumber(filtered.length)} จาก ${formatNumber(items.length)}` : `${formatNumber(section.total_records ?? items.length)} รายการ`} · ${escapeHtml(STATUS_LABELS[section.status] || section.status || "ไม่ระบุ")}</span></header>
      ${shown.length ? `<div class="record-grid">${shown.map((item) => renderRecordCard(item, section.title_th)).join("")}</div>` : `<p class="empty-block">${query && items.length ? "ไม่พบรายการที่ตรงกับคำค้น" : "ต้นทางไม่มีระเบียนที่เชื่อมจังหวัดนี้"}</p>`}
      ${remaining ? `<button class="load-more" type="button" data-load-section="${escapeHtml(key)}">ดูเพิ่มอีก ${formatNumber(Math.min(24, remaining))} รายการ · เหลือ ${formatNumber(remaining)}</button>` : ""}
    </section>`;
  }).join("");
}

function setupPeople(briefing) {
  detailState.peopleSections = SECTION_ORDER.map((key) => [key, briefing.sections?.[key]])
    .filter(([, section]) => section);
  detailState.peopleSections.forEach(([key]) => { detailState.visibleBySection[key] = 12; });
  renderPeopleSections();
  document.getElementById("peopleSearch").addEventListener("input", (event) => {
    detailState.query = event.target.value;
    renderPeopleSections();
  });
  document.getElementById("peopleSections").addEventListener("click", (event) => {
    const button = event.target.closest("[data-load-section]");
    if (!button) return;
    const key = button.dataset.loadSection;
    detailState.visibleBySection[key] = (detailState.visibleBySection[key] || 12) + 24;
    renderPeopleSections();
  });
}

function renderDimensions(summary) {
  const dimensions = summary.dimensions || [];
  document.getElementById("detailDimensions").innerHTML = dimensions.length ? dimensions.map((dimension) => `
    <article class="dimension-card">
      <header><h3>${escapeHtml(dimension.label_th)}</h3><p>${escapeHtml(dimension.summary_th || "")}</p></header>
      ${(dimension.metrics || []).map((metric) => `<div class="breakdown"><h4>${escapeHtml(metric.label_th)}</h4><div class="bar-row"><span>${escapeHtml(metric.benchmark_label_th || "ค่าจังหวัด")}</span><div class="bar-track"><i style="width:100%"></i></div><strong>${escapeHtml(metric.display_value || scalarText(metric.value))}</strong></div></div>`).join("")}
      ${(dimension.breakdowns || []).map((breakdown) => {
        const items = breakdown.items || [];
        const max = Math.max(...items.map((item) => Number(item.share_pct ?? item.value) || 0), 1);
        return `<div class="breakdown"><h4>${escapeHtml(breakdown.label_th)}</h4>${items.map((item) => {
          const value = Number(item.share_pct ?? item.value) || 0;
          return `<div class="bar-row"><span title="${escapeHtml(item.label_th)}">${escapeHtml(item.label_th)}</span><div class="bar-track"><i style="width:${Math.max(2, value / max * 100)}%"></i></div><strong>${item.display_value ? escapeHtml(item.display_value) : `${formatNumber(item.value, 2)}${item.share_pct !== undefined ? ` · ${formatNumber(item.share_pct, 1)}%` : ""}`}</strong></div>`;
        }).join("")}${breakdown.note_th ? `<p>${escapeHtml(breakdown.note_th)}</p>` : ""}</div>`;
      }).join("")}
      ${(dimension.highlights || []).length ? `<details class="gap-list"><summary>รายการตัวอย่าง ${formatNumber(dimension.highlights.length)}</summary><ul>${dimension.highlights.map((item) => `<li><strong>${escapeHtml(item.title_th)}</strong> — ${escapeHtml(item.detail_th || "")}</li>`).join("")}</ul></details>` : ""}
    </article>
  `).join("") : "<p class='empty-block'>ยังไม่มีมิติที่แสดงได้</p>";
  const missing = summary.missing_dimensions || [];
  document.getElementById("missingDimensions").innerHTML = `<strong>มิติที่ยังไม่มีข้อมูลสาธารณะสำหรับจังหวัดนี้</strong><div>${missing.length ? missing.map((row) => `<span>${escapeHtml(row.label_th)}</span>`).join("") : "<span>ไม่มีช่องว่างที่ระบบระบุ</span>"}</div>`;
}

function renderSources(summary) {
  const quality = summary.data_quality_overview || {};
  document.getElementById("detailQuality").innerHTML = `
    <div class="quality-score"><strong>${formatNumber(quality.accepted_source_count || 0)}/${formatNumber(quality.public_source_count || 0)}</strong><span>แหล่งที่ผ่าน accepted</span></div>
    <div class="quality-copy"><h3>${escapeHtml(STATUS_LABELS[quality.status] || "Candidate / Needs review")}</h3><p>มี as_of ชัดเจน ${formatNumber(quality.sources_with_explicit_as_of || 0)} แหล่ง · ไม่มี as_of ${formatNumber(quality.sources_without_explicit_as_of || 0)} แหล่ง · ดึงล่าสุดที่สังเกต ${escapeHtml(formatDate(quality.latest_observed_fetch))}</p></div>`;
  document.getElementById("detailSources").innerHTML = (summary.source_coverage || []).map((source) => {
    const url = safeExternalUrl(source.url);
    return `<details class="source-row"><summary><div><h3>${escapeHtml(source.name_th)}</h3><small>${escapeHtml(source.source_id)} · ${escapeHtml(source.acquisition_mode || "ไม่ระบุวิธีดึง")}</small></div><span class="status-pill">${escapeHtml(STATUS_LABELS[source.status] || source.status || "ไม่ระบุ")}</span><strong class="source-count">${source.records === null || source.records === undefined ? "—" : formatNumber(source.records)} ระเบียน</strong></summary><div class="source-body"><p><span>ระดับข้อมูล · </span>${escapeHtml(source.data_grain_th || "ไม่ระบุ")}</p><p><span>as_of · </span>${escapeHtml(source.observed_as_of || "ไม่ระบุ")} · <span>fetched_at · </span>${escapeHtml(source.observed_fetched_at ? formatDate(source.observed_fetched_at) : "ไม่ระบุ")}</p><p>${escapeHtml(source.note_th || source.source_note_th || source.quality_label_th || "")}</p>${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">เปิดแหล่งข้อมูล ↗</a>` : ""}</div></details>`;
  }).join("");
}

function renderOperations(operations) {
  const summary = operations.summary || {};
  const scheduler = operations.scheduler || {};
  const audit = operations.last_connectivity_audit || {};
  document.getElementById("operationsStatus").innerHTML = `
    <div class="ops-overview">
      <article><span>Connector ที่ทดสอบสด</span><strong>${formatNumber(audit.successful_connectors || 0)}/${formatNumber(audit.configured_connectors || 0)}</strong></article>
      <article><span>Candidate records ที่เห็น</span><strong>${formatNumber(audit.records_seen_total || 0)}</strong></article>
      <article><span>ดึงอัตโนมัติบน Production</span><strong>${summary.automatic_refresh_enabled ? "เปิด" : "ยังไม่เปิด"}</strong></article>
    </div>
    <p class="ops-warning"><strong>${escapeHtml(scheduler.status_th || "สถานะ scheduler ไม่ระบุ")}</strong> · ${escapeHtml(scheduler.reason_th || "")}</p>
    <div class="ops-pipeline">${(operations.pipeline || []).map((stage) => `<article class="ops-step"><b>${escapeHtml(stage.stage)}</b><span>${escapeHtml(stage.rule_th)}</span></article>`).join("")}</div>
    <div class="ops-audit"><h3>ผลตรวจการเชื่อมต่อครั้งล่าสุด · ${escapeHtml(formatDate(audit.audited_at))}</h3><div class="ops-table">${(audit.results || []).map((row) => `<div class="ops-row"><span>${escapeHtml(row.source_id)}</span><strong>${formatNumber(row.records_seen)} records</strong><span>${escapeHtml(row.note_th)}</span></div>`).join("")}</div></div>
    <a class="ops-link" href="/docs" target="_blank" rel="noreferrer">ดู Public API contract ↗</a>`;
}

function renderPage(summary, briefing, operations) {
  detailState.summary = summary;
  detailState.briefing = briefing;
  detailState.operations = operations;
  setText("detailCoverage", `เชื่อม ${formatNumber(summary.coverage?.available_source_count || 0)} จาก ${formatNumber(summary.coverage?.public_source_count || 0)} แหล่งสาธารณะ`);
  setText("detailGenerated", `สร้างชุดข้อมูล ${formatDate(summary.generated_at)}`);
  renderKpis(summary, briefing);
  renderAnswerBoard(summary);
  renderDecisionChain(summary);
  renderExecutiveReadout(summary);
  renderResearch(briefing, summary);
  setupPeople(briefing);
  renderDimensions(summary);
  renderSources(summary);
  renderOperations(operations);
  document.getElementById("detailLoading").hidden = true;
  document.getElementById("detailContent").hidden = false;
}

async function loadDetail() {
  const code = document.body.dataset.provinceCode;
  document.getElementById("detailError").hidden = true;
  document.getElementById("detailLoading").hidden = false;
  document.getElementById("detailContent").hidden = true;
  try {
    const [summary, briefing, operations] = await Promise.all([
      fetchJson(`/api/public/v1/provinces/${encodeURIComponent(code)}/summary`),
      fetchJson(`/api/public/v1/provinces/${encodeURIComponent(code)}/briefing`),
      fetchJson("/api/public/v1/operations"),
    ]);
    renderPage(summary, briefing, operations);
  } catch (error) {
    console.error("Province detail load failed", error);
    document.getElementById("detailLoading").hidden = true;
    document.getElementById("detailError").hidden = false;
  }
}

document.getElementById("retryDetail").addEventListener("click", loadDetail);
loadDetail();
