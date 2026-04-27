#!/usr/bin/env python3
"""測試更新 ZNGA-9943 的 Model 和 versions"""

import json
import requests
from requests.auth import HTTPBasicAuth
from config_loader import load_config

def test_update():
    config = load_config()
    issue_key = "ZNGA-9943"

    # 準備更新資料
    put_fields = {
        "customfield_10088": [{"value": "USG FLEX 100H"}],
        "versions": [{"name": "1.37 p0c0"}]
    }

    print("準備更新的資料:")
    print(json.dumps(put_fields, ensure_ascii=False, indent=2))
    print()

    # 發送 PUT 請求
    url = f"{config['JIRA_BASE_URL']}/rest/api/3/issue/{issue_key}"
    payload = {"fields": put_fields}

    print(f"PUT URL: {url}")
    print(f"Payload:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print()

    response = requests.put(
        url,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        auth=HTTPBasicAuth(config["EMAIL"], config["API_TOKEN"]),
        data=json.dumps(payload)
    )

    print(f"回應狀態碼: {response.status_code}")
    print(f"回應內容: {response.text}")

    if response.status_code == 204:
        print("\n✓ 更新成功 (HTTP 204)")
    else:
        print(f"\n✗ 更新失敗 (HTTP {response.status_code})")

if __name__ == "__main__":
    test_update()
