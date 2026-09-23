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
- ตรวจ secrets และข้อมูลส่วนตัวตามบริบท; เครดิตเจ้าของผลงาน หน่วยงาน ช่องทางติดต่องาน และที่ตั้งสาธารณะประกาศใน `outputs[].field_contexts` ตาม [คู่มือบริบทข้อมูล](field-contexts.md)
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

รูปหรือสื่อที่เผยแพร่อยู่บน hostname แยกจากหน้าแหล่งข้อมูล สามารถประกาศ `outputs[].media_source_prefixes` เป็น object จาก canonical source ID ไปยังรายการ HTTPS prefix ที่ลงท้ายด้วย `/` ได้ ต้องระบุ source ที่อยู่ใน contract และห้ามมี query, fragment หรือ credentials กติกานี้ใช้เฉพาะ field `media[].url` เท่านั้น ไม่ขยายสิทธิ์ให้ `source_url` หรือลิงก์อื่น และไม่ยกเว้น restricted endpoint การเพิ่ม prefix เป็นการเปลี่ยน trusted contract ที่ต้องเข้าเลนตรวจเอง ไม่ใช่การอนุมัติอัตโนมัติจากการพบ URL ใน raw

เพดานรวมของ publication workspace คือ 160 MiB ชุดตรวจรับ C02 v2 ใช้ replacement overlay 145,584,410 bytes และ successor ที่ยอมรับแล้วใช้ active workspace 145,510,848 bytes เพดานนี้ได้รับอนุญาตเพื่อรักษารายละเอียดที่ผ่านการคัดเลือก โดยยังบังคับ `max_bytes` ราย output และเพดานรายไฟล์แยกกัน F2 ใช้ overview ไม่เกิน 512 KiB, geography/detail child ไม่เกิน 4 MiB และ topic entry ไม่เกิน 8 MiB; ไม่โหลด detail children ทั้งชุดเพื่อแสดงหน้าแรก การเพิ่มเพดานไม่ใช่สิทธิ์ให้ขยายฟิลด์บุคคลหรือ deploy ข้อมูล

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

ไฟล์ JSON, GeoJSON และ CSV ที่สร้างใต้ `data/public/` ใช้ LF ทั้งตอนเขียนและตอน checkout ตาม `.gitattributes` เพื่อให้ SHA-256/ขนาดใน build manifest ตรงกับ Git บน Windows และ Linux ตัวสร้าง CSV ต้องกำหนด `lineterminator="\n"` ด้วย ไม่เปลี่ยน line endings ของ raw evidence เพราะ manifest ของต้นทางตรวจจาก byte เดิม

| ไฟล์ | หน้าที่ | แก้ใน routine refresh ได้ไหม |
|---|---|---|
| Build/source manifest เช่น `data/public/manifest.json` หรือ `*_manifest.json` | บอก provenance และผลจาก builder ของ dataset | ได้ เมื่อ contract ประกาศไฟล์นั้นเป็น output |
| `data/public/serving_manifest.json` | บอก Dashboard ว่า artifact ใดเข้า `public_artifacts` และใช้ key/source ใด | ไม่ได้ ต้องให้ทีมตรวจเอง |
| `data/public/publication_receipt.json` | รายการ hash ของ output และ contract ทั้ง release เพื่อยืนยันว่า CI กำลังตรวจไฟล์ชุดเดียวกัน | ต้องสร้างใหม่ทุกครั้ง; receipt ไม่ใช่การอนุมัติและไม่ใช่รายการ seed database |

## AppTech KPI ฝ่าย 4

`f4/apptech-aggregates` ใช้จำนวนรวมรายจังหวัดจาก innovator dashboard และยอดเงินระดับประเทศจาก family dashboard เท่านั้น UI และสูตร KPI อ่าน reviewed artifact ชุดเดียวกันทั้งประเทศ จังหวัด และภาค การ ingest เข้า Candidate จึงไม่เปลี่ยนค่าบนหน้า public ทันที

หลัง ingest `f2_target_household` ให้ใช้ run directory ที่ `ResponseRecorder` บันทึกสถานะ `complete` แล้ว build แบบ offline:

```powershell
python -m tools.build_apptech_aggregates --run-dir data/runtime/raw/f2_target_household/<run_id>
python -m app.cli publication receipt
python -m app.cli check
```

Builder ตรวจ SHA-256/ขนาดของ response และบังคับให้มีสอง dashboard ครบทุก `dashboard_year_filters` ใน plan ก่อนเขียน `apptech_aggregates.json` กับ provenance manifest ถ้า schema หรือยอดเงินขาดจะหยุด ไม่แทนค่าที่หายด้วยศูนย์ `generated_at` คือเวลาบันทึกหลักฐาน ส่วน `as_of` เป็น null เพราะต้นทางไม่ได้ระบุวันที่อ้างอิงชุดข้อมูล ยอดเศรษฐกิจคงเป็นค่าที่ต้นทางแสดง ไม่คำนวณใหม่หรือกระจายลงจังหวัด

ไฟล์ raw อยู่ใน runtime/evidence เท่านั้น PR เผยแพร่ได้เฉพาะ projection กับ manifest/receipt ตาม contract และต้องผ่าน review ก่อน merge

## F2 local promotion

See the [F2 guide](f2.md) for the complete build, review, staged-validation and refresh workflow, data semantics, and API/UI contract.

Local promotion is a separate owner-authorized action after all staged detail fields are accepted. It does not authorize commit, push, deployment, upstream fetching or image hosting.

`python -m tools.f2_pipeline promote-local` takes the approved `--stage`, reviewed internal `--release`, `--comparison`, `--comparison-review`, explicit `--decision` and a new `--output` directory. The decision must bind the exact stage-manifest SHA-256 and explicitly permit `local_publication_only` with deployment disabled. It is a trusted local workflow record, not a cryptographic identity check or an endpoint for untrusted callers. Repository review and owner authorization remain required; neither field approval nor a publication receipt grants promotion.

The builder rederives the approved stage, verifies its policy/review bindings, and creates a separate activation bundle. `verify-local-promotion` accepts the same inputs with `--bundle` instead of `--output` and independently reproduces every bundle byte. Neither command activates files or writes a receipt.

The bundle contains `data/public/f2/`, `config/publication_contracts/f2_dashboard.json`, `serving-entries.json` and a promotion attestation. Before activation, validate these alongside all existing public files/contracts in a disposable workspace. Then replace the F2 directory and contract, replace only serving entries whose path starts with `f2/`, and regenerate the receipt with `python -m app.cli publication receipt`. Preserve all prior source artifacts and existing non-F2 data. Run `python -m app.cli check` after local activation.

Publication-ready F2 roots use `publication_status=approved_local_publication`, `staged_for_review=false`, `owner_checkpoint_required=false` and `publication_approval_claimed=true`. Historical field/internal approval blocks remain unchanged and non-promotional; a separate `local_promotion` manifest binding records the actual promotion decision. Prices, locations, identities, uncertainty, withheld fields and media references do not change.

The active C02 aggregate-map successor is `f2-dashboard-snapshot-v3-c02-map-accepted-v1`. Its acceptance is bound to the exact immutable pending candidate `f2-dashboard-snapshot-v3-c02-map-review-v1`, separately from the historical person-field and province-membership acceptances. Evidence is under `data/runtime/f2/checkpoints/c02-map-review-v1/` and `c02-map-local-promotion-v1/`. The verified active workspace retains 39 F2 serving entries and the 4,640-person national population, with 4,418 nonadditive province memberships for 4,415 people and 225 people remaining national-only. The map publishes aggregate distinct-person counts over 77 canonical province scopes only; it publishes no person points, coordinates, lower-level geography, residence, or workplace inference. The active F2 manifest SHA-256 is `cb454f3b8afb5665450e09d79a835a767f69b52fb6de1ebeb5859f5fa80fe0d5`; the receipt release digest is `bd51c9c0eff4c73051119d99b255e5d21afee160b74c8004940e59585b775475`. Deployment remains disabled.

Unavailable methodology-only topics may have no source IDs. They are admitted to serving only through an exact database-output contract binding, not invented source provenance. Complete receipt/publication/privacy checks still apply.

## หลัง merge

Railway deploy จาก `main` แล้ว Dashboard startup จึงตรวจ manifest/payload และ sync reviewed artifact เข้า PostgreSQL แบบ idempotent ภายใต้ lock นี่เป็นจุดเดียวที่ routine publication เปลี่ยน production database

Codex/team automation มีหน้าที่ review PR, ใส่ label และตรวจ `/health` กับ database coverage หลัง deploy เท่านั้น ห้าม automation เขียน database, รัน ingestion ด้วย production secret หรือแก้ row โดยตรง หาก health ไม่ผ่านให้หยุด release/rollback deployment และแก้ผ่าน PR ใหม่
