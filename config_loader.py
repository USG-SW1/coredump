import json
import os
import sys

BASE_REQUIRED_KEYS = ["jira-url", "account", "ELK-token"]

DEFAULTS = {
    "download-timeout": 120,
    "download-retries": 3,
    "download-retry-delay": 5,
    "user-confirm": True,
    "max-log-files": 100,
    "max-coredump-dirs": 30,
    "daemon-whitelist": [],
}


def load_config(extra_keys=None, config_path=None):
    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

    required_keys = BASE_REQUIRED_KEYS + (extra_keys or [])

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"錯誤：找不到設定檔 {config_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"錯誤：設定檔 JSON 格式錯誤 - {e}")
        sys.exit(1)

    # Apply defaults for optional keys
    for key, default_value in DEFAULTS.items():
        config.setdefault(key, default_value)

    errors = []
    for key in required_keys:
        if key not in config:
            errors.append(f"錯誤：config.json 缺少 '{key}'")

    if errors:
        for e in errors:
            print(e)
        sys.exit(1)

    config["JIRA_BASE_URL"] = config["jira-url"]
    config["EMAIL"] = config["account"]
    config["API_TOKEN"] = config["ELK-token"]

    return config
