# Bug 修復：OPTOOLS 上傳失敗導致使用舊 key_path

## 問題描述

在 Step 3 Download 中，當 OPTOOLS 上傳失敗（POST 請求沒有返回 200），代碼仍然會使用前一次成功上傳的舊 key_path 進行下載，導致下載到錯誤的檔案。

### 具體案例（2026-04-20）

- **ZNGA-10011**：成功上傳 → key_path = `prod/acf6d642-d057-4a02-ba1d-bd52bc057afb/1776688127221`
- **ZNGA-10012**：上傳失敗（`[WARN] Upload may not have succeeded`）→ 但代碼仍使用舊的 key_path
- **結果**：ZNGA-10012 下載到了 ZNGA-10011 的檔案，造成資料混亂

## 根本原因

在 Step 3 的 `trigger_and_download()` 函數（第 676-683 行）中：

```python
if not success:
    logger.log("  [WARN] Upload may not have succeeded.")

key_path = page.evaluate("$('#key-path').val() || 'not found'")
logger.log(f"  Key path: {key_path}")
```

**問題**：
1. 即使上傳失敗（`success = False`），代碼仍然繼續執行
2. OPTOOLS 頁面上的 `$('#key-path')` 沒有被清除或更新
3. 代碼取得的是前一次成功上傳的 key_path
4. 使用舊的 key_path 進行 `check_device_log()` 和下載

## 修復方案

在取得 key_path 後添加**驗證邏輯**：

1. **儲存前一次的 key_path**（上傳前）
2. **檢查 key_path 是否真的改變了**（上傳後）
3. **如果 key_path 沒變或無效，直接拋出異常**

### 修改代碼

```python
# 上傳前：儲存舊的 key_path
prev_key_path = page.evaluate("$('#key-path').val() || ''")
logger.log(f"  [DEBUG] Previous key_path: {prev_key_path}")

# 上傳
page.evaluate("trigger_device_upload_log()")

# ... 等待 alert ...

# 上傳後：驗證 key_path 改變
key_path = page.evaluate("$('#key-path').val() || 'not found'")
logger.log(f"  Key path: {key_path}")

# 檢查是否真的上傳成功
if key_path == prev_key_path or key_path == "not found" or key_path == "":
    error_msg = f"Upload failed or returned invalid key_path: prev={prev_key_path}, new={key_path}"
    logger.log(f"  [ERROR] {error_msg}")
    raise Exception(error_msg)
```

## 效果

修復後的行為：

- ✅ 上傳失敗時立即拋出異常，標記該 SN 為 `download_fail`
- ✅ 不會使用舊的 key_path 進行錯誤下載
- ✅ 日誌會清楚顯示 previous key_path 和新的 key_path（用於除錯）
- ✅ ZNGA-10012 會被正確標記為失敗，而不是下載到錯誤的檔案

## 日誌示例

修復後的日誌會顯示：

```
[DEBUG] Previous key_path: prod/acf6d642-d057-4a02-ba1d-bd52bc057afb/1776688127221
[NET] Request: POST https://...
[WARN] Upload may not have succeeded.
Key path: prod/acf6d642-d057-4a02-ba1d-bd52bc057afb/1776688127221
[ERROR] Upload failed or returned invalid key_path: prev=prod/acf6d642-d057-4a02-ba1d-bd52bc057afb/1776688127221, new=prod/acf6d642-d057-4a02-ba1d-bd52bc057afb/1776688127221
[FAIL] SN S252L07102690 下載失敗: Upload failed or returned invalid key_path: ...
```

## 相關文件

- `coredump-v4.py`: Step 3 的 `trigger_and_download()` 函數
- `config.json`: OPTOOLS 相關配置
