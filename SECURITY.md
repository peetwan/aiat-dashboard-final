# Security and data gates

## ค่าเริ่มต้นที่จงใจล็อก

- production_values_allowed เป็น true สำหรับ 10 source ตาม project-owner approval และ false สำหรับ wallet 2 source
- PUBLIC_DATA_VALUES_ENABLED เป็น false
- ALLOW_PENDING_OWNER_SOURCES เป็น false
- wallet สอง source เป็น restricted_local_only และ pipeline ปฏิเสธเสมอ
- auth, login, person, household และ error endpoints อยู่ใน catalog แต่ runtime_enabled เป็น false

## สิ่งที่ห้าม commit

- .env และ secrets
- database files
- data/snapshots และ data/runtime
- signed URL, cookie, API key หรือ authorization header
- raw payload ที่มี contact, household, health หรือ financial data

## Checklist ก่อนอนุมัติ source ขึ้น Railway

1. มี owner decision และ publication scope เป็นลายลักษณ์อักษร
2. ยืนยัน schema, grain, unit, denominator, as_of และ freshness
3. PII scan ผ่าน และระบุ fields ที่อนุญาตแสดง
4. เปรียบเทียบ row count กับ immutable raw + manifest
5. ทดสอบ API retry/rate limit โดยไม่ bypass auth
6. ตรวจว่า source อยู่ใน approved 10 sources และไม่ใช่ restricted wallet
7. เปิด PUBLIC_DATA_VALUES_ENABLED โดยคง candidate/needs_review label
