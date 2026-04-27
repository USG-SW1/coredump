# Coredump Auto-Processing Tool

從 Elasticsearch 自動查詢 coredump 記錄，建立 Jira issue，下載 coredump 檔案並上傳至 FTP。

## 流程總覽

```
Step 0: 檢查上次失敗的 SN，詢問是否重試
Step 1: ELK-query.py       — 查詢 Elasticsearch，產生 CSV
Step 2: jira-post.py       — 互動式確認，建立 Jira issue
Step 3: optools.py         — 透過 OpTools 查詢每個 SN 的 MAC address
Step 4: optools-download.py — 下載 coredump 檔案
Step 5: upload-coredump.py — 上傳 coredump 至 FTP server
Step 6: ELK-query.py       — 合併 CSV 為 XLSX
Step 7: report-check.py    — 驗證 Jira 與 FTP 狀態
```

## 事前準備

### config.json

在專案目錄下建立 `config.json`：

```json
{
  "jira-url": "https://your-domain.atlassian.net",
  "account": "your-email@example.com",
  "ELK-token": "Jira API token",
  "parent-SF": "SF-xxxx",
  "ES-url": "https://elasticsearch-host:port",
  "optools-host": "optools.example.com",
  "optools-user": "user@example.com",
  "optools-pass": "password",
  "ftp-host": "ftp.example.com",
  "ftp-user": "ftp-user",
  "ftp-pass": "ftp-password",
  "sharepoint-url": "https://your-sharepoint-link"
}
```

以下為選填（有預設值）：

| Key | 預設值 | 說明 |
|-----|--------|------|
| `download-timeout` | 120 | 下載檔案的 timeout（秒） |
| `download-retries` | 3 | 下載失敗重試次數 |
| `download-retry-delay` | 5 | 重試間隔（秒） |
| `poll-interval` | 5 | OpTools 輪詢間隔（秒） |
| `poll-timeout` | 120 | OpTools 輪詢 timeout（秒） |

### 環境需求

- Python 3
- Playwright（`pip install playwright && playwright install chromium`）
- 相關 Python 套件：`requests`, `openpyxl`

## 基本用法

### 完整流程（一鍵執行）

```bash
# 查詢昨天的 coredump（預設）
./coredump-run.sh

# 指定查詢天數
./coredump-run.sh -d 3

# 指定日期
./coredump-run.sh --date 2026-03-15

# 顯示瀏覽器畫面（debug 用）
./coredump-run.sh --head
```

### 單獨執行各步驟

```bash
# Step 1: 查詢 ELK
python3 ELK-query.py -d 1
python3 ELK-query.py --date 2026-03-15

# Step 2: 建立 Jira（互動式，會逐筆詢問）
python3 jira-post.py

# Step 3+4: 查 MAC + 下載 coredump
python3 optools.py -s <SN>
python3 optools-download.py -s <SN> -m <MAC>

# Step 5: 上傳至 FTP
python3 upload-coredump.py

# Step 6: 合併 CSV 為 XLSX
python3 ELK-query.py --merge-xlsx

# Step 7: 驗證報告
python3 report-check.py
```

## 失敗處理與 Retry

### Download 失敗時自動處理

當 `optools-download.py` 下載失敗時，會自動：
1. 刪除對應的 Jira issue
2. 將 CSV 中的 jira-id 標記為 `Fail`
3. 將 SN 寫入 `failed_sns.txt`

### Retry 失敗的 SN

```bash
# 重試所有失敗的 SN（讀取 failed_sns.txt）
./coredump-run.sh --retry

# 重試單一 SN
./coredump-run.sh --retry S252L31101480

# 顯示瀏覽器畫面
./coredump-run.sh --retry --head
```

Retry 流程會重新執行 OpTools 查 MAC → 下載 → 建 Jira → 上傳 FTP → 合併 XLSX。

### 手動刪除 Jira issue

如果需要手動刪除已建立的 Jira issue 並清空 CSV 記錄：

```bash
# 刪除單一 issue
python3 del-ELK-jira.py ZNGA-9747

# 刪除多個 issue
python3 del-ELK-jira.py ZNGA-9747 ZNGA-9748 ZNGA-9749
```

刪除成功後會自動清空 ELK-summary.csv 和 daily CSV 中對應的 jira-id，下次執行 `jira-post.py` 時可以重新建立。

### 手動 Retry 單一 SN（逐步操作）

如果不想用 `--retry`，可以手動逐步重跑：

```bash
# 1. 刪除殘留的 Jira issue（如果有的話）
python3 del-ELK-jira.py ZNGA-xxxx

# 2. 重新建立 Jira
python3 jira-post.py

# 3. 查 MAC
python3 optools.py -s <SN>

# 4. 下載 coredump（MAC 從 logs/mac_address.txt 取得）
python3 optools-download.py -s <SN> -m <MAC>

# 5. 上傳 FTP
python3 upload-coredump.py

# 6. 更新 XLSX
python3 ELK-query.py --merge-xlsx
```

## CSV 中的特殊標記

| 標記 | 意義 |
|------|------|
| `Skip` | 使用者在 jira-post.py 中選擇跳過 |
| `Fail` | 下載失敗，Jira 已刪除 |
| `OPTOOLS fail` | OpTools 查詢失敗 |

## 產出檔案

| 檔案 | 說明 |
|------|------|
| `YYYY-MM-DD.csv` | 每日 ELK 查詢結果 |
| `ELK-summary.csv` | 合併後的總表 |
| `ELK-summary.xlsx` | XLSX 格式的總表 |
| `coredumps/<JIRA-ID>/` | 下載的 coredump 檔案 |
| `posted_sns.txt` | 本次已建 Jira 的 SN 列表 |
| `failed_sns.txt` | 下載失敗的 SN 列表（供 retry 使用） |
| `logs/` | 每日 log 與截圖 |
