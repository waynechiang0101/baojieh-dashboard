#!/usr/bin/env python3
"""
解析 P&G Cosmed Sufficiency Summary xlsx
→ 更新 dashboard.html COSMED_SFY 變數
→ 複製 xlsx 到 data/cosmed_sufficiency_latest.xlsx（供業務下載）

用法：
  python3 scripts/parse_cosmed_sufficiency.py /path/to/file.xlsx
  python3 scripts/parse_cosmed_sufficiency.py  （自動找 Downloads 最新）
"""
import sys, os, re, json, shutil, glob
from pathlib import Path
import openpyxl

DASHBOARD = Path(__file__).parent.parent / 'dashboard.html'
DATA_DIR  = Path(__file__).parent.parent / 'data'

# (Category, Brand) → 我們的 key
# Category=X Brand=Total → 該 category 的 total
# Category=Brand=X → 單一品牌
TARGETS = {
    ('HNS',     'HNS'):     'HNS',
    ('PTN',     'PTN'):     'PTN',
    ('HR',      'HR'):      'HR',
    ('Pert',    'Pert'):    'PERT',
    ('Ariel',   'Total'):   'ARIEL',
    ('Lenor',   'Lenor'):   'LENOR',
    ('Bold',    'Bold'):    'BOLD',
    ('Oral-B',  'OCM'):     'ORALB',   # Oral-B Core Market (volume SKU)
    ('Crest',   'OCM'):     'CREST',
    ('Whisper', 'OVN Pants'): 'WHSP',  # Whisper 主力 SKU
    ('Febreze', 'Fabric Refresher'): 'FBRZ',
    ('Olay',    'RG'):      'OLAY',    # Olay Regenerist = 主力
    ('Shave',   'Total'):   'SHAVE',
}
BRAND_ORDER = ['PTN','HNS','HR','PERT','ARIEL','LENOR','ORALB','CREST','OLAY','WHSP','FBRZ','SHAVE']
BRAND_LABEL = {
    'PTN':'Pantene','HNS':'海倫仙度絲','HR':'Hair Recipe','PERT':'飛柔',
    'ARIEL':'ARIEL','LENOR':'蘭諾','ORALB':'Oral-B','CREST':'Crest',
    'OLAY':'OLAY','WHSP':'好自在','FBRZ':'風倍清','SHAVE':'Shave',
}


def parse(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sh = wb['Summary']
    rows = list(sh.iter_rows(values_only=True))
    header = rows[0]

    # 找所有月份欄位
    month_cols = {str(int(h)): i for i,h in enumerate(header)
                  if isinstance(h,int) and 202000 < h < 202800}

    # 取最近 15 個月
    all_months = sorted(month_cols.keys())
    months = all_months[-15:]

    result = {'offtake': {}, 'sellin': {}, 'sellthru': {}}
    cur_type = None

    for r in rows:
        if r[0]: cur_type = r[0]
        cat   = str(r[1] or '').strip()
        brand = str(r[2] or '').strip()
        key = TARGETS.get((cat, brand))
        if not key: continue

        type_key = {'Offtake':'offtake','Sell-in':'sellin',
                    'Sell-Thru':'sellthru','Sell-Thru ':'sellthru'}.get(cur_type)
        if not type_key: continue

        vals = {}
        for m in months:
            ci = month_cols[m]
            v = r[ci]
            vals[m] = round(float(v), 4) if isinstance(v,(int,float)) else None
        result[type_key][key] = vals

    return months, result


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        patterns = [
            os.path.expanduser('~/Downloads/Cosmed*Sufficiency*.xlsx'),
            os.path.expanduser('~/Downloads/cosmed*sufficiency*.xlsx'),
            os.path.expanduser('~/Downloads/Cosmed*.xlsx'),
        ]
        files = []
        for p in patterns:
            files.extend(glob.glob(p))
        if not files:
            print('✗ 找不到 Cosmed Sufficiency xlsx，請手動指定路徑')
            sys.exit(1)
        path = max(files, key=os.path.getmtime)

    fname = os.path.basename(path)
    print(f'[Cosmed Sufficiency]\n  來源: {fname}')

    months, data = parse(path)
    print(f'  月份: {months[0]} ~ {months[-1]}（{len(months)} 個月）')

    brand_count = len(data['offtake'])
    print(f'  品牌: {brand_count} 個')

    js_data = {
        'updated':  str(__import__('datetime').date.today()),
        'filename': fname,
        'months':   months,
        'offtake':  data['offtake'],
        'sellin':   data['sellin'],
        'sellthru': data['sellthru'],
        'order':    [b for b in BRAND_ORDER if b in data['offtake']],
    }
    js = 'const COSMED_SFY=' + json.dumps(js_data, ensure_ascii=False) + ';'

    html = DASHBOARD.read_text(encoding='utf-8')
    if 'const COSMED_SFY=' in html:
        html = re.sub(r'const COSMED_SFY=\{[\s\S]*?\};', js, html)
        print('  ✓ COSMED_SFY 更新')
    else:
        html = html.replace('</script>', f'\n{js}\n</script>', 1)
        print('  ✓ COSMED_SFY 新增')
    DASHBOARD.write_text(html, encoding='utf-8')

    # 複製 xlsx 到 data/
    dest = DATA_DIR / 'cosmed_sufficiency_latest.xlsx'
    shutil.copy2(path, dest)
    print(f'  ✓ 複製至 {dest.name}（業務下載用）')
    print(f'\n  下一步: git add -A && git commit -m "data: Cosmed Sufficiency 更新" && git push')


if __name__ == '__main__':
    main()
