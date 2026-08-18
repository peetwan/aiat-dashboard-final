# การเพิ่ม Connector ใหม่

เอกสารนี้เป็นเส้นทางมาตรฐานสำหรับเพิ่ม URL เข้า central pipeline ผ่าน Pull Request

## สิ่งที่ต้องมีในหนึ่ง PR

1. แหล่งเดิมต้องมี entry ใน generated `config/source_catalog.json`; source ลำดับใหม่ต้องเพิ่ม canonical registry/source card ผ่าน evidence workspace แล้ว regenerate ห้ามแก้ catalog ด้วยมือ
2. เพิ่ม plan ใน `config/ingestion_plans.json` พร้อม `driver` และ `connector` entrypoint
3. เพิ่ม Python module ที่ `app/connectors/<source_id>.py`
4. เพิ่ม contract ที่ `config/connector_contracts/<source_id>.json`
5. เพิ่ม fixture ที่ลบข้อมูลระบุตัวบุคคลแล้วใน `tests/fixtures/connectors/<source_id>.json`
6. เพิ่ม unit tests ที่ใช้ fixture หรือ fake recorder; ห้ามเรียก network จริงใน CI
7. รัน `python -m app.cli validate-pipeline`, `python tools/validate_public_repo.py` และ `python -m pytest -q`

เริ่มจากไฟล์ใน `templates/connector/` หรือให้ tool สร้าง connector + contract + fixture + offline test ตั้งต้น:

```powershell
python tools/scaffold_connector.py <source_id> --transport <lower_snake_case> --dataset-key <key> --grain-th "หนึ่งแถวแทน..." --identity-fields <field[,field]>
```

รันด้วย `--dry-run` ก่อนได้ และเพิ่ม `--identity-fields` หลายครั้งเมื่อต้นทางมี identity สำรอง Tool ไม่แก้ generated source catalog/ingestion plan และไม่ overwrite ไฟล์เดิม จึงต้องเพิ่ม plan และแก้ parser, grain, identity, geography, `as_of` และ completeness ให้ตรงกับต้นทางจริงก่อนเปิด PR

สำหรับ source ลำดับใหม่ที่ยังไม่อยู่ใน catalog ให้ลงทะเบียนใน canonical evidence workspace ก่อน — ในโฟลเดอร์ workspace (`AIAT_EVIDENCE_ROOT`; ค่าเริ่มต้นคือโฟลเดอร์แม่ของ repo นี้) รันคำสั่งเดียว:

```powershell
python scripts/new_source.py <url> --name "ชื่อไทย" --group "ฝ่าย ..."
```

ได้ registry entry + source card skeleton ครบ จากนั้นกลับมา repo นี้รัน `tools/build_source_catalog.py` และ `tools/build_source_coverage.py` เพื่อให้ PR มี generated catalog/coverage diff ที่ตรวจย้อนกลับได้ ดูภาพรวมทุกขั้นที่ [เพิ่ม source ใหม่ (Quickstart)](add-new-source.md)

อย่าพยายามบังคับให้ทุก URL คืน schema เดียวกัน Generalization อยู่ที่ interface ของ connector และ contract ส่วน parsing ยังคงเป็นของ source นั้น ตัวอย่าง pattern ที่รองรับ:

| ต้นทาง | สิ่งที่ connector รับผิดชอบ |
|---|---|
| REST/JSON | query, pagination, total count และ stable ID |
| form JSON | request body/headers ตาม public frontend และ response envelope |
| CKAN | package/resource discovery, CSV download และ resource identity |
| header-array Dashboard | แปลง header + rows พร้อม fail เมื่อความกว้างไม่ตรง |
| snapshot/export | ตรวจ manifest/hash และ parse ไฟล์ที่อนุมัติแล้ว |

หาก URL หนึ่งมีหลาย grain ให้คืนหลาย `dataset_key` และประกาศ grain แยกใน contract ห้ามรวมคน โครงการ จังหวัด และ aggregate เป็น record ชนิดเดียวเพื่อให้ code ดูง่าย

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

Plan ต้องประกาศ request shape ที่ connector ส่งจริงด้วย: GET ระบุ `params`, POST JSON ระบุ `json_body` และใช้ `$PLACEHOLDER` เฉพาะค่าที่เปลี่ยนระหว่าง pagination ตอน generate catalog ค่าพวกนี้จะกลายเป็น `<value>` ส่วน key และค่าคงที่จะถูกล็อกไว้ Runtime จะปฏิเสธ URL, query key, POST body field หรือ action ที่ไม่ตรงกับ reviewed plan

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
