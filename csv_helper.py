import csv
import glob
import os
import sys
from logger import Logger

JIRA_ID_COLUMNS = ['jira-id', 'related-jira-id', 'ITS-jira-id', 'ITS-related-jira-id']


def load_csv(csv_filename="ELK-summary.csv"):
    """讀取 CSV，回傳 (csv_path, fieldnames, rows)"""
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), csv_filename)
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)
    except FileNotFoundError:
        logger = Logger(source="csv_helper")
        logger.log(f"錯誤：找不到 {csv_path}")
        logger.close()
        sys.exit(1)
    return csv_path, fieldnames, rows


def save_csv(csv_path, fieldnames, rows):
    """寫入 CSV"""
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def find_jira_in_csv(rows, jira_id):
    """在 CSV 中尋找 jira_id，回傳 (row_index, column_name) 的 list"""
    found = []
    for i, row in enumerate(rows):
        for col in JIRA_ID_COLUMNS:
            if row.get(col, '').strip() == jira_id:
                found.append((i, col))
    return found


def update_daily_csv(record_id, column, value):
    """根據 _id 更新原始日期 CSV 檔案中的指定欄位。

    掃描所有 ????-??-??.csv 檔案，找到 _id 匹配的 row 並更新。
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    daily_files = glob.glob(os.path.join(base_dir, "????-??-??.csv"))
    for daily_path in daily_files:
        with open(daily_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)
        updated = False
        for row in rows:
            if row.get('_id', '') == record_id:
                row[column] = value
                updated = True
        if updated:
            save_csv(daily_path, fieldnames, rows)
            return True
    return False
