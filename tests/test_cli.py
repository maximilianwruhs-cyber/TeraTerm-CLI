from __future__ import annotations

from pathlib import Path

from tt_agent_hw.cli import main

FIXTURE_MACRO = Path(__file__).parent / "fixtures" / "fake_ttpmacro.py"


def test_cli_provision_success(tmp_path: Path, monkeypatch) -> None:
    firmware = tmp_path / "fw.bin"
    firmware.write_bytes(b"FW")
    monkeypatch.setenv("FAKE_TT_STATUS", "STATUS=SUCCESS_PROVISIONED")
    monkeypatch.setenv("FAKE_TT_DELAY", "0.1")
    monkeypatch.delenv("FAKE_TT_HANG", raising=False)

    code = main(
        [
            "provision",
            "--com",
            "4",
            "--binary",
            str(firmware),
            "--boot-prompt",
            "U-Boot>",
            "--erase-command",
            "sf erase",
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
            str(tmp_path / "rt"),
            "--tt-bin-dir",
            str(tmp_path),
            "--macro-exe",
            str(FIXTURE_MACRO),
            "--json",
        ]
    )
    assert code == 0


def test_cli_provision_failure_exit_1(tmp_path: Path, monkeypatch) -> None:
    firmware = tmp_path / "fw.bin"
    firmware.write_bytes(b"FW")
    monkeypatch.setenv("FAKE_TT_STATUS", "FAILED_FLASH_ERASE")
    monkeypatch.setenv("FAKE_TT_DELAY", "0.1")

    code = main(
        [
            "provision",
            "--com",
            "1",
            "--binary",
            str(firmware),
            "--boot-prompt",
            ">",
            "--erase-command",
            "erase",
            "--erase-ack",
            "OK",
            "--transfer-trigger",
            "loady",
            "--boot-command",
            "boot",
            "--boot-success-regex",
            "Ready",
            "--runtime-dir",
            str(tmp_path / "rt"),
            "--tt-bin-dir",
            str(tmp_path),
            "--macro-exe",
            str(FIXTURE_MACRO),
        ]
    )
    assert code == 1
