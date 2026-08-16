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
| Public serving artifacts | 161 |
| Restricted values บน Cloud | 0 |
| Operational candidate rows | 0 จนกว่าจะรัน API refresh |

Production ใช้ PostgreSQL เป็น serving database และตรวจความครบได้ที่ `/api/public/v1/database-coverage`

## Source coverage findings

| Source | สิ่งที่พบ | วิธีนำเสนอ |
|---|---|---|
| SRA-DSS | Registry มี 20 จังหวัด แต่ overall ปี 2569 มีตัวเลข 15 จังหวัด | แสดง 15 จังหวัด; อีก 5 จังหวัดคง `null` ไม่แทนด้วย 0 |
| PPPConnext | Full BI มี 997,293 chart points แต่ geography semantics ไม่ครบ | ใช้ curated aggregate 660 แถว; generic points คงเป็น evidence |
| Cultural Map | มี 5,258 จุดและ supporting records 361 แถว | แสดงจุดกับ sanitized aggregate; ไม่แสดง contact fields |
| RMUTDB | 2,001 records ไม่มี location ระดับ record | แสดงเป็น national/non-geo catalog |
| AppTech MTR | 621 registry rows, aggregate ครบ 77 จังหวัด | แยก registry overview จาก provincial interaction metrics |
| AppTech MRU | มี requirement 2 แถวที่ต่าง grain จาก innovation | แสดงเป็น “โจทย์หรือความต้องการจากพื้นที่” แยกต่างหาก |
| Learning Dashboard | Aggregate 66 จังหวัดและ lookup tables หลาย grain | Exact province join; lookup อื่นอยู่ source insight; unit/`as_of` คง `null` |
| Area-Based | 1,002 records; 996 เชื่อม 55 จังหวัดและ 6 แถวไม่มีจังหวัด | 996 อยู่ province views; 6 อยู่ unmapped section |
| City Capital | 18 เทศบาล × 39 metrics | คง grain เทศบาล; เชื่อม 16 จังหวัดด้วยทะเบียน DLA |
| Ruam Thiao | 5 payloads รวม 54 records | แสดง tourism/transport/place/service โดยตัด contact cells |
| Housing | 7,259 public rows; 6,953 ผูก 12 จังหวัดและ 306 ไม่มีจังหวัด | แยก province briefings กับ unassigned/non-map projection |
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
- เมื่อเลือกจังหวัด แสดง context และข้อสังเกตก่อน technical coverage
- รายการยาวโหลดเมื่อเปิดรายละเอียดพื้นที่
- Non-geo, unmapped และสถานะครบ 28 แหล่งอยู่หน้า `/insights`
- ไม่มี composite score, budget ranking, ลูกศรเชิงตัดสิน หรือ raw spreadsheet dump
- `null` หมายถึงไม่มีข้อมูล ไม่ใช่ศูนย์
- สีแผนที่สื่อ evidence coverage ไม่ใช่ performance หรือความต้องการงบ

## Remaining limitations

- ทุก public value ยังเป็น `candidate`/`needs_review`; `HTTP 200` ไม่ใช่ fact acceptance
- 12 metadata-only sources ต้องมี structured endpoint, schema และ freshness contract ก่อนแสดงค่า
- Learning Dashboard ยังไม่มี source-wide unit/`as_of` และครอบคลุม selected project participants
- Operational refresh มี 6 executable plans แต่ยังไม่ควรเปิด cron จนมี persistent raw/manifest storage
- Dashboard ไม่สร้าง composite score หรือคำแนะนำจัดสรรงบจากข้อมูลต่างหน่วย

Classification และ publication rules ฉบับเต็มอยู่ใน [Data governance](data-governance.md)
