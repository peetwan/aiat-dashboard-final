# Data workflow สำหรับ Public Evidence Atlas

## ภาพรวมสองเส้นทาง

~~~text
source registry + endpoint inventory
                 |
          policy / access gate
                 |
       +---------+----------+
       |                    |
       v                    v
Serving projection     operational ingest
(build-time, read-only) (scheduled/runtime)
       |                    |
       v                    v
data/public/*          immutable Bronze raw + SHA-256
manifest + hashes            |
       |                     v
       |               privacy projection
       |                     |
       |                PostgreSQL/SQLite
       +----------+----------+
                  v
        FastAPI public API + WebGL UI
~~~

Public dashboard เปิดได้แม้ยังไม่รัน operational ingestion เพราะ `data/public/` เป็น projection ที่สร้างจาก merged evidence และตรวจ hash แล้ว ส่วน database ใช้เก็บ ingestion run และข้อมูลเชิงปฏิบัติการเมื่อเปิดใช้งานภายหลัง

## 1. Public projection

รันจากโฟลเดอร์ `dashboard_final`:

~~~powershell
python tools/build_source_insights.py
python tools/build_public_data.py
python tools/build_provincial_briefings.py
python tools/build_executive_summaries.py
~~~

ตัว builder จะ:

1. รับเฉพาะ 10 source ที่ owner อนุมัติให้เผยแพร่
2. ตัด 2 wallet source ออกจาก public artifacts โดยอัตโนมัติ
3. อ่าน merged evidence โดยไม่แก้ raw เดิม
4. audit geography ของ PPPConnext, AppTech MTR และ City Capital; แยก RMUTDB เป็น non-geo
5. สร้าง source insight ที่คง field, หน่วย, เวลา และ URL ต้นทาง
6. สร้าง source-shaped provincial briefing ที่คง record และ provenance ฉบับเต็ม
7. สร้าง executive summary โดย clean, group และเปรียบเทียบเฉพาะ metric เดียวกัน ไม่สร้างคะแนนนโยบายใหม่
8. สร้าง province boundary จากแหล่งทางการ 77 จังหวัด และ cultural point 5,258 จุด
9. เขียน manifest พร้อม SHA-256 ของ output ทั้ง 77 จังหวัด

ไฟล์สำคัญ:

- `public_dashboard.json` — overview, source metadata และ province profiles
- `province_evidence.csv` — ตารางสัญญาณรายจังหวัด
- `source_inventory.csv` — source, endpoint และ provenance สำหรับประชาชน
- `thailand_provinces.geojson` — polygon สำหรับ WebGL map
- `cultural_points.geojson` — จุดข้อมูลวัฒนธรรมสำหรับ cluster layer
- `provincial_briefings/{code}.json` — ค่าจริง รายการจริง source coverage และ provenance รายจังหวัด
- `executive_summaries/{code}.json` — สรุปรายมิติที่ clean แล้ว ไม่มี raw rows และพร้อมแสดงผลทันที
- `source_insights.json` — ภาพรวม 4 source, distributions และ geography link ที่ audit แล้ว

## 2. Public API

API ใต้ `/api/public/v1` เป็น read-only และเปิด CORS สำหรับ `GET` เพื่อให้ website ภายนอกนำข้อมูลสาธารณะไปใช้ต่อได้:

- `/overview`
- `/sources`
- `/provinces`
- `/provinces/{province_code}`
- `/provinces/{province_code}/briefing`
- `/provinces/{province_code}/summary`
- `/map/provinces`
- `/map/cultural-points`
- `/catalog`
- `/source-insights`

ไฟล์ projection ยังดาวน์โหลดตรงได้จาก `/downloads/` และไม่ต้องเปิด raw payload gate

## 3. Operational ingestion

1. `config/source_catalog.json` เก็บครบ 12 source และ endpoint inventory
2. `app/ingestion.py` ตรวจ `cloud_policy` ก่อน fetch ทุกครั้ง
3. `api_first` ใช้ API ก่อนและ fallback ไป approved snapshot เมื่อ API ล้มเหลว
4. `snapshot_only` อ่านไฟล์ที่วางใน `data/snapshots/<source_id>/`
5. API fetch ทุกครั้งสร้าง immutable run folder, SHA-256 และ manifest
6. privacy projection ลบ email, phone, address, token, cookie และ credential-shaped fields
7. database เก็บ source ID, record ID, hash, fetched time และ quality status เพื่อย้อนกลับได้

## 4. Provincial panel semantics

เมื่อผู้ใช้คลิกจังหวัด frontend จะเรียก `/api/public/v1/provinces/{code}/summary` ซึ่งเป็น serving projection ขนาดเล็กที่สรุปและเปรียบเทียบไว้แล้ว ส่วน `/briefing` ฉบับเต็มจะโหลดเมื่อเปิดแท็บโครงการเท่านั้น

ชั้นรายมิติแสดงทุกกลุ่มพร้อมอ่านโดยไม่ใช้ dropdown หรือ raw cells หน้า `/insights` แสดงข้อมูลข้ามพื้นที่และ RMUTDB ส่วน source ที่ไม่มีจังหวัดจะระบุสถานะโดยไม่แทนด้วย `0` และไม่เดา geography

## 5. Source routing

- API-first: `f1_sradss_ppaos`, `f2_apptech_mtr`, `f2_apptech_mru`, `f2_learning_area_based`, `f3_housing_portal`
- Snapshot-only: `f1_pppconnext`, `f2_rmutdb`
- Snapshot ที่คง external provenance: `f2_culturalmap_university`, `f3_city_capital_open_data`, `f3_ruamthiao_lamphun`
- Local-only และไม่อยู่ใน public artifacts: `f2_wallet_all_realtime`, `f2_wallet_cluster_realtime`

## 6. Update cycle

1. อัปเดต source ตาม registry และเก็บ raw run ใหม่
2. รวม/validate ที่ data layer หลัก
3. รัน `tools/build_source_insights.py`, `tools/build_public_data.py`, `tools/build_provincial_briefings.py` และ `tools/build_executive_summaries.py`
4. ตรวจ diff ของ manifest, Gold values และ provenance URL
5. รัน test, เปิดดู desktop/mobile แล้วจึง deploy
