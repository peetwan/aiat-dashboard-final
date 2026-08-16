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
Gold projection        operational ingest
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
python tools/build_public_data.py
python tools/build_provincial_briefings.py
~~~

ตัว builder จะ:

1. รับเฉพาะ 10 source ที่ owner อนุมัติให้เผยแพร่
2. ตัด 2 wallet source ออกจาก public artifacts โดยอัตโนมัติ
3. อ่าน merged evidence โดยไม่แก้ raw เดิม
4. สร้าง Silver projection ที่คง field, หน่วย, เวลา และ URL ต้นทาง
5. สร้าง Gold provincial briefing แยก “ข้อมูลสำคัญ” ออกจาก “ข้อมูลอื่นทั้งหมด” โดยไม่รวมเป็นคะแนนใหม่
6. สร้าง province boundary จากแหล่งทางการ 77 จังหวัด และ cultural point 5,258 จุด
7. เขียน manifest พร้อม SHA-256 ของ output และ Gold JSON ทั้ง 77 จังหวัด

ไฟล์สำคัญ:

- `public_dashboard.json` — overview, source metadata และ province profiles
- `province_evidence.csv` — ตารางสัญญาณรายจังหวัด
- `source_inventory.csv` — source, endpoint และ provenance สำหรับประชาชน
- `thailand_provinces.geojson` — polygon สำหรับ WebGL map
- `cultural_points.geojson` — จุดข้อมูลวัฒนธรรมสำหรับ cluster layer
- `provincial_briefings/{code}.json` — ค่าจริง รายการจริง source coverage และ provenance รายจังหวัด

## 2. Public API

API ใต้ `/api/public/v1` เป็น read-only และเปิด CORS สำหรับ `GET` เพื่อให้ website ภายนอกนำข้อมูลสาธารณะไปใช้ต่อได้:

- `/overview`
- `/sources`
- `/provinces`
- `/provinces/{province_code}`
- `/provinces/{province_code}/briefing`
- `/map/provinces`
- `/map/cultural-points`
- `/catalog`

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

เมื่อผู้ใช้คลิกจังหวัด frontend จะเรียก `/api/public/v1/provinces/{code}/briefing` ซึ่งเป็น Gold projection ที่ materialize จาก Silver data ล่วงหน้า จึงไม่ต้องยิงหลาย API ระหว่างเปิดหน้าและยังย้อนกลับไปยัง URL ต้นทางได้ทุกส่วน

ชั้นบนแสดง actual executive signals; ชั้นถัดมาแสดงโครงการและทะเบียนจริง; ชั้น “ข้อมูลอื่นทั้งหมด” คืนทุก resource row ที่ผูกจังหวัดได้ ส่วน source ที่ไม่มีจังหวัดจะระบุสถานะโดยไม่แทนด้วย `0` และไม่เดา geography

## 5. Source routing

- API-first: `f1_sradss_ppaos`, `f2_apptech_mtr`, `f2_apptech_mru`, `f2_learning_area_based`, `f3_housing_portal`
- Snapshot-only: `f1_pppconnext`, `f2_rmutdb`
- Snapshot ที่คง external provenance: `f2_culturalmap_university`, `f3_city_capital_open_data`, `f3_ruamthiao_lamphun`
- Local-only และไม่อยู่ใน public artifacts: `f2_wallet_all_realtime`, `f2_wallet_cluster_realtime`

## 6. Update cycle

1. อัปเดต source ตาม registry และเก็บ raw run ใหม่
2. รวม/validate ที่ data layer หลัก
3. รัน `tools/build_public_data.py` และ `tools/build_provincial_briefings.py`
4. ตรวจ diff ของ manifest, Gold values และ provenance URL
5. รัน test, เปิดดู desktop/mobile แล้วจึง deploy
