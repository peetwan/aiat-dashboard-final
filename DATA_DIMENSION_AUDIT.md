# Audit การจัดกลุ่มข้อมูลรายมิติ

อัปเดต: 2026-08-16

## ข้อค้นพบ

- Public catalog มี 10 source; 5 source ใช้ API-first และ 5 source ใช้ snapshot ที่มี provenance
- 6 source เชื่อมเข้าระดับจังหวัดได้: SRA-DSS, Cultural Map, AppTech MRU, Area-Based, Ruam Thiao และ Thai Housing Portal
- 4 source ยังไม่มี province key ที่ยืนยันแล้ว จึงอยู่ใน source inventory เท่านั้น: PPPConnext, RMUTDB, AppTech MTR และ City Capital Open Data
- Wallet 2 source เป็น restricted local-only และไม่อยู่ใน public artifact หรือ API
- ปัญหา UI เดิมเกิดจากการส่ง Housing resource หลายร้อยแถวต่อจังหวัดให้ browser แสดงเป็น dropdown แทนการสรุปใน data pipeline

## มิติที่ใช้ใน Serving layer

| มิติ | ข้อมูลที่รวม | การย่อยข้อมูล |
|---|---|---|
| ที่อยู่อาศัยและกำลังซื้อ | ราคาบ้านต่อรายได้, การผ่านสินเชื่อ, ที่อยู่อาศัยแออัด, แนวโน้มประชากร | เลือกค่าระดับจังหวัด, เปรียบเทียบกับ median ของจังหวัดที่มี metric เดียวกัน, เก็บ time series ล่าสุด |
| ความเสี่ยงและความเปราะบาง | พื้นที่เสี่ยงน้ำท่วมระดับ 4–5, คะแนน 5 มิติจาก SRA-DSS | รวมระดับความเสี่ยง 4 และ 5 ตาม derivation เดิม; คะแนน SRA คงสถานะ provisional และไม่ตีความทิศทางแทนต้นทาง |
| โครงการและนวัตกรรม | Area-Based projects, AppTech MRU, Ruam Thiao เฉพาะลำพูน | จัดกลุ่มปีงบประมาณ พื้นที่ดำเนินงาน หมวดนวัตกรรม และเลือกชื่อรายการล่าสุดสำหรับอ่านต่อ |
| ทุนวัฒนธรรม | Cultural Map records | จัดกลุ่มหมวด อำเภอ และชนิดทุนวัฒนธรรม; แสดงข้อความประกอบสถานะจากต้นทางโดยไม่ตีความรหัสความเสี่ยงเอง |

## Join contract

- ใช้รหัสจังหวัดเป็นหลักเมื่อ source มีรหัสยืนยันแล้ว
- ชื่อจังหวัดใช้ผ่าน crosswalk 77 จังหวัดที่ materialize ใน pipeline เท่านั้น ไม่ join ด้วยชื่อแบบ ad hoc ในหน้าเว็บ
- Source ระดับเทศบาลหรือไม่มี geography key จะไม่ถูกบังคับเข้าจังหวัด
- สถานะไม่มี record ไม่ถูกแทนด้วยศูนย์

## Serving pipeline ใหม่

~~~text
source-shaped provincial briefing
            |
            v
metric selection + province join audit
            |
            v
same-metric provincial median
            |
            v
clean dimension summaries + distributions + highlights
            |
            v
/api/public/v1/provinces/{code}/summary
~~~

`tools/build_executive_summaries.py` สร้างไฟล์ compact แยก 77 จังหวัดไว้ใน
`data/public/executive_summaries/` หน้าเว็บโหลด summary นี้ก่อน ส่วน briefing ฉบับเต็มจะโหลดเมื่อผู้ใช้เปิดแท็บโครงการเท่านั้น

## ขอบเขตการตีความ

- comparison ใช้ค่ากลางของจังหวัดที่มีข้อมูลใน metric เดียวกัน ไม่ใช่เกณฑ์นโยบาย
- ค่าใกล้ median หมายถึงต่างไม่เกิน 10% ตามกติกาของ serving view
- ไม่มี composite score, budget score หรือ ranking จังหวัดที่สร้างขึ้นใหม่
- ทุก metric ยังคง source URL และสถานะ candidate/needs_review
