# Coredump Auto-Processing Tool v2

從 Elasticsearch 自動查詢 coredump 記錄，下載 coredump 檔案，建立 Jira issue 並上傳至 FTP。

與 v1（`coredump-run.sh`）的主要差異：
- 單一 Python 程式取代 shell script 串接
- **先下載，成功後才建 Jira**（不需要回滾刪除 Jira）
- 兩階段 user 確認（確認處理 → 確認 post）
- 用 `coredump-key` 判定重複（取代原本的 `daemon`）
- `status.json` 支援中斷續跑（`--resume`）與失敗重試（`--retry`）
- `user-confirm` 設定可切換為全自動模式

## 流程總覽

```
Step 1: ELK Query
  查詢 Elasticsearch → 產生 daily CSV → merge 到 ELK-summary.csv

Step 2: 第一次確認（逐筆）
  2a. Summary 總覽：
      顯示統計：待處理總筆數、自動 related、batch 重複、新 key（非ITS/ITS）、需確認數
  2b. List 預覽：
      列出所有需要確認的 records，標注 [ITS]、[batch 重複]
  2c. 逐筆確認：
      ├── coredump-key 已存在於 CSV → 自動填 related-jira-id（不問）
      ├── coredump-key 在本次 batch 內重複 → 顯示重複內容，問 user: y / s
      └── 新的 coredump-key → 顯示完整資訊，問 user: y / s / i / q
  每筆確認後立即寫入 status.json

Step 3: Download（以 SN 為單位）
  從已確認的 records 取出 unique SNs
  對每個 SN：
  ├── 3a. OpTools 查 MAC（Playwright）
  ├── 3b. OpTools 下載 coredump（Playwright）
  └── 3c. Verify: unzip -l 檢查 zip 內容是否包含對應的 coredump-key
      ├── 包含 → download_ok
      └── 不包含 → download_fail，標記 'OPTOOLS mis-match'
  每個 SN 完成後立即更新 status.json

Step 4: 第二次確認 & Post Jira
  4a. Summary 總覽：
      顯示統計：總筆數、下載成功、下載失敗（含 mis-match）、重複（related）、需要 confirm
  4b. List 預覽：
      列出所有需要 confirm 的 records（下載成功 & 非 related）
  4c. 逐筆確認：
      對每筆需要 confirm 的 record：
      ├── 顯示檔案資訊，問 user 是否 post: y / s
      ├── y → 建立 Jira、update description、更新 CSV
      └── s → 跳過
      同 batch 相同 coredump-key 的 related records：
          primary 建完拿到 jira-id 後自動填入

Step 5: Upload FTP
Step 6: Merge CSV → XLSX
Step 7: Report（驗證 Jira & FTP 狀態）
Step 8: Cleanup
  ├── logs/ 超過 max-log-files（預設 100）→ 刪除最舊的
  └── coredumps/ 超過 max-coredump-dirs（預設 30）→ 刪除最舊的
```

## coredump-key 說明

用於判定兩筆 record 是否為「同一個 coredump issue」的 key。

```
target filename: 260322-194917-1.37_ABXF.1_-157fc_libedit-nc-cli.core.zip
                 ├── 日期時間 ──┤├─ firmware ─┤├──── coredump-key ────────┤
```

解析方式：
1. 取 target 的 basename（去掉路徑）
2. 去掉前 14 個字元（日期時間 `260322-194917-`）
3. 去掉第一個 `-` 之前的部分（firmware `1.37_ABXF.1_`）
4. 剩下的即為 coredump-key：`157fc_libedit-nc-cli.core.zip`

coredump-key 相同的 records 視為重複，第一筆建 Jira（填 `jira-id`），後續筆填 `related-jira-id`。

## 用法

### 正常模式

```bash
# 查詢昨天的 coredump（預設）
python3 coredump-v2.py

# 指定查詢天數
python3 coredump-v2.py -d 3

# 指定日期
python3 coredump-v2.py --date 2026-03-15

# 顯示瀏覽器畫面（debug 用）
python3 coredump-v2.py --head
```

### 續跑未完成的工作

```bash
python3 coredump-v2.py --resume [--head]
```

如果不帶 `--resume` 直接執行，程式會自動偵測未完成的 `status.json`：
```
發現上次未完成的工作（2026-03-25）：
  已確認: 8 筆, 已下載: 5 筆, 下載失敗: 1 筆, 待下載: 2 筆
  (r) 繼續上次進度
  (n) 放棄上次進度，重新開始
  (q) 離開
```

如果 resume 的日期與今天不同，resume 跑完後會自動繼續執行今天的查詢。

### 重試失敗的下載

```bash
# 重試所有失敗的 SN
python3 coredump-v2.py --retry [--head]

# 重試單一 SN
python3 coredump-v2.py --retry S252L41101892 [--head]
```

Retry 流程：
1. 讀取 status.json，列出失敗清單（最新在前）
2. 逐筆顯示 SN、錯誤原因、失敗時間、已 retry 次數
3. 問 user：要試這筆嗎？(y/s/q)
4. 下載成功 → 進入第二次確認（是否 post Jira）
5. 下載失敗 → 更新 status.json（retries + 1）

## 設定

### config.json

在 `config.json` 中新增 `user-confirm` 選項：

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
  "sharepoint-url": "https://your-sharepoint-link",
  "user-confirm": true
}
```

### user-confirm 行為

| 確認點 | `true`（預設） | `false`（全自動） |
|--------|---------------|-------------------|
| Step 2: 第一次確認 | 逐筆問 y/s/i/q | ITS → 自動 skip, 非 ITS → 自動 yes |
| Step 2: 同 batch 重複 coredump-key | 問 y/s | 自動填 related-jira-id |
| Step 4: 第二次確認（post 前） | 逐筆問 y/s | 下載成功 → 自動 post |
| 偵測到未完成的 status.json | 問 r/n/q | 自動 resume，跨日則 resume 後繼續當天 |
| Retry 逐筆確認 | 問 y/s/q | 全部自動 retry |

### 其他選填設定

| Key | 預設值 | 說明 |
|-----|--------|------|
| `download-timeout` | 120 | 下載檔案的 timeout（秒） |
| `download-retries` | 3 | 下載失敗重試次數 |
| `download-retry-delay` | 5 | 重試間隔（秒） |
| `poll-interval` | 5 | OpTools 輪詢間隔（秒） |
| `poll-timeout` | 120 | OpTools 輪詢 timeout（秒） |
| `max-log-files` | 100 | `logs/` 目錄保留的最大檔案數，超過刪除最舊的 |
| `max-coredump-dirs` | 30 | `coredumps/` 目錄保留的最大資料夾數，超過刪除最舊的 |

## status.json

程式執行狀態的持久化檔案，每個關鍵動作完成後立即寫入。

```json
{
  "session": {
    "started": "2026-03-25T10:30:00",
    "updated": "2026-03-25T14:22:10",
    "elk_date": "2026-03-24",
    "current_step": "download"
  },
  "records": [
    {
      "_id": "qtq_G50BiSsRy7ClcL8G",
      "sn": "S252L41101892",
      "daemon": "postgres",
      "firmware": "1.37(ABXF.1)",
      "model": "USG FLEX 100H",
      "coredump_key": "622a8_libc-a47a4-a67fc-f9eec-postgres.core.zip",
      "temp_id": "tmp-a1b2c3d4",
      "status": "download_ok",
      "jira_id": null,
      "jira_col": "jira-id",
      "download_path": "coredumps/tmp-a1b2c3d4/...-postgres.core.zip",
      "error": null,
      "retries": 0
    }
  ]
}
```

### record status 狀態流轉

```
(新 record)
  ├── confirmed     ── user 第一次確認 y
  ├── skipped        ── user 選 s
  └── ignored        ── user 選 i
       │
       ▼
  ├── download_ok    ── 下載成功
  └── download_fail  ── 下載失敗
       │
       ▼
  ├── posted         ── Jira 建立成功
  ├── post_skipped   ── user 第二次確認選 s
  └── uploaded       ── FTP 上傳成功
```

### --resume 時的處理

| record status | 處理方式 |
|---------------|---------|
| `confirmed` | 排入 Step 3 下載 |
| `download_ok` | 排入 Step 4 確認 post |
| `download_fail` | 問 user 要不要 retry |
| `posted` | 排入 Step 5 上傳 FTP |
| `uploaded` | 跳過 |
| `skipped` / `ignored` / `post_skipped` | 跳過 |

## 產出檔案

| 檔案 | 說明 |
|------|------|
| `YYYY-MM-DD.csv` | 每日 ELK 查詢結果 |
| `ELK-summary.csv` | 合併後的總表 |
| `ELK-summary.xlsx` | XLSX 格式的總表 |
| `coredumps/<JIRA-ID>/` | 下載的 coredump 檔案 |
| `status.json` | 執行狀態（支援 resume / retry） |
| `logs/YYYY-MM-DD.log` | 每日 log |

## 與 v1 的相容性

- `coredump-run.sh` 及所有現有 `.py` 檔案不受影響，仍可獨立執行
- `coredump-v2.py` 會 import 現有模組（`config_loader`, `logger`, `csv_helper`, `jira_api`）
- 兩者共用相同的 `ELK-summary.csv`、`config.json`、`logs/` 目錄
- 不建議同時執行 v1 和 v2（會互相覆蓋 CSV）

## CSV 中的特殊標記

| 標記 | 意義 |
|------|------|
| `Skip` | 使用者選擇跳過 |
| `Fail` | 下載失敗（v1） |
| `OPTOOLS fail` | OpTools 查詢/下載失敗 |
| `OPTOOLS mis-match` | 下載的 zip 內容不含對應的 coredump-key（檔案不符） |
