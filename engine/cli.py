# -*- coding: utf-8 -*-
import sys, os, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from loader import Dataset
from review import review_case, format_report


def main():
    ap = argparse.ArgumentParser(description="不動產估價案件審查引擎")
    ap.add_argument("region", nargs="?", help="區域代碼（省略則全部）")
    ap.add_argument("--case", help="案號")
    ap.add_argument("--json", action="store_true", help="輸出 JSON")
    ap.add_argument("--no-derive", action="store_true", help="不顯示表5 推導")
    a = ap.parse_args()
    ds = Dataset()
    regions = [a.region] if a.region else ds.regions()
    results = [review_case(ds, r, a.case) for r in regions]
    if a.json:
        print(json.dumps([{**r, "findings": [f.to_dict() for f in r["findings"]]}
                          for r in results], ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(format_report(r, show_derived=not a.no_derive)); print()
    errs = sum(1 for r in results for f in r["findings"] if f.severity == "error")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
