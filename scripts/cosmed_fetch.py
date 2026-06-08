#!/usr/bin/env python3
"""
康是美供應商平台 — 實銷資料自動抓取
每天自動登入、抓所有 P&G 廠編、合併成月報 xlsx

用法：python3 scripts/cosmed_fetch.py
輸出：~/Downloads/康是美實銷_YYYYMM.xlsx
"""
import os, json, re, base64
from datetime import datetime
from playwright.sync_api import sync_playwright
import anthropic
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment

# ── 設定 ─────────────────────────────────────────
COSMED_USER = '860417111'
COSMED_PASS = 'Pj86041711'
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# 保留的 P&G 廠編（排除 085804/065189/203135）
PG_SUPPLIERS = [
    '8604171183',  # OLAY PRO X
    '8604171186',  # ORALB / BRAUN
    '8604171187',  # ARIEL
    '8604171189',  # GLT 吉列
    '8604171191',  # CREST
    '8604171192',  # OLAY 歐蕾
    '8604171193',  # WHSP 好自在
    '8604171199',  # HR 髮的食譜
]

BRAND_MAP = {
    '8604171183': 'OLAY',
    '8604171186': 'ORALB',
    '8604171187': 'ARIEL',
    '8604171189': 'GLT',
    '8604171191': 'CREST',
    '8604171192': 'OLAY',
    '8604171193': 'WHSP',
    '8604171199': 'HAIR',  # HR/HS/PNTN/PERT 全髮類
}

# 從品名判斷品牌
BRAND_KEYWORDS = [
    ('PAMPS',  ['幫寶適', 'PAMPERS']),
    ('WHSP',   ['whisper', '好自在', 'Whisper']),
    ('OLAY',   ['OLAY', '歐蕾', 'PRO X']),
    ('HS',     ['海倫仙度絲', 'Head & Shoulders']),
    ('PNTN',   ['潘婷', 'PANTENE']),
    ('PERT',   ['飛柔', 'PERT']),
    ('HR',     ['髮の食譜', '髮的食譜']),
    ('ARIEL',  ['ARIEL', 'Ariel']),
    ('LENOR',  ['蘭諾', 'LENOR', 'Lenor']),
    ('ORALB',  ['Oral-B', 'ORAL-B', '歐樂']),
    ('BRAUN',  ['BRAUN', '百靈']),
    ('CREST',  ['Crest', 'CREST']),
    ('GLT',    ['吉列', 'Gillette', 'GILLETTE']),
    ('FBRZ',   ['風倍清', 'Febreze']),
    ('BOLD',   ['BOLD']),
]

def detect_brand(name, default='OTHER'):
    for brand, keywords in BRAND_KEYWORDS:
        if any(kw in name for kw in keywords):
            return brand
    return default

# ── 驗證碼辨識 ────────────────────────────────────
def read_captcha(page):
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    captcha_bytes = page.locator('img[src*="securityImage"]').first.screenshot()
    b64 = base64.standard_b64encode(captcha_bytes).decode()
    resp = client.messages.create(
        model='claude-opus-4-5', max_tokens=20,
        messages=[{'role':'user','content':[
            {'type':'image','source':{'type':'base64','media_type':'image/png','data':b64}},
            {'type':'text','text':'這張圖片裡的驗證碼文字是什麼？注意英文大小寫，只回答驗證碼本身。'}
        ]}]
    )
    return resp.content[0].text.strip()

# ── 登入 ──────────────────────────────────────────
def login(page):
    for attempt in range(4):
        page.goto('https://scm.cosmed.com.tw/APCSM/loginOut', timeout=30000)
        captcha = read_captcha(page)
        print(f'  驗證碼: {captcha}')
        page.fill('input[name="loginUserId"]', COSMED_USER)
        page.fill('input[name="loginUserPp"]', COSMED_PASS)
        page.fill('input[name="securityId"]', captcha)
        page.click('button:has-text("登入")')
        page.wait_for_load_state('networkidle', timeout=15000)
        if 'home' in page.url:
            print('  登入成功!')
            return True
        print(f'  嘗試{attempt+1}失敗，重試...')
    return False

# ── 抓取單一廠編資料 ──────────────────────────────
def fetch_supplier(page, supplier_id):
    page.locator('select').first.select_option(supplier_id)
    page.locator('button:has-text("查詢")').click()
    page.wait_for_load_state('networkidle', timeout=20000)

    # 抓表頭（週期欄位）
    raw_headers = [th.inner_text().strip() for th in page.locator('table thead tr th').all()]
    # 去重，取第一組
    seen = []; headers = []
    for h in raw_headers:
        if h not in seen:
            seen.append(h); headers.append(h)
    week_cols = [h for h in headers if '~' in h]

    # 抓所有資料行
    rows = []
    for tr in page.locator('table tbody tr').all():
        cells = [td.inner_text().strip() for td in tr.locator('td').all()]
        if len(cells) >= 6:
            rows.append(cells)

    return week_cols, rows

# ── 主流程 ────────────────────────────────────────
def fetch_all_km_sell():
    """給 derp_fetch.py 呼叫，回傳康是美實銷彙總資料。
    回傳格式：
    {
      'weeks': ['20260601~20260607', ...],   # 週期欄位
      'by_brand': {
        'ARIEL': {'週期': 總件數, ...},
        'OLAY':  {...},
        ...
      },
      'by_sku': [
        {'brand':'ARIEL','name':'...','barcode':'...','weeks':[件數,...]},
        ...
      ]
    }
    """
    from collections import defaultdict

    all_rows = []
    week_cols = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print('  登入康是美...')
        if not login(page):
            print('  ❌ 登入失敗')
            browser.close()
            return None

        page.locator('a:has-text("銷售庫存")').click()
        page.wait_for_timeout(500)
        page.locator('a:has-text("銷售數量查詢")').click()
        page.wait_for_load_state('networkidle', timeout=15000)

        for sid in PG_SUPPLIERS:
            brand_default = BRAND_MAP.get(sid, 'OTHER')
            wc, rows = fetch_supplier(page, sid)
            if not week_cols and wc:
                week_cols = wc
            for row in rows:
                if len(row) >= 6:
                    name = row[5]
                    brand = detect_brand(name, brand_default)
                    week_vals = []
                    for w in row[6:6+len(week_cols)]:
                        try:
                            week_vals.append(int(w.replace(',', '')) if w else 0)
                        except:
                            week_vals.append(0)
                    all_rows.append({
                        'supplier_id': row[1] if len(row) > 1 else sid,
                        'brand': brand,
                        'barcode': row[3] if len(row) > 3 else '',
                        'item_no': row[4] if len(row) > 4 else '',
                        'name': name,
                        'weeks': week_vals,
                    })
            print(f'    {sid}: {len(rows)}筆')

        browser.close()

    if not week_cols:
        return None

    # 彙總 by brand
    by_brand = defaultdict(lambda: [0] * len(week_cols))
    for row in all_rows:
        for i, v in enumerate(row['weeks']):
            if i < len(week_cols):
                by_brand[row['brand']][i] += v

    print(f'  ✓ 康是美實銷: {len(all_rows)}筆 SKU, {len(week_cols)}週')
    return {
        'weeks': week_cols,
        'by_brand': {b: list(v) for b, v in by_brand.items()},
        'by_sku': all_rows,
    }


def main():
    today = datetime.now()
    out_path = os.path.expanduser(f'~/Downloads/康是美實銷_{today.strftime("%Y%m")}.xlsx')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print('[登入康是美]')
        if not login(page):
            print('❌ 登入失敗')
            browser.close()
            return

        # 去銷售查詢
        page.locator('a:has-text("銷售庫存")').click()
        page.wait_for_timeout(500)
        page.locator('a:has-text("銷售數量查詢")').click()
        page.wait_for_load_state('networkidle', timeout=15000)

        all_rows = []
        week_cols = []

        print('[抓取各廠編]')
        for sid in PG_SUPPLIERS:
            brand = BRAND_MAP.get(sid, sid)
            print(f'  {sid} ({brand})...')
            wc, rows = fetch_supplier(page, sid)
            if not week_cols and wc:
                week_cols = wc
            for row in rows:
                if len(row) >= 6:
                    item_name = row[5] if len(row) > 5 else ''
                    all_rows.append({
                        'supplier_id': row[1] if len(row) > 1 else sid,
                        'brand': detect_brand(item_name, BRAND_MAP.get(sid, 'OTHER')),
                        'barcode': row[3] if len(row) > 3 else '',
                        'item_no': row[4] if len(row) > 4 else '',
                        'name': item_name,
                        'weeks': row[6:6+len(week_cols)]
                    })
            print(f'    {len(rows)} 筆')

        browser.close()

    # ── 寫 Excel ──────────────────────────────────
    print(f'[寫入 Excel] {out_path}')

    # 讀現有檔案或建新檔
    existing = os.path.expanduser('~/Downloads/康是美門市實銷資料(不包含網購 )-2026年04月.xlsx')
    if os.path.exists(existing):
        wb = openpyxl.load_workbook(existing)
    else:
        wb = openpyxl.Workbook()

    sheet_name = f'{today.year}.{today.month:02d}實銷'
    if sheet_name in wb.sheetnames:
        del wb[sheet_name]
    ws = wb.create_sheet(sheet_name, 0)

    # 表頭
    hdr_fill = PatternFill('solid', fgColor='FF8C00')
    hdr_font = Font(bold=True, color='FFFFFF')
    headers = ['10碼廠編', '品牌', '條碼', '品號', '品名'] + week_cols
    for col, h in enumerate(headers, 1):
        cell = ws.cell(1, col, h)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal='center')

    # 資料行
    for r, row in enumerate(all_rows, 2):
        ws.cell(r, 1, row['supplier_id'])
        ws.cell(r, 2, row['brand'])
        ws.cell(r, 3, row['barcode'])
        ws.cell(r, 4, row['item_no'])
        ws.cell(r, 5, row['name'])
        for w, val in enumerate(row['weeks'], 6):
            try:
                ws.cell(r, w, int(val.replace(',',''))) if val else None
            except:
                ws.cell(r, w, val)

    # 欄寬
    ws.column_dimensions['A'].width = 14
    ws.column_dimensions['B'].width = 10
    ws.column_dimensions['C'].width = 18
    ws.column_dimensions['D'].width = 8
    ws.column_dimensions['E'].width = 45
    for col in range(6, 6+len(week_cols)):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 18

    wb.save(out_path)
    print(f'✅ 完成 — {len(all_rows)} 筆 SKU，{len(week_cols)} 週')
    print(f'   檔案: {out_path}')

if __name__ == '__main__':
    main()
