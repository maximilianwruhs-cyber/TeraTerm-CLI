"""Local smoke: doctor exit + mock provision success/failure."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from tt_agent_hw.cli import main

FIXTURE = ROOT / "tests" / "fixtures" / "fake_ttpmacro.py"
FW = ROOT / "smoke_fw" / "fw.bin"
FW.parent.mkdir(exist_ok=True)
FW.write_bytes(b"FW")


def run(argv: list[str]) -> int:
    print(">>", " ".join(argv))
    code = main(argv)
    print("exit", code)
    return code


def provision_argv(runtime: Path) -> list[str]:
    return [
        "provision",
        "--com",
        "4",
        "--binary",
        str(FW),
        "--boot-prompt",
        "U-Boot>",
        "--erase-command",
        "erase",
        "--erase-ack",
        "OK",
        "--transfer-trigger",
        "loady",
        "--boot-command",
        "bootm",
        "--boot-success-regex",
        "Ready",
        "--boot-timeout",
        "5",
        "--runtime-dir",
        str(runtime),
        "--tt-bin-dir",
        str(runtime),
        "--macro-exe",
        str(FIXTURE),
        "--json",
    ]


def main_smoke() -> int:
    doc = run(["doctor"])
    if doc not in (0, 2):
        print("doctor returned unexpected", doc)
        return 1
    print("doctor_ok_for_env", doc)

    os.environ["FAKE_TT_STATUS"] = "STATUS=SUCCESS_PROVISIONED"
    os.environ["FAKE_TT_DELAY"] = "0.1"
    os.environ.pop("FAKE_TT_HANG", None)

    ok = run(provision_argv(ROOT / "smoke_runtime_ok"))
    if ok != 0:
        return 1

    os.environ["FAKE_TT_STATUS"] = "STATUS=FAILED_FLASH_ERASE"
    fail = run(provision_argv(ROOT / "smoke_runtime_fail"))
    if fail != 1:
        print("expected exit 1 for failure, got", fail)
        return 1

    print("SMOKE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_smoke())
