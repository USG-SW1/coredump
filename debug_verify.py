#!/usr/bin/env python3
"""Debug 驗證函數"""

import json
import requests
from requests.auth import HTTPBasicAuth
from config_loader import load_config
from jira_api import verify_issue_fields, get_custom_field_map
from logger import Logger

def debug_verify():
    config = load_config()
    logger = Logger(source="debug")
    issue_key = "ZNGA-9943"

    # 取得 Model 欄位 ID
    field_map = get_custom_field_map(config, {'Model'}, logger=logger)
    model_field_id = field_map.get('Model')

    if not model_field_id:
        print("錯誤: 找不到 Model 欄位")
        return

    print(f"Model 欄位 ID: {model_field_id}\n")

    # 使用驗證函數
    print("=" * 60)
    print("使用 verify_issue_fields 函數:")
    print("=" * 60)
    model_ok, versions_ok, model_val, versions_val = verify_issue_fields(
        config, issue_key, model_field_id, logger=logger
    )

    print(f"\n回傳值:")
    print(f"  model_ok: {model_ok}")
    print(f"  versions_ok: {versions_ok}")
    print(f"  model_val: {model_val}")
    print(f"  versions_val: {versions_val}")

    # 直接查詢 API
    print("\n" + "=" * 60)
    print("直接查詢 API:")
    print("=" * 60)

    url = f"{config['JIRA_BASE_URL']}/rest/api/3/issue/{issue_key}?fields={model_field_id},versions"
    response = requests.get(
        url,
        headers={"Accept": "application/json"},
        auth=HTTPBasicAuth(config["EMAIL"], config["API_TOKEN"])
    )

    if response.status_code == 200:
        data = response.json()
        fields = data.get("fields", {})

        print(f"\nModel 欄位 ({model_field_id}):")
        model_field = fields.get(model_field_id)
        print(f"  原始值: {json.dumps(model_field, ensure_ascii=False)}")
        print(f"  type: {type(model_field)}")

        print(f"\nversions 欄位:")
        versions_field = fields.get("versions")
        print(f"  原始值: {json.dumps(versions_field, ensure_ascii=False)}")
        print(f"  type: {type(versions_field)}")

        # 檢查驗證邏輯
        print("\n" + "=" * 60)
        print("驗證邏輯測試:")
        print("=" * 60)

        print(f"\nModel 欄位檢查:")
        print(f"  isinstance(model_field, list): {isinstance(model_field, list)}")
        if isinstance(model_field, list):
            print(f"  len(model_field): {len(model_field)}")
            if len(model_field) > 0:
                print(f"  model_field[0]: {model_field[0]}")

        print(f"\nversions 欄位檢查:")
        print(f"  isinstance(versions_field, list): {isinstance(versions_field, list)}")
        if isinstance(versions_field, list):
            print(f"  len(versions_field): {len(versions_field)}")

    logger.close()

if __name__ == "__main__":
    debug_verify()
