#!/usr/bin/env python3
"""
檢查 JIRA 欄位名稱
用來找出 Model 和 Affects Version/s 的正確欄位名稱
"""

import json
import requests
from requests.auth import HTTPBasicAuth
from config_loader import load_config

def main():
    config = load_config()

    url = f"{config['JIRA_BASE_URL']}/rest/api/3/field"
    headers = {"Accept": "application/json"}
    auth = HTTPBasicAuth(config["EMAIL"], config["API_TOKEN"])

    print(f"正在查詢 JIRA 欄位...")
    print(f"URL: {url}\n")

    response = requests.get(url, headers=headers, auth=auth)

    if response.status_code != 200:
        print(f"錯誤：HTTP {response.status_code}")
        print(response.text)
        return

    fields = response.json()

    print(f"總共找到 {len(fields)} 個欄位\n")
    print("=" * 80)

    # 查找包含 "model", "version", "affect" 等關鍵字的欄位
    keywords = ["model", "version", "affect", "fix"]

    print("包含關鍵字的欄位:")
    print("-" * 80)

    for field in fields:
        field_name = field.get('name', '')
        field_id = field.get('id', '')
        field_type = field.get('schema', {}).get('type', 'N/A')

        # 檢查是否包含關鍵字（不分大小寫）
        if any(keyword.lower() in field_name.lower() for keyword in keywords):
            print(f"名稱: {field_name}")
            print(f"  ID: {field_id}")
            print(f"  類型: {field_type}")
            if field.get('custom'):
                print(f"  自訂欄位: Yes")
            print()

    print("=" * 80)
    print("\n完整欄位清單已儲存到 jira_fields.json")

    # 儲存完整清單到檔案
    with open('jira_fields.json', 'w', encoding='utf-8') as f:
        json.dump(fields, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
