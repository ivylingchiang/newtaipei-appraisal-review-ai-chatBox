# `service/` — 產出 HTTP 服務

把 `output/` 的產出用 HTTP 對外提供，讓**外部程式碼**可以直接接進來取用
`output/fieldMapping/index.html`（地價查估書表審查對照總覽）。

該檔是完全自包含的單一 HTML（約 790 KB，沒有任何外部 CSS／JS／圖片），
所以服務端只要把它送出去，對方就能完整呈現。

送檔案的部分是純 Python 標準庫，不需要安裝任何套件；只有「把人工審查修正
套回 xlsx」的 `POST /export/xlsx` 需要 `openpyxl`，沒裝的話該端點回 `503`，
其餘功能照常。

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
| POST | `/export/xlsx` | 收人工審查修正清單，回傳套用後的書表 zip（見 §6） |
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
- **gzip**：請求帶 `Accept-Encoding: gzip` 時自動壓縮，對照總覽 793 KB → 約 98 KB。
- **快取**：帶 `Last-Modified` 與 `Cache-Control: no-cache`；外部程式帶
  `If-Modified-Since` 就會收到 `304`，報表重新產生後才會重送完整內容。
- **並行**：`ThreadingHTTPServer`，多個用戶端同時抓沒問題。

---

## 5. 注意

- 除了 `POST /export/xlsx`，服務都是唯讀的，只送檔案。該端點本身也**不寫磁碟**：
  它讀原始 xlsx、在記憶體套用修正、回傳 zip，不會改動 `output/` 底下任何檔案，
  所以一個人的修正不會影響其他人看到的內容。
- 預設監聽 `0.0.0.0`，同網段的機器都連得到；只想給本機用請加 `--host 127.0.0.1`。
- 沒有內建 TLS 與存取控制。要對外公開請放在 nginx／Caddy 之類的反向代理後面處理憑證與權限。
- 服務不會自己產生報表。`output/fieldMapping/index.html` 由
  `engine/export_field_map.py` 產生，服務只負責送出目前磁碟上的那一份。

---

## 6. 人工審查編輯（完整書表分頁）

對照總覽的「完整書表」分頁可以直接改儲存格，供人工審查更正 AI 判定錯誤。

**可以改哪些格**：有底色的格（題目原載／AI判定／推定／資料不足／外部推算／
覆蓋不足／代理判準）共 1,212 格。灰色「不適用」與表格框線、標題不開放。
點一下會整格選起來，打字即取代；Enter 結束、Shift+Enter 換行、Esc 取消該格。

**頁面不保存任何修改**。重新整理就回到 AI 產出的原狀，離開前瀏覽器會攔一次。
這是刻意的：服務沒有帳號也沒有存取控制，不適合存放審查中的狀態。改完請用
工具列的三個下載擇一帶走。

| 下載 | 內容 |
|---|---|
| 修正清單 CSV | 書表／工作表／儲存格／AI原值／更正為／修正理由，給工程端回頭修 engine |
| JSON | 同上，機器可讀（`edits[]`），格式即 `POST /export/xlsx` 的請求本體 |
| 修正後書表 | zip：套用修正的 xlsx ＋ 修正清單 CSV／JSON ＋ 說明.txt |

**修正後書表**由 `POST /export/xlsx` 產生：服務端開原始 xlsx、套用修正、回傳，
全程在記憶體裡。更正過的格會加**粗紅外框**與儲存格註解（保留 AI 原值與修正
理由，原本的填表依據註解仍在），每份 xlsx 另附「人工審查更正」工作表列出全部
更正。在瀏覽器端自己組 xlsx 會丟掉底色、合併儲存格與註解，所以走服務端。

### 小計與總計不會自動重算

三份 xlsx 共 11,062 格幾乎全是 `engine/compute.py` 推導後寫入的**靜態值**，
不是 Excel 公式（全部只有 1 個公式），改了上游欄位不會連動。

所以改完之後，受牽連的下游格會標上**橘色斜線**提醒，由審查員自行判斷要不要
一併更正——寧可標出來讓人決定，也不要送出半套重算的錯數字。依賴關係取自
`index.html` 既有的欄位對照資料，涵蓋：

- 表5：等級序號／等級文字 → 同列修正百分比 → 該主要項目百分比小計 → 總修正數
- 表3 → 表5：某地價區段工作表的勘查事實與判定等級 → 表5 對應區段的等級欄
- 表4：個別因素條件欄 → 同列差異率

要真正重算，仍須把更正回填 `datasets/` 後重跑 `engine/`。

### 相關檔案

| 檔案 | 角色 |
|---|---|
| `engine/preview_html.py` | `render_sheet(editable=True)` 輸出 `data-ref`／`contenteditable` |
| `engine/field_map_template.html` | 編輯介面、依賴圖、三種匯出 |
| `service/patch_xlsx.py` | 套用修正並打包 zip（含輸入驗證） |
| `service/server.py` | `do_POST` 路由與大小上限 |

---

## 7. AWS 部署（ECS Fargate）

服務已部署在 AWS 帳號 `242971039848` 的 `us-west-2`，以 ECR 映像跑在 ECS Fargate 上。

| 項目 | 值 |
| --- | --- |
| ECR 映像 | `242971039848.dkr.ecr.us-west-2.amazonaws.com/ntpc-appraisal-output:latest` |
| ECS 叢集／服務 | `ntpc-appraisal` / `ntpc-appraisal-output` |
| 任務規格 | Fargate ARM64，0.25 vCPU／0.5 GB |
| Security group | `sg-09f19d9b31bdf84f7`（對外開放 TCP 8000） |
| CloudWatch 日誌 | `/ecs/ntpc-appraisal-output`（保留 7 天） |

### 憑證

**憑證不進版控**：`.gitignore` 已排除 `.env*`、`.aws/`、`*.pem` 與含 `credentials` 的檔名。
`deploy-aws.sh` 不帶任何金鑰，只寫死帳號、區域與資源名稱（這些不是機密），
實際憑證由 aws CLI 自行解析。

**本專案目前的作法**：金鑰以環境變數寫在開發機的 `~/.zshrc`
（`AWS_ACCESS_KEY_ID`／`AWS_SECRET_ACCESS_KEY`／`AWS_SESSION_TOKEN`／`AWS_DEFAULT_REGION=us-west-2`）。
兩個實務上一定會踩到的點：

- **憑證是短效的。** session token 屬活動用角色
  `arn:aws:sts::242971039848:assumed-role/WSParticipantRole/Participant`，過期後所有 `aws`
  指令都會失敗，必須把新的值貼回 `~/.zshrc`。
- **`~/.zshrc` 只有互動式 shell 會載入。** 從 CI、cron 或非互動的工具執行部署時完全讀不到，
  第一個 `aws` 呼叫就會失敗。請在互動式終端機執行，或在該環境另外 export。

`~/.zshrc` 存的是有效金鑰且不在本倉庫內 —— 不要複製進來，外洩時務必輪換。

其他標準來源同樣可用：

```bash
aws configure sso                  # IAM Identity Center（SSO，長期帳號建議用這個）
aws sso login --profile ntpc

aws configure --profile ntpc       # IAM 使用者的 access key（長效，請定期輪換）

export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_SESSION_TOKEN=...   # 本專案採此法
export AWS_DEFAULT_REGION=us-west-2

aws sts get-caller-identity        # 應印出帳號 242971039848
```

用 named profile 時，跑腳本前先 `export AWS_PROFILE=ntpc`。
aws CLI 需在 `PATH` 上；腳本另外會找 `~/.local/bin`（macOS 安裝器的預設位置），
並在開始建置前先驗一次身分 —— 憑證過期時一秒內就失敗，不必等映像建完才發現。

**更新部署所需的最小 IAM 權限**：

| 服務 | 動作 |
|---|---|
| ECR | `GetAuthorizationToken`、`BatchCheckLayerAvailability`、`InitiateLayerUpload`、`UploadLayerPart`、`CompleteLayerUpload`、`PutImage`、`BatchGetImage` |
| ECS | `UpdateService`、`DescribeServices`、`ListTasks`、`DescribeTasks` |
| EC2 | `DescribeNetworkInterfaces`（只用來印出新的公開 IP） |

從零建立整套資源另需 `ecr:CreateRepository`、`ecs:CreateCluster`／`RegisterTaskDefinition`／
`CreateService`、`logs:CreateLogGroup`、`ec2:CreateSecurityGroup`／`AuthorizeSecurityGroupIngress`，
以及對 `ecsTaskExecutionRole` 的 `iam:PassRole`。首次建置步驟見專案根目錄
[`README.md §7.3`](../README.md#73-first-time-bootstrap)。

### 更新部署

`output/` 重新產生之後，映像要重推一次：

```bash
./service/deploy-aws.sh        # 建置 → 推 ECR → 滾動更新 → 印出新的 URL
```

查看日誌：

```bash
aws logs tail /ecs/ntpc-appraisal-output --follow --region us-west-2
```

### 注意

- **公開 IP 每次換任務都會變**。Fargate 任務沒有固定 IP，重新部署或任務被替換後
  就要重新查一次（`deploy-aws.sh` 最後會印出來）。要固定網址得再加
  ALB 或 CloudFront，這個唯讀報表服務目前沒有加。
- **對外是純 HTTP，沒有 TLS，也沒有存取控制**，任何知道 IP 的人都讀得到
  `output/` 底下的內容。要限制來源請改 security group 的 ingress CIDR。
- 映像把 `output/` 包進去（不像本機 compose 是掛載），所以報表改了一定要重新
  建置推送，否則線上還是舊的那一份。
