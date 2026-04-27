import os
import re
import sys
from datetime import datetime
from config_loader import load_config
from jira_api import get_custom_field_map, create_issue, update_description, update_fields
from csv_helper import load_csv, save_csv, update_daily_csv
from logger import Logger

_config = load_config(extra_keys=["parent-SF", "ftp-host", "sharepoint-url"])
PARENT_SF = _config["parent-SF"]
POSTED_SNS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posted_sns.txt")

#PROJECT_KEY = "SF"
PROJECT_KEY = "ZNGA"
ISSUE_TYPE_NAME = "漏洞"
# =======================


def extract_coredump_files(target):
    """從 target 路徑取得檔名，移除前 14 個字元和後面的 '.core.zip'"""
    filename = os.path.basename(target)
    # 去除前 14 個字元（日期時間）
    name = filename[14:] if len(filename) > 14 else filename
    # 去除後面的 '.core.zip'
    #if name.endswith('.core.zip'):
    #    name = name[:-len('.core.zip')]
    return name


def extract_coredump_info(coredump_files):
    """從 Coredump File(s) 值，刪除從開頭到第一個 '-' 的內容"""
    idx = coredump_files.find('-')
    if idx >= 0:
        return coredump_files[idx + 1:]
    return coredump_files


def parse_affects_version(firmware):
    """從 firmware 字串解析影響版本。
    e.g. '1.37(ACLO.0)'    -> '1.37 p0c0'
         '1.37(ACII.1)'    -> '1.37 p1c0'
         '1.37(ACII.1)b3'  -> '1.37 p1b3'
    """
    match = re.match(r'^([\d.]+)\([^.]+\.(\d+)\)(.*)', firmware)
    if not match:
        return firmware
    major = match.group(1)
    patch = match.group(2)
    suffix = match.group(3)
    if suffix:
        return f"{major} p{patch}{suffix}"
    else:
        return f"{major} p{patch}c0"


def is_its_firmware(firmware):
    """判斷 firmware 是否含有 ITS 關鍵字"""
    return 'ITS' in firmware.upper() if firmware else False


def append_posted_sn(sn):
    """將已 post 的 SN 寫入 posted_sns.txt"""
    with open(POSTED_SNS_FILE, "a", encoding="utf-8") as f:
        f.write(sn + "\n")


def process_elk_summary():
    logger = Logger()

    # 清空上次的 posted_sns.txt
    with open(POSTED_SNS_FILE, "w", encoding="utf-8") as f:
        pass

    csv_path, fieldnames, rows = load_csv()
    logger.log(f"讀取 ELK-summary.csv，共 {len(rows)} 筆資料")

    # 取得 JIRA 自訂欄位 ID
    logger.log("查詢 JIRA 自訂欄位 ID...")
    field_map = get_custom_field_map(_config, {
        'Coredump Daemon', 'Model', 'Coredump Information',
        'Function Category', 'Report Dept.', 'Severity',
        'Reproducible ?', 'Coredump File',
    }, logger=logger)
    for name, fid in field_map.items():
        logger.log(f"  {name} -> {fid}")

    # 收集已經 post 過的 daemon（從現有資料），記錄 daemon -> jira-id
    posted_daemons = {}
    its_posted_daemons = {}
    for row in rows:
        daemon = row.get('daemon', '').strip()
        if not daemon:
            continue
        jid = row.get('jira-id', '').strip()
        its_jid = row.get('ITS-jira-id', '').strip()
        if jid and jid not in ('Skip', 'Fail', 'OPTOOLS fail') and daemon not in posted_daemons:
            posted_daemons[daemon] = jid
        if its_jid and its_jid not in ('Skip', 'Fail', 'OPTOOLS fail') and daemon not in its_posted_daemons:
            its_posted_daemons[daemon] = its_jid

    # 先計算待處理筆數
    pending_indices = []
    for i, row in enumerate(rows):
        jid = row.get('jira-id', '').strip()
        rid = row.get('related-jira-id', '').strip()
        its_jid = row.get('ITS-jira-id', '').strip()
        its_rid = row.get('ITS-related-jira-id', '').strip()
        if not (jid or rid or its_jid or its_rid):
            pending_indices.append(i)

    total_pending = len(pending_indices)
    logger.log(f"待處理：{total_pending} 筆")

    post_count = 0
    skip_count = 0
    ignore_count = 0
    fail_count = 0
    current = 0

    for i, row in enumerate(rows):
        # 只處理四個 jira 欄位都為空的資料
        jira_id = row.get('jira-id', '').strip()
        related_jira_id = row.get('related-jira-id', '').strip()
        its_jira_id = row.get('ITS-jira-id', '').strip()
        its_related_jira_id = row.get('ITS-related-jira-id', '').strip()

        if jira_id or related_jira_id or its_jira_id or its_related_jira_id:
            continue

        # 判斷是否屬於 ITS
        firmware = row.get('firmware', '')
        is_its = is_its_firmware(firmware)

        # 判斷此 daemon 是否已經 post 過
        daemon = row.get('daemon', '').strip()
        if is_its:
            already_posted = daemon in its_posted_daemons
        else:
            already_posted = daemon in posted_daemons

        # 準備顯示資訊
        sn_value = row.get('sn', '').strip()
        firmware_value = row.get('firmware', '').strip()
        coredump_value = row.get('coredump', '')
        model_value = row.get('model', '')
        target_value = row.get('target', '')
        coredump_files = extract_coredump_files(target_value)
        coredump_info = extract_coredump_info(coredump_files)
        summary = f"[AUTO][ML][coredump] {daemon} coredump (SN:{sn_value})"
        current += 1

        # 重複的 daemon：不需要 post，直接填入既有的 jira-id
        if already_posted:
            existing_jira_id = its_posted_daemons[daemon] if is_its else posted_daemons[daemon]
            target_col = 'ITS-related-jira-id' if is_its else 'related-jira-id'

            logger.log(f"\n{'='*60}")
            logger.log(f"({current}/{total_pending}) 重複 daemon，自動填入")
            logger.log(f"  Daemon:             {daemon}")
            logger.log(f"  ITS:                {'Yes' if is_its else 'No'}")
            logger.log(f"  既有 Jira ID:       {existing_jira_id}")
            logger.log(f"  填入欄位:           {target_col}")

            rows[i][target_col] = existing_jira_id
            save_csv(csv_path, fieldnames, rows)
            update_daily_csv(row.get('_id', ''), target_col, existing_jira_id)
            post_count += 1
            continue

        # 決定填入哪個欄位（新 daemon）
        target_col = 'ITS-jira-id' if is_its else 'jira-id'

        # 顯示內容
        logger.log(f"\n{'='*60}")
        logger.log(f"({current}/{total_pending})")
        logger.log(f"  ITS:                {'Yes' if is_its else 'No'}")
        logger.log(f"  Firmware:           {firmware}")
        logger.log(f"  影響版本:           {parse_affects_version(firmware_value)}")
        logger.log(f"  Serial Number:      {sn_value}")
        logger.log(f"  工作 (Summary):     {summary}")
        logger.log(f"  Coredump Daemon:    {coredump_value}")
        logger.log(f"  Model:              {model_value}")
        logger.log(f"  Coredump File(s):   {coredump_files}")
        #logger.log(f"  Coredump Info:      {coredump_info}")
        logger.log(f"  Coredump Info:      {coredump_files}")
        logger.log(f"  目標欄位:           {target_col}")

        choice = input(f"({current}/{total_pending}) 要 Post 嗎？(y=Post / s=跳過 / i=忽略 / q=結束): ").strip().lower()

        if choice == 'q':
            logger.log("使用者選擇結束。")
            break
        elif choice == 's':
            rows[i][target_col] = 'Skip'
            save_csv(csv_path, fieldnames, rows)
            update_daily_csv(row.get('_id', ''), target_col, 'Skip')
            skip_count += 1
            continue
        elif choice == 'i':
            ignore_count += 1
            continue
        elif choice == 'y':
            # 組自訂欄位
            custom_fields = {}
            if 'Function Category' in field_map:
                custom_fields[field_map['Function Category']] = [{"value": "Coredump"}]
            if 'Report Dept.' in field_map:
                custom_fields[field_map['Report Dept.']] = {"value": "RD"}
            if 'Severity' in field_map:
                custom_fields[field_map['Severity']] = {"value": "L2"}
            if 'Reproducible ?' in field_map:
                custom_fields[field_map['Reproducible ?']] = {"value": "Yes"}
            #if 'Coredump Daemon' in field_map:
            #    custom_fields[field_map['Coredump Daemon']] = [daemon]
            #if 'Coredump File' in field_map:
            #    custom_fields[field_map['Coredump File']] = [coredump_files]
            if 'Coredump Information' in field_map:
                #custom_fields[field_map['Coredump Information']] = coredump_info
                custom_fields[field_map['Coredump Information']] = coredump_files
            # Serial Number
            custom_fields['customfield_10283'] = sn_value

            try:
                issue = create_issue(_config, PROJECT_KEY, ISSUE_TYPE_NAME, summary, custom_fields=custom_fields, logger=logger)
                issue_key = issue.get('key', '')

                # Model 和 versions 在 Create Screen 可能不支援，改用 PUT 更新
                put_fields = {}
                if 'Model' in field_map:
                    put_fields[field_map['Model']] = [{"value": model_value}]
                affects_version = parse_affects_version(firmware_value)
                put_fields['versions'] = [{"name": affects_version}]
                try:
                    update_fields(_config, issue_key, put_fields, logger=logger)
                except Exception as e:
                    logger.log(f"[WARN] 更新 Model/versions 失敗: {e}")
                rows[i][target_col] = issue_key
                post_count += 1

                # 更新 description（需要 issue_key 才能組 FTP 路徑）
                year = datetime.now().strftime("%Y")
                ftp_url = f"ftp://{_config['ftp-host']}/jira/{year}_ML_Coredump_files/{issue_key}/"

                def _adf_para(contents):
                    return {"type": "paragraph", "content": contents}

                def _adf_empty():
                    return {"type": "paragraph", "content": []}

                def _adf_bold(text):
                    return {"type": "text", "text": text, "marks": [{"type": "strong"}]}

                def _adf_text(text):
                    return {"type": "text", "text": text}

                def _adf_link(url):
                    return {"type": "text", "text": url, "marks": [{"type": "link", "attrs": {"href": url}}]}

                def _adf_link_text(url, text):
                    return {"type": "text", "text": text, "marks": [{"type": "link", "attrs": {"href": url}}]}

                adf_content = [
                    _adf_para([_adf_text(
                        "We have identified several coredump issues on customer devices "
                        "through Elasticsearch monitoring. These incidents have been processed "
                        "by the ELK Agent and automatically synchronized to Jira for tracking."
                    )]),
                    _adf_empty(),
                    _adf_para([_adf_text("Please investigate and address these issues accordingly.")]),
                    _adf_empty(),
                    _adf_para([_adf_text(
                        "For your reference, all coredump instances identified from Elasticsearch "
                        "have been compiled into the following SharePoint document:"
                    )]),
                    _adf_para([_adf_text("\U0001f517 "), _adf_link_text(_config['sharepoint-url'], "Coredump Compilation List (SharePoint)")]),
                    _adf_empty(),
                    _adf_para([_adf_text(
                        "If you require any further clarification or technical details, "
                        "please contact Max directly."
                    )]),
                    _adf_empty(),
                    _adf_para([_adf_bold("SN: "), _adf_text(sn_value)]),
                    _adf_para([_adf_bold("Model: "), _adf_text(model_value)]),
                    _adf_para([_adf_bold("Daemon: "), _adf_text(daemon)]),
                    _adf_para([_adf_bold("Firmware: "), _adf_text(firmware_value)]),
                    _adf_empty(),
                    _adf_para([_adf_text("You can download the coredump file from FTP site:")]),
                    _adf_para([_adf_link(ftp_url)]),
                ]
                try:
                    update_description(_config, issue_key, adf_content, logger=logger)
                except Exception as e:
                    logger.log(f"[WARN] 更新 description 失敗: {e}")

                # 記錄已 post 的 SN，供後續 optools 使用
                if sn_value:
                    append_posted_sn(sn_value)

                # 更新已 post 的 daemon 記錄
                if is_its:
                    its_posted_daemons[daemon] = issue_key
                else:
                    posted_daemons[daemon] = issue_key

                # 每筆成功後立即存檔
                save_csv(csv_path, fieldnames, rows)
                update_daily_csv(row.get('_id', ''), target_col, issue_key)

            except Exception as e:
                logger.log(f"Post 失敗: {e}")
                logger.log("此筆跳過，不填入任何值。")
                fail_count += 1
        else:
            logger.log("無效輸入，跳過此筆。")
            skip_count += 1

    # 全部處理完畢
    save_csv(csv_path, fieldnames, rows)
    logger.log(f"\n{'='*60}")
    logger.log(f"結果：成功 {post_count} 筆，失敗 {fail_count} 筆，跳過 {skip_count} 筆，忽略 {ignore_count} 筆")
    logger.close()


if __name__ == "__main__":
    process_elk_summary()
