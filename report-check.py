#!/usr/bin/env python3
"""Report: verify Jira issues and FTP files for valid jira-ids in ELK-summary.csv."""

import ftplib
import os
from datetime import datetime
from config_loader import load_config
from csv_helper import load_csv, JIRA_ID_COLUMNS
from jira_api import check_issue_exists
from logger import Logger

_config = load_config(extra_keys=["ftp-host", "ftp-user", "ftp-pass"])

YEAR = datetime.now().strftime("%Y")
REMOTE_BASE_DIR = f"./jira/{YEAR}_ML_Coredump_files"
SKIP_VALUES = ("", "Skip", "Fail", "OPTOOLS fail", "OPTOOLS mis-match")


def get_ftp_folders(ftp, base_dir):
    """取得 FTP base_dir 下所有子目錄名稱，回傳 dict: folder_name -> set of filenames"""
    folders = {}
    try:
        entries = ftp.nlst(base_dir)
    except ftplib.error_perm:
        return folders

    for entry in entries:
        name = os.path.basename(entry)
        path = f"{base_dir}/{name}"
        # 嘗試列出內容，能列出就是目錄
        try:
            files = ftp.nlst(path)
            filenames = {os.path.basename(f) for f in files if os.path.basename(f) != name}
            folders[name] = filenames
        except ftplib.error_perm:
            pass
    return folders


def main():
    logger = Logger()
    _, _, rows = load_csv()

    # 收集所有有效的 jira-id（去重）
    jira_ids = {}  # jira_id -> [(row_index, col_name, sn, daemon, model)]
    for i, row in enumerate(rows):
        for col in JIRA_ID_COLUMNS:
            jid = row.get(col, "").strip()
            if jid and jid not in SKIP_VALUES:
                sn = row.get("sn", "").strip()
                daemon = row.get("daemon", "").strip()
                model = row.get("model", "").strip()
                if jid not in jira_ids:
                    jira_ids[jid] = []
                jira_ids[jid].append((i, col, sn, daemon, model))

    unique_ids = sorted(jira_ids.keys())
    total = len(unique_ids)
    logger.log(f"ELK-summary.csv 中有 {total} 個有效 Jira ID")

    if total == 0:
        logger.log("沒有需要檢查的項目。")
        logger.close()
        return

    # 連線 FTP，取得所有資料夾
    logger.log(f"連線 FTP: {_config['ftp-host']} ...")
    try:
        ftp = ftplib.FTP(_config["ftp-host"])
        ftp.login(_config["ftp-user"], _config["ftp-pass"])
        ftp_folders = get_ftp_folders(ftp, REMOTE_BASE_DIR)
        logger.log(f"FTP 上共有 {len(ftp_folders)} 個資料夾")
    except ftplib.all_errors as e:
        logger.log(f"[ERROR] FTP 連線失敗: {e}")
        ftp = None
        ftp_folders = {}

    # 逐筆檢查
    jira_ok = 0
    jira_fail = 0
    ftp_ok = 0
    ftp_fail = 0
    problems = []

    for idx, jid in enumerate(unique_ids, 1):
        entries = jira_ids[jid]
        # 取第一筆的資訊作為代表
        _, col, sn, daemon, model = entries[0]
        is_related = "related" in col

        # 檢查 Jira
        exists, status = check_issue_exists(_config, jid)
        if exists:
            jira_ok += 1
            jira_status = f"OK ({status})"
        else:
            jira_fail += 1
            jira_status = "NOT FOUND"
            problems.append(f"  {jid}: Jira issue 不存在 (SN: {sn}, daemon: {daemon})")

        # 檢查 FTP（只檢查主 jira-id，related 不需要有自己的 FTP 資料夾）
        if is_related:
            ftp_status = "skip (related)"
        elif jid in ftp_folders:
            files = ftp_folders[jid]
            if files:
                ftp_ok += 1
                ftp_status = f"OK ({len(files)} file(s))"
            else:
                ftp_fail += 1
                ftp_status = "EMPTY"
                problems.append(f"  {jid}: FTP 資料夾存在但沒有檔案 (SN: {sn}, daemon: {daemon})")
        else:
            ftp_fail += 1
            ftp_status = "NOT FOUND"
            problems.append(f"  {jid}: FTP 資料夾不存在 (SN: {sn}, daemon: {daemon})")

        logger.log(f"  ({idx}/{total}) {jid}  Jira: {jira_status}  FTP: {ftp_status}")

    # 關閉 FTP
    if ftp:
        try:
            ftp.quit()
        except ftplib.all_errors:
            ftp.close()

    # 結果摘要
    logger.log(f"\n{'='*60}")
    logger.log(f"Report Summary")
    logger.log(f"  Jira: {jira_ok} OK, {jira_fail} failed")
    logger.log(f"  FTP:  {ftp_ok} OK, {ftp_fail} failed (related 不計入)")
    if problems:
        logger.log(f"\nProblems ({len(problems)}):")
        for p in problems:
            logger.log(p)
    else:
        logger.log("\nAll checks passed!")
    logger.log(f"{'='*60}")

    logger.close()


if __name__ == "__main__":
    main()
