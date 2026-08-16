# Product and interface design

AIAT Provincial Evidence Map เป็น public decision-support interface ไม่ใช่ monitoring console ของทีม data เป้าหมายคือให้ผู้บริหารและประชาชนเริ่มจากพื้นที่ เห็นบริบทของตัวเลข และย้อนกลับไปยังแหล่งข้อมูลได้โดยไม่ต้องอ่าน raw tables

## Design principles

1. **Map first** — แผนที่ประเทศไทยแบบ 2D flat choropleth เป็น interaction หลัก
2. **Evidence before judgment** — สีแสดงความครอบคลุมหลักฐาน ไม่ใช่ performance score
3. **Progressive disclosure** — แสดง summary ก่อน แล้วโหลดรายละเอียดเมื่อผู้ใช้เลือกจังหวัด
4. **Preserve meaning** — ไม่รวม metric ต่างหน่วย ไม่แทน `null` ด้วยศูนย์ และไม่สร้าง budget ranking
5. **Honest geography** — ข้อมูลที่ผูกจังหวัดไม่ได้อยู่ non-geo/unmapped
6. **Public-safe by design** — Browser ได้เฉพาะ cleaned projection; ไม่มี raw/restricted payload

## Current interaction model

- Default view แสดงแผนที่ 77 จังหวัด, legend และตัวเลือกจังหวัด
- Desktop ใช้ side panel; mobile ใช้ bottom sheet
- Province panel โหลด `/summary` ก่อนและโหลด `/briefing` สำหรับรายละเอียด/provenance
- เนื้อหาแบ่งเป็น 5 แท็บตามงานตัดสินใจ:
  - **ภาพรวม** — 3 ตัวเลขจังหวัดขนาดใหญ่, flow แบบเส้นจากโครงการถึงการติดตามผล, กราฟ TRL/ทะเบียนผลงาน, อำเภอ และทุนที่ผูกกับนวัตกรรม; source coverage อยู่ในแท็บคุณภาพข้อมูลเท่านั้น
  - **โครงการและงบ** — provisional project groups, participant records, innovation, research/IP/ROI/SROI และ funding caveat
  - **คนและพื้นที่** — SRA/PPPConnext target groups และ area context
  - **มิติการพัฒนา** — context/need, input, activity, output, outcome labels
  - **คุณภาพข้อมูล** — grain, status, `as_of`, `fetched_at`, record count และ source URL
- หน้า `/insights` รองรับ cross-province, national/non-geo, unmapped และ coverage 28 sources
- หน้า `/province/{code}` เป็น progressive full-detail view 6 section: executive, research/funding, people/place, dimensions, provenance และ data operations
- ชื่อจังหวัดและสีปรับตาม evidence coverage เพื่อไม่ให้แผนที่รก
- ใช้ฟอนต์ Anuphan, contrast และ touch targets ที่รองรับ desktop/mobile

## Visual encoding contract

- แผนที่มี lens สำหรับ project groups, SRA, innovation และ evidence coverage; project lens ใช้ provisional project-group count ไม่ใช้ participant rows
- SRA region lens นับจังหวัดใน target registry ทั้ง 20 จังหวัด ส่วน province color ใช้คะแนนเฉพาะ 15 จังหวัดที่มีค่า
- จำนวน records ไม่ถูกใช้เป็นค่าความสูง สี performance หรือ proxy ของความต้องการงบ
- Metric card เปรียบเทียบภายใน metric/grain ที่เข้ากันได้เท่านั้น
- รายการวัฒนธรรม ท่องเที่ยว และโครงการโหลดเมื่อเปิดรายละเอียดพื้นที่
- Quality status, unit, `as_of` และ caveat ต้องอยู่ใกล้ค่าที่แสดง
- ไม่แสดง `0` เมื่อสถานะคือ not-found/unknown; แสดง `—` และเหตุผลแทน
- Funding ของ innovation ที่เชื่อมหลายจังหวัดต้องมีคำเตือนและห้ามใช้เป็น provincial allocation

## Executive readability and responsive contract

Province panel ออกแบบสำหรับการอ่านแบบผู้บริหาร: เห็นภาพรวมในไม่กี่วินาที แล้วค่อยเปิดรายละเอียดหรือ provenance เมื่อจำเป็น โดยทุกแท็บใช้ลำดับ **summary → visualization → supporting evidence**

- Desktop panel กว้าง `700px`; แท็บทั้ง 5 ช่องกว้างเท่ากันและอยู่ในแถวเดียว
- Mobile แสดงแท็บครบใน grid 2 แถวโดยไม่ต้องเลื่อนแนวนอน; panel ต้องเริ่มใต้ header และไม่ทำให้หน้าเกิด horizontal overflow
- ขนาดข้อความพื้นฐานใน panel คือ `15px`; หัวข้อ section คือ `18px` บน desktop และ `17px` บน mobile ส่วนข้อความในการ์ดบน mobile ต้องไม่น้อยกว่า `12px`
- การ์ดที่อยู่ในแถวเดียวกันต้องสูงเท่ากัน ค่า KPI ต้องเด่นกว่าป้ายกำกับ และคำอธิบายต้องสั้นพอให้สแกนได้
- กราฟแท่งและแนวโน้มต้องแสดงค่าตัวเลขที่อ่านได้โดยตรง ไม่ให้ผู้ใช้ต้องประมาณจากความยาวหรือสีเพียงอย่างเดียว
- มุมมองคนและพื้นที่ต้องเริ่มจาก summary cards และกราฟประเภทพื้นที่ ก่อนรายการวัฒนธรรม/ท่องเที่ยวแบบยาว
- รายละเอียดหลักฐานรายมิติ กฎคุณภาพ และ metadata ราย source ใช้ collapsed details เป็นค่าเริ่มต้น เพื่อลดความหนาแน่นโดยไม่ทิ้งข้อมูลตรวจสอบ
- แท็บภาพรวมต้องอ่านจบได้ใน 20 วินาที: project groups, participant records, innovations และ source coverage ต้องแยกกัน พร้อมบอก data gaps โดยไม่ใช้พื้นที่หนึ่งในสามกับ metric ที่ไม่มีค่า
- หน้า full detail ต้องเปิดทุก field ใน public projection ได้ผ่าน collapsed details; รายการยาวแสดงครั้งละส่วน ค้นหาและโหลดเพิ่มได้ เพื่อคงความครบโดยไม่ทำลาย readability
- สถานะ API ต้องบอกความต่างระหว่าง “connector ดึงได้”, “candidate ผ่าน validation” และ “public revision ได้รับอนุมัติ” อย่างชัดเจน
- QA ต้องตรวจอย่างน้อยที่ `1440×1000`, `390×844` และ `320×800`: แท็บต้องอยู่ใน panel, flow/กราฟต้องไม่ล้น และค่าบนกราฟต้องมองเห็นครบ

## Reference patterns

แนวทางที่นำมาศึกษา ไม่ใช่หน้าจอที่คัดลอก:

- [UNDP GeoHub](https://geohub.data.undp.org/) — map-led discovery และ metadata
- [UNDP SDG Push Diagnostic](https://sdgdiagnostics.data.undp.org/) — แยก evidence, policy choice และ scenario
- [USAspending Agency Profiles](https://www.usaspending.gov/agency) — drill-down จากภาพรวมไปแหล่งข้อมูล
- [Seattle Budget Dashboard](https://www.seattle.gov/council/topics/budget-dashboard) — อธิบายบริบทก่อนตัวเลข
- [Open Treasury](https://www.opentreasury.org/) — การสื่อสารงบด้วยภาษาคนทั่วไป
- [PMUA Data Command Center Mockup](https://pmua-dashboard-mock.poomzi.com/) — หัวข้อเดิมด้าน source coverage, พื้นที่ และงบประมาณ

Reference screens ที่ใช้ศึกษารูปแบบ interaction:

- [Squarespace — Geography analytics](https://mobbin.com/screens/be6a849b-1fde-42ca-a6f2-f69ffcf4439c)
- [Cloudflare — Account analytics](https://mobbin.com/screens/254f6c74-2e18-4638-ad6f-ff8dc6c5c297)
- [Navattic — Analytics](https://mobbin.com/screens/a5be5a57-9c24-49a2-9ce5-ccd5edc17a1b)
- [Hotjar — Custom dashboard](https://mobbin.com/screens/f43a5082-26d2-40d3-ba2a-6c4bee3958b5)
- [Deel — Global Hiring Guide](https://mobbin.com/screens/a6cb49ca-18e2-49d4-9a58-da555b0c4855)
- [Profound — Answer Engine Insights](https://mobbin.com/screens/98b82305-3239-4d52-b0c9-0e7f701dc127)
- [Felt — Operational Map](https://mobbin.com/screens/e3ac649f-a644-4545-a798-9d50366385db)
- [Rocket Money — Budget](https://mobbin.com/screens/e8e471f9-dc5d-47a7-8d02-8b62c096149b)
- [Origin — Spending](https://mobbin.com/screens/d74b56f7-a4f0-43c9-b708-6615de691c5c)

## Review checklist

- ผู้ใช้เข้าใจว่าสีหมายถึง coverage ไม่ใช่คะแนนหรือ ranking
- จังหวัดที่ไม่มีข้อมูลไม่แสดงเป็นศูนย์
- ทุกค่ามี source/quality context ที่เพียงพอ
- UI ไม่แสดง raw table, contact field หรือ restricted value
- Keyboard, touch, contrast และ responsive layout ใช้งานได้
- ผู้บริหารเห็น summary และค่าบน visualization ได้ก่อนรายละเอียดทางเทคนิค
- การ์ดในแถวเดียวกันเสมอกัน และไม่มี horizontal overflow ที่ desktop/mobile QA viewports
- Province panel และ `/insights` แสดง non-geo/unmapped อย่างตรงไปตรงมา
- Project count, participant count และ innovation–province link ผ่าน regression test แยก grain ทั้ง 77 จังหวัด

ข้อจำกัดข้อมูลที่ UI ต้องรักษาอยู่ใน [Data audit](data-audit.md)
