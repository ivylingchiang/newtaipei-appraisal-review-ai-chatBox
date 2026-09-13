# -*- coding: utf-8 -*-
"""資料集回歸測試：以「查估書表範本」(金山) 的已知答案驗證資料正確性"""
import os, sys, json, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from threshold import match_level

FAIL = []
def check(name, got, exp):
    ok = got == exp
    if not ok: FAIL.append(f"{name}: 得 {got} 期望 {exp}")
    return ok

def load(p): return json.load(open(p, encoding="utf-8"))

print("=" * 66)
print("測試 1：基準表結構完整性")
print("=" * 66)
tot_items = 0
for reg, ft, n in [("shulin","regional",29),("shulin","individual",20),
                   ("jinshan","regional",28),("jinshan","individual",19)]:
    d = load(f"datasets/regions/{reg}/criteria/{ft}.json")
    ok = check(f"{reg}.{ft} 項目數", len(d["items"]), n)
    tot_items += len(d["items"])
    bad = 0
    for it in d["items"]:
        if it.get("rule_type") != "matrix": continue
        m, k = it["matrix"], it["level_count"]
        if any(len(r) != k for r in m): bad += 1
        if any(abs(m[i][i]) > 1e-9 for i in range(k)): bad += 1
        if any(abs(m[i][jj] + m[jj][i]) > 1e-6 for i in range(k) for jj in range(k)): bad += 1
        if any(not lv["criterion"] for lv in it["levels"]): bad += 1
    check(f"{reg}.{ft} 矩陣/級距瑕疵", bad, 0)
    print(f"  {reg:8s} {ft:11s} {len(d['items']):2d} 項  矩陣反對稱/級距完整 {'✅' if bad==0 else '❌'}")
print(f"  合計 {tot_items} 個細項")

print("\n" + "=" * 66)
print("測試 2：表4 個別因素差異率（金山範本，19 項已知答案）")
print("=" * 66)
D = load("datasets/regions/jinshan/criteria/individual.json")
items = {i["item_code"]: i for i in D["items"]}
def lv(code, value=None, cat=None):
    it = items[code]
    if cat is not None:
        for l in it["levels"]:
            th = l["threshold"]
            if th["kind"] == "categorical" and cat in th["categories"]: return l["rank"]
        return None
    return match_level(value, it["levels"])
CASES = [
    ("area",{"value":113.21},{"value":111.85},0.00),("width",{"value":5},{"value":7},0.00),
    ("depth",{"value":23},{"value":16},1.00),("shape",{"cat":"方形"},{"cat":"方形"},0.00),
    ("street_frontage",{"cat":"單面臨街"},{"cat":"單面臨街"},0.00),("terrain",{"cat":"平坦"},{"cat":"平坦"},0.00),
    ("road_type",{"cat":"主要道路"},{"cat":"次要道路"},2.00),("front_road_width",{"value":18},{"value":6},5.00),
    ("near_school",{"value":150},{"value":100},0.00),("near_market",{"value":30},{"value":92},0.00),
    ("near_park",{"value":190},{"value":200},0.00),("near_station",{"value":80},{"value":190},0.00),
    ("near_business",{"value":0},{"value":0},0.00),("nuisance",{"value":260},{"value":80},3.00),
    ("parking_ease",{"cat":"可路邊停車"},{"cat":"不可路邊停車"},2.00),("zoning",{"cat":"商業區"},{"cat":"商業區"},0.00),
    ("bcr",{"value":70},{"value":70},0.00),("far",{"value":240},{"value":240},0.00),
    ("build_ban_restrict",{"cat":"無禁止或限制建築"},{"cat":"無禁止或限制建築"},0.00),
]
total = 0.0; passed = 0
for code, b, c, exp in CASES:
    rb, rc = lv(code, b.get("value"), b.get("cat")), lv(code, c.get("value"), c.get("cat"))
    got = items[code]["matrix"][rb-1][rc-1] if (rb and rc) else None
    total += got or 0
    if check(f"表4 {code}", got, exp): passed += 1
print(f"  逐項符合 {passed}/{len(CASES)}")
check("表4 個別因素合計", round(total, 2), 13.00)
print(f"  個別因素合計 {total:.2f}% (期望 13.00%) {'✅' if abs(total-13)<1e-9 else '❌'}")

print("\n" + "=" * 66)
print("測試 3：價格鏈（表4）")
print("=" * 66)
unit, date_adj, regional = 184763, 0.02, 0.0
adjusted = unit * (1 + date_adj)
trial = round(adjusted * (1 + regional + total/100))
abs_sum = 2.00 + 0.00 + sum(abs(c[3]) for c in CASES)
check("試算價格", trial, 212958)
check("絕對值加總", round(abs_sum, 2), 15.00)
print(f"  {unit:,} × 1.02 = {adjusted:,.2f} × 1.13 = {trial:,} (期望 212,958) {'✅' if trial==212958 else '❌'}")
print(f"  調整百分率絕對值加總 {abs_sum:.2f}% (期望 15.00%) {'✅' if abs(abs_sum-15)<1e-9 else '❌'}")

print("\n" + "=" * 66)
print("測試 4：表3 觀測 → 表5 優劣等級（金山範本）")
print("=" * 66)
seg = load("datasets/regions/jinshan/segments/P002-00.json")
crit = {i["item_code"]: i for i in load("datasets/regions/jinshan/criteria/regional.json")["items"]}
t5 = {r["item_code"]: r for r in load("datasets/regions/jinshan/cases/1140901-99-001.json")["table5"]["rows"]}
from collections import defaultdict
byitem = defaultdict(list)
for f in seg["facilities"]:
    if f["criteria_item_code"]: byitem[f["criteria_item_code"]].append(f)
n = ok = 0
for code, fs in sorted(byitem.items()):
    it = crit.get(code)
    if not it or code not in t5: continue
    inseg = any(f["in_segment"] for f in fs)
    ds = [f["distance_m"] for f in fs if f["distance_m"] is not None]
    # 表3 明載「無」者以「或無」級距判定（如無交流道 → 劣）
    is_none = (not ds) and (not inseg) and any(f.get("is_none") for f in fs)
    rank = match_level(min(ds) if ds else None, it["levels"],
                       in_segment=inseg, is_none=is_none)
    exp = (t5[code]["levels"] or [{}])[0].get("rank")
    n += 1; ok += check(f"表5 {code} 等級", rank, exp)
print(f"  設施距離→等級 符合 {ok}/{n}")

print("\n" + "=" * 66)
print("測試 5：案件層級規則 CR1 / CR2")
print("=" * 66)
p1 = load("datasets/regions/shulin/segments/P001-00.json")
vb = p1.get("valuation_basis") or {}
check("CR1 觸發", vb.get("rule_applied"), "CR1")
check("CR1 變更前分區", vb.get("zoning_prior_to_change"), "第一種住宅區")
check("CR1 估價採用分區", vb.get("zoning_for_valuation"), "第一種住宅區")
check("CR1 現況欄已標記覆蓋", vb.get("land_use_current_overridden"), True)
# 分區等級：第一種住宅區 → 樹林住宅基準表「稍優」(2)，而非捷運用地之「優」(1)
reg = {i["item_code"]: i for i in load("datasets/regions/shulin/criteria/regional.json")["items"]}
def cat_rank(item, text):
    for l in item["levels"]:
        th = l["threshold"]
        if th["kind"] == "categorical" and any(c in text or text in c for c in th["categories"]):
            return l["rank"]
    return None
r_house = cat_rank(reg["zoning"], "住宅區")
r_mrt   = cat_rank(reg["zoning"], "捷運用地(聯開)")
check("第一種住宅區→稍優(2)", r_house, 2)
check("捷運用地→優(1)", r_mrt, 1)
print(f"  CR1 套用：P001-00 分區採「{vb.get('zoning_for_valuation')}」"
      f"（表3 現況欄「{vb.get('land_use_current_in_form')}」不採計）✅")
print(f"  分區等級差異：住宅區 rank {r_house} vs 捷運用地 rank {r_mrt} "
      f"→ 誤判將產生 {abs(r_house-r_mrt)*reg['zoning']['step']:.0f}% 的使用分區修正率偏差")
c2 = {s["segment_no"]: s for s in
      [load(f"datasets/regions/shulin/segments/P00{i}-00.json") for i in (1,2,3,4)]}
hit = [x for x in (c2["P002-00"].get("rule_checks") or []) if x["rule"] == "CR2"]
check("CR2 於 P002-00 適用", bool(hit) and hit[0]["applicable"], True)
check("CR2 於 P002-00 相符", hit[0]["consistent"] if hit else None, True)
print(f"  CR2 驗證：P002-00 主要道路 7m ≤ 8m，容積率 200% 與規則相符 ✅")

print("\n" + "=" * 66)
print("測試 6：資料庫完整性")
print("=" * 66)
con = sqlite3.connect("datasets/db/appraisal.sqlite")
q = lambda s: con.execute(s).fetchone()[0]
check("criteria_items 數", q("SELECT COUNT(*) FROM criteria_items"), 96)
check("矩陣列數", q("SELECT COUNT(*) FROM criteria_matrix"), 2120)
check("孤兒 levels", q("""SELECT COUNT(*) FROM criteria_levels l
    LEFT JOIN criteria_items i ON l.item_id=i.item_id WHERE i.item_id IS NULL"""), 0)
check("孤兒 matrix", q("""SELECT COUNT(*) FROM criteria_matrix m
    LEFT JOIN criteria_items i ON m.item_id=i.item_id WHERE i.item_id IS NULL"""), 0)
check("圖像數", q("SELECT COUNT(*) FROM images"), 74)
check("case_rules 數", q("SELECT COUNT(*) FROM case_rules"), 2)
check("valuation_basis 數", q("SELECT COUNT(*) FROM segment_valuation_basis"), 1)
check("rule_checks 數", q("SELECT COUNT(*) FROM segment_rule_checks"), 4)
miss = q("SELECT COUNT(*) FROM images WHERE path IS NULL OR path=''")
check("圖像路徑缺漏", miss, 0)
broken = sum(1 for (p,) in con.execute("SELECT path FROM images")
             if not os.path.exists(os.path.join("datasets", p)))
check("圖像檔案遺失", broken, 0)
print(f"  細項 96 / 矩陣 2120 / 圖像 74  外鍵與檔案存在性 {'✅' if not FAIL else '❌'}")

print("\n" + "=" * 66)
if FAIL:
    print(f"❌ 失敗 {len(FAIL)} 項")
    for f in FAIL: print("   -", f)
    sys.exit(1)
print("✅ 全部測試通過")
