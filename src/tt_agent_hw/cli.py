"""CLI: tt-agent-hw doctor | provision | ports | discover | profile | cmds | call."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tt_agent_hw import __version__
from tt_agent_hw.call_session import run_call
from tt_agent_hw.controller import PreflightError, TeraTermAgentController
from tt_agent_hw.discover import run_discover
from tt_agent_hw.models import TargetJob
from tt_agent_hw.paths import runtime_dir, tt_bin_dir
from tt_agent_hw.ports import list_ports, resolve_default_com
from tt_agent_hw.profile_store import load_profile
from tt_agent_hw.status import (
    FAILED_NO_PORT,
    FAILED_PROBE_SILENT,
    SUCCESS_DISCOVERED,
    is_success,
)
from tt_agent_hw.workspace import ensure_runtime_writable

# Discover connection-refused token (also in status.KNOWN_FAILURE).
_FAILED_CONNECTION_REFUSED = "STATUS=FAILED_CONNECTION_REFUSED"


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

    sp = sub.add_parser("ports", help="List serial ports")
    sp.add_argument("--json", action="store_true", help="Print ports as JSON")
    sp.add_argument(
        "--runtime-dir",
        type=Path,
        default=None,
        help="Override TT_AGENT_RUNTIME_DIR",
    )

    sd = sub.add_parser("discover", help="Probe UART and write device profile")
    sd.add_argument("--com", type=int, default=None, help="COM port index (default: auto)")
    sd.add_argument("--baud", type=int, default=None, help="Single baud to try")
    sd.add_argument(
        "--baud-list",
        type=str,
        default=None,
        help="Comma-separated baud list (e.g. 115200,9600)",
    )
    sd.add_argument(
        "--no-early-stop",
        action="store_true",
        help="Try full baud list even after a strong hit",
    )
    sd.add_argument(
        "--no-break",
        action="store_true",
        help="Skip serial break before probe",
    )
    sd.add_argument("--json", action="store_true", help="Print result as JSON")
    sd.add_argument(
        "--runtime-dir",
        type=Path,
        default=None,
        help="Override TT_AGENT_RUNTIME_DIR",
    )

    prof = sub.add_parser("profile", help="Inspect saved device profiles")
    prof_sub = prof.add_subparsers(dest="profile_cmd", required=True)
    ps = prof_sub.add_parser("show", help="Show profile for a COM port")
    ps.add_argument("--com", type=int, required=True, help="COM port index")
    ps.add_argument("--json", action="store_true", help="Print profile as JSON")
    ps.add_argument(
        "--runtime-dir",
        type=Path,
        default=None,
        help="Override TT_AGENT_RUNTIME_DIR",
    )

    sc = sub.add_parser("cmds", help="List discovered commands for a COM port")
    sc.add_argument("--com", type=int, required=True, help="COM port index")
    sc.add_argument("--json", action="store_true", help="Print commands as JSON")
    sc.add_argument(
        "--runtime-dir",
        type=Path,
        default=None,
        help="Override TT_AGENT_RUNTIME_DIR",
    )

    sca = sub.add_parser("call", help="Send a command against a discovered profile")
    sca.add_argument("--com", type=int, required=True, help="COM port index")
    sca.add_argument("command_id", nargs="?", default=None, help="Discovered command id")
    sca.add_argument("--send", type=str, default=None, help="Raw text to send (XOR with id)")
    sca.add_argument("--expect", type=str, default=None, help="Regex expected in RX")
    sca.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="RX timeout seconds (default 3.0)",
    )
    sca.add_argument("--json", action="store_true", help="Print result as JSON")
    sca.add_argument(
        "--runtime-dir",
        type=Path,
        default=None,
        help="Override TT_AGENT_RUNTIME_DIR",
    )

    return parser


def _runtime(args: argparse.Namespace) -> Path:
    return Path(args.runtime_dir) if getattr(args, "runtime_dir", None) else runtime_dir()


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
        import serial  # noqa: F401

        checks.append(("pyserial", True, getattr(serial, "__version__", "ok")))
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks.append(("pyserial", False, str(exc)))

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


def cmd_ports(args: argparse.Namespace) -> int:
    base = _runtime(args)
    try:
        ports = list_ports(runtime_dir=base)
    except Exception as exc:  # noqa: BLE001
        print(f"ports error: {exc}", file=sys.stderr)
        return 2

    payload = [
        {
            "name": p.name,
            "com": p.com,
            "description": p.description,
            "hardware_id": p.hardware_id,
            "has_profile": p.has_profile,
        }
        for p in ports
    ]
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        if not ports:
            print("(no serial ports)")
        for p in ports:
            profile = "profile" if p.has_profile else "no-profile"
            print(f"{p.name}\t{p.description}\t{profile}")
    return 0


def _parse_baud_list(args: argparse.Namespace) -> list[int] | None:
    if args.baud is not None:
        return [int(args.baud)]
    if args.baud_list:
        parts = [p.strip() for p in str(args.baud_list).split(",") if p.strip()]
        return [int(p) for p in parts]
    return None


def cmd_discover(args: argparse.Namespace) -> int:
    base = _runtime(args)
    com = args.com
    if com is None:
        try:
            ports = list_ports(runtime_dir=base)
        except Exception as exc:  # noqa: BLE001
            print(f"ports error: {exc}", file=sys.stderr)
            return 2
        com = resolve_default_com(ports)
        if com is None:
            print("no default COM port (use --com)", file=sys.stderr)
            return 2

    baud_list = _parse_baud_list(args)
    try:
        result = run_discover(
            com=int(com),
            runtime_dir=base,
            baud_list=baud_list,
            send_break=not args.no_break,
            early_stop=not args.no_early_stop,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"discover error: {exc}", file=sys.stderr)
        return 3

    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"run_id:       {result.run_id}")
        print(f"status:       {result.status}")
        print(f"duration:     {result.duration_sec}s")
        print(f"profile_path: {result.profile_path}")
        print(f"log_file:     {result.log_file}")
        print(f"workspace:    {result.workspace}")

    if result.status == SUCCESS_DISCOVERED or is_success(result.status):
        return 0
    if result.status == FAILED_PROBE_SILENT:
        return 1
    if result.status in (FAILED_NO_PORT, _FAILED_CONNECTION_REFUSED):
        return 2
    return 3


def cmd_profile_show(args: argparse.Namespace) -> int:
    base = _runtime(args)
    try:
        profile = load_profile(base, int(args.com))
    except FileNotFoundError:
        print(f"no profile for COM{args.com}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"profile error: {exc}", file=sys.stderr)
        return 2

    payload = profile.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"COM{profile.com} baud={profile.baud} confidence={profile.confidence}")
        print(f"port_name: {profile.port_name}")
        print(f"commands:  {len(profile.commands)}")
        print(f"run_id:    {profile.run_id}")
        print(f"at:        {profile.discovered_at}")
    return 0


def cmd_cmds(args: argparse.Namespace) -> int:
    base = _runtime(args)
    try:
        profile = load_profile(base, int(args.com))
    except FileNotFoundError:
        print(f"no profile for COM{args.com}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"cmds error: {exc}", file=sys.stderr)
        return 2

    payload = [c.to_dict() for c in profile.commands]
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        if not profile.commands:
            print("(no commands)")
        for c in profile.commands:
            print(f"{c.id}\t{c.send!r}\t{c.summary}")
    return 0


def cmd_call(args: argparse.Namespace) -> int:
    base = _runtime(args)
    try:
        result = run_call(
            runtime_dir=base,
            com=int(args.com),
            command_id=args.command_id,
            send=args.send,
            expect=args.expect,
            timeout_s=float(args.timeout),
        )
    except (FileNotFoundError, ValueError, KeyError) as exc:
        print(f"call error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"call error: {exc}", file=sys.stderr)
        return 3

    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"run_id: {result.run_id}")
        print(f"tx:     {result.tx!r}")
        print(f"rx:     {result.rx!r}")
        print(f"matched:{result.matched}")
        print(f"baud:   {result.profile_baud}")
        print(f"log:    {result.log_file}")

    if result.matched is False:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return cmd_doctor(runtime_dir(), tt_bin_dir())
    if args.command == "provision":
        return cmd_provision(args)
    if args.command == "ports":
        return cmd_ports(args)
    if args.command == "discover":
        return cmd_discover(args)
    if args.command == "profile":
        if args.profile_cmd == "show":
            return cmd_profile_show(args)
        parser.error(f"unknown profile subcommand: {args.profile_cmd}")
        return 2
    if args.command == "cmds":
        return cmd_cmds(args)
    if args.command == "call":
        return cmd_call(args)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
