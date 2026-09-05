# ใช้ข้อมูลตามบริบทของงาน

ชื่อเจ้าของผลงาน ผู้วิจัย เจ้าของสิทธิ์ และชื่อหน่วยงานเป็นรายละเอียดที่มีประโยชน์ของงานนั้น ระบบรองรับการเก็บและเผยแพร่ฟิลด์เหล่านี้ รวมถึงช่องทางติดต่องานที่ต้นทางเผยแพร่และที่ตั้งสถานที่สาธารณะ ชื่ออาจระบุตัวบุคคลได้ แต่ไม่จำเป็นต้องลบชื่อทุกประเภทออกจากทุก dataset

ฟิลด์ทั่วไป เช่น ชื่อโครงการ จังหวัด ยอดรวม งบโครงการ และจำนวนรายการ ใช้ได้ตามเดิม `field_contexts` ใช้เฉพาะฟิลด์ที่ตัวกรองอาจเข้าใจผิด กรอกครั้งเดียวใน contract และใช้ซ้ำได้ทุกรอบ refresh การ review ใช้ PR ปกติของทีม ไม่ต้องมีแบบขออนุญาตเพิ่มสำหรับแต่ละ record

## เลือกบริบท

| ค่า | ใช้กับ | ตัวอย่าง |
|---|---|---|
| `work_attribution` | เครดิตเจ้าของงาน ผู้วิจัย ผู้แต่ง เจ้าของสิทธิ์ที่ต้นทางแสดงคู่กับผลงาน | ชื่อ PI ของโครงการ, `research_leads[].name` |
| `organization` | ชื่อหน่วยงานหรือนิติบุคคลที่ตัวกรองตีความเป็นชื่อบุคคล | `rights_owner` ที่เป็นมหาวิทยาลัย |
| `public_contact` | ช่องทางติดต่องาน/ธุรกิจที่ต้นทางประกาศให้ใช้ติดต่อ | อีเมลสำนักงาน เบอร์ติดต่องาน LINE OA |
| `public_location` | ที่ตั้งหน่วยงาน ธุรกิจ สถานที่ท่องเที่ยว หรือสถานที่จัดงาน | `address`, `venue_address` |
| `record_identifier` | รหัส record ที่หลักฐานยืนยันว่าเป็นรหัส แม้ตัวเลขมีรูปเหมือนเบอร์โทร | รหัสโครงการ |
| `public_measure` | ค่าตัวเลขสาธารณะที่มีรูปเหมือนเบอร์โทร | ยอดเงินหรือจำนวนรวม |

ใช้หลักฐานที่มีอยู่ เช่น source URL, manifest หรือหน้ารายละเอียด เพื่ออธิบายเหตุผลใน `notes_th` ของ connector หรือใน PR ของ publication ฟิลด์ใหม่ที่ไม่มีหลักฐานให้ใช้ค่าเริ่มต้นและตรวจบริบทก่อนประกาศ ช่องทางส่วนตัวของผู้ตอบแบบสอบถามไม่กลายเป็นช่องทางติดต่องานเพียงเพราะพบใน response

Secrets เลขประจำตัวประชาชน ข้อมูลสุขภาพหรือการเงินระดับบุคคล และที่อยู่บ้านยังใช้บริบทสาธารณะมาเปิดไม่ได้ งบโครงการหรือยอดรวมตามจังหวัดเป็นข้อมูลอีกประเภทหนึ่งและใช้งานได้

URL รายละเอียดที่ registry ประกาศเป็น template เช่น `?id={project_id}` ใช้ ID ของแต่ละผลงานเป็น provenance ได้เลย โดยไม่ต้องลงทะเบียน URL ใหม่ทีละรายการ ชื่อ parameter และ filter คงที่ยังต้องตรงกับ endpoint ที่ประกาศ

## ใส่ใน connector

เพิ่ม `field_contexts` ใน grain ที่เกี่ยวข้องของ `config/connector_contracts/<source_id>.json`:

```json
"field_contexts": {
  "/researcher_name": "work_attribution",
  "/rights_owner": "organization",
  "/ownerContact/name": "work_attribution",
  "/ownerContact/email": "public_contact",
  "/address": "public_location"
}
```

Path เริ่มจาก record หนึ่งรายการ ใช้ JSON pointer: `/` แยกชั้น, `*` แทนสมาชิก array เช่น `/research_leads/*/name` และใช้ `~1` แทน `/` ในชื่อฟิลด์ ต้องชี้ถึงค่าปลายทาง การประกาศชื่อเจ้าของงานไม่ได้เปิดฟิลด์พี่น้องทั้งหมดให้ผ่าน

Parser ต้องคืนฟิลด์นั้นด้วย ถ้า parser ทิ้งชื่อก่อนถึงขั้น sanitize การเพิ่ม contract อย่างเดียวไม่สามารถคืนข้อมูลที่หายไปได้ ตัวอย่างจริงที่แก้แล้วคือ `app/connectors/clig_projects.py` กับ `config/connector_contracts/clig_projects.json`

## ใส่ใน publication

เพิ่ม `field_contexts` ใน output ที่เกี่ยวข้องของ publication contract โดย path เริ่มจากไฟล์ทั้งไฟล์:

```json
"field_contexts": {
  "/items/*/researcher_name": "work_attribution",
  "/items/*/rights_owner": "organization",
  "/items/*/ownerContact/email": "public_contact"
}
```

CSV ใช้ `/*/ชื่อคอลัมน์` output แต่ละไฟล์มีบริบทของตัวเอง ชื่อใน JSON จึงไม่เปิดทางให้ไฟล์ download อีกไฟล์โดยอัตโนมัติ ใช้กับ `source_scope: approved_values` และ source ที่มีอยู่ใน contract สร้าง receipt ใหม่แล้วรันชุดตรวจตามปกติ เมื่อ contract คงเดิม รอบอัปเดตถัดไปใช้ routine refresh ได้

## ลองก่อนนำเข้าจริง

```powershell
python tools/preview_privacy.py tests/fixtures/connectors/clig_projects.json --source clig_projects --dataset-key projects
python tools/preview_privacy.py path/to/records.jsonl.gz --source clig_projects --dataset-key projects
python tools/preview_privacy.py data/public/apptech_aggregates.json --publication apptech_aggregates --artifact data/public/apptech_aggregates.json
python -m app.cli check
```

Preview แสดงฟิลด์ที่มีบริบท รายการเปลี่ยนแปลงและเหตุผล โดยไม่แสดงค่าชื่อหรือข้อมูลติดต่อ ไม่เขียน database หรือ R2 สำหรับ connector จะตรวจ grain และ identity ด้วย แต่ยังไม่ตรวจความครบของการดึงทุกหน้าจากต้นทาง ส่วน publication preview ตรวจเฉพาะ privacy จึงยังต้องรัน `check` ก่อนส่งงาน

ข้อมูลต้นทางเก็บใน private R2 ตาม manifest ได้ การพบฟิลด์ที่ไม่ใช้ใน public projection ไม่ต้องทำให้ชุดข้อมูลทั้งชุดใช้ไม่ได้ ค่า unit, geography หรือ as_of ที่ต้นทางไม่ได้ระบุให้คง `null` พร้อมหมายเหตุและแสดงข้อจำกัดได้ โดยไม่ต้องเดาค่าเพื่อให้ดูสมบูรณ์

## หลักฐานและผลที่แก้

ดู [ผลตรวจข้อมูลทุกแหล่ง](data-context-audit.md) สำหรับ R2 ทั้ง 22 source prefixes รวมไฟล์ ZIP และ PDF และรายการที่คืนให้ dashboard แล้ว

หน้า `/insights` มีทะเบียนผลงาน MTR, RMUTDB และ Cultural Map ที่ค้นหาชื่อเจ้าของงานและเปิดต้นทางได้ MRU และ Cultural Map แสดงชื่อผู้รับผิดชอบในหน้าจังหวัด ส่วนข้อมูลติดต่อบริการลำพูนอยู่ในหมวดท่องเที่ยว หน้า F4 แสดงชื่อและตำแหน่งผู้วิจัย CLIG จาก public artifact ที่จับคู่โครงการแล้ว

สร้าง publication contract ใหม่ด้วย scaffold ใช้ `--field-context /items/*/owner_name work_attribution` หรือ `--field-context /*/email public_contact` สำหรับ CSV ได้ ไม่ต้องเปลี่ยนชื่อคอลัมน์หลบตัวกรอง

`public_contact` ครอบคลุมข้อความที่รวมชื่อ อีเมล เบอร์ และที่อยู่สำหรับติดต่องานไว้ในช่องเดียวด้วย ส่วน `public_location` ใช้เมื่อเป็นที่ตั้งอย่างเดียว

## สร้างข้อมูลซ้ำจากหลักฐาน

ทีมที่แก้ connector หรือ UI ใช้ไฟล์ public ที่ commit อยู่และ fixture ได้เลย ไม่ต้องมี R2 ทุกคน ผู้ที่ rebuild ข้อมูลต้องตั้ง `AIAT_EVIDENCE_ROOT` ให้ชี้ evidence workspace เดิม

การ regenerate catalog/coverage ต้องมี source card ของแต่ละ source ใน `data/source_audit/` ของ evidence workspace รวม `29_clig_projects/source_card.json` ที่อ้าง hash ของหลักฐาน R2 จริง Connector contract บอกวิธีรับข้อมูล แต่ใช้แทนบันทึกการตรวจแหล่งข้อมูลไม่ได้

```powershell
python tools/build_source_catalog.py
python tools/build_source_coverage.py
python tools/build_source_insights.py
python tools/build_provincial_briefings.py
python tools/build_executive_summaries.py
python -m app.cli publication receipt
python -m app.cli check
```

RMUTDB ใช้ PDF เดิมและ parser ภาษาไทยใน `scripts/rmutdb_ebook_silver.py`, `pdf_object_reader.py`, `pdf_text_extract.py` ของ evidence workspace เพื่ออ่าน font/glyph เหมือนรอบที่สร้าง Silver ตรวจ SHA-256, ID และชื่อผลงานให้ตรงก่อนจับคู่ช่องทางติดต่อ ไม่ยิง API ที่ต้อง login

หลังสร้าง housing spatial seed ด้วยเครื่องมือเดิม ให้เติมรายละเอียดสถานที่ด้วย `python tools/build_housing_place_details.py <run_dir>` โดย run_dir มี `manifest.json` และ `housing_points_rows.jsonl.gz` ที่ดึงจาก R2 โปรแกรมตรวจ hash, จำนวน, ID และ geometry ก่อนเขียน ไม่เขียนทับหลักฐาน

ฟังก์ชัน `build(generated_at=...)` ของ source insights, briefings และ executive summaries รับ timestamp เดียวกันได้สำหรับตรวจ byte-for-byte deterministic build

CLIG ใช้ `python tools/build_clig_work_attribution.py <clig_project_run> <psu_detail_run>` โดยโฟลเดอร์แรกมี manifest และ projects.jsonl.gz ส่วนโฟลเดอร์ที่สองมี manifest และ project_detail_records.jsonl.gz โปรแกรมตรวจ hash, จำนวน, ID และ URL ทั้งชุด แล้วสร้าง clig_work_attribution.json สำหรับ API และ download ใส่ `--generated-at` เมื่อต้องการสร้างซ้ำให้ได้ timestamp เดิม ขั้นตอนนี้ทำเมื่ออัปเดตหลักฐาน CLIG โดยไม่ต้องรันซ้ำเมื่อแก้ UI หรือ source อื่น
