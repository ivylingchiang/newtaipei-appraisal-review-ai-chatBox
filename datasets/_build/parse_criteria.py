# -*- coding: utf-8 -*-
"""從 pdftotext -layout 輸出解析評價基準明細表的矩陣與級距定義"""
import re, sys, json

LEVEL_TOKENS = ['超極優','超極劣','極優','極劣','稍優','稍劣','普通','極輕微','極嚴重',
                '輕微','中度','嚴重','嚴格','極嚴格','優','劣','無']
# 依長度排序避免 '優' 先吃掉 '稍優'
LEVEL_RE = '|'.join(sorted(LEVEL_TOKENS, key=len, reverse=True))
NOTE_RE = re.compile(r'(' + LEVEL_RE + r')\s*[：:]\s*(.*)$')
NUM_RE  = re.compile(r'[+-]?\d+(?:\.\d+)?')

def parse(path):
    lines = open(path, encoding='utf-8').read().split('\n')
    blocks, cur = [], None
    notes_buf = []
    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        # 1. 抽出備註 (級距定義)
        note = None
        m = NOTE_RE.search(line)
        if m:
            note = (m.group(1), m.group(2).strip())
            line = line[:m.start()]
        # 2. 抽數字
        nums = NUM_RE.findall(line)
        # 3. 判斷是否為表頭行(含級別token但無數字)
        toks = re.findall(LEVEL_RE, line)
        is_header = (len(nums) == 0 and len(toks) >= 2)
        is_row = (len(nums) >= 2 and len(toks) >= 1)
        if is_header:
            if cur and cur['rows']:
                blocks.append(cur)
            cur = {'header': toks, 'rows': [], 'notes': []}
            if note: cur['notes'].append(note)
        elif is_row and cur is not None:
            label = toks[-1]
            cur['rows'].append((label, [float(x) for x in nums]))
            if note: cur['notes'].append(note)
        elif note and cur is not None:
            cur['notes'].append(note)
    if cur and cur['rows']:
        blocks.append(cur)
    # 正規化：金山表左緣印有「最大影響範圍」權重數字，可能混入矩陣列。
    # 以表頭級別數 n 為準，取每列最後 n 個數字。
    from collections import Counter
    for b in blocks:
        # 級數以「各列數字個數的眾數」判定。不可用表頭 token 數：
        # 項目名稱如「有無」之『無』會被誤認為級別標籤而灌水。
        n = Counter(len(nums) for _, nums in b['rows']).most_common(1)[0][0]
        b['level_count'] = n
        if n >= 2:
            b['stray_weights'] = []
            fixed = []
            for lbl, nums in b['rows']:
                if len(nums) > n:
                    b['stray_weights'].extend(nums[:len(nums)-n])
                    nums = nums[-n:]
                fixed.append((lbl, nums))
            b['rows'] = fixed
    return blocks

if __name__ == '__main__':
    bs = parse(sys.argv[1])
    print(f"共 {len(bs)} 個候選區塊\n")
    for i,b in enumerate(bs[:int(sys.argv[2]) if len(sys.argv)>2 else 6]):
        print(f"--- block {i} header={b['header']} rows={len(b['rows'])}")
        for lbl,nums in b['rows']: print(f"    {lbl:4s} {nums}")
        for n in b['notes']: print(f"    註 {n[0]}: {n[1]}")
