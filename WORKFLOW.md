# Database workflow

## ภาพรวม

~~~text
source registry + endpoint inventory
                 |
                 v
        policy gate ก่อน fetch
                 |
        +--------+---------+
        |                  |
        v                  v
  public API          approved snapshot
        |                  |
        +--------+---------+
                 v
       immutable raw + SHA-256
                 |
                 v
       remove forbidden fields
                 |
                 v
  PostgreSQL / SQLite candidate records
                 |
                 v
       FastAPI + dashboard
~~~

## ลำดับงานปกติ

1. config/source_catalog.json เก็บครบทั้ง 12 source และ 140 endpoints รวม blocked endpoints เพื่อ audit ได้
2. app/ingestion.py ตรวจ cloud_policy ก่อนทุกครั้ง
3. Source แบบ api_first จะลอง API ก่อน ถ้าล้มเหลวจึงอ่าน snapshot
4. Source แบบ snapshot_only จะอ่าน CSV, JSON, JSONL หรือไฟล์ gzip ใน data/snapshots/source_id
5. ทุก API fetch สร้าง run folder ใหม่ พร้อม response, SHA-256 และ manifest ห้าม overwrite
6. ก่อนเข้า database ระบบลบ email, phone, address, token, cookie และ credential-shaped fields
7. ทุก row เก็บ source_id, dataset_key, source_record_id, hash, fetched_at และ quality_status
8. หน้า dashboard แสดง readiness/count เป็นค่าเริ่มต้น ค่าราย record ต้องผ่าน gate ก่อน

## Source routing

- API-first: f1_sradss_ppaos, f2_apptech_mtr, f2_apptech_mru, f2_learning_area_based, f3_housing_portal
- Snapshot-only: f1_pppconnext, f2_rmutdb
- Snapshot พร้อม project-owner approval และต้องคง external provenance: f2_culturalmap_university, f3_city_capital_open_data, f3_ruamthiao_lamphun
- ห้ามขึ้น Cloud: f2_wallet_all_realtime, f2_wallet_cluster_realtime

## Local workflow

ใช้ MAX_RECORDS_PER_SOURCE จำกัดจำนวนระหว่างพัฒนา ค่า 0 หมายถึงไม่จำกัด หลัง ingest ให้ดู manifest และรัน pytest ก่อนเสมอ

## Railway workflow หลัง approval

1. production_values_allowed เปิดแล้วสำหรับ 10 source ตาม APPROVAL_RECORD.md
2. ตั้ง APP_ENV=production และ DATABASE_URL จาก Railway PostgreSQL
3. Web service เปิด FastAPI อย่างเดียว
4. Cron service ใช้ image เดียวกันและรัน python -m app.cli ingest --all
5. Raw fallback ให้วางบน private object storage หรือ Railway Volume และตรวจ SHA-256
6. ตั้ง PUBLIC_DATA_VALUES_ENABLED=true เมื่อต้องการเปิดค่า candidate ของ 10 source โดยต้องคงป้าย needs_review
