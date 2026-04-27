#!/usr/bin/env python3
"""
Test OpTools - inspect JS source and try different upload approaches.
"""
import os
import re
import time
import json
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

step_num = 0
def shot(page, label):
    global step_num
    step_num += 1
    path = os.path.join(SHOTS_DIR, f"t2_{step_num:02d}_{label}.png")
    page.screenshot(path=path)
    print(f"[SHOT {step_num}] {label}")


def main():
    # Prepare shell script
    sh_path = os.path.join(SCRIPT_DIR, f"{DATETIME_PREFIX}.zysh")
    with open(os.path.join(SCRIPT_DIR, "temp.zysh"), "r") as f:
        content = f.read()
    with open(sh_path, "w") as f:
        f.write(content.replace("<date-time>", DATETIME_PREFIX))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--ignore-certificate-errors"])
        context = browser.new_context(ignore_https_errors=True, viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        # Go to query tab
        page.goto(OPTOOLS_QUERY_TAB, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        page.evaluate("document.querySelectorAll('.loadingoverlay').forEach(el => el.remove());")
        page.wait_for_timeout(1000)

        # === Step 1: Dump JS function source code ===
        print("=== JS function source code ===")
        trigger_src = page.evaluate("trigger_device_upload_log.toString()")
        print(f"\ntrigger_device_upload_log:\n{trigger_src}")

        check_src = page.evaluate("check_device_log.toString()")
        print(f"\ncheck_device_log:\n{check_src}")

        # Look for any script-related upload function
        print("\n=== Looking for script upload handler ===")
        script_handler = page.evaluate("""(() => {
            // Check button click handlers
            const uploadBtn = document.getElementById('detail-log-upload');
            const events = uploadBtn ? ($._data ? $._data(uploadBtn, 'events') : null) : null;
            let handlers = [];
            if (events && events.click) {
                events.click.forEach(h => handlers.push(h.handler.toString().substring(0, 500)));
            }

            // Check #script-upload change handler
            const scriptInput = document.getElementById('script-upload');
            const scriptEvents = scriptInput ? ($._data ? $._data(scriptInput, 'events') : null) : null;
            let scriptHandlers = [];
            if (scriptEvents) {
                for (const [evName, evList] of Object.entries(scriptEvents)) {
                    evList.forEach(h => scriptHandlers.push({event: evName, handler: h.handler.toString().substring(0, 500)}));
                }
            }

            return {
                uploadBtnHandlers: handlers,
                scriptInputHandlers: scriptHandlers
            };
        })()""")
        print(f"Handlers: {json.dumps(script_handler, indent=2)}")

        # === Step 2: Fill MAC/SN without script first, try upload ===
        print("\n=== Try 1: Upload WITHOUT script (original flow) ===")
        page.evaluate(f"""(() => {{
            $('#detail-log-mac').val('{MAC}');
            $('#detail-log-sn').val('{SN}');
            $('#detail-log-textarea').val('test');
        }})()""")
        page.evaluate("if (!$.LoadingOverlay) { $.LoadingOverlay = function() {}; }")

        all_requests = []
        def on_request(req):
            if "dev-troubleshoot" in req.url:
                body = ""
                try:
                    body = req.post_data or ""
                except:
                    pass
                entry = f"  [REQ] {req.method} {req.url[:120]}"
                if body:
                    entry += f"\n    BODY: {body[:500]}"
                print(entry)
                all_requests.append({"method": req.method, "url": req.url, "body": body[:500]})
        def on_response(resp):
            if "dev-troubleshoot" in resp.url:
                body = ""
                try:
                    body = resp.text()[:500]
                except:
                    pass
                print(f"  [RESP] {resp.status} {resp.url[:120]}")
                if body:
                    print(f"    BODY: {body[:300]}")

        page.on("request", on_request)
        page.on("response", on_response)

        last_alert = {"msg": None}
        def on_dialog(dialog):
            last_alert["msg"] = dialog.message
            print(f"  [DIALOG] {dialog.type}: {dialog.message}")
            dialog.accept()
        page.on("dialog", on_dialog)

        print("  Calling trigger_device_upload_log() (no script)...")
        last_alert["msg"] = None
        page.evaluate("trigger_device_upload_log()")
        start = time.time()
        while time.time() - start < 30:
            if last_alert["msg"]:
                break
            page.wait_for_timeout(500)
        shot(page, "upload_no_script")

        key_path = page.evaluate("$('#key-path').val() || 'not found'")
        print(f"  Key path: {key_path}")
        print(f"  Alert: {last_alert['msg']}")

        # If upload succeeded, poll for download
        if last_alert["msg"] and ("Succeed" in last_alert["msg"] or "Success" in last_alert["msg"]):
            print("\n=== Upload succeeded, polling check ===")
            for attempt in range(1, 25):
                last_alert["msg"] = None
                page.evaluate("check_device_log()")
                page.wait_for_timeout(15000)

                check_result = page.evaluate("""(() => {
                    const span = document.getElementById('detail-log-check-result');
                    const a = document.getElementById('detail-log-check-result-a');
                    return {
                        text: span ? span.innerText : '',
                        href: a ? (a.getAttribute('href') || '') : ''
                    };
                })()""")
                href = check_result.get("href", "")
                alert_msg = last_alert.get("msg", "")
                print(f"  Attempt {attempt}: href={href} alert={alert_msg}")

                if href and href.strip() and not href.endswith("#") and "index.html" not in href:
                    print(f"  [OK] Download link: {href}")
                    shot(page, "download_found")
                    break
            else:
                print("  [FAIL] No link after polling")
                shot(page, "poll_fail")
        else:
            print(f"\n  Upload failed, trying alternative approach...")

            # === Step 3: Try clicking the upload button directly (DOM click) ===
            print("\n=== Try 2: Click #detail-log-upload button directly ===")
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

            # Set script file
            page.locator("#script-upload").first.set_input_files(sh_path)
            page.wait_for_timeout(1000)
            shot(page, "before_button_click")

            # Click the button directly
            last_alert["msg"] = None
            page.locator("#detail-log-upload").first.click(force=True)
            start = time.time()
            while time.time() - start < 30:
                if last_alert["msg"]:
                    break
                page.wait_for_timeout(500)
            shot(page, "after_button_click")
            print(f"  Alert after click: {last_alert['msg']}")

            key_path = page.evaluate("$('#key-path').val() || 'not found'")
            print(f"  Key path: {key_path}")

            # If succeeded, poll
            if last_alert["msg"] and ("Succeed" in last_alert["msg"] or "Success" in last_alert["msg"]):
                print("\n=== Button click succeeded, polling check ===")
                for attempt in range(1, 25):
                    last_alert["msg"] = None
                    page.evaluate("check_device_log()")
                    page.wait_for_timeout(15000)
                    check_result = page.evaluate("""(() => {
                        const span = document.getElementById('detail-log-check-result');
                        const a = document.getElementById('detail-log-check-result-a');
                        return {text: span ? span.innerText : '', href: a ? (a.getAttribute('href') || '') : ''};
                    })()""")
                    href = check_result.get("href", "")
                    print(f"  Attempt {attempt}: href={href} alert={last_alert['msg']}")
                    if href and href.strip() and not href.endswith("#") and "index.html" not in href:
                        print(f"  [OK] Download link: {href}")
                        break

        print("\n=== Done ===")
        page.wait_for_timeout(5000)
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
