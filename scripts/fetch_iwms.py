#!/usr/bin/env python3
"""
iWMS 效期庫存抓取
token 從 Cloudflare KV 取（由 bookmarklet 更新）
輸出：IWMS_EXPIRY JS 物件，寫入 dashboard.html
"""
import urllib.request, json, ssl, re, os, sys
from datetime import date, timedelta
from pathlib import Path

DASHBOARD = Path(__file__).parent.parent / 'dashboard.html'
BASE      = 'https://iwms.logistics.org.tw/iwms-standard'
CF_URL    = 'https://baojieh-dashboard.pages.dev/api/iwms-token'
HEADERS_TPL = {
    'Referer': 'https://iwms.logistics.org.tw/',
    'Origin':  'https://iwms.logistics.org.tw',
    'User-Agent': 'Mozilla/5.0',
}
CTX = ssl._create_unverified_context()
# 忽略這些「假有效期」（代表無限期或資料未填）
IGNORE_DATES = {'2100-01-01','2099-01-01','2039-06-13','2100-12-31','2039-12-31','2039-01-01'}

DC_LIST = [
    {'dcId': 11, 'dcCode': 'BJ_KS', 'name': '高雄倉'},
    {'dcId': 17, 'dcCode': 'BJ_TN', 'name': '台南倉'},
]


def get_token():
    secret = os.environ.get('IWMS_SECRET', '')
    url = CF_URL + (f'?secret={secret}' if secret else '')
    req = urllib.request.Request(url, headers={'User-Agent': 'baojieh-bot'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            j = json.loads(r.read())
        if j.get('ok'):
            print(f'  ✓ 取得 iWMS token')
            return j['token']
        print(f'  ⚠ token 取得失敗: {j.get("error")}')
    except Exception as e:
        print(f'  ⚠ 無法連接 Cloudflare KV: {e}')
    return None


def fetch_dc(token, dc_id, dc_code):
    headers = dict(HEADERS_TPL)
    headers['Authorization'] = token
    items = []
    page = 1
    while True:
        url = (f'{BASE}/location/api/stock/v1/product/search'
               f'?dcId={dc_id}&direction=ASC&page={page}'
               f'&properties=prod_code&size=200&dcCode={dc_code}')
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                msg = json.loads(r.read())['message']
        except Exception as e:
            print(f'  ⚠ 抓取失敗 page={page}: {e}')
            break
        items.extend(msg['content'])
        print(f'\r    {dc_code} 頁{page}/{msg["totalPages"]} ({len(items)}筆)', end='', flush=True)
        if msg['last']: break
        page += 1
    print()
    return items


def classify(items):
    today = date.today()
    d90  = today + timedelta(days=90)
    d180 = today + timedelta(days=180)
    result = {'expired': [], 'd90': [], 'd180': [], 'ok': []}
    for x in items:
        gd = x.get('prodGoodDate', '')
        if not gd or gd in IGNORE_DATES: continue
        try:
            exp = date.fromisoformat(gd)
        except: continue
        entry = {
            'code': x.get('prodCode',''),
            'name': x.get('prodName','')[:30],
            'exp':  gd,
            'qty':  x.get('totalQty', 0),
            'sup':  x.get('supplierName',''),
        }
        if   exp < today:   result['expired'].append(entry)
        elif exp <= d90:    result['d90'].append(entry)
        elif exp <= d180:   result['d180'].append(entry)
        else:               result['ok'].append(entry)
    return result


def main():
    print('[iWMS 效期庫存]')
    token = get_token()
    if not token:
        print('  ✗ 無 token，跳過 iWMS 更新')
        return False

    today = str(date.today())
    dc_results = {}
    for dc in DC_LIST:
        print(f'  抓取 {dc["name"]} (dcId={dc["dcId"]})...')
        items = fetch_dc(token, dc['dcId'], dc['dcCode'])
        cls = classify(items)
        dc_results[dc['name']] = {
            'total': len(items),
            'expired': len(cls['expired']),
            'd90': len(cls['d90']),
            'd180': len(cls['d180']),
            'ok': len(cls['ok']),
            'expired_top': sorted(cls['expired'], key=lambda x: x['exp'])[:30],
            'd90_list':    sorted(cls['d90'],    key=lambda x: x['exp'])[:50],
            'd180_list':   sorted(cls['d180'],   key=lambda x: x['exp'])[:50],
        }
        print(f'    已過期:{len(cls["expired"])} 90天:{len(cls["d90"])} 180天:{len(cls["d180"])} 正常:{len(cls["ok"])}')

    data = {'updated': today, 'warehouses': dc_results}
    js = 'const IWMS_EXPIRY=' + json.dumps(data, ensure_ascii=False) + ';'

    html = DASHBOARD.read_text(encoding='utf-8')
    if 'const IWMS_EXPIRY=' in html:
        html = re.sub(r'const IWMS_EXPIRY=\{[\s\S]*?\};', js, html)
    else:
        html = html.replace('</script>', f'\n{js}\n</script>', 1)
    DASHBOARD.write_text(html, encoding='utf-8')
    print(f'  ✓ IWMS_EXPIRY 寫入 dashboard.html（{today}）')
    return True


if __name__ == '__main__':
    ok = main()
    sys.exit(0 if ok else 1)
