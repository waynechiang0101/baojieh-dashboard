#!/usr/bin/env python3
"""
DERP → Dashboard 自動更新
本地: python3 scripts/derp_fetch.py
CI:   DERP_USER / DERP_PASS 環境變數由 GitHub Secrets 帶入
"""
import os, re, sys, requests
from datetime import date
from pathlib import Path
import urllib3
urllib3.disable_warnings()

BASE_URL   = "https://gderp.titan.ebiz.tw/derp"
ACCOUNT_ID = "86041711"
DASHBOARD  = Path(__file__).parent.parent / "dashboard.html"

_today  = date.today()
today   = _today.strftime("%Y/%m/%d")
q_start = f"{_today.year}/04/01"
mo_start = f"{_today.year}/{_today.month:02d}/01"
m_end   = f"{_today.year}/04/30"


# ── Session ──────────────────────────────────────────────
def get_session():
    user = os.environ.get("DERP_USER", "user34")
    pwd  = os.environ.get("DERP_PASS", "user34")

    if os.environ.get("CI"):
        return _login_playwright(user, pwd)

    try:
        import subprocess
        result = subprocess.run(
            ["agent-browser", "cookies", "get", "--url", "https://gderp.titan.ebiz.tw"],
            capture_output=True, text=True, timeout=10
        )
        jsid = re.search(r'JSESSIONID=([A-F0-9]+)', result.stdout)
        if jsid:
            s = _make_session(jsid.group(1))
            r = s.get(f"{BASE_URL}/6.BR/derp-610-82.jsp", verify=False, timeout=10)
            if "610-82" in r.text or "Sell" in r.text:
                print(f"✓ Session ({jsid.group(1)[:8]}...)")
                return s
    except:
        pass

    return _login_playwright(user, pwd)


def _login_playwright(user, pwd):
    from playwright.sync_api import sync_playwright
    print(f"  Playwright 登入 ({user})...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{BASE_URL}/PC.sys", timeout=30000)
        page.fill('[name="*userID"]', user)
        page.fill('[name="*password"]', pwd)
        page.click('[name="login"]')
        page.wait_for_load_state("networkidle", timeout=20000)
        cookies = page.context.cookies()
        browser.close()
    jsid = next((c["value"] for c in cookies if c["name"] == "JSESSIONID"), None)
    if not jsid:
        print("✗ 登入失敗"); sys.exit(1)
    print(f"✓ 登入成功 ({jsid[:8]}...)")
    return _make_session(jsid)


def _make_session(jsid):
    s = requests.Session()
    s.cookies.set("JSESSIONID", jsid, domain="gderp.titan.ebiz.tw", path="/")
    s.headers.update({"User-Agent": "Mozilla/5.0",
                      "Referer": f"{BASE_URL}/6.BR/derp-610-82.jsp"})
    return s


# ── 下載銷售報表 ──────────────────────────────────────────
def download_report(s, date_start, date_end, label=""):
    print(f"  {label} ({date_start}~{date_end})...")
    params = {
        "*transDateStart": date_start, "*transDateEnd": date_end,
        "*itemNoStart": "", "*itemNoEnd": "",
        "*soldToCode": "", "*soldToCodeMerge": "",
        "*customerNo": "", "customerNo": "", "*customerNoMerge": "",
        "*territoryCodeStart": "", "*territoryCodeStartName": "",
        "*territoryCodeEnd": "", "*territoryCodeEndName": "",
        "*dsrNoStart": "", "*dsrNoStartName": "",
        "*dsrNoEnd": "", "*dsrNoEndName": "",
        "*brandCodeStart": "", "*brandCodeStartName": "",
        "*brandCodeEnd": "", "*brandCodeEndName": "",
        "*acChannelCode": "", "*pgChannelCode": "",
        "*pageCmd": "dsrDailySales",
        "closedType": "closedNot", "dsrNoCredit": "O",
        "reportRange": "S", "reportRangeSelect": "S",
        "*keySelected": f"{ACCOUNT_ID},",
        "*maxKeyValue": "", "*minKeyValue": "",
        "*rowsPerPage": "20", "*indexSelected": "",
    }
    r = s.get(f"{BASE_URL}/BizPlan/dsrDailySales", params=params,
              verify=False, timeout=120)
    print(f"  ✓ {len(r.content)//1024}KB")
    return r.content


# ── 解析 XLS ─────────────────────────────────────────────
def parse_xls(data):
    import xlrd
    wb = xlrd.open_workbook(file_contents=data)
    ws = wb.sheet_by_index(0)

    header_row = None
    for i in range(ws.nrows):
        row = [str(ws.cell_value(i, j)).strip() for j in range(min(ws.ncols, 20))]
        if "總公司名稱" in row:
            header_row = i
            headers = [str(ws.cell_value(i, j)).strip() for j in range(ws.ncols)]
            break

    if header_row is None:
        return {}, {}, {}

    def col(name): return next((i for i, h in enumerate(headers) if name in h), None)
    c_grp, c_store, c_rep = col("總公司名稱"), col("店家名稱"), col("業務代表")
    c_ac, c_amt = col("AC通路"), col("合計")

    grp, store, rep = {}, {}, {}
    for i in range(header_row + 2, ws.nrows):
        try:
            def v(c): return str(ws.cell_value(i, c)).strip() if c is not None and c < ws.ncols else ""
            def n(c):
                val = ws.cell_value(i, c) if c is not None and c < ws.ncols else 0
                return float(val) if isinstance(val, (int, float)) else 0

            g, st, r2, ac, amt = v(c_grp), v(c_store), v(c_rep), v(c_ac), n(c_amt)
            if not g or amt <= 0: continue

            grp[g] = grp.get(g, 0) + amt
            if st:
                if st not in store:
                    store[st] = {"grp": g, "rep": r2.split(".")[1] if "." in r2 else r2,
                                 "ch": ac, "amt": 0}
                store[st]["amt"] += amt
            if r2:
                rn = r2.split(".")[1] if "." in r2 else r2
                rep[rn] = rep.get(rn, 0) + amt
        except:
            continue

    return grp, store, rep


# ── 更新 dashboard.html ──────────────────────────────────
def update_dashboard(grp_q, grp_m, store_q, store_m, total_mo, total_q, cust_count):
    html = DASHBOARD.read_text(encoding="utf-8")
    def esc(s): return s.replace("'", "`")
    def fm(n): return f"${n/1e6:.1f}M"

    # ── GRP（集團排行）──
    grp_sorted = sorted(grp_q.items(), key=lambda x: -x[1])[:15]
    lines = [f"  {{n:'{esc(n)}',s5:{int(s5)},s4:{int(grp_m.get(n, s5*0.85))}}}"
             for n, s5 in grp_sorted]
    html = re.sub(r"const GRP=\[[\s\S]*?\];",
                  "const GRP=[\n" + ",\n".join(lines) + "\n];", html)

    # ── STORES（門市排行）──
    store_sorted = sorted(store_q.items(), key=lambda x: -x[1]["amt"])[:20]
    lines = [
        f"  {{s:'{esc(n)}',g:'{esc(d['grp'])}',r:'{esc(d['rep'])}',ch:'{esc(d['ch'])}',"
        f"v5:{int(d['amt'])},v4:{int(store_m.get(n, {}).get('amt', d['amt']*0.85))}}}"
        for n, d in store_sorted
    ]
    html = re.sub(r"const STORES=\[[\s\S]*?\];",
                  "const STORES=[\n" + ",\n".join(lines) + "\n];", html)

    # ── KPI 頂部數字 ──
    # P&G 本月業績
    html = re.sub(
        r'(<div class="kl">P&amp;G 本月業績</div><div class="kv">)[^<]*(</div>)',
        rf'\g<1>{fm(total_mo)}\g<2>', html)
    # 季累計
    html = re.sub(
        r'(<div class="kl">季累計</div><div class="kv">)[^<]*(</div>)',
        rf'\g<1>{fm(total_q)}\g<2>', html)
    # 交易客戶
    html = re.sub(
        r'(<div class="kl">交易客戶</div><div class="kv">)[^<]*(</div>)',
        rf'\g<1>{int(cust_count):,}\g<2>', html)

    # ── 日期 ──
    td = _today
    td_str = td.strftime("%Y/%m/%d")
    mo_label = td.strftime("%m/%d")
    html = re.sub(r'\d{4}/\d{2}/\d{2} · 寶捷實業有限公司',
                  f'{td_str} · 寶捷實業有限公司', html)
    html = re.sub(r'\d{4}年\d+月（截至\d+/\d+）',
                  f'{td.year}年{td.month}月（截至{mo_label}）', html)

    DASHBOARD.write_text(html, encoding="utf-8")
    print(f"\n✅ {td_str} 更新完成")
    print(f"   本月: {fm(total_mo)}  季累計: {fm(total_q)}  交易客戶: {cust_count:,}")
    print(f"   Top3: {', '.join(n.split('(')[0].strip() for n, _ in grp_sorted[:3])}")


# ── Main ─────────────────────────────────────────────────
def main():
    print(f"\n{'='*50}\n  DERP → Dashboard  {today}\n{'='*50}\n")

    s = get_session()

    print("[下載]")
    data_q  = download_report(s, q_start,  today,    "季累計")
    data_mo = download_report(s, mo_start, today,    "本月")
    data_m  = download_report(s, q_start,  m_end,    "4月全月")

    print("\n[解析]")
    grp_q,  store_q,  _ = parse_xls(data_q)
    grp_mo, _,        _ = parse_xls(data_mo)
    grp_m,  store_m,  _ = parse_xls(data_m)

    if not grp_q:
        print("✗ 解析失敗"); sys.exit(1)

    total_q  = sum(grp_q.values())
    total_mo = sum(grp_mo.values())
    cust_count = len(store_q)

    update_dashboard(grp_q, grp_m, store_q, store_m, total_mo, total_q, cust_count)


if __name__ == "__main__":
    main()
