#!/usr/bin/env python3
"""
Web Automation Script - Debug Log Retrieval Tool
Uses Playwright to automate the OpTools web UI to retrieve device debug log download links.

Usage:
    python optools.py -s <serial_number> -o <output_file>
    python optools.py -s S232L52100220 -o file-link.txt
    python optools.py -s S232L52100220 -o file-link.txt --head
"""

import argparse
import os
import re
import sys
import time
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from config_loader import load_config
from logger import Logger

# ─── Config ──────────────────────────────────────────────────────────────────
_config = load_config(extra_keys=["optools-host", "optools-user", "optools-pass"])

URL_HOST = _config["optools-host"]
URL_USER_PASS = _config["optools-user"].replace("@", "%40") + ":" + _config["optools-pass"]
BASE_URL = f"https://{URL_USER_PASS}@{URL_HOST}"
DEVICE_TAB_URL = f"{BASE_URL}#tabs-device"
QUERY_TAB_URL = f"{BASE_URL}#tabs-3"

# ─── Constants ───────────────────────────────────────────────────────────────
DEFAULT_SN = "S232L52100220"
DEFAULT_OUTPUT = "file-link.txt"
MESSAGE_TEXT = "test"
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

POLL_INTERVAL_SEC = 10    # Check every 10 seconds
POLL_TIMEOUT_SEC = 180    # 3 minutes total


# ─── User Confirmation ───────────────────────────────────────────────────────
def confirm(logger, prompt):
    """Ask user for Y/N confirmation. Returns True to continue, False to abort."""
    logger.log(f"[CONFIRM] {prompt}")
    while True:
        ans = input(f"\n>>> {prompt} (Y/N): ").strip().upper()
        if ans in ("Y", "YES"):
            logger.log("[CONFIRM] User chose: YES")
            return True
        elif ans in ("N", "NO"):
            logger.log("[CONFIRM] User chose: NO")
            return False
        else:
            print("Please enter Y or N.")


# ─── Alert Handler ────────────────────────────────────────────────────────────
class AlertHandler:
    """Captures browser dialog (alert/confirm/prompt) text and auto-accepts."""

    def __init__(self, logger):
        self.logger = logger
        self.last_alert = None

    def handle(self, dialog):
        self.last_alert = dialog.message
        self.logger.log(f"[ALERT] {dialog.type}: {dialog.message}")
        dialog.accept()

    def get_last(self):
        msg = self.last_alert
        self.last_alert = None
        return msg


# ─── Main Automation ──────────────────────────────────────────────────────────
def run_automation(serial_number, output_file, headless=True):
    logger = Logger()

    logger.log(f"Serial Number : {serial_number}")
    logger.log(f"Output File   : {output_file}")
    logger.log(f"Headless      : {headless}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--ignore-certificate-errors"]
        )
        context = browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()

        alert_handler = AlertHandler(logger)
        page.on("dialog", alert_handler.handle)

        try:
            # ═══════════════════════════════════════════════════════════
            # STAGE 1 : Login & Get MAC Address
            # ═══════════════════════════════════════════════════════════
            logger.log("=" * 60)
            logger.log("STAGE 1: Login and Get MAC Address")
            logger.log("=" * 60)

            # Navigate directly to Device tab URL
            logger.log(f"Navigating directly to Device tab...")
            page.goto(DEVICE_TAB_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)
            # Remove any loading overlays
            page.evaluate("try { $('.loadingoverlay').remove(); } catch(e) {}")
            page.wait_for_timeout(1000)
            page.screenshot(path=os.path.join(LOG_DIR, "stage1_01_device_tab.png"))
            logger.log("Screenshot: stage1_01_device_tab.png")

            # The page has duplicate DOM (entire page embedded twice), causing
            # duplicate element IDs. Fill all SN inputs and ensure JS handlers
            # are initialized before clicking.

            # Enter serial number in all duplicate SN inputs
            logger.log(f"Entering SN: {serial_number}")
            sn_inputs = page.locator("#get-device-by-sn-input")
            sn_count = sn_inputs.count()
            for i in range(sn_count):
                sn_inputs.nth(i).fill(serial_number)
            logger.log(f"[OK] SN filled in {sn_count} input(s).")

            # Ensure device tab JS handlers are initialized.
            # device.js stores init as window.initDeviceTab for main.js to call,
            # but the duplicate DOM can cause main.js initialization to fail.
            page.evaluate("""(() => {
                var btn = $('#get-device-by-mac-sn-button');
                if (btn.length === 0) return;
                var events = $._data(btn[0], 'events');
                if (!(events && events.click) && typeof window.initDeviceTab === 'function') {
                    window.initDeviceTab();
                }
            })()""")

            # Click the check button
            logger.log("Clicking 'check' button to look up MAC...")
            check_btn = page.locator("#get-device-by-mac-sn-button").first
            check_btn.click(force=True)

            # Wait for result div to have content
            logger.log("Waiting for device query result...")
            poll_start = time.time()
            result_text = ""
            while time.time() - poll_start < 30:
                result_text = page.evaluate("$('#get-device-result').text().trim()")
                if result_text:
                    logger.log("[OK] Result appeared.")
                    break
                page.wait_for_timeout(1000)
            else:
                logger.log("[WARN] Result did not appear within 30s.")

            # Remove loading overlay if still present
            page.evaluate("try { $('.loadingoverlay').remove(); } catch(e) {}")
            page.screenshot(path=os.path.join(LOG_DIR, "stage1_03_mac_result.png"))
            logger.log("Screenshot: stage1_03_mac_result.png")

            # Read result HTML
            result_html = page.evaluate("$('#get-device-result').html() || ''")
            
            logger.log("--- DEVICE INFORMATION ---")
            logger.log(f"Raw text:\n{result_text}")
            logger.log("--------------------------")

            logger.log(f"Device result HTML: {result_html[:500] if result_html else '(empty)'}")

            # Parse mac_address
            mac_match = re.search(r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', result_text)
            mac_address = mac_match.group(0) if mac_match else None

            # Parse model_name
            model_match = re.search(r'model_name["\s:]+([^\s,"<>\\]+)', result_text, re.IGNORECASE)
            model_name = model_match.group(1) if model_match else None

            # Parse serial_number
            sn_match = re.search(r'serial_number["\s:]+([^\s,"<>\\]+)', result_text, re.IGNORECASE)
            result_sn = sn_match.group(1) if sn_match else None
            
            # Parse org
            org_match = re.search(r'org(?:_name)?["\s:]+([^\n,"<>]+)', result_text, re.IGNORECASE)
            org_name = org_match.group(1).strip() if org_match else None
            
            # Parse site
            site_match = re.search(r'site(?:_name)?["\s:]+([^\n,"<>]+)', result_text, re.IGNORECASE)
            site_name = site_match.group(1).strip() if site_match else None

            logger.log(f"Parsed Org           : {org_name}")
            logger.log(f"Parsed Site          : {site_name}")
            logger.log(f"Parsed mac_address   : {mac_address}")
            logger.log(f"Parsed model_name    : {model_name}")
            logger.log(f"Parsed serial_number : {result_sn}")



            if mac_address:
                logger.log(f"[OK] MAC Address found: {mac_address}")
                # Verify serial_number matches
                if result_sn and result_sn != serial_number:
                    logger.log(f"[WARN] Warning: result SN '{result_sn}' differs from input SN '{serial_number}'")
            else:
                logger.log("[FAIL] Failed to find MAC address in result!")
                page.screenshot(path=os.path.join(LOG_DIR, "stage1_error_no_mac.png"))
                logger.log("Screenshot: stage1_error_no_mac.png")

                # ★ Breakpoint 1: MAC not found
                ##if not confirm(logger, "MAC address not found. Continue anyway? (will abort if No)"):
                logger.log("User aborted at Stage 1.")
                write_output(output_file, "FAILED: MAC address not found.", logger)
                return

            # ★ Breakpoint 1: Confirm MAC
            if mac_address:
                info = f"Org: {org_name}, Site: {site_name}, MAC: {mac_address}, Model: {model_name}, SN: {result_sn}"
                ##if not confirm(logger, f"Device Info:\n{info}\nContinue to upload?"):
                ##    logger.log("User aborted at Stage 1.")
                ##    write_output(output_file, f"Aborted after MAC retrieval. {info}", logger)
                ##    return
                with open(os.path.join(LOG_DIR, "mac_address.txt"), "w", encoding="utf-8") as f:
                    f.write(mac_address)

            return
		

            # ═══════════════════════════════════════════════════════════
            # STAGE 2 : Fill form & Upload on Query Debug Log tab
            # ═══════════════════════════════════════════════════════════
            logger.log("=" * 60)
            logger.log("STAGE 2: Fill form and Upload debug log request")
            logger.log("=" * 60)

            # Navigate directly to Query Debug Log tab URL

            # Close current session and start fresh to avoid interference
            _browser = page.context.browser
            page.context.close()
            page = _browser.new_page()

            logger.log("Navigating to 'Query Device's Debug Log' tab...")
            page.goto(QUERY_TAB_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)

            # Remove any loading overlays
            page.evaluate("document.querySelectorAll('.loadingoverlay').forEach(el => el.remove());")
            page.wait_for_timeout(1000)
            page.screenshot(path=os.path.join(LOG_DIR, "stage2_01_query_tab.png"))
            logger.log("Screenshot: stage2_01_query_tab.png")

            # Fill MAC address
            if mac_address:
                logger.log(f"Filling MAC: {mac_address}")
                page.locator("#detail-log-mac").last.fill(mac_address)
            else:
                logger.log("Skipping MAC field (not found).")

            # Fill Serial Number
            logger.log(f"Filling SN: {serial_number}")
            page.locator("#detail-log-sn").last.fill(serial_number)

            # Fill message
            logger.log(f"Filling message: {MESSAGE_TEXT}")
            page.locator("#detail-log-textarea").last.fill(MESSAGE_TEXT)

            page.screenshot(path=os.path.join(LOG_DIR, "stage2_02_form_filled.png"))
            logger.log("Screenshot: stage2_02_form_filled.png")

            # ★ Breakpoint 2: Confirm upload
            ##if not confirm(logger, "Form filled. Click 'upload' to submit?"):
            logger.log("User aborted at Stage 2.")
            write_output(output_file, "Aborted before upload.", logger)
            return

            # debug start
            with open(os.path.join(LOG_DIR, "page2.txt"), "w", encoding="utf-8") as f:
                f.write(page.content())
            # debug end

            # Click upload
            logger.log("Clicking 'upload' button...")
            upload_btn = page.locator("#detail-log-upload").last
            logger.log(f"Targeting upload button. Count found: {page.locator('#detail-log-upload').count()}")
            upload_btn.click()
            
            # Handle any alert popup from upload (Verify "Succeed!")
            logger.log("Waiting for upload popup...")
            # We wait for the alert_handler to capture something
            start_wait = time.time()
            while time.time() - start_wait < 10:
                last_alert = alert_handler.get_last()
                if last_alert:
                    logger.log(f"Upload popup received: '{last_alert}'")
                    if "Succeed!" in last_alert:
                        logger.log("[OK] Upload verification: Succeed!")
                    else:
                        logger.log(f"[WARN] Upload verification: Unexpected message '{last_alert}'")
                    break
                page.wait_for_timeout(500)
            else:
                logger.log("[WARN] No upload popup detected after 10 seconds.")

            page.screenshot(path=os.path.join(LOG_DIR, "stage2_03_after_upload.png"))
            logger.log("Screenshot: stage2_03_after_upload.png")
            logger.log("Upload submitted. Waiting before checking result...")

            # ═══════════════════════════════════════════════════════════
            # STAGE 3 : Press check & Poll for download link
            # ═══════════════════════════════════════════════════════════
            logger.log("=" * 60)
            logger.log("STAGE 3: Check and poll for download link")
            logger.log("=" * 60)

            final_link = None
            total_waited = 0
            attempt = 0
            keep_polling = True

            while keep_polling:
                # Click the 'check' button
                logger.log(f"Attempt {attempt + 1}: Clicking 'check' button...")
                page.locator("#detail-log-check").last.click()
                page.wait_for_timeout(POLL_INTERVAL_SEC * 1000)
                total_waited += POLL_INTERVAL_SEC
                attempt += 1

                # Handle alerts
                last_alert = alert_handler.get_last()
                if last_alert:
                    logger.log(f"Check alert: {last_alert}")

                # Check for the result link
                link_el = page.locator("#detail-log-check-result-a").last
                href = link_el.get_attribute("href")
                link_text = link_el.inner_text()
                result_text = page.locator("#detail-log-check-result").last.inner_text()

                logger.log(f"  Result text: '{result_text}'")
                logger.log(f"  Link href : '{href}'")
                logger.log(f"  Link text : '{link_text}'")

                if href and href.strip() and href != "#" and href != "":
                    final_link = href.strip()
                    logger.log("[OK] SUCCESS! Download link found: {final_link}")
                    break

                # Take periodic screenshots
                if attempt % 3 == 0:
                    ss_path = os.path.join(LOG_DIR, f"stage3_poll_{attempt}.png")
                    page.screenshot(path=ss_path)
                    logger.log(f"Screenshot: {ss_path}")

                logger.log(f"  Waited {total_waited}s / {POLL_TIMEOUT_SEC}s")

                # ★ Breakpoint 3: Timeout check
                if total_waited >= POLL_TIMEOUT_SEC:
                    logger.log(f"Polling timeout reached ({POLL_TIMEOUT_SEC}s).")
                    page.screenshot(path=os.path.join(LOG_DIR, "stage3_timeout.png"))
                    logger.log("Screenshot: stage3_timeout.png")

                    if confirm(logger, f"Timeout after {total_waited}s. Keep waiting another {POLL_TIMEOUT_SEC}s?"):
                        total_waited = 0
                        logger.log("User chose to continue polling.")
                    else:
                        logger.log("User chose to stop polling.")
                        keep_polling = False

            # ─── Write output ─────────────────────────────────────────
            if final_link:
                write_output(output_file, final_link, logger)
                logger.log(f"Download link saved to: {output_file}")
            else:
                write_output(output_file, "FAILED: No download link found after polling.", logger)
                logger.log("No download link found.")

            page.screenshot(path=os.path.join(LOG_DIR, "stage3_final.png"))
            logger.log("Screenshot: stage3_final.png")
            logger.log("Execution complete.")

        except PlaywrightTimeout as e:
            logger.log(f"[ERROR] Playwright timeout: {e}")
            page.screenshot(path=os.path.join(LOG_DIR, "error_timeout.png"))
            write_output(output_file, f"FAILED: Timeout - {e}", logger)
        except Exception as e:
            logger.log(f"[ERROR] Unexpected error: {e}")
            try:
                page.screenshot(path=os.path.join(LOG_DIR, "error_unexpected.png"))
            except Exception:
                pass
            write_output(output_file, f"FAILED: {e}", logger)
        finally:
            logger.log("Closing browser...")
            context.close()
            browser.close()
            logger.close()


def write_output(output_file, content, logger):
    """Write content to the output file."""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)
    logger.log(f"Output written to: {output_file}")


# ─── Entry point ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Automate debug log retrieval from OpTools web UI."
    )
    parser.add_argument(
        "-s", "--serial",
        default=DEFAULT_SN,
        help=f"Device serial number (default: {DEFAULT_SN})"
    )
    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output file path for the download link (default: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--head",
        action="store_true",
        default=False,
        help="Run browser in headed mode (default: headless)"
    )
    args = parser.parse_args()

    run_automation(
        serial_number=args.serial,
        output_file=args.output,
        headless=not args.head
    )


if __name__ == "__main__":
    main()
