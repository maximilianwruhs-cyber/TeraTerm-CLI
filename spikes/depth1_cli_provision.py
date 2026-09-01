"""Depth-1 real-CLI provision runner: real Tera Term, no serial device.

Drives tt_agent_hw.cli.main() with real argv (no shell quoting) against the
real ttpmacro.exe. With no device on the given COM port, the expected terminal
state is STATUS=FAILED_CONNECTION_REFUSED and CLI exit 1 -- which still proves
the full real pipeline: arg-parse -> render -> spawn real engine -> poll ->
status parse -> exit-code mapping.

Run:
    .venv\\Scripts\\python.exe spikes\\depth1_cli_provision.py \\
        --tt-bin-dir "C:\\Users\\...\\TeraTerm\\current"
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tt_agent_hw.cli import main
from tt_agent_hw.paths import tt_bin_dir


def run() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tt-bin-dir", default=None)
    ap.add_argument("--com", default="4")
    args = ap.parse_args()

    bin_dir = args.tt_bin_dir or str(tt_bin_dir())
    work = Path(tempfile.mkdtemp(prefix="d1_cli_"))
    fw = work / "fw.bin"
    fw.write_bytes(b"DUMMYFW")

    return main(
        [
            "provision",
            "--com", args.com,
            "--baud", "115200",
            "--binary", str(fw),
            "--boot-prompt", "U-Boot>",
            "--erase-command", "sf erase 0 0x1000",
            "--erase-ack", "Erased: OK",
            "--transfer-trigger", "loady",
            "--boot-command", "bootm",
            "--boot-success-regex", "System Ready",
            "--boot-timeout", "10",
            "--runtime-dir", str(work / "rt"),
            "--tt-bin-dir", bin_dir,
            "--json",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(run())
