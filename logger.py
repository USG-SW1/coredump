import inspect
import json
import os
import sys
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


class Logger:
    """Unified logger: writes to both console and a single daily log file under logs/.

    All scripts share the same log file (logs/YYYY-MM-DD.log).
    Use `source` to tag log lines, e.g. [ELK], [optools], [merge].
    """

    def __init__(self, source=None):
        os.makedirs(LOG_DIR, exist_ok=True)
        if source is None:
            caller = inspect.stack()[1].filename
            source = os.path.splitext(os.path.basename(caller))[0]
        today = datetime.now().strftime("%Y-%m-%d")
        self.log_path = os.path.join(LOG_DIR, f"{today}.log")
        self.source = source
        self.log_file = open(self.log_path, "a", encoding="utf-8")
        self.log(f"=== Log started ===")
        self.log(f"argv: {sys.argv}")

    def log(self, message):
        ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        tag = f"[{self.source}]" if self.source else ""
        line = f"{ts}{tag} {message}"
        print(line)
        self.log_file.write(line + "\n")
        self.log_file.flush()

    def log_records(self, records, label="ELK query results"):
        self.log(f"--- {label}: {len(records)} records ---")
        for rec in records:
            self.log_file.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        self.log_file.flush()
        self.log(f"--- End of {label} ---")

    def log_record(self, action, row):
        _id = row.get("_id", "")
        sn = row.get("sn", "")
        firmware = row.get("firmware", "")
        target = row.get("target", "")
        self.log(f"  {action}: _id={_id}, sn={sn}, firmware={firmware}, target={os.path.basename(target)}")

    def close(self):
        if self.log_file.closed:
            return
        self.log(f"=== Log ended ===")
        self.log_file.close()
