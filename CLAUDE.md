# 寶捷實業業績看板 — Claude 工作手冊

## 專案概覽
- **網址**: https://baojieh-dashboard.pages.dev/dashboard.html
- **GitHub**: https://github.com/waynechiang0101/baojieh-dashboard
- **部署**: Cloudflare Pages — git push 自動觸發部署，無需手動 deploy
- **資料來源**: DERP ERP (https://gderp.titan.ebiz.tw/derp), 帳號 user34

## 自動化流程
GitHub Actions 每個工作日 17:00（台灣）自動執行：
1. 登入 DERP → 下載本月/季累計/去年同期/庫存
2. 從 DERP 計算通路明細（不需要 XLS）
3. 更新 dashboard.html → git push
4. 用 zip API 直接部署到 Netlify（不耗 build credit）

## 手動更新指令
```bash
python3 scripts/derp_fetch.py
```
資料來源 100% 為 DERP，不讀本地 XLS。

## 部署到 Netlify（手動）
```python
import json, zipfile, requests
token = json.load(open('/Users/wayne/Library/Preferences/netlify/config.json'))
# ... 見 deploy 函式
```
或直接用腳本跑完後 commit + push，GitHub Actions 會接手部署。

## 關鍵檔案
- `dashboard.html` — 單頁看板（所有資料內嵌 JS）
- `scripts/derp_fetch.py` — 主更新腳本（DERP 登入、解析、寫 HTML）
- `.github/workflows/update-dashboard.yml` — 自動化排程

## 資料結構（dashboard.html 內的 JS）
| 變數 | 說明 |
|---|---|
| `GRP` | 集團排行，本月順序，含 s3/s4/s5/iya/iya3/br |
| `STORES` | 個別門市 Top100，含 v3/v4/v5/iy3/iy5/br |
| `UNIF` | 康是美分點，含 v3/v4/v5/iy3/iy5/br |
| `CVS_STORES` | CVS 便利商店門市 |
| `XB_STORES` | 小北各分店 |
| `REPS` | 業務代表績效 |
| `PAYS` | 收款資料（from 115-XX收款*.xls，抓最新修改的檔） |
| `INV_BRANDS` | 庫存（from DERP 327-50.jsp 約45MB） |
| `XLS_BIZ` | 通路明細（業務直銷：藥房/超市/丁丁/大樹/小北/啄木鳥/B&C） |
| `XLS_DIRECT` | 通路明細（直送：康是美/全家/7-11/萊爾富/OK） |
| `XLS_TOTAL` | P&G Total 本月 |

## 重要業務邏輯
- **P&G 本月業績** = XLS P&G Total（若無 XLS 則用 DERP total_mo）
- **排序** = 全部按本月（v3/s3）降冪排列，不是季累計
- **IYA** = iy5（季）和 iy3（本月）分別 vs 去年同期
- DERP total_mo 比 XLS 多約 $1-2M（因包含 OMD/ETC 特殊帳）

## DERP 關鍵集團名稱對應
| 通路 | DERP 集團名稱 |
|---|---|
| 康是美 | 統一藥品股份有限公司(總公司) |
| 捷盟(7-11) | 捷盟-總公司 |
| 全台(全家) | 全台物流-總公司 |
| 大樹 | A01-大樹 |
| 丁丁 | A02-丁丁 |
| 啄木鳥 | A03-啄木鳥 |
| 小北 | 小北（多集團，加總） |

## DERP API
- **dsrDailySales**: 業績 XLS（門市×品牌×通路）
- **327-50.jsp**: 庫存 HTML-XLS（~45MB streaming）
- **登入**: POST to CCderp.jsp with accountID=86041711, dataOwner='CVS-7,CVS-HL,CVS-OK,CVS-FM,ETC,OMD,COSMED,DMC,CVS-7N'

## 已知問題 / 待辦
- 劉暄芸 tgt=0（無月目標，業務達成率顯示 N/A）
- 月趨勢圖 12月-3月 為估算值，非 DERP 實際數字
- Netlify build credit 已耗盡，改用 zip API 部署

## 常見操作

### 更新數字 + 部署
```bash
python3 scripts/derp_fetch.py
git add dashboard.html && git commit -m "更新" && git push
```
Cloudflare Pages 連 GitHub，push 後自動部署，約 1 分鐘上線。不需要手動 deploy。

### 只重新部署（不更新數字）
用 Netlify API zip 上傳，見 scripts/derp_fetch.py 末段邏輯。
