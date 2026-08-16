# Design references — Public Evidence Atlas

หน้าเว็บนี้ออกแบบเป็น **public provincial decision-support map** สำหรับผู้บริหารและประชาชน ไม่ใช่หน้า monitoring ของทีม data ภายใน และไม่ได้คัดลอกหน้าจอใดหน้าจอหนึ่ง

## Mobbin MCP

- [Squarespace — Geography analytics](https://mobbin.com/screens/be6a849b-1fde-42ca-a6f2-f69ffcf4439c): choropleth ที่ใช้ legend สั้นและไม่แสดงชื่อพื้นที่ทุกจุดพร้อมกัน
- [Cloudflare — Account analytics](https://mobbin.com/screens/254f6c74-2e18-4638-ad6f-ff8dc6c5c297): map + ranked evidence และ filter hierarchy ที่แยกข้อมูลหลักจากรายละเอียด
- [Navattic — Analytics](https://mobbin.com/screens/a5be5a57-9c24-49a2-9ce5-ccd5edc17a1b): KPI card ที่มีกราฟย่อและเปรียบเทียบภายใน metric เดียวกัน
- [Hotjar — Custom dashboard](https://mobbin.com/screens/f43a5082-26d2-40d3-ba2a-6c4bee3958b5): tab/filter hierarchy และ progressive disclosure สำหรับ dashboard ที่มีข้อมูลมาก
- [Deel — Global Hiring Guide](https://mobbin.com/screens/a6cb49ca-18e2-49d4-9a58-da555b0c4855): แนวคิด map-first hero และการเปิดรายละเอียดตามพื้นที่
- [Profound — Answer Engine Insights](https://mobbin.com/screens/98b82305-3239-4d52-b0c9-0e7f701dc127): การเปิดรายละเอียดจากพื้นที่โดยไม่พาผู้ใช้ออกจาก context ของแผนที่
- [Felt — Operational Map](https://mobbin.com/screens/e3ac649f-a644-4545-a798-9d50366385db): layer control และข้อมูลเชิงพื้นที่ที่เปิดดูได้โดยไม่ทำให้หน้าหนักเกินไป
- [Rocket Money — Budget](https://mobbin.com/screens/e8e471f9-dc5d-47a7-8d02-8b62c096149b): รูปแบบตัวเลขงบ แถวจัดสรร และยอดรวมที่อ่านง่าย
- [Origin — Spending](https://mobbin.com/screens/d74b56f7-a4f0-43c9-b708-6615de691c5c): แนวคิด money-flow; รอบนี้ยังไม่ใช้ Sankey เพราะ dataset ไม่มีเส้นทางเงินที่ยืนยันแล้ว

## Public policy dashboards

- [UNDP GeoHub](https://geohub.data.undp.org/): แผนที่เป็นเครื่องมือสำรวจหลักและมี metadata ประกอบ
- [UNDP SDG Push Diagnostic](https://sdgdiagnostics.data.undp.org/): แยก evidence, policy choice และ scenario ออกจากกัน
- [USAspending Agency Profiles](https://www.usaspending.gov/agency): drill-down จากภาพรวมไปยังหน่วยงานและแหล่งข้อมูล
- [Seattle Budget Dashboard](https://www.seattle.gov/council/topics/budget-dashboard): public budget communication ที่อธิบายบริบทก่อนตัวเลข
- [Open Treasury](https://www.opentreasury.org/): budget simulation ที่ใช้ภาษาคนทั่วไป

## Existing PMUA mock

ตรวจ [PMUA Data Command Center Mockup](https://pmua-dashboard-mock.poomzi.com/) เพื่อเข้าใจหัวข้อเดิม เช่น source coverage, พื้นที่ และงบประมาณ แต่ไม่ได้นำค่าตัวอย่าง สี หรือ visual hierarchy เดิมมาใช้

## Design decisions ที่นำมาใช้จริง

1. WebGL 3D province map กินพื้นที่เต็ม viewport และเป็น interaction หลักเพียงอย่างเดียว
2. หน้าเริ่มต้นมีคำสั่งสั้น ช่องเลือกจังหวัด และ legend ความครอบคลุม; default แสดงชื่อเฉพาะจังหวัดที่เชื่อมหลักฐานได้ 4–5 แหล่ง แล้วค่อยเพิ่มชื่อเมื่อ zoom
3. คลิกจังหวัดแล้วเปิด command panel ด้านข้างบน desktop และ bottom sheet บน mobile
4. Panel เรียก `/api/public/v1/provinces/{code}/briefing` และแสดงค่าจริงแทน record counts
5. Panel แบ่งเป็น 4 tabs: ภาพรวม → โครงการและพื้นที่ → ข้อมูลรายมิติ → แหล่งข้อมูล เพื่อไม่ให้เป็นหน้า scroll ยาวต่อกัน
6. แหล่งข้อมูลครบ 10 URL แยก API-first กับ snapshot พร้อม availability, URL และ quality status
7. สีและความสูงบนแผนที่ใช้ `evidence_source_count` เท่านั้น เพื่อสื่อ “ความครอบคลุมหลักฐาน” ไม่ใช้จำนวน record เป็น KPI และมี legend อธิบายตรงหน้า
8. ข้อมูล CKAN ถูก clean และสรุปใน serving pipeline ก่อนถึง browser; หน้ารายมิติแสดง comparison และ distribution ทันทีโดยไม่มี dropdown หรือ raw cell
9. ใช้ Anuphan เป็นฟอนต์หลัก พร้อมขนาดตัวอักษรและ touch target ที่อ่านง่ายทั้ง desktop/mobile
10. ลดข้อความกำกับ ไอคอนลูกศร และตัวเลขลำดับที่ไม่ช่วยการตัดสินใจ; ใช้ contrast และ spacing แยกลำดับข้อมูลแทน
