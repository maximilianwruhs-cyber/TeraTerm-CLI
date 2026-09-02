from __future__ import annotations

from pathlib import Path

from tt_agent_hw.discover import run_discover
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
