#!/usr/bin/env python3
"""Fake ttpmacro.exe: parse rendered TTL lightly and write execution.state.

Usage: py fake_ttpmacro.py <task.ttl>

Environment:
  FAKE_TT_STATUS   terminal status body or full STATUS= line (default SUCCESS_PROVISIONED)
  FAKE_TT_DELAY    seconds to sleep before writing terminal status (default 0.2)
  FAKE_TT_HANG     if "1", sleep forever (orchestrator timeout test)
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path


def extract_state_file(ttl_text: str) -> Path | None:
    m = re.search(r"StateFile\s*=\s*'([^']+)'", ttl_text)
    if not m:
        return None
    # TTL may use doubled backslashes
    raw = m.group(1).replace("\\\\", "\\")
    return Path(raw)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: fake_ttpmacro.py <task.ttl>", file=sys.stderr)
        return 2
    ttl_path = Path(sys.argv[1])
    text = ttl_path.read_text(encoding="ascii", errors="replace")
    state_file = extract_state_file(text)
    if state_file is None:
        print("StateFile not found in TTL", file=sys.stderr)
        return 2

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("STATUS=INITIALIZING\n", encoding="ascii")

    if os.environ.get("FAKE_TT_HANG") == "1":
        while True:
            time.sleep(3600)

    delay = float(os.environ.get("FAKE_TT_DELAY", "0.2"))
    time.sleep(delay)

    status = os.environ.get("FAKE_TT_STATUS", "STATUS=SUCCESS_PROVISIONED")
    if not status.startswith("STATUS="):
        status = f"STATUS={status}"
    state_file.write_text(status.strip() + "\n", encoding="ascii")

    # Optional console log sibling
    log_m = re.search(r"LogFile\s*=\s*'([^']+)'", text)
    if log_m:
        log_path = Path(log_m.group(1).replace("\\\\", "\\"))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("fake macro completed\n", encoding="ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
