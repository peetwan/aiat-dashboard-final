# Full Data Coverage Audit — 28 URLs

Audit date: 2026-08-16

## Executive result

| Layer | Before | After this revision |
|---|---:|---:|
| Source metadata in application DB | 12 | 28 |
| Public candidate sources | 10 | 11 |
| Verified catalog endpoints | 140 | 141 |
| Runtime-enabled endpoints | 89 | 90 |
| Province briefings | 77 files only | 77 database-backed artifacts |
| Executive summaries | 77 files only | 77 database-backed artifacts |
| Total public serving artifacts in DB | 0 | 161 |
| Operational candidate records | 0 | 0 until an explicit API refresh run |

Production before this revision reported `database_backend: sqlite` despite an existing Railway PostgreSQL service. This revision makes PostgreSQL the serving database and exposes `/api/public/v1/database-coverage` for direct verification.

## Source classification

- **Public candidate 11** — มี structured projection สำหรับ Dashboard แต่ยัง needs_review: #1, #2, #3, #6, #7, #8, #10, #11, #14, #16, #23
- **Metadata-only 12** — มี URL/audit status แต่ยังไม่มี structured record contract ที่ยืนยัน: #4, #5, #17, #18, #19, #21, #22, #24, #25, #26, #27, #28
- **Restricted local-only 5** — Cloud มี metadata แต่ไม่มี payload/value: #9, #12, #13, #15, #20

Source #25 มี `sensitive_possible` และยังมี 0 records จึงคง metadata-only/values disabled; ต้องผ่าน sensitivity gate ก่อนเปลี่ยน lane หรือ ingest ค่าใด ๆ

## Data gaps found and disposition

| Source | Audit finding | Disposition |
|---|---|---|
| #1 SRA-DSS | ทะเบียน 20 จังหวัด แต่ overall ปี 2569 มีตัวเลข 15 จังหวัด | แสดง 15; เก็บรายชื่อ 5 จังหวัดที่เป็น null และไม่แทนด้วย 0 |
| #2 PPPConnext | Full BI 997,293 chart points ไม่มี geography semantics ครบ | ใช้ curated aggregate 660 แถว; full chart points เป็น evidence ไม่เทลง UI |
| #3 Cultural Map | 5,258 points อยู่บน map แต่ supporting records 361 แถวหาย | เพิ่ม source insight แบบ sanitized aggregate; ไม่เอา contact field มาแสดง |
| #8 AppTech MRU | requirement 2 แถวไม่อยู่ใน Dashboard | เพิ่ม “โจทย์หรือความต้องการจากพื้นที่” ให้จังหวัด 33 และ 73 แยกจาก innovation |
| #10 Learning Dashboard | API aggregate 66 จังหวัด + ตาราง 3/7/6/6 ไม่มี catalog/API/UI | เพิ่ม builder, exact province join, API driver, source insight และ province summary; unit/as_of คง `null` |
| #11 Area-Based | 1,002 records แต่ 6 แถวไม่มีจังหวัดและหายไป | 996 อยู่ 55 จังหวัด; 6 อยู่ public unmapped section โดยไม่เดาพื้นที่ |
| #16 Ruam Thiao | 5 page payloads/54 recordsอยู่ใน JSON แต่ UI ไม่ render | เพิ่ม tourism/transport/place/service summaries; ไม่แสดง phone/contact cells |
| #23 Housing | public package 7,259 แถว; 6,953 ผูก 12 จังหวัด, 306 ไม่มีจังหวัด | 6,953 อยู่ province briefing; 306 อยู่ unassigned/non-map projection |
| #4–5, #17–19, #21–22, #24–28 | discovery assets ถูกนับเหมือน data ได้ง่าย | แสดงเป็น metadata-only และห้ามสร้าง record/KPI จาก sitemap/page count |
| #9, #12–13, #15, #20 | household/financial/health/sensitive lane | values ไม่อยู่ public artifacts/Railway; restricted leak count = 0 |

## Serving/database boundary

Railway PostgreSQL เก็บเฉพาะสิ่งที่ Dashboard ต้องอ่าน:

- source metadata 28 แถวและ verified endpoint inventory
- public catalog, source insights, source coverage, Source 10 projection และ unmapped data
- province polygon/cultural point layers
- 77 province briefings และ 77 executive summaries

Raw evidence, generic chart payload, restricted rows และ local full datasetsไม่ถูกคัดลอกขึ้น serving DB เพียงเพื่อให้จำนวนดูมาก ข้อมูลที่ไม่ผูกจังหวัดถูกวางใน non-geo/unmapped แทนการเดา join key

## Remaining honest limitations

- ทุก public value ยังเป็น candidate/needs_review; `HTTP 200` ไม่ใช่ fact acceptance
- 12 metadata-only URLs ต้องมี structured endpoint/schema/freshness contract ก่อนจะแสดงค่าจริง
- Source 10 ยังไม่มี source-wide unit/as_of และครอบคลุม selected project participants
- Operational API refresh พร้อม 6 executable plans แต่ไม่เปิด cron จนกว่าจะมี persistent raw/manifest storage
- Dashboard ไม่สร้าง composite score หรือคำแนะนำงบอัตโนมัติจากข้อมูลต่างหน่วย
