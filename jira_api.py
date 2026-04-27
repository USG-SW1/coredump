import json
import requests
from requests.auth import HTTPBasicAuth
from logger import Logger


def _get_logger(logger):
    """Return provided logger or create a default one."""
    return logger if logger else Logger(source="jira_api")


def get_custom_field_map(config, target_names, logger=None):
    """查詢 JIRA 自訂欄位名稱對應的 field ID"""
    logger = _get_logger(logger)
    url = f"{config['JIRA_BASE_URL']}/rest/api/3/field"
    headers = {"Accept": "application/json"}
    auth = HTTPBasicAuth(config["EMAIL"], config["API_TOKEN"])

    response = requests.get(url, headers=headers, auth=auth)
    response.raise_for_status()

    field_map = {}
    for f in response.json():
        if f['name'] in target_names:
            field_map[f['name']] = f['id']

    missing = target_names - set(field_map.keys())
    if missing:
        logger.log(f"警告：找不到以下 JIRA 自訂欄位: {', '.join(missing)}")

    return field_map


def create_issue(config, project_key, issue_type, summary, description=None,
                 assignee_account_id=None, custom_fields=None, logger=None):
    """透過 Jira API 建立 issue"""
    logger = _get_logger(logger)
    url = f"{config['JIRA_BASE_URL']}/rest/api/3/issue"

    fields = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }

    if description:
        # Jira Cloud API v3 要求 ADF 格式
        fields["description"] = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": description}
                    ]
                }
            ]
        }

    if assignee_account_id:
        fields["assignee"] = {"accountId": assignee_account_id}

    if custom_fields:
        fields.update(custom_fields)

    payload = {"fields": fields}
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    auth = HTTPBasicAuth(config["EMAIL"], config["API_TOKEN"])

    response = requests.post(url, headers=headers, auth=auth, data=json.dumps(payload))

    if response.status_code not in (200, 201):
        logger.log(f"建立失敗，HTTP {response.status_code}")
        logger.log(response.text)
        response.raise_for_status()

    issue = response.json()
    logger.log("建立成功！")
    logger.log(f"Key: {issue.get('key')}")
    logger.log(f"URL: {config['JIRA_BASE_URL']}/browse/{issue.get('key')}")
    return issue


def update_fields(config, issue_key, fields, logger=None):
    """更新 issue 的任意欄位（PUT）"""
    logger = _get_logger(logger)
    url = f"{config['JIRA_BASE_URL']}/rest/api/3/issue/{issue_key}"
    payload = {"fields": fields}
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    auth = HTTPBasicAuth(config["EMAIL"], config["API_TOKEN"])

    response = requests.put(url, headers=headers, auth=auth, data=json.dumps(payload))

    if response.status_code != 204:
        logger.log(f"更新欄位失敗，HTTP {response.status_code}")
        logger.log(response.text)
        response.raise_for_status()

    logger.log(f"已更新 {issue_key} 的欄位")


def update_description(config, issue_key, description, logger=None):
    """更新 issue 的 description（ADF 格式）
    description 可以是：
      - 字串：自動拆行轉成 ADF paragraph
      - list：直接作為 ADF content 陣列
    """
    logger = _get_logger(logger)
    url = f"{config['JIRA_BASE_URL']}/rest/api/3/issue/{issue_key}"

    if isinstance(description, list):
        content = description
    else:
        # 將多行文字拆成多個 paragraph
        lines = description.split('\n')
        content = []
        for line in lines:
            if line.strip():
                content.append({
                    "type": "paragraph",
                    "content": [{"type": "text", "text": line}]
                })
            else:
                content.append({"type": "paragraph", "content": []})

    payload = {
        "fields": {
            "description": {
                "type": "doc",
                "version": 1,
                "content": content
            }
        }
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    auth = HTTPBasicAuth(config["EMAIL"], config["API_TOKEN"])

    response = requests.put(url, headers=headers, auth=auth, data=json.dumps(payload))

    if response.status_code != 204:
        logger.log(f"更新 description 失敗，HTTP {response.status_code}")
        logger.log(response.text)
        response.raise_for_status()

    logger.log(f"已更新 {issue_key} 的 description")


def update_parent(config, issue_key, parent_key, logger=None):
    """更新 issue 的 parent"""
    logger = _get_logger(logger)
    url = f"{config['JIRA_BASE_URL']}/rest/api/3/issue/{issue_key}"
    payload = {"fields": {"parent": {"key": parent_key}}}
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    auth = HTTPBasicAuth(config["EMAIL"], config["API_TOKEN"])

    response = requests.put(url, headers=headers, auth=auth, data=json.dumps(payload))

    if response.status_code != 204:
        logger.log(f"更新失敗，HTTP {response.status_code}")
        logger.log(response.text)
        response.raise_for_status()

    logger.log(f"設定成功！{issue_key} 的 parent 已設為 {parent_key}")


def check_issue_exists(config, issue_key):
    """檢查 Jira issue 是否存在，回傳 (exists, status_name)"""
    url = f"{config['JIRA_BASE_URL']}/rest/api/3/issue/{issue_key}?fields=status"
    headers = {"Accept": "application/json"}
    auth = HTTPBasicAuth(config["EMAIL"], config["API_TOKEN"])

    response = requests.get(url, headers=headers, auth=auth)
    if response.status_code == 200:
        status = response.json().get("fields", {}).get("status", {}).get("name", "")
        return True, status
    return False, ""


def verify_issue_fields(config, issue_key, model_field_id, logger=None):
    """驗證 issue 的 Model 和 versions 欄位是否已填入

    Args:
        config: 配置字典
        issue_key: Jira issue key
        model_field_id: Model 自訂欄位的 ID（例如 'customfield_10088'）
        logger: Logger 實例

    Returns:
        tuple: (model_ok, versions_ok, model_value, versions_value)
    """
    logger = _get_logger(logger)
    url = f"{config['JIRA_BASE_URL']}/rest/api/3/issue/{issue_key}?fields={model_field_id},versions"
    headers = {"Accept": "application/json"}
    auth = HTTPBasicAuth(config["EMAIL"], config["API_TOKEN"])

    response = requests.get(url, headers=headers, auth=auth)
    if response.status_code != 200:
        logger.log(f"  [WARN] 驗證失敗，無法獲取 issue 資料，HTTP {response.status_code}")
        return False, False, None, None

    fields = response.json().get("fields", {})

    # 檢查 Model 欄位
    model_field = fields.get(model_field_id, [])
    model_value = None
    model_ok = False
    if isinstance(model_field, list) and len(model_field) > 0:
        model_value = model_field[0].get("value", "")
        model_ok = bool(model_value)

    # 檢查 versions 欄位
    versions_field = fields.get("versions", [])
    versions_value = None
    versions_ok = False
    if isinstance(versions_field, list) and len(versions_field) > 0:
        versions_value = versions_field[0].get("name", "")
        versions_ok = bool(versions_value)

    return model_ok, versions_ok, model_value, versions_value


def delete_jira_issue(config, issue_key, logger=None):
    """透過 Jira API 刪除 issue"""
    logger = _get_logger(logger)
    url = f"{config['JIRA_BASE_URL']}/rest/api/3/issue/{issue_key}"
    headers = {"Accept": "application/json"}
    auth = HTTPBasicAuth(config["EMAIL"], config["API_TOKEN"])

    response = requests.delete(url, headers=headers, auth=auth)

    if response.status_code == 204:
        logger.log(f"  已刪除 Jira issue: {issue_key}")
        return True
    else:
        logger.log(f"  刪除失敗 {issue_key}，HTTP {response.status_code}")
        logger.log(f"  {response.text}")
        return False
