const number = new Intl.NumberFormat("th-TH", { maximumFractionDigits: 1 });

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
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
    renderAudit(payload);
    renderPpp(payload.sources.f1_pppconnext);
    renderApptech(payload.sources.f2_apptech_mtr);
    renderCity(payload.sources.f3_city_capital_open_data);
    renderRmut(payload.sources.f2_rmutdb);
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
