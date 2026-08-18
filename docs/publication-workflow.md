# ส่งข้อมูลขึ้น Public แบบสองเลน

ระบบนี้ไม่ย้าย Candidate ไป Public เอง งานเผยแพร่แบ่งเป็นสองเลนตามชนิดของการเปลี่ยนแปลง

| เลน | ใช้เมื่อ | วิธี merge |
|---|---|---|
| ตั้งชุดข้อมูล/ความหมายใหม่ | เพิ่ม URL หรือ dataset, เปลี่ยนความหมาย, `config/publication_contracts/`, builder, `data/public/serving_manifest.json`, code/config/workflow หรือไฟล์ใต้ `data/spatial/` และ `data/demand/` | Codex review + checks; ถ้า `peetwan` เป็นผู้เขียนให้ Peet กด squash merge เอง |
| อัปเดตข้อมูลรอบเดิม | builder เดิมเขียนทับเฉพาะไฟล์ที่ contract เดิมประกาศไว้ใต้ `data/public/` และสร้าง `data/public/publication_receipt.json` ใหม่ | PR ของ `peetwan`: owner manual squash merge หลัง Codex review; PR ของ contributor: `codex-publication-reviewed` + squash auto-merge |

ถ้าไม่แน่ใจว่าอยู่เลนไหน ให้ใช้เลนตรวจเองก่อน การเพิ่ม contract ครั้งแรกต้องตรวจเองเสมอ แต่รอบถัดไปของ dataset เดิมใช้เลนอัปเดตอัตโนมัติได้

## อัปเดตข้อมูลรอบเดิม

1. สร้าง branch ใหม่จาก `main` แล้วรัน deterministic builder ของ dataset นั้น
2. ตรวจว่า diff มีเฉพาะ output ที่ประกาศใน contract เดิม
3. สร้าง receipt และตรวจทั้ง release:

```powershell
python -m app.cli publication receipt
python -m app.cli publication validate
```

4. เปิด Pull Request ชนิด `Routine public-data refresh`
5. รอ checks `pipeline` และ `publication-gate` ผ่าน
6. ให้ Codex review revision ล่าสุดและแก้ P0/P1 หรือ conversation ให้หมด
7. ถ้า `peetwan` เป็นผู้เขียน ให้ Peet ตรวจ head SHA ล่าสุดแล้วกด squash merge เอง; ถ้า contributor เป็นผู้เขียน ผู้ตรวจที่ไม่ใช่ author จึงใส่ `codex-publication-reviewed` เพื่อเปิด auto-merge

Codex review เป็น findings ไม่ใช่ GitHub approval และ branch protection ไม่บังคับ teammate Approve ผู้กด merge ต้องตรวจเองว่า review ครอบคลุม head SHA ล่าสุด ไม่มี P0/P1 ค้าง และ checks ผ่าน ห้ามใส่ auto-merge label ให้ PR ของตัวเอง ทุกครั้งที่ push commit เพิ่ม, เปลี่ยน base หรือ `main` เดินหน้า ต้องตรวจ revision ใหม่

เลนอัตโนมัตินี้ใช้กับ branch ของ collaborator ภายใน repository เดียวกันเท่านั้น เพราะต้องผูก GitHub check กับ PR/head/base แบบตรวจสอบได้ PR จาก fork ให้ผ่าน gate เหมือนเดิมแต่ทีมต้อง review และ merge เอง

## `publication-gate` ตรวจอะไร

Gate ทำงานแบบ fail-closed โดยไม่เรียกเว็บไซต์ต้นทางและไม่ต่อ production database:

- diff เป็น routine refresh จริง และไม่มี code, config, contract, builder หรือ `serving_manifest.json` ปน
- ทุกไฟล์อยู่ใต้ `data/public/` และมี contract ครอบไว้
- JSON, GeoJSON หรือ CSV อ่านได้ ขนาดและ schema ไม่หลุดจากที่ประกาศ
- identity ไม่ซ้ำ, ชุด identity เปลี่ยนไม่เกิน `max_identity_churn_ratio` และ count/completeness อยู่ในช่วงที่ contract ยอมรับ
- source ยังมีสิทธิ์เผยแพร่ตาม catalog
- ไม่พบ secret, field อ่อนไหว, เบอร์โทร, อีเมล หรือที่อยู่จาก heuristic scan; ผู้ตรวจยังต้องดูชื่อบุคคลและความหมายระดับบุคคลใน diff เอง
- hash ของไฟล์และ contract ตรงกับ `publication_receipt.json`

Gate ผ่านหมายถึง revision ตรงตามกติกาที่ทีมเคยอนุมัติ ไม่ได้แปลว่าข้อมูลกลายเป็น KPI ที่รับรองแล้ว

## Publication contract

หนึ่ง dataset มี contract ใต้ `config/publication_contracts/` เพื่อบอกระบบว่า output แบบใดปลอดภัยและถือว่าครบ:

| ส่วน | บอกอะไร |
|---|---|
| `grain_th` | หนึ่ง record แทนอะไร |
| `identity` | field ใดทำให้แต่ละ record ไม่ซ้ำ |
| `geography` | เชื่อมพื้นที่ระดับใดและใช้ field ไหน |
| `as_of` | ข้อมูลอ้างถึงเวลาใด หรือระบุว่าต้นทางไม่มี |
| `measures.unit` / `denominator` | ตัวเลขวัดด้วยหน่วยใดและหารด้วยฐานอะไร |
| `completeness` | ใช้กติกาใน `outputs`: จำนวนหลักอยู่ที่ `records_pointer`; ชุดรองเพิ่ม `completeness_rules` ด้วย pointer + expected/minimum count |
| `privacy_profile` | ข้อมูลชนิดใดอนุญาตให้เผยแพร่ |
| `outputs` | path, format, schema, identity, ขอบเขตการเปลี่ยนชุด identity และ count ของไฟล์ |

Contract ใช้ได้กับทุก URL เพราะกำหนดกติกากลาง แต่ไม่บังคับให้ทุกเว็บมี schema เหมือนกัน หากหลักฐานยังไม่บอกหน่วย, denominator, เวลา หรือพื้นที่ ให้คงค่าเป็น `ไม่ระบุ`/`needs_review`; ห้ามเดาเพื่อให้ gate ผ่าน การแก้ความหมายเหล่านี้คือการแก้ contract และต้องเข้าเลนตรวจเอง

เริ่ม dataset ใหม่แบบไม่เขียน public output ได้ด้วย scaffold (คำสั่งตัวอย่างเป็น dry run):

```powershell
python tools/scaffold_publication.py rmutdb_summary `
  --source-ids f2_rmutdb --source-scope approved_values `
  --grain "หนึ่งแถวต่อหนึ่งรายการสรุป" --identity-fields row_id `
  --geography-level "ไม่ระบุ" --geography-fields "ไม่ระบุ" `
  --as-of-status "ไม่ระบุ" --as-of-fields "ไม่ระบุ" `
  --measure-name record_count --measure-field record_count `
  --measure-unit "รายการ" --measure-denominator "ไม่เกี่ยวข้อง" `
  --output-path data/public/rmutdb_summary.json --output-format json `
  --output-role database --downloadable true --records-pointer /items `
  --privacy-profile aggregate_public --max-bytes 1048576 --minimum-count 1 `
  --max-count-drop-ratio 0.1 --max-count-increase-ratio 1 `
  --max-identity-churn-ratio 0.25 --dry-run
```

เมื่อตัด `--dry-run` เครื่องมือจะสร้าง contract, builder ที่ยัง fail-closed, fixture สังเคราะห์แบบ redacted และ focused test เท่านั้น โดยตั้งใจไม่สร้างไฟล์ใต้ `data/public/` ขั้นต่อไปคือให้ทีมตรวจและเขียน mapping ใน builder, สร้าง output จริง, เพิ่ม `serving_manifest.json` เมื่อ role เป็น `database`, สร้าง receipt ใหม่ แล้วรัน `publication validate`; PR รอบแรกทั้งหมดอยู่เลน manual review

## Manifest กับ receipt ต่างกันอย่างไร

| ไฟล์ | หน้าที่ | แก้ใน routine refresh ได้ไหม |
|---|---|---|
| Build/source manifest เช่น `data/public/manifest.json` หรือ `*_manifest.json` | บอก provenance และผลจาก builder ของ dataset | ได้ เมื่อ contract ประกาศไฟล์นั้นเป็น output |
| `data/public/serving_manifest.json` | บอก Dashboard ว่า artifact ใดเข้า `public_artifacts` และใช้ key/source ใด | ไม่ได้ ต้องให้ทีมตรวจเอง |
| `data/public/publication_receipt.json` | รายการ hash ของ output และ contract ทั้ง release เพื่อยืนยันว่า CI กำลังตรวจไฟล์ชุดเดียวกัน | ต้องสร้างใหม่ทุกครั้ง; receipt ไม่ใช่การอนุมัติและไม่ใช่รายการ seed database |

## หลัง merge

Railway deploy จาก `main` แล้ว Dashboard startup จึงตรวจ manifest/payload และ sync reviewed artifact เข้า PostgreSQL แบบ idempotent ภายใต้ lock นี่เป็นจุดเดียวที่ routine publication เปลี่ยน production database

Codex/team automation มีหน้าที่ review PR, ใส่ label และตรวจ `/health` กับ database coverage หลัง deploy เท่านั้น ห้าม automation เขียน database, รัน ingestion ด้วย production secret หรือแก้ row โดยตรง หาก health ไม่ผ่านให้หยุด release/rollback deployment และแก้ผ่าน PR ใหม่
