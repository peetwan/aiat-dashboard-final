(() => {
  "use strict";
  const API = "/api/public/v1/f2";
  const $ = (id) => document.getElementById(id);
  const panel = $("f2DashboardPanel");
  const views = { overview: $("f2-view-overview"), list: $("f2-view-list"), sources: $("f2-view-sources") };
  const state = { open: false, tab: "overview", province: "", measure: "", topic: "", detail: "", detailHistory: false, revision: "", overview: null, topicData: null, controllers: {}, requests: {}, returnFocus: null, pendingListFocus: "", callbacks: {}, filters: {}, searchDraft: "", searchTimer: null, scopeNotice: "", offset: 0, limit: 25 };
  const C02_MEASURE_ID = "C02_COMMUNITY";
  const C02_SOURCE_PROVINCE_MEANING = "จังหวัดที่แสดงเป็นจังหวัดที่แหล่งข้อมูลระบุไว้ในทะเบียน ไม่ใช่ที่อยู่หรือสถานที่ทำงานปัจจุบัน";
  const FILTER_LABELS = {
    category: "หมวดหมู่ตามแหล่งข้อมูล",
    source_level: "ระดับตามแหล่งข้อมูล",
    source_region: "ภูมิภาคตามแหล่งข้อมูล",
    component: "องค์ประกอบของตัวเลข",
    source_dimension: "มิติข้อมูลตามแหล่งข้อมูล",
  };
  const RESULT_STATUS_LABELS = {
    source_aggregate: "ยอดรวมที่แหล่งข้อมูลรายงาน",
    assumed_aggregate: "ยอดรวมที่มีข้อสมมติในการคำนวณ",
    assumed_historical_reconstruction: "ค่าประมาณเพื่ออธิบายตัวเลขเดิม",
    available: "มีข้อมูล",
    unavailable: "ไม่มีข้อมูลสำหรับขอบเขตนี้",
    insufficient_data: "ข้อมูลไม่เพียงพอ",
    deferred: "ยังไม่คำนวณ",
  };
  const SOURCE_NAMES = {
    f2_apptech_mru: "AppTech เครือข่ายมหาวิทยาลัยราชภัฏ",
    f2_apptech_mtr: "AppTech เครือข่ายมหาวิทยาลัยเทคโนโลยีราชมงคล",
    f2_cultural_market_civil: "แผนที่ตลาดวัฒนธรรม",
    f2_culturalmap_university: "แผนที่วัฒนธรรมไทย",
    f2_icommunity: "ชุมชนนวัตกรรม",
    f2_learning_area_based: "โครงการพัฒนาพื้นที่การเรียนรู้",
    f2_learning_dashboard: "ระบบรายงานผลโครงการพัฒนาพื้นที่การเรียนรู้",
    f2_target_household: "ระบบฐานข้อมูลครัวเรือนมุ่งเป้า",
  };
  const MEASURE_LIMITATIONS = {
    K01A: "การพบหลักฐานในจังหวัดไม่ได้หมายความว่าตัวชี้วัดทุกตัวมีข้อมูลครบในจังหวัดนั้น และไม่นับที่อยู่ของสถาบันแทนพื้นที่ดำเนินงาน",
    K01B: "นับเฉพาะพื้นที่วัฒนธรรมตามนิยามที่กำหนด รายการที่อาจซ้ำแต่ยังยืนยันไม่ได้ยังคงนับแยกและแสดงความไม่แน่นอน",
    K02: "เป็นยอดรวมที่ต้นทางรายงาน ไม่ใช่รายชื่อบุคคล จังหวัดที่ไม่มีข้อมูลต้องอ่านว่า “ไม่มีข้อมูล” ไม่ใช่ศูนย์ และไม่ควรนำไปรวมหรือลบกับรายชื่อ C02",
    C02_COMMUNITY: "จังหวัดมาจากระเบียนนวัตกรของต้นทาง ไม่ใช่ที่อยู่หรือที่ทำงานปัจจุบัน บางคนมีมากกว่าหนึ่งจังหวัด จึงบวกยอดรายจังหวัดเพื่อหายอดประเทศไม่ได้ และไม่ควรนำไปรวมกับ K02",
    K03: "สิ่งพิมพ์และช่วงกิจกรรมเป็นรายละเอียดของกิจกรรม ไม่ใช่กิจกรรมเพิ่ม และการมีรายงานไม่ได้ยืนยันว่าโครงการทั้งหมดเสร็จสมบูรณ์",
    K04: "ระดับความพร้อมเป็นหลักฐานที่ต้นทางรายงานตามกฎของชุดข้อมูล ไม่ใช่การรับรองสถานะปัจจุบัน หากแหล่งข้อมูลขัดกันจะแสดงหลักฐานแยกกัน",
    C04_LISTED: "รวมรายการที่อยู่ใน K04 ด้วย รายการที่ไม่ผ่านเกณฑ์ความพร้อมอาจเป็นเพราะไม่มีหลักฐานเพียงพอ ไม่ได้แปลว่ายืนยันแล้วว่าไม่พร้อม",
    K05: "เป็นความครอบคลุมบางส่วนจากแหล่งข้อมูลที่ตรวจแล้ว ไม่ใช่ทะเบียนธุรกิจวัฒนธรรมทั้งหมด และไม่นำที่ตั้งสินค้าหรือโครงการมาแทนที่ตั้งธุรกิจ",
    K06: "ยังไม่เผยแพร่ยอดรวม เพราะการค้นหาและยืนยันบทบาทบุคคลยังไม่สม่ำเสมอ การไม่มีตัวเลขไม่ได้แปลว่าไม่มีผู้ประกอบการ",
    K07: "นับเป็นตระกูลสินค้า บริการ หรือผลงาน ไม่ใช่จำนวนรูปแบบย่อยทั้งหมด การมีรายการหรือราคาไม่ยืนยันว่าพร้อมขายหรือเกิดจากโครงการ",
    K08: "ยังคำนวณไม่ได้ การเข้าร่วมโครงการหรือคะแนนบุคคลที่เพิ่มขึ้นยังไม่เพียงพอที่จะยืนยันว่าธุรกิจพัฒนาขีดความสามารถ",
    C08_PARTICIPATING: "ยืนยันเพียงว่าหน่วยธุรกิจมีหลักฐานเข้าร่วมโครงการ ไม่ได้ยืนยันว่าผลประกอบการหรือขีดความสามารถดีขึ้น",
    C08_REPORTED_BUSINESSES: "มีเฉพาะยอดรวมแยกตามแต่ละมิติ ไม่มีรายชื่อหรือข้อมูลไขว้ระหว่างมิติ จึงห้ามบวกยอดแต่ละมิติเข้าด้วยกัน",
    C08_ASSESSED_PEOPLE: "คนหนึ่งอาจมีหลายแบบประเมิน จึงไม่นับจำนวนแบบประเมินเป็นจำนวนคน และแบบประเมินที่ไม่มีวันที่อาจไม่ใช่ข้อมูลล่าสุด",
    C08_INCREASED_PEOPLE: "เป็นกลุ่มย่อยของผู้ที่มีคะแนนก่อน–หลังครบ ไม่ใช่จำนวนธุรกิจ และข้อมูลที่หายไปไม่ได้แปลว่าไม่มีการเปลี่ยนแปลง",
    K09: "เป็นจำนวนการจ้างงาน ไม่ใช่รายได้ ไม่มีรายชื่อหรือการจัดสรรระดับจังหวัด และคำว่า “ต่อเดือน” ไม่ได้ระบุว่าเป็นเดือนปฏิทินใด",
    K10: "ตัวเลขอาศัยข้อสมมติว่ายอดรับในพื้นที่บวกกันได้และเป็นช่วงเดือนที่เทียบกันได้ จึงไม่ใช่รายได้สุทธิที่ยืนยันแล้ว",
    C10_ALTERNATIVE: "เป็นสูตรทางเลือกเพื่ออธิบายตัวเลขเดิม ความหมายของยอดที่แยกออกและช่วงเดือนยังเป็นข้อสมมติ ห้ามนำไปบวกกับ K10",
    K11A: "ป้ายหมวดอุตสาหกรรมยังไม่เพียงพอที่จะยืนยันตัวตนคลัสเตอร์ จึงแสดงว่าไม่มีข้อมูล ไม่ใช่ศูนย์",
    K11B: "จังหวัดที่มีหลักฐานโครงการทั่วไปใช้แทนจังหวัดที่มีคลัสเตอร์ไม่ได้ จึงแสดงว่าไม่มีข้อมูล ไม่ใช่ศูนย์",
    K12: "นับเรื่องหรือทุนวัฒนธรรมที่ทำแผนที่แล้ว ไม่ได้นับเว็บไซต์หรือระบบสารสนเทศ รายการที่อยู่หลายหมวดนับเพียงครั้งเดียว",
  };

  const text = (value) => value == null ? "" : String(value);
  const label = (key) => text(key).replaceAll("_", " ");
  const isObject = (value) => value && typeof value === "object" && !Array.isArray(value);
  const clear = (node) => { while (node.firstChild) node.removeChild(node.firstChild); return node; };
  const el = (tag, attrs, ...children) => {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      if (value == null || value === false) return;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = text(value);
      else if (key === "htmlFor") node.htmlFor = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? "" : text(value));
    });
    children.flat().forEach((child) => node.append(child?.nodeType ? child : document.createTextNode(text(child))));
    return node;
  };
  const valueText = (value) => Array.isArray(value) ? value.map(valueText).filter(Boolean).join(", ") : isObject(value) ? (value.name || value.label || value.title || value.value || "") : text(value);
  const hasValue = (value) => value !== null && value !== undefined && value !== "";
  const titleOf = (item) => item?.title || item?.name || item?.label || item?.headline || item?.id || "รายการ";
  const detailId = (item) => item?.entity_id || item?.id || item?.detail_id || item?.record_id || item?.identifier;
  const externalUrl = (value) => typeof value === "string" && /^https?:\/\//i.test(value) ? value : "";
  const selectedMeasureDefinition = () => allMeasureDefinitions().find((item) => item.measure_id === state.measure);
  const formattedCount = (value) => Number.isFinite(Number(value))
    ? new Intl.NumberFormat("th-TH").format(Number(value))
    : "";
  const allMeasureDefinitions = () => (state.overview?.headlines || []).flatMap((headline) => [headline, ...(headline.companions || [])]);
  const supportsProvince = (definition) => definition?.filter_contract?.supported_filters?.includes("province");
  const statusLabel = (value) => RESULT_STATUS_LABELS[value] || label(value);

  function status(view, heading, message, retry) {
    clear(view).append(el("div", { class: "f2-status", role: "status", "aria-live": "polite" }, el("strong", { text: heading }), el("p", { text: message }), retry ? el("button", { class: "f2-retry", type: "button", text: "ลองอีกครั้ง", onclick: retry }) : ""));
  }
  function abort(key) { state.controllers[key]?.abort(); }
  async function request(path, key) {
    abort(key);
    const controller = new AbortController();
    state.controllers[key] = controller;
    const current = (state.requests[key] || 0) + 1;
    state.requests[key] = current;
    const response = await fetch(`${API}${path}`, { headers: { Accept: "application/json" }, signal: controller.signal, cache: "no-store" });
    if (current !== state.requests[key]) throw Object.assign(new Error("stale"), { stale: true });
    if (response.status === 304) return null;
    const body = await response.json().catch(() => ({}));
    if (response.status === 409) state.revision = "";
    if (!response.ok) throw new Error(text(body.detail || body.message || `HTTP ${response.status}`));
    return body;
  }
  function query(params) {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => { if (hasValue(value)) search.set(key, value); });
    return search.toString() ? `?${search}` : "";
  }
  function apiScope(extra = {}) { return { measure: state.measure, province: state.province, revision: state.revision, ...state.filters, ...extra }; }
  function detailScope(extra = {}) { const { q, ...filters } = state.filters; return { measure: state.measure, province: state.province, revision: state.revision, ...filters, ...extra }; }
  function writeUrl(push = false) {
    const url = new URL(location.href);
    url.searchParams.set("mode", "f2");
    url.searchParams.set("f2tab", state.tab);
    ["f2measure", "province", "f2detail", "f2category", "f2source_level", "f2source_region", "f2component", "f2source_dimension", "f2q", "f2offset"].forEach((name) => url.searchParams.delete(name));
    if (state.measure) url.searchParams.set("f2measure", state.measure);
    if (state.province) url.searchParams.set("province", state.province);
    if (state.detail) url.searchParams.set("f2detail", state.detail);
    ["category", "source_level", "source_region", "component", "source_dimension", "q"].forEach((key) => { if (state.filters[key]) url.searchParams.set(`f2${key}`, state.filters[key]); });
    if (state.offset) url.searchParams.set("f2offset", state.offset);
    history[push ? "pushState" : "replaceState"]({}, "", url);
  }
  function restoreUrl() {
    const params = new URLSearchParams(location.search);
    state.tab = ["overview", "list", "sources"].includes(params.get("f2tab")) ? params.get("f2tab") : "overview";
    state.measure = params.get("f2measure") || "";
    state.province = params.get("province") || "";
    state.detail = params.get("f2detail") || "";
    state.filters = Object.fromEntries(["category", "source_level", "source_region", "component", "source_dimension", "q"].map((key) => [key, params.get(`f2${key}`)]).filter(([, value]) => value));
    state.searchDraft = state.filters.q || "";
    state.offset = Math.max(0, Number(params.get("f2offset")) || 0);
  }
  function setTab(tab, push = true) {
    state.tab = tab;
    Object.entries(views).forEach(([key, view]) => {
      const active = key === tab;
      view.hidden = !active;
      const button = $("f2-tab-" + key);
      button.setAttribute("aria-selected", String(active));
      button.tabIndex = active ? 0 : -1;
    });
    writeUrl(push);
    if (tab === "overview") loadOverview();
    if (tab === "list") loadTopic();
    if (tab === "sources") loadSources();
  }
  function renderBreadcrumbs(scope) {
    const crumb = $("f2Breadcrumbs"); clear(crumb);
    crumb.append(el("button", { type: "button", text: "ประเทศไทย", onclick: () => handleProvince("", true) }));
    const province = scope?.province_name_th || scope?.province || scope?.province_code || state.province;
    if (province) crumb.append(el("span", { text: province }));
  }
  function choices(contract, key, fallback) {
    const source = contract?.choices?.[key] || contract?.[key] || contract?.filters?.[key] || fallback?.choices?.[key] || fallback?.[key];
    const raw = Array.isArray(source) ? source : source?.options || source?.values || [];
    return raw.map((item) => isObject(item) ? { value: item.value ?? item.id ?? item.code ?? item.key, label: item.label_th ?? item.label ?? item.name ?? item.value ?? item.id } : { value: item, label: item });
  }
  function controls(data) {
    const host = $("f2Controls"); clear(host);
    const definition = selectedMeasureDefinition();
    const contract = data?.filter_contract || data?.filters || definition?.filter_contract || state.topicData?.filter_contract || {};
    const supportedFilters = Array.isArray(contract.supported_filters) ? contract.supported_filters : [];
    const headlineMeasures = allMeasureDefinitions().map((headline) => ({ value: headline.measure_id, label: headline.label_th || headline.label || headline.measure_id })).filter((item) => item.value);
    const measures = choices(contract, "measure", data?.measures || data?.available_measures).concat(headlineMeasures.filter((item) => !choices(contract, "measure", data?.measures || data?.available_measures).some((option) => option.value === item.value)));
    if (measures.length) {
      const select = el("select", { id: "f2Measure" }, el("option", { value: "", text: "เลือกตัวชี้วัด" }));
      measures.forEach((option) => select.append(el("option", { value: option.value, text: option.label, selected: option.value === state.measure }))); select.value = state.measure;
      select.addEventListener("change", () => changeMeasure(select.value));
      host.append(el("label", { htmlFor: "f2Measure", text: "ตัวชี้วัด" }, select));
    }
    if (supportedFilters.includes("province")) {
      const provinces = (state.callbacks.getProvinces?.() || [])
        .map((province) => ({ value: text(province.province_code), label: text(province.province_name_th) }))
        .filter((province) => province.value && province.label)
        .sort((a, b) => a.label.localeCompare(b.label, "th"));
      const provinceSelect = el("select", { id: "f2Province" }, el("option", { value: "", text: "ทั่วประเทศ" }));
      provinces.forEach((province) => provinceSelect.append(el("option", { value: province.value, text: province.label })));
      provinceSelect.value = state.province;
      provinceSelect.addEventListener("change", () => handleProvince(provinceSelect.value, true));
      host.append(el("label", {
        class: "f2-province",
        htmlFor: "f2Province",
        text: state.measure === C02_MEASURE_ID ? "จังหวัดที่ต้นทางระบุสำหรับนวัตกร" : "จังหวัด",
      }, provinceSelect));
    }
    supportedFilters.filter((key) => ["category", "source_level", "source_region", "component", "source_dimension"].includes(key)).forEach((key) => {
      const prepared = data?.prepared_filters?.[state.measure]?.choices?.[key] || state.topicData?.prepared_filters?.[state.measure]?.choices?.[key];
      const options = choices(contract, key, { ...(data?.filters || {}), [key]: data?.filters?.[key] || prepared });
      const id = "f2-" + key;
      const select = el("select", { id }, el("option", { value: "", text: "ทั้งหมด" }));
      options.forEach((option) => {
        const codeOnly = key === "category" && String(option.label) === String(option.value);
        select.append(el("option", { value: option.value, text: codeOnly ? `รหัสต้นทาง ${option.label}` : option.label }));
      }); select.value = state.filters[key] || "";
      select.addEventListener("change", () => { state.filters[key] = select.value; state.offset = 0; if (!select.value) delete state.filters[key]; writeUrl(true); loadMap(); if (state.tab === "list") loadTopic(); });
      host.append(el("label", { htmlFor: id, text: FILTER_LABELS[key] || label(key) }, select));
    });
    const searchable = data?.list?.capability === "available" || (!data?.list && definition?.filter_contract?.detail_availability === "available");
    if (state.tab === "list" && searchable) {
      const input = el("input", { id: "f2Search", type: "search", value: state.searchDraft, placeholder: "ค้นหาในรายการ", autocomplete: "off" });
      input.addEventListener("input", () => {
        state.searchDraft = input.value;
        clearTimeout(state.searchTimer);
        state.searchTimer = setTimeout(() => {
          state.filters.q = state.searchDraft;
          state.offset = 0;
          if (!state.searchDraft) delete state.filters.q;
          writeUrl(true);
          loadTopic();
        }, 300);
      });
      host.append(el("label", { class: "f2-search", htmlFor: "f2Search", text: "ค้นหา" }, input));
    }
  }
  function cardFor(value, fallbackTitle) {
    const card = el("article", { class: "f2-generic-card" });
    if (!isObject(value)) { card.append(el("h4", { text: fallbackTitle }), el("p", { text: valueText(value) || "ไม่มีข้อมูล" })); return card; }
    card.append(el("h4", { text: value.title_th || value.label_th || value.title || value.label || value.name || fallbackTitle }));
    const summary = value.description || value.summary || value.note || value.display_value || valueText(value.value);
    if (summary) card.append(el("p", { text: summary }));
    if (value.unit) card.append(el("small", { text: value.unit }));
    return card;
  }
  function renderMetadata(data, omit = []) {
    const dl = el("dl", { class: "f2-metadata" });
    Object.entries(data || {}).forEach(([key, value]) => {
      if (omit.includes(key) || !hasValue(value) || typeof value === "object") return;
      dl.append(el("dt", { text: label(key) }), el("dd", { text: valueText(value) }));
    });
    return dl.childNodes.length ? dl : null;
  }
  function section(title, content, note) { const node = el("section", { class: "f2-section" }, el("h3", { text: title })); if (note) node.append(note?.nodeType ? note : el("p", { text: note })); if (content) node.append(content); return node; }
  function selectMeasure(measure) {
    state.measure = measure;
    const selected = allMeasureDefinitions().find((headline) => headline.measure_id === measure);
    if (selected?.topic_id) state.topic = selected.topic_id;
  }
  function changeMeasure(measure) {
    selectMeasure(measure);
    state.filters = {};
    state.searchDraft = "";
    state.offset = 0;
    const definition = selectedMeasureDefinition();
    if (state.province && !supportsProvince(definition)) {
      const provinceName = (state.callbacks.getProvinces?.() || []).find((province) => text(province.province_code) === state.province)?.province_name_th || "จังหวัดที่เลือก";
      state.province = "";
      state.scopeNotice = `${definition?.label_th || "ตัวชี้วัดนี้"} ไม่มีข้อมูลระดับจังหวัด ระบบจึงเปลี่ยนจาก ${provinceName} เป็นมุมมองประเทศไทย`;
      state.callbacks.onProvinceRestore?.("");
    } else {
      state.scopeNotice = "";
    }
    writeUrl(true);
    loadOverview();
  }
  function renderOverview(data) {
    const view = views.overview; clear(view); renderBreadcrumbs(data.requested_scope || {});
    const headlines = Array.isArray(data.headlines) ? data.headlines : [];
    if (!state.measure && headlines.length) selectMeasure((headlines.find((headline) => headline.measure_id === "K01A") || headlines[0]).measure_id);
    else selectMeasure(state.measure);
    controls(data);
    const groups = [
      ["พื้นที่ ภูมิศาสตร์ และทุนวัฒนธรรม", ["K01A", "K01B", "K12"]],
      ["คน กิจกรรม และนวัตกรรม", ["K02", "K03", "K04"]],
      ["ธุรกิจและข้อเสนอ", ["K05", "K06", "K07", "K08"]],
      ["การจ้างงานและการจ่ายเงิน", ["K09", "K10"]],
      ["คลัสเตอร์", ["K11A", "K11B"]],
    ];
    groups.forEach(([title, ids]) => {
      const rows = headlines.filter((headline) => ids.includes(headline.measure_id));
      if (!rows.length) return;
      const group = el("div", { class: "f2-headlines" });
      const appendMetric = (item, companion = false) => {
        const result = item.result || {};
        const unavailable = result.unavailable_reason?.message_th || result.unavailable_reason;
        const metric = el("button", {
          class: `f2-metric${companion ? " f2-metric--companion" : ""}`,
          type: "button",
          "data-f2-measure": item.measure_id,
          onclick: () => {
            changeMeasure(item.measure_id);
            setTab("list");
            loadMap();
          },
        });
        metric.append(
          el("span", { text: item.label_th || item.measure_id }),
          el("strong", { text: valueText(result.display_value ?? result.value) || "—" }),
        );
        if (item.unit || result.unit || unavailable) {
          metric.append(el("small", { text: item.unit || result.unit || unavailable }));
        }
        if (item.measure_id === C02_MEASURE_ID) {
          metric.append(el("span", { class: "f2-metric-action", text: "ดูรายชื่อ →" }));
        }
        group.append(metric);
      };
      rows.forEach((item) => {
        appendMetric(item);
        (item.companions || []).forEach((companion) => appendMetric(companion, true));
      });
      view.append(section(title, group));
    });
    if (!headlines.length) view.append(section("ภาพรวม", null, "ยังไม่มีข้อมูลสรุปสำหรับขอบเขตที่เลือก"));
  }
  async function loadOverview() {
    if (!state.open) return;
    status(views.overview, "กำลังโหลดภาพรวม", "กำลังขอข้อมูลจากระบบ");
    try {
      const data = await request("/overview" + query({ province: state.province, revision: state.revision }), "overview");
      if (!data) return;
      state.overview = data;
      state.revision = data.revision || state.revision;
      renderOverview(data);
      loadMap();
      if (state.tab === "list") await loadTopic();
      if (state.tab === "sources") await loadSources();
      if (state.detail) openDetail(state.detail, false);
    } catch (error) {
      if (!error.stale && error.name !== "AbortError") status(views.overview, "เปิดภาพรวมไม่ได้", error.message, loadOverview);
    }
  }
  async function loadMap() {
    const selected = selectedMeasureDefinition();
    if (!selected || selected.map_availability !== "province") {
      state.callbacks.onMapData?.({
        measure_id: state.measure,
        map_available: false,
        unit: selected?.result?.unit || selected?.unit || "",
        cells: [],
        legend: {
          label_th: selected?.label_th || "ข้อมูลฝ่าย 2",
          meaning_th: selected?.result?.unavailable_reason?.message_th || "มาตรวัดนี้ไม่มีแผนที่รายจังหวัด",
        },
      });
      return;
    }
    const { q, ...mapFilters } = state.filters;
    try {
      const data = await request("/map" + query({ measure: state.measure, revision: state.revision, ...mapFilters }), "map");
      if (data) state.callbacks.onMapData?.({ ...data, map_available: true });
    } catch (error) {
      if (!error.stale && error.name !== "AbortError") console.warn("F2 map data unavailable", error);
    }
  }
  function itemCard(item) {
    const id = detailId(item);
    const model = window.F2DetailPresenter?.presentListItem?.(state.measure, item) || {
      title: titleOf(item),
      context: [],
      warning: "",
      action: "ดูรายละเอียด",
    };
    const card = el(
      id ? "button" : "article",
      id
        ? {
            class: "f2-item",
            type: "button",
            "data-f2-detail-id": id,
            "aria-label": `${model.action} ${model.title}`,
            onclick: () => openDetail(id),
          }
        : { class: "f2-item" },
    );
    card.append(el("h3", { text: model.title }));
    if (model.context?.length) {
      card.append(el("p", { class: "f2-item-context", text: model.context.join(" · ") }));
    }
    if (model.warning) {
      card.append(el("span", { class: "f2-item-warning", text: model.warning }));
    }
    if (id) card.append(el("span", { class: "f2-item-action", text: `${model.action} →` }));
    return card;
  }
  function captureSearchFocus() {
    const input = $("f2Search");
    if (!input || document.activeElement !== input) return null;
    return { start: input.selectionStart, end: input.selectionEnd, direction: input.selectionDirection };
  }
  function restoreSearchFocus(selection) {
    if (!selection) return;
    const input = $("f2Search");
    if (!input) return;
    input.focus({ preventScroll: true });
    const length = input.value.length;
    input.setSelectionRange(Math.min(selection.start ?? length, length), Math.min(selection.end ?? length, length), selection.direction || "none");
  }
  function restorePendingListFocus() {
    if (!state.pendingListFocus) return;
    const target = [...views.list.querySelectorAll("[data-f2-detail-id]")].find((node) => node.dataset.f2DetailId === state.pendingListFocus);
    if (!target) return;
    state.pendingListFocus = "";
    state.returnFocus = target;
    target.focus({ preventScroll: true });
  }
  function renderList(data) {
    const searchSelection = captureSearchFocus();
    const view = views.list; clear(view); controls(data); restoreSearchFocus(searchSelection); const list = data.list || {}; const items = Array.isArray(list.items) ? list.items : [];
    const definition = selectedMeasureDefinition();
    const measureSupportsProvince = supportsProvince(definition);
    const requestedProvince = state.province
      ? (state.callbacks.getProvinces?.() || []).find((province) => text(province.province_code) === state.province)?.province_name_th || state.overview?.requested_scope?.province_name_th
      : "";
    if (state.measure === C02_MEASURE_ID) {
      const coverage = data.coverage || definition?.coverage || {};
      const national = formattedCount(coverage.national_total);
      const withProvince = formattedCount(coverage.with_province);
      const withoutProvince = formattedCount(coverage.without_province);
      const context = el("ul", { class: "f2-c02-context" },
        el("li", { text: C02_SOURCE_PROVINCE_MEANING }),
      );
      if (national && withProvince && withoutProvince) {
        context.append(el("li", { text: `จากทั้งหมด ${national} คน มี ${withProvince} คนที่มีข้อมูลจังหวัด ส่วนอีก ${withoutProvince} คนจะแสดงเฉพาะในยอดรวมประเทศ` }));
      }
      context.append(el("li", { text: "บางคนมีข้อมูลมากกว่าหนึ่งจังหวัด จึงไม่ควรนำยอดรายจังหวัดมาบวกกัน" }));
      view.append(section("ข้อมูลจังหวัดในทะเบียน", context));
    }
    renderScopeNotice(view);
    const resultNote = state.measure === C02_MEASURE_ID && requestedProvince
      ? `${requestedProvince} ${formattedCount(data.result?.value) || "—"} คน · ทั้งประเทศ ${formattedCount(data.coverage?.national_total) || "—"} คน`
      : measureSupportsProvince && data.coverage?.province_sum_is_additive === false
        ? "ค่าระดับประเทศและผลรวมรายจังหวัดอาจไม่เท่ากัน"
        : "";
    view.append(section(
      "ผลตัวชี้วัด",
      cardFor(data.result, definition?.label_th || data.measure_id),
      resultNote,
    ));
    if (Array.isArray(data.source_region_results) && data.source_region_results.length) {
      const table = el("table", { class: "f2-source-region-table" });
      table.append(el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "ภูมิภาคตามต้นทาง" }), el("th", { scope: "col", text: "ค่า" }), el("th", { scope: "col", text: "สถานะ" }))));
      table.append(el("tbody", {}, data.source_region_results.map((row) => el("tr", {}, el("th", { scope: "row", text: row.label_th }), el("td", { text: [row.result?.display_value || "—", row.result?.unit].filter(Boolean).join(" ") }), el("td", { text: statusLabel(row.result?.status || row.result?.availability || "") || "—" })))));
      view.append(section("ตารางภูมิภาคตามต้นทาง", el("div", { class: "f2-table-scroll", tabindex: "0" }, table), "ภูมิภาคตามต้นทางไม่ใช่ภาคของแดชบอร์ด"));
    }
    if (!list.capability || ["none", "unavailable", "aggregate_only"].includes(list.capability)) {
      const unavailable = data.availability === "unavailable" || data.result?.availability === "unavailable";
      view.append(section("รายการ", null, unavailable
        ? "ยังไม่มีข้อมูลเพียงพอสำหรับคำนวณตัวชี้วัดนี้ จึงไม่มีตัวเลขหรือรายการให้ค้นหา"
        : "ตัวชี้วัดนี้มีเฉพาะยอดรวม ไม่มีรายการรายชื่อให้ค้นหา"));
      return;
    }
    if (!items.length) {
      view.append(section("รายการ", null, el("p", { class: "f2-results-summary", role: "status", "aria-live": "polite", text: "ไม่พบรายการที่ตรงกับเงื่อนไขการค้นหา" })));
      return;
    }
    view.append(section("รายการ", el("div", { class: "f2-item-list" }, items.map(itemCard)), el("p", { class: "f2-results-summary", role: "status", "aria-live": "polite", text: `${list.matching_item_count ?? items.length} รายการที่ตรงเงื่อนไข` })));
    const previous = el("button", { type: "button", "aria-label": "หน้าก่อนหน้า", text: "ก่อนหน้า", disabled: !list.offset, onclick: () => { state.offset = Math.max(0, Number(list.offset || 0) - state.limit); writeUrl(true); loadTopic(); } });
    const next = el("button", { type: "button", "aria-label": "หน้าถัดไป", text: "ถัดไป", disabled: Number(list.offset || 0) + Number(list.returned_count || items.length) >= Number(list.matching_item_count || 0), onclick: () => { state.offset = Number(list.offset || 0) + Number(list.returned_count || items.length); writeUrl(true); loadTopic(); } });
    view.append(el("nav", { class: "f2-pagination", "aria-label": "เปลี่ยนหน้ารายการ" }, previous, el("span", { text: `แสดง ${Number(list.offset || 0) + 1}–${Number(list.offset || 0) + items.length}` }), next));
    restorePendingListFocus();
  }
  function renderScopeNotice(view) {
    if (!state.scopeNotice) return;
    view.append(el("div", { class: "f2-scope-notice", role: "status" }, el("strong", { text: "ปรับขอบเขตข้อมูลแล้ว" }), el("p", { text: state.scopeNotice })));
    state.scopeNotice = "";
  }
  function recoverUnsupportedProvince(error) {
    if (!state.province || !/unsupported|filter combination|ตัวกรอง/.test(error.message)) return false;
    const definition = selectedMeasureDefinition();
    const provinceName = (state.callbacks.getProvinces?.() || []).find((province) => text(province.province_code) === state.province)?.province_name_th || "จังหวัดที่เลือก";
    state.province = "";
    state.scopeNotice = `${definition?.label_th || "ตัวชี้วัดนี้"} ไม่มีข้อมูลระดับจังหวัด ระบบจึงเปลี่ยนจาก ${provinceName} เป็นมุมมองประเทศไทย`;
    state.callbacks.onProvinceRestore?.("");
    writeUrl(false);
    loadOverview();
    return true;
  }
  async function loadTopic() {
    if (!state.open || state.tab !== "list" || !state.topic) { if (!state.topic) status(views.list, "ยังไม่มีหัวข้อรายการ", "เลือกตัวชี้วัดจากภาพรวมก่อน"); return; }
    status(views.list, "กำลังโหลดรายการ", "กำลังขอข้อมูลตามเงื่อนไขที่เลือก");
    try { const data = await request(`/topics/${encodeURIComponent(state.topic)}` + query(apiScope({ limit: state.limit, offset: state.offset })), "topic"); if (!data) return; state.topicData = data; state.revision = data.revision || state.revision; renderList(data); }
    catch (error) {
      if (error.stale || error.name === "AbortError") return;
      if (recoverUnsupportedProvince(error)) return;
      status(views.list, "เปิดรายการไม่ได้", "ระบบยังเปิดรายการนี้ไม่ได้ โปรดลองอีกครั้ง", loadTopic);
    }
  }
  function appendLinks(container, value) {
    const rows = Array.isArray(value) ? value : isObject(value) ? Object.values(value) : [value];
    const links = rows.map((row) => typeof row === "string" ? { url: row, label: row } : row).filter((row) => externalUrl(row?.url || row?.href || row?.link || row?.public_url));
    if (links.length) container.append(el("ul", { class: "f2-links" }, links.map((row) => el("li", {}, el("a", { href: externalUrl(row.url || row.href || row.link || row.public_url), target: "_blank", rel: "noopener noreferrer", text: row.label_th || row.label || row.title || row.source_id || row.url || row.href || row.link || row.public_url })))));
  }
  async function loadSources() {
    if (!state.topic) {
      renderSources();
      return;
    }
    const current = state.topicData;
    if (current?.topic_id === state.topic && current?.measure_id === state.measure && current?.scope === (state.province ? `province/${state.province}` : "national")) {
      renderSources();
      return;
    }
    status(views.sources, "กำลังโหลดที่มา", "กำลังขอคำจำกัดความและแหล่งข้อมูล");
    try {
      const data = await request(`/topics/${encodeURIComponent(state.topic)}` + query(detailScope()), "topic");
      if (!data) return;
      state.topicData = data;
      renderSources();
    } catch (error) {
      if (error.stale || error.name === "AbortError") return;
      if (recoverUnsupportedProvince(error)) return;
      status(views.sources, "เปิดที่มาไม่ได้", "ระบบยังเปิดที่มานี้ไม่ได้ โปรดลองอีกครั้ง", loadSources);
    }
  }
  function renderSources() {
    const view = views.sources; clear(view); controls(state.topicData || state.overview || {});
    renderScopeNotice(view);
    const data = state.topicData || state.overview || {};
    const definition = selectedMeasureDefinition();
    if (definition) {
      const geography = supportsProvince(definition)
        ? "ดูได้ทั้งประเทศไทยและจังหวัดที่แหล่งข้อมูลรองรับ"
        : definition.filter_contract?.supported_filters?.includes("source_region")
          ? "ดูได้ระดับประเทศไทยและภูมิภาคตามที่แหล่งข้อมูลรายงาน ไม่ใช่ระดับจังหวัด"
          : "แสดงตามขอบเขตที่แหล่งข้อมูลรองรับ โดยไม่มีตัวเลขระดับจังหวัด";
      view.append(section("ตัวเลขนี้หมายถึงอะไร", el("div", { class: "f2-source-summary" },
        el("p", { text: definition.label_th || state.measure }),
        el("dl", { class: "f2-detail-facts" },
          el("dt", { text: "หน่วย" }), el("dd", { text: definition.unit || data.result?.unit || "ไม่ระบุ" }),
          el("dt", { text: "ขอบเขตพื้นที่" }), el("dd", { text: geography }),
        ),
      )));
    }
    if (state.measure === C02_MEASURE_ID) {
      view.append(section(
        "ข้อควรทราบ",
        el("p", { text: "ข้อมูลชุดนี้มีนิยามต่างจาก K02 จึงไม่ควรนำตัวเลขของทั้งสองชุดมารวมกัน" }),
      ));
    }
    const sources = Array.isArray(data.sources) ? data.sources : [];
    if (sources.length) {
      const sourceCards = el("div", { class: "f2-source-cards" });
      sources.forEach((source) => {
        const sourceName = SOURCE_NAMES[source.source_id] || source.label_th || source.label || "แหล่งข้อมูลต้นทาง";
        const link = externalUrl(source.public_url);
        sourceCards.append(el("article", { class: "f2-generic-card" },
          el("h4", { text: sourceName }),
          source.originating_system ? el("p", { text: `ระบบต้นทาง: ${source.originating_system}` }) : "",
          link ? el("a", { href: link, target: "_blank", rel: "noopener noreferrer", text: "เปิดแหล่งข้อมูลต้นทาง" }) : "",
        ));
      });
      view.append(section("แหล่งข้อมูล", sourceCards));
    }
    const releaseDate = data.provenance?.release_date;
    if (releaseDate) {
      view.append(section("วันที่ของข้อมูล", el("div", { class: "f2-source-summary" },
        el("p", { text: `ฉบับข้อมูลที่ระบบกำลังแสดงจัดเตรียมวันที่ ${releaseDate}` }),
        el("p", { text: "วันที่นี้เป็นวันที่จัดเตรียมฉบับข้อมูล ไม่ใช่ช่วงเวลาที่ตัวเลขวัด เว้นแต่แหล่งข้อมูลจะระบุช่วงเวลาไว้โดยตรง" }),
      )));
    }
    const limitation = MEASURE_LIMITATIONS[state.measure];
    if (limitation) view.append(section("ข้อจำกัดที่ควรรู้ก่อนนำไปใช้", el("p", { class: "f2-plain-limitation", text: limitation })));
    const technical = {
      formula: definition?.formula,
      source_scope: definition?.scope,
      filter_contract: definition?.filter_contract,
      coverage: data.coverage,
      availability: data.availability,
      provenance: data.provenance,
      source_notes: data.limitations,
    };
    if (Object.values(technical).some(hasValue)) {
      view.append(el("details", { class: "f2-detail-technical f2-source-technical" },
        el("summary", { text: "สูตร รหัส และรายละเอียดทางเทคนิค" }),
        genericDetail(technical),
      ));
    }
    if (!view.childNodes.length) view.append(section("ที่มาและข้อจำกัด", null, "ยังไม่มีข้อมูลที่มาและข้อจำกัดสำหรับขอบเขตนี้"));
  }
  function genericDetail(value, depth = 0) {
    if (!isObject(value) && !Array.isArray(value)) return el("p", { text: valueText(value) || "ไม่มีข้อมูล" });
    const wrap = el("div", { class: "f2-section" });
    (Array.isArray(value) ? value.map((item, index) => [String(index + 1), item]) : Object.entries(value)).forEach(([key, item]) => {
      if (["url", "href", "link", "public_url", "media_url", "thumbnail"].includes(key)) return;
      if (depth < 6 && (isObject(item) || Array.isArray(item))) {
        const nested = genericDetail(item, depth + 1);
        if ((Array.isArray(item) && item.length > 3) || (isObject(item) && Object.keys(item).length > 5)) {
          wrap.append(el("details", { class: "f2-detail-group" }, el("summary", { text: `${label(key)} (${Array.isArray(item) ? item.length : Object.keys(item).length})` }), nested));
        } else {
          wrap.append(section(label(key), nested));
        }
      } else {
        wrap.append(el("div", { class: "f2-generic-card" }, el("h4", { text: label(key) }), el("p", { text: valueText(item) || "ไม่มีข้อมูล" })));
      }
    });
    appendLinks(wrap, value);
    return wrap;
  }
  function detailFacts(facts) {
    const rows = (facts || []).filter((fact) => fact?.label && hasValue(fact.value));
    if (!rows.length) return null;
    return el("dl", { class: "f2-detail-facts" }, rows.flatMap((fact) => [
      el("dt", { text: fact.label }),
      el("dd", { text: valueText(fact.value) }),
    ]));
  }
  function detailLinks(links) {
    const rows = (links || []).filter((link) => externalUrl(link?.url));
    if (!rows.length) return null;
    return el("ul", { class: "f2-detail-links" }, rows.map((link) =>
      el("li", {}, el("a", {
        href: externalUrl(link.url),
        target: "_blank",
        rel: "noopener noreferrer",
        text: link.label || "ดูข้อมูลจากแหล่งต้นทาง",
      })),
    ));
  }
  function openTargetDetail(target) {
    if (!isObject(target) || !text(target.topicId) || !text(target.measureId) || !text(target.entityId)) return;
    state.topic = text(target.topicId);
    state.measure = text(target.measureId);
    state.province = "";
    state.filters = {};
    state.offset = 0;
    openDetail(text(target.entityId), true);
  }

  function detailItem(item, kind) {
    if (kind === "tags") return el("span", { class: "f2-detail-badge", text: item.value });
    if (kind === "links") return null;
    const card = el("article", { class: `f2-detail-item f2-detail-item--${kind}` });
    if (item.title) card.append(el("h4", { text: item.title }));
    if (item.subtitle) card.append(el("p", { class: "f2-detail-subtitle", text: item.subtitle }));
    if (item.text) card.append(el("p", { class: "f2-detail-prose", text: item.text }));
    const facts = detailFacts(item.facts);
    if (facts) card.append(facts);
    const links = detailLinks(item.links);
    if (links) card.append(links);
    if (item.note) card.append(el("p", { class: "f2-detail-note", text: item.note }));
    if (item.targetDetail) {
      card.append(el("button", {
        class: "f2-item-action",
        type: "button",
        text: "ดูรายละเอียดผลงาน",
        onclick: () => openTargetDetail(item.targetDetail),
      }));
    }
    return card;
  }
  function renderDetailPresentation(model) {
    const article = el("article", { class: "f2-human-detail" });
    const intro = el("header", { class: "f2-detail-intro" });
    if (model.eyebrow) intro.append(el("p", { class: "f2-detail-eyebrow", text: model.eyebrow }));
    if ((model.badges || []).length) {
      intro.append(el("div", { class: "f2-detail-badges", "aria-label": "ประเภทและสถานะ" },
        model.badges.map((badge) => el("span", { class: "f2-detail-badge", text: badge })),
      ));
    }
    const facts = detailFacts(model.facts);
    if (facts) intro.append(facts);
    if (intro.childNodes.length) article.append(intro);
    (model.sections || []).forEach((group) => {
      const content = el("section", { class: `f2-detail-section f2-detail-section--${group.kind || "cards"}` },
        el("h3", { text: group.title }),
      );
      if (group.note) content.append(el("p", { class: "f2-detail-note", text: group.note }));
      if (group.kind === "links") {
        const links = detailLinks(group.items);
        if (links) content.append(links);
      } else {
        const items = el("div", { class: "f2-detail-items" });
        group.items.forEach((item) => {
          const rendered = detailItem(item, group.kind || "cards");
          if (rendered) items.append(rendered);
        });
        if (items.childNodes.length) content.append(items);
      }
      article.append(content);
    });
    if ((model.notices || []).length) {
      article.append(el("section", { class: "f2-detail-section" },
        el("h3", { text: "สถานะและข้อควรทราบ" }),
        el("div", { class: "f2-detail-notices" }, model.notices.map((notice) =>
          el("p", { class: `f2-detail-notice f2-detail-notice--${notice.tone || "info"}`, text: notice.text }),
        )),
      ));
    }
    if ((model.sources || []).length) {
      const links = detailLinks(model.sources);
      if (links) article.append(el("section", { class: "f2-detail-section" }, el("h3", { text: "ที่มา" }), links));
    }
    if (model.technical && Object.values(model.technical).some(hasValue)) {
      article.append(el("details", { class: "f2-detail-technical" },
        el("summary", { text: "รายละเอียดทางเทคนิคและการตรวจสอบย้อนกลับ" }),
        genericDetail(model.technical),
      ));
    }
    return article;
  }
  async function openDetail(id, pushHistory = true) {
    if (!state.topic) return;
    const sheet = $("f2DetailSheet");
    if (sheet.hidden) state.returnFocus = document.activeElement;
    state.detail = text(id);
    state.detailHistory = pushHistory;
    if (pushHistory) writeUrl(true);
    sheet.hidden = false; $("f2DetailBody").replaceChildren(el("div", { class: "f2-status", text: "กำลังโหลดรายละเอียด" }));
    try {
      const data = await request(`/topics/${encodeURIComponent(state.topic)}/details/${encodeURIComponent(id)}` + query(detailScope()), "detail");
      if (!data) return;
      if (!window.F2DetailPresenter?.present) throw new Error("ไม่พบตัวจัดรูปแบบรายละเอียด");
      const model = window.F2DetailPresenter.present(data.measure_id || state.measure, data.detail || data, data.provenance || {});
      $("f2DetailTitle").textContent = model.title || titleOf(data.detail || data);
      $("f2DetailBody").replaceChildren(renderDetailPresentation(model));
      sheet.querySelector("button").focus();
    }
    catch (error) { if (!error.stale && error.name !== "AbortError") $("f2DetailBody").replaceChildren(el("div", { class: "f2-status" }, el("strong", { text: "เปิดรายละเอียดไม่ได้" }), el("p", { text: error.message }), el("button", { class: "f2-retry", type: "button", text: "ลองอีกครั้ง", onclick: () => openDetail(id, false) }))); }
  }
  function closeDetail(fromHistory = false) {
    const sheet = $("f2DetailSheet");
    if (sheet.hidden) return;
    const closedDetailId = state.detail;
    const shouldGoBack = state.detailHistory && !fromHistory;
    abort("detail");
    sheet.hidden = true;
    state.detail = "";
    state.detailHistory = false;
    if (shouldGoBack) {
      state.pendingListFocus = closedDetailId;
      history.back();
      return;
    }
    if (!fromHistory) writeUrl(false);
    state.returnFocus?.focus?.({ preventScroll: true });
  }
  function handleProvince(code, notifyHost = false) {
    const nextProvince = text(code || "");
    const changed = nextProvince !== state.province;
    state.province = nextProvince;
    if (state.province) delete state.filters.source_region;
    if (changed) state.offset = 0;
    if (notifyHost) {
      state.callbacks.onProvinceSelect?.(state.province);
      return;
    }
    writeUrl(true);
    if (state.open) loadOverview();
  }
  function open(options = {}) {
    state.returnFocus = document.activeElement;
    restoreUrl();
    if (options.provinceCode !== undefined && !new URLSearchParams(location.search).has("province")) state.province = text(options.provinceCode);
    state.open = true;
    panel.hidden = false;
    panel.setAttribute("aria-hidden", "false");
    document.body.classList.add("f2-dashboard-open");
    setTab(state.tab, false);
    if (state.tab !== "overview") loadOverview();
  }
  function close() { state.open = false; ["overview", "map", "topic", "detail"].forEach(abort); closeDetail(true); panel.hidden = true; panel.setAttribute("aria-hidden", "true"); document.body.classList.remove("f2-dashboard-open"); state.callbacks.onClose?.(); }
  function init(callbacks = {}) {
    state.callbacks = callbacks;
    const tabs = [...document.querySelectorAll("[data-f2-tab]")];
    tabs.forEach((button, index) => button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const target = event.key === "Home"
        ? 0
        : event.key === "End"
          ? tabs.length - 1
          : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
      tabs[target].focus();
      setTab(tabs[target].dataset.f2Tab);
    }));
    tabs.forEach((button) => button.addEventListener("click", () => setTab(button.dataset.f2Tab)));
    $("f2FiltersToggle")?.addEventListener("click", () => {
      const button = $("f2FiltersToggle");
      const expanded = button.getAttribute("aria-expanded") !== "true";
      button.setAttribute("aria-expanded", String(expanded));
      if (expanded) $("f2Controls")?.querySelector("select, input")?.focus({ preventScroll: true });
    });
    document.querySelectorAll("[data-f2-close]").forEach((button) => button.addEventListener("click", close));
    document.querySelectorAll("[data-f2-detail-close]").forEach((button) => button.addEventListener("click", () => closeDetail()));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !$("f2DetailSheet").hidden) closeDetail();
    });
    $("f2DetailSheet").addEventListener("keydown", (event) => {
      if (event.key !== "Tab") return;
      const sheet = $("f2DetailSheet");
      const focusable = [...sheet.querySelectorAll("button, a[href], summary")]
        .filter((node) => {
          if (node.hidden || node.tabIndex === -1 || !node.getClientRects().length) return false;
          for (let parent = node.parentElement; parent && parent !== sheet; parent = parent.parentElement) {
            if (parent.matches("details:not([open])") && parent.querySelector(":scope > summary") !== node) return false;
          }
          return true;
        });
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
    window.addEventListener("popstate", () => {
      if (!state.open) return;
      const activeTab = [...document.querySelectorAll("[data-f2-tab]")]
        .find((button) => button.getAttribute("aria-selected") === "true")?.dataset.f2Tab;
      restoreUrl();
      selectMeasure(state.measure);
      state.callbacks.onProvinceRestore?.(state.province);
      state.detailHistory = false;
      if (state.detail) {
        if (activeTab !== state.tab) setTab(state.tab, false);
        openDetail(state.detail, false);
      } else {
        closeDetail(true);
        if (activeTab !== state.tab) setTab(state.tab, false);
        else loadOverview();
      }
    });
  }
  window.F2Dashboard = { init, open, close, handleProvince, isOpen: () => state.open };
})();
