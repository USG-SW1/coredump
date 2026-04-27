#!/usr/bin/env python3
"""
測試 JIRA 欄位更新
用來驗證 Model 和 Affects Version 是否可以正確更新
"""

import json
import sys
import requests
from requests.auth import HTTPBasicAuth
from config_loader import load_config
from jira_api import get_custom_field_map, update_fields

def test_update_fields(jira_key):
    """測試更新指定 JIRA issue 的 Model 和 Affects Version"""
    config = load_config()

    print(f"測試更新 JIRA issue: {jira_key}")
    print("=" * 60)

    # 1. 獲取 Model 欄位的 ID
    field_map = get_custom_field_map(config, {'Model'})
    print(f"\nModel 欄位 ID: {field_map.get('Model', 'NOT FOUND')}")

    # 2. 準備更新的欄位
    put_fields = {}

    # Model (自訂欄位)
    if 'Model' in field_map:
        test_model = "USG FLEX 200"  # 測試用的 model
        put_fields[field_map['Model']] = [{"value": test_model}]
        print(f"將更新 Model 為: {test_model}")
    else:
        print("警告：找不到 Model 欄位")

    # Affects Version (系統欄位)
    test_version = "V1.30(ABZY.0)C0"  # 測試用的版本
    put_fields['versions'] = [{"name": test_version}]
    print(f"將更新 Affects Version 為: {test_version}")

    # 3. 執行更新
    print(f"\n準備更新的欄位:")
    print(json.dumps(put_fields, indent=2, ensure_ascii=False))

    confirm = input(f"\n確定要更新 {jira_key}? (y/n): ")
    if confirm.lower() != 'y':
        print("已取消")
        return

    try:
        update_fields(config, jira_key, put_fields)
        print(f"\n✓ 更新成功！")
        print(f"請檢查: {config['JIRA_BASE_URL']}/browse/{jira_key}")

        # 驗證更新
        print("\n驗證更新...")
        verify_url = f"{config['JIRA_BASE_URL']}/rest/api/3/issue/{jira_key}"
        response = requests.get(
            verify_url,
            headers={"Accept": "application/json"},
            auth=HTTPBasicAuth(config["EMAIL"], config["API_TOKEN"])
        )

        if response.status_code == 200:
            issue_data = response.json()
            fields = issue_data.get('fields', {})

            # 檢查 Model
            if 'Model' in field_map:
                model_value = fields.get(field_map['Model'])
                print(f"  Model: {model_value}")

            # 檢查 Affects Version
            versions = fields.get('versions', [])
            print(f"  Affects Versions: {[v.get('name') for v in versions]}")

    except Exception as e:
        print(f"\n✗ 更新失敗: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 test_jira_update.py <JIRA_KEY>")
        print("例如: python3 test_jira_update.py ZNGA-9916")
        sys.exit(1)

    jira_key = sys.argv[1]
    test_update_fields(jira_key)
