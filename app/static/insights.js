const number = new Intl.NumberFormat("th-TH", { maximumFractionDigits: 1 });

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

function compactText(value, limit = 150) {
  const text = String(value ?? "").trim();
  return text.length > limit ? `${text.slice(0, limit).trim()}…` : text;
}

function safeUrl(value) {
  try {
    const url = new URL(String(value || ""), window.location.origin);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function objectArray(value, keyName = "source_id") {
  if (Array.isArray(value)) return value;
  if (!value || typeof value !== "object") return [];
  if (Array.isArray(value.items)) return value.items;
  return Object.entries(value).map(([key, item]) =>
    item && typeof item === "object" && !Array.isArray(item) ? { [keyName]: key, ...item } : { [keyName]: key, value: item },
  );
}

function pathValue(payload, path) {
  return path.split(".").reduce((value, key) => value?.[key], payload);
}

function firstDefined(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

function firstFinite(...values) {
  for (const value of values) {
    const parsed = Number(value);
    if (value !== null && value !== "" && Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function sourceRows(payload) {
  if (Array.isArray(payload)) return payload;
  for (const path of ["sources", "source_coverage", "registry.sources", "coverage.sources", "items"]) {
    const rows = objectArray(pathValue(payload, path));
    if (rows.length) return rows;
  }
  return [];
}

function coverageClass(source) {
  const visibility = source.public_visibility || {};
  const status = [source.public_status, source.serving_status, source.usable_status, source.readiness_status, source.status?.audit, source.status?.readiness, source.status?.network_api_export]
    .filter(Boolean).join(" ").toLowerCase();
  const sensitivity = String(firstDefined(source.sensitivity_lane, source.sensitivity, source.cloud_policy, "") || "").toLowerCase();
  const publicCount = firstFinite(
    source.public_record_count,
    source.public_rows,
    source.serving_record_count,
    source.records?.serving_projection_count,
    source.records?.additional_public_non_map_count,
    source.public_projection?.record_count,
    source.public_projection?.rows,
  );
  const usableCount = firstFinite(source.usable_record_count, source.usable_rows, source.latest_usable_asset?.record_count, source.latest_usable_asset?.rows);
  if (visibility.classification === "restricted_local_only" || source.railway_allowed === false) return "local-only";
  if (visibility.current_public_data_artifact === true || source.public_projection_available === true || source.usable_data === true || source.usable === true || (publicCount ?? usableCount ?? 0) > 0 || /public.ready|serving|published/.test(status)) return "ready";
  if (visibility.classification === "metadata_only") return "discovery";
  if (/blocked|timeout|unreachable|auth/.test(status)) return "blocked";
  if (/page|discovery|map.only|asset.only/.test(status)) return "discovery";
  return "review";
}

function geographyLabel(source) {
  const explicit = firstDefined(source.geo_linkability, source.geography_status, source.geo_status, source.geography?.status, source.geo?.status, source.geo?.linkability);
  const normalized = String(explicit ?? "").toLowerCase();
  const linkable = firstDefined(source.geo_linkable, source.province_linkable, source.geography?.linkable, source.geo?.linkable);
  if (linkable === true || /province|geo.linkable|linked|exact/.test(normalized)) return "ผูกจังหวัดได้";
  if (/non.geo|national|not.province/.test(normalized)) return "ข้อมูลระดับประเทศ";
  if (/not.expected/.test(normalized)) return "ไม่ใช้มิติพื้นที่";
  if (linkable === false || /unmapped|unknown|not.linked/.test(normalized)) return "ยังไม่ผูกจังหวัด";
  return "ไม่ระบุระดับพื้นที่";
}

function modeLabel(value) {
  const mode = String(value || "").toLowerCase();
  if (/api|network/.test(mode)) return "API";
  if (/gis/.test(mode)) return "GIS / directory";
  if (/export|snapshot|structured/.test(mode)) return "Raw snapshot";
  if (/dashboard|portal/.test(mode)) return "Dashboard";
  return String(value || "Metadata").replaceAll("_", " ");
}

function normalizeSource(source, index) {
  const state = coverageClass(source);
  const statusLabels = {
    ready: "พร้อมใช้บน Dashboard",
    review: "กำลังตรวจข้อมูล",
    discovery: "มีหลักฐานหน้าเว็บ",
    blocked: "ยังเข้าถึงข้อมูลไม่ได้",
    "local-only": "ใช้เฉพาะในเครื่อง",
  };
  const publicCount = firstFinite(
    source.public_record_count,
    source.public_rows,
    source.serving_record_count,
    source.records?.serving_projection_count,
    source.records?.observed_count,
    source.public_projection?.record_count,
    source.public_projection?.rows,
  );
  const usableCount = firstFinite(source.usable_record_count, source.usable_rows, source.latest_usable_asset?.record_count, source.latest_usable_asset?.rows);
  return {
    original: source,
    ordinal: firstFinite(source.ordinal, source.order, source.source_ordinal) ?? index + 1,
    sourceId: firstDefined(source.source_id, source.id, source.slug, `source-${index + 1}`),
    name: firstDefined(source.name_th, source.source_name_th, source.title_th, source.name, source.source_id, `แหล่งข้อมูล ${index + 1}`),
    group: firstDefined(source.group, source.phase, source.team, ""),
    mode: modeLabel(firstDefined(source.access_mode, source.acquisition_mode, source.mode, source.status?.network_api_export, source.source_type, source.latest_usable_asset?.access_mode, "Metadata")),
    statusClass: state,
    statusLabel: source.public_visibility?.classification === "metadata_only" ? "มีเฉพาะ Metadata" : statusLabels[state],
    geography: geographyLabel(source),
    count: state === "ready" ? publicCount ?? usableCount : null,
    nonMapCount: firstFinite(source.records?.additional_public_non_map_count),
    note: firstDefined(source.note_th, source.notes_th?.[1], source.notes_th?.[0], source.gap_th, source.status_reason_th, source.status_reason, source.next_safe_action, source.geo?.known_omissions?.[0]?.reason_th, source.gaps?.[0], ""),
    url: safeUrl(firstDefined(source.url, source.normalized_url, source.source_url, source.raw_url, "")),
  };
}

function renderSourceCoverage(payload) {
  const sources = sourceRows(payload)
    .map(normalizeSource)
    .sort((a, b) => a.ordinal - b.ordinal);
  const state = document.getElementById("sourceCoverageState");
  if (!sources.length) {
    state.textContent = "ยังไม่มีทะเบียน public projection สำหรับรอบนี้";
    return [];
  }

  const ready = sources.filter((source) => source.statusClass === "ready").length;
  const linked = sources.filter((source) => source.geography === "ผูกจังหวัดได้").length;
  const localOnly = sources.filter((source) => source.statusClass === "local-only").length;
  document.getElementById("sourceCoverageMeta").innerHTML = [
    `<span><strong>${number.format(sources.length)}</strong> URL ในทะเบียน</span>`,
    `<span><strong>${number.format(ready)}</strong> พร้อมใช้</span>`,
    `<span><strong>${number.format(linked)}</strong> ผูกจังหวัดได้</span>`,
    localOnly ? `<span><strong>${number.format(localOnly)}</strong> เก็บเฉพาะในเครื่อง</span>` : "",
  ].join("");
  state.textContent = sources.length === 29 ? "แสดงครบทั้ง 29 แหล่ง" : `แสดง ${number.format(sources.length)} จาก 29 แหล่งที่อยู่ในทะเบียน`;
  state.classList.toggle("is-warning", sources.length !== 29);
  document.getElementById("sourceCoverageGrid").innerHTML = sources.map((source) => `
    <article class="source-coverage-card is-${source.statusClass}">
      <header><span class="source-order">${String(source.ordinal).padStart(2, "0")}</span><div><small>${escapeHtml(source.group || source.sourceId)}</small><h3>${escapeHtml(source.name)}</h3></div><b>${escapeHtml(source.statusLabel)}</b></header>
      <div class="source-coverage-tags"><span>${escapeHtml(source.mode)}</span><span>${escapeHtml(source.geography)}</span>${source.count !== null ? `<span>${number.format(source.count)} รายการ public</span>` : ""}${source.nonMapCount ? `<span>${number.format(source.nonMapCount)} รายการนอกแผนที่</span>` : ""}</div>
      ${source.note ? `<p>${escapeHtml(compactText(source.note))}</p>` : ""}
      ${source.url ? `<a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">เปิด URL ต้นทาง</a>` : ""}
    </article>`).join("");
  return sources;
}

function collectLooseData(payload) {
  const paths = {
    unmapped: ["unmapped_records", "unmapped", "records.unmapped", "public_projection.unmapped_records", "geography.unmapped_records"],
    non_geo: ["non_geo_records", "non_geo", "records.non_geo", "public_projection.non_geo_records", "geography.non_geo_records"],
  };
  const rows = [];
  Object.entries(paths).forEach(([scope, candidates]) => {
    for (const path of candidates) {
      const value = pathValue(payload, path);
      const items = objectArray(value);
      if (items.length) {
        items.forEach((item) => rows.push({ scope, ...item }));
        break;
      }
    }
  });
  sourceRows(payload).forEach((source) => {
    const omissions = source.geo?.known_omissions || [];
    omissions.forEach((omission) => rows.push({
      scope: "map_omission",
      source_id: source.source_id,
      source_name_th: source.name_th,
      title_th: source.name_th,
      summary_th: [omission.labels_th?.join(" · "), omission.reason_th].filter(Boolean).join(" — "),
      record_count: omission.count,
      source_url: source.url,
    }));
    const linkability = String(source.geo?.linkability || "").toLowerCase();
    if (/not.province|non.geo|national/.test(linkability)) {
      rows.push({
        scope: "non_geo",
        source_id: source.source_id,
        source_name_th: source.name_th,
        title_th: source.name_th,
        summary_th: source.notes_th?.[1] || source.notes_th?.[0] || "ต้นทางไม่ได้ระบุพื้นที่ใช้งานที่ผูกจังหวัดได้",
        record_count: source.records?.serving_projection_count,
        grain_th: source.records?.serving_projection_grain || source.geo?.grain,
        source_url: source.url,
      });
    }
  });
  return rows;
}

function collectUnmappedProjection(payload) {
  const rows = [];
  objectArray(payload?.sources).forEach((source) => {
    const items = source.items || [];
    if (items.length > 24) {
      const reasonLabels = {
        source_geography_missing: "ต้นทางไม่ระบุพื้นที่",
        source_geography_not_at_province_grain: "ข้อมูลต่ำกว่าหรือไม่ใช่ระดับจังหวัด",
        source_province_code_not_in_official_crosswalk: "รหัสต้นทางไม่ตรงทะเบียนจังหวัด",
      };
      const reasonMetrics = Object.entries(source.reason_counts || {}).map(([reason, count]) => ({
        label_th: reasonLabels[reason] || reason,
        display_value: `${number.format(count)} แถว`,
      }));
      rows.push({
        scope: "unmapped",
        source_id: source.source_id,
        title_th: source.source_id === "f3_housing_portal" ? "ข้อมูลที่อยู่อาศัยนอกชั้นจังหวัด" : source.source_id,
        summary_th: "เก็บไว้ครบใน public database แต่ไม่บังคับผูกจังหวัด เพราะ grain หรือรหัสพื้นที่จากต้นทางยังไม่ผ่าน exact crosswalk",
        record_count: source.record_count || items.length,
        source_url: items.find((item) => item.source_url)?.source_url,
        display_metrics: [
          { label_th: "รายการที่ไม่ผูกจังหวัด", display_value: number.format(source.record_count || items.length) },
          ...reasonMetrics,
        ],
      });
      return;
    }
    items.forEach((item) => {
      const record = item.record || {};
      rows.push({
        scope: "unmapped",
        source_id: source.source_id,
        title_th: firstDefined(record.project_name, record.title, "รายการที่ไม่ระบุจังหวัด"),
        summary_th: [record.business_name, record.research_unit].filter(Boolean).join(" · "),
        source_url: record.source_url,
        display_metrics: [
          record.fiscal_year ? { label_th: "ปีงบประมาณ", display_value: record.fiscal_year } : null,
          record.subdistrict ? { label_th: "ตำบลจากต้นทาง", display_value: record.subdistrict } : null,
          { label_th: "เหตุผล", display_value: item.reason === "source_province_missing" ? "ต้นทางไม่ระบุจังหวัด" : item.reason || "ยังจับคู่พื้นที่ไม่ได้" },
        ].filter(Boolean),
      });
    });
  });
  return rows;
}

function looseMetrics(item) {
  const structured = objectArray(firstDefined(item.display_metrics, item.metrics), "label_th");
  if (structured.length) {
    return structured.slice(0, 4).map((metric) => ({
      label: firstDefined(metric.label_th, metric.label, metric.name_th, metric.label_th, "ค่า"),
      value: firstDefined(metric.display_value, metric.value, metric.count, "ไม่ระบุ"),
    }));
  }
  return [
    ["จำนวนรายการ", firstFinite(item.record_count, item.records, item.public_record_count, item.usable_record_count)],
    ["ระดับข้อมูล", firstDefined(item.grain_th, item.grain, item.scope_th)],
    ["สถานะพื้นที่", firstDefined(item.geo_status_th, item.geography_status_th)],
  ].filter(([, value]) => value !== null && value !== undefined && value !== "").map(([label, value]) => ({ label, value }));
}

function renderLooseData(payload, unmappedPayload = null) {
  let rows = [...collectLooseData(payload), ...collectUnmappedProjection(unmappedPayload)];
  if (!rows.length) return;
  if (rows.length > 32) {
    const grouped = new Map();
    rows.forEach((row) => {
      const key = `${row.scope}:${firstDefined(row.source_id, row.name_th, "unknown")}`;
      const current = grouped.get(key) || { ...row, record_count: 0 };
      current.record_count += firstFinite(row.record_count, row.records, 1) || 1;
      grouped.set(key, current);
    });
    rows = [...grouped.values()];
  }
  document.getElementById("unmapped").hidden = false;
  document.getElementById("looseDataGrid").innerHTML = rows.map((item) => {
    const title = firstDefined(item.title_th, item.name_th, item.label_th, item.source_name_th, item.source_id, "ข้อมูลจาก public projection");
    const note = firstDefined(item.summary_th, item.note_th, item.reason_th, item.description_th, item.status_reason, "");
    const metrics = looseMetrics(item);
    const sourceUrl = safeUrl(firstDefined(item.url, item.source_url, ""));
    return `
      <article class="loose-data-card">
        <span>${item.scope === "non_geo" ? "ข้อมูลระดับประเทศ" : item.scope === "map_omission" ? "ข้อมูลนอกชั้นแผนที่" : "ยังไม่ผูกจังหวัด"}</span>
        <h3>${escapeHtml(title)}</h3>
        ${note ? `<p>${escapeHtml(compactText(note))}</p>` : ""}
        ${metrics.length ? `<dl>${metrics.map((metric) => `<div><dt>${escapeHtml(metric.label)}</dt><dd>${escapeHtml(metric.value)}</dd></div>`).join("")}</dl>` : ""}
        ${sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noreferrer">เปิดหลักฐานต้นทาง</a>` : ""}
      </article>`;
  }).join("");
}

function learningSummaryItems(payload, sources) {
  const learning = sources.find((source) => source.ordinal === 10 || source.sourceId === "f2_learning_dashboard")?.original || {};
  const candidates = [
    learning.executive_summaries,
    learning.executive_summary,
    payload.source_10_executive_summaries,
    payload.executive_summaries?.f2_learning_dashboard,
    payload.executive_summaries?.source_10,
  ];
  for (const candidate of candidates) {
    if (!candidate) continue;
    if (typeof candidate === "string") return [{ text_th: candidate }];
    if (Array.isArray(candidate)) return candidate;
    if (Array.isArray(candidate.items)) return candidate.items;
    if (Array.isArray(candidate.observations)) return candidate.observations;
    if (typeof candidate === "object") return [candidate];
  }
  return [];
}

function renderLearningSummary(payload, sources) {
  const items = learningSummaryItems(payload, sources);
  if (!items.length) return;
  document.getElementById("learningSummary").hidden = false;
  document.getElementById("learningSummaryGrid").innerHTML = items.map((item) => {
    const title = firstDefined(item.title_th, item.label_th, item.name_th, "ภาพรวมจาก Dashboard LE");
    const text = firstDefined(item.summary_th, item.text_th, item.readout_th, item.description_th, "");
    const metrics = looseMetrics(item);
    return `<article class="learning-summary-card"><span>Source 10</span><h3>${escapeHtml(title)}</h3>${text ? `<p>${escapeHtml(compactText(text, 220))}</p>` : ""}${metrics.length ? `<div>${metrics.map((metric) => `<small>${escapeHtml(metric.label)} <strong>${escapeHtml(metric.value)}</strong></small>`).join("")}</div>` : ""}</article>`;
  }).join("");
}

function renderLearningDashboard(payload) {
  if (!payload?.coverage) return;
  const source = payload.source || payload;
  const tables = payload.non_province_tables || {};
  const tableLabels = {
    entity_types: "รูปแบบองค์กรในชุดข้อมูล",
    categories: "หมวดกิจกรรมในชุดข้อมูล",
    geography: "ภาพรวมตามภูมิภาค",
  };
  const cards = [{
    title: "ขอบเขตข้อมูลที่เชื่อมจังหวัด",
    text: payload.quality?.scope_warning_th || payload.scope_warning_th || source.notes_th || payload.readout_th,
    metrics: [
      { label: "จังหวัดที่เชื่อมได้", value: number.format(payload.coverage.linked_provinces) },
      { label: "แถวระดับจังหวัด", value: number.format(payload.coverage.province_rows) },
    ],
  }];
  Object.entries(tables).forEach(([key, table]) => {
    const rows = [...(table.rows || [])].sort((a, b) => Number(b.value || 0) - Number(a.value || 0)).slice(0, 5);
    if (!rows.length) return;
    cards.push({
      title: tableLabels[key] || key,
      text: "ค่าตามหมวดของต้นทาง ไม่ถูกรวมเป็นคะแนน",
      metrics: rows.map((row) => ({ label: row.label, value: number.format(row.value) })),
    });
  });
  const impact = payload.non_province_impact || {};
  const impactSummary = impact.summary || {};
  const impactMetrics = [
    ["การใช้ทรัพยากรท้องถิ่น", impactSummary.totalResourceConsumption],
    ["มูลค่าทรัพยากรท้องถิ่น", impactSummary.totalResourceExpense],
    ["การจ้างงานท้องถิ่น", firstDefined(impactSummary.totalEmployeeAmount, impactSummary.totalEmplyeeAmount)],
    ["ค่าใช้จ่ายการจ้างงาน", impactSummary.totalEmployeeExpense],
  ].filter(([, value]) => Number.isFinite(Number(value))).map(([label, value]) => ({ label, value: number.format(value) }));
  if (impactMetrics.length) {
    cards.push({
      title: "ผลรวมที่ยังไม่ผูกจังหวัด",
      text: "ต้นทางไม่ระบุหน่วยและวันที่อ้างอิง จึงแสดงแยกจากแผนที่และไม่ใช้จัดอันดับพื้นที่",
      metrics: impactMetrics,
    });
  }
  document.getElementById("learningSummary").hidden = false;
  document.getElementById("learningSummaryGrid").innerHTML = cards.map((card) => `
    <article class="learning-summary-card">
      <span>Source 10 · Candidate</span>
      <h3>${escapeHtml(card.title)}</h3>
      ${card.text ? `<p>${escapeHtml(compactText(card.text, 240))}</p>` : ""}
      <div>${card.metrics.map((metric) => `<small>${escapeHtml(metric.label)} <strong>${escapeHtml(metric.value)}</strong></small>`).join("")}</div>
    </article>`).join("");
}

async function fetchPublicJson(...paths) {
  for (const path of paths) {
    try {
      const response = await fetch(path, { cache: "no-store" });
      if (response.ok) return response.json();
    } catch {
      // Try the static public projection when the API is not mounted in development.
    }
  }
  return null;
}

async function loadSourceCoverage() {
  const [payload, learningPayload, unmappedPayload] = await Promise.all([
    fetchPublicJson("/api/public/v1/source-coverage", "/downloads/source_coverage.json"),
    fetchPublicJson("/api/public/v1/learning-dashboard", "/downloads/learning_dashboard.json"),
    fetchPublicJson("/api/public/v1/unmapped-records", "/downloads/unmapped_records.json"),
  ]);
  if (payload) {
    const sources = renderSourceCoverage(payload);
    renderLearningSummary(payload, sources);
    renderLooseData(payload, unmappedPayload);
  } else {
    document.getElementById("sourceCoverageState").textContent = "ทะเบียน public projection ยังไม่ถูกสร้างใน environment นี้";
    document.getElementById("sourceCoverageState").classList.add("is-warning");
  }
  if (learningPayload) renderLearningDashboard(learningPayload);
  if (!payload && unmappedPayload) renderLooseData({}, unmappedPayload);
}

function fact(label, value, note = "") {
  return `<article class="fact"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>${note ? `<small>${escapeHtml(note)}</small>` : ""}</article>`;
}

function renderBars(target, items, color = "#1f5b43", limit = 10) {
  const rows = (items || []).slice(0, limit);
  const max = Math.max(...rows.map((item) => Number(item.value) || 0), 1);
  document.getElementById(target).innerHTML = `<div class="bar-list" style="--bar:${color}">${rows.map((item) => `
    <div class="bar-row" title="${escapeHtml(item.label_th)} ${number.format(item.value)}">
      <span>${escapeHtml(item.label_th)}</span><i><b style="width:${Math.max(2, Number(item.value || 0) / max * 100).toFixed(1)}%"></b></i><strong>${number.format(item.value)}</strong>
    </div>`).join("")}</div>`;
}

function renderExecutivePortfolio(portfolio) {
  if (!portfolio?.audit || !Array.isArray(portfolio.headline_metrics)) return;
  const section = document.getElementById("executivePortfolio");
  section.hidden = false;

  document.getElementById("executiveKpis").innerHTML = portfolio.headline_metrics.map((metric) => {
    const display = metric.display_value ?? number.format(metric.value);
    return `<article class="portfolio-kpi" data-source="${escapeHtml(metric.source_id)}">
      <span>${escapeHtml(metric.label_th)}</span>
      <div><strong>${escapeHtml(display)}</strong><b>${escapeHtml(metric.unit)}</b></div>
      <small>${escapeHtml(metric.note_th)}</small>
    </article>`;
  }).join("");

  const audit = portfolio.audit;
  const total = Math.max(Number(audit.source_count) || 0, 1);
  const completePct = Number(audit.complete_source_count || 0) / total * 100;
  const partialPct = Number(audit.partial_source_count || 0) / total * 100;
  const completeEnd = completePct.toFixed(1);
  const partialEnd = (completePct + partialPct).toFixed(1);
  document.getElementById("auditReadiness").innerHTML = `
    <div class="readiness-donut" role="img" aria-label="ตรวจครบตามหน้าเว็บ ${number.format(audit.complete_source_count)} แหล่ง และใช้ได้บางส่วน ${number.format(audit.partial_source_count)} แหล่ง" style="background:conic-gradient(#1f5b43 0 ${completeEnd}%,#f0c66a ${completeEnd}% ${partialEnd}%,#73b8d5 ${partialEnd}% 100%)">
      <div><strong>${number.format(audit.source_count)}</strong><span>เว็บไซต์</span></div>
    </div>
    <div class="readiness-legend">
      <span class="is-complete"><i></i><b>${number.format(audit.complete_source_count)}</b> ครบตาม public surface</span>
      <span class="is-partial"><i></i><b>${number.format(audit.partial_source_count)}</b> ใช้ได้บางส่วน</span>
      ${audit.mixed_source_count ? `<span class="is-mixed"><i></i><b>${number.format(audit.mixed_source_count)}</b> มีหลาย data lane</span>` : ""}
    </div>`;

  const charts = portfolio.charts || {};
  renderBars("capitalChart", charts.livelihood_capital?.items, "#2f7659", 8);
  renderBars("businessTypeChart", charts.area_business_types?.items, "#73b8d5", 8);
  renderBars("culturalChart", charts.cultural_records?.items, "#a58bd4", 8);
  renderBars("housingSpatialChart", charts.housing_spatial?.items, "#e99b62", 8);
  renderBars("tourismChart", charts.tourism_inventory?.items, "#59a88a", 8);
  renderBars("cityCompletenessChart", charts.city_data_completeness?.items, "#7a91cf", 4);

  document.getElementById("sourceHealthGrid").innerHTML = audit.status_rows.map((source) => `
    <article class="source-health-card is-${escapeHtml(source.status)}">
      <header><strong>${escapeHtml(source.label_th)}</strong><span>${escapeHtml(source.status_th)}</span></header>
      <p>${escapeHtml(source.summary_th)}</p>
      <div class="source-tab-chips">${(source.dashboard_tabs || []).map((tab) => `<span>${escapeHtml(tab)}</span>`).join("")}</div>
    </article>`).join("");
}

function topMetric(ppp, metricName, limit = 5) {
  return ppp.provinces
    .map((province) => {
      const record = province.metrics.find((item) => item.metric_name === metricName);
      return record ? { name: province.province_name_th, value: Number(record.value) } : null;
    })
    .filter(Boolean)
    .sort((a, b) => b.value - a.value)
    .slice(0, limit);
}

function profileCard(title, rows) {
  return `<article class="profile-card"><h3>${escapeHtml(title)}</h3>${rows.map((row) => `<div class="rank-row"><span>${escapeHtml(row.name)}</span><strong>${number.format(row.value)}</strong></div>`).join("")}</article>`;
}

function metricLine(metric) {
  const min = Number(metric.minimum);
  const max = Number(metric.maximum);
  const middle = Number(metric.median);
  const span = Math.max(max - min, 1);
  const position = Math.max(0, Math.min(100, (middle - min) / span * 100));
  const unit = metric.display_unit || "";
  return `<div class="metric-line">
    <div class="metric-title"><strong>${escapeHtml(metric.label_th)}</strong><span>${escapeHtml(metric.description_th || "")}</span></div>
    <div class="range-track" aria-label="ค่ากลาง ${number.format(middle)} ${escapeHtml(unit)}"><i style="left:${position.toFixed(1)}%"></i></div>
    <div class="metric-meta"><span>ช่วง ${number.format(min)} ถึง ${number.format(max)} ${escapeHtml(unit)}</span><strong>กลาง ${number.format(middle)}</strong></div>
  </div>`;
}

function renderAudit(payload) {
  const labels = {
    f1_pppconnext: ["PPPConnext", "ผูกระดับจังหวัด"],
    f2_apptech_mtr: ["AppTech MTR", "API จังหวัด"],
    f3_city_capital_open_data: ["City Capital", "ทะเบียนเทศบาล"],
    f2_rmutdb: ["RMUTDB", "ไม่ฝืนผูกพื้นที่"],
  };
  const ids = [...payload.audit_summary.geo_linkable_source_ids, ...payload.audit_summary.non_geo_source_ids];
  document.getElementById("auditStrip").innerHTML = ids.map((id) => {
    const nonGeo = payload.audit_summary.non_geo_source_ids.includes(id);
    return `<article class="audit-item${nonGeo ? " is-non-geo" : ""}"><span><i></i>${nonGeo ? "ข้อมูลระดับประเทศ" : "เชื่อมพื้นที่แล้ว"}</span><strong>${labels[id][0]}</strong><span>${labels[id][1]}</span></article>`;
  }).join("");
}

function renderPpp(source) {
  document.getElementById("pppReadout").textContent = source.readout_th;
  document.getElementById("pppFacts").innerHTML = [
    fact("ระดับข้อมูล", "ภาค จังหวัด อำเภอ", "แยก grain ชัดเจน"),
    fact("พื้นที่ที่ผูกได้", `${number.format(source.coverage.linked_provinces)} จังหวัด`, "exact name crosswalk"),
    fact("ตัวชี้วัดจังหวัด", number.format(source.coverage.province_rows), "aggregate rows"),
    fact("ความสด", "ไม่ระบุ", "แสดงเป็น snapshot"),
  ].join("");
  document.getElementById("pppProfiles").innerHTML = [
    profileCard("จำนวนครัวเรือน", topMetric(source, "จำนวนครัวเรือน")),
    profileCard("กลุ่มที่ 1 อยู่ลำบาก", topMetric(source, "กลุ่มที่ 1 อยู่ลำบาก")),
    profileCard("กลุ่มที่ 2 อยู่ยาก", topMetric(source, "กลุ่มที่ 2 อยู่ยาก")),
  ].join("");
}

function renderApptech(source) {
  const stats = source.statistics;
  document.getElementById("apptechReadout").textContent = source.readout_th;
  document.getElementById("apptechFacts").innerHTML = [
    fact("ผลงานใน snapshot", number.format(stats.snapshot_records), "รายการ public API"),
    fact("ผู้ใช้ที่ลงทะเบียน", number.format(stats.registered_users), "รวมจาก API จังหวัด"),
    fact("การปฏิสัมพันธ์", number.format(stats.province_interaction_total), "รวมจาก API จังหวัด"),
    fact("ความต้องการที่จับคู่", number.format(stats.matched_requirements), `จาก ${number.format(stats.requirements)} ความต้องการ`),
  ].join("");
  renderBars("apptechCategories", source.distributions.categories, "#467d64", 8);
  renderBars("apptechProvinces", source.province_activity.map((item) => ({ label_th: item.province_name_th, value: item.registered_users })), "#73b8d5", 10);
}

function renderCity(source) {
  document.getElementById("cityReadout").textContent = source.readout_th;
  document.getElementById("cityFacts").innerHTML = [
    fact("เทศบาล", number.format(source.coverage.cities), "เชื่อมทะเบียนครบทุกเมือง"),
    fact("จังหวัด", number.format(source.coverage.linked_provinces), "เก็บระดับเมืองแยกกัน"),
    fact("ตัวชี้วัด", number.format(source.coverage.metrics), "สามมิติ"),
    fact("ปีข้อมูล", "ไม่ระบุ", "ตามข้อจำกัดต้นทาง"),
  ].join("");
  const signalMetrics = new Set();
  const signals = source.executive_signals.filter((signal) => {
    if (signalMetrics.has(signal.metric_id)) return false;
    signalMetrics.add(signal.metric_id);
    return true;
  }).slice(0, 8);
  document.getElementById("citySignals").innerHTML = signals.map((signal) => `
    <article class="signal-card"><span>${escapeHtml(signal.city_name_th)}</span><strong>${escapeHtml(signal.label_th)}</strong><p>${number.format(signal.value)} ${escapeHtml(signal.display_unit || "")}</p><small>${signal.comparison === "above" ? "สูงกว่า" : "ต่ำกว่า"}ค่ากลางของ 18 เมือง</small></article>`).join("");
  document.getElementById("cityGroups").innerHTML = source.groups.map((group) => `
    <article class="city-group"><header><h3>${escapeHtml(group.label_th)}</h3><span>${number.format(group.metrics.length)} ตัวชี้วัด</span></header>${group.metrics.map(metricLine).join("")}</article>`).join("");
}

function renderRmut(source) {
  const stats = source.statistics;
  document.getElementById("rmutReadout").textContent = source.readout_th;
  document.getElementById("rmutFacts").innerHTML = [
    fact("ฉบับละเอียด", number.format(stats.detailed_records), "มีเทคโนโลยี TRL และ IP"),
    fact("สรุปประจำปี", number.format(stats.annual_summary_records), "รูปแบบข้อมูลต่างกัน"),
    fact("แหล่งข้อมูล", "Public e-book", "API มี auth boundary"),
    fact("ระดับพื้นที่", "ไม่ระบุ", "ไม่เดาจากชื่อมหาวิทยาลัย"),
  ].join("");
  renderBars("rmutTechnology", source.distributions.technology_groups, "#1f5b43", 10);
  renderBars("rmutTrl", source.distributions.trl_levels, "#a58bd4", 8);
  renderBars("rmutIp", source.distributions.ip_status, "#f0c66a", 8);
}

async function loadInsights() {
  try {
    const response = await fetch("/api/public/v1/source-insights");
    if (!response.ok) throw new Error("source insights unavailable");
    const payload = await response.json();
    renderExecutivePortfolio(payload.executive_portfolio);
    renderAudit(payload);
    renderPpp(payload.sources.f1_pppconnext);
    renderApptech(payload.sources.f2_apptech_mtr);
    renderCity(payload.sources.f3_city_capital_open_data);
    renderRmut(payload.sources.f2_rmutdb);
    if (payload.sources.f2_learning_dashboard) renderLearningDashboard(payload.sources.f2_learning_dashboard);
    document.getElementById("pageLoading").hidden = true;
    document.getElementById("insightContent").hidden = false;
    if (window.location.hash) document.querySelector(window.location.hash)?.scrollIntoView();
  } catch (error) {
    console.error(error);
    document.getElementById("pageLoading").hidden = true;
    document.getElementById("pageError").hidden = false;
  }
}

loadInsights();
loadSourceCoverage();
