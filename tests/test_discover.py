from __future__ import annotations

import hashlib
import time
from pathlib import Path

from tt_agent_hw.discover import read_until_quiet, run_discover
from tt_agent_hw.serial_transport import FakeSerialTransport


def test_discover_silent(tmp_path: Path) -> None:
    def factory(port: str, baud: int) -> FakeSerialTransport:
        return FakeSerialTransport(port=port, baud=baud, script={})  # always empty RX

    result = run_discover(
        com=7,
        runtime_dir=tmp_path,
        baud_list=[9600, 115200],
        transport_factory=factory,
        send_break=False,
    )
    assert "FAILED_PROBE_SILENT" in result.status
    assert result.profile is None
    assert not (tmp_path / "profiles" / "COM7.json").exists()


def test_discover_finds_baud_and_writes_profile(tmp_path: Path) -> None:
    help_body = b"\r\nAvailable commands:\r\nreset - reboot\r\nhelp - help\r\n>"

    def factory(port: str, baud: int) -> FakeSerialTransport:
        script: dict[int, list[tuple[bytes | None, bytes]]] = {}
        if baud == 9600:
            script[9600] = [
                (b"\r", b""),
                (b"help", help_body),
                (b"?", b""),
                (b"AT", b""),
                (b"help", help_body),  # harvest
            ]
        return FakeSerialTransport(port=port, baud=baud, script=script)

    result = run_discover(
        com=7,
        runtime_dir=tmp_path,
        baud_list=[115200, 9600],
        transport_factory=factory,
        send_break=False,
        early_stop=True,
    )
    assert "SUCCESS_DISCOVERED" in result.status
    assert result.profile is not None
    assert result.profile.baud == 9600
    assert (tmp_path / "profiles" / "COM7.json").is_file()
    assert any(c.send == "reset" for c in result.profile.commands)


def test_help_raw_preserves_crlf_and_matches_sha(tmp_path: Path) -> None:
    help_body = b"\r\nAvailable commands:\r\nreset - reboot\r\nhelp - help\r\n>"

    def factory(port: str, baud: int) -> FakeSerialTransport:
        script: dict[int, list[tuple[bytes | None, bytes]]] = {}
        if baud == 9600:
            script[9600] = [
                (b"\r", b""),
                (b"help", help_body),
                (b"?", b""),
                (b"AT", b""),
                (b"help", help_body),
            ]
        return FakeSerialTransport(port=port, baud=baud, script=script)

    result = run_discover(
        com=7,
        runtime_dir=tmp_path,
        baud_list=[9600],
        transport_factory=factory,
        send_break=False,
        early_stop=True,
    )
    assert "SUCCESS_DISCOVERED" in result.status
    assert result.profile is not None

    paths = list(tmp_path.glob("workspaces/*/artifacts/help_raw.txt"))
    assert len(paths) == 1
    on_disk = paths[0].read_bytes()
    assert b"\r\n" in on_disk
    assert b"\r\r\n" not in on_disk
    assert on_disk == help_body
    assert result.profile.fingerprint["help_raw_sha256"] == hashlib.sha256(on_disk).hexdigest()


def test_early_stop_skips_pure_length_noise(tmp_path: Path) -> None:
    """Printable noise must not early-stop before a real help baud is tried."""
    help_body = b"\r\nAvailable commands:\r\nreset - reboot\r\nhelp - help\r\n>"
    noise = b"A" * 64

    def factory(port: str, baud: int) -> FakeSerialTransport:
        script: dict[int, list[tuple[bytes | None, bytes]]] = {}
        if baud == 115200:
            script[115200] = [
                (b"\r", noise),
                (b"help", b""),
                (b"?", b""),
                (b"AT", b""),
            ]
        elif baud == 9600:
            script[9600] = [
                (b"\r", b""),
                (b"help", help_body),
                (b"?", b""),
                (b"AT", b""),
                (b"help", help_body),
            ]
        return FakeSerialTransport(port=port, baud=baud, script=script)

    result = run_discover(
        com=7,
        runtime_dir=tmp_path,
        baud_list=[115200, 9600],
        transport_factory=factory,
        send_break=False,
        early_stop=True,
    )
    assert "SUCCESS_DISCOVERED" in result.status
    assert result.profile is not None
    assert result.profile.baud == 9600
    assert any(c.send == "reset" for c in result.profile.commands)


def test_read_until_quiet_waits_for_delayed_first_byte() -> None:
    class _DelayedFirstByte:
        """Empty until wall-clock delay, then one payload, then silence."""

        def __init__(self, delay_s: float, payload: bytes) -> None:
            self._t0 = time.monotonic()
            self._delay_s = delay_s
            self._payload = payload
            self._sent = False

        def read(self, max_bytes: int = 4096, timeout: float | None = None) -> bytes:
            del max_bytes, timeout
            if time.monotonic() - self._t0 < self._delay_s:
                return b""
            if not self._sent:
                self._sent = True
                return self._payload
            return b""

    transport = _DelayedFirstByte(delay_s=0.35, payload=b"hello")
    # quiet_s alone would give up before first byte; first_byte_s must cover delay.
    rx = read_until_quiet(
        transport,  # type: ignore[arg-type]
        quiet_s=0.08,
        max_s=1.0,
        first_byte_s=0.6,
    )
    assert rx == b"hello"


def test_read_until_quiet_gives_up_before_first_byte_budget() -> None:
    class _AlwaysEmpty:
        def read(self, max_bytes: int = 4096, timeout: float | None = None) -> bytes:
            del max_bytes, timeout
            return b""

    t0 = time.monotonic()
    rx = read_until_quiet(
        _AlwaysEmpty(),  # type: ignore[arg-type]
        quiet_s=0.05,
        max_s=2.0,
        first_byte_s=0.2,
    )
    elapsed = time.monotonic() - t0
    assert rx == b""
    assert 0.15 <= elapsed < 0.6
