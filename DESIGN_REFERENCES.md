# Design references — Public Evidence Atlas

หน้าเว็บนี้ออกแบบเป็น **public decision-support dashboard** สำหรับผู้บริหารและประชาชน ไม่ใช่หน้า monitoring ของทีม data ภายใน และไม่ได้คัดลอกหน้าจอใดหน้าจอหนึ่ง

## Mobbin MCP

- [Deel — Global Hiring Guide](https://mobbin.com/screens/a6cb49ca-18e2-49d4-9a58-da555b0c4855): แนวคิด map-first hero และการเปิดรายละเอียดตามพื้นที่
- [Profound — Answer Engine Insights](https://mobbin.com/screens/98b82305-3239-4d52-b0c9-0e7f701dc127): การเชื่อมแผนที่กับตารางเปรียบเทียบใน workspace เดียว
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

1. WebGL 3D province map เป็น entry point หลัก และมี table เป็นทางเลือกที่เข้าถึงง่ายกว่า
2. ผู้ใช้สลับดูแต่ละ signal แยกกัน ได้แก่ coverage, SRA, innovation, housing และ culture
3. ไม่มีการรวม signal เป็น “คะแนนความต้องการงบ” เพราะยังไม่มีสูตรที่เจ้าของนโยบายรับรอง
4. Budget Lab คำนวณจากงบ จังหวัด และน้ำหนักที่ผู้ใช้เลือกเท่านั้น ผลลัพธ์ติดป้ายว่าเป็น scenario ไม่ใช่ข้อเสนออย่างเป็นทางการ
5. ทุกหน้ามี provenance, quality status และ download/API เพื่อให้ประชาชนตรวจข้อมูลต้นทางได้
6. โทน dark atlas ใช้เฉพาะ hero/map ส่วน workspace วิเคราะห์ใช้พื้นสว่างเพื่อให้อ่านตารางและตัวเลขได้นาน
