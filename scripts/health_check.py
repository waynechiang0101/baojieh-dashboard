#!/usr/bin/env python3
"""
寶捷看板自動排錯 — health_check.py
每次 derp_fetch.py 跑完後自動執行，發現異常送 Telegram 告警。

告警等級：
  🔴 CRITICAL — 數字可能嚴重錯誤，看板不可信
  🟡 WARNING  — 有異常但可能是正常波動，需要人工確認
  ℹ️  INFO    — 資料狀態說明，不是錯誤
"""
import re, os, sys, glob, json
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ── 基本設定 ──────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent.parent
DASHBOARD = ROOT / 'dashboard.html'
DATA_DIR  = ROOT / 'data'

TG_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
TG_CHAT  = os.environ.get('TG_CHAT_ID', '1094670750')
TW_TZ    = timezone(timedelta(hours=8))

TOLERANCE_CRITICAL = 0.10  # 差 >10% → CRITICAL
TOLERANCE_WARN     = 0.05  # 差 >5%  → WARNING

CHANNEL_MIN_AFTER_DAY7 = {
    '康是美':  20_000_000,
    '業務通路': 15_000_000,
    'P&G全通路': 40_000_000,
}

# ── Telegram 發送 ──────────────────────────────────────────────────────
def send_tg(msg: str):
    if not TG_TOKEN:
        print('  ⚠ TELEGRAM_TOKEN 未設定，跳過發送')
        return
    try:
        import urllib.request, urllib.parse, ssl
        ctx = ssl._create_unverified_context()
        data = urllib.parse.urlencode({
            'chat_id':    TG_CHAT,
            'text':       msg,
            'parse_mode': 'HTML'
        }).encode()
        urllib.request.urlopen(
            f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage',
            data=data, context=ctx, timeout=15
        )
        print('  📱 Telegram 已送出')
    except Exception as e:
        print(f'  ⚠ Telegram 發送失敗: {e}')

# ── 從 dashboard.html 讀 KPI ──────────────────────────────────────────
def read_dashboard():
    if not DASHBOARD.exists():
        return {}
    html = DASHBOARD.read_text(encoding='utf-8')

    def kv_dollar(label):
        m = re.search(
            rf'<div class="kl">{re.escape(label)}</div><div class="kv">\$([0-9,]+)</div>', html)
        return int(m.group(1).replace(',', '')) if m else None

    def kv_plain(label):
        m = re.search(
            rf'<div class="kl">{re.escape(label)}</div><div class="kv">([^<]+)</div>', html)
        return m.group(1).strip() if m else None

    def js_int(name):
        m = re.search(rf'const {name}=([0-9]+);', html)
        return int(m.group(1)) if m else None

    def js_str(name):
        m = re.search(rf'const {name}="([^"]*)"', html)
        return m.group(1) if m else None

    # IYA
    iya_raw = kv_plain('IYA 成長')
    iya_pct = None
    if iya_raw:
        m = re.search(r'([+-]?[\d.]+)%', iya_raw)
        iya_pct = float(m.group(1)) if m else None

    # 交易客戶
    traded_raw = kv_plain('交易客戶')
    traded = None
    if traded_raw:
        part = traded_raw.split('/')[0]
        m = re.search(r'([\d,]+)', part)
        traded = int(m.group(1).replace(',', '')) if m else None

    # 黑燈庫存金額
    inv_black = None
    m = re.search(r'"black":\{"n":\d+,"amt":(\d+)\}', html)
    if m:
        inv_black = int(m.group(1))

    return {
        'pg_total':    kv_dollar('P&G 本月業績（全通路）'),
        'km':          kv_dollar('康是美本月'),
        'cvs':         kv_dollar('CVS盤商本月'),
        'biz':         kv_dollar('藥房+超市業務本月'),
        'today_ship':  kv_dollar('今日出貨'),
        'ar_unpaid':   kv_dollar('應收未付'),
        'iya_pct':     iya_pct,
        'traded':      traded,
        'xls_total':   js_int('XLS_TOTAL'),
        'last_update': js_str('LAST_UPDATE'),
        'inv_black':   inv_black,
    }

# ── 從 XLS 讀數字 ────────────────────────────────────────────────────
def read_xls():
    try:
        import xlrd
    except ImportError:
        return None, 'xlrd 未安裝'

    pattern = os.path.expanduser('~/Downloads/*業績追踨*.xls')
    files = glob.glob(pattern)
    if not files:
        return None, '找不到業績追踨 XLS（助理是否漏放？）'

    def key(p):
        m = re.search(r'115-(\d+)', os.path.basename(p))
        month = int(m.group(1)) if m else 0
        is_draft = bool(re.search(r'\(1\)-\d+', os.path.basename(p)))
        return (month, 0 if is_draft else 1, int(os.path.getmtime(p)))

    path = sorted(files, key=key)[-1]
    age_days = (datetime.now().timestamp() - os.path.getmtime(path)) / 86400

    try:
        wb = xlrd.open_workbook(path)
        sh = wb.sheet_by_index(0)
        def fv(r, c):
            v = sh.cell_value(r, c)
            return float(v) if isinstance(v, (int, float)) else 0.0
        return {
            'file':     os.path.basename(path),
            'age_days': age_days,
            'pg_total': int(fv(47, 4)),
            'pharma':   int(fv(26, 6)),
            'super_':   int(fv(27, 6)),
            'traded':   int(fv(30, 2)),
        }, None
    except Exception as e:
        return None, f'XLS 讀取失敗: {e}'

# ── 主驗證邏輯 ────────────────────────────────────────────────────────
def main():
    now_tw = datetime.now(TW_TZ)
    today  = now_tw.strftime('%Y-%m-%d %H:%M')
    day    = now_tw.day
    hour   = now_tw.hour

    print(f'\n[健康檢查] {today}')
    print('=' * 50)

    criticals, warnings, infos = [], [], []

    dash = read_dashboard()
    xls, xls_err = read_xls()

    # ── 1. DERP 今日有無資料 ─────────────────────────────────────────
    print('\n[1] DERP 連線確認')
    pg = dash.get('pg_total')
    if not pg:
        criticals.append('P&G 全通路業績 = 0，DERP 可能掛掉或登入失敗')
        print('  🔴 P&G全通路 = 0')
    else:
        print(f'  ✅ P&G全通路 = ${pg:,}')

    # ── 2. 各通路數字 ────────────────────────────────────────────────
    print('\n[2] 通路數字')
    km  = dash.get('km')
    cvs = dash.get('cvs')
    biz = dash.get('biz')

    if km == 0:
        criticals.append('康是美本月 = 0，資料異常（康是美每月必有出貨）')
    elif km and day >= 7 and km < CHANNEL_MIN_AFTER_DAY7['康是美']:
        warnings.append(f'康是美本月 ${km:,} 偏低（月初第{day}天，< $2000萬）')

    if biz and day >= 7 and biz < CHANNEL_MIN_AFTER_DAY7['業務通路']:
        warnings.append(f'業務通路本月 ${biz:,} 偏低（月初第{day}天，< $1500萬）')

    for label, val in [('康是美', km), ('CVS盤商', cvs), ('業務通路', biz)]:
        mark = '✅' if val else '⚠'
        print(f'  {mark} {label}: ${val:,}' if val else f'  ⚠ {label}: 讀不到')

    # ── 3. XLS 對比 ──────────────────────────────────────────────────
    print('\n[3] XLS 數字對比')
    if xls_err:
        warnings.append(f'XLS 問題：{xls_err}')
        print(f'  ⚠ {xls_err}')
    elif xls:
        age = xls['age_days']
        print(f'  XLS: {xls["file"]} (更新 {age:.1f}天前)')
        if age > 2:
            warnings.append(f'業績追踨 XLS {age:.1f} 天未更新（助理漏放？）')

        # 藥房+超市 vs XLS G27+G28
        xls_ps   = xls['pharma'] + xls['super_']
        dash_biz = dash.get('biz')
        if dash_biz and xls_ps > 0:
            diff = abs(dash_biz - xls_ps) / max(dash_biz, xls_ps)
            icon = '✅' if diff < 0.05 else ('🟡' if diff < 0.10 else '🔴')
            print(f'  {icon} 藥房+超市: 看板 ${dash_biz:,} | XLS G27+G28 ${xls_ps:,} | 差 {diff*100:.1f}%')
            if diff >= TOLERANCE_CRITICAL:
                criticals.append(f'藥房+超市口徑差 {diff*100:.1f}%（看板 ${dash_biz:,} vs XLS ${xls_ps:,}）')
            elif diff >= TOLERANCE_WARN:
                warnings.append(f'藥房+超市口徑差 {diff*100:.1f}%（看板 ${dash_biz:,} vs XLS ${xls_ps:,}）')

        # 交易客戶
        d_traded = dash.get('traded')
        x_traded = xls.get('traded')
        if d_traded and x_traded:
            diff_t = abs(d_traded - x_traded)
            icon = '✅' if diff_t <= 20 else '🟡'
            print(f'  {icon} 交易客戶: 看板 {d_traded} | XLS {x_traded} | 差 {diff_t}筆')
            if diff_t > 50:
                warnings.append(f'交易客戶差異 {diff_t} 筆（看板 {d_traded} vs XLS {x_traded}）')

    # ── 4. IYA 異常 ──────────────────────────────────────────────────
    print('\n[4] IYA 成長率')
    iya = dash.get('iya_pct')
    if iya is None:
        warnings.append('IYA 讀不到（DERP 去年同期 timeout）')
        print('  ⚠ IYA = None')
    elif iya == 0.0:
        infos.append('IYA 顯示 +0%，DERP 去年同期 timeout，請以 XLS 為準')
        print('  ℹ️ IYA = +0%（去年同期 timeout）')
    elif iya < -30:
        criticals.append(f'IYA {iya:+.1f}%，業績驟降 30% 以上，請確認 DERP 資料完整性')
        print(f'  🔴 IYA = {iya:+.1f}%（異常驟降）')
    else:
        print(f'  ✅ IYA = {iya:+.1f}%')

    # ── 5. 資料新鮮度 ─────────────────────────────────────────────────
    print('\n[5] 資料新鮮度')
    lu = dash.get('last_update')
    if not lu:
        warnings.append('LAST_UPDATE 空白（derp_fetch.py 可能沒跑完）')
        print('  ⚠ LAST_UPDATE 空白')
    else:
        try:
            lu_dt = datetime.strptime(lu, '%Y-%m-%d %H:%M').replace(tzinfo=TW_TZ)
            age_h = (now_tw - lu_dt).total_seconds() / 3600
            icon  = '✅' if age_h < 26 else '🟡'
            print(f'  {icon} LAST_UPDATE = {lu}（{age_h:.1f}h 前）')
            if age_h > 26:
                warnings.append(f'看板 {age_h:.1f}h 未更新（上次：{lu}）')
        except Exception:
            print(f'  ✅ LAST_UPDATE = {lu}')

    # ── 6. 黑燈庫存摘要 ──────────────────────────────────────────────
    print('\n[6] 庫存摘要')
    inv_black = dash.get('inv_black')
    if inv_black:
        monthly_cost = int(inv_black * 0.035)
        print(f'  ℹ️ 黑燈庫存 ${inv_black:,}，本月持有成本 ${monthly_cost:,}（3.5%）')
        if inv_black > 100_000_000:
            infos.append(f'黑燈庫存 ${inv_black//10000}萬，本月持有成本約 ${monthly_cost//10000}萬')

    # ── 彙總 ─────────────────────────────────────────────────────────
    print('\n' + '=' * 50)
    n_crit = len(criticals)
    n_warn = len(warnings)

    if n_crit + n_warn == 0:
        status_icon, status_line = '✅', '所有檢查通過'
    elif n_crit:
        status_icon, status_line = '🔴', f'{n_crit} 個嚴重問題 · {n_warn} 個警告'
    else:
        status_icon, status_line = '🟡', f'{n_warn} 個警告'

    print(f'\n結果：{status_icon} {status_line}')

    # ── 組 Telegram 訊息 ─────────────────────────────────────────────
    lines = [
        f'<b>📊 寶捷看板健康檢查</b> {today}',
        f'{status_icon} {status_line}',
        '',
    ]
    if criticals:
        lines.append('<b>🔴 嚴重問題（請立即確認）</b>')
        lines += [f'• {c}' for c in criticals]
        lines.append('')
    if warnings:
        lines.append('<b>🟡 警告</b>')
        lines += [f'• {w}' for w in warnings]
        lines.append('')
    if infos:
        lines.append('<b>ℹ️ 備注</b>')
        lines += [f'• {i}' for i in infos]
        lines.append('')

    if pg:
        lines.append(f'全通路 ${pg//10000}萬 | KM ${(km or 0)//10000}萬 | 業務 ${(biz or 0)//10000}萬')
    lines.append('https://baojieh-dashboard.pages.dev/dashboard.html')

    msg = '\n'.join(lines)

    # 有問題必送；每天 18:30-19:00 固定送一次狀態
    should_send = (n_crit + n_warn > 0) or (18 <= hour <= 19)
    if should_send:
        send_tg(msg)
    else:
        print('  （無異常且非告警時段，跳過 Telegram）')

    if n_crit:
        sys.exit(1)

if __name__ == '__main__':
    main()
