"""Agentic call session: send a profile command or raw line and capture RX."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from tt_agent_hw.models import CallResult, DeviceProfile
from tt_agent_hw.profile_store import load_profile
from tt_agent_hw.serial_io import append_cr, read_until_quiet
from tt_agent_hw.serial_transport import PyserialTransport, SerialTransport
from tt_agent_hw.workspace import create_workspace, ensure_runtime_writable

TransportFactory = Callable[[str, int], SerialTransport]


def _default_transport_factory(port: str, baud: int) -> SerialTransport:
    return PyserialTransport(port=port, baud=baud)


def _resolve_tx(
    profile: DeviceProfile,
    *,
    command_id: str | None,
    send: str | None,
) -> str:
    has_id = command_id is not None
    has_send = send is not None
    if has_id == has_send:
        raise ValueError("exactly one of command_id or send is required")
    if has_send:
        assert send is not None
        return send
    assert command_id is not None
    for cmd in profile.commands:
        if cmd.id == command_id:
            return cmd.send
    raise KeyError(command_id)


def _append_log(log_file: Path, line: str) -> None:
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(line.rstrip("\n") + "\n")


def run_call(
    *,
    runtime_dir: Path,
    com: int,
    command_id: str | None = None,
    send: str | None = None,
    expect: str | None = None,
    timeout_s: float = 3.0,
    transport_factory: TransportFactory | None = None,
) -> CallResult:
    """Send one line using a required per-COM profile and optionally match expect."""
    runtime_dir = Path(runtime_dir)
    # Validate XOR before touching the filesystem so bad args fail fast.
    if (command_id is None) == (send is None):
        raise ValueError("exactly one of command_id or send is required")

    profile = load_profile(runtime_dir, com)
    tx = _resolve_tx(profile, command_id=command_id, send=send)

    ensure_runtime_writable(runtime_dir)
    ws = create_workspace(runtime_dir)
    _append_log(ws.log_file, f"call com={com} baud={profile.baud} tx={tx!r}")

    factory = transport_factory or _default_transport_factory
    port_name = profile.port_name or f"COM{com}"
    transport = factory(port_name, profile.baud)
    transport.open()
    try:
        transport.reset_input_buffer()
        transport.write(append_cr(tx))
        rx_bytes = read_until_quiet(transport, max_s=timeout_s)
    finally:
        transport.close()

    rx_text = rx_bytes.decode("utf-8", errors="replace")
    matched: bool | None
    if expect is None:
        matched = None
    else:
        matched = re.search(expect, rx_text) is not None

    _append_log(ws.log_file, f"rx={rx_text!r} matched={matched!r}")

    return CallResult(
        run_id=ws.run_id,
        tx=tx,
        rx=rx_text,
        matched=matched,
        profile_baud=profile.baud,
        log_file=str(ws.log_file),
        workspace=str(ws.root),
    )
