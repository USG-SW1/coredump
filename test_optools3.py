#!/usr/bin/env python3
"""
Test 3: Debug why script upload returns 400.
- Try direct API call with script file
- Check downloaded file type from no-script approach
"""
import os
import requests
from requests.auth import HTTPBasicAuth
from config_loader import load_config

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_config = load_config(extra_keys=["optools-host", "optools-user", "optools-pass"])

BASE_URL = f"https://{_config['optools-host']}"
AUTH = HTTPBasicAuth(_config["optools-user"], _config["optools-pass"])

MAC = "70:49:A2:4C:36:86"
SN = "S252L19100948"
DATETIME_PREFIX = "260413-184509"

# Prepare script
sh_path = os.path.join(SCRIPT_DIR, f"{DATETIME_PREFIX}.zysh")
with open(os.path.join(SCRIPT_DIR, "temp.zysh"), "r") as f:
    content = f.read()
with open(sh_path, "w") as f:
    f.write(content.replace("<date-time>", DATETIME_PREFIX))

print(f"Shell script: {sh_path}")
with open(sh_path) as f:
    print(f"Content:\n{f.read()}")
print(f"File size: {os.path.getsize(sh_path)} bytes")

# === Test 1: POST with script file (like the browser does) ===
print("\n=== Test 1: POST with script file ===")
with open(sh_path, 'rb') as script_file:
    files = {'script_file': (f'{DATETIME_PREFIX}.zysh', script_file, 'application/octet-stream')}
    data = {'mac': MAC, 'sn': SN, 'reason': 'test'}
    resp = requests.post(
        f"{BASE_URL}/dev-troubleshoot/do/",
        files=files, data=data, auth=AUTH, verify=False
    )
print(f"Status: {resp.status_code}")
print(f"Headers: {dict(resp.headers)}")
print(f"Body: {resp.text[:500]}")

# === Test 2: POST with script file as text/plain ===
print("\n=== Test 2: POST with script file (text/plain) ===")
with open(sh_path, 'rb') as script_file:
    files = {'script_file': (f'{DATETIME_PREFIX}.zysh', script_file, 'text/plain')}
    data = {'mac': MAC, 'sn': SN, 'reason': 'test'}
    resp = requests.post(
        f"{BASE_URL}/dev-troubleshoot/do/",
        files=files, data=data, auth=AUTH, verify=False
    )
print(f"Status: {resp.status_code}")
print(f"Body: {resp.text[:500]}")

# === Test 3: POST without script (like undefined) ===
print("\n=== Test 3: POST without script (script_file=undefined as string) ===")
data = {'script_file': 'undefined', 'mac': MAC, 'sn': SN, 'reason': 'test'}
resp = requests.post(
    f"{BASE_URL}/dev-troubleshoot/do/",
    data=data, auth=AUTH, verify=False
)
print(f"Status: {resp.status_code}")
print(f"Body: {resp.text[:500]}")

if resp.status_code == 200:
    import json
    result = resp.json()
    key_path = result.get('result', '')
    print(f"Key path: {key_path}")

    # Check the file
    import time
    print("\n=== Polling for download ===")
    for i in range(10):
        time.sleep(15)
        check_resp = requests.get(
            f"{BASE_URL}/dev-troubleshoot/check-file-available/{key_path}",
            auth=AUTH, verify=False
        )
        print(f"  Attempt {i+1}: status={check_resp.status_code} body={check_resp.text[:200]}")
        if check_resp.status_code == 200:
            # Download the file
            download_url = f"{BASE_URL}/datecode-op-tool/page/{key_path}"
            print(f"\n=== Downloading: {download_url} ===")
            dl_resp = requests.get(download_url, auth=AUTH, verify=False, stream=True)
            dl_path = os.path.join(SCRIPT_DIR, "test_download.bin")
            total = 0
            with open(dl_path, 'wb') as f:
                for chunk in dl_resp.iter_content(8192):
                    f.write(chunk)
                    total += len(chunk)
            print(f"Downloaded {total} bytes -> {dl_path}")

            # Check file type
            import subprocess
            file_type = subprocess.run(['file', dl_path], capture_output=True, text=True)
            print(f"File type: {file_type.stdout}")

            # Try unzip
            unzip_result = subprocess.run(['unzip', '-l', dl_path], capture_output=True, text=True)
            print(f"unzip -l: {unzip_result.stdout[:500]}")
            if unzip_result.returncode != 0:
                print(f"unzip stderr: {unzip_result.stderr[:300]}")

            # Try tar
            tar_result = subprocess.run(['tar', 'tzf', dl_path], capture_output=True, text=True)
            print(f"tar tzf: {tar_result.stdout[:500]}")
            if tar_result.returncode != 0:
                # Try plain tar
                tar_result2 = subprocess.run(['tar', 'tf', dl_path], capture_output=True, text=True)
                print(f"tar tf: {tar_result2.stdout[:500]}")

            # Check first bytes
            with open(dl_path, 'rb') as f:
                magic = f.read(16)
            print(f"Magic bytes: {magic.hex()} ({magic[:4]})")
            break
