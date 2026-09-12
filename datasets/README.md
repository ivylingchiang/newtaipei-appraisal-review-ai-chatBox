# datasets — 土地徵收補償市價查估審查知識庫

由 `doc/` 內的 PDF／Excel 抽取結構化而成，**依行政區 + 用地別分類歸檔**，
同時提供 JSON（程式取用）、YAML（人工閱讀／審閱）、SQLite（SQL 檢索）三種形式。

> 全部資料以 `doc/rules/查估書表範本.pdf`（金山區已填完整範例）反算驗證通過，
> 詳見 [§6 驗證](#6-驗證)。重建與測試：`datasets/_build/run_all.sh`

---

## 1. 目錄結構

```
datasets/
├── index.json                    # 全域索引（先讀這個）
├── README.md
├── db/
│   └── appraisal.sqlite          # 15 張表，可直接 SQL 查詢
├── regions/
│   ├── shulin/                   # 新北市樹林區．普通住宅用地　【target = 待作答】
│   │   ├── criteria/
│   │   │   ├── regional.json|yaml     # 區域因素評價基準明細表（29 細項）
│   │   │   └── individual.json|yaml   # 個別因素評價基準明細表（20 細項）
│   │   ├── segments/             # 表3 地價區段勘查表
│   │   │   ├── _index.json
│   │   │   ├── P001-00.json … P004-00.json
│   │   │   └── segments.yaml
│   │   ├── cases/                # 表5 + 表4
│   │   │   └── 1110901-99-XXX.json|yaml
│   │   └── img/                  # 15 張頁面渲染
│   └── jinshan/                  # 新北市金山區．商業用地　【reference = 已填範例】
│       ├── criteria/             # 28 + 19 細項
│       ├── segments/P002-00.json
│       ├── cases/1140901-99-001.json|yaml
│       └── img/                  # 45 張（15 頁面 + 6 地圖 + 24 現況照片）
├── common/                       # 跨區域共用知識
│   ├── forms.json|yaml           # 表1~表14 體系與製作流程
│   ├── formulas.json|yaml        # 計算規則、尾數、權重、填表慣例
│   ├── review_rules.json|yaml    # 官方審查檢核清單 + 跨表參照矩陣
│   ├── legal_references.json|yaml
│   ├── images.json               # 全部 74 張圖像的 manifest
│   └── img/                      # 14 張（作業手冊流程圖、公保地圖例、命題文件）
└── _build/                       # 可重現的建置腳本
    ├── run_all.sh                # 一鍵重建 + 測試
    ├── parse_criteria.py  threshold.py  catalog.py
    ├── build_criteria.py  build_segments.py  build_cases.py
    ├── build_common.py    build_images.py    build_db.py  build_index.py
    └── run_tests.py              # 回歸測試
```

### 為什麼分成 shulin / jinshan 兩區

兩區是**刻意配對的樣本**，不是兩批無關資料：

| | `jinshan`（reference） | `shulin`（target） |
|---|---|---|
| 用地別 | 商業用地 | 普通住宅用地 |
| 來源 | `查估書表範本.pdf` + `評價基準明細表範例.pdf` | `題目.pdf` + `評價基準明細表.pdf` |
| 狀態 | **全部填妥**，含優劣等級與修正率 | **優劣等級與修正率留白**（AI 要算的） |
| 用途 | 學習填法、驗證演算法 | 實際作答對象 |

**級距與修正率兩區完全不同**，例如建蔽率「優」在金山是 60% 以上、樹林是 80% 以上。
系統必須以 `(region_code, land_use_code)` 動態載入，**不可寫死**。

---

## 2. 核心資料：評價基準明細表

`regions/{region}/criteria/{regional|individual}.json`

每個細項（item）的結構：

```jsonc
{
  "item_id": "shulin.regional.far",      // 主鍵
  "region_code": "shulin",
  "factor_type": "regional",             // regional | individual
  "seq": 4,
  "group_code": 1, "group_name": "土地使用管制",
  "item_code": "far", "item_name": "容積率",
  "field_no": null,                      // 個別因素才有（表4 的 7~25）
  "level_count": 5,
  "level_labels": ["優","稍優","普通","稍劣","劣"],
  "max_adjustment": 25.0,                // 最大影響範圍 ±25%
  "step": 6.25,                          // = max_adjustment / (level_count-1)
  "rule_type": "matrix",                 // matrix | narrative
  "direction": "higher_is_better",
  "levels": [
    { "rank": 1, "label": "優", "criterion": "460%以上",
      "threshold": { "kind": "numeric", "unit": "percent",
                     "ranges": [{ "min": 460.0, "min_inclusive": true }],
                     "in_segment": false, "or_none": false, "raw": "460%以上" } },
    …
  ],
  "matrix": [[0, 6.25, 12.5, 18.75, 25], …]   // 反對稱方陣
}
```

### 查表方式（兩種等價）

```python
# 方式 A：直接查矩陣
adj = item["matrix"][base_rank - 1][comparable_rank - 1]

# 方式 B：等差公式
adj = (comparable_rank - base_rank) * item["step"]
```

**符號約定：比較標的條件較差 → 修正率為正。**

### `threshold` 可機器比對

`kind` 為 `numeric` 時：

| 欄位 | 意義 |
|---|---|
| `ranges[]` | `{min, max, min_inclusive, max_inclusive}`，可多段（如深度「7~14m 或 40~50m」） |
| `unit` | `m` / `m2` / `percent` / `degree` |
| `in_segment` | 「區段內有」即屬此級 |
| `or_none` | 「或無」即屬此級（嫌惡設施常見） |

`kind` 為 `categorical` 時用 `categories[]`（如 `["方形","梯形"]`）。

判級輔助函式：`_build/threshold.py` 的 `match_level(value, levels, in_segment, is_none)`。

### 特例

- `shulin.individual.far`（樹林個別因素容積率）`rule_type = "narrative"`，**無矩陣**——
  原表載明「以土地開發分析法試算調整；須與區域因素容積率併同考量」。
- `jinshan` 個別因素**有**容積率矩陣（±40）。兩區處理方式不同。
- `source_anomalies` 欄位記錄原文誤植（金山有 2 處單位 `km` 應為 `m`）。

---

## 3. 表3 地價區段勘查表

`regions/{region}/segments/{segment_no}.json`

```jsonc
{
  "segment_id": "jinshan.1140901.P002-00",
  "year_period": "1140901", "segment_no": "P002-00",
  "scope_desc": "北側至金包里街以北臨路第一筆宗地…",
  "observations": {
    "far": { "field_name": "容積率", "raw": "240%", "value": 240.0, "unit": "percent",
             "level_rank": 1, "level_count": 5 },
    …
  },
  "facilities": [
    { "label": "電 變電所或高壓", "name": "金山變電所",
      "in_segment": false, "distance_m": 700.0,
      "criteria_item_code": "utility_facility",     // ← 已對應到基準表細項
      "mapping_confidence": "high", "needs_review": false }
  ],
  "improvements": [...], "land_use_current": "住商混合",
  "completeness": { "observed_fields": 14, "total_fields": 18, "facilities_recorded": 12,
                    "missing_fields": ["sunlight","view","slope","land_improve"] }
}
```

- `level_rank`/`level_count` 來自原表左側的 `[N] [M]` 編碼（第 N 級／共 M 級）。
- `facilities[].criteria_item_code` 將現場設施連到基準表細項，是 R1 檢查的接點。
- `label` 保留原始擷取文字（含版面雜訊），標準化結果看 `criteria_item_code`。

樹林 4 個區段各有 17/18 欄觀測值（缺風勢或土質，原表即空白）；金山 P002-00 有 14/18 欄
但含 12 筆設施距離。

> ⚠️ **樹林 4 個區段的 `facilities` 皆為空**——原始 `題目.pdf` 的表3 中，
> 公共建設／特殊設施／環境污染／工商活動所有勾選框都是未勾選（`○`）狀態。
> 亦即該案**沒有提供設施距離資料**，這些細項無法計算，須向承辦單位補件。
> 可計算的只有：土地使用管制、主要道路/平均路寬/道路闢建、自然條件、土地改良。

---

## 4. 案件（表5 + 表4）

`regions/{region}/cases/{case_no}.json`

```jsonc
{
  "case_no": "1140901-99-001",
  "table5": {
    "form": "表5-2", "land_use_label": "商業用地",
    "segment_nos": ["P002-00"],
    "rows": [ { "item_code": "far", "item_label": "容積率",
                "levels": [{"rank":1,"label":"優"}, {"rank":1,"label":"優"}],  // [比準地, 比較標的1…]
                "adjustments": [0.0] } ],
    "subtotals": { "order": [[0.0], …] },   // 8 組，對應主要項目 (1)~(8)
    "total": [0.0]                          // 影響地價區域因素總修正數
  },
  "table4": {
    "appraisal_date": "1140901",
    "rows": { "unit_price": [...], "date_adj": [...], "adjusted_price": [...], … },
    "lots": ["新北市金山區金美段489地號", "新北市金山區溫泉段218地號"],
    "notes": ["依土地徵收補償市價查估辦法第17條第3項規定…"]
  }
}
```

`table4.rows` 保留 `raw_cells`（原始欄位文字）與 `numbers`（抽出的數值），
因表4 欄位隨比較標的數量變動，未強制正規化欄位數。

> 樹林案 `table5.total` 為 `null`、各列 `adjustments` 為空——**這正是待作答的部分**。
> 表5 共 29 列結構已保留完整。

---

## 5. SQLite 資料庫

`db/appraisal.sqlite`（18 張表）

| 資料表 | 列數 | 說明 |
|---|---|---|
| `regions` | 2 | 行政區 + 用地別 + role |
| `criteria_items` | 96 | 全部細項（索引：region+factor_type、item_code） |
| `criteria_levels` | 438 | 各級距，含 `min_value`/`max_value` 可直接 SQL 比對 |
| `criteria_matrix` | 2,120 | 攤平的修正率矩陣 |
| `segments` | 5 | 地價區段 |
| `segment_observations` | 90 | 區段逐欄觀測值 |
| `segment_facilities` | 12 | 設施距離 + 對應細項 |
| `cases` | 2 | 案件 |
| `case_regional_rows` | 58 | 表5 逐列 |
| `case_table4_rows` | 61 | 表4 逐列 |
| `images` | 74 | 圖像 manifest |
| `forms` | 16 | 表1~表14 |
| `review_checklist` | 11 | 官方審查重點 i~xi |
| `cross_reference_matrix` | 14 | R1~R14 跨表檢查 |
| `legal_articles` | 11 | 法條 |
| `case_rules` | 2 | 案件層級判定規則 CR1/CR2 |
| `segment_valuation_basis` | 1 | CR1 套用結果（分區回溯） |
| `segment_rule_checks` | 4 | CR2 逐區段檢核結果 |

### 常用查詢

```sql
-- 某面積屬於哪一級
SELECT rank, label, criterion FROM criteria_levels
WHERE item_id = 'shulin.individual.area'
  AND min_value <= 250 AND (max_value IS NULL OR 250 < max_value);
--> 3 | 普通 | 200m2以上未滿400m2

-- 查修正率：比準地普通(3) vs 比較標的劣(5)
SELECT adjustment FROM criteria_matrix
WHERE item_id='shulin.regional.far' AND base_rank=3 AND comparable_rank=5;
--> 12.5

-- 兩區同名細項的最大影響範圍差異（驗證「不可寫死」）
SELECT a.item_name, a.max_adjustment AS 樹林, b.max_adjustment AS 金山
FROM criteria_items a JOIN criteria_items b
  ON a.item_code=b.item_code AND a.factor_type=b.factor_type
WHERE a.region_code='shulin' AND b.region_code='jinshan'
  AND a.factor_type='regional' AND a.max_adjustment <> b.max_adjustment;

-- 應優先實作的自動化審查項目
SELECT id, src, dst, check_desc FROM cross_reference_matrix ORDER BY priority LIMIT 5;

-- 地圖類圖像
SELECT image_id, path, caption FROM images WHERE kind='map';
```

---

## 5.5 案件層級判定規則（`common/case_rules.json`）

基準明細表之外，另有兩條**案件層級**規則，來源為 `doc/rules/extra.md` 與承辦單位確認。

### CR1 — 捷運開發區以「變更前」使用分區認定

> extra.md 第1條：捷運開發地要用變身分之前的土地規格為準則（一般住宅規格）
> 承辦單位確認：本案 P001-00 以**第一種住宅區**判斷

樹林比準地區段 **P001-00** 的區段範圍載明「捷運開發區**(變更前為第一種住宅區)**」。
表3『土地利用現況』欄勾選「商業用」，但該欄僅為現況描述，**不作為使用分區優劣判定依據**。

已寫入 `segments/P001-00.json` 的 `valuation_basis`：

```jsonc
{
  "rule_applied": "CR1",
  "zoning_label_in_scope": "捷運開發區",
  "zoning_prior_to_change": "第一種住宅區",
  "zoning_for_valuation": "第一種住宅區",     // ← 估價judgment 採此值
  "land_use_current_in_form": "商業用",
  "land_use_current_overridden": true
}
```

**為什麼這條規則有實質影響**：樹林住宅用地區域因素「使用分區」的級距為

| rank | label | criterion |
|---|---|---|
| 1 | 優 | 商業區、**捷運用地(聯開)** |
| 2 | 稍優 | **住宅區**、市場用地 |

若誤以「捷運開發區」查表會得 rank 1（優），正確應為 rank 2（稍優）。
該細項 5 級、最大 ±20%、step 5%，**一級之差即造成 5% 的使用分區修正率偏差**。

### CR2 — 8公尺以下道路旁住宅區之基準容積率 200%

> extra.md 第2條：都市計畫中，未特別獎勵或一般巷道（8公尺寬以下道路）旁之住宅區，基準容積率常規劃為 200%

作為**交叉檢核**（非硬性判錯）。逐區段結果存於 `rule_checks`：

| 區段 | 主要道路 | 容積率 | CR2 |
|---|---|---|---|
| P001-00 | 八德街 28m | 260% | 不適用（>8m） |
| **P002-00** | **樹人街 7m** | **200%** | **適用且相符 ✅** |
| P003-00 | 東榮街 10m | 260% | 不適用（>8m） |
| P004-00 | 潭興街 10m | 260% | 不適用（>8m） |

P002-00 獨立驗證了這條規則：7m 巷道旁住宅區，容積率正好是 200%。
不符者標記 `severity: warning`，提示「請確認是否另有獎勵或特殊規定」，不逕行判錯。

---

## 6. 驗證

`python3 datasets/_build/run_tests.py` — 全部通過。

| 測試 | 內容 | 結果 |
|---|---|---|
| 1 | 96 個細項的矩陣反對稱性、對角線為 0、步長一致、級距定義無缺漏 | ✅ |
| 2 | 用資料集重算金山範本表4 的 19 項個別因素差異率 | ✅ 19/19，合計 13.00% |
| 3 | 價格鏈 184,763 × 1.02 × 1.13 = **212,958**（與表上完全一致） | ✅ |
| 4 | 表3 設施距離 → 基準表判級 → 比對表5 已填等級 | ✅ 10/10 |
| 5 | CR1 分區回溯、CR2 容積率與路寬相容性 | ✅ |
| 6 | 資料庫外鍵完整性、74 個圖檔存在性 | ✅ |

測試 2~4 是**端到端反算**：不是檢查抽取有沒有跑完，而是用抽出的資料
重新推導出官方範本上的答案，逐位吻合。

---

## 7. 圖像（img）

74 張，manifest 在 `common/images.json`，亦同步至 `images` 資料表。

| kind | 數量 | 說明 |
|---|---|---|
| `page_render` | 44 | 150 DPI JPEG 頁面渲染（表單版面、基準表原貌、作業手冊圖例） |
| `map` | 6 | 地價區段略圖／使用分區圖／地價區段圖（金山，1838×914 等） |
| `photo` | 24 | 比準地與比較標的現況照片（金山） |

每筆含 `caption`（取自該頁首行）、`tags`（如 `表3`、`地價區段略圖`）、`sha256_16`、`bytes`。
點陣圖抽取時已濾除 pdfimages 另存的灰階 alpha 遮罩與 <150px 的文字標籤小圖。

---

## 8. 已知限制

1. **樹林案設施資料缺漏**（見 §3 警告）——來源文件本身未填，非抽取失敗。
   已查證：`題目.pdf` 共 6 頁、**零張嵌入影像**（4×表3 + 表5-1 + 表4，全為表單），
   無地價區段略圖，全部文件中亦查無任何樹林在地設施名稱。
   公開資料可補的部分見下表，但**屬我方量測，非承辦單位原始認定**，
   審查上仍應退補原始表3：

   | 需要的資料 | 公開來源 | 可得性 |
   |---|---|---|
   | 學校／車站／政府機關座標 | [新北市重要地標資訊](https://data.gov.tw/dataset/123027)（CSV，TWD97 座標，每日更新） | ✅ 可直接下載 |
   | 土地使用分區圖 | [新北市城鄉資訊查詢平台](https://urban.planning.ntpc.gov.tw/) | ✅ 圖資可查 |
   | 地價區段圖 | [新北市不動產愛連網 / 地政局](https://www.land.ntpc.gov.tw/cp.aspx?n=12877) | ⚠ 可線上查閱，無批次下載 |
   | **地價區段勘查表（表3）本身** | — | ❌ **未公開**，僅內部作業文件 |
   | 公園／市場／嫌惡設施座標 | [新北市資料開放平臺](https://data.ntpc.gov.tw/datasets) | ◐ 分散於多資料集，需逐項比對 |
2. **`segment_facilities.label`** 保留原始版面文字，含直排雜訊；
   標準化結果請用 `criteria_item_code`（目前 12/12 皆為 `high` 信度）。
3. **`題目.pdf` 表5-1 有「修正差異數」一列**，金山範本無此列，定義未明，
   未納入結構化；建議向承辦單位確認後再補。
4. **樹林案表5 備註載明**「使用分區、建蔽率、容積率修正併同於比較法調查估價表
   宗地個別因素考量調整修正」——這 3 項**不在表5 重複修正**，屬案件層級例外，
   已保留於 `cases/*.json` 但未編碼為規則。
5. 作業手冊僅抽取流程圖與公保地圖例頁，未全文結構化（169 頁）。
6. ~~P001-00 捷運開發區未編碼~~ → **已於 §5.5 編碼為 CR1**，並加入回歸測試。

---

## 9. 重建

```bash
datasets/_build/run_all.sh            # 需 poppler(pdftotext/pdfimages/pdftoppm) 與 pyyaml
python3 datasets/_build/run_tests.py  # 僅跑測試
```

領域背景與填表順序說明見 [dev/01-文件體系與審查填表指南.md](../dev/01-文件體系與審查填表指南.md)。
