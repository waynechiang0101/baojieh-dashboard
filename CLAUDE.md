# 寶捷實業業績看板 — Claude 工作手冊

## 專案概覽

| 項目 | 值 |
|---|---|
| 正式網址 | https://baojieh-dashboard.pages.dev/dashboard.html |
| GitHub | https://github.com/waynechiang0101/baojieh-dashboard |
| 本地路徑 | /Users/wayne/Downloads/fmcg-v4-1/ |
| 部署平台 | **Cloudflare Pages**（連 GitHub，git push 自動部署） |
| 資料來源 | DERP ERP https://gderp.titan.ebiz.tw/derp 帳號 user34 |

## ⚠️ 部署注意事項（2026-06-04 更新）

- **只要 `git push` 就好**，Cloudflare Pages 自動部署，約 1 分鐘上線
- **Netlify 已廢棄**（bjworks.netlify.app，credits 耗盡）— 不要叫 Wayne 跑 `netlify deploy`，會 403
- GitHub Actions 排程每天 18:30 TW 自動跑腳本 + push，不需要手動觸發

## 更新數字 + 部署

```bash
cd /Users/wayne/Downloads/fmcg-v4-1
python3 scripts/derp_fetch.py
git add dashboard.html && git commit -m "更新" && git push
# 完成，Cloudflare Pages 自動接手
```

## 關鍵檔案

- `dashboard.html` — 單頁看板，所有資料內嵌為 JS 變數
- `scripts/derp_fetch.py` — 主更新腳本（DERP 登入、解析、寫 HTML）
- `.github/workflows/update-dashboard.yml` — 每日 18:30 自動排程

## 資料結構（dashboard.html 內的 JS 變數）

| 變數 | 說明 |
|---|---|
| `GRP` | 集團排行，含 s3/s4/s5/iya/iya3/br |
| `STORES` | 個別門市 Top100，含 v3/v4/v5/iy3/iy5/br |
| `UNIF` | 康是美分點 |
| `CVS_STORES` | CVS 便利商店門市 |
| `XB_STORES` | 小北各分店 |
| `REPS` | 業務代表績效 |
| `PAYS` | 收款資料（from 115-XX收款*.xls，抓最新 mtime） |
| `AR_REPS` | 應收帳款（自動從 DERP derp-421-14-1.jsp 撈） |
| `INV_BRANDS` | 庫存（from DERP 327-50.jsp ~45MB） |

排序：全部按本月（v3/s3）降冪排列。

## 庫存模組（INV_BRANDS）— 2026-06-04 結構

### SKU 資料結構
每個品牌的 topQ/topA 各存 top30 SKU，每個 SKU：
```js
{s:'SKU代號', n:'品名', q:數量, a:金額, d:庫存天數或null,
 wh:{
   tainan:   {q:數量, a:金額, d:天數},
   kaohsiung:{q:數量, a:金額, d:天數},
   tp:       {q:數量, a:金額, d:天數},  // 桃園
   km:       {q:數量, a:金額, d:天數},  // 康是美
   cvs:      {q:數量, a:金額, d:天數},
 }}
```

### 庫存天數計算規則
- `x.d` = DERP 327-50.jsp 的「日均銷」欄位（col7）算出來的天數
- 日均銷是全公司同一個值，不是各倉個別的
- 各倉天數 = 各倉數量 ÷ 同一個日均銷
- **不要自己用業績估算天數**，直接讀 `x.d` / `x.wh[k].d`
- parse 時用 `=` 覆寫不是 `+=`（各倉日均銷相同，累加會翻倍）

### 倉庫 Filter Tab（方案 C）
- 上排：品牌 tab（PAMPS/HS/OLAY...）
- 下排：倉庫 tab（全倉/台南/高雄/桃園/康是美/CVS）
- 切倉後必須按「該倉金額」重新排序，不能用全倉排序

### pitfall：兩次才生效
改 `parse_inventory_html()` 結構後必須：
1. `git push`（更新腳本）
2. 重跑 `python3 scripts/derp_fetch.py`（重產 HTML）
只推 code 不跑腳本，HTML 裡的資料還是舊結構。

## 小北退步分店表（2026-06-04 新增）

在小北分店明細下方，篩出本月業績 < 去年同月的分店：

```js
const declined = XB_STORES
  .filter(x => x.iy3 > 0 && x.v3 < x.iy3)
  .map(x => ({...x,
    gap:   x.iy3 - x.v3,
    moAch: Math.round(x.v3 / x.iy3 * 100),
    qAch:  x.iy5 > 0 ? Math.round(x.v5 / x.iy5 * 100) : null
  }))
  .sort((a, b) => b.gap - a.gap)
  .slice(0, 50);
```

顏色：< 70% 紅 / < 90% 橙 / ≥ 90% 白；季達成 ≥ 100% 綠。
**年達成暫不做**：XB_STORES 沒有 YTD 資料，需要另外從 DERP 抓。

## 業務邏輯

- P&G 本月業績 = DERP `total_mo`（含 OMD/ETC，比 XLS 多約 $1-2M）
- IYA：`iy5` = 季 vs 去年季，`iy3` = 本月 vs 去年本月
- 劉暄芸 `tgt=0` 正常（管康是美直送，沒有月目標）
- 月趨勢圖 12-3 月為估算值

## DERP 關鍵集團名稱

| 看板 | DERP 集團名稱 |
|---|---|
| 康是美 | 統一藥品股份有限公司(總公司) |
| 捷盟(7-11) | 捷盟-總公司 |
| 全台(全家) | 全台物流-總公司 |
| 大樹 | A01-大樹 |
| 丁丁 | A02-丁丁 |
| 啄木鳥 | A03-啄木鳥 |
| 小北 | 小北（多集團加總） |

## DERP API 端點

- `BizPlan/dsrDailySales` — 業績 XLS
- `3.IN/derp-327-50.jsp` — 庫存 HTML-XLS（~45MB streaming）
- `4.FN/derp-421-00.jsp` + `derp-421-14-1.jsp` — 應收帳款
- `6.BR/derp-610-24.jsp` — 客戶品項銷售 CSV（POST `*pageCmd=PrintCSV`，品項級出貨明細）
- `CCderp.jsp` — 登入 POST，accountID=86041711

## 康是美消化率（2026-06-10 新增）

- **SU 不能用**：SU 與實銷件數單位不一致（各品牌換算倍數不同），且看板業務不看 SU
- 正解：610-24 的 `totalQty` 欄 = **件數**，與實銷同單位（驗證：720件=30箱×箱入數24）
- `fetch_km_ship(d0,d1)`：抓 610-24 CSV → 篩 `soldToCode=110`（統一藥品）→ 品牌彙總淨出貨件數（SR 退貨扣回、BRAUN 併 ORALB）
- 消化率 = 4週實銷件數 ÷ 同期出貨件數，>100% 去庫存、<100% 堆庫存
- 口徑限制：DERP 出貨到統一藥品 3 個物流中心（中壢/高雄仁武/西園，分點=廠編），**含網購**；實銷不含網購 → 消化率偏保守（偏低）。網購無法從 DERP 端排除
- 每週一隨 cosmed_fetch 一起更新，寫入 `KM_SELL.ship_by_brand`

## 待辦

- 年達成欄位（需要 DERP YTD 資料）
- DERP 廠商 REST API 洽談中（2026-06，談判籌碼：看板商業化合作）
- 月中達標預估、庫存預警 Telegram 推播（等 API）
- 消化率：用 DERP SU（標準單位出貨數）÷ 康是美實銷件數（待做）

## 康是美實銷模組（2026-06-08 新增）

### 腳本
`scripts/cosmed_fetch.py` — playwright + Claude Vision 讀驗證碼自動登入，每次跑 `derp_fetch.py` 自動帶上。

```bash
# 手動只跑實銷
ANTHROPIC_API_KEY=xxx python3 scripts/cosmed_fetch.py
```

### P&G 廠編（排除非P&G）
| 廠編 | 品牌 |
|---|---|
| 8604171183 | OLAY PRO X |
| 8604171186 | ORALB/BRAUN |
| 8604171187 | ARIEL |
| 8604171189 | GLT 吉列 |
| 8604171191 | CREST |
| 8604171192 | OLAY 歐蕾 |
| 8604171193 | WHSP 好自在 |
| 8604171199 | Hair Care（HS/PNTN/PERT/HR） |

排除：085804（一點絕）、065189（家樂氏）、203135

### KM_SELL JS 結構
```js
{
  weeks: ['20260601~20260607', ...],
  by_brand_qty: {ARIEL: [件數,...], ...},
  by_brand_amt: {ARIEL: [估算金額,...], ...},  // 件數 × 零售價
  by_sku: [{brand, name, barcode, retail, weeks:[件數], amt_weeks:[估算金額]}, ...]
}
```

### 零售價來源
`~/Downloads/康是美門市實銷資料*.xlsx` → sheet `2026實銷資料`
- col5 = 條碼，col10 = 零售價，col9 = 成本(含稅)
- 542 筆有價格，28 筆無（新品或獨家包裝）
- 新增 SKU 直接在這個 xlsx 補充即可

### DERP XLS 欄位結構（dsrDailySales）
每個品牌佔 4 欄：`箱數 | 含稅金額 | SU | GIV`
- **SU**（Standard Unit）= 標準單位出貨數，跟實銷件數同單位 → 可做消化率（待實作）

### 數字口徑對照
| 數字 | 來源 | 口徑 |
|---|---|---|
| 看板業績 | DERP dsrDailySales | 和清價，全通路 |
| 業績追踨XLS | 610.82 業務員銷售 | 和清價，業務管轄通路 |
| 康是美實銷件數 | 康是美供應商平台 | 消費者實際購買 |
| 康是美預估銷售額 | 件數 × 進貨價（xlsx成本含稅欄） | 寶捷出貨價視角；**不要用零售價**（2026-06-10 Wayne指正） |

## Session 記錄 2026-06-09（Hermes）

### 今天完成
1. **康是美頁面統一**：標籤/標題全改「康是美」，拿掉分點圖、分點數KPI，只保留分點明細表
2. **實銷翻頁修正**：改用頁碼select+wait_for_timeout(2000)，不用networkidle（背景請求太多會timeout）。HR=105筆/ARIEL=78筆，全部324筆完整
3. **SKU明細新增欄位**：估算收入、成本/件、估算毛利（收入-成本×件數，綠/紅色顯示）
4. **實銷改每週一抓**：`if _today.weekday() == 0` 才跑cosmed_fetch，其他天跳過，節省時間
5. **ANTHROPIC_API_KEY**：已用 `gh secret set` 自動加入GitHub secrets，workflow 週一可正常跑
6. **文字統一**：估算金額→估算收入

### 待處理
- CREST/ORALB/OLAY 部分SKU無成本資料（需補充xlsx）
- 消化率：DERP SU出貨數 ÷ 康是美實銷件數（待實作）
- 小北退步分店年達成（需要DERP YTD資料）

### 口徑備注（經銷商視角）
- 看板業績 = 和清價（寶捷實際收款）✓
- 成本/件 = 康是美實銷xlsx的「成本(含稅)」
- 估算毛利 = 估算收入 - 成本×件數（供參考，非精確P&L）
- GIV = P&G發票面額，對寶捷沒有直接管理意義

### cosmed_fetch.py 關鍵pitfall
- 翻頁用頁碼select（第三個select），不動page size select
- 翻頁等待用 `wait_for_timeout(2000)`，不用 `wait_for_load_state('networkidle')` 
- 頁碼select在查詢完才出現（初始只有1個select）
- barcode欄位可能含換行符（多條碼SKU），序列化時要 `.split('\n')[0]` 清掉
