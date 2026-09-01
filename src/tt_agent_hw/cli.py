"""CLI: tt-agent-hw doctor | provision."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tt_agent_hw import __version__
from tt_agent_hw.controller import PreflightError, TeraTermAgentController
from tt_agent_hw.models import TargetJob
from tt_agent_hw.paths import runtime_dir, tt_bin_dir
from tt_agent_hw.status import is_success
from tt_agent_hw.workspace import ensure_runtime_writable


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tt-agent-hw",
        description="Autonomous Tera Term single-target flash+verify orchestrator",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Check runtime dir and Tera Term binaries")

    p = sub.add_parser("provision", help="Flash and verify one UART target")
    p.add_argument("--com", type=int, required=True, help="COM port index (e.g. 4 for COM4)")
    p.add_argument("--baud", type=int, default=115200, help="Baud rate (default 115200)")
    p.add_argument("--binary", type=Path, required=True, help="Firmware image path")
    p.add_argument("--boot-prompt", required=True, help="Bootloader prompt string")
    p.add_argument("--erase-command", required=True, help="Flash erase command")
    p.add_argument("--erase-ack", required=True, help="Erase success token")
    p.add_argument("--transfer-trigger", required=True, help="YMODEM receive trigger command")
    p.add_argument("--boot-command", required=True, help="Boot command after transfer")
    p.add_argument("--boot-success-regex", required=True, help="Regex for successful boot")
    p.add_argument("--boot-timeout", type=int, default=30, help="Boot wait seconds (default 30)")
    p.add_argument(
        "--runtime-dir",
        type=Path,
        default=None,
        help="Override TT_AGENT_RUNTIME_DIR",
    )
    p.add_argument(
        "--tt-bin-dir",
        type=Path,
        default=None,
        help="Override TT_AGENT_TT_BIN_DIR",
    )
    p.add_argument(
        "--macro-exe",
        type=Path,
        default=None,
        help="Override ttpmacro.exe (tests / alternate engines)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print result as JSON",
    )
    return parser


def cmd_doctor(runtime: Path, tt_bin: Path) -> int:
    ok = True
    checks: list[tuple[str, bool, str]] = []

    try:
        import tt_agent_hw as pkg  # noqa: F401

        checks.append(("package_import", True, f"tt_agent_hw {__version__}"))
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(("package_import", False, str(exc)))

    try:
        ensure_runtime_writable(runtime)
        checks.append(("runtime_writable", True, str(runtime)))
    except OSError as exc:
        ok = False
        checks.append(("runtime_writable", False, f"{runtime}: {exc}"))

    macro = tt_bin / "ttpmacro.exe"
    term = tt_bin / "ttermpro.exe"
    if macro.is_file():
        checks.append(("ttpmacro.exe", True, str(macro)))
    else:
        ok = False
        checks.append(("ttpmacro.exe", False, f"missing: {macro}"))
    if term.is_file():
        checks.append(("ttermpro.exe", True, str(term)))
    else:
        ok = False
        checks.append(("ttermpro.exe", False, f"missing: {term}"))

    for name, passed, detail in checks:
        mark = "OK" if passed else "FAIL"
        print(f"[{mark}] {name}: {detail}")

    return 0 if ok else 2


def cmd_provision(args: argparse.Namespace) -> int:
    base = Path(args.runtime_dir) if args.runtime_dir else runtime_dir()
    tt_bin = Path(args.tt_bin_dir) if args.tt_bin_dir else tt_bin_dir()
    job = TargetJob(
        com_port=args.com,
        baud_rate=args.baud,
        boot_prompt=args.boot_prompt,
        erase_command=args.erase_command,
        erase_ack=args.erase_ack,
        transfer_trigger_command=args.transfer_trigger,
        boot_command=args.boot_command,
        boot_success_regex=args.boot_success_regex,
        boot_timeout=args.boot_timeout,
        binary_path=Path(args.binary),
    )
    controller = TeraTermAgentController(
        base_dir=base,
        tt_bin_dir=tt_bin,
        macro_exe=args.macro_exe,
    )
    try:
        result = controller.execute_provisioning(job)
    except PreflightError as exc:
        print(f"preflight error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"controller error: {exc}", file=sys.stderr)
        return 3

    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"run_id:    {result.run_id}")
        print(f"status:    {result.status}")
        print(f"duration:  {result.duration_sec}s")
        print(f"log_file:  {result.log_file}")
        print(f"workspace: {result.workspace}")

    if is_success(result.status):
        return 0
    if result.is_timeout():
        return 3
    if "PREFLIGHT" in result.status:
        return 2
    if "FAILED" in result.status:
        return 1
    return 3


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return cmd_doctor(runtime_dir(), tt_bin_dir())
    if args.command == "provision":
        return cmd_provision(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
