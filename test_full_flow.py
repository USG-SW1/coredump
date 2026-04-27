#!/usr/bin/env python3
"""測試完整的更新流程"""

import json
import time
import requests
from requests.auth import HTTPBasicAuth
from config_loader import load_config
from jira_api import update_fields, verify_issue_fields, get_custom_field_map
from logger import Logger

def test_full_flow():
    config = load_config()
    logger = Logger(source="test")
    issue_key = "ZNGA-9943"

    # 取得 Model 欄位 ID
    field_map = get_custom_field_map(config, {'Model'}, logger=logger)
    model_field_id = field_map.get('Model')

    if not model_field_id:
        print("錯誤: 找不到 Model 欄位")
        return

    model = "USG FLEX 100H"
    fw = "1.37 p0c0"

    print("=" * 60)
    print(f"測試 issue: {issue_key}")
    print(f"Model 欄位 ID: {model_field_id}")
    print(f"要更新的值:")
    print(f"  Model: {model}")
    print(f"  影響版本: {fw}")
    print("=" * 60)

    # 1. 查詢更新前的狀態
    print("\n[1] 更新前的狀態:")
    model_ok, versions_ok, model_val, versions_val = verify_issue_fields(
        config, issue_key, model_field_id, logger=logger
    )
    print(f"  Model: {model_val} (ok={model_ok})")
    print(f"  影響版本: {versions_val} (ok={versions_ok})")

    # 2. 執行更新
    print("\n[2] 執行更新...")
    put_fields = {}
    put_fields[model_field_id] = [{"value": model}]
    put_fields['versions'] = [{"name": fw}]

    print(f"  PUT payload:")
    print(f"    {json.dumps(put_fields, ensure_ascii=False, indent=6)}")

    try:
        update_fields(config, issue_key, put_fields, logger=logger)
        print("  ✓ update_fields 執行完成，沒有拋出異常")
    except Exception as e:
        print(f"  ✗ update_fields 拋出異常: {e}")
        logger.close()
        return

    # 3. 等待一下（確保 Jira 更新完成）
    print("\n[3] 等待 2 秒...")
    time.sleep(2)

    # 4. 查詢更新後的狀態
    print("\n[4] 更新後的狀態:")
    model_ok, versions_ok, model_val, versions_val = verify_issue_fields(
        config, issue_key, model_field_id, logger=logger
    )
    print(f"  Model: {model_val} (ok={model_ok})")
    print(f"  影響版本: {versions_val} (ok={versions_ok})")

    # 5. 直接查詢 API 確認
    print("\n[5] 直接查詢 API:")
    url = f"{config['JIRA_BASE_URL']}/rest/api/3/issue/{issue_key}?fields={model_field_id},versions"
    response = requests.get(
        url,
        headers={"Accept": "application/json"},
        auth=HTTPBasicAuth(config["EMAIL"], config["API_TOKEN"])
    )

    if response.status_code == 200:
        fields = response.json().get("fields", {})
        print(f"  Model 原始值: {json.dumps(fields.get(model_field_id), ensure_ascii=False)}")
        print(f"  versions 原始值: {json.dumps(fields.get('versions'), ensure_ascii=False)}")

    print("\n" + "=" * 60)
    if model_ok and versions_ok:
        print("✓ 測試成功！Model 和 versions 都已正確填入")
    else:
        print("✗ 測試失敗！部分欄位未正確填入")
    print("=" * 60)

    logger.close()

if __name__ == "__main__":
    test_full_flow()
