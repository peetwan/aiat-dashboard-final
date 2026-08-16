# Design references

หน้า dashboard เวอร์ชันนี้ออกแบบใหม่จาก pattern ของผลิตภัณฑ์จริง ไม่ได้คัดลอกหน้าจอใดหน้าจอหนึ่ง

## Mobbin MCP

- [Amplitude — data home](https://mobbin.com/screens/c019d856-cf4a-4faa-a0a7-cd28dfbd531c): ใช้แนวคิด navigation ซ้าย, onboarding ของ data source และ quick status
- [Mixpanel — main dashboard](https://mobbin.com/screens/116b19b1-6e4d-418a-8587-220b0c844f8e): ใช้ลำดับ filter → chart → detail
- [Databricks — pipeline run](https://mobbin.com/screens/2a53f9eb-b8e1-4958-afb7-f441acbdf414): ใช้แนวคิด pipeline state และ event log ที่ตรวจย้อนหลังได้
- [Render — database metrics](https://mobbin.com/screens/50504a21-dc6e-4450-a235-ce809c9d3355): ใช้แนวคิด health indicator และ event timeline

## Public dashboard references

- [Swetrix](https://github.com/Swetrix/swetrix): dashboard analytics ที่เน้น KPI หลักและ progressive disclosure
- [Chartbrew](https://github.com/chartbrew/chartbrew): ตัวอย่างการเชื่อม API, SQL และ NoSQL เข้า dashboard เดียว
- [Story Analytics](https://storyanalytics.ai/): ตัวอย่าง publication-ready chart และ data-source workflow

## Existing PMUA mock

ตรวจ [PMUA Data Command Center Mockup](https://pmua-dashboard-mock.poomzi.com/) เพื่อเก็บ information architecture เดิม เช่น source coverage, project lookup, area และ budget

ค่าตัวอย่างใน mock เช่น งบประมาณ, ROI, outcome, จำนวนโครงการ หรือชื่อบุคคล ไม่ถูกนำมาใช้ เพราะยังไม่มี evidence ใน merged dataset ปัจจุบัน หน้าใหม่จึงแสดงเฉพาะ:

1. จำนวน source และ endpoint จาก source catalog
2. API/raw connector ที่กำหนดไว้จริง
3. expected record count ที่ติดป้าย candidate reference
4. loaded record และ ingestion run จาก database
5. policy state ที่ย้อนกลับไปหา source registry ได้
