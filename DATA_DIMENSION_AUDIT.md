# Audit การจัดกลุ่มข้อมูลรายมิติ

อัปเดต: 2026-08-16

## ผล audit

- Registry ครบ 28 source; public candidate 11, metadata-only 12, restricted local-only 5
- ข้อมูลระดับจังหวัดใช้ exact code/name หรือ official crosswalk เท่านั้น
- Learning Dashboard เชื่อม 66 จังหวัดและแยกตาราง entity/category/region/impact ที่ไม่ใช่ province ออกจากกัน
- Area-Based มี 1,002 records: 996 เชื่อม 55 จังหวัด และ 6 แถวอยู่ใน unmapped section โดยไม่เดาพื้นที่
- PPPConnext ใช้ curated aggregate 660 แถว; generic BI chart points ไม่ถูกเทลง UI
- City Capital คง grain 18 เทศบาล/39 metrics และเชื่อม 16 จังหวัดด้วยทะเบียน DLA
- RMUTDB เป็น national/non-geo catalog เพราะ affiliation ไม่ใช่พื้นที่ใช้งาน
- SRA-DSS มี overall ตัวเลข 15 จาก 20 จังหวัดในทะเบียน; 5 จังหวัดที่เป็น null ไม่ถูกแทนด้วยศูนย์
- Housing public projection มี 7,259 แถว; อีก 306 แถวที่ไม่มีจังหวัดต้องอยู่ non-geo/unmapped ไม่ถูกทิ้งหรือเดา
- Wallet/household/health และ ArcGIS sensitive lanes ไม่มี values บน Railway

## มิติที่ผู้บริหารเห็นทันที

| มิติ | ตัวอย่างข้อมูล | หลักอ่าน |
|---|---|---|
| ที่อยู่อาศัยและกำลังซื้อ | ราคาบ้านต่อรายได้, การผ่านสินเชื่อ, ความแออัด | เทียบ metric เดียวกันและคงหน่วยต้นทาง |
| ความเสี่ยงและความเปราะบาง | น้ำท่วม, SRA-DSS | แสดง definition status; ไม่ตีความทิศทางแทนต้นทาง |
| ครัวเรือนและทุนดำรงชีพ | PPPConnext aggregate | ไม่รวม metric ต่างหน่วยเป็นคะแนนเดียว |
| เศรษฐกิจชุมชน | Learning Dashboard, Area-Based | ระบุชัดว่าเป็น selected-project/participant scope |
| โครงการและนวัตกรรม | AppTech/Area-Based และความต้องการพื้นที่ | แยกรายการผลงาน ความต้องการ และ platform activity |
| บริการเมือง | City Capital 39 metrics | คงระดับเทศบาล; benchmark เฉพาะ 18 เมืองใน snapshot |
| วัฒนธรรมและท่องเที่ยว | Cultural Map, Ruam Thiao | จุดมีพิกัดอยู่บน map; non-point/tourism อยู่ในข้อมูลพื้นที่/insights |

## UX contract

- หน้าแรกให้แผนที่เด่นและบอกเพียงวิธีคลิกจังหวัด
- เมื่อเลือกจังหวัด แสดง context metrics และข้อสังเกตก่อน technical coverage
- รายมิติแสดงทุกกลุ่มที่มีข้อมูลโดยไม่ใช้ dropdown ซ้อน
- รายการยาวโหลดเมื่อเปิด “ข้อมูลพื้นที่”
- non-geo, unmapped และสถานะ 28 URL อยู่หน้า `/insights`
- ไม่มี composite score, budget ranking, ลูกศรเชิงตัดสิน หรือ raw spreadsheet table
- ค่า `null` คือไม่มีข้อมูล ไม่ใช่ศูนย์
