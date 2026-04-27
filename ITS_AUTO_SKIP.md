# ITS Issue 自動跳過功能

## 功能說明

在 Step 2（逐筆確認）的 Case 3（新 coredump-key）中，ITS firmware 的 issue 會自動跳過，無需用戶確認，並記錄 log。

## 實現位置

`coredump-v4.py` Step 2 的 `step2_first_confirm()` 函數，第 488-495 行：

```python
# ── Skip ITS issues ──
if is_its:
    logger.log(f"[ITS] 屬於 ITS firmware，自動跳過")
    rows[i][target_col] = "Skip"
    save_csv(csv_path, fieldnames, rows)
    update_daily_csv(row.get("_id", ""), target_col, "Skip")
    skip_count += 1
    continue
```

## 執行流程

在 Step 2 的逐筆確認中：

1. **Case 1**：existing_jid → 自動填入 related-jira-id
2. **Case 2**：batch_temp（同一 batch 內重複）→ 詢問用戶
3. **Case 3**：新的 coredump-key
   - ✅ 檢查 daemon 白名單 → 匹配則跳過
   - ✅ **檢查 ITS firmware → 匹配則跳過（新增）**
   - 詢問用戶（確認 / 跳過 / 忽略 / 結束）

## 判定標準

ITS firmware 的判定通過 `is_its_firmware()` 函數：

```python
def is_its_firmware(firmware):
    return 'ITS' in firmware.upper() if firmware else False
```

**範例**：
- ✅ ITS：`1.38(ABZH.0)ITS-26WK04-m10433` → 自動跳過
- ✅ ITS：`1.37(ABZI.0)ITS-...` → 自動跳過
- ❌ 非 ITS：`1.38(ABZH.0)` → 詢問用戶
- ❌ 非 ITS：`1.37(ABWV.1)Italy` → 詢問用戶

## 日誌輸出示例

```
(1/5)
  ITS:              Yes
  Firmware:         1.38(ABZH.0)ITS-26WK04-m10433
  Serial Number:    S252L30100055
  Model:            USG FLEX 500H
  Daemon:           fp-rte
  Coredump File(s): 260415-073537_1.38p0_ABZH#fp-rte#no-key.core.zip
  Coredump Key:     no-key.core.zip
  目標欄位:         ITS-jira-id

[ITS] 屬於 ITS firmware，自動跳過
```

## 優先級順序

檢查順序（短路邏輯）：

```
是否為 existing_jid（已有重複的 key）?
  ↓ Yes → 自動填入 related-jira-id，跳過
  
是否在 batch 內重複?
  ↓ Yes → 詢問用戶
  
是否為新 coredump-key?
  ↓ 檢查 daemon 白名單
    ↓ Yes → 自動跳過
    ↓ No → 檢查 ITS firmware
      ↓ Yes → 自動跳過
      ↓ No → 詢問用戶
```

## 統計計數

ITS 自動跳過的 issue 會計入 `skip_count`，在最後的確認結果中顯示：

```
第一次確認結果：確認 5，重複 2，跳過 8，忽略 0
```

（其中的 8 個跳過包括：白名單 + ITS 自動跳過 + 用戶選擇跳過）

## 相關配置

無特殊配置需要，根據 firmware 欄位自動判定。

## 常見問題

**Q: 為什麼要自動跳過 ITS issue？**

A: ITS issue 通常有專門的追蹤流程（透過 ITS-ticket），不需進入常規 Jira 流程，因此自動跳過可提高工作效率。

**Q: 如果要處理某個 ITS issue 怎麼辦？**

A: 修改 firmware 欄位去除 "ITS" 標記，或使用 `--resume` 重新執行並手動選擇。
