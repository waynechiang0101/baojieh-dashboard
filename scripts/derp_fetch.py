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

# 上個完整月份（動態）
_prev_m      = (_today.replace(day=1) - __import__('datetime').timedelta(days=1))
m_end        = f"{_prev_m.year}/{_prev_m.month:02d}/{_prev_m.day:02d}"
m_start      = f"{_prev_m.year}/{_prev_m.month:02d}/01"

# 去年上月（同月份，用於小北退步對比）
_ly_prev_m   = _prev_m.replace(year=_prev_m.year - 1)
import calendar as _cal
ly_prev_m_last = _cal.monthrange(_ly_prev_m.year, _ly_prev_m.month)[1]
ly_m_start   = f"{_ly_prev_m.year}/{_ly_prev_m.month:02d}/01"
ly_m_end     = f"{_ly_prev_m.year}/{_ly_prev_m.month:02d}/{ly_prev_m_last:02d}"

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
# KBD 費率 25/26（品類 → 品牌）
KBD_RATES = {
    'PAMPS':0.1366, 'WHSP':0.2066,
    'HS':0.1995, 'PNTN':0.1995, 'PERT':0.1995, 'HR':0.1995, 'VS':0.1995,
    'OLAY':0.2710,
    'ARIEL':0.1340, 'LENOR':0.1340, 'BOLD':0.1340, 'TIDE':0.1340,
    'FBRZ':0.2266, 'JOY':0.2266, 'FAIRY':0.2266,
    'GLT':0.1836, 'BRAUN':0.1836,
    'CREST':0.2716, 'ORALB':0.3516, 'SARASA':0.2000,
}
# COGS 費率（cogs/net）：以 1~5月靜態資料為基準，未來逐步調整
BRAND_COGS_RATE = {
    'PAMPS':0.922, 'HS':0.945, 'PNTN':0.975, 'OLAY':0.972,
    'ARIEL':0.985, 'WHSP':0.983, 'HR':0.976, 'GLT':0.922,
    'LENOR':0.977, 'FBRZ':0.983, 'BRAUN':0.907, 'CREST':0.851,
    'ORALB':0.928, 'PERT':0.961, 'BOLD':0.987, 'TIDE':0.990,
    'VS':0.950, 'JOY':0.950, 'FAIRY':0.950, 'SARASA':0.950,
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
    'HR':'髮的食譜','OLAY':'歐蕾','FBRZ':'風倍清','ORALB':'歐樂B',
    'GLT':'吉列','LENOR':'蘭諾','ARIEL':'ARIEL','PERT':'飛柔',
    'BRAUN':'百靈','CREST':'Crest','BOLD':'BOLD','TIDE':'汰漬',
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
    # Try agent-browser cookie first, validate with actual XLS download
    try:
        import subprocess
        r = subprocess.run(
            ["agent-browser","cookies","get","--url","https://gderp.titan.ebiz.tw"],
            capture_output=True, text=True, timeout=10)
        m = re.search(r'JSESSIONID=([A-F0-9]+)', r.stdout)
        if m:
            s = _make_session(m.group(1))
            # Validate by trying a real XLS download (not just a JSP page)
            rr = s.get(f"{BASE_URL}/BizPlan/dsrDailySales",
                       params={"*transDateStart":"2026/05/01","*transDateEnd":"2026/05/01",
                               "*pageCmd":"dsrDailySales","closedType":"closedNot",
                               "dsrNoCredit":"O","reportRange":"S","reportRangeSelect":"S",
                               "*keySelected":f"{ACCOUNT_ID},","*rowsPerPage":"20",
                               "*itemNoStart":"","*itemNoEnd":"","*soldToCode":"","*soldToCodeMerge":"",
                               "*customerNo":"","customerNo":"","*customerNoMerge":"",
                               "*dsrNoStart":"","*dsrNoStartName":"","*dsrNoEnd":"","*dsrNoEndName":"",
                               "*brandCodeStart":"","*brandCodeEnd":"","*acChannelCode":"","*pgChannelCode":"",
                               "*maxKeyValue":"","*minKeyValue":"","*indexSelected":""},
                       verify=False, timeout=30)
            if rr.content[:4] == b'\xd0\xcf\x11\xe0':  # valid XLS magic bytes
                print(f"✓ Session ({m.group(1)[:8]}...)")
                return s
            print(f"  agent-browser session expired, using POST login")
    except: pass
    # Fallback: POST login (most reliable)
    return _post_login(user, pwd)

def _post_login(user, pwd):
    print(f"  POST 登入 ({user})...")
    s = requests.Session()
    s.headers.update({'User-Agent':'Mozilla/5.0'})
    s.post(f'{BASE_URL}/CCderp.jsp', verify=False, timeout=30, data={
        '*userID': user, '*password': pwd,
        '*accountID': ACCOUNT_ID,
        '*dataOwner': 'CVS-7,CVS-HL,CVS-OK,CVS-FM,ETC,OMD,COSMED,DMC,CVS-7N',
        '*requestURL': f'{BASE_URL}/PC.sys',
        '*loginTemplate': 'Login.html', '*menuTemplate': 'indexBlank.html',
        '*pageCmd': 'Login', 'execCode':'0','execMsg':'','actionCode':'0',
        'focusField':'','urlAlter':'','urlYes':'','urlNo':''
    })
    s.headers.update({'Referer': f'{BASE_URL}/6.BR/derp-610-82.jsp'})
    jsid = s.cookies.get('JSESSIONID','')
    print(f"✓ POST 登入 ({jsid[:8]}...)")
    return s

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
    import time
    user = os.environ.get("DERP_USER", "user34")
    pwd  = os.environ.get("DERP_PASS", "user34")
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
    for attempt in range(3):
        if attempt > 0:
            wait = attempt * 10
            print(f"  retry {attempt}/2，等 {wait}s...")
            time.sleep(wait)
        # 每次重新 login
        s = _post_login(user, pwd)
        print(f"  {label} {d0}~{d1}...")
        try:
            r = s.get(f"{BASE_URL}/BizPlan/dsrDailySales",
                      params=params, verify=False, timeout=180)
        except Exception as e:
            print(f"  ⚠ 連線錯誤（{type(e).__name__}），重試...")
            continue
        size_kb = len(r.content) // 1024
        print(f"    ✓ {size_kb}KB")
        if size_kb < 10:
            print(f"  ⚠ 回傳太小（{size_kb}KB），可能是 HTML，重試...")
            continue
        return r.content
    print(f"  ✗ {label} 3次都失敗，回傳空白")
    return b''


# ── 康是美出貨件數（610-24 客戶品項銷售，CSV）──────────────
def fetch_km_ship(d0, d1):
    """抓 610-24 品項級出貨明細，回傳康是美（soldToCode=110）各品牌淨出貨件數。
    totalQty 單位 = 件（與實銷件數同單位）；SR 退貨扣回；BRAUN 併入 ORALB。"""
    import csv, io
    s = _post_login(os.environ.get("DERP_USER","user34"), os.environ.get("DERP_PASS","user34"))
    data = {
        '*listOMD':'','*fixSupplierNo':'','gLCategorySelect':'',
        '*customerNoStart':ACCOUNT_ID,'*soldToCode':'','*soldToCodeName':'',
        '*customerNoEnd':'','*customerName':'','*customerNoMerge':'',
        '*transDateStart':d0,'*transDateEnd':d1,
        '*warehouseStart':'','*warehouseStartName':'',
        '*saleType':'0','*goldenSkuFlag':'2',
        '*brandCodeStart':'','*brandCodeMerge':'',
        '*transType':'0','*subSegMent':'','*subSegMentMerge':'',
        '*itemNoEnd':'','*itemNoMerge':'','*itemNoStart':'','*itemDesc':'',
        '*box1View':'','*box2View':'',
        '*pageCmd':'PrintCSV','*maxKeyValue':'','*minKeyValue':'',
        '*rowsPerPage':'20','*indexSelected':'','*keySelected':'',
        'execCode':'0','execMsg':'','actionCode':'0','focusField':'',
        'urlAlter':'','urlYes':'','urlNo':'',
        'derpPage':'derp-610-24','accountID':ACCOUNT_ID,'dataOwner':'','appSysName':'derp',
    }
    print(f"  康是美出貨 610-24 {d0}~{d1}...")
    r = s.post(f'{BASE_URL}/6.BR/derp-610-24.jsp', data=data, verify=False, timeout=600,
               headers={'Referer':f'{BASE_URL}/6.BR/derp-610-24.jsp'})
    print(f"    ✓ {len(r.content)//1024}KB")
    ship = {}
    rows = csv.DictReader(io.StringIO(r.content.decode('utf-8-sig', errors='replace')))
    for x in rows:
        if (x.get('soldToCode') or '').strip() != '110': continue
        try: q = float(x.get('totalQty') or 0)
        except ValueError: continue
        if x.get('txnType') == 'SR': q = -abs(q)
        b = (x.get('brandCode') or '').strip()
        if b == 'BRAUN': b = 'ORALB'
        ship[b] = ship.get(b, 0) + q
    ship = {b: round(q) for b, q in ship.items()}
    print(f"    ✓ 康是美淨出貨 {len(ship)} 品牌")
    return ship


# ── 解析銷售 XLS ─────────────────────────────────────────
def parse_xls(data):
    import xlrd
    if data[:9].lower().lstrip() in (b'<!doctype', b'<html') or data[:5] == b'<html':
        print("  ⚠ DERP 回傳 HTML（非 XLS），跳過此報表")
        return {}
    if not data or data[:8].lower().startswith(b'<!'):
        print("  ⚠ DERP 回傳無效資料，跳過此報表")
        return {}
    try:
        wb = xlrd.open_workbook(file_contents=data)
    except Exception as e:
        print(f"  ⚠ XLS 解析失敗 ({e.__class__.__name__})，跳過此報表")
        return {}
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

    grp, grp_brands, store, ch, rep = {}, {}, {}, {}, {}
    brand_net, brand_giv = {}, {}

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
        for c, b in BRAND_COLS.items():
            brand_net[b] = brand_net.get(b, 0.0) + n(c)
            brand_giv[b] = brand_giv.get(b, 0.0) + (n(c+2) if c+2 < ws.ncols else 0.0)

        grp[g] = grp.get(g,0) + amt
        if g not in grp_brands: grp_brands[g] = {}
        for b,bv in brands.items():
            if bv > 0: grp_brands[g][b] = grp_brands[g].get(b,0) + bv

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

    return {'grp':grp,'grp_brands':grp_brands,'store':store,'ch':ch,'rep':rep,
            'brand_net':brand_net,'brand_giv':brand_giv}


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
    # 偵測 header，找「日均銷」欄位 index
    daily_col = None
    for row in rows[:10]:
        cells = re.findall(r'<T[DH][^>]*>(.*?)</T[DH]>', row, re.I|re.S)
        cleaned_h = [re.sub(r'<[^>]+>','',c).strip() for c in cells]
        for i,h in enumerate(cleaned_h):
            if '日均' in h:
                daily_col = i
                break
        if daily_col is not None:
            break
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
        daily = 0.0
        if daily_col is not None:
            try: daily = float(cleaned[daily_col])
            except: pass
        g = _wh_group(wh)
        b = brands[brand]
        b['qty'] += qty; b['amt'] += amt; b[g] += amt
        if sku not in b['skus']:
            b['skus'][sku] = {'name': name[:30], 'qty':0, 'amt':0, 'daily':0.0, 'wh':{}}
        b['skus'][sku]['qty'] += qty
        b['skus'][sku]['amt'] += amt
        if daily > 0:
            b['skus'][sku]['daily'] = daily  # 全公司日均銷，各倉相同，直接覆寫
        # 各倉明細
        if g not in b['skus'][sku]['wh']:
            b['skus'][sku]['wh'][g] = {'qty':0, 'amt':0}
        b['skus'][sku]['wh'][g]['qty'] += qty
        b['skus'][sku]['wh'][g]['amt'] += amt

    def sku_days(v, qty_override=None):
        d = v['daily']
        if d <= 0: return None
        q = qty_override if qty_override is not None else v['qty']
        return round(q / d) if q > 0 else None

    def sku_wh(v):
        result = {}
        for k in ['tainan','kaohsiung','tp','km','cvs']:
            w = v['wh'].get(k)
            if w and w['qty'] > 0:
                result[k] = {'q': int(w['qty']), 'a': int(w['amt']),
                              'd': sku_days(v, w['qty'])}
        return result

    result = []
    for code, d in sorted(brands.items(), key=lambda x:-x[1]['amt']):
        skus = d['skus']
        topQ = sorted(skus.items(), key=lambda x:-x[1]['qty'])[:30]
        topA = sorted(skus.items(), key=lambda x:-x[1]['amt'])[:30]
        result.append({
            'code':code, 'label':BRAND_NAMES.get(code,code),
            'qty':int(d['qty']), 'amt':int(d['amt']),
            'tainan':int(d['tainan']), 'kaohsiung':int(d['kaohsiung']),
            'tp':int(d['tp']), 'km':int(d['km']), 'cvs':int(d['cvs']),
            'topQ':[{'s':k,'n':v['name'],'q':int(v['qty']),'a':int(v['amt']),
                     'd':sku_days(v),'wh':sku_wh(v)} for k,v in topQ],
            'topA':[{'s':k,'n':v['name'],'q':int(v['qty']),'a':int(v['amt']),
                     'd':sku_days(v),'wh':sku_wh(v)} for k,v in topA],
        })
    total_amt = sum(d['amt'] for d in result)
    print(f"  ✓ 庫存: {len(result)} 品牌  ${total_amt/1e6:.1f}M  日均銷欄={'col'+str(daily_col) if daily_col else '未偵測'}")
    return result


# ── 解析 DERP 應收帳款 XLS（業務別收款總表by Excel）────────────────
def parse_derp_ar_xls():
    """自動從 DERP 撈應收帳款，回傳 (ar_reps, total_unpaid)"""
    import glob, xlrd, datetime, re
    user = os.environ.get("DERP_USER", "user34")
    pwd  = os.environ.get("DERP_PASS",  "user34")
    s = _post_login(user, pwd)
    today_d = datetime.date.today()
    # AR 查近90天，涵蓋所有未付帳款
    ar_start = today_d - datetime.timedelta(days=90)

    base_params = {
        'appContext': 'derp', 'handheldDevice': 'N', 'accountID': ACCOUNT_ID,
        '*customerNo': '', '*customerName': '', '*dsr': '', '*dsrName': '',
        '*territoryCode': '', '*territoryCodeName': '',
        '*customerNoMerge': '', '*dsrNoMerge': '', '*territoryMerge': '',
        '*deliveryDate': ar_start.strftime('%Y/%m/%d'),
        '*deliveryDateEnd': today_d.strftime('%Y/%m/%d'),
        'offSetFlagSelect': '1', '*offSetFlag': '1',
        '*queryRows': '', '*pageMax': '', '*pageOffset': '0',
        '*rowsPerPage': '100', '*pageIndex': '1',
        '*soldToCode': '', '*soldToCodeMerge': '',
        '*customerClass': '', '*descLocal': '',
        '*deliveryNo': '', '*deliveryNoEnd': '',
        'transTypeSelect': '1', '*transType': '1',
        '*remainTotal': '', '*pageCmd': 'query',
        '*maxKeyValue': '', '*minKeyValue': '', '*indexSelected': '', '*keySelected': '',
        'linePerPage': '', '*rptFormat': 'HTML',
        '*rptLines': '', '*rptOrientation': '', '*rptPageSize': '',
        '*rptGrayScale': '', '*rptDraftMode': '',
    }
    try:
        r1 = s.post(f'{BASE_URL}/4.FN/derp-421-00.jsp', verify=False, timeout=60, data=base_params)
        qrows  = re.search(r'name="\*queryRows"[^>]*value="(\d+)"',   r1.text)
        remain = re.search(r'name="\*remainTotal"[^>]*value="([\d.]+)"', r1.text)
        if not qrows:
            print("  ⚠ AR: 查詢無結果，跳過")
            return [], 0
        xls_params = dict(base_params)
        xls_params.update({
            '*queryRows': qrows.group(1),
            '*remainTotal': remain.group(1) if remain else '',
            '*pageOffset': '0', '*pageIndex': '1',
            '*pageCmd': '', '*rptFormat': 'XLS',
        })
        r2 = s.get(f'{BASE_URL}/4.FN/derp-421-14-1.jsp', params=xls_params, verify=False, timeout=120)
        if r2.content[:4] != b'\xd0\xcf\x11\xe0':
            print("  ⚠ AR: 下載失敗，回傳非 XLS")
            return [], 0
        wb = xlrd.open_workbook(file_contents=r2.content)
        ws = wb.sheet_by_index(0)
    except Exception as e:
        print(f"  ⚠ AR 下載失敗: {e}")
        return [], 0

    ar_reps = []
    total_unpaid = 0
    for i in range(ws.nrows):
        v4 = str(ws.cell_value(i, 4)).strip()
        if v4 == '業務小計':
            code = str(ws.cell_value(i, 0)).strip()
            name = str(ws.cell_value(i, 1)).strip()
            sales   = float(ws.cell_value(i, 5) or 0)
            cleared = float(ws.cell_value(i, 6) or 0)
            unpaid  = float(ws.cell_value(i, 7) or 0)
            if code.startswith('MS') and code != 'MS999':
                m = re.match(r'MS\d+[. ]+(.+)', name)
                short = m.group(1).strip() if m else name
                ar_reps.append({'code': code, 'name': short, 'sales': int(sales), 'cleared': int(cleared), 'unpaid': int(unpaid)})
        elif v4 == '業務總計':
            total_unpaid = int(float(ws.cell_value(i, 7) or 0))
    print(f"  ✓ AR: {len(ar_reps)}人  應收未付: ${total_unpaid/1e6:.1f}M")
    return ar_reps, total_unpaid


# ── 讀取本地收款 Excel ────────────────────────────────────
def parse_local_payment_xls():
    import glob, xlrd
    pattern = os.path.expanduser("~/Downloads/115-??收款*.xls")
    files = sorted(glob.glob(pattern), key=os.path.getmtime)
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
    if uncollected < 0:
        print(f"  ✓ {len(pays)}人  已超收: ${-uncollected/1e6:.1f}M（超過目標）")
    else:
        print(f"  ✓ {len(pays)}人  未收款: ${uncollected/1e6:.1f}M")
    return pays, uncollected


# ── 讀取業績追踨 Excel (數字對齊 XLS) ────────────────────────
def parse_xls_performance():
    """解析 ~/Downloads/*業績追踨*.xls，回傳 dict 或 None。
    用檔名的月份數字排序（115-06 > 115-05），不用 mtime，避免舊檔被開過後搶先。
    """
    import glob, xlrd as _xlrd, re as _re
    pattern = os.path.expanduser("~/Downloads/*業績追踨*.xls")
    files = glob.glob(pattern)
    if not files:
        print("  ⚠ 找不到業績追踨 XLS，通路 KPI 改用 DERP 資料")
        return None
    def xls_sort_key(p):
        base = os.path.basename(p)
        m = _re.search(r'115-(\d+)', base)
        month = int(m.group(1)) if m else 0
        # 草稿版：(1)-N 格式，排除
        is_draft = bool(_re.search(r'\(1\)-\d+', base))
        if is_draft:
            return (month, 0, 0)
        # 非草稿：用 mtime 排序（越新越好）
        return (month, 1, int(os.path.getmtime(p)))
    path = sorted(files, key=xls_sort_key)[-1]
    print(f"  讀取業績追踨: {os.path.basename(path)}")
    try:
        wb = _xlrd.open_workbook(path)
    except Exception as e:
        print(f"  ⚠ 無法開啟: {e}"); return None

    sh0 = wb.sheet_by_index(0)   # PG最新業績
    sh1 = wb.sheet_by_index(1)   # 品牌業績

    def fv(r, c):
        v = sh0.cell_value(r, c)
        return float(v) if isinstance(v, (int, float)) else 0.0

    # 時間進度 (row 0)
    work_done  = int(fv(0, 2))
    work_total = int(fv(0, 0))
    time_pct   = fv(0, 5)

    # 總計 row (row 30): col4=5月目標, col5=達成率, col6=家品累計, col2=已交易, col1=交易目標
    biz_tgt    = fv(30, 4)
    biz_pct    = fv(30, 5)
    biz_home   = fv(30, 6)   # 業務通路累計
    traded     = int(fv(30, 2))
    traded_tgt = int(fv(30, 1))

    # 藥房/超市小計 (rows 26–27, col6)
    pharma = fv(26, 6)
    super_ = fv(27, 6)

    # 通路列 (col4 = 累計業績): 丁丁33 啄木鳥34 大樹35 小北36 B&C37
    channels = {}
    ch_map = {33:'丁丁',34:'啄木鳥',35:'大樹',36:'小北',37:'B&C',
              41:'全台全家',42:'捷盟7-11',43:'萊爾富',44:'來來OK',45:'康是美'}
    for r, name in ch_map.items():
        v = sh0.cell_value(r, 4)
        channels[name] = float(v) if isinstance(v, (int, float)) and v > 0 else 0.0

    # P&G Total (row 47, col4)
    pg_total = fv(47, 4)

    # Sheet1: 康是美(row33 col20), CVS盤商合計(row34 col20)
    def fv1(r, c):
        v = sh1.cell_value(r, c)
        return float(v) if isinstance(v, (int, float)) else 0.0
    km_direct  = fv1(33, 20)   # 康是美直送
    cvs_total  = fv1(34, 20)   # CVS合計 (全家+7-11+萊爾富+OK+康是美)
    cvs_others = cvs_total - km_direct  # 全家+7-11+萊爾富+OK

    # 業務月目標 (E欄 col4)，每個業務一行
    rep_tgt = {}
    for i in range(2, sh0.nrows):
        cell0 = str(sh0.cell_value(i, 0)).strip()
        if not cell0: continue
        m2 = re.match(r'(MS\d+)[. ]+(.+)', cell0)
        if not m2: continue
        code = m2.group(1)
        tgt_v = sh0.cell_value(i, 4)
        if isinstance(tgt_v, (int, float)) and tgt_v > 0:
            rep_tgt[code] = int(tgt_v)

    # 今日出貨：header row (row 1) 找 MMDD 格式的欄位（如 '0617'），讀總計 row
    today_ship = 0
    hdr_row = [str(sh0.cell_value(1, c)).strip() for c in range(sh0.ncols)]
    import re as _re2
    for ci, h in enumerate(hdr_row):
        if _re2.fullmatch(r'\d{4}', h):  # MMDD 格式
            today_ship = int(fv(30, ci))
            break

    return {
        'pg_total':    int(pg_total),
        'pharma':      int(pharma),
        'super':       int(super_),
        'km_direct':   int(km_direct),
        'cvs_others':  int(cvs_others),
        'cvs_total':   int(cvs_total),
        'biz_home':    int(biz_home),
        'biz_tgt':     int(biz_tgt),
        'biz_pct':     biz_pct,
        'traded':      traded,
        'traded_tgt':  traded_tgt,
        'work_done':   work_done,
        'work_total':  work_total,
        'time_pct':    time_pct,
        'channels':    channels,
        'rep_tgt':     rep_tgt,
        'today_ship':  today_ship,
    }


# ── 退貨憑單清單（161-00-09 銷貨退回日報表，財報口徑）──────
def fetch_sr_vouchers(d0, d1):
    """抓 ERP 銷貨退回日報表（accountID=22884510，會計確認=財報數字），
    按憑單彙總，供退貨原因登記頁使用。"""
    s = _post_login(os.environ.get("DERP_USER","user34"), os.environ.get("DERP_PASS","user34"))
    params = {
        '*ReportType':'1','*orderDateStart':d0,'*orderDateEnd':d1,
        '*deliveryDateStart':'','*deliveryDateEnd':'','*shipmentDateStart':'','*shipmentDateEnd':'',
        '*selectedVANSale':'','*orderNo':'','*orderNoMerge':'','*returnNo':'','*returnNoMerge':'',
        '*brandCode':'','*brandCodeMerge':'','*itemNo':'','*itemNoMerge':'','*barcode':'','*barcodeMerge':'',
        '*selectedStatus':'','*orderSeqNo':'','*orderSeqNoMerge':'','*supplierNo':'','*supplierNoMerge':'',
        '*territoryCode':'','*territoryMerge':'','*dsrNo':'','*dsrNoMerge':'',
        '*soldToCode':'','*soldToCodeName':'','*customerNoStart':'','*customerNoMerge':'',
        '*warehouse':'','*warehouseMerge':'',
        '*pageCmd':'view','*maxKeyValue':'','*minKeyValue':'','*rowsPerPage':'14','*linePerPage':'20',
        '*indexSelected':'','*keySelected':'','*rptFormat':'HTML','*rptLines':'','*rptOrientation':'',
        '*rptPageSize':'','*rptGrayScale':'','*rptDraftMode':'','*rptFormatSelected':'','*rptLinesSelected':'',
        'parmLines':'','*rptOrientationSelected':'','*rptPageSizeSelected':'','*rptGrayScaleSelected':'',
        '*rptDraftModeSelected':'','execCode':'0','execMsg':'','actionCode':'0','focusField':'',
        'urlAlter':'','urlYes':'','urlNo':'',
        'accountID':'22884510','derpPage':'derp-161-00','*htmlPage':'derp-161-00','appSysName':'derp',
    }
    print(f"  退貨憑單 161-10 {d0}~{d1}...")
    r = s.get(f'{BASE_URL}/1.SO/derp-161-10.jsp', params=params, verify=False, timeout=300,
              headers={'Referer':f'{BASE_URL}/1.SO/derp-161-00.jsp'})
    print(f"    ✓ {len(r.content)//1024}KB")
    rows = re.findall(r'<TR[^>]*>(.*?)</TR>', r.text, re.I|re.S)
    vouchers = {}
    for row in rows:
        c = [re.sub(r'<[^>]+>','',x).strip().replace('&nbsp;','') for x in
             re.findall(r'<T[DH][^>]*>(.*?)</T[DH]>', row, re.I|re.S)]
        if len(c) < 11 or not c[1].startswith('SR'): continue
        try: amt = float(c[9].replace(',',''))
        except: continue
        no = c[1]
        if no not in vouchers:
            vouchers[no] = {'no':no,'date':c[0],'cust':c[2],'wh':c[3],'amt':0,'n':0,'first':c[6][:24],'note':c[10][:30]}
        v = vouchers[no]
        v['amt'] += amt; v['n'] += 1
        if c[10] and not v['note']: v['note'] = c[10][:30]
    out = sorted(vouchers.values(), key=lambda x: (x['date'], x['no']), reverse=True)
    for v in out: v['amt'] = round(v['amt'])
    print(f"    ✓ {len(out)} 張憑單")
    return out


# ── 退貨分析（寶捷ERP退貨憑單口徑，月報XLS）────────────────
def parse_returns_xls():
    """讀月報「P&G銷貨退回比較表/排行榜」XLS（Downloads 遞迴找最新）。
    口徑：寶捷ERP退貨憑單（Wayne 2026-06-11 裁定，不用DERP SR）。"""
    import glob as _glob, xlrd
    def newest(pat):
        fs = _glob.glob(os.path.expanduser(f'~/Downloads/**/{pat}'), recursive=True)
        return max(fs, key=os.path.getmtime) if fs else None

    cmp_f = newest('*P&G銷貨退回比較表*.xls')
    if not cmp_f:
        return None
    wb = xlrd.open_workbook(cmp_f, on_demand=True)

    # 月度×分類×年（2026/2025/2024）
    sh = wb.sheet_by_name('2025&2024&2023&2022比較表')
    def n(v):
        try: return int(float(v))
        except: return 0
    monthly = {}
    for yi, col0 in [('2026', 0), ('2025', 6), ('2024', 12)]:
        rows = []
        for i in range(2, 14):
            rows.append({'total': n(sh.cell_value(i, col0+1)), 'store': n(sh.cell_value(i, col0+2)),
                         'reject': n(sh.cell_value(i, col0+3)), 'other': n(sh.cell_value(i, col0+4))})
        monthly[yi] = rows

    # 業務×月：實際退貨 + 佔比（退貨÷出貨）
    # 月報自身分段：「合計(以上不含小北)」之前 = 一般業務（品質係數適用）；
    # 之後 = 特殊段（小北 / 林哲暉北寶總倉 / 吳建德金永發等政策性，不適用係數）
    sh2 = wb.sheet_by_name('2026分析總表')
    cut = sh2.nrows
    for i in range(2, sh2.nrows):
        if '不含小北' in str(sh2.cell_value(i, 0)):
            cut = i; break
    def _rep_row(i):
        name = str(sh2.cell_value(i, 0)).strip()
        mo, pct = [], []
        for m in range(12):
            ret = sh2.cell_value(i, 1+m*2)
            p   = sh2.cell_value(i, 2+m*2)
            ret = float(ret) if isinstance(ret, (int,float)) else 0
            p   = float(p) if isinstance(p, (int,float)) and p < 1 else None
            mo.append(round(ret)); pct.append(round(p*100, 2) if (p is not None and ret > 0) else None)
        return name, mo, pct
    # 特殊段到「總計」列為止；之後的高雄/台南=倉別拆分、再後面的業務列=小北明細（與小北列重複，獨立存放）
    total_row = sh2.nrows
    for i in range(cut+1, sh2.nrows):
        if str(sh2.cell_value(i, 0)).replace(' ','').strip() == '總計':
            total_row = i; break
    reps, special, xb_reps = [], [], []
    for i in range(2, sh2.nrows):
        name, mo, pct = _rep_row(i)
        if not name.startswith('MS') and name != '小北': continue
        if sum(mo) <= 0: continue
        item = {'n': name.split('.')[-1], 'code': name.split('.')[0] if '.' in name else '',
                'mo': mo, 'pct': pct, 'total': sum(mo)}
        if i < cut: reps.append(item)
        elif i < total_row: special.append(item)
        else: xb_reps.append(item)   # 小北業務明細（加總=小北列）
    reps.sort(key=lambda x: -x['total'])
    special.sort(key=lambda x: -x['total'])
    xb_reps.sort(key=lambda x: -x['total'])

    # TOP 退貨客戶（排行榜 XLS 年度累計）
    top_cust = []
    rank_f = newest('*P&G銷貨退回排行榜*.xls')
    if rank_f:
        wb2 = xlrd.open_workbook(rank_f, on_demand=True)
        for sn in wb2.sheet_names():
            if '2026' in sn and '前50' in sn:
                s3 = wb2.sheet_by_name(sn)
                for i in range(3, min(s3.nrows, 33)):
                    cn = str(s3.cell_value(i, 1)).strip()
                    if not cn: continue
                    top_cust.append({'c': cn, 'a': n(s3.cell_value(i, 2)),
                                     'rep': str(s3.cell_value(i, 3)).strip().split('.')[-1]})
                break

    print(f"  ✓ 退貨XLS: {os.path.basename(cmp_f)[:30]} 一般{len(reps)} 特殊{len(special)} 小北明細{len(xb_reps)} 客戶{len(top_cust)}")
    return {'monthly': monthly, 'reps': reps, 'special': special, 'xb_reps': xb_reps,
            'top_cust': top_cust, 'src': '寶捷ERP退貨憑單（月報）'}


# ── 庫存健康預警（紅黃綠燈）──────────────────────────────
def parse_inventory_health(path):
    """從 327-50 庫存報表算燈號。主力倉（主貨倉/出貨倉/康是美倉）按庫存天數分級：
    60+黃 / 90+橘 / 120+紅(D級出清) / 180+黑；無動銷(日均銷=0)與下架品直接進D級。
    即期倉/壞品倉獨立統計。"""
    from collections import defaultdict
    with open(path,'rb') as f:
        content = f.read().decode('utf-8', errors='replace')
    rows = re.findall(r'<TR[^>]*>(.*?)</TR>', content, re.I|re.S)

    def is_main(wh):   return ('主貨倉' in wh or '出貨倉' in wh or wh.strip() == '康是美倉')
    def is_expiry(wh): return '即期' in wh
    def is_damaged(wh):return '壞品' in wh

    skus = {}          # 產品編號 → 主力倉彙總
    exp_skus = defaultdict(lambda: {'q':0,'a':0.0,'n':'','b':'','wh':set()})
    dmg_skus = defaultdict(lambda: {'q':0,'a':0.0,'n':'','b':'','wh':set()})

    for row in rows[6:]:
        cells = re.findall(r'<T[DH][^>]*>(.*?)</T[DH]>', row, re.I|re.S)
        c = [re.sub(r'<[^>]+>','',x).strip() for x in cells]
        if len(c) < 16: continue
        sku, name, status, brand, wh = c[0], c[2], c[3], c[4] or '其他', c[5]
        if brand in SKIP_INV_BRANDS and brand != '其他': continue
        if '合計' in sku: continue
        try:
            qty = float(c[11]); amt = float(c[15])
        except: continue
        if qty <= 0: continue
        try: daily = float(c[7])
        except: daily = 0.0

        if is_expiry(wh):
            e = exp_skus[sku]; e['q'] += qty; e['a'] += amt; e['n'] = name[:30]; e['b'] = brand; e['wh'].add(wh)
        elif is_damaged(wh):
            e = dmg_skus[sku]; e['q'] += qty; e['a'] += amt; e['n'] = name[:30]; e['b'] = brand; e['wh'].add(wh)
        elif is_main(wh):
            if sku not in skus:
                skus[sku] = {'n':name[:30],'b':brand,'st':status,'q':0,'a':0.0,'daily':0.0,'wh':{}}
            s = skus[sku]
            s['q'] += qty; s['a'] += amt
            if daily > 0: s['daily'] = daily   # 全公司日均銷，各倉相同
            g = _wh_group(wh)
            s['wh'][g] = s['wh'].get(g, 0) + amt

    WH_NAMES = {'tainan':'台南','kaohsiung':'高雄','tp':'桃園','km':'康是美倉','cvs':'CVS','other':'其他'}
    light_sum = {k:{'n':0,'amt':0} for k in ['yellow','orange','red','black']}
    brand_sum = defaultdict(lambda: {'y':0,'o':0,'r':0,'k':0,'exp':0,'dmg':0})
    wh_sum    = defaultdict(lambda: {'y':0,'o':0,'r':0,'k':0})
    dlist = []
    for sku, s in skus.items():
        d = round(s['q']/s['daily']) if s['daily'] > 0 else None
        delisted = '下架' in s['st']
        if d is None or d >= 180: lk = 'black'
        elif d >= 120: lk = 'red'
        elif d >= 90:  lk = 'orange'
        elif d >= 60:  lk = 'yellow'
        else: lk = None
        if delisted and lk not in ('red','black'): lk = 'red'   # 下架品有庫存直接進D級
        if lk is None: continue
        light_sum[lk]['n'] += 1; light_sum[lk]['amt'] += s['a']
        bk = {'yellow':'y','orange':'o','red':'r','black':'k'}[lk]
        brand_sum[s['b']][bk] += s['a']
        for g, ga in s['wh'].items():
            wh_sum[WH_NAMES.get(g, g)][bk] += ga
        if lk in ('red','black'):
            whs = sorted(s['wh'].items(), key=lambda x:-x[1])
            wh_label = '/'.join(WH_NAMES.get(g, g) for g, _ in whs[:2])
            dlist.append({'s':sku,'n':s['n'],'b':s['b'],'q':int(s['q']),
                          'a':int(s['a']),'d':d,'wh':wh_label,
                          'st':'下架' if delisted else ('無動銷' if d is None else '')})

    for e in exp_skus.values(): brand_sum[e['b']]['exp'] += e['a']
    for e in dmg_skus.values(): brand_sum[e['b']]['dmg'] += e['a']

    dlist.sort(key=lambda x:-x['a'])
    top = lambda dd: sorted(
        [{'n':v['n'],'b':v['b'],'q':int(v['q']),'a':int(v['a']),'wh':'/'.join(sorted(v['wh']))} for v in dd.values()],
        key=lambda x:-x['a'])[:12]
    return {
        'light':  {k:{'n':v['n'],'amt':int(v['amt'])} for k,v in light_sum.items()},
        'whs':    sorted([{'w':w,**{k:int(v[k]) for k in ['y','o','r','k']}}
                          for w,v in wh_sum.items()],
                         key=lambda x:-(x['r']+x['k'])),
        'brands': sorted([{'b':b,**{k:int(v[k]) for k in ['y','o','r','k','exp','dmg']}}
                          for b,v in brand_sum.items() if sum(v.values())>0],
                         key=lambda x:-(x['r']+x['k'])),
        'expiry_total':  int(sum(e['a'] for e in exp_skus.values())),
        'damaged_total': int(sum(e['a'] for e in dmg_skus.values())),
        'dlist': dlist[:60],
        'expiry_top':  top(exp_skus),
        'damaged_top': top(dmg_skus),
    }


def _brand_pl_cache_path():
    return DASHBOARD.parent / 'data' / 'brand_pl_monthly.json'

def load_brand_monthly_cache():
    import json as _j
    p = _brand_pl_cache_path()
    return _j.loads(p.read_text('utf-8')) if p.exists() else {}

def save_brand_monthly_cache(cache):
    import json as _j
    p = _brand_pl_cache_path()
    p.parent.mkdir(exist_ok=True)
    p.write_text(_j.dumps(cache, ensure_ascii=False), 'utf-8')

def calc_brand_pl(ytd, period_label, monthly_cache=None, fy_month_list=None):
    """從 YTD parse_xls 結果自動計算 BRAND_PL。
    fy_month_list: [(year, month), ...] 財年各月順序，用於月度欄。
    monthly_cache: {'{year}-{mm}': {brand_net, brand_giv}}
    """
    net_d = ytd.get('brand_net', {})
    giv_d = ytd.get('brand_giv', {})

    # 月度快取 → 各品牌 monthly contrib 陣列
    mo_labels, mo_by_brand = [], {}
    if monthly_cache and fy_month_list:
        mo_labels = [f'{cy}/{cm:02d}' for cy, cm in fy_month_list]
        for b in net_d:
            mo_by_brand[b] = []
            for cy, cm in fy_month_list:
                md = monthly_cache.get(f'{cy}-{cm:02d}', {})
                m_net = md.get('brand_net', {}).get(b, 0)
                m_giv = md.get('brand_giv', {}).get(b, 0)
                m_kbd  = round(m_giv / 1.05 * KBD_RATES.get(b, 0.15))
                m_cogs = round(m_net * BRAND_COGS_RATE.get(b, 0.95))
                mo_by_brand[b].append(m_net - m_cogs + m_kbd)

    brands = []
    for b in sorted(net_d.keys(), key=lambda x: -net_d.get(x, 0)):
        net = net_d.get(b, 0)
        if net <= 0: continue
        giv  = giv_d.get(b, 0)
        kbd  = round(giv / 1.05 * KBD_RATES.get(b, 0.15))
        cogs = round(net * BRAND_COGS_RATE.get(b, 0.95))
        gm   = round((net - cogs) / net * 100, 1) if net else 0
        entry = {'b':b,'net':int(net),'ret':0,'cogs':cogs,
                 'kbd':kbd,'contrib':net-cogs+kbd,'gm':gm}
        if mo_by_brand.get(b):
            entry['mo'] = mo_by_brand[b]
        brands.append(entry)

    result = {'period': period_label, 'brands': brands}
    if mo_labels:
        result['months'] = mo_labels
    return result


# ── 更新 dashboard.html ──────────────────────────────────
def update_dashboard(q, m, mo, iya_q, iya_mo, pays_list, uncollected, inv_data=None, ar_reps=None, ar_unpaid=0, km_sell=None, iya_m=None, inv_health=None, brand_pl=None, today_ship=0):
    html = DASHBOARD.read_text(encoding='utf-8')
    def esc(s): return s.replace("'","`")
    def fm(n): return '$' + f"{int(round(n)):,}"

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

    mo_store_early = mo.get('store', {})  # 本月各門市
    km_total  = sum(d['amt'] for d in km_stores.values())   # 季累計 (供 total_q 等用)
    km_mo     = sum(mo_store_early.get(n,{}).get('amt',0) for n in km_stores)  # 本月
    km_apr    = sum(store_m.get(n,{}).get('amt',0) for n in km_stores)
    km_cnt    = len(km_stores)
    cvs_total = sum(d['amt'] for d in cvs_stores.values())
    cvs_mo    = sum(mo_store_early.get(n,{}).get('amt',0) for n in cvs_stores)
    cvs_apr   = sum(store_m.get(n,{}).get('amt',0) for n in cvs_stores)
    cvs_cnt   = len(cvs_stores)
    xb_total  = sum(d['amt'] for d in xb_stores.values())
    xb_mo     = sum(mo_store_early.get(n,{}).get('amt',0) for n in xb_stores)
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
    sub_kpi('季累計', fm(total_q))
    sub_kpi('IYA 成長', f'+{iya_pct}%' if iya_pct>=0 else f'{iya_pct}%')
    if ar_unpaid:
        sub_kpi('應收未付', fm(ar_unpaid), '應收帳款未付')

    # ── 通路明細：從 DERP 自動計算（XLS 僅作輔助對照）──
    ch_mo_data = mo.get('ch', {})

    # 直送盤商：從 grp_mo 用集團名稱比對
    DIRECT_GRP = [
        ('統一藥品', '康是美'),
        ('捷盟',    '捷盟(7-11)'),
        ('全台物流', '全台(全家)'),
        ('萊爾富',  '萊爾富'),
        ('來來物流', '來來(OK)'),
        ('來來(OK)', '來來(OK)'),
    ]
    CHAIN_GRP = [
        ('A01-大樹', '大樹'),
        ('A02-丁丁', '丁丁'),
        ('A03-啄木鳥','啄木鳥'),
        ('小北',     '小北'),
        ('B&C',      'B&C'),
    ]
    direct_totals = {}
    chain_totals  = {}
    for grp_name, amt in grp_mo.items():
        for pat, label in DIRECT_GRP:
            if pat in grp_name:
                direct_totals[label] = direct_totals.get(label, 0) + amt
                break
        for pat, label in CHAIN_GRP:
            if pat in grp_name:
                chain_totals[label] = chain_totals.get(label, 0) + amt
                break

    km_derp      = direct_totals.get('康是美', 0)
    cvs_others   = sum(v for k,v in direct_totals.items() if k != '康是美')
    all_direct   = km_derp + cvs_others
    pharma_derp  = sum(ch_mo_data.get(c, 0) for c in [
        '小型藥局', '大型藥局', '月子中心', '大型嬰兒專門店', '小型嬰兒專門店'
    ])
    super_derp   = sum(ch_mo_data.get(c, 0) for c in [
        '超級市場', '大型小超', '小型小超'
    ])
    pander_derp  = sum(ch_mo_data.get(c, 0) for c in [
        '盤商:量販/超市/傳統商店', '盤商:專業領域通路(國外)'
    ])
    # 業務通路 = DERP rep 加總（不依 AC通路分類，避免跨組業務造成誤差）
    rep_mo_data  = mo.get('rep', {})
    biz_rep_total = int(sum(r.get('amt', 0) for r in rep_mo_data.values()))
    derp_total   = total_mo

    # KPI cards — 100% DERP，不依賴 XLS
    xls_perf = None
    try:
        xls_perf = parse_xls_performance()
    except Exception as e:
        print(f"  ⚠ XLS讀取失敗: {e}")
    pg_total_fin  = derp_total
    xls_total_fin = xls_perf['pg_total'] if xls_perf else 0
    pharma_final  = pharma_derp
    super_final   = super_derp
    chain_fin    = {k: int(chain_totals.get(k, 0)) for k in ['丁丁','啄木鳥','大樹','小北','B&C']}
    dir_fin      = {
        '全台(全家)': int(direct_totals.get('全台(全家)', 0)),
        '捷盟(7-11)': int(direct_totals.get('捷盟(7-11)', 0)),
        '萊爾富':     int(direct_totals.get('萊爾富', 0)),
        '來來(OK)':   int(direct_totals.get('來來(OK)', 0)),
        '康是美':     int(km_derp),
    }
    sub_kpi('P&G 本月業績（全通路）', fm(pg_total_fin), '含康是美/CVS直送')
    if xls_total_fin:
        sub_kpi('業務通路本月', fm(xls_total_fin), '業務員管轄通路（不含直送）')
    sub_kpi('交易客戶', f'{cust_cnt:,}', f'目標 {cust_cnt:,} 門市')
    sub_kpi('藥房+超市業務本月', fm(biz_rep_total), '業務 rep 加總（不含KM/CVS直送）')
    sub_kpi('康是美本月',   fm(km_derp),     '直送門市')
    sub_kpi('CVS盤商本月',  fm(cvs_others),  '全家+7-11+萊爾富+OK')
    if pander_derp > 0:
        sub_kpi('盤商本月', fm(int(pander_derp)), '量販/超市/傳統商店盤商')
    if today_ship > 0:
        sub_kpi('今日出貨', fm(today_ship), '截至今日開單金額')
    print(f"  ✓ DERP 通路KPI: 藥房{pharma_derp//10000}萬 "
          f"超市{super_derp//10000}萬 KM{km_derp//10000}萬")

    # ── 通路明細 JS arrays ──
    biz_rows = [
        f"  {{n:'業務通路合計',v:{biz_rep_total}}}",
        f"  {{n:'└ 丁丁',v:{chain_fin.get('丁丁',0)}}}",
        f"  {{n:'└ 啄木鳥',v:{chain_fin.get('啄木鳥',0)}}}",
        f"  {{n:'└ 大樹',v:{chain_fin.get('大樹',0)}}}",
        f"  {{n:'└ 小北',v:{chain_fin.get('小北',0)}}}",
        f"  {{n:'└ B&C',v:{chain_fin.get('B&C',0)}}}",
    ]
    direct_rows = [
        f"  {{n:'全台(全家)',v:{dir_fin['全台(全家)']}}}",
        f"  {{n:'捷盟(7-11)',v:{dir_fin['捷盟(7-11)']}}}",
        f"  {{n:'萊爾富',v:{dir_fin['萊爾富']}}}",
        f"  {{n:'來來(OK)',v:{dir_fin['來來(OK)']}}}",
        f"  {{n:'康是美',v:{dir_fin['康是美']}}}",
    ]

    # ── AC通路明細 + 客戶展開（CH_DETAIL）──
    # 整理 store_mo：依 AC通路分類，每通路列出前20大客戶（含業務）
    store_mo = mo.get('store', {})
    ch_detail = {}
    for st_name, st in store_mo.items():
        ac = st.get('ch', '其他') or '其他'
        amt = st.get('amt', 0)
        if amt <= 0: continue
        if ac not in ch_detail:
            ch_detail[ac] = {'v': 0, 'customers': []}
        ch_detail[ac]['v'] += amt
        ch_detail[ac]['customers'].append({
            'n': st_name[:20],
            'v': int(amt),
            'r': st.get('rep', '')
        })
    # 排序 customers by amt desc, keep top 20
    ch_detail_js_parts = []
    for ac, data in sorted(ch_detail.items(), key=lambda x: -x[1]['v']):
        top_cust = sorted(data['customers'], key=lambda x: -x['v'])[:20]
        cust_js = ','.join(
            f"{{n:{repr(c['n'])},v:{c['v']},r:{repr(c['r'])}}}" for c in top_cust
        )
        ch_detail_js_parts.append(
            f"  {{n:{repr(ac)},v:{int(data['v'])},customers:[{cust_js}]}}"
        )
    ch_detail_js = 'const CH_DETAIL=[\n' + ',\n'.join(ch_detail_js_parts) + '\n];'
    html = re.sub(r'const XLS_BIZ=\[[\s\S]*?\];',
                  'const XLS_BIZ=[\n'+',\n'.join(biz_rows)+'\n];', html)
    html = re.sub(r'const XLS_DIRECT=\[[\s\S]*?\];',
                  'const XLS_DIRECT=[\n'+',\n'.join(direct_rows)+'\n];', html)
    html = re.sub(r'const XLS_TOTAL=\d+;',
                  f'const XLS_TOTAL={xls_total_fin if xls_total_fin else pg_total_fin};', html)
    # CH_DETAIL: replace if exists, else inject after XLS_TOTAL
    if 'const CH_DETAIL=' in html:
        html = re.sub(r'const CH_DETAIL=\[[\s\S]*?\];', ch_detail_js, html)
    else:
        html = html.replace('const XLS_TOTAL=', ch_detail_js + '\nconst XLS_TOTAL=', 1)

    # ── 集團排行 KPIs（以本月排序）──
    grp_s     = sorted(grp_q.keys(), key=lambda n: -grp_mo.get(n, 0))[:15]
    grp_s     = [(n, grp_q[n]) for n in grp_s]   # (name, 季累計) pairs, 本月 order
    grp_mo_total = sum(grp_mo.values())
    grp_total = sum(grp_q.values())
    grp_count = len(grp_q)
    top5_sum  = sum(grp_mo.get(n,0) for n,_ in grp_s[:5])
    top5_pct  = round(top5_sum/grp_mo_total*100, 1) if grp_mo_total else 0
    top1_name = grp_s[0][0] if grp_s else ''
    top1_amt  = grp_mo.get(top1_name, 0)  # 本月第1名金額
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
    km_pct = round(km_mo/total_mo*100, 1) if total_mo else 0
    km_mo_chg = round((km_mo/km_apr-1)*100, 1) if km_apr else 0
    sub_kpi('康是美本月', fm(km_mo), f'↑ +{km_mo_chg}% vs 上月' if km_mo_chg >= 0 else f'↓ {km_mo_chg}% vs 上月')
    sub_kpi('康是美上月', fm(km_apr), '完整月份')
    # 康是美分點數已拿掉（送貨點非實際門市數）
    sub_kpi('康是美佔比', f'{km_pct}%', '高度集中' if km_pct > 40 else '佔全公司')

    # ── CVS KPIs ──
    cvs_pct = round(cvs_mo/total_mo*100, 1) if total_mo else 0
    cvs_mo_chg = round((cvs_mo/cvs_apr-1)*100, 1) if cvs_apr else 0
    sub_kpi('CVS本月', fm(cvs_mo), f'↑ +{cvs_mo_chg}% vs 上月' if cvs_mo_chg >= 0 else f'↓ {cvs_mo_chg}% vs 上月')
    sub_kpi('CVS上月', fm(cvs_apr), '完整月份')
    sub_kpi('CVS門市數', f'{cvs_cnt}', '便利商店')
    sub_kpi('CVS佔比', f'{cvs_pct}%', '佔全公司')

    # ── 小北 KPIs ──
    xb_pct = round(xb_mo/total_mo*100, 1) if total_mo else 0
    xb_mo_chg = round((xb_mo/xb_apr-1)*100, 1) if xb_apr else 0
    sub_kpi('小北本月', fm(xb_mo), f'↑ +{xb_mo_chg}% vs 上月' if xb_mo_chg >= 0 else f'↓ {xb_mo_chg}% vs 上月')
    sub_kpi('小北上月', fm(xb_apr), '完整月份')
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

    # ── helper: brand top5 for a store ──
    def top5_brands(brands_dict, max_n=5):
        top = sorted(brands_dict.items(), key=lambda x:-x[1])[:max_n]
        return '[' + ','.join(f"{{b:'{b}',v:{int(v)}}}" for b,v in top if v>0) + ']'

    # ── GRP ──
    iya_grp_data  = iya_q.get('grp',{})  if iya_q  else {}
    iya_mo_grp    = iya_mo.get('grp',{}) if iya_mo else {}
    grp_brands_q  = q.get('grp_brands',{})
    lines = []
    for n, s5 in grp_s:
        gb = grp_brands_q.get(n, {})
        lines.append(
            f"  {{n:'{esc(n)}',s5:{int(s5)},s4:{int(grp_m.get(n,0))},"
            f"s3:{int(grp_mo.get(n,0))},iya:{int(iya_grp_data.get(n,0))},"
            f"iya3:{int(iya_mo_grp.get(n,0))},br:{top5_brands(gb)}}}"
        )
    html = re.sub(r'const GRP=\[[\s\S]*?\];',
                  'const GRP=[\n'+',\n'.join(lines)+'\n];', html)

    # ── STORES (排除 KM 和 CVS，按本月排序 Top 100) ──
    iya_q_store  = iya_q.get('store',{})  if iya_q  else {}
    iya_mo_store = iya_mo.get('store',{}) if iya_mo else {}
    mo_store     = mo.get('store',{})
    st_s = sorted(other_stores.items(),
                  key=lambda x: -mo_store.get(x[0],{}).get('amt',0))[:100]
    lines = []
    for n, d in st_s:
        br = top5_brands(d.get('brands',{}))
        v3 = int(mo_store.get(n,{}).get('amt',0))
        iy5 = int(iya_q_store.get(n,{}).get('amt',0))
        iy3 = int(iya_mo_store.get(n,{}).get('amt',0))
        lines.append(
            f"  {{s:'{esc(n)}',g:'{esc(d['grp'])}',r:'{esc(d['rep'])}',ch:'{esc(d['ch'])}',"
            f"v5:{int(d['amt'])},v4:{int(store_m.get(n,{}).get('amt',0))},"
            f"v3:{v3},iy5:{iy5},iy3:{iy3},br:{br}}}"
        )
    html = re.sub(r'const STORES=\[[\s\S]*?\];',
                  'const STORES=[\n'+',\n'.join(lines)+'\n];', html)

    # ── CHS ──
    ch_s = sorted(ch_q.items(), key=lambda x:-x[1])[:10]
    lines = [f"  {{n:'{esc(n)}',s5:{int(v)},s4:{int(ch_m.get(n,0))}}}"
             for n,v in ch_s]
    html = re.sub(r'const CHS=\[[\s\S]*?\];',
                  'const CHS=[\n'+',\n'.join(lines)+'\n];', html)

    # ── UNIF (康是美分點，按本月排序) ──
    km_s = sorted(km_stores.items(),
                  key=lambda x: -mo_store.get(x[0],{}).get('amt',0))[:50]
    def unif_label(name):
        m2 = re.search(r'(\d+)\s*[\(（]([^)\）]+)[\)）]', name)
        return f"{m2.group(1)}({m2.group(2)})" if m2 else name[:20]
    lines = []
    for n, d in km_s:
        br = top5_brands(d.get('brands',{}))
        v3 = int(mo_store.get(n,{}).get('amt',0))
        iy5 = int(iya_q_store.get(n,{}).get('amt',0))
        iy3 = int(iya_mo_store.get(n,{}).get('amt',0))
        lines.append(
            f"  {{s:'{unif_label(n)}',r:'{esc(d['rep'])}',v5:{int(d['amt'])},v4:{int(store_m.get(n,{}).get('amt',0))},"
            f"v3:{v3},iy5:{iy5},iy3:{iy3},br:{br}}}"
        )
    if lines:
        html = re.sub(r'const UNIF=\[[\s\S]*?\];',
                      'const UNIF=[\n'+',\n'.join(lines)+'\n];', html)

    # ── CVS_STORES（按本月排序）──
    cvs_s = sorted(cvs_stores.items(),
                   key=lambda x: -mo_store.get(x[0],{}).get('amt',0))[:50]
    lines = []
    for n, d in cvs_s:
        br = top5_brands(d.get('brands',{}))
        v3 = int(mo_store.get(n,{}).get('amt',0))
        iy5 = int(iya_q_store.get(n,{}).get('amt',0))
        iy3 = int(iya_mo_store.get(n,{}).get('amt',0))
        lines.append(
            f"  {{s:'{esc(n[:22])}',r:'{esc(d['rep'])}',v5:{int(d['amt'])},v4:{int(store_m.get(n,{}).get('amt',0))},"
            f"v3:{v3},iy5:{iy5},iy3:{iy3},br:{br}}}"
        )
    html = re.sub(r'const CVS_STORES=\[[\s\S]*?\];',
                  'const CVS_STORES=[\n'+(',\n'.join(lines) if lines else '')+'\n];', html)

    # ── XB_STORES (小北，按本月排序) ──
    # iy3 改為「去年上月全月」，讓退步分店表月初也有足夠資料（不再只有3家）
    iya_m_store = iya_m.get('store', {}) if iya_m else {}
    xb_s = sorted(xb_stores.items(),
                  key=lambda x: -mo_store.get(x[0],{}).get('amt',0))[:50]
    lines = []
    for n, d in xb_s:
        br = top5_brands(d.get('brands',{}))
        v3 = int(mo_store.get(n,{}).get('amt',0))
        iy5 = int(iya_q_store.get(n,{}).get('amt',0))
        iy3 = int(iya_m_store.get(n,{}).get('amt',0))  # 去年上月全月
        lines.append(
            f"  {{s:'{esc(n[:22])}',r:'{esc(d['rep'])}',v5:{int(d['amt'])},v4:{int(store_m.get(n,{}).get('amt',0))},"
            f"v3:{v3},iy5:{iy5},iy3:{iy3},br:{br}}}"
        )
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

    # 從 XLS 讀業務月目標（優先）
    xls_perf = None
    try:
        xls_perf = parse_xls_performance()
    except Exception as e:
        print(f"  ⚠ XLS業務目標讀取失敗: {e}")
    xls_rep_tgt = xls_perf.get('rep_tgt', {}) if xls_perf else {}

    rep_lines = []
    for rn, rd in sorted(rep_q.items(), key=lambda x:-x[1]['amt']):
        act   = int(rep_mo.get(rn,{}).get('amt',0))
        q_val = int(rd['amt'])
        iya   = int(rep_iya.get(rn,{}).get('amt',0)) if rep_iya else int(act*.9)
        code  = rd.get('code','')
        # 目標優先順序：XLS業績追踨 > HTML舊值 > 0
        tgt = xls_rep_tgt.get(code, existing_tgts.get(rn, (0,0))[0])
        _, qT = existing_tgts.get(rn, (0, 0))
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

    # ── AR 應收帳款資料注入 ──
    if ar_reps:
        ar_lines = [
            f"  {{code:'{r['code']}',name:'{esc(r['name'])}',sales:{r['sales']},cleared:{r['cleared']},unpaid:{r['unpaid']}}}"
            for r in sorted(ar_reps, key=lambda x: x['unpaid'], reverse=True)
        ]
        html = re.sub(r'const AR_REPS=\[[\s\S]*?\];',
                      'const AR_REPS=[\n'+',\n'.join(ar_lines)+'\n];', html)
        html = re.sub(r'const AR_TOTAL=\d+;', f'const AR_TOTAL={ar_unpaid};', html)

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
        def wh_js(wh):
            if not wh: return '{}'
            parts = []
            for k in ['tainan','kaohsiung','tp','km','cvs']:
                if k in wh:
                    w = wh[k]
                    d_str = str(w['d']) if w['d'] is not None else 'null'
                    parts.append(f"{k}:{{q:{w['q']},a:{w['a']},d:{d_str}}}")
            return '{'+','.join(parts)+'}'
        brand_lines = []
        for b in inv_data:
            tq = ','.join(f"{{s:'{jstr(x['s'])}',n:'{jstr(x['n'])}',q:{x['q']},a:{x['a']},d:{x['d'] if x['d'] is not None else 'null'},wh:{wh_js(x.get('wh',{}))}}}" for x in b['topQ'])
            ta = ','.join(f"{{s:'{jstr(x['s'])}',n:'{jstr(x['n'])}',q:{x['q']},a:{x['a']},d:{x['d'] if x['d'] is not None else 'null'},wh:{wh_js(x.get('wh',{}))}}}" for x in b['topA'])
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

    # ── 退貨分析 RETURNS（月報XLS有更新才覆寫）──
    try:
        returns = parse_returns_xls()
    except Exception as e:
        returns = None
        print(f"  ⚠ 退貨XLS解析失敗: {e}")
    if returns:
        import json as _json
        html = re.sub(r'const RETURNS=\{[\s\S]*?\};',
                      'const RETURNS=' + _json.dumps(returns, ensure_ascii=False) + ';',
                      html)

    # ── 庫存健康預警 INV_HEALTH ──
    if inv_health:
        import json as _json
        html = re.sub(r'const INV_HEALTH=\{[\s\S]*?\};',
                      'const INV_HEALTH=' + _json.dumps(inv_health, ensure_ascii=False) + ';',
                      html)
        print(f"  ✓ INV_HEALTH 寫入: D級 {len(inv_health['dlist'])} SKU, 即期 {inv_health['expiry_total']:,}, 壞品 {inv_health['damaged_total']:,}")

    # ── 品牌損益 BRAND_PL ──
    if brand_pl:
        import json as _json
        html = re.sub(r'const BRAND_PL=\{[\s\S]*?\};',
                      'const BRAND_PL=' + _json.dumps(brand_pl, ensure_ascii=False) + ';',
                      html)
        print(f"  ✓ BRAND_PL 更新: {len(brand_pl['brands'])} 品牌, 期間={brand_pl['period']}")

    # ── 康是美實銷 KM_SELL ──
    if km_sell:
        import json as _json
        weeks_js      = _json.dumps(km_sell['weeks'], ensure_ascii=False)
        by_qty_js     = _json.dumps(km_sell['by_brand_qty'], ensure_ascii=False)
        by_amt_js     = _json.dumps(km_sell['by_brand_amt'], ensure_ascii=False)
        ship_js       = _json.dumps(km_sell.get('ship_by_brand', {}), ensure_ascii=False)
        sku_lines = []
        for s in km_sell['by_sku']:
            bc = s['barcode'].split('\n')[0].strip().replace("'", '')  # 取第一個條碼，清換行
            dc_js = (f",dc:{s['dc']},transit:{s.get('transit',0)},kst:'{s.get('kst','')}'"
                     if 'dc' in s else '')
            sku_lines.append(
                f"  {{brand:'{esc(s['brand'])}',name:'{esc(s['name'])}',barcode:'{bc}',"
                f"retail:{s['retail']},cost:{s.get('cost',0)},weeks:{s['weeks']},amt_weeks:{s['amt_weeks']}{dc_js}}}"
            )
        by_sku_js = '[\n' + ',\n'.join(sku_lines) + '\n]'
        html = re.sub(r'const KM_SELL=\{[^;]*\};',
                      f'const KM_SELL={{weeks:{weeks_js},by_brand_qty:{by_qty_js},by_brand_amt:{by_amt_js},ship_by_brand:{ship_js},by_sku:{by_sku_js}}};',
                      html, flags=re.S)
        print(f'  ✓ KM_SELL 寫入: {len(km_sell["by_sku"])}筆 SKU')

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
    if xls_perf:
        print(f"   本月(XLS):{fm(xls_perf['pg_total'])}  季累計:{fm(total_q)}  IYA:{iya_pct:+.1f}%  交易客戶:{xls_perf['traded']:,}/{xls_perf['traded_tgt']:,}")
        print(f"   藥房業務:{fm(xls_perf['pharma'])}  超市業務:{fm(xls_perf['super'])}  KM直送:{fm(xls_perf['km_direct'])}  CVS盤商:{fm(xls_perf['cvs_others'])}")
    else:
        print(f"   本月:{fm(total_mo)}  季累計:{fm(total_q)}  IYA:{iya_pct:+.1f}%  交易客戶:{cust_cnt:,}")
    print(f"   KM本月:{fm(km_mo)}({km_cnt}點)  CVS本月:{fm(cvs_mo)}({cvs_cnt}點)  小北本月:{fm(xb_mo)}({xb_cnt}點)")
    print(f"   通路:{len(ch_s)}種  業務:{len(rep_lines)}人{inv_summary}")


# ── Main ─────────────────────────────────────────────────
def main():
    print(f"\n{'='*52}\n  DERP → Dashboard 全指標更新  {today}\n{'='*52}\n")
    s = get_session()

    print("[下載 本期]")
    data_q  = dl_sales(s, q_start,  today,  "季累計")
    data_mo = dl_sales(s, mo_start, today,  "本月")
    data_m  = dl_sales(s, m_start, m_end, "上月全月")
    # P&G 財年：7 月起，跨兩個日曆年
    fy_start_year = _today.year if _today.month >= 7 else _today.year - 1
    ytd_start = f'{fy_start_year}/07/01'
    data_ytd = dl_sales(s, ytd_start, today, "財年YTD(品牌損益)")

    print("\n[下載 去年同期 IYA]")
    data_iya_q  = dl_sales(s, ly_qstart,  ly_today, "去年季累計")
    data_iya_mo  = dl_sales(s, ly_mostart, ly_today, "去年本月")
    data_iya_m   = dl_sales(s, ly_m_start, ly_m_end, "去年上月全月")

    print("\n[收款 Excel]")
    pays_list, uncollected = parse_local_payment_xls()

    print("\n[應收帳款 AR]")
    ar_reps, ar_unpaid = parse_derp_ar_xls()

    print("\n[解析]")
    q      = parse_xls(data_q);      print(f"  季累計  → 集團:{len(q.get('grp',{}))} 門市:{len(q.get('store',{}))} 業務:{len(q.get('rep',{}))}")
    mo     = parse_xls(data_mo);     print(f"  本月    → 集團:{len(mo.get('grp',{}))}")
    m      = parse_xls(data_m);      print(f"  上月全月 → 集團:{len(m.get('grp',{}))}")
    iya_q  = parse_xls(data_iya_q);  print(f"  去年季  → 集團:{len(iya_q.get('grp',{}))}")
    iya_mo  = parse_xls(data_iya_mo);  print(f"  去年月  → 集團:{len(iya_mo.get('grp',{}))}")
    iya_m   = parse_xls(data_iya_m);   print(f"  去年上月全月 → 集團:{len(iya_m.get('grp',{}))}")
    ytd     = parse_xls(data_ytd);     print(f"  YTD 品牌 → {len(ytd.get('brand_net',{}))} 品牌")
    pays_list, uncollected = parse_local_payment_xls()

    if not q.get('grp'):
        if mo.get('grp'):
            print("⚠ 季累計失敗，以本月資料代替季累計（數字偏低為正常）")
            q = mo  # 用本月頂替，讓看板能繼續更新
        else:
            print("✗ 解析失敗（季累計+本月都空白）"); sys.exit(1)

    print("\n[庫存下載]")
    inv_data = None
    inv_health = None
    try:
        ws = get_web_session()
        if ws:
            inv_path = dl_inventory(ws)
            if inv_path:
                inv_data = parse_inventory_html(inv_path)
                inv_health = parse_inventory_health(inv_path)
    except Exception as e:
        print(f"  ⚠ 庫存下載失敗（業績仍正常更新）: {e}")

    # 康是美實銷：每週一才抓（週銷量，7天更新一次，不需要每天）
    km_sell = None
    if _today.weekday() == 0:  # 0 = 週一
        print("\n[康是美實銷]（週一更新）")
        try:
            sys.path.insert(0, os.path.dirname(__file__))
            from cosmed_fetch import fetch_all_km_sell
            km_sell = fetch_all_km_sell()
        except Exception as e:
            print(f"  ⚠ 康是美實銷抓取失敗: {e}")
        if km_sell and km_sell.get('weeks'):
            try:
                w0 = km_sell['weeks'][0].split('~')[0]
                w1 = km_sell['weeks'][-1].split('~')[1]
                km_sell['ship_by_brand'] = fetch_km_ship(
                    f'{w0[:4]}/{w0[4:6]}/{w0[6:]}', f'{w1[:4]}/{w1[4:6]}/{w1[6:]}')
            except Exception as e:
                print(f"  ⚠ 康是美出貨(610-24)抓取失敗: {e}")
    else:
        print(f"\n[康是美實銷] 跳過（今天{['一','二','三','四','五','六','日'][_today.weekday()]}，週一才更新）")

    # 退貨憑單清單（登記頁資料源，當月+上月）
    try:
        import json as _json
        from datetime import timedelta as _td
        first_prev = (_today.replace(day=1) - _td(days=1)).replace(day=1)
        vouchers = fetch_sr_vouchers(first_prev.strftime('%Y/%m/%d'), _today.strftime('%Y/%m/%d'))
        _data_dir = DASHBOARD.parent / 'data'
        os.makedirs(_data_dir, exist_ok=True)
        (_data_dir / 'sr_pending.json').write_text(
            _json.dumps({'updated': today, 'vouchers': vouchers}, ensure_ascii=False),
            encoding='utf-8')
        print(f"  ✓ data/sr_pending.json: {len(vouchers)} 張")
    except Exception as e:
        print(f"  ⚠ 退貨憑單清單失敗（不影響看板）: {e}")

    # ── 月度品牌損益快取（財年各月只抓一次）──
    import calendar as _cal
    print("\n[月度品牌損益快取]")
    monthly_cache = load_brand_monthly_cache()

    # 財年月份序列：[(year, month), ...]，從財年起月到上個月
    fy_months = []
    y, mo_idx = fy_start_year, 7
    while (y, mo_idx) < (_today.year, _today.month):
        fy_months.append((y, mo_idx))
        mo_idx += 1
        if mo_idx > 12:
            mo_idx = 1; y += 1

    for cy, cm in fy_months:
        cache_key = f'{cy}-{cm:02d}'
        if cache_key not in monthly_cache:
            m0 = f'{cy}/{cm:02d}/01'
            m1_day = _cal.monthrange(cy, cm)[1]
            m1 = f'{cy}/{cm:02d}/{m1_day}'
            md = parse_xls(dl_sales(s, m0, m1, f'{cy}/{cm:02d}(快取)'))
            monthly_cache[cache_key] = {
                'brand_net': md.get('brand_net', {}),
                'brand_giv': md.get('brand_giv', {})
            }
            print(f"  ✓ {cy}/{cm:02d} 新增快取")
        else:
            print(f"  · {cy}/{cm:02d} 已有快取")

    # 當月用已下載的 mo
    cur_key = f'{_today.year}-{_today.month:02d}'
    monthly_cache[cur_key] = {
        'brand_net': mo.get('brand_net', {}),
        'brand_giv': mo.get('brand_giv', {})
    }
    save_brand_monthly_cache(monthly_cache)

    fy_end_year = fy_start_year + 1
    period_label = f'{fy_start_year}/{fy_end_year % 100:02d} 財年（7月~{_today.month}月）'
    brand_pl = calc_brand_pl(ytd, period_label, monthly_cache, fy_months + [(_today.year, _today.month)])
    xls_perf = None
    try:
        xls_perf = parse_xls_performance()
    except Exception as e:
        print(f"  ⚠ XLS業務目標讀取失敗: {e}")
    today_ship = xls_perf.get('today_ship', 0) if xls_perf else 0
    if today_ship: print(f"  今日出貨（業績追踨H欄）: ${int(round(today_ship)):,}")
    update_dashboard(q, m, mo, iya_q, iya_mo, pays_list, uncollected, inv_data, ar_reps, ar_unpaid, km_sell, iya_m, inv_health, brand_pl, today_ship)

    # iWMS 效期（token 從 Cloudflare KV 取，由 bookmarklet 每日更新）
    print("\n[iWMS 效期庫存]")
    try:
        from fetch_iwms import main as iwms_main
        iwms_main()
    except Exception as e:
        print(f"  ⚠ iWMS 更新失敗（不影響其他指標）: {e}")

    # 排錯驗證：比對 XLS 與看板數字
    print("\n[排錯驗證]")
    try:
        import subprocess, sys as _sys
        _vpath = Path(__file__).parent / 'verify_dashboard.py'
        subprocess.run([_sys.executable, str(_vpath)], check=False)
    except Exception as e:
        print(f"  ⚠ 驗證腳本失敗: {e}")


if __name__ == "__main__":
    main()
