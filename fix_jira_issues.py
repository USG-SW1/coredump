#!/usr/bin/env python3
"""
修復 ZNGA-9916 和 ZNGA-9917 的 Model 和 Affects Version 欄位
"""

import json
import requests
from requests.auth import HTTPBasicAuth
from config_loader import load_config
from jira_api import get_custom_field_map, update_fields

def parse_affects_version(firmware):
    """Parse firmware version to Jira Affects Version format"""
    if not firmware:
        return ""
    # 1.37(ABZH.1) -> V1.37(ABZH.1)
    firmware = firmware.strip()
    if firmware and not firmware.startswith('V'):
        return f"V{firmware}"
    return firmware

def create_version_if_not_exists(config, project_key, version_name):
    """在 JIRA project 中建立 version（如果不存在）"""
    try:
        # 查詢現有版本
        versions_url = f"{config['JIRA_BASE_URL']}/rest/api/3/project/{project_key}/versions"
        versions_response = requests.get(
            versions_url,
            headers={"Accept": "application/json"},
            auth=HTTPBasicAuth(config["EMAIL"], config["API_TOKEN"])
        )
        existing_versions = []
        if versions_response.status_code == 200:
            existing_versions = [v.get('name', '') for v in versions_response.json()]

        # 建立版本（如果不存在）
        if version_name not in existing_versions:
            create_url = f"{config['JIRA_BASE_URL']}/rest/api/3/version"
            create_response = requests.post(
                create_url,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                auth=HTTPBasicAuth(config["EMAIL"], config["API_TOKEN"]),
                data=json.dumps({
                    "name": version_name,
                    "project": project_key,
                })
            )
            if create_response.status_code in (200, 201):
                print(f"    ✓ 已建立新版本: {version_name}")
                return True
            else:
                print(f"    ✗ 建立版本失敗 {version_name}，HTTP {create_response.status_code}")
                return False
        else:
            print(f"    ℹ 版本已存在: {version_name}")
            return True
    except Exception as e:
        print(f"    ✗ 版本檢查/建立失敗: {e}")
        return False

def fix_issue(config, jira_key, model, firmware, project_key="ZNGA"):
    """修復單個 JIRA issue 的 Model 和 Affects Version"""
    print(f"\n{'='*80}")
    print(f"修復 {jira_key}")
    print(f"{'='*80}")

    # 獲取 Model 欄位的 ID
    field_map = get_custom_field_map(config, {'Model'})
    model_field_id = field_map.get('Model')

    if not model_field_id:
        print(f"  ✗ 找不到 Model 欄位")
        return False

    # 準備更新的欄位
    put_fields = {}

    # Model (自訂欄位 customfield_10088)
    put_fields[model_field_id] = [{"value": model}]
    print(f"  將更新 Model: {model}")

    # Affects Version (系統欄位 versions)
    version_name = parse_affects_version(firmware)
    print(f"  將更新 Affects Version: {version_name}")

    # 建立 version（如果不存在）
    create_version_if_not_exists(config, project_key, version_name)

    put_fields['versions'] = [{"name": version_name}]

    # 執行更新
    print(f"\n  準備更新的欄位:")
    print(f"    {model_field_id}: [{{'value': '{model}'}}]")
    print(f"    versions: [{{'name': '{version_name}'}}]")

    try:
        update_fields(config, jira_key, put_fields)
        print(f"\n  ✓ 更新成功！")
        print(f"  URL: {config['JIRA_BASE_URL']}/browse/{jira_key}")
        return True
    except Exception as e:
        print(f"\n  ✗ 更新失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    config = load_config()

    issues_to_fix = [
        {
            "jira_key": "ZNGA-9916",
            "model": "USG FLEX 500H",
            "firmware": "1.37(ABZH.1)",
        },
        {
            "jira_key": "ZNGA-9917",
            "model": "USG FLEX 50H",
            "firmware": "1.37(ACLO.1)",
        },
    ]

    print("準備修復以下 JIRA issues:")
    for issue in issues_to_fix:
        print(f"  - {issue['jira_key']}: Model={issue['model']}, Firmware={issue['firmware']}")

    success_count = 0
    for issue in issues_to_fix:
        if fix_issue(config, issue['jira_key'], issue['model'], issue['firmware']):
            success_count += 1

    print(f"\n{'='*80}")
    print(f"修復完成：{success_count}/{len(issues_to_fix)} 成功")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()
