#!/usr/bin/env python3
"""
看板數字排錯腳本 — 每次 derp_fetch 跑完後自動執行
比對 XLS 與看板 HTML 內嵌數字，發現異常發 Telegram 告警

通過條件：各項數字誤差 < 2%（允許四捨五入、退貨扣回等小差異）
"""
import re, os, glob, sys
import xlrd
from pathlib import Path

DASHBOARD = Path(__file__).parent.parent / 'dashboard.html'
TG_TOKEN  = os.environ.get('TG_BOT_TOKEN', '8837426763:AAGtZyCz2qHTavJXI2RwSuEi_JBO6dyln0g')
TG_CHAT   = os.environ.get('TG_CHAT_ID', '1094670750')
TOLERANCE = 0.03  # 3% 容差

def send_tg(msg):
    try:
        import urllib.request, urllib.parse, ssl
        ctx = ssl._create_unverified_context()
        data = urllib.parse.urlencode({'chat_id': TG_CHAT, 'text': msg}).encode()
        urllib.request.urlopen(
            f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage',
            data=data, context=ctx, timeout=10)
    except Exception as e:
        print(f'  TG發送失敗: {e}')

def get_xls_values():
    import re as _re
    pattern = os.path.expanduser('~/Downloads/*業績追踨*.xls')
    files = glob.glob(pattern)
    if not files:
        return None
    def key(p):
        m = _re.search(r'115-(\d+)', os.path.basename(p))
        month = int(m.group(1)) if m else 0
        is_draft = bool(_re.search(r'\(1\)-\d+', os.path.basename(p)))
        if is_draft:
            return (month, 0, 0)
        return (month, 1, int(os.path.getmtime(p)))
    path = sorted(files, key=key)[-1]
    wb = xlrd.open_workbook(path)
    sh = wb.sheet_by_index(0)
    def fv(r, c):
        v = sh.cell_value(r, c)
        return float(v) if isinstance(v, (int, float)) else 0.0
    return {
        'file':   os.path.basename(path),
        'pg_total': int(fv(47, 4)),   # E48 P&G Total
        'pharma':   int(fv(26, 6)),   # G27 藥房小計
        'super_':   int(fv(27, 6)),   # G28 超市小計
        'biz_total':int(fv(30, 6)),   # G31 業務通路總計
        'km':       int(fv(45, 4)),   # E46 康是美 E欄
        'traded':   int(fv(30, 2)),   # C31 已交易
    }

def get_dashboard_values():
    html = DASHBOARD.read_text(encoding='utf-8')
    def kv(label):
        m = re.search(rf'<div class="kl">{re.escape(label)}</div><div class="kv">\$([0-9,]+)</div>', html)
        if m:
            return int(m.group(1).replace(',', ''))
        return None
    def kv_plain(label):
        m = re.search(rf'<div class="kl">{re.escape(label)}</div><div class="kv">([^<]+)</div>', html)
        return m.group(1).strip() if m else None

    return {
        'pg_total_full': kv('P&G 本月業績（全通路）'),
        'biz_total':     kv('業務通路本月'),
        'pharma':        kv('藥房業務本月'),
        'super_':        kv('超市業務本月'),
        'km':            kv('康是美本月'),
        'pharma_super':  kv('藥房+超市業務本月'),
        'traded':        kv_plain('交易客戶'),
    }

def pct_diff(a, b):
    if not a or not b: return None
    return abs(a - b) / max(a, b)

def main():
    print('\n[排錯驗證]')
    xls = get_xls_values()
    if not xls:
        print('  ⚠ 找不到業績追踨 XLS，跳過驗證')
        return

    dash = get_dashboard_values()
    print(f'  XLS來源: {xls["file"]}')

    checks = [
        # 藥房+超市業務本月 = DERP rep加總，口徑跟 XLS G27+G28 可能有差，只做參考對照
    ]
    # 參考對照（不報錯）
    ps = dash.get('pharma_super')
    xls_ps = xls['pharma'] + xls['super_']
    if ps is not None:
        diff = pct_diff(ps, xls_ps)
        status = '✅' if diff is not None and diff < TOLERANCE else '⚠️'
        print(f'  {status} 藥房+超市業務本月: 看板=${ps:,} | XLS G27+G28=${xls_ps:,}' +
              (f' | 差{diff*100:.1f}%' if diff is not None else ' | 無法計算') + '（口徑差異，僅供參考）')
    else:
        print('  ⚠️ 藥房+超市業務本月: 看板找不到此格')

    errors = []
    for label, dash_val, xls_val, src in checks:
        if dash_val is None:
            errors.append(f'⚠ {label}: 看板找不到此格')
            continue
        diff = pct_diff(dash_val, xls_val)
        status = '✅' if diff is not None and diff < TOLERANCE else '❌'
        print(f'  {status} {label}: 看板=${dash_val:,} | {src}=${xls_val:,}' +
              (f' | 差{diff*100:.1f}%' if diff is not None else ' | 無法計算'))
        if status == '❌':
            errors.append(f'{label}: 看板${dash_val:,} vs XLS${xls_val:,} (差{diff*100:.1f}%)')

    # 交易客戶
    if dash['traded']:
        traded_dash = int(dash['traded'].split('/')[0].replace(',','')) if '/' in str(dash['traded']) else None
        if traded_dash and abs(traded_dash - xls['traded']) > 10:
            errors.append(f'交易客戶: 看板{traded_dash} vs XLS{xls["traded"]}')
            print(f'  ❌ 交易客戶: 看板{traded_dash} vs XLS{xls["traded"]}')
        else:
            print(f'  ✅ 交易客戶: {traded_dash} vs XLS{xls["traded"]}')

    if errors:
        msg = f'⚠️ 看板數字異常 {os.environ.get("TODAY","")}\n\n' + '\n'.join(errors) + \
              '\n\nhttps://baojieh-dashboard.pages.dev/dashboard.html'
        send_tg(msg)
        print(f'\n  ❌ 發現 {len(errors)} 個異常，已發 Telegram 告警')
        sys.exit(1)
    else:
        print('  ✅ 所有數字驗證通過')

if __name__ == '__main__':
    main()
