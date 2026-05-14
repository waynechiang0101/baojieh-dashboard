#!/usr/bin/env python3
"""
DERP → Dashboard 自動更新
執行: python3 derp_fetch.py
"""
import requests, re, sys, subprocess
from datetime import date
from pathlib import Path
import urllib3
urllib3.disable_warnings()

# ── 設定 ──────────────────────────────────────────────
BASE_URL   = "https://gderp.titan.ebiz.tw/derp"
ACCOUNT_ID = "86041711"
DASHBOARD  = Path("/Users/wayne/Downloads/fmcg-v4-1/dashboard.html")
OUT_DIR    = Path("/Users/wayne/Wayne Agent/data")
OUT_DIR.mkdir(parents=True, exist_ok=True)

today   = date.today().strftime("%Y/%m/%d")
q_start = "2026/04/01"   # 季起始（可改）
m_start = "2026/04/01"
m_end   = "2026/04/30"


# ── Step 1: 從 agent-browser 取 JSESSIONID ─────────────
def get_session():
    try:
        result = subprocess.run(
            ["agent-browser", "cookies", "get", "--url", "https://gderp.titan.ebiz.tw"],
            capture_output=True, text=True, timeout=10
        )
        jsid = re.search(r'JSESSIONID=([A-F0-9]+)', result.stdout)
        if jsid:
            s = requests.Session()
            s.cookies.set('JSESSIONID', jsid.group(1), domain='gderp.titan.ebiz.tw', path='/')
            s.headers.update({
                'User-Agent': 'Mozilla/5.0',
                'Referer': f'{BASE_URL}/6.BR/derp-610-82.jsp'
            })
            print(f"✓ Session ({jsid.group(1)[:8]}...)")
            return s
    except Exception as e:
        pass
    print("✗ 請先用 Claude Code 登入 DERP（agent-browser open + login）")
    sys.exit(1)


# ── Step 2: 取得 610-82 的正確 form data ───────────────
def get_form_url(s):
    r = s.get(f"{BASE_URL}/6.BR/derp-610-82.jsp", verify=False, timeout=15)
    # 從頁面取到 box2View 的值（公司代號）
    m = re.search(r'name="box2View"[^>]*>.*?<option[^>]*value="([^"]+)"', r.text, re.DOTALL)
    company_id = m.group(1) if m else ACCOUNT_ID
    return company_id


# ── Step 3: 下載銷售日報表 (derp-610-82 → BizPlan/dsrDailySales) ─
def download_sales_report(s, date_start, date_end, label=""):
    print(f"\n下載銷售報表 {date_start} ~ {date_end} {label}...")

    params = {
        '*transDateStart': date_start, '*transDateEnd': date_end,
        '*itemNoStart': '', '*itemNoEnd': '',
        '*soldToCode': '', '*soldToCodeMerge': '',
        '*customerNo': '', 'customerNo': '', '*customerNoMerge': '',
        '*territoryCodeStart': '', '*territoryCodeStartName': '',
        '*territoryCodeEnd': '', '*territoryCodeEndName': '',
        '*dsrNoStart': '', '*dsrNoStartName': '',
        '*dsrNoEnd': '', '*dsrNoEndName': '',
        '*brandCodeStart': '', '*brandCodeStartName': '',
        '*brandCodeEnd': '', '*brandCodeEndName': '',
        '*acChannelCode': '', '*pgChannelCode': '',
        '*pageCmd': 'dsrDailySales',
        'closedType': 'closedNot',
        'dsrNoCredit': 'O',
        'reportRange': 'S',
        'reportRangeSelect': 'S',
        '*keySelected': f'{ACCOUNT_ID},',
        '*maxKeyValue': '', '*minKeyValue': '',
        '*rowsPerPage': '20', '*indexSelected': '',
    }

    r = s.get(f"{BASE_URL}/BizPlan/dsrDailySales", params=params, verify=False, timeout=120)
    fname = f"derp-sales-{date_start[:7].replace('/','-')}.xls"
    path = OUT_DIR / fname
    # 若今天已下載過就跳過
    if path.exists() and path.stat().st_size > 10000:
        from datetime import datetime
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if mtime.date() == date.today():
            print(f"  (使用快取: {fname})")
            return path
    path.write_bytes(r.content)
    size = len(r.content)
    print(f"✓ {size//1024}KB → {fname}")
    return path


# ── Step 4: 解析 XLS（binary格式）──────────────────────
def parse_sales_xls(path):
    import xlrd
    wb = xlrd.open_workbook(str(path))
    ws = wb.sheet_by_index(0)

    # 找 header row（含「總公司名稱」的那行）
    header_row = None
    for i in range(ws.nrows):
        row = [str(ws.cell_value(i, j)).strip() for j in range(min(ws.ncols, 20))]
        if '總公司名稱' in row or '店家名稱' in row:
            header_row = i
            headers = [str(ws.cell_value(i, j)).strip() for j in range(ws.ncols)]
            break

    if header_row is None:
        print("  ⚠ 找不到 header")
        return {}, {}, {}

    # 欄位索引
    def col(name): return next((i for i, h in enumerate(headers) if name in h), None)
    c_grp  = col('總公司名稱')
    c_store = col('店家名稱')
    c_rep  = col('業務代表')
    c_ac   = col('AC通路')
    c_amt  = col('合計')
    c_brand_start = 12  # 品牌金額從第12欄開始

    grp_data   = {}
    store_data = {}
    rep_data   = {}

    for i in range(header_row + 2, ws.nrows):
        try:
            def v(c): return str(ws.cell_value(i, c)).strip() if c is not None and c < ws.ncols else ''
            def n(c):
                val = ws.cell_value(i, c) if c is not None and c < ws.ncols else 0
                return float(val) if isinstance(val, (int, float)) else 0

            grp   = v(c_grp)
            store = v(c_store)
            rep   = v(c_rep)
            ac    = v(c_ac)
            amt   = n(c_amt)

            if not grp or amt <= 0:
                continue

            grp_data[grp] = grp_data.get(grp, 0) + amt
            if store:
                if store not in store_data:
                    store_data[store] = {'grp': grp, 'rep': rep.split('.')[1] if '.' in rep else rep, 'ch': ac, 'amt': 0}
                store_data[store]['amt'] += amt
            if rep:
                rep_name = rep.split('.')[1] if '.' in rep else rep
                if rep_name not in rep_data:
                    rep_data[rep_name] = {'code': rep.split('.')[0] if '.' in rep else rep, 'amt': 0}
                rep_data[rep_name]['amt'] += amt
        except:
            continue

    print(f"  集團:{len(grp_data)} 門市:{len(store_data)} 業務:{len(rep_data)}")
    return grp_data, store_data, rep_data


# ── Step 5: 更新 dashboard.html ─────────────────────────
def update_dashboard(grp_q, grp_m, store_q, store_m, rep_q):
    html = DASHBOARD.read_text(encoding='utf-8')

    # ── GRP ──
    grp_sorted = sorted(grp_q.items(), key=lambda x: -x[1])[:15]
    grp_lines = []
    for n, s5 in grp_sorted:
        s4 = int(grp_m.get(n, s5 * 0.85))
        grp_lines.append(f"  {{n:'{n.replace(chr(39),chr(96))}',s5:{int(s5)},s4:{s4}}}")
    grp_js = "const GRP=[\n" + ",\n".join(grp_lines) + "\n];"

    # ── STORES ──
    store_sorted = sorted(store_q.items(), key=lambda x: -x[1]['amt'])[:20]
    st_lines = []
    for name, d in store_sorted:
        v4 = int(store_m.get(name, {}).get('amt', d['amt'] * 0.85))
        st_lines.append(
            f"  {{s:'{name.replace(chr(39),chr(96))}',g:'{d['grp'].replace(chr(39),chr(96))}',"
            f"r:'{d['rep']}',ch:'{d['ch']}',v5:{int(d['amt'])},v4:{v4}}}"
        )
    store_js = "const STORES=[\n" + ",\n".join(st_lines) + "\n];"

    # 替換 JS 資料
    html = re.sub(r'const GRP=\[[\s\S]*?\];', grp_js, html)
    html = re.sub(r'const STORES=\[[\s\S]*?\];', store_js, html)

    # 更新頁面日期
    td = date.today().strftime("%Y/%m/%d")
    html = re.sub(r'\d{4}/\d{2}/\d{2} · 寶捷實業有限公司', f'{td} · 寶捷實業有限公司', html)
    html = re.sub(r'2026年\d+月（截至\d+/\d+）', f'{td[:4]}年{int(td[5:7])}月（截至{td[5:]}）', html)

    DASHBOARD.write_text(html, encoding='utf-8')
    print(f"\n✅ dashboard.html 已更新（{td}）")

    # 摘要
    print(f"\n  Top 5 集團:")
    for n, v in grp_sorted[:5]:
        print(f"    {n:<20} {v/1e6:.2f}M")
    print(f"\n  Top 5 門市:")
    for name, d in store_sorted[:5]:
        print(f"    {name:<30} {d['amt']/1e6:.2f}M")


# ── Main ────────────────────────────────────────────────
def main():
    print(f"\n{'='*52}")
    print(f"  DERP → Dashboard 自動更新 — {today}")
    print(f"{'='*52}")

    s = get_session()

    # 下載季累計（q_start → today）
    path_q = download_sales_report(s, q_start, today, "（季累計）")

    # 下載4月全月（比較基準）
    path_m = download_sales_report(s, m_start, m_end, "（4月全月）")

    print("\n解析資料...")
    grp_q, store_q, rep_q = parse_sales_xls(path_q)
    grp_m, store_m, rep_m = parse_sales_xls(path_m)

    if not grp_q:
        print("✗ 解析失敗")
        sys.exit(1)

    update_dashboard(grp_q, grp_m, store_q, store_m, rep_q)


if __name__ == "__main__":
    main()
