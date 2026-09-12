# -*- coding: utf-8 -*-
"""解析表5 區域因素分析明細表 與 表4 比較法調查估價表 → 案件資料"""
import os, re, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml

OUT = "datasets"
LV = {1:"優",2:"稍優",3:"普通",4:"稍劣",5:"劣"}
NUMTOK = re.compile(r'^-?[\d,]+(?:\.\d+)?%?$')

def cells(line):
    return [c.strip() for c in re.split(r'\s{2,}', line.strip()) if c.strip()]

def nums_in(line):
    """直接由整列抓數值：小計/總修正數列的值後面接全形 ％，切格子會失敗"""
    return [float(x.replace(',', '')) for x in re.findall(r'-?\d[\d,]*(?:\.\d+)?', line)]

def num(s):
    if s is None: return None
    s = s.replace(',', '').replace('%', '').strip()
    try: return float(s)
    except ValueError: return None

# ---------- 表5 ----------
T5_ITEMS = [
    ("urban_plan",["都市計畫（內、外）","都市計畫（內"]),("zoning",["使用分區"]),
    ("bcr",["建蔽率"]),("far",["容積率"]),
    ("build_ban",["有無禁止建築"]),("build_restrict",["有無限制建築"]),
    ("main_road_width",["主要道路寬度"]),("avg_road_width",["區段內道路平均寬度"]),
    ("near_station",["接近大型車站之程度"]),("near_busstop",["站牌"]),
    ("near_interchange",["交流道"]),("road_dev",["區段內道路規劃及闢建程度"]),
    ("sunlight",["日照"]),("view",["景觀"]),("slope",["傾斜度"]),
    ("drainage",["排水之良否"]),("terrain",["地勢"]),
    ("land_improve",["建築基地改良"]),
    ("near_school",["接近學校之程度"]),("near_market",["接近市場之程度"]),
    ("near_park",["接近公園"]),("near_tourism",["接近觀光遊憩設施之程度"]),
    ("parking",["停車場地之便利程度"]),("near_service",["接近服務性設施"]),
    # 樹林與金山對同一細項的措辭不同，兩種都要能命中
    ("utility_facility",["電業設施","變電所"]),
    ("funeral_facility",["殯葬設施","墓地"]),
    ("waste_facility",["廢棄物處理設施","垃圾場"]),
    ("pollution",["環境污染","水污染"]),
    ("dept_store",["百貨公司"]),("financial",["金融機構"]),("entertainment",["娛樂設施"]),
    ("exhibition_hotel",["大型展示中心或觀光飯店"]),("customer_flow",["顧客通行量","顧客之通行量"]),
    ("shop_adjacency",["店舖之毗連狀態","店鋪之毗連狀態"]),
    ("other",["其他影響"]),
]

def parse_t5(text):
    m = re.search(r'表5-(\d)\s*影響地價區域因素分析明細表\s*[（(](.+?)[)）]', text)
    if not m: return None
    start = m.start()
    end = text.find("表4", start)
    blk = text[start: end if end > 0 else len(text)]
    out = {"form":"表5-"+m.group(1), "land_use_label":m.group(2), "rows":[], "subtotals":{}, "total":None}
    cm = re.search(r'案號[：:]\s*(\S+)', blk)
    if cm: out["case_no"] = cm.group(1)
    seg = re.findall(r'P\d{3}-\d{2}', blk)
    out["segment_nos"] = list(dict.fromkeys(seg))
    # 表5 的修正細項名稱常跨行（如「有無限制建築（整體開發、面\n積限制、高度限制……等）」），
    # 數值則落在其後某一列。故以狀態機處理：記住最近出現的細項，數值列回填給它。
    pending = None
    seen, filled = [], {}
    for line in blk.split("\n"):
        if not line.strip(): continue
        if "百分比小計" in line:
            # 「其他影響因素(8) 百分比小計」的 (8) 是群組編號，不是數值
            out["subtotals"].setdefault("order", []).append(
                nums_in(line.split("百分比小計")[-1]))
            pending = None; continue
        if "總修正數" in line or "=(1)+(2)" in line:
            # 「=(1)+(2)+…+(8)」本身含數字，需排除公式部分只取其後數值
            tail = line.split(")")[-1] if "=(1)" in line else line
            vals = nums_in(tail)
            if vals: out["total"] = vals
            pending = None; continue
        hit = next(((c, kws[0]) for c, kws in T5_ITEMS if any(k in line for k in kws)), None)
        if hit:
            pending = hit
            if hit[0] not in [c for c, _ in seen]: seen.append(hit)
        toks = re.findall(r'(\d)\s+(優|稍優|普通|稍劣|劣|無)|(-?\d+\.\d+)', line)
        levels, adjs = [], []
        for a, b, cnum in toks:
            if a: levels.append({"rank": int(a), "label": b})
            elif cnum: adjs.append(float(cnum))
        if pending and (levels or adjs) and pending[0] not in filled:
            filled[pending[0]] = {"levels": levels, "adjustments": adjs}
            pending = None
    for code, label in seen:
        f = filled.get(code, {"levels": [], "adjustments": []})
        out["rows"].append({"item_code": code, "item_label": label, **f})
    return out

# ---------- 表4 ----------
T4_ROWS = [
    ("unit_price","土地正常單價"),("date_adj","調整百分率"),
    ("adjusted_price","調整至估價基準日單價"),("segment_row","區域因素調整百分率"),
    ("area","7面積"),("width","8寬度"),("depth","9深度"),("shape","10形狀"),
    ("street_frontage","11臨街情形"),("terrain","12地勢"),
    ("road_type","13道路種類"),("front_road_width","14面前道路寬度"),
    ("near_school","15接近學校之程度"),("near_market","16接近市場之程度"),
    ("near_park","17接近公園"),("near_station","18接近車站之程度"),
    ("near_business","19接近商圈之程度"),("nuisance","20嫌惡設施"),
    ("parking_ease","21停車方便性"),("zoning","22使用分區或編定用地"),
    ("bcr","23建蔽率"),("far","24容積率"),("build_ban_restrict","25有無禁限建"),
    ("total","合計"),("abs_sum","調整百分率絕對值加總"),
    ("trial_price","試算價格"),("final","比準地"),
]

def parse_t4(text):
    i = text.find("表4")
    if i < 0: return None
    blk = text[i:]
    out = {"form":"表4","rows":{}}
    m = re.search(r'估價基準日[：:]\s*(\d+)', blk);  out["appraisal_date"] = m.group(1) if m else None
    m = re.search(r'案號[：:]\s*(\S+)', blk);        out["case_no"] = m.group(1) if m else None
    out["segment_nos"] = list(dict.fromkeys(re.findall(r'P\d{3}-\d{2}', blk)))
    for line in blk.split("\n"):
        for code, kw in T4_ROWS:
            if kw in line:
                c = cells(line)
                out["rows"].setdefault(code, []).append(
                    {"raw_cells": c,
                     "numbers": [num(x) for x in c if NUMTOK.match(x)]})
                break
    out["factors"], out["summary"] = _normalize_t4(blk)
    m = re.search(r'0基本資料\s+(.*)', blk)
    if m: out["lots"] = cells(m.group(1))
    notes = re.findall(r'(依土地徵收補償市價查估辦法第\s*\d+\s*條[^\n]*)', blk)
    if notes: out["notes"] = [re.sub(r'\s+',' ',n) for n in notes]
    return out

PCT = re.compile(r'^-?[\d,]+(?:\.\d+)?\s*[%％]$')
GROUP_NOISE = re.compile(r'^(?:個|別|因|素|調|整|條件|宗地|道路|接近|周邊環|境條件|行政|決|定|比|較)$')
FIELD_ROWS = [(c, k) for c, k in T4_ROWS if re.match(r'\d', k)]

def _normalize_t4(blk):
    """把表4 各列整理成 {條件值, 差異率}。差異率以『%』結尾辨識，可避開群組編號等雜訊。"""
    lines = blk.split("\n")
    factors, summary = {}, {}
    _fill_summary(lines, summary)
    # 比較標的數＝土地正常單價列的數值個數；差異率為每列最後 n_comp 個百分比。
    # 建蔽率/容積率的「條件」本身就是百分比，必須靠這個數量才切得開。
    n_comp = max(1, len(summary.get("unit_price", {}).get("values", []) or [1]))
    for code, kw in FIELD_ROWS:
        idx = next((i for i, l in enumerate(lines) if kw in l), None)
        if idx is None: continue
        c = cells(lines[idx])
        # 值落在標籤列的鄰行時（合併儲存格所致）往上下各找一行
        if len([x for x in c if PCT.match(x)]) == 0:
            for d in (-1, 1):
                if not (0 <= idx + d < len(lines)): continue
                c2 = cells(lines[idx + d])
                if any(PCT.match(x) for x in c2) and kw not in lines[idx + d]:
                    c = c + c2; break
        lab_i = next((i for i, x in enumerate(c) if kw in x), 0)
        rest = [x for i, x in enumerate(c) if i > lab_i and not GROUP_NOISE.match(x)]
        pcts = [x for x in rest if PCT.match(x)]
        diffs = [float(x.rstrip('%％').replace(',', '')) for x in pcts[-n_comp:]]
        extra_pct = pcts[:-n_comp] if len(pcts) > n_comp else []
        conds = [x for x in rest
                 if (not PCT.match(x) or x in extra_pct) and x not in ('M', 'm')]
        fno = int(re.match(r'(\d+)', kw).group(1))
        factors[code] = {"field_no": fno, "label": kw, "conditions": conds, "diffs": diffs}
    return factors, summary


def _fill_summary(lines, summary):
    for code, kw in [("unit_price","土地正常單價"),("adjusted_price","調整至估價基準日單價"),
                     ("date_adj","調整百分率"),("regional","區域因素調整百分率"),
                     ("total","合計"),("abs_sum","調整百分率絕對值加總"),
                     ("trial","試算價格"),("weight","比較標的權重")]:
        idx = next((i for i, l in enumerate(lines) if kw in l), None)
        if idx is None: continue
        c = cells(lines[idx])
        lab_i = next((i for i, x in enumerate(c) if kw in x), 0)
        rest = [x for i, x in enumerate(c) if i > lab_i]
        pcts = [float(x.rstrip('%％').replace(',', '')) for x in rest if PCT.match(x)]
        vals = [float(x.replace(',', '')) for x in rest
                if re.fullmatch(r'-?[\d,]+(?:\.\d+)?', x)]
        summary[code] = {"percents": pcts, "values": vals, "raw": rest}


def main():
    S = sys.argv[1]
    specs = [
        ("題目.txt","shulin","doc/題目.pdf","target"),
        ("查估書表範本.txt","jinshan","doc/rules/查估書表範本.pdf","reference"),
    ]
    for fn, region, src, role in specs:
        text = open(os.path.join(S, fn), encoding="utf-8").read()
        t5, t4 = parse_t5(text), parse_t4(text)
        case_no = (t4 or {}).get("case_no") or (t5 or {}).get("case_no") or "unknown"
        d = os.path.join(OUT,"regions",region,"cases"); os.makedirs(d, exist_ok=True)
        doc = {"schema_version":"1.0","case_no":case_no,"region_code":region,
               "source":{"pdf":src,"role":role},
               "table5":t5,"table4":t4}
        safe = case_no.replace("/","_")
        json.dump(doc, open(os.path.join(d,f"{safe}.json"),"w",encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        yaml.safe_dump(doc, open(os.path.join(d,f"{safe}.yaml"),"w",encoding="utf-8"),
                       allow_unicode=True, sort_keys=False, width=200)
        n5 = len(t5["rows"]) if t5 else 0
        filled = sum(1 for r in (t5["rows"] if t5 else []) if r["adjustments"])
        print(f"{region} [{role}] 案號 {case_no}")
        print(f"   表5: {n5} 列（已填修正率 {filled} 列）  區段 {(t5 or {}).get('segment_nos')}")
        print(f"   表4: {len(t4['rows']) if t4 else 0} 個欄位列  基準日 {(t4 or {}).get('appraisal_date')}")

if __name__ == "__main__": main()
