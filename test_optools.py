#!/usr/bin/env python3
"""
Test OpTools download flow step by step with screenshots.
SN: S252L19100948
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

_config = load_config(extra_keys=[
    "optools-host", "optools-user", "optools-pass",
])

_optools_user = _config["optools-user"]
_optools_pass = _config["optools-pass"]
_optools_host = _config["optools-host"]
_optools_user_encoded = _optools_user.replace("@", "%40") + ":" + _optools_pass
OPTOOLS_BASE_URL = f"https://{_optools_user_encoded}@{_optools_host}"
OPTOOLS_DEVICE_TAB = f"{OPTOOLS_BASE_URL}#tabs-device"
OPTOOLS_QUERY_TAB = f"{OPTOOLS_BASE_URL}#tabs-3"

SN = "S252L19100948"
DATETIME_PREFIX = "260413-184509"

step_num = 0
def shot(page, label):
    global step_num
    step_num += 1
    path = os.path.join(SHOTS_DIR, f"{step_num:02d}_{label}.png")
    page.screenshot(path=path)
    print(f"[SHOT {step_num}] {label}: {path}")


def main():
    # Prepare shell script
    template_path = os.path.join(SCRIPT_DIR, "temp.zysh")
    sh_path = os.path.join(SCRIPT_DIR, f"{DATETIME_PREFIX}.zysh")
    with open(template_path, "r") as f:
        content = f.read()
    with open(sh_path, "w") as f:
        f.write(content.replace("<date-time>", DATETIME_PREFIX))
    print(f"[OK] Shell script: {sh_path}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--ignore-certificate-errors"],
        )
        context = browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        # === Step A: Get MAC from Device tab ===
        print("\n=== Getting MAC ===")
        page.goto(OPTOOLS_DEVICE_TAB, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        page.evaluate("try { $('.loadingoverlay').remove(); } catch(e) {}")
        page.wait_for_timeout(1000)
        shot(page, "device_tab_loaded")

        sn_inputs = page.locator("#get-device-by-sn-input")
        for idx in range(sn_inputs.count()):
            sn_inputs.nth(idx).fill(SN)

        page.evaluate("""(() => {
            var btn = $('#get-device-by-mac-sn-button');
            if (btn.length === 0) return;
            var events = $._data(btn[0], 'events');
            if (!(events && events.click) && typeof window.initDeviceTab === 'function')
                window.initDeviceTab();
        })()""")
        page.locator("#get-device-by-mac-sn-button").first.click(force=True)

        result_text = ""
        poll_start = time.time()
        while time.time() - poll_start < 30:
            result_text = page.evaluate("$('#get-device-result').text().trim()")
            if result_text:
                break
            page.wait_for_timeout(1000)

        page.evaluate("try { $('.loadingoverlay').remove(); } catch(e) {}")
        shot(page, "mac_result")

        mac_match = re.search(r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})', result_text)
        mac = mac_match.group(0) if mac_match else None
        print(f"MAC: {mac}")

        if not mac:
            print("[FAIL] No MAC found, cannot proceed")
            browser.close()
            return

        # === Step B: Go to Query tab (tabs-3) ===
        print("\n=== Going to Query tab ===")
        page.goto(OPTOOLS_QUERY_TAB, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        page.evaluate("document.querySelectorAll('.loadingoverlay').forEach(el => el.remove());")
        page.wait_for_timeout(1000)
        shot(page, "query_tab_loaded")

        # === Step C: Dump page structure for the troubleshoot section ===
        print("\n=== Inspecting page structure ===")

        # Find all tabs
        tabs_info = page.evaluate("""(() => {
            const tabs = document.querySelectorAll('[role="tab"], .ui-tabs-anchor, a[href^="#tabs"]');
            return Array.from(tabs).map(t => ({
                text: t.innerText.trim(),
                href: t.getAttribute('href'),
                id: t.id,
                class: t.className
            }));
        })()""")
        print(f"Tabs: {json.dumps(tabs_info, indent=2)}")

        # Find all visible forms and inputs in the troubleshoot section
        form_info = page.evaluate("""(() => {
            const section = document.querySelector('#tabs-3') || document.body;
            const inputs = section.querySelectorAll('input, textarea, select, button');
            return Array.from(inputs).map(el => ({
                tag: el.tagName,
                type: el.type || '',
                id: el.id,
                name: el.name || '',
                value: (el.type === 'file' ? '' : (el.value || '').substring(0, 50)),
                class: el.className.substring(0, 80),
                visible: el.offsetParent !== null,
                text: (el.innerText || '').substring(0, 50)
            }));
        })()""")
        print(f"\nForm elements in tabs-3:")
        for el in form_info:
            if el.get('visible'):
                print(f"  {el['tag']} type={el['type']} id={el['id']} name={el['name']} val={el['value']}")

        # Find all buttons
        buttons_info = page.evaluate("""(() => {
            const btns = document.querySelectorAll('#tabs-3 button, #tabs-3 input[type="button"], #tabs-3 input[type="submit"]');
            return Array.from(btns).map(b => ({
                tag: b.tagName,
                id: b.id,
                class: b.className.substring(0, 80),
                text: (b.innerText || b.value || '').substring(0, 80),
                visible: b.offsetParent !== null,
                onclick: (b.getAttribute('onclick') || '').substring(0, 100)
            }));
        })()""")
        print(f"\nButtons in tabs-3:")
        for b in buttons_info:
            if b.get('visible'):
                print(f"  id={b['id']} text='{b['text']}' onclick='{b['onclick']}'")

        # === Step D: Fill MAC, SN, textarea ===
        print("\n=== Filling MAC/SN ===")
        page.evaluate(f"""(() => {{
            $('#detail-log-mac').val('{mac}');
            $('#detail-log-sn').val('{SN}');
            $('#detail-log-textarea').val('test');
        }})()""")

        verify = page.evaluate("""(() => ({
            mac: $('#detail-log-mac').val(),
            sn: $('#detail-log-sn').val(),
            msg: $('#detail-log-textarea').val()
        }))()""")
        print(f"Verified: {verify}")
        shot(page, "filled_mac_sn")

        # === Step E: Upload shell script to #script-upload ===
        print("\n=== Uploading shell script ===")
        page.locator("#script-upload").first.set_input_files(sh_path)
        page.wait_for_timeout(1000)

        # Check what happened after script upload
        script_info = page.evaluate("""(() => {
            const inp = document.getElementById('script-upload');
            if (!inp) return {found: false};
            return {
                found: true,
                files: inp.files.length,
                fileName: inp.files.length > 0 ? inp.files[0].name : 'none'
            };
        })()""")
        print(f"Script input: {script_info}")
        shot(page, "script_uploaded")

        # === Step F: Look for script-related buttons/actions ===
        print("\n=== Looking for script upload/run button ===")
        script_btns = page.evaluate("""(() => {
            // Look for buttons near script-upload
            const allBtns = document.querySelectorAll('button, input[type="button"]');
            return Array.from(allBtns).map(b => ({
                id: b.id,
                text: (b.innerText || b.value || '').trim().substring(0, 80),
                class: b.className.substring(0, 80),
                visible: b.offsetParent !== null,
                onclick: (b.getAttribute('onclick') || '').substring(0, 150)
            })).filter(b => b.visible);
        })()""")
        print(f"All visible buttons:")
        for b in script_btns:
            print(f"  id='{b['id']}' text='{b['text']}' onclick='{b['onclick']}'")

        # === Step G: Check available JS functions ===
        print("\n=== Checking JS functions ===")
        js_funcs = page.evaluate("""(() => {
            const fns = [];
            for (const key of Object.keys(window)) {
                if (typeof window[key] === 'function' &&
                    (key.toLowerCase().includes('upload') ||
                     key.toLowerCase().includes('script') ||
                     key.toLowerCase().includes('device') ||
                     key.toLowerCase().includes('trigger') ||
                     key.toLowerCase().includes('check') ||
                     key.toLowerCase().includes('log') ||
                     key.toLowerCase().includes('troubleshoot'))) {
                    fns.push(key);
                }
            }
            return fns.sort();
        })()""")
        print(f"Relevant JS functions: {json.dumps(js_funcs, indent=2)}")

        # === Step H: Try trigger_device_upload_log ===
        print("\n=== Trying trigger_device_upload_log() ===")
        page.evaluate("if (!$.LoadingOverlay) { $.LoadingOverlay = function() {}; }")

        last_alert = {"msg": None}
        def on_dialog(dialog):
            last_alert["msg"] = dialog.message
            print(f"  [DIALOG] {dialog.type}: {dialog.message}")
            dialog.accept()
        page.on("dialog", on_dialog)

        def on_request(req):
            if "dev-troubleshoot" in req.url or "script" in req.url.lower():
                print(f"  [NET] Request: {req.method} {req.url[:150]}")
        def on_response(resp):
            if "dev-troubleshoot" in resp.url or "script" in resp.url.lower():
                print(f"  [NET] Response: {resp.status} {resp.url[:150]}")
        page.on("request", on_request)
        page.on("response", on_response)

        last_alert["msg"] = None
        page.evaluate("trigger_device_upload_log()")

        start = time.time()
        while time.time() - start < 30:
            if last_alert["msg"]:
                print(f"  Alert after trigger: {last_alert['msg']}")
                break
            page.wait_for_timeout(500)
        shot(page, "after_trigger_upload")

        key_path = page.evaluate("$('#key-path').val() || 'not found'")
        print(f"  Key path: {key_path}")

        # === Step I: Poll check_device_log ===
        print("\n=== Polling check_device_log() ===")
        for attempt in range(1, 25):
            last_alert["msg"] = None
            page.evaluate("check_device_log()")
            page.wait_for_timeout(15000)

            if last_alert["msg"]:
                print(f"  Attempt {attempt}: Alert = {last_alert['msg']}")

            check_result = page.evaluate("""(() => {
                const span = document.getElementById('detail-log-check-result');
                const a = document.getElementById('detail-log-check-result-a');
                return {
                    text: span ? span.innerText : '',
                    href: a ? (a.getAttribute('href') || '') : '',
                    linkText: a ? a.innerText : ''
                };
            })()""")

            href = check_result.get("href", "")
            print(f"  Attempt {attempt}: result={check_result}")

            if href and href.strip() and not href.endswith("#") and "index.html" not in href:
                print(f"  [OK] Download link: {href}")
                shot(page, "download_link_found")
                break
        else:
            print("  [FAIL] No download link after all attempts")
            shot(page, "poll_timeout")

        print("\n=== Done, keeping browser open for 10s ===")
        page.wait_for_timeout(10000)
        shot(page, "final")

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
