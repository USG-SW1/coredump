#!/usr/bin/env python3
"""
Download Link Script - Retrieve debug log download link from OpTools.
Reads sn.txt and mac.txt, fills the "Query Device's Debug Log" form,
uploads, waits for success, clicks check, and saves the file link.

Usage:
    python optools-download.py
    python optools-download.py --head
"""

import argparse
import csv
import os
import sys
import time

import requests
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from config_loader import load_config
from csv_helper import load_csv, save_csv, find_jira_in_csv, update_daily_csv
from jira_api import delete_jira_issue
from logger import Logger

# ─── Config ──────────────────────────────────────────────────────────────────
_config = load_config(extra_keys=["optools-host", "optools-user", "optools-pass"])

URL_HOST = _config["optools-host"]
URL_USER = _config["optools-user"]
URL_PASS = _config["optools-pass"]
URL_USER_PASS = URL_USER.replace("@", "%40") + ":" + URL_PASS
BASE_URL = f"https://{URL_USER_PASS}@{URL_HOST}"
QUERY_TAB_URL = f"{BASE_URL}#tabs-3"

DOWNLOAD_TIMEOUT = _config["download-timeout"]
DOWNLOAD_RETRIES = _config["download-retries"]
DOWNLOAD_RETRY_DELAY = _config["download-retry-delay"]

# ─── Constants ───────────────────────────────────────────────────────────────
MESSAGE_TEXT = "test"
OUTPUT_FILE = "file-link.txt"
DOWNLOAD_DIR = "coredumps"
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
POLL_INTERVAL_SEC = _config.get("poll-interval", 5)
POLL_TIMEOUT_SEC = _config.get("poll-timeout", 120)


def read_input(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def extract_coredump_info(target):
    """從 target 路徑取得檔名，移除最前面 14 個字元（日期時間）"""
    filename = os.path.basename(target)
    return filename[14:] if len(filename) > 14 else filename


SKIP_JIRA_VALUES = ("", "Skip", "Fail", "OPTOOLS fail", "OPTOOLS mis-match")


def lookup_sn_in_csv(sn):
    """Look up serial number in ELK-summary.csv and return all matching rows."""
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ELK-summary.csv")
    matches = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("sn", "").strip() == sn:
                matches.append(row)
    return matches


def _resolve_jira_id(row):
    """從 row 中找出有效的 jira-id，回傳 (jira_id, column_name) 或 ('', '')。"""
    for col in ["jira-id", "related-jira-id", "ITS-jira-id", "ITS-related-jira-id"]:
        val = (row.get(col) or "").strip()
        if val and val not in SKIP_JIRA_VALUES:
            return val, col
    return "", ""


def resolve_download_path(sn, logger):
    """Use SN to find jira-id and target from ELK-summary.csv, return (dest_dir, filename)."""
    rows = lookup_sn_in_csv(sn)
    if not rows:
        logger.log(f"[WARN] SN '{sn}' not found in ELK-summary.csv, using default path.")
        return None, None

    # 從所有匹配的 row 中，找第一筆有有效 jira-id 的
    row = None
    resolved_jira_id = ""
    for r in rows:
        jid, _ = _resolve_jira_id(r)
        if jid:
            row = r
            resolved_jira_id = jid
            break

    if not row or not resolved_jira_id:
        logger.log(f"[WARN] No valid jira-id found for SN '{sn}' ({len(rows)} rows checked), using default path.")
        return None, None

    # Extract filename from target
    target = (row.get("target") or "").strip()
    daemon = (row.get("daemon") or "").strip()
    if not target:
        logger.log(f"[WARN] No target found for SN '{sn}', using default path.")
        return None, None

    filename = extract_coredump_info(target)
    dest_dir = os.path.join(DOWNLOAD_DIR, resolved_jira_id)

    logger.log(f"  SN:       {sn}")
    logger.log(f"  Jira ID:  {resolved_jira_id}")
    logger.log(f"  Daemon:   {daemon}")
    logger.log(f"  Target:   {target}")
    logger.log(f"  Filename: {filename}")

    return dest_dir, filename


def mark_download_fail(sn, logger):
    """Download 失敗時：刪除該 SN 所有相關的 Jira issues，並將 CSV 中的 jira-id 標記為 'OPTOOLS fail'。"""
    rows = lookup_sn_in_csv(sn)
    if not rows:
        logger.log(f"[FAIL] SN '{sn}' not found in CSV, skip.")
        return

    # 收集該 SN 所有有效的 jira-id（主 jira-id，不含 related）
    jira_targets = []  # list of (jira_id, jira_col, record_id)
    for r in rows:
        for col in ["jira-id", "ITS-jira-id"]:
            val = (r.get(col) or "").strip()
            if val and val not in SKIP_JIRA_VALUES:
                rid = (r.get("_id") or "").strip()
                jira_targets.append((val, col, rid))

    if not jira_targets:
        logger.log(f"[FAIL] No valid Jira ID to process for SN '{sn}'.")
        return

    unique_jira_ids = list(dict.fromkeys(jid for jid, _, _ in jira_targets))
    logger.log(f"[FAIL] Download failed for SN '{sn}', processing {len(unique_jira_ids)} Jira(s): {', '.join(unique_jira_ids)}...")

    # 1. Delete all Jira issues
    for jira_id in unique_jira_ids:
        if delete_jira_issue(_config, jira_id, logger=logger):
            logger.log(f"[FAIL] Jira '{jira_id}' deleted.")
        else:
            logger.log(f"[FAIL] Failed to delete Jira '{jira_id}', marking as 'OPTOOLS fail' anyway.")

    # 2. Mark all jira-id entries as 'OPTOOLS fail' in ELK-summary.csv
    csv_path, fieldnames, all_rows = load_csv()
    for jira_id, jira_col, _ in jira_targets:
        for r in all_rows:
            if r.get("sn", "").strip() == sn and r.get(jira_col, "").strip() == jira_id:
                r[jira_col] = "OPTOOLS fail"
    save_csv(csv_path, fieldnames, all_rows)
    logger.log(f"[FAIL] Marked {len(jira_targets)} jira-id(s) as 'OPTOOLS fail' in ELK-summary.csv for SN '{sn}'.")

    # 3. Mark all jira-id entries as 'OPTOOLS fail' in daily CSV
    for jira_id, jira_col, record_id in jira_targets:
        if record_id:
            update_daily_csv(record_id, jira_col, "OPTOOLS fail")
            logger.log(f"[FAIL] Marked '{jira_col}' as 'OPTOOLS fail' in daily CSV for _id '{record_id}'.")

    # 4. Also mark related-jira-id entries that reference any of these jira-ids as 'OPTOOLS fail'
    csv_path, fieldnames, all_rows = load_csv()
    marked_related = 0
    for jira_id in unique_jira_ids:
        for related_col in ["related-jira-id", "ITS-related-jira-id"]:
            for r in all_rows:
                if r.get(related_col, "").strip() == jira_id:
                    rid = (r.get("_id") or "").strip()
                    r[related_col] = "OPTOOLS fail"
                    marked_related += 1
                    if rid:
                        update_daily_csv(rid, related_col, "OPTOOLS fail")
    if marked_related:
        save_csv(csv_path, fieldnames, all_rows)
        logger.log(f"[FAIL] Marked {marked_related} related-jira-id reference(s) as 'OPTOOLS fail' in CSV.")

    logger.log(f"[FAIL] Mark complete for SN '{sn}'.")


def js_fill_and_upload(page, mac, sn, message):
    """Use JavaScript to fill the FIRST set of form fields and click upload.
    The page has duplicate #tabs-3 divs; the first has working JS bindings
    but is not visible, so we must use JS to set values and trigger click."""
    return page.evaluate(f"""
    (() => {{
        // Get the first instance of each element (the one with JS bindings)
        const macInput = document.getElementById('detail-log-mac');
        const snInput = document.getElementById('detail-log-sn');
        const msgInput = document.getElementById('detail-log-textarea');

        if (!macInput || !snInput || !msgInput) {{
            return 'ERROR: form fields not found';
        }}

        macInput.value = '{mac}';
        snInput.value = '{sn}';
        msgInput.value = '{message}';

        // Trigger input events so any JS watchers pick up the values
        macInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
        snInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
        msgInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
        macInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
        snInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
        msgInput.dispatchEvent(new Event('change', {{ bubbles: true }}));

        return 'OK: fields filled - mac=' + macInput.value + ' sn=' + snInput.value;
    }})()
    """)


def download_file(url, logger, sn=None):
    """Download the file from the given URL with retry support.
    If sn is provided, use ELK-summary.csv to determine the destination path and filename."""
    dest_dir, filename = None, None
    if sn:
        dest_dir, filename = resolve_download_path(sn, logger)

    if not dest_dir or not filename:
        dest_dir = DOWNLOAD_DIR
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path) or "debug_log"

    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, filename)

    logger.log(f"Downloading: {url}")
    logger.log(f"Saving to  : {dest}")
    logger.log(f"Config: timeout={DOWNLOAD_TIMEOUT}s, retries={DOWNLOAD_RETRIES}, delay={DOWNLOAD_RETRY_DELAY}s")

    last_error = None
    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        try:
            resp = requests.get(url, verify=False, timeout=DOWNLOAD_TIMEOUT, stream=True,
                                auth=(URL_USER, URL_PASS))
            resp.raise_for_status()

            total = 0
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
                    total += len(chunk)

            size_kb = total / 1024
            logger.log(f"[OK] Downloaded {size_kb:.1f} KB -> {dest}")
            return dest

        except (requests.RequestException, IOError) as e:
            last_error = e
            if attempt < DOWNLOAD_RETRIES:
                logger.log(f"[WARN] Download attempt {attempt}/{DOWNLOAD_RETRIES} failed: {e}")
                logger.log(f"  Retrying in {DOWNLOAD_RETRY_DELAY}s...")
                time.sleep(DOWNLOAD_RETRY_DELAY)
            else:
                logger.log(f"[ERROR] Download failed after {DOWNLOAD_RETRIES} attempts: {e}")

    raise last_error


def main():
    parser = argparse.ArgumentParser(description="Download debug log from OpTools.")
    parser.add_argument("-s", "--serial", help="Device serial number (overrides sn.txt)")
    parser.add_argument("-m", "--mac", help="Device MAC address (overrides mac.txt)")
    parser.add_argument("--head", action="store_true", default=False, help="Run browser in headed mode (default: headless)")
    args = parser.parse_args()

    logger = Logger()
    os.makedirs(LOG_DIR, exist_ok=True)

    sn = args.serial if args.serial else read_input("sn.txt")
    mac = args.mac if args.mac else read_input("mac.txt")
    headless = not args.head
    logger.log(f"SN : {sn}")
    logger.log(f"MAC: {mac}")

    download_ok = False
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--ignore-certificate-errors"],
        )
        context = browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        # Auto-accept dialogs and capture their text
        last_alert = {"msg": None}

        def on_dialog(dialog):
            last_alert["msg"] = dialog.message
            logger.log(f"[DIALOG] {dialog.type}: {dialog.message}")
            dialog.accept()

        page.on("dialog", on_dialog)

        try:
            # ── Navigate to Query Debug Log tab ──────────────────────
            logger.log("Navigating to 'Query Device's Debug Log' tab...")
            page.goto(QUERY_TAB_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(3000)
            # Remove loading overlays
            page.evaluate(
                "document.querySelectorAll('.loadingoverlay').forEach(el => el.remove());"
            )
            page.wait_for_timeout(1000)

            # ── Fill form via jQuery (matching how the page reads values) ─
            logger.log("Filling form via jQuery...")
            page.evaluate(f"""
            (() => {{
                $('#detail-log-mac').val('{mac}');
                $('#detail-log-sn').val('{sn}');
                $('#detail-log-textarea').val('{MESSAGE_TEXT}');
                console.log('jQuery fill done: mac=' + $('#detail-log-mac').val()
                    + ' sn=' + $('#detail-log-sn').val()
                    + ' msg=' + $('#detail-log-textarea').val());
            }})()
            """)

            # Verify values
            verify = page.evaluate("""
            (() => ({
                mac: $('#detail-log-mac').val(),
                sn: $('#detail-log-sn').val(),
                msg: $('#detail-log-textarea').val()
            }))()
            """)
            logger.log(f"Verified: mac={verify['mac']} sn={verify['sn']} msg={verify['msg']}")

            page.screenshot(path=os.path.join(LOG_DIR, "dl_form_filled.png"))

            # ── Monitor network requests ─────────────────────────────
            def on_request(request):
                if "dev-troubleshoot" in request.url:
                    logger.log(f"[NET] Request: {request.method} {request.url}")

            def on_response(response):
                if "dev-troubleshoot" in response.url:
                    logger.log(f"[NET] Response: {response.status} {response.url}")

            page.on("request", on_request)
            page.on("response", on_response)

            # ── Patch LoadingOverlay if missing (dual jQuery issue) ──
            page.evaluate("""
                if (!$.LoadingOverlay) {
                    $.LoadingOverlay = function() {};
                    console.log('Patched $.LoadingOverlay as no-op');
                }
            """)

            # ── Call upload function directly ─────────────────────────
            logger.log("Calling trigger_device_upload_log() directly...")
            last_alert["msg"] = None
            page.evaluate("trigger_device_upload_log()")

            # Wait for alert
            logger.log("Waiting for alert...")
            start = time.time()
            success = False
            while time.time() - start < 30:
                if last_alert["msg"]:
                    logger.log(f"Alert received: '{last_alert['msg']}'")
                    if "Succeed" in last_alert["msg"] or "Success" in last_alert["msg"]:
                        logger.log("[OK] Upload succeeded!")
                        success = True
                    break
                page.wait_for_timeout(500)
            else:
                logger.log("[WARN] No alert after 30s.")

            page.screenshot(path=os.path.join(LOG_DIR, "dl_after_upload.png"))

            if not success:
                logger.log("Upload may not have succeeded. Continuing to check anyway...")

            # ── Read key path (element ID is 'key-path') ────────────
            key_path = page.evaluate("$('#key-path').val() || 'not found'")
            logger.log(f"Key path: '{key_path}'")

            # ── Click check and poll for file link ───────────────────
            logger.log("Polling for download link...")
            final_link = None
            total_waited = 0
            attempt = 0

            while total_waited < POLL_TIMEOUT_SEC:
                attempt += 1
                logger.log(f"Attempt {attempt}: calling check_device_log()...")
                last_alert["msg"] = None
                page.evaluate("check_device_log()")
                page.wait_for_timeout(POLL_INTERVAL_SEC * 1000)
                total_waited += POLL_INTERVAL_SEC

                # Check alert
                if last_alert["msg"]:
                    logger.log(f"  Alert: {last_alert['msg']}")

                # Read result from first element via JS
                check_result = page.evaluate("""
                    (() => {
                        const span = document.getElementById('detail-log-check-result');
                        const a = document.getElementById('detail-log-check-result-a');
                        return {
                            text: span ? span.innerText : '',
                            href: a ? (a.getAttribute('href') || '') : '',
                            linkText: a ? a.innerText : ''
                        };
                    })()
                """)

                result_text = check_result.get("text", "")
                href = check_result.get("href", "")
                link_text = check_result.get("linkText", "")

                logger.log(f"  Result: '{result_text}'")
                logger.log(f"  Href  : '{href}'")
                logger.log(f"  Link  : '{link_text}'")

                page.screenshot(path=os.path.join(LOG_DIR, "dl_check.png"))

                if href and href.strip() and not href.endswith("#") and "index.html" not in href:
                    final_link = href.strip()
                    logger.log(f"[OK] Download link found: {final_link}")
                    break

                logger.log(f"  Waited {total_waited}s / {POLL_TIMEOUT_SEC}s")

            # ── Save result ──────────────────────────────────────────
            download_ok = False
            if final_link:
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    f.write(final_link)
                logger.log(f"Download link saved to: {OUTPUT_FILE}")

                # ── Download the file ────────────────────────────────
                try:
                    download_file(final_link, logger, sn=sn)
                    download_ok = True
                except Exception as e:
                    logger.log(f"[ERROR] Download failed: {e}")
            else:
                logger.log("FAILED: No download link found after polling.")
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    f.write("FAILED: No download link found.")

            page.screenshot(path=os.path.join(LOG_DIR, "dl_final.png"))

            if not download_ok:
                mark_download_fail(sn, logger)
            else:
                logger.log("Done.")

        except PlaywrightTimeout as e:
            logger.log(f"[ERROR] Timeout: {e}")
            page.screenshot(path=os.path.join(LOG_DIR, "dl_error.png"))
            mark_download_fail(sn, logger)
            download_ok = False
        except Exception as e:
            logger.log(f"[ERROR] {e}")
            try:
                page.screenshot(path=os.path.join(LOG_DIR, "dl_error.png"))
            except Exception:
                pass
            mark_download_fail(sn, logger)
            download_ok = False
        finally:
            context.close()
            browser.close()

    logger.close()
    if not download_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
