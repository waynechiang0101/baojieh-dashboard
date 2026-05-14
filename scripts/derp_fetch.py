#!/usr/bin/env python3
"""
DERP → Dashboard 全指標自動更新
更新: GRP, STORES, CHS, UNIF, REPS, PAYS, BRANDS, KPIs, IYA
"""
import os, re, sys, requests
from datetime import date
from pathlib import Path
import urllib3
urllib3.disable_warnings()

BASE_URL   = "https://gderp.titan.ebiz.tw/derp"
ACCOUNT_ID = "86041711"
DASHBOARD  = Path(__file__).parent.parent / "dashboard.html"

_today   = date.today()
_ly      = _today.replace(year=_today.year - 1)
today    = _today.strftime("%Y/%m/%d")
q_start  = f"{_today.year}/04/01"
mo_start = f"{_today.year}/{_today.month:02d}/01"
m_end    = f"{_today.year}/04/30"
ly_today  = _ly.strftime("%Y/%m/%d")
ly_qstart = f"{_ly.year}/04/01"
ly_mostart = f"{_ly.year}/{_ly.month:02d}/01"
ly_mend   = f"{_ly.year}/04/30"

# XLS 品牌金額欄位對照（col+1 才是含稅金額，col 本身是數量）
BRAND_COLS = {
    13:'PAMPS', 17:'WHSP', 21:'HS', 25:'PNTN', 29:'PERT', 33:'VS',
    37:'HR', 41:'OLAY', 45:'TIDE', 49:'ARIEL', 53:'BOLD', 57:'LENOR',
    61:'SARASA', 65:'FAIRY', 69:'FBRZ', 73:'JOY', 77:'GLT',
    81:'ORALB', 85:'CREST', 89:'BRAUN'
}
# 看板顯示品牌（b[] 順序 + 整體排行）
REP_BRANDS  = ['PAMPS', 'WHSP', 'OLAY', 'GLT', 'LENOR', 'ORALB']
DASH_BRANDS = ['PAMPS', 'WHSP', 'OLAY', 'GLT', 'ORALB', 'LENOR', 'FBRZ']

# 業務區域對照
AREA_MAP = {
    'MS032':'雲嘉','MS033':'雲嘉','MS035':'雲嘉',
    'MS006':'高屏','MS009':'高屏','MS023':'高屏',
    'MS026':'高屏','MS027':'高屏','MS013':'高屏',
    'MS030':'北部','MS001':'中部','MS002':'中部',
    'MS011':'中部','MS015':'中部','MS017':'其他',
    'MS031':'其他',
}


# ── Session ──────────────────────────────────────────────
def get_session():
    user = os.environ.get("DERP_USER", "user34")
    pwd  = os.environ.get("DERP_PASS", "user34")
    if os.environ.get("CI"):
        return _login_playwright(user, pwd)
    try:
        import subprocess
        r = subprocess.run(
            ["agent-browser","cookies","get","--url","https://gderp.titan.ebiz.tw"],
            capture_output=True, text=True, timeout=10)
        m = re.search(r'JSESSIONID=([A-F0-9]+)', r.stdout)
        if m:
            s = _make_session(m.group(1))
            rr = s.get(f"{BASE_URL}/6.BR/derp-610-82.jsp", verify=False, timeout=10)
            if "Sell" in rr.text or "610" in rr.text:
                print(f"✓ Session ({m.group(1)[:8]}...)")
                return s
    except: pass
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
    jsid = next((c["value"] for c in cookies if c["name"]=="JSESSIONID"), None)
    if not jsid: print("✗ 登入失敗"); sys.exit(1)
    print(f"✓ 登入 ({jsid[:8]}...)")
    return _make_session(jsid)

def _make_session(jsid):
    s = requests.Session()
    s.cookies.set("JSESSIONID", jsid, domain="gderp.titan.ebiz.tw", path="/")
    s.headers.update({"User-Agent":"Mozilla/5.0",
                      "Referer":f"{BASE_URL}/6.BR/derp-610-82.jsp"})
    return s


# ── 下載銷售日報（dsrDailySales）────────────────────────
def dl_sales(s, d0, d1, label):
    print(f"  {label} {d0}~{d1}...")
    params = {
        "*transDateStart":d0, "*transDateEnd":d1,
        "*itemNoStart":"","*itemNoEnd":"",
        "*soldToCode":"","*soldToCodeMerge":"",
        "*customerNo":"","customerNo":"","*customerNoMerge":"",
        "*territoryCodeStart":"","*territoryCodeStartName":"",
        "*territoryCodeEnd":"","*territoryCodeEndName":"",
        "*dsrNoStart":"","*dsrNoStartName":"",
        "*dsrNoEnd":"","*dsrNoEndName":"",
        "*brandCodeStart":"","*brandCodeStartName":"",
        "*brandCodeEnd":"","*brandCodeEndName":"",
        "*acChannelCode":"","*pgChannelCode":"",
        "*pageCmd":"dsrDailySales",
        "closedType":"closedNot","dsrNoCredit":"O",
        "reportRange":"S","reportRangeSelect":"S",
        "*keySelected":f"{ACCOUNT_ID},",
        "*maxKeyValue":"","*minKeyValue":"",
        "*rowsPerPage":"20","*indexSelected":"",
    }
    r = s.get(f"{BASE_URL}/BizPlan/dsrDailySales",
              params=params, verify=False, timeout=120)
    print(f"    ✓ {len(r.content)//1024}KB")
    return r.content


# ── 下載應收帳款（收款狀況）────────────────────────────
def dl_payment(s, d0, d1):
    print(f"  收款報表 {d0}~{d1}...")
    s.headers.update({"Referer":f"{BASE_URL}/4.FN/derp-421-00.jsp"})
    params = {
        "*customerNo":"","*customerName":"","*dsr":"","*dsrName":"",
        "*territoryCode":"","*territoryCodeName":"",
        "*customerNoMerge":"","*dsrNoMerge":"","*territoryMerge":"",
        "*deliveryDate":d0,"*deliveryDateEnd":d1,
        "offSetFlagSelect":"1","*offSetFlag":"1",
        "*queryRows":"","*pageMax":"","*pageOffset":"",
        "*rowsPerPage":"100","*pageIndex":"",
        "*soldToCode":"","*soldToCodeMerge":"",
        "*deliveryNo":"","*deliveryNoEnd":"",
        "buttonDsrPrint":"業務別收款總表by Excel(E)",
        "*pageCmd":"print",
    }
    r = s.get(f"{BASE_URL}/4.FN/derp-421-14-1.jsp",
              params=params, verify=False, timeout=60)
    print(f"    {'✓' if len(r.content)>5000 else '⚠'} {len(r.content)//1024}KB")
    return r.content if len(r.content) > 5000 else None


# ── 解析銷售 XLS（Binary）───────────────────────────────
def parse_xls(data):
    import xlrd
    wb = xlrd.open_workbook(file_contents=data)
    ws = wb.sheet_by_index(0)

    # 找 header row
    hdr = None
    for i in range(ws.nrows):
        row = [str(ws.cell_value(i,j)).strip() for j in range(min(ws.ncols,20))]
        if '總公司名稱' in row:
            hdr = i
            hdrs = [str(ws.cell_value(i,j)).strip() for j in range(ws.ncols)]
            break
    if hdr is None: return {}

    def col(nm): return next((i for i,h in enumerate(hdrs) if nm in h), None)
    ci = {k: col(k) for k in ['總公司名稱','店家名稱','業務代表','業代編號','AC通路','合計']}

    grp, store, ch, rep = {}, {}, {}, {}

    for i in range(hdr+2, ws.nrows):
        def v(c): return str(ws.cell_value(i,c)).strip() if c is not None and c<ws.ncols else ''
        def n(c):
            val = ws.cell_value(i,c) if c is not None and c<ws.ncols else 0
            return float(val) if isinstance(val,(int,float)) else 0

        g  = v(ci['總公司名稱'])
        st = v(ci['店家名稱'])
        r2 = v(ci['業務代表'])
        rc = v(ci['業代編號'])
        ac = v(ci['AC通路'])
        amt= n(ci['合計'])
        if not g or amt<=0: continue

        # 品牌金額
        brands = {b: n(c) for c,b in BRAND_COLS.items()}

        grp[g] = grp.get(g,0) + amt

        if st:
            if st not in store:
                rn = r2.split('.')[1] if '.' in r2 else r2
                store[st] = {'grp':g,'rep':rn,'ch':ac,'amt':0,'brands':{b:0 for b in BRAND_COLS.values()}}
            store[st]['amt'] += amt
            for b,bv in brands.items():
                store[st]['brands'][b] = store[st]['brands'].get(b,0)+bv

        ac_clean = ac.replace('大型','').replace('小型','').strip() if ac else '其他'
        ch[ac] = ch.get(ac,0)+amt

        if r2:
            rn = r2.split('.')[1] if '.' in r2 else r2
            if rn not in rep:
                area = AREA_MAP.get(rc,'')
                rep[rn] = {'code':rc,'area':area,'amt':0,'brands':{b:0 for b in BRAND_COLS.values()}}
            rep[rn]['amt'] += amt
            for b,bv in brands.items():
                rep[rn]['brands'][b] = rep[rn]['brands'].get(b,0)+bv

    return {'grp':grp,'store':store,'ch':ch,'rep':rep}


# ── 讀取本地收款 Excel（115-05收款.xls 格式）──────────
def parse_local_payment_xls():
    """
    讀 Downloads 最新的 115-XX收款.xls，格式：
    col0=業務代號.名稱, col1=MBO目標, col2=已達成, col5=GAP
    """
    import glob, xlrd
    pattern = os.path.expanduser("~/Downloads/115-??收款.xls")
    files = sorted(glob.glob(pattern))
    if not files:
        print("  ⚠ 找不到 115-XX收款.xls，跳過收款資料")
        return [], 0

    path = files[-1]  # 最新的
    print(f"  讀取: {os.path.basename(path)}")
    wb = xlrd.open_workbook(path)
    ws = wb.sheet_by_index(0)

    pays = []
    total_tgt = total_act = 0
    for i in range(2, ws.nrows):
        cell0 = str(ws.cell_value(i, 0)).strip()
        if not cell0 or cell0.lower() == 'total': continue
        m = re.match(r'MS\d+[. ]+(.+)', cell0)
        name = m.group(1).strip() if m else cell0
        tgt  = float(ws.cell_value(i, 1) or 0)
        act  = float(ws.cell_value(i, 2) or 0)
        gap  = tgt - act
        if tgt == 0 and act == 0: continue
        pays.append({'r': name, 'tgt': int(tgt), 'act': int(act), 'gap': int(gap)})
        total_tgt += tgt
        total_act += act

    uncollected = total_tgt - total_act
    print(f"  ✓ {len(pays)}人  未收款: ${uncollected/1e6:.1f}M")
    return pays, uncollected


# ── 更新 dashboard.html ──────────────────────────────────
def update_dashboard(q, m, mo, iya_q, iya_mo, pays_list, uncollected):
    html = DASHBOARD.read_text(encoding='utf-8')
    def esc(s): return s.replace("'","`")
    def fm(n): return f"${n/1e6:.1f}M"

    grp_q  = q.get('grp',{})
    grp_m  = m.get('grp',{})
    grp_mo = mo.get('grp',{})
    store_q= q.get('store',{})
    store_m= m.get('store',{})
    ch_q   = q.get('ch',{})
    ch_m   = m.get('ch',{})
    rep_q  = q.get('rep',{})
    rep_mo = mo.get('rep',{})
    rep_iya= iya_q.get('rep',{}) if iya_q else {}
    iya_grp= iya_q.get('grp',{}) if iya_q else {}
    iya_mo_grp = iya_mo.get('grp',{}) if iya_mo else {}

    total_q  = sum(grp_q.values())
    total_mo = sum(grp_mo.values())
    total_iya_q  = sum(iya_grp.values()) if iya_grp else 0
    total_iya_mo = sum(iya_mo_grp.values()) if iya_mo_grp else 0
    iya_pct  = round((total_q/total_iya_q-1)*100,1) if total_iya_q else 0
    cust_cnt = len(store_q)

    # ── KPI HTML ──
    def sub_kpi(label, val):
        nonlocal html
        html = re.sub(
            rf'(<div class="kl">{re.escape(label)}</div><div class="kv">)[^<]*(</div>)',
            rf'\g<1>{val}\g<2>', html)

    sub_kpi('P&G 本月業績', fm(total_mo))
    sub_kpi('季累計', fm(total_q))
    sub_kpi('交易客戶', f'{cust_cnt:,}')
    if iya_pct:
        sub_kpi('IYA 成長', f'+{iya_pct}%' if iya_pct>=0 else f'{iya_pct}%')
    if uncollected:
        sub_kpi('未收款', fm(uncollected))

    # ── GRP ──
    grp_s = sorted(grp_q.items(), key=lambda x:-x[1])[:15]
    lines = [f"  {{n:'{esc(n)}',s5:{int(s5)},s4:{int(grp_m.get(n,s5*.85))}}}"
             for n,s5 in grp_s]
    html = re.sub(r'const GRP=\[[\s\S]*?\];',
                  'const GRP=[\n'+',\n'.join(lines)+'\n];', html)

    # ── STORES ──
    st_s = sorted(store_q.items(), key=lambda x:-x[1]['amt'])[:20]
    lines = [
        f"  {{s:'{esc(n)}',g:'{esc(d['grp'])}',r:'{esc(d['rep'])}',ch:'{esc(d['ch'])}',"
        f"v5:{int(d['amt'])},v4:{int(store_m.get(n,{}).get('amt',d['amt']*.85))}}}"
        for n,d in st_s
    ]
    html = re.sub(r'const STORES=\[[\s\S]*?\];',
                  'const STORES=[\n'+',\n'.join(lines)+'\n];', html)

    # ── CHS（通路別）──
    ch_s = sorted(ch_q.items(), key=lambda x:-x[1])[:10]
    lines = [f"  {{n:'{esc(n)}',s5:{int(v)},s4:{int(ch_m.get(n,v*.85))}}}"
             for n,v in ch_s]
    html = re.sub(r'const CHS=\[[\s\S]*?\];',
                  'const CHS=[\n'+',\n'.join(lines)+'\n];', html)

    # ── UNIF（統一藥品門市）──
    unif_stores = {n:d for n,d in store_q.items() if '統一藥品' in d['grp']}
    unif_s = sorted(unif_stores.items(), key=lambda x:-x[1]['amt'])[:20]
    def unif_label(name):
        # "統一藥品股份有限公司 99 (中壢)" → "99(中壢)"
        m2 = re.search(r'(\d+)\s*[\(（]([^)\）]+)[\)）]', name)
        return f"{m2.group(1)}({m2.group(2)})" if m2 else name
    lines = [
        f"  {{s:'{unif_label(n)}',v5:{int(d['amt'])},v4:{int(store_m.get(n,{}).get('amt',d['amt']*.85))}}}"
        for n,d in unif_s
    ]
    if lines:
        html = re.sub(r'const UNIF=\[[\s\S]*?\];',
                      'const UNIF=[\n'+',\n'.join(lines)+'\n];', html)

    # ── BRANDS（品牌排行）──
    def brand_total(data_dict, brand):
        return sum(d.get('brands',{}).get(brand,0) for d in data_dict.get('store',{}).values())

    bapr  = [int(brand_total(m,  b)) for b in DASH_BRANDS]
    bmay  = [int(brand_total(mo, b)) for b in DASH_BRANDS]
    biya  = [int(brand_total(iya_q, b)) for b in DASH_BRANDS] if iya_q else bapr

    html = re.sub(r'const BAPR=\[[^\]]*\];',  f'const BAPR={bapr};',  html)
    html = re.sub(r'const BMAY=\[[^\]]*\];',  f'const BMAY={bmay};',  html)
    html = re.sub(r'const BIYA_=\[[^\]]*\];', f'const BIYA_={biya};', html)
    html = re.sub(r"const BRANDS=\[[^\]]*\];",
                  f"const BRANDS={[b for b in DASH_BRANDS]};", html)

    # ── REPS（業務排行）──
    # 保留現有 tgt / qT，只更新 act / iya / q / b[]
    existing_tgts = {}
    for m2 in re.finditer(r"\{n:'([^']+)'[^}]*tgt:(\d+)[^}]*qT:(\d+)", html):
        existing_tgts[m2.group(1)] = (int(m2.group(2)), int(m2.group(3)))

    rep_lines = []
    for rn, rd in sorted(rep_q.items(), key=lambda x:-x[1]['amt']):
        act   = int(rep_mo.get(rn,{}).get('amt',0))
        q_val = int(rd['amt'])
        iya   = int(rep_iya.get(rn,{}).get('amt',0)) if rep_iya else int(act*.9)
        tgt, qT = existing_tgts.get(rn, (0, 0))
        area  = rd.get('area','')
        bvals = [int(rd['brands'].get(b,0)) for b in REP_BRANDS]
        rep_lines.append(
            f"  {{n:'{esc(rn)}',area:'{area}',tgt:{tgt},act:{act},"
            f"iya:{iya},q:{q_val},qT:{qT},b:{bvals}}}"
        )
    if rep_lines:
        html = re.sub(r'const REPS=\[[\s\S]*?\];',
                      'const REPS=[\n'+',\n'.join(rep_lines)+'\n];', html)

    # ── PAYS（收款狀況，來自 115-XX收款.xls）──
    if pays_list:
        pay_lines = [
            f"  {{r:'{esc(p['r'])}',tgt:{p['tgt']},act:{p['act']},gap:{p['gap']}}}"
            for p in sorted(pays_list, key=lambda x: x['tgt']-x['act'], reverse=True)
        ]
        html = re.sub(r'const PAYS=\[[\s\S]*?\];',
                      'const PAYS=[\n'+',\n'.join(pay_lines)+'\n];', html)

    # ── 月業績趨勢（c0）：更新 4月 和 本月 資料點 ──
    apr_total = sum(m.get('grp',{}).values())    # 4月全月
    iya_apr   = sum(iya_q.get('grp',{}).values()) * (apr_total / total_q) if total_q else 0
    # 今年 data[4]=4月全月, data[5]=本月
    html = re.sub(
        r"(label:'今年',data:\[)([^\]]+)(\])",
        lambda mm: (
            mm.group(1) +
            ','.join(mm.group(2).split(',')[:-2] +
                     [str(int(apr_total)), str(int(total_mo))]) +
            mm.group(3)
        ), html)
    # 去年 data[4]=去年4月, data[5]=去年本月
    iya_apr_total  = sum(iya_q.get('grp',{}).values()) - sum(iya_mo.get('grp',{}).values()) if iya_q else 0
    iya_mo_total   = sum(iya_mo.get('grp',{}).values()) if iya_mo else 0
    html = re.sub(
        r"(label:'去年',data:\[)([^\]]+)(\])",
        lambda mm: (
            mm.group(1) +
            ','.join(mm.group(2).split(',')[:-2] +
                     [str(int(iya_apr_total)), str(int(iya_mo_total))]) +
            mm.group(3)
        ), html)

    # ── 通路圓餅（c1 overview）：更新成實際 CHS 資料 ──
    top6_ch = sorted(ch_q.items(), key=lambda x:-x[1])[:5]
    others  = sum(v for n,v in sorted(ch_q.items(), key=lambda x:-x[1])[5:])
    ch_labels = str([n for n,_ in top6_ch] + ['其他']).replace('"',"'")
    ch_data   = [int(v) for _,v in top6_ch] + [int(others)]
    html = re.sub(
        r"(labels:\[(?:'[^']*',?\s*){3,8}\],\s*\n?\s*datasets:\[{data:\[)[\d,\s]+(])",
        lambda mm: mm.group(1) + ','.join(str(x) for x in ch_data) + mm.group(2),
        html, count=1)

    # ── REPS：只保留有目標的業務在達成率圖 ──
    # 劉暄芸等沒有 tgt 的業務改放最後，tgt 為 0 的在 JS 端以 'N/A' 顯示
    # （JS 層 Math.round(NaN) = NaN → Chart.js 自動略過，不會顯示錯誤 bar）

    # ── 日期 ──
    td = _today.strftime("%Y/%m/%d")
    mo_lbl = _today.strftime("%m/%d")
    html = re.sub(r'\d{4}/\d{2}/\d{2} · 寶捷實業有限公司',
                  f'{td} · 寶捷實業有限公司', html)
    html = re.sub(r'\d{4}年\d+月（截至\d+/\d+）',
                  f'{_today.year}年{_today.month}月（截至{mo_lbl}）', html)

    DASHBOARD.write_text(html, encoding='utf-8')

    print(f"\n✅ {td} 全指標更新完成")
    print(f"   本月:{fm(total_mo)}  季累計:{fm(total_q)}  "
          f"IYA:{iya_pct:+.1f}%  交易客戶:{cust_cnt:,}")
    print(f"   通路:{len(ch_s)}種  統一藥品門市:{len(unif_s)}點  業務:{len(rep_lines)}人")


# ── Main ─────────────────────────────────────────────────
def main():
    print(f"\n{'='*52}\n  DERP → Dashboard 全指標更新  {today}\n{'='*52}\n")
    s = get_session()

    print("[下載 本期]")
    data_q  = dl_sales(s, q_start,  today,    "季累計")
    data_mo = dl_sales(s, mo_start, today,    "本月")
    data_m  = dl_sales(s, q_start,  m_end,    "4月全月")

    print("\n[下載 去年同期 IYA]")
    data_iya_q  = dl_sales(s, ly_qstart,  ly_today,  "去年季累計")
    data_iya_mo = dl_sales(s, ly_mostart, ly_today,  "去年本月")

    print("\n[收款 Excel]")

    print("\n[解析]")
    q   = parse_xls(data_q);   print(f"  季累計  → 集團:{len(q.get('grp',{}))} 門市:{len(q.get('store',{}))} 業務:{len(q.get('rep',{}))}")
    mo  = parse_xls(data_mo);  print(f"  本月    → 集團:{len(mo.get('grp',{}))}")
    m   = parse_xls(data_m);   print(f"  4月全月 → 集團:{len(m.get('grp',{}))}")
    iya_q  = parse_xls(data_iya_q);  print(f"  去年季  → 集團:{len(iya_q.get('grp',{}))}")
    iya_mo = parse_xls(data_iya_mo); print(f"  去年月  → 集團:{len(iya_mo.get('grp',{}))}")
    pays_list, uncollected = parse_local_payment_xls()

    if not q.get('grp'):
        print("✗ 解析失敗"); sys.exit(1)

    update_dashboard(q, m, mo, iya_q, iya_mo, pays_list, uncollected)


if __name__ == "__main__":
    main()
