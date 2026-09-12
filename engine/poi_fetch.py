#!/usr/bin/env python3
"""抓取並快取 doc/extraInfo/poi-links.md 所列開放資料 + OSM 補充圖資。

輸出：datasets/external/cache/*.json
各來源之信心等級說明見 output/thirdVersion/README.md §3。
"""
import json, os, sys, urllib.request, urllib.parse, csv, io, math, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "datasets", "external", "cache")
os.makedirs(CACHE, exist_ok=True)

UA = {"User-Agent": "ntpc-appraisal-review/1.0 (open-data ingest)"}


def _get(url, data=None, timeout=120):
    req = urllib.request.Request(url, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def ntpc(ds_id, page_size=10000, max_pages=10):
    """新北市資料開放平台 JSON API，自動分頁至回傳 0 筆為止。"""
    rows = []
    for p in range(max_pages):
        url = f"https://data.ntpc.gov.tw/api/datasets/{ds_id}/json?page={p}&size={page_size}"
        d = json.loads(_get(url))
        if isinstance(d, dict):
            d = d.get("data", [])
        if not d:
            break
        rows += d
        if len(d) < page_size:      # 該資料集頁上限低於 page_size
            if p == 0 and len(d) in (1000,):
                page_size = len(d)  # 頁上限 1000 型，續抓
                continue
            break
    return rows


def csv_rows(url, enc="utf-8-sig", delim=","):
    raw = _get(url)
    for e in (enc, "big5", "cp950", "utf-8"):
        try:
            txt = raw.decode(e)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError(f"decode failed: {url}")
    return list(csv.DictReader(io.StringIO(txt), delimiter=delim))


def overpass(query):
    return json.loads(_get("https://overpass-api.de/api/interpreter",
                           data=query.encode("utf-8"), timeout=180))


NTPC_SETS = {
    "landmark":   "6dcff24a-838c-40fb-a9df-f1160afafe84",   # 重要地標 (A)
    "busstop":    "34b402a8-53d9-483d-9406-24a682c2d6dc",   # 公車站位 (A)
    "parking":    "b1464ef0-9c7c-4a6f-abf7-6bdf32847e68",   # 路外停車場 (A)
    "park":       "5fe3a136-29cc-4695-a17e-6636a32c3342",   # 公園 (B)
    "riverpark":  "c3867812-6188-4b0a-a487-03bb4d93238d",   # 河濱公園 (B)
    "tourism":    "b3a30a19-4b89-4da2-8d99-18200dc5dfde",   # 觀光景點 (B)
    "market":     "785be91a-caaf-4e1c-91d6-f7d616d31a45",   # 公有市場超市 (C)
    "cemetery":   "1d228eab-23d4-41a6-bd33-f4014dd44660",   # 公立公墓納骨塔 (B)
    "incinerator":"39e17852-9ac9-45b7-bc60-d8d0ed7e3161",   # 垃圾焚化廠 (B)
    "hotel":      "8565597e-a174-4907-99c7-adb5ddee1326",   # 合法旅館 (C)
    "funeralbiz": "77676118-d894-4527-b88a-6d236a462923",   # 禮儀業者 (D, 不判級)
}

CSV_SETS = {
    "soil":       ("https://data.ntpc.gov.tw/api/datasets/9987dc63-2c8d-4c75-903d-6ebd82d1792d/csv/file", "utf-8-sig", ","),
    "air":        ("https://data.ntpc.gov.tw/api/datasets/0f0967bd-3c42-4fd4-80ac-786509c315f3/csv/file", "utf-8-sig", ","),
    "funeral_moi":("https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
                   "CFF7163A-8C96-417E-B93D-156461404881/resource/"
                   "0B675274-AA5F-4163-8C9A-16604BC53A2E/download", "utf-8-sig", "\t"),
    "substation": ("https://service.taipower.com.tw/data/opendata/apply/file/d077002/001.csv", "utf-8-sig", ","),
    "bank":       ("https://stat.fsc.gov.tw/api/v1/public/datasets/6041/export", "utf-8-sig", ","),
}

FREEWAY_META = "https://data.gov.tw/api/v2/rest/dataset/166496"

# 區段界街 + 設施類 OSM 查詢
OSM_STREETS = """
[out:json][timeout:120];
area["name"="樹林區"]->.a;
(way(area.a)["highway"]["name"];);
out geom;
"""

OSM_POI = """
[out:json][timeout:180];
area["name"="樹林區"]->.a;
(
 nwr(area.a)["leisure"="park"];
 nwr(area.a)["amenity"="marketplace"];
 nwr(area.a)["shop"~"^(supermarket|mall|department_store)$"];
 nwr(area.a)["amenity"~"^(bank|post_office|hospital|clinic|crematorium|funeral_hall|grave_yard)$"];
 nwr(area.a)["landuse"~"^(cemetery|landfill)$"];
 nwr(area.a)["man_made"~"^(wastewater_plant|storage_tank|gasometer)$"];
 nwr(area.a)["power"~"^(substation|tower|plant)$"];
 nwr(area.a)["name"~"焚化"];
);
out center tags;
"""


def save(name, obj):
    p = os.path.join(CACHE, name + ".json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    print(f"  {name:14s} {len(obj):6d} 筆  -> {os.path.relpath(p, ROOT)}")


def main():
    print("新北市開放平台：")
    for k, v in NTPC_SETS.items():
        save(k, ntpc(v))
    print("全國/部會轉出檔：")
    for k, (u, e, d) in CSV_SETS.items():
        save(k, csv_rows(u, e, d))
    print("高速公路交流道（11 條國道合併）：")
    meta = json.loads(_get(FREEWAY_META))["result"]
    ic = []
    for dist in meta.get("distribution", []):
        u = dist.get("resourceDownloadUrl")
        if not u or not u.endswith(".csv"):
            continue
        for r in csv_rows(u, "big5"):
            r["_國道"] = dist.get("resourceDescription", "")
            ic.append(r)
    save("interchange", ic)
    print("OSM Overpass：")
    save("osm_streets", overpass(OSM_STREETS)["elements"])
    save("osm_poi", overpass(OSM_POI)["elements"])
    print("\n完成。")


if __name__ == "__main__":
    main()
