# New Taipei City — Land Expropriation Appraisal Review Assistant

An AI-assisted review system for **land expropriation compensation appraisal** under Taiwan's
*土地徵收補償市價查估辦法*, built for the New Taipei City Land Administration Bureau AI hackathon
(命題：AI 輔助不動產估價案件審查).

The system reads an appraisal case (Forms 3 / 4 / 5), checks it against the governing manual and
the district-specific valuation criteria tables, derives every value that can be computed — and
flags everything that cannot, rather than filling it with a guess.

**Working case:** 新北市樹林區 (Shulin District), ordinary residential land, valuation date
1 September 2022 (民國 111 年 9 月 1 日), case no. `1110901-99-XXX`.
Benchmark parcel `P001-00`; comparables `P002-00`, `P003-00`, `P004-00`.

This project is developed as our team's proposal for the 2026 New Taipei City Government Hackathon. For the full system concept, workflow, problem definition, and proposed solution, please refer to our team's proposal presentation: [`Team UCLab.pdf`](output/Team UCLab.pdf).

| | |
|---|---|
| **Deliverables** | 3 filled official workbooks + 3 black-and-white PDFs + an interactive field-provenance map |
| **Validation** | Back-calculates the authority's own completed case: 13/13 facility items, 19/19 individual factors |
| **Engine tests** | Reference case → 0 errors; 7 injected errors → 7 caught (`engine/test_engine.py`) |
| **Coverage** | Form 5: 25 of 29 items graded, 6 of 8 group subtotals, grand total delivered in `finalVersion` |
| **Deployed** | Read-only HTTP service on AWS ECS Fargate (`service/deploy-aws.sh`) |

---

## Table of contents

1. [The brief and what was built for it](#1-the-brief-and-what-was-built-for-it)
2. [Architecture](#2-architecture)
3. [Repository layout](#3-repository-layout)
4. [Results](#4-results)
5. [Reproducing everything](#5-reproducing-everything)
6. [Serving the output — local, Docker, AWS](#6-serving-the-output--local-docker-aws)
7. [AWS credentials and deployment](#7-aws-credentials-and-deployment)
8. [Known limits](#8-known-limits)
9. [Follow-up work](#9-follow-up-work)
10. [Conventions](#10-conventions)

---

## 1. The brief and what was built for it

The problem statement (`doc/【命題文件】…pdf`) names three pain points. Each one is answered by a
specific part of this repository — and the mapping is the fastest way to read the project:

| Pain point (from the brief) | What answers it | Where |
|---|---|---|
| **1. Too many forms to cross-check by hand; omissions are easy.** Reviewers manually compare Form 3 (地價區段勘查表), Form 5 (影響地價區域因素分析明細表) and Form 4 (比較法調查估價表) item by item. | A rule engine that runs the manual's own review checklist as code — 14 cross-table rules (R1–R14) plus the price chain, each finding carrying its severity and the manual clause behind it. | [`engine/checks.py`](engine/checks.py), [`engine/README.md`](engine/README.md) |
| **2. Grades depend on a per-district, per-land-use criteria table; human consistency is hard to hold.** | The criteria tables are extracted into structured data keyed by `(region_code, land_use_code)`, each item carrying its level thresholds *and* the full reciprocal adjustment matrix. Grading is a lookup, not a judgement call. | [`datasets/regions/*/criteria/`](datasets/), [`engine/grading.py`](engine/grading.py) |
| **3. Adjustment-rate sums and cross-form transcription (e.g. the regional total) go wrong.** | Every subtotal, grand total and cross-form copy is recomputed and compared; the total that Form 4 must carry is derived from Form 5 rather than transcribed. | [`engine/compute.py`](engine/compute.py), rules R4 / R14 / R7 |

The brief's expected outcomes map just as directly:

- *「透過 AI 輔助完成估價書填寫流程」* → `output/finalVersion/` — the three official forms filled
  and rendered as PDFs, every cell traceable to its source.
- *「降低人工審查時間與錯誤率」* → `engine/cli.py` returns exit code 1 on any `error`-level finding,
  so it drops straight into CI or a pre-submission gate.
- *「作為估價審查數位化的基礎應用案例」* → `datasets/` is a reusable knowledge base (JSON + YAML +
  SQLite), and `service/` publishes the result over HTTP for other systems to consume.

### The design decision that shapes everything

**"Cannot find" never means "none."** For a positive facility (school, market, park) a blank means
the worst grade; for a nuisance facility (crematorium, incinerator) it means the best. Either way it
moves compensation money. So unknown sub-fields stay blank — never filled with 「無」 — and are
listed for field survey. Where a value *is* inferred, the inference and its confidence travel with
it all the way to the cell comment.

---

## 2. Architecture

```
doc/                    datasets/                engine/                  output/            service/
─────────────           ─────────────            ─────────────            ─────────────      ─────────────
題目.pdf         ┐                      ┌ loader.py                ┌ firstVersion    CSV/MD/JSON
查估書表範本.pdf  │  _build/*.py         │ grading.py   judge        │ secondVersion   xlsx
評價基準明細表    ├─────────────────────>│ compute.py   derive       ├ thirdVersion    xlsx + POI
作業手冊 (169pp) │  PDF → text →        │ checks.py    R1–R14  ────>│ fourthVersion   xlsx           HTTP
extra.md        │  parse → JSON/YAML   │ review.py    report        ├ finalVersion    xlsx + PDF ──> server.py
表3/4/5 .xlsx    ┘  → SQLite → index    └ export_*.py  write         └ fieldMapping    single HTML     ECS
                                                                                                    Fargate
poi-links.md ──> poi_fetch.py ──> external/cache/ ──> poi_infer.py ──> external/poi_inference.json
(18 open datasets + OpenStreetMap)                    segment centroids · nearest facility · grade
```

Four properties hold across the whole pipeline:

- **`doc/` is read-only.** It is the only hand-authored source of truth. Everything downstream is
  regenerated, never hand-patched.
- **`datasets/` is fully derived** and rebuilt by one script (`datasets/_build/run_all.sh`).
- **Nothing is hard-coded per district.** Shulin and Jinshan disagree on almost every threshold
  ("excellent" building coverage is ≥ 60 % in Jinshan, ≥ 80 % in Shulin), so criteria are always
  loaded by `(region_code, land_use_code)`.
- **Every derived number is traceable** to a source line in Form 3 and a threshold string in the
  criteria table — through the workbook's 填表依據 sheet, the cell comment, and the field map.

### The two parallel sample sets

The problem statement deliberately ships one worked example and one blank case. Understanding the
pairing is the key to the whole repository:

```
  REFERENCE SET (learn and validate from)   TARGET SET (answer)
  查估書表範本.pdf          ←pairs with→    題目.pdf
  評價基準明細表範例.pdf     ←pairs with→    評價基準明細表.pdf
  Jinshan · commercial                      Shulin · residential
```

The reference set is the only answer key available, so it is used as a **regression fixture**: the
engine must reproduce the authority's own figures on Jinshan before any Shulin output is trusted.

---

## 3. Repository layout

```
.
├── doc/          Source documents (PDF / Excel) — ground truth, never edited
├── dev/          Domain research notes written before implementation (see dev/README.md)
├── datasets/     Structured knowledge base derived from doc/ (JSON + YAML + SQLite)
├── engine/       Rule engine: review checks, table lookups, form export, PDF rendering
├── input/        Blank official Excel templates to be filled
├── output/       Deliverables: finalVersion/ + fieldMapping/ + log/ (versions 1–4) + the submission deck
├── service/      Read-only HTTP service + Docker + AWS deployment
└── requirements.txt
```

| Directory | Read its own README | What is in it |
|---|---|---|
| `doc/` | — | 題目.pdf (target case), 查估書表範本.pdf (completed reference), two criteria tables, the 169-page MOI manual, `extra.md` case rulings, blank Excel templates, 18 open-data URLs |
| [`dev/`](dev/README.md) | [`dev/README.md`](dev/README.md) | Five research notes (~2,900 lines): form system and filling order, facility-field rules, open-data audit with every API actually called, per-cell API mapping |
| [`datasets/`](datasets/README.md) | [`datasets/README.md`](datasets/README.md) | `index.json`, `regions/{shulin,jinshan}/{criteria,segments,cases,img}`, `common/` (forms, formulas, review rules, case rules, legal refs, 74 images), `external/` (19 cached sources, POI inference), `db/appraisal.sqlite` (18 tables), `_build/` |
| [`engine/`](engine/README.md) | [`engine/README.md`](engine/README.md) | 18 modules — see the table below |
| `input/` | — | The three official templates copied unmodified from `doc/table/`; exporters write into these so the deliverable is visually identical to the authority's own form |
| [`output/`](output/finalVersion/README.md) | one README per version | `finalVersion/` (the hand-over set), `fieldMapping/` (the field map), `log/` (versions 1–4, the development record), `Team UCLab.pdf` (submission deck) — see §4 |
| [`service/`](service/README.md) | [`service/README.md`](service/README.md) | `server.py` (stdlib-only HTTP), `patch_xlsx.py` (apply reviewer corrections), `Dockerfile`, `docker-compose.yml`, `deploy-aws.sh` |

### Engine modules

| Module | Purpose |
|---|---|
| `loader.py` | Dataset loading layer (criteria, segments, cases, common rules) |
| `grading.py` | Fact → grade → adjustment-rate lookup (`grade` / `adjust`) |
| `compute.py` | Derive Form 5 grades and percentages from Form 3 observations; Form 4 individual factors |
| `checks.py` | Cross-table rules R1–R14, case rules CR1/CR2, price-chain recomputation |
| `review.py`, `cli.py` | Review pipeline, report formatting, CLI |
| `export.py` | Version 1 — analysis output (CSV / Markdown / JSON) |
| `export_xlsx.py` | Version 2 — write results back into the `input/` templates |
| `poi_fetch.py`, `poi_infer.py` | Fetch 18 open datasets + OSM; locate segment centroids; infer facility fields |
| `export_v3.py` | Version 3 — Form 3 facility fields filled from inferred data |
| `export_v4.py` | Version 4 — Form 4 individual factors 13–21 |
| `export_final.py` | Deliverable — Forms 3/4/5 filled and worded the way the Jinshan reference is |
| `export_pdf.py` | Renders a filled workbook to black-and-white PDF (no Excel or LibreOffice needed) |
| `preview_html.py`, `export_artifact_html.py` | HTML previews of the filled workbooks |
| `export_field_map.py`, `field_map_template.html` | The field-provenance map (`output/fieldMapping/index.html`) |
| `test_engine.py` | Positive + negative regression tests |

---

## 4. Results

### 4.1 Validation against the authority's own case

All extraction and grading logic is verified by back-calculating the fully completed Jinshan
reference case — the only answer key that exists.

| Check | Result |
|---|---|
| Facility-type regional items regraded from the reference Form 3 | **13 / 13** match the authority's grades |
| Individual-factor rates recomputed on the reference Form 4 | **19 / 19** match, total 13.00 % |
| Review engine run on the completed reference case | **0 errors** (1 warning: 2 labels in Form 3 that do not map, not a data gap) |
| 7 deliberately injected errors (wrong rate, wrong total, wrong weight, wrong price …) | **7 / 7 caught**, each by its intended rule |

A watchdog that never barks is worthless, so the negative tests matter as much as the positive one.
Every form reads the matrix the same way — `(comparable_rank − base_rank) × step`, comparable graded
worse gives a positive adjustment — and the tests pin that direction against the five non-zero items
of the completed Jinshan Form 4, so it cannot be silently flipped later. (Form 5 was briefly split
onto the opposite direction; the reviewing authority confirmed that reading was mistaken and the
single direction is restored. The reference Form 5 cannot arbitrate it: all of its adjustments are
0.00, so both directions fit.)

### 4.2 What the system produced for the target case

| | `log/firstVersion` | `log/secondVersion` | `log/thirdVersion` | `log/fourthVersion` | `finalVersion` |
|---|---|---|---|---|---|
| Format | CSV + MD + JSON | Excel | Excel | Excel | **Excel + PDF** |
| Form 3 facility fields | blank | blank | **filled** (13 items × 4 segments) | filled | filled |
| Form 5 items graded | 15 / 29 | 15 / 29 | **25 / 29** | 25 / 29 | **29 / 29** |
| Form 5 group subtotals | 4 / 8 | 4 / 8 | **6 / 8** | 6 / 8 | **8 / 8** |
| Form 5 grand total | — | — | — | — | **+23.75 / +13.75 / +17.75 %** |
| Form 4 individual factors 13–21 | — | — | — | **filled** | filled |
| Form 4 regional adjustment row | — | — | — | — | **filled** |
| Produced by | `export.py` | `export_xlsx.py` | `export_v3.py` | `export_v4.py` | `export_final.py` |

Versions 1–4 are the development record and live under [`output/log/`](output/log/); the hand-over
set is [`output/finalVersion/`](output/finalVersion/README.md) and the field map is
[`output/fieldMapping/`](output/fieldMapping/). Each version keeps its own README explaining what it
added and what it still could not determine.

The step from 15 to 25 graded items is the open-data work: the four price segments were located by
intersecting their boundary-street names (recorded only as prose in the source forms) against
OpenStreetMap street geometry, giving centroids with an uncertainty radius of **±25 to ±65.5 m** —
comfortably inside the innermost grading thresholds of 200–300 m. Of the 52 resulting grades
(13 items × 4 segments), **8 fall within one uncertainty radius of a threshold** and are marked
borderline for human review.

### 4.3 The grand total, and who decides to produce it

Form 5's grand total is the sum of eight group subtotals. Groups (6) 特殊設施 and (7) 環境污染 have
sub-fields with no locatable open data at all — funeral parlour, crematorium, landfill, and four of
the five pollution columns. The nearest facility that *can* be found is therefore only an optimistic
bound: the real nearest one can only be closer, i.e. worse. Versions 1–4 leave those two groups, and
the grand total, blank and report the gap.

`finalVersion` grades them from the nearest facility on record — exactly the way the Jinshan
reference case is filled — **at the reviewing authority's instruction**. That makes all eight
subtotals, the grand total (+23.75 % / +13.75 % / +17.75 %) and with it Form 4's regional adjustment
row available. The bound stays what it is: the limitation is recorded in
[`output/finalVersion/README.md §2`](output/finalVersion/README.md) and in every affected cell's
basis row, and those two groups head the field-survey list.

### 4.4 Provenance built into the deliverable

Every filled cell in the Excel outputs carries three layers of provenance: a **fill colour** for
data quality, a **cell comment** with the rule applied, and a row in the workbook's 填表依據 sheet
(584 rows for Form 3, 220 for Form 4, 356 for Form 5).

| Fill | Meaning |
|---|---|
| Green | Transcribed from `doc/題目.pdf` |
| Yellow | Derived by table lookup against the criteria — no estimation |
| Orange (segment) | Inferred from segment level to parcel level |
| Blue / Purple | Inferred from open data — official register (A/B) / OpenStreetMap only (C) |
| Amber | Coverage insufficient — value shown but not used for grading |
| Red | Required but no data available — left blank and listed for supplementation |
| Grey | Not applicable to this land-use type |

`finalVersion` drops the colours (the official form is black and white); the reasoning survives
intact in the comments and the basis sheets.

### 4.5 The field map

[`output/fieldMapping/index.html`](output/fieldMapping/index.html) is a single self-contained HTML
file (~790 KB, no external CSS/JS/images) answering a different question from the four versions:
not *what is the number* but *where must this cell come from*. Seven tabs: Form 3, Form 4, Form 5,
the complete rendered forms, the missing-data register, the open-data sources, and the formulas and
review rules. Every field is clickable, showing the cross-form references, the formula, the criteria
thresholds and full N×N matrix, the current data status and confidence, and the manual clause.

The 完整書表 tab is **editable**: 1,212 cells (of 11,062) can be corrected by a human reviewer, and
the toolbar exports the corrections three ways — a CSV correction list, a JSON payload, and a
corrected workbook produced server-side by `POST /export/xlsx`. The page stores nothing; reloading
returns the AI output. Downstream cells affected by an edit are struck orange rather than silently
recomputed, because the workbooks hold static derived values, not Excel formulas — see
[`service/README.md §6`](service/README.md).

---

## 5. Reproducing everything

### 5.1 Prerequisites

```bash
python3 --version                 # 3.10 or newer
python3 -m pip install -r requirements.txt
brew install poppler              # pdftotext / pdfimages / pdftoppm  (Linux: apt install poppler-utils)
```

`engine/cli.py` itself needs only PyYAML. `openpyxl` is needed to write workbooks, `matplotlib` +
`Pillow` to render PDFs, and poppler only to rebuild `datasets/` from the PDFs.

### 5.2 Rebuild the knowledge base from `doc/`

```bash
datasets/_build/run_all.sh        # PDF → text → parse → JSON/YAML → SQLite → index → tests
```

Six stages, ending with the dataset regression tests and the engine tests. Text extraction goes to
`/tmp/_appraisal_txt` by default; pass a directory to override.

### 5.3 Run the review engine

```bash
python3 engine/cli.py                  # both districts
python3 engine/cli.py shulin           # the target case
python3 engine/cli.py jinshan          # the reference case — must report 0 errors
python3 engine/cli.py shulin --json    # machine-readable
python3 engine/test_engine.py          # positive + negative tests
```

Exit code is 1 when any `error`-level finding exists, 0 otherwise.

### 5.4 Regenerate the deliverables

```bash
# versions 1 and 2 — analysis, then the same results written back into input/
python3 engine/export.py
python3 engine/export_xlsx.py

# version 3 — open data (poi_fetch takes ~15 min and hits 19 endpoints; the cache is committed,
# so skip it unless you want fresh data)
python3 engine/poi_fetch.py
python3 engine/poi_infer.py
python3 engine/export_v3.py
PREVIEW_VERSION=thirdVersion python3 engine/preview_html.py    # reads output/log/thirdVersion

# version 4 — Form 4 individual factors 13–21
python3 engine/export_v4.py
PREVIEW_VERSION=fourthVersion python3 engine/preview_html.py

# deliverable — three workbooks and three PDFs, worded like the Jinshan reference
python3 engine/export_final.py

# the field map
python3 engine/export_field_map.py
```

Versions 1–4 write into `output/log/<version>/`; `export_final.py` and `export_field_map.py` write
to `output/finalVersion/` and `output/fieldMapping/`. All of them are deterministic — rerunning
overwrites in place.

Any filled workbook can be rendered on its own:

```bash
python3 engine/export_pdf.py <xlsx> [<pdf>]
```

### 5.5 Verify what you rebuilt

```bash
python3 datasets/_build/run_tests.py   # dataset regression
python3 engine/test_engine.py          # engine, both directions of the lookup
python3 engine/cli.py jinshan          # the reference case must still come out clean
```

---

## 6. Serving the output — local, Docker, AWS

`service/server.py` is a stdlib-only, read-only HTTP server that publishes `output/` so other
programs can consume it. No dependencies to install (only `POST /export/xlsx` needs `openpyxl`; if
it is missing that one endpoint returns 503 and everything else keeps working).

```bash
python3 service/server.py                             # http://localhost:8000/
python3 service/server.py --port 9000 --host 127.0.0.1
docker compose -f service/docker-compose.yml up -d    # mounts ./output read-only
```

| Method | Route | Serves |
|---|---|---|
| GET / HEAD | `/`, `/index.html`, `/fieldMapping/index.html` | the field map |
| GET / HEAD | `/output/`, `/output/<path>` | directory index and every generated file |
| POST | `/export/xlsx` | apply a reviewer's corrections, return a zip (in memory; nothing is written to disk) |
| OPTIONS | any | CORS preflight |

Responses carry `Access-Control-Allow-Origin: *` and no `X-Frame-Options`, so external code can
`fetch()` the page cross-origin or embed it in an `<iframe>`. gzip (793 KB → ~98 KB),
`Last-Modified`/`304` and UTF-8 charset are handled; paths outside `output/` are refused. Full
client snippets in [`service/README.md`](service/README.md).

---

## 7. AWS credentials and deployment

The service runs on **ECS Fargate** in AWS account `242971039848`, region `us-west-2`, from an image
in ECR. The image bakes `output/` in (unlike the local compose file, which mounts it), so
regenerating the reports means rebuilding and pushing the image.

| Resource | Value |
|---|---|
| ECR image | `242971039848.dkr.ecr.us-west-2.amazonaws.com/ntpc-appraisal-output:latest` |
| ECS cluster / service | `ntpc-appraisal` / `ntpc-appraisal-output` |
| Task | Fargate **ARM64**, 0.25 vCPU / 0.5 GB, container port 8000 |
| Security group | `sg-09f19d9b31bdf84f7` — inbound TCP 8000 |
| CloudWatch logs | `/ecs/ntpc-appraisal-output`, 7-day retention |

### 7.1 Credentials

**No credential ever belongs in this repository.** `.gitignore` excludes `.env*`, `.aws/`, `*.pem`
and anything matching `*credentials*`; the deploy script reads whatever the AWS CLI resolves and
hard-codes only the account id, region and resource names, which are not secrets.

**How this project is set up today:** the credentials are exported from the developer's `~/.zshrc`
as environment variables — `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` and
`AWS_DEFAULT_REGION=us-west-2`. Two consequences worth knowing before you debug a failed deploy:

- **They are temporary.** The session token belongs to the event role
  `arn:aws:sts::242971039848:assumed-role/WSParticipantRole/Participant`; when it expires every
  `aws` call fails with an auth error until the new values are pasted into `~/.zshrc`.
- **`~/.zshrc` is read by interactive shells only.** A deploy launched from CI, cron, or a
  non-interactive tool runner inherits nothing and fails at the first `aws` call. Export the
  variables in that environment, or run the script from an interactive terminal.

`~/.zshrc` holds a live secret and lives outside this repository — never copy it in, and rotate the
key if it ever leaks.

Any of the standard credential sources works equally well:

```bash
# a) IAM Identity Center / SSO — preferred for a long-lived account
aws configure sso            # or: aws login   (AWS CLI v2.36+)
aws sso login --profile ntpc

# b) IAM user access key — long-lived, rotate it and never commit it
aws configure --profile ntpc # AWS Access Key ID / Secret / region us-west-2 / json

# c) environment variables — what this project uses (see above); expire with the session
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_SESSION_TOKEN=...
export AWS_DEFAULT_REGION=us-west-2

# confirm — must print account 242971039848
aws sts get-caller-identity
```

If you use a named profile, export it before running the deploy script:
`export AWS_PROFILE=ntpc`. The AWS CLI is expected on `PATH`; the script also looks in
`~/.local/bin`, where the macOS installer puts it, and checks the credentials before it starts
building so an expired session fails in a second rather than after a multi-minute image build.

**Minimum IAM permissions** for the update path:

| Service | Actions |
|---|---|
| ECR | `ecr:GetAuthorizationToken`, `BatchCheckLayerAvailability`, `InitiateLayerUpload`, `UploadLayerPart`, `CompleteLayerUpload`, `PutImage`, `BatchGetImage` |
| ECS | `ecs:UpdateService`, `DescribeServices`, `ListTasks`, `DescribeTasks` |
| EC2 | `ec2:DescribeNetworkInterfaces` (only to print the new public IP) |

Creating the stack from scratch additionally needs `ecr:CreateRepository`,
`ecs:CreateCluster`/`RegisterTaskDefinition`/`CreateService`, `logs:CreateLogGroup`,
`ec2:CreateSecurityGroup`/`AuthorizeSecurityGroupIngress`, and `iam:PassRole` for the task execution
role (`ecsTaskExecutionRole`, AWS-managed policy `AmazonECSTaskExecutionRolePolicy`).

### 7.2 Deploying an update

```bash
./service/deploy-aws.sh
```

Build (`linux/arm64`, matching Fargate and Apple Silicon) → push to ECR → `ecs update-service
--force-new-deployment` → wait for `services-stable` → print the new URL. Takes a few minutes,
most of it the wait for the old task to drain.

### 7.3 First-time bootstrap

Already done for this account; these are the steps if you are standing it up elsewhere.

```bash
REGION=us-west-2; ACCOUNT=$(aws sts get-caller-identity --query Account --output text)

aws ecr create-repository --repository-name ntpc-appraisal-output --region $REGION
aws ecs create-cluster --cluster-name ntpc-appraisal --region $REGION
aws logs create-log-group --log-group-name /ecs/ntpc-appraisal-output --region $REGION
aws logs put-retention-policy --log-group-name /ecs/ntpc-appraisal-output --retention-in-days 7 --region $REGION
```

Then create a security group allowing inbound TCP 8000, register a Fargate task definition
(ARM64, 256 CPU / 512 MB, `awslogs` driver pointed at that log group, execution role
`ecsTaskExecutionRole`), and create the service with `--launch-type FARGATE`,
`--desired-count 1` and `assignPublicIp=ENABLED` on a public subnet. After that,
`deploy-aws.sh` handles every subsequent update.

### 7.4 Operating notes

- **The public IP changes whenever the task is replaced.** Fargate tasks have no stable IP;
  `deploy-aws.sh` prints the current one at the end. A fixed hostname needs an ALB or CloudFront,
  which this read-only report service does not currently have.
- **Plain HTTP, no TLS, no access control.** Anyone who knows the IP can read everything under
  `output/`. Restrict the security group's ingress CIDR, or put it behind a reverse proxy that
  terminates TLS, before treating it as public.
- **The image carries `output/`.** Regenerate the reports → rerun `deploy-aws.sh`, or the deployed
  copy stays stale.
- Logs: `aws logs tail /ecs/ntpc-appraisal-output --follow --region us-west-2`.

---

## 8. Known limits

These are properties of the data available, not of the implementation, and each is recorded in the
deliverable itself as well as here.

| Limit | Effect | What would resolve it |
|---|---|---|
| **No price-segment boundary geometry.** The official segment polygons are not published; centroids are approximated by intersecting boundary-street names against OSM. | ±25–65.5 m uncertainty; 8 of 52 grades borderline; the 「本區段內／外」 checkbox cannot be decided from a centroid. | The Bureau's 地價區段界線 SHP — the single highest-leverage missing item. |
| **Nuisance-facility registers are incomplete.** Funeral parlour, crematorium, landfill and 4 of 5 pollution columns have no locatable open data. | Groups (6) and (7) can only be an optimistic bound; `finalVersion` grades them anyway on instruction, so the grand total inherits that bound. | Field survey, or the competent authority's own registers. |
| **Distances are straight-line from the segment centroid.** The manual prefers route distance for facilities that must be reached on foot. | Systematically over-optimistic for positive facilities (schools, markets, parks); correct for nuisance facilities and for the interchange, where the criteria table specifies straight-line. | A routing service, or field measurement. |
| **No parcel-level cadastral geometry.** Form 4's individual factors 7–11 (area, width, depth, shape, frontage) cannot be computed. | Those five rows stay blank, and with them Form 4's total, weights and trial price. | Form 7 (宗地個別因素清冊) or a cadastral WFS feed. |
| **Form 4 items 13–21 are segment-level values applied to parcels.** | Parcels in the same segment get identical values; they are not parcel-specific. | Field survey or Form 7. |
| **Form 6's sign convention is unsettled.** The authority's rule (benchmark better → positive) applies to every form; the official Form 6 template's own sample data runs the other way, consistently across 9 items and 5 parcels. | Nothing here depends on it — Form 6 is not implemented, since Form 7 was never supplied — but it must be settled before it is. | Confirmation from the reviewing authority. Recorded in `formulas.json` under `price_chain_table6.open_issue` with every sample row. |
| **Inferred values are not survey records.** Form 3 is a statutory survey record whose authority comes from the surveying officer's on-site determination. | Open-data inference is valid as a pre-survey candidate list, a plausibility cross-check and a basis for requesting supplementation — never as a submitted survey result. | Unchanged by any amount of better data. |

---

## 9. Follow-up work

Ordered by leverage, with the reason each one is worth doing next.

1. **Obtain the 地價區段界線 SHP from the Bureau.** Replaces approximate centroids with real
   polygons, settles the in-segment/out-of-segment checkbox, and clears the borderline flags in one
   step. Every other geometry-dependent limitation collapses into this one.
2. **Ingest Form 7 (宗地個別因素清冊) or a cadastral geometry feed.** Unblocks Form 4's individual
   factors 7–11, and with them the total, the weights (R7), the trial price and the benchmark
   comparison price — i.e. the rest of the price chain the engine already knows how to check.
3. **Field-survey the nuisance facilities first.** Groups (6) and (7) carry the largest adjustment
   ranges (±15 %, ±20 %) and the worst data coverage; confirming them converts today's optimistic
   bound into a defensible grade.
4. **Close the human-correction loop.** The field map already exports corrections as JSON; feeding
   them back into `datasets/` and re-running the engine would make review a round trip instead of a
   one-way export, and would give the project a labelled disagreement set over time.
5. **Extend to the downstream forms.** [`dev/02`](dev/02-下游表單模擬.md) simulates Form 14 and
   Form 6 from a completed Form 4, deliberately outside `engine/` because Form 7 was not supplied.
   With item 2 done, it becomes implementable rather than illustrative.
6. **Route distance instead of straight-line** for facilities the manual says must be reachable,
   removing the known systematic bias toward over-optimistic grades.
7. **Generalise beyond these two districts.** Nothing is hard-coded per district, but only two
   criteria tables have been parsed. Adding districts is a parser exercise plus a new regression
   fixture — the reference-case validation pattern is already in place.
8. **Harden the service if it is to stay public**: a stable hostname (ALB/CloudFront), TLS, and
   access control. It is currently plain HTTP on a changing IP, which is fine for a demo and not
   fine for anything else.

---

## 10. Conventions

- **Never hard-code thresholds.** Load by `(region_code, land_use_code)`; the two districts differ
  on almost every item.
- **`doc/` is read-only.** Everything downstream is regenerated, never hand-patched.
- **Report missing data as `blocked`, not `error`.** Treating "not filled in" as "filled in wrong"
  is the fastest way to lose a reviewer's trust in the tool.
- **One lookup direction for every form.** The authority's rule is that a benchmark better than its
  counterpart yields a positive rate, so Forms 5, 4 and 6 all read the anti-symmetric matrix as
  `(counterpart − base) × step` through a single `adjust()`. Calibrate any doubt about the sign
  against the completed Jinshan Form 4, the only filled evidence that constrains it. Form 6 carries
  an open question — the official template's sample data runs the other way; see
  [§8](#8-known-limits).
- **Every derived number is traceable** to a Form 3 line and a criteria threshold, via the basis
  sheets and the field map.
- Third-party open data (including OpenStreetMap) is used for cross-checking and for generating
  field-survey candidate lists. It is **not** a substitute for the surveying authority's on-site
  determination, which is what gives Form 3 its legal standing.
- `datasets/external/cache/` holds ~17 MB of raw API responses, committed so version 3 reproduces
  offline; `engine/poi_fetch.py` refetches them from scratch if deleted.
