# datasets — structured knowledge base

Everything here is **extracted from `doc/`** and filed by **district × land-use type**.
Nothing is hand-authored; the whole tree is rebuilt by `_build/run_all.sh`.

Three formats are published side by side:

| Format | For |
|---|---|
| **JSON** | programs (`engine/` reads these) |
| **YAML** | human review — same content, easier to diff and read |
| **SQLite** | ad-hoc SQL queries across regions (`db/appraisal.sqlite`, 18 tables) |

All extraction and grading logic is verified by back-calculating the fully completed Jinshan
reference case — see [§8 Validation](#8-validation).

---

## 1. Layout

```
datasets/
├── index.json                  Global index — start here
├── db/appraisal.sqlite         18 tables
├── regions/
│   ├── shulin/                 Shulin · residential          role: target
│   │   ├── criteria/
│   │   │   ├── regional.json|yaml     29 regional-factor items
│   │   │   └── individual.json|yaml   20 individual-factor items
│   │   ├── segments/           Form 3 — P001-00 … P004-00, _index.json, segments.yaml
│   │   ├── cases/              Forms 4 + 5 — 1110901-99-XXX
│   │   └── img/                15 page renders
│   └── jinshan/                Jinshan · commercial          role: reference
│       ├── criteria/           28 + 19 items
│       ├── segments/           P002-00
│       ├── cases/              1140901-99-001
│       └── img/                45 images (15 renders, 6 maps, 24 site photos)
├── common/                     Cross-district knowledge
│   ├── forms.json|yaml             Form 1–14 system and production workflow
│   ├── formulas.json|yaml          Calculation rules, rounding, weighting
│   ├── review_rules.json|yaml      Official review checklist + R1–R14 cross-table matrix
│   ├── case_rules.json|yaml        Case-level rulings CR1 / CR2
│   ├── legal_references.json|yaml  Cited articles
│   ├── images.json                 Manifest for all 74 images
│   └── img/                        14 images (workflow diagrams, legends)
├── external/                   Open data — used only by output/thirdVersion
│   ├── cache/                      Raw API responses, 19 sources (~17 MB)
│   └── poi_inference.json          Segment centroids, nearest facilities, grades
└── _build/                     Build scripts + regression tests
```

---

## 2. Where each file comes from

| Source in `doc/` | Build script | Produces |
|---|---|---|
| `rules/評價基準明細表.pdf`<br>`rules/評價基準明細表範例.pdf` | `build_criteria.py` | `regions/*/criteria/{regional,individual}.json\|yaml` |
| `題目.pdf` (Form 3 pages)<br>`rules/查估書表範本.pdf` | `build_segments.py` | `regions/*/segments/*.json`, `segments.yaml`, `_index.json` |
| `題目.pdf` (Forms 4, 5)<br>`rules/查估書表範本.pdf` | `build_cases.py` | `regions/*/cases/*.json\|yaml` |
| `rules/土地徵收補償市價查估作業手冊.pdf`<br>`rules/extra.md` | `build_common.py` | `common/{forms,formulas,review_rules,case_rules,legal_references}` |
| All PDFs — embedded bitmaps + page renders | `build_images.py` | `*/img/`, `common/images.json` |
| ↑ all JSON above | `build_db.py` | `db/appraisal.sqlite` |
| ↑ all of the above | `build_index.py` | `index.json` |
| `extraInfo/poi-links.md` + OpenStreetMap | `engine/poi_fetch.py`<br>`engine/poi_infer.py` | `external/cache/`, `external/poi_inference.json` |

---

## 3. Why two regions

They are a **deliberately paired sample**, not two unrelated batches.

| | `jinshan` — reference | `shulin` — target |
|---|---|---|
| Land use | Commercial | Ordinary residential |
| Source | `查估書表範本.pdf` + `評價基準明細表範例.pdf` | `題目.pdf` + `評價基準明細表.pdf` |
| State | **Fully completed** by the authority, grades and rates included | **Grades and rates left blank** — this is what the system must produce |
| Used for | Learning the filling rules; validating the algorithm | The actual case being answered |

> **Thresholds differ between the two districts.** "Excellent" building coverage ratio is ≥ 60 %
> in Jinshan but ≥ 80 % in Shulin; floor area ratio ≥ 240 % vs ≥ 460 %. Always load criteria by
> `(region_code, land_use_code)` — **never hard-code a threshold**.

---

## 4. Criteria items — the core data

`regions/{region}/criteria/{regional|individual}.json`

Each item carries its level thresholds **and** the full adjustment matrix, so grading and rate
lookup need no interpretation at runtime.

```jsonc
{
  "item_id": "shulin.regional.far",       // primary key
  "region_code": "shulin",
  "factor_type": "regional",              // regional | individual
  "seq": 4,
  "group_code": 1, "group_name": "土地使用管制",
  "item_code": "far", "item_name": "容積率",
  "field_no": null,                       // individual factors only (Form 4 fields 7–25)
  "level_count": 5,
  "level_labels": ["優", "稍優", "普通", "稍劣", "劣"],
  "max_adjustment": 25.0,                 // ±25 %
  "step": 6.25,                           // max_adjustment / (level_count - 1)
  "rule_type": "matrix",                  // matrix | narrative
  "direction": "higher_is_better",        // vs lower_is_better
  "levels": [
    { "rank": 1, "label": "優", "criterion": "460%以上",
      "threshold": { "kind": "numeric", "unit": "percent",
                     "ranges": [{ "min": 460.0, "min_inclusive": true }],
                     "in_segment": false, "or_none": false, "raw": "460%以上" } }
    // … ranks 2–5
  ],
  "matrix": [[0, 6.25, 12.5, 18.75, 25], …]   // anti-symmetric, zero diagonal
}
```

### Looking up an adjustment rate

```python
adj = item["matrix"][base_rank - 1][comparable_rank - 1]   # direct
adj = (comparable_rank - base_rank) * item["step"]         # equivalent
```

**Sign convention:** a positive rate means the comparable is *worse* than the benchmark.

### Matching a fact to a level

`threshold.kind == "numeric"`:

| Field | Meaning |
|---|---|
| `ranges[]` | `{min, max, min_inclusive, max_inclusive}`; may hold several disjoint bands |
| `unit` | `m` / `m2` / `percent` / `degree` |
| `in_segment` | "a facility inside the segment" also falls in this level |
| `or_none` | "or none" also falls in this level — common for nuisance facilities |

`threshold.kind == "categorical"` uses `categories[]` instead, e.g. `["方形", "梯形"]`.

Helper: `_build/threshold.py` → `match_level(value, levels, in_segment, is_none)`.

### Exceptions worth knowing

- `shulin.individual.far` has `rule_type: "narrative"` and **no matrix** — the source table states
  the difference must be tried out by land development analysis, jointly with the regional-factor
  floor area ratio. Jinshan's individual FAR *does* have a matrix (±40). Handle per region.
- `source_anomalies` records typos in the originals (Jinshan has two `km` that should read `m`).

---

## 5. Segments — Form 3

`regions/{region}/segments/{segment_no}.json`

```jsonc
{
  "segment_id": "jinshan.1140901.P002-00",
  "year_period": "1140901", "segment_no": "P002-00",
  "scope_desc": "北側至金包里街以北臨路第一筆宗地…",
  "observations": {
    "far": { "field_name": "容積率", "raw": "240%", "value": 240.0, "unit": "percent",
             "level_rank": 1, "level_count": 5 }
    // … 20 fields
  },
  "facilities": [
    { "label": "電 變電所或高壓", "name": "金山變電所",
      "in_segment": false, "distance_m": 700.0, "is_none": false,
      "criteria_item_code": "utility_facility",   // ← linked to a criteria item
      "mapping_confidence": "high", "needs_review": false },
    { "label": "無高鐵站", "name": null, "distance_m": null, "is_none": true,
      "criteria_item_code": "near_station", ... }    // "none" is a surveyed finding, not a blank
  ],
  "improvements": [...], "land_use_current": "住商混合",
  "completeness": { "observed_fields": 15, "total_fields": 20,
                    "facilities_recorded": 26, "missing_fields": ["sunlight", …] }
}
```

- `level_rank` / `level_count` come from the `[N] [M]` code printed down the left edge of Form 3
  ("level N of M").
- `facilities[].criteria_item_code` is the join point used by review rule R1.
- `label` keeps the raw extracted text including layout noise; use `criteria_item_code` for the
  normalised meaning.

| Segment | Observations | Facilities |
|---|---|---|
| `jinshan P002-00` | 15 / 20 | **26** |
| `shulin P001-00` … `P004-00` | 16 / 20 each | **0** |

> ⚠️ **All four Shulin segments have zero facilities.** In the source `題目.pdf`, every checkbox
> under public facilities, special facilities, environmental pollution and commercial activity is
> unticked (`○`). The case simply does not supply facility distances, so those items cannot be
> graded from the documents alone and must be returned to the surveying authority.
>
> `output/thirdVersion` infers them from open data instead — see [§7](#7-external--open-data)
> for what that is and is not.

---

## 6. Cases — Forms 5 and 4

`regions/{region}/cases/{case_no}.json`

```jsonc
{
  "case_no": "1140901-99-001",
  "table5": {
    "form": "表5-2", "land_use_label": "商業用地",
    "segment_nos": ["P002-00"],
    "rows": [ { "item_code": "far", "item_label": "容積率",
                "levels": [{"rank":1,"label":"優"}, {"rank":1,"label":"優"}],  // [benchmark, comparable 1…]
                "adjustments": [0.0] } ],
    "subtotals": { "order": [[0.0], …] },   // 8 groups, matching main categories (1)–(8)
    "total": [0.0]                          // grand total of regional-factor adjustment
  },
  "table4": {
    "appraisal_date": "1140901",
    "rows": { "unit_price": [...], "date_adj": [...], "adjusted_price": [...], … },
    "lots": ["新北市金山區金美段489地號", "新北市金山區溫泉段218地號"],
    "notes": ["依土地徵收補償市價查估辦法第17條第3項規定…"]
  }
}
```

`table4.rows` keeps both `raw_cells` (original cell text) and `numbers` (extracted values). Form 4
columns vary with the number of comparables, so the column count is not forced into a fixed shape.

> In the Shulin case, `table5.total` is `null` and every row's `adjustments` is empty — **that is
> the part to be answered.** All 29 rows of the structure are preserved.

---

## 7. `external/` — open data

Used only by `output/thirdVersion`, which fills the Shulin facility fields that the source
documents leave blank.

| Path | Content |
|---|---|
| `cache/` | Raw responses from 19 sources — 18 government open-data endpoints listed in `doc/extraInfo/poi-links.md`, plus OpenStreetMap (street geometry and facility features) |
| `poi_inference.json` | Derived results: segment centroids, the nearest facility per Form 3 sub-field, the resulting grade, and a sensitivity check |

`poi_inference.json` shape:

```jsonc
{
  "segments": {
    "P001-00": { "center_twd97": [291932.1, 2764444.5],   // from OSM boundary-street intersections
                 "uncertainty_m": 25.0, "corner_count": 2, "corners": [...] }
  },
  "items": {
    "near_school": {
      "label": "接近學校之程度（國小、國中、高中、大專院校）",
      "max_adjustment": 8.0, "step": 2.0, "direction": "lower_is_better",
      "coverage": { "complete": false, "usable_for_grading": true, "bound": "conservative" },
      "subs": [ { "cell": "I35", "name": "國小", "candidate_count": 11 }, … ],
      "by_segment": { "P001-00": { "rank": 1, "level_label": "優",
                                   "aggregated": { "facility": "市立育林國小",
                                                   "distance_m": 182, "confidence": "A" },
                                   "borderline": false } },
      "adjustments": { "P002-00": 0.0, "P003-00": 0.0, "P004-00": 0.0 }
    }
  }
}
```

Two rules govern how these values may be used:

- **Confidence tiers.** `A` = official register with its own coordinates; `B` = official register
  cross-matched to third-party coordinates by name; `C` = OpenStreetMap only.
- **Coverage direction.** For nuisance facilities (`higher_is_better`, nearer = worse), a missing
  sub-field means the true nearest could be *closer*, i.e. worse — so an incomplete result is only
  an optimistic bound and `usable_for_grading` is set to `false`. For positive facilities the same
  gap makes the result a conservative bound, which is usable.

> These are third-party measurements, not the surveying authority's on-site determination. They
> support field-survey candidate lists, plausibility checks and supplementation requests — they do
> not replace Form 3, and **"cannot find" is never recorded as "none".**

Regenerate with `python3 engine/poi_fetch.py` (about 15 minutes) then `python3 engine/poi_infer.py`.

---

## 8. Case-level rules — `common/case_rules.json`

Two rulings that sit outside the criteria tables, sourced from `doc/rules/extra.md` and confirmed
by the authority.

### CR1 — MRT development zones are valued by their *pre-change* zoning

Shulin's benchmark segment **P001-00** is described as a "捷運開發區 (變更前為第一種住宅區)"
— an MRT development zone, formerly Residential Zone Type 1. Form 3's "current land use" box is
ticked "commercial", but that box only describes present use and **does not drive the zoning
grade**.

Recorded in `segments/P001-00.json` under `valuation_basis`:

```jsonc
{
  "rule_applied": "CR1",
  "zoning_label_in_scope": "捷運開發區",
  "zoning_prior_to_change": "第一種住宅區",
  "zoning_for_valuation": "第一種住宅區",     // ← the value used for grading
  "land_use_current_in_form": "商業用",
  "land_use_current_overridden": true
}
```

**Why it matters.** Shulin's zoning levels read: rank 1 「商業區、捷運用地(聯開)」,
rank 2 「住宅區、市場用地」. Taking "MRT development zone" at face value yields rank 1; the
correct answer is rank 2. The item is 5-level, ±20 %, step 5 % — **one grade apart is 5 %.**

### CR2 — residential zones on lanes ≤ 8 m usually have a 200 % base FAR

Applied as a **cross-check**, not a hard error. Per-segment results live in `rule_checks`:

| Segment | Main road | FAR | CR2 |
|---|---|---|---|
| P001-00 | 八德街 28 m | 260 % | not applicable (> 8 m) |
| **P002-00** | **樹人街 7 m** | **200 %** | **applicable and consistent ✅** |
| P003-00 | 東榮街 10 m | 260 % | not applicable (> 8 m) |
| P004-00 | 潭興街 10 m | 260 % | not applicable (> 8 m) |

P002-00 independently confirms the rule. A mismatch is flagged `severity: warning` with a prompt
to check for incentives or special provisions — it is never failed outright.

---

## 9. SQLite

`db/appraisal.sqlite` — 18 tables.

| Table | Rows | Content |
|---|---:|---|
| `regions` | 2 | District + land use + role |
| `criteria_items` | 96 | All items (indexed on region+factor_type, item_code) |
| `criteria_levels` | 438 | Levels with `min_value`/`max_value` for direct SQL comparison |
| `criteria_matrix` | 2,120 | Flattened adjustment matrices |
| `segments` | 5 | Land value segments |
| `segment_observations` | 100 | Per-field observations |
| `segment_facilities` | 26 | Facility distances + mapped criteria item |
| `segment_valuation_basis` | 1 | CR1 result |
| `segment_rule_checks` | 4 | CR2 results |
| `cases` | 2 | Cases |
| `case_regional_rows` | 58 | Form 5 rows |
| `case_table4_rows` | 61 | Form 4 rows |
| `case_rules` | 2 | CR1 / CR2 definitions |
| `forms` | 16 | Form 1–14 system |
| `review_checklist` | 11 | Official review points i–xi |
| `cross_reference_matrix` | 14 | R1–R14 cross-table checks |
| `legal_articles` | 11 | Cited articles |
| `images` | 74 | Image manifest |

```sql
-- Which level does an area of 250 m² fall into?
SELECT rank, label, criterion FROM criteria_levels
WHERE item_id = 'shulin.individual.area'
  AND min_value <= 250 AND (max_value IS NULL OR 250 < max_value);
--> 3 | 普通 | 200m2以上未滿400m2

-- Adjustment rate: benchmark 普通(3) vs comparable 劣(5)
SELECT adjustment FROM criteria_matrix
WHERE item_id = 'shulin.regional.far' AND base_rank = 3 AND comparable_rank = 5;
--> 12.5

-- Items whose range differs between the two districts (proves "never hard-code")
SELECT a.item_name, a.max_adjustment AS shulin, b.max_adjustment AS jinshan
FROM criteria_items a JOIN criteria_items b
  ON a.item_code = b.item_code AND a.factor_type = b.factor_type
WHERE a.region_code = 'shulin' AND b.region_code = 'jinshan'
  AND a.factor_type = 'regional' AND a.max_adjustment <> b.max_adjustment;

-- Highest-priority automated review checks
SELECT id, src, dst, check_desc FROM cross_reference_matrix ORDER BY priority LIMIT 5;
```

---

## 10. Validation

`python3 datasets/_build/run_tests.py` — all passing.

| # | Test | Result |
|---|---|---|
| 1 | All 96 items: matrix anti-symmetry, zero diagonal, consistent step, no gaps between levels | ✅ |
| 2 | Recompute the 19 individual-factor rates on Jinshan's completed Form 4 | ✅ 19/19, total 13.00 % |
| 3 | Price chain 184,763 × 1.02 × 1.13 = **212,958** (matches the form exactly) | ✅ |
| 4 | Form 3 facility distances → criteria lookup → compare with Form 5's printed grades | ✅ 10/10 |
| 5 | CR1 zoning fallback, CR2 FAR/road-width consistency | ✅ |
| 6 | Database foreign-key integrity, all 74 image files present | ✅ |

Tests 2–4 are **end-to-end back-calculations**: not "did extraction finish", but "does the
extracted data reproduce the authority's own answers, digit for digit".

---

## 11. Images

74 files; manifest in `common/images.json`, mirrored into the `images` table.

| `kind` | Count | Content |
|---|---:|---|
| `page_render` | 44 | 150 DPI JPEG page renders (form layouts, criteria tables, manual figures) |
| `map` | 6 | Segment sketch maps, zoning maps, land value segment maps (Jinshan) |
| `photo` | 24 | Site photographs of the benchmark and comparable parcels (Jinshan) |

Each entry carries `caption` (first line of the page), `tags`, `sha256_16` and `bytes`. Bitmap
extraction filters out the greyscale alpha masks `pdfimages` emits separately, and label fragments
under 150 px.

---

## 12. Known limitations

1. **Shulin facility data is absent from the source** (§5). Verified: `題目.pdf` is 6 pages with
   **zero embedded images** (4 × Form 3 + Form 5-1 + Form 4, all forms), no segment sketch map, and
   no Shulin facility name appears anywhere in the supplied documents. `external/` fills the gap
   from open data for reference, but the original Form 3 still has to be supplemented.
2. `segment_facilities.label` keeps raw layout text including vertical-typesetting noise. Use
   `criteria_item_code` for the normalised meaning. Of the 26 Jinshan facility rows, 24 map at
   `high` confidence; 2 carry `mapping_confidence: "none"` and `needs_review: true`.
3. `題目.pdf`'s Form 5-1 has a 「修正差異數」 row that the Jinshan reference does not. Its
   definition is unclear, so it is not structured; confirm with the authority before adding it.
4. The Shulin Form 5 note states that zoning, building coverage ratio and floor area ratio are
   adjusted **in Form 4's individual factors instead**, to avoid double-counting. This is preserved
   in `cases/*.json` but not encoded as a rule.
5. The 169-page manual is not fully structured — only its workflow diagrams and public-facility
   -reservation-land figures were extracted.

---

## 13. Rebuilding

```bash
datasets/_build/run_all.sh            # needs poppler (pdftotext / pdfimages / pdftoppm) and pyyaml
python3 datasets/_build/run_tests.py  # tests only
```

`run_all.sh` converts the PDFs to text, runs every builder in order, rebuilds the database and
index, then runs both the dataset regression tests and `engine/test_engine.py`.

`external/` is **not** rebuilt by `run_all.sh` — it depends on live network calls. Regenerate it
separately with `engine/poi_fetch.py` and `engine/poi_infer.py`.
