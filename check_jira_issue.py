#!/usr/bin/env python3
"""
查看 JIRA issue 的 Model 和 Affects Version 欄位
"""

import sys
import requests
from requests.auth import HTTPBasicAuth
from config_loader import load_config
from jira_api import get_custom_field_map

def check_issue(jira_key):
    """查看指定 JIRA issue 的欄位"""
    config = load_config()

    print(f"查詢 JIRA issue: {jira_key}")
    print("=" * 80)

    # 獲取 Model 欄位的 ID
    field_map = get_custom_field_map(config, {'Model'})
    model_field_id = field_map.get('Model')

    # 查詢 issue
    url = f"{config['JIRA_BASE_URL']}/rest/api/3/issue/{jira_key}"
    response = requests.get(
        url,
        headers={"Accept": "application/json"},
        auth=HTTPBasicAuth(config["EMAIL"], config["API_TOKEN"])
    )

    if response.status_code != 200:
        print(f"錯誤：無法查詢 {jira_key}，HTTP {response.status_code}")
        print(response.text)
        return

    issue_data = response.json()
    fields = issue_data.get('fields', {})

    print(f"\n基本資訊:")
    print(f"  Key: {jira_key}")
    print(f"  Summary: {fields.get('summary', 'N/A')}")
    print(f"  Status: {fields.get('status', {}).get('name', 'N/A')}")
    print(f"  URL: {config['JIRA_BASE_URL']}/browse/{jira_key}")

    print(f"\n欄位狀態:")
    print("-" * 80)

    # Model
    if model_field_id:
        model_value = fields.get(model_field_id)
        print(f"  Model (ID: {model_field_id}):")
        if model_value:
            if isinstance(model_value, list):
                print(f"    值: {[item.get('value', item) for item in model_value]}")
            else:
                print(f"    值: {model_value}")
        else:
            print(f"    值: 未設定 ❌")
    else:
        print(f"  Model: 找不到欄位 ❌")

    # Affects Version (系統欄位: versions)
    versions = fields.get('versions', [])
    print(f"  Affects Version/s (ID: versions):")
    if versions:
        print(f"    值: {[v.get('name') for v in versions]}")
    else:
        print(f"    值: 未設定 ❌")

    # Fix Versions (系統欄位: fixVersions)
    fix_versions = fields.get('fixVersions', [])
    print(f"  Fix Version/s (ID: fixVersions):")
    if fix_versions:
        print(f"    值: {[v.get('name') for v in fix_versions]}")
    else:
        print(f"    值: 未設定")

    # 其他可能相關的欄位
    print(f"\n其他資訊:")
    print("-" * 80)
    print(f"  SN (customfield_10283): {fields.get('customfield_10283', 'N/A')}")

    # Coredump Information
    coredump_info = fields.get('customfield_10085')
    if coredump_info:
        print(f"  Coredump Information (customfield_10085): {coredump_info[:100]}...")
    else:
        print(f"  Coredump Information: 未設定")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 check_jira_issue.py <JIRA_KEY>")
        print("例如: python3 check_jira_issue.py ZNGA-9916")
        sys.exit(1)

    jira_key = sys.argv[1]
    check_issue(jira_key)
