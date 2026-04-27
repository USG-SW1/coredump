#!/usr/bin/env python3
"""Upload coredump folders and their contents to FTP server.

Uploads everything under ./coredumps/ to the FTP server at
./{YEAR}_ML_Coredump_files/, creating the remote directory if needed.
Skips files that already exist on the server to avoid redundant uploads.
"""

import os
import sys
import ftplib
from datetime import datetime
from config_loader import load_config
from logger import Logger

_config = load_config(extra_keys=["ftp-host", "ftp-user", "ftp-pass"])
FTP_HOST = _config["ftp-host"]
FTP_USER = _config["ftp-user"]
FTP_PASS = _config["ftp-pass"]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_COREDUMPS_DIR = os.path.join(SCRIPT_DIR, "coredumps")

YEAR = datetime.now().strftime("%Y")
REMOTE_BASE_DIR = f"./jira/{YEAR}_ML_Coredump_files"


def ftp_dir_exists(ftp, path):
    """Check if a remote directory exists."""
    original = ftp.pwd()
    try:
        ftp.cwd(path)
        ftp.cwd(original)
        return True
    except ftplib.error_perm:
        ftp.cwd(original)
        return False


def ftp_remote_files(ftp, path):
    """List files in a remote directory. Returns set of filenames."""
    try:
        return set(ftp.nlst(path))
    except ftplib.error_perm:
        return set()


def ensure_remote_dir(ftp, path, logger):
    """Create remote directory if it does not exist."""
    if ftp_dir_exists(ftp, path):
        logger.log(f"[DEBUG] Remote directory already exists: {path}")
    else:
        logger.log(f"[DEBUG] Creating remote directory: {path}")
        ftp.mkd(path)
        logger.log(f"[OK] Created: {path}")


def upload_file(ftp, local_path, remote_path, logger):
    """Upload a single file to the FTP server."""
    size = os.path.getsize(local_path)
    logger.log(f"[DEBUG] Uploading {local_path} -> {remote_path} ({size} bytes)")
    with open(local_path, "rb") as f:
        ftp.storbinary(f"STOR {remote_path}", f)
    logger.log(f"[OK] Uploaded: {remote_path}")


def main():
    logger = Logger()

    if not os.path.isdir(LOCAL_COREDUMPS_DIR):
        logger.log(f"[ERROR] Local coredumps directory not found: {LOCAL_COREDUMPS_DIR}")
        logger.close()
        sys.exit(1)

    subfolders = [
        d for d in os.listdir(LOCAL_COREDUMPS_DIR)
        if os.path.isdir(os.path.join(LOCAL_COREDUMPS_DIR, d))
    ]

    if not subfolders:
        logger.log("[INFO] No folders found under coredumps/. Nothing to upload.")
        logger.close()
        sys.exit(0)

    logger.log(f"[DEBUG] Found {len(subfolders)} folder(s) to upload: {subfolders}")
    logger.log(f"[DEBUG] Connecting to FTP server: {FTP_HOST}")

    try:
        ftp = ftplib.FTP(FTP_HOST)
        ftp.login(FTP_USER, FTP_PASS)
        logger.log(f"[OK] Logged in as {FTP_USER}")
        logger.log(f"[DEBUG] Server welcome: {ftp.getwelcome()}")
    except ftplib.all_errors as e:
        logger.log(f"[ERROR] FTP connection failed: {e}")
        logger.close()
        sys.exit(1)

    try:
        # Ensure base year directory exists
        ensure_remote_dir(ftp, REMOTE_BASE_DIR, logger)

        uploaded_count = 0
        skipped_count = 0

        for folder_name in subfolders:
            local_folder = os.path.join(LOCAL_COREDUMPS_DIR, folder_name)
            remote_folder = f"{REMOTE_BASE_DIR}/{folder_name}"

            logger.log(f"\n[DEBUG] Processing folder: {folder_name}")
            ensure_remote_dir(ftp, remote_folder, logger)

            # Get list of existing remote files for skip check
            existing_remote = ftp_remote_files(ftp, remote_folder)
            # nlst may return full paths; normalize to basenames
            existing_basenames = {os.path.basename(f) for f in existing_remote}
            logger.log(f"[DEBUG] Existing files on server in {remote_folder}: {existing_basenames if existing_basenames else '(none)'}")

            for filename in os.listdir(local_folder):
                local_file = os.path.join(local_folder, filename)
                if not os.path.isfile(local_file):
                    logger.log(f"[DEBUG] Skipping non-file: {filename}")
                    continue

                if filename in existing_basenames:
                    logger.log(f"[SKIP] Already exists on server: {remote_folder}/{filename}")
                    skipped_count += 1
                    continue

                remote_file = f"{remote_folder}/{filename}"
                try:
                    upload_file(ftp, local_file, remote_file, logger)
                    uploaded_count += 1
                except ftplib.all_errors as e:
                    logger.log(f"[ERROR] Failed to upload {filename}: {e}")

        logger.log(f"\n[DONE] Upload complete. Uploaded: {uploaded_count}, Skipped (already exists): {skipped_count}")

    except ftplib.all_errors as e:
        logger.log(f"[ERROR] FTP error: {e}")
        logger.close()
        sys.exit(1)
    finally:
        try:
            ftp.quit()
            logger.log("[DEBUG] FTP connection closed.")
        except ftplib.all_errors:
            ftp.close()

    logger.close()


if __name__ == "__main__":
    main()
