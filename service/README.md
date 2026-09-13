# `service/` — 產出 HTTP 服務

把 `output/` 的產出用 HTTP 對外提供，讓**外部程式碼**可以直接接進來取用
`output/fieldMapping/index.html`（地價查估書表審查對照總覽）。

該檔是完全自包含的單一 HTML（約 670 KB，沒有任何外部 CSS／JS／圖片），
所以服務端只要把它送出去，對方就能完整呈現。

純 Python 標準庫，**不需要安裝任何套件**。

---

## 1. 啟動

```bash
# 本機直接跑
python3 service/server.py                 # 預設 0.0.0.0:8000
python3 service/server.py --port 9000
python3 service/server.py --host 127.0.0.1   # 只給本機連
```

```bash
# Docker（build context 必須是專案根目錄）
docker build -f service/Dockerfile -t ntpc-appraisal-output .
docker run --rm -p 8000:8000 ntpc-appraisal-output

# 或用 compose；它會把本機 output/ 以唯讀掛進去，
# 重新產生報表後不必重建映像，重整頁面就是新的
docker compose -f service/docker-compose.yml up -d
```

環境變數 `HOST` / `PORT` 與 `--host` / `--port` 等效，容器內以 `PORT` 調整較方便。

---

## 2. 路由

| 方法 | 路徑 | 回應 |
|---|---|---|
| GET / HEAD | `/` | 欄位對照總覽 HTML |
| GET / HEAD | `/index.html`、`/fieldMapping/`、`/fieldMapping/index.html` | 同上（同一份檔案的別名） |
| GET / HEAD | `/output/` | `output/` 目錄索引（可用瀏覽器往下翻） |
| GET / HEAD | `/output/<路徑>` | `output/` 底下的檔案：各版本 `.html` `.xlsx` `.csv` `.md` |
| OPTIONS | 任意 | CORS preflight，`204` |

`output/` 以外的路徑一律 `404`；含 `..` 的路徑會被正規化後擋在 `output/` 內，不會讀到專案其他檔案。

---

## 3. 外部程式怎麼接

**內嵌到別的頁面**（回應不送 `X-Frame-Options`，可直接 iframe）：

```html
<iframe src="http://localhost:8000/" style="width:100%;height:900px;border:0"></iframe>
```

**用 JS 取回內容**（回應帶 `Access-Control-Allow-Origin: *`，跨網域 fetch 不會被擋）：

```js
const html = await fetch("http://localhost:8000/fieldMapping/index.html").then(r => r.text());
```

**Python**：

```python
import urllib.request
html = urllib.request.urlopen("http://localhost:8000/").read().decode("utf-8")
```

**curl**：

```bash
curl -o 對照總覽.html http://localhost:8000/
curl -s http://localhost:8000/output/ | grep href     # 看有哪些版本
```

---

## 4. 回應行為

- **CORS**：所有回應都帶 `Access-Control-Allow-Origin: *`，允許 `GET, HEAD, OPTIONS`。
- **編碼**：`text/*` 與 JSON 一律補 `charset=utf-8`，中文不會亂碼。
- **gzip**：請求帶 `Accept-Encoding: gzip` 時自動壓縮，對照總覽 687 KB → 約 80 KB。
- **快取**：帶 `Last-Modified` 與 `Cache-Control: no-cache`；外部程式帶
  `If-Modified-Since` 就會收到 `304`，報表重新產生後才會重送完整內容。
- **並行**：`ThreadingHTTPServer`，多個用戶端同時抓沒問題。

---

## 5. 注意

- 服務是**唯讀**的，只送檔案，沒有任何寫入或執行路徑。
- 預設監聽 `0.0.0.0`，同網段的機器都連得到；只想給本機用請加 `--host 127.0.0.1`。
- 沒有內建 TLS 與存取控制。要對外公開請放在 nginx／Caddy 之類的反向代理後面處理憑證與權限。
- 服務不會自己產生報表。`output/fieldMapping/index.html` 由
  `engine/export_field_map.py` 產生，服務只負責送出目前磁碟上的那一份。
