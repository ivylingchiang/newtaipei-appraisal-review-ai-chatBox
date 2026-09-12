#!/usr/bin/env bash
# 由 doc/ 重建整個資料集。需先以 pdftotext -layout 產生文字檔至 $TXTDIR
set -euo pipefail
cd "$(dirname "$0")/../.."
TXTDIR="${1:-/tmp/_appraisal_txt}"
mkdir -p "$TXTDIR"
echo "▸ 1/6 PDF → 文字"
for f in "doc/題目.pdf" "doc/rules/評價基準明細表.pdf" "doc/rules/查估書表範本.pdf" \
         "doc/rules/評價基準明細表範例.pdf" "doc/rules/土地徵收補償市價查估作業手冊.pdf"; do
  pdftotext -layout "$f" "$TXTDIR/$(basename "${f%.pdf}").txt"
done
echo "▸ 2/6 評價基準明細表"; python3 datasets/_build/build_criteria.py "$TXTDIR"
echo "▸ 3/6 地價區段勘查表"; python3 datasets/_build/build_segments.py "$TXTDIR"
echo "▸ 4/6 案件（表4/表5）"; python3 datasets/_build/build_cases.py "$TXTDIR"
echo "▸ 5/6 共用規則 + 圖像"; python3 datasets/_build/build_common.py; python3 datasets/_build/build_images.py
echo "▸ 6/6 資料庫 + 索引";  python3 datasets/_build/build_db.py; python3 datasets/_build/build_index.py
echo "▸ 資料集回歸測試";      python3 datasets/_build/run_tests.py
echo "▸ 引擎測試";            python3 engine/test_engine.py
