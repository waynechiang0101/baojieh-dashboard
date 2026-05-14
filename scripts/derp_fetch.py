#!/usr/bin/env python3
"""
DERP → Dashboard 全指標自動更新
更新: GRP, STORES, KM, CVS, XB, CHS, REPS, PAYS, BRANDS, KPIs, IYA
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

BRAND_COLS = {
    13:'PAMPS', 17:'WHSP', 21:'HS', 25:'PNTN', 29:'PERT', 33:'VS',
    37:'HR', 41:'OLAY', 45:'TIDE', 49:'ARIEL', 53:'BOLD', 57:'LENOR',
    61:'SARASA', 65:'FAIRY', 69:'FBRZ', 73:'JOY', 77:'GLT',
    81:'ORALB', 85:'CREST', 89:'BRAUN'
}
REP_BRANDS  = ['PAMPS', 'WHSP', 'OLAY', 'GLT', 'LENOR', 'ORALB']
DASH_BRANDS = ['PAMPS', 'WHSP', 'OLAY', 'GLT', 'ORALB', 'LENOR', 'FBRZ']

AREA_MAP = {
    'MS032':'雲嘉','MS033':'雲嘉','MS035':'雲嘉',
    'MS006':'高屏','MS009':'高屏','MS023':'高屏',
    'MS026':'高屏','MS027':'高屏','MS013':'高屏',
    'MS030':'北部','MS001':'中部','MS002':'中部',
    'MS011':'中部','MS015':'中部','MS017':'其他',
    'MS031':'其他',
}

BRAND_NAMES = {
    'PAMPS':'幫寶適','WHSP':'好自在','HS':'海倫仙度絲','PNTN':'潘婷',
    'HR':'赫本','OLAY':'玉蘭油','FBRZ':'風倒','ORALB':'歐樂B',
    'GLT':'吉列','LENOR':'蘭諾','ARIEL':'碧浪','PERT':'飛柔',
    'BRAUN':'百靈','CREST':'Crest','BOLD':'潮','TIDE':'汰漬',
    'VS':'沙宣','JOY':'Joy','FAIRY':'Fairy','SARASA':'Sarasa',
}
SKIP_INV_BRANDS = {'SAMPLE','POSM','OTHER','GIFT','DISPLAY',''}

def _wh_group(wh):
    if '台南' in wh: return 'tainan'
    if '高雄' in wh: return 'kaohsiung'
    if 'TP' in wh or '台北' in wh: return 'tp'
    if '康是美' in wh: return 'km'
    if 'CVS' in wh: return 'cvs'
    return 'other'


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


# ── 下載銷售日報 ──────────────────────────────────────────
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


# ── 解析銷售 XLS ─────────────────────────────────────────
def parse_xls(data):
    import xlrd
    wb = xlrd.open_workbook(file_contents=data)
    ws = wb.sheet_by_index(0)

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


# ── 庫存：POST 登入 + 下載 + 解析 ───────────────────────
def get_web_session():
    ws = requests.Session()
    ws.headers.update({'User-Agent':'Mozilla/5.0'})
    r = ws.post(f'{BASE_URL}/CCderp.jsp', verify=False, timeout=30, data={
        '*userID': os.environ.get("DERP_USER","user34"),
        '*password': os.environ.get("DERP_PASS","user34"),
        '*accountID': ACCOUNT_ID,
        '*dataOwner': 'CVS-7,CVS-HL,CVS-OK,CVS-FM,ETC,OMD,COSMED,DMC,CVS-7N',
        '*requestURL': f'{BASE_URL}/PC.sys',
        '*loginTemplate':'Login.html','*menuTemplate':'indexBlank.html',
        '*pageCmd':'Login','execCode':'0','execMsg':'','actionCode':'0',
        'focusField':'','urlAlter':'','urlYes':'','urlNo':''
    })
    jsid = ws.cookies.get('JSESSIONID','')
    print(f"  Web session: {'✓' if jsid else '✗'} {jsid[:8] if jsid else ''}...")
    return ws if jsid else None

def dl_inventory(ws):
    import tempfile
    params = {
        '*pageCmd':'print','*sortType':'4','*sort':'0',
        '*ABCClass':'','*barcode':'','*itemNo':'','*itemDesc':'',
        '*warehouse':'','*warehouseMerge':'','*categoryCode':'','*categoryCodeMerge':'',
        '*brandCode':'','*brandCodeMerge':'','*idleDay':'','*inventoryDay':'',
        '*invQueryType':'0','*rowsPerPage':'500','linePerPage':'25',
        '*indexSelected':'','*keySelected':'','*derpPage':'derp-327-00',
        'execCode':'0','execMsg':'','actionCode':'0',
        'focusField':'','urlAlter':'','urlYes':'','urlNo':'',
        'accountID':ACCOUNT_ID,'userID':'user34','appSysName':'derp'
    }
    print("  下載庫存報表 (streaming ~45MB)...")
    try:
        r = ws.get(f'{BASE_URL}/3.IN/derp-327-50.jsp',
                   params=params, verify=False, timeout=(30, 600), stream=True,
                   headers={'Referer':f'{BASE_URL}/3.IN/derp-327-00.jsp'})
        tmp = tempfile.mktemp(suffix='.html')
        total = 0
        with open(tmp,'wb') as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
                total += len(chunk)
        print(f"    ✓ {total/1024/1024:.1f}MB")
        return tmp
    except Exception as e:
        print(f"    ⚠ 庫存下載失敗: {e}")
        return None

def parse_inventory_html(path):
    from collections import defaultdict
    with open(path,'rb') as f:
        content = f.read().decode('utf-8', errors='replace')
    rows = re.findall(r'<TR[^>]*>(.*?)</TR>', content, re.I|re.S)
    brands = defaultdict(lambda: {
        'qty':0,'amt':0,'tainan':0,'kaohsiung':0,'tp':0,'km':0,'cvs':0,'other':0,
        'skus':{}
    })
    for row in rows[6:]:
        cells = re.findall(r'<T[DH][^>]*>(.*?)</T[DH]>', row, re.I|re.S)
        cleaned = [re.sub(r'<[^>]+>','',c).strip() for c in cells]
        if len(cleaned) < 16: continue
        sku, name, brand, wh = cleaned[0], cleaned[2], cleaned[4], cleaned[5]
        if brand in SKIP_INV_BRANDS or '合計' in sku: continue
        try:
            qty = float(cleaned[11])
            amt = float(cleaned[15])
        except: continue
        if qty <= 0: continue
        g = _wh_group(wh)
        b = brands[brand]
        b['qty'] += qty; b['amt'] += amt; b[g] += amt
        if sku not in b['skus']:
            b['skus'][sku] = {'name': name[:30], 'qty':0, 'amt':0}
        b['skus'][sku]['qty'] += qty
        b['skus'][sku]['amt'] += amt
    result = []
    for code, d in sorted(brands.items(), key=lambda x:-x[1]['amt']):
        skus = d['skus']
        topQ = sorted(skus.items(), key=lambda x:-x[1]['qty'])[:5]
        topA = sorted(skus.items(), key=lambda x:-x[1]['amt'])[:5]
        result.append({
            'code':code, 'label':BRAND_NAMES.get(code,code),
            'qty':int(d['qty']), 'amt':int(d['amt']),
            'tainan':int(d['tainan']), 'kaohsiung':int(d['kaohsiung']),
            'tp':int(d['tp']), 'km':int(d['km']), 'cvs':int(d['cvs']),
            'topQ':[{'s':k,'n':v['name'],'q':int(v['qty']),'a':int(v['amt'])} for k,v in topQ],
            'topA':[{'s':k,'n':v['name'],'q':int(v['qty']),'a':int(v['amt'])} for k,v in topA],
        })
    total_amt = sum(d['amt'] for d in result)
    print(f"  ✓ 庫存: {len(result)} 品牌  ${total_amt/1e6:.1f}M")
    return result


# ── 讀取本地收款 Excel ────────────────────────────────────
def parse_local_payment_xls():
    import glob, xlrd
    pattern = os.path.expanduser("~/Downloads/115-??收款.xls")
    files = sorted(glob.glob(pattern))
    if not files:
        print("  ⚠ 找不到 115-XX收款.xls，跳過收款資料")
        return [], 0

    path = files[-1]
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
def update_dashboard(q, m, mo, iya_q, iya_mo, pays_list, uncollected, inv_data=None):
    html = DASHBOARD.read_text(encoding='utf-8')
    def esc(s): return s.replace("'","`")
    def fm(n): return f"${n/1e6:.1f}M"

    grp_q   = q.get('grp',{})
    grp_mo  = mo.get('grp',{})
    grp_m   = m.get('grp',{})
    store_q = q.get('store',{})
    store_m = m.get('store',{})
    ch_q    = q.get('ch',{})
    ch_m    = m.get('ch',{})
    rep_q   = q.get('rep',{})
    rep_mo  = mo.get('rep',{})
    rep_iya = iya_q.get('rep',{}) if iya_q else {}
    iya_grp = iya_q.get('grp',{}) if iya_q else {}
    iya_mo_grp = iya_mo.get('grp',{}) if iya_mo else {}

    total_q      = sum(grp_q.values())
    total_mo     = sum(grp_mo.values())
    total_iya_q  = sum(iya_grp.values()) if iya_grp else 0
    total_iya_mo = sum(iya_mo_grp.values()) if iya_mo_grp else 0
    iya_pct      = round((total_q/total_iya_q-1)*100,1) if total_iya_q else 0
    iya_mo_pct   = round((total_mo/total_iya_mo-1)*100,1) if total_iya_mo else 0
    cust_cnt     = len(store_q)

    # ── 門市分組 ──
    km_stores   = {n:d for n,d in store_q.items() if '統一藥品' in d.get('grp','')}
    cvs_stores  = {n:d for n,d in store_q.items() if '便利商店' in d.get('ch','')}
    xb_stores   = {n:d for n,d in store_q.items() if '小北' in d.get('grp','')}
    other_stores = {n:d for n,d in store_q.items()
                    if '統一藥品' not in d.get('grp','') and '便利商店' not in d.get('ch','')}

    km_total  = sum(d['amt'] for d in km_stores.values())
    km_apr    = sum(store_m.get(n,{}).get('amt',0) for n in km_stores)
    km_cnt    = len(km_stores)
    cvs_total = sum(d['amt'] for d in cvs_stores.values())
    cvs_apr   = sum(store_m.get(n,{}).get('amt',0) for n in cvs_stores)
    cvs_cnt   = len(cvs_stores)
    xb_total  = sum(d['amt'] for d in xb_stores.values())
    xb_apr    = sum(store_m.get(n,{}).get('amt',0) for n in xb_stores)
    xb_cnt    = len(xb_stores)

    # ── KPI 更新 helper ──
    def sub_kpi(label, kv_val, ks_val=None):
        nonlocal html
        if ks_val is not None:
            html = re.sub(
                rf'(<div class="kl">{re.escape(label)}</div><div class="kv">)[^<]*(</div><div class="ks[^"]*">)[^<]*(</div>)',
                rf'\g<1>{kv_val}\g<2>{ks_val}\g<3>', html)
        else:
            html = re.sub(
                rf'(<div class="kl">{re.escape(label)}</div><div class="kv">)[^<]*(</div>)',
                rf'\g<1>{kv_val}\g<2>', html)

    # ── Overview KPIs ──
    sub_kpi('P&G 本月業績', fm(total_mo))
    sub_kpi('季累計', fm(total_q))
    sub_kpi('交易客戶', f'{cust_cnt:,}')
    sub_kpi('IYA 成長', f'+{iya_pct}%' if iya_pct>=0 else f'{iya_pct}%')
    if uncollected:
        sub_kpi('未收款', fm(uncollected))

    # ── 集團排行 KPIs ──
    grp_s     = sorted(grp_q.items(), key=lambda x:-x[1])[:15]
    grp_total = sum(grp_q.values())
    grp_count = len(grp_q)
    top5_sum  = sum(v for _,v in grp_s[:5])
    top5_pct  = round(top5_sum/grp_total*100, 1) if grp_total else 0
    top1_name = grp_s[0][0] if grp_s else ''
    top1_amt  = grp_s[0][1] if grp_s else 0
    top1_short = re.sub(r'股份有限公司.*|有限公司.*', '', top1_name).strip()[:8]

    best_grp_name, best_grp_growth = '', -999
    for gn, s5 in grp_q.items():
        s4 = grp_m.get(gn, 0)
        if s4 > 100000:
            growth = round((s5/s4-1)*100)
            if growth > best_grp_growth:
                best_grp_growth = growth
                best_grp_name = gn
    best_short = re.sub(r'股份有限公司.*|有限公司.*|-PC$|^[A-Z]\d+-|^[A-Z]\d+-', '', best_grp_name).strip()[:5]

    html = re.sub(
        r'(<div class="kl">第1名</div><div class="kv">)[^<]*(</div><div class="ks[^"]*">)[^<]*(</div>)',
        rf'\g<1>{esc(top1_short)}\g<2>{fm(top1_amt)} 季累計\g<3>', html)
    sub_kpi('集團總數', f'{grp_count:,}')
    sub_kpi('前5大佔比', f'{top5_pct}%')
    html = re.sub(
        r'(<div class="kl">最快成長</div><div class="kv">)[^<]*(</div><div class="ks[^"]*">)[^<]*(</div>)',
        rf'\g<1>{esc(best_short)}+{best_grp_growth}%\g<2>4月→季累計\g<3>', html)

    # ── 康是美 KPIs ──
    km_pct = round(km_total/total_q*100, 1) if total_q else 0
    km_chg = round((km_total/km_apr-1)*100, 1) if km_apr else 0
    sub_kpi('康是美季累計', fm(km_total), f'↑ +{km_chg}% vs 4月' if km_chg >= 0 else f'↓ {km_chg}% vs 4月')
    sub_kpi('康是美四月', fm(km_apr), '完整月份')
    sub_kpi('康是美分點數', f'{km_cnt}', '康是美門市')
    sub_kpi('康是美佔比', f'{km_pct}%', '高度集中' if km_pct > 40 else '佔全公司')

    # ── CVS KPIs ──
    cvs_pct = round(cvs_total/total_q*100, 1) if total_q else 0
    cvs_chg = round((cvs_total/cvs_apr-1)*100, 1) if cvs_apr else 0
    sub_kpi('CVS季累計', fm(cvs_total), f'↑ +{cvs_chg}% vs 4月' if cvs_chg >= 0 else f'↓ {cvs_chg}% vs 4月')
    sub_kpi('CVS四月', fm(cvs_apr), '完整月份')
    sub_kpi('CVS門市數', f'{cvs_cnt}', '便利商店')
    sub_kpi('CVS佔比', f'{cvs_pct}%', '佔全公司')

    # ── 小北 KPIs ──
    xb_pct = round(xb_total/total_q*100, 1) if total_q else 0
    xb_chg = round((xb_total/xb_apr-1)*100, 1) if xb_apr else 0
    sub_kpi('小北季累計', fm(xb_total), f'↑ +{xb_chg}% vs 4月' if xb_chg >= 0 else f'↓ {xb_chg}% vs 4月')
    sub_kpi('小北四月', fm(xb_apr), '完整月份')
    sub_kpi('小北分點數', f'{xb_cnt}', '小北門市')
    sub_kpi('小北佔比', f'{xb_pct}%', '佔全公司')

    # ── IYA KPIs ──
    iya_grp_cnt  = len(iya_grp)
    this_grp_cnt = len(grp_q)
    iya_grp_chg  = round((this_grp_cnt/iya_grp_cnt-1)*100,1) if iya_grp_cnt else 0

    def brand_total(data_dict, brand):
        return sum(d.get('brands',{}).get(brand,0) for d in data_dict.get('store',{}).values())

    best_brand_name, best_brand_pct = '', -999
    for bname in DASH_BRANDS:
        this_amt = brand_total(mo, bname)
        iya_amt  = brand_total(iya_q, bname) if iya_q else 0
        if iya_amt > 0:
            pct = round((this_amt/iya_amt-1)*100)
            if pct > best_brand_pct:
                best_brand_pct = pct
                best_brand_name = bname

    sub_kpi('本月 IYA',
            f'+{iya_mo_pct}%' if iya_mo_pct>=0 else f'{iya_mo_pct}%',
            f'去年 {fm(total_iya_mo)}')
    sub_kpi('季累計 IYA',
            f'+{iya_pct}%' if iya_pct>=0 else f'{iya_pct}%',
            f'去年 {fm(total_iya_q)}')
    sub_kpi('集團數 IYA',
            f'+{iya_grp_chg}%' if iya_grp_chg>=0 else f'{iya_grp_chg}%',
            f'去年 {iya_grp_cnt:,} 個集團')
    if best_brand_name:
        sign = '+' if best_brand_pct >= 0 else ''
        sub_kpi('最強成長品牌', f'{best_brand_name} {sign}{best_brand_pct}%', '↑ 最快')

    # ── GRP ──
    lines = [f"  {{n:'{esc(n)}',s5:{int(s5)},s4:{int(grp_m.get(n,int(s5*.85)))}}}"
             for n,s5 in grp_s]
    html = re.sub(r'const GRP=\[[\s\S]*?\];',
                  'const GRP=[\n'+',\n'.join(lines)+'\n];', html)

    # ── STORES (排除 KM 和 CVS，Top 100) ──
    st_s = sorted(other_stores.items(), key=lambda x:-x[1]['amt'])[:100]
    lines = [
        f"  {{s:'{esc(n)}',g:'{esc(d['grp'])}',r:'{esc(d['rep'])}',ch:'{esc(d['ch'])}',"
        f"v5:{int(d['amt'])},v4:{int(store_m.get(n,{}).get('amt',d['amt']*.85))}}}"
        for n,d in st_s
    ]
    html = re.sub(r'const STORES=\[[\s\S]*?\];',
                  'const STORES=[\n'+',\n'.join(lines)+'\n];', html)

    # ── CHS ──
    ch_s = sorted(ch_q.items(), key=lambda x:-x[1])[:10]
    lines = [f"  {{n:'{esc(n)}',s5:{int(v)},s4:{int(ch_m.get(n,v*.85))}}}"
             for n,v in ch_s]
    html = re.sub(r'const CHS=\[[\s\S]*?\];',
                  'const CHS=[\n'+',\n'.join(lines)+'\n];', html)

    # ── UNIF (康是美分點，加 rep 欄位) ──
    km_s = sorted(km_stores.items(), key=lambda x:-x[1]['amt'])[:50]
    def unif_label(name):
        m2 = re.search(r'(\d+)\s*[\(（]([^)\）]+)[\)）]', name)
        return f"{m2.group(1)}({m2.group(2)})" if m2 else name[:20]
    lines = [
        f"  {{s:'{unif_label(n)}',r:'{esc(d['rep'])}',v5:{int(d['amt'])},v4:{int(store_m.get(n,{}).get('amt',d['amt']*.85))}}}"
        for n,d in km_s
    ]
    if lines:
        html = re.sub(r'const UNIF=\[[\s\S]*?\];',
                      'const UNIF=[\n'+',\n'.join(lines)+'\n];', html)

    # ── CVS_STORES ──
    cvs_s = sorted(cvs_stores.items(), key=lambda x:-x[1]['amt'])[:50]
    lines = [
        f"  {{s:'{esc(n[:22])}',r:'{esc(d['rep'])}',v5:{int(d['amt'])},v4:{int(store_m.get(n,{}).get('amt',d['amt']*.85))}}}"
        for n,d in cvs_s
    ]
    html = re.sub(r'const CVS_STORES=\[[\s\S]*?\];',
                  'const CVS_STORES=[\n'+(',\n'.join(lines) if lines else '')+'\n];', html)

    # ── XB_STORES (小北) ──
    xb_s = sorted(xb_stores.items(), key=lambda x:-x[1]['amt'])[:50]
    lines = [
        f"  {{s:'{esc(n[:22])}',r:'{esc(d['rep'])}',v5:{int(d['amt'])},v4:{int(store_m.get(n,{}).get('amt',d['amt']*.85))}}}"
        for n,d in xb_s
    ]
    html = re.sub(r'const XB_STORES=\[[\s\S]*?\];',
                  'const XB_STORES=[\n'+(',\n'.join(lines) if lines else '')+'\n];', html)

    # ── BRANDS ──
    bapr  = [int(brand_total(m,  b)) for b in DASH_BRANDS]
    bmay  = [int(brand_total(mo, b)) for b in DASH_BRANDS]
    biya  = [int(brand_total(iya_q, b)) for b in DASH_BRANDS] if iya_q else bapr

    html = re.sub(r'const BAPR=\[[^\]]*\];',  f'const BAPR={bapr};',  html)
    html = re.sub(r'const BMAY=\[[^\]]*\];',  f'const BMAY={bmay};',  html)
    html = re.sub(r'const BIYA_=\[[^\]]*\];', f'const BIYA_={biya};', html)
    html = re.sub(r"const BRANDS=\[[^\]]*\];",
                  f"const BRANDS={[b for b in DASH_BRANDS]};", html)

    # ── REPS ──
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

    # ── PAYS ──
    if pays_list:
        pay_lines = [
            f"  {{r:'{esc(p['r'])}',tgt:{p['tgt']},act:{p['act']},gap:{p['gap']}}}"
            for p in sorted(pays_list, key=lambda x: x['tgt']-x['act'], reverse=True)
        ]
        html = re.sub(r'const PAYS=\[[\s\S]*?\];',
                      'const PAYS=[\n'+',\n'.join(pay_lines)+'\n];', html)

        total_tgt   = sum(p['tgt'] for p in pays_list)
        total_act   = sum(p['act'] for p in pays_list)
        achieve_pct = round(total_act / total_tgt * 100) if total_tgt else 0
        over        = max(0, total_act - total_tgt)
        behind      = sum(1 for p in pays_list if p['tgt'] > 0 and p['act'] < p['tgt'])
        mo_label    = f"{_today.month}月"

        html = re.sub(r'(\d+)月 MBO 收款目標 vs 實際達成',
                      f'{mo_label} MBO 收款目標 vs 實際達成', html)
        html = re.sub(
            r'(<div class="kl">總收款目標</div><div class="kv">)[^<]*(</div><div class="ks">)[^<]*(</div>)',
            rf'\g<1>{fm(total_tgt)}\g<2>{mo_label} MBO\g<3>', html)
        html = re.sub(
            r'(<div class="kl">已收款</div><div class="kv">)[^<]*(</div><div class="ks[^"]*">)[^<]*(</div>)',
            rf'\g<1>{fm(total_act)}\g<2>{"↑ " if achieve_pct>=100 else ""}達成 {achieve_pct}%\g<3>', html)
        if over > 0:
            html = re.sub(
                r'(<div class="kl">超收金額</div><div class="kv">)[^<]*(</div><div class="ks[^"]*">)[^<]*(</div>)',
                rf'\g<1>{fm(over)}\g<2>超越目標\g<3>', html)
        else:
            html = re.sub(
                r'(<div class="kl">超收金額</div><div class="kv">)[^<]*(</div><div class="ks[^"]*">)[^<]*(</div>)',
                rf'\g<1>{fm(total_tgt - total_act)}\g<2>尚未達標\g<3>', html)
        html = re.sub(
            r'(<div class="kl">未達標人數</div><div class="kv">)[^<]*(</div>)',
            rf'\g<1>{behind}人\g<2>', html)
        html = re.sub(r'(\d+)月 MBO 收款 · 真實資料',
                      f'{mo_label} MBO 收款 · 真實資料', html)

    # ── 月業績趨勢 ──
    apr_total     = sum(m.get('grp',{}).values())
    iya_apr_total = sum(iya_q.get('grp',{}).values()) - sum(iya_mo.get('grp',{}).values()) if iya_q else 0
    iya_mo_total  = sum(iya_mo.get('grp',{}).values()) if iya_mo else 0

    html = re.sub(
        r"(label:'今年',data:\[)([^\]]+)(\])",
        lambda mm: (mm.group(1) +
            ','.join(mm.group(2).split(',')[:-2] + [str(int(apr_total)), str(int(total_mo))]) +
            mm.group(3)), html)
    html = re.sub(
        r"(label:'去年',data:\[)([^\]]+)(\])",
        lambda mm: (mm.group(1) +
            ','.join(mm.group(2).split(',')[:-2] + [str(int(iya_apr_total)), str(int(iya_mo_total))]) +
            mm.group(3)), html)

    # ── 通路圓餅 ──
    top5_ch = sorted(ch_q.items(), key=lambda x:-x[1])[:5]
    others  = sum(v for _,v in sorted(ch_q.items(), key=lambda x:-x[1])[5:])
    ch_data = [int(v) for _,v in top5_ch] + [int(others)]
    html = re.sub(
        r"(labels:\[(?:'[^']*',?\s*){3,8}\],\s*\n?\s*datasets:\[{data:\[)[\d,\s]+(])",
        lambda mm: mm.group(1) + ','.join(str(x) for x in ch_data) + mm.group(2),
        html, count=1)

    # ── 庫存 (INV_BRANDS / INV_WH) ──
    if inv_data:
        def jstr(v): return str(v).replace("'","`")
        brand_lines = []
        for b in inv_data:
            tq = ','.join(f"{{s:'{jstr(x['s'])}',n:'{jstr(x['n'])}',q:{x['q']},a:{x['a']}}}" for x in b['topQ'])
            ta = ','.join(f"{{s:'{jstr(x['s'])}',n:'{jstr(x['n'])}',q:{x['q']},a:{x['a']}}}" for x in b['topA'])
            brand_lines.append(
                f"  {{code:'{b['code']}',label:'{b['label']}',qty:{b['qty']},amt:{b['amt']},"
                f"tainan:{b['tainan']},kaohsiung:{b['kaohsiung']},tp:{b['tp']},km:{b['km']},cvs:{b['cvs']},"
                f"topQ:[{tq}],topA:[{ta}]}}"
            )
        html = re.sub(r'const INV_BRANDS=\[[\s\S]*?\];',
                      'const INV_BRANDS=[\n'+',\n'.join(brand_lines)+'\n];', html)

        wh_totals = {'台南':0,'高雄':0,'桃園':0,'康是美':0,'CVS':0}
        wh_qty    = {'台南':0,'高雄':0,'桃園':0,'康是美':0,'CVS':0}
        for b in inv_data:
            wh_totals['台南']   += b['tainan']
            wh_totals['高雄']   += b['kaohsiung']
            wh_totals['桃園']   += b['tp']
            wh_totals['康是美'] += b['km']
            wh_totals['CVS']    += b['cvs']
        wh_lines = [f"  {{name:'{k}',amt:{int(v)}}}" for k,v in wh_totals.items()]
        html = re.sub(r'const INV_WH=\[[\s\S]*?\];',
                      'const INV_WH=[\n'+',\n'.join(wh_lines)+'\n];', html)

        total_inv = sum(b['amt'] for b in inv_data)
        sub_kpi('總庫存金額', fm(total_inv), f'{len(inv_data)} 品牌')
        sub_kpi('台南倉庫存', fm(wh_totals['台南']), '台南出貨倉')
        sub_kpi('高雄倉庫存', fm(wh_totals['高雄']), '高雄主貨倉')
        sub_kpi('桃園倉庫存', fm(wh_totals['桃園']), 'TP主貨倉')
        sub_kpi('康是美倉庫存', fm(wh_totals['康是美']), '康是美寄倉')

    # ── 日期 ──
    td     = _today.strftime("%Y/%m/%d")
    mo_lbl = _today.strftime("%m/%d")
    html = re.sub(r'\d{4}/\d{2}/\d{2} · 寶捷實業有限公司', f'{td} · 寶捷實業有限公司', html)
    html = re.sub(r'\d{4}年\d+月（截至\d+/\d+）', f'{_today.year}年{_today.month}月（截至{mo_lbl}）', html)
    html = re.sub(r'季累計（至\d+/\d+）', f'季累計（至{mo_lbl}）', html)
    html = re.sub(r"'季累計（4/1－[^']*）'", f"'季累計（4/1－{mo_lbl}）'", html)

    DASHBOARD.write_text(html, encoding='utf-8')

    inv_summary = f"  庫存:{fm(sum(b['amt'] for b in inv_data))}({len(inv_data)}品牌)" if inv_data else ""
    print(f"\n✅ {td} 全指標更新完成")
    print(f"   本月:{fm(total_mo)}  季累計:{fm(total_q)}  IYA:{iya_pct:+.1f}%  交易客戶:{cust_cnt:,}")
    print(f"   KM:{fm(km_total)}({km_cnt}點)  CVS:{fm(cvs_total)}({cvs_cnt}點)  小北:{fm(xb_total)}({xb_cnt}點)")
    print(f"   通路:{len(ch_s)}種  業務:{len(rep_lines)}人{inv_summary}")


# ── Main ─────────────────────────────────────────────────
def main():
    print(f"\n{'='*52}\n  DERP → Dashboard 全指標更新  {today}\n{'='*52}\n")
    s = get_session()

    print("[下載 本期]")
    data_q  = dl_sales(s, q_start,  today,  "季累計")
    data_mo = dl_sales(s, mo_start, today,  "本月")
    data_m  = dl_sales(s, q_start,  m_end,  "4月全月")

    print("\n[下載 去年同期 IYA]")
    data_iya_q  = dl_sales(s, ly_qstart,  ly_today, "去年季累計")
    data_iya_mo = dl_sales(s, ly_mostart, ly_today, "去年本月")

    print("\n[收款 Excel]")

    print("\n[解析]")
    q      = parse_xls(data_q);      print(f"  季累計  → 集團:{len(q.get('grp',{}))} 門市:{len(q.get('store',{}))} 業務:{len(q.get('rep',{}))}")
    mo     = parse_xls(data_mo);     print(f"  本月    → 集團:{len(mo.get('grp',{}))}")
    m      = parse_xls(data_m);      print(f"  4月全月 → 集團:{len(m.get('grp',{}))}")
    iya_q  = parse_xls(data_iya_q);  print(f"  去年季  → 集團:{len(iya_q.get('grp',{}))}")
    iya_mo = parse_xls(data_iya_mo); print(f"  去年月  → 集團:{len(iya_mo.get('grp',{}))}")
    pays_list, uncollected = parse_local_payment_xls()

    if not q.get('grp'):
        print("✗ 解析失敗"); sys.exit(1)

    print("\n[庫存下載]")
    inv_data = None
    try:
        ws = get_web_session()
        if ws:
            inv_path = dl_inventory(ws)
            if inv_path:
                inv_data = parse_inventory_html(inv_path)
    except Exception as e:
        print(f"  ⚠ 庫存下載失敗（業績仍正常更新）: {e}")

    update_dashboard(q, m, mo, iya_q, iya_mo, pays_list, uncollected, inv_data)


if __name__ == "__main__":
    main()
