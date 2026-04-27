#!/usr/bin/env python3
"""
Test 4: Debug script upload 400 error via Playwright.
- Capture the exact 400 response body
- Try different approaches: with/without script, check response content
- Also download the no-script file and check what it is
"""
import os
import re
import time
import json
import subprocess
from config_loader import load_config
from playwright.sync_api import sync_playwright

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHOTS_DIR = os.path.join(SCRIPT_DIR, "test_shots")
os.makedirs(SHOTS_DIR, exist_ok=True)

_config = load_config(extra_keys=["optools-host", "optools-user", "optools-pass"])
_optools_user = _config["optools-user"]
_optools_pass = _config["optools-pass"]
_optools_host = _config["optools-host"]
_optools_user_encoded = _optools_user.replace("@", "%40") + ":" + _optools_pass
OPTOOLS_BASE_URL = f"https://{_optools_user_encoded}@{_optools_host}"
OPTOOLS_QUERY_TAB = f"{OPTOOLS_BASE_URL}#tabs-3"

SN = "S252L19100948"
MAC = "70:49:A2:4C:36:86"
DATETIME_PREFIX = "260413-184509"


def main():
    sh_path = os.path.join(SCRIPT_DIR, f"{DATETIME_PREFIX}.zysh")
    with open(os.path.join(SCRIPT_DIR, "temp.zysh"), "r") as f:
        content = f.read()
    with open(sh_path, "w") as f:
        f.write(content.replace("<date-time>", DATETIME_PREFIX))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--ignore-certificate-errors"])
        context = browser.new_context(ignore_https_errors=True, viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        page.goto(OPTOOLS_QUERY_TAB, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        page.evaluate("document.querySelectorAll('.loadingoverlay').forEach(el => el.remove());")
        page.wait_for_timeout(1000)

        # === Test A: Upload WITH script, capture response body ===
        print("=== Test A: Upload WITH script file ===")
        page.evaluate(f"""(() => {{
            $('#detail-log-mac').val('{MAC}');
            $('#detail-log-sn').val('{SN}');
            $('#detail-log-textarea').val('test');
        }})()""")
        page.evaluate("if (!$.LoadingOverlay) { $.LoadingOverlay = function() {}; }")

        # Set script
        page.locator("#script-upload").first.set_input_files(sh_path)
        page.wait_for_timeout(500)

        # Intercept the POST response
        captured = {"body": None, "status": None}
        def on_response(resp):
            if "dev-troubleshoot/do" in resp.url:
                captured["status"] = resp.status
                try:
                    captured["body"] = resp.text()
                except:
                    captured["body"] = "(cannot read)"
                print(f"  [RESP] {resp.status} body: {captured['body'][:500]}")
        page.on("response", on_response)

        last_alert = {"msg": None}
        def on_dialog(dialog):
            last_alert["msg"] = dialog.message
            print(f"  [DIALOG] {dialog.message}")
            dialog.accept()
        page.on("dialog", on_dialog)

        page.evaluate("trigger_device_upload_log()")
        time.sleep(10)
        print(f"  Result: status={captured['status']} alert={last_alert['msg']}")
        print(f"  Response body: {captured['body']}")

        # === Test B: Reload, no script, get download, check file type ===
        print("\n=== Test B: Upload WITHOUT script, download and check file ===")
        page.goto(OPTOOLS_QUERY_TAB, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        page.evaluate("document.querySelectorAll('.loadingoverlay').forEach(el => el.remove());")
        page.wait_for_timeout(1000)

        page.evaluate(f"""(() => {{
            $('#detail-log-mac').val('{MAC}');
            $('#detail-log-sn').val('{SN}');
            $('#detail-log-textarea').val('test');
        }})()""")
        page.evaluate("if (!$.LoadingOverlay) { $.LoadingOverlay = function() {}; }")

        # Remove old listeners
        page.remove_listener("response", on_response)

        def on_response2(resp):
            if "dev-troubleshoot" in resp.url:
                try:
                    body = resp.text()[:300]
                except:
                    body = ""
                print(f"  [RESP] {resp.status} {resp.url[-80:]} body={body}")
        page.on("response", on_response2)

        last_alert["msg"] = None
        page.evaluate("trigger_device_upload_log()")
        start = time.time()
        while time.time() - start < 30:
            if last_alert["msg"]:
                break
            page.wait_for_timeout(500)
        print(f"  Alert: {last_alert['msg']}")

        key_path = page.evaluate("$('#key-path').val() || 'not found'")
        print(f"  Key path: {key_path}")

        if "Succeed" in str(last_alert["msg"]):
            # Poll and download
            for attempt in range(1, 15):
                last_alert["msg"] = None
                page.evaluate("check_device_log()")
                page.wait_for_timeout(15000)

                check_result = page.evaluate("""(() => {
                    const a = document.getElementById('detail-log-check-result-a');
                    return a ? (a.getAttribute('href') || '') : '';
                })()""")

                if check_result and check_result.strip() and not check_result.endswith("#"):
                    download_url = check_result.strip()
                    print(f"  [OK] Download link: {download_url}")

                    # Download the file
                    import requests as req
                    dl = req.get(download_url, auth=(
                        _config["optools-user"], _config["optools-pass"]
                    ), verify=False, timeout=120)
                    dl_path = os.path.join(SCRIPT_DIR, "test_download.bin")
                    with open(dl_path, 'wb') as f:
                        f.write(dl.content)
                    print(f"  Downloaded {len(dl.content)} bytes")

                    # Check file type
                    ft = subprocess.run(['file', dl_path], capture_output=True, text=True)
                    print(f"  File type: {ft.stdout.strip()}")

                    # Magic bytes
                    with open(dl_path, 'rb') as f:
                        magic = f.read(16)
                    print(f"  Magic: {magic.hex()} = {magic[:8]}")

                    # Try unzip
                    uz = subprocess.run(['unzip', '-l', dl_path], capture_output=True, text=True)
                    if uz.returncode == 0:
                        print(f"  unzip -l:\n{uz.stdout[:500]}")
                    else:
                        print(f"  unzip failed: {uz.stderr[:200]}")

                    # Try tar
                    tar = subprocess.run(['tar', 'tzf', dl_path], capture_output=True, text=True)
                    if tar.returncode == 0:
                        print(f"  tar tzf:\n{tar.stdout[:500]}")
                    else:
                        tar2 = subprocess.run(['tar', 'tf', dl_path], capture_output=True, text=True)
                        if tar2.returncode == 0:
                            print(f"  tar tf:\n{tar2.stdout[:500]}")
                        else:
                            print(f"  Not tar either")

                    # First 200 chars as text
                    with open(dl_path, 'r', errors='replace') as f:
                        head = f.read(200)
                    print(f"  Head (text): {repr(head[:200])}")
                    break
                else:
                    print(f"  Attempt {attempt}: waiting... alert={last_alert['msg']}")

        print("\n=== Done ===")
        page.wait_for_timeout(3000)
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
