const detailState = {
  summary: null,
  briefing: null,
  operations: null,
  peopleSections: [],
  visibleBySection: {},
  activePeopleSection: "all",
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

const SECTION_LABELS = {
  area_based: "ผู้เข้าร่วมโครงการ",
  sra: "สถานการณ์พื้นที่",
  pppconnext: "ครัวเรือนและทุนดำรงชีพ",
  learning_dashboard: "ธุรกิจชุมชน",
  apptech_mtr: "กิจกรรมแพลตฟอร์ม",
  culture: "ทุนวัฒนธรรม",
  tourism: "ท่องเที่ยว",
  city_capital: "ทุนเมือง",
  housing: "ที่อยู่อาศัย",
};

const FIELD_LABELS = {
  official_project_id: "Project ID ทางการ",
  fiscal_year: "ปีงบประมาณ",
  research_unit: "หน่วยวิจัย",
  definition_status: "สถานะนิยาม",
  project_status: "สถานะโครงการ",
  budget_status: "สถานะงบประมาณ",
  participant_record_count: "ระเบียนผู้เข้าร่วม",
  business_count: "กลุ่ม/ธุรกิจ",
  businesses: "กลุ่ม/ธุรกิจที่เชื่อมได้",
  geography: "พื้นที่ดำเนินงาน",
  latest_source_update: "อัปเดตล่าสุดจากต้นทาง",
  category: "หมวด",
  cultural_type: "ลักษณะทุนวัฒนธรรม",
  owner_affiliation_name: "หน่วยงานเจ้าของผลงาน",
  innovation_type: "ประเภทนวัตกรรม",
  trl_level: "ระดับความพร้อมเทคโนโลยี",
  srl_level: "ระดับความพร้อมสังคม",
  innovation_value_baht: "มูลค่านวัตกรรม",
  funding: "แหล่งทุนที่ต้นทางระบุ",
  target_groups: "กลุ่มเป้าหมาย",
  research_leads: "สังกัดนักวิจัย/ผู้พัฒนา",
  ip: "ทรัพย์สินทางปัญญา",
  areas: "พื้นที่ใช้งาน",
  linked_province_count: "จังหวัดที่เชื่อม",
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
  district: "อำเภอ/เขต",
  amphoe: "อำเภอ/เขต",
  subdistrict: "ตำบล/แขวง",
  tambon: "ตำบล/แขวง",
};

const STATUS_LABELS = {
  available: "มีข้อมูล",
  limited: "มีบางส่วน",
  not_available: "ยังไม่มีข้อมูล",
  source_has_no_record_for_province: "ไม่พบข้อมูลจังหวัดนี้",
  not_province_scoped: "ไม่ใช่ข้อมูลระดับจังหวัด",
  metadata_only: "มีเฉพาะข้อมูลอธิบาย",
  blocked: "ไม่เผยแพร่ค่า",
  candidate_needs_review: "Candidate · รอตรวจรับรอง",
  projected_from_source: "สรุปจากต้นทาง",
};

const GENERIC_DETAIL_KEYS = [
  "metric_label_th",
  "value",
  "unit",
  "as_of",
  "scope_warning_th",
  "registered_users",
  "interactions",
  "institutes",
  "category",
  "cultural_type",
  "district",
  "amphoe",
  "subdistrict",
  "tambon",
  "updated_at",
  "fetched_at",
  "quality_status",
];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return new Intl.NumberFormat("th-TH", { maximumFractionDigits: digits }).format(number);
}

function formatMoney(value) {
  if (value === null || value === undefined || value === "") return "ไม่ระบุ";
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

function hasValue(value) {
  return value !== null && value !== undefined && value !== "";
}

function preferredObjectText(value) {
  if (!value || typeof value !== "object") return "";
  const preferred = [
    value.label_th,
    value.name_th,
    value.name,
    value.title_th,
    value.title,
    value.business_name,
    value.funder,
    value.amount_text,
    value.district,
    value.amphoe,
    value.subdistrict,
    value.tambon,
    value.province,
    value.amount_baht,
    value.value,
  ].filter(hasValue);
  if (preferred.length) return preferred.map((item) => String(item)).join(" · ");
  return Object.values(value)
    .filter((item) => ["string", "number"].includes(typeof item) && hasValue(item))
    .slice(0, 4)
    .join(" · ");
}

function humanValue(value) {
  if (!hasValue(value)) return "ไม่ระบุ";
  if (typeof value === "boolean") return value ? "ใช่" : "ไม่ใช่";
  if (typeof value === "number") return formatNumber(value, 2);
  if (Array.isArray(value)) {
    if (!value.length) return "ไม่ระบุ";
    const items = value.map((item) => (typeof item === "object" ? preferredObjectText(item) : String(item))).filter(Boolean);
    const visible = items.slice(0, 12).join(" · ");
    return items.length > 12 ? `${visible} · และอีก ${formatNumber(items.length - 12)} รายการ` : visible;
  }
  if (typeof value === "object") return preferredObjectText(value) || "มีข้อมูลจากต้นทาง";
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
  const culture = briefing.sections?.culture?.total_records;
  const demand = briefing.sections?.housing?.demand_record_total;
  const metrics = [
    [portfolio.project_count, "กลุ่มโครงการ", "จัดกลุ่มเบื้องต้น"],
    [portfolio.participant_record_count, "ระเบียนผู้เข้าร่วม", "ไม่ใช่จำนวนโครงการ"],
    [portfolio.innovation_count, "นวัตกรรม", "ผลงานที่เชื่อมจังหวัด"],
    [culture, "ทุนวัฒนธรรม", "ระเบียนที่บันทึกในพื้นที่"],
    [demand, "คำตอบ Housing demand", "ผู้ตอบที่อาศัยในจังหวัด ไม่ใช่ประชากร"],
  ];
  document.getElementById("executiveKpis").innerHTML = metrics.map(([value, label, note]) => `
    <article class="metric-item">
      <span>${escapeHtml(label)}</span>
      <strong>${formatNumber(value)}</strong>
      <small>${escapeHtml(note)}</small>
    </article>
  `).join("");
}

function renderHousingDemand(briefing) {
  const target = document.getElementById("housingDemandPanel");
  const demand = briefing.sections?.housing?.demand_summary;
  if (!target) return;
  if (!demand || !Number(demand.respondents_living)) {
    target.innerHTML = "";
    return;
  }
  const single = demand.single_choice_distributions || {};
  const ranked = demand.ranked_choice_distributions || {};
  const distributions = [
    single.future_housing_demand,
    single.intended_housing_type,
    single.preferred_price_range,
    single.preferred_price_range_per_month,
    single.urgency_of_housing_purchase_rent,
    ranked.disaster_prevention,
  ].filter(Boolean);
  const futureAnswered = single.future_housing_demand?.answered || 0;
  target.innerHTML = `
    <article class="demand-panel">
      <header class="demand-heading">
        <div><span>Housing demand</span><h3>ความต้องการที่อยู่อาศัยของผู้ตอบในจังหวัด</h3></div>
        <p>สรุปจากแบบสำรวจที่ตัด source id และตรวจชื่อ เบอร์โทร อีเมลแล้ว</p>
      </header>
      <div class="demand-facts">
        <article><span>ผู้ตอบที่อาศัยในจังหวัด</span><strong>${formatNumber(demand.respondents_living)}</strong><small>คำตอบแบบสำรวจ</small></article>
        <article><span>เลือกจังหวัดนี้เป็นพื้นที่ที่ต้องการ</span><strong>${formatNumber(demand.respondents_preferring_destination)}</strong><small>คำตอบที่ระบุจังหวัดเป้าหมาย</small></article>
        <article><span>ตอบคำถามความต้องการอนาคต</span><strong>${formatNumber(futureAnswered)}</strong><small>ไม่ใช่จำนวนประชากรจังหวัด</small></article>
      </div>
      <div class="demand-charts">
        ${distributions.map((distribution) => `
          <figure class="chart-panel">
            <figcaption><span>${distribution.mention_count ? "การถูกเลือกใน 5 อันดับ" : `${formatNumber(distribution.answered)} คำตอบ`}</span><strong>${escapeHtml(distribution.label_th)}</strong></figcaption>
            <div>${chartRows((distribution.items || []).slice(0, 8))}</div>
            ${distribution.share_basis_th ? `<p class="chart-note">${escapeHtml(distribution.share_basis_th)}</p>` : ""}
          </figure>`).join("")}
      </div>
      <p class="demand-note">ค่าทั้งหมดเป็นสัดส่วนในกลุ่มผู้ตอบแบบสำรวจของจังหวัด ใช้ดูรูปแบบความต้องการ ไม่ใช้แทนประชากรหรือครัวเรือนทั้งหมด</p>
    </article>`;
}

function renderExecutiveReadout(summary) {
  const observations = summary.readout?.observations || [];
  document.getElementById("executiveReadout").innerHTML = observations.length
    ? observations.map((item, index) => `
      <div class="insight-item">
        <span>${String(index + 1).padStart(2, "0")}</span>
        <div><strong>${escapeHtml(item.label_th)}</strong><p>${escapeHtml(item.text_th)}</p></div>
      </div>
    `).join("")
    : `<div class="insight-empty"><strong>ยังสรุปแนวโน้มไม่ได้</strong><p>ข้อมูลที่เชื่อมจังหวัดนี้ยังไม่พอสำหรับข้อสังเกต</p></div>`;
}

function renderDecisionChain(summary) {
  const stages = summary.decision_chain || [];
  document.getElementById("detailDecisionChain").innerHTML = stages.map((stage) => {
    const metric = stage.metrics?.map((item) => item.display_value).filter(Boolean).join(" · ");
    return `
      <div class="journey-step ${escapeHtml(stage.status || "not_available")}">
        <i aria-hidden="true"></i>
        <div>
          <span>${escapeHtml(stage.label_th)}</span>
          <strong>${escapeHtml(metric || STATUS_LABELS[stage.status] || "ยังไม่มีข้อมูล")}</strong>
          <p>${escapeHtml(stage.note_th || "")}</p>
        </div>
      </div>`;
  }).join("");
}

function renderExecutiveGaps(summary) {
  const portfolioGaps = summary.research_portfolio?.data_gaps_th || [];
  const missingDimensions = summary.missing_dimensions || [];
  const total = portfolioGaps.length + missingDimensions.length;
  document.getElementById("executiveGaps").innerHTML = total ? `
    <details class="gap-disclosure">
      <summary><span>ข้อมูลที่ยังตอบไม่ได้</span><strong>${formatNumber(total)} ประเด็น</strong></summary>
      <div class="gap-columns">
        ${portfolioGaps.length ? `<div><h3>โครงการและงบ</h3><ul>${portfolioGaps.map((text) => `<li>${escapeHtml(text)}</li>`).join("")}</ul></div>` : ""}
        ${missingDimensions.length ? `<div><h3>มิติที่ยังไม่มีข้อมูลจังหวัด</h3><ul>${missingDimensions.map((row) => `<li><strong>${escapeHtml(row.label_th)}</strong>${row.note_th ? ` — ${escapeHtml(row.note_th)}` : ""}</li>`).join("")}</ul></div>` : ""}
      </div>
    </details>` : "";
}

function chartRows(items, { valueKey = "value", showShare = true } = {}) {
  const values = items.map((item) => Number(item.share_pct ?? item[valueKey]) || 0);
  const max = Math.max(...values, 1);
  return items.map((item, index) => {
    const raw = values[index];
    const width = raw <= 0 ? 0 : Math.max(2, raw / max * 100);
    const display = item.display_value
      || (showShare && item.share_pct !== undefined
        ? `${formatNumber(item[valueKey], 1)} · ${formatNumber(item.share_pct, 1)}%`
        : formatNumber(item[valueKey], 1));
    const aria = `${item.label_th} ${display}`;
    return `
      <div class="chart-row" role="img" aria-label="${escapeHtml(aria)}">
        <div class="chart-row-label"><span>${escapeHtml(item.label_th)}</span><strong>${escapeHtml(display)}</strong></div>
        <div class="chart-track"><i style="--bar-width:${width.toFixed(1)}%"></i></div>
      </div>`;
  }).join("");
}

function renderResearchSummary(summary) {
  const portfolio = summary.research_portfolio || {};
  const funding = portfolio.funding || {};
  const trl = portfolio.trl_distribution || [];
  const innovationCount = Number(portfolio.innovation_count) || 0;
  const outcome = portfolio.outcome_coverage || {};
  const outcomeRows = [
    { label_th: "มีข้อมูลทรัพย์สินทางปัญญา", value: outcome.ip_records || 0 },
    { label_th: "มีข้อมูล ROI", value: outcome.roi_records || 0 },
    { label_th: "มีข้อมูล SROI", value: outcome.sroi_records || 0 },
  ].map((item) => ({
    ...item,
    display_value: `${formatNumber(item.value)}/${formatNumber(innovationCount)} รายการ`,
  }));
  document.getElementById("researchSummary").innerHTML = `
    <div class="portfolio-summary">
      <div class="portfolio-facts">
        <p class="panel-label">ขอบเขตผลงาน</p>
        <div>
          <span><strong>${formatNumber(portfolio.university_count)}</strong> มหาวิทยาลัย</span>
          <span><strong>${formatNumber(portfolio.district_count)}</strong> อำเภอที่เชื่อม</span>
          <span><strong>${formatNumber(portfolio.business_count)}</strong> กลุ่ม/ธุรกิจ</span>
        </div>
        <p>${escapeHtml(portfolio.scope_note_th || "")}</p>
      </div>
      <div class="money-readout">
        <article>
          <span>ทุนที่ระบุในนวัตกรรม</span>
          <strong>${formatMoney(funding.pmua_amount_baht)}</strong>
          <small>${formatNumber(funding.pmua_funded_innovation_count)} นวัตกรรมที่มีข้อมูลทุน</small>
        </article>
        <article>
          <span>มูลค่านวัตกรรมที่ระบุ</span>
          <strong>${formatMoney(funding.innovation_value_baht_total)}</strong>
          <small>${formatNumber(funding.innovation_value_known_entries)} รายการที่มีตัวเลข</small>
        </article>
      </div>
    </div>
    <p class="funding-note">${escapeHtml(funding.note_th || "ตัวเลขนี้ไม่ใช่งบจัดสรรหรือยอดเบิกจ่ายของจังหวัด")}</p>
    <div class="research-charts">
      <figure class="chart-panel">
        <figcaption><span>ความพร้อมของนวัตกรรม</span><strong>ระดับ TRL</strong></figcaption>
        <div>${trl.length ? chartRows(trl) : `<p class="empty-chart">ยังไม่มีข้อมูล TRL</p>`}</div>
      </figure>
      <figure class="chart-panel">
        <figcaption><span>ความครบของผลลัพธ์</span><strong>จาก ${formatNumber(innovationCount)} นวัตกรรม</strong></figcaption>
        <div>${chartRows(outcomeRows, { showShare: false })}</div>
        <p class="chart-note">${escapeHtml(outcome.note_th || "")}</p>
      </figure>
    </div>
  `;
}

function recordTitle(item, fallback) {
  return item.business_name || item.title || item.title_th || item.project_name || item.metric_label_th || item.name_th || item.record_code || fallback;
}

function recordMeta(item) {
  return [
    item.fiscal_year,
    item.research_unit,
    item.category,
    item.innovation_type,
    item.district || item.amphoe,
    item.subdistrict || item.tambon,
  ].filter(hasValue).slice(0, 4);
}

function recordDescription(item) {
  const value = item.description || item.scope_warning_th || item.knowledge_technology || item.owner_affiliation_name || "";
  return value.length > 260 ? `${value.slice(0, 257).trim()}…` : value;
}

function renderFactList(rows) {
  const visible = rows.filter(([, value]) => hasValue(value) && humanValue(value) !== "ไม่ระบุ");
  if (!visible.length) return `<p class="fact-empty">ต้นทางไม่มีรายละเอียดเพิ่มเติมที่สรุปได้</p>`;
  return `<dl class="record-facts">${visible.map(([label, value]) => `
    <div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(humanValue(value))}</dd></div>
  `).join("")}</dl>`;
}

function recordSourceLink(item) {
  const sourceUrl = safeExternalUrl(item.source_url || item.endpoint_url || item.provenance?.endpoint_url);
  return sourceUrl
    ? `<a class="record-source" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noreferrer">เปิดหลักฐานต้นทาง</a>`
    : "";
}

function renderProjectDigest(item, fallback) {
  const areas = humanValue(item.geography);
  const countLine = [
    hasValue(item.participant_record_count) ? `${formatNumber(item.participant_record_count)} ระเบียนผู้เข้าร่วม` : "",
    hasValue(item.business_count) ? `${formatNumber(item.business_count)} กลุ่ม/ธุรกิจ` : "",
    areas !== "ไม่ระบุ" ? areas : "",
  ].filter(Boolean).join(" · ");
  return `<article class="record-card record-project">
    <header><div><span class="record-kind">โครงการ</span><h4>${escapeHtml(recordTitle(item, fallback))}</h4></div><span class="record-value">${formatNumber(item.participant_record_count)} records</span></header>
    <div class="record-meta">${recordMeta(item).map((value) => `<span>${escapeHtml(value)}</span>`).join("")}</div>
    ${countLine ? `<p class="record-summary">${escapeHtml(countLine)}</p>` : ""}
    <details><summary>ดูสาระสำคัญ</summary>${renderFactList([
      [FIELD_LABELS.official_project_id, item.official_project_id],
      [FIELD_LABELS.definition_status, item.definition_status],
      [FIELD_LABELS.project_status, item.project_status],
      [FIELD_LABELS.budget_status, item.budget_status],
      [FIELD_LABELS.geography, item.geography],
      [FIELD_LABELS.businesses, item.businesses],
      [FIELD_LABELS.latest_source_update, item.latest_source_update],
    ])}</details>
    ${recordSourceLink(item)}
  </article>`;
}

function renderInnovationDigest(item, fallback) {
  const badges = [
    hasValue(item.trl_level) ? `TRL ${item.trl_level}` : "",
    hasValue(item.srl_level) ? `SRL ${item.srl_level}` : "",
    item.category,
  ].filter(Boolean);
  return `<article class="record-card record-innovation">
    <header><div><span class="record-kind">นวัตกรรม</span><h4>${escapeHtml(recordTitle(item, fallback))}</h4></div>${hasValue(item.innovation_value_baht) ? `<span class="record-value">${escapeHtml(formatMoney(item.innovation_value_baht))}</span>` : ""}</header>
    <div class="record-meta">${badges.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}</div>
    ${recordDescription(item) ? `<p class="record-summary">${escapeHtml(recordDescription(item))}</p>` : ""}
    <details><summary>ดูสาระสำคัญ</summary>${renderFactList([
      [FIELD_LABELS.owner_affiliation_name, item.owner_affiliation_name],
      [FIELD_LABELS.innovation_type, item.innovation_type],
      [FIELD_LABELS.funding, item.funding],
      [FIELD_LABELS.target_groups, item.target_groups],
      [FIELD_LABELS.ip, item.ip],
      [FIELD_LABELS.research_leads, item.research_leads],
      [FIELD_LABELS.areas, item.areas],
      [FIELD_LABELS.fetched_at, item.fetched_at],
    ])}</details>
    ${recordSourceLink(item)}
  </article>`;
}

function renderGenericDigest(item, fallback, sectionKey) {
  const displayValue = hasValue(item.value)
    ? `${formatNumber(item.value, 2)}${item.unit ? ` ${item.unit}` : ""}`
    : null;
  const detailRows = GENERIC_DETAIL_KEYS
    .filter((key) => hasValue(item[key]))
    .map((key) => [FIELD_LABELS[key] || key.replaceAll("_", " "), item[key]]);
  return `<article class="record-card record-${escapeHtml(sectionKey || "generic")}">
    <header><div><span class="record-kind">${escapeHtml(SECTION_LABELS[sectionKey] || fallback)}</span><h4>${escapeHtml(recordTitle(item, fallback))}</h4></div>${displayValue ? `<span class="record-value">${escapeHtml(displayValue)}</span>` : ""}</header>
    <div class="record-meta">${recordMeta(item).map((value) => `<span>${escapeHtml(value)}</span>`).join("")}</div>
    ${recordDescription(item) ? `<p class="record-summary">${escapeHtml(recordDescription(item))}</p>` : ""}
    <details><summary>ดูสาระสำคัญ</summary>${renderFactList(detailRows)}</details>
    ${recordSourceLink(item)}
  </article>`;
}

function renderRecordDigest(item, fallback = "รายการข้อมูล", kind = "generic") {
  if (kind === "project") return renderProjectDigest(item, fallback);
  if (kind === "innovation") return renderInnovationDigest(item, fallback);
  return renderGenericDigest(item, fallback, kind);
}

function renderResearchSection(targetId, section, emptyText, kind) {
  const target = document.getElementById(targetId);
  const items = section?.items || [];
  target.innerHTML = `
    <div class="subsection-head">
      <div><span>${escapeHtml(kind === "project" ? "ACTIVITY" : kind === "innovation" ? "OUTPUT" : "NEED")}</span><h3>${escapeHtml(section?.title_th || emptyText)}</h3></div>
      <strong>${formatNumber(section?.total_records ?? items.length)} รายการ</strong>
    </div>
    ${items.length
      ? `<div class="record-grid">${items.map((item) => renderRecordDigest(item, emptyText, kind)).join("")}</div>`
      : `<p class="empty-block">${escapeHtml(emptyText)} — ยังไม่มีระเบียนที่เชื่อมจังหวัดนี้</p>`}`;
}

function renderResearch(briefing, summary) {
  renderResearchSummary(summary);
  renderResearchSection("projectRecords", briefing.sections?.project_master, "โครงการ", "project");
  renderResearchSection("innovationRecords", briefing.sections?.innovation, "นวัตกรรม", "innovation");
  renderResearchSection("requirementRecords", briefing.sections?.requirements, "โจทย์หรือความต้องการจากพื้นที่", "requirements");
}

function renderPeopleCategoryNav() {
  const available = detailState.peopleSections.filter(([, section]) => (section.items || []).length);
  const buttons = [["all", { title_th: "ทั้งหมด", total_records: available.reduce((sum, [, section]) => sum + (section.items || []).length, 0) }], ...available];
  document.getElementById("peopleCategoryNav").innerHTML = buttons.map(([key, section]) => `
    <button type="button" data-people-category="${escapeHtml(key)}" aria-pressed="${key === detailState.activePeopleSection}">
      ${escapeHtml(key === "all" ? "ทั้งหมด" : section.title_th || SECTION_LABELS[key] || key)}
      <span>${formatNumber(section.total_records ?? section.items?.length ?? 0)}</span>
    </button>
  `).join("");
}

function renderPeopleSections() {
  const container = document.getElementById("peopleSections");
  const query = detailState.query.trim().toLocaleLowerCase("th-TH");
  const selected = detailState.peopleSections.filter(([key, section]) => {
    if (!(section.items || []).length) return false;
    return detailState.activePeopleSection === "all" || detailState.activePeopleSection === key;
  });
  container.innerHTML = selected.map(([key, section]) => {
    const items = section.items || [];
    const filtered = query
      ? items.filter((item) => searchableText(item).toLocaleLowerCase("th-TH").includes(query))
      : items;
    const visible = detailState.visibleBySection[key] || 12;
    const shown = filtered.slice(0, visible);
    const remaining = Math.max(0, filtered.length - shown.length);
    return `<section class="data-block" data-section="${escapeHtml(key)}">
      <header>
        <div><span>${escapeHtml(STATUS_LABELS[section.status] || section.status || "ไม่ระบุ")}</span><h3>${escapeHtml(section.title_th || SECTION_LABELS[key] || key)}</h3></div>
        <strong>${query ? `พบ ${formatNumber(filtered.length)} จาก ${formatNumber(items.length)}` : `${formatNumber(section.total_records ?? items.length)} รายการ`}</strong>
      </header>
      ${shown.length
        ? `<div class="record-grid">${shown.map((item) => renderRecordDigest(item, section.title_th, key)).join("")}</div>`
        : `<p class="empty-block">ไม่พบรายการที่ตรงกับคำค้น</p>`}
      ${remaining ? `<button class="load-more" type="button" data-load-section="${escapeHtml(key)}">ดูเพิ่มอีก ${formatNumber(Math.min(24, remaining))} รายการ <span>เหลือ ${formatNumber(remaining)}</span></button>` : ""}
    </section>`;
  }).join("") || `<p class="empty-block">ยังไม่มีข้อมูลสาธารณะในหมวดนี้</p>`;
  renderPeopleCategoryNav();
}

function renderPeopleMissingSummary() {
  const missing = detailState.peopleSections.filter(([, section]) => !(section.items || []).length);
  document.getElementById("peopleMissingSummary").innerHTML = missing.length ? `
    <details class="missing-source-summary">
      <summary>หมวดที่ยังไม่มีข้อมูลจังหวัดนี้ <strong>${formatNumber(missing.length)} หมวด</strong></summary>
      <div>${missing.map(([key, section]) => `<span>${escapeHtml(section.title_th || SECTION_LABELS[key] || key)}</span>`).join("")}</div>
    </details>` : "";
}

function setupPeople(briefing) {
  detailState.peopleSections = SECTION_ORDER
    .map((key) => [key, briefing.sections?.[key]])
    .filter(([, section]) => section);
  detailState.visibleBySection = {};
  detailState.peopleSections.forEach(([key]) => { detailState.visibleBySection[key] = 12; });
  detailState.activePeopleSection = "all";
  detailState.query = "";
  document.getElementById("peopleSearch").value = "";
  renderPeopleSections();
  renderPeopleMissingSummary();

  const search = document.getElementById("peopleSearch");
  if (!search.dataset.bound) {
    search.dataset.bound = "true";
    search.addEventListener("input", (event) => {
      detailState.query = event.target.value;
      renderPeopleSections();
    });
  }

  const categoryNav = document.getElementById("peopleCategoryNav");
  if (!categoryNav.dataset.bound) {
    categoryNav.dataset.bound = "true";
    categoryNav.addEventListener("click", (event) => {
      const button = event.target.closest("[data-people-category]");
      if (!button) return;
      detailState.activePeopleSection = button.dataset.peopleCategory;
      renderPeopleSections();
    });
  }

  const sections = document.getElementById("peopleSections");
  if (!sections.dataset.bound) {
    sections.dataset.bound = "true";
    sections.addEventListener("click", (event) => {
      const button = event.target.closest("[data-load-section]");
      if (!button) return;
      const key = button.dataset.loadSection;
      detailState.visibleBySection[key] = (detailState.visibleBySection[key] || 12) + 24;
      renderPeopleSections();
    });
  }
}

function renderHighlights(items) {
  if (!items.length) return "";
  return `<div class="highlight-list"><span>รายการตัวอย่าง</span>${items.map((item) => {
    const url = safeExternalUrl(item.source_url);
    const content = `<strong>${escapeHtml(item.title_th)}</strong><small>${escapeHtml([item.detail_th, item.meta_th].filter(Boolean).join(" · "))}</small>`;
    return url
      ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${content}</a>`
      : `<div>${content}</div>`;
  }).join("")}</div>`;
}

function renderDimensions(summary) {
  const dimensions = summary.dimensions || [];
  document.getElementById("detailDimensions").innerHTML = dimensions.length ? dimensions.map((dimension) => `
    <article class="dimension-panel">
      <header>
        <div><span>${escapeHtml(dimension.evidence_stage || "บริบทพื้นที่")}</span><h3>${escapeHtml(dimension.label_th)}</h3></div>
        <p>${escapeHtml(dimension.summary_th || "")}</p>
      </header>
      <div class="dimension-charts">
        ${(dimension.metrics || []).map((metric) => `
          <figure class="chart-panel">
            <figcaption><span>ค่าจังหวัด</span><strong>${escapeHtml(metric.label_th)}</strong></figcaption>
            ${chartRows([{ label_th: metric.benchmark_label_th || "ค่าจังหวัด", value: metric.value, display_value: metric.display_value }], { showShare: false })}
          </figure>`).join("")}
        ${(dimension.breakdowns || []).map((breakdown) => `
          <figure class="chart-panel">
            <figcaption><span>${escapeHtml(breakdown.kind === "scores" ? "ค่าตามต้นทาง" : "สัดส่วนข้อมูล")}</span><strong>${escapeHtml(breakdown.label_th)}</strong></figcaption>
            ${(breakdown.items || []).length ? chartRows(breakdown.items, { showShare: breakdown.kind !== "scores" }) : `<p class="empty-chart">ยังไม่มีข้อมูล</p>`}
            ${breakdown.note_th ? `<p class="chart-note">${escapeHtml(breakdown.note_th)}</p>` : ""}
          </figure>`).join("")}
      </div>
      ${renderHighlights(dimension.highlights || [])}
    </article>
  `).join("") : `<p class="empty-block">ยังไม่มีมิติที่สรุปเป็นภาพได้</p>`;

  const missing = summary.missing_dimensions || [];
  document.getElementById("missingDimensions").innerHTML = missing.length ? `
    <details>
      <summary>มิติที่ยังไม่มีข้อมูลสาธารณะ <strong>${formatNumber(missing.length)} มิติ</strong></summary>
      <div>${missing.map((row) => `<span>${escapeHtml(row.label_th)}</span>`).join("")}</div>
    </details>` : "";
}

function renderSources(summary) {
  const quality = summary.data_quality_overview || {};
  const coverage = summary.coverage || {};
  const latest = quality.latest_observed_fetch ? formatDate(quality.latest_observed_fetch) : "ไม่ระบุ";
  document.getElementById("detailQuality").innerHTML = `
    <div class="quality-heading">
      <span>สถานะชุดข้อมูล</span>
      <strong>${escapeHtml(STATUS_LABELS[quality.status] || "Candidate · รอตรวจรับรอง")}</strong>
      <p>ยังไม่มีแหล่งใดผ่าน accepted gate จึงไม่เรียกค่าบนหน้านี้ว่า KPI</p>
    </div>
    <div class="quality-facts">
      <span><strong>${formatNumber(coverage.available_source_count)}</strong>/${formatNumber(coverage.public_source_count)} แหล่งมีข้อมูลจังหวัดนี้</span>
      <span><strong>${formatNumber(quality.sources_with_explicit_as_of)}</strong> แหล่งระบุ as_of ชัดเจน</span>
      <span>พบการดึงล่าสุด <strong>${escapeHtml(latest)}</strong></span>
    </div>`;

  document.getElementById("detailSources").innerHTML = (summary.source_coverage || []).map((source) => {
    const url = safeExternalUrl(source.url);
    const recordText = source.records === null || source.records === undefined ? "ไม่ใช่ข้อมูลจังหวัด" : `${formatNumber(source.records)} ระเบียน`;
    return `<details class="source-row">
      <summary>
        <div><h3>${escapeHtml(source.name_th)}</h3><small>${escapeHtml(source.data_grain_th || "ไม่ระบุระดับข้อมูล")}</small></div>
        <span class="status-pill">${escapeHtml(STATUS_LABELS[source.status] || source.status || "ไม่ระบุ")}</span>
        <strong>${escapeHtml(recordText)}</strong>
      </summary>
      <div class="source-body">
        <dl>
          <div><dt>วิธีนำเข้า</dt><dd>${escapeHtml(source.acquisition_mode || "ไม่ระบุ")}</dd></div>
          <div><dt>ข้อมูล ณ วันที่</dt><dd>${escapeHtml(source.observed_as_of || "ไม่ระบุ")}</dd></div>
          <div><dt>ดึงข้อมูลเมื่อ</dt><dd>${escapeHtml(source.observed_fetched_at ? formatDate(source.observed_fetched_at) : "ไม่ระบุ")}</dd></div>
          <div><dt>ข้อจำกัด</dt><dd>${escapeHtml(source.note_th || source.source_note_th || source.quality_label_th || "ไม่ระบุ")}</dd></div>
        </dl>
        ${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">เปิดแหล่งข้อมูล</a>` : ""}
      </div>
    </details>`;
  }).join("");
}

function renderOperations(operations) {
  const summary = operations.summary || {};
  const scheduler = operations.scheduler || {};
  const audit = operations.last_connectivity_audit || {};
  const sourceNames = Object.fromEntries((detailState.summary?.source_coverage || []).map((source) => [source.source_id, source.name_th]));
  document.getElementById("operationsStatus").innerHTML = `
    <div class="ops-overview">
      <article><span>Connector ที่ทดสอบสำเร็จ</span><strong>${formatNumber(audit.successful_connectors)}/${formatNumber(audit.configured_connectors)}</strong></article>
      <article><span>Candidate records ที่พบ</span><strong>${formatNumber(audit.records_seen_total)}</strong></article>
      <article><span>ดึงอัตโนมัติบน Production</span><strong>${summary.automatic_refresh_enabled ? "เปิดอยู่" : "ยังไม่เปิด"}</strong></article>
    </div>
    <div class="scheduler-note"><strong>${escapeHtml(scheduler.status_th || "ยังไม่ระบุสถานะ scheduler")}</strong><p>${escapeHtml(scheduler.reason_th || "")}</p></div>
    <ol class="ops-pipeline">${(operations.pipeline || []).map((stage) => `<li><span>${escapeHtml(stage.stage)}</span><p>${escapeHtml(stage.rule_th)}</p></li>`).join("")}</ol>
    <div class="ops-audit">
      <h3>ผลตรวจการเชื่อมต่อล่าสุด <span>${escapeHtml(formatDate(audit.audited_at))}</span></h3>
      ${(audit.results || []).map((row) => `<div class="ops-row"><span>${escapeHtml(sourceNames[row.source_id] || row.source_id)}</span><strong>${formatNumber(row.records_seen)} records</strong><p>${escapeHtml(row.note_th)}</p></div>`).join("")}
    </div>
    <a class="ops-link" href="/docs" target="_blank" rel="noreferrer">ดูสัญญา Public API</a>`;
}

function setupSectionNavigation() {
  const links = [...document.querySelectorAll(".section-nav a")];
  const sections = links.map((link) => document.querySelector(link.getAttribute("href"))).filter(Boolean);
  if (!links.length || !sections.length || document.body.dataset.sectionNavBound) return;
  document.body.dataset.sectionNavBound = "true";
  let ticking = false;
  const update = () => {
    const marker = window.scrollY + 150;
    let active = sections[0];
    sections.forEach((section) => {
      if (section.offsetTop <= marker) active = section;
    });
    links.forEach((link) => link.classList.toggle("active", link.getAttribute("href") === `#${active.id}`));
    ticking = false;
  };
  window.addEventListener("scroll", () => {
    if (!ticking) {
      ticking = true;
      window.requestAnimationFrame(update);
    }
  }, { passive: true });
  update();
}

function renderPage(summary, briefing, operations) {
  detailState.summary = summary;
  detailState.briefing = briefing;
  detailState.operations = operations;
  setText("detailCoverage", `${formatNumber(summary.coverage?.available_source_count)} จาก ${formatNumber(summary.coverage?.public_source_count)} แหล่งมีข้อมูล`);
  setText("detailGenerated", `ชุดข้อมูล ${formatDate(summary.generated_at)}`);
  renderKpis(summary, briefing);
  renderExecutiveReadout(summary);
  renderDecisionChain(summary);
  renderExecutiveGaps(summary);
  renderResearch(briefing, summary);
  renderHousingDemand(briefing);
  setupPeople(briefing);
  renderDimensions(summary);
  renderSources(summary);
  renderOperations(operations);
  document.getElementById("detailLoading").hidden = true;
  document.getElementById("detailContent").hidden = false;
  setupSectionNavigation();
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
