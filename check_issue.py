#!/usr/bin/env python3
"""快速查詢 Jira issue 的 Model 和 versions 欄位"""

import json
import sys
import requests
from requests.auth import HTTPBasicAuth
from config_loader import load_config

def check_issue(issue_key):
    config = load_config()

    # 先查詢 Model 欄位 ID
    print(f"正在查詢 {issue_key}...\n")

    field_url = f"{config['JIRA_BASE_URL']}/rest/api/3/field"
    response = requests.get(
        field_url,
        headers={"Accept": "application/json"},
        auth=HTTPBasicAuth(config["EMAIL"], config["API_TOKEN"])
    )

    model_field_id = None
    for f in response.json():
        if f['name'] == 'Model':
            model_field_id = f['id']
            break

    if not model_field_id:
        print("錯誤: 找不到 Model 欄位")
        return

    print(f"Model 欄位 ID: {model_field_id}\n")

    # 查詢 issue
    issue_url = f"{config['JIRA_BASE_URL']}/rest/api/3/issue/{issue_key}"
    params = {"fields": f"{model_field_id},versions,summary"}

    response = requests.get(
        issue_url,
        headers={"Accept": "application/json"},
        auth=HTTPBasicAuth(config["EMAIL"], config["API_TOKEN"]),
        params=params
    )

    if response.status_code != 200:
        print(f"錯誤: HTTP {response.status_code}")
        print(response.text)
        return

    data = response.json()
    fields = data.get("fields", {})

    print("=" * 60)
    print(f"Issue: {issue_key}")
    print(f"Summary: {fields.get('summary', 'N/A')}")
    print("=" * 60)

    # 檢查 Model
    model_field = fields.get(model_field_id)
    print(f"\nModel 欄位 ({model_field_id}):")
    print(f"  原始值: {json.dumps(model_field, ensure_ascii=False, indent=2)}")

    if isinstance(model_field, list) and len(model_field) > 0:
        model_value = model_field[0].get("value", "")
        print(f"  解析值: {model_value}")
        print(f"  狀態: ✓ 有值")
    else:
        print(f"  狀態: ✗ 無值或格式錯誤")

    # 檢查 versions
    versions_field = fields.get("versions")
    print(f"\nversions 欄位:")
    print(f"  原始值: {json.dumps(versions_field, ensure_ascii=False, indent=2)}")

    if isinstance(versions_field, list) and len(versions_field) > 0:
        versions_value = versions_field[0].get("name", "")
        print(f"  解析值: {versions_value}")
        print(f"  狀態: ✓ 有值")
    else:
        print(f"  狀態: ✗ 無值或格式錯誤")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    issue_key = sys.argv[1] if len(sys.argv) > 1 else "ZNGA-9943"
    check_issue(issue_key)
