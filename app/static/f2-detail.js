(() => {
  "use strict";

  const SOURCE_NAMES = {
    f2_apptech_mru: "AppTech เครือข่าย มรภ. / 38RAT",
    f2_apptech_mtr: "AppTech เครือข่าย มทร. / RinMP",
    f2_cultural_market_civil: "แผนที่ตลาดวัฒนธรรม",
    f2_culturalmap_university: "แผนที่วัฒนธรรมไทย",
    f2_icommunity: "ชุมชนนวัตกรรม",
    f2_learning_area_based: "Dashboard LE – Area Based",
    f2_target_household: "ระบบฐานข้อมูลครัวเรือนมุ่งเป้า",
  };

  const LEGACY_IDENTITY_REVIEW = {
    accepted_cross_source_link: { outcome: "merged", merge_scope: "cross_source", counting: "merged", name_quality: "supported" },
    reviewed_cross_source: { outcome: "merged", merge_scope: "cross_source", counting: "merged", name_quality: "supported" },
    reviewed_identity: { outcome: "merged", counting: "merged", name_quality: "supported" },
    reviewed_extended_identity: { outcome: "merged", counting: "merged", name_quality: "supported" },
    supported_reviewed_merge: { outcome: "merged", merge_scope: "within_source", counting: "merged", name_quality: "supported" },
    supported_within_source_merge: { outcome: "merged", merge_scope: "within_source", counting: "merged", name_quality: "supported" },
    source_supported: { outcome: "source_record_only", counting: "separate", name_quality: "supported" },
    source_local_identity: { outcome: "source_record_only", counting: "separate", name_quality: "supported" },
    source_local_only: { outcome: "source_record_only", counting: "separate", name_quality: "supported" },
    source_listing_identity: { outcome: "source_record_only", counting: "separate", name_quality: "supported" },
    reviewed_provisional_identity: { outcome: "source_record_only", counting: "separate", name_quality: "supported" },
    provisional_source_local_operator: { outcome: "source_record_only", counting: "separate", name_quality: "supported" },
    provisional_source_unit: { outcome: "source_record_only", counting: "separate", name_quality: "supported" },
    provisional_reported_activity: { outcome: "reported_activity", counting: "separate", name_quality: "supported" },
    reported_occurrence_provisional: { outcome: "reported_activity", counting: "separate", name_quality: "supported" },
    provisional_parent_occurrence: { outcome: "reported_activity", counting: "separate", name_quality: "supported" },
    provisional_unresolved_candidates: { outcome: "unresolved", counting: "separate", name_quality: "supported" },
    reviewed_possible_duplicate: { outcome: "unresolved", counting: "separate", name_quality: "supported" },
    unresolved_possible_duplicate: { outcome: "unresolved", counting: "separate", name_quality: "supported" },
    provisional_malformed_name: { outcome: "malformed_name", counting: "separate", name_quality: "unavailable" },
    reviewed_product_family: { outcome: "grouped_family", counting: "grouped", name_quality: "supported" },
  };

  const ROLE_LABELS = {
    university: "มหาวิทยาลัย",
    institute: "สถาบัน",
    institution: "หน่วยงาน",
    rights_holder: "ผู้ถือสิทธิ์",
    inventor: "ผู้ประดิษฐ์",
    researcher: "นักวิจัย",
    source_reported_owner: "เจ้าของผลงานตามที่แหล่งข้อมูลรายงาน",
    affiliated_organization: "หน่วยงานที่สังกัด",
    research_organization: "หน่วยงานวิจัย",
    community_organization: "องค์กรชุมชน",
    source_reported_organization: "หน่วยงานตามที่แหล่งข้อมูลรายงาน",
    listing_account_owner: "เจ้าของรายการตามแหล่งข้อมูล",
  };
  const C02_ROLE_LABELS = {
    community_innovator: "นวัตกรชุมชน",
    inventor: "ผู้ประดิษฐ์",
  };
  const C02_MEASURES = new Set(["C02_COMMUNITY"]);
  const C02_QUALIFYING_ROLES = new Set(Object.keys(C02_ROLE_LABELS));
  const C02_MEASURE_LABELS = {
    C02_COMMUNITY: "ทะเบียนนวัตกรชุมชนและผู้ประดิษฐ์",
  };

  const CATEGORY_LABELS = {
    AA: "โบราณวัตถุ",
    AR: "สถาปัตยกรรม",
    AS: "โบราณสถาน",
    CS: "พื้นที่วัฒนธรรม",
    EL: "ภาษา",
    FL: "วรรณกรรมพื้นบ้าน",
    KP: "ความรู้และแนวปฏิบัติเกี่ยวกับธรรมชาติและจักรวาล",
    PA: "ศิลปะการแสดง",
    SM: "กีฬาภูมิปัญญาไทย",
    SP: "แนวปฏิบัติทางสังคม พิธีกรรม และงานเทศกาล",
    TC: "งานช่างฝีมือดั้งเดิม",
  };

  const LIST_TYPE_LABELS = {
    K01B: "พื้นที่วัฒนธรรม",
    K03: "กิจกรรม",
    K04: "นวัตกรรมพร้อมใช้",
    C04_LISTED: "นวัตกรรมในรายการ",
    K05: "ธุรกิจหรือผู้ประกอบการ",
    K07: "กลุ่มสินค้าและบริการ",
    C08_PARTICIPATING: "ธุรกิจที่เข้าร่วมโครงการ",
    K12: "รายการทุนวัฒนธรรม",
  };
  const IDENTITY_PRESENTATIONS = {
    source_record_only: { label: "ระบุตามข้อมูลต้นทาง", notice: "รายการนี้ระบุตามข้อมูลต้นทาง และยังไม่ได้เชื่อมโยงข้ามแหล่งข้อมูล", warning: false },
    kept_separate: { label: "ตรวจสอบแล้วว่าเป็นคนละรายการ", notice: "ตรวจสอบแล้วว่าเป็นคนละรายการ จึงนับแยก", warning: false },
    unresolved: { label: "อาจซ้ำกับรายการอื่น — ยังนับแยก", notice: "หลักฐานยังไม่พอสำหรับการรวม จึงยังนับแยก", warning: true },
    malformed_name: { label: "ไม่มีชื่อรายการจากแหล่งข้อมูล", notice: "แหล่งข้อมูลไม่มีชื่อที่นำมาแสดงได้", warning: true },
    grouped_family: { label: "จัดกลุ่มสินค้าและบริการแล้ว", notice: "", warning: false },
    reported_activity: { label: "กิจกรรมตามที่แหล่งข้อมูลรายงาน", notice: "", warning: false },
    unknown: { label: "ยังไม่มีสถานะการตรวจสอบ", notice: "", warning: false },
  };

  const asArray = (value) => Array.isArray(value) ? value : value == null ? [] : [value];
  const isObject = (value) => value && typeof value === "object" && !Array.isArray(value);
  const hasValue = (value) => value !== null && value !== undefined && value !== "";
  const unique = (values) => [...new Set(values.filter(hasValue))];
  const cleanText = (value) => hasValue(value) ? String(value).trim() : "";
  const safeUrl = (value) => typeof value === "string" && /^https?:\/\//i.test(value) ? value : "";
  const sourceName = (sourceId) => SOURCE_NAMES[sourceId] || sourceId || "แหล่งข้อมูล";
  const roleName = (role) => ROLE_LABELS[role] || "ผู้เกี่ยวข้อง";

  function identityReview(item) {
    const structured = item?.identity_review || item?.flags?.identity_review;
    if (isObject(structured) && structured.outcome) return structured;
    const legacy = LEGACY_IDENTITY_REVIEW[item?.identity_status] || { outcome: "unknown", counting: "separate", name_quality: "unknown" };
    if (legacy.outcome !== "merged" || legacy.merge_scope) return legacy;
    return {
      ...legacy,
      merge_scope: unique(asArray(item?.source_ids)).length > 1 ? "cross_source" : "within_source",
    };
  }

  function identityPresentation(item) {
    const review = identityReview(item);
    if (review.outcome === "merged") {
      return review.merge_scope === "cross_source"
        ? { label: "เชื่อมโยงข้ามแหล่งข้อมูลแล้ว", notice: "", warning: false }
        : { label: "รวมระเบียนซ้ำในแหล่งข้อมูลแล้ว", notice: "", warning: false };
    }
    return IDENTITY_PRESENTATIONS[review.outcome] || IDENTITY_PRESENTATIONS.unknown;
  }

  function dedupeRows(rows, key = (row) => JSON.stringify(row)) {
    const seen = new Set();
    return rows.filter((row) => {
      const value = key(row);
      if (!value || seen.has(value)) return false;
      seen.add(value);
      return true;
    });
  }

  function formatDate(value) {
    const text = cleanText(value);
    if (!/^\d{4}-\d{2}-\d{2}/.test(text)) return text;
    const date = new Date(`${text.slice(0, 10)}T00:00:00Z`);
    if (Number.isNaN(date.valueOf())) return text;
    return new Intl.DateTimeFormat("th-TH", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(date);
  }

  function formatLocation(location) {
    if (!isObject(location)) return "";
    const parts = [];
    if (location.subdistrict) parts.push(`ตำบล${location.subdistrict}`);
    if (location.district) parts.push(`อำเภอ${location.district}`);
    if (location.province) parts.push(`จังหวัด${location.province}`);
    if (!parts.length && location.label) parts.push(location.label);
    return unique(parts).join(" · ");
  }

  function publicLabel(value, fallback = "ไม่ระบุชื่อรายการ") {
    const label = cleanText(value);
    if (!label || label === "Name unavailable") return fallback === "ไม่ระบุชื่อรายการ" ? "ไม่พบชื่อจากแหล่งข้อมูล" : fallback;
    return label;
  }

  function descriptionTitle(kind, fallbackTitle) {
    const value = cleanText(kind).toLowerCase();
    if (value === "history") return "ประวัติและความเป็นมา";
    if (value === "description" || value === "detail") return fallbackTitle;
    if (value === "identity") return "ลักษณะสำคัญ";
    return fallbackTitle;
  }

  function locationRows(detail) {
    return dedupeRows(
      asArray(detail.locations)
        .map((row) => ({ title: formatLocation(row), facts: [] }))
        .filter((row) => row.title),
      (row) => row.title,
    );
  }

  function descriptionRows(descriptions, fallbackTitle = "รายละเอียด") {
    return dedupeRows(
      asArray(descriptions)
        .filter(isObject)
        .map((row) => ({ title: descriptionTitle(row.kind, fallbackTitle), text: cleanText(row.text) }))
        .filter((row) => row.text),
      (row) => `${row.title}\u0000${row.text}`,
    );
  }

  function listingLinks(listings) {
    return dedupeRows(
      asArray(listings).flatMap((row) => {
        if (!isObject(row)) return [];
        const url = safeUrl(row.source_url || row.public_url || row.url);
        if (!url) return [];
        return [{ label: cleanText(row.label) || `ดูข้อมูลจาก ${sourceName(row.source_id)}`, url }];
      }),
      (row) => row.url,
    );
  }

  function mediaLinks(media) {
    return dedupeRows(
      asArray(media).flatMap((row) => {
        if (!isObject(row)) return [];
        const url = safeUrl(row.url);
        if (!url) return [];
        const label = row.label_availability === "withheld"
          ? "สื่ออ้างอิง — ไม่แสดงชื่อระหว่างการตรวจสอบ"
          : cleanText(row.label) || "เปิดสื่ออ้างอิง";
        return [{ label, url }];
      }),
      (row) => row.url,
    );
  }

  function provenanceSources(provenance, sourceIds = []) {
    const admitted = new Set(asArray(sourceIds));
    return dedupeRows(
      asArray(provenance?.sources)
        .filter((row) => !admitted.size || admitted.has(row?.source_id))
        .map((row) => ({
          label: sourceName(row?.source_id),
          url: safeUrl(row?.public_url),
        })).filter((row) => row.url),
      (row) => row.url,
    );
  }

  function c02SourceName(sourceId) {
    return SOURCE_NAMES[sourceId] || "แหล่งข้อมูลที่อนุมัติ";
  }

  function c02ProvenanceSources(provenance, sourceIds) {
    const admitted = new Set(asArray(sourceIds).map(cleanText).filter(Boolean));
    return dedupeRows(
      asArray(provenance?.sources).filter((row) => admitted.has(cleanText(row?.source_id))).map((row) => ({
        label: c02SourceName(row.source_id),
        url: safeUrl(row.public_url),
      })).filter((row) => row.url),
      (row) => row.url,
    );
  }

  function categoryLabels(codes) {
    return unique(asArray(codes).map((code) => CATEGORY_LABELS[String(code).slice(0, 2)]).filter(Boolean));
  }

  function c02RoleRows(measureId, roles) {
    return dedupeRows(
      asArray(roles).filter(isObject).flatMap((row) => {
        const code = cleanText(row.role_code);
        if (!C02_QUALIFYING_ROLES.has(code) || !asArray(row.qualifies_for).includes(measureId)) return [];
        return [{ code, label: C02_ROLE_LABELS[code], sourceId: cleanText(row.source_id), organization: cleanText(row.organization) }];
      }),
      (row) => `${row.code}\u0000${row.sourceId}\u0000${row.organization}`,
    );
  }

  function c02ListPresentation(measureId, item) {
    const roles = unique(asArray(item?.role_codes).map((code) => C02_ROLE_LABELS[code]).filter(Boolean));
    const organizations = unique(asArray(item?.organization_labels).map(cleanText).filter(Boolean));
    const countUnavailable = item?.related_work_count_unavailable || item?.flags?.related_work_count_unavailable;
    const count = countUnavailable
      ? "จำนวนผลงานที่แสดงในฉบับเผยแพร่นี้ยังระบุไม่ได้"
      : Number.isInteger(item?.related_work_count) && item.related_work_count >= 0
        ? `ผลงานที่แสดงในฉบับเผยแพร่นี้ ${item.related_work_count} รายการ`
        : "";
    const withheld = item?.label_availability === "withheld";
    const identity = identityPresentation(item);
    return {
      title: withheld ? "ชื่ออยู่ระหว่างการตรวจสอบ" : cleanText(item?.label) || "ชื่ออยู่ระหว่างการตรวจสอบ",
      context: unique([...roles, ...organizations, count]),
      warning: withheld
        ? "ชื่อยังไม่แสดง เนื่องจากอยู่ระหว่างการตรวจสอบ"
        : identity.warning
          ? identity.label
          : "",
      action: "ดูรายละเอียด",
    };
  }

  function c02TargetDetail(value, sourceId, admittedSources) {
    if (!isObject(value) || !cleanText(value.topic_id) || !cleanText(value.measure_id) || !cleanText(value.entity_id)) return null;
    if (!admittedSources.has(cleanText(sourceId))) return null;
    return { topicId: cleanText(value.topic_id), measureId: cleanText(value.measure_id), entityId: cleanText(value.entity_id) };
  }

  function c02RelationshipRows(detail) {
    const admittedSources = new Set(asArray(detail.source_ids).map(cleanText).filter(Boolean));
    return dedupeRows(
      asArray(detail.relationships).filter(isObject).flatMap((row) => {
        const title = cleanText(row.label);
        if (!title) return [];
        const target = c02TargetDetail(row.target_detail, row.source_id, admittedSources);
        const card = {
          title,
          subtitle: C02_ROLE_LABELS[cleanText(row.role_code)] || "ผลงานหรือโครงการที่เกี่ยวข้อง",
          facts: row.source_id && admittedSources.has(cleanText(row.source_id)) ? [{ label: "แหล่งข้อมูล", value: c02SourceName(row.source_id) }] : [],
        };
        const workIdentity = cleanText(row.entity_id);
        if (workIdentity) Object.defineProperty(card, "workIdentity", { value: workIdentity, enumerable: false });
        if (target) Object.defineProperty(card, "targetDetail", { value: target, enumerable: false });
        return [card];
      }),
      (row) => row.workIdentity || `${row.title}\u0000${row.subtitle}`,
    );
  }

  function presentListItem(measureId, item) {
    if (C02_MEASURES.has(measureId)) return c02ListPresentation(measureId, item);
    const type = LIST_TYPE_LABELS[measureId] || "รายการ";
    const categories = categoryLabels(item?.category_codes);
    const provinces = unique(asArray(item?.province_names_th).map((name) => `จังหวัด${name}`));
    const locations = provinces.length > 2
      ? [...provinces.slice(0, 2), `และอีก ${provinces.length - 2} จังหวัด`]
      : provinces;
    const identity = identityPresentation(item);
    const warning = identity.warning ? identity.label : "";
    return {
      title: publicLabel(item?.label || item?.title || item?.name),
      context: unique([type, ...categories.slice(0, 1), ...locations]),
      warning,
      action: "ดูรายละเอียด",
    };
  }

  function baseNotices(detail) {
    const notices = [];
    const flags = detail.flags || {};
    const review = identityReview(detail);
    const identity = identityPresentation(detail);
    if (identity.notice) {
      notices.push({ tone: identity.warning ? "warning" : "info", text: identity.notice });
    }
    if (flags.missing_geography) notices.push({ tone: "warning", text: "แหล่งข้อมูลไม่ได้ระบุพื้นที่อย่างเพียงพอ จึงไม่ควรอนุมานสถานที่เพิ่มเติม" });
    if (flags.possible_duplicate && review.outcome !== "unresolved") {
      notices.push({ tone: "warning", text: "รายการนี้อาจเกี่ยวข้องหรือซ้ำกับรายการอื่น แต่หลักฐานยังไม่เพียงพอสำหรับการรวมรายการ" });
    }
    if (flags.label_availability === "withheld" || flags.label_withholding_reason) notices.push({ tone: "warning", text: "ชื่อรายการยังไม่แสดง เนื่องจากอยู่ระหว่างการตรวจสอบ" });
    return dedupeRows(notices, (row) => row.text);
  }

  function technical(detail) {
    return {
      entity_id: detail.entity_id,
      identity_status: detail.identity_status,
      category_codes: detail.category_codes,
      province_codes: detail.province_codes,
      source_ids: detail.source_ids,
      originating_systems: detail.originating_systems,
      flags: detail.flags,
    };
  }

  function section(title, kind, items, note = "") {
    const present = asArray(items).filter((item) => item && (typeof item !== "object" || Object.values(item).some(hasValue)));
    return present.length ? { title, kind, items: present, note } : null;
  }

  function culturalPresentation(measureId, detail, provenance) {
    const isArea = measureId === "K01B";
    const type = isArea ? "พื้นที่วัฒนธรรม" : "รายการทุนวัฒนธรรม";
    const locations = locationRows(detail);
    const categories = categoryLabels(detail.category_codes);
    const descriptions = descriptionRows(detail.descriptions, "เรื่องราว");
    const listingRows = asArray(detail.listings).filter(isObject).map((row) => ({
      title: cleanText(row.label) || sourceName(row.source_id),
      subtitle: sourceName(row.source_id),
      facts: Object.entries(row.source_dates || {}).map(([key, value]) => ({
        label: key === "recorded" ? "วันที่บันทึก" : key === "updated" ? "วันที่ปรับปรุง" : "วันที่นำเข้าระบบ",
        value: formatDate(value),
      })).filter((fact) => fact.value),
      links: listingLinks([row]),
    }));
    const relationshipRows = asArray(detail.relationships).filter(isObject).map((row) => ({
      title: cleanText(row.label),
      subtitle: sourceName(row.source_id),
    })).filter((row) => row.title);
    const allMedia = mediaLinks(detail.media);
    const notices = baseNotices(detail);
    if (!isArea && detail.label === "Title withheld pending review") {
      notices.unshift({ tone: "warning", text: "ชื่อรายการยังไม่แสดง เนื่องจากอยู่ระหว่างการตรวจสอบ" });
    }
    return {
      eyebrow: type,
      title: cleanText(detail.label) === "Title withheld pending review" ? "ชื่อรายการอยู่ระหว่างการตรวจสอบ" : cleanText(detail.label),
      badges: unique([type, ...categories, identityPresentation(detail).label]).slice(0, 4),
      facts: [locations[0]?.title ? { label: "สถานที่", value: locations[0].title } : null].filter(Boolean),
      sections: [
        section(isArea ? "เรื่องราวและความสำคัญ" : "เรื่องราวและประวัติ", "prose", descriptions),
        section("หมวดหมู่ทางวัฒนธรรม", "tags", categories.map((value) => ({ value }))),
        section("สถานที่ตามแหล่งข้อมูล", "cards", locations),
        section(isArea ? "ความเกี่ยวข้อง" : "บุคคลหรือรายการที่เกี่ยวข้อง", "cards", relationshipRows),
        section("รายการจากแหล่งข้อมูล", "cards", listingRows),
        section("สื่ออ้างอิง", "links", allMedia),
      ].filter(Boolean),
      notices: dedupeRows(notices, (row) => row.text),
      sources: dedupeRows([...listingLinks(detail.listings), ...provenanceSources(provenance, detail.source_ids)], (row) => row.url),
      technical: technical(detail),
    };
  }

  function activityPresentation(detail, provenance) {
    const children = detail.children || {};
    const dates = asArray(children.dates).filter(isObject);
    const locations = locationRows(detail);
    const dateCards = dates.map((row) => {
      const start = formatDate(row.start_date);
      const end = formatDate(row.end_date);
      return {
        title: start && end && start !== end ? `${start} – ${end}` : start || end || "แหล่งข้อมูลไม่ได้ระบุวันที่แน่นอน",
        subtitle: row.has_conflict ? "พบวันที่จากแหล่งข้อมูลที่ไม่ตรงกัน" : "วันที่ตามแหล่งข้อมูล",
      };
    });
    const descriptions = descriptionRows(detail.descriptions, "รายละเอียดกิจกรรม");
    const sectionRows = asArray(children.sections).filter(isObject).map((row) => ({
      title: "รายละเอียดเพิ่มเติม",
      text: cleanText(row.description?.text),
    })).filter((row) => row.text);
    const sessions = asArray(children.sessions).filter(isObject).map((row) => ({
      title: cleanText(row.label) || "ช่วงกิจกรรม",
      facts: [
        row.start_date ? { label: "เริ่ม", value: formatDate(row.start_date) } : null,
        row.end_date ? { label: "สิ้นสุด", value: formatDate(row.end_date) } : null,
      ].filter(Boolean),
    }));
    const publications = asArray(detail.listings).filter(isObject).map((row) => ({
      title: cleanText(row.label) || "ประกาศหรือสิ่งพิมพ์ต้นทาง",
      text: cleanText(row.description?.text),
      facts: row.published_at ? [{ label: "เผยแพร่", value: formatDate(row.published_at) }] : [],
      links: listingLinks([row]),
    }));
    return {
      eyebrow: "กิจกรรม",
      title: cleanText(detail.label),
      badges: unique(["กิจกรรม", identityPresentation(detail).label]),
      facts: [
        dateCards[0]?.title ? { label: "วันเวลา", value: dateCards[0].title } : null,
        locations[0]?.title ? { label: "สถานที่", value: locations[0].title } : null,
      ].filter(Boolean),
      sections: [
        section("เกี่ยวกับกิจกรรม", "prose", descriptions),
        section("วันเวลา", "cards", dateCards),
        section("สถานที่จัดหรือพื้นที่ดำเนินงาน", "cards", locations),
        section("กำหนดการและรายละเอียดเพิ่มเติม", "prose", [...sessions, ...sectionRows]),
        section("ประกาศหรือสิ่งพิมพ์ต้นทาง", "cards", publications),
        section("สื่ออ้างอิง", "links", mediaLinks(detail.media)),
      ].filter(Boolean),
      notices: dedupeRows([
        ...baseNotices(detail),
        { tone: "info", text: "รายการนี้ยืนยันว่ามีการรายงานกิจกรรมหรือเหตุการณ์ ไม่ได้ยืนยันว่าโครงการทั้งหมดเสร็จสมบูรณ์" },
        dates.some((row) => row.has_conflict) ? { tone: "warning", text: "แหล่งข้อมูลระบุวันที่ไม่ตรงกัน โปรดตรวจสอบข้อมูลต้นทางประกอบ" } : null,
      ].filter(Boolean), (row) => row.text),
      sources: dedupeRows([...listingLinks(detail.listings), ...provenanceSources(provenance, detail.source_ids)], (row) => row.url),
      technical: technical(detail),
    };
  }

  function innovationDescriptionTitle(kind) {
    const value = cleanText(kind).toLowerCase();
    if (/pain|ปัญหา/.test(value)) return "ปัญหาที่ต้องการแก้";
    if (/gain|ประโยชน์/.test(value)) return "ประโยชน์";
    if (/จุดเด่น|highlight/.test(value)) return "จุดเด่น";
    if (/ความรู้|เทคโนโลยี|functional|apptechdescription|service/.test(value)) return "เทคโนโลยีและองค์ความรู้";
    if (/เงื่อนไข/.test(value)) return "เงื่อนไขการใช้งาน";
    if (/ที่มา|จุดมุ่งหมาย|ความต้องการ/.test(value)) return "ที่มาและความต้องการ";
    return "รายละเอียดนวัตกรรม";
  }

  function innovationPresentation(measureId, detail, provenance) {
    const children = detail.children || {};
    const locations = locationRows(detail);
    const descriptions = dedupeRows(
      asArray(detail.descriptions).filter(isObject).map((row) => ({
        title: innovationDescriptionTitle(row.kind),
        text: cleanText(row.text),
      })).filter((row) => row.text),
      (row) => `${row.title}\u0000${row.text}`,
    );
    const readiness = asArray(children.readiness).filter(isObject).map((row) => {
      const scale = cleanText(row.scale);
      const level = row.numeric_level
        ? scale.toUpperCase() === "TRL"
          ? `ระดับความพร้อมเทคโนโลยี (TRL) ${row.numeric_level}`
          : `${scale || "ระดับ"} ${row.numeric_level}`
        : cleanText(row.label) || scale;
      return {
        title: level || "ระดับความพร้อมตามแหล่งข้อมูล",
        subtitle: row.qualifies ? "ผ่านเกณฑ์ของตัวชี้วัด" : "ไม่อยู่ในเกณฑ์ของตัวชี้วัดนี้",
        facts: [{ label: "แหล่งข้อมูล", value: sourceName(row.source_id) }],
      };
    });
    const organizations = asArray(children.organizations).filter(isObject).map((row) => ({
      title: cleanText(row.organization),
      subtitle: roleName(row.role),
    })).filter((row) => row.title);
    const people = asArray(children.work_attributions).filter(isObject).map((row) => ({
      title: cleanText(row.attribution),
      subtitle: roleName(row.role),
    })).filter((row) => row.title);
    const readinessBadges = unique(asArray(children.readiness).map((row) => row?.numeric_level
      ? cleanText(row.scale).toUpperCase() === "TRL"
        ? `ความพร้อมเทคโนโลยีระดับ ${row.numeric_level}`
        : `${row.scale || "ระดับ"} ${row.numeric_level}`
      : row?.label)).slice(0, 2);
    const listings = asArray(detail.listings).filter(isObject).map((row) => ({
      title: cleanText(row.label) || sourceName(row.source_id),
      subtitle: sourceName(row.source_id),
      links: listingLinks([row]),
      note: row.record_link_availability === "withheld" ? "แหล่งข้อมูลไม่เผยแพร่ลิงก์ระดับรายการ" : "",
    }));
    return {
      eyebrow: measureId === "K04" ? "นวัตกรรมพร้อมใช้" : "นวัตกรรมในรายการทั้งหมด",
      title: cleanText(detail.label),
      badges: unique([measureId === "K04" ? "นวัตกรรมพร้อมใช้" : "นวัตกรรม", ...readinessBadges, identityPresentation(detail).label]).slice(0, 5),
      facts: [locations[0]?.title ? { label: "พื้นที่ใช้งาน", value: locations[0].title } : null].filter(Boolean),
      sections: [
        section("รายละเอียดและประโยชน์", "prose", descriptions),
        section("ระดับความพร้อมตามแหล่งข้อมูล", "cards", readiness),
        section("ผู้พัฒนาและผู้เกี่ยวข้อง", "cards", people),
        section("หน่วยงาน", "cards", organizations),
        section("พื้นที่นำไปใช้", "cards", locations),
        section("รายการจากแหล่งข้อมูล", "cards", listings),
      ].filter(Boolean),
      notices: dedupeRows([
        ...baseNotices(detail),
        { tone: "info", text: "ระดับความพร้อมเป็นข้อมูลที่แหล่งต้นทางรายงาน ไม่ใช่การประเมินสถานะปัจจุบันโดยแดชบอร์ด" },
        detail.flags?.readiness_conflict ? { tone: "warning", text: "แหล่งข้อมูลระบุระดับความพร้อมต่างกัน จึงแสดงแต่ละหลักฐานแยกกัน" } : null,
      ].filter(Boolean), (row) => row.text),
      sources: dedupeRows([...listingLinks(detail.listings), ...provenanceSources(provenance, detail.source_ids)], (row) => row.url),
      technical: technical(detail),
    };
  }

  function operatorPresentation(detail, provenance) {
    const locations = locationRows(detail);
    const descriptions = descriptionRows(detail.descriptions, "ข้อมูลธุรกิจตามแหล่งต้นทาง");
    const offerings = asArray(detail.relationships).filter(isObject).map((row) => ({
      title: cleanText(row.label),
      subtitle: "สินค้า บริการ หรือผลงานที่เกี่ยวข้อง",
    })).filter((row) => row.title);
    const memberships = asArray(detail.children?.source_memberships).filter(isObject).map((row) => ({
      title: sourceName(row.source_id),
      subtitle: cleanText(row.label),
    }));
    const notices = baseNotices(detail);
    if (detail.flags?.person_relationships_withheld) notices.push({ tone: "info", text: "ไม่แสดงความเชื่อมโยงระดับบุคคล เพื่อคงขอบเขตข้อมูลสาธารณะที่ได้รับอนุมัติ" });
    if (detail.flags?.geography_not_borrowed_from_offerings && !locations.length) notices.push({ tone: "info", text: "ไม่มีที่ตั้งของผู้ประกอบการที่ยืนยันได้ ระบบจึงไม่นำที่ตั้งของสินค้ามาใช้แทน" });
    return {
      eyebrow: "ธุรกิจ ร้านค้า หรือกลุ่มผู้ดำเนินการ",
      title: publicLabel(detail.label, "ไม่พบชื่อธุรกิจจากแหล่งข้อมูล"),
      badges: unique(["ผู้ประกอบการ", identityPresentation(detail).label]),
      facts: [locations[0]?.title ? { label: "ที่ตั้ง", value: locations[0].title } : null].filter(Boolean),
      sections: [
        section("เกี่ยวกับธุรกิจหรือกลุ่ม", "prose", descriptions),
        section("ที่ตั้งผู้ประกอบการ", "cards", locations),
        section("สินค้าและบริการที่เกี่ยวข้อง", "cards", offerings),
        section("พบในแหล่งข้อมูล", "cards", memberships),
      ].filter(Boolean),
      notices: dedupeRows(notices, (row) => row.text),
      sources: provenanceSources(provenance, detail.source_ids),
      technical: technical(detail),
    };
  }

  function priceText(price) {
    const amounts = asArray(price?.amounts).filter(isObject);
    if (!amounts.length) return "ไม่ระบุราคา";
    const values = amounts.map((amount) => {
      if (amount.status === "unspecified" || String(amount.value) === "0" && amount.display_label) {
        return "ไม่ระบุราคา — แหล่งข้อมูลรายงานค่า 0";
      }
      const numeric = Number(amount.value);
      if (Number.isFinite(numeric)) return `${numeric.toLocaleString("th-TH")} ${price.currency === "THB" ? "บาท" : price.currency || ""}`.trim();
      return cleanText(amount.display_label || amount.value);
    });
    return unique(values).join(" – ");
  }

  function offeringPresentation(detail, provenance) {
    const offerings = asArray(detail.children?.offerings).filter(isObject);
    const cards = offerings.map((offering) => {
      const prices = asArray(offering.children?.prices).filter(isObject).map(priceText);
      const location = asArray(offering.locations).map(formatLocation).find(Boolean);
      const sellers = asArray(offering.relationships).filter(isObject).map((row) => cleanText(row.label)).filter(Boolean);
      const categories = unique(asArray(offering.listings).map((row) => row?.category).filter(Boolean));
      return {
        title: cleanText(offering.label),
        subtitle: offering.membership_role === "variant" ? "รูปแบบหรือรุ่นย่อย" : "รายการสินค้าและบริการ",
        text: descriptionRows(offering.descriptions)[0]?.text || "",
        facts: [
          prices.length ? { label: "ราคาที่แหล่งข้อมูลรายงาน", value: unique(prices).join(" · ") } : null,
          categories.length ? { label: "หมวดหมู่", value: categories.join(", ") } : null,
          sellers.length ? { label: "ผู้ขายหรือผู้ดำเนินการ", value: unique(sellers).join(", ") } : null,
          location ? { label: "สถานที่ของรายการ", value: location } : null,
        ].filter(Boolean),
        links: dedupeRows([...listingLinks(offering.listings), ...mediaLinks(offering.media)], (row) => row.url),
      };
    });
    const innovations = dedupeRows(offerings.flatMap((offering) => asArray(offering.children?.innovation_context)).filter(isObject).map((row) => ({
      title: cleanText(row.label),
      subtitle: "นวัตกรรมที่เชื่อมโยงกับสินค้า",
    })).filter((row) => row.title), (row) => row.title);
    const notices = baseNotices(detail);
    notices.push({ tone: "info", text: "จำนวนตัวชี้วัดนับกลุ่มสินค้าและบริการ ส่วนรายการย่อยด้านล่างเป็นรูปแบบหรือรุ่นภายในกลุ่ม ไม่ใช่หน่วยนับเพิ่มเติม" });
    if (cards.some((card) => card.facts?.some((fact) => fact.value.includes("รายงานค่า 0")))) {
      notices.push({ tone: "warning", text: "ค่า 0 จากแหล่งข้อมูลหมายถึงไม่ได้ระบุราคา ไม่ได้หมายความว่าสินค้าหรือบริการไม่มีค่าใช้จ่าย" });
    }
    return {
      eyebrow: "กลุ่มสินค้า บริการ และผลงาน",
      title: cleanText(detail.label),
      badges: unique(["กลุ่มผลิตภัณฑ์", identityPresentation(detail).label]),
      facts: [],
      sections: [
        section("รายการและรูปแบบที่พบ", "cards", cards),
        section("นวัตกรรมที่เกี่ยวข้อง", "cards", innovations),
      ].filter(Boolean),
      notices: dedupeRows(notices, (row) => row.text),
      sources: provenanceSources(provenance, detail.source_ids),
      technical: technical(detail),
    };
  }

  function participationPresentation(detail, provenance) {
    const locations = locationRows(detail);
    const participations = asArray(detail.children?.participations).filter(isObject).map((row) => ({
      title: cleanText(row.project) || "โครงการที่เข้าร่วม",
      subtitle: row.fiscal_year_be ? `ปีงบประมาณ ${row.fiscal_year_be}` : "",
      facts: [
        row.research_unit ? { label: "หน่วยงานวิจัย", value: row.research_unit } : null,
        row.source_id ? { label: "แหล่งข้อมูล", value: sourceName(row.source_id) } : null,
      ].filter(Boolean),
    }));
    const notices = baseNotices(detail);
    notices.push({ tone: "warning", text: "ข้อมูลนี้ยืนยันการเข้าร่วมโครงการ แต่ไม่ได้ยืนยันว่าธุรกิจมีผลประกอบการหรือขีดความสามารถดีขึ้น" });
    if (detail.flags?.person_assessments_withheld) notices.push({ tone: "info", text: "ไม่แสดงผลประเมินระดับบุคคลในหน้าสาธารณะ" });
    return {
      eyebrow: "ธุรกิจหรือหน่วยธุรกิจที่เข้าร่วมโครงการ",
      title: publicLabel(detail.label, "ไม่พบชื่อธุรกิจจากแหล่งข้อมูล"),
      badges: unique(["เข้าร่วมโครงการ", identityPresentation(detail).label]),
      facts: [locations[0]?.title ? { label: "ที่ตั้ง", value: locations[0].title } : null].filter(Boolean),
      sections: [
        section("โครงการที่เข้าร่วม", "timeline", participations),
        section("ที่ตั้งหน่วยธุรกิจ", "cards", locations),
      ].filter(Boolean),
      notices: dedupeRows(notices, (row) => row.text),
      sources: provenanceSources(provenance, detail.source_ids),
      technical: technical(detail),
    };
  }

  function c02PersonPresentation(measureId, detail, provenance) {
    const roles = c02RoleRows(measureId, detail.children?.qualifying_roles);
    const organizations = dedupeRows(
      asArray(detail.children?.organizations).filter(isObject).map((row) => ({
        title: cleanText(row.organization),
        subtitle: cleanText(row.role_label_th) || roleName(row.role),
      })).filter((row) => row.title),
      (row) => `${row.title}\u0000${row.subtitle}`,
    );
    const works = c02RelationshipRows(detail);
    const locations = locationRows(detail);
    const notices = baseNotices(detail);
    if (detail.flags?.k02_relationship === "not_established") {
      notices.push({ tone: "info", text: "รายการบุคคลนี้ไม่ได้นำมาใช้ปรับยอดรวม K02 และไม่ควรนำไปเทียบหรือบวกกับ K02" });
    }
    if (locations.length) {
      notices.push({ tone: "info", text: "จังหวัดนี้เป็นข้อมูลที่ต้นทางผูกกับระเบียนนวัตกร ไม่ได้หมายถึงจังหวัดที่อยู่อาศัยหรือสถานที่ทำงานปัจจุบัน" });
      const admittedProvinceCount = unique(asArray(detail.province_codes).map(cleanText).filter(Boolean)).length || unique(asArray(detail.locations).map((location) => cleanText(location?.province_code || location?.province)).filter(Boolean)).length;
      if (admittedProvinceCount > 1) {
        notices.push({ tone: "info", text: "บุคคลนี้มีจังหวัดที่ต้นทางระบุมากกว่าหนึ่งจังหวัด การนับรายจังหวัดจึงไม่เป็นผลรวมแบบบวกกัน" });
      }
    } else if (Object.prototype.hasOwnProperty.call(detail.flags || {}, "person_province_basis")) {
      notices.push({ tone: "info", text: "ไม่มีจังหวัดที่ต้นทางระบุสำหรับระเบียนนวัตกรนี้ บุคคลยังคงอยู่ในยอดระดับประเทศ และระบบไม่อนุมานจังหวัดจากหน่วยงาน ผลงาน หรือสถานที่ทำงาน" });
    } else if (detail.flags?.geography_not_published !== false) {
      notices.push({ tone: "info", text: "ทะเบียนนี้เผยแพร่ในระดับประเทศ และไม่เผยแพร่หรืออนุมานภูมิศาสตร์ของบุคคลจากหน่วยงาน ผลงาน หรือรายการที่เกี่ยวข้อง" });
    }
    if (detail.flags?.related_work_count_unavailable) {
      notices.push({ tone: "info", text: "จำนวนผลงานที่แสดงในฉบับเผยแพร่นี้ยังระบุไม่ได้ เพราะไม่สามารถยืนยันตัวตนผลงานที่ซ้ำกันได้" });
    }
    if (asArray(detail.flags?.missing_public_detail_fields).length) {
      notices.push({ tone: "info", text: "บางรายละเอียดไม่แสดง เพราะยังไม่ได้รับอนุมัติให้เผยแพร่ในบริบทสาธารณะ" });
    }
    const withheld = detail.label_availability === "withheld";
    if (withheld) {
      notices.push({ tone: "warning", text: "ชื่อยังไม่แสดง เนื่องจากอยู่ระหว่างการตรวจสอบ" });
    }
    return {
      eyebrow: C02_MEASURE_LABELS[measureId],
      title: withheld ? "ชื่ออยู่ระหว่างการตรวจสอบ" : cleanText(detail.label) || "ชื่ออยู่ระหว่างการตรวจสอบ",
      badges: unique([C02_MEASURE_LABELS[measureId], ...roles.map((row) => row.label), identityPresentation(detail).label]).slice(0, 5),
      facts: [],
      sections: [
        section("บทบาทที่ยืนยันคุณสมบัติ", "cards", roles.map((row) => ({
          title: row.label,
          subtitle: "บทบาทตามหลักฐานจากแหล่งข้อมูล",
          facts: row.organization ? [{ label: "หน่วยงานที่ระบุร่วมกับบทบาท", value: row.organization }] : [],
        }))),
        section("จังหวัดที่ต้นทางระบุสำหรับนวัตกร", "cards", locations, locations.length ? "จังหวัดจากระเบียนนวัตกรของต้นทางเท่านั้น ไม่ใช่ที่อยู่อาศัยหรือสถานที่ทำงานปัจจุบัน" : ""),
        section("หน่วยงานที่ระบุ", "cards", organizations),
        section("ผลงานหรือโครงการที่เกี่ยวข้อง", "cards", works, "แสดงเฉพาะผลงานที่มีบริบทเผยแพร่ที่อนุมัติแล้ว ไม่ใช่ผลงานทั้งหมดตลอดชีวิต"),
      ].filter(Boolean),
      notices: dedupeRows(notices, (row) => row.text),
      sources: c02ProvenanceSources(provenance, detail.source_ids),
      technical: technical(detail),
    };
  }

  function fallbackPresentation(detail, provenance) {
    return {
      eyebrow: "รายละเอียด",
      title: cleanText(detail.label || detail.title || detail.name) || "รายการ",
      badges: unique([identityPresentation(detail).label]),
      facts: [],
      sections: [],
      notices: baseNotices(detail),
      sources: provenanceSources(provenance, detail.source_ids),
      technical: detail,
    };
  }

  function present(measureId, detail, provenance = {}) {
    if (!isObject(detail)) return fallbackPresentation({}, provenance);
    if (["K01B", "K12"].includes(measureId)) return culturalPresentation(measureId, detail, provenance);
    if (measureId === "K03") return activityPresentation(detail, provenance);
    if (C02_MEASURES.has(measureId)) return c02PersonPresentation(measureId, detail, provenance);
    if (["K04", "C04_LISTED"].includes(measureId)) return innovationPresentation(measureId, detail, provenance);
    if (measureId === "K05") return operatorPresentation(detail, provenance);
    if (measureId === "K07") return offeringPresentation(detail, provenance);
    if (measureId === "C08_PARTICIPATING") return participationPresentation(detail, provenance);
    return fallbackPresentation(detail, provenance);
  }

  const api = { present, presentListItem, formatDate, formatLocation, priceText, sourceName };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window !== "undefined") window.F2DetailPresenter = api;
})();
