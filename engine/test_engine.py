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
row["adjustments"] = [0.00]          # 正解應為 +7.5
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
# 已知正確值：容積率 P001(260%,普通) vs P002(200%,稍劣) → +6.25
far = next(x for x in d["rows"] if x["item_code"] == "far")
expect("容積率 P002 修正率 +6.25", abs(far["adjustments"][0] - 6.25) < 1e-9,
       f"得 {far['adjustments'][0]}")
road = next(x for x in d["rows"] if x["item_code"] == "main_road_width")
expect("主要道路寬度 P002 修正率 +15.00", abs(road["adjustments"][0] - 15.0) < 1e-9,
       f"得 {road['adjustments'][0]}")
print(f"  可算 {d['computable_items']}/{d['total_items']} 項，"
      f"標記完整={d['complete']} ✅")
print(f"  容積率 P001(普通) vs P002(稍劣) = {far['adjustments'][0]:+.2f}% ✅")
print(f"  主要道路 P001(優,28m) vs P002(劣,7m) = {road['adjustments'][0]:+.2f}% ✅")

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
