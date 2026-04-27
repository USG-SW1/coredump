import sys
from config_loader import load_config
from jira_api import delete_jira_issue
from csv_helper import load_csv, save_csv, find_jira_in_csv, update_daily_csv
from logger import Logger

_config = load_config()


def main():
    logger = Logger()

    if len(sys.argv) < 2:
        logger.log(f"用法: python {sys.argv[0]} JIRA-ID1 [JIRA-ID2 ...]")
        logger.log(f"範例: python {sys.argv[0]} ZNGA-12 ZNGA-34 ZNGA-56")
        logger.close()
        sys.exit(1)

    jira_ids = sys.argv[1:]
    csv_path, fieldnames, rows = load_csv()

    # 比對每個 jira-id 是否存在於 CSV
    not_found = []
    found_map = {}  # jira_id -> [(row_index, column_name), ...]

    for jira_id in jira_ids:
        matches = find_jira_in_csv(rows, jira_id)
        if not matches:
            not_found.append(jira_id)
        else:
            found_map[jira_id] = matches

    # 如果有任何 jira-id 不在 CSV 中，報錯並退出
    if not_found:
        logger.log("錯誤：以下 Jira ID 在 ELK-summary.csv 中找不到：")
        for jid in not_found:
            logger.log(f"  - {jid}")
        logger.close()
        sys.exit(1)

    # 逐筆確認並刪除
    total = len(found_map)
    logger.log(f"待處理：{total} 筆")
    success_ids = []
    fail_ids = []
    skip_ids = []

    for current, (jira_id, matches) in enumerate(found_map.items(), 1):
        logger.log(f"\n{'='*60}")
        logger.log(f"({current}/{total})")
        for row_idx, col_name in matches:
            row = rows[row_idx]
            daemon = row.get('daemon', '').strip()
            model = row.get('model', '').strip()
            logger.log(f"  {jira_id}  (CSV 第 {row_idx + 2} 行, 欄位: {col_name}, daemon: {daemon}, model: {model})")

        choice = input(f"({current}/{total}) 要刪除嗎？(y=刪除 / s=跳過 / q=結束): ").strip().lower()

        if choice == 'q':
            logger.log("使用者選擇結束。")
            break
        elif choice == 's':
            skip_ids.append(jira_id)
            continue
        elif choice == 'y':
            logger.log(f"刪除 {jira_id} ...")
            if delete_jira_issue(_config, jira_id, logger=logger):
                success_ids.append(jira_id)
                # 清空 CSV 中對應的 jira-id
                for row_idx, col_name in matches:
                    record_id = (rows[row_idx].get('_id') or '').strip()
                    rows[row_idx][col_name] = ''
                    if record_id:
                        update_daily_csv(record_id, col_name, '')
                    logger.log(f"  已清空 CSV 第 {row_idx + 2} 行 '{col_name}'")
                save_csv(csv_path, fieldnames, rows)
            else:
                fail_ids.append(jira_id)
        else:
            logger.log("無效輸入，跳過此筆。")
            skip_ids.append(jira_id)

    # 結果摘要
    logger.log(f"\n{'='*60}")
    logger.log(f"結果：成功 {len(success_ids)} 筆，失敗 {len(fail_ids)} 筆，跳過 {len(skip_ids)} 筆")
    if fail_ids:
        logger.log(f"失敗的 Jira ID: {', '.join(fail_ids)}")
    logger.close()


if __name__ == "__main__":
    main()
