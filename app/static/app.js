const state = {
  catalog: null,
  boundaries: null,
  points: null,
  map: null,
  mapLoaded: false,
  activeMetric: "evidence_source_count",
  rankMetric: "evidence_source_count",
  activeProvince: null,
  hoveredProvince: null,
  scenario: new Map(),
};

const metricMeta = {
  evidence_source_count: {
    label: "ความครอบคลุมหลักฐาน",
    unit: "sources",
    color: "#78efb1",
    dark: "#173b2e",
    caveat: "ความสูงแสดงจำนวน source ที่มีหลักฐานในจังหวัด ไม่ใช่ระดับความต้องการงบ",
  },
  sra_overall_score: {
    label: "SRA overall score",
    unit: "source_score",
    color: "#ff8066",
    dark: "#49271f",
    caveat: "แสดง source_score ปี 2569 ตามนิยาม provisional ของ SRA-DSS ไม่ใช่ดัชนีที่ผ่านการรับรอง",
  },
  innovation_records: {
    label: "ผลงาน AppTech ที่ระบุพื้นที่",
    unit: "records",
    color: "#b59cff",
    dark: "#332b4c",
    caveat: "แสดงจำนวนทะเบียนนวัตกรรม candidate ที่ระบุจังหวัด ไม่ใช่มูลค่าผลกระทบหรือจำนวนผู้ได้รับประโยชน์",
  },
  housing_observations: {
    label: "ข้อมูล Thai Housing Portal",
    unit: "observations",
    color: "#78cfff",
    dark: "#193847",
    caveat: "แสดงจำนวน observation ทางเทคนิคจาก CKAN หลาย resource ห้ามตีความเป็นจำนวนครัวเรือน",
  },
  cultural_records: {
    label: "จุดวัฒนธรรมที่มีพิกัด",
    unit: "records",
    color: "#ffd166",
    dark: "#493b1e",
    caveat: "แสดงทะเบียนวัฒนธรรมที่มีพิกัดและผ่าน structural validation สถานะยังเป็น candidate",
  },
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
  if (value === null || value === undefined || value === "") return "ไม่ระบุ";
  const options = compact
    ? { notation: "compact", maximumFractionDigits: 1 }
    : { maximumFractionDigits: 2 };
  return new Intl.NumberFormat("th-TH", options).format(Number(value));
}

function formatMetricValue(province, metric) {
  const value = province?.[metric];
  if (value === null || value === undefined || value === 0) {
    return { value: "ไม่มีข้อมูล", unit: metricMeta[metric]?.unit ?? "" };
  }
  if (metric === "evidence_source_count") return { value: `${value}/5`, unit: "sources" };
  if (metric === "sra_overall_score") return { value: Number(value).toFixed(2), unit: "source_score" };
  return { value: number(value, value >= 10000), unit: metricMeta[metric]?.unit ?? "records" };
}

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2600);
}

function provinceByCode(code) {
  return state.catalog?.provinces.find((row) => row.province_code === String(code).padStart(2, "0"));
}

function renderOverview() {
  const { summary, generated_at: generatedAt } = state.catalog;
  const stats = [
    [summary.public_sources, "แหล่งสาธารณะ"],
    [summary.provinces_with_evidence, "จังหวัดมีหลักฐาน"],
    [summary.geocoded_cultural_points, "จุดบน WebGL"],
  ];
  document.getElementById("heroStats").innerHTML = stats
    .map(([value, label]) => `<article><strong>${number(value, value > 9999)}</strong><span>${label}</span></article>`)
    .join("");
  document.getElementById("pointCount").textContent = number(summary.geocoded_cultural_points, true);
  document.getElementById("downloadPointCopy").textContent = `${number(summary.geocoded_cultural_points)} จุดพร้อมพิกัด · GeoJSON`;
  document.getElementById("sourceTotal").textContent = `${summary.public_sources} sources`;
  document.getElementById("footerUpdated").textContent = new Intl.DateTimeFormat("th-TH", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(generatedAt));
}

function renderSources() {
  document.getElementById("sourceGrid").innerHTML = state.catalog.sources
    .map(
      (source) => `
        <article class="source-card">
          <span class="source-index">${String(source.ordinal).padStart(2, "0")}</span>
          <div>
            <strong>${escapeHtml(source.name_th)}</strong>
            <p>${escapeHtml(source.acquisition_mode.replaceAll("_", " "))} · ${number(source.expected_record_count, true)} reference records · ${escapeHtml(source.readiness_status)}</p>
          </div>
          <a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer" aria-label="เปิดต้นทาง ${escapeHtml(source.name_th)}">↗</a>
        </article>`,
    )
    .join("");
}

function renderRanking() {
  const query = document.getElementById("provinceSearch").value.trim().toLocaleLowerCase("th");
  const metric = state.rankMetric;
  const rows = state.catalog.provinces
    .filter((province) => province.evidence_source_count > 0)
    .filter((province) => metric !== "sra_overall_score" || province.sra_overall_score !== null)
    .filter(
      (province) =>
        !query ||
        province.province_name_th.toLocaleLowerCase("th").includes(query) ||
        province.province_name_en.toLowerCase().includes(query),
    )
    .sort((a, b) => (Number(b[metric]) || 0) - (Number(a[metric]) || 0) || a.province_name_th.localeCompare(b.province_name_th, "th"));

  document.getElementById("rankingCount").textContent = `${number(rows.length)} จังหวัด`;
  document.getElementById("provinceRanking").innerHTML = rows
    .map((province, index) => {
      const formatted = formatMetricValue(province, metric);
      const dots = Array.from({ length: 5 }, (_, dot) => `<i class="${dot < province.evidence_source_count ? "on" : ""}"></i>`).join("");
      const isAdded = state.scenario.has(province.province_code);
      return `
        <article class="province-row" data-code="${province.province_code}">
          <button class="province-name" type="button" data-view-province="${province.province_code}">
            <span class="rank-number">${String(index + 1).padStart(2, "0")}</span>
            <span><strong>${escapeHtml(province.province_name_th)}</strong><small>${escapeHtml(province.region)}</small></span>
          </button>
          <span class="coverage-dots" aria-label="${province.evidence_source_count} จาก 5 แหล่ง">${dots}</span>
          <span class="rank-value"><strong>${escapeHtml(formatted.value)}</strong><span>${escapeHtml(formatted.unit)}</span></span>
          <button class="row-add ${isAdded ? "added" : ""}" type="button" data-add-province="${province.province_code}">${isAdded ? "เลือกแล้ว" : "+ เพิ่ม"}</button>
        </article>`;
    })
    .join("");

  document.querySelectorAll("[data-view-province]").forEach((button) => {
    button.addEventListener("click", () => selectProvince(button.dataset.viewProvince, true));
  });
  document.querySelectorAll("[data-add-province]").forEach((button) => {
    button.addEventListener("click", () => addProvinceToScenario(button.dataset.addProvince));
  });
}

function renderProvincePeek(province) {
  const peek = document.getElementById("provincePeek");
  state.activeProvince = province || null;
  if (!province) {
    document.getElementById("peekProvince").textContent = "เลือกจังหวัดบนแผนที่";
    document.getElementById("peekRegion").textContent = "คลิกพื้นที่เพื่อดูสัญญาณที่มีอยู่";
    document.getElementById("peekCoverage").textContent = "—";
    document.getElementById("peekSignals").innerHTML = "";
    document.getElementById("addProvince").disabled = true;
    return;
  }

  peek.classList.remove("is-hidden");
  document.getElementById("peekProvince").textContent = province.province_name_th;
  document.getElementById("peekRegion").textContent = `${province.region} · รหัส ${province.province_code}`;
  document.getElementById("peekCoverage").textContent = `${province.evidence_source_count}/5`;
  const signals = [
    ["SRA overall", province.sra_overall_score === null ? "ไม่มีข้อมูล" : Number(province.sra_overall_score).toFixed(2)],
    ["Area-Based", number(province.area_based_participant_records)],
    ["AppTech", number(province.innovation_records)],
    ["Culture points", number(province.cultural_records)],
    ["Housing rows", number(province.housing_observations)],
  ];
  document.getElementById("peekSignals").innerHTML = signals
    .map(([label, value]) => `<article><span>${label}</span><strong>${value}</strong></article>`)
    .join("");
  const addButton = document.getElementById("addProvince");
  addButton.disabled = false;
  addButton.innerHTML = state.scenario.has(province.province_code)
    ? `อยู่ในฉากทัศน์แล้ว <span>✓</span>`
    : `เพิ่มในฉากทัศน์งบ <span>＋</span>`;
}

function selectProvince(code, fly = false) {
  const province = provinceByCode(code);
  if (!province) return;

  if (state.mapLoaded && state.activeProvince) {
    state.map.setFeatureState(
      { source: "provinces", id: state.activeProvince.province_code },
      { selected: false },
    );
  }
  renderProvincePeek(province);
  if (state.mapLoaded) {
    state.map.setFeatureState({ source: "provinces", id: province.province_code }, { selected: true });
    if (fly && province.centroid?.every((value) => Number.isFinite(Number(value)))) {
      state.map.flyTo({ center: province.centroid, zoom: 7.1, pitch: 52, duration: 1000 });
    }
  }
}

function metricPaint(metric) {
  const meta = metricMeta[metric];
  const indexProperty = `idx_${metric}`;
  return {
    color: [
      "interpolate",
      ["linear"],
      ["to-number", ["get", indexProperty], 0],
      0,
      "#15241f",
      0.02,
      meta.dark,
      0.5,
      meta.color,
      1,
      "#e9fff3",
    ],
    height: [
      "interpolate",
      ["linear"],
      ["to-number", ["get", indexProperty], 0],
      0,
      500,
      0.01,
      3500,
      1,
      62000,
    ],
  };
}

function setActiveMetric(metric) {
  if (!metricMeta[metric]) return;
  state.activeMetric = metric;
  document.querySelectorAll("[data-metric]").forEach((button) => button.classList.toggle("active", button.dataset.metric === metric));
  document.getElementById("activeMetricLabel").textContent = metricMeta[metric].label;
  document.getElementById("metricCaveat").textContent = metricMeta[metric].caveat;
  if (!state.mapLoaded) return;
  const paint = metricPaint(metric);
  state.map.setPaintProperty("province-extrusion", "fill-extrusion-color", paint.color);
  state.map.setPaintProperty("province-extrusion", "fill-extrusion-height", paint.height);
}

function initMap() {
  const container = document.getElementById("map");
  if (!window.maplibregl) {
    container.innerHTML = '<div class="map-fallback"><strong>ไม่สามารถโหลด WebGL map ได้</strong><p>ตารางและไฟล์ Public Data ด้านล่างยังใช้งานได้ครบ</p></div>';
    return;
  }

  const map = new window.maplibregl.Map({
    container: "map",
    style: {
      version: 8,
      sources: {},
      layers: [{ id: "background", type: "background", paint: { "background-color": "#07110f" } }],
    },
    center: [101.15, 13.4],
    zoom: 4.55,
    pitch: 43,
    bearing: -8,
    minZoom: 3.8,
    maxZoom: 13,
    maxBounds: [[94.5, 3.5], [109.4, 23]],
    antialias: true,
    attributionControl: false,
  });
  state.map = map;
  map.addControl(new window.maplibregl.AttributionControl({ compact: true, customAttribution: "ขอบเขตจังหวัด: ปภ. · Cultural Map Thailand" }), "bottom-right");
  map.addControl(new window.maplibregl.NavigationControl({ showCompass: true, visualizePitch: true }), "bottom-right");

  map.on("load", () => {
    state.mapLoaded = true;
    map.addSource("provinces", { type: "geojson", data: state.boundaries, promoteId: "province_code" });
    const paint = metricPaint(state.activeMetric);
    map.addLayer({
      id: "province-extrusion",
      type: "fill-extrusion",
      source: "provinces",
      paint: {
        "fill-extrusion-color": paint.color,
        "fill-extrusion-height": paint.height,
        "fill-extrusion-base": 0,
        "fill-extrusion-opacity": 0.78,
        "fill-extrusion-vertical-gradient": false,
      },
    });
    map.addLayer({
      id: "province-outline",
      type: "line",
      source: "provinces",
      paint: { "line-color": "rgba(219, 255, 239, 0.68)", "line-width": 0.75, "line-opacity": 0.6 },
    });

    map.addSource("cultural-points", {
      type: "geojson",
      data: state.points,
      cluster: true,
      clusterRadius: 45,
      clusterMaxZoom: 10,
    });
    map.addLayer({
      id: "cultural-clusters",
      type: "circle",
      source: "cultural-points",
      filter: ["has", "point_count"],
      paint: {
        "circle-color": "#ffd166",
        "circle-radius": ["interpolate", ["linear"], ["get", "point_count"], 2, 7, 100, 16, 800, 26],
        "circle-stroke-width": 2,
        "circle-stroke-color": "rgba(7, 17, 15, 0.8)",
        "circle-opacity": 0.9,
      },
    });
    map.addLayer({
      id: "cultural-point",
      type: "circle",
      source: "cultural-points",
      filter: ["!", ["has", "point_count"]],
      paint: {
        "circle-color": "#ffd166",
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 2, 10, 5],
        "circle-stroke-width": 1,
        "circle-stroke-color": "#08130f",
        "circle-opacity": 0.84,
      },
    });

    map.on("mousemove", "province-extrusion", (event) => {
      map.getCanvas().style.cursor = "pointer";
      const code = event.features?.[0]?.properties?.province_code;
      if (!code || code === state.hoveredProvince) return;
      if (state.hoveredProvince) map.setFeatureState({ source: "provinces", id: state.hoveredProvince }, { hover: false });
      state.hoveredProvince = code;
      map.setFeatureState({ source: "provinces", id: code }, { hover: true });
    });
    map.on("mouseleave", "province-extrusion", () => {
      map.getCanvas().style.cursor = "";
      if (state.hoveredProvince) map.setFeatureState({ source: "provinces", id: state.hoveredProvince }, { hover: false });
      state.hoveredProvince = null;
    });
    map.on("click", "province-extrusion", (event) => {
      const code = event.features?.[0]?.properties?.province_code;
      if (code) selectProvince(code, false);
    });
    map.on("click", "cultural-clusters", async (event) => {
      const feature = event.features?.[0];
      if (!feature) return;
      const zoom = await map.getSource("cultural-points").getClusterExpansionZoom(feature.properties.cluster_id);
      map.easeTo({ center: feature.geometry.coordinates, zoom });
    });
    map.on("click", "cultural-point", (event) => {
      const feature = event.features?.[0];
      if (!feature) return;
      const props = feature.properties;
      new window.maplibregl.Popup({ offset: 8, maxWidth: "280px" })
        .setLngLat(feature.geometry.coordinates)
        .setHTML(`<strong>${escapeHtml(props.title)}</strong><br><span>${escapeHtml(props.category)} · ${escapeHtml(props.province_name_th)}</span><br><a href="${escapeHtml(props.source_url)}" target="_blank" rel="noreferrer">เปิดข้อมูลต้นทาง ↗</a>`)
        .addTo(map);
    });
  });

  map.on("error", (event) => {
    if (event?.error) console.warn("MapLibre:", event.error.message);
  });
}

function rebalanceScenario() {
  const size = state.scenario.size;
  if (!size) return;
  const base = Math.floor((100 / size) * 10) / 10;
  let used = 0;
  [...state.scenario.keys()].forEach((code, index) => {
    const weight = index === size - 1 ? Math.round((100 - used) * 10) / 10 : base;
    state.scenario.set(code, weight);
    used += weight;
  });
}

function addProvinceToScenario(code) {
  const province = provinceByCode(code);
  if (!province) return;
  if (!state.scenario.has(code)) {
    state.scenario.set(code, 0);
    rebalanceScenario();
    showToast(`เพิ่ม ${province.province_name_th} ในฉากทัศน์แล้ว`);
  } else {
    showToast(`${province.province_name_th} อยู่ในฉากทัศน์แล้ว`);
  }
  renderScenario();
  renderRanking();
  renderProvincePeek(state.activeProvince);
}

function removeProvinceFromScenario(code) {
  state.scenario.delete(code);
  rebalanceScenario();
  renderScenario();
  renderRanking();
  renderProvincePeek(state.activeProvince);
}

function budgetTotal() {
  const value = Number(document.getElementById("budgetTotal").value);
  return Number.isFinite(value) && value > 0 ? Math.min(value, 1000000) : 0;
}

function renderScenario() {
  const list = document.getElementById("scenarioList");
  const entries = [...state.scenario.entries()].map(([code, weight]) => ({ province: provinceByCode(code), weight }));
  document.getElementById("scenarioCount").textContent = `${entries.length} พื้นที่`;

  if (!entries.length) {
    list.innerHTML = '<div class="empty-scenario"><span>＋</span><strong>ยังไม่ได้เลือกพื้นที่</strong><p>คลิกจังหวัดบนแผนที่หรือปุ่ม “เพิ่ม” ในตารางด้านบน</p></div>';
  } else {
    list.innerHTML = entries
      .map(
        ({ province, weight }) => `
          <article class="scenario-item">
            <div class="scenario-item-head">
              <strong>${escapeHtml(province.province_name_th)}</strong>
              <div><span>${Number(weight).toFixed(1)}%</span><button type="button" data-remove="${province.province_code}" aria-label="นำ ${escapeHtml(province.province_name_th)} ออก">×</button></div>
            </div>
            <input type="range" min="0" max="100" step="1" value="${weight}" data-weight="${province.province_code}" aria-label="สัดส่วน ${escapeHtml(province.province_name_th)}" />
          </article>`,
      )
      .join("");
    document.querySelectorAll("[data-remove]").forEach((button) => button.addEventListener("click", () => removeProvinceFromScenario(button.dataset.remove)));
    document.querySelectorAll("[data-weight]").forEach((input) => {
      input.addEventListener("input", () => {
        state.scenario.set(input.dataset.weight, Number(input.value));
        renderScenario();
      });
    });
  }

  renderAllocation(entries);
}

function renderAllocation(entries) {
  const total = budgetTotal();
  const weightTotal = entries.reduce((sum, entry) => sum + Number(entry.weight), 0);
  const allocated = (total * weightTotal) / 100;
  document.getElementById("summaryBudget").textContent = `${number(total)} ลบ.`;
  document.getElementById("summaryAllocated").textContent = `${number(weightTotal)}%`;
  document.getElementById("summaryAllocated").style.color = weightTotal > 100 ? "#ff8066" : "";
  document.getElementById("allocatedTotal").textContent = `${number(allocated)} ล้านบาท`;
  const chart = document.getElementById("allocationChart");
  if (!entries.length) {
    chart.innerHTML = '<div class="chart-empty"><span></span><p>เพิ่มพื้นที่อย่างน้อย 1 จังหวัดเพื่อเริ่มจำลอง</p></div>';
    return;
  }
  const maxWeight = Math.max(...entries.map((entry) => Number(entry.weight)), 1);
  chart.innerHTML = entries
    .sort((a, b) => b.weight - a.weight)
    .map(({ province, weight }) => {
      const amount = (total * weight) / 100;
      return `<article class="allocation-row"><span>${escapeHtml(province.province_name_th)}</span><div class="allocation-track"><i style="width:${Math.max(1, (weight / maxWeight) * 100)}%"></i></div><strong>${number(amount)} ลบ.</strong></article>`;
    })
    .join("");
}

async function copyScenario() {
  if (!state.scenario.size) {
    showToast("เพิ่มพื้นที่ก่อนคัดลอกฉากทัศน์");
    return;
  }
  const total = budgetTotal();
  const lines = [
    `AIAT Public Evidence Atlas — ฉากทัศน์งบ ${number(total)} ล้านบาท`,
    ...[...state.scenario.entries()].map(([code, weight]) => {
      const province = provinceByCode(code);
      return `- ${province.province_name_th}: ${number(weight)}% (${number((total * weight) / 100)} ล้านบาท)`;
    }),
    "หมายเหตุ: Simulation only · Candidate data · ไม่ใช่คำแนะนำจัดสรรงบ",
  ];
  try {
    await navigator.clipboard.writeText(lines.join("\n"));
    showToast("คัดลอกสรุปฉากทัศน์แล้ว");
  } catch {
    showToast("เบราว์เซอร์ไม่อนุญาตให้คัดลอกอัตโนมัติ");
  }
}

function bindEvents() {
  document.getElementById("metricOptions").addEventListener("click", (event) => {
    const button = event.target.closest("[data-metric]");
    if (button) setActiveMetric(button.dataset.metric);
  });
  document.getElementById("rankMetric").addEventListener("click", (event) => {
    const button = event.target.closest("[data-rank]");
    if (!button) return;
    state.rankMetric = button.dataset.rank;
    document.querySelectorAll("[data-rank]").forEach((item) => item.classList.toggle("active", item === button));
    renderRanking();
  });
  document.getElementById("provinceSearch").addEventListener("input", renderRanking);
  document.getElementById("pointToggle").addEventListener("change", (event) => {
    if (!state.mapLoaded) return;
    const visibility = event.target.checked ? "visible" : "none";
    state.map.setLayoutProperty("cultural-clusters", "visibility", visibility);
    state.map.setLayoutProperty("cultural-point", "visibility", visibility);
  });
  document.getElementById("resetMap").addEventListener("click", () => {
    if (state.mapLoaded) state.map.flyTo({ center: [101.15, 13.4], zoom: 4.55, pitch: 43, bearing: -8, duration: 1000 });
  });
  document.getElementById("closePeek").addEventListener("click", () => document.getElementById("provincePeek").classList.add("is-hidden"));
  document.getElementById("addProvince").addEventListener("click", () => {
    if (state.activeProvince) addProvinceToScenario(state.activeProvince.province_code);
  });
  document.getElementById("budgetTotal").addEventListener("input", renderScenario);
  document.getElementById("clearScenario").addEventListener("click", () => {
    state.scenario.clear();
    renderScenario();
    renderRanking();
    renderProvincePeek(state.activeProvince);
  });
  document.getElementById("copyScenario").addEventListener("click", copyScenario);

  const sections = [...document.querySelectorAll("main section[id]")];
  const navLinks = [...document.querySelectorAll(".site-nav a")];
  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      navLinks.forEach((link) => link.classList.toggle("active", link.getAttribute("href") === `#${visible.target.id}`));
    },
    { rootMargin: "-25% 0px -60%", threshold: [0.05, 0.25, 0.5] },
  );
  sections.forEach((section) => observer.observe(section));
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
    renderSources();
    renderRanking();
    renderScenario();
    renderProvincePeek(null);
    initMap();
    bindEvents();
  } catch (error) {
    console.error(error);
    document.getElementById("map").innerHTML = `<div class="map-fallback"><strong>โหลด Public Data ไม่สำเร็จ</strong><p>${escapeHtml(error.message)}</p></div>`;
    showToast("โหลดข้อมูลสาธารณะไม่สำเร็จ กรุณาลองใหม่");
  }
}

loadDashboard();
