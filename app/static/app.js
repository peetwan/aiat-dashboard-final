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
  currentSummary: null,
  currentBriefing: null,
  briefingLoading: false,
  cultureVisible: 12,
  cultureQuery: "",
  projectQuery: "",
  projectYear: "",
  projectDistrict: "",
  hoverPopup: null,
};

const THAILAND_BOUNDS = [[97.2, 5.5], [105.7, 20.5]];

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
  if (tabName === "projects" || tabName === "portfolio") ensurePortfolioLoaded();
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
  // Flat single-hue scale that stays readable on the light canvas.
  const richnessColor = [
    "step",
    sourceCount,
    "#e4eae3",
    1, "#cfe4d4",
    2, "#a9d3b8",
    3, "#7fbf97",
    4, "#54a578",
    6, "#2f875c",
    8, "#176747",
  ];
  return {
    baseColor: richnessColor,
    color: [
      "case",
      ["boolean", ["feature-state", "selected"], false],
      "#0f4a32",
      richnessColor,
    ],
  };
}

function updateLabelVisibility() {
  if (!state.mapLoaded) return;
  const zoom = state.map.getZoom();
  const threshold = zoom < 5.4 ? 4 : zoom < 6.4 ? 2 : zoom < 7.4 ? 1 : 0;
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
    zoom: isMobile ? 6.4 : 7,
    pitch: 0,
    bearing: 0,
    padding: isMobile ? { top: 72, right: 18, bottom: 360, left: 18 } : { top: 80, right: 660, bottom: 60, left: 60 },
    duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 700,
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
  state.currentSummary = null;
  state.currentBriefing = null;
  state.briefingLoading = false;
  state.cultureVisible = 12;
  state.cultureQuery = "";
  state.projectQuery = "";
  state.projectYear = "";
  state.projectDistrict = "";
  document.getElementById("portfolioLoading").hidden = false;
  document.getElementById("portfolioEmpty").hidden = true;
  document.getElementById("projectsLoading").hidden = false;
  document.getElementById("projectsEmpty").hidden = true;
  document.getElementById("researchSection").hidden = true;
  ["areaSection", "innovationSection", "requirementsSection", "tourismSection", "cultureSection"].forEach((id) => {
    document.getElementById(id).hidden = true;
  });
  const cultureSearch = document.getElementById("cultureSearch");
  if (cultureSearch) cultureSearch.value = "";
  const projectSearch = document.getElementById("projectSearch");
  if (projectSearch) projectSearch.value = "";
  ["projectYearFilter", "projectDistrictFilter"].forEach((id) => {
    const select = document.getElementById(id);
    if (select) select.value = "";
  });
  activatePanelTab("overview", false);
}

function trimText(value, length = 180) {
  const text = String(value ?? "").trim();
  return text.length > length ? `${text.slice(0, length).trim()}…` : text;
}

function renderExecutiveSignals(summary) {
  const signals = summary.readout?.context_metrics || [];
  document.getElementById("executiveSignals").innerHTML = signals.length
    ? signals
        .map(
          (signal) => `
            <article class="decision-card">
              <span>${escapeHtml(signal.label_th)}</span>
              <strong>${escapeHtml(signal.display_value)}</strong>
              <small>${escapeHtml(signal.unit || "")}</small>
            </article>`,
        )
        .join("")
    : '<article class="empty-data"><strong>ยังไม่มีค่าระดับจังหวัดที่สรุปได้</strong></article>';
}

function applyProjectDistrict(district) {
  state.projectDistrict = district;
  state.projectYear = "";
  state.projectQuery = "";
  const search = document.getElementById("projectSearch");
  if (search) search.value = "";
  activatePanelTab("projects");
  if (state.currentBriefing) {
    populateProjectFilters(state.currentBriefing.sections.area_based);
    renderAreaProjects(state.currentBriefing.sections.area_based);
  }
}

function researchBars(entries, unitLabel) {
  const max = Math.max(...entries.map((entry) => Number(entry.value) || 0), 1);
  return `<div class="research-bars">${entries
    .map(
      (entry) => `
        <div class="research-bar-row">
          <span>${escapeHtml(entry.label_th)}</span>
          <i><b style="width:${Math.max(4, (Number(entry.value) / max) * 100).toFixed(1)}%"></b></i>
          <strong>${formatNumber(entry.value)}${unitLabel ? ` ${unitLabel}` : ""}</strong>
        </div>`,
    )
    .join("")}</div>`;
}

function renderResearchPortfolio(summary) {
  const section = document.getElementById("researchSection");
  const portfolio = summary.research_portfolio;
  if (!portfolio) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  document.getElementById("researchScope").textContent = portfolio.scope_note_th || "";

  const stats = [
    ["โครงการที่เชื่อมได้", portfolio.project_count, "โครงการ"],
    ["หน่วยวิจัยที่รับทุน", portfolio.university_count, "แห่ง"],
    ["อำเภอที่มีโครงการ", portfolio.district_count, "อำเภอ"],
    ["นวัตกรรมพร้อมใช้", portfolio.innovation_count, "รายการ"],
  ];
  const statHtml = `<div class="research-stats">${stats
    .map(
      ([label, value, unit]) => `
        <article><span>${escapeHtml(label)}</span><strong>${formatNumber(value)}</strong><small>${escapeHtml(unit)}</small></article>`,
    )
    .join("")}</div>`;

  const yearsHtml = portfolio.fiscal_years?.length
    ? `<section class="research-block"><h4>โครงการรายปีงบประมาณ</h4>${researchBars(portfolio.fiscal_years, "โครงการ")}</section>`
    : "";
  const universitiesHtml = portfolio.universities?.length
    ? `<section class="research-block"><h4>มหาวิทยาลัย/หน่วยวิจัยที่รับทุน</h4>${researchBars(portfolio.universities, "")}</section>`
    : "";
  const districtsHtml = portfolio.districts?.length
    ? `<section class="research-block"><h4>กดอำเภอเพื่อดูโครงการและตัวคนในพื้นที่</h4><div class="district-chips">${portfolio.districts
        .map(
          (district) => `
            <button type="button" class="district-chip" data-district="${escapeHtml(district.label_th)}">
              <strong>อ.${escapeHtml(district.label_th)}</strong><span>${formatNumber(district.value)} โครงการ</span>
            </button>`,
        )
        .join("")}</div></section>`
    : "";

  const funding = portfolio.funding || {};
  const fundingHtml = `
    <section class="research-block funding-block">
      <h4>${escapeHtml(funding.label_th || "ทุนที่ปรากฏในข้อมูล")}</h4>
      <div class="funding-grid">
        <article><span>นวัตกรรมที่ระบุทุน บพท.</span><strong>${formatNumber(funding.pmua_funded_count || 0)}</strong><small>รายการ</small></article>
        <article><span>มูลค่าทุน บพท. ที่ต้นทางกรอก</span><strong>${formatNumber(funding.pmua_amount_baht || 0)}</strong><small>บาท</small></article>
        <article><span>มูลค่านวัตกรรมรวมที่กรอก</span><strong>${formatNumber(funding.innovation_value_baht_total || 0)}</strong><small>บาท</small></article>
      </div>
      ${funding.note_th ? `<small class="funding-note">${escapeHtml(funding.note_th)}</small>` : ""}
    </section>`;

  const gapsHtml = portfolio.data_gaps_th?.length
    ? `<details class="research-gaps"><summary>ข้อมูลที่ผู้บริหารถามถึงแต่ยังไม่มีในแหล่งสาธารณะ (${portfolio.data_gaps_th.length})</summary><ul>${portfolio.data_gaps_th
        .map((gap) => `<li>${escapeHtml(gap)}</li>`)
        .join("")}</ul></details>`
    : "";

  document.getElementById("researchPortfolio").innerHTML = `
    ${statHtml}
    <div class="research-grid">${yearsHtml}${universitiesHtml}</div>
    ${districtsHtml}
    ${fundingHtml}
    ${gapsHtml}`;

  document.querySelectorAll(".district-chip").forEach((chip) => {
    chip.addEventListener("click", () => applyProjectDistrict(chip.dataset.district));
  });
}

function renderDecisionNarrative(summary) {
  const facts = summary.readout?.observations || [];
  document.getElementById("decisionNarrative").innerHTML = facts.length
    ? facts.map((fact) => `
        <article class="briefing-fact">
          <i aria-hidden="true"></i>
          <div><small>${escapeHtml(fact.label_th)}</small><p>${escapeHtml(fact.text_th)}</p></div>
        </article>`).join("")
    : '<article class="empty-data"><strong>ยังไม่มีข้อมูลเพียงพอสำหรับสรุปภาพจังหวัด</strong></article>';
}

function populateProjectFilters(section) {
  const items = section.items || [];
  const years = [...new Set(items.map((item) => item.fiscal_year).filter(Boolean))].sort();
  const districts = [...new Set(items.map((item) => item.district).filter(Boolean))].sort((a, b) =>
    String(a).localeCompare(String(b), "th"),
  );
  const yearSelect = document.getElementById("projectYearFilter");
  const districtSelect = document.getElementById("projectDistrictFilter");
  yearSelect.innerHTML = '<option value="">ทุกปี</option>' + years.map((year) => `<option value="${escapeHtml(year)}">${escapeHtml(year)}</option>`).join("");
  districtSelect.innerHTML = '<option value="">ทุกอำเภอ</option>' + districts.map((district) => `<option value="${escapeHtml(district)}">${escapeHtml(district)}</option>`).join("");
  yearSelect.value = state.projectYear && years.includes(state.projectYear) ? state.projectYear : "";
  districtSelect.value = state.projectDistrict && districts.includes(state.projectDistrict) ? state.projectDistrict : "";
}

function renderAreaProjects(section) {
  const container = document.getElementById("areaProjects");
  document.getElementById("areaSection").hidden = section.status !== "available";
  if (section.status !== "available") return;
  const query = state.projectQuery.trim().toLocaleLowerCase("th");
  const filtered = (section.items || []).filter((item) => {
    if (state.projectYear && item.fiscal_year !== state.projectYear) return false;
    if (state.projectDistrict && item.district !== state.projectDistrict) return false;
    if (!query) return true;
    return [item.project_name, item.business_name, item.research_unit, item.district, item.subdistrict]
      .filter(Boolean)
      .join(" ")
      .toLocaleLowerCase("th")
      .includes(query);
  });
  document.getElementById("projectResultCount").textContent =
    `แสดง ${formatNumber(filtered.length)} จาก ${formatNumber((section.items || []).length)} โครงการ`;
  container.innerHTML = filtered
    .map(
      (item) => `
        <article class="data-card project-card">
          <div class="record-kicker"><span>ปีงบประมาณ ${escapeHtml(item.fiscal_year || "ไม่ระบุ")}</span><span>${escapeHtml([item.district ? `อ.${item.district}` : "", item.subdistrict ? `ต.${item.subdistrict}` : ""].filter(Boolean).join(" · ") || "ไม่ระบุพื้นที่")}</span></div>
          <h3>${escapeHtml(item.project_name || "ไม่ระบุชื่อโครงการ")}</h3>
          <p class="project-people"><span>ผู้ประกอบการ/กลุ่มเป้าหมาย</span><strong>${escapeHtml(item.business_name || "ต้นทางไม่ระบุ")}</strong></p>
          <footer><span>${escapeHtml(item.research_unit || "ไม่ระบุหน่วยวิจัย")}</span><a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">ต้นทาง</a></footer>
        </article>`,
    )
    .join("") || '<article class="empty-data"><strong>ไม่พบโครงการที่ตรงกับตัวกรอง</strong><span>ลองล้างคำค้นหรือเลือกทุกปี/ทุกอำเภอ</span></article>';
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
          <footer><span>${escapeHtml(item.owner_affiliation_name || "ไม่ระบุสังกัด")}</span><a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">รายละเอียด</a></footer>
        </article>`;
    })
    .join("");
}

function localizedText(value) {
  if (value === null || value === undefined) return "";
  if (typeof value !== "object") return String(value);
  return String(value.TH ?? value.th ?? value.EN ?? value.en ?? "");
}

function safeExternalUrl(value) {
  try {
    const url = new URL(String(value || ""));
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function renderRequirements(section = {}) {
  const wrapper = document.getElementById("requirementsSection");
  const items = section.items || [];
  wrapper.hidden = section.status !== "available" || items.length === 0;
  if (wrapper.hidden) return;
  document.getElementById("requirementItems").innerHTML = items.map((item) => {
    const area = item.area || item.areas?.[0] || {};
    const location = [
      firstRequirementValue(item.subdistrict, item.tambon, area.tambon),
      firstRequirementValue(item.district, item.amphoe, area.amphoe),
    ].filter(Boolean).join(" · ");
    const sourceUrl = safeExternalUrl(item.source_url);
    return `
      <article class="data-card requirement-card">
        <div class="record-kicker"><span>${escapeHtml(item.category || item.category_label || "โจทย์ความต้องการ")}</span><span>${escapeHtml(location || "ยืนยันระดับจังหวัด")}</span></div>
        <h3>${escapeHtml(item.title || item.requirement_title || item.name || "ไม่ระบุชื่อโจทย์")}</h3>
        <p>${escapeHtml(trimText(item.summary || item.description || "โจทย์จากทะเบียนสาธารณะของ AppTech", 180))}</p>
        <footer><span>${escapeHtml(item.owner_affiliation_name || item.organization || item.scope_note_th || "ข้อมูล candidate")}</span>${sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noreferrer">ต้นทาง</a>` : ""}</footer>
      </article>`;
  }).join("");
}

function firstRequirementValue(...values) {
  return values.find((value) => value !== null && value !== undefined && value !== "") || "";
}

function tourismPage(section, pageId) {
  return (section?.items || []).find((item) => item.page_id === pageId) || { data: {} };
}

function renderTourism(section = {}) {
  const wrapper = document.getElementById("tourismSection");
  const available = section.status === "available" && (section.items || []).length > 0;
  wrapper.hidden = !available;
  if (!available) return;

  const contactPage = tourismPage(section, "contact");
  const homePage = tourismPage(section, "homepage");
  const lanternPage = tourismPage(section, "komepage");
  const recommendPage = tourismPage(section, "recommend");
  const travelPage = tourismPage(section, "travel");
  const contact = contactPage.data || {};
  const travel = travelPage.data || {};
  const categories = recommendPage.data?.categories || [];
  const recommendations = categories.flatMap((category) =>
    (category.items || []).map((item) => ({ ...item, category_th: localizedText(category.label) })),
  );
  const stations = homePage.data?.map?.stations || [];
  const lanternGroupCount = Number(lanternPage.data?.lantern_group_count || 0);
  const trainServices = travel.train?.services || [];
  const tramServices = travel.tourism_tram?.services || [];
  const otherTransport = travel.other_transport || [];
  const serviceAvailability = contact.service_availability || [];
  const scrapedAt = (section.items || []).map((item) => item.scraped_at).filter(Boolean).sort().at(-1);

  document.getElementById("tourismUpdated").textContent = scrapedAt ? `snapshot ${formatDate(scrapedAt)}` : "public snapshot";
  document.getElementById("tourismFacts").innerHTML = [
    ["เรื่องแนะนำ", recommendations.length],
    ["สถานีหลัก", stations.length],
    ["เที่ยวรถ", trainServices.length + tramServices.length],
    ["กลุ่มทำโคม", lanternGroupCount],
  ].map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${formatNumber(value)}</strong></article>`).join("");

  const recommendationCards = recommendations.map((item) => {
    const imageUrl = safeExternalUrl(item.image_url);
    return `
      <article class="tourism-place">
        ${imageUrl ? `<img src="${escapeHtml(imageUrl)}" alt="" loading="lazy" referrerpolicy="no-referrer" />` : ""}
        <div><span>${escapeHtml(item.category_th || "แนะนำ")}</span><strong>${escapeHtml(localizedText(item.title) || "ไม่ระบุชื่อ")}</strong><p>${escapeHtml(trimText(localizedText(item.description), 125))}</p></div>
      </article>`;
  }).join("");

  const trainRows = trainServices.map((service) => `
    <article class="schedule-row">
      <time>${escapeHtml(service.departure_time || "ไม่ระบุเวลา")}</time>
      <div><strong>${escapeHtml(localizedText(service.origin?.name))} – ${escapeHtml(localizedText(service.destination?.name))}</strong><span>${escapeHtml(localizedText(service.description) || "รถไฟโดยสาร")}</span></div>
      <b>${service.fare?.amount !== null && service.fare?.amount !== undefined ? `${formatNumber(service.fare.amount)} บาท` : "ไม่ระบุราคา"}</b>
    </article>`).join("");
  const tramRows = tramServices.map((service) => `
    <article class="schedule-row tram-row">
      <time>${escapeHtml(service.departure_time || "ไม่ระบุเวลา")}</time>
      <div><strong>รถรางท่องเที่ยว</strong><span>${escapeHtml(localizedText(service.route_name))}</span></div>
      <b>${service.fare?.amount !== null && service.fare?.amount !== undefined ? `${formatNumber(service.fare.amount)} บาท` : "ไม่ระบุราคา"}</b>
    </article>`).join("");

  const stationRows = stations.map((station) => {
    const nearbyCount = Number(station.nearby_count || 0);
    return `<article class="tourism-station"><strong>${escapeHtml(localizedText(station.name))}</strong><span>${formatNumber(nearbyCount)} จุดใกล้เคียง</span></article>`;
  }).join("");
  const transportTags = otherTransport.map((item) => `<span>${escapeHtml(localizedText(item.name) || item.type)}</span>`).join("");
  const serviceTags = serviceAvailability
    .map((item) => localizedText(item.label).replace(/\s*:\s*$/, ""))
    .filter(Boolean)
    .map((label) => `<span>${escapeHtml(label)}</span>`)
    .join("");

  const sourceUrl = safeExternalUrl(recommendPage.source_url || travelPage.source_url || homePage.source_url);
  document.getElementById("tourismItems").innerHTML = `
    ${recommendationCards ? `<section class="tourism-block"><header><h3>ของดีและจุดแนะนำ</h3><span>${formatNumber(recommendations.length)} รายการ</span></header><div class="tourism-place-grid">${recommendationCards}</div></section>` : ""}
    ${(trainRows || tramRows) ? `<section class="tourism-block"><header><h3>ตารางเดินทาง</h3><span>รถไฟและรถราง</span></header><div class="schedule-list">${trainRows}${tramRows}</div>${transportTags ? `<div class="transport-tags">${transportTags}</div>` : ""}</section>` : ""}
    ${stationRows ? `<section class="tourism-block"><header><h3>จุดตั้งต้นเที่ยวเมือง</h3><span>จำนวนจุดใกล้เคียง</span></header><div class="station-grid">${stationRows}</div></section>` : ""}
    ${serviceTags ? `<section class="tourism-block tourism-service-summary"><header><h3>บริการที่มีในข้อมูลต้นทาง</h3><span>${formatNumber(serviceAvailability.length)} บริการ</span></header><div class="transport-tags">${serviceTags}</div></section>` : ""}
    ${sourceUrl ? `<a class="tourism-source-link" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noreferrer">เปิดข้อมูลท่องเที่ยวต้นทาง</a>` : ""}`;
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
            <div class="record-kicker"><span>${escapeHtml(item.cultural_type || "ทุนวัฒนธรรม")}</span><span>${escapeHtml(item.category || "ไม่ระบุหมวด")}</span></div>
            <h3>${escapeHtml(item.title_th || "ไม่ระบุชื่อ")}</h3>
            <p>${escapeHtml(trimText(item.risk_reason || item.history || "ต้นทางไม่ได้ระบุเหตุผลความเสี่ยง", 180))}</p>
            <footer><span>${escapeHtml([item.tambon, item.amphoe].filter(Boolean).join(" · ") || "ไม่ระบุพื้นที่ย่อย")}</span><a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">ต้นทาง</a></footer>
          </div>
        </article>`,
    )
    .join("") || '<article class="empty-data"><strong>ไม่พบรายการที่ตรงกับคำค้น</strong><span>ลองใช้ชื่ออำเภอหรือหมวดวัฒนธรรม</span></article>';
}

function renderDimensionMetric(metric) {
  return `
    <article class="clean-metric${metric.attention ? " is-attention" : ""}">
      <div class="clean-metric-head">
        <span>${escapeHtml(metric.label_th)}</span>
        <strong>${escapeHtml(metric.display_value)}</strong>
      </div>
      <p>${escapeHtml(metric.comparison_th)}</p>
      <div class="comparison-track" aria-label="${escapeHtml(metric.label_th)} ${escapeHtml(metric.comparison_th)}">
        <i class="benchmark-marker" style="left:${Number(metric.benchmark_position_pct).toFixed(1)}%"></i>
        <b class="value-marker" style="left:${Number(metric.position_pct).toFixed(1)}%"></b>
      </div>
      <small>${escapeHtml(metric.benchmark_label_th)} ${escapeHtml(metric.benchmark_display_value)}</small>
    </article>`;
}

function renderBreakdown(breakdown) {
  const items = breakdown.items || [];
  if (!items.length) return "";
  if (breakdown.kind === "trend") {
    const values = items.map((item) => Number(item.value)).filter(Number.isFinite);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = Math.max(max - min, 1);
    return `
      <section class="clean-breakdown trend-breakdown">
        <h4>${escapeHtml(breakdown.label_th)}</h4>
        <div class="trend-bars">${items.map((item) => {
          const height = 28 + ((Number(item.value) - min) / span) * 72;
          return `<div title="${escapeHtml(item.display_value)}"><i style="height:${height.toFixed(1)}%"></i><span>${escapeHtml(item.label_th)}</span></div>`;
        }).join("")}</div>
        <strong>${escapeHtml(items.at(-1)?.display_value || "")}</strong>
      </section>`;
  }
  const max = Math.max(...items.map((item) => Number(item.value) || 0), 1);
  return `
    <section class="clean-breakdown">
      <h4>${escapeHtml(breakdown.label_th)}</h4>
      <div class="clean-bars">${items.map((item) => {
        const width = breakdown.kind === "distribution"
          ? Number(item.share_pct || 0)
          : (Number(item.value || 0) / max) * 100;
        return `<div class="clean-bar-row"><span>${escapeHtml(item.label_th)}</span><i><b style="width:${Math.max(3, width).toFixed(1)}%"></b></i>${breakdown.kind === "scores" ? `<strong>${escapeHtml(item.display_value)}</strong>` : ""}</div>`;
      }).join("")}</div>
      ${breakdown.note_th ? `<small>${escapeHtml(breakdown.note_th)}</small>` : ""}
    </section>`;
}

function renderHighlights(highlights) {
  if (!highlights?.length) return "";
  return `<div class="dimension-highlights">${highlights.slice(0, 4).map((item) => `
    <article>
      <span>${item.kind === "project" ? "โครงการ" : item.kind === "innovation" ? "นวัตกรรม" : "รายการจากต้นทาง"}</span>
      <strong>${escapeHtml(item.title_th)}</strong>
      ${item.detail_th ? `<p>${escapeHtml(trimText(item.detail_th, 160))}</p>` : ""}
      ${item.meta_th ? `<small>${escapeHtml(item.meta_th)}</small>` : ""}
    </article>`).join("")}</div>`;
}

function renderAllData(summary) {
  const dimensions = summary.dimensions || [];
  const missing = summary.missing_dimensions || [];
  document.getElementById("allDataSections").innerHTML = dimensions.length
    ? `${dimensions.map((dimension) => `
        <article class="executive-dimension" data-dimension="${escapeHtml(dimension.key)}">
          <header>
            <span>${escapeHtml(dimension.label_th)}</span>
            <p>${escapeHtml(dimension.summary_th)}</p>
          </header>
          ${dimension.metrics?.length ? `<div class="clean-metric-list">${dimension.metrics.map(renderDimensionMetric).join("")}</div>` : ""}
          ${dimension.breakdowns?.map(renderBreakdown).join("") || ""}
          ${renderHighlights(dimension.highlights)}
        </article>`).join("")}
        ${missing.length ? `<p class="missing-dimensions">ยังไม่มีข้อมูลระดับจังหวัดในมิติ ${missing.map((item) => escapeHtml(item.label_th)).join(" · ")}</p>` : ""}`
    : '<article class="empty-data"><strong>ยังไม่มีข้อมูลระดับจังหวัดที่สรุปเป็นรายมิติได้</strong></article>';
}

function renderSources(summary) {
  const statusLabel = {
    available: "มีข้อมูล",
    source_has_no_record_for_province: "ไม่มีรายการจังหวัดนี้",
    not_province_scoped: "ไม่ผูกจังหวัด",
  };
  document.getElementById("provinceSources").innerHTML = summary.source_coverage
    .map((source) => {
      const apiFirst = source.acquisition_mode === "api_first";
      return `
        <article class="source-row ${escapeHtml(source.status)}">
          <span class="source-mode${apiFirst ? "" : " snapshot"}">${apiFirst ? "API" : "RAW"}</span>
          <div><strong>${escapeHtml(source.name_th)}</strong><small>${escapeHtml(statusLabel[source.status] || source.status)}${source.note_th ? ` · ${escapeHtml(source.note_th)}` : ""}</small></div>
          <a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer" aria-label="เปิดต้นทาง ${escapeHtml(source.name_th)}">ดู</a>
        </article>`;
    })
    .join("");
}

function renderProvincePanel(summary) {
  const province = summary.province;
  state.currentSummary = summary;
  document.getElementById("panelLoading").hidden = true;
  document.getElementById("panelError").hidden = true;
  document.getElementById("panelContent").hidden = false;
  document.getElementById("provinceMeta").textContent = `${province.region} · รหัส ${province.province_code}`;
  document.getElementById("provinceName").textContent = province.province_name_th;
  document.getElementById("provinceEnglish").textContent = province.province_name_en;
  document.getElementById("coverageLabel").textContent = summary.coverage?.label_th || "ข้อมูลยังบาง";
  document.getElementById("coverageCount").textContent = `เชื่อม ${formatNumber(summary.coverage?.available_source_count || 0)} จาก ${formatNumber(summary.coverage?.public_source_count || 10)} แหล่ง`;
  renderResearchPortfolio(summary);
  renderExecutiveSignals(summary);
  renderDecisionNarrative(summary);
  renderAllData(summary);
  renderSources(summary);
  document.getElementById("panelUpdated").textContent = `อัปเดตชุดสรุป ${formatDate(summary.generated_at)}`;
  document.getElementById("provinceApiLink").href = `/api/public/v1/provinces/${province.province_code}/briefing`;
  const requestedView = new URLSearchParams(window.location.search).get("view");
  if (["overview", "projects", "portfolio", "dimensions", "sources"].includes(requestedView)) activatePanelTab(requestedView, false);
  document.getElementById("provinceName").focus({ preventScroll: true });
}

async function ensurePortfolioLoaded() {
  if (!state.selectedCode || state.currentBriefing || state.briefingLoading) return;
  const code = state.selectedCode;
  state.briefingLoading = true;
  document.getElementById("portfolioLoading").hidden = false;
  document.getElementById("portfolioEmpty").hidden = true;
  document.getElementById("projectsLoading").hidden = false;
  document.getElementById("projectsEmpty").hidden = true;
  try {
    const response = await fetch(`/api/public/v1/provinces/${code}/briefing`, { cache: "no-store" });
    if (!response.ok) throw new Error(`Province briefing API ${response.status}`);
    const briefing = await response.json();
    if (state.selectedCode !== code) return;
    state.currentBriefing = briefing;
    populateProjectFilters(briefing.sections.area_based);
    renderAreaProjects(briefing.sections.area_based);
    renderInnovations(briefing.sections.innovation);
    renderRequirements(briefing.sections.requirements);
    renderTourism(briefing.sections.tourism);
    renderCulture(briefing.sections.culture);
    const hasProjects = ["area_based", "innovation", "requirements"].some(
      (key) => briefing.sections[key]?.status === "available",
    );
    const hasPortfolio = ["tourism", "culture"].some(
      (key) => briefing.sections[key]?.status === "available",
    );
    document.getElementById("projectsEmpty").hidden = hasProjects;
    document.getElementById("portfolioEmpty").hidden = hasPortfolio;
  } catch (error) {
    console.error(error);
    ["projectsEmpty", "portfolioEmpty"].forEach((id) => {
      const element = document.getElementById(id);
      element.textContent = "โหลดรายการโครงการไม่สำเร็จ";
      element.hidden = false;
    });
  } finally {
    if (state.selectedCode === code) {
      document.getElementById("portfolioLoading").hidden = true;
      document.getElementById("projectsLoading").hidden = true;
    }
    state.briefingLoading = false;
  }
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
    const response = await fetch(`/api/public/v1/provinces/${normalized}/summary`, { cache: "no-store" });
    if (!response.ok) throw new Error(`Province API ${response.status}`);
    const summary = await response.json();
    if (token !== state.requestToken || state.selectedCode !== normalized) return;
    renderProvincePanel(summary);
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
  state.currentSummary = null;
  state.currentBriefing = null;
  state.briefingLoading = false;
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
  state.map.fitBounds(THAILAND_BOUNDS, {
    padding: window.matchMedia("(max-width: 720px)").matches
      ? { top: 84, right: 16, bottom: 96, left: 16 }
      : { top: 96, right: 60, bottom: 80, left: 60 },
    pitch: 0,
    bearing: 0,
    duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 700,
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
  document.getElementById("projectSearch").addEventListener("input", (event) => {
    state.projectQuery = event.target.value;
    if (state.currentBriefing) renderAreaProjects(state.currentBriefing.sections.area_based);
  });
  document.getElementById("projectYearFilter").addEventListener("change", (event) => {
    state.projectYear = event.target.value;
    if (state.currentBriefing) renderAreaProjects(state.currentBriefing.sections.area_based);
  });
  document.getElementById("projectDistrictFilter").addEventListener("change", (event) => {
    state.projectDistrict = event.target.value;
    if (state.currentBriefing) renderAreaProjects(state.currentBriefing.sections.area_based);
  });
  document.getElementById("loadMoreCulture").addEventListener("click", () => {
    state.cultureVisible += 12;
    if (state.currentBriefing) renderCulture(state.currentBriefing.sections.culture);
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
      layers: [{ id: "background", type: "background", paint: { "background-color": "#edf1ec" } }],
    },
    bounds: THAILAND_BOUNDS,
    fitBoundsOptions: {
      padding: window.matchMedia("(max-width: 720px)").matches
        ? { top: 84, right: 16, bottom: 96, left: 16 }
        : { top: 96, right: 60, bottom: 80, left: 60 },
    },
    minZoom: 3.6,
    maxZoom: 13,
    maxBounds: [[88, 0], [114, 27]],
    pitch: 0,
    bearing: 0,
    pitchWithRotate: false,
    dragRotate: false,
    touchPitch: false,
    antialias: true,
    attributionControl: false,
  });
  map.touchZoomRotate?.disableRotation();
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
        "fill-color": paint.color,
        "fill-opacity": [
          "case",
          ["boolean", ["feature-state", "hover"], false],
          1,
          0.94,
        ],
      },
    });
    map.addLayer({
      id: "province-outline",
      type: "line",
      source: "provinces",
      paint: {
        "line-color": "#ffffff",
        "line-width": ["interpolate", ["linear"], ["zoom"], 4, 0.7, 8, 1.4],
        "line-opacity": 0.95,
      },
    });
    map.addLayer({
      id: "province-highlight",
      type: "line",
      source: "provinces",
      paint: {
        "line-color": [
          "case",
          ["boolean", ["feature-state", "selected"], false],
          "#0f4a32",
          "#1d7a52",
        ],
        "line-width": [
          "case",
          ["boolean", ["feature-state", "selected"], false],
          3,
          2.2,
        ],
        "line-opacity": [
          "case",
          ["boolean", ["feature-state", "selected"], false],
          1,
          ["boolean", ["feature-state", "hover"], false],
          1,
          0,
        ],
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
        "circle-color": "#e39b17",
        "circle-radius": ["interpolate", ["linear"], ["get", "point_count"], 2, 7, 100, 16, 800, 25],
        "circle-stroke-width": 2,
        "circle-stroke-color": "#ffffff",
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
        "circle-color": "#e39b17",
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 2.5, 10, 5.5],
        "circle-stroke-width": 1,
        "circle-stroke-color": "#ffffff",
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
