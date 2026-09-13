# -*- coding: utf-8 -*-
"""產生全域索引 index.json"""
import os, json, glob, datetime, sqlite3
OUT = "datasets"

def load(p): return json.load(open(p, encoding="utf-8"))


def table_count():
    """實際數資料庫的表數，不要寫死（build_db.py 增表時這裡不會跟著改）。"""
    db = f"{OUT}/db/appraisal.sqlite"
    if not os.path.exists(db):
        return 0
    with sqlite3.connect(db) as con:
        return con.execute("SELECT count(*) FROM sqlite_master "
                           "WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]

regions = []
for rdir in sorted(glob.glob(f"{OUT}/regions/*")):
    rk = os.path.basename(rdir)
    reg = load(f"{rdir}/criteria/regional.json")
    ind = load(f"{rdir}/criteria/individual.json")
    segs = sorted(glob.glob(f"{rdir}/segments/P*.json"))
    cases = sorted(glob.glob(f"{rdir}/cases/*.json"))
    imgs = [m for m in load(f"{OUT}/common/images.json")["images"] if m["region"] == rk]
    regions.append({
        "region_code": rk,
        "region_name": reg["region_name"],
        "land_use_code": reg["land_use_code"],
        "land_use_name": reg["land_use_name"],
        "role": reg["source"]["role"],
        "role_desc": "待作答案件（優劣等級與修正率留白）" if reg["source"]["role"] == "target"
                     else "已填完整範例（可作為驗證基準）",
        "criteria": {
            "regional": {"path": f"regions/{rk}/criteria/regional.json", "items": reg["item_count"]},
            "individual": {"path": f"regions/{rk}/criteria/individual.json", "items": ind["item_count"]},
        },
        "segments": {"path": f"regions/{rk}/segments/", "count": len(segs),
                     "ids": [os.path.basename(s)[:-5] for s in segs]},
        "cases": {"path": f"regions/{rk}/cases/", "count": len(cases),
                  "ids": [os.path.basename(c)[:-5] for c in cases]},
        "images": {"path": f"regions/{rk}/img/", "count": len(imgs)},
    })

idx = {
    "schema_version": "1.0",
    "name": "新北市土地徵收補償市價查估 — 審查知識資料集",
    "built_at": datetime.date.today().isoformat(),
    "source_dir": "doc/",
    "description": "由 doc/ 內之命題文件、評價基準明細表、查估書表範本、作業手冊與 Excel 範本"
                   "抽取結構化而成，依行政區 + 用地別分類歸檔。",
    "formats": ["json", "yaml", "sqlite"],
    "database": {"path": "db/appraisal.sqlite", "tables": table_count()},
    "regions": regions,
    "common": {
        "forms": "common/forms.json",
        "formulas": "common/formulas.json",
        "review_rules": "common/review_rules.json",
        "legal_references": "common/legal_references.json",
        "images": "common/images.json",
        "img_dir": "common/img/",
    },
    "verification": {
        "script": "_build/run_tests.py",
        "golden_source": "doc/rules/查估書表範本.pdf（金山區商業用地，已填完整）",
        "tests": [
            "基準表矩陣反對稱/步長/級距完整性（96 細項）",
            "表4 個別因素差異率 19/19 逐項吻合，合計 13.00%",
            "價格鏈 184,763 → 212,958 完全一致",
            "表3 設施距離 → 表5 優劣等級 10/10 吻合",
            "資料庫外鍵與圖檔存在性",
        ],
    },
}
json.dump(idx, open(f"{OUT}/index.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("index.json 已產生")
for r in regions:
    print(f"  {r['region_code']:8s} {r['region_name']}{r['land_use_name']:8s} "
          f"[{r['role']}] 基準 {r['criteria']['regional']['items']}+{r['criteria']['individual']['items']} 項, "
          f"區段 {r['segments']['count']}, 案件 {r['cases']['count']}, 圖 {r['images']['count']}")
