# -*- coding: utf-8 -*-
"""將 JSON 資料集載入 SQLite，提供 SQL 檢索"""
import os, json, glob, sqlite3

OUT = "datasets"
DB = os.path.join(OUT, "db", "appraisal.sqlite")
os.makedirs(os.path.dirname(DB), exist_ok=True)
if os.path.exists(DB): os.remove(DB)
con = sqlite3.connect(DB); cur = con.cursor()

cur.executescript("""
PRAGMA foreign_keys=ON;

CREATE TABLE regions(
  region_code TEXT PRIMARY KEY, region_name TEXT, land_use_code TEXT,
  land_use_name TEXT, role TEXT);

CREATE TABLE criteria_items(
  item_id TEXT PRIMARY KEY, region_code TEXT, factor_type TEXT, seq INTEGER,
  group_code INTEGER, group_name TEXT, item_code TEXT, item_name TEXT,
  field_no INTEGER, level_count INTEGER, max_adjustment REAL, step REAL,
  rule_type TEXT, direction TEXT, basis TEXT);
CREATE INDEX ix_ci_region ON criteria_items(region_code, factor_type);
CREATE INDEX ix_ci_code   ON criteria_items(item_code);

CREATE TABLE criteria_levels(
  item_id TEXT, rank INTEGER, label TEXT, criterion TEXT,
  kind TEXT, unit TEXT, in_segment INTEGER, or_none INTEGER,
  min_value REAL, max_value REAL, categories TEXT, threshold_json TEXT,
  PRIMARY KEY(item_id, rank));

CREATE TABLE criteria_matrix(
  item_id TEXT, base_rank INTEGER, comparable_rank INTEGER, adjustment REAL,
  PRIMARY KEY(item_id, base_rank, comparable_rank));

CREATE TABLE segments(
  segment_id TEXT PRIMARY KEY, region_code TEXT, land_use_code TEXT,
  year_period TEXT, segment_no TEXT, scope_desc TEXT,
  land_use_current TEXT, observed_fields INTEGER, facilities_count INTEGER, source TEXT);

CREATE TABLE segment_observations(
  segment_id TEXT, field_code TEXT, field_name TEXT, raw TEXT,
  value REAL, unit TEXT, level_rank INTEGER, level_count INTEGER,
  PRIMARY KEY(segment_id, field_code));

CREATE TABLE segment_facilities(
  segment_id TEXT, idx INTEGER, label TEXT, name TEXT, quantity TEXT,
  in_segment INTEGER, distance_m REAL, criteria_item_code TEXT,
  mapping_confidence TEXT, needs_review INTEGER,
  PRIMARY KEY(segment_id, idx));

CREATE TABLE cases(
  case_no TEXT PRIMARY KEY, region_code TEXT, role TEXT,
  appraisal_date TEXT, form5 TEXT, land_use_label TEXT,
  segment_nos TEXT, regional_total REAL, source TEXT);

CREATE TABLE case_regional_rows(
  case_no TEXT, seq INTEGER, item_code TEXT, item_label TEXT,
  base_rank INTEGER, base_label TEXT,
  comp_ranks TEXT, adjustments TEXT,
  PRIMARY KEY(case_no, seq));

CREATE TABLE case_table4_rows(
  case_no TEXT, row_code TEXT, seq INTEGER, cells TEXT, numbers TEXT,
  PRIMARY KEY(case_no, row_code, seq));

CREATE TABLE images(
  image_id TEXT PRIMARY KEY, region TEXT, doc_id TEXT, kind TEXT,
  source_pdf TEXT, page INTEGER, path TEXT, caption TEXT,
  width INTEGER, height INTEGER, tags TEXT, bytes INTEGER, sha256_16 TEXT);
CREATE INDEX ix_img_region ON images(region, kind);

CREATE TABLE forms(
  code TEXT PRIMARY KEY, article TEXT, name TEXT, producer TEXT, is_core INTEGER);

CREATE TABLE review_checklist(
  id TEXT PRIMARY KEY, target TEXT, automatable INTEGER, content TEXT);

CREATE TABLE cross_reference_matrix(
  id TEXT PRIMARY KEY, src TEXT, dst TEXT, check_desc TEXT,
  checklist TEXT, priority INTEGER);

CREATE TABLE case_rules(
  id TEXT PRIMARY KEY, name TEXT, source TEXT, confirmed_by TEXT,
  severity TEXT, detail_json TEXT);

CREATE TABLE segment_valuation_basis(
  segment_id TEXT PRIMARY KEY, rule_applied TEXT,
  zoning_label_in_scope TEXT, zoning_prior_to_change TEXT,
  zoning_declared_in_form TEXT, zoning_for_valuation TEXT,
  land_use_current_in_form TEXT, land_use_current_overridden INTEGER, note TEXT);

CREATE TABLE segment_rule_checks(
  segment_id TEXT, rule TEXT, applicable INTEGER, consistent INTEGER,
  severity TEXT, message TEXT, detail_json TEXT,
  PRIMARY KEY(segment_id, rule));

CREATE TABLE legal_articles(
  law TEXT, article TEXT, content TEXT, PRIMARY KEY(law, article));
""")

def j(x): return json.dumps(x, ensure_ascii=False)

# --- criteria ---
for path in sorted(glob.glob(f"{OUT}/regions/*/criteria/*.json")):
    d = json.load(open(path, encoding="utf-8"))
    cur.execute("INSERT OR IGNORE INTO regions VALUES(?,?,?,?,?)",
                (d["region_code"], d["region_name"], d["land_use_code"],
                 d["land_use_name"], d["source"]["role"]))
    for it in d["items"]:
        cur.execute("""INSERT INTO criteria_items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            it["item_id"], it["region_code"], it["factor_type"], it.get("seq"),
            it.get("group_code"), it.get("group_name"), it["item_code"], it["item_name"],
            it.get("field_no"), it.get("level_count"), it.get("max_adjustment"),
            it.get("step"), it.get("rule_type"), it.get("direction"), it.get("basis")))
        for lv in it.get("levels", []):
            th = lv.get("threshold") or {}
            rs = th.get("ranges") or [{}]
            cur.execute("INSERT OR REPLACE INTO criteria_levels VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
                it["item_id"], lv["rank"], lv["label"], lv.get("criterion"),
                th.get("kind"), th.get("unit"),
                int(bool(th.get("in_segment"))), int(bool(th.get("or_none"))),
                rs[0].get("min"), rs[0].get("max"),
                j(th.get("categories")) if th.get("categories") else None, j(th)))
        mx = it.get("matrix")
        if mx:
            for i, row in enumerate(mx, 1):
                for k, v in enumerate(row, 1):
                    cur.execute("INSERT OR REPLACE INTO criteria_matrix VALUES(?,?,?,?)",
                                (it["item_id"], i, k, v))

# --- segments ---
for path in sorted(glob.glob(f"{OUT}/regions/*/segments/P*.json")):
    s = json.load(open(path, encoding="utf-8"))
    cur.execute("INSERT OR REPLACE INTO segments VALUES(?,?,?,?,?,?,?,?,?,?)", (
        s["segment_id"], s["region_code"], s["land_use_code"], s["year_period"],
        s["segment_no"], s.get("scope_desc"), s.get("land_use_current"),
        s["completeness"]["observed_fields"], s["completeness"]["facilities_recorded"],
        s["source"]))
    for code, o in s["observations"].items():
        cur.execute("INSERT OR REPLACE INTO segment_observations VALUES(?,?,?,?,?,?,?,?)", (
            s["segment_id"], code, o.get("field_name"), o.get("raw"),
            o.get("value"), o.get("unit"), o.get("level_rank"), o.get("level_count")))
    vb = s.get("valuation_basis")
    if vb:
        cur.execute("INSERT OR REPLACE INTO segment_valuation_basis VALUES(?,?,?,?,?,?,?,?,?)", (
            s["segment_id"], vb.get("rule_applied"), vb.get("zoning_label_in_scope"),
            vb.get("zoning_prior_to_change"), vb.get("zoning_declared_in_form"),
            vb.get("zoning_for_valuation"), vb.get("land_use_current_in_form"),
            int(bool(vb.get("land_use_current_overridden"))), vb.get("note")))
    for ck in s.get("rule_checks", []):
        cur.execute("INSERT OR REPLACE INTO segment_rule_checks VALUES(?,?,?,?,?,?,?)", (
            s["segment_id"], ck["rule"],
            int(bool(ck.get("applicable"))),
            None if ck.get("consistent") is None else int(ck["consistent"]),
            ck.get("severity"), ck.get("message"), j(ck)))
    for i, f in enumerate(s.get("facilities", [])):
        cur.execute("INSERT OR REPLACE INTO segment_facilities VALUES(?,?,?,?,?,?,?,?,?,?)", (
            s["segment_id"], i, f.get("label"), f.get("name"), f.get("quantity"),
            int(bool(f.get("in_segment"))), f.get("distance_m"),
            f.get("criteria_item_code"), f.get("mapping_confidence"),
            int(bool(f.get("needs_review")))))

# --- cases ---
for path in sorted(glob.glob(f"{OUT}/regions/*/cases/*.json")):
    c = json.load(open(path, encoding="utf-8"))
    t5, t4 = c.get("table5") or {}, c.get("table4") or {}
    tot = t5.get("total")
    cur.execute("INSERT OR REPLACE INTO cases VALUES(?,?,?,?,?,?,?,?,?)", (
        c["case_no"], c["region_code"], c["source"]["role"], t4.get("appraisal_date"),
        t5.get("form"), t5.get("land_use_label"), j(t5.get("segment_nos")),
        (tot[0] if tot else None), c["source"]["pdf"]))
    for i, r in enumerate(t5.get("rows", [])):
        lv = r.get("levels") or []
        cur.execute("INSERT OR REPLACE INTO case_regional_rows VALUES(?,?,?,?,?,?,?,?)", (
            c["case_no"], i, r["item_code"], r["item_label"],
            lv[0]["rank"] if lv else None, lv[0]["label"] if lv else None,
            j([x["rank"] for x in lv[1:]]), j(r.get("adjustments"))))
    for code, rows in (t4.get("rows") or {}).items():
        for i, r in enumerate(rows):
            cur.execute("INSERT OR REPLACE INTO case_table4_rows VALUES(?,?,?,?,?)", (
                c["case_no"], code, i, j(r.get("raw_cells")), j(r.get("numbers"))))

# --- images / common ---
imgs = json.load(open(f"{OUT}/common/images.json", encoding="utf-8"))["images"]
for m in imgs:
    cur.execute("INSERT OR REPLACE INTO images VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (
        m["image_id"], m["region"], m["doc_id"], m["kind"], m["source_pdf"], m["page"],
        m["path"], m.get("caption"), m.get("width"), m.get("height"),
        j(m.get("tags")), m.get("bytes"), m.get("sha256_16")))

F = json.load(open(f"{OUT}/common/forms.json", encoding="utf-8"))
for f in F["forms"]:
    cur.execute("INSERT OR REPLACE INTO forms VALUES(?,?,?,?,?)",
                (f["code"], f.get("article"), f["name"], f.get("producer"), int(f.get("core", False))))
R = json.load(open(f"{OUT}/common/review_rules.json", encoding="utf-8"))
for r in R["official_checklist"]:
    cur.execute("INSERT OR REPLACE INTO review_checklist VALUES(?,?,?,?)",
                (r["id"], r.get("target"), int(r.get("automatable", False)), r["content"]))
for r in R["cross_reference_matrix"]:
    cur.execute("INSERT OR REPLACE INTO cross_reference_matrix VALUES(?,?,?,?,?,?)",
                (r["id"], r["from"], r["to"], r["check"], r.get("checklist"), r.get("priority")))
CR = json.load(open(f"{OUT}/common/case_rules.json", encoding="utf-8"))
for r in CR["rules"]:
    cur.execute("INSERT OR REPLACE INTO case_rules VALUES(?,?,?,?,?,?)",
                (r["id"], r["name"], r.get("source"), r.get("confirmed_by"),
                 r.get("severity"), j(r)))
L = json.load(open(f"{OUT}/common/legal_references.json", encoding="utf-8"))
for a in L["articles"]:
    cur.execute("INSERT OR REPLACE INTO legal_articles VALUES(?,?,?)",
                (a["law"], a["article"], a["content"]))

con.commit()
print("=== SQLite 建置完成:", DB, "===")
tables = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
for t in tables:
    n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t:28s} {n:6d} 列")
print(f"\n檔案大小 {os.path.getsize(DB)/1024:.0f} KB")
con.close()
