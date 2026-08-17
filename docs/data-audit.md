# Data coverage and quality audit

อัปเดต: 2026-08-16

เอกสารนี้รวมผลตรวจ coverage 28 แหล่ง, geography linkage, การจัดกลุ่มข้อมูลรายมิติ และข้อจำกัดของ serving projection ปัจจุบัน

## Executive result

| Control | ผลตรวจ |
|---|---:|
| Source metadata ใน database | 28 |
| Public candidate | 11 |
| Metadata-only | 12 |
| Restricted local-only | 5 |
| Verified catalog endpoints | 141 |
| Runtime-enabled endpoints | 90 |
| Province briefings | 77 |
| Executive summaries | 77 |
| Public serving artifacts | 162 |
| Accepted public sources | 0 |
| Candidate/needs-review public sources | 11 |
| Restricted values บน Cloud | 0 |
| Operational candidate rows | 0 จนกว่าจะรัน API refresh |
| Live connector audit | 6/6 สำเร็จ; 9,652 candidate records |

Production ใช้ PostgreSQL เป็น serving database และตรวจความครบได้ที่ `/api/public/v1/database-coverage`

## Audit ตามคำถามผู้บริหารจากภาพความต้องการ

สถานะใช้ 3 ระดับ: **ตอบได้** = มี field/หลักฐานตรงคำถาม, **ตอบได้บางส่วน** = มีข้อมูลใกล้เคียงแต่ grain/definition ยังไม่ครบ, **ยังตอบไม่ได้** = ห้ามสร้างคำตอบจากการอนุมาน

| คำถาม/ความต้องการ | สถานะปัจจุบัน | สิ่งที่ Dashboard แสดงแล้ว | ข้อมูลที่ต้องเพิ่มเพื่อให้ตอบได้จริง |
|---|---|---|---|
| Dashboard ต้องมีชีวิตและเห็นรายโครงการทันที | ยังตอบไม่ได้ | มี public projection แบบ revision และ 6 connector ที่เรียกซ้ำได้ | Production scheduler, persistent raw storage, alert, source watermark และ approval workflow; ห้าม auto-publish ก่อน review |
| กลุ่มเป้าหมายเป็นใคร อยู่ที่ไหน ได้ประโยชน์อย่างไร | ตอบได้บางส่วน | Area-Based แสดงกลุ่ม/ธุรกิจ อำเภอ ตำบล; innovation มี `target_groups` และพื้นที่ | Target-group taxonomy, beneficiary ID แบบไม่ระบุตัวบุคคล, intervention, benefit type, baseline/target/result และวันที่วัด |
| ออกแบบจากเป้าหมายใช้งาน เช่น wellness/ผู้สูงอายุ/โรค/เหตุฉุกเฉิน | ตอบได้บางส่วน | แยกมิติ development, housing, risk, livelihood, urban, culture | ชุดข้อมูลสุขภาพและ household อยู่ restricted; ต้องมี owner/privacy gate และ aggregate contract ที่ปลอดภัยก่อนเชื่อม |
| ฐานข้อมูลหลายฝ่ายเชื่อมเป็นภาพรวมเดียว | ตอบได้บางส่วน | Registry 28 แหล่ง, serving database, source provenance และ 11 public projections | Canonical Project ID, organization ID, program/framework code, geography crosswalk และ shared `as_of` contract |
| ข้อมูลถูกต้อง แม่นยำ ไม่ซ้ำ/ไม่ตกหล่น | ตอบได้บางส่วน | มี hash, unique key, manifest, privacy scan, unmapped lane และ regression tests | Source owner sign-off, reconciliation กับยอดควบคุม, completeness threshold และ accepted status; ปัจจุบัน accepted = 0 |
| จำนวนโครงการที่ไหน ระดับจังหวัด/อำเภอ/ตำบล | ตอบได้บางส่วน | 73 provisional project groups, 156 project–province links; participant rows 996 ใน 55 จังหวัด | Project ID ทางการและ project–area bridge; ปัจจุบัน grouping จากชื่อ+ปีงบ+หน่วยวิจัย |
| หัวหน้าโครงการ ทุน กรอบ และชื่อโครงการ | ตอบได้บางส่วน | AppTech มี research lead/funding บางผลงาน; Area-Based มีชื่อโครงการ ปี และหน่วยวิจัย | Project master จากระบบวิจัยหลักที่มี PI, fund, program/framework, contract และ organization IDs |
| ผลผลิต ผลลัพธ์ ผลกระทบ เชิงปริมาณ/คุณภาพ | ตอบได้บางส่วน | มี innovation, TRL/SRL, IP, target group และ ROI/SROI บาง field | Outcome registry ที่มี indicator definition, unit, denominator, baseline, target, actual, measurement date และ evidence URL |
| สถานะดำเนินงาน อยู่ระหว่าง/เสร็จสิ้น | ยังตอบไม่ได้ | แสดง `not_reported_by_source` ตรงไปตรงมา | Milestone/status history พร้อมวันที่, owner และนิยามสถานะกลาง |
| ประเด็นนี้เคยให้ทุนหรือยัง งานวิจัยถูกใช้โดย บพท. หรือไม่ | ยังตอบไม่ได้ | ยังไม่มี cross-project topic/adoption relation ที่ยืนยันได้ | Controlled topic taxonomy, prior-award linkage, adoption/use case, adopting unit, date และหลักฐานการนำใช้ |
| งบภาพรวมรายหน่วย/ฝ่าย/กรอบ/โครงการ/พื้นที่ | ยังตอบไม่ได้ | แสดงเฉพาะทุนที่ต้นทางผูกกับ innovation และเตือนว่าไม่ใช่งบจังหวัด | Official budget ledger ที่มี allocation grain, fiscal year, fund/program/project/unit/area keys |
| สถานะเบิกจ่าย | ยังตอบไม่ได้ | ไม่สร้างค่าทดแทน | Disbursement transactions หรือ approved aggregate: committed, disbursed, balance, percent, cutoff date และ reconciliation total |

ลำดับ data acquisition ที่มีผลต่อคำถามมากที่สุดคือ: **(1) Project master + Project ID, (2) official budget/disbursement ledger, (3) milestone/outcome registry, (4) target-group/benefit schema, (5) adoption/prior-funding linkage** หากยังไม่มี 5 ชุดนี้ การเพิ่มกราฟหรือจำนวน source จะไม่ทำให้ Dashboard ตอบคำถามเชิงนโยบายดีขึ้น

## Audit ความจำเป็นของแต่ละแท็บ

| แท็บ | ควรมีหรือไม่ | บทบาทที่ถูกต้อง | สิ่งที่ปรับใน release นี้ |
|---|---|---|---|
| ภาพรวม | ต้องมี | เห็นขนาดงาน พื้นที่ และความพร้อมของผลงานในจังหวัดโดยไม่ปนข้อมูลต้นทาง | ใช้ 3 ตัวเลขหลัก + flow ของค่าจริง + กราฟ TRL/ทะเบียนผลงาน + รายชื่ออำเภอ; ย้าย source coverage ไปอยู่ชั้นคุณภาพข้อมูล |
| โครงการและงบ | ต้องมี | ตอบ project/funding/output โดยรักษา grain | รวม summary, project records, innovation, requirements, funding caveat และ data gaps |
| คนและพื้นที่ | ต้องมี | แสดงผู้เข้าร่วม/กลุ่มเป้าหมายและพื้นที่จริง ไม่ใช่ยอดรวมอย่างเดียว | ค้นหารายการได้และแสดง district/tambon; restricted records ไม่เผยแพร่ |
| มิติการพัฒนา | ต้องมี | จัดข้อมูลตาม use case และ evidence stage | แยก metric ต่างหน่วย มีตัวเลขกำกับ และบอก missing dimensions |
| คุณภาพข้อมูล/ต้นทาง | ต้องมี แต่เป็น supporting layer | ให้ผู้ใช้ตรวจ grain, วันที่, caveat และ URL โดยไม่แย่งพื้นที่จากคำตอบหลัก | อยู่ท้ายลำดับในหน้าเต็มและใช้ collapsed details |

หน้า preview มีไว้เลือกและอ่านเร็ว ส่วน `/province/{code}` เป็นข้อมูลจังหวัดฉบับเต็ม 6 section เพื่อไม่อัดทุกอย่างลง side panel 700px

## Live API connectivity audit — 16 สิงหาคม 2569

ทดสอบแบบ read-only เฉพาะ executable allowlist; ไม่เรียก restricted, person/household, auth หรือ write route และไม่ promote ค่าเข้า public artifacts

| Connector | ผล | Records seen | หมายเหตุ |
|---|---|---:|---|
| `f1_sradss_ppaos` | สำเร็จ | 169 | aggregate route เท่านั้น |
| `f2_apptech_mtr` | สำเร็จ | 630 | มากกว่า public baseline 621 จำนวน 9 ระเบียน; ต้อง review diff |
| `f2_apptech_mru` | สำเร็จ | 503 | 501 innovation + 2 requirements; แก้ request contract เป็น nested JSON |
| `f2_learning_dashboard` | สำเร็จ | 89 | หลาย grain; unit และ source-wide `as_of` ยังไม่ระบุ |
| `f2_learning_area_based` | สำเร็จ | 1,002 | participant/business grain ไม่ใช่ project count |
| `f3_housing_portal` | สำเร็จ | 7,259 | เฉพาะ dataset ที่ policy อนุญาต values |
| **รวม** | **6/6** | **9,652** | candidate only; public promotion = none |

ทุก HTTP error ถูกเก็บ response + failed manifest ก่อน raise แล้ว และการทดสอบ `--strategy api` จะไม่ซ่อนความล้มเหลวด้วย snapshot fallback ส่วน `auto` ใช้ fallback ได้เฉพาะ source ที่ policy อนุญาต

## Source coverage findings

| Source | สิ่งที่พบ | วิธีนำเสนอ |
|---|---|---|
| SRA-DSS | Registry มี 20 จังหวัด แต่ overall ปี 2569 มีตัวเลข 15 จังหวัด | แสดง target scope ครบ 20 จังหวัด; 15 จังหวัดมี score และอีก 5 จังหวัดคง `null` ไม่แทนด้วย 0 |
| PPPConnext | Full BI มี 997,293 chart points แต่ geography semantics ไม่ครบ | ใช้ curated aggregate 660 แถว; generic points คงเป็น evidence |
| Cultural Map | มี 5,258 จุดและ supporting records 361 แถว | แสดงจุดกับ sanitized aggregate; ไม่แสดง contact fields |
| RMUTDB | 2,001 records ไม่มี location ระดับ record | แสดงเป็น national/non-geo catalog |
| AppTech MTR | 621 registry rows, aggregate ครบ 77 จังหวัด | แยก registry overview จาก provincial interaction metrics |
| AppTech MRU | มี requirement 2 แถวที่ต่าง grain จาก innovation | แสดงเป็น “โจทย์หรือความต้องการจากพื้นที่” แยกต่างหาก |
| Learning Dashboard | Aggregate 66 จังหวัดและ lookup tables หลาย grain | Exact province join; lookup อื่นอยู่ source insight; unit/`as_of` คง `null` |
| Area-Based | 1,002 participant/business records; 996 เชื่อม 55 จังหวัดและ 6 แถวไม่มีจังหวัด | แยก 996 participant rows ออกจาก 73 provisional project groups / 156 project–province links; 6 แถวอยู่ unmapped |
| City Capital | 18 เทศบาล × 39 metrics | คง grain เทศบาล; เชื่อม 16 จังหวัดด้วยทะเบียน DLA |
| Ruam Thiao | 5 payloads รวม 54 records | แสดง tourism/transport/place/service โดยตัด contact cells |
| Housing | 7,259 public CKAN rows; 194,532 spatial features; demand 25,919 rows ไม่เผยแพร่ | แยก tabular/spatial grain และคง demand local-only |
| Metadata-only 12 แหล่ง | มี discovery/catalog แต่ยังไม่มี structured contract | แสดง source coverage เท่านั้น ไม่สร้าง record/KPI |
| Restricted 5 แหล่ง | Household, financial, health หรือ sensitivity ยังไม่ผ่าน | Cloud มี metadata; payload/value อยู่ local-only |

Source #25 (`spu_sukhothai_care`) ยังเป็น `sensitive_possible` และมี 0 records จึงต้องผ่าน sensitivity gate ก่อนเปลี่ยน lane

## Geography linkage audit

| Source | ผลตรวจ | Dashboard usage |
|---|---|---|
| PPPConnext | Aggregate 660 แถว; province rows 307; เชื่อมได้ 21 จังหวัด | แสดง metric ครัวเรือน/ทุนดำรงชีพแยกหน่วย |
| AppTech MTR | Aggregate ครบ 77 จังหวัด; ผู้ใช้ 2,356; interactions 371 | แสดง provincial aggregate และ registry overview แยกกัน |
| City Capital | Exact DLA match 18/18 เมือง | แสดง 18 เทศบาลใน 16 จังหวัด; benchmark ภายใน snapshot |
| RMUTDB | ไม่มี location ระดับ record | ใช้ non-map national insight เท่านั้น |

หลักฐานต้นทางอยู่ใน AIAT evidence workspace ภายนอก repo นี้:

- `data/staged/f1_pppconnext/20260804T_pppconnext_bi_silver_01/manifest.json`
- `data/raw/network/f2_apptech_mtr/20260816T_geo_link_audit_07/manifest.json`
- `data/raw/ckan/f3_city_capital_open_data/20260816T_dla_city_crosswalk_14b/manifest.json`
- `data/staged/silver/f2_rmutdb/20260805T_ebook_silver_01/summary.json`

ระบบห้าม infer จังหวัดจากชื่อหน่วยงาน, affiliation หรือข้อความประกอบ ถ้าไม่มี exact key/official crosswalk ต้องอยู่ non-geo หรือ unmapped

## Executive dimensions

| มิติ | ตัวอย่างข้อมูล | หลักอ่าน |
|---|---|---|
| ที่อยู่อาศัยและกำลังซื้อ | ราคาบ้านต่อรายได้, การผ่านสินเชื่อ, ความแออัด | เทียบ metric เดียวกันและคงหน่วยต้นทาง |
| ความเสี่ยงและความเปราะบาง | น้ำท่วม, SRA-DSS | แสดง definition status; ไม่ตีความทิศทางแทนต้นทาง |
| ครัวเรือนและทุนดำรงชีพ | PPPConnext aggregate | ไม่รวม metric ต่างหน่วยเป็นคะแนนเดียว |
| เศรษฐกิจชุมชน | Learning Dashboard, Area-Based | ระบุ selected-project/participant scope |
| โครงการและนวัตกรรม | AppTech, Area-Based และความต้องการพื้นที่ | แยก innovation, requirement และ platform activity |
| บริการเมือง | City Capital 39 metrics | คง grain เทศบาล; benchmark เฉพาะ 18 เมือง |
| วัฒนธรรมและท่องเที่ยว | Cultural Map, Ruam Thiao | จุดอยู่บนแผนที่; non-point อยู่ใน briefing/insights |

## UX and interpretation contract

- หน้าแรกให้แผนที่เด่นและอธิบายวิธีเลือกจังหวัดแบบสั้น
- เมื่อเลือกจังหวัด แสดง 5 แท็บ: ภาพรวม, โครงการและงบ, คนและพื้นที่, มิติการพัฒนา และคุณภาพข้อมูล
- ภาพรวมต้องมีเส้นทาง `Need → Input → Activity → Output → Outcome` และแสดงช่องที่ไม่มีหลักฐานอย่างตรงไปตรงมา
- “โครงการ” ใช้ provisional grouping จากชื่อโครงการ+ปีงบ+หน่วยวิจัย; participant records แสดงเป็นคนละ metric
- เงินทุน AppTech เป็นค่าที่ติดกับ innovation record และอาจเชื่อมหลายจังหวัด; ไม่ใช่งบจัดสรรหรือเบิกจ่ายจังหวัด
- รายการยาวโหลดเมื่อเปิดรายละเอียดพื้นที่
- Non-geo, unmapped และสถานะครบ 28 แหล่งอยู่หน้า `/insights`
- ไม่มี composite score, budget ranking, ลูกศรเชิงตัดสิน หรือ raw spreadsheet dump
- `null` หมายถึงไม่มีข้อมูล ไม่ใช่ศูนย์
- สีแผนที่สื่อ evidence coverage ไม่ใช่ performance หรือความต้องการงบ

## Remaining limitations

- ทุก public value ยังเป็น `candidate`/`needs_review`; `HTTP 200` ไม่ใช่ fact acceptance
- Source #24 (`f4_research_dashboard_psu`) ยังเป็น metadata-only และไม่มี verified structured project/budget API จึงยังไม่มี Project ID ทางการ, หัวหน้าโครงการ, สถานะดำเนินงาน หรืองบเบิกจ่ายสำหรับเติมใน Dashboard
- 12 metadata-only sources ต้องมี structured endpoint, schema และ freshness contract ก่อนแสดงค่า
- Learning Dashboard ยังไม่มี source-wide unit/`as_of` และครอบคลุม selected project participants
- Operational refresh มี 6 executable plans และ live audit ผ่าน 6/6 แต่ยังไม่เปิด cron จนมี persistent raw/manifest storage, retention และ alerting
- Dashboard ไม่สร้าง composite score หรือคำแนะนำจัดสรรงบจากข้อมูลต่างหน่วย

Classification และ publication rules ฉบับเต็มอยู่ใน [Data governance](data-governance.md)
