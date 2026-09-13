# -*- coding: utf-8 -*-
"""引擎測試：正向（官方範例應零錯誤）＋ 反向（注入錯誤必須被抓到）"""
import sys, os, copy, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from loader import Dataset
from review import review_case
import checks as C

FAIL = []


def expect(name, cond, detail=""):
    if not cond: FAIL.append(f"{name}{(' — ' + detail) if detail else ''}")
    return cond


def fired(findings, rule, severity="error"):
    return [f for f in findings if f.rule == rule and f.severity == severity]


ds = Dataset()
JS = ds.cases("jinshan")["1140901-99-001"]
SEGS = ds.segments("jinshan")

print("=" * 70)
print("正向測試：官方已填範例（金山）不應出現 error")
print("=" * 70)
r = review_case(ds, "jinshan")
errs = [f for f in r["findings"] if f.severity == "error"]
expect("金山零錯誤", not errs, "; ".join(f"{f.rule}:{f.message}" for f in errs))
print(f"  error {len(errs)} 件　"
      f"warning {sum(1 for f in r['findings'] if f.severity=='warning')} 件 "
      f"{'✅' if not errs else '❌'}")
for f in errs: print("   ❌", f.rule, f.item, f.message, f.expected, f.actual)

print()
print("=" * 70)
print("反向測試：注入已知錯誤，檢查必須觸發")
print("=" * 70)

CASES = []

# ---- R2：竄改表5 修正百分比
c = copy.deepcopy(JS)
row = next(r_ for r_ in c["table5"]["rows"] if r_["item_code"] == "main_road_width")
row["levels"] = [{"rank": 3, "label": "普通"}, {"rank": 5, "label": "劣"}]
row["adjustments"] = [0.00]          # 表5 方向：(5-3)×3.75 = +7.5（與表4 同向）
CASES.append(("R2 修正率與基準表不符", lambda cc: C.check_R2(ds, "jinshan", cc), c, "R2", 7.5))

# ---- R4：表4 區域因素調整率與表5 總修正數不一致
c = copy.deepcopy(JS)
c["table4"]["summary"]["regional"]["percents"] = [3.21]
CASES.append(("R4 表5→表4 總修正數不符", lambda cc: C.check_R4(ds, "jinshan", cc), c, "R4", 0.0))

# ---- R6：竄改表4 個別因素差異率
c = copy.deepcopy(JS)
c["table4"]["factors"]["front_road_width"]["diffs"] = [2.50]   # 正解 5.00
CASES.append(("R6 個別因素差異率錯誤", lambda cc: C.check_R6(ds, "jinshan", cc), c, "R6", 5.0))

# ---- R6：條件值改動後差異率未同步
c = copy.deepcopy(JS)
c["table4"]["factors"]["depth"]["conditions"] = ["23", "55"]    # 55m → 稍劣
CASES.append(("R6 條件已改但差異率未更新", lambda cc: C.check_R6(ds, "jinshan", cc), c, "R6", None))

# ---- R14：小計加總與總修正數不符
c = copy.deepcopy(JS)
c["table5"]["subtotals"]["order"][0] = [2.5]
CASES.append(("R14 小計加總錯誤", lambda cc: C.check_R14(ds, "jinshan", cc), c, "R14", 2.5))

# ---- R7：單一比較標的權重非 100%
c = copy.deepcopy(JS)
c["table4"]["summary"]["weight"]["percents"] = [80.0]
CASES.append(("R7 權重不合邏輯", lambda cc: C.check_R7(ds, "jinshan", cc), c, "R7", 100.0))

# ---- PRICE：試算價格與連乘結果不符
c = copy.deepcopy(JS)
c["table4"]["summary"]["trial"]["values"] = [999999.0]
CASES.append(("PRICE 試算價格錯誤", lambda cc: C.check_price_chain(ds, "jinshan", cc), c, "PRICE", 212958))

for name, fn, case, rule, exp in CASES:
    fs = fn(case)
    hit = fired(fs, rule)
    ok = expect(name, bool(hit), "檢查未觸發")
    detail = ""
    if hit:
        h = hit[0]
        detail = f"應為 {h.expected} 實際 {h.actual}"
        if exp is not None and h.expected is not None:
            expect(name + "（期望值）", abs(float(h.expected) - float(exp)) < 1e-6,
                   f"引擎算出 {h.expected}，測試預期 {exp}")
    print(f"  {'✅' if ok else '❌'} {name:28s} {detail}")

print()
print("=" * 70)
print("表5 推導（樹林待作答案件）")
print("=" * 70)
r2 = review_case(ds, "shulin")
d = r2["derived_table5"]
expect("樹林可算項目數 > 0", d["computable_items"] > 0)
expect("樹林未宣稱完整", not d["complete"], "資料不足時不得標記為完整")
expect("樹林比準地為 P001-00", d["base_segment"] == "P001-00")
# 表5 方向：(比較標的級距 − 比準地級距) × 級距差，與表4 同向，比較標的較劣為正
# 期望值由基準表 step 獨立推算，不抄引擎輸出，方向錯誤時必然失敗
crit_reg = ds.criteria("shulin", "regional")
# 接近大型車站等設施類細項不在此列：表3 未載勘查資料，僅 output/thirdVersion
# 以開放資料推算補填，review_case 的推導路徑取不到值
for code, name in (("far", "容積率"), ("main_road_width", "主要道路寬度"),
                   ("avg_road_width", "區段內道路平均寬度"),
                   ("road_dev", "區段內道路規劃及闢建程度")):
    r_ = next(x for x in d["rows"] if x["item_code"] == code)
    b_, c_ = r_["base"]["rank"], r_["comparables"][0]["rank"]
    exp_ = (c_ - b_) * crit_reg[code]["step"]
    expect(f"{name} P002 修正率 {exp_:+.2f}", abs(r_["adjustments"][0] - exp_) < 1e-9,
           f"比準地{b_} 比較標的{c_}，期望 {exp_:+.2f} 得 {r_['adjustments'][0]:+.2f}")
far = next(x for x in d["rows"] if x["item_code"] == "far")
road = next(x for x in d["rows"] if x["item_code"] == "main_road_width")
print(f"  可算 {d['computable_items']}/{d['total_items']} 項，"
      f"標記完整={d['complete']} ✅")
print(f"  容積率 P001(普通) vs P002(稍劣) = {far['adjustments'][0]:+.2f}% ✅")
print(f"  主要道路 P001(優,28m) vs P002(劣,7m) = {road['adjustments'][0]:+.2f}% ✅")

print()
print("=" * 70)
print("查表方向：表5 與表4 同向，皆以金山官方範本校準")
print("=" * 70)
# 表4 個別因素方向以金山官方已填範本校準（查估書表範本 表4，五筆非零細項）
from grading import adjust as _adj
ji = ds.criteria("jinshan", "individual")
for code, b_, c_, exp_, why in (
        ("front_road_width", 2, 4, 5.0, "比準地18m(稍優)／比較標的6m(稍劣)"),
        ("road_type", 1, 2, 2.0, "比準地主要道路(優)／比較標的次要道路(稍優)"),
        ("parking_ease", 1, 2, 2.0, "比準地可路邊停車(優)／比較標的不可(劣)"),
        ("depth", 3, 4, 1.0, "比準地23m(普通)／比較標的16m(稍劣)"),
        ("nuisance", 3, 5, 3.0, "比準地公墓260m(普通)／比較標的80m(劣)")):
    got = _adj(ji[code], b_, c_)
    expect(f"表4 {ji[code]['item_name']} 與官方範本一致",
           abs(got - exp_) < 1e-9, f"{why}，範本填 {exp_:+.2f}，引擎得 {got:+.2f}")
    print(f"  ✅ 表4 {ji[code]['item_name']:8s} {why} → {got:+.2f}（範本 {exp_:+.2f}）")
# 表5 與表4 共用同一查表方向，此斷言防止日後又被拆成一正一反
sr = ds.criteria("shulin", "regional")["far"]
_far = next(x for x in d["rows"] if x["item_code"] == "far")
expect("表5 與表4 查表方向相同",
       abs(_adj(sr, 3, 4) - (4 - 3) * sr["step"]) < 1e-9,
       f"adjust={_adj(sr,3,4)}，期望 {(4-3)*sr['step']:+.2f}")
print(f"  ✅ 容積率 普通(3) vs 稍劣(4)：表5／表4 同為 {_adj(sr,3,4):+.2f}（比較標的較劣為正）")

print()
# CR1 應在樹林觸發
cr1 = [f for f in r2["findings"] if f.rule == "CR1"]
expect("CR1 於樹林觸發", bool(cr1))
print(f"  CR1 觸發 {len(cr1)} 件 ✅")

print()
print("=" * 70)
if FAIL:
    print(f"❌ 失敗 {len(FAIL)} 項")
    for f in FAIL: print("   -", f)
    sys.exit(1)
print("✅ 引擎測試全部通過")
