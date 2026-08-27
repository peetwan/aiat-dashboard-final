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
  mapMode: "projects",
  disasterProvinces: null,
  selectedRegion: null,
  hoveredRegion: null,
  regions: {},
  regionMarkers: [],
  countryZoom: null,
  pendingLock: null,
  disasterCharts: [],
  pendingDisasterCharts: [],
  disasterChartSequence: 0,
  stationHistoryChart: null,
  f4Overview: null,
  f4RegionOverviews: {},
  f4BoardCollapsed: false,
  f4CountryTab: "overview",
  f4InnovationRows: [],
  f4InnovationQuery: "",
  f4PolicyRows: [],
  f4PolicyQuery: "",
  f4PolicyMeta: null,
  f4ListContextKey: "",
  f4TargetProvinceCodes: new Set(),
  f4Province: null,
};

const THAILAND_BOUNDS = [[97.2, 5.5], [105.7, 20.5]];
const NO_DATA_COLOR = "#e7ebe6";

// Executive map lenses: each colors provinces by one source-backed metric.
const MAP_MODES = {
  projects: {
    label: "โครงการ บพท.",
    legendTitle: "กลุ่มโครงการพัฒนาพื้นที่ที่เชื่อมได้",
    legendNote: "จัดกลุ่มชั่วคราวจากชื่อโครงการ + ปีงบ + หน่วยวิจัย · ไม่ใช่จำนวนผู้เข้าร่วม",
    zeroLabel: "ไม่มีในทะเบียน",
    value: (province) => Number(province.area_based_project_groups || 0) || null,
    format: (value) => `${formatNumber(value)} กลุ่มโครงการ`,
    summarize: (summary) => `${formatNumber(summary.total)} การเชื่อมโครงการ–จังหวัด`,
    steps: [
      { min: 40, color: "#14532e", label: "40+" },
      { min: 15, color: "#2e7d51", label: "15–39" },
      { min: 5, color: "#63ac79", label: "5–14" },
      { min: 1, color: "#a9d3b8", label: "1–4" },
    ],
    regionLegendTitle: "การเชื่อมกลุ่มโครงการ–จังหวัดรวมรายภาค",
    regionLegendNote: "โครงการข้ามจังหวัดอาจปรากฏมากกว่า 1 ครั้ง",
    regionValue: (summary) => (summary.withData ? summary.total : null),
    regionSteps: [
      { min: 40, color: "#14532e", label: "40+" },
      { min: 20, color: "#2e7d51", label: "20–39" },
      { min: 8, color: "#63ac79", label: "8–19" },
      { min: 1, color: "#a9d3b8", label: "1–7" },
    ],
  },
  sra: {
    label: "ความเปราะบาง",
    legendTitle: "คะแนนทุนดำรงชีพรวม (SRA-DSS)",
    legendNote: "จังหวัดเป้าหมายแก้จน · สีเข้ม = คะแนนทุนต่ำกว่า ตามนิยามต้นทาง",
    zeroLabel: "ไม่มีคะแนนปัจจุบัน",
    noDataLabel: (province) =>
      province.sra_scope_status === "in_scope_no_current_value"
        ? "อยู่ใน 20 จังหวัดเป้าหมาย แต่ยังไม่มีคะแนนปัจจุบัน"
        : "อยู่นอกขอบเขต 20 จังหวัดเป้าหมาย SRA-DSS",
    value: (province) =>
      province.sra_overall_score === null || province.sra_overall_score === undefined
        ? null
        : Number(province.sra_overall_score),
    format: (value) => `คะแนนรวม ${value.toFixed(2)}`,
    summarize: (summary) =>
      summary.scopeCount
        ? `${formatNumber(summary.scopeCount)} จังหวัดเป้าหมาย · มีคะแนน ${formatNumber(summary.withData)} จังหวัด${summary.min !== null ? ` · คะแนนต่ำสุด ${summary.minName} (${summary.min.toFixed(2)})` : ""}`
        : "ไม่มีจังหวัดเป้าหมาย SRA-DSS ในภาคนี้",
    steps: [
      { max: 1.8, color: "#b4551d", label: "≤ 1.80" },
      { max: 1.95, color: "#dd8a4a", label: "1.81–1.95" },
      { max: Infinity, color: "#f2c49a", label: "> 1.95" },
    ],
    // A region-level mean hid the story: อีสาน holds 10 of the 15 target
    // provinces (incl. the most vulnerable one) yet averaged lighter than a
    // region whose single target province scored low. Region darkness now
    // means "how many poverty-target provinces are here".
    regionLegendTitle: "จังหวัดเป้าหมายแก้จนรายภาค (SRA-DSS)",
    regionLegendNote: "สีเข้ม = มีจังหวัดเป้าหมายหลายจังหวัด",
    regionValue: (summary) => (summary.scopeCount ? summary.scopeCount : null),
    regionSteps: [
      { min: 8, color: "#b4551d", label: "8 จว. ขึ้นไป" },
      { min: 3, color: "#dd8a4a", label: "3–7 จว." },
      { min: 1, color: "#f2c49a", label: "1–2 จว." },
    ],
  },
  innovation: {
    label: "นวัตกรรม",
    legendTitle: "นวัตกรรมพร้อมใช้ที่เชื่อมได้",
    legendNote: "ทะเบียน AppTech · สีเข้ม = นวัตกรรมมาก",
    zeroLabel: "ไม่มีในทะเบียน",
    value: (province) => Number(province.innovation_records || 0) || null,
    format: (value) => `${formatNumber(value)} นวัตกรรม`,
    summarize: (summary) => `${formatNumber(summary.total)} นวัตกรรม`,
    steps: [
      { min: 40, color: "#1d5482", label: "40+" },
      { min: 15, color: "#3a78a8", label: "15–39" },
      { min: 5, color: "#6ba3cd", label: "5–14" },
      { min: 1, color: "#b0cde4", label: "1–4" },
    ],
    regionLegendTitle: "นวัตกรรมพร้อมใช้รวมรายภาค",
    regionLegendNote: "สีเข้ม = นวัตกรรมรวมมาก",
    regionValue: (summary) => (summary.withData ? summary.total : null),
    // Real regional totals run 17–237, so the scale tops out at 200+.
    regionSteps: [
      { min: 200, color: "#1d5482", label: "200+" },
      { min: 100, color: "#28679a", label: "100–199" },
      { min: 40, color: "#3a78a8", label: "40–99" },
      { min: 1, color: "#b0cde4", label: "1–39" },
    ],
  },
  f4: {
    label: "เสริมพลังท้องถิ่น",
    legendTitle: "พื้นที่เป้าหมาย 67 จังหวัด",
    legendNote: "สีแสดงจังหวัดที่อยู่ในพื้นที่เป้าหมาย",
    zeroLabel: "ไม่อยู่ในพื้นที่เป้าหมาย / ไม่มีหลักฐานในชุดนี้",
    value: (province) => province.f4_target_province ? 1 : null,
    format: () => "อยู่ในพื้นที่เป้าหมาย",
    summarize: (summary) => `${formatNumber(summary.withData)} จังหวัดในพื้นที่เป้าหมาย`,
    steps: [
      { min: 1, color: "#8060b8", label: "อยู่ในพื้นที่เป้าหมาย" },
    ],
    regionLegendTitle: "พื้นที่เป้าหมาย 67 จังหวัด",
    regionLegendNote: "สีม่วง = อยู่ในพื้นที่เป้าหมาย · เทา = ไม่อยู่ในตารางเป้าหมาย",
    regionValue: (summary) => (summary.withData ? summary.withData : null),
    regionSteps: [
      { min: 1, color: "#8060b8", label: "อยู่ในพื้นที่เป้าหมาย" },
    ],
  },
  disaster: {
    label: "ติดตามภัย",
    legendTitle: "ข้อมูลติดตามภัย (SPU)",
    legendNote: "สีเข้ม = มีหลายแหล่งติดตามสถานการณ์น้ำ · ข้อมูลเบื้องต้น",
    zeroLabel: "ไม่มีข้อมูล",
    value: (province) => Number(province.disaster_source_count || 0) || null,
    format: (value) => `${formatNumber(value)} แหล่งติดตามภัย`,
    summarize: (summary) => `${formatNumber(summary.total)} แหล่งติดตามภัย`,
    steps: [
      { min: 4, color: "#8b1a1a", label: "4 แหล่ง" },
      { min: 3, color: "#b33636", label: "3 แหล่ง" },
      { min: 2, color: "#d96c6c", label: "2 แหล่ง" },
      { min: 1, color: "#f0b3b3", label: "1 แหล่ง" },
    ],
    regionLegendTitle: "ข้อมูลติดตามภัยรวมรายภาค",
    regionLegendNote: "สีเข้ม = มีข้อมูลติดตามภัย",
    regionValue: (summary) => (summary.withData ? summary.total : null),
    regionSteps: [
      { min: 4, color: "#8b1a1a", label: "4+" },
      { min: 2, color: "#b33636", label: "2–3" },
      { min: 1, color: "#f0b3b3", label: "1" },
    ],
  },
  coverage: {
    label: "ความครอบคลุมข้อมูล",
    legendTitle: "ความครอบคลุมข้อมูล",
    legendNote: "จำนวนแหล่งที่ผูกกับจังหวัดได้ · สีเข้ม = หลายแหล่ง",
    zeroLabel: "0 แหล่ง",
    value: (province) => Number(province.evidence_source_count || 0) || null,
    format: (value) => `เชื่อมได้ ${formatNumber(value)} แหล่ง`,
    summarize: (summary) => `เฉลี่ย ${(summary.total / summary.withData).toFixed(1)} แหล่งต่อจังหวัด`,
    steps: [
      { min: 6, color: "#176747", label: "6+" },
      { min: 4, color: "#54a578", label: "4–5" },
      { min: 2, color: "#a9d3b8", label: "2–3" },
      { min: 1, color: "#cfe4d4", label: "1" },
    ],
    regionLegendTitle: "ความครอบคลุมข้อมูลเฉลี่ยรายภาค",
    regionLegendNote: "สีเข้ม = เฉลี่ยหลายแหล่งต่อจังหวัด",
    regionValue: (summary) => (summary.withData ? summary.total / summary.withData : null),
    regionSteps: [
      { min: 5.5, color: "#176747", label: "5.5+" },
      { min: 4.5, color: "#54a578", label: "4.5–5.4" },
      { min: 3, color: "#a9d3b8", label: "3.0–4.4" },
      { min: 0.01, color: "#cfe4d4", label: "< 3.0" },
    ],
  },
};

function colorFromSteps(steps, value) {
  if (value === null || value === undefined) return NO_DATA_COLOR;
  if (steps[0].max !== undefined) {
    for (const step of steps) {
      if (value <= step.max) return step.color;
    }
    return NO_DATA_COLOR;
  }
  for (const step of steps) {
    if (value >= step.min) return step.color;
  }
  return NO_DATA_COLOR;
}

function modeColor(mode, value) {
  return colorFromSteps(MAP_MODES[mode].steps, value);
}

function regionColor(mode, regionName) {
  const config = MAP_MODES[mode];
  return colorFromSteps(config.regionSteps, config.regionValue(regionSummary(mode, regionName)));
}

function buildFillExpression(mode) {
  // Country level paints whole regions by their aggregate; inside a region
  // provinces get their own colors. Selection is drawn as an ink outline so
  // the mode color stays truthful.
  const expression = ["match", ["get", "province_code"]];
  if (!state.selectedRegion) {
    const colorByRegion = {};
    Object.keys(state.regions).forEach((name) => {
      colorByRegion[name] = regionColor(mode, name);
    });
    state.catalog.provinces.forEach((province) => {
      const color = mode === "f4"
        ? modeColor(mode, MAP_MODES[mode].value(province))
        : colorByRegion[province.region] || NO_DATA_COLOR;
      expression.push(province.province_code, color);
    });
  } else {
    state.catalog.provinces.forEach((province) => {
      expression.push(province.province_code, modeColor(mode, MAP_MODES[mode].value(province)));
    });
  }
  expression.push(NO_DATA_COLOR);
  return expression;
}

function applyFillForLevel() {
  if (!state.mapLoaded) return;
  state.map.setPaintProperty("province-base", "fill-color", buildFillExpression(state.mapMode));
}

function updateRegionMarkerColors() {
  state.regionMarkers.forEach(({ element, name }) => {
    const dot = element.querySelector("i");
    if (dot) dot.style.background = regionColor(state.mapMode, name);
    const count = element.querySelector("span");
    if (count && state.mapMode === "f4") {
      count.textContent = formatNumber(regionSummary("f4", name).withData);
    } else if (count) {
      count.textContent = formatNumber(state.regions[name]?.codes.length || 0);
    }
  });
}

function regionSummary(mode, regionName) {
  const config = MAP_MODES[mode];
  let total = 0;
  let withData = 0;
  let min = null;
  let minName = "";
  let scopeCount = 0;
  (state.regions[regionName]?.codes || []).forEach((code) => {
    const province = provinceByCode(code) || {};
    if (mode === "sra" && String(province.sra_scope_status || "").startsWith("in_scope")) {
      scopeCount += 1;
    }
    const value = config.value(province);
    if (value !== null && value !== undefined) {
      total += value;
      withData += 1;
      if (min === null || value < min) {
        min = value;
        minName = province.province_name_th || "";
      }
    }
  });
  return { total, withData, min, minName, scopeCount };
}

function renderLegend() {
  const config = MAP_MODES[state.mapMode];
  const atCountry = !state.selectedRegion;
  const steps = atCountry ? config.regionSteps : config.steps;
  document.getElementById("legendTitle").textContent = atCountry
    ? config.regionLegendTitle
    : config.legendTitle;
  document.getElementById("legendNote").textContent = atCountry
    ? config.regionLegendNote
    : config.legendNote;
  const ordered = steps[0].max !== undefined ? steps : [...steps].reverse();
  document.getElementById("legendItems").innerHTML =
    ordered
      .map((step) => `<li><i style="background:${step.color}"></i><span>${escapeHtml(step.label)}</span></li>`)
      .join("") +
    `<li><i style="background:${NO_DATA_COLOR}"></i><span>${escapeHtml(atCountry ? "ไม่มีข้อมูล" : config.zeroLabel)}</span></li>`;
}

function setMapMode(mode) {
  if (!MAP_MODES[mode]) return;
  state.mapMode = mode;
  document.querySelectorAll("[data-map-mode]").forEach((button) => {
    button.classList.toggle("active", button.dataset.mapMode === mode);
  });
  const url = new URL(window.location.href);
  if (mode === "projects") url.searchParams.delete("mode");
  else url.searchParams.set("mode", mode);
  window.history.replaceState({}, "", url);
  renderLegend();
  updateRegionMarkerColors();
  applyFillForLevel();
  if (mode === "f4") {
    state.f4BoardCollapsed = true;
    document.getElementById("showF4Country").hidden = Boolean(state.selectedCode);
    document.getElementById("f4CountryPanel").hidden = true;
    loadF4Overview();
    if (state.selectedCode) loadF4ProvinceOverview(state.selectedCode);
    else if (state.selectedRegion) fitRegionBounds(state.regions[state.selectedRegion], 500);
    else if (state.mapLoaded) lockCountryView(true);
  } else {
    state.f4BoardCollapsed = false;
    document.getElementById("showF4Country").hidden = true;
    document.getElementById("f4CountryPanel").hidden = true;
  }
  if (mode === "disaster") {
    loadDisasterProvinces().then(() => {
      renderLegend();
      updateRegionMarkerColors();
      applyFillForLevel();
      if (state.selectedCode) renderDisaster();
    });
  } else {
    document.getElementById("disasterSection").hidden = true;
  }
}

async function fetchPublicJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${url} ${response.status}`);
  return response.json();
}

async function loadF4Overview() {
  if (state.f4Overview) {
    applyF4TargetProvinceMembership();
    renderF4CountryPanel();
    return state.f4Overview;
  }
  try {
    state.f4Overview = await fetchPublicJson("/api/public/v1/f4/overview");
    applyF4TargetProvinceMembership();
    renderF4CountryPanel();
    return state.f4Overview;
  } catch (error) {
    console.error("Failed to load F4 overview:", error);
    showToast("โหลดข้อมูลเสริมพลังท้องถิ่นไม่สำเร็จ");
    return null;
  }
}

function applyF4TargetProvinceMembership() {
  const codes = new Set((state.f4Overview?.target_province_codes || []).map((code) => String(code).padStart(2, "0")));
  state.f4TargetProvinceCodes = codes;
  (state.catalog?.provinces || []).forEach((province) => {
    province.f4_target_province = codes.has(String(province.province_code).padStart(2, "0"));
  });
  if (state.mapMode === "f4") {
    renderLegend();
    updateRegionMarkerColors();
    applyFillForLevel();
  }
}

function f4RegionEndpoint(path = "") {
  return `/api/public/v1/f4/regions/${encodeURIComponent(state.selectedRegion)}${path}`;
}

function f4ProvinceEndpoint(path = "") {
  return `/api/public/v1/f4/provinces/${encodeURIComponent(state.selectedCode)}${path}`;
}

function currentF4Overview() {
  if (state.selectedCode) return state.f4Province;
  return state.selectedRegion ? state.f4RegionOverviews[state.selectedRegion] : state.f4Overview;
}

async function loadF4RegionOverview(regionName) {
  if (!regionName) return null;
  if (state.f4RegionOverviews[regionName]) return state.f4RegionOverviews[regionName];
  try {
    const payload = await fetchPublicJson(`/api/public/v1/f4/regions/${encodeURIComponent(regionName)}`);
    state.f4RegionOverviews[regionName] = payload;
    return payload;
  } catch (error) {
    console.error("Failed to load F4 region overview:", error);
    showToast("โหลดข้อมูลเสริมพลังท้องถิ่นระดับภาคไม่สำเร็จ");
    return null;
  }
}

async function loadF4ProvinceOverview(code) {
  if (!code) return null;
  const normalized = String(code).padStart(2, "0");
  if (state.f4Province?.province_code === normalized) {
    renderF4CountryPanel();
    return state.f4Province;
  }
  try {
    const payload = await fetchPublicJson(`/api/public/v1/f4/provinces/${normalized}`);
    if (state.selectedCode !== normalized || state.mapMode !== "f4") return null;
    state.f4Province = payload;
    renderF4CountryPanel();
    return payload;
  } catch (error) {
    console.error("Failed to load F4 province overview:", error);
    showToast("โหลดข้อมูลเสริมพลังท้องถิ่นระดับจังหวัดไม่สำเร็จ");
    return null;
  }
}

function renderF4Card(card, scope = "country") {
  const clickable = ["innovations", "policy_projects"].includes(card.key);
  const action = clickable ? ` data-f4-${scope}-kind="${card.key}"` : "";
  const value = card.value === null || card.value === undefined ? "—" : formatNumber(card.value);
  return `
    <button type="button" class="province-kpi f4-kpi"${action}${clickable ? "" : " disabled"}>
      <span>${escapeHtml(card.label)}</span>
      <strong>${value}</strong>
      <small>${escapeHtml(card.unit || "")}${card.match_type ? ` · ${escapeHtml(card.match_type)}` : ""}</small>
    </button>`;
}

function renderF4CountryPanel() {
  if (state.mapMode !== "f4" || !state.f4Overview || state.f4BoardCollapsed) return;
  const panel = document.getElementById("f4CountryPanel");
  panel.hidden = false;
  document.getElementById("showF4Country").hidden = true;
  const overview = currentF4Overview();
  if (state.selectedCode && !overview) {
    const province = provinceByCode(state.selectedCode);
    document.getElementById("f4PanelScopeLabel").textContent = "ข้อมูลจังหวัด";
    document.getElementById("f4PanelSubtitle").textContent = `${province?.province_name_th || "จังหวัด"} · PROVINCE KPI`;
    document.getElementById("f4OverviewHeading").textContent = "Overview KPI ระดับจังหวัด";
    document.getElementById("f4CountryCards").innerHTML = `<div class="portfolio-loading"><span></span><span></span><span></span></div>`;
    loadF4ProvinceOverview(state.selectedCode);
    return;
  }
  if (state.selectedRegion && !overview) {
    document.getElementById("f4PanelScopeLabel").textContent = "ข้อมูลภาค";
    document.getElementById("f4PanelSubtitle").textContent = `${state.selectedRegion} · Regional KPI`;
    document.getElementById("f4OverviewHeading").textContent = "Overview KPI ระดับภาค";
    document.getElementById("f4CountryCards").innerHTML = `<div class="portfolio-loading"><span></span><span></span><span></span></div>`;
    loadF4RegionOverview(state.selectedRegion).then(() => {
      if (state.mapMode === "f4" && state.selectedRegion && !state.selectedCode) renderF4CountryPanel();
    });
    return;
  }
  if (!overview) return;
  document.getElementById("f4PanelTitle").textContent = "เสริมพลังท้องถิ่น";
  document.getElementById("f4PanelScopeLabel").textContent = state.selectedCode
    ? "ข้อมูลจังหวัด"
    : state.selectedRegion ? "ข้อมูลภาค" : "ข้อมูลประเทศ";
  document.getElementById("f4PanelSubtitle").textContent = state.selectedCode
    ? `${overview.province_name_th || provinceByCode(state.selectedCode)?.province_name_th || "จังหวัด"} · PROVINCE KPI`
    : state.selectedRegion
      ? `${state.selectedRegion} · Regional KPI`
    : "Thailand · Overview KPI";
  document.getElementById("f4OverviewHeading").textContent = state.selectedCode
    ? "Overview KPI ระดับจังหวัด"
    : state.selectedRegion
      ? "Overview KPI ระดับภาค"
    : "Overview KPI ระดับประเทศ";
  const cards = state.selectedCode
    ? (overview.cards || []).filter((card) => ["innovations", "policy_projects"].includes(card.key))
    : (overview.cards || []);
  document.getElementById("f4CountryCards").innerHTML = cards
    .map((card) => renderF4Card(card, "country"))
    .join("");
  document.querySelectorAll("[data-f4-country-kind]").forEach((card) => {
    card.addEventListener("click", () => {
      const tab = card.dataset.f4CountryKind === "policy_projects" ? "policy" : "innovations";
      setF4CountryTab(tab);
    });
  });
  renderF4Evidence();
  setF4CountryTab(state.f4CountryTab || "overview", false);
  if (["innovations", "policy"].includes(state.f4CountryTab)) {
    const contextKey = `${state.selectedCode ? `province:${state.selectedCode}` : state.selectedRegion || "country"}:${state.f4CountryTab}`;
    if (state.f4ListContextKey !== contextKey) {
      state.f4ListContextKey = contextKey;
      openF4CountryList(state.f4CountryTab === "policy" ? "policy_projects" : "innovations");
    }
  }
}

function f4RowSearchText(row) {
  return Object.values(row)
    .flatMap((value) => Array.isArray(value) ? value : [value])
    .join(" ")
    .toLowerCase();
}

function f4ValueOrFallback(value) {
  return value !== null && value !== undefined && String(value).trim() !== "" ? String(value).trim() : "ไม่ระบุ";
}

function f4ReadinessLabel(row) {
  const level = f4ValueOrFallback(row.trl_level);
  const status = f4ValueOrFallback(row.trl_status);
  if (level === "ไม่ระบุ" && status === "ไม่ระบุ") return "ไม่ระบุ";
  if (level !== "ไม่ระบุ" && status !== "ไม่ระบุ") return `ระดับ ${level} · ${status}`;
  return level !== "ไม่ระบุ" ? `ระดับ ${level}` : status;
}

function f4AreaLabel(prefix, values, knownPrefixes = []) {
  const items = (values || []).map((value) => String(value || "").trim()).filter(Boolean);
  if (!items.length) return `${prefix} ไม่ระบุ`;
  const hasThaiNamePrefix = items.every((value) => knownPrefixes.some((known) => value.startsWith(known)));
  return hasThaiNamePrefix ? items.join(", ") : `${prefix} ${items.join(", ")}`;
}

function renderF4InnovationRow(row) {
  const areaLine = [
    f4AreaLabel("อำเภอ", row.district_names || row.districts, ["อำเภอ", "เขต"]),
    f4AreaLabel("ตำบล", row.subdistrict_names || row.subdistricts, ["ตำบล", "แขวง"]),
  ].join(" · ");
  return `
    <article class="f4-record-card">
      <header><strong>${escapeHtml(row.title || "ไม่ระบุชื่อ")}</strong><span>#${escapeHtml(row.product_id || "—")}</span></header>
      <p>${escapeHtml((row.province_names || row.provinces || []).join(", ") || "ไม่ระบุจังหวัด")}</p>
      <small>${escapeHtml(areaLine)}</small>
      <dl class="f4-record-metrics">
        <div><dt>ระดับความพร้อม (TRL)</dt><dd>${escapeHtml(f4ReadinessLabel(row))}</dd></div>
      </dl>
      ${row.source_url ? `<a href="${escapeHtml(row.source_url)}" target="_blank" rel="noreferrer">เปิดต้นทาง</a>` : ""}
    </article>`;
}

function renderF4PolicyRow(row) {
  const budget = row.budget_baht !== null && row.budget_baht !== undefined && row.budget_baht !== ""
    ? `${formatNumber(Math.round(Number(row.budget_baht)))} บาท`
    : "ไม่ระบุงบประมาณ";
  return `
    <article class="f4-record-card">
      <header><strong>${escapeHtml(row.project_title || "ไม่ระบุชื่อโครงการ")}</strong><span>${escapeHtml(row.fiscal_year || "—")}</span></header>
      <p>${escapeHtml(row.lead_organization || "ไม่ระบุหน่วยงาน")}</p>
      <small>${escapeHtml(row.status || "ไม่ระบุสถานะ")} · ${escapeHtml(row.contract_no || "ไม่มีเลขสัญญา")} · ${escapeHtml(budget)}</small>
      ${row.detail_url ? `<a href="${escapeHtml(row.detail_url)}" target="_blank" rel="noreferrer">เปิดรายละเอียด</a>` : ""}
    </article>`;
}

function renderF4Rows(containerId, rows, kind, query) {
  const normalized = String(query || "").trim().toLowerCase();
  const filtered = normalized ? rows.filter((row) => f4RowSearchText(row).includes(normalized)) : rows;
  document.getElementById(containerId).innerHTML = filtered.length
    ? filtered.map((row) => kind === "policy_projects" ? renderF4PolicyRow(row) : renderF4InnovationRow(row)).join("")
    : `<div class="portfolio-empty">ไม่พบรายการที่ตรงกับคำค้น</div>`;
  return filtered.length;
}

function renderF4Evidence() {
  const overview = currentF4Overview() || state.f4Overview;
  if (!overview) return;
  const scopeNote = state.selectedCode
    ? `Current view: ${overview.province_name_th || provinceByCode(state.selectedCode)?.province_name_th || "province"} province evidence filter.`
    : state.selectedRegion
      ? `Current view: ${state.selectedRegion} regional evidence filter.`
      : "Current view: Thailand country evidence.";
  const membershipNote = state.selectedCode
    ? [overview.is_target_province ? "จังหวัดนี้อยู่ในพื้นที่เป้าหมาย 67 จังหวัด" : "จังหวัดนี้ไม่อยู่ในชุดพื้นที่เป้าหมาย 67 จังหวัด"]
    : [];
  document.getElementById("f4CountryNotes").innerHTML = [
    scopeNote,
    ...membershipNote,
    ...(overview.evidence_notes || overview.notes || []),
  ]
    .map((note) => `<p>${escapeHtml(note)}</p>`)
    .join("");
  const sourceKeys = {
    ...(state.selectedCode ? { target_membership: overview.target_membership_source } : {}),
    ...(overview.source_keys || {}),
  };
  document.getElementById("f4SourceGrid").innerHTML = Object.entries(sourceKeys)
    .filter(([, key]) => key)
    .map(([label, key]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(key)}</strong></article>`)
    .join("");
}

function setF4CountryTab(tab, load = true) {
  state.f4CountryTab = tab;
  document.querySelectorAll("[data-f4-tab]").forEach((button) => {
    const active = button.dataset.f4Tab === tab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll("[data-f4-panel]").forEach((panel) => {
    const active = panel.dataset.f4Panel === tab;
    panel.hidden = !active;
    panel.classList.toggle("active", active);
  });
  if (!load) return;
  if (tab === "innovations") openF4CountryList("innovations");
  if (tab === "policy") openF4CountryList("policy_projects");
}

function renderF4PolicySummary(payload, ids = {}) {
  const targetIds = {
    total: "f4PolicyTotal",
    budget: "f4PolicyBudget",
    budgetNote: "f4PolicyBudgetNote",
    donut: "f4PolicyDonut",
    legend: "f4PolicyStatusLegend",
    ...ids,
  };
  const total = Number(payload.total || 0);
  const budget = Number(payload.budget_baht_total || 0);
  const statuses = payload.status_summary || [];
  const colors = ["#173f2c", "#8a6a18", "#5f7869", "#9b4f40", "#9aa59d"];
  let cursor = 0;
  const slices = statuses.map((item, index) => {
    const start = cursor;
    const degrees = total ? (Number(item.count || 0) / total) * 360 : 0;
    cursor += degrees;
    return `${colors[index % colors.length]} ${start.toFixed(2)}deg ${cursor.toFixed(2)}deg`;
  });
  document.getElementById(targetIds.total).textContent = formatNumber(total);
  document.getElementById(targetIds.budget).textContent = `${formatNumber(Math.round(budget))} บาท`;
  const budgetNote = document.getElementById(targetIds.budgetNote);
  if (budgetNote) budgetNote.textContent = "";
  document.getElementById(targetIds.donut).style.background = slices.length
    ? `conic-gradient(${slices.join(", ")})`
    : "#dce4de";
  document.getElementById(targetIds.legend).innerHTML = statuses
    .map((item, index) => `
      <p><i style="background:${colors[index % colors.length]}"></i><span>${escapeHtml(item.label)}</span><strong>${formatNumber(item.count)} โครงการ</strong></p>`)
    .join("");
}

async function openF4CountryList(kind) {
  const isPolicy = kind === "policy_projects";
  const endpoint = state.selectedCode
    ? f4ProvinceEndpoint(isPolicy ? "/policy-projects" : "/innovations")
    : state.selectedRegion
      ? f4RegionEndpoint(isPolicy ? "/policy-projects" : "/innovations")
      : (isPolicy ? "/api/public/v1/f4/policy-projects" : "/api/public/v1/f4/innovations");
  const rowsId = isPolicy ? "f4PolicyRows" : "f4InnovationRows";
  const summaryId = isPolicy ? "f4PolicyListSummary" : "f4InnovationListSummary";
  const query = isPolicy ? state.f4PolicyQuery : state.f4InnovationQuery;
  document.getElementById(rowsId).innerHTML = `<div class="portfolio-loading"><span></span><span></span><span></span></div>`;
  try {
    const payload = await fetchPublicJson(endpoint);
    if (isPolicy) {
      state.f4PolicyRows = payload.rows || [];
      state.f4PolicyMeta = payload;
      renderF4PolicySummary(payload);
      const count = renderF4Rows(rowsId, state.f4PolicyRows, kind, query);
      document.getElementById(summaryId).textContent = `${formatNumber(count)} รายการ`;
    } else {
      state.f4InnovationRows = payload.rows || [];
      const count = renderF4Rows(rowsId, state.f4InnovationRows, kind, query);
      document.getElementById(summaryId).textContent = `${formatNumber(count)} รายการ`;
      const innovationSummary = document.getElementById("f4InnovationSummary");
      if (innovationSummary) innovationSummary.textContent = "";
    }
  } catch (error) {
    console.error(error);
    document.getElementById(rowsId).innerHTML = `<div class="portfolio-empty">โหลดรายการไม่สำเร็จ</div>`;
  }
}

function rerenderF4InnovationList() {
  const count = renderF4Rows("f4InnovationRows", state.f4InnovationRows, "innovations", state.f4InnovationQuery);
  document.getElementById("f4InnovationListSummary").textContent = `${formatNumber(count)} รายการ`;
}

function rerenderF4PolicyList() {
  const count = renderF4Rows("f4PolicyRows", state.f4PolicyRows, "policy_projects", state.f4PolicyQuery);
  document.getElementById("f4PolicyListSummary").textContent = `${formatNumber(count)} รายการ`;
}

function setPrompt(title, hint) {
  document.getElementById("promptTitle").textContent = title;
  document.getElementById("promptHint").textContent = hint;
}

async function loadDisasterProvinces() {
  try {
    const response = await fetch("/api/public/v1/disaster/provinces", { cache: "no-store" });
    if (response.ok) {
      state.disasterProvinces = await response.json();
      const provinces = state.disasterProvinces?.provinces || {};
      (state.catalog?.provinces || []).forEach((province) => {
        const info = provinces[province.province_code];
        province.disaster_source_count = info ? info.sources.length : 0;
        province.disaster_record_count = info ? Number(info.total_records || 0) : 0;
        province.disaster_sources = info ? info.sources : [];
      });
    }
  } catch (e) {
    console.error("Failed to load disaster provinces:", e);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function plainLanguage(value) {
  return String(value ?? "")
    .replace(/public projection/gi, "ข้อมูลที่เผยแพร่")
    .replace(/candidate database/gi, "ฐานข้อมูลเบื้องต้น")
    .replace(/candidate/gi, "ข้อมูลเบื้องต้น")
    .replace(/needs[_ ]review/gi, "รอตรวจ")
    .replace(/accepted/gi, "ผ่านการตรวจ")
    .replace(/quality gate/gi, "การตรวจคุณภาพ")
    .replace(/data owner/gi, "เจ้าของข้อมูล")
    .replace(/snapshot/gi, "ข้อมูลที่บันทึกไว้")
    .replace(/metadata/gi, "รายละเอียดแหล่งข้อมูล")
    .replace(/grain/gi, "หน่วยนับ")
    .replace(/records?/gi, "รายการ")
    .replace(/as_of/gi, "วันที่ข้อมูล")
    .replace(/fetched_at/gi, "วันที่ดึง")
    .replace(/source id/gi, "รหัสแหล่งข้อมูล");
}

function formatNumber(value, maximumFractionDigits = 0) {
  if (value === null || value === undefined || value === "") return "ไม่มีค่า";
  return new Intl.NumberFormat("th-TH", { maximumFractionDigits }).format(Number(value));
}

function formatCompactNumber(value) {
  if (value === null || value === undefined || value === "") return "—";
  return new Intl.NumberFormat("th-TH", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(Number(value));
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

function isObservedStatus(status) {
  return ["available", "provisional_grouping", "limited"].includes(String(status || ""));
}

function metricValueHtml(value, status, unit = "") {
  if (!isObservedStatus(status)) {
    return `<strong class="metric-na">—</strong><small>ไม่พบในทะเบียนนี้</small>`;
  }
  return `<strong>${formatNumber(value)}</strong><small>${escapeHtml(unit)}</small>`;
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

function renderMapOverview() {
  const select = document.getElementById("provinceSelect");
  const options = [...state.catalog.provinces]
    .sort((a, b) => a.province_name_th.localeCompare(b.province_name_th, "th"))
    .map(
      (province) =>
        `<option value="${province.province_code}">${escapeHtml(province.province_name_th)} · ${escapeHtml(province.region)}</option>`,
    );
  select.insertAdjacentHTML("beforeend", options.join(""));
}

function updateLabelVisibility() {
  if (!state.mapLoaded) return;
  state.labelMarkers.forEach(({ element, code, region }) => {
    const emphasized = code === state.selectedCode || code === state.hoveredCode;
    const visible = (state.selectedRegion && region === state.selectedRegion) || emphasized;
    element.classList.toggle("is-secondary", !visible);
    element.style.display = visible ? "block" : "none";
    element.classList.toggle("is-active", code === state.selectedCode);
    element.classList.toggle("is-hovered", code === state.hoveredCode);
  });
  state.regionMarkers.forEach(({ element }) => {
    element.style.display = state.selectedRegion ? "none" : "flex";
  });
}

function computeRegions() {
  const regions = {};
  state.catalog.provinces.forEach((province) => {
    const region = province.region;
    if (!regions[region]) {
      regions[region] = { name: region, codes: [], centroids: [] };
    }
    regions[region].codes.push(province.province_code);
    if (province.centroid?.every((value) => Number.isFinite(Number(value)))) {
      regions[region].centroids.push(province.centroid);
    }
  });
  const boundsByCode = {};
  (state.boundaries.features || []).forEach((feature) => {
    const code = feature.properties?.province_code;
    if (!code) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    const walk = (coords) => {
      if (typeof coords[0] === "number") {
        minX = Math.min(minX, coords[0]);
        maxX = Math.max(maxX, coords[0]);
        minY = Math.min(minY, coords[1]);
        maxY = Math.max(maxY, coords[1]);
        return;
      }
      coords.forEach(walk);
    };
    walk(feature.geometry.coordinates);
    boundsByCode[code] = [minX, minY, maxX, maxY];
  });
  Object.values(regions).forEach((region) => {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    region.codes.forEach((code) => {
      const box = boundsByCode[code];
      if (!box) return;
      minX = Math.min(minX, box[0]);
      minY = Math.min(minY, box[1]);
      maxX = Math.max(maxX, box[2]);
      maxY = Math.max(maxY, box[3]);
    });
    region.bounds = [[minX, minY], [maxX, maxY]];
    const centroids = region.centroids;
    region.center = centroids.length
      ? [
          centroids.reduce((sum, point) => sum + Number(point[0]), 0) / centroids.length,
          centroids.reduce((sum, point) => sum + Number(point[1]), 0) / centroids.length,
        ]
      : null;
  });
  state.regions = regions;
}

function addRegionMarkers() {
  Object.values(state.regions).forEach((region) => {
    if (!region.center) return;
    const element = document.createElement("button");
    element.type = "button";
    element.className = "region-label";
    element.innerHTML = `<i aria-hidden="true"></i><strong>${escapeHtml(region.name.replace(/^ภาค/, ""))}</strong><span>${formatNumber(region.codes.length)}</span>`;
    element.setAttribute("aria-label", `ซูมเข้าไปดู${region.name}`);
    element.addEventListener("mouseenter", () => setHoveredRegion(region.name));
    element.addEventListener("mouseleave", () => setHoveredRegion(null));
    element.addEventListener("click", (event) => {
      event.stopPropagation();
      selectRegion(region.name);
    });
    const marker = new window.maplibregl.Marker({ element, anchor: "center" })
      .setLngLat(region.center)
      .addTo(state.map);
    state.regionMarkers.push({ marker, element, name: region.name });
  });
}

function applyRegionFocus() {
  if (!state.mapLoaded) return;
  if (state.selectedRegion) {
    const codes = state.regions[state.selectedRegion]?.codes || [];
    state.map.setPaintProperty("province-base", "fill-opacity", [
      "*",
      ["case", ["boolean", ["feature-state", "hover"], false], 1, 0.94],
      ["match", ["get", "province_code"], codes, 1, 0.28],
    ]);
    return;
  }
  // Country view: provinces are not individually interactive — the whole
  // hovered region brightens while the rest recede.
  if (state.hoveredRegion) {
    const codes = state.regions[state.hoveredRegion]?.codes || [];
    state.map.setPaintProperty("province-base", "fill-opacity", [
      "match", ["get", "province_code"], codes, 1, 0.45,
    ]);
    return;
  }
  state.map.setPaintProperty("province-base", "fill-opacity", 0.94);
}

function setHoveredRegion(name) {
  if (state.hoveredRegion === name) return;
  state.hoveredRegion = name;
  state.regionMarkers.forEach(({ element, name: markerName }) => {
    element.classList.toggle("is-hovered", markerName === name);
  });
  applyRegionFocus();
}

function regionPadding() {
  // Mobile keeps a tall clear zone at the bottom: the legend/actions column
  // and the mode dock live there, and province labels must stay tappable.
  const isMobile = window.matchMedia("(max-width: 720px)").matches;
  const base = isMobile
    ? { top: 92, right: 24, bottom: 200, left: 24 }
    : { top: 110, right: 90, bottom: 110, left: 90 };
  return mapPanelPadding(base);
}

function f4BoardIsOpen() {
  return state.mapMode === "f4" && !state.f4BoardCollapsed && !document.getElementById("f4CountryPanel")?.hidden;
}

function mapPanelPadding(base) {
  if (!f4BoardIsOpen() || window.matchMedia("(max-width: 720px)").matches) return base;
  return { ...base, right: Math.max(base.right, 760), left: Math.max(base.left, 48) };
}

function mapPanelOffset() {
  if (!f4BoardIsOpen() || window.matchMedia("(max-width: 720px)").matches) return [0, 0];
  return [-340, 0];
}

function cancelPendingLock() {
  if (state.pendingLock && state.map) {
    state.map.off("moveend", state.pendingLock);
    state.pendingLock = null;
  }
}

function fitRegionBounds(region, duration = 700) {
  if (!state.mapLoaded || !region?.bounds) return;
  cancelPendingLock();
  state.map.fitBounds(region.bounds, {
    padding: regionPadding(),
    pitch: 0,
    bearing: 0,
    duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : duration,
  });
}

function selectRegion(name, moveMap = true) {
  const region = state.regions[name];
  if (!region) return;
  state.selectedRegion = name;
  setHoveredRegion(null);
  state.hoverPopup?.remove();
  document.getElementById("backToCountry").hidden = false;
  setPrompt(`${name}: คลิกจังหวัดเพื่อเปิดข้อมูล`, "หรือกด ทุกภาค เพื่อกลับมุมมองประเทศ");
  applyFillForLevel();
  renderLegend();
  applyRegionFocus();
  updateLabelVisibility();
  if (state.mapMode === "f4") {
    state.f4ListContextKey = "";
    renderF4CountryPanel();
  }
  if (moveMap) fitRegionBounds(region);
}

function countryPadding() {
  // Mobile bottom padding clears the overlay stack (dock + legend column) so
  // the southern region chip never hides behind them.
  const base = window.matchMedia("(max-width: 720px)").matches
    ? { top: 76, right: 12, bottom: 190, left: 12 }
    : { top: 84, right: 48, bottom: 76, left: 48 };
  return mapPanelPadding(base);
}

function lockCountryView(animate = false) {
  // Fit the whole country to the actual viewport first, THEN derive the
  // zoom floor and pan bounds from that view. A hardcoded maxBounds fought
  // wide screens and clamped the zoom so the map never fully fit.
  const map = state.map;
  if (!map) return;
  cancelPendingLock();
  map.setMaxBounds(null);
  map.setMinZoom(2);
  const camera = map.cameraForBounds(THAILAND_BOUNDS, { padding: countryPadding() });
  if (!camera) return;
  state.countryZoom = camera.zoom;
  const lock = () => {
    state.pendingLock = null;
    // The user may have drilled into a region/province while the return
    // animation was still running — never lock that view as "country".
    if (state.selectedRegion || state.selectedCode) return;
    if (Math.abs(map.getZoom() - camera.zoom) > 0.2) {
      map.jumpTo({ ...camera, pitch: 0, bearing: 0 });
    }
    map.setMinZoom(Math.max(2, map.getZoom() - 0.05));
    const view = map.getBounds();
    map.setMaxBounds([
      [view.getWest() - 0.4, view.getSouth() - 0.4],
      [view.getEast() + 0.4, view.getNorth() + 0.4],
    ]);
  };
  if (animate && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    state.pendingLock = lock;
    map.once("moveend", lock);
    map.easeTo({ ...camera, pitch: 0, bearing: 0, duration: 700 });
  } else {
    map.jumpTo({ ...camera, pitch: 0, bearing: 0 });
    lock();
  }
}

function backToCountry() {
  state.selectedRegion = null;
  state.f4ListContextKey = "";
  setHoveredRegion(null);
  closePanel(false);
  document.getElementById("backToCountry").hidden = true;
  setPrompt("เลือกภาค แล้วเจาะลงรายจังหวัด", "ซูมเข้าไปเลือกจังหวัดเพื่อเปิดข้อมูลจริงจาก URL ต้นทาง");
  applyFillForLevel();
  renderLegend();
  updateRegionMarkerColors();
  applyRegionFocus();
  updateLabelVisibility();
  if (state.mapLoaded) lockCountryView(true);
}

function resetF4ToCountryOverview() {
  if (state.selectedCode) closePanel(false);
  state.f4BoardCollapsed = false;
  state.selectedRegion = null;
  state.selectedCode = null;
  state.f4CountryTab = "overview";
  state.f4ListContextKey = "";
  state.f4InnovationQuery = "";
  state.f4PolicyQuery = "";
  setHoveredRegion(null);
  document.getElementById("backToCountry").hidden = true;
  document.getElementById("f4CountryPanel").hidden = false;
  document.getElementById("showF4Country").hidden = true;
  document.getElementById("mapPrompt").classList.remove("is-hidden");
  document.querySelector(".picker-copy strong").textContent = "คลิกจังหวัด หรือค้นหาที่นี่";
  document.getElementById("provinceSelect").value = "";
  setPrompt("เลือกภาค แล้วเจาะลงรายจังหวัด", "ซูมเข้าไปเลือกจังหวัดเพื่อเปิดข้อมูลจริงจาก URL ต้นทาง");
  applyFillForLevel();
  renderLegend();
  updateRegionMarkerColors();
  applyRegionFocus();
  updateLabelVisibility();
  renderF4CountryPanel();
  const url = new URL(window.location.href);
  url.searchParams.set("mode", "f4");
  url.searchParams.delete("province");
  url.searchParams.delete("view");
  window.history.replaceState({}, "", url);
  if (state.mapLoaded) lockCountryView(true);
}

function collapseF4Board() {
  state.f4BoardCollapsed = true;
  document.getElementById("f4CountryPanel").hidden = true;
  document.getElementById("showF4Country").hidden = false;
  if (state.mapLoaded) {
    cancelPendingLock();
    if (state.selectedRegion) fitRegionBounds(state.regions[state.selectedRegion], 500);
    else if (state.selectedCode) fitProvince(provinceByCode(state.selectedCode));
    else lockCountryView(true);
  }
}

function showF4Board() {
  state.f4BoardCollapsed = false;
  document.getElementById("showF4Country").hidden = true;
  renderF4CountryPanel();
  if (state.mapLoaded) {
    cancelPendingLock();
    if (state.selectedRegion) fitRegionBounds(state.regions[state.selectedRegion], 500);
    else if (state.selectedCode) fitProvince(provinceByCode(state.selectedCode));
    else lockCountryView(true);
  }
}

function addProvinceLabels() {
  state.catalog.provinces.forEach((province) => {
    if (!province.centroid?.every((value) => Number.isFinite(Number(value)))) return;
    const element = document.createElement("button");
    element.type = "button";
    element.className = "province-map-label";
    element.textContent = province.province_name_th;
    element.setAttribute("aria-label", `เปิดข้อมูลจังหวัด${province.province_name_th}`);
    element.addEventListener("click", (event) => {
      event.stopPropagation();
      selectProvince(province.province_code, true);
    });
    const marker = new window.maplibregl.Marker({ element, anchor: "center" })
      .setLngLat(province.centroid)
      .addTo(state.map);
    state.labelMarkers.push({ marker, element, code: province.province_code, region: province.region });
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
  cancelPendingLock();
  state.map.easeTo({
    center: province.centroid,
    zoom: isMobile ? 6.4 : 7,
    pitch: 0,
    bearing: 0,
    // Shift only while the F4 KPI board is open; closing the board returns
    // the same camera helpers to a centered map.
    offset: mapPanelOffset(),
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
  state.f4Province = null;
  document.getElementById("f4CountryPanel").hidden = true;
  document.getElementById("showF4Country").hidden = true;
  document.getElementById("portfolioLoading").hidden = false;
  document.getElementById("portfolioEmpty").hidden = true;
  document.getElementById("projectsLoading").hidden = false;
  document.getElementById("projectsEmpty").hidden = true;
  document.getElementById("researchSection").hidden = true;
  [
    "areaSection",
    "innovationSection",
    "requirementsSection",
    "peopleOverviewSection",
    "sraAreaSection",
    "tourismSection",
    "cultureSection",
    "povertySection",
    "citySection",
    "housingSection",
    "disasterSection",
  ].forEach((id) => {
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

function applyProjectDistrict(district) {
  state.projectDistrict = district;
  state.projectYear = "";
  state.projectQuery = "";
  const search = document.getElementById("projectSearch");
  if (search) search.value = "";
  activatePanelTab("projects");
  if (state.currentBriefing) {
    populateProjectFilters(state.currentBriefing.sections.project_master);
    renderAreaProjects(state.currentBriefing.sections.project_master);
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
  document.getElementById("researchScope").textContent = "แยกกลุ่มโครงการออกจากรายการผู้เข้าร่วม";

  const stats = [
    ["กลุ่มโครงการ", portfolio.project_count, portfolio.project_count_status, "กลุ่ม"],
    ["ผู้เข้าร่วม", portfolio.participant_record_count, portfolio.participant_record_status, "รายการ"],
    ["หน่วยวิจัย", portfolio.university_count, portfolio.project_count_status, "แห่ง"],
    ["พื้นที่ครอบคลุม", portfolio.district_count, portfolio.project_count_status, "อำเภอ"],
    ["นวัตกรรม", portfolio.innovation_count, portfolio.innovation_count_status, "รายการ"],
  ];
  const statHtml = `<div class="research-stats">${stats
    .map(
      ([label, value, status, unit]) => `
        <article><span>${escapeHtml(label)}</span>${metricValueHtml(value, status, unit)}</article>`,
    )
    .join("")}</div>`;

  const yearsHtml = portfolio.fiscal_years?.length
    ? `<section class="research-block"><h4>โครงการรายปีงบประมาณ</h4>${researchBars(portfolio.fiscal_years, "โครงการ")}</section>`
    : "";
  const universitiesHtml = portfolio.universities?.length
    ? `<section class="research-block"><h4>มหาวิทยาลัย/หน่วยวิจัยที่รับทุน</h4>${researchBars(portfolio.universities, "")}</section>`
    : "";
  const districtsHtml = portfolio.districts?.length
    ? `<section class="research-block"><h4>กดอำเภอเพื่อดูโครงการและผู้เข้าร่วมในพื้นที่</h4><div class="district-chips">${portfolio.districts
        .map(
          (district) => `
            <button type="button" class="district-chip" data-district="${escapeHtml(district.label_th)}">
              <strong>อ.${escapeHtml(district.label_th)}</strong><span>${formatNumber(district.value)} กลุ่มโครงการครอบคลุม</span>
            </button>`,
        )
        .join("")}</div></section>`
    : "";

  const funding = portfolio.funding || {};
  const fundedCountKnown = Number(funding.pmua_funding_entry_count || 0) > 0;
  const amountKnown = Number(funding.pmua_amount_known_entries || 0) > 0;
  const innovationValueKnown = Number(funding.innovation_value_known_entries || 0) > 0;
  const fundingHtml = `
    <section class="research-block funding-block">
      <h4>${escapeHtml(funding.label_th || "ทุนที่ปรากฏในข้อมูล")}</h4>
      <div class="funding-grid">
        <article><span>นวัตกรรมที่มีรายการทุน บพท.</span>${fundedCountKnown ? `<strong>${formatNumber(funding.pmua_funded_innovation_count)}</strong><small>นวัตกรรม · ${formatNumber(funding.pmua_funding_entry_count)} รายการทุน</small>` : '<strong class="metric-na">—</strong><small>ต้นทางไม่พบรายการทุน</small>'}</article>
        <article><span>มูลค่าทุนที่ต้นทางกรอก</span>${amountKnown ? `<strong>${formatNumber(funding.pmua_amount_baht)}</strong><small>บาท · ไม่ใช่งบจัดสรรจังหวัด</small>` : '<strong class="metric-na">—</strong><small>ต้นทางไม่ระบุมูลค่าทุน</small>'}</article>
        <article><span>มูลค่านวัตกรรมที่ต้นทางกรอก</span>${innovationValueKnown ? `<strong>${formatNumber(funding.innovation_value_baht_total)}</strong><small>บาท · ${formatNumber(funding.innovation_value_known_entries)} รายการ</small>` : '<strong class="metric-na">—</strong><small>ต้นทางไม่ระบุมูลค่า</small>'}</article>
      </div>
      ${funding.note_th ? `<small class="funding-note">${escapeHtml(funding.note_th)}</small>` : ""}
      ${funding.cross_province_sum_warning ? '<p class="funding-warning">มีนวัตกรรมเชื่อมหลายจังหวัด ห้ามรวมยอดรายจังหวัดเป็นยอดประเทศเพราะจะนับซ้ำ</p>' : ""}
    </section>`;

  const outcomes = portfolio.outcome_coverage || {};
  const outcomeHtml = `
    <section class="research-block outcome-coverage-block">
      <h4>ความพร้อมของข้อมูลผลผลิตและผลลัพธ์</h4>
      <div class="funding-grid">
        <article><span>ระบุสังกัดนักวิจัย</span><strong>${formatNumber(outcomes.research_lead_affiliations || 0)}</strong><small>สังกัด</small></article>
        <article><span>ระบุทรัพย์สินทางปัญญา</span><strong>${formatNumber(outcomes.ip_records || 0)}</strong><small>นวัตกรรม</small></article>
        <article><span>ระบุ ROI / SROI</span><strong>${formatNumber((outcomes.roi_records || 0) + (outcomes.sroi_records || 0))}</strong><small>รายการที่มีค่า</small></article>
      </div>
      ${outcomes.note_th ? `<small class="funding-note">${escapeHtml(outcomes.note_th)}</small>` : ""}
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
    ${outcomeHtml}
    ${gapsHtml}`;

  document.querySelectorAll(".district-chip").forEach((chip) => {
    chip.addEventListener("click", () => applyProjectDistrict(chip.dataset.district));
  });
}

const SRA_DIMENSION_LABELS = {
  human: "ทุนมนุษย์",
  physical: "ทุนกายภาพ",
  financial: "ทุนการเงิน",
  natural_res: "ทรัพยากรธรรมชาติ",
  social: "ทุนสังคม",
};

function sraRank(code) {
  const scored = (state.catalog?.provinces || [])
    .filter((province) => province.sra_overall_score !== null && province.sra_overall_score !== undefined)
    .sort((a, b) => a.sra_overall_score - b.sra_overall_score);
  const index = scored.findIndex((province) => province.province_code === code);
  return index === -1 ? null : { rank: index + 1, of: scored.length };
}

function overviewMetricValue(value, status) {
  return isObservedStatus(status) ? formatNumber(value || 0) : "—";
}

function overviewBars(entries, widthAccessor) {
  const maximum = Math.max(...entries.map((entry) => Number(widthAccessor(entry)) || 0), 1);
  return entries.map((entry) => {
    const rawWidth = Number(widthAccessor(entry)) || 0;
    const width = Math.min(100, (rawWidth / maximum) * 100);
    return `
      <div class="overview-bar-row">
        <span>${escapeHtml(entry.label)}</span>
        <i aria-hidden="true"><b style="width:${width.toFixed(1)}%"></b></i>
        <strong>${escapeHtml(entry.display)}</strong>
      </div>`;
  }).join("");
}

function renderProvinceOverview(summary) {
  const portfolio = summary.research_portfolio || {};
  const housingDimension = (summary.dimensions || []).find((item) => item.key === "housing") || {};
  const demandMetric = (housingDimension.metrics || []).find((item) => item.key === "housing_demand_respondents");
  const metrics = [
    { label: "กลุ่มโครงการ", value: portfolio.project_count, status: portfolio.project_count_status, note: "การจัดกลุ่มเบื้องต้น", tab: "projects" },
    { label: "ผู้เข้าร่วมโครงการ", value: portfolio.participant_record_count, status: portfolio.participant_record_status, note: "รายการผู้เข้าร่วม", tab: "portfolio" },
    { label: "นวัตกรรม", value: portfolio.innovation_count, status: portfolio.innovation_count_status, note: "รายการที่เชื่อมจังหวัด", tab: "projects" },
    { label: "Housing demand", value: demandMetric?.value, status: demandMetric ? "available" : "missing", note: "คำตอบแบบสำรวจ ไม่ใช่ประชากร", tab: "portfolio" },
  ];
  const metricGrid = document.getElementById("overviewMetrics");
  metricGrid.innerHTML = metrics.map((metric) => `
    <button type="button" class="province-kpi" data-goto-tab="${metric.tab}">
      <span>${escapeHtml(metric.label)}</span><strong>${overviewMetricValue(metric.value, metric.status)}</strong><small>${escapeHtml(metric.note)}</small>
    </button>`).join("");
  metricGrid.querySelectorAll("[data-goto-tab]").forEach((card) => {
    card.addEventListener("click", () => activatePanelTab(card.dataset.gotoTab));
  });

  const outcomes = portfolio.outcome_coverage || {};
  const projectsKnown = isObservedStatus(portfolio.project_count_status);
  const participantsKnown = isObservedStatus(portfolio.participant_record_status);
  const innovationsKnown = isObservedStatus(portfolio.innovation_count_status);
  const outcomeRecords = Number(outcomes.roi_records || 0) + Number(outcomes.sroi_records || 0);
  const flow = [
    { label: "กลุ่มโครงการ", value: projectsKnown ? portfolio.project_count : null, unit: "กลุ่ม" },
    { label: "ผู้เข้าร่วม", value: participantsKnown ? portfolio.participant_record_count : null, unit: "รายการ" },
    { label: "นวัตกรรม", value: innovationsKnown ? portfolio.innovation_count : null, unit: "รายการ" },
    { label: "ทรัพย์สินทางปัญญา", value: innovationsKnown ? outcomes.ip_records : null, unit: "รายการ" },
    { label: "ROI / SROI", value: innovationsKnown ? outcomeRecords : null, unit: "ช่องข้อมูล" },
  ];
  document.getElementById("overviewFlow").innerHTML = flow.map((item) => `
    <article class="overview-flow-node${item.value === null || item.value === undefined ? " is-missing" : ""}">
      <i aria-hidden="true"></i>
      <strong>${item.value === null || item.value === undefined ? "—" : formatNumber(item.value)}</strong>
      <span>${escapeHtml(item.label)}</span>
      <small>${escapeHtml(item.unit)}</small>
    </article>`).join("");

  const trlEntries = (portfolio.trl_distribution || []).map((entry) => ({
    label: entry.label_th,
    value: Number(entry.value || 0),
    share: Number(entry.share_pct || 0),
    display: `${formatNumber(entry.value || 0)} · ${formatNumber(entry.share_pct || 0, 1)}%`,
  }));
  const trlSection = document.getElementById("overviewTrlSection");
  trlSection.hidden = !trlEntries.length;
  document.getElementById("overviewTrlChart").innerHTML = trlEntries.length
    ? overviewBars(trlEntries, (entry) => entry.share)
    : "";

  const outcomeEntries = [
    { label: "ระบุสังกัดนักวิจัย", value: Number(outcomes.research_lead_affiliations || 0) },
    { label: "ทรัพย์สินทางปัญญา", value: Number(outcomes.ip_records || 0) },
    { label: "ROI / SROI", value: outcomeRecords },
  ].map((entry) => ({ ...entry, display: formatNumber(entry.value) }));
  const outcomeSection = document.getElementById("overviewOutcomeSection");
  outcomeSection.hidden = !innovationsKnown;
  document.getElementById("overviewOutcomeNote").textContent = innovationsKnown
    ? `นวัตกรรมที่เชื่อมจังหวัด ${formatNumber(portfolio.innovation_count || 0)} รายการ`
    : "";
  document.getElementById("overviewOutcomeChart").innerHTML = innovationsKnown
    ? overviewBars(outcomeEntries, (entry) => entry.value)
    : "";
  document.getElementById("overviewVizGrid").hidden = !trlEntries.length && !innovationsKnown;

  const districts = portfolio.districts || [];
  const geographySection = document.getElementById("overviewGeographySection");
  geographySection.hidden = !projectsKnown || !districts.length;
  document.getElementById("overviewDistrictCount").textContent = districts.length
    ? `${formatNumber(portfolio.district_count || districts.length)} อำเภอ`
    : "";
  document.getElementById("overviewDistricts").innerHTML = districts.map((district) => `
    <button type="button" data-overview-district="${escapeHtml(district.label_th)}">
      <span>${escapeHtml(district.label_th)}</span><strong>${formatNumber(district.value || 0)}</strong>
    </button>`).join("");
  document.querySelectorAll("[data-overview-district]").forEach((chip) => {
    chip.addEventListener("click", () => applyProjectDistrict(chip.dataset.overviewDistrict));
  });

  const funding = portfolio.funding || {};
  const fundingKnown = Number(funding.pmua_amount_known_entries || 0) > 0;
  const fundingSection = document.getElementById("overviewFunding");
  fundingSection.hidden = !fundingKnown;
  fundingSection.innerHTML = fundingKnown
    ? `<span>มูลค่าทุนที่ผูกกับนวัตกรรม</span><strong>${formatNumber(funding.pmua_amount_baht || 0)} บาท</strong><small>ไม่ใช่งบจัดสรรจังหวัด</small>`
    : "";
}

function renderSraArea(section = {}) {
  const wrapper = document.getElementById("sraAreaSection");
  const available = section.status === "available" && section.scope_status === "in_scope";
  wrapper.hidden = !available;
  if (!available) return;

  const latestAssistance = [...(section.assistance_trend || [])].sort((a, b) =>
    String(a.year).localeCompare(String(b.year), "th"),
  ).at(-1);
  const om = section.om_total || {};
  const scoreNote = section.score_status === "in_scope_no_current_value"
    ? "จังหวัดเป้าหมายปี 2569 · ยังไม่มีคะแนนทุนดำรงชีพปัจจุบัน"
    : `จังหวัดเป้าหมายปี ${section.scope_as_of || "ไม่ระบุ"} · มีคะแนนทุนดำรงชีพปัจจุบัน`;
  document.getElementById("sraAreaNote").textContent = scoreNote;
  document.getElementById("sraAreaSummary").innerHTML = `
    <article><span>ครัวเรือนรับความช่วยเหลือปี ${escapeHtml(latestAssistance?.year || "ล่าสุด")}</span><strong>${latestAssistance ? formatNumber(latestAssistance.households) : "—"}</strong><small>ครัวเรือน</small></article>
    <article><span>เหตุการณ์ช่วยเหลือ</span><strong>${latestAssistance ? formatNumber(latestAssistance.episodes) : "—"}</strong><small>ครั้ง</small></article>
    <article><span>OM ที่ปรากฏ</span><strong>${om.om_count !== null && om.om_count !== undefined ? formatNumber(om.om_count) : "—"}</strong><small>โมเดล</small></article>
    <article><span>ทุน OM ที่ต้นทางกรอก</span><strong>${om.capital_baht !== null && om.capital_baht !== undefined ? formatNumber(om.capital_baht) : "—"}</strong><small>บาท · ไม่ใช่งบโครงการ บพท.</small></article>`;

  const trend = section.assistance_trend || [];
  document.getElementById("sraAssistanceTrend").innerHTML = trend.length
    ? `<section class="sra-detail-block"><h4>การช่วยเหลือรายปี</h4><div class="sra-table">${trend.map((row) => `
        <p><strong>${escapeHtml(row.year)}</strong><span>${formatNumber(row.households)} ครัวเรือน</span><span>${formatNumber(row.episodes)} ครั้ง</span><span>${formatNumber(row.budget_baht)} บาท</span></p>`).join("")}</div></section>`
    : "";

  const dimensions = section.assistance_dimensions_latest || [];
  document.getElementById("sraAssistanceDimensions").innerHTML = dimensions.length
    ? `<section class="sra-detail-block"><h4>ความช่วยเหลือตามด้าน ปี ${escapeHtml(dimensions[0]?.year || "ล่าสุด")}</h4><div class="sra-table">${dimensions.map((row) => `
        <p><strong>${escapeHtml(row.dimension_title || row.dimension_key)}</strong><span>${formatNumber(row.households)} ครัวเรือน</span><span>${formatNumber(row.budget_baht)} บาท</span></p>`).join("")}</div></section>`
    : "";

  const projectMetrics = section.project_metrics_latest || [];
  document.getElementById("sraProjectMetrics").innerHTML = projectMetrics.length
    ? `<section class="sra-detail-block"><h4>ตัวชี้วัดการดำเนินงานที่ต้นทางรายงาน ปี ${escapeHtml(projectMetrics[0]?.year || "ล่าสุด")}</h4><div class="sra-project-metrics">${projectMetrics.map((metric) => `
        <article><span>${escapeHtml(metric.metric_label || metric.metric_key)}</span><strong>${formatNumber(metric.value, 2)}</strong><small>${escapeHtml(metric.unit || "ไม่ระบุหน่วย")}${metric.target_value !== null && metric.target_value !== undefined ? ` · เป้าหมาย ${formatNumber(metric.target_value, 2)}` : ""}</small></article>`).join("")}</div><p class="section-method-note">${escapeHtml(plainLanguage(section.quality_note_th || "ข้อมูลเบื้องต้นจากต้นทาง"))}</p></section>`
    : "";
}

function renderPoverty(section = {}) {
  const wrapper = document.getElementById("povertySection");
  const items = section.items || [];
  const available = section.status === "available" && items.length > 0;
  wrapper.hidden = !available;
  if (!available) return;

  const byWidget = (widget) => items.filter((item) => item.widget === widget);
  const householdRows = byWidget("households_by_province");
  const findMetric = (rows, name) => rows.find((item) => item.metric_name === name);
  const total = findMetric(householdRows, "จำนวนครัวเรือน");
  const groups = householdRows.filter((item) => /^กลุ่มที่ \d/.test(item.metric_name));
  const members = findMetric(byWidget("members_by_area"), "จำนวนสมาชิกในครัวเรือนยากจน");
  const surveyRows = byWidget("survey_profile");
  const tpmap = findMetric(surveyRows, "TPMAP (2565)");
  const pppSurvey = findMetric(surveyRows, "PPPConnext (2564-2565)");

  const groupPalette = { 1: "#b4551d", 2: "#dd8a4a", 3: "#f2c49a", 4: "#17573f" };
  const groupSum = groups.reduce((sum, item) => sum + (Number(item.value) || 0), 0) || 1;
  const groupBars = groups
    .map((item) => {
      const groupNo = (item.metric_name.match(/กลุ่มที่ (\d)/) || [])[1];
      const value = Number(item.value) || 0;
      const pct = (value / groupSum) * 100;
      const label = item.metric_name.replace(/^กลุ่มที่ (\d)\s*/, "กลุ่ม $1 · ");
      return `
        <div class="poverty-row">
          <span>${escapeHtml(label)}</span>
          <i><b style="width:${Math.max(1.5, pct).toFixed(1)}%; background:${groupPalette[groupNo] || "#8a9a90"}"></b></i>
          <strong>${formatNumber(value)}<small> (${pct.toFixed(1)}%)</small></strong>
        </div>`;
    })
    .join("");

  const benchmarkParts = [];
  if (tpmap) benchmarkParts.push(`TPMAP ปี 2565: ${formatNumber(tpmap.value)}`);
  if (pppSurvey) benchmarkParts.push(`ฐานสำรวจ PPPConnext 2564–65: ${formatNumber(pppSurvey.value)}`);
  const sourceUrl = safeExternalUrl(items[0]?.source_url);

  document.getElementById("povertyNote").textContent = "ตัวเลขเบื้องต้นจากหน้า PPAOS";
  document.getElementById("povertyContent").innerHTML = `
    <div class="poverty-stats">
      <article><span>ครัวเรือนที่สำรวจ</span><strong>${formatNumber(total?.value || 0)}</strong></article>
      <article><span>สมาชิกในครัวเรือนยากจน</span><strong>${formatNumber(members?.value || 0)}</strong></article>
    </div>
    ${groupBars ? `<div class="poverty-rows">${groupBars}</div>` : ""}
    <p class="poverty-benchmark">${benchmarkParts.length ? `ฐานเทียบ: ${escapeHtml(benchmarkParts.join(" · "))} · ` : ""}${sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noreferrer">เปิดหน้า BI ต้นทาง</a>` : ""}</p>`;
}

const CITY_METRICS = [
  ["environment.pm25", "PM2.5", "µg/m³"],
  ["environment.heatDays", "วันร้อนจัดต่อปี", "วัน"],
  ["environment.flood", "พื้นที่เสี่ยงน้ำท่วม", "%"],
  ["environment.green", "พื้นที่สีเขียว", "%"],
  ["infrastructure.internet", "เข้าถึงอินเทอร์เน็ต", "%"],
  ["infrastructure.waterAccess", "เข้าถึงน้ำประปา", "%"],
];

function renderCityCapital(section = {}) {
  const wrapper = document.getElementById("citySection");
  const items = section.items || [];
  wrapper.hidden = section.status !== "available" || !items.length;
  if (wrapper.hidden) return;
  document.getElementById("cityNote").textContent = `${formatNumber(items.length)} เทศบาลจากชุดข้อมูลเมืองเปิด`;
  document.getElementById("cityItems").innerHTML = items
    .map((city) => {
      const values = city.values || {};
      const rows = CITY_METRICS.filter(([key]) => values[key] !== null && values[key] !== undefined)
        .map(([key, label, unit]) => `<div><dt>${escapeHtml(label)}</dt><dd>${formatNumber(values[key], 1)} ${escapeHtml(unit)}</dd></div>`)
        .join("");
      return `
        <article class="data-card city-card">
          <div class="record-kicker"><span>${escapeHtml(city.district_name_th ? `อ.${city.district_name_th}` : "ไม่ระบุอำเภอ")}</span></div>
          <h3>${escapeHtml(city.city_name_th || "ไม่ระบุเทศบาล")}</h3>
          <dl>${rows}</dl>
        </article>`;
    })
    .join("");
}

async function renderDisaster() {
  const wrapper = document.getElementById("disasterSection");
  const content = document.getElementById("disasterContent");
  const note = document.getElementById("disasterNote");
  const code = state.selectedCode;
  if (!code || !wrapper || !content) { 
    destroyDisasterCharts();
    if (wrapper) wrapper.hidden = true; 
    return; 
  }
  
  try {
    const response = await fetch("/api/public/v1/provinces/" + code + "/disaster-tracking", { cache: "no-store" });
    if (!response.ok) throw new Error("Disaster API " + response.status);
    const data = await response.json();
    if (state.selectedCode !== code) return;
    
    const sources = data.sources || {};
    const sourceCount = Number(data.source_count || Object.keys(sources).length || 0);
    const recordCount = Number(data.record_count || 0);
    
    if (sourceCount === 0) {
      destroyDisasterCharts();
      wrapper.hidden = true;
      return;
    }
    wrapper.hidden = false;
    if (note) note.textContent = plainLanguage(data.quality_label_th || "ข้อมูลเบื้องต้น · ยังไม่ใช่สถานการณ์ภัยที่รับรอง");
    destroyDisasterCharts();
    state.pendingDisasterCharts = [];
    
    const html = `
      <div class="disaster-summary">
        <article><span>แหล่งติดตามภัย</span><strong>${formatNumber(sourceCount)}</strong></article>
        <article><span>รายการเบื้องต้น</span><strong>${formatNumber(recordCount)}</strong></article>
        <article><span>อัปเดตล่าสุดที่พบ</span><strong>${escapeHtml(data.latest_observed_at || "ไม่ระบุ")}</strong></article>
      </div>
      <div class="disaster-source-list">
        ${Object.values(sources)
          .map((info) => {
            const records = info.records || [];
            const datasetTags = (info.dataset_keys || [])
              .map((key) => `<span>${escapeHtml(formatDisasterDatasetLabel(key))}</span>`)
              .join("");
            return `
              <article class="disaster-source-card">
                <header>
                  <div><strong>${escapeHtml(info.name_th || info.source_id)}</strong><small>${escapeHtml(plainLanguage(info.quality_label_th || data.quality_label_th || ""))}</small></div>
                  <span>${formatNumber(info.count || 0)} รายการ</span>
                </header>
                ${datasetTags ? `<div class="disaster-tags">${datasetTags}</div>` : ""}
                ${renderDisasterInsights(info.insights || {}, records)}
                ${Number(info.count || 0) > records.length ? `<p class="disaster-more">ยังมีอีก ${formatNumber(Number(info.count || 0) - records.length)} รายการ</p>` : ""}
              </article>`;
          })
          .join("")}
      </div>`;
    content.innerHTML = html;
    requestAnimationFrame(renderPendingDisasterCharts);
  } catch (error) {
    console.error("Disaster error:", error);
    if (wrapper) wrapper.hidden = true;
  }
}

function renderDisasterInsights(insights = {}, records = []) {
  const datasetCounts = insights.dataset_counts || [];
  const datasetBars = datasetCounts.length
    ? `<section class="disaster-insight-block"><h4>ข้อมูลที่ดึงได้</h4>${disasterBars(datasetCounts)}</section>`
    : "";
  if (insights.kind === "incident_feed") {
    const statusBars = (insights.status_counts || []).length
      ? `<section class="disaster-insight-block"><h4>ประเภทเหตุการณ์</h4>${disasterBars(insights.status_counts)}</section>`
      : "";
    const priorityBars = (insights.priority_counts || []).length
      ? `<section class="disaster-insight-block"><h4>ระดับประกาศ</h4>${disasterBars(insights.priority_counts)}</section>`
      : "";
    const highlights = (insights.highlights || []).length
      ? `<section class="disaster-insight-block disaster-highlights"><h4>ประกาศล่าสุด</h4>${insights.highlights
          .map((item) => `<article><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml([item.status, item.observed_at].filter(Boolean).join(" · "))}</small></article>`)
          .join("")}</section>`
      : "";
    return `<div class="disaster-insights">${statusBars}${priorityBars}${highlights}${datasetBars}</div>`;
  }
  if (insights.kind === "water_metrics") {
    return `
      <div class="disaster-insights">
        ${renderDisasterMetrics(insights.metrics || [])}
        ${renderDisasterTrends(insights.trends || [])}
        ${datasetBars}
      </div>`;
  }
  if (insights.kind === "station_status") {
    const stations = (insights.stations || []).filter((item) => item.station).slice(0, 10);
    const stationCards = stations.length
      ? `<section class="disaster-insight-block"><h4>สถานีตรวจวัด</h4><div class="disaster-station-grid">${stations
          .map((item) => `
            <article>
              <strong>${escapeHtml(item.station)}</strong>
              <span>${escapeHtml(item.status || "ไม่ระบุสถานะ")}</span>
              <small>${[
                item.water_level !== null && item.water_level !== undefined ? `ระดับน้ำ ${formatNumber(item.water_level, 2)} ม.รทก.` : null,
                item.water_percent !== null && item.water_percent !== undefined ? `ปริมาณน้ำ ${formatNumber(item.water_percent, 1)}%` : null,
                item.bank_level !== null && item.bank_level !== undefined ? `ตลิ่ง ${formatNumber(item.bank_level, 2)} ม.รทก.` : null,
              ].filter(Boolean).map(escapeHtml).join(" · ")}</small>
            </article>`)
          .join("")}</div></section>`
      : "";
    const statusBars = (insights.status_counts || []).length
      ? `<section class="disaster-insight-block"><h4>สถานะสถานี</h4>${disasterBars(insights.status_counts)}</section>`
      : "";
    return `<div class="disaster-insights">${statusBars}${stationCards}${datasetBars}</div>`;
  }
  if (insights.kind === "rain_shelter") {
    const districtBars = (insights.district_counts || []).length
      ? `<section class="disaster-insight-block"><h4>ศูนย์พักพิงตามอำเภอ</h4>${disasterBars(insights.district_counts)}</section>`
      : "";
    return `
      <div class="disaster-insights">
        ${renderDisasterMetrics(insights.metrics || [])}
        ${renderDisasterTrends(insights.trends || [])}
        ${districtBars}
        ${datasetBars}
      </div>`;
  }
  return records.length
    ? `<div class="disaster-records">${records.slice(0, 4).map(renderDisasterRecord).join("")}</div>`
    : datasetBars;
}

function formatDisasterDatasetLabel(key = "") {
  const labels = {
    "announcements.row": "ประกาศ",
    "incident_map.row": "เหตุการณ์บนแผนที่",
    "incidents.row": "รายงานเหตุการณ์",
    "water_levels.row": "ระดับน้ำ",
    "rain_24h.row": "ฝน 24 ชม.",
    "stations.row": "สถานีตรวจวัด",
    "shelters.row": "ศูนย์พักพิง",
    "rain_analysis.row": "เรดาร์ฝน",
    "dams.dam_medium": "เขื่อนขนาดกลาง",
    "dams.dam_small_tele": "เขื่อนโทรมาตร",
    "dams.dam_daily": "เขื่อนรายวัน",
    "dams.dam_hourly": "เขื่อนรายชั่วโมง",
  };
  return labels[key] || String(key).replace(/_/g, " ");
}

function renderDisasterMetrics(metrics = []) {
  const items = metrics.filter((item) => item.value !== null && item.value !== undefined);
  if (!items.length) return "";
  return `<section class="disaster-metrics">${items
    .map((item) => `<article><span>${escapeHtml(item.label)}</span><strong>${formatNumber(item.value, 2)}</strong><small>${escapeHtml(item.unit || "")}</small></article>`)
    .join("")}</section>`;
}

function renderDisasterTrends(trends = []) {
  const visible = trends.filter((trend) => (trend.series || []).length || (trend.latest_points || []).length);
  if (!visible.length) return "";
  return visible
    .map((trend) => `
      <section class="disaster-insight-block">
        <h4>${escapeHtml(trend.title)} <span>${escapeHtml(trend.unit || "")}</span></h4>
        ${(trend.series || []).length || (trend.latest_points || []).length ? `<div class="disaster-trend-list">${[...(trend.series || []), ...(trend.latest_points || [])].map((series) => renderDisasterLineChart(series, trend.unit)).join("")}</div>` : ""}
      </section>`)
    .join("");
}

function renderDisasterLineChart(series = {}, unit = "") {
  const points = (series.points || []).filter((point) => Number.isFinite(Number(point.v)));
  if (!points.length) return "";
  const chartId = `disasterChart${++state.disasterChartSequence}`;
  state.pendingDisasterCharts.push({
    id: chartId,
    label: series.label || "สถานี",
    stationId: series.station_id || series.label || "",
    metric: series.metric || "water",
    unit,
    points,
  });
  const firstLabel = points[0]?.t ? formatShortDateTime(points[0].t) : "";
  const lastLabel = points[points.length - 1]?.t ? formatShortDateTime(points[points.length - 1].t) : "";
  return `
    <article class="disaster-trend">
      <div class="disaster-trend-head">
        <div>
          <strong>${escapeHtml(series.label)}</strong>
          <small>${formatNumber(series.latest, 2)} ${escapeHtml(unit || "")}</small>
        </div>
        <button type="button" data-disaster-history data-station-id="${escapeHtml(series.station_id || series.label || "")}" data-station-name="${escapeHtml(series.label || "")}" data-metric="${escapeHtml(series.metric || "water")}">ขยาย</button>
      </div>
      <div class="disaster-chart-frame"><canvas id="${chartId}" aria-label="${escapeHtml(series.label)}"></canvas></div>
      <div class="disaster-trend-axis"><span>${escapeHtml(firstLabel)}</span><span>${escapeHtml(lastLabel)}</span></div>
    </article>`;
}

function destroyDisasterCharts() {
  state.disasterCharts.forEach((chart) => chart.destroy());
  state.disasterCharts = [];
}

function renderPendingDisasterCharts() {
  if (!window.Chart) return;
  state.pendingDisasterCharts.forEach((spec) => {
    const canvas = document.getElementById(spec.id);
    if (!canvas) return;
    const labels = spec.points.map((point) => formatShortDateTime(point.t));
    const values = spec.points.map((point) => Number(point.v));
    const chart = new Chart(canvas, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: spec.label,
            data: values,
            borderColor: "#a92626",
            backgroundColor: "rgba(169, 38, 38, 0.12)",
            borderWidth: 2,
            pointRadius: 2,
            pointHoverRadius: 4,
            tension: 0.25,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: { intersect: false, mode: "index" },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (context) => `${formatNumber(context.parsed.y, 2)} ${spec.unit || ""}`,
            },
          },
        },
        scales: {
          x: {
            ticks: { color: "#7b8580", maxTicksLimit: 4, font: { size: 10 } },
            grid: { display: false },
          },
          y: {
            ticks: {
              color: "#7b8580",
              font: { size: 10 },
              callback: (value) => formatNumber(value, 1),
            },
            grid: { color: "rgba(160, 120, 120, 0.18)" },
          },
        },
      },
    });
    state.disasterCharts.push(chart);
  });
  state.pendingDisasterCharts = [];
}

function ensureStationHistoryModal() {
  let modal = document.getElementById("stationHistoryModal");
  if (modal) return modal;
  document.body.insertAdjacentHTML(
    "beforeend",
    `
      <div class="station-history-modal" id="stationHistoryModal" hidden>
        <div class="station-history-dialog" role="dialog" aria-modal="true" aria-labelledby="stationHistoryTitle">
          <header>
            <div>
              <span id="stationHistoryKicker">ติดตามภัย</span>
              <h3 id="stationHistoryTitle">ประวัติสถานี</h3>
              <small id="stationHistoryStatus"></small>
            </div>
            <button type="button" data-station-history-close aria-label="ปิด">×</button>
          </header>
          <div class="station-history-controls" role="group" aria-label="เลือกช่วงกราฟ">
            <button type="button" class="active" data-history-grain="daily">รายวัน</button>
            <button type="button" data-history-grain="weekly">รายสัปดาห์</button>
            <button type="button" data-history-grain="monthly">รายเดือน</button>
          </div>
          <div class="station-history-chart"><canvas id="stationHistoryChart"></canvas></div>
          <p id="stationHistoryMessage"></p>
        </div>
      </div>`
  );
  modal = document.getElementById("stationHistoryModal");
  modal.addEventListener("click", (event) => {
    if (event.target === modal || event.target.closest("[data-station-history-close]")) {
      closeStationHistoryModal();
    }
    const grainButton = event.target.closest("[data-history-grain]");
    if (grainButton) {
      modal.querySelectorAll("[data-history-grain]").forEach((button) => {
        button.classList.toggle("active", button === grainButton);
      });
      loadStationHistory({
        stationId: modal.dataset.stationId,
        stationName: modal.dataset.stationName,
        metric: modal.dataset.metric,
        grain: grainButton.dataset.historyGrain,
      });
    }
  });
  return modal;
}

function closeStationHistoryModal() {
  const modal = document.getElementById("stationHistoryModal");
  if (modal) modal.hidden = true;
  if (state.stationHistoryChart) {
    state.stationHistoryChart.destroy();
    state.stationHistoryChart = null;
  }
}

function openStationHistoryModal({ stationId, stationName, metric }) {
  if (!state.selectedCode || !stationId) return;
  const modal = ensureStationHistoryModal();
  modal.dataset.stationId = stationId;
  modal.dataset.stationName = stationName || stationId;
  modal.dataset.metric = metric || "water";
  modal.hidden = false;
  modal.querySelectorAll("[data-history-grain]").forEach((button) => {
    button.classList.toggle("active", button.dataset.historyGrain === "daily");
  });
  loadStationHistory({ stationId, stationName, metric: metric || "water", grain: "daily" });
}

async function loadStationHistory({ stationId, stationName, metric, grain }) {
  const modal = ensureStationHistoryModal();
  const title = document.getElementById("stationHistoryTitle");
  const status = document.getElementById("stationHistoryStatus");
  const message = document.getElementById("stationHistoryMessage");
  title.textContent = stationName || stationId;
  status.textContent = "กำลังโหลดประวัติ 90 วัน";
  message.textContent = "";
  const params = new URLSearchParams({ metric: metric || "water", grain: grain || "daily", days: "90" });
  try {
    const response = await fetch(`/api/public/v1/provinces/${state.selectedCode}/disaster-stations/${encodeURIComponent(stationId)}/history?${params}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`History API ${response.status}`);
    const data = await response.json();
    status.textContent = stationHistoryStatusText(data);
    renderStationHistoryChart(data);
    if (!data.points?.length) {
      message.textContent = "ยังไม่มีข้อมูลย้อนหลังของสถานีนี้";
    } else if (data.history_status === "snapshot_only") {
      message.textContent = "มีเฉพาะข้อมูลที่บันทึกไว้ ยังไม่มีข้อมูลย้อนหลังครบ 90 วัน";
    } else {
      message.textContent = data.quality_label_th || "";
    }
  } catch (error) {
    console.error("Station history error:", error);
    status.textContent = "โหลดประวัติไม่สำเร็จ";
    message.textContent = "ยังไม่สามารถเชื่อมประวัติย้อนหลังของสถานีนี้ได้";
    renderStationHistoryChart({ metric, grain, unit: "", points: [] });
  }
}

function stationHistoryStatusText(data = {}) {
  const metric = data.metric === "rain" ? "ฝน" : "ระดับน้ำ";
  const grain = { daily: "รายวัน", weekly: "รายสัปดาห์", monthly: "รายเดือน" }[data.grain] || "รายวัน";
  const status = data.history_status === "available" ? "มีข้อมูลย้อนหลัง" : data.history_status === "snapshot_only" ? "มีข้อมูลที่บันทึกไว้" : "ยังไม่มีข้อมูลย้อนหลัง";
  return `${metric} ${grain} · ${data.days || 90} วัน · ${status}`;
}

function renderStationHistoryChart(data = {}) {
  if (state.stationHistoryChart) {
    state.stationHistoryChart.destroy();
    state.stationHistoryChart = null;
  }
  const canvas = document.getElementById("stationHistoryChart");
  if (!canvas || !window.Chart) return;
  const points = data.points || [];
  const chartType = data.metric === "rain" ? "bar" : "line";
  state.stationHistoryChart = new Chart(canvas, {
    type: chartType,
    data: {
      labels: points.map((point) => point.t),
      datasets: [{
        label: data.metric === "rain" ? "ฝน" : "ระดับน้ำ",
        data: points.map((point) => Number(point.v)),
        borderColor: "#a92626",
        backgroundColor: data.metric === "rain" ? "rgba(169, 38, 38, 0.32)" : "rgba(169, 38, 38, 0.12)",
        borderWidth: 2,
        pointRadius: data.metric === "rain" ? 0 : 2,
        tension: 0.25,
        fill: data.metric !== "rain",
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (context) => `${formatNumber(context.parsed.y, 2)} ${data.unit || ""}`,
          },
        },
      },
      scales: {
        x: { ticks: { color: "#6f7b75", maxTicksLimit: 8 }, grid: { display: false } },
        y: {
          ticks: { color: "#6f7b75", callback: (value) => formatNumber(value, 1) },
          grid: { color: "rgba(160, 120, 120, 0.18)" },
        },
      },
    },
  });
}

function renderDisasterLatestPoints(points = [], unit = "") {
  const items = points.filter((point) => point.label && Number.isFinite(Number(point.latest)));
  if (!items.length) return "";
  return `
    <div class="disaster-latest-grid">
      ${items.map((item) => `
        <article>
          <span>${escapeHtml(item.label)}</span>
          <strong>${formatNumber(item.latest, 2)}</strong>
          <small>${escapeHtml(unit || "")}</small>
        </article>`).join("")}
    </div>`;
}

function formatShortDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16);
  return date.toLocaleDateString("th-TH", { month: "short", day: "numeric" });
}

function disasterBars(items = []) {
  const max = Math.max(...items.map((item) => Number(item.value) || 0), 1);
  return `<div class="disaster-bars">${items
    .map((item) => {
      const value = Number(item.value) || 0;
      return `<p><span>${escapeHtml(item.label)}</span><i><b style="width:${Math.max(2, (value / max) * 100).toFixed(1)}%"></b></i><strong>${formatNumber(value)}</strong></p>`;
    })
    .join("")}</div>`;
}

function renderDisasterRecord(record = {}) {
  const primary = record.label || record.status || record.dataset_key || "รายการติดตามภัย";
  const facts = [
    record.district ? ["พื้นที่", record.district] : null,
    record.observed_at ? ["เวลา", record.observed_at] : null,
    record.water_level !== undefined ? ["ระดับน้ำ", record.water_level] : null,
    record.rainfall !== undefined ? ["ฝน", record.rainfall] : null,
    record.status ? ["สถานะ", record.status] : null,
  ].filter(Boolean);
  return `
    <div class="disaster-record">
      <strong>${escapeHtml(primary)}</strong>
      ${facts.length ? `<dl>${facts.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")}</dl>` : ""}
    </div>`;
}

function renderHousing(section = {}) {
  const wrapper = document.getElementById("housingSection");
  const groups = section.resource_groups || [];
  const spatial = section.spatial_summary || null;
  const demand = section.demand_summary || null;
  const available = section.status === "available" && (groups.length > 0 || spatial || demand);
  wrapper.hidden = !available;
  if (!available) return;
  const spatialTotal = Number(section.spatial_feature_total || spatial?.total_spatial_features || 0);
  document.getElementById("housingNote").textContent = [
    `${formatNumber(section.total_records || 0)} รายการ`,
    spatial ? `${formatNumber(spatialTotal)} จุดและพื้นที่` : null,
    demand ? `${formatNumber(section.demand_record_total || demand.respondents_living || 0)} คำตอบ` : null,
  ].filter(Boolean).join(" · ");
  const counts = spatial?.counts || {};
  const categories = Object.entries(spatial?.housing_points?.by_category || {})
    .map(([label, value]) => ({ label, value: Number(value) || 0 }))
    .sort((a, b) => b.value - a.value);
  const maxCategory = Math.max(...categories.map((item) => item.value), 1);
  const categoryLabels = {
    apartment: "อพาร์ตเมนต์", condo: "คอนโด", lodging: "ที่พัก",
    dormitory: "หอพัก", camping: "แคมป์", other: "ประเภทอื่น",
  };
  const demandFuture = demand?.single_choice_distributions?.future_housing_demand;
  const demandHtml = demand ? `
    <div class="housing-spatial-kpis housing-demand-kpis">
      <article><span>ผู้ตอบที่อาศัยในจังหวัด</span><strong>${formatNumber(demand.respondents_living || 0)}</strong><small>คำตอบแบบสำรวจ</small></article>
      <article><span>เลือกจังหวัดนี้เป็นพื้นที่ที่ต้องการ</span><strong>${formatNumber(demand.respondents_preferring_destination || 0)}</strong><small>คำตอบที่ระบุปลายทาง</small></article>
    </div>
    ${demandFuture ? `<article class="housing-spatial-chart"><header><strong>${escapeHtml(demandFuture.label_th)}</strong><small>${formatNumber(demandFuture.answered || 0)} คำตอบ</small></header><div>${overviewBars((demandFuture.items || []).slice(0, 5).map((item) => ({ label: item.label_th, value: item.value, display: `${formatNumber(item.value)} · ${formatNumber(item.share_pct, 1)}%` })), (item) => item.value)}</div></article>` : ""}` : "";
  const spatialHtml = spatial ? `
    <div class="housing-spatial-kpis">
      <article><span>จุดที่อยู่อาศัย</span><strong>${formatNumber(counts.housing_points || 0)}</strong><small>จุดสาธารณะ</small></article>
      <article><span>กริดการเข้าถึง</span><strong>${formatNumber(counts.accessibility_grid || 0)}</strong><small>คะแนนเฉลี่ย ${formatNumber(spatial.accessibility_grid?.score_mean || 0, 1)}</small></article>
      <article><span>พื้นที่เสี่ยงน้ำท่วม</span><strong>${formatNumber(counts.flood_grid || 0)}</strong><small>polygon features</small></article>
      <article><span>ขอบเขตแขวง</span><strong>${formatNumber(counts.subdistrict_boundaries || 0)}</strong><small>169 แขวงครบ</small></article>
    </div>
    <article class="housing-spatial-chart">
      <header><strong>ประเภทจุดที่อยู่อาศัย</strong><small>นับแยกจาก CKAN และ demand respondents</small></header>
      <div>${categories.map((item) => `
        <div class="housing-bar"><span>${escapeHtml(categoryLabels[item.label] || item.label)}</span><i><b style="width:${Math.max(2, item.value / maxCategory * 100).toFixed(1)}%"></b></i><strong>${formatNumber(item.value)}</strong></div>`).join("")}</div>
    </article>` : "";
  document.getElementById("housingSpatialSummary").innerHTML = demandHtml + spatialHtml;
  const visibleGroups = groups.slice(0, 8);
  const remaining = groups.length - visibleGroups.length;
  document.getElementById("housingItems").innerHTML =
    visibleGroups
      .map((group) => {
        const url = safeExternalUrl(group.source_url);
        return `
        <article class="housing-link">
          <div><strong>${escapeHtml(group.dataset_title || group.dataset_key || "ชุดข้อมูลที่อยู่อาศัย")}</strong><small>${escapeHtml(group.resource_name || "")}</small></div>
          ${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">เปิดชุดข้อมูล</a>` : ""}
        </article>`;
      })
      .join("") +
    (remaining > 0
      ? `<p class="housing-more">และอีก ${formatNumber(remaining)} ชุดข้อมูลในต้นทางเดียวกัน</p>`
      : "");
}

function populateProjectFilters(section) {
  const items = section.items || [];
  const years = [...new Set(items.map((item) => item.fiscal_year).filter(Boolean))].sort();
  const districts = [...new Set(items.flatMap((item) => (item.geography || []).map((area) => area.district)).filter(Boolean))].sort((a, b) =>
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
    if (state.projectDistrict && !(item.geography || []).some((area) => area.district === state.projectDistrict)) return false;
    if (!query) return true;
    return [
      item.project_name,
      item.research_unit,
      ...(item.businesses || []),
      ...(item.geography || []).flatMap((area) => [area.district, ...(area.subdistricts || [])]),
    ]
      .filter(Boolean)
      .join(" ")
      .toLocaleLowerCase("th")
      .includes(query);
  });
  document.getElementById("projectResultCount").textContent =
    `แสดง ${formatNumber(filtered.length)} จาก ${formatNumber((section.items || []).length)} กลุ่มโครงการชั่วคราว`;
  container.innerHTML = filtered
    .map((item) => {
      const geography = (item.geography || []).map((area) =>
        `อ.${area.district}${area.subdistricts?.length ? ` (${area.subdistricts.map((name) => `ต.${name}`).join(", ")})` : ""}`,
      ).join(" · ");
      const participantPreview = (item.businesses || []).slice(0, 6);
      const sourceUrl = safeExternalUrl(item.source_url);
      return `
        <article class="data-card project-card">
          <div class="record-kicker"><span>ปีงบประมาณ ${escapeHtml(item.fiscal_year || "ไม่ระบุ")}</span><span>กลุ่มชั่วคราว · ไม่มีรหัสโครงการกลาง</span></div>
          <h3>${escapeHtml(item.project_name || "ไม่ระบุชื่อโครงการ")}</h3>
          <div class="project-record-stats">
            <span><strong>${formatNumber(item.participant_record_count)}</strong> รายการผู้เข้าร่วม</span>
            <span><strong>${formatNumber(item.business_count)}</strong> กลุ่ม/ธุรกิจ</span>
            <span><strong>${formatNumber((item.geography || []).length)}</strong> อำเภอ</span>
          </div>
          <p class="project-geography"><span>พื้นที่ดำเนินงาน</span><strong>${escapeHtml(geography || "ต้นทางไม่ระบุพื้นที่ย่อย")}</strong></p>
          <p class="project-data-gap">สถานะโครงการและงบจัดสรร/เบิกจ่าย: <strong>ต้นทางไม่ระบุ</strong></p>
          ${participantPreview.length ? `<details class="project-participants"><summary>ดูตัวอย่างผู้เข้าร่วม ${formatNumber(participantPreview.length)} จาก ${formatNumber(item.business_count)} ราย</summary><ul>${participantPreview.map((name) => `<li>${escapeHtml(name)}</li>`).join("")}</ul></details>` : ""}
          <footer><span>${escapeHtml(item.research_unit || "ไม่ระบุหน่วยวิจัย")}</span>${sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noreferrer">ต้นทาง</a>` : ""}</footer>
        </article>`;
    })
    .join("") || '<article class="empty-data"><strong>ไม่พบโครงการที่ตรงกับตัวกรอง</strong><span>ลองล้างคำค้นหรือเลือกทุกปี/ทุกอำเภอ</span></article>';
}

function renderInnovations(section) {
  const container = document.getElementById("innovationItems");
  document.getElementById("innovationSection").hidden = section.status !== "available";
  container.innerHTML = (section.items || [])
    .map((item) => {
      const funding = (item.funding || []).map((entry) =>
        [entry.funder, entry.amount_text].filter(Boolean).join(" · "),
      ).filter(Boolean).join(" | ");
      const target = (item.target_groups || [])[0];
      const leads = (item.research_leads || []).map((lead) =>
        [lead.faculty, lead.institute].filter(Boolean).join(" · "),
      ).filter(Boolean);
      const ip = item.ip || {};
      const ipText = [ip.type, ip.asset_name].filter(Boolean).join(" · ");
      const roi = item.roi_indicator !== null && item.roi_indicator !== undefined
        ? `${item.roi_indicator}${item.roi_unit ? ` ${item.roi_unit}` : ""}`
        : "ไม่ระบุ";
      const sroi = item.sroi_indicator !== null && item.sroi_indicator !== undefined
        ? `${item.sroi_indicator}${item.sroi_unit ? ` ${item.sroi_unit}` : ""}`
        : "ไม่ระบุ";
      const sourceUrl = safeExternalUrl(item.source_url);
      return `
        <article class="data-card innovation-card">
          <div class="record-kicker"><span>ความพร้อมเทคโนโลยี ${escapeHtml(item.trl_level ?? "ไม่ระบุ")} · ความพร้อมสังคม ${escapeHtml(item.srl_level ?? "ไม่ระบุ")}</span><span>${escapeHtml(item.category || "ไม่ระบุหมวด")}</span></div>
          <h3>${escapeHtml(item.title || "ไม่ระบุชื่อนวัตกรรม")}</h3>
          <p>${escapeHtml(trimText((item.highlights || [])[0] || target || item.description, 220))}</p>
          <dl>
            <div><dt>ประเภท</dt><dd>${escapeHtml(item.innovation_type || "ไม่ระบุ")}</dd></div>
            <div><dt>เงินทุนที่ต้นทางกรอก</dt><dd>${escapeHtml(funding || "ไม่ระบุ")}</dd></div>
            <div><dt>กลุ่มเป้าหมาย</dt><dd>${escapeHtml(trimText(target || "ไม่ระบุ", 150))}</dd></div>
            <div><dt>สังกัดนักวิจัย</dt><dd>${escapeHtml(leads.join(" | ") || "ไม่ระบุ")}</dd></div>
            <div><dt>ทรัพย์สินทางปัญญา</dt><dd>${escapeHtml(ipText || "ไม่ระบุ")}</dd></div>
            <div><dt>ROI / SROI</dt><dd>${escapeHtml(`${roi} / ${sroi}`)}</dd></div>
          </dl>
          ${Number(item.linked_province_count || 0) > 1 ? `<p class="funding-warning">รายการนี้เชื่อม ${formatNumber(item.linked_province_count)} จังหวัด เงินทุนจึงไม่ใช่งบจัดสรรเฉพาะจังหวัดนี้</p>` : ""}
          <footer><span>${escapeHtml(item.owner_affiliation_name || "ไม่ระบุสังกัด")} · นักวิจัยร่วม ${formatNumber(item.co_researcher_count || 0)} คน</span>${sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noreferrer">รายละเอียด</a>` : ""}</footer>
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
        <footer><span>${escapeHtml(plainLanguage(item.owner_affiliation_name || item.organization || item.scope_note_th || "ข้อมูลเบื้องต้น"))}</span>${sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noreferrer">ต้นทาง</a>` : ""}</footer>
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

  document.getElementById("tourismUpdated").textContent = scrapedAt ? `บันทึกเมื่อ ${formatDate(scrapedAt)}` : "ข้อมูลที่บันทึกไว้";
  document.getElementById("tourismFacts").innerHTML = [
    ["เรื่องแนะนำ", recommendations.length],
    ["สถานีหลัก", stations.length],
    ["เที่ยวรถ", trainServices.length + tramServices.length],
    ["กลุ่มทำโคม", lanternGroupCount],
  ].map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${formatNumber(value)}</strong></article>`).join("");

  const recommendationCards = recommendations.map((item) => {
    const imageUrl = safeExternalUrl(item.image_url);
    return `
      <article class="tourism-place${imageUrl ? "" : " no-image"}">
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
      (item) => {
        // Without an image the content used to fall into the 76px image
        // column and render as a crushed one-word-per-line strip.
        const imageUrl = safeExternalUrl(item.image_url);
        return `
        <article class="data-card culture-card${imageUrl ? "" : " no-image"}">
          ${imageUrl ? `<img src="${escapeHtml(imageUrl)}" alt="" loading="lazy" referrerpolicy="no-referrer" />` : ""}
          <div>
            <div class="record-kicker"><span>${escapeHtml(item.cultural_type || "ทุนวัฒนธรรม")}</span><span>${escapeHtml(item.category || "ไม่ระบุหมวด")}</span></div>
            <h3>${escapeHtml(item.title_th || "ไม่ระบุชื่อ")}</h3>
            <p>${escapeHtml(trimText(item.risk_reason || item.history || "ต้นทางไม่ได้ระบุเหตุผลความเสี่ยง", 180))}</p>
            <footer><span>${escapeHtml([item.tambon, item.amphoe].filter(Boolean).join(" · ") || "ไม่ระบุพื้นที่ย่อย")}</span><a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">ต้นทาง</a></footer>
          </div>
        </article>`;
      },
    )
    .join("") || '<article class="empty-data"><strong>ไม่พบรายการที่ตรงกับคำค้น</strong><span>ลองใช้ชื่ออำเภอหรือหมวดวัฒนธรรม</span></article>';
}

function renderPeopleAreaOverview(summary = state.currentSummary, briefing = state.currentBriefing) {
  const wrapper = document.getElementById("peopleOverviewSection");
  const target = document.getElementById("peopleAreaOverview");
  if (!wrapper || !target || !summary) return;

  const portfolio = summary.research_portfolio || {};
  const sections = briefing?.sections || {};
  const metrics = [];
  if (isObservedStatus(portfolio.participant_record_status)) {
    metrics.push(["ผู้เข้าร่วม", portfolio.participant_record_count, "รายการ"]);
  }
  if (isObservedStatus(portfolio.project_count_status)) {
    metrics.push(["พื้นที่โครงการ", portfolio.district_count, "อำเภอ"]);
  }
  if (sections.culture?.status === "available") {
    metrics.push(["ทุนวัฒนธรรม", sections.culture.total_records ?? sections.culture.items?.length, "รายการ"]);
  }
  const latestAssistance = [...(sections.sra?.assistance_trend || [])]
    .sort((a, b) => String(a.year).localeCompare(String(b.year), "th"))
    .at(-1);
  if (sections.sra?.status === "available" && latestAssistance) {
    metrics.push(["ครัวเรือนช่วยเหลือ", latestAssistance.households, `ปี ${latestAssistance.year}`]);
  }
  if (sections.tourism?.status === "available") {
    metrics.push(["ข้อมูลท่องเที่ยว", sections.tourism.total_records ?? sections.tourism.items?.length, "รายการ"]);
  }
  if (sections.city_capital?.status === "available") {
    metrics.push(["เทศบาล", sections.city_capital.items?.length ?? 0, "แห่ง"]);
  }

  const cultureItems = sections.culture?.items || [];
  const typeCounts = cultureItems.reduce((accumulator, item) => {
    const label = item.cultural_type || "ไม่ระบุประเภท";
    accumulator[label] = (accumulator[label] || 0) + 1;
    return accumulator;
  }, {});
  const typeRows = Object.entries(typeCounts).sort((a, b) => b[1] - a[1]);
  const maxTypeCount = Math.max(...typeRows.map(([, value]) => value), 1);
  const cultureChart = typeRows.length
    ? `<section class="people-breakdown">
        <header><h4>องค์ประกอบทุนวัฒนธรรม</h4><span>${formatNumber(cultureItems.length)} รายการ</span></header>
        <div class="people-bars">${typeRows.map(([label, value]) => `
          <div class="people-bar-row">
            <span>${escapeHtml(label)}</span>
            <i><b style="width:${Math.max(3, (value / maxTypeCount) * 100).toFixed(1)}%"></b></i>
            <strong>${formatNumber(value)}</strong>
          </div>`).join("")}</div>
      </section>`
    : "";

  wrapper.hidden = metrics.length === 0 && !cultureChart;
  if (wrapper.hidden) return;
  target.innerHTML = `
    <div class="people-stats">${metrics.slice(0, 6).map(([label, value, unit]) => `
      <article><strong>${formatNumber(value)}</strong><span>${escapeHtml(label)}</span><small>${escapeHtml(unit)}</small></article>`).join("")}</div>
    ${cultureChart}`;
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
  const stageLabel = {
    context: "บริบท/ความต้องการ",
    need: "บริบท/ความต้องการ",
    input: "ปัจจัยนำเข้า",
    activity: "กิจกรรม",
    output: "ผลผลิต",
    outcome_impact: "ผลลัพธ์/ผลกระทบ",
  }[breakdown.evidence_stage];
  if (breakdown.kind === "trend") {
    const values = items.map((item) => Number(item.value)).filter(Number.isFinite);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = Math.max(max - min, 1);
    return `
      <section class="clean-breakdown trend-breakdown">
        <h4>${escapeHtml(breakdown.label_th)}${stageLabel ? `<span class="evidence-stage stage-${escapeHtml(breakdown.evidence_stage)}">${escapeHtml(stageLabel)}</span>` : ""}</h4>
        <div class="trend-bars">${items.map((item) => {
          const height = 28 + ((Number(item.value) - min) / span) * 72;
          const displayValue = item.display_value || formatNumber(item.value, 1);
          return `<div title="${escapeHtml(displayValue)}"><small>${escapeHtml(displayValue)}</small><i style="height:${height.toFixed(1)}%"></i><span>${escapeHtml(item.label_th)}</span></div>`;
        }).join("")}</div>
        <strong>ล่าสุด ${escapeHtml(items.at(-1)?.display_value || formatNumber(items.at(-1)?.value, 1))}</strong>
      </section>`;
  }
  const max = Math.max(...items.map((item) => Number(item.value) || 0), 1);
  return `
    <section class="clean-breakdown">
      <h4>${escapeHtml(breakdown.label_th)}${stageLabel ? `<span class="evidence-stage stage-${escapeHtml(breakdown.evidence_stage)}">${escapeHtml(stageLabel)}</span>` : ""}</h4>
      <div class="clean-bars">${items.map((item) => {
        const width = breakdown.kind === "distribution"
          ? Number(item.share_pct || 0)
          : (Number(item.value || 0) / max) * 100;
        const displayValue = item.display_value || (breakdown.kind === "distribution" && item.share_pct !== null && item.share_pct !== undefined
          ? `${formatNumber(item.value)} · ${formatNumber(item.share_pct, 1)}%`
          : formatNumber(item.value, 1));
        return `<div class="clean-bar-row"><span>${escapeHtml(item.label_th)}</span><i><b style="width:${Math.max(3, width).toFixed(1)}%"></b></i><strong>${escapeHtml(displayValue)}</strong></div>`;
      }).join("")}</div>
      ${breakdown.note_th ? `<small>${escapeHtml(breakdown.note_th)}</small>` : ""}
    </section>`;
}

function renderHighlights(highlights) {
  if (!highlights?.length) return "";
  return `<details class="dimension-evidence">
    <summary>ดูตัวอย่างหลักฐาน ${formatNumber(Math.min(highlights.length, 4))} รายการ</summary>
    <div class="dimension-highlights">${highlights.slice(0, 4).map((item) => `
      <article>
        <span>${item.kind === "project" ? "โครงการ" : item.kind === "innovation" ? "นวัตกรรม" : "รายการจากต้นทาง"}</span>
        <strong>${escapeHtml(item.title_th)}</strong>
        ${item.detail_th ? `<p>${escapeHtml(trimText(item.detail_th, 96))}</p>` : ""}
        ${item.meta_th ? `<small>${escapeHtml(item.meta_th)}</small>` : ""}
      </article>`).join("")}</div>
  </details>`;
}

function renderAllData(summary) {
  const dimensions = summary.dimensions || [];
  const missing = summary.missing_dimensions || [];
  document.getElementById("allDataSections").innerHTML = dimensions.length
    ? `${dimensions.map((dimension) => `
        <article class="executive-dimension" data-dimension="${escapeHtml(dimension.key)}">
          <header>
            <span>${escapeHtml(dimension.label_th)}</span>
            <p>${escapeHtml(trimText(dimension.summary_th, 120))}</p>
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
      const sourceUrl = safeExternalUrl(source.url);
      const dates = [
        source.observed_as_of ? `ข้อมูล ณ ${source.observed_as_of}` : "ไม่ระบุวันที่ข้อมูล",
        source.observed_fetched_at ? `ดึง ${formatDate(source.observed_fetched_at)}` : "ไม่ระบุวันที่ดึง",
      ].join(" · ");
      const breakdown = source.record_breakdown
        ? Object.entries(source.record_breakdown).map(([key, value]) => `${key}: ${formatNumber(value)}`).join(" · ")
        : "";
      return `
        <details class="source-row ${escapeHtml(source.status)}">
          <summary>
            <span class="source-mode${apiFirst ? "" : " snapshot"}">${apiFirst ? "เชื่อมตรง" : "ไฟล์ข้อมูล"}</span>
            <span class="source-summary-copy">
              <strong>${escapeHtml(source.name_th)}</strong>
              <small>${escapeHtml(plainLanguage(statusLabel[source.status] || source.status))} · ${escapeHtml(plainLanguage(source.quality_label_th || source.readiness_status || "ไม่ระบุคุณภาพ"))}</small>
            </span>
            <span class="source-count"><strong>${source.records === null || source.records === undefined ? "—" : formatNumber(source.records)}</strong><small>รายการ</small></span>
            <i class="source-chevron" aria-hidden="true">รายละเอียด</i>
          </summary>
          <div class="source-detail">
            <p><span>ระดับข้อมูล</span>${escapeHtml(plainLanguage(source.data_grain_th || "ไม่ระบุ"))}</p>
            ${breakdown ? `<p><span>องค์ประกอบ</span>${escapeHtml(breakdown)}</p>` : ""}
            <p><span>เวลาอ้างอิง</span>${escapeHtml(dates)}</p>
            ${(source.note_th || source.source_note_th) ? `<p class="source-note">${escapeHtml(plainLanguage(source.note_th || source.source_note_th))}</p>` : ""}
            ${sourceUrl ? `<a class="source-link" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noreferrer">เปิดข้อมูลต้นทาง</a>` : ""}
          </div>
        </details>`;
    })
    .join("");
}

function renderDataQuality(summary) {
  const quality = summary.data_quality_overview || {};
  const rules = quality.rules_th || [];
  const totalSources = Number(quality.public_source_count || 0);
  const acceptedSources = Number(quality.accepted_source_count || 0);
  const datedSources = Number(quality.sources_with_explicit_as_of || 0);
  const acceptedPct = totalSources ? (acceptedSources / totalSources) * 100 : 0;
  const datedPct = totalSources ? (datedSources / totalSources) * 100 : 0;
  document.getElementById("dataQualitySummary").innerHTML = `
    <div class="quality-overview-card">
      <div class="quality-ring" style="--quality-progress:${acceptedPct.toFixed(1)}%" aria-label="ผ่านการตรวจ ${formatNumber(acceptedSources)} จาก ${formatNumber(totalSources)} แหล่ง">
        <span><strong>${formatNumber(acceptedSources)}/${formatNumber(totalSources)}</strong><small>ผ่าน</small></span>
      </div>
      <div class="quality-status-copy">
        <span class="quality-status-badge">ใช้สำรวจได้</span>
        <h3>ยังไม่ใช่ตัวเลขทางการ</h3>
        <p>ข้อมูลยังรอตรวจ จึงไม่ควรใช้อ้างอิงเชิงนโยบาย</p>
      </div>
    </div>
    <div class="quality-mini-stats">
      <article><strong>${formatNumber(quality.candidate_or_review_source_count ?? 0)}</strong><span>แหล่งที่รอตรวจรับรอง</span><small>รอตรวจ</small></article>
      <article><strong>${formatNumber(datedSources)}/${formatNumber(totalSources)}</strong><span>มีวันที่ข้อมูลชัดเจน</span><i><b style="width:${datedPct.toFixed(1)}%"></b></i></article>
      <article><strong>${quality.latest_observed_fetch ? escapeHtml(formatDate(quality.latest_observed_fetch)) : "—"}</strong><span>ดึงข้อมูลล่าสุด · ไม่ใช่วันที่ของข้อมูลเสมอไป</span></article>
    </div>
    ${rules.length ? `<details class="quality-rules"><summary>หลักการอ่านข้อมูล ${formatNumber(rules.length)} ข้อ</summary><ul>${rules.map((rule) => `<li>${escapeHtml(plainLanguage(rule))}</li>`).join("")}</ul></details>` : ""}`;
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
  renderProvinceOverview(summary);
  renderPeopleAreaOverview(summary, null);
  renderResearchPortfolio(summary);
  renderAllData(summary);
  renderDataQuality(summary);
  renderSources(summary);
  // Load the briefing right away for the regular province dashboard: the
  // overview carries briefing-backed sections, not just the projects tabs.
  ensurePortfolioLoaded();
  if (state.mapMode === "disaster") renderDisaster();
  document.getElementById("panelUpdated").textContent = `อัปเดตชุดสรุป ${formatDate(summary.generated_at)}`;
  document.getElementById("provinceApiLink").href = `/api/public/v1/provinces/${province.province_code}/briefing`;
  document.getElementById("fullProvinceLink").href = `/province/${province.province_code}`;
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
    populateProjectFilters(briefing.sections.project_master);
    renderAreaProjects(briefing.sections.project_master);
    renderInnovations(briefing.sections.innovation);
    renderRequirements(briefing.sections.requirements);
    renderSraArea(briefing.sections.sra);
    renderTourism(briefing.sections.tourism);
    renderCulture(briefing.sections.culture);
    renderPoverty(briefing.sections.pppconnext);
    renderCityCapital(briefing.sections.city_capital);
    renderHousing(briefing.sections.housing);
    renderPeopleAreaOverview(state.currentSummary, briefing);
    renderSources({ source_coverage: briefing.source_coverage || [] });
    const hasProjects = ["project_master", "innovation", "requirements"].some(
      (key) => briefing.sections[key]?.status === "available",
    );
    const hasPortfolio = ["project_master", "area_based", "sra", "pppconnext", "tourism", "culture", "city_capital", "housing"].some(
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
  if (provinceMeta.region && state.selectedRegion !== provinceMeta.region) {
    state.selectedRegion = provinceMeta.region;
    document.getElementById("backToCountry").hidden = false;
    setPrompt(`${provinceMeta.region}: คลิกจังหวัดเพื่อเปิดข้อมูล`, "หรือกด ทุกภาค เพื่อกลับมุมมองประเทศ");
    applyFillForLevel();
    renderLegend();
    applyRegionFocus();
  }

  const previousCode = state.selectedCode;
  setFeatureSelection(normalized);
  state.selectedCode = normalized;
  if (previousCode && previousCode !== normalized && state.mapLoaded) {
    state.map.setFeatureState({ source: "provinces", id: previousCode }, { selected: false });
    state.map.setFeatureState({ source: "provinces", id: normalized }, { selected: true });
  }
  updateLabelVisibility();
  if (state.mapMode === "f4") {
    state.f4Province = null;
    state.f4BoardCollapsed = false;
    state.f4CountryTab = "overview";
    state.f4ListContextKey = "";
    state.f4InnovationQuery = "";
    state.f4PolicyQuery = "";
    document.getElementById("f4InnovationSearch").value = "";
    document.getElementById("f4PolicySearch").value = "";
    document.getElementById("provincePanel").classList.remove("is-open");
    document.getElementById("provincePanel").setAttribute("aria-hidden", "true");
    document.body.classList.remove("panel-open");
    document.getElementById("showF4Country").hidden = true;
    document.getElementById("f4CountryPanel").hidden = false;
    document.querySelector(".picker-copy strong").textContent = provinceMeta.province_name_th;
    document.getElementById("provinceSelect").value = normalized;
    if (moveMap) fitProvince(provinceMeta);

    const url = new URL(window.location.href);
    url.searchParams.set("province", normalized);
    url.searchParams.set("mode", "f4");
    url.searchParams.delete("view");
    window.history.replaceState({}, "", url);

    if (!state.f4Overview) await loadF4Overview();
    await loadF4ProvinceOverview(normalized);
    return;
  }
  openPanelLoading(provinceMeta);
  if (moveMap) fitProvince(provinceMeta);

  const url = new URL(window.location.href);
  url.searchParams.set("province", normalized);
  if (state.mapMode === "projects") url.searchParams.delete("mode");
  else url.searchParams.set("mode", state.mapMode);
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

function closePanel(refitMap = true) {
  state.requestToken += 1;
  closeStationHistoryModal();
  destroyDisasterCharts();
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
  if (state.mapMode === "f4") {
    if (state.f4BoardCollapsed) {
      document.getElementById("f4CountryPanel").hidden = true;
      document.getElementById("showF4Country").hidden = false;
    } else {
      renderF4CountryPanel();
    }
  }
  const url = new URL(window.location.href);
  url.searchParams.delete("province");
  url.searchParams.delete("view");
  window.history.replaceState({}, "", url);
  // Ease back to the region overview so opening and closing a province always
  // lands on the same stable view instead of wherever the last fit left off.
  if (refitMap && state.selectedRegion) {
    fitRegionBounds(state.regions[state.selectedRegion], 600);
  } else if (refitMap && state.mapMode === "f4") {
    lockCountryView(true);
  }
}

function toggleCulturalPoints() {
  if (!state.mapLoaded) return;
  state.pointsVisible = !state.pointsVisible;
  const visibility = state.pointsVisible ? "visible" : "none";
  ["cultural-clusters", "cultural-point"].forEach((layer) => state.map.setLayoutProperty(layer, "visibility", visibility));
  document.getElementById("togglePoints").setAttribute("aria-pressed", String(state.pointsVisible));
}

function bindEvents() {
  document.getElementById("provinceSelect").addEventListener("change", (event) => {
    if (event.target.value) selectProvince(event.target.value, true);
  });
  document.getElementById("closePanel").addEventListener("click", () => closePanel());
  document.getElementById("backToCountry").addEventListener("click", backToCountry);
  document.getElementById("togglePoints").addEventListener("click", toggleCulturalPoints);
  document.getElementById("closeF4Country").addEventListener("click", () => {
    collapseF4Board();
  });
  document.getElementById("showF4Country").addEventListener("click", showF4Board);
  document.querySelectorAll("[data-f4-tab]").forEach((button) => {
    button.addEventListener("click", () => setF4CountryTab(button.dataset.f4Tab));
  });
  document.getElementById("f4InnovationSearch").addEventListener("input", (event) => {
    state.f4InnovationQuery = event.target.value;
    rerenderF4InnovationList();
  });
  document.getElementById("f4PolicySearch").addEventListener("input", (event) => {
    state.f4PolicyQuery = event.target.value;
    rerenderF4PolicyList();
  });
  document.querySelectorAll("[data-map-mode]").forEach((button) => {
    button.addEventListener("click", () => setMapMode(button.dataset.mapMode));
  });
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
    if (state.currentBriefing) renderAreaProjects(state.currentBriefing.sections.project_master);
  });
  document.getElementById("projectYearFilter").addEventListener("change", (event) => {
    state.projectYear = event.target.value;
    if (state.currentBriefing) renderAreaProjects(state.currentBriefing.sections.project_master);
  });
  document.getElementById("projectDistrictFilter").addEventListener("change", (event) => {
    state.projectDistrict = event.target.value;
    if (state.currentBriefing) renderAreaProjects(state.currentBriefing.sections.project_master);
  });
  document.getElementById("loadMoreCulture").addEventListener("click", () => {
    state.cultureVisible += 12;
    if (state.currentBriefing) renderCulture(state.currentBriefing.sections.culture);
  });
  document.addEventListener("click", (event) => {
    const historyButton = event.target.closest("[data-disaster-history]");
    if (!historyButton) return;
    openStationHistoryModal({
      stationId: historyButton.dataset.stationId,
      stationName: historyButton.dataset.stationName,
      metric: historyButton.dataset.metric,
    });
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!document.getElementById("stationHistoryModal")?.hidden) closeStationHistoryModal();
    else if (state.mapMode === "f4" && (state.selectedRegion || state.selectedCode)) resetF4ToCountryOverview();
    else if (state.selectedCode) closePanel();
    else if (state.selectedRegion) backToCountry();
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
    fitBoundsOptions: { padding: countryPadding() },
    minZoom: 2,
    maxZoom: 13,
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
    map.addLayer({
      id: "province-base",
      type: "fill",
      source: "provinces",
      paint: {
        "fill-color": buildFillExpression(state.mapMode),
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
          "#141d18",
          "#2c4237",
        ],
        "line-width": [
          "case",
          ["boolean", ["feature-state", "selected"], false],
          2.6,
          1.8,
        ],
        "line-opacity": [
          "case",
          ["boolean", ["feature-state", "selected"], false],
          1,
          ["boolean", ["feature-state", "hover"], false],
          0.9,
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
      const province = code ? provinceByCode(code) : null;
      if (!province) return;

      if (!state.selectedRegion) {
        // Country view is region-only: no per-province hover or popup.
        if (state.hoveredCode) {
          map.setFeatureState({ source: "provinces", id: state.hoveredCode }, { hover: false });
          state.hoveredCode = null;
        }
        setHoveredRegion(province.region);
        const summary = regionSummary(state.mapMode, province.region);
        const config = MAP_MODES[state.mapMode];
        const hasRegionData = state.mapMode === "sra" ? summary.scopeCount : summary.withData;
        const detail = hasRegionData
          ? `${escapeHtml(config.summarize(summary))}${state.mapMode === "sra" ? "" : ` · มีข้อมูล ${formatNumber(summary.withData)} จังหวัด`}`
          : "ยังไม่มีข้อมูลในมุมมองนี้";
        state.hoverPopup
          .setLngLat(event.lngLat)
          .setHTML(`<strong>${escapeHtml(province.region)}</strong><span>${detail}</span><small>คลิกเพื่อซูมเข้าภาค</small>`)
          .addTo(map);
        return;
      }

      setHoveredRegion(null);
      if (code === state.hoveredCode) return;
      if (state.hoveredCode) map.setFeatureState({ source: "provinces", id: state.hoveredCode }, { hover: false });
      state.hoveredCode = code;
      map.setFeatureState({ source: "provinces", id: code }, { hover: true });
      const config = MAP_MODES[state.mapMode];
      const value = config.value(province);
      const valueLine = value === null
        ? (config.noDataLabel ? config.noDataLabel(province) : config.zeroLabel)
        : config.format(value);
      const inActiveRegion = province.region === state.selectedRegion;
      const hint = inActiveRegion
        ? (code === state.selectedCode ? "คลิกอีกครั้งเพื่อยกเลิก" : "คลิกเพื่อเปิดข้อมูล")
        : `คลิกเพื่อไป${escapeHtml(province.region)}`;
      state.hoverPopup
        .setLngLat(event.lngLat)
        .setHTML(`<strong>${escapeHtml(province.province_name_th)}</strong><span>${escapeHtml(valueLine)}</span><small>${hint}</small>`)
        .addTo(map);
      updateLabelVisibility();
    });
    map.on("mouseleave", "province-base", () => {
      map.getCanvas().style.cursor = "";
      if (state.hoveredCode) map.setFeatureState({ source: "provinces", id: state.hoveredCode }, { hover: false });
      state.hoveredCode = null;
      setHoveredRegion(null);
      state.hoverPopup?.remove();
      updateLabelVisibility();
    });
    map.on("click", (event) => {
      const culturalHits = map.queryRenderedFeatures(event.point, {
        layers: ["cultural-clusters", "cultural-point"],
      });
      if (culturalHits.length) return;
      const features = map.queryRenderedFeatures(event.point, { layers: ["province-base"] });
      if (!features.length) {
        if (state.selectedCode) closePanel();
        return;
      }
      const code = features[0]?.properties?.province_code;
      const province = code ? provinceByCode(code) : null;
      if (!province) return;
      if (!state.selectedRegion || state.selectedRegion !== province.region) {
        selectRegion(province.region);
        return;
      }
      if (code === state.selectedCode) {
        closePanel();
        return;
      }
      selectProvince(code, true);
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
    addProvinceLabels();
    addRegionMarkers();
    updateRegionMarkerColors();
    applyRegionFocus();
    lockCountryView();
    if (state.selectedCode) {
      map.setFeatureState({ source: "provinces", id: state.selectedCode }, { selected: true });
      fitProvince(provinceByCode(state.selectedCode));
    }
  });

  // Container resizes (window resize, mobile URL bar show/hide) re-fit the
  // locked country view so the whole map always matches the screen.
  map.on("resize", () => {
    if (!state.mapLoaded || state.selectedRegion || state.selectedCode) return;
    lockCountryView();
  });

  // Pinching/scrolling out to country scale while inside a region would leave
  // the map in a half-region half-country state — treat it as "back to all
  // regions" so the view and the interactions always agree.
  map.on("zoomend", () => {
    if (!state.mapLoaded || !state.selectedRegion || state.selectedCode) return;
    if (state.pendingLock) return;
    if (state.countryZoom !== null && map.getZoom() <= state.countryZoom + 0.25) {
      backToCountry();
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
    renderMapOverview();
    computeRegions();
    const params = new URLSearchParams(window.location.search);
    const initialMode = params.get("mode");
    if (initialMode && MAP_MODES[initialMode]) state.mapMode = initialMode;
    renderLegend();
    bindEvents();
    document.querySelectorAll("[data-map-mode]").forEach((button) => {
      button.classList.toggle("active", button.dataset.mapMode === state.mapMode);
    });
    initMap();

    if (state.mapMode === "f4") loadF4Overview();
    const initialCode = params.get("province");
    if (initialCode && provinceByCode(initialCode)) selectProvince(initialCode, false);
  } catch (error) {
    console.error(error);
    document.getElementById("mapFallback").hidden = false;
    showToast("โหลดข้อมูลสาธารณะไม่สำเร็จ");
  }
}

loadDashboard();
