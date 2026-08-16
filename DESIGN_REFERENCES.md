# Design references — Public Evidence Atlas

หน้าเว็บนี้ออกแบบเป็น **public provincial decision-support map** สำหรับผู้บริหารและประชาชน ไม่ใช่หน้า monitoring ของทีม data ภายใน และไม่ได้คัดลอกหน้าจอใดหน้าจอหนึ่ง

## Mobbin MCP

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
2. หน้าเริ่มต้นมีคำสั่งสั้นหนึ่งจุด ป้ายชื่อจังหวัด และช่องเลือกจังหวัด ไม่มี hero copy หรือตารางยาว
3. คลิกจังหวัดแล้วเปิด command panel ด้านข้างบน desktop และ bottom sheet บน mobile
4. Panel เรียก `/api/public/v1/provinces/{code}/briefing` และแสดงค่าจริงแทน record counts
5. ลำดับข้อมูลเป็น executive signals → รายการโครงการ/นวัตกรรม/วัฒนธรรม → resource อื่นทั้งหมด
6. แหล่งข้อมูลครบ 10 URL แยก API-first กับ snapshot พร้อม availability, URL และ quality status
7. แผนที่ใช้ความสูงคงที่ ไม่บิดความหมายด้วยจำนวน record; โทน dark atlas คงแผนที่ให้เด่น ส่วน panel ใช้พื้นสว่างเพื่ออ่านข้อมูลเร็ว
