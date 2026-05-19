# 寶捷實業業績看板 — Hermes Agent 交接文件

## 你負責維護什麼
寶捷實業（P&G 經銷商）的業績自動化看板，每天從 DERP ERP 抓資料更新。

- **看板網址**: https://bjworks.netlify.app/dashboard.html
- **GitHub**: https://github.com/waynechiang0101/baojieh-dashboard
- **本地路徑**: /Users/wayne/Downloads/fmcg-v4-1/

## 每天自動更新流程
GitHub Actions 每個工作日 17:00（台灣）自動跑，完全不需要人工：
1. 登入 DERP → 下載本月/季累計/去年同期/庫存
2. 從 DERP 計算所有通路業績（康是美/捷盟7-11/全台全家/藥房/超市...）
3. 更新 dashboard.html → git push → 自動部署到 Netlify

## 手動更新（Wayne 給新 XLS 時）
```bash
# Wayne 把最新業績追踨.xls 放進 ~/Downloads 後：
python3 scripts/derp_fetch.py
git add dashboard.html && git commit -m "更新" && git push
```
腳本自動讀最新 XLS 並覆蓋通路數字，再部署到 Netlify。

## 關鍵檔案
| 檔案 | 說明 |
|---|---|
| `dashboard.html` | 單頁看板（所有資料內嵌 JS，直接部署） |
| `scripts/derp_fetch.py` | 主更新腳本 |
| `.github/workflows/update-dashboard.yml` | 每日排程 |
| `CLAUDE.md` | 技術細節手冊 |

## DERP 系統
- URL: https://gderp.titan.ebiz.tw/derp
- 帳號: user34 / 密碼: user34（或讀環境變數 DERP_USER/DERP_PASS）
- AccountID: 86041711
- DataOwner: CVS-7,CVS-HL,CVS-OK,CVS-FM,ETC,OMD,COSMED,DMC,CVS-7N

## Netlify 部署
- Site ID: 425e94c7-d4a5-478e-a10c-a7205fa69c21
- Token: 在 ~/Library/Preferences/netlify/config.json
- 用 zip API 部署（不耗 build credit）
- GitHub Secrets 已設好 NETLIFY_AUTH_TOKEN + NETLIFY_SITE_ID

## 看板頁面結構
| 頁面 | 說明 |
|---|---|
| 業績總覽 | P&G Total、通路明細表（XLS_BIZ/XLS_DIRECT）、趨勢圖 |
| 集團排行 | GRP，按本月排序，含本月IYA/季IYA/品牌Top3 |
| 個別門市 | STORES Top100，按本月排序 |
| 康是美 | UNIF（統一藥品分點），按本月排序 |
| CVS | CVS_STORES（便利商店），按本月排序 |
| 小北 | XB_STORES，按本月排序 |
| 通路分析 | CHS 各通路季累計 |
| 業務績效 | REPS 業務達成率 |
| 品牌業績 | BRANDS 各品牌本月/4月/季累計 |
| IYA 對比 | 去年同期比較 |
| 收款追蹤 | PAYS（from 115-05收款.xls） |
| 公司庫存 | INV_BRANDS（from DERP 327-50.jsp ~45MB） |

## 資料欄位說明
- `v3` = 本月累積, `v4` = 4月全月, `v5` = 季累計（4/1起）
- `iy3` = 去年本月, `iy5` = 去年同季
- `s3/s4/s5/iya/iya3/br` = GRP 用的欄位（同上意義）
- `br` = 品牌Top5 `[{b:'PAMPS',v:123456},...]`

## 常見問題處理

### 數字沒更新
1. 檢查 GitHub Actions 是否成功：`gh run list --repo waynechiang0101/baojieh-dashboard`
2. 若失敗，手動跑：`python3 scripts/derp_fetch.py`

### DERP session 過期
腳本會自動 POST 登入，不需要手動處理。若持續失敗檢查帳密。

### Netlify 沒更新
GitHub Actions 最後一步會用 zip API 推到 Netlify。若沒推到，檢查 NETLIFY_AUTH_TOKEN secret 是否有效。

## 業務背景
- Wayne Chiang 是寶捷實業負責人，代理 P&G 產品
- 主要通路：康是美（最大，約 42M/月）、藥房業務、超市業務
- 業績季節：Q2（4月-6月）是旺季
- IYA（Index Year Ago）= 本期 vs 去年同期
- XLS 業績追踨 是業務助理手動整理的報表，比 DERP 少約 $1-2M（DERP 含特殊帳）
