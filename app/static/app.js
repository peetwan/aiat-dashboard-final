const state = {
  catalog: null,
  boundaries: null,
  points: null,
  map: null,
  mapLoaded: false,
  selectedCode: null,
  hoveredCode: null,
  requestToken: 0,
  labelMarkers: [],
  pointsVisible: false,
  currentBriefing: null,
  cultureVisible: 12,
  cultureQuery: "",
  hoverPopup: null,
};

const DIMENSION_FIELDS = new Set([
  "year", "income_rank_id", "house_type", "house_tenure", "house_tenure_type",
  "supply_type", "price_rank", "Attribute", "gap_type",
]);

const HIDDEN_FIELDS = new Set(["cwt_id", "cwt_dc", "cwt_name", "province_name"]);

const FIELD_META = {
  year: ["ปีข้อมูล", "number"],
  income_rank_id: ["กลุ่มรายได้", "number"],
  house_type: ["ประเภทที่อยู่อาศัย", "text"],
  house_tenure: ["ลักษณะการครอบครอง", "text"],
  house_tenure_type: ["ลักษณะการครอบครอง", "text"],
  supply_type: ["ประเภทที่อยู่อาศัย", "text"],
  price_rank: ["ระดับราคา", "number"],
  Attribute: ["หมวดค่าใช้จ่าย", "text"],
  gap_type: ["ประเภทช่องว่าง", "text"],
  human: ["มิติทุนมนุษย์", "decimal"],
  physical: ["มิติทุนกายภาพ", "decimal"],
  financial: ["มิติทุนการเงิน", "decimal"],
  natural_res: ["มิติทรัพยากรธรรมชาติ", "decimal"],
  social: ["มิติทุนสังคม", "decimal"],
  overall: ["คะแนนรวมตามต้นทาง", "decimal"],
  population: ["จำนวนประชากร", "number"],
  household_number: ["จำนวนครัวเรือน", "number"],
  household_average_member: ["สมาชิกเฉลี่ยต่อครัวเรือน", "decimal"],
  average_price: ["ราคาที่อยู่อาศัยเฉลี่ย", "number"],
  house_price_income_ratio: ["อัตราส่วนราคาบ้านต่อรายได้", "decimal"],
  pct_overcrowded: ["ที่อยู่อาศัยแออัด", "percent"],
  count_overcrowded: ["ครัวเรือนแออัดตามต้นทาง", "number"],
  count_not_overcrowded: ["ครัวเรือนไม่แออัดตามต้นทาง", "number"],
  total_count: ["จำนวนรวมตามต้นทาง", "number"],
  share_loan_pass: ["ผ่านเกณฑ์สินเชื่อ", "ratio"],
  share_loan_fail: ["ไม่ผ่านเกณฑ์สินเชื่อ", "ratio"],
  share_tenure_owner: ["เป็นเจ้าของ", "ratio"],
  share_tenure_rent: ["เช่า", "ratio"],
  share_tenure_squatter: ["อยู่อาศัยโดยไม่มีกรรมสิทธิ์", "ratio"],
  risk_level_1_pct_area: ["พื้นที่เสี่ยงระดับ 1", "percent"],
  risk_level_2_pct_area: ["พื้นที่เสี่ยงระดับ 2", "percent"],
  risk_level_3_pct_area: ["พื้นที่เสี่ยงระดับ 3", "percent"],
  risk_level_4_pct_area: ["พื้นที่เสี่ยงระดับ 4", "percent"],
  risk_level_5_pct_area: ["พื้นที่เสี่ยงระดับ 5", "percent"],
  risk_level_1_population: ["ประชากรในพื้นที่เสี่ยงระดับ 1", "number"],
  risk_level_2_population: ["ประชากรในพื้นที่เสี่ยงระดับ 2", "number"],
  risk_level_3_population: ["ประชากรในพื้นที่เสี่ยงระดับ 3", "number"],
  risk_level_4_population: ["ประชากรในพื้นที่เสี่ยงระดับ 4", "number"],
  risk_level_5_population: ["ประชากรในพื้นที่เสี่ยงระดับ 5", "number"],
  Mean: ["ค่าดัชนี", "decimal"],
  house_burden_pct: ["ภาระค่าใช้จ่ายที่อยู่อาศัย", "percent"],
  exp_pct_house_burden: ["สัดส่วนค่าใช้จ่ายด้านที่อยู่อาศัย", "percent"],
  share_over_30: ["ภาระค่าใช้จ่ายเกิน 30%", "ratio"],
  share_over_40: ["ภาระค่าใช้จ่ายเกิน 40%", "ratio"],
  pct_house: ["สัดส่วนที่อยู่อาศัย", "percent"],
  supply_unit: ["จำนวนหน่วยที่อยู่อาศัย", "number"],
  supply_rent: ["อุปทานสำหรับเช่า", "number"],
  supply_sale: ["อุปทานสำหรับขาย", "number"],
  rent_cost: ["ค่าเช่าตามต้นทาง", "number"],
  mortgage_cost: ["ค่าผ่อนตามต้นทาง", "number"],
  house_tenure_owner: ["เจ้าของ", "number"],
  house_tenure_owner_landrented: ["เจ้าของบ้านบนที่ดินเช่า", "number"],
  house_tenure_rented: ["เช่า", "number"],
  house_tenure_squatter: ["ไม่มีกรรมสิทธิ์", "number"],
  house_tenure_mortgage: ["อยู่ระหว่างผ่อน", "number"],
  pct_house_tenure_owner: ["สัดส่วนเจ้าของ", "percent"],
  pct_house_tenure_owner_landrented: ["สัดส่วนเจ้าของบ้านบนที่ดินเช่า", "percent"],
  pct_house_tenure_rented: ["สัดส่วนเช่า", "percent"],
  pct_house_tenure_squatter: ["สัดส่วนไม่มีกรรมสิทธิ์", "percent"],
  pct_house_tenure_mortgage: ["สัดส่วนอยู่ระหว่างผ่อน", "percent"],
  exp_water_electricity: ["ค่าน้ำและไฟตามต้นทาง", "number"],
  exp_cooking_fuel: ["เชื้อเพลิงประกอบอาหารตามต้นทาง", "number"],
  exp_garbage: ["ค่าจัดการขยะตามต้นทาง", "number"],
  exp_services: ["ค่าบริการตามต้นทาง", "number"],
  exp_health: ["ค่าใช้จ่ายสุขภาพตามต้นทาง", "number"],
  exp_fuel: ["ค่าเชื้อเพลิงตามต้นทาง", "number"],
  exp_transportation: ["ค่าเดินทางตามต้นทาง", "number"],
  exp_food: ["ค่าอาหารตามต้นทาง", "number"],
  exp_foodbev: ["ค่าอาหารและเครื่องดื่มตามต้นทาง", "number"],
  exp_house_repair: ["ค่าซ่อมแซมที่อยู่อาศัยตามต้นทาง", "number"],
  exp_rental: ["ค่าเช่าตามต้นทาง", "number"],
  exp_mortgage: ["ค่าผ่อนตามต้นทาง", "number"],
  exp_pct_utilities: ["สัดส่วนค่าสาธารณูปโภค", "percent"],
  exp_pct_transportation: ["สัดส่วนค่าเดินทาง", "percent"],
  exp_pct_medical: ["สัดส่วนค่ารักษาพยาบาล", "percent"],
  exp_pct_foodbev: ["สัดส่วนค่าอาหารและเครื่องดื่ม", "percent"],
  pct_medical: ["สัดส่วนค่ารักษาพยาบาล", "percent"],
  pct_others: ["สัดส่วนค่าใช้จ่ายอื่น", "percent"],
  pct_transportation: ["สัดส่วนค่าเดินทาง", "percent"],
  value: ["ค่าช่องว่างอุปสงค์–อุปทาน", "decimal"],
  Value: ["ค่าตามต้นทาง", "decimal"],
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatNumber(value, maximumFractionDigits = 0) {
  if (value === null || value === undefined || value === "") return "ไม่มีค่า";
  return new Intl.NumberFormat("th-TH", { maximumFractionDigits }).format(Number(value));
}

function formatDate(value) {
  if (!value) return "ไม่ระบุวันที่";
  return new Intl.DateTimeFormat("th-TH", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function fieldLabel(key) {
  if (FIELD_META[key]) return FIELD_META[key][0];
  return String(key)
    .replace(/^exp_/, "ค่าใช้จ่าย ")
    .replace(/^pct_/, "สัดส่วน ")
    .replace(/^share_/, "สัดส่วน ")
    .replaceAll("_", " ")
    .trim();
}

function formatSourceValue(key, value) {
  if (value === null || value === undefined || value === "") return "ไม่ระบุ";
  const type = FIELD_META[key]?.[1] || "auto";
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || type === "text") return String(value);
  if (type === "ratio") return `${formatNumber(numeric * 100, 2)}%`;
  if (type === "percent") return `${formatNumber(numeric, 2)}%`;
  if (type === "decimal") return formatNumber(numeric, 2);
  return formatNumber(numeric, 0);
}

function displayUnit(unit) {
  if (unit === "source_score") return "คะแนนตามต้นทาง";
  return unit || "";
}

function rowDimensions(row) {
  return Object.entries(row?.values || {})
    .filter(([key, value]) => DIMENSION_FIELDS.has(key) && value !== null && value !== "")
    .map(([key, value]) => `${fieldLabel(key)} ${formatSourceValue(key, value)}`);
}

function rowMetrics(row, limit = 5) {
  return Object.entries(row?.values || {})
    .filter(([key, value]) => FIELD_META[key] && !DIMENSION_FIELDS.has(key) && !HIDDEN_FIELDS.has(key) && value !== null && value !== "")
    .slice(0, limit);
}

function activatePanelTab(tabName, updateUrl = true) {
  document.querySelectorAll("[data-panel-tab]").forEach((button) => {
    const active = button.dataset.panelTab === tabName;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll("[data-panel-view]").forEach((view) => {
    const active = view.dataset.panelView === tabName;
    view.hidden = !active;
    view.classList.toggle("active", active);
  });
  document.getElementById("panelStage")?.scrollTo({ top: 0, behavior: "smooth" });
  if (updateUrl && state.selectedCode) {
    const url = new URL(window.location.href);
    url.searchParams.set("view", tabName);
    window.history.replaceState({}, "", url);
  }
}

function provinceByCode(code) {
  const normalized = String(code ?? "").padStart(2, "0");
  return state.catalog?.provinces.find((province) => province.province_code === normalized);
}

function sourceById(sourceId) {
  return state.catalog?.sources.find((source) => source.source_id === sourceId);
}

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2200);
}

function renderOverview() {
  const select = document.getElementById("provinceSelect");
  const options = [...state.catalog.provinces]
    .sort((a, b) => a.province_name_th.localeCompare(b.province_name_th, "th"))
    .map(
      (province) =>
        `<option value="${province.province_code}">${escapeHtml(province.province_name_th)} · ${escapeHtml(province.region)}</option>`,
    );
  select.insertAdjacentHTML("beforeend", options.join(""));
}

function metricPaint() {
  const sourceCount = ["coalesce", ["get", "evidence_source_count"], 0];
  const richnessColor = [
    "step",
    sourceCount,
    "#10241d",
    1, "#18352b",
    2, "#21523f",
    3, "#2f7859",
    4, "#48ac7a",
    5, "#75e7ab",
  ];
  return {
    baseColor: richnessColor,
    color: [
      "case",
      ["boolean", ["feature-state", "selected"], false],
      "#f4cf72",
      ["boolean", ["feature-state", "hover"], false],
      "#b9ffd8",
      richnessColor,
    ],
    height: [
      "+",
      [
        "*",
        ["+", 1, sourceCount],
        ["interpolate", ["linear"], ["zoom"], 2.8, 40, 7, 520, 11, 900],
      ],
      [
        "case",
        ["boolean", ["feature-state", "selected"], false],
        ["interpolate", ["linear"], ["zoom"], 2.8, 180, 7, 1200, 11, 1800],
        0,
      ],
    ],
  };
}

function updateLabelVisibility() {
  if (!state.mapLoaded) return;
  const zoom = state.map.getZoom();
  const threshold = zoom < 7.5 ? 4 : zoom < 9 ? 3 : zoom < 10.5 ? 2 : 0;
  state.labelMarkers.forEach(({ element, code, sourceCount }) => {
    const emphasized = code === state.selectedCode || code === state.hoveredCode;
    const hidden = sourceCount < threshold && !emphasized;
    element.classList.toggle("is-secondary", hidden);
    element.style.display = hidden ? "none" : "block";
    element.classList.toggle("is-active", code === state.selectedCode);
    element.classList.toggle("is-hovered", code === state.hoveredCode);
  });
}

function addProvinceLabels() {
  state.catalog.provinces.forEach((province) => {
    if (!province.centroid?.every((value) => Number.isFinite(Number(value)))) return;
    const element = document.createElement("button");
    element.type = "button";
    element.className = "province-map-label";
    element.textContent = province.province_name_th;
    const sourceCount = Number(province.evidence_source_count || 0);
    element.dataset.richness = String(sourceCount);
    element.setAttribute("aria-label", `เปิดข้อมูลจังหวัด${province.province_name_th}`);
    element.addEventListener("click", (event) => {
      event.stopPropagation();
      selectProvince(province.province_code, true);
    });
    const marker = new window.maplibregl.Marker({ element, anchor: "center" })
      .setLngLat(province.centroid)
      .addTo(state.map);
    state.labelMarkers.push({ marker, element, code: province.province_code, sourceCount });
  });
  updateLabelVisibility();
}

function setFeatureSelection(code) {
  if (!state.mapLoaded) return;
  if (state.selectedCode) {
    state.map.setFeatureState({ source: "provinces", id: state.selectedCode }, { selected: false });
  }
  if (code) {
    state.map.setFeatureState({ source: "provinces", id: code }, { selected: true });
  }
}

function fitProvince(province) {
  if (!state.mapLoaded || !province.centroid?.every((value) => Number.isFinite(Number(value)))) return;
  const isMobile = window.matchMedia("(max-width: 720px)").matches;
  state.map.easeTo({
    center: province.centroid,
    zoom: isMobile ? 6.1 : 6.65,
    pitch: 56,
    bearing: -10,
    padding: isMobile ? { top: 72, right: 18, bottom: 360, left: 18 } : { top: 80, right: 660, bottom: 60, left: 60 },
    duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 900,
  });
}

function openPanelLoading(province) {
  const panel = document.getElementById("provincePanel");
  panel.classList.add("is-open");
  panel.setAttribute("aria-hidden", "false");
  document.body.classList.add("panel-open");
  document.getElementById("panelLoading").hidden = false;
  document.getElementById("panelContent").hidden = true;
  document.getElementById("panelError").hidden = true;
  document.getElementById("mapPrompt").classList.add("is-hidden");
  document.querySelector(".picker-copy strong").textContent = province.province_name_th;
  document.getElementById("provinceSelect").value = province.province_code;
  state.currentBriefing = null;
  state.cultureVisible = 12;
  state.cultureQuery = "";
  const cultureSearch = document.getElementById("cultureSearch");
  if (cultureSearch) cultureSearch.value = "";
  activatePanelTab("overview", false);
}

function trimText(value, length = 180) {
  const text = String(value ?? "").trim();
  return text.length > length ? `${text.slice(0, length).trim()}…` : text;
}

function renderExecutiveSignals(briefing) {
  const signals = briefing.executive_signals || [];
  document.getElementById("executiveSignals").innerHTML = signals.length
    ? signals
        .map(
          (signal) => `
            <a class="decision-card" href="${escapeHtml(signal.source_url)}" target="_blank" rel="noreferrer">
              <span>${escapeHtml(signal.label_th)}</span>
              <strong>${escapeHtml(signal.display_value)}</strong>
              <small>${escapeHtml(signal.unit || "")} · ดูต้นทาง ↗</small>
            </a>`,
        )
        .join("")
    : '<article class="empty-data"><strong>ต้นทางยังไม่มีตัวชี้วัดที่ยืนยันสำหรับจังหวัดนี้</strong><span>ดูรายการจริงในหมวดข้อมูลด้านล่างแทน</span></article>';
}

function renderDecisionNarrative(briefing) {
  const signals = new Map((briefing.executive_signals || []).map((signal) => [signal.key, signal]));
  const facts = [];
  const affordability = signals.get("house_price_income_ratio");
  const loan = signals.get("housing_loan_pass_share");
  const overcrowding = signals.get("overcrowding_pct");
  const flood = signals.get("flood_risk_area_level_4_5");
  if (affordability) facts.push({
    eyebrow: "กำลังซื้อที่อยู่อาศัย",
    text: `ราคาบ้านคิดเป็น ${affordability.display_value} เท่าของรายได้ตามชุดข้อมูลต้นทาง`,
  });
  if (loan) facts.push({
    eyebrow: "การเข้าถึงสินเชื่อ",
    text: `สัดส่วนที่ผ่านเกณฑ์สินเชื่ออยู่ที่ ${loan.display_value}`,
  });
  if (overcrowding) facts.push({
    eyebrow: "คุณภาพที่อยู่อาศัย",
    text: `ที่อยู่อาศัยแออัดคิดเป็น ${overcrowding.display_value} ตามนิยามของต้นทาง`,
  });
  if (flood) facts.push({
    eyebrow: "ความเสี่ยงเชิงพื้นที่",
    text: `พื้นที่เสี่ยงน้ำท่วมระดับ 4–5 รวม ${flood.display_value} ของพื้นที่ตามต้นทาง`,
  });
  document.getElementById("decisionNarrative").innerHTML = facts.length
    ? facts.map((fact, index) => `
        <article class="briefing-fact">
          <span>${String(index + 1).padStart(2, "0")}</span>
          <div><small>${escapeHtml(fact.eyebrow)}</small><p>${escapeHtml(fact.text)}</p></div>
        </article>`).join("")
    : '<article class="empty-data"><strong>ยังไม่มีค่าที่เพียงพอสำหรับสรุปสถานการณ์</strong><span>เลือกดูโครงการหรือข้อมูลรายมิติแทนได้</span></article>';
}

function renderAreaProjects(section) {
  const container = document.getElementById("areaProjects");
  document.getElementById("areaSection").hidden = section.status !== "available";
  container.innerHTML = (section.items || [])
    .map(
      (item) => `
        <article class="data-card project-card">
          <div class="record-kicker"><span>ปีงบประมาณ ${escapeHtml(item.fiscal_year || "ไม่ระบุ")}</span><span>${escapeHtml(item.district || "ไม่ระบุอำเภอ")}</span></div>
          <h3>${escapeHtml(item.project_name || "ไม่ระบุชื่อโครงการ")}</h3>
          <p>${escapeHtml(item.business_name || "ไม่ระบุหน่วยธุรกิจ")}</p>
          <footer><span>${escapeHtml(item.research_unit || "ไม่ระบุหน่วยวิจัย")}</span><a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">API ↗</a></footer>
        </article>`,
    )
    .join("");
}

function renderInnovations(section) {
  const container = document.getElementById("innovationItems");
  document.getElementById("innovationSection").hidden = section.status !== "available";
  container.innerHTML = (section.items || [])
    .map((item) => {
      const funding = (item.funding || []).map((entry) => entry.amount_text).filter(Boolean).join(" · ");
      const target = (item.target_groups || [])[0];
      return `
        <article class="data-card innovation-card">
          <div class="record-kicker"><span>TRL ${escapeHtml(item.trl_level ?? "ไม่ระบุ")}</span><span>${escapeHtml(item.category || "ไม่ระบุหมวด")}</span></div>
          <h3>${escapeHtml(item.title || "ไม่ระบุชื่อนวัตกรรม")}</h3>
          <p>${escapeHtml(trimText((item.highlights || [])[0] || target || item.description, 220))}</p>
          <dl>
            <div><dt>ประเภท</dt><dd>${escapeHtml(item.innovation_type || "ไม่ระบุ")}</dd></div>
            <div><dt>เงินทุนต้นทาง</dt><dd>${escapeHtml(funding || "ไม่ระบุ")}</dd></div>
            <div><dt>กลุ่มเป้าหมาย</dt><dd>${escapeHtml(trimText(target || "ไม่ระบุ", 150))}</dd></div>
          </dl>
          <footer><span>${escapeHtml(item.owner_affiliation_name || "ไม่ระบุสังกัด")}</span><a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">รายละเอียด ↗</a></footer>
        </article>`;
    })
    .join("");
}

function renderCulture(section) {
  document.getElementById("cultureSection").hidden = section.status !== "available";
  const query = state.cultureQuery.trim().toLocaleLowerCase("th");
  const filtered = (section.items || []).filter((item) => {
    if (!query) return true;
    return [item.title_th, item.category, item.cultural_type, item.amphoe, item.tambon]
      .filter(Boolean)
      .join(" ")
      .toLocaleLowerCase("th")
      .includes(query);
  });
  const visible = filtered.slice(0, state.cultureVisible);
  document.getElementById("cultureResultCount").textContent = `แสดง ${formatNumber(visible.length)} จาก ${formatNumber(filtered.length)} รายการ`;
  const loadMore = document.getElementById("loadMoreCulture");
  loadMore.hidden = visible.length >= filtered.length;
  document.getElementById("cultureItems").innerHTML = visible
    .map(
      (item) => `
        <article class="data-card culture-card">
          ${item.image_url ? `<img src="${escapeHtml(item.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer" />` : ""}
          <div>
            <div class="record-kicker"><span>สถานะจากต้นทาง ${escapeHtml(item.risk_status_code ?? "ไม่ระบุ")}</span><span>${escapeHtml(item.category || "ไม่ระบุหมวด")}</span></div>
            <h3>${escapeHtml(item.title_th || "ไม่ระบุชื่อ")}</h3>
            <p>${escapeHtml(trimText(item.risk_reason || item.history || "ต้นทางไม่ได้ระบุเหตุผลความเสี่ยง", 180))}</p>
            <footer><span>${escapeHtml([item.tambon, item.amphoe].filter(Boolean).join(" · ") || "ไม่ระบุพื้นที่ย่อย")}</span><a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">ต้นทาง ↗</a></footer>
          </div>
        </article>`,
    )
    .join("") || '<article class="empty-data"><strong>ไม่พบรายการที่ตรงกับคำค้น</strong><span>ลองใช้ชื่ออำเภอหรือหมวดวัฒนธรรม</span></article>';
}

function resourceSummary(group) {
  const dimensions = (group.field_names || [])
    .filter((key) => DIMENSION_FIELDS.has(key))
    .map(fieldLabel);
  if ((group.field_names || []).includes("year")) {
    return `ดูแนวโน้มตามปีจาก ${formatNumber(group.row_count)} ช่วงข้อมูล`;
  }
  if (group.row_count === 1) return "ค่าภาพรวมระดับจังหวัดจากต้นทาง";
  if (dimensions.length) return `เปรียบเทียบได้ตาม ${[...new Set(dimensions)].join(" · ")}`;
  return `มีข้อมูลย่อย ${formatNumber(group.row_count)} รายการที่ผูกกับจังหวัดนี้`;
}

function renderMetricTiles(row, limit = 6) {
  const metrics = rowMetrics(row, limit);
  return metrics.length
    ? `<div class="interpreted-metrics">${metrics.map(([key, value]) => `
        <div><small>${escapeHtml(fieldLabel(key))}</small><strong>${escapeHtml(formatSourceValue(key, value))}</strong></div>`).join("")}</div>`
    : '<p class="dimension-note">รายการนี้ไม่มีค่าตัวเลขเพิ่มเติมจากมิติที่เลือก</p>';
}

function recordOptionLabel(row, index) {
  const dimensions = rowDimensions(row);
  return dimensions.length ? dimensions.join(" · ") : `รายการ ${index + 1}`;
}

function renderMiniBars(group) {
  const rows = group.rows || [];
  if (!rows.length || (rows.length > 12 && !(group.field_names || []).includes("year"))) return "";
  const metricKey = Object.keys(rows[0].values || {}).find((key) => {
    if (!FIELD_META[key] || DIMENSION_FIELDS.has(key) || HIDDEN_FIELDS.has(key)) return false;
    return Number.isFinite(Number(rows[0].values[key]));
  });
  if (!metricKey) return "";
  const plotted = [...rows]
    .sort((a, b) => Number(a.values?.year || 0) - Number(b.values?.year || 0))
    .slice(-8);
  const max = Math.max(...plotted.map((row) => Math.abs(Number(row.values?.[metricKey]) || 0)), 1);
  return `
    <div class="mini-chart" aria-label="กราฟ ${escapeHtml(fieldLabel(metricKey))}">
      <div class="mini-chart-head"><span>${escapeHtml(fieldLabel(metricKey))}</span><small>เปรียบเทียบภายในชุดข้อมูลเดียวกัน</small></div>
      <div class="mini-bars">${plotted.map((row, index) => {
        const numeric = Number(row.values?.[metricKey]) || 0;
        const label = rowDimensions(row)[0] || `รายการ ${index + 1}`;
        const width = Math.max(4, Math.min(100, Math.abs(numeric) / max * 100));
        return `<div><span title="${escapeHtml(label)}">${escapeHtml(label.replace(/^[^ ]+ /, ""))}</span><i><b style="width:${width.toFixed(2)}%"></b></i><strong>${escapeHtml(formatSourceValue(metricKey, numeric))}</strong></div>`;
      }).join("")}</div>
    </div>`;
}

function renderResourceCard(group, groupIndex) {
  const rows = group.rows || [];
  const latestIndex = (group.field_names || []).includes("year")
    ? rows.reduce((best, row, index) => Number(row.values?.year || 0) > Number(rows[best]?.values?.year || 0) ? index : best, 0)
    : 0;
  const selected = rows[latestIndex];
  const dimensionLabels = [...new Set((group.field_names || []).filter((key) => DIMENSION_FIELDS.has(key)).map(fieldLabel))];
  return `
    <article class="dimension-card">
      <header>
        <div><span>${escapeHtml(group.dataset_title || "ข้อมูลที่อยู่อาศัย")}</span><h3>${escapeHtml(group.resource_name || "ไม่ระบุชื่อชุดข้อมูล")}</h3></div>
        <em>${formatNumber(group.row_count)} รายการย่อย</em>
      </header>
      <p>${escapeHtml(resourceSummary(group))}</p>
      ${dimensionLabels.length ? `<div class="dimension-chips">${dimensionLabels.map((label) => `<span>${escapeHtml(label)}</span>`).join("")}</div>` : ""}
      ${renderMiniBars(group)}
      ${rows.length === 1 ? renderMetricTiles(selected) : `
        <details class="resource-explorer">
          <summary>สำรวจรายละเอียดตามมิติ <span>⌄</span></summary>
          <div class="resource-explorer-body">
            <label><span>เลือกรายการเปรียบเทียบ</span>
              <select data-resource-select="${groupIndex}" aria-label="เลือกมิติของ ${escapeHtml(group.resource_name)}">
                ${rows.map((row, index) => `<option value="${index}"${index === latestIndex ? " selected" : ""}>${escapeHtml(recordOptionLabel(row, index))}</option>`).join("")}
              </select>
            </label>
            <div id="resourceMetrics${groupIndex}">${renderMetricTiles(selected)}</div>
          </div>
        </details>`}
      <footer><span>นิยามและหน่วยยึดตามต้นทาง</span><a href="${escapeHtml(group.source_url)}" target="_blank" rel="noreferrer">เปิดชุดข้อมูล ↗</a></footer>
    </article>`;
}

function renderAllData(briefing) {
  const { sra, housing } = briefing.sections;
  const groups = housing.resource_groups || [];
  const categoryMap = new Map();
  groups.forEach((group, index) => {
    const category = group.dataset_title || "ข้อมูลอื่น";
    if (!categoryMap.has(category)) categoryMap.set(category, []);
    categoryMap.get(category).push({ group, index });
  });
  const housingContent = [...categoryMap.entries()].map(([category, items], categoryIndex) => `
    <details class="dimension-category"${categoryIndex === 0 ? " open" : ""}>
      <summary><div><strong>${escapeHtml(category)}</strong><small>${formatNumber(items.length)} ชุดข้อมูลที่ผูกจังหวัดได้</small></div><span>⌄</span></summary>
      <div class="dimension-category-body">${items.map(({ group, index }) => renderResourceCard(group, index)).join("")}</div>
    </details>`).join("");
  const sraContent = sra.status === "available"
    ? `<div class="interpreted-metrics">${sra.items.map((item) => `<div><small>${escapeHtml(fieldLabel(item.metric_key))}</small><strong>${formatNumber(item.value, 2)} ${escapeHtml(displayUnit(item.unit))}</strong></div>`).join("")}</div>`
    : '<div class="data-absence"><strong>ไม่มีข้อมูลจังหวัดนี้ใน API ปี 2569</strong><p>ระบบแสดงสถานะว่าไม่มี record และไม่แทนค่าด้วยศูนย์</p></div>';
  document.getElementById("allDataSections").innerHTML = `
    <section class="dimension-intro">
      <span>Housing intelligence</span>
      <h3>ข้อมูลที่อยู่อาศัยในภาษาที่อ่านง่าย</h3>
      <p>เลือกมิติเพื่อดูรายละเอียด ระบบคงค่าต้นทางและไม่สร้างคะแนนเปรียบเทียบจังหวัดใหม่</p>
    </section>
    ${housingContent || '<div class="data-absence"><strong>ยังไม่มีข้อมูลที่อยู่อาศัยของจังหวัดนี้</strong></div>'}
    <details class="dimension-category sra-category">
      <summary><div><strong>SRA-DSS</strong><small>สถานการณ์ความเปราะบางจาก aggregate API</small></div><span>⌄</span></summary>
      <div class="dimension-category-body">${sraContent}</div>
    </details>`;
}

function updateResourceRecord(groupIndex, rowIndex) {
  const group = state.currentBriefing?.sections?.housing?.resource_groups?.[groupIndex];
  const target = document.getElementById(`resourceMetrics${groupIndex}`);
  if (!group || !target) return;
  target.innerHTML = renderMetricTiles(group.rows?.[rowIndex]);
}

function renderSources(briefing) {
  const statusLabel = {
    available: "มีข้อมูล",
    source_has_no_record_for_province: "ไม่มีรายการจังหวัดนี้",
    not_province_scoped: "ไม่ผูกจังหวัด",
  };
  document.getElementById("provinceSources").innerHTML = briefing.source_coverage
    .map((source) => {
      const apiFirst = source.acquisition_mode === "api_first";
      return `
        <article class="source-row ${escapeHtml(source.status)}">
          <span class="source-mode${apiFirst ? "" : " snapshot"}">${apiFirst ? "API" : "RAW"}</span>
          <div><strong>${escapeHtml(source.name_th)}</strong><small>${escapeHtml(statusLabel[source.status] || source.status)}${source.note_th ? ` · ${escapeHtml(source.note_th)}` : ""}</small></div>
          <a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer" aria-label="เปิดต้นทาง ${escapeHtml(source.name_th)}">↗</a>
        </article>`;
    })
    .join("");
}

function renderProvincePanel(briefing) {
  const province = briefing.province;
  state.currentBriefing = briefing;
  document.getElementById("panelLoading").hidden = true;
  document.getElementById("panelError").hidden = true;
  document.getElementById("panelContent").hidden = false;
  document.getElementById("provinceMeta").textContent = `${province.region} · รหัส ${province.province_code}`;
  document.getElementById("provinceName").textContent = province.province_name_th;
  document.getElementById("provinceEnglish").textContent = province.province_name_en;
  document.getElementById("coverageCount").textContent = `${formatNumber(briefing.available_source_ids?.length || 0)} / 10`;
  renderExecutiveSignals(briefing);
  renderDecisionNarrative(briefing);
  renderAreaProjects(briefing.sections.area_based);
  renderInnovations(briefing.sections.innovation);
  renderCulture(briefing.sections.culture);
  renderAllData(briefing);
  renderSources(briefing);
  document.getElementById("panelUpdated").textContent = `สร้าง Gold projection ${formatDate(briefing.generated_at)}`;
  document.getElementById("provinceApiLink").href = `/api/public/v1/provinces/${province.province_code}/briefing`;
  const requestedView = new URLSearchParams(window.location.search).get("view");
  if (["overview", "portfolio", "dimensions", "sources"].includes(requestedView)) activatePanelTab(requestedView, false);
  document.getElementById("provinceName").focus({ preventScroll: true });
}

function renderPanelError() {
  document.getElementById("panelLoading").hidden = true;
  document.getElementById("panelContent").hidden = true;
  document.getElementById("panelError").hidden = false;
}

async function selectProvince(code, moveMap = true) {
  const normalized = String(code ?? "").padStart(2, "0");
  const provinceMeta = provinceByCode(normalized);
  if (!provinceMeta) return;
  state.hoverPopup?.remove();

  const previousCode = state.selectedCode;
  setFeatureSelection(normalized);
  state.selectedCode = normalized;
  if (previousCode && previousCode !== normalized && state.mapLoaded) {
    state.map.setFeatureState({ source: "provinces", id: previousCode }, { selected: false });
    state.map.setFeatureState({ source: "provinces", id: normalized }, { selected: true });
  }
  updateLabelVisibility();
  openPanelLoading(provinceMeta);
  if (moveMap) fitProvince(provinceMeta);

  const url = new URL(window.location.href);
  url.searchParams.set("province", normalized);
  window.history.replaceState({}, "", url);

  const token = ++state.requestToken;
  try {
    const response = await fetch(`/api/public/v1/provinces/${normalized}/briefing`, { cache: "no-store" });
    if (!response.ok) throw new Error(`Province API ${response.status}`);
    const province = await response.json();
    if (token !== state.requestToken || state.selectedCode !== normalized) return;
    renderProvincePanel(province);
  } catch (error) {
    if (token !== state.requestToken) return;
    console.error(error);
    renderPanelError();
  }
}

function closePanel() {
  state.requestToken += 1;
  if (state.mapLoaded && state.selectedCode) {
    state.map.setFeatureState({ source: "provinces", id: state.selectedCode }, { selected: false });
  }
  state.selectedCode = null;
  updateLabelVisibility();
  const panel = document.getElementById("provincePanel");
  panel.classList.remove("is-open");
  panel.setAttribute("aria-hidden", "true");
  document.body.classList.remove("panel-open");
  document.getElementById("provinceSelect").value = "";
  document.querySelector(".picker-copy strong").textContent = "คลิกจังหวัด หรือค้นหาที่นี่";
  document.getElementById("mapPrompt").classList.remove("is-hidden");
  const url = new URL(window.location.href);
  url.searchParams.delete("province");
  url.searchParams.delete("view");
  window.history.replaceState({}, "", url);
}

function toggleCulturalPoints() {
  if (!state.mapLoaded) return;
  state.pointsVisible = !state.pointsVisible;
  const visibility = state.pointsVisible ? "visible" : "none";
  ["cultural-clusters", "cultural-point"].forEach((layer) => state.map.setLayoutProperty(layer, "visibility", visibility));
  document.getElementById("togglePoints").setAttribute("aria-pressed", String(state.pointsVisible));
}

function resetMap() {
  closePanel();
  if (!state.mapLoaded) return;
  state.map.easeTo({
    center: [101.15, 12.25],
    zoom: window.matchMedia("(max-width: 720px)").matches ? 3.0 : 3.25,
    pitch: 40,
    bearing: -8,
    padding: { top: 0, right: 0, bottom: 0, left: 0 },
    duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 900,
  });
}

function bindEvents() {
  document.getElementById("provinceSelect").addEventListener("change", (event) => {
    if (event.target.value) selectProvince(event.target.value, true);
  });
  document.getElementById("closePanel").addEventListener("click", closePanel);
  document.getElementById("resetMap").addEventListener("click", resetMap);
  document.getElementById("togglePoints").addEventListener("click", toggleCulturalPoints);
  document.getElementById("retryProvince").addEventListener("click", () => {
    if (state.selectedCode) selectProvince(state.selectedCode, false);
  });
  document.querySelectorAll("[data-panel-tab]").forEach((button) => {
    button.addEventListener("click", () => activatePanelTab(button.dataset.panelTab));
  });
  document.getElementById("cultureSearch").addEventListener("input", (event) => {
    state.cultureQuery = event.target.value;
    state.cultureVisible = 12;
    if (state.currentBriefing) renderCulture(state.currentBriefing.sections.culture);
  });
  document.getElementById("loadMoreCulture").addEventListener("click", () => {
    state.cultureVisible += 12;
    if (state.currentBriefing) renderCulture(state.currentBriefing.sections.culture);
  });
  document.getElementById("allDataSections").addEventListener("change", (event) => {
    const select = event.target.closest("[data-resource-select]");
    if (!select) return;
    updateResourceRecord(Number(select.dataset.resourceSelect), Number(select.value));
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.selectedCode) closePanel();
  });
}

function initMap() {
  if (!window.maplibregl) {
    document.getElementById("mapFallback").hidden = false;
    return;
  }

  const map = new window.maplibregl.Map({
    container: "provinceMap",
    style: {
      version: 8,
      sources: {},
      layers: [{ id: "background", type: "background", paint: { "background-color": "#06110e" } }],
    },
    center: [101.15, 12.25],
    zoom: window.matchMedia("(max-width: 720px)").matches ? 3.0 : 3.25,
    pitch: 40,
    bearing: -8,
    minZoom: 2.8,
    maxZoom: 13,
    maxBounds: [[88, 0], [114, 27]],
    antialias: true,
    attributionControl: false,
  });
  state.map = map;
  state.hoverPopup = new window.maplibregl.Popup({
    closeButton: false,
    closeOnClick: false,
    offset: 18,
    className: "evidence-popup",
  });
  map.addControl(new window.maplibregl.AttributionControl({ compact: true, customAttribution: "ขอบเขตจังหวัด ปภ. · Cultural Map Thailand" }), "bottom-right");
  map.on("load", () => {
    state.mapLoaded = true;
    map.addSource("provinces", { type: "geojson", data: state.boundaries, promoteId: "province_code" });
    const paint = metricPaint();
    map.addLayer({
      id: "province-base",
      type: "fill",
      source: "provinces",
      paint: {
        "fill-color": paint.baseColor,
        "fill-opacity": 0.9,
      },
    });
    map.addLayer({
      id: "province-extrusion",
      type: "fill-extrusion",
      source: "provinces",
      minzoom: 5.2,
      paint: {
        "fill-extrusion-color": paint.color,
        "fill-extrusion-height": paint.height,
        "fill-extrusion-base": 0,
        "fill-extrusion-opacity": 0.88,
        "fill-extrusion-vertical-gradient": false,
      },
    });
    map.addLayer({
      id: "province-outline",
      type: "line",
      source: "provinces",
      paint: {
        "line-color": ["case", ["boolean", ["feature-state", "selected"], false], "#fff1bd", "rgba(220,255,239,0.64)"],
        "line-width": ["case", ["boolean", ["feature-state", "selected"], false], 2.4, 0.72],
        "line-opacity": 0.82,
      },
    });

    map.addSource("cultural-points", {
      type: "geojson",
      data: state.points,
      cluster: true,
      clusterRadius: 44,
      clusterMaxZoom: 10,
    });
    map.addLayer({
      id: "cultural-clusters",
      type: "circle",
      source: "cultural-points",
      filter: ["has", "point_count"],
      layout: { visibility: "none" },
      paint: {
        "circle-color": "#f4cf72",
        "circle-radius": ["interpolate", ["linear"], ["get", "point_count"], 2, 7, 100, 16, 800, 25],
        "circle-stroke-width": 2,
        "circle-stroke-color": "#06110e",
        "circle-opacity": 0.92,
      },
    });
    map.addLayer({
      id: "cultural-point",
      type: "circle",
      source: "cultural-points",
      filter: ["!", ["has", "point_count"]],
      layout: { visibility: "none" },
      paint: {
        "circle-color": "#f4cf72",
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 2, 10, 5],
        "circle-stroke-width": 1,
        "circle-stroke-color": "#06110e",
        "circle-opacity": 0.9,
      },
    });

    map.on("mousemove", "province-base", (event) => {
      map.getCanvas().style.cursor = "pointer";
      const code = event.features?.[0]?.properties?.province_code;
      if (!code || code === state.hoveredCode) return;
      if (state.hoveredCode) map.setFeatureState({ source: "provinces", id: state.hoveredCode }, { hover: false });
      state.hoveredCode = code;
      map.setFeatureState({ source: "provinces", id: code }, { hover: true });
      const province = provinceByCode(code);
      if (province) {
        state.hoverPopup
          .setLngLat(event.lngLat)
          .setHTML(`<strong>${escapeHtml(province.province_name_th)}</strong><span>เชื่อมได้ ${formatNumber(province.evidence_source_count)} แหล่ง</span><small>คลิกเพื่อเปิดข้อมูล</small>`)
          .addTo(map);
      }
      updateLabelVisibility();
    });
    map.on("mouseleave", "province-base", () => {
      map.getCanvas().style.cursor = "";
      if (state.hoveredCode) map.setFeatureState({ source: "provinces", id: state.hoveredCode }, { hover: false });
      state.hoveredCode = null;
      state.hoverPopup?.remove();
      updateLabelVisibility();
    });
    map.on("click", "province-base", (event) => {
      const code = event.features?.[0]?.properties?.province_code;
      if (code) selectProvince(code, true);
    });
    map.on("click", "cultural-clusters", async (event) => {
      const feature = event.features?.[0];
      if (!feature) return;
      const zoom = await map.getSource("cultural-points").getClusterExpansionZoom(feature.properties.cluster_id);
      map.easeTo({ center: feature.geometry.coordinates, zoom });
    });
    map.on("click", "cultural-point", (event) => {
      const code = event.features?.[0]?.properties?.province_code;
      if (code) selectProvince(code, true);
    });
    map.on("zoomend", updateLabelVisibility);

    addProvinceLabels();
    if (state.selectedCode) {
      map.setFeatureState({ source: "provinces", id: state.selectedCode }, { selected: true });
      fitProvince(provinceByCode(state.selectedCode));
    }
  });

  map.on("error", (event) => {
    if (!state.mapLoaded && event?.error) document.getElementById("mapFallback").hidden = false;
  });
}

async function loadDashboard() {
  try {
    const [catalogResponse, boundaryResponse, pointResponse] = await Promise.all([
      fetch("/api/public/v1/catalog"),
      fetch("/api/public/v1/map/provinces"),
      fetch("/api/public/v1/map/cultural-points"),
    ]);
    if (![catalogResponse, boundaryResponse, pointResponse].every((response) => response.ok)) {
      throw new Error("Public data API returned an error");
    }
    [state.catalog, state.boundaries, state.points] = await Promise.all([
      catalogResponse.json(),
      boundaryResponse.json(),
      pointResponse.json(),
    ]);
    renderOverview();
    bindEvents();
    initMap();

    const initialCode = new URLSearchParams(window.location.search).get("province");
    if (initialCode && provinceByCode(initialCode)) selectProvince(initialCode, false);
  } catch (error) {
    console.error(error);
    document.getElementById("mapFallback").hidden = false;
    showToast("โหลดข้อมูลสาธารณะไม่สำเร็จ");
  }
}

loadDashboard();
