# แผนแบ่ง phase แก้ UI/UX มือถือ (จากรายงาน 28 ตุลาคม 2569)

ที่มา: `docs/ui-audit-2026-10-28.md` ทุกปัญหาในรายงานถูกจัดลงตารางนี้ครบ ไม่มีข้อไหนตกหล่น
กติกา: ไม่แตะข้อมูลและ API, รัน `python -m app.cli check` ปิดทุก phase, ไม่ commit หรือ push จนกว่า Peet สั่ง
สถานะ: ทำแล้ว = แก้ไฟล์แล้วและผ่าน check, รอ = ยังไม่แตะ, ตัดสินใจ = ต้องให้ Peet เลือกก่อน

ลำดับคิดจากความเสี่ยงต่ำไปสูง: phase 0 ไม่เปลี่ยนหน้าตา desktop เลย, phase 1 แก้คำบ่นตรง ๆ ("กดยาก" "ตัวหนังสือเล็ก"), phase 2 ขึ้นไปค่อย ๆ แตะ motion, โค้ด JS และการออกแบบ

## Phase 0 ฐานแพลตฟอร์ม (ทำแล้ว)

เป้าหมาย: ตัดปัญหาที่เป็น "เว็บในเบราว์เซอร์" ออกครั้งเดียวทั้งระบบ ไม่เปลี่ยน layout ใด ๆ

| # | ปัญหา (แถวในรายงาน) | ไฟล์ที่แก้ | สถานะ |
|---|---|---|---|
| 0.1 | viewport ไม่มี `viewport-fit=cover` และ `interactive-widget=resizes-content`, ไม่มี `color-scheme`, `theme-color` หน้า index ไม่ตรงสีพื้น (lane C) | `app/templates/index.html`, `province.html`, `insights.html` | ทำแล้ว |
| 0.2 | dock, header, ชีต, มุมแผนที่ ไม่เผื่อ `env(safe-area-inset-*)` (lane C) | `styles.css` บล็อกมือถือ, `mobile.css` ส่วนที่ 9, `f2.css` บล็อกมือถือ (คงบรรทัด `top: 68px;` ที่ `tests/test_ui_coverage.py` ตรวจไว้ แล้ว override ด้วยกฎ safe-area ถัดไป) | ทำแล้ว |
| 0.3 | ไม่มี tap-highlight ที่ root, ไม่มี `text-size-adjust`, ไม่มี `overscroll-behavior` (lane C) | `app/static/touch.css` ใหม่ โหลดท้ายสุดทุกหน้า | ทำแล้ว |
| 0.4 | ไม่มี `touch-action: manipulation`, `user-select: none` บน control, ไม่มี `:active` feedback (lane C, D) | `touch.css` | ทำแล้ว |
| 0.5 | input และ select ต่ำกว่า 16px ทำ iOS ซูม (BLOCKER lane C) | `touch.css` บล็อก `(pointer: coarse)` รวม selector ของ `province.css` (`.record-search input`) และ `insights.css` (`.work-directory-controls`) ที่ specificity สูงกว่า `input` เปล่า ๆ | ทำแล้ว |
| 0.6 | `:hover` ค้างหลังแตะบน control ที่ใช้บนมือถือ (dock, ปุ่มปิด, tab, crumb, ป้ายภาค, KPI) (lane A) | `styles.css` 17 กฎ, `departments.css` 1 กฎ ครอบด้วย `@media (hover: hover) and (pointer: fine)` | ทำแล้ว |
| 0.7 | `100vh` 3 จุด (lane C) | `styles.css:3808, 5867`, `f2.css:171` | ทำแล้ว |
| 0.8 | `.claude/launch.json` และ `.codex_tmp/` ไม่อยู่ใน `.gitignore` (lane H) | `.gitignore` | ทำแล้ว |

## Phase 1 กดยาก และตัวหนังสือเล็กบนมือถือ (ทำแล้ว)

เป้าหมาย: ทุกปุ่มที่นิ้วต้องแตะมีพื้นที่ 44px ขึ้นไป และไม่มีข้อความที่ต้องอ่านเล็กกว่า 11px บนจอ 375px

| # | ปัญหา (แถวในรายงาน) | ไฟล์ที่แก้ | สถานะ |
|---|---|---|---|
| 1.1 | ปุ่ม 17 ถึง 26px: ปุ่ม "ประเทศไทย" ใน breadcrumb F2, summary "วิธีอ่านภาพรวม", ปุ่มสลับตัวกรองขั้นสูง, ปุ่มช่วยอ่านตัวชี้วัด, select หัวข้อ `#f2TopicJump` 36px, ปุ่มใน `.f2-coverage-note` 26px (BLOCKER lane C) | `f2.css` บล็อกมือถือ | ทำแล้ว |
| 1.2 | ปุ่ม 32 ถึง 42px: ปุ่มปิด × ทุกชีต, breadcrumb F1, ป้ายภาค ขยายพื้นที่แตะด้วย pseudo element; dock, tabs F1 F4 F2, ปุ่มมุมแผนที่, ปุ่มตัวกรอง F2, ปุ่มสลับจังหวัด F1, ปุ่ม "ดูภาพรวมฝ่าย 4" ตั้ง `min-height: 44px`; ปุ่มปิด × ของ F2 และแผงผู้บริหารกว้างจริง 30.7px จึงใช้ `inset: -8px` (lane C) | `mobile.css` ส่วนที่ 9 ใหม่, `styles.css` บล็อกมือถือ, `departments.css:125`, `f2.css` | ทำแล้ว |
| 1.3 | ตัวหนังสือต่ำกว่า 11px บนมือถือ: dock, ปุ่มมุมแผนที่, legend, ป้ายภาค, picker, kicker F4, crumb F1, flow node และ bar row ภาพรวมผู้บริหาร, ป้าย KPI ฝ่าย 1 และแผงผู้บริหาร, ป้ายจังหวัดบนแผนที่, badge แหล่งข้อมูล F4, F2 key, note, metric span และ label หัวข้อ (lane H) | `styles.css` บล็อกมือถือ, `mobile.css` ส่วนที่ 9, `departments.css` บล็อกมือถือ, `f2.css` บล็อกมือถือ | ทำแล้ว |
| 1.4 | ช่องค้นหาไม่มี `enterkeyhint="search"`, `autocapitalize`, `spellcheck` และ `#workDirectorySearch` ไม่มี `autocomplete="off"` (lane D) | `index.html` 4 ช่อง, `insights.html`, `province.html`, `f2.js` | ทำแล้ว |

### ผลตรวจ phase 0 และ 1 (28 ตุลาคม 2569)

วัดใน dev server ที่ viewport 375x812 แบบ `pointer: coarse` ด้วยสคริปต์ใน console (นับ control ที่มองเห็นซึ่งพื้นที่แตะรวม pseudo element ต่ำกว่า 44px, ข้อความที่มองเห็นต่ำกว่า 11px และ input ต่ำกว่า 16px)

| หน้า | control ที่วัด | ต่ำกว่า 44px | ข้อความต่ำกว่า 11px | input ต่ำกว่า 16px |
|---|---|---|---|---|
| F1 แผนที่ | 10 | 0 | 0 | 0 |
| F1 แผงภาพรวมประเทศ | 18 | 0 | 0 | 0 |
| ผู้บริหาร แผนที่ | 10 | 0 | 0 | 0 |
| ผู้บริหาร แผงภาพรวม | 10 | 0 | 0 | 0 |
| F2 ภาพรวม | 18 | 0 | 0 | 0 |
| F2 รายการ | 16 | 0 | 0 | 0 |
| F4 แผนที่ | 10 | 0 | 0 | 0 |
| F4 แผงภาพรวม | 16 | 0 | 0 | 0 |
| `/province/81` | ช่องค้นหา 16px | | | 0 |
| `/insights` | select และช่องค้นหา 16px | | | 0 |

ก่อนแก้ (ตัวเลขจากรายงาน): F1 จังหวัด 20 control ต่ำกว่า 44px และ 22 ข้อความต่ำกว่า 11px, ผู้บริหาร 9 และ 15, F2 ปุ่มเล็กสุด 17px, F4 แผนที่ 23 จาก 24 ข้อความต่ำกว่า 12px

ยังต้องดูบนเครื่องจริง (emulation ไม่จำลองให้): safe area บน iPhone ที่มี notch, คีย์บอร์ดดันชีตบน Android, hover ค้างหลังแตะ, การซูมตอน focus input บน iOS Safari

ผล `python -m app.cli check` หลังแก้ (รันแบบ `PYTHONUTF8=1 .venv\Scripts\python.exe -m app.cli check`): compile, validate-pipeline, publication-validate, public-repo-boundary ผ่านทั้งหมด, pytest 1036 passed, 6 skipped
หมายเหตุเครื่อง Windows ภาษาไทย: ถ้ารันโดยไม่ตั้ง `PYTHONUTF8=1` จะมี 26 เทสต์ใน `tests/f2_pipeline` ล้มด้วย UnicodeDecodeError (cp874) จาก `Path.read_text()` ที่ไม่ระบุ encoding ซึ่งไม่เกี่ยวกับไฟล์ที่แก้ในรอบนี้

## Phase 2 ความลื่นบนมือถือ (motion และ performance) (ทำแล้ว)

เป้าหมาย: animate เฉพาะ transform และ opacity, ปิดชีตมีจังหวะจริง, ไม่มี blur ซ้อน canvas บนมือถือ, reduced motion ยังมี fade, ค้นหาไม่ render ทุก keystroke

| # | ปัญหา | ไฟล์ | สถานะ |
|---|---|---|---|
| 2.1 | dock, มุมแผนที่, prompt animate `left right bottom width` ทุกครั้งที่เปิดปิดชีต (BLOCKER lane B) patch M | `styles.css` กฎ transition ของ `.mode-dock`, `.map-prompt`, `.map-corner` เหลือ `transform, opacity`; prompt ตอนชีตเปิดย้ายด้วย `translateX(calc(-50% - (P + 22px) / 2))` แทน `left`, มุมแผนที่ที่จอกว้าง 1160px ขึ้นไปใช้ `translateY(-64px)` แทน `bottom: 84px` (ตำแหน่งปลายทางเท่าเดิม วัดแล้ว) | ทำแล้ว |
| 2.2 | ชีตจังหวัดปิดแล้วหายวับ (visibility ทันที) และเปิด 360ms (lane F) | `styles.css` กฎ `.province-panel` ไม่มี layer: เปิด 280ms, ปิด 200ms แล้ว `visibility: hidden` ตามหลัง 200ms | ทำแล้ว |
| 2.3 | `.panel-view` keyframes เล่นทุกครั้งที่สลับ tab (lane F) | `styles.css` ตัด `animation` และ `@keyframes panel-view-in` ออก (สลับ tab เป็นงานถี่ ไม่ควร animate) | ทำแล้ว |
| 2.4 | `backdrop-filter: blur()` 20 จุดบน canvas แผนที่ (lane B) บนมือถือใช้พื้นทึบ | `mobile.css` ส่วนที่ 10: ปิด blur 16 จุดของหน้าแผนที่ และให้ brand, dock, prompt, ปุ่มแผนที่ ใช้พื้นขาว 96% (จาก 92%); อีก 4 จุดอยู่ใน `province.css` และ `insights.css` ซึ่งเป็นหน้าเอกสารไม่มี canvas จึงคงไว้ | ทำแล้ว |
| 2.5 | reduced motion ปิดทุกอย่างเหลือ 0.01ms (lane A) patch R และเพิ่มใน `province.css` (pulse 340, 358) | `styles.css` ท้ายไฟล์ (บล็อกใหม่: ชีต dock prompt ป้ายภาค เหลือ transition opacity และสี 160ms, skeleton หยุด pulse), `touch.css` (กดแล้วไม่ย่อ แต่ยังจาง), `province.css` (จุดโหลดหยุดเด้ง) ไม่ใช้ `transform: none !important` ตาม patch R เดิม เพราะ dock และ prompt ใช้ translateX(-50%) จัดกึ่งกลาง | ทำแล้ว |
| 2.6 | ค้นหา F4, โครงการ, วัฒนธรรม render ทุก keystroke ไม่มี debounce (lane B) | `app.js` เพิ่ม `debounce()` 120ms ใช้กับ 4 ช่อง (state อัปเดตทันที render รอหยุดพิมพ์) | ทำแล้ว |
| 2.7 | `font-weight` เปลี่ยนเป็น 750 เมื่อ active ทำให้ breadcrumb ขยับ (lane E) | `styles.css` 3 กฎ (`.department-flow span.active`, `:is(.f1-flow, .f4-flow) span.active`, `button.active`) เหลือสีและวงกลมเลขขั้นเป็นตัวบอกสถานะ น้ำหนักคงที่ | ทำแล้ว |

### ผลตรวจ phase 2 (28 ตุลาคม 2569)

วัดใน dev server ด้วยสคริปต์ใน console

| ที่วัด | ผล |
|---|---|
| transition ของ dock, prompt, มุมแผนที่ (computed) | `transform, opacity` ทั้งสามตัว |
| desktop 1280x800 เปิดชีตจังหวัด | prompt กึ่งกลางที่ x=319 (สูตรเดิม 319), มุมแผนที่ห่างขอบล่าง 84px (เดิม 84), dock กว้าง 860 กึ่งกลาง (เดิม 860) |
| ปิดชีตจังหวัด (sample ทุก 50ms) | transform เลื่อน 0 ถึง 660px ภายใน 200ms แล้ว `visibility: hidden` ที่ 250ms ไม่หายวับ |
| `.panel-view` | `animation-name: none` ทุก view |
| breadcrumb F1 | น้ำหนัก 500 ทั้ง active และไม่ active |
| mobile 375 backdrop-filter | `none` ที่ brand, dock, prompt, legend, ปุ่มแผนที่; พื้น dock, brand, prompt = rgba(255,255,255,.96) |
| reduced motion | มีบล็อกใน styles.css (5 กฎ) และ touch.css (1 กฎ) ตรวจจาก CSSOM; ยังไม่ได้ลองกับ OS ที่เปิด reduce จริง |
| ค้นหา F4 พิมพ์แล้ว | ไม่ render ทันที (DOM เท่าเดิม) และ render หลัง 300ms |

ยังต้องดูบนเครื่องจริง: pan แผนที่ขณะชีตเปิดบน Android รุ่นเก่า (ดู frame หลังตัด blur), เปิด reduce motion ใน OS แล้วเปิดปิดชีต

ผล `python -m app.cli check` หลังแก้ (รันแบบ `PYTHONUTF8=1`): compile, validate-pipeline, publication-validate, public-repo-boundary ผ่านทั้งหมด, pytest 1036 passed, 6 skipped

## Phase 3 การเข้าถึง (blocker ด้าน a11y) (ทำแล้ว)

| # | ปัญหา | ไฟล์ | สถานะ |
|---|---|---|---|
| 3.1 | modal ประวัติสถานีไม่ย้าย focus ไม่ trap ไม่คืน focus (BLOCKER lane A) เปลี่ยนเป็น `<dialog>` + `showModal()` แบบ F2 | `app.js:3550-3612`, `index.html` | ทำแล้ว: `ensureStationHistoryModal()` สร้าง `<dialog>` (ไม่ต้องเขียน `role`/`aria-modal` เอง) เปิดด้วย `showModal()` ซึ่งให้ top layer, focus trap และ Esc มาเอง ปิดด้วย `close()`; close event ทำลายกราฟและคืน focus ให้ตัวที่เปิด (`state.stationHistoryOpener`) ทางเดียวทั้งปุ่มปิด คลิกนอกการ์ด และ Esc; handler Escape ตรวจ `.open` แทน `.hidden`; `styles.css` ตัว dialog โปร่งใส padding 0 (คลิกนอกการ์ดจึงตกที่ dialog = ปิด) ฉากหลังย้ายไป `::backdrop`; `mobile.css` ข้อ 11 ปุ่มปิด 44px และปุ่มช่วงกราฟสูง 44px |
| 3.2 | `outline: none` 13 จุดแทน focus ring (BLOCKER lane A) | `styles.css:438, 1063, 1843, 3227`, `departments.css:191, 198, 229, 237`, `province.css:168, 323, 1119, 1184` | ทำแล้ว: ลบ 12 จุด คงไว้เฉพาะ `#provinceName:focus` (h1 ที่ focus ด้วยโปรแกรม รายงานยกเว้นให้) canvas แผนที่เปลี่ยนเป็น `:focus:not(:focus-visible)` และได้ ring ด้านใน 3px เมื่อ focus ด้วยคีย์บอร์ด; `.f1-country-detail` และ `.f1-province-detail` ได้ ring ตอน focus-visible; province.css เพิ่ม ring กลาง `2px solid var(--ink)` ท้ายไฟล์เพราะเดิมหน้าจังหวัดไม่มี ring กลางเลย |
| 3.3 | `closePanel()` ไม่คืน focus ให้ปุ่มที่เปิด (lane A) | `app.js:4545-4560` | ทำแล้ว: `openPanelLoading()` จำ `document.activeElement` ไว้ที่ `state.panelOpener` (ถ้าสลับจังหวัดจากในชีตเองคงตัวเปิดเดิม) และ `restoreFocusAfterPanelClose()` ท้าย `closePanel()` ย้าย focus เฉพาะเมื่อ focus ค้างในชีตที่ปิดหรือหลุดไป body ไปที่ตัวเปิด ถ้าไม่มีหรือซ่อนอยู่ไป `#provinceSelect` ถ้าผู้ใช้กดที่อื่นอยู่แล้ว (คลิกแผนที่ ปุ่มสลับโหมด) ไม่แย่ง focus |
| 3.4 | toast หาย 2.2 วินาทีคงที่ ไม่หยุดเมื่อสลับแท็บ (lane A) | `app.js:2461-2466` | ทำแล้ว: แสดง 2.6 ถึง 6 วินาทีตามความยาวข้อความ (1.2 วินาที + 55ms ต่อตัวอักษร) เมื่อแท็บถูกซ่อนหยุดนับและจำเวลาที่เหลือ กลับมาแล้วนับต่อ (อย่างน้อย 1.2 วินาที) ผูก `visibilitychange` ครั้งเดียวตอนเรียก `showToast()` ครั้งแรก |
| 3.5 | skip link หน้า index ชี้ไป canvas (lane A) | `index.html:21` | ทำแล้ว: `href="#provinceSelect"` ข้อความ "ข้ามไปยังตัวเลือกจังหวัด" กด Enter แล้ว focus ไปที่ select จริง |
| 3.6 | focus ring กลางเป็นสีเขียวแบรนด์ 3px (lane A POLISH) | `styles.css:2231` | ทำแล้ว: ring กลางทุกจุดเป็น `2px solid #141d18` offset 2px (styles.css 6 กฎที่เคยเป็นเขียว 3px, departments.css 1 กฎที่เคยเป็นน้ำเงิน #294f75) กฎในชั้น controls ที่ 1035 ไม่แตะเพราะ layer lightmap ทับอยู่แล้ว |
| 3.7 | ตัวหนังสือโปร่งบนแผนที่ (alpha .55 ถึง .68) อาจไม่ถึง 4.5:1 ต้องวัดจริงก่อน (lane A) | `styles.css:1239, 1652, 2646` | ทำแล้ว (วัดก่อนแก้): กฎที่ 1239 และ 1652 ถูก layer lightmap ทับเป็น `--ink-soft` บนการ์ดขาวอยู่แล้ว วัดได้ 5.88:1 ไม่ต้องแก้; `.region-label span` ยังโปร่งจริง alpha .55 วัดได้ 4.41:1 บนแผนที่สว่าง (ไม่ถึง 4.5) ยกเป็น .85 ได้ 8.12:1 |

### ผลตรวจ phase 3 (28 ตุลาคม 2569)

วัดใน dev server ด้วยสคริปต์ใน console และกดคีย์บอร์ดจริงผ่าน browser pane (desktop 1280x800 และ mobile 375x812)

| ที่วัด | ผล |
|---|---|
| Tab ครั้งแรกบนหน้า index | ไปที่ skip link, ring `2px solid rgb(20, 29, 24)` offset 2px, ลิงก์โผล่ที่ top 12px |
| Enter ที่ skip link | focus ไปที่ `#provinceSelect` (hash `#provinceSelect`) และเห็น ring |
| Tab ต่อไป | ลิงก์ "ข้อมูลเปิด" ได้ ring แบบเดียวกัน |
| เปิด modal ประวัติสถานี | เป็น `<dialog>` จริง (`:modal` ตรง) ไม่มี `role`/`aria-modal` ที่เขียนเอง focus อยู่ที่ปุ่มปิดใน dialog; dialog โปร่งใส padding 0 กว้าง 900; `::backdrop` rgba(24, 31, 28, .42); การ์ด #fffafa เหมือนเดิม |
| ปิด modal ด้วยปุ่มและด้วย Esc | `open=false`, กราฟถูกทำลาย (`state.stationHistoryChart` เป็น null), focus กลับไปปุ่มที่เปิด (ในการทดสอบคือ `#closePanel`) |
| Esc ครั้งที่สอง | ปิดชีตจังหวัดแล้ว focus กลับไปที่ตัวที่เปิดชีต (ลิงก์ที่ focus อยู่ตอนเรียก `selectProvince`) |
| ปิดชีตด้วยปุ่ม × | focus กลับไป `#provinceSelect` (ตัวเปิดในการทดสอบ) และ `state.panelOpener` ถูกล้าง |
| toast | ข้อความสั้น 2600ms, 200 ตัวอักษร 6000ms; ซ่อนแท็บหลัง 600ms เหลือ 1990ms, ซ่อนต่ออีก 2.5 วินาที toast ยังอยู่, กลับมาแล้วนับต่อ (จำลอง `document.hidden` + `visibilitychange`) |
| contrast | `.map-prompt small`, `.evidence-legend li`, `.brand small`, `.picker-copy small` = #5a675f บนขาว 5.88:1; `.region-label span` เดิม .55 = 4.41:1 บนแผนที่สว่างและ 5.32:1 บนเข้ม ตอนนี้ .85 = 8.12:1 และ 10.96:1 |
| mobile 375x812 modal | dialog กว้าง 339, การ์ดสูง 621 อยู่ในจอ, ปุ่มปิด 44x44, ปุ่มช่วงกราฟสูง 44, ปุ่มใน modal ที่ต่ำกว่า 44 = 0 |
| console | ไม่มี error |

ยังต้องดูบนเครื่องจริง: screen reader (VoiceOver/TalkBack) อ่าน dialog เป็น modal และ Tab ไม่หลุดออกนอก dialog (ตรวจจาก `:modal` แล้วแต่ยังไม่ได้ลองกับ screen reader), ring สีเข้มบนปุ่มที่พื้นเข้ม (เช่น ปุ่มหมวดคนที่กดอยู่ในหน้าจังหวัด) ว่ายังเห็นชัด, และ modal กับข้อมูลสถานีจริง (ชุดสาธารณะตอนนี้ไม่มีสถานี จึงทดสอบด้วย station id ปลอมซึ่ง API ตอบว่าไม่มีข้อมูล)

ผล `python -m app.cli check` หลังแก้ (รันแบบ `PYTHONUTF8=1`): compile, validate-pipeline, publication-validate, public-repo-boundary ผ่านทั้งหมด, pytest 1036 passed, 6 skipped, exit 0 (7 นาที 53 วินาที) รอบนี้รันก่อนเพิ่ม mobile.css ข้อ 11 จึงรัน `tests/test_ui_coverage.py` ซ้ำหลังเพิ่ม ผ่าน 15 ข้อ

## Phase 4 สถานะ เนื้อหา และของเหลือ (ทำแล้ว)

| # | ปัญหา | ไฟล์ | สถานะ |
|---|---|---|---|
| 4.1 | F1 ประเทศโหลดล้มเหลวไม่มีปุ่มลองใหม่ (lane E) | `index.html` (`#f1CountryLoading`), `app.js` (`setF1CountryStatus`, `#retryF1Overview`), `styles.css` | ทำแล้ว กล่องโหลดมี `<p id="f1CountryStatusMessage">` กับปุ่ม `ลองอีกครั้ง` (44px) ที่เรียก `loadF1Overview()` ซ้ำ ระหว่างโหลดข้อความเป็น screen reader only อยู่หลัง skeleton เมื่อล้มเหลวจึงโชว์ข้อความกับปุ่ม ทดสอบด้วย fetch ที่ล้มเหลวจำลองแล้วกดปุ่มจริง โหลดสำเร็จ |
| 4.2 | skeleton สูงไม่ตรงของจริง, F1 F2 ใช้ข้อความ "กำลังโหลด" (lane E) | `styles.css` (`.panel-loading`, `.skeleton-bars`, `.sr-only`), `mobile.css` ข้อ 12, `index.html`, `app.js`, `f2.js` (`skeleton()`), `f2.css` | ทำแล้ว ชีตจังหวัด: eyebrow 18 + ชื่อ 48 + กริด KPI 3 คอลัมน์การ์ด 154px (มือถือ 2 คอลัมน์ 92px) + บล็อก 210 ตามที่วัดจากของจริง F1 ประเทศ: บรรทัดคำแนะนำ 18 + การ์ด 8 ใบ 118px ในกริด 2 คอลัมน์ F1 จังหวัด: 53/144/120 F1 แท็บย่อย: 3 แท่ง 44 F2 ภาพรวม: 4 แท่ง 177 สองคอลัมน์ (มือถือ 1 คอลัมน์) F2 รายการ: 3 แท่ง 96 ทุกจุดยังมีหัวข้อ "กำลังโหลด" แบบ `.sr-only` ใน `role="status"` กฎร่วม `.sr-only` และ `.skeleton-bars` อยู่ใน `@layer panel` เพราะกฎนอก layer จะทับกฎสถานะล้มเหลวใน `@layer lightmap` |
| 4.3 | `.region-label span` ไม่มี `tabular-nums` ในกฎหลัก (lane E POLISH) | `styles.css` (`.region-label span`) | ทำแล้ว เพิ่ม `font-variant-numeric: tabular-nums` ตรวจค่า computed แล้วในโหมดฝ่าย 1 (ป้าย 6 ป้าย) |
| 4.4 | `letter-spacing` ติดลบบนหัวข้อภาษาไทย (lane H) | `insights.css` (h1, h2, h3), `province.css` (`.title-row h1`, `.section-title h2`), `styles.css` (`.overview-heading > span`, `.province-title-block h1` 2 จุด, `.data-card h3`, `.section-heading > span`, `.department-panel-head h2`) | ทำแล้ว 11 จุดเป็น `letter-spacing: 0` และ line-height 1.5 ตัวเลข KPI (`strong`) คงค่าติดลบไว้ตามเดิม |
| 4.5 | จุดกลาง ขีดยาว ลูกศร ประมาณ 90 จุดในข้อความ UI (lane H) ข้อ C | `app.js`, `f2.js`, `f2-detail.js`, `province.js`, `insights.js`, `index.html`, `province.html`, `tests/test_f2_detail_presentation.py` | ทำแล้ว ตามข้อ C โดยปรับดังนี้: รายการตัวกรองและมิติใช้ `joinThai()` ("ก, ข และ ค") ส่วน metadata ใช้ ", " แทนเว้นวรรคสองช่อง เพราะ HTML ยุบช่องว่างซ้ำ ประโยคสองท่อนใช้เว้นวรรคหรือวงเล็บ ค่าว่าง "—" เป็น "ไม่ระบุ" (แก้ประโยคอธิบายใน f2.js และ province.html ตาม) ลูกศรตัดออก ("ดูรายการทั้งหมด", "กลับไปภาพรวม", "เปิดรายการต้นทาง") attribution แผนที่ใช้ " \| " และ `•••` ในตัวเลือกจังหวัดเป็น SVG chevron 16px ไฟล์ UI ไม่เหลืออักขระเหล่านี้ (grep 0) ยังเหลือเฉพาะที่มากับข้อมูลจาก API (`data/public/public_dashboard.json` 11 จุด และ `disaster_tracking.json`, `learning_dashboard.json`, `pmua_product_details.json` ไฟล์ละ 1 จุด เช่น "ข้อมูล candidate · ต้องทบทวนความหมายก่อนใช้เป็น KPI" และหมายเหตุ F2 "คลัสเทอร์อุตสาหกรรม — ไม่มีข้อมูลเพียงพอ") ซึ่งเป็น generated data ต้องแก้ที่ builder หรือต้นทาง ไม่แก้ในงาน UI นี้ |
| 4.6 | `href="#"` 2 จุด (lane H POLISH) | `index.html` | ทำแล้ว ลบ `href="#"` ออกทั้ง `#fullProvinceLink` และ `#provinceApiLink` JS ตั้ง href ก่อนแสดงเนื้อหาอยู่แล้ว (ตรวจได้ `/province/81` และ `/api/public/v1/provinces/81/briefing`) |
| 4.7 | `?v=` ไม่มีบน `province.css`, `insights.css`, `province.js`, `insights.js` และไม่มี `Cache-Control` (lane H POLISH) | `main.py` (`VersionedStaticFiles`), templates, `tests/test_api.py` | ทำแล้ว ไฟล์ static ที่ URL มี `?v=` ได้ `public, max-age=604800` (ไม่ใช่ immutable เพราะ bump ด้วยมือ) ไม่มีได้ `public, max-age=0, must-revalidate` คำตอบ 304 ก็ได้ header เดียวกัน เติม `?v=20261028-phase04` ให้ insights.css, insights.js, province.js และ bump ทุกไฟล์ที่แก้ (styles, mobile, app.js, f2.css, f2.js, f2-detail.js, province.css) มี assertion ใน `tests/test_api.py` |
| 4.8 | ไม่มี `apple-touch-icon` 180px (lane G POLISH) | `app/static/apple-touch-icon.png`, 3 templates | ทำแล้ว ไอคอน 180x180 ทึบ วาดจาก favicon.svg บน canvas (1,492 ไบต์) และ `<link rel="apple-touch-icon">` ใน index, province, insights |
| 4.9 | `.map-texture` โค้ดตาย (lane G POLISH) | `styles.css` | ทำแล้ว ลบทั้ง 2 กฎ ไม่มี element หรือ JS อ้างถึง |

### ผลตรวจ phase 4 (28 ตุลาคม 2569)

ตรวจใน browser pane (Chromium) ที่ 1280x800 และ 375x812 หลัง restart dev server

| รายการ | ของจริง | skeleton หรือค่าที่ได้ |
|---|---|---|
| ชีตจังหวัด การ์ด KPI (executive) | 154px 3 คอลัมน์ / มือถือ 92px 2 คอลัมน์ | 154px 3 คอลัมน์ / มือถือ 92px 2 คอลัมน์ |
| F1 ประเทศ การ์ด KPI | 121px 2 คอลัมน์ (มือถือ 154px) | 118px 2 คอลัมน์ (8 ใบ + บรรทัด 18px) |
| F1 จังหวัด หัวเรื่อง / รายละเอียด | 53 / 145px | 53 / 144 / 120px |
| F1 แท็บย่อย (`.f1-inline-loading`) | รายละเอียดจริง 145 ถึง 1,585px | 3 แท่ง 44px รวม 152px, `role="status"` + ข้อความ sr-only |
| F2 การ์ดตัวชี้วัด (`.f2-metric-wrap`) | 178px 2 คอลัมน์ / มือถือ 191px 1 คอลัมน์ | 177px 2 คอลัมน์ / มือถือ 177px 1 คอลัมน์ |
| F2 การ์ดรายการ | 96px | 96px x 3 |
| F1 ล้มเหลว (จำลอง fetch พัง) | ข้อความ 20px สูง, ปุ่มลองอีกครั้ง 44px, skeleton `display: none` ทั้ง 1280 และ 375 | กดปุ่มจริงแล้วโหลดสำเร็จ เนื้อหาแสดง ปุ่มซ่อน |
| `.region-label span` | 6 ป้ายในโหมดฝ่าย 1 | `font-variant-numeric: tabular-nums` |
| หัวข้อไทย 11 จุด | letter-spacing computed `normal` ทุกจุด line-height 1.5 (insights h1 89.6px/134.4px, province h1 70/105, h2 38/57) | |
| อักขระพิเศษบนหน้าจอ | index (executive, F1, F2 ภาพรวมและรายการ), `/province/81`, `/insights` | เหลือเฉพาะข้อความจากข้อมูล API ตามข้อ 4.5 `/insights` ไม่เหลือเลย |
| Cache-Control | `touch.css?v=x` 200 และ 304 | `public, max-age=604800`; ไม่มี `?v=`: `public, max-age=0, must-revalidate` |
| ลิงก์ในชีต | ก่อนเปิด ไม่มี `href` | หลังเปิด `/province/81`, `/api/public/v1/provinces/81/briefing` |
| console | | ไม่มี error นอกจาก error ที่จำลองเองตอนทดสอบปุ่มลองใหม่ |

ยังต้องดูบนเครื่องจริง: iPhone Add to Home Screen ว่าใช้ `apple-touch-icon.png` (Chromium ไม่แสดง) และปุ่มลองใหม่ของฝ่าย 1 เมื่อเครือข่ายหลุดจริง

ข้อควรรู้ที่เจอรอบนี้: ตั้งแต่ 4.7 เบราว์เซอร์จะ cache ไฟล์ที่มี `?v=` ไว้ 7 วัน ระหว่างแก้งานต้อง bump `?v=` ทุกครั้งที่แก้ไฟล์ หรือใช้ `fetch(url, { cache: "reload" })` ก่อน reload ใน browser pane

การตรวจ: `PYTHONUTF8=1 .venv/Scripts/python.exe -m app.cli check` ผ่านทุกขั้น pytest 1036 passed, 6 skipped, exit 0 (8 นาที 55 วินาที) รอบนี้รันก่อนย้ายกฎ `.skeleton-bars` เข้า `@layer panel`, ขยาย skeleton ฝ่าย 1 เป็น 8 ใบ, bump `?v=` ของ f2.js กับ f2-detail.js และ line-height ของชื่อชีต จึงรัน `tests/test_ui_coverage.py` กับ `tests/test_api.py` ซ้ำหลังแก้ ผ่าน 36 ข้อ

## Phase 5 ต้องตัดสินใจก่อนลงมือ (ทำแล้ว)

Peet ตัดสินใจ 29 ตุลาคม 2569: 5.1 ทาง ก, 5.2 ให้ dock หายตอนขยาย, 5.3 dock อยู่เหนือชีต, 5.4 ไม่แก้

| # | เรื่อง | ที่ตัดสินใจและทำ | สถานะ |
|---|---|---|---|
| 5.1 | ฟอนต์: Google เสิร์ฟ Anuphan ถึง 700 แต่โค้ดใช้ 750 ถึง 850 (lane B) | ก ตัดน้ำหนักเกิน 700 เป็น 700 ทั้ง 131 จุดใน 7 ไฟล์ CSS (styles 89, mobile 2, departments 9, f2 5, province 15, insights 11) และตัดลิงก์ Google Fonts เหลือ 400;500;600;700 ใน 3 เทมเพลต เหตุผล: แกน wght ของ Anuphan บน Google Fonts มีถึง 700 (ขอ 800 ได้ HTTP 400) เบราว์เซอร์จับ 750 ถึง 850 ไปที่หน้า 700 อยู่แล้ว วัดความกว้างข้อความเท่ากันทุกจุด หน้าตาจึงไม่เปลี่ยน ค่า 650 และ 550 คงไว้ | ทำแล้ว |
| 5.2 | ชีตโหมดขยาย แก้ "ที่แสดงข้อมูลน้อย" (lane C) patch S | ปุ่มขีดจับ `.sheet-grip` 5 จุด (ชีตจังหวัด, F1 ประเทศ, F4 ประเทศ, workspace, F2) แสดงเฉพาะมือถือ กว้าง 160 สูง 36 บวก hit area ถึง 44 แตะแล้ว `body.sheet-expanded` ชีตขยายจาก 68/68 เป็น 8px จากขอบจอทั้งบนล่าง header dock และมุมแผนที่จางหาย 160ms เลื่อนในชีตเกิน 40px ขยายให้เอง ย่อเมื่อแตะขีดจับอีกครั้งหรือปิดชีต (`setSheetExpanded` และ `initSheetExpand` ใน app.js, mobile.css ส่วนที่ 13) | ทำแล้ว |
| 5.3 | z-index 22 ค่าไม่มี scale (lane E) | ประกาศ token 7 ตัวใน `:root` (map-ui 20, header 30, sheet 40, dock 50, modal 100, toast 110, skip 1000) แทนเลขลอยใน styles.css, f2.css, province.css, insights.css ลำดับใหม่คือ dock อยู่เหนือชีตทุกแบบ F2 detail sheet เป็นชั้น modal ผลพลอยได้: ชีตจังหวัดโหมดผู้บริหารบนเดสก์ท็อปเคยลงถึง bottom 18px จึงโดน dock ทับ 53px ย้ายเป็น bottom 84px เท่าชีตฝ่าย (กฎ `body.panel-open .mode-dock` ที่ min-width 721px ทำให้ dock อยู่กลางจอทุกความกว้างเมื่อชีตเปิด) | ทำแล้ว |
| 5.4 | dock สูง 52 เป็น 56 เพื่อให้ปุ่ม 46px (ข้อ T) | คง dock 52 ปุ่ม 44 ตาม phase 1 | ไม่ทำ |

### ผลตรวจ phase 5 (29 ตุลาคม 2569)

ตรวจใน browser pane (Chromium) ที่ 1280x800, 1024x768, 1920x1080 และ 375x812 ส่วนใหญ่ด้วย `?mode=executive&province=46`

| รายการ | ค่าที่วัดได้ |
|---|---|
| z-index ที่คำนวณได้ (desktop และ mobile เท่ากัน) | dock 50, ชีตทุกแบบ 40, header และ board toggle 30, modal 100, toast 110, skip 1000, map-ui 20 |
| ขีดจับบนมือถือ | 160x36 (hit area ถึง 44) ที่ขอบบนของ header ชีต ไม่ทับปุ่มปิด (ปุ่มปิด F1 อยู่ x 310 ถึง 350, F2 324 ถึง 356) |
| ชีตขยายบนมือถือ 375x812 | ชีตจาก 68 ถึง 744 เป็น 8 ถึง 804 พื้นที่อ่านชีตจังหวัด 578px เป็น 698px (71% เป็น 86% ของจอ) header dock และมุมแผนที่ opacity 0 และ visibility hidden แตะขีดจับอีกครั้งกลับเป็นเดิม |
| ขีดจับบนเดสก์ท็อป | display none ทุกจุด |
| ชีตจังหวัดโหมดผู้บริหารกับ dock | 1280x800 ชีต 84 ถึง 716 และ dock 729 ถึง 782; 1024x768 ชีต 84 ถึง 684 และ dock 697 ถึง 750; 1920x1080 ชีต 84 ถึง 996 และ dock 1009 ถึง 1062 ไม่ทับกันทุกขนาด (ก่อนแก้ทับกัน 53px ทุกขนาด) |
| ชีต F1 F4 workspace กับ dock บนเดสก์ท็อป | bottom 84px อยู่แล้ว ไม่ทับ |
| น้ำหนักฟอนต์ | ความกว้างข้อความที่ 700 เท่ากับที่ 750 ถึง 850 ทุกจุดที่วัด |
| Node harness ของ tests | `window.matchMedia` ระดับไฟล์ใน app.js ทำให้ 2 เทสใน test_department_requests ล้มใน check รอบแรก (vm ไม่มี window) แก้เป็น stub เมื่อไม่มี window แล้วผ่าน |

ต้องดูบนเครื่องจริง: เลื่อนนิ้วจริงเกิน 40px แล้วชีตขยายเอง, ขีดจับมองเห็นชัดพอไหม, การจาง 160ms (pane ที่ซ่อนอยู่ไม่รัน transition จึงวัดด้วย transition none)

เหลือไป phase 6: กฎเลื่อน dock ไปทางซ้ายที่ 1080px ใน styles.css มี 3 จุด (บรรทัด 832, 2855, 4927) ถูกกฎ `body.panel-open .mode-dock` ที่ min-width 721px (บรรทัด 5102) ทับทั้งหมด เป็นโค้ดตาย

check: `PYTHONUTF8=1 .venv/Scripts/python.exe -m app.cli check` exit 0 (compile, validate-pipeline, publication-validate, public-repo-boundary, pytest 1037 passed 6 skipped) 29/10/2569

## Phase 6 ปิดท้าย (โครงสร้าง CSS)

| # | ปัญหา | ไฟล์ | สถานะ |
|---|---|---|---|
| 6.1 | `:hover` ที่เหลือประมาณ 46 กฎ (card, row, link ในชีต) ยังไม่ครอบ media query (lane A) | `styles.css`, `departments.css`, `f2.css`, `province.css`, `insights.css` | รอ |
| 6.2 | token `:root` ธีมมืดชั้น base ถูกทับด้วย lightmap 11 บล็อก มี `color-scheme: dark` ค้าง (lane G) | `styles.css:990-1008, 2213, 2620` | รอ |
| 6.3 | `@layer uiux2026` ไม่อยู่ในประกาศลำดับชั้น (lane G) | `styles.css:1` | รอ |
| 6.4 | รายการ F4 ไม่มี load more (lane B POLISH) รอจำนวนแถวจริงจาก API | `app.js:1407` | รอ นับก่อน |
| 6.5 | F2 filter dialog ไม่มี enter animation (lane F POLISH) ไม่ใช่ข้อผิดพลาด | `f2.css:110` | ไม่ทำก็ได้ |

## ต้องทดสอบบนเครื่องจริงหลังแต่ละ phase

รายการเต็มอยู่ในรายงานส่วนที่ 3 ที่เกี่ยวกับ phase 0 และ 1 โดยตรง:

- iPhone: แตะ select ใน F2 filter dialog แล้วหน้าต้องไม่ซูม
- iPhone ที่มี home indicator: dock ต้องไม่ถูกแถบขาวทับ (เปิดจาก Safari และเพิ่มลงหน้าจอหลัก)
- Android Chrome: แตะช่องค้นหา F4 แล้ว layout ต้องหดให้เห็นช่อง
- ทุกเครื่อง: แตะปุ่ม dock แล้วปล่อย สีต้องไม่ค้าง กดค้างต้องไม่เลือกข้อความ
- ทุกเครื่อง: ปุ่มปิด × และ breadcrumb ต้องแตะโดนจากขอบ 6px รอบตัว
