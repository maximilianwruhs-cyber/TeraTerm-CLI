"""Baud sweep discover controller: nudge, score, harvest, profile write."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from tt_agent_hw import __version__
from tt_agent_hw.commands_extract import extract_commands
from tt_agent_hw.models import BaudAttempt, DeviceProfile, DiscoverResult
from tt_agent_hw.profile_store import save_profile
from tt_agent_hw.scoring import SILENCE_FLOOR, STRONG_SCORE, score_rx
from tt_agent_hw.serial_io import read_until_quiet  # re-export for callers/tests
from tt_agent_hw.serial_transport import PyserialTransport, SerialTransport
from tt_agent_hw.status import (
    FAILED_PROBE_SILENT,
    SUCCESS_DISCOVERED,
    write_status_file,
)
from tt_agent_hw.workspace import RunWorkspace, create_workspace, ensure_runtime_writable

DEFAULT_BAUD_LIST: list[int] = [115200, 57600, 38400, 19200, 9600, 4800]

NUDGES: list[tuple[str, bytes]] = [
    ("cr", b"\r"),
    ("help", b"help\r"),
    ("?", b"?\r"),
    ("AT", b"AT\r"),
]

_DEFAULT_FRAMING = {"bytesize": 8, "parity": "N", "stopbits": 1}
_FAILED_CONNECTION_REFUSED = "STATUS=FAILED_CONNECTION_REFUSED"
_STATUS_INITIALIZING = "STATUS=INITIALIZING"
_MIN_STRONG_BYTES = 1

# Logical TX payload for each nudge (without trailing CR), used as command send text.
_NUDGE_SEND: dict[str, str] = {
    "cr": "",
    "help": "help",
    "?": "?",
    "AT": "AT",
}


class DiscoverError(Exception):
    """Discover pipeline failure."""


TransportFactory = Callable[[str, int], SerialTransport]


def _default_transport_factory(port: str, baud: int) -> SerialTransport:
    return PyserialTransport(port=port, baud=baud)


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _nudge_send_text(name: str) -> str:
    return _NUDGE_SEND.get(name, name)


def _preferred_harvest_nudge(productive: list[tuple[str, bytes]]) -> tuple[str, bytes]:
    """Pick help-like productive nudge: help, then ?, else first productive."""
    by_name = {name: rx for name, rx in productive}
    for name in ("help", "?"):
        if name in by_name:
            payload = next(p for n, p in NUDGES if n == name)
            return name, payload
    name, _rx = productive[0]
    payload = next(p for n, p in NUDGES if n == name)
    return name, payload


def _probe_baud(
    transport: SerialTransport,
    *,
    send_break: bool,
) -> tuple[bytes, list[tuple[str, bytes]], list[str]]:
    """Run nudge ladder; return aggregate RX, per-nudge RX pairs, names tried."""
    if send_break:
        transport.send_break(0.25)
    transport.reset_input_buffer()

    aggregate = bytearray()
    per_nudge: list[tuple[str, bytes]] = []
    tried: list[str] = []
    for name, payload in NUDGES:
        tried.append(name)
        transport.write(payload)
        rx = read_until_quiet(transport)
        per_nudge.append((name, rx))
        if rx:
            aggregate.extend(rx)
    return bytes(aggregate), per_nudge, tried


def _harvest_help(
    transport: SerialTransport,
    *,
    productive: list[tuple[str, bytes]],
    fallback_raw: bytes,
) -> bytes:
    if not productive:
        return fallback_raw
    _name, payload = _preferred_harvest_nudge(productive)
    transport.reset_input_buffer()
    transport.write(payload)
    harvested = read_until_quiet(transport)
    return harvested if harvested else fallback_raw


def _write_scores_artifact(ws: RunWorkspace, attempts: list[BaudAttempt]) -> None:
    path = ws.artifacts_dir / "discover_scores.json"
    path.write_text(
        json.dumps([a.to_dict() for a in attempts], indent=2) + "\n",
        encoding="utf-8",
    )


def _append_log(ws: RunWorkspace, line: str) -> None:
    with ws.log_file.open("a", encoding="utf-8") as fh:
        fh.write(line.rstrip("\n") + "\n")


def run_discover(
    *,
    com: int,
    runtime_dir: Path,
    baud_list: list[int] | None = None,
    send_break: bool = True,
    early_stop: bool = True,
    transport_factory: TransportFactory | None = None,
    usb_hint: dict | None = None,
    tool_version: str = __version__,
) -> DiscoverResult:
    """Sweep bauds, score RX, harvest help, and persist a per-COM profile."""
    runtime_dir = Path(runtime_dir)
    ensure_runtime_writable(runtime_dir)
    ws = create_workspace(runtime_dir)
    write_status_file(ws.status_file, _STATUS_INITIALIZING)
    started = time.monotonic()

    bauds = list(baud_list) if baud_list is not None else list(DEFAULT_BAUD_LIST)
    factory = transport_factory or _default_transport_factory
    port_name = f"COM{com}"
    hint = dict(usb_hint or {})

    attempts: list[BaudAttempt] = []
    nudge_names_tried: list[str] = [name for name, _ in NUDGES]
    # Best non-silent probe so far.
    best: dict | None = None
    opened_any = False
    open_failures = 0
    help_raw = b""
    harvested = False

    def _finish(status: str, profile: DeviceProfile | None) -> DiscoverResult:
        write_status_file(ws.status_file, status)
        _write_scores_artifact(ws, attempts)
        duration = time.monotonic() - started
        profile_path: str | None = None
        if profile is not None:
            dest = save_profile(runtime_dir, profile)
            profile_path = str(dest)
        return DiscoverResult(
            run_id=ws.run_id,
            status=status,
            profile_path=profile_path,
            log_file=str(ws.log_file),
            duration_sec=duration,
            workspace=str(ws.root),
            profile=profile,
        )

    for baud in bauds:
        transport = factory(port_name, baud)
        try:
            transport.open()
        except Exception as exc:  # noqa: BLE001 — any open failure is connection refuse path
            open_failures += 1
            _append_log(ws, f"open failed baud={baud}: {exc}")
            attempts.append(BaudAttempt(baud=baud, bytes_rx=0, score=0.0))
            continue

        opened_any = True
        try:
            aggregate, per_nudge, tried = _probe_baud(transport, send_break=send_break)
            nudge_names_tried = tried
            score = score_rx(aggregate)
            attempt = BaudAttempt(baud=baud, bytes_rx=len(aggregate), score=score)
            attempts.append(attempt)
            _append_log(
                ws,
                f"probe baud={baud} bytes={len(aggregate)} score={score:.4f}",
            )

            productive = [(n, rx) for n, rx in per_nudge if rx]
            if score > SILENCE_FLOOR and (
                best is None or score > float(best["score"])
            ):
                best = {
                    "baud": baud,
                    "score": score,
                    "aggregate": aggregate,
                    "productive": productive,
                    "per_nudge": per_nudge,
                }

            strong = score >= STRONG_SCORE and len(aggregate) >= _MIN_STRONG_BYTES
            if early_stop and strong and productive:
                # Harvest on the live link before close (keeps fake FIFO intact).
                fallback = next(
                    (rx for n, rx in productive if n in ("help", "?")),
                    productive[0][1],
                )
                help_raw = _harvest_help(
                    transport,
                    productive=productive,
                    fallback_raw=fallback,
                )
                harvested = True
                break
        finally:
            try:
                transport.close()
            except Exception:  # noqa: BLE001
                pass

    if not opened_any and open_failures:
        return _finish(_FAILED_CONNECTION_REFUSED, None)

    if best is None:
        return _finish(FAILED_PROBE_SILENT, None)

    win_baud = int(best["baud"])
    win_score = float(best["score"])
    productive: list[tuple[str, bytes]] = list(best["productive"])

    if not harvested:
        fallback = b""
        if productive:
            fallback = next(
                (rx for n, rx in productive if n in ("help", "?")),
                productive[0][1],
            )
        transport = factory(port_name, win_baud)
        try:
            transport.open()
            if send_break:
                transport.send_break(0.25)
            transport.reset_input_buffer()
            help_raw = _harvest_help(
                transport,
                productive=productive,
                fallback_raw=fallback or bytes(best["aggregate"]),
            )
        except Exception as exc:  # noqa: BLE001
            _append_log(ws, f"harvest open failed: {exc}")
            help_raw = fallback or bytes(best["aggregate"])
        finally:
            try:
                if transport.is_open:
                    transport.close()
            except Exception:  # noqa: BLE001
                pass

    help_text = help_raw.decode("utf-8", errors="replace")
    help_path = ws.artifacts_dir / "help_raw.txt"
    # Binary write preserves device CRLF; text mode would expand \n → \r\n on Windows.
    help_path.write_bytes(help_raw)
    help_sha = hashlib.sha256(help_raw).hexdigest()

    productive_sends: list[str] = []
    for name, _rx in productive:
        send = _nudge_send_text(name)
        # Skip empty CR-only as a named command send; still a tried nudge.
        if send == "" and name == "cr":
            continue
        if send not in productive_sends:
            productive_sends.append(send)

    commands = extract_commands(help_text, productive_nudges=productive_sends)

    # Banner: first non-empty line of aggregate/help if present.
    banner = ""
    for line in help_text.splitlines():
        stripped = line.strip()
        if stripped:
            banner = stripped[:200]
            break

    profile = DeviceProfile(
        schema_version=1,
        com=com,
        port_name=port_name,
        baud=win_baud,
        framing=dict(_DEFAULT_FRAMING),
        usb_hint=hint,
        fingerprint={
            "banner": banner,
            "help_raw_path": "artifacts/help_raw.txt",
            "help_raw_sha256": help_sha,
        },
        commands=commands,
        nudges_tried=list(nudge_names_tried),
        baud_tried=list(attempts),
        confidence=win_score,
        discovered_at=_utc_now_iso(),
        run_id=ws.run_id,
        tool_version=tool_version,
    )
    _append_log(ws, f"discovered baud={win_baud} confidence={win_score:.4f}")
    return _finish(SUCCESS_DISCOVERED, profile)
