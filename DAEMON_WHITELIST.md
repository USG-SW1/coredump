# Daemon 白名單使用指南

## 功能說明

在 `coredump-v4.py` 的 Step 2（逐筆確認）中，對於白名單中的 daemon，系統會自動跳過處理，無需再詢問用戶，但會記錄 log。

## 配置方法

在 `config.json` 中添加 `daemon-whitelist` 配置：

```json
{
    "jira-url": "...",
    "account": "...",
    ...
    "daemon-whitelist": [
        "isc-worker0000",
        "syslog-ng",
        "dnsmasq",
        "nginx.*",
        ".*cache.*"
    ]
}
```

## 白名單匹配規則

1. **完全匹配**：daemon 名稱完全相同（不區分大小寫）
   - 例：`"isc-worker0000"` 會匹配 `isc-worker0000` 或 `ISC-WORKER0000`

2. **正則表達式匹配**：支援正則表達式
   - 例：`"nginx.*"` 會匹配 `nginx`, `nginx-worker0`, `nginx-cache` 等
   - 例：`".*cache.*"` 會匹配任何含 `cache` 的 daemon 名稱

## 日誌輸出示例

當 daemon 匹配白名單時，日誌會顯示：

```
[白名單] Daemon 'isc-worker0000' 在白名單中，自動跳過
```

## 常見使用場景

1. **跳過已知的重複 daemon**：
   ```json
   "daemon-whitelist": ["isc-worker0000", "syslog-ng"]
   ```

2. **跳過所有 worker 相關的 daemon**：
   ```json
   "daemon-whitelist": [".*worker.*"]
   ```

3. **結合多個條件**：
   ```json
   "daemon-whitelist": [
       "isc-worker0000",
       "nginx.*",
       ".*test.*"
   ]
   ```

## 修改白名單

修改 `config.json` 後，下次執行 coredump-v4.py 時新配置會自動生效，無需重啟。

## 注意事項

- 白名單配置是可選的，默認為空列表 `[]`
- 匹配時不區分大小寫
- 正則表達式需要符合 Python `re` 模塊的語法
- 白名單只適用於 Step 2 的首次確認，不影響後續步驟
