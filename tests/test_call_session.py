from __future__ import annotations

import time
from pathlib import Path

import pytest

from tt_agent_hw.call_session import run_call
from tt_agent_hw.models import BaudAttempt, DeviceProfile, DiscoveredCommand
from tt_agent_hw.profile_store import save_profile
from tt_agent_hw.serial_io import append_cr
from tt_agent_hw.serial_transport import FakeSerialTransport


@pytest.fixture
def profile_on_disk(tmp_path: Path) -> DeviceProfile:
    profile = DeviceProfile(
        schema_version=1,
        com=7,
        port_name="COM7",
        baud=9600,
        framing={"bytesize": 8, "parity": "N", "stopbits": 1},
        usb_hint={"friendly_name": "USB Serial Port (COM7)"},
        fingerprint={
            "banner": "hi",
            "help_raw_path": "artifacts/help_raw.txt",
            "help_raw_sha256": "",
        },
        commands=[
            DiscoveredCommand(
                id="help", send="help", summary="nudge", source="nudge"
            )
        ],
        nudges_tried=["cr", "help"],
        baud_tried=[BaudAttempt(baud=9600, bytes_rx=10, score=0.8)],
        confidence=0.8,
        discovered_at="2026-09-01T00:00:00Z",
        run_id="run_abc",
        tool_version="0.2.0",
    )
    save_profile(tmp_path, profile)
    return profile


def test_append_cr_adds_once() -> None:
    assert append_cr("help") == b"help\r"
    assert append_cr(b"help\r") == b"help\r"
    assert append_cr("help\r") == b"help\r"


def test_call_by_id_expect_match(tmp_path: Path, profile_on_disk: DeviceProfile) -> None:
    del profile_on_disk

    def factory(port: str, baud: int) -> FakeSerialTransport:
        return FakeSerialTransport(
            port=port,
            baud=baud,
            script={baud: [(b"help", b"help text OK\r\n")]},
        )

    result = run_call(
        runtime_dir=tmp_path,
        com=7,
        command_id="help",
        expect="OK",
        transport_factory=factory,
    )
    assert result.matched is True
    assert "OK" in result.rx
    assert result.tx == "help"
    assert result.profile_baud == 9600
    assert result.run_id
    assert Path(result.log_file).is_file()
    assert Path(result.workspace).is_dir()


def test_call_expect_miss(tmp_path: Path, profile_on_disk: DeviceProfile) -> None:
    del profile_on_disk

    def factory(port: str, baud: int) -> FakeSerialTransport:
        return FakeSerialTransport(
            port=port,
            baud=baud,
            script={baud: [(b"help", b"help text FAIL\r\n")]},
        )

    result = run_call(
        runtime_dir=tmp_path,
        com=7,
        command_id="help",
        expect="OK",
        transport_factory=factory,
    )
    assert result.matched is False
    assert "OK" not in result.rx


def test_call_no_expect_matched_none(tmp_path: Path, profile_on_disk: DeviceProfile) -> None:
    del profile_on_disk

    def factory(port: str, baud: int) -> FakeSerialTransport:
        return FakeSerialTransport(
            port=port,
            baud=baud,
            script={baud: [(b"help", b"anything\r\n")]},
        )

    result = run_call(
        runtime_dir=tmp_path,
        com=7,
        command_id="help",
        transport_factory=factory,
    )
    assert result.matched is None


def test_call_by_send(tmp_path: Path, profile_on_disk: DeviceProfile) -> None:
    del profile_on_disk

    def factory(port: str, baud: int) -> FakeSerialTransport:
        return FakeSerialTransport(
            port=port,
            baud=baud,
            script={baud: [(b"raw line", b"echo raw\r\n")]},
        )

    result = run_call(
        runtime_dir=tmp_path,
        com=7,
        send="raw line",
        expect="echo",
        transport_factory=factory,
    )
    assert result.matched is True
    assert result.tx == "raw line"


def test_call_missing_profile(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_call(runtime_dir=tmp_path, com=7, command_id="help")


def test_call_neither_or_both_raises(tmp_path: Path, profile_on_disk: DeviceProfile) -> None:
    del profile_on_disk
    with pytest.raises(ValueError):
        run_call(runtime_dir=tmp_path, com=7)
    with pytest.raises(ValueError):
        run_call(runtime_dir=tmp_path, com=7, command_id="help", send="x")


def test_call_unknown_id(tmp_path: Path, profile_on_disk: DeviceProfile) -> None:
    del profile_on_disk
    with pytest.raises(KeyError):
        run_call(runtime_dir=tmp_path, com=7, command_id="nope")


def test_call_timeout_waits_for_delayed_first_byte(
    tmp_path: Path, profile_on_disk: DeviceProfile
) -> None:
    del profile_on_disk

    class _DelayedHelp(FakeSerialTransport):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self._delay_s = 1.0
            self._payload = b"late OK\r\n"
            self._t0: float | None = None
            self._sent = False

        def write(self, data: bytes) -> None:
            super().write(data)
            self._t0 = time.monotonic()
            self._sent = False
            self._rx.clear()

        def read(self, max_bytes: int = 4096, timeout: float | None = None) -> bytes:
            del max_bytes, timeout
            self._require_open()
            if self._t0 is None:
                return b""
            if time.monotonic() - self._t0 < self._delay_s:
                return b""
            if not self._sent:
                self._sent = True
                return self._payload
            return b""

    def factory(port: str, baud: int) -> FakeSerialTransport:
        return _DelayedHelp(port=port, baud=baud, script={})

    result = run_call(
        runtime_dir=tmp_path,
        com=7,
        command_id="help",
        expect="OK",
        timeout_s=2.0,
        transport_factory=factory,
    )
    assert result.matched is True
    assert "OK" in result.rx

