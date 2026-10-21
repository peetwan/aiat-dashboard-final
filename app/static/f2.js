(() => {
  "use strict";
  const API = "/api/public/v1/f2";
  const $ = (id) => document.getElementById(id);
  const panel = $("f2DashboardPanel");
  const views = { overview: $("f2-view-overview"), areas: $("f2-view-areas"), universities: $("f2-view-universities"), innovations: $("f2-view-innovations"), list: $("f2-view-list"), sources: $("f2-view-sources") };
  const state = { open: false, tab: "overview", province: "", measure: "", topic: "", detail: "", detailHistory: false, revision: "", overview: null, topicData: null, filterChoices: {}, choiceFailures: {}, controllers: {}, requests: {}, returnFocus: null, pendingListFocus: "", callbacks: {}, filters: {}, searchDraft: "", searchTimer: null, scopeNotice: "", offset: 0, limit: 25, sort: "source", rememberedProvince: "", overviewScroll: 0, overviewTopic: "", filterDraft: null, coverageData: null, openCoverage: false, universities: null, university: "", universityOffset: 0, universityQuery: "", universitySearch: "", universityFocus: "", mapData: null, areaUniversities: null, areaShowAll: false, areaFocus: "", innovationFilters: {}, innovationOffset: 0, innovationFocus: "" };
  const C02_MEASURE_ID = "C02_COMMUNITY";
  const C02_SOURCE_PROVINCE_MEANING = "จังหวัดที่แสดงเป็นจังหวัดที่แหล่งข้อมูลระบุไว้ในทะเบียน ไม่ใช่ที่อยู่หรือสถานที่ทำงานปัจจุบัน";
  const K12_DISPLAY_LABEL = "รายการทุนวัฒนธรรมบนแผนที่";
  const MEASURE_DISPLAY_LABELS = {
    K05: "ธุรกิจและกลุ่มผู้ประกอบการวัฒนธรรม",
    K06: "บุคคลที่เป็นผู้ประกอบการวัฒนธรรม",
    K12: K12_DISPLAY_LABEL,
  };
  const OVERVIEW_GROUPS = [
    ["พื้นที่และทุนวัฒนธรรม", ["K01B", "K12"]],
    ["คน กิจกรรม และนวัตกรรม", ["K02", "K03", "K04"]],
    ["ธุรกิจและข้อเสนอ", ["K05", "K06", "K07", "K08"]],
    ["การจ้างงานและการจ่ายเงิน", ["K09", "K10"]],
    ["ครัวเรือนเป้าหมายและตัวเลขเศรษฐกิจที่ PMUA AppTech รายงาน", ["H01"]],
    ["คลัสเตอร์", ["K11A", "K11B"]],
  ];
  const COMPANION_NOTES = {
    K02: "รายชื่อในทะเบียนชุมชนเป็นข้อมูลคนละชุดกับยอดรวมนวัตกรที่ PMUA รายงาน จึงนำตัวเลขมาบวกหรือลบกันไม่ได้",
    K04: "ยอดรายการนวัตกรรมทั้งหมดรวมรายการที่ผ่านเกณฑ์ความพร้อมแล้ว จึงไม่ควรนำสองยอดมาบวกกัน",
    K08: "ตัวเลขประกอบเหล่านี้บอกการเข้าร่วม จำนวนธุรกิจที่ต้นทางรายงาน หรือคะแนนของบุคคล ยังใช้ยืนยันว่าธุรกิจพัฒนาขึ้นไม่ได้",
  };
  const OFFICIAL_TITLE = "ตัวเลขในสไลด์ บพท. กับข้อมูลที่เรารวบรวม";
  // Area tab: the measures it compares by province, and what "in a province" means for each (measures/members.sql).
  const AREA_MEASURES = ["C04_LISTED", "C02_COMMUNITY", "K05", "K07", "K12", "H01"];
  const AREA_PLACE_MEANINGS = {
    C04_LISTED: "จังหวัดที่แหล่งข้อมูลระบุว่าเป็นพื้นที่ใช้หรือพื้นที่ของผู้ใช้เป้าหมายของนวัตกรรม ไม่ใช่ที่ตั้งของมหาวิทยาลัย",
    C02_COMMUNITY: C02_SOURCE_PROVINCE_MEANING,
    K05: "จังหวัดที่ตั้งของธุรกิจตามที่แหล่งข้อมูลระบุ",
    K07: "จังหวัดที่แหล่งข้อมูลระบุไว้กับรายการสินค้าหรือบริการ",
    K12: "จังหวัดของรายการบนแผนที่วัฒนธรรมไทย",
    H01: "จังหวัดของครัวเรือนเป้าหมายตามที่ PMUA AppTech รายงาน",
  };
  const AREA_TOP = 15;
  const UNIVERSITY_GROUP_ORDER =["rajabhat", "rajamangala", "university", "other"];
  const UNIVERSITY_COUNTS = [["C04_LISTED", "นวัตกรรม"], ["C02_COMMUNITY", "นวัตกรชุมชน"], ["K05", "ธุรกิจ"]];
  // Innovation tab: the list filters of /topics/k04 (?f2i<key>=), on top of the page's province.
  const INNOVATION_FILTERS = ["university", "source", "trl", "evidence", "q"];
  const INNOVATION_MEASURE = "C04_LISTED";
  const MONTH_NOTE = "แหล่งข้อมูลยังไม่ระบุว่าเป็นเดือนปฏิทินใด";
  const K10_EXCLUDED_AMOUNT_NOTE = "ข้อมูลต้นทางทั้งชุดมีอีกยอด 200,093,000 บาท (ประมาณ 200.1 ล้านบาท) ที่ไม่ได้รวมในการคำนวณนี้ เพราะยังไม่ชัดเจนว่าเป็นค่าอะไรและครอบคลุมช่วงเวลาใด";
  const FILTER_LABELS = {
    category: "หมวดหมู่ตามแหล่งข้อมูล",
    source_level: "ระดับนวัตกรชุมชน",
    source_region: "ภูมิภาคตามแหล่งข้อมูล",
    component: "องค์ประกอบของตัวเลข",
    source_dimension: "ดูข้อมูลแยกตาม",
  };
  // Labels published by https://pmua-apptech.com/dashboard/innovatordashboard?year_filter=
  const PMUA_LEVEL_LABELS = {
    "1": "ระดับ 1 (เรียนรู้/รับการถ่ายทอด)",
    "2": "ระดับ 2 (ใช้งานได้ด้วยตนเอง)",
    "3": "ระดับ 3 (ประยุกต์ใช้/ดัดแปลงได้)",
    "4": "ระดับ 4 (ถ่ายทอดได้)",
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
  const MEASURE_HELP_TITLES = {
    K01A: "ดูวิธีนับความครอบคลุม",
    K01B: "พื้นที่วัฒนธรรมหนึ่งแห่งนับอย่างไร?",
    K02: "นับใครบ้าง และต่างจากรายชื่อในทะเบียนอย่างไร?",
    C02_COMMUNITY: "รายชื่อกลุ่มนี้คือใคร และจังหวัดหมายถึงอะไร?",
    K03: "กิจกรรมหนึ่งครั้งนับอย่างไร?",
    K04: "นวัตกรรมแบบใดนับว่าพร้อมใช้?",
    C04_LISTED: "นวัตกรรมทั้งหมดต่างจากกลุ่มที่ผ่านเกณฑ์อย่างไร?",
    K05: "ยอดนี้ครอบคลุมธุรกิจใดบ้าง?",
    K06: "ทำไมยังไม่มีจำนวนผู้ประกอบการ?",
    K07: "สินค้าหลายรุ่นนับแยกกันหรือไม่?",
    K08: "ทำไมยังบอกไม่ได้ว่าธุรกิจพัฒนาขึ้นกี่แห่ง?",
    C08_PARTICIPATING: "เข้าร่วมโครงการแล้วหมายถึงธุรกิจดีขึ้นหรือไม่?",
    C08_REPORTED_BUSINESSES: "ยอดธุรกิจที่แยกแต่ละด้านนำมาบวกกันได้หรือไม่?",
    C08_ASSESSED_PEOPLE: "นับจำนวนคนหรือจำนวนแบบประเมิน?",
    C08_INCREASED_PEOPLE: "คะแนนเพิ่มขึ้นหมายถึงอะไร?",
    K09: "จำนวนการจ้างงานนี้เป็นของเดือนไหน?",
    K10: "ยอดเงินนี้เป็นรายได้สุทธิหรือไม่?",
    K11A: "ทำไมยังไม่มีจำนวนคลัสเตอร์?",
    K11B: "ทำไมยังระบุจังหวัดที่มีคลัสเตอร์ไม่ได้?",
    K12: "รายการทุนวัฒนธรรมหนึ่งรายการคืออะไร?",
    H01: "ครัวเรือนเป้าหมายคือใคร และตัวเลขเงินมาจากไหน?",
  };
  const MEASURE_LIMITATIONS = {
    K01A: "นับจังหวัดที่พบข้อมูลพื้นที่อย่างน้อยหนึ่งประเภทจากแหล่งข้อมูลที่รวบรวม เช่น พื้นที่ใช้หรือพื้นที่เป้าหมายของนวัตกรรม ที่ตั้งธุรกิจที่เข้าร่วมโครงการ รายการทุนวัฒนธรรม สินค้า หรือกิจกรรม จังหวัดเดียวกันที่พบหลายรายการหรือหลายแหล่งนับเพียงครั้งเดียว โดยรวมกรุงเทพมหานครด้วย ที่อยู่ของมหาวิทยาลัยหรือหน่วยงานเพียงอย่างเดียวไม่นำมานับ ยอดนี้ไม่ได้ยืนยันว่ามีการดำเนินโครงการจริงในทุกจังหวัด หรือมีข้อมูลครบทุกหัวข้อ",
    K01B: "นับพื้นที่ที่อยู่ในทะเบียนพื้นที่วัฒนธรรมที่ใช้ในข้อมูลฉบับนี้เป็นจำนวนแห่ง หากสองรายการอาจเป็นพื้นที่เดียวกันแต่ยังยืนยันไม่ได้ จะยังนับแยกและแจ้งความไม่แน่นอนไว้",
    K02: "แสดงจำนวนนวัตกรตามยอดรวมที่ PMUA รายงาน โดยไม่มีรายชื่อบุคคลให้ตรวจดูทีละคน ยอดนี้กับ “บุคคลที่มีหลักฐานนวัตกรชุมชนในทะเบียน” เป็นคนละชุดข้อมูล จึงนำมาบวกหรือลบกันไม่ได้ จังหวัดที่ไม่มีข้อมูลไม่ได้หมายความว่ามีนวัตกรศูนย์คน",
    C02_COMMUNITY: "นับบุคคลที่มีหลักฐานในทะเบียนว่าเป็นนวัตกรชุมชนหรือผู้ประดิษฐ์ จังหวัดคือจังหวัดที่แหล่งข้อมูลผูกไว้กับบุคคล ไม่ใช่ที่อยู่หรือที่ทำงานปัจจุบัน คนหนึ่งอาจอยู่ในข้อมูลหลายจังหวัด จึงบวกยอดรายจังหวัดเป็นยอดประเทศไม่ได้ รายชื่อเหล่านี้ไม่ใช่รายชื่อเบื้องหลัง “นวัตกรตามยอดรวมที่ PMUA รายงาน” และนำสองยอดมาบวกกันไม่ได้",
    K03: "นับกิจกรรมโครงการที่มีรายงานเป็นจำนวนครั้ง ช่วงกิจกรรมย่อยและสิ่งพิมพ์ที่เกี่ยวข้องเป็นรายละเอียดของกิจกรรมนั้น จึงไม่นับเป็นกิจกรรมเพิ่ม การมีรายงานกิจกรรมยังไม่ได้ยืนยันว่าโครงการทั้งหมดเสร็จสมบูรณ์",
    K04: "นับนวัตกรรมที่มีแหล่งข้อมูลอย่างน้อยหนึ่งรายการระบุระดับความพร้อมทางเทคโนโลยี (TRL) เป็นระดับ 8 หรือ 9 โดยระดับ 8 หมายถึงเทคโนโลยีที่พัฒนาเสร็จและผ่านการทดสอบ ส่วนระดับ 9 หมายถึงมีการใช้งานจริงแล้ว นวัตกรรมเดียวกันที่พบหลายแหล่งนับเพียงครั้งเดียว หากแหล่งข้อมูลระบุระดับต่างกัน ยังนับรวมเมื่อมีอย่างน้อยหนึ่งรายการระบุระดับ 8 หรือ 9 และแสดงข้อมูลที่ต่างกันให้ตรวจสอบ ตัวเลขนี้อ้างอิงการรายงานของแหล่งข้อมูล ไม่ใช่การยืนยันความพร้อมใช้งานในปัจจุบันโดยแดชบอร์ด",
    C04_LISTED: "แสดงนวัตกรรมที่มีรายการทั้งหมด รวมกลุ่ม “นวัตกรรมที่มีหลักฐานความพร้อมตามเกณฑ์” อยู่แล้ว จึงนำสองยอดมาบวกกันไม่ได้ รายการนอกกลุ่มที่ผ่านเกณฑ์อาจยังไม่มีหลักฐานเพียงพอ ไม่ได้แปลว่ายืนยันแล้วว่าไม่พร้อมใช้งาน",
    K05: "เป็นความครอบคลุมบางส่วนจากแหล่งข้อมูลที่ตรวจแล้ว ไม่ใช่ทะเบียนธุรกิจวัฒนธรรมทั้งหมด และไม่นำที่ตั้งสินค้าหรือโครงการมาแทนที่ตั้งธุรกิจ",
    K06: "ยังไม่เผยแพร่ยอดรวม เพราะการค้นหาและยืนยันบทบาทบุคคลยังไม่สม่ำเสมอ การไม่มีตัวเลขไม่ได้แปลว่าไม่มีผู้ประกอบการ",
    K07: "สินค้า บริการ หรือผลงานที่จัดเป็นกลุ่มเดียวกันนับเป็นหนึ่งหน่วย แม้มีสมาชิกหรือรุ่นย่อยหลายรายการ ราคาและรายละเอียดของสมาชิกยังแยกกัน การมีรายการหรือราคาไม่ยืนยันว่าพร้อมขายหรือเกิดจากโครงการ",
    K08: "ยังคำนวณไม่ได้ การเข้าร่วมโครงการหรือคะแนนบุคคลที่เพิ่มขึ้นยังไม่เพียงพอที่จะยืนยันว่าธุรกิจพัฒนาขีดความสามารถ",
    C08_PARTICIPATING: "ยืนยันเพียงว่าหน่วยธุรกิจมีหลักฐานเข้าร่วมโครงการ ไม่ได้ยืนยันว่าผลประกอบการหรือขีดความสามารถดีขึ้น",
    C08_REPORTED_BUSINESSES: "แสดงจำนวนธุรกิจที่แหล่งข้อมูลสรุปแยกไว้ในแต่ละด้าน โดยไม่มีรายชื่อธุรกิจให้ตรวจดูว่าซ้ำกันระหว่างด้านหรือไม่ จึงนำยอดแต่ละด้านมาบวกเป็นจำนวนธุรกิจทั้งหมดไม่ได้",
    C08_ASSESSED_PEOPLE: "นับคนที่มีคะแนนประเมินก่อนและหลังครบ คนหนึ่งอาจมีหลายแบบประเมิน จึงไม่ใช้จำนวนแบบประเมินแทนจำนวนคน แบบประเมินที่ไม่มีวันที่อาจไม่ใช่ข้อมูลล่าสุด",
    C08_INCREASED_PEOPLE: "นับคนที่มีคะแนนก่อนและหลังให้เทียบกันได้ และมีคะแนนเพิ่มขึ้นอย่างน้อยหนึ่งด้าน คนกลุ่มนี้รวมอยู่ใน “บุคคลที่มีชุดคะแนนก่อนและหลังครบ” แล้ว จึงนำสองยอดมาบวกกันไม่ได้ คะแนนที่เพิ่มขึ้นเป็นผลของบุคคล ไม่ใช่จำนวนธุรกิจที่พัฒนาขึ้น และข้อมูลที่ขาดไม่ได้แปลว่าไม่มีการเปลี่ยนแปลง",
    H01: "แสดงจำนวนครัวเรือนเป้าหมายตามยอดที่ PMUA AppTech รายงาน ไม่ได้แปลว่าทุกครัวเรือนได้ผลลัพธ์ และไม่มีรายชื่อครัวเรือนให้ตรวจดู ยอดรายจังหวัดรวมกันเท่ากับยอดประเทศ จังหวัดที่ต้นทางไม่ได้รายงานไม่ได้แปลว่ามีศูนย์ครัวเรือน ต้นทางแก้ตัวเลขย้อนหลังได้และไม่ได้บอกช่วงเวลาที่วัด ตัวเลขเงินมีเฉพาะระดับประเทศ ดูได้ในตารางครัวเรือนเป้าหมายบนหน้าภาพรวม",
    K09: "แสดงจำนวนการจ้างงานที่ต้นทางรายงานในหน่วยคนต่อเดือน แต่ไม่ได้ระบุว่าเป็นเดือนปฏิทินใด จึงยังบอกไม่ได้ว่าเป็นยอดของเดือนล่าสุด มีเฉพาะข้อมูลรวม ไม่มีรายชื่อแรงงานหรือจำนวนแยกรายจังหวัด",
    K10: "เป็นยอดเงินที่รายงานว่าจ่ายแก่แรงงานและผู้จัดหาทรัพยากรในพื้นที่ ไม่ใช่รายได้สุทธิที่ยืนยันแล้ว การรวมยอดนี้อาศัยข้อสมมติว่ายอดรับในพื้นที่นำมาบวกกันได้และครอบคลุมช่วงเดือนที่เทียบกันได้",
    K11A: "ป้ายหมวดอุตสาหกรรมยังไม่เพียงพอที่จะยืนยันตัวตนคลัสเตอร์ จึงแสดงว่าไม่มีข้อมูล ไม่ใช่ศูนย์",
    K11B: "จังหวัดที่มีหลักฐานโครงการทั่วไปใช้แทนจังหวัดที่มีคลัสเตอร์ไม่ได้ จึงแสดงว่าไม่มีข้อมูล ไม่ใช่ศูนย์",
    K12: "นับรายการจากทุกหมวดหมู่ในข้อมูลเว็บไซต์ แผนที่วัฒนธรรมไทย Cultural Mapping โดยตัดรายการซ้ำออกแล้ว รายการเดียวที่อยู่หลายหมวดหมู่นับเพียงครั้งเดียว",
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
  const measureDisplayLabel = (definition) => MEASURE_DISPLAY_LABELS[definition?.measure_id]
    || (definition?.label_th || definition?.label || definition?.measure_id || "").replace(/ชุดส่งมอบ(?:นี้)?/g, "ข้อมูลฉบับนี้").replace("ตระกูลสินค้า", "กลุ่มสินค้า");
  const selectedMeasureDefinition = () => allMeasureDefinitions().find((item) => item.measure_id === state.measure);
  const filterChoiceKey = () => JSON.stringify([state.revision, state.measure, state.province]);
  const formattedCount = (value) => Number.isFinite(Number(value))
    ? new Intl.NumberFormat("th-TH").format(Number(value))
    : "";
  // Coverage is dataset context; the historical reconstruction remains outside the dashboard.
  const visibleMeasures = (items) => items.filter((item) => !["K01A", "C10_ALTERNATIVE"].includes(item.measure_id || item.value));
  const allMeasureDefinitions = () => visibleMeasures((state.overview?.headlines || []).flatMap((headline) => [headline, ...(headline.companions || [])]));
  const supportsProvince = (definition) => definition?.filter_contract?.supported_filters?.includes("province");
  const statusLabel = (value) => RESULT_STATUS_LABELS[value] || label(value);
  // A missing value says why, not what kind of number it would be (a source total's status is not a reason).
  const unavailableLabel = (result) => result?.unavailable_reason?.code === "unknown_province" ? "ไม่มีข้อมูลรายจังหวัด"
    : statusLabel(["deferred", "insufficient_data"].includes(result?.status) ? result.status : "unavailable");
  const provinceName = (code) => code
    ? (state.callbacks.getProvinces?.() || []).find((province) => text(province.province_code) === code)?.province_name_th || code
    : "";

  // Mobile controls preview a reversible draft. Only Apply writes browser history.
  function openFilters() {
    if (state.filterDraft) return;
    state.filterDraft = Object.fromEntries(["measure", "topic", "province", "rememberedProvince", "filters", "searchDraft", "sort", "offset", "scopeNotice"].map((key) => [key, structuredClone(state[key])]));
    clearTimeout(state.searchTimer);
    $("f2FilterFields").append($("f2Controls"));
    $("f2FiltersToggle").setAttribute("aria-expanded", "true");
    $("f2FilterDialog").showModal();
  }
  function finishFilters(apply) {
    if (!state.filterDraft) return;
    clearTimeout(state.searchTimer);
    ["overview", "topic", "choices", "map"].forEach(abort);
    if (apply) {
      if (state.searchDraft !== (state.filters.q || "")) state.offset = 0;
      if (state.searchDraft) state.filters.q = state.searchDraft;
      else delete state.filters.q;
    } else Object.assign(state, state.filterDraft);
    state.filterDraft = null;
    $("f2FilterDialog").close();
    $("f2FiltersToggle").after($("f2Controls"));
    $("f2FiltersToggle").setAttribute("aria-expanded", "false");
    state.callbacks.onProvinceRestore?.(state.province);
    writeUrl(apply);
    loadOverview();
    $("f2FiltersToggle").focus({ preventScroll: true });
  }
  function metricContext(measure) {
    const name = provinceName(state.province);
    if (name && supportsProvince(measure)) return `ขอบเขต: จังหวัด${name}`;
    if (name) return `ยังไม่มีตัวเลขจังหวัด${name} · เปิดดูข้อมูลประเทศไทยได้`;
    return measure?.filter_contract?.supported_filters?.includes("source_region")
      ? "ขอบเขต: ประเทศไทย / ภูมิภาคตามต้นทาง"
      : "ขอบเขต: ประเทศไทย";
  }
  const BANGKOK_DAY = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Bangkok" });
  const THAI_DAY = new Intl.DateTimeFormat("th-TH", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  function thaiDay(day) { return THAI_DAY.format(new Date(`${day}T00:00:00Z`)); }
  function sourceSnapshots() { return state.overview?.sources?.by_id || {}; }
  // The days (Thai time) we fetched these sources, as one date or a range: "12–14 ต.ค. 2569".
  function fetchedRange(ids) {
    const days = [...new Set(ids.map((id) => sourceSnapshots()[id]?.fetched_at).filter(Boolean)
      .map((value) => BANGKOK_DAY.format(new Date(value))))].sort();
    if (!days.length) return "";
    const first = days[0], last = days[days.length - 1];
    if (first === last) return thaiDay(first);
    return first.slice(0, 7) === last.slice(0, 7) ? `${Number(first.slice(8))}–${thaiDay(last)}` : `${thaiDay(first)} – ${thaiDay(last)}`;
  }
  // "ที่มา: <source> · ดึงข้อมูล <date>" for a number; empty for a release without fetch dates.
  function sourceLine(ids, lead = "ที่มา") {
    const unique = [...new Set(ids || [])];
    const fetched = fetchedRange(unique);
    if (!unique.length || !fetched) return "";
    return `${lead}: ${unique.length === 1 ? SOURCE_NAMES[unique[0]] || unique[0] : `${unique.length} แหล่ง`} · ดึงข้อมูล ${fetched}`;
  }
  function metricExplanation(measureId) {
    return MEASURE_LIMITATIONS[measureId] || "";
  }
  function metricRows(group) {
    const columns = getComputedStyle(group).gridTemplateColumns.split(/\s+/).length;
    const rows = [];
    let row = [];
    for (const child of group.children) {
      if (child.classList.contains("f2-metric-explanation")) continue;
      if (child.classList.contains("f2-metric-wrap")) row.push(child);
      // Section headings and notes span the grid and start a new card row.
      if (row.length && (row.length === columns || !child.classList.contains("f2-metric-wrap"))) {
        rows.push(row);
        row = [];
      }
    }
    if (row.length) rows.push(row);
    return rows;
  }
  function layoutMetricExplanations(group, preferredButton) {
    metricRows(group).forEach((row) => {
      const buttons = row.map((wrapper) => wrapper.querySelector(".f2-metric-help")).filter(Boolean);
      const expanded = buttons.filter((button) => button.getAttribute("aria-expanded") === "true");
      const active = expanded.includes(preferredButton) ? preferredButton : expanded[0];
      buttons.forEach((button) => {
        const explanation = $(button.getAttribute("aria-controls"));
        const open = button === active;
        button.setAttribute("aria-expanded", String(open));
        explanation.hidden = !open;
        if (open) row.at(-1).after(explanation);
      });
    });
  }
  function backToOverview(view) {
    view.append(el("button", { type: "button", class: "f2-back-overview", text: "← กลับไปภาพรวม", onclick: () => setTab("overview") }));
  }

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
    if (!response.ok) {
      const error = new Error(text(body.detail || body.message || `HTTP ${response.status}`));
      error.status = response.status;
      throw error;
    }
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
    if (state.filterDraft) return;
    const url = new URL(location.href);
    url.searchParams.set("mode", "f2");
    url.searchParams.set("f2tab", state.tab);
    ["f2measure", "province", "f2detail", "f2areaall", "f2category", "f2source_level", "f2source_region", "f2component", "f2source_dimension", "f2q", "f2offset", "f2sort", "f2preferredProvince", "f2uni", "f2unioffset", "f2uniq", "f2unisearch", "f2ioffset", ...INNOVATION_FILTERS.map((key) => `f2i${key}`)].forEach((name) => url.searchParams.delete(name));
    if (state.measure) url.searchParams.set("f2measure", state.measure);
    if (state.province) url.searchParams.set("province", state.province);
    if (state.detail) url.searchParams.set("f2detail", state.detail);
    ["category", "source_level", "source_region", "component", "source_dimension", "q"].forEach((key) => { if (state.filters[key]) url.searchParams.set(`f2${key}`, state.filters[key]); });
    if (state.offset) url.searchParams.set("f2offset", state.offset);
    if (state.sort !== "source") url.searchParams.set("f2sort", state.sort);
    if (state.rememberedProvince && !state.province) url.searchParams.set("f2preferredProvince", state.rememberedProvince);
    if (state.tab === "areas" && state.areaShowAll) url.searchParams.set("f2areaall", "1");
    if (state.tab === "universities" && state.universitySearch) url.searchParams.set("f2unisearch", state.universitySearch);
    if (state.tab === "innovations") {
      INNOVATION_FILTERS.forEach((key) => { if (state.innovationFilters[key]) url.searchParams.set(`f2i${key}`, state.innovationFilters[key]); });
      if (state.innovationOffset) url.searchParams.set("f2ioffset", state.innovationOffset);
    }
    if (state.tab === "universities" && state.university) {
      url.searchParams.set("f2uni", state.university);
      if (state.universityOffset) url.searchParams.set("f2unioffset", state.universityOffset);
      if (state.universityQuery) url.searchParams.set("f2uniq", state.universityQuery);
    }
    history[push ? "pushState" : "replaceState"]({}, "", url);
  }
  function restoreUrl() {
    const params = new URLSearchParams(location.search);
    state.tab = ["overview", "areas", "universities", "innovations", "list", "sources"].includes(params.get("f2tab")) ? params.get("f2tab") : "overview";
    state.innovationFilters = Object.fromEntries(INNOVATION_FILTERS.map((key) => [key, params.get(`f2i${key}`)]).filter(([, value]) => value));
    state.innovationOffset = Math.max(0, Number(params.get("f2ioffset")) || 0);
    state.areaShowAll = params.get("f2areaall") === "1";
    state.university = params.get("f2uni") || "";
    state.universityOffset = Math.max(0, Number(params.get("f2unioffset")) || 0);
    state.universityQuery = params.get("f2uniq") || "";
    state.universitySearch = params.get("f2unisearch") || "";
    state.measure = params.get("f2measure") || "";
    state.province = params.get("province") || "";
    state.rememberedProvince = params.get("f2preferredProvince") || state.province;
    state.scopeNotice = !state.province && state.rememberedProvince
      ? `ไม่มีข้อมูลระดับจังหวัดสำหรับ${provinceName(state.rememberedProvince)} กำลังแสดงมุมมองประเทศไทย ระบบจะคืนจังหวัดเดิมเมื่อเลือกตัวชี้วัดที่รองรับ`
      : "";
    state.sort = ["name_asc", "name_desc"].includes(params.get("f2sort")) ? params.get("f2sort") : "source";
    state.detail = params.get("f2detail") || "";
    state.filters = Object.fromEntries(["category", "source_level", "source_region", "component", "source_dimension", "q"].map((key) => [key, params.get(`f2${key}`)]).filter(([, value]) => value));
    state.searchDraft = state.filters.q || "";
    state.offset = Math.max(0, Number(params.get("f2offset")) || 0);
    if (["K01A", "C10_ALTERNATIVE"].includes(state.measure)) {
      state.measure = state.measure === "K01A" ? "K12" : "K10";
      state.topic = state.measure.toLowerCase();
      state.filters = {};
      state.searchDraft = "";
      state.offset = 0;
      state.sort = "source";
      state.detail = "";
    }
  }
  function setTab(tab, push = true) {
    const changingTab = $("f2-tab-" + tab).getAttribute("aria-selected") !== "true";
    if (state.tab === "overview" && tab !== "overview" && views.overview.querySelector(".f2-topic-jump")) state.overviewScroll = panel.querySelector(".f2-stage").scrollTop;
    state.tab = tab;
    Object.entries(views).forEach(([key, view]) => {
      const active = key === tab;
      view.hidden = !active;
      const button = $("f2-tab-" + key);
      button.setAttribute("aria-selected", String(active));
      button.tabIndex = active ? 0 : -1;
    });
    if (changingTab) panel.querySelector(".f2-stage").scrollTop = 0;
    if (tab === "areas") enterAreas();
    if (tab === "innovations") enterInnovations();
    // the university tab counts nationally with its own counts; the area and innovation tabs have their own pickers
    $("f2Controls").hidden = $("f2FiltersToggle").hidden = ["universities", "areas", "innovations"].includes(tab);
    renderBreadcrumbs(state.overview?.requested_scope || {});
    writeUrl(push);
    if (tab === "overview" || tab === "areas" || tab === "innovations") loadOverview();
    if (tab === "universities") loadUniversities();
    if (tab === "list") loadTopic();
    if (tab === "sources") loadSources();
  }
  function renderBreadcrumbs(scope) {
    const crumb = $("f2Breadcrumbs");
    const hadFocus = crumb.contains(document.activeElement);
    clear(crumb);
    crumb.append(el("button", { type: "button", text: "ประเทศไทย", onclick: () => handleProvince("", true) }));
    if (hadFocus) crumb.firstChild.focus({ preventScroll: true });
    // the university tab counts nationally; the province stays selected for the other tabs
    const province = state.tab === "universities" ? "" : scope?.province_name_th || scope?.province || scope?.province_code || state.province;
    if (province) crumb.append(el("span", { text: province }));
  }
  function choices(contract, key, fallback) {
    const source = contract?.choices?.[key] || contract?.[key] || contract?.filters?.[key] || fallback?.choices?.[key] || fallback?.[key];
    const raw = Array.isArray(source) ? source : source?.options || source?.values || [];
    return raw.map((item) => isObject(item) ? { value: item.value ?? item.id ?? item.code ?? item.key, label: item.label_th ?? item.label ?? item.name ?? item.value ?? item.id } : { value: item, label: item });
  }
  function selectedValueNote(select) {
    const note = el("span", { class: "f2-selected-value", "aria-hidden": "true" });
    const update = () => { note.textContent = select.value ? select.selectedOptions[0]?.textContent || "" : ""; };
    select.addEventListener("change", update);
    update();
    return note;
  }
  function applyFilter(key, value) {
    if (value) state.filters[key] = value;
    else delete state.filters[key];
    state.offset = 0;
    writeUrl(true);
    if (key !== "q") loadMap();
    if (state.tab === "list") loadTopic();
  }
  function clearListFilters() {
    state.filters = {};
    state.searchDraft = "";
    clearTimeout(state.searchTimer);
    state.offset = 0;
    writeUrl(true);
    loadMap();
    loadTopic();
  }
  function filterValueLabel(key, value, data) {
    if (key === "q") return value;
    if (key === "source_level" && state.measure === "K02" && PMUA_LEVEL_LABELS[value]) return PMUA_LEVEL_LABELS[value];
    const available = data?.filters?.choices || state.filterChoices[filterChoiceKey()] || {};
    const option = choices({ choices: available }, key).find((item) => String(item.value) === String(value));
    if (option && String(option.label) !== String(option.value)) return option.label;
    return key === "category" ? `รหัสต้นทาง ${value}` : option?.label || value;
  }
  function activeListFilters(data) {
    const active = [];
    if (state.province) {
      const province = (state.callbacks.getProvinces?.() || []).find((item) => text(item.province_code) === state.province);
      active.push(["จังหวัด", province?.province_name_th || state.province]);
    }
    Object.entries(state.filters).forEach(([key, value]) => {
      if (!value) return;
      active.push([key === "q" ? "คำค้นหา" : FILTER_LABELS[key] || label(key), filterValueLabel(key, value, data)]);
    });
    if (!active.length) return null;
    return el("div", { class: "f2-active-filters", "aria-label": "เงื่อนไขที่ใช้" },
      el("span", { class: "f2-active-filters-title", text: "เงื่อนไขที่ใช้" }),
      el("div", { class: "f2-filter-chips" }, active.map(([name, value]) => el("span", { class: "f2-filter-chip", text: `${name}: ${value}` }))),
      el("button", { class: "f2-edit-filters", type: "button", text: "แก้ไขตัวกรอง", onclick: () => {
        openFilters();
      } }),
    );
  }
  function controls(data) {
    const host = $("f2Controls");
    const focusedControl = host.contains(document.activeElement) ? document.activeElement.id : "";
    const expandedAdvanced = host.dataset.measure === state.measure
      ? new Set([...host.querySelectorAll(".f2-advanced-toggle[aria-expanded='true']")].map((button) => button.id))
      : new Set();
    clear(host);
    host.dataset.measure = state.measure;
    const advancedSections = [];
    const cacheKey = filterChoiceKey();
    const currentScope = state.province ? `province/${state.province}` : "national";
    if (data?.measure_id === state.measure && data?.scope === currentScope && isObject(data?.filters?.choices)) {
      state.filterChoices[cacheKey] = data.filters.choices;
      delete state.choiceFailures[cacheKey];
    }
    const definition = selectedMeasureDefinition();
    const contract = data?.filter_contract || data?.filters || definition?.filter_contract || state.topicData?.filter_contract || {};
    const supportedFilters = Array.isArray(contract.supported_filters) ? contract.supported_filters : [];
    const availableChoices = data?.filters?.choices || state.filterChoices[cacheKey] || {};
    const headlineMeasures = allMeasureDefinitions().map((headline) => ({ value: headline.measure_id, label: measureDisplayLabel(headline) })).filter((item) => item.value);
    const measures = visibleMeasures(choices(contract, "measure", data?.measures || data?.available_measures).concat(headlineMeasures.filter((item) => !choices(contract, "measure", data?.measures || data?.available_measures).some((option) => option.value === item.value))))
      .map((option) => ({ ...option, label: measureDisplayLabel({ measure_id: option.value, label: option.label }) }));
    if (measures.length) {
      const select = el("select", { id: "f2Measure" }, el("option", { value: "", text: "เลือกตัวชี้วัด" }));
      const grouped = new Set();
      OVERVIEW_GROUPS.forEach(([title, ids]) => {
        const options = measures.filter((option) => {
          const definition = allMeasureDefinitions().find((item) => item.measure_id === option.value);
          return ids.includes(option.value) || ids.includes(definition?.parent_measure_id);
        });
        if (!options.length) return;
        const group = el("optgroup", { label: title });
        options.forEach((option) => {
          grouped.add(option.value);
          group.append(el("option", { value: option.value, text: option.label }));
        });
        select.append(group);
      });
      measures.filter((option) => !grouped.has(option.value)).forEach((option) => select.append(el("option", { value: option.value, text: option.label })));
      select.value = state.measure;
      select.addEventListener("change", () => changeMeasure(select.value));
      host.append(el("label", { htmlFor: "f2Measure", text: state.tab === "overview" ? "ตัวเลขที่แสดงบนแผนที่" : "ตัวชี้วัด" }, select, selectedValueNote(select)));
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
      const options = choices(contract, key, { choices: availableChoices }).map((option) => ({
        ...option,
        label: key === "source_level" && state.measure === "K02" ? PMUA_LEVEL_LABELS[option.value] || option.label : option.label,
      }));
      const id = "f2-" + key;
      const selected = state.filters[key] || "";
      const codeOnly = key === "category" ? options.filter((option) => String(option.label) === String(option.value)) : [];
      const named = key === "category" ? options.filter((option) => String(option.label) !== String(option.value)) : options;
      const selectedIsCode = codeOnly.some((option) => String(option.value) === selected);
      const select = el("select", { id }, el("option", { value: "", text: "ทั้งหมด" }));
      if (key === "source_dimension" && state.measure === "C08_REPORTED_BUSINESSES") {
        select.options[0].textContent = "หมวดหมู่ธุรกิจ (ค่าเริ่มต้น)";
      }
      if (selectedIsCode) select.options[0].textContent = `ใช้รหัสย่อย ${selected}`;
      let advanced = null;
      let updateAdvanced = null;
      named.forEach((option) => select.append(el("option", { value: option.value, text: option.label })));
      if (selected && !options.some((option) => String(option.value) === selected)) select.append(el("option", { value: selected, text: `ตัวกรองที่เลือก: ${selected}` }));
      select.value = selectedIsCode ? "" : selected;
      if (!options.length) {
        select.options[0].textContent = state.choiceFailures[cacheKey] ? "ตัวเลือกไม่พร้อม" : "กำลังโหลดตัวเลือก";
        select.disabled = true;
      }
      select.addEventListener("change", () => {
        if (advanced) advanced.value = "";
        select.options[0].textContent = key === "source_dimension" && state.measure === "C08_REPORTED_BUSINESSES" ? "หมวดหมู่ธุรกิจ (ค่าเริ่มต้น)" : "ทั้งหมด";
        updateAdvanced?.(false);
        applyFilter(key, select.value);
      });
      const field = el("div", { class: "f2-filter-field" }, el("label", { htmlFor: id, text: FILTER_LABELS[key] || label(key) }, select, selectedValueNote(select)));
      host.append(field);
      if (codeOnly.length) {
        const advancedId = `${id}-code`;
        const sectionId = `${advancedId}-section`;
        const toggleId = `${advancedId}-toggle`;
        const helpId = `${advancedId}-help`;
        advanced = el("select", { id: advancedId, "aria-describedby": helpId }, el("option", { value: "", text: "ไม่เลือกรหัสย่อย" }));
        codeOnly.forEach((option) => advanced.append(el("option", { value: option.value, text: `รหัสต้นทาง ${option.value}` })));
        advanced.value = selectedIsCode ? selected : "";
        const toggle = el("button", { id: toggleId, type: "button", class: "f2-advanced-toggle", "aria-controls": sectionId });
        const advancedSection = el("div", { id: sectionId, class: "f2-advanced-filter" },
          el("label", { htmlFor: advancedId, text: "รหัสหมวดหมู่ย่อยจากต้นทาง" }, advanced),
          el("p", { id: helpId, text: "สำหรับกรณีที่ทราบรหัสหมวดหมู่จากต้นทาง ซึ่งยังไม่มีชื่อหมวดหมู่กำกับ" }),
        );
        updateAdvanced = (open) => {
          const activeCode = advanced.value;
          advancedSection.hidden = !open && !activeCode;
          toggle.setAttribute("aria-expanded", String(!advancedSection.hidden));
          toggle.disabled = Boolean(activeCode);
          toggle.textContent = activeCode ? `กำลังใช้รหัสหมวดหมู่: ${activeCode}` : "ค้นหาด้วยรหัสหมวดหมู่";
        };
        toggle.addEventListener("click", () => updateAdvanced(advancedSection.hidden));
        advanced.addEventListener("change", () => {
          select.value = "";
          select.options[0].textContent = advanced.value ? `ใช้รหัสย่อย ${advanced.value}` : "ทั้งหมด";
          select.parentElement.querySelector(".f2-selected-value").textContent = "";
          updateAdvanced(true);
          applyFilter(key, advanced.value);
        });
        updateAdvanced(selectedIsCode || expandedAdvanced.has(toggleId));
        field.append(toggle);
        advancedSections.push(advancedSection);
      }
    });
    const searchable = data?.list?.capability === "available" || (!data?.list && definition?.filter_contract?.detail_availability === "available");
    if (state.tab === "list" && searchable) {
      const input = el("input", { id: "f2Search", type: "search", value: state.searchDraft, placeholder: "ค้นหาในรายการ", autocomplete: "off" });
      input.addEventListener("input", () => {
        state.searchDraft = input.value;
        clearTimeout(state.searchTimer);
        state.searchTimer = setTimeout(() => {
          applyFilter("q", state.searchDraft);
        }, 300);
      });
      host.append(el("label", { class: "f2-search", htmlFor: "f2Search", text: "ค้นหา" }, input));
      const sort = el("select", { id: "f2Sort" },
        el("option", { value: "source", text: "ลำดับในชุดข้อมูล" }),
        el("option", { value: "name_asc", text: "ตามชื่อ (น้อยไปมาก)" }),
        el("option", { value: "name_desc", text: "ตามชื่อ (มากไปน้อย)" }));
      sort.value = state.sort;
      sort.addEventListener("change", () => { state.sort = sort.value; state.offset = 0; writeUrl(true); loadTopic(); });
      host.append(el("label", { htmlFor: "f2Sort", text: "เรียงรายการ" }, sort));
    }
    host.append(...advancedSections);
    if (focusedControl && focusedControl !== "f2Search") $(focusedControl)?.focus({ preventScroll: true });
  }
  async function ensureFilterChoices(overviewData) {
    const supported = selectedMeasureDefinition()?.filter_contract?.supported_filters || [];
    const choiceKeys = supported.filter((key) => ["category", "source_level", "source_region", "component", "source_dimension"].includes(key));
    if (!choiceKeys.length) return;
    const cacheKey = filterChoiceKey();
    if (choiceKeys.every((key) => state.filterChoices[cacheKey]?.[key]?.length)) return;
    try {
      const data = await request(`/topics/${encodeURIComponent(state.topic)}` + query({ measure: state.measure, province: state.province, revision: state.revision }), "choices");
      if (!data || !state.open || cacheKey !== filterChoiceKey()) return;
      const availableChoices = data.filters?.choices || {};
      state.filterChoices[cacheKey] = availableChoices;
      state.choiceFailures[cacheKey] = choiceKeys.some((key) => !availableChoices[key]?.length);
    } catch (error) {
      if (error.stale || error.name === "AbortError" || cacheKey !== filterChoiceKey()) return;
      state.choiceFailures[cacheKey] = true;
    }
    if (state.tab === "overview" && state.overview === overviewData) controls(overviewData);
  }
  function cardFor(value, fallbackTitle) {
    const card = el("article", { class: "f2-generic-card" });
    if (!isObject(value)) { card.append(el("h4", { text: fallbackTitle }), el("p", { text: valueText(value) || "ไม่มีข้อมูล" })); return card; }
    card.append(el("h4", { text: MEASURE_DISPLAY_LABELS[state.measure] || value.title_th || value.label_th || value.title || value.label || value.name || fallbackTitle }));
    if (value.availability === "unavailable") {
      card.append(el("p", { class: "f2-unavailable-value", text: unavailableLabel(value) }));
      return card;
    }
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
    if (!measure || measure === "K01A") measure = "K12";
    if (measure === "C10_ALTERNATIVE") measure = "K10";
    state.measure = measure;
    const selected = allMeasureDefinitions().find((headline) => headline.measure_id === measure);
    if (selected?.topic_id) state.topic = selected.topic_id;
  }
  function changeMeasure(measure) {
    if (state.tab === "overview" && views.overview.querySelector(".f2-topic-jump")) state.overviewScroll = panel.querySelector(".f2-stage").scrollTop;
    abort("choices");
    selectMeasure(measure);
    state.filters = {};
    state.searchDraft = "";
    state.offset = 0;
    state.sort = "source";
    clearTimeout(state.searchTimer);
    const definition = selectedMeasureDefinition();
    if (state.province && !supportsProvince(definition)) {
      const provinceName = (state.callbacks.getProvinces?.() || []).find((province) => text(province.province_code) === state.province)?.province_name_th || "จังหวัดที่เลือก";
      state.rememberedProvince = state.province;
      state.province = "";
      state.scopeNotice = `${measureDisplayLabel(definition) || "ตัวชี้วัดนี้"} ไม่มีข้อมูลระดับจังหวัด ระบบจึงเปลี่ยนจาก ${provinceName} เป็นมุมมองประเทศไทย`;
      if (!state.filterDraft) state.callbacks.onProvinceRestore?.("");
    } else {
      if (!state.province && state.rememberedProvince && supportsProvince(definition)) {
        state.province = state.rememberedProvince;
        if (!state.filterDraft) state.callbacks.onProvinceRestore?.(state.province);
      }
      state.scopeNotice = "";
    }
    writeUrl(true);
    loadOverview();
  }
  function renderOverview(data) {
    const view = views.overview; clear(view); renderBreadcrumbs(data.requested_scope || {});
    const headlines = Array.isArray(data.headlines) ? data.headlines : [];
    selectMeasure(state.measure);
    controls(data);
    const jump = el("select", { id: "f2TopicJump", "aria-label": "ข้ามไปยังหัวข้อ" }, el("option", { value: "", text: "ข้ามไปยังหัวข้อ" }));
    if (data.official?.rows?.length) jump.append(el("option", { value: "f2-overview-official", text: OFFICIAL_TITLE }));
    OVERVIEW_GROUPS.forEach(([title, ids], index) => {
      if (headlines.some((headline) => ids.includes(headline.measure_id))) jump.append(el("option", { value: `f2-overview-group-${index}`, text: title }));
    });
    jump.value = state.overviewTopic;
    jump.addEventListener("change", () => {
      state.overviewTopic = jump.value;
      $(jump.value)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    view.append(el("div", { class: "f2-topic-jump" }, el("label", { htmlFor: "f2TopicJump", text: "หัวข้อที่ต้องการดู" }, jump)));
    renderScopeNotice(view);
    view.append(el("details", { class: "f2-overview-guide" },
      el("summary", { text: `วิธีอ่านภาพรวม${data.provenance?.release_date ? ` · ฉบับ ${data.provenance.release_date}` : ""}` }),
      el("p", { class: "f2-overview-key", text: "0 หมายถึงนับได้ศูนย์ในข้อมูลชุดนี้ ส่วน — หมายถึงยังไม่มีตัวเลขที่รองรับสำหรับพื้นที่ที่เลือก" }),
      el("p", { class: "f2-overview-key", text: "กรอบเส้นประคือตัวเลขประกอบ ซึ่งอาจใช้ข้อมูลคนละชุดหรือวิธีนับต่างกัน" }),
      el("p", { class: "f2-overview-key", text: "วันที่ฉบับข้อมูลเป็นวันที่จัดเตรียม ไม่ใช่ช่วงเวลาที่วัด ตัวเลขแต่ละชุดอาจครอบคลุมคนละช่วงเวลา ตรวจสอบช่วงเวลาจากที่มาของแต่ละตัวชี้วัด" }),
      Object.keys(sourceSnapshots()).length ? el("p", { class: "f2-overview-key" },
        `ทุกตัวเลขบอกแหล่งและวันที่ดึงข้อมูลไว้ใต้ตัวเลข ข้อมูลชุดนี้ดึงจากเว็บต้นทาง ${Object.keys(sourceSnapshots()).length} แห่ง ${fetchedRange(Object.keys(sourceSnapshots()))} `,
        el("button", { type: "button", class: "f2-inline-link", text: "ดูที่มาข้อมูล", onclick: () => { setTab("sources"); $("f2-tab-sources").focus(); } })) : "",
    ));
    const coverageCount = datasetCoverageCount(data);
    if (coverageCount !== null) view.append(el("aside", { class: "f2-coverage-note", "aria-label": "ความครอบคลุมของข้อมูล" },
      el("strong", { text: `ความครอบคลุมของข้อมูล: ${formattedCount(coverageCount)} จังหวัด` }),
      el("p", { text: "พบข้อมูลพื้นที่จากแหล่งข้อมูลที่รวบรวมอย่างน้อยหนึ่งประเภทในแต่ละจังหวัด แต่ละจังหวัดอาจมีข้อมูลไม่ครบทุกหัวข้อ" }),
      el("button", { type: "button", text: MEASURE_HELP_TITLES.K01A, onclick: () => { state.openCoverage = true; setTab("sources"); } }),
    ));
    renderOfficial(view, data);
    OVERVIEW_GROUPS.forEach(([title, ids], index) => {
      const rows = headlines.filter((headline) => ids.includes(headline.measure_id));
      if (!rows.length) return;
      const group = el("div", { class: "f2-headlines" });
      if (ids.includes("K11A") && rows.every((item) => item.result?.availability === "unavailable")) {
        const unavailable = section(title, el("div", { class: "f2-cluster-notice" },
          el("strong", { text: "ยังไม่มีหลักฐานเพียงพอสำหรับจำนวนคลัสเตอร์และจังหวัดที่มีคลัสเตอร์" }),
          el("p", { text: "ยังยืนยันตัวตนคลัสเตอร์ไม่ได้ และหลักฐานโครงการทั่วไปใช้แทนหลักฐานคลัสเตอร์ไม่ได้ การไม่มีข้อมูลไม่ใช่ศูนย์" }),
          rows.map((item) => el("details", { class: "f2-detail-group" }, el("summary", { text: measureDisplayLabel(item) }), el("p", { text: metricExplanation(item.measure_id) }), el("button", { type: "button", text: "ดูวิธีนับและที่มา", onclick: () => { changeMeasure(item.measure_id); setTab("sources"); } }))),
        ));
        unavailable.id = `f2-overview-group-${index}`;
        view.append(unavailable);
        return;
      }
      if (index === 0) group.append(el("p", { class: "f2-companion-note", text: "พื้นที่วัฒนธรรมนับเป็นแห่ง ส่วนรายการทุนวัฒนธรรมนับเรื่องหรือทุนที่ผูกกับพื้นที่ รวมบุคคลและผู้ถือครององค์ความรู้ด้วย เป็นคนละวิธีนับ ไม่ควรนำสองยอดมาบวกกัน" }));
      const appendMetric = (item, companion = false) => {
        const result = item.result || {};
        const metric = el("button", {
          class: `f2-metric${companion ? " f2-metric--companion" : ""}`,
          type: "button",
          "data-f2-measure": item.measure_id,
          onclick: () => {
            state.overviewScroll = panel.querySelector(".f2-stage").scrollTop;
            state.overviewTopic = `f2-overview-group-${index}`;
            changeMeasure(item.measure_id);
            setTab("list");
            loadMap();
          },
        });
        metric.append(
          el("span", { text: measureDisplayLabel(item) }),
          el("strong", { text: valueText(result.display_value ?? result.value) || "—" }),
        );
        if (item.unit || result.unit) metric.append(el("small", { text: item.unit || result.unit }));
        if (result.availability === "unavailable") metric.append(el("span", { class: "f2-metric-state", text: unavailableLabel(result) }));
        if (["K09", "K10"].includes(item.measure_id) && result.availability !== "unavailable") {
          metric.append(el("span", { class: "f2-metric-state", text: MONTH_NOTE }));
        }
        if (companion) metric.append(el("span", { class: "f2-metric-kind", text: "ข้อมูลประกอบ" }));
        metric.append(el("small", { class: "f2-metric-scope", text: metricContext(item) }));
        const origin = sourceLine(item.source_ids);
        if (origin) metric.append(el("small", { class: "f2-metric-source", text: origin }));
        metric.append(el("span", { class: "f2-metric-action", text: item.detail_availability === "available" ? "ดูรายการ →" : "ดูรายละเอียดตัวเลข →" }));
        const wrapper = el("div", { class: "f2-metric-wrap" }, metric);
        group.append(wrapper);
        if (metricExplanation(item.measure_id)) {
          const explanationId = `f2-explanation-${item.measure_id}`;
          const titleId = `${explanationId}-title`;
          const button = el("button", {
            type: "button", class: "f2-metric-help", "aria-expanded": "false", "aria-controls": explanationId,
            text: MEASURE_HELP_TITLES[item.measure_id] || "ตัวเลขนี้หมายถึงอะไร?",
            onclick: () => {
              button.setAttribute("aria-expanded", String(button.getAttribute("aria-expanded") !== "true"));
              layoutMetricExplanations(group, button);
            },
          });
          wrapper.append(button);
          group.append(el("section", { id: explanationId, class: "f2-metric-explanation", role: "region", "aria-labelledby": titleId, hidden: true },
            el("h4", { id: titleId, text: measureDisplayLabel(item) }),
            el("p", { text: metricExplanation(item.measure_id) }),
          ));
        }
      };
      rows.forEach((item) => {
        if (index === 2) {
          const subtitle = { K05: "ธุรกิจและผู้ประกอบการ", K07: "สินค้าและบริการ", K08: "การพัฒนาธุรกิจและหลักฐานประกอบ" }[item.measure_id];
          if (subtitle) group.append(el("h4", { class: "f2-subgroup-title", text: subtitle }));
        }
        appendMetric(item);
        visibleMeasures(item.companions || []).forEach((companion) => {
          if (companion.measure_id === "C08_ASSESSED_PEOPLE") group.append(el("h4", { class: "f2-subgroup-title", text: "คะแนนของบุคคล — ไม่ใช่ผลลัพธ์ของธุรกิจ" }));
          appendMetric(companion, true);
        });
        if (COMPANION_NOTES[item.measure_id]) group.append(el("p", { class: "f2-companion-note", text: COMPANION_NOTES[item.measure_id] }));
        if (item.measure_id === data.households?.measure_id) group.append(householdTable(data.households));
      });
      const topicSection = section(title, group);
      topicSection.id = `f2-overview-group-${index}`;
      view.append(topicSection);
    });
    if (!headlines.length) view.append(section("ภาพรวม", null, "ยังไม่มีข้อมูลสรุปสำหรับขอบเขตที่เลือก"));
  }
  // PMUA's national household and money figures as the page states them; never per province or per household.
  function householdTable(households) {
    const money = (value) => `${(value / 1e6).toLocaleString("th-TH", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} ล้านบาท`;
    const name = provinceName(state.province);
    const origin = sourceLine([households.source_id]);
    return el("div", { class: "f2-household-table" },
      name ? el("p", { class: "f2-companion-note", text: `ตารางนี้เป็นยอดระดับประเทศ ไม่ใช่ของจังหวัด${name} ต้นทางไม่ได้แยกตัวเลขเงินรายจังหวัด` }) : "",
      el("div", { class: "f2-table-scroll", tabindex: "0", role: "region", "aria-label": "ตารางครัวเรือนเป้าหมายระดับประเทศ" },
        el("table", { class: "f2-source-region-table" },
          el("caption", { text: "ยอดระดับประเทศตามที่ PMUA AppTech แสดง แยกตามปีงบประมาณที่ต้นทางใช้กรอง" }),
          el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "รายการ" }), households.columns.map((column) => el("th", { scope: "col", text: column.label_th })))),
          el("tbody", {}, households.rows.map((row) => el("tr", {},
            el("th", { scope: "row", text: row.label_th }),
            households.columns.map((column) => el("td", { "data-label": column.label_th,
              title: row.unit_th === "บาท" ? `${formattedCount(row.values[column.id])} บาท` : null,
              text: row.unit_th === "บาท" ? money(row.values[column.id]) : `${formattedCount(row.values[column.id])} ${row.unit_th}` }))))))),
      el("ul", { class: "f2-household-notes" }, households.notes_th.map((note) => el("li", { text: note }))),
      origin ? el("p", { class: "f2-metric-source", text: origin }) : "");
  }
  // บพท.'s slide figures beside ours, grouped by how far they can be read together. Never a ratio or a gap.
  function renderOfficial(view, data) {
    const official = data.official;
    if (!official?.rows?.length) return;
    const node = section(OFFICIAL_TITLE, null);
    node.id = "f2-overview-official";
    node.classList.add("f2-official");
    view.append(node);
    if (state.province) {
      node.append(el("p", { class: "f2-companion-note" }, `ตัวเลขในสไลด์ บพท. มีเฉพาะระดับประเทศ จึงไม่แสดงคู่กับตัวเลขจังหวัด${provinceName(state.province)} `,
        el("button", { type: "button", class: "f2-inline-link", text: "ดูทั้งประเทศ", onclick: () => handleProvince("", true) })));
      return;
    }
    node.append(el("p", { class: "f2-official-intro", text: `ตัวเลขฝั่ง บพท. มาจาก${official.source_th} ข้อมูล ณ ${thaiDay(official.as_of)} ส่วนของเรานับจากข้อมูลบนเว็บที่ดึงเมื่อ ${fetchedRange(Object.keys(sourceSnapshots())) || "วันที่ระบุในแท็บที่มาข้อมูล"} ซึ่งเป็นวันที่ดึง ไม่ใช่ช่วงเวลาที่ตัวเลขวัด ยังไม่รู้ว่านิยามและช่วงเวลาของสองฝั่งตรงกันหรือไม่ ตารางนี้จึงไม่ได้บอกว่าฝั่งไหนถูก และไม่ใช่สัดส่วนของผลงาน` }));
    const measures = Object.fromEntries((data.headlines || []).flatMap((h) => [h, ...(h.companions || [])]).map((m) => [m.measure_id, m]));
    const kind = (m) => m.status === "source_aggregate" ? "ยอดที่ต้นทางรายงาน" : m.status === "assumed_aggregate" ? "คำนวณโดยมีข้อสมมติ" : "นับจากรายการที่พบ";
    const open = (m) => {
      state.overviewScroll = panel.querySelector(".f2-stage").scrollTop;
      state.overviewTopic = "f2-overview-official";
      if (m.measure_id === "K01A") { state.openCoverage = true; setTab("sources"); return; }
      state.rememberedProvince = "";  // these are national figures: do not reopen a province chosen earlier
      changeMeasure(m.measure_id);
      if (m.result?.availability === "unavailable") { setTab("sources"); return; }
      setTab("list");
      loadMap();
    };
    const ours = (ids) => ids.map((id) => measures[id]).filter(Boolean).map((m, _, all) => {
      const unavailable = m.result?.availability === "unavailable";
      return el("div", { class: "f2-official-ours" },
        all.length > 1 ? el("span", { text: measureDisplayLabel(m) }) : "",  // one measure: the row and "เรานับอะไร" say it
        unavailable ? el("strong", { text: "—" }) : el("strong", {}, valueText(m.result?.display_value ?? m.result?.value) || "—", m.unit ? el("small", { text: ` ${m.unit}` }) : ""),
        unavailable ? "" : el("span", { class: "f2-official-kind", text: kind(m) }),
        el("button", { type: "button", class: "f2-inline-link", text: unavailable || m.measure_id === "K01A" ? "ดูวิธีนับ" : m.detail_availability === "available" ? "ดูรายการ" : "ดูรายละเอียดตัวเลข", onclick: () => open(m) }));
    });
    official.groups.forEach((group) => {
      const rows = official.rows.filter((row) => row.group === group.id);
      if (!rows.length) return;
      node.append(el("div", { class: "f2-table-scroll" }, el("table", { class: "f2-source-region-table f2-official-table" },
        el("caption", {}, el("strong", { text: group.title_th }), el("span", { text: group.note_th })),
        el("thead", {}, el("tr", {}, ["ตัวชี้วัดในสไลด์", "สไลด์ บพท.", "ข้อมูลที่เรารวบรวม", "เรานับอะไร"].map((name) => el("th", { scope: "col", text: name })))),
        el("tbody", {}, rows.map((row) => el("tr", {},
          el("th", { scope: "row", text: row.label_th }),
          el("td", { "data-label": "สไลด์ บพท." },
            el("strong", { text: formattedCount(row.value) }), el("small", { class: "f2-official-unit", text: ` ${row.unit_th}${row.qualifier_th ? ` ${row.qualifier_th}` : ""}` }),
            (row.published || []).map((place) => el("small", { class: "f2-official-published" },
              `พบเผยแพร่ใน ${place.where_th}${place.period_th ? ` · ${place.period_th}` : ""}${place.says_th ? ` · เขียนว่า “${place.says_th}”` : ""}`))),
          el("td", { "data-label": "ข้อมูลที่เรารวบรวม" }, ours(row.measure_ids)),
          el("td", { "data-label": "เรานับอะไร", text: row.ours_th })))))));
    });
  }
  async function loadOverview() {
    if (!state.open) return;
    status(views.overview, "กำลังโหลดภาพรวม", "กำลังขอข้อมูลจากระบบ");
    // the area tab draws from this response: an old province's brief must not stay up (or printable) meanwhile
    if (state.tab === "areas") status(views.areas, "กำลังโหลดข้อมูลพื้นที่", "กำลังขอข้อมูลจากระบบ");
    try {
      const data = await request("/overview" + query({ province: state.province, revision: state.revision }), "overview");
      if (!data) return;
      state.overview = data;
      state.revision = data.revision || state.revision;
      renderOverview(data);
      if (state.tab === "overview") panel.querySelector(".f2-stage").scrollTop = state.overviewScroll;
      loadMap();
      const activeTab = state.tab;
      if (activeTab === "overview") await ensureFilterChoices(data);
      if (activeTab === "list") await loadTopic();
      if (activeTab === "sources") await loadSources();
      if (activeTab === "universities") await loadUniversities();
      if (activeTab === "areas") await loadAreas();
      if (activeTab === "innovations") await loadInnovations();
      if (state.detail) openDetail(state.detail, false);
    } catch (error) {
      if (error.stale || error.name === "AbortError") return;
      status(views.overview, "เปิดภาพรวมไม่ได้", error.message, loadOverview);
      if (state.tab === "areas") status(views.areas, "เปิดข้อมูลพื้นที่ไม่ได้", error.message, loadOverview);
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
          label_th: measureDisplayLabel(selected) || "ข้อมูลฝ่าย 2",
          meaning_th: selected?.result?.unavailable_reason?.message_th || "มาตรวัดนี้ไม่มีแผนที่รายจังหวัด",
        },
      });
      return;
    }
    const { q, ...mapFilters } = state.filters;
    try {
      const data = await request("/map" + query({ measure: state.measure, revision: state.revision, ...mapFilters }), "map");
      if (!data) return;
      const drawn = areaMap();
      state.mapData = data;
      state.callbacks.onMapData?.({ ...data, map_available: true, legend: { ...data.legend, label_th: measureDisplayLabel(selected) || data.legend?.label_th } });
      // the area list already drew this map; drawing it again would drop the reader's focus
      if (state.tab === "areas" && !state.province && !drawn) renderAreas();
    } catch (error) {
      if (!error.stale && error.name !== "AbortError") console.warn("F2 map data unavailable", error);
    }
  }
  function sourceTitleNote(measureId, title) {
    if (measureId === "K03" && /[A-Za-z]/.test(title || "") && !/[ก-๙]/.test(title || "")) return "ชื่อกิจกรรมภาษาอังกฤษตามแหล่งข้อมูล";
    if (measureId === "K05" && /(?:^|\s)\d{2}_\d+(?:$|\s)/.test(title || "")) return "แหล่งข้อมูลใช้รหัสเป็นชื่อรายการ";
    return "";
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
    const titleNote = sourceTitleNote(state.measure, model.title);
    if (titleNote) card.append(el("span", { class: "f2-item-source-note", text: titleNote }));
    if (model.context?.length) {
      card.append(el("p", { class: "f2-item-context", text: model.context.join(" · ") }));
    }
    const sources = (item.source_ids || []).map((id) => SOURCE_NAMES[id]).filter(Boolean);
    if (sources.length) card.append(el("p", { class: "f2-item-preview", text: `ที่มา: ${[...new Set(sources)].join(" · ")}` }));
    if (state.measure === "K03") {
      const dates = item.activity_dates || [];
      const displayedDates = [...new Set(dates.map((row) => [row.start_date, row.end_date !== row.start_date ? row.end_date : ""].filter(Boolean).map(window.F2DetailPresenter.formatDate).join(" – ")))];
      card.append(el("p", { class: "f2-item-preview", text: dates.length
        ? `วันที่ตามต้นทาง: ${displayedDates.join(" / ")}${dates.some((row) => row.has_conflict) ? " (มีข้อมูลวันที่ต่างกัน)" : ""}`
        : "วันที่กิจกรรม: ยังไม่มีวันที่ที่เผยแพร่" }));
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
    const target = [...(views[state.tab] || views.list).querySelectorAll("[data-f2-detail-id]")].find((node) => node.dataset.f2DetailId === state.pendingListFocus);
    if (!target) return;
    state.pendingListFocus = "";
    state.returnFocus = target;
    target.focus({ preventScroll: true });
  }
  function renderList(data) {
    const searchSelection = captureSearchFocus();
    const view = views.list; clear(view); controls(data); restoreSearchFocus(searchSelection); const list = data.list || {}; const items = Array.isArray(list.items) ? list.items : [];
    const definition = selectedMeasureDefinition();
    backToOverview(view);
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
    const activeFilters = activeListFilters(data);
    if (activeFilters) view.append(activeFilters);
    const searching = Boolean(state.filters.q);
    const resultNote = state.measure === C02_MEASURE_ID && requestedProvince
      ? `${requestedProvince} ${formattedCount(data.result?.value) || "—"} คน · ทั้งประเทศ ${formattedCount(data.coverage?.national_total) || "—"} คน`
      : measureSupportsProvince && data.coverage?.province_sum_is_additive === false
        ? "ค่าระดับประเทศและผลรวมรายจังหวัดอาจไม่เท่ากัน"
        : "";
    view.append(section(
      "ผลตัวชี้วัด",
      cardFor(data.result, measureDisplayLabel(definition) || data.measure_id),
      [resultNote, ["K09", "K10"].includes(state.measure) ? MONTH_NOTE : "", searching ? "ตัวเลขนี้คำนวณตามพื้นที่และตัวกรองข้างต้น โดยไม่เปลี่ยนตามคำค้นหาในรายการ" : ""].filter(Boolean).join(" · "),
    ));
    if (state.measure === "K10") view.append(el("p", { class: "f2-result-context", text: K10_EXCLUDED_AMOUNT_NOTE }));
    view.append(el("p", { class: "f2-result-context", text: state.filters.source_region
      ? `ขอบเขตตัวเลข: ${filterValueLabel("source_region", state.filters.source_region, data)} (ภูมิภาคตามต้นทาง)`
      : state.province ? `ขอบเขตตัวเลข: จังหวัด${provinceName(state.province)}` : "ขอบเขตตัวเลข: ประเทศไทย" }));
    const origin = sourceLine(definition?.source_ids);
    if (origin) view.append(el("p", { class: "f2-result-context", text: origin }));
    if (metricExplanation(state.measure)) view.append(el("p", { class: "f2-result-context", text: metricExplanation(state.measure) }));
    const businessBreakdown = data.source_dimension_breakdown;
    if (state.measure === "C08_REPORTED_BUSINESSES" && businessBreakdown?.rows?.length) {
      const table = el("table", { class: "f2-source-region-table" },
        el("thead", {}, el("tr", {}, el("th", { scope: "col", text: businessBreakdown.label_th }), el("th", { scope: "col", text: "จำนวนธุรกิจ" }))),
        el("tbody", {}, businessBreakdown.rows.map((row) => el("tr", {},
          el("th", { scope: "row", text: row.label_th }),
          el("td", { text: `${formattedCount(row.display_value)} ${row.unit || ""}`.trim() }),
        ))),
      );
      view.append(section("ข้อมูลแยกตามต้นทาง", el("div", { class: "f2-table-scroll", tabindex: "0" }, table),
        "เลือกวิธีแบ่งข้อมูลได้ในตัวกรอง แต่ละวิธีนับธุรกิจชุดเดียวกัน จึงไม่ควรนำยอดจากต่างวิธีมาบวกกัน"));
    }
    if (Array.isArray(data.source_region_results) && data.source_region_results.length) {
      const table = el("table", { class: "f2-source-region-table" });
      const selectedRegion = state.filters.source_region || "";
      table.append(el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "ภูมิภาคตามต้นทาง" }), el("th", { scope: "col", text: "ค่า" }), el("th", { scope: "col", text: "สถานะ" }))));
      table.append(el("tbody", {}, data.source_region_results.map((row) => {
        const selected = String(row.source_region_id) === selectedRegion;
        return el("tr", { class: selected ? "f2-region-selected" : null },
          el("th", { scope: "row" }, row.label_th, selected ? el("span", { class: "f2-region-current", text: "เลือกอยู่" }) : ""),
          el("td", { text: [row.result?.display_value || "—", row.result?.unit].filter(Boolean).join(" ") }),
          el("td", { text: statusLabel(row.result?.status || row.result?.availability || "") || "—" }),
        );
      })));
      view.append(section("เปรียบเทียบทุกภูมิภาคตามต้นทาง", el("div", { class: "f2-table-scroll", tabindex: "0" }, table), "ตารางแสดงทุกภูมิภาคเพื่อเปรียบเทียบ โดยเน้นแถวที่เลือก ภูมิภาคตามต้นทางไม่ใช่ภาคของแดชบอร์ด"));
    }
    if (!list.capability || ["none", "unavailable", "aggregate_only"].includes(list.capability)) {
      const unavailable = data.availability === "unavailable" || data.result?.availability === "unavailable";
      const explanation = unavailable
        ? MEASURE_LIMITATIONS[state.measure] || "ยังไม่มีข้อมูลเพียงพอสำหรับคำนวณตัวชี้วัดนี้"
        : "ข้อมูลชุดนี้แสดงเป็นยอดรวม จึงไม่มีรายชื่อให้ค้นหา";
      view.append(section("เกี่ยวกับข้อมูลชุดนี้", el("div", { class: "f2-aggregate-explanation" },
        el("p", { text: explanation }),
        el("button", { type: "button", text: "ดูที่มาและข้อควรทราบ", onclick: () => setTab("sources") }),
      )));
      return;
    }
    const scopedCount = formattedCount(list.scoped_item_count);
    const matchingCount = formattedCount(list.matching_item_count);
    const countSummary = searching && scopedCount && matchingCount
      ? `${matchingCount} รายการที่ตรงคำค้นหา จาก ${scopedCount} รายการในขอบเขตที่เลือก`
      : `${matchingCount || formattedCount(items.length)} รายการที่ตรงเงื่อนไข`;
    if (!items.length) {
      const empty = el("div", { class: "f2-list-empty" },
        el("p", { class: "f2-results-summary", role: "status", "aria-live": "polite", text: countSummary }),
        el("p", { text: "ไม่พบรายการที่ตรงกับเงื่อนไขนี้ ลองเปลี่ยนคำค้นหาหรือตัวกรอง" }),
      );
      if (searching) empty.append(el("button", { type: "button", text: "ล้างคำค้นหา", onclick: () => {
        state.searchDraft = "";
        clearTimeout(state.searchTimer);
        applyFilter("q", "");
      } }));
      if (Object.keys(state.filters).length) empty.append(el("button", { type: "button", text: "ล้างคำค้นหาและตัวกรองรายการ", onclick: clearListFilters }));
      view.append(section("รายการ", empty));
      return;
    }
    view.append(el("p", { class: "f2-result-context", text: `เรียง: ${{ source: "ลำดับในชุดข้อมูล", name_asc: "ตามชื่อ (น้อยไปมาก)", name_desc: "ตามชื่อ (มากไปน้อย)" }[state.sort]} · เปลี่ยนได้ในตัวกรอง` }));
    view.append(section("รายการ", el("div", { class: "f2-item-list" }, items.map(itemCard)), el("p", { class: "f2-results-summary", role: "status", "aria-live": "polite", text: countSummary })));
    const previous = el("button", { type: "button", "aria-label": "หน้าก่อนหน้า", text: "ก่อนหน้า", disabled: !list.offset, onclick: () => { state.offset = Math.max(0, Number(list.offset || 0) - state.limit); writeUrl(true); loadTopic(); } });
    const next = el("button", { type: "button", "aria-label": "หน้าถัดไป", text: "ถัดไป", disabled: Number(list.offset || 0) + Number(list.returned_count || items.length) >= Number(list.matching_item_count || 0), onclick: () => { state.offset = Number(list.offset || 0) + Number(list.returned_count || items.length); writeUrl(true); loadTopic(); } });
    view.append(el("nav", { class: "f2-pagination", "aria-label": "เปลี่ยนหน้ารายการ" }, previous, el("span", { text: `แสดง ${Number(list.offset || 0) + 1}–${Number(list.offset || 0) + items.length} จาก ${matchingCount} รายการ` }), next));
    restorePendingListFocus();
  }
  function renderScopeNotice(view) {
    if (!state.scopeNotice) return;
    view.append(el("div", { class: "f2-scope-notice", role: "status" }, el("strong", { text: "ปรับขอบเขตข้อมูลแล้ว" }), el("p", { text: state.scopeNotice })));
  }
  function recoverUnsupportedProvince(error) {
    if (!state.province || !/unsupported|filter combination|ตัวกรอง/.test(error.message)) return false;
    const definition = selectedMeasureDefinition();
    const provinceName = (state.callbacks.getProvinces?.() || []).find((province) => text(province.province_code) === state.province)?.province_name_th || "จังหวัดที่เลือก";
    state.rememberedProvince = state.province;
    state.province = "";
    state.scopeNotice = `${measureDisplayLabel(definition) || "ตัวชี้วัดนี้"} ไม่มีข้อมูลระดับจังหวัด ระบบจึงเปลี่ยนจาก ${provinceName} เป็นมุมมองประเทศไทย`;
    if (!state.filterDraft) state.callbacks.onProvinceRestore?.("");
    writeUrl(false);
    loadOverview();
    return true;
  }
  async function loadTopic() {
    if (!state.open || state.tab !== "list" || !state.topic) { if (!state.topic) status(views.list, "ยังไม่มีหัวข้อรายการ", "เลือกตัวชี้วัดจากภาพรวมก่อน"); return; }
    status(views.list, "กำลังโหลดรายการ", "กำลังขอข้อมูลตามเงื่อนไขที่เลือก");
    try { const data = await request(`/topics/${encodeURIComponent(state.topic)}` + query(apiScope({ limit: state.limit, offset: state.offset, sort: state.sort })), "topic"); if (!data) return; state.topicData = data; state.revision = data.revision || state.revision; renderList(data); }
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
  function datasetCoverageCount(data) {
    const coverage = data?.headlines?.find((item) => item.measure_id === "K01A")?.coverage;
    return coverage?.national_total ?? null;
  }
  async function loadSources() {
    status(views.sources, "กำลังโหลดที่มา", "กำลังขอคำจำกัดความและแหล่งข้อมูล");
    try {
      const current = state.topicData;
      const topicIsCurrent = current?.topic_id === state.topic && current?.measure_id === state.measure
        && current?.scope === (state.province ? `province/${state.province}` : "national");
      const [data, coverage] = await Promise.all([
        !state.topic || topicIsCurrent ? Promise.resolve(current)
          : request(`/topics/${encodeURIComponent(state.topic)}` + query(detailScope()), "topic"),
        state.coverageData?.revision === state.revision ? Promise.resolve(state.coverageData)
          : request("/topics/k01a" + query({ measure: "K01A", revision: state.revision }), "coverage"),
      ]);
      if (!coverage || (state.topic && !data) || !state.open || state.tab !== "sources") return;
      state.topicData = data;
      state.coverageData = coverage;
      renderSources();
    } catch (error) {
      if (error.stale || error.name === "AbortError") return;
      if (recoverUnsupportedProvince(error)) return;
      status(views.sources, "เปิดที่มาไม่ได้", "ระบบยังเปิดที่มานี้ไม่ได้ โปรดลองอีกครั้ง", loadSources);
    }
  }
  // Every source of the release: when we fetched it, and the latest change date the source itself states.
  function renderSourceDates(view) {
    const snapshots = Object.values(sourceSnapshots());
    if (!snapshots.length) return;
    const windowDays = Number(state.overview.sources.updated_within_days) || 365;
    const span = windowDays === 365 ? "1 ปี" : `${formattedCount(windowDays)} วัน`;
    const freshness = { stamped_within_window: `พบวันที่แก้ไขภายใน ${span} ก่อนวันดึง`, none_within_window: `ไม่พบวันที่แก้ไขภายใน ${span} ก่อนวันดึง`, no_date: "ต้นทางไม่ระบุวันที่" };
    const rows = snapshots.slice().sort((a, b) => text(SOURCE_NAMES[a.source_id]).localeCompare(text(SOURCE_NAMES[b.source_id]), "th"));
    const table = el("table", { class: "f2-source-region-table f2-source-dates-table" },
      el("thead", {}, el("tr", {}, ["แหล่งข้อมูล", "ดึงข้อมูลล่าสุด", "ต้นทางแก้ไขล่าสุด", "สถานะ"].map((name) => el("th", { scope: "col", text: name })))),
      el("tbody", {}, rows.map((row) => el("tr", {},
        // phones hide the status column and show the status under the name instead
        el("th", { scope: "row" }, SOURCE_NAMES[row.source_id] || row.source_id,
          el("span", { class: `f2-freshness f2-freshness--${row.freshness} f2-freshness--inline`, text: freshness[row.freshness] || row.freshness })),
        el("td", { text: fetchedRange([row.source_id]) }),
        el("td", {}, row.updated
          ? [`${row.updated.basis_th} ล่าสุด ${thaiDay(row.updated.latest)}`, el("small", { text: row.updated.days === 1 && row.updated.records > 1
            ? `ทั้ง ${formattedCount(row.updated.records)} รายการลงวันที่เดียวกัน จึงน่าจะเป็นวันที่ของทั้งชุดข้อมูล`
            : `จาก ${formattedCount(row.updated.records)} รายการที่ต้นทางระบุวันที่` })]
          : "—"),
        el("td", {}, el("span", { class: `f2-freshness f2-freshness--${row.freshness}`, text: freshness[row.freshness] || row.freshness }))))));
    view.append(section("แหล่งข้อมูลและวันที่ของข้อมูล", el("div", { class: "f2-source-dates" },
      el("dl", { class: "f2-detail-facts" },
        el("dt", { text: "ดึงข้อมูล" }), el("dd", { text: "วันที่ระบบของเราไปเก็บข้อมูลจากเว็บต้นทาง ตัวเลขทุกตัวบอกวันที่นี้ไว้ใต้ตัวเลข" }),
        el("dt", { text: "ต้นทางแก้ไขล่าสุด" }), el("dd", { text: "วันที่แก้ไขล่าสุดที่เว็บต้นทางใส่ไว้ในรายการ มีให้แค่บางแหล่ง และบางแหล่งใส่ไว้แค่ในข้อมูลบางส่วน (ตารางบอกว่าครอบคลุมอะไร) เป็นวันที่ที่ต้นทางระบุเอง ไม่ได้ยืนยันว่าเนื้อหาเปลี่ยนจริง และไม่ได้บอกว่าแหล่งยังมีคนดูแล ข้อมูลถูกต้อง หรือครบถ้วน" })),
      el("div", { class: "f2-table-scroll", tabindex: "0", role: "region", "aria-label": "ตารางวันที่ของแหล่งข้อมูล" }, table))));
  }
  function renderSources() {
    const view = views.sources; clear(view); controls(state.topicData || state.overview || {});
    backToOverview(view);
    renderScopeNotice(view);
    renderSourceDates(view);
    const data = state.topicData || state.overview || {};
    const definition = selectedMeasureDefinition();
    const coverage = state.coverageData;
    if (coverage) {
      const summary = el("summary", { text: MEASURE_HELP_TITLES.K01A });
      const coverageDetails = el("details", { class: "f2-coverage-details", open: state.openCoverage },
        summary,
        el("p", { text: `ความครอบคลุมของข้อมูลทั้งประเทศ: ${formattedCount(coverage.coverage?.national_total ?? coverage.result?.value)} จังหวัด` }),
        el("p", { text: MEASURE_LIMITATIONS.K01A }),
        el("strong", { text: "แหล่งข้อมูลที่ใช้ในการนับความครอบคลุม" }),
      );
      appendLinks(coverageDetails, (coverage.sources || []).map((source) => ({
        url: source.public_url, label: SOURCE_NAMES[source.source_id] || source.originating_system,
      })));
      view.append(coverageDetails);
      if (state.openCoverage) summary.focus();
      state.openCoverage = false;
    }
    if (definition) {
      const geography = supportsProvince(definition)
        ? "ดูได้ทั้งประเทศไทยและจังหวัดที่แหล่งข้อมูลรองรับ"
        : definition.filter_contract?.supported_filters?.includes("source_region")
          ? "ดูได้ระดับประเทศไทยและภูมิภาคตามที่แหล่งข้อมูลรายงาน ไม่ใช่ระดับจังหวัด"
          : "แสดงตามขอบเขตที่แหล่งข้อมูลรองรับ โดยไม่มีตัวเลขระดับจังหวัด";
      view.append(section("ตัวเลขนี้หมายถึงอะไร", el("div", { class: "f2-source-summary" },
        el("p", { text: measureDisplayLabel(definition) || state.measure }),
        el("dl", { class: "f2-detail-facts" },
          el("dt", { text: "หน่วย" }), el("dd", { text: definition.unit || data.result?.unit || "ไม่ระบุ" }),
          el("dt", { text: "ขอบเขตพื้นที่" }), el("dd", { text: geography }),
        ),
      )));
    }
    if (state.measure === C02_MEASURE_ID) {
      view.append(section(
        "ข้อควรทราบ",
        el("p", { text: "รายชื่อในทะเบียนนี้เป็นคนละชุดข้อมูลกับ “นวัตกรตามยอดรวมที่ PMUA รายงาน” จึงไม่ควรนำตัวเลขของทั้งสองชุดมารวมกัน" }),
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
          fetchedRange([source.source_id]) ? el("p", { text: `ดึงข้อมูล ${fetchedRange([source.source_id])}` }) : "",
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
    if (state.measure === "K10") view.append(section("ยอดที่ยังไม่รวมในการคำนวณ", el("p", { text: K10_EXCLUDED_AMOUNT_NOTE })));
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
  // University tab: every university the sources name, then one university with its innovations (?f2uni=).
  async function loadUniversities() {
    if (!state.open || state.tab !== "universities") return;
    const view = views.universities;
    status(view, "กำลังโหลดข้อมูลมหาวิทยาลัย", "กำลังขอข้อมูลจากระบบ");
    if (!state.university) abort("university");
    const wanted = JSON.stringify([state.university, state.universityQuery, state.universityOffset]);
    const current = () => state.tab === "universities" && wanted === JSON.stringify([state.university, state.universityQuery, state.universityOffset]);
    try {
      const list = state.universities && state.universities.revision === state.revision ? state.universities
        : await request("/universities" + query({ revision: state.revision }), "universities");
      if (!list || !current()) return;
      state.universities = list;
      state.revision = list.revision || state.revision;
      if (!state.university) { renderUniversities(list); return; }
      const data = await request(`/universities/${encodeURIComponent(state.university)}`
        + query({ q: state.universityQuery, limit: state.limit, offset: state.universityOffset, revision: state.revision }), "university");
      if (!data || !current()) return;
      renderUniversity(list, data);
    } catch (error) {
      if (error.stale || error.name === "AbortError") return;
      if (error.status === 404 && state.university) { showUniversity("", false); return; }
      if (error.status === 404) { status(view, "ข้อมูลชุดนี้ยังไม่มีมุมมองมหาวิทยาลัย", "ข้อมูลที่เผยแพร่ชุดนี้สร้างก่อนมีแท็บมหาวิทยาลัย"); return; }
      status(view, "เปิดข้อมูลมหาวิทยาลัยไม่ได้", "ระบบยังเปิดข้อมูลนี้ไม่ได้ โปรดลองอีกครั้ง", loadUniversities);
    }
  }
  function showUniversity(id, push = true) {
    state.universityFocus = id ? "heading" : state.university && `row:${state.university}`;
    state.university = id;
    state.universityOffset = 0;
    state.universityQuery = "";
    writeUrl(push);
    panel.querySelector(".f2-stage").scrollTop = 0;
    loadUniversities();
  }
  function countList(counts, rows) {
    return el("dl", { class: "f2-university-counts" }, rows.map(([measureId, name]) => el("div", {},
      el("dt", { text: name }), el("dd", { text: formattedCount(counts?.[measureId]) || "0" }))));
  }
  function applyUniversityFocus(view) {
    const focus = state.universityFocus;
    state.universityFocus = "";
    const target = focus === "heading" ? view.querySelector(".f2-university-head h3")
      : focus === "search" ? $("f2UniversityItemSearch")
        : focus === "list" ? view.querySelector(".f2-item")
          : focus.startsWith("row:") ? view.querySelector(`[data-f2-university-id="${CSS.escape(focus.slice(4))}"]`) : null;
    target?.focus({ preventScroll: focus !== "list" });
  }
  function bar(value, max) {
    const fill = el("span");
    fill.style.width = `${Math.round(100 * (Number(value) || 0) / Math.max(1, max))}%`;
    return el("span", { class: "f2-bar", "aria-hidden": "true" }, fill);
  }
  function renderUniversities(list) {
    const view = clear(views.universities);
    const groups = list.groups || {};
    const rows = list.universities || [];
    backToOverview(view);
    view.append(el("p", { class: "f2-result-context", text: "ขอบเขต: ประเทศไทย · แท็บนี้ยังไม่แยกตามจังหวัด" }));
    const [comparison, ...howCounted] = list.notes || [];
    view.append(section("ผลงานแยกตามกลุ่มมหาวิทยาลัย", el("div", { class: "f2-university-groups" },
      UNIVERSITY_GROUP_ORDER.filter((key) => groups[key]).map((key) => el("article", { class: "f2-university-group" },
        el("h4", {}, groups[key].label_th, el("span", { text: `${formattedCount(groups[key].university_count)} แห่ง` })),
        countList(groups[key].counts, UNIVERSITY_COUNTS)))),
      comparison ? el("p", { class: "f2-university-note", text: comparison }) : ""));
    const coverage = UNIVERSITY_COUNTS.map(([measureId, name]) => {
      const row = list.coverage?.[measureId];
      return row ? `${name} ${formattedCount(row.with_university)} จาก ${formattedCount(row.counted)}` : "";
    }).filter(Boolean).join(" · ");
    if (coverage) view.append(el("p", { class: "f2-result-context", text: `ระบุมหาวิทยาลัยได้: ${coverage}` }));
    const origin = sourceLine(list.attribution_source_ids, "แหล่งที่ระบุมหาวิทยาลัย");
    if (origin) view.append(el("p", { class: "f2-result-context", text: origin }));
    if (howCounted.length) view.append(el("details", { class: "f2-university-method" },
      el("summary", { text: "นับอย่างไร" }), el("ul", {}, howCounted.map((note) => el("li", { text: note })))));

    const search = el("input", { id: "f2UniversitySearch", type: "search", placeholder: "ชื่อมหาวิทยาลัย", autocomplete: "off", value: state.universitySearch });
    const summary = el("p", { class: "f2-results-summary", role: "status", "aria-live": "polite" });
    const body = el("tbody");
    const max = Math.max(...rows.map((row) => Number(row.counts?.C04_LISTED) || 0));
    const fill = () => {
      const wanted = search.value.trim().normalize("NFKC");
      const shown = rows.filter((row) => !wanted || text(row.name_th).normalize("NFKC").includes(wanted));
      body.replaceChildren(...shown.map((row) => el("tr", {},
        el("th", { scope: "row" },
          el("button", { type: "button", class: "f2-university-link", "data-f2-university-id": row.university_id, text: row.name_th, onclick: () => showUniversity(row.university_id) }),
          // the group only where the name does not already say it ("มหาวิทยาลัยราชภัฏ..." does)
          text(row.name_th).startsWith(groups[row.group]?.label_th) ? "" : el("span", { class: "f2-university-group-label", text: groups[row.group]?.label_th || "" })),
        el("td", {}, el("span", { class: "f2-bar-value" }, bar(row.counts?.C04_LISTED, max), formattedCount(row.counts?.C04_LISTED) || "0")),
        el("td", { text: formattedCount(row.counts?.C02_COMMUNITY) || "0" }),
        el("td", { text: formattedCount(row.counts?.K05) || "0" }),
        el("td", { text: formattedCount(row.province_count) || "0" }))));
      summary.textContent = wanted ? `${shown.length} จาก ${rows.length} แห่งที่ตรงคำค้นหา` : `${rows.length} แห่ง เรียงตามจำนวนนวัตกรรม`;
    };
    search.addEventListener("input", () => { state.universitySearch = search.value.trim(); writeUrl(false); fill(); });
    fill();
    const table = el("table", { class: "f2-source-region-table f2-university-table" },
      el("thead", {}, el("tr", {}, ["มหาวิทยาลัย", "นวัตกรรม", "นวัตกร", "ธุรกิจ", "จังหวัด"]
        .map((name) => el("th", { scope: "col", text: name })))), body);
    view.append(section("รายชื่อมหาวิทยาลัย", el("div", { class: "f2-university-list" },
      el("label", { class: "f2-university-search", htmlFor: "f2UniversitySearch", text: "ค้นหา" }, search),
      summary, el("div", { class: "f2-table-scroll", tabindex: "0" }, table))));
    applyUniversityFocus(view);
  }
  function renderUniversity(list, data) {
    const view = clear(views.universities);
    const university = data.university || {};
    const counts = university.counts || {};
    const items = data.list?.items || [];
    view.append(el("button", { type: "button", class: "f2-back-overview", text: "← กลับไปรายชื่อมหาวิทยาลัย", onclick: () => showUniversity("") }));
    view.append(el("header", { class: "f2-university-head" },
      el("p", { class: "f2-detail-eyebrow", text: data.group_label_th || "" }), el("h3", { text: university.name_th, tabindex: "-1" })));
    const places = university.innovation_provinces || [];
    view.append(countList({ ...counts, provinces: places.length }, [
      ["C04_LISTED", "นวัตกรรม"], ["K04", "มีหลักฐาน TRL 8–9"], ["C02_COMMUNITY", "นวัตกรชุมชน"],
      ["K05", "ธุรกิจที่โยงกับมหาวิทยาลัย"], ["provinces", "จังหวัดที่ใช้นวัตกรรม"]]));
    view.append(el("p", { class: "f2-result-context", text: "TRL 8–9 คือระดับที่แหล่งข้อมูลระบุ ไม่ใช่การยืนยันว่าใช้งานได้ในวันนี้ และบางชิ้นมีแหล่งที่ระบุระดับต่างกัน · "
      + "ธุรกิจนับเมื่อแหล่งข้อมูลระบุหน่วยวิจัยที่ดูแล หรือพบชื่อธุรกิจในข้อมูลนวัตกรรมของมหาวิทยาลัยนี้ จึงยังไม่ได้ยืนยันว่าเข้าร่วมโครงการ" }));
    if (places.length) {
      const max = Number(places[0].count) || 1;
      const row = (place) => el("li", {}, el("span", { text: place.province_name_th || place.province_code }), bar(place.count, max), el("span", { text: formattedCount(place.count) }));
      const top = el("ol", { class: "f2-university-places" }, places.slice(0, 5).map(row));
      view.append(section("นวัตกรรมไปใช้ที่จังหวัดไหนมากที่สุด", el("div", {}, top, places.length > 5
        ? el("details", { class: "f2-detail-more" }, el("summary", { text: `อีก ${places.length - 5} จังหวัด` }), el("ol", { class: "f2-university-places" }, places.slice(5).map(row)))
        : "")));
    }
    const sources = (university.innovation_sources || []).map((row) => `${SOURCE_NAMES[row.source_id] || row.source_id} ${formattedCount(row.count)}`);
    if (sources.length) view.append(el("p", { class: "f2-result-context", text: `ที่มาของนวัตกรรม: ${sources.join(" · ")} (นวัตกรรมชิ้นเดียวกันอยู่ได้หลายแหล่ง)` }));
    // each count with the sources that tie it to this university, and when they were fetched
    const origins = UNIVERSITY_COUNTS.map(([measureId, name]) => sourceLine(university.source_ids_by_measure?.[measureId], `ที่มาของ${name}`)).filter(Boolean);
    if (origins.length) view.append(el("ul", { class: "f2-result-context f2-university-origins" }, origins.map((line) => el("li", { text: line }))));

    const search = el("input", { id: "f2UniversityItemSearch", type: "search", placeholder: "ชื่อนวัตกรรม", value: state.universityQuery, autocomplete: "off" });
    const form = el("form", { class: "f2-university-search", role: "search", onsubmit: (event) => {
      event.preventDefault();
      state.universityQuery = search.value.trim();
      state.universityOffset = 0;
      state.universityFocus = "search";
      writeUrl(true);
      loadUniversities();
    } }, el("label", { htmlFor: "f2UniversityItemSearch", text: "ค้นหานวัตกรรมของมหาวิทยาลัยนี้" }, search), el("button", { type: "submit", class: "f2-retry", text: "ค้นหา" }));
    const found = data.list || {};
    const matching = formattedCount(found.matching_item_count) || "0";
    const cards = items.map((item) => {
      const model = window.F2DetailPresenter?.presentListItem?.(found.measure_id, item) || { title: titleOf(item), context: [], action: "ดูรายละเอียด" };
      return el("button", { class: "f2-item", type: "button", "data-f2-detail-id": item.entity_id, "aria-label": `${model.action} ${model.title}`,
        onclick: () => openTargetDetail({ topicId: found.topic_id, measureId: found.measure_id, entityId: item.entity_id }) },
      el("h3", { text: model.title }),
      model.context?.length ? el("p", { class: "f2-item-context", text: model.context.join(" · ") }) : "",
      el("span", { class: "f2-item-action", text: `${model.action} →` }));
    });
    view.append(section(`นวัตกรรมของมหาวิทยาลัยนี้`, el("div", { class: "f2-university-list" }, form,
      el("p", { class: "f2-results-summary", role: "status", "aria-live": "polite", text: state.universityQuery
        ? `${matching} รายการที่ตรงคำค้นหา จาก ${formattedCount(found.scoped_item_count)} รายการ` : `${matching} รายการ เรียงตามชื่อ` }),
      cards.length ? el("div", { class: "f2-item-list" }, cards) : el("p", { text: "ไม่พบนวัตกรรมที่ตรงกับคำค้นหา" }))));
    if (Number(found.matching_item_count) > items.length) {
      const offset = Number(found.offset || 0);
      const page = (next) => { state.universityOffset = next; state.universityFocus = "list"; writeUrl(true); panel.querySelector(".f2-stage").scrollTop = 0; loadUniversities(); };
      view.append(el("nav", { class: "f2-pagination", "aria-label": "เปลี่ยนหน้ารายการนวัตกรรม" },
        el("button", { type: "button", text: "ก่อนหน้า", disabled: !offset, onclick: () => page(Math.max(0, offset - state.limit)) }),
        el("span", { text: `แสดง ${offset + 1}–${offset + items.length} จาก ${matching} รายการ` }),
        el("button", { type: "button", text: "ถัดไป", disabled: offset + items.length >= Number(found.matching_item_count), onclick: () => page(offset + items.length) })));
    }
    if (list.notes?.length) view.append(el("details", { class: "f2-university-method" },
      el("summary", { text: "นับอย่างไร" }), el("ul", {}, list.notes.map((note) => el("li", { text: note })))));
    restorePendingListFocus();
    applyUniversityFocus(view);
  }
  // Innovation tab: every innovation (C04) with what its sources state that helps follow it up (/topics/k04 list
  // filters). The map keeps showing all innovations by province; these filters only narrow the list.
  function enterInnovations() {
    if (state.measure !== INNOVATION_MEASURE) selectMeasure(INNOVATION_MEASURE);
    state.filters = {};
    state.searchDraft = "";
    state.offset = 0;
    state.sort = "source";
    state.scopeNotice = "";
    clearTimeout(state.searchTimer);
  }
  async function loadInnovations() {
    if (!state.open || state.tab !== "innovations") return;
    const view = views.innovations;
    const wanted = JSON.stringify([state.province, state.innovationFilters, state.innovationOffset]);
    const current = () => state.tab === "innovations" && wanted === JSON.stringify([state.province, state.innovationFilters, state.innovationOffset]);
    status(view, "กำลังโหลดรายการนวัตกรรม", "กำลังขอข้อมูลตามเงื่อนไขที่เลือก");
    try {
      // the university filter's names
      const universities = state.universities && state.universities.revision === state.revision ? state.universities
        : await request("/universities" + query({ revision: state.revision }), "universities");
      if (!current()) return;
      if (universities) state.universities = universities;
      const data = await request("/topics/k04" + query({ measure: INNOVATION_MEASURE, province: state.province, ...state.innovationFilters,
        limit: state.limit, offset: state.innovationOffset, revision: state.revision }), "innovations");
      if (!data || !current()) return;
      state.revision = data.revision || state.revision;
      renderInnovations(data);
    } catch (error) {
      if (error.stale || error.name === "AbortError") return;
      if (error.status === 404) { status(view, "ข้อมูลชุดนี้ยังไม่มีแท็บนวัตกรรม", "ข้อมูลที่เผยแพร่ชุดนี้สร้างก่อนมีแท็บนวัตกรรม"); return; }
      // a link from an older release can name a filter value this one does not have
      if (error.status === 422 && Object.keys(state.innovationFilters).length) {
        status(view, "ใช้ตัวกรองนี้ไม่ได้", "ตัวกรองบางค่าไม่มีในข้อมูลชุดนี้");
        view.querySelector(".f2-status").append(el("button", { type: "button", class: "f2-retry", text: "ล้างตัวกรอง", onclick: () => clearInnovationFilters() }));
        return;
      }
      status(view, "เปิดรายการนวัตกรรมไม่ได้", "ระบบยังเปิดรายการนี้ไม่ได้ โปรดลองอีกครั้ง", loadInnovations);
    }
  }
  function setInnovationFilter(key, value) {
    if (value) state.innovationFilters[key] = value;
    else delete state.innovationFilters[key];
    state.innovationOffset = 0;
    state.innovationFocus = `f2i-${key}`;
    writeUrl(true);
    loadInnovations();
  }
  function clearInnovationFilters() {
    state.innovationFilters = {};
    state.innovationOffset = 0;
    state.innovationFocus = "f2i-university";
    writeUrl(true);
    loadInnovations();
  }
  function countedFrom(ids, all) {
    return ids.length === all.length ? "นับจากนวัตกรรมทุกแหล่ง" : `นับเฉพาะนวัตกรรมจาก ${ids.map((id) => SOURCE_NAMES[id] || id).join(", ")}`;
  }
  // One innovation with its follow-up badges; with a source filter, only that source's evidence and TRL.
  function innovationCard(item, followUp) {
    const source = state.innovationFilters.source;
    const rows = source ? { [source]: item.follow_up?.[source] || {} } : item.follow_up || {};
    const considered = Object.keys(rows);
    const model = window.F2DetailPresenter?.presentListItem?.(INNOVATION_MEASURE, item) || { title: titleOf(item), warning: "", action: "ดูรายละเอียด" };
    const stated = considered.filter((id) => rows[id].trl?.length);
    const levels = new Set(stated.flatMap((id) => rows[id].trl));
    const trl = !levels.size ? "ไม่ระบุ TRL"
      : `TRL ตามที่แหล่งระบุ: ${stated.map((id) => `${rows[id].trl.join(", ")} (${SOURCE_NAMES[id] || id})`).join(" · ")}${levels.size > 1 ? " · แหล่งระบุไม่ตรงกัน" : ""}`;
    // a kind none of these sources carries gets no badge: "not found" would claim a field the source does not have
    const badges = (followUp.evidence || []).filter((kind) => considered.some((id) => kind.source_ids.includes(id))).map((kind) => {
      const values = considered.map((id) => rows[id][kind.field]).filter(Boolean);
      if (!values.length) return el("span", { class: "f2-follow-up-badge f2-follow-up-missing", text: kind.missing_th });
      const extra = kind.field === "updated" ? ` ${thaiDay(values.sort().at(-1))}`
        : kind.field === "project_codes" ? ` ${[...new Set(values.flat())].join(", ")}` : "";
      return el("span", { class: "f2-follow-up-badge", text: kind.label_th + extra });
    });
    const universities = item.university_names_th || [];
    // with a source selected, only the provinces that source states
    const provinces = source ? (rows[source].province_codes || []).map(provinceName) : item.province_names_th || [];
    const where = source ? "พื้นที่ที่แหล่งนี้ระบุ" : "พื้นที่ที่ต้นทางระบุ";
    const list = (names, prefix = "") => names.length > 3 ? `${names.slice(0, 3).map((n) => prefix + n).join(", ")} และอีก ${names.length - 3}` : names.map((n) => prefix + n).join(", ");
    // no aria-label: the button's name is its whole text, so a screen reader hears the evidence too
    return el("button", { class: "f2-item f2-innovation-item", type: "button", "data-f2-detail-id": item.entity_id,
      onclick: () => { state.topic = "k04"; state.measure = INNOVATION_MEASURE; openDetail(item.entity_id); } },
    el("h3", { text: model.title }),
    el("p", { class: "f2-item-context", text: universities.length ? list(universities) : "แหล่งข้อมูลไม่ได้ระบุมหาวิทยาลัย" }),
    el("p", { class: "f2-item-preview", text: provinces.length ? `${where}: ${list(provinces, "จังหวัด")}` : `ไม่มี${where}` }),
    el("p", { class: "f2-item-preview", text: trl }),
    el("span", { class: "f2-follow-up-badges" }, badges),
    el("p", { class: "f2-item-preview", text: `ที่มา: ${considered.map((id) => SOURCE_NAMES[id] || id).join(" · ")}` }),
    model.warning ? el("span", { class: "f2-item-warning", text: model.warning }) : "",
    el("span", { class: "f2-item-action", text: `${model.action} →` }));
  }
  function renderInnovations(data) {
    const view = clear(views.innovations);
    const followUp = data.follow_up;
    if (!isObject(followUp)) { status(view, "ข้อมูลชุดนี้ยังไม่มีแท็บนวัตกรรม", "ข้อมูลที่เผยแพร่ชุดนี้สร้างก่อนมีแท็บนวัตกรรม"); return; }
    const list = data.list || {};
    const items = list.items || [];
    const summary = list.summary || { matching: 0, evidence: [] };
    const kinds = followUp.evidence || [];
    const allSources = [...new Set(kinds.flatMap((kind) => kind.source_ids))];
    const [limitation, ...notes] = followUp.notes_th || [];
    backToOverview(view);
    view.append(el("p", { class: "f2-result-context", text: state.province ? `ขอบเขต: จังหวัด${provinceName(state.province)}` : "ขอบเขต: ประเทศไทย" }));

    const select = (key, name, options) => {
      const node = el("select", { id: `f2i-${key}` }, el("option", { value: "", text: "ทั้งหมด" }),
        options.map(([value, label]) => el("option", { value, text: label })));
      node.value = state.innovationFilters[key] || "";
      node.addEventListener("change", () => setInnovationFilter(key, node.value));
      return el("label", { htmlFor: `f2i-${key}`, text: name }, node);
    };
    const province = el("select", { id: "f2i-province" }, el("option", { value: "", text: "ทั่วประเทศ" }),
      (state.callbacks.getProvinces?.() || []).map((row) => [text(row.province_code), text(row.province_name_th)]).filter(([code, name]) => code && name)
        .sort((a, b) => a[1].localeCompare(b[1], "th")).map(([code, name]) => el("option", { value: code, text: name })));
    province.value = state.province;
    province.addEventListener("change", () => { state.innovationFocus = "f2i-province"; handleProvince(province.value, true); });
    const universities = [...(state.universities?.universities || [])].sort((a, b) => text(a.name_th).localeCompare(text(b.name_th), "th"));
    const search = el("input", { id: "f2i-q", type: "search", value: state.innovationFilters.q || "", placeholder: "ชื่อนวัตกรรมหรือรหัสโครงการ", autocomplete: "off" });
    const form = el("form", { class: "f2-university-search", role: "search", onsubmit: (event) => { event.preventDefault(); setInnovationFilter("q", search.value.trim()); } },
      el("label", { htmlFor: "f2i-q", text: "ค้นหา" }, search), el("button", { type: "submit", class: "f2-retry", text: "ค้นหา" }));
    const filters = el("div", { class: "f2-innovation-filters" },
      select("university", "มหาวิทยาลัย", universities.map((row) => [row.university_id, row.name_th])),
      el("label", { htmlFor: "f2i-province", text: "จังหวัด (พื้นที่ที่ต้นทางระบุ)" }, province),
      select("source", "แหล่งข้อมูล", allSources.map((id) => [id, SOURCE_NAMES[id] || id])),
      select("trl", "ระดับความพร้อม (TRL)", (followUp.trl_bands || []).map((band) => [band.id, band.label_th])),
      select("evidence", "ข้อมูลประกอบ", kinds.map((kind) => [kind.id, kind.label_th])));
    const matching = formattedCount(list.matching_item_count) || "0";
    view.append(section("ค้นหาและกรองนวัตกรรม", el("div", { class: "f2-university-list" }, filters, form,
      Object.keys(state.innovationFilters).length ? el("button", { type: "button", class: "f2-retry", text: "ล้างตัวกรอง", onclick: clearInnovationFilters }) : "",
      el("p", { class: "f2-result-context", text: "แผนที่ไม่เปลี่ยนตามตัวกรองในแท็บนี้ แผนที่แสดงจำนวนนวัตกรรมทั้งหมดรายจังหวัด" }),
      el("p", { class: "f2-results-summary", role: "status", "aria-live": "polite", text: `${matching} รายการที่ตรงตัวกรอง จาก ${formattedCount(list.scoped_item_count) || "0"} นวัตกรรม` }))));

    // the cards count the whole filtered list, not this page
    const found = Object.fromEntries((summary.evidence || []).map((row) => [row.id, row]));
    const cards = el("div", { class: "f2-follow-up-cards" }, kinds.map((kind) => {
      const row = found[kind.id] || { found: 0, eligible: 0 };
      const others = Number(summary.matching) - Number(row.eligible);
      return el("article", { class: "f2-follow-up-card" },
        el("h4", { text: kind.label_th }),
        Number(row.eligible)
          ? el("p", { class: "f2-follow-up-value" }, el("strong", { text: formattedCount(row.found) || "0" }), ` จาก ${formattedCount(row.eligible)} ชิ้น`)
          : el("p", { class: "f2-follow-up-value", text: Number(summary.matching) ? "รายการที่เลือกมาจากแหล่งที่ไม่มีข้อมูลนี้" : "ไม่มีรายการที่ตรงตัวกรอง" }),
        el("p", { text: `${countedFrom(kind.source_ids, allSources)}${others > 0 && Number(row.eligible) ? ` · อีก ${formattedCount(others)} ชิ้นมาจากแหล่งที่ไม่มีข้อมูลนี้` : ""}` }),
        el("p", { class: "f2-follow-up-basis", text: kind.basis_th }));
    }));
    view.append(section(followUp.title_th, cards,
      `${matching} ชิ้นที่ตรงตัวกรอง · ตัวเลขของแต่ละใบนำมาบวกกันไม่ได้`));
    if (limitation) view.append(el("p", { class: "f2-follow-up-limit" }, el("strong", { text: "ข้อจำกัด: " }), limitation));
    if (notes.length) view.append(el("details", { class: "f2-university-method" },
      el("summary", { text: "วิธีอ่านข้อมูลนี้" }), el("ul", {}, notes.map((note) => el("li", { text: note })))));
    const origin = sourceLine(allSources);
    if (origin) view.append(el("p", { class: "f2-result-context", text: origin }));
    view.append(section("รายการนวัตกรรม", items.length ? el("div", { class: "f2-item-list" }, items.map((item) => innovationCard(item, followUp)))
      : el("p", { text: "ไม่พบนวัตกรรมที่ตรงกับตัวกรองนี้ ลองเปลี่ยนหรือล้างตัวกรอง" })));
    if (Number(list.matching_item_count) > items.length) {
      const offset = Number(list.offset || 0);
      const page = (next) => { state.innovationOffset = next; state.innovationFocus = "list"; writeUrl(true); panel.querySelector(".f2-stage").scrollTop = 0; loadInnovations(); };
      view.append(el("nav", { class: "f2-pagination", "aria-label": "เปลี่ยนหน้ารายการนวัตกรรม" },
        el("button", { type: "button", text: "ก่อนหน้า", disabled: !offset, onclick: () => page(Math.max(0, offset - state.limit)) }),
        el("span", { text: `แสดง ${offset + 1}–${offset + items.length} จาก ${matching} รายการ` }),
        el("button", { type: "button", text: "ถัดไป", disabled: offset + items.length >= Number(list.matching_item_count), onclick: () => page(offset + items.length) })));
    }
    const focus = state.innovationFocus;
    state.innovationFocus = "";
    if (focus) (focus === "list" ? view.querySelector(".f2-innovation-item") : $(focus))?.focus({ preventScroll: focus !== "list" });
    restorePendingListFocus();
  }
  // Area tab: where the sources place the work (national), and one province's brief (?province=).
  // List filters do not apply here: /overview ignores them, so the table, map and brief would disagree.
  function enterAreas() {
    if (!AREA_MEASURES.includes(state.measure)) selectMeasure(AREA_MEASURES[0]);
    state.filters = {};
    state.searchDraft = "";
    state.offset = 0;
    state.sort = "source";
    state.scopeNotice = "";
    clearTimeout(state.searchTimer);
  }
  async function loadAreas() {
    if (!state.open || state.tab !== "areas") return;
    if (!state.province) { renderAreas(); return; }
    const wanted = JSON.stringify([state.province, state.revision]);
    if (state.areaUniversities?.key !== wanted || state.areaUniversities.failed) {
      status(views.areas, "กำลังโหลดสรุปจังหวัด", "กำลังขอข้อมูลจากระบบ");
      try {
        const data = await request("/universities" + query({ province: state.province, revision: state.revision }), "areaUniversities");
        if (!data || state.tab !== "areas" || wanted !== JSON.stringify([state.province, state.revision])) return;
        state.areaUniversities = { key: wanted, data };
      } catch (error) {
        if (error.stale || error.name === "AbortError") return;
        // a release without the university view still has the province's numbers
        state.areaUniversities = { key: wanted, data: null, failed: error.status !== 404 };
      }
    }
    renderAreas();
  }
  // The map response the area list may use: this measure and release, and no list filter (the tab drops them).
  function areaMap() {
    const map = state.mapData;
    return map?.measure_id === state.measure && map?.revision === state.revision && !Object.keys(map.filters?.applied || {}).length ? map : null;
  }
  function areaMeasure(measureId) { return allMeasureDefinitions().find((item) => item.measure_id === measureId); }
  function renderAreas() {
    if (state.tab !== "areas") return;
    const hadFocus = views.areas.contains(document.activeElement);
    const view = clear(views.areas);
    renderBreadcrumbs(state.overview?.requested_scope || {});
    // a loading placeholder keeps the pending focus for the render that has content
    if (!(state.province ? renderAreaProvince(view) : renderAreaNational(view))) return;
    // a control the reader was on is redrawn: go back to it, else to the start of what replaced it
    const focus = state.areaFocus || (hadFocus ? (state.province ? "heading" : "measure") : "");
    state.areaFocus = "";
    const target = focus === "measure" ? $("f2AreaMeasure") : focus === "toggle" ? $("f2AreaToggle")
      : focus === "heading" ? view.querySelector(".f2-area-brief h3")
        : focus.startsWith("province:") ? view.querySelector(`[data-f2-area-province="${CSS.escape(focus.slice(9))}"]`) : null;
    target?.focus({ preventScroll: focus !== "heading" });
  }
  function areaLimits() {
    return el("p", { class: "f2-result-context", text: "ตัวเลขในแท็บนี้บอกว่าแหล่งข้อมูลที่เรารวบรวมพบหลักฐานผลงานที่ไหน ยังไม่ได้บอกว่าทุนลงไปที่จังหวัดใด ผลลัพธ์ใดเกิดจากทุน หรือผลงานยังใช้งานอยู่หรือไม่ ค่า 0 หมายถึงไม่พบในข้อมูลที่รวบรวม ไม่ได้แปลว่าจังหวัดนั้นไม่มี เพราะแต่ละแหล่งครอบคลุมพื้นที่ไม่เท่ากัน" });
  }
  function selectAreaProvince(code) {
    state.areaFocus = code ? "heading" : `province:${state.province}`;
    handleProvince(code, true);
  }
  function renderAreaNational(view) {
    const definition = areaMeasure(state.measure);
    const map = areaMap();
    if (!definition || !map) { status(view, "กำลังโหลดข้อมูลรายจังหวัด", "กำลังขอข้อมูลจากระบบ"); return false; }
    const picker = el("select", { id: "f2AreaMeasure" }, AREA_MEASURES.map((id) => areaMeasure(id)).filter(Boolean)
      .map((item) => el("option", { value: item.measure_id, text: measureDisplayLabel(item) })));
    picker.value = state.measure;
    picker.addEventListener("change", () => { state.areaFocus = "measure"; changeMeasure(picker.value); });
    view.append(el("div", { class: "f2-area-picker" }, el("label", { htmlFor: "f2AreaMeasure", text: "ตัวชี้วัดที่ใช้เทียบจังหวัด (แผนที่เปลี่ยนตาม)" }, picker)));
    const unit = map.unit || definition.unit || "";
    const coverage = map.coverage || {};
    const cells = (map.cells || []).map((cell) => ({ ...cell, value: cell.result?.availability === "available" ? Number(cell.result.value) : null }));
    const byName = (a, b) => text(a.province_name_th).localeCompare(text(b.province_name_th), "th");
    const found = cells.filter((cell) => cell.value > 0).sort((a, b) => b.value - a.value || byName(a, b));
    const zero = cells.filter((cell) => cell.value === 0).sort(byName);
    const unavailable = cells.filter((cell) => cell.value === null || Number.isNaN(cell.value)).sort(byName);
    const summary = [`พบใน ${formattedCount(found.length)} จาก ${formattedCount(cells.length)} จังหวัด`];
    if (Number(coverage.without_province) > 0) summary.push(`${formattedCount(coverage.without_province)} ${unit} ไม่ระบุจังหวัด (จากทั้งหมด ${formattedCount(coverage.national_total)})`);
    const origin = sourceLine(definition.source_ids);
    view.append(section(`${measureDisplayLabel(definition)} รายจังหวัด`, null, el("div", { class: "f2-area-summary" },
      el("strong", { text: summary.join(" · ") }),
      el("p", { text: `จังหวัดในที่นี้หมายถึง${AREA_PLACE_MEANINGS[state.measure] || "จังหวัดที่แหล่งข้อมูลระบุ"} ${coverage.province_sum_is_additive
        ? `ต้นทางรายงานยอดแยกรายจังหวัด และยอดรายจังหวัดรวมกันเท่ากับยอดประเทศ ${formattedCount(coverage.national_total)} ${unit}`.trim()
        : "รายการเดียวอาจอยู่ได้หลายจังหวัด ยอดรายจังหวัดจึงบวกกันเป็นยอดประเทศไม่ได้"}` }),
      origin ? el("p", { class: "f2-metric-source", text: origin }) : "")));
    view.append(areaLimits());
    const shown = state.areaShowAll ? found : found.slice(0, AREA_TOP);
    const max = found[0]?.value || 1;
    const row = (cell) => el("tr", {},
      el("th", { scope: "row" }, el("button", { type: "button", class: "f2-university-link", "data-f2-area-province": cell.province_code, text: cell.province_name_th || cell.province_code, onclick: () => selectAreaProvince(cell.province_code) })),
      el("td", {}, el("span", { class: "f2-bar-value" }, bar(cell.value, max), `${formattedCount(cell.value)} ${unit}`.trim())));
    const table = el("table", { class: "f2-source-region-table f2-area-table" },
      el("caption", { text: `จังหวัดที่พบ เรียงจากมากไปน้อย (ค่าเท่ากันเรียงตามชื่อ) · แสดง ${formattedCount(shown.length)} จาก ${formattedCount(found.length)} จังหวัด` }),
      el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "จังหวัด" }), el("th", { scope: "col", text: measureDisplayLabel(definition) }))),
      el("tbody", {}, shown.map(row)));
    const toggle = found.length > AREA_TOP ? el("button", { id: "f2AreaToggle", type: "button", class: "f2-retry", text: state.areaShowAll ? `แสดง ${AREA_TOP} จังหวัดแรก` : `ดูทั้ง ${formattedCount(found.length)} จังหวัดที่พบ`, onclick: () => {
      state.areaShowAll = !state.areaShowAll;
      state.areaFocus = "toggle";
      writeUrl(false);
      renderAreas();
    } }) : "";
    view.append(section("จังหวัดที่พบ", el("div", {}, el("div", { class: "f2-table-scroll", tabindex: "0", role: "region", "aria-label": "ตารางจังหวัดที่พบ" }, table), toggle)));
    const others = (title, rows, note) => rows.length ? view.append(section(`${title} (${formattedCount(rows.length)} จังหวัด)`,
      el("ul", { class: "f2-area-others" }, rows.map((cell) => el("li", {}, el("button", { type: "button", class: "f2-university-link", "data-f2-area-province": cell.province_code, text: cell.province_name_th || cell.province_code, onclick: () => selectAreaProvince(cell.province_code) })))), note)) : null;
    others("ไม่พบในข้อมูลที่รวบรวม", zero, "แหล่งข้อมูลที่รวบรวมไม่มีรายการที่ระบุจังหวัดเหล่านี้ ไม่ได้แปลว่าในจังหวัดนั้นไม่มีผลงาน");
    others("ไม่มีข้อมูลรายจังหวัด", unavailable, definition.status === "source_aggregate"
      ? "แหล่งข้อมูลไม่ได้รายงานจังหวัดเหล่านี้ ไม่ได้แปลว่ามีศูนย์" : "ตัวชี้วัดนี้ยังไม่มีตัวเลขที่รองรับสำหรับจังหวัดเหล่านี้");
    return true;
  }
  function renderAreaProvince(view) {
    const overview = state.overview;
    if (overview?.scope !== `province/${state.province}`) { status(view, "กำลังโหลดสรุปจังหวัด", "กำลังขอข้อมูลจากระบบ"); return false; }
    const name = overview.requested_scope?.province_name_th || provinceName(state.province);
    const complete = !state.areaUniversities?.failed;
    const brief = el("article", { class: "f2-area-brief", "data-f2-printable": complete ? "true" : null });
    view.append(el("div", { class: "f2-area-actions f2-no-print" },
      el("button", { type: "button", class: "f2-back-overview", text: "← ดูทุกจังหวัด", onclick: () => selectAreaProvince("") }),
      complete ? el("button", { type: "button", class: "f2-retry", text: "พิมพ์หรือบันทึกเป็น PDF", onclick: () => window.print() }) : ""), brief);
    brief.append(el("header", { class: "f2-university-head" },
      el("p", { class: "f2-detail-eyebrow", text: "สรุปจังหวัด · ข้อมูลฝ่าย 2" }), el("h3", { text: `จังหวัด${name}`, tabindex: "-1" })));
    brief.append(el("p", { class: "f2-result-context", text: `สิ่งที่แหล่งข้อมูลที่เรารวบรวมพบในจังหวัด${name}` }), areaLimits());
    const rows = AREA_MEASURES.map(areaMeasure).filter(Boolean).map((item) => {
      const result = item.result || {};
      const value = result.availability === "available" ? Number(result.value) : null;
      const unit = result.unit || item.unit || "";
      const figure = value > 0 ? el("strong", { text: `${valueText(result.display_value ?? result.value)} ${unit}`.trim() })
        : value === 0 ? el("strong", { class: "f2-area-none", text: "ไม่พบในข้อมูลที่รวบรวม" })
          : el("strong", { class: "f2-area-none", text: "ไม่มีข้อมูลรายจังหวัด" });
      const origin = sourceLine(item.source_ids);
      return el("tr", {},
        el("th", { scope: "row" }, measureDisplayLabel(item), el("small", { text: item.measure_id === "H01"
          ? "ตัวเลขเงินของครัวเรือนเป้าหมายมีเฉพาะระดับประเทศ ดูได้ที่หน้าภาพรวม" : AREA_PLACE_MEANINGS[item.measure_id] || "" })),
        el("td", { "data-label": "ในจังหวัดนี้" }, figure, origin ? el("small", { class: "f2-metric-source", text: origin }) : "",
          value > 0 && item.detail_availability === "available" ? el("button", { type: "button", class: "f2-inline-link f2-no-print", text: "ดูรายการในจังหวัดนี้", onclick: () => {
            changeMeasure(item.measure_id);
            setTab("list");
            loadMap();
          } }) : ""));
    });
    brief.append(section("พบอะไรในจังหวัดนี้", el("div", { class: "f2-table-scroll" }, el("table", { class: "f2-source-region-table f2-area-brief-table" },
      el("caption", { text: "ตัวชี้วัดแต่ละตัวนับคนละแบบและมาจากคนละแหล่ง จึงนำมาบวกกันหรือเทียบกันตรง ๆ ไม่ได้" }),
      el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "ตัวชี้วัด" }), el("th", { scope: "col", text: "ในจังหวัดนี้" }))),
      el("tbody", {}, rows)))));
    brief.append(areaInstitutions(name));
    const release = overview.provenance?.release_date ? `ฉบับข้อมูล ${overview.release_id} จัดเตรียม ${thaiDay(overview.provenance.release_date)}` : "";
    const fetched = fetchedRange(Object.keys(sourceSnapshots()));
    brief.append(el("footer", { class: "f2-area-footer" },
      el("p", { text: [release, fetched ? `ดึงข้อมูลจากเว็บต้นทาง ${fetched}` : ""].filter(Boolean).join(" · ") }),
      el("p", { class: "f2-print-only", text: `ดูฉบับออนไลน์: ${location.href}` })));
    return true;
  }
  function areaInstitutions(name) {
    const loaded = state.areaUniversities?.data;
    const title = "มหาวิทยาลัยและหน่วยงานที่มีนวัตกรรมเชื่อมกับจังหวัดนี้";
    if (state.areaUniversities?.failed) return section(title, el("button", { type: "button", class: "f2-retry", text: "ลองอีกครั้ง", onclick: loadAreas }), "เปิดรายชื่อหน่วยงานไม่ได้ จึงยังพิมพ์สรุปจังหวัดนี้ไม่ได้");
    if (!loaded) return section(title, null, "ข้อมูลฉบับนี้ยังไม่มีรายชื่อหน่วยงาน");
    const rows = loaded.universities || [];
    const place = loaded.province || {};
    const groups = loaded.groups || {};
    const note = el("div", {},
      el("p", { text: `นับจากนวัตกรรมที่แหล่งข้อมูลระบุจังหวัด${name}เป็นพื้นที่ใช้หรือพื้นที่ของผู้ใช้เป้าหมาย และระบุชื่อหน่วยงานไว้ในรายการ ไม่ได้ยืนยันว่านำไปใช้จริง และไม่ได้แปลว่าหน่วยงานนั้นลงพื้นที่เองหรือตั้งอยู่ในจังหวัดนี้ นวัตกรรมหนึ่งชิ้นอาจมีหลายหน่วยงาน จำนวนของแต่ละแห่งจึงบวกกันไม่ได้ ธุรกิจและนวัตกรชุมชนยังโยงกับจังหวัดผ่านหน่วยงานไม่ได้` }),
      el("p", { class: "f2-result-context", text: `ระบุหน่วยงานได้ ${formattedCount(place.innovations_with_university)} จาก ${formattedCount(place.innovations)} นวัตกรรมในจังหวัดนี้ · หน้ามหาวิทยาลัยแสดงผลงานทั้งประเทศ` }));
    if (!rows.length) return section(title, el("p", { text: "ไม่พบหน่วยงานที่มีนวัตกรรมเชื่อมกับจังหวัดนี้ในข้อมูลที่รวบรวม" }), note);
    const item = (row) => el("li", {},
      el("button", { type: "button", class: "f2-university-link", text: row.name_th, onclick: () => {
        state.university = row.university_id;
        state.universityOffset = 0;
        state.universityQuery = "";
        state.universityFocus = "heading";
        setTab("universities");
      } }),
      text(row.name_th).startsWith(groups[row.group]?.label_th) ? "" : el("span", { class: "f2-university-group-label", text: groups[row.group]?.label_th || "" }),
      el("span", { class: "f2-area-count", text: `${formattedCount(row.province_innovations)} นวัตกรรม` }));
    return section(title, el("div", {},
      el("ol", { class: "f2-area-institutions" }, rows.slice(0, AREA_TOP).map(item)),
      rows.length > AREA_TOP ? el("details", { class: "f2-detail-more" }, el("summary", { text: `และอีก ${formattedCount(rows.length - AREA_TOP)} แห่ง` }),
        el("ol", { class: "f2-area-institutions", start: AREA_TOP + 1 }, rows.slice(AREA_TOP).map(item))) : ""), note);
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
    if (item.text && state.measure === "K04" && kind === "prose" && item.text.length > 500) {
      card.append(el("p", { class: "f2-detail-prose", text: `${item.text.slice(0, 260).trimEnd()}…` }));
      card.append(el("details", { class: "f2-detail-more" },
        el("summary", { text: "อ่านรายละเอียดทั้งหมด" }),
        el("p", { class: "f2-detail-prose", text: item.text }),
      ));
    } else if (item.text) card.append(el("p", { class: "f2-detail-prose", text: item.text }));
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
    const titleNote = sourceTitleNote(state.measure, model.title);
    if (titleNote) intro.append(el("p", { class: "f2-detail-title-note", text: titleNote }));
    const directSource = (model.sources || []).find((source) => source.kind === "record" && externalUrl(source.url))
      || (model.sources || []).find((source) => externalUrl(source.url));
    if (directSource) intro.append(el("a", {
      class: "f2-detail-source-action",
      href: externalUrl(directSource.url),
      target: "_blank",
      rel: "noopener noreferrer",
      text: directSource.kind === "record" ? "เปิดรายการต้นทาง ↗" : "เปิดเว็บไซต์แหล่งข้อมูล ↗",
    }));
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
        const additional = group.kind === "prose" && group.items.length > 3
          ? el("details", { class: "f2-detail-more" }, el("summary", { text: `รายละเอียดเพิ่มเติมจากต้นทาง (${group.items.length - 3})` }))
          : null;
        group.items.forEach((item, index) => {
          const rendered = detailItem(item, group.kind || "cards");
          if (rendered) (additional && index >= 3 ? additional : items).append(rendered);
        });
        if (additional) items.append(additional);
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
    sheet.hidden = false;
    $("f2DetailTitle").textContent = "รายละเอียด";
    $("f2DetailBody").replaceChildren(el("div", { class: "f2-status", text: "กำลังโหลดรายละเอียด" }));
    sheet.querySelector("button[data-f2-detail-close]").focus();
    try {
      const data = await request(`/topics/${encodeURIComponent(state.topic)}/details/${encodeURIComponent(id)}` + query(detailScope()), "detail");
      if (!data) return;
      if (!window.F2DetailPresenter?.present) throw new Error("ไม่พบตัวจัดรูปแบบรายละเอียด");
      const model = window.F2DetailPresenter.present(data.measure_id || state.measure, data.detail || data, data.provenance || {}, { provinceName: provinceName(state.province) });
      $("f2DetailTitle").textContent = model.title || titleOf(data.detail || data);
      $("f2DetailBody").replaceChildren(renderDetailPresentation(model));
      sheet.querySelector("button").focus();
    }
    catch (error) {
      if (error.stale || error.name === "AbortError") return;
      const missing = [400, 404, 422].includes(error.status);
      $("f2DetailTitle").textContent = "เปิดรายละเอียดไม่ได้";
      $("f2DetailBody").replaceChildren(el("div", { class: "f2-status", role: "status" },
        el("strong", { text: missing ? "ไม่พบรายละเอียดนี้" : "เปิดรายละเอียดไม่ได้" }),
        el("p", { text: missing ? "รายการนี้อาจไม่อยู่ในตัวชี้วัดหรือพื้นที่ที่เลือก" : "ระบบยังเปิดรายละเอียดนี้ไม่ได้ โปรดลองอีกครั้ง" }),
        missing ? "" : el("button", { class: "f2-retry", type: "button", text: "ลองอีกครั้ง", onclick: () => openDetail(id, false) }),
      ));
    }
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
    state.rememberedProvince = nextProvince;
    state.scopeNotice = "";
    if (state.province) delete state.filters.source_region;
    if (changed) state.offset = state.innovationOffset = 0;
    if (notifyHost && !state.filterDraft) {
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
  function close() { state.open = false; ["overview", "map", "topic", "choices", "coverage", "detail", "universities", "university", "areaUniversities", "innovations"].forEach(abort); closeDetail(true); panel.hidden = true; panel.setAttribute("aria-hidden", "true"); document.body.classList.remove("f2-dashboard-open"); state.callbacks.onClose?.(); }
  function init(callbacks = {}) {
    state.callbacks = callbacks;
    let previousPanelWidth = 0;
    const explanationResizeObserver = new ResizeObserver(([entry]) => {
      const width = entry.contentRect.width;
      if (!width || width === previousPanelWidth) return;
      previousPanelWidth = width;
      views.overview.querySelectorAll(".f2-headlines").forEach((group) => layoutMetricExplanations(group));
    });
    explanationResizeObserver.observe(panel);
    const stage = panel.querySelector(".f2-stage");
    stage.addEventListener("scroll", () => {
      if (state.tab !== "overview") return;
      const sections = [...views.overview.querySelectorAll("[id^=f2-overview-group-]")];
      if (!sections.length) return;
      const atBottom = stage.scrollTop + stage.clientHeight >= stage.scrollHeight - 2;
      const current = atBottom ? sections.at(-1) : sections.filter((section) => section.getBoundingClientRect().top <= stage.getBoundingClientRect().top + 100).at(-1);
      state.overviewScroll = stage.scrollTop;
      state.overviewTopic = current?.id || "";
      $("f2TopicJump").value = state.overviewTopic;
    }, { passive: true });
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
      openFilters();
    });
    $("f2FiltersApply").addEventListener("click", () => finishFilters(true));
    $("f2FiltersCancel").addEventListener("click", () => finishFilters(false));
    $("f2FilterDialog").addEventListener("cancel", (event) => { event.preventDefault(); finishFilters(false); });
    $("f2Expand").addEventListener("click", () => {
      const expanded = panel.classList.toggle("f2-expanded");
      $("f2Expand").setAttribute("aria-pressed", String(expanded));
      $("f2Expand").textContent = expanded ? "กลับไปดูแผนที่" : "ขยายข้อมูล";
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
    // Printing the area tab prints only the province brief: a copy outside the fixed panel, removed afterwards.
    window.addEventListener("beforeprint", () => {
      $("f2PrintRoot")?.remove();
      const brief = state.open && state.tab === "areas" ? views.areas.querySelector(".f2-area-brief[data-f2-printable]") : null;
      if (!brief) return;
      document.body.append(el("div", { id: "f2PrintRoot", class: "f2-print-root" }, brief.cloneNode(true)));
      document.body.classList.add("f2-printing");
    });
    window.addEventListener("afterprint", () => {
      $("f2PrintRoot")?.remove();
      document.body.classList.remove("f2-printing");
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
