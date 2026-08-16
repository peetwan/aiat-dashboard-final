# Audit การจัดกลุ่มข้อมูลรายมิติ

อัปเดต: 2026-08-16

## ผลล่าสุด

- Public catalog มี 10 source; 9 source เชื่อมพื้นที่ได้ด้วย key ที่ตรวจแล้ว
- PPPConnext เชื่อมได้ 21 จังหวัดจาก curated BI aggregate 660 แถว
- AppTech MTR มี API aggregate ครบ 77 จังหวัด แต่แยกผู้ใช้ การปฏิสัมพันธ์ และผลงานออกจากกัน
- City Capital เชื่อมเทศบาล 18/18 แห่งกับ 16 จังหวัดด้วยทะเบียน DLA
- RMUTDB ไม่ผูกจังหวัด เพราะเจ้าของผลงานไม่ใช่สถานที่ใช้งานนวัตกรรม
- Wallet 2 source เป็น restricted local-only และไม่อยู่ใน public artifact หรือ API

## มิติใน Serving layer

| มิติ | ข้อมูล | วิธีอ่าน |
|---|---|---|
| ที่อยู่อาศัยและกำลังซื้อ | ราคาบ้านต่อรายได้, การผ่านสินเชื่อ, ความแออัด, ประชากร | เทียบ median ของจังหวัดที่มี metric เดียวกัน |
| ความเสี่ยงและความเปราะบาง | น้ำท่วม, SRA-DSS 5 มิติ | คงคะแนน provisional และไม่ตีความทิศทางแทนต้นทาง |
| ครัวเรือนและทุนดำรงชีพ | PPPConnext aggregate | แสดงค่าแยก metric และ widget; ไม่รวมต่างหน่วย |
| โครงการและนวัตกรรม | Area-Based, AppTech MRU, AppTech MTR, Ruam Thiao | แยกรายการผลงานออกจาก aggregate ผู้ใช้/กิจกรรม |
| บริการเมืองและคุณภาพชีวิต | City Capital 39 metric | คงระดับเทศบาล; เทียบ median ของ 18 เมืองใน snapshot |
| ทุนวัฒนธรรม | Cultural Map | จัดกลุ่มหมวด อำเภอ และชนิดทุนวัฒนธรรม |

## Join contract

- ใช้รหัสจังหวัดจากต้นทางเมื่อมี
- ชื่อจังหวัดผ่าน crosswalk 77 จังหวัดใน pipeline เท่านั้น
- เทศบาลใช้ exact `ประเภท + ชื่อ` กับทะเบียน DLA
- สถานะไม่มี record ไม่ถูกแทนด้วยศูนย์
- ค่า aggregate ระดับเมืองไม่ถูกยกเป็น KPI จังหวัด

## Pipeline

~~~text
public API / immutable raw snapshot
  clean schema + keep source grain
  audited geography crosswalk
  same-metric median where valid
  source insights + provincial briefing
  compact executive summary + public API
~~~

## ขอบเขต

- ไม่มี composite score, budget score หรือ ranking จังหวัดที่สร้างขึ้นใหม่
- `near median` ใช้ส่วนต่างไม่เกิน 10% เฉพาะ metric เดียวกัน
- ทุก metric คง source URL, provenance และสถานะ candidate/needs_review
- `as_of` ที่ต้นทางไม่ระบุจะแสดงว่าไม่ระบุ
