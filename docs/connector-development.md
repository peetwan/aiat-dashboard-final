# การเพิ่ม Connector ใหม่

เอกสารนี้เป็นเส้นทางมาตรฐานสำหรับเพิ่ม URL เข้า central pipeline ผ่าน Pull Request

## สิ่งที่ต้องมีในหนึ่ง PR

1. แหล่งข้อมูลต้องอยู่ใน `config/source_catalog.json`
2. เพิ่ม plan ใน `config/ingestion_plans.json` พร้อม `driver` และ `connector` entrypoint
3. เพิ่ม Python module ที่ `app/connectors/<source_id>.py`
4. เพิ่ม contract ที่ `config/connector_contracts/<source_id>.json`
5. เพิ่ม fixture ที่ลบข้อมูลระบุตัวบุคคลแล้วใน `tests/fixtures/connectors/<source_id>/`
6. เพิ่ม unit tests ที่ใช้ fixture หรือ fake recorder; ห้ามเรียก network จริงใน CI
7. รัน `python -m app.cli validate-pipeline`, `python tools/validate_public_repo.py` และ `python -m pytest -q`

เริ่มจากไฟล์ใน `templates/connector/` แล้วเปลี่ยนชื่อ class, driver, grain และ completeness checks ให้ตรงกับต้นทางจริง

## ขอบเขตของ Connector

Connector ทำได้เฉพาะ:

- เรียก public endpoint ตาม config
- จัด pagination
- parse response
- ตรวจ schema, จำนวนแถว, ID ซ้ำ และความครบ
- คืนค่าเป็นรายการ `(dataset_key, payload)`

Connector ห้าม:

- เขียน `public_artifacts` โดยตรง
- promote Candidate เป็น Public
- เก็บ token/cookie ลง config, fixture หรือ log
- bypass 401/403, login หรือ CAPTCHA
- นำชื่อบุคคล เบอร์โทร อีเมล หรือที่อยู่เข้า fixture

ส่วนกลางใน `app/ingestion.py` จะเป็นผู้เก็บ response, SHA-256, manifest, sanitize payload, ป้องกัน record version ซ้ำ และเขียน Candidate เข้า `dashboard_records`

## Contract ต้องตอบอะไรได้

- Source ID และ Python connector อยู่ที่ไหน
- ข้อมูลเดินทางมาแบบใด เช่น JSON, form JSON หรือ CKAN CSV
- แต่ละ dataset มี grain อะไร
- ใช้ field ใดเป็น identity
- ใช้ field ใดเชื่อมพื้นที่
- ตรวจอย่างไรว่าดึงครบ
- field ใดห้ามเผยแพร่

`python -m app.cli validate-pipeline` ตรวจ contract ทุกตัวโดยไม่ติดต่อเว็บไซต์ต้นทาง จึงใช้ใน Pull Request ได้อย่างเสถียร

## การทดสอบ

ทดสอบอย่างน้อยสี่กรณี:

1. response ปกติได้ dataset/grain ที่ถูกต้อง
2. pagination หรือจำนวนรวมครบ
3. response ไม่ครบหรือ schema เปลี่ยนแล้วต้อง fail ก่อนเขียน database
4. fixture ไม่มีข้อมูลส่วนบุคคลหรือ secret

ดูรูปแบบ fake recorder ได้ใน `tests/test_ingestion.py`

## Publication boundary

ผลจาก connector เป็น Candidate เท่านั้น การเปลี่ยน Public release ต้องผ่าน builder, privacy tests, semantic diff review และการ merge revision ใหม่ ห้ามเพิ่ม code path ที่ auto-promote Candidate ไป `public_artifacts`
