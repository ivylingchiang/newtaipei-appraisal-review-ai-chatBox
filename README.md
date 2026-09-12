# New Taipei City — Land Expropriation Appraisal Review Assistant

An AI-assisted review system for **land expropriation compensation appraisal** under Taiwan's
*土地徵收補償市價查估辦法* (Regulations for Market Price Appraisal of Land Expropriation
Compensation), built for the New Taipei City Land Administration Bureau AI hackathon.

The system reads an appraisal case (Forms 3 / 4 / 5), checks it against the governing manual and
the district-specific valuation criteria tables, and derives the values that can be computed —
flagging everything that cannot, rather than filling it with guesses.

**Working case:** 新北市樹林區 (Shulin District), ordinary residential land, valuation date
1 September 2022 (民國 111 年 9 月 1 日), case no. `1110901-99-XXX`.

---

## 1. Repository layout

```
.
├── doc/          Source documents (PDF / Excel) — the ground truth, never edited
├── datasets/     Structured knowledge base extracted from doc/  (JSON + YAML + SQLite)
├── engine/       Rule engine: review checks, table lookups, form export
├── input/        Blank official Excel templates to be filled
└── output/       Generated deliverables (three successive versions)
```

Everything in `datasets/` is **derived** from `doc/` and is fully reproducible
(`datasets/_build/run_all.sh`). `doc/` is the only hand-authored source of truth.

---

## 2. `doc/` — source documents and what each one is for

The problem statement deliberately supplies **two parallel sample sets**: one fully worked example
and one blank case to solve. Understanding this pairing is the key to the whole repository.

| File | Role | Used for |
|---|---|---|
| `doc/題目.pdf` | **Target case** — Shulin, residential | 4 × Form 3 + Form 5-1 + Form 4, with grades and adjustment rates **left blank** — this is what the system must produce |
| `doc/rules/評價基準明細表.pdf` | **Criteria — Shulin** | Regional (29 items) + individual (20 items) lookup matrices for the target case |
| `doc/rules/查估書表範本.pdf` | **Reference case** — Jinshan, commercial | The same forms **fully completed** by the authority — the only "answer key" available |
| `doc/rules/評價基準明細表範例.pdf` | **Criteria — Jinshan** | Lookup matrices matching the reference case |
| `doc/rules/土地徵收補償市價查估作業手冊.pdf` | Governing manual (MOI, 169 pp.) | Form system, filling rules, official review checklist, rounding rules |
| `doc/rules/extra.md` | Supplementary rules | Two case-specific rulings supplied by the authority |
| `doc/table/表3,4,5*.xlsx` | Official Excel templates | Source of the blank templates copied into `input/` |
| `doc/extraInfo/poi-links.md` | 18 open-data URLs | Facility datasets used to infer Form 3 facility fields (see §6, version 3) |
| `doc/【命題文件】…pdf` | Problem statement | Scope, pain points, expected deliverables |

```
  REFERENCE SET (learn from)              TARGET SET (answer)
  查估書表範本.pdf        ←pairs with→    題目.pdf
  評價基準明細表範例.pdf   ←pairs with→    評價基準明細表.pdf
  Jinshan · commercial                    Shulin · residential
```

> **The thresholds differ between the two districts.** "Excellent" building coverage ratio is
> ≥ 60 % in Jinshan but ≥ 80 % in Shulin; floor area ratio ≥ 240 % vs ≥ 460 %. Criteria must
> always be loaded dynamically by `(region_code, land_use_code)` — never hard-coded.

---

## 3. `datasets/` — the structured knowledge base

Extracted from `doc/`, filed **by district × land-use type**, and published in three formats:
JSON (for programs), YAML (for human review), SQLite (for SQL queries).

```
datasets/
├── index.json                  Global index — read this first
├── db/appraisal.sqlite         18 tables, directly queryable
├── regions/
│   ├── shulin/                 Shulin · residential      role: target
│   │   ├── criteria/
│   │   │   ├── regional.json|yaml     29 regional-factor items
│   │   │   └── individual.json|yaml   20 individual-factor items
│   │   ├── segments/           Form 3 — P001-00 … P004-00 + _index.json
│   │   ├── cases/              Form 5 + Form 4 — 1110901-99-XXX
│   │   └── img/                15 page renders
│   └── jinshan/                Jinshan · commercial      role: reference
│       ├── criteria/           28 + 19 items
│       ├── segments/           P002-00
│       ├── cases/              1140901-99-001
│       └── img/                45 images (renders, maps, site photos)
├── common/                     Cross-district knowledge
│   ├── forms.json|yaml         Form 1–14 system and production workflow
│   ├── formulas.json|yaml      Calculation rules, rounding, weighting
│   ├── review_rules.json|yaml  Official review checklist + cross-table reference matrix
│   ├── case_rules.json|yaml    Case-specific rulings (from extra.md)
│   ├── legal_references.json|yaml
│   ├── images.json             Manifest for all 74 extracted images
│   └── img/                    14 images (workflow diagrams, legends)
├── external/                   Open data for facility inference (version 3 only)
│   ├── cache/                  Raw API responses, 19 sources
│   └── poi_inference.json      Derived segment centroids, nearest facilities, grades
└── _build/                     Reproducible build scripts
```

### 3.1 Document → dataset mapping

| Source document | Build script | Output |
|---|---|---|
| `評價基準明細表.pdf`, `評價基準明細表範例.pdf` | `build_criteria.py` | `regions/*/criteria/{regional,individual}.json\|yaml` |
| `題目.pdf` (Form 3 pages), `查估書表範本.pdf` | `build_segments.py` | `regions/*/segments/*.json`, `segments.yaml` |
| `題目.pdf` (Forms 4 & 5), `查估書表範本.pdf` | `build_cases.py` | `regions/*/cases/*.json\|yaml` |
| `土地徵收補償市價查估作業手冊.pdf`, `extra.md` | `build_common.py` | `common/{forms,formulas,review_rules,case_rules,legal_references}` |
| All PDFs (embedded bitmaps + page renders) | `build_images.py` | `*/img/`, `common/images.json` |
| All of the above JSON | `build_db.py` | `db/appraisal.sqlite` (18 tables) |
| All of the above | `build_index.py` | `index.json` |
| `doc/extraInfo/poi-links.md` + OpenStreetMap | `engine/poi_fetch.py`, `engine/poi_infer.py` | `external/cache/`, `external/poi_inference.json` |

### 3.2 Shape of a criteria item

Every item in `criteria/regional.json` carries its level thresholds **and** the full
reciprocal adjustment matrix, so grading and rate lookup need no interpretation at runtime:

```jsonc
{
  "item_id": "shulin.regional.near_school",
  "group_code": 5,                    // (5) 公共建設 Public facilities
  "item_name": "接近學校之程度（國小、國中、高中、大專院校）",
  "level_count": 5,
  "max_adjustment": 8.0,              // ±8 %
  "step": 2.0,                        // one grade apart = 2 %
  "direction": "lower_is_better",     // vs "higher_is_better" for nuisance facilities
  "levels": [
    { "rank": 1, "label": "優",
      "criterion": "區段內有學校者或距離未滿300m",
      "threshold": { "kind": "numeric", "unit": "m",
                     "ranges": [{ "max": 300.0, "max_inclusive": false }],
                     "in_segment": true, "or_none": false } }
    // … ranks 2–5
  ],
  "matrix": [[0, 2, 4, 6, 8], [-2, 0, 2, 4, 6], …]   // anti-symmetric, zero diagonal
}
```

Adjustment rate is then simply `matrix[benchmark_rank - 1][comparable_rank - 1]`.

### 3.3 Rebuilding

```bash
datasets/_build/run_all.sh          # PDF → text → parse → JSON/YAML → SQLite → index → tests
```

Requires `pdftotext -layout` (poppler). The script ends by running both the dataset regression
tests and the engine tests.

---

## 4. `engine/` — rule engine

Reads `datasets/` and runs two modes simultaneously: **review** existing content and **derive**
what is computable.

| Module | Purpose |
|---|---|
| `loader.py` | Dataset loading layer |
| `grading.py` | Fact → grade → adjustment-rate lookup |
| `compute.py` | Derive Form 5 grades and adjustment percentages from Form 3 observations |
| `checks.py` | Cross-table consistency rules R1–R14, mapped to the manual's review checklist |
| `review.py`, `cli.py` | Review pipeline and CLI |
| `export.py` | Version 1 — analysis output (CSV / Markdown / JSON) |
| `export_xlsx.py` | Version 2 — write results back into the `input/` templates |
| `poi_fetch.py`, `poi_infer.py` | Version 3 — fetch open data, locate segments, infer facility fields |
| `export_v3.py` | Version 3 — Form 3 with facility fields filled from inferred data |
| `preview_html.py`, `export_artifact_html.py` | HTML previews of the filled workbooks |
| `test_engine.py` | Positive (official example must produce zero errors) + negative (injected errors must be caught) |

```bash
python3 engine/cli.py shulin          # review one district
python3 engine/cli.py shulin --json   # machine-readable
python3 engine/test_engine.py
```

Exit code is 1 when any `error`-level finding exists, so it can be wired into CI directly.

---

## 5. `input/` — blank templates

The three official Excel templates, copied unmodified from `doc/table/`:

| File | Sheet filled by |
|---|---|
| `表3地價區段勘查表.xlsx` | Form 3 — Land Value Segment Survey |
| `表4比較法調查估價表.xlsx` | Form 4 — Comparison Approach Appraisal |
| `表5影響地價區域因素分析明細表(住宅用地).xlsx` | Form 5-1 — Regional Factor Analysis |

Layout, merged cells and print settings are preserved; the exporters write into these files so the
deliverable is visually identical to the authority's own form.

---

## 6. `output/` — three successive versions

All three describe the *same* case and share the same grading logic. They differ in output format
and in how much of Form 3 is populated.

| | `firstVersion/` | `secondVersion/` | `thirdVersion/` |
|---|---|---|---|
| Format | CSV + Markdown + JSON | **Excel** (filled templates) | **Excel** (filled templates) |
| Content | Analysis results | Same results written back into the forms | Same, **plus** Form 3 facility fields inferred from open data |
| Form 3 facility fields | Left blank | Left blank | **Filled** — 13 items × 4 segments |
| Form 5 subtotals available | 4 of 8 | 4 of 8 | **6 of 8** |
| Form 5 grand total | Not produced | Not produced | Not produced |
| Produced by | `engine/export.py` | `engine/export_xlsx.py` | `engine/export_v3.py` |

Each version has its own `README.md` with the full reasoning; the third one also documents the
limits of the inferred values. Every filled cell in the Excel outputs carries three layers of
provenance: a **fill colour** for data quality, a **cell comment** with the rule applied, and a row
in the workbook's `填表依據` (basis) sheet.

| Fill | Meaning |
|---|---|
| Green | Transcribed from `doc/題目.pdf` |
| Yellow | Derived by table lookup against the criteria — no estimation |
| Orange | Inferred from segment level to parcel level |
| Blue / Purple (v3) | Inferred from open data — official register / OpenStreetMap only |
| Amber (v3) | Coverage insufficient — value shown but not used for grading |
| Red | Required but no data available — left blank and listed for supplementation |
| Grey | Not applicable to this land-use type |

### Why the grand total is never produced

Form 5's grand total is the sum of eight group subtotals. Groups (6) special facilities and
(7) environmental pollution cannot be completed from the available data, and together they carry
up to ±55 % of adjustment — more than the ±26 % that *is* computable. Summing an incomplete set
would be misleading, so the system reports the gap instead of estimating it.

The governing principle throughout: **"cannot find" never means "none".** For positive facilities
a blank means the worst grade; for nuisance facilities it means the best. Either way it moves
money, so unknown fields stay blank and are listed for field survey.

---

## 7. Conventions

- **Never hard-code thresholds.** Load by `(region_code, land_use_code)`; the two districts differ
  on almost every item.
- **`doc/` is read-only.** Everything downstream is regenerated, never hand-patched.
- **Every derived number is traceable** to a source line in Form 3 and a threshold string in the
  criteria table, via the basis sheets and `填表依據明細.csv`.
- **Validation baseline:** all extraction and grading logic is verified by back-calculating the
  fully completed Jinshan reference case — 13/13 regional facility items and 19/19 individual
  factors reproduce the authority's own figures.

---

## 8. Notes

- `datasets/external/cache/` holds ~17 MB of raw open-data API responses. They are kept in the
  repository so the third version can be reproduced offline; `engine/poi_fetch.py` refetches them
  from scratch if deleted.
- Third-party open data (including OpenStreetMap) is used for cross-checking and for generating
  field-survey candidate lists. It is **not** a substitute for the surveying authority's on-site
  determination, which is what gives Form 3 its legal standing.
