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
};

const priorityProvinceCodes = new Set(["10", "20", "30", "34", "40", "50", "65", "71", "80", "83", "84", "90"]);

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
  return {
    color: [
      "case",
      ["boolean", ["feature-state", "selected"], false],
      "#f4cf72",
      ["boolean", ["feature-state", "hover"], false],
      "#b9ffd8",
      "#1d4939",
    ],
    height: [
      "+",
      4200,
      ["case", ["boolean", ["feature-state", "selected"], false], 7200, 0],
    ],
  };
}

function updateLabelVisibility() {
  if (!state.mapLoaded) return;
  const showAll = state.map.getZoom() >= 5.75;
  state.labelMarkers.forEach(({ element, code }) => {
    const hidden = !showAll && !priorityProvinceCodes.has(code) && code !== state.selectedCode;
    element.classList.toggle("is-secondary", hidden);
    element.classList.toggle("is-active", code === state.selectedCode);
  });
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
    state.labelMarkers.push({ marker, element, code: province.province_code });
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
    padding: isMobile ? { top: 80, right: 20, bottom: 340, left: 20 } : { top: 80, right: 600, bottom: 60, left: 60 },
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
  const prioritized = [...(section.items || [])]
    .sort((a, b) => Number(b.risk_status_code || 0) - Number(a.risk_status_code || 0))
    .slice(0, 8);
  document.getElementById("cultureItems").innerHTML = prioritized
    .map(
      (item) => `
        <article class="data-card culture-card">
          ${item.image_url ? `<img src="${escapeHtml(item.image_url)}" alt="" loading="lazy" referrerpolicy="no-referrer" />` : ""}
          <div>
            <div class="record-kicker"><span>risk status ${escapeHtml(item.risk_status_code ?? "ไม่ระบุ")}</span><span>${escapeHtml(item.category || "ไม่ระบุหมวด")}</span></div>
            <h3>${escapeHtml(item.title_th || "ไม่ระบุชื่อ")}</h3>
            <p>${escapeHtml(trimText(item.risk_reason || item.history || "ต้นทางไม่ได้ระบุเหตุผลความเสี่ยง", 180))}</p>
            <footer><span>${escapeHtml([item.tambon, item.amphoe].filter(Boolean).join(" · ") || "ไม่ระบุพื้นที่ย่อย")}</span><a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">ต้นทาง ↗</a></footer>
          </div>
        </article>`,
    )
    .join("");
}

function renderValueRows(rows) {
  return rows
    .slice(0, 2)
    .map(
      (row) => `
        <div class="raw-value-row">
          ${Object.entries(row.values || {})
            .slice(0, 8)
            .map(([key, value]) => `<span><small>${escapeHtml(key)}</small><strong>${escapeHtml(value)}</strong></span>`)
            .join("")}
        </div>`,
    )
    .join("");
}

function renderAllData(briefing) {
  const { sra, housing, culture, area_based: area, innovation } = briefing.sections;
  const sraContent = sra.status === "available"
    ? sra.items.map((item) => `<span><small>${escapeHtml(item.metric_key)}</small><strong>${formatNumber(item.value, 2)} ${escapeHtml(item.unit || "")}</strong></span>`).join("")
    : '<p>API ปี 2569 ไม่มีจังหวัดนี้ใน province registry — ไม่แทนค่าด้วย 0</p>';
  const housingGroups = (housing.resource_groups || [])
    .map(
      (group) => `
        <details class="resource-detail">
          <summary><span>${escapeHtml(group.resource_name)}</span><small>${escapeHtml(group.dataset_title || group.dataset_key || "CKAN resource")}</small></summary>
          <div class="resource-body">
            ${renderValueRows(group.rows || [])}
            <a href="${escapeHtml(group.source_url)}" target="_blank" rel="noreferrer">เปิด CSV ต้นทาง ↗</a>
          </div>
        </details>`,
    )
    .join("");
  document.getElementById("allDataSections").innerHTML = `
    <details class="dataset-detail" open>
      <summary><span>ที่อยู่อาศัย</span><small>ทุก resource ที่ผูกจังหวัดได้</small></summary>
      <div class="dataset-body">${housingGroups || "<p>ต้นทางไม่มีข้อมูลจังหวัดนี้</p>"}</div>
    </details>
    <details class="dataset-detail">
      <summary><span>SRA-DSS</span><small>ค่ารายมิติจาก aggregate API</small></summary>
      <div class="dataset-body sra-values">${sraContent}</div>
    </details>
    <details class="dataset-detail">
      <summary><span>ทะเบียนรายการทั้งหมด</span><small>โครงการ นวัตกรรม และทุนวัฒนธรรม</small></summary>
      <div class="dataset-body registry-links">
        <p>รายการ Area-Based, AppTech และ Cultural Map ถูกส่งกลับครบใน Gold JSON เดียวกัน</p>
        <span>โครงการในพื้นที่ <strong>${formatNumber(area.total_records)}</strong></span>
        <span>นวัตกรรม <strong>${formatNumber(innovation.total_records)}</strong></span>
        <span>ทุนวัฒนธรรม <strong>${formatNumber(culture.total_records)}</strong></span>
      </div>
    </details>`;
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
  document.getElementById("panelLoading").hidden = true;
  document.getElementById("panelError").hidden = true;
  document.getElementById("panelContent").hidden = false;
  document.getElementById("provinceMeta").textContent = `${province.region} · รหัส ${province.province_code}`;
  document.getElementById("provinceName").textContent = province.province_name_th;
  document.getElementById("provinceEnglish").textContent = province.province_name_en;
  renderExecutiveSignals(briefing);
  renderAreaProjects(briefing.sections.area_based);
  renderInnovations(briefing.sections.innovation);
  renderCulture(briefing.sections.culture);
  renderAllData(briefing);
  renderSources(briefing);
  document.getElementById("panelUpdated").textContent = `สร้าง Gold projection ${formatDate(briefing.generated_at)}`;
  document.getElementById("provinceApiLink").href = `/api/public/v1/provinces/${province.province_code}/briefing`;
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
    center: [101.15, 13.35],
    zoom: 4.6,
    pitch: 48,
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
    center: [101.15, 13.35],
    zoom: 4.6,
    pitch: 48,
    bearing: -8,
    minZoom: 3.75,
    maxZoom: 13,
    maxBounds: [[94.5, 3.5], [109.4, 23]],
    antialias: true,
    attributionControl: false,
  });
  state.map = map;
  map.addControl(new window.maplibregl.AttributionControl({ compact: true, customAttribution: "ขอบเขตจังหวัด ปภ. · Cultural Map Thailand" }), "bottom-right");
  map.on("load", () => {
    state.mapLoaded = true;
    map.addSource("provinces", { type: "geojson", data: state.boundaries, promoteId: "province_code" });
    const paint = metricPaint();
    map.addLayer({
      id: "province-extrusion",
      type: "fill-extrusion",
      source: "provinces",
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

    map.on("mousemove", "province-extrusion", (event) => {
      map.getCanvas().style.cursor = "pointer";
      const code = event.features?.[0]?.properties?.province_code;
      if (!code || code === state.hoveredCode) return;
      if (state.hoveredCode) map.setFeatureState({ source: "provinces", id: state.hoveredCode }, { hover: false });
      state.hoveredCode = code;
      map.setFeatureState({ source: "provinces", id: code }, { hover: true });
    });
    map.on("mouseleave", "province-extrusion", () => {
      map.getCanvas().style.cursor = "";
      if (state.hoveredCode) map.setFeatureState({ source: "provinces", id: state.hoveredCode }, { hover: false });
      state.hoveredCode = null;
    });
    map.on("click", "province-extrusion", (event) => {
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
