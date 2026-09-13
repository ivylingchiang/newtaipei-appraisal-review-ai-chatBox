# -*- coding: utf-8 -*-
"""解析表3 地價區段勘查表 → 結構化區段觀測資料"""
import os, re, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml
from datasets._build.case_rules import CASE_RULES, apply_cr1, check_cr2

OUT = "datasets"

# 欄位標籤（允許 pdftotext 在字元間插入空白）
def lab(*chars):
    return r'\s*'.join(map(re.escape, chars))

FIELDS = [
    ("urban_plan",       "都市計畫(內外)",        "L", lab("都市計畫") + r'\s*[（(]\s*內\s*外\s*[)）]'),
    ("zoning",           "使用分區(使用地類別)",   "L", lab("使用分區")),
    ("bcr",              "建蔽率",               "L", lab("建","蔽","率")),
    ("far",              "容積率",               "L", lab("容","積","率")),
    ("build_ban",        "有無禁止建築",          "L", lab("有無禁止建築")),
    ("build_restrict",   "有無限制建築",          "L", lab("有無限制建築")),
    ("main_road",        "主要道路",              "L", lab("主要道路")),
    ("avg_road_width",   "區段內道路平均寬度",     "L", lab("區段內道路平均寬度")),
    ("road_dev",         "區段內道路規劃及闢建程度", "L", lab("區段內道路規劃及闢建程度")),
    ("sunlight",         "日照",                 "L", lab("日","照")),
    ("view",             "景觀",                 "L", lab("景","觀")),
    ("slope",            "傾斜度",               "L", lab("傾","斜","度")),
    ("drainage",         "保（排）水之良否",       "L", lab("保") + r'\s*[（(]\s*排\s*[)）]\s*水\s*之\s*良\s*否'),
    ("terrain",          "地勢",                 "L", lab("地","勢")),
    ("wind",             "風勢",                 "L", lab("風","勢")),
    ("soil",             "土質",                 "L", lab("土","質")),
    ("build_density",    "建築密度",              "R", lab("建築密度")),
    ("build_type",       "建築型態",              "R", lab("建築型態")),
    ("customer_flow",    "顧客之通行量",          "R", lab("顧客") + r'之?' + lab("通行量")),
    ("shop_adjacency",   "店舖之毗連狀態",        "R", r'店[鋪舖]之毗連狀態'),
]

LEVEL_PREFIX = re.compile(r'^\s*(\d)\s+(\d)\s+')
COL_SPLIT = 92   # 表3 雙欄版面之分欄字元位置（左欄 0-91 / 右欄 92+）
# 勾選框 + 距離（名稱可能在同列前段或上方數列，故分兩段處理）
CHECKBOX = re.compile(r'([○●])\s*本區段內\s*([○●])\s*本區段?外\s*[（(]\s*距\s*([\d.]*)\s*M?')
NAME_IN_LINE = re.compile(r'名稱[：:]\s*([^○●\s][^○●]*?)\s*(?:數量[:：]\s*(\S*))?\s*$')
NUM_UNIT = re.compile(r'([\d.]+)\s*(%|％|M|m|㎡)?')

def clean(s):
    s = re.sub(r'\s+', ' ', s or '').strip()
    return s

def split_tables(text, marker):
    """依表頭切分多份表3"""
    idx = [m.start() for m in re.finditer(marker, text)]
    return [text[a:b] for a, b in zip(idx, idx[1:] + [len(text)])]

def extract_segment(block, region, land_use, source):
    out = {"observations": {}, "facilities": [], "improvements": [], "land_use_current": None}
    hdr = re.search(r'(\d{7})\s+區段編號\s+(P\d{3}-\d{2})\s+區段範圍(.*)', block)
    if hdr:
        # 區段範圍可能跨行：前段落在表頭「(公共設施保留地請填明毗鄰…」那一列的右側
        head_line_no = block[:hdr.start()].count("\n")
        prefix = ""
        for k in (1, 2):
            if head_line_no - k < 0: break
            prev = block.split("\n")[head_line_no - k]
            if "公共設施保留地請填明" in prev:
                frag = clean(prev.split("毗鄰")[-1])
                # 樣板字「非保留地區段號)」會被斷行切開，殘句需剝除
                frag = re.sub(r'^非?保?留?地?區?段?號?[)）]?\s*', '', frag)
                if len(frag) > 4: prefix = frag
                break
        out["year_period"] = hdr.group(1)
        out["segment_no"] = hdr.group(2)
        scope = clean(hdr.group(3))
        scope = re.sub(r'^.*?區段號[)）]?', '', scope).strip()
        if prefix: scope = (prefix + scope).strip()
        # 續行判準：括號未閉合表示範圍描述被斷行，往下找收尾片段
        def unbalanced(t):
            return (t.count("(") + t.count("（")) > (t.count(")") + t.count("）"))
        blines = block.split("\n")
        k = 1
        while scope and unbalanced(scope) and k <= 3 and head_line_no + k < len(blines):
            tail = clean(blines[head_line_no + k][40:])
            if tail and not re.search(r'都市計畫|使用分區|建\s*蔽|容\s*積|區段編號', tail):
                scope += tail
            k += 1
        # 表頭「(公共設施保留地請填明毗鄰非保留地區段號)」的殘句不是真正的區段範圍
        if re.fullmatch(r'[（(]?[^、。]{0,12}區段號[)）]?', scope or '') or len(scope) < 6:
            scope = None
        out["scope_desc"] = scope
    NUMERIC_ONLY = ("bcr", "far", "avg_road_width", "build_density")
    all_lines = block.split("\n")
    halves = {
        "L": [l[:COL_SPLIT] for l in all_lines],
        "R": [l[COL_SPLIT:] for l in all_lines],
    }
    ALL_PATS = [p for _c, _n, _s, p in FIELDS]

    def _is_label_line(txt):
        return any(re.search(p, txt) for p in ALL_PATS)

    def _is_noise(v, code):
        """右欄直排欄名滲入、或等級碼被誤當值"""
        if not v: return True
        if code not in NUMERIC_ONLY and re.fullmatch(r'[\d\s.]+', v): return True
        if len(v) == 1 and v not in ("有", "無"): return True
        if re.search(r'[□■○●]|名稱', v): return True
        return False

    def _clean_value_line(txt):
        t = clean(txt)
        # 直排欄名（土/地/使/用/管/制…）會單字散落在列首，需剝除
        while True:
            m2 = re.match(r'^([\u4e00-\u9fff])\s+(.*)$', t)
            if not m2: break
            t = m2.group(2)
        return t.strip()

    for code, name, side, pat in FIELDS:
        lines = halves[side]
        idx = next((i for i, l in enumerate(lines) if re.search(pat, l)), None)
        if idx is None: continue
        m = re.search(pat, lines[idx])
        post = lines[idx][m.end():]
        # 欄名補述「(使用地類別)」要先剝掉，否則會被當成值而擋掉鄰列回補
        post = re.sub(r'^\s*[（(][^)）]*[)）]', '', post)
        # 必須先依大空白切欄，再壓縮空白：clean() 會把欄距抹平，
        # 導致右側鄰欄文字（如「普通完善      環」的「環」）被併入值。
        segs = [x for x in re.split(r'\s{4,}', post.strip()) if x.strip()]
        raw = clean(segs[0]) if segs else ""
        raw = re.sub(r'[○●].*$', '', raw).strip()
        raw = re.sub(r'[（(][^)）]*$', '', raw).strip()   # 未閉合括號＝換行的欄名補述
        if _is_noise(raw, code): raw = ""
        # 合併儲存格會讓值落在標籤的上一／下一列
        if not raw:
            for d in (-1, 1, -2, 2):
                k = idx + d
                if not (0 <= k < len(lines)): continue
                line_k = lines[k]
                if _is_label_line(line_k): continue
                # 第 30 欄之前是欄名區（直排群組名＋細項名），整段遮蔽；
                # 不可用「單字＋空白」規則去剝，否則值本身為單字時（如「無」）會被吃掉。
                t = re.sub(r'[\u4e00-\u9fff]', ' ', line_k[:20]) + line_k[20:]
                # 值未必在第一段（列首可能是「1    2」等級碼），故逐段檢查
                picked = None
                for chunk in re.split(r'\s{4,}', t.strip()):
                    c2 = clean(chunk)
                    if _is_noise(c2, code): continue
                    picked = c2; break
                if picked:
                    raw = picked; break
        pre = lines[idx][:m.start()]
        lv = LEVEL_PREFIX.match(pre)
        raw = re.sub(r'^[（(][^)）]*[)）]\s*', '', raw).strip()
        rec = {"field_name": name, "raw": raw or None}
        if lv:
            rec["level_rank"] = int(lv.group(1)); rec["level_count"] = int(lv.group(2))
        nm = NUM_UNIT.match(raw) if raw else None
        if nm and nm.group(1):
            try:
                rec["value"] = float(nm.group(1))
                rec["unit"] = {"%":"percent","％":"percent","M":"m","m":"m","㎡":"m2"}.get(nm.group(2))
                if code in NUMERIC_ONLY:
                    rec["raw"] = nm.group(0).strip()
            except ValueError: pass
        if code == "main_road":
            mm = re.search(r'(?:名稱[：:])?\s*(\S+?)\s*寬度[：:]?\s*([\d.]+)\s*M', clean(post))
            if mm:
                rec["road_name"] = mm.group(1); rec["value"] = float(mm.group(2)); rec["unit"] = "m"
                rec["raw"] = clean(mm.group(0))
        out["observations"][code] = rec
    # 設施（名稱 + 區段內外 + 距離）
    # 表3 為雙欄版面：左欄約 col 0-91（交通運輸、公共建設），右欄 col 92+（特殊設施、
    # 環境污染、工商活動）。若不分欄，左欄文字會污染右欄設施的標籤判讀。
    for m in re.finditer(r'■\s*([^\s□■]+)', block):
        out["improvements"].append(m.group(1))
    lu = re.search(r'●\s*(商業用|住宅用|工業用|住商混合|住工混合|農作用|漁牧用|空地|公共設施)', block)
    if lu: out["land_use_current"] = lu.group(1)
    out["region_code"] = region; out["land_use_code"] = land_use; out["source"] = source
    if out.get("segment_no"):
        out["segment_id"] = f"{region}.{out['year_period']}.{out['segment_no']}"

    raw_lines = block.split("\n")
    for half in (0, 1):
        lines = [(l[:COL_SPLIT] if half == 0 else l[COL_SPLIT:]) for l in raw_lines]
        _scan_facilities(lines, out)
    return out


def _scan_facilities(lines, out):
    for li, line in enumerate(lines):
        for m in CHECKBOX.finditer(line):
            inseg, outseg, dist = m.groups()
            head = line[:m.start()]
            label, name, qty, lv = _facility_label(head, lines, li)
            checked = (inseg == "●" or outseg == "●")
            # 未勾選時仍須區分兩種情形：
            #   名稱填「無」        → 確認無此設施（可判級為最優/最劣端）
            #   名稱空白            → 未勘查（資料缺漏，不可判級）
            nm_t = re.sub(r"\s+", "", name or "")
            lb_t = re.sub(r"\s+", "", label or "")
            explicit_none = (nm_t.startswith("無") or lb_t.startswith("無"))
            if not checked and not explicit_none:
                continue
            rec = {
                "label": label or None,
                "name": name or None,
                "quantity": qty or None,
                "in_segment": inseg == "●",
                "distance_m": (float(dist) if dist else (0.0 if inseg == "●" else None))
                              if checked else None,
                "is_none": (not checked) and explicit_none,
            }
            if lv: rec["level_rank"], rec["level_count"] = lv
            code, conf = map_facility(label, name)
            rec["criteria_item_code"] = code
            rec["mapping_confidence"] = conf
            rec["needs_review"] = conf != "high"
            out["facilities"].append(rec)
    return out

def _facility_label(head, lines, li):
    """由勾選框左側文字(或上方數列)推得設施標籤、名稱、數量、優劣等級"""
    name = qty = None
    nm = NAME_IN_LINE.search(head)
    if nm:
        name = clean(nm.group(1)) or None
        qty = nm.group(2) or None
        head = head[:nm.start()]
    lv = None
    def strip(t):
        t2 = re.sub(r'名稱[：:].*$', '', t)
        t2 = re.sub(r'數量[:：].*$', '', t2)
        t2 = t2.replace('○', ' ').replace('●', ' ')
        return clean(t2)
    cand = strip(head)
    m = LEVEL_PREFIX.match(cand)
    if m:
        lv = (int(m.group(1)), int(m.group(2))); cand = cand[m.end():].strip()
    cand = re.sub(r'^\d+\s+\d+\s+', '', cand).strip()
    # 同列無標籤 → 先往上、再往下找。含勾選框之列屬「其他設施自己的列」，必須跳過，
    # 否則會把上一筆設施的名稱誤植為本筆標籤。
    def probe(idx):
        nonlocal lv
        if idx < 0 or idx >= len(lines): return None
        prev = lines[idx]
        if CHECKBOX.search(prev): return None
        c = strip(prev)
        m2 = LEVEL_PREFIX.match(c)
        if m2:
            lv = lv or (int(m2.group(1)), int(m2.group(2))); c = c[m2.end():].strip()
        c = re.sub(r'[（(].*$', '', c).strip()
        c = re.sub(r'^\d+\s+\d+\s+', '', c).strip()
        if c and not re.fullmatch(r'[\d\s.]+', c): return c
        return None
    if not cand:
        for d in (1, 2, 3):
            cand = probe(li - d)
            if cand: break
    if not cand:
        for d in (1, 2):
            cand = probe(li + d)
            if cand: break
    return cand or None, name, qty, lv


# 標籤/名稱 → 評價基準明細表細項代碼（順序即優先序）
FACILITY_MAP = [
    ("near_busstop",     ["站牌", "密集程度"]),
    ("near_station",     ["高鐵站", "火車站", "客運站", "捷運站", "大型車站", "客運", "高鐵", "火車"]),
    ("near_interchange", ["交流道"]),
    ("near_school",      ["國小", "國中", "高中", "大專", "學校"]),
    ("near_market",      ["傳統市場", "超級市場", "超大型購物中心", "市場"]),
    ("near_park",        ["里鄰公園", "一般公園", "公園", "廣場", "徒步區"]),
    ("near_tourism",     ["觀光遊憩"]),
    ("parking",          ["停車場"]),
    ("near_service",     ["服務性設施", "郵局", "醫院"]),
    ("utility_facility", ["變電所", "高壓", "瓦斯槽", "儲油槽", "電業", "電力"]),
    ("funeral_facility", ["墓", "殯儀館", "火葬場", "納骨"]),
    ("waste_facility",   ["污水處理", "垃圾場", "掩埋場", "焚化爐", "廢棄物處理"]),
    ("pollution",        ["水污染", "噪音污染", "廢氣污染", "廢棄物污染", "污染"]),
    ("dept_store",       ["百貨公司"]),
    ("financial",        ["金融機構", "農會", "銀行"]),
    ("entertainment",    ["娛樂設施"]),
    ("exhibition_hotel", ["展示中心", "飯店", "酒店", "光飯店"]),
]

def map_facility(label, name):
    """回傳 (item_code, confidence)。label 命中為 high，僅 name 命中為 medium。"""
    # 直式中文經 pdftotext 會被拆成「站 牌」，比對前需先去除空白
    lab_t = re.sub(r"^無", "", re.sub(r"\s+", "", label or ""))
    for code, kws in FACILITY_MAP:
        if any(k in lab_t for k in kws): return code, "high"
    nm_t = re.sub(r"^無", "", re.sub(r"\s+", "", name or ""))
    for code, kws in FACILITY_MAP:
        if any(k in nm_t for k in kws): return code, "medium"
    return None, "none"


def main():
    S = sys.argv[1]
    specs = [
        ("題目.txt", "shulin", "residential", "doc/題目.pdf", r'表3\s+地價區段勘查表'),
        ("查估書表範本.txt", "jinshan", "commercial", "doc/rules/查估書表範本.pdf", r'表1\s+地價區段勘查表'),
    ]
    for fn, region, lu, src, marker in specs:
        text = open(os.path.join(S, fn), encoding="utf-8").read()
        blocks = split_tables(text, marker)
        segs = [extract_segment(b, region, lu, src) for b in blocks]
        segs = [s for s in segs if s.get("segment_no")]
        d = os.path.join(OUT, "regions", region, "segments"); os.makedirs(d, exist_ok=True)
        for s in segs:
            # 案件層級規則：CR1 捷運開發區分區回溯、CR2 容積率與路寬相容性
            vb = apply_cr1(s)
            if vb: s["valuation_basis"] = vb
            c2 = check_cr2(s)
            if c2: s.setdefault("rule_checks", []).append(c2)
            # 資料完整度
            filled = [k for k, v in s["observations"].items() if v.get("raw")]
            s["completeness"] = {
                "observed_fields": len(filled),
                "total_fields": len(FIELDS),
                "facilities_recorded": len(s["facilities"]),
                "missing_fields": [k for k, _n, _s, _p in FIELDS if k not in filled],
            }
            json.dump(s, open(os.path.join(d, f"{s['segment_no']}.json"), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
        idx = {"schema_version":"1.0","region_code":region,"land_use_code":lu,"source":src,
               "count":len(segs),
               "segments":[{"segment_id":s["segment_id"],"segment_no":s["segment_no"],
                            "year_period":s["year_period"],"scope_desc":s.get("scope_desc"),
                            "observed_fields":s["completeness"]["observed_fields"],
                            "facilities":s["completeness"]["facilities_recorded"]} for s in segs]}
        json.dump(idx, open(os.path.join(d, "_index.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        yaml.safe_dump({"segments": segs}, open(os.path.join(d, "segments.yaml"), "w", encoding="utf-8"),
                       allow_unicode=True, sort_keys=False, width=200)
        print(f"{region}: {len(segs)} 個區段")
        for s in segs:
            print(f"  {s['segment_no']}  觀測 {s['completeness']['observed_fields']}/{len(FIELDS)} 欄, "
                  f"設施 {s['completeness']['facilities_recorded']} 筆, 用途 {s.get('land_use_current')}")

if __name__ == "__main__": main()
