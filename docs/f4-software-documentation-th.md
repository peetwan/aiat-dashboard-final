# คู่มือซอฟต์แวร์ F4 Dashboard

เอกสารนี้อธิบายขอบเขต การทำงาน ข้อมูล แหล่งที่มา และวิธีดูแลส่วน F4 ของ AIAT Dashboard

## 1. วัตถุประสงค์

F4 แสดงหลักฐานด้านพื้นที่จาก 2 กลุ่มข้อมูลในหน้าจอเดียวกัน แต่แยกความหมายออกจากกัน:

1. **เทคโนโลยีและนวัตกรรม** — รายการผลิตภัณฑ์/นวัตกรรม นวัตกรชุมชน TRL, ROI, SROI, ผลลัพธ์ และผลกระทบจากต้นทาง PMUA AppTech
2. **นวัตกรรมเชิงนโยบาย** — โครงการวิจัย สถานะ และงบประมาณจากรายการโครงการ CLIG

ระบบรองรับการดูข้อมูลระดับประเทศ ภาค และจังหวัด รวมถึงการเปิดรายการรายละเอียดที่ใช้เป็นหลักฐานประกอบ KPI

## 2. สิ่งที่ต้องมี

### ขั้นต่ำสำหรับเปิด Dashboard

- Python 3.12 ขึ้นไป
- dependencies จาก `requirements.txt`
- ฐานข้อมูล local ตามค่า `DATABASE_URL` หรือ PostgreSQL สำหรับ production
- ไฟล์ public catalog และไฟล์ serving ที่อยู่ใน repository

### สิ่งที่ต้องมีสำหรับข้อมูล F4

ต้องตั้งค่า read-only access ของ evidence store ที่ `.env` ที่ root ของ repo:

```text
AIAT_S3_ENDPOINT=https://<account>.r2.cloudflarestorage.com
AIAT_S3_BUCKET=<bucket>
AIAT_S3_ACCESS_KEY_ID=<read-only-key>
AIAT_S3_SECRET_ACCESS_KEY=<read-only-secret>
```

ห้าม commit `.env`, token หรือ secret ลง Git และไม่ควรใช้ key แบบเขียนได้สำหรับการรัน Dashboard

## 3. ภาพรวมการทำงาน

```text
R2 evidence store
        │
        ├── PMUA product catalogue + product details
        └── CLIG manifest + project list
        │
        ▼
app/f4_data.py
  โหลด snapshot, รวม KPI, กรองจังหวัด/ภาค,
  จัดรูป ROI/SROI, outcomes/impacts และสร้าง evidence notes
        │
        ▼
app/main.py  ── Public F4 API
        │
        ▼
app/static/app.js + app/templates/index.html
  แผนที่ → ประเทศ → ภาค → จังหวัด → รายการรายละเอียด
```

หลักการสำคัญคือ Dashboard อ่าน reviewed evidence จาก R2 ไม่ดึงเว็บไซต์ต้นทางโดยตรงตอนผู้ใช้เปิดหน้าเว็บ

## 4. หน้าจอ F4

### ภาพรวม

- แผนที่แสดงจังหวัดที่มีข้อมูลจากอย่างน้อยหนึ่งกลุ่ม
- ส่วน **เทคโนโลยีและนวัตกรรม** แสดงจำนวนรายการ นวัตกร และข้อมูลเศรษฐกิจถ้ามี
- ผลกระทบเศรษฐกิจรวมระดับประเทศแสดงยอดรวมเป็น 3 KPI และใช้ตารางสำหรับเปรียบเทียบรายปี โดยไม่ตีความเป็น before-after รายพื้นที่
- ส่วน **นวัตกรรมเชิงนโยบาย** แสดงจำนวนโครงการ สถานะโครงการ และงบประมาณรวม
- รายการพื้นที่แยกจาก KPI เพื่อไม่ให้จำนวนจังหวัดถูกปนกับจำนวนโครงการ/นวัตกรรม

### เทคโนโลยีและนวัตกรรม

แสดงรายการที่ค้นหาได้ โดยแต่ละรายการอาจมี:

- ชื่อผลิตภัณฑ์และรหัสผลิตภัณฑ์
- จังหวัด อำเภอ และตำบล
- ระดับความพร้อม TRL
- ROI (Economic) และ SROI (Social) ตามข้อความต้นทาง
- ผลลัพธ์ (Outcomes)
- ผลกระทบ (Impacts)
- สถานะหลักฐาน `complete`, `partial` หรือ `not_reported`
- ข้อความ `ยังไม่ระบุข้อมูลจากต้นทาง` เมื่อหมวดนั้นไม่มีข้อมูลที่ใช้ได้
- ลิงก์กลับไปยังหน้าต้นทาง

### นวัตกรรมเชิงนโยบาย

แสดงรายการโครงการที่ค้นหาได้ โดยแต่ละรายการอาจมี:

- ชื่อโครงการ
- ปีงบประมาณและสถานะ
- หน่วยงานหลัก
- เลขสัญญา
- งบประมาณถ้ามี
- ลิงก์รายละเอียดโครงการ

## 5. โครงสร้างไฟล์ที่เกี่ยวข้อง

| ไฟล์ | หน้าที่ |
|---|---|
| `app/f4_data.py` | โหลด evidence, สร้าง KPI, กรองประเทศ/ภาค/จังหวัด และจัดรูปข้อมูลรายการ |
| `app/main.py` | ประกาศ API ของ F4 และแปลงข้อผิดพลาดของ evidence เป็น HTTP 503 |
| `app/templates/index.html` | โครงสร้าง HTML ของแผง F4 และแท็บต่าง ๆ |
| `app/static/app.js` | เรียก API, วาด KPI/แผนที่/รายการ และควบคุมการเปลี่ยนระดับพื้นที่ |
| `app/static/departments.css` | รูปแบบการแสดงผลของ F4 |
| `app/connectors/pmua_product_details.py` | connector และ parser กลางสำหรับหน้า PMUA product detail |
| `config/connector_contracts/f4_pmua_product_details.json` | สัญญา grain, identity, completeness และ privacy ของ connector |
| `tools/scrape_pmua_product_details.py` | wrapper สำหรับ review/publish ข้อมูล TRL, ROI/SROI, Outcomes และ Impacts |
| `tools/evidence_store.py` | อ่าน configuration และเชื่อมต่อ S3-compatible evidence store |

## 6. แหล่งข้อมูลและความหมาย

| กลุ่ม | ข้อมูล | ตำแหน่ง evidence ปัจจุบัน | ความหมาย |
|---|---|---|---|
| เทคโนโลยีและนวัตกรรม | รายการผลิตภัณฑ์ | `raw/f2/f2_target_household/20260818T163603Z/products_redacted.jsonl.gz` | หนึ่งแถวต่อหนึ่งผลิตภัณฑ์ที่ผ่านการทำข้อมูลให้ปลอดภัย |
| เทคโนโลยีและนวัตกรรม | หน้า headline เดิม | `raw/f2/f2_target_household/20260820T134640Z/public_pages/propose.html` | หลักฐานตัวเลข headline จากหน้าเว็บ ไม่ใช่รายการรายละเอียด |
| เทคโนโลยีและนวัตกรรม | รายละเอียดผลิตภัณฑ์ | `raw/f4/f4_pmua_product_details/20260905T112853Z/product_details.jsonl.gz` | 1,160 product detail พร้อม TRL, ROI/SROI แบบข้อความ, Outcomes, Impacts และ evidence status |
| นวัตกรรมเชิงนโยบาย | manifest | `raw/f4/clig_projects/20260823T072251Z/manifest.json` | จำนวนแถวและ metadata ของชุดโครงการ |
| นวัตกรรมเชิงนโยบาย | รายการโครงการ | `raw/f4/clig_projects/20260823T072251Z/projects.jsonl.gz` | หนึ่งแถวต่อหนึ่งโครงการวิจัย |
| นวัตกร/เศรษฐกิจ | aggregate ที่ผ่านการ review | `data/public/apptech_aggregates.json` | ตัวเลข aggregate ระดับจังหวัด/ประเทศตามที่ contract อนุญาต |

## 7. Public API

ทุก endpoint อยู่ใต้ `/api/public/v1` และคืน HTTP 503 เมื่อ evidence ของ F4 ใช้งานไม่ได้

| Method | Endpoint | หน้าที่ |
|---|---|---|
| GET | `/f4/overview` | ภาพรวมประเทศ, source sections, KPI และจังหวัดที่ครอบคลุม |
| GET | `/f4/innovations` | รายการเทคโนโลยีและนวัตกรรมระดับประเทศ |
| GET | `/f4/policy-projects` | รายการโครงการนวัตกรรมเชิงนโยบายระดับประเทศ |
| GET | `/f4/regions/{region_name}` | สรุปของภาคที่เลือก |
| GET | `/f4/regions/{region_name}/innovations` | รายการนวัตกรรมของภาค |
| GET | `/f4/regions/{region_name}/policy-projects` | รายการโครงการของภาค |
| GET | `/f4/provinces/{province_code}` | สรุปของจังหวัดที่เลือก |
| GET | `/f4/provinces/{province_code}/innovations` | รายการนวัตกรรมของจังหวัด |
| GET | `/f4/provinces/{province_code}/policy-projects` | รายการโครงการของจังหวัด |

### ฟิลด์สำคัญของ overview

- `schema_version`: เวอร์ชัน payload เช่น `f4-dashboard-v2`
- `source_sections`: กลุ่มข้อมูลและ KPI ของแต่ละกลุ่ม
- `covered_province_codes`: union ของจังหวัดจากทั้งสองกลุ่ม
- `coverage_province_codes_by_source`: แยกจังหวัดตามกลุ่มข้อมูล
- `economic_impact_rows`: ยอดรวมระดับประเทศและแถวเปรียบเทียบรายปี
- `evidence_notes`: ข้อควรอ่านและข้อจำกัดของหลักฐาน
- `source_keys`: ตำแหน่ง evidence ที่ใช้สร้าง payload

## 8. กฎการกรองพื้นที่และข้อจำกัด

- รายการเทคโนโลยีและนวัตกรรมกรองจังหวัดจาก province code ที่มีอยู่ในรายการผลิตภัณฑ์
- รายการนวัตกรรมเชิงนโยบายไม่มี province field ที่เป็นมาตรฐาน จึงจับคู่ชื่อจังหวัดจากชื่อโครงการ รายละเอียด บทคัดย่อ และหน่วยงาน
- การจับคู่ CLIG เป็น **evidence-matched** ไม่ใช่การยืนยันว่าครอบคลุมทุกโครงการ
- `null` หรือไม่ระบุ ไม่ควรแปลเป็นศูนย์
- ผลกระทบเศรษฐกิจจาก AppTech เป็น aggregate ระดับประเทศ/ปี และยังไม่ควรนำไปแจกแจงเป็นรายจังหวัดหรือรายภาค
- ROI และ SROI เก็บข้อความตามต้นทาง เพราะรูปแบบและหน่วยไม่สม่ำเสมอระหว่างผลิตภัณฑ์
- ค่า blank และ `-` ถือว่าไม่รายงาน ส่วน `0` ถือเป็น placeholder เฉพาะกรณีที่ไม่มี indicator คู่กัน
- Outcomes และ Impacts คือข้อมูลที่ต้นทางรายงาน ไม่ใช่ผลการคำนวณ before-after ของระบบนี้
- ข้อมูลในรายการรายละเอียดเป็น evidence drilldown ไม่ใช่ KPI รับรองใหม่โดยอัตโนมัติ

## 9. การดึงรายละเอียด PMUA

connector `f4_pmua_product_details` อ่าน pagination จากหน้า `/search` แล้วเปิดเฉพาะ `/product/show/{numeric_product_id}` ทีละรายการ หากหน้ารายละเอียดใดล้มเหลวหลัง retry 3 ครั้ง ระบบจะล้มทั้ง refresh และไม่ publish snapshot ที่ไม่ครบ parser กลางเก็บ ROI/SROI เป็นข้อความและกรอง Outcomes/Impacts เฉพาะแถวที่ว่างทั้ง label และ value

สคริปต์ `tools/scrape_pmua_product_details.py` ใช้ parser เดียวกันสำหรับ review และ publish ในเครื่อง โดยจะปฏิเสธการ publish หากพบ `fetch_error`

ทดลองจำนวนน้อยก่อน:

```bash
python tools/scrape_pmua_product_details.py \
  --from-r2-products \
  --limit 10 \
  --output-root data/raw/f4/pmua_product_details
```

เมื่อ review ผลลัพธ์แล้วจึงรันชุดเต็ม:

```bash
python tools/scrape_pmua_product_details.py \
  --from-r2-products \
  --output-root data/raw/f4/pmua_product_details
```

การ push ขึ้น R2 ต้องทำหลังตรวจ row count, `fetch_error`, `empirical_evidence`, `evidence_status`, `outcomes`, `impacts` และ manifest แล้วเท่านั้น จึงค่อยเพิ่ม `--push`

## 10. การติดตั้งและรัน local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.cli init-db
python -m app.server
```

เปิดใช้งานที่:

- Dashboard: `http://localhost:8000/?mode=f4`
- API documentation: `http://localhost:8000/docs`
- F4 overview API: `http://localhost:8000/api/public/v1/f4/overview`

## 11. การตรวจสอบก่อน merge

ขั้นต่ำที่ควรตรวจเมื่อแก้ F4:

1. `git diff --check`
2. เปิดหน้า F4 ระดับประเทศ ภาค และจังหวัด
3. ตรวจว่า Overview แยก 2 กลุ่มข้อมูลและตัวเลขไม่ปนกัน
4. ตรวจ API overview และ endpoint รายการทั้งสองประเภท
5. เปิดผลิตภัณฑ์ตัวอย่างที่เป็น `complete`, `partial` และ `not_reported` เพื่อตรวจ ROI/SROI, Outcomes และ Impacts
6. ตรวจผลกระทบเศรษฐกิจว่ามี KPI รวม 3 ค่าและตารางรายปี โดยไม่แสดงแถวรวมซ้ำในตาราง
7. ตรวจกรณี R2 ใช้งานไม่ได้ว่าหน้าแสดงข้อความผิดพลาดและปุ่มลองใหม่
8. ตรวจว่าข้อมูลลับไม่ถูกส่งเข้า HTML, JSON response หรือ commit

## 12. การแก้ปัญหาเบื้องต้น

| อาการ | ตรวจอะไร |
|---|---|
| `โหลดข้อมูลพื้นที่นี้ไม่สำเร็จ` | `.env`, R2 endpoint, bucket, read key และ object path |
| Overview โหลดได้แต่รายการว่าง | ตรวจ `products_redacted.jsonl.gz`, `projects.jsonl.gz` และ schema ของ row |
| จังหวัด CLIG น้อยกว่าที่คาด | ตรวจข้อความจังหวัดใน title/detail/abstract/organization และอ่าน `evidence_notes` |
| ROI/SROI หรือ Outcomes/Impacts ไม่มี | ตรวจ product detail snapshot, `empirical_evidence`, `evidence_status`, `outcome_known_rows`, `impact_known_rows` และ `fetch_error` |
| ตัวเลขเก่าค้างในหน้าเว็บ | refresh หน้าเว็บและตรวจ cache-bust version ของ `app.js`/CSS |

## 13. สิ่งที่ยังไม่ควรทำ

- อย่าให้หน้าเว็บเรียก PMUA หรือ CLIG โดยตรงทุกครั้งที่เปิดหน้า
- อย่าใช้ Candidate data แทน reviewed public evidence
- อย่าเปลี่ยน `null` เป็น `0` เพื่อให้ KPI ดูครบ
- อย่าแปลง ROI/SROI ที่มีรูปแบบไม่สม่ำเสมอเป็นตัวเลขรวมข้ามผลิตภัณฑ์
- อย่าเรียก ROI/SROI หรือ Outcomes/Impacts ว่าเป็นผลกระทบที่ระบบคำนวณเอง
- อย่า commit credential หรือไฟล์ `.env`
