from __future__ import annotations

from pathlib import Path

from tt_agent_hw.cli import main
from tt_agent_hw.models import CallResult, DiscoverResult
from tt_agent_hw.ports import PortInfo
from tt_agent_hw.status import FAILED_PROBE_SILENT, SUCCESS_DISCOVERED


def test_cli_discover_success(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TT_AGENT_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr("tt_agent_hw.cli.list_ports", lambda **kwargs: [])

    def fake_run_discover(**kwargs):
        assert kwargs["com"] == 7
        return DiscoverResult(
            run_id="run_test",
            status=SUCCESS_DISCOVERED,
            profile_path=str(tmp_path / "profiles" / "COM7.json"),
            log_file=str(tmp_path / "log.txt"),
            duration_sec=0.5,
            workspace=str(tmp_path / "ws"),
            profile=None,
        )

    monkeypatch.setattr("tt_agent_hw.cli.run_discover", fake_run_discover)
    assert main(["discover", "--com", "7", "--json"]) == 0


def test_cli_discover_silent_exit_1(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TT_AGENT_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr("tt_agent_hw.cli.list_ports", lambda **kwargs: [])

    def fake_run_discover(**kwargs):
        return DiscoverResult(
            run_id="run_silent",
            status=FAILED_PROBE_SILENT,
            profile_path=None,
            log_file=str(tmp_path / "log.txt"),
            duration_sec=0.1,
            workspace=str(tmp_path / "ws"),
            profile=None,
        )

    monkeypatch.setattr("tt_agent_hw.cli.run_discover", fake_run_discover)
    assert main(["discover", "--com", "3"]) == 1


def test_cli_discover_no_default_com(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TT_AGENT_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr("tt_agent_hw.cli.list_ports", lambda **kwargs: [])
    assert main(["discover"]) == 2


def test_cli_ports_json(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setenv("TT_AGENT_RUNTIME_DIR", str(tmp_path))

    def fake_list_ports(**kwargs):
        return [
            PortInfo(
                name="COM7",
                com=7,
                description="USB Serial",
                hardware_id="USB\\VID_1234",
                has_profile=False,
            )
        ]

    monkeypatch.setattr("tt_agent_hw.cli.list_ports", fake_list_ports)
    assert main(["ports", "--json"]) == 0
    out = capsys.readouterr().out
    assert "COM7" in out
    assert '"com": 7' in out or '"com":7' in out


def test_cli_call_requires_profile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TT_AGENT_RUNTIME_DIR", str(tmp_path))
    assert main(["call", "--com", "7", "help"]) == 2


def test_cli_cmds_missing_profile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TT_AGENT_RUNTIME_DIR", str(tmp_path))
    assert main(["cmds", "--com", "9"]) == 2


def test_cli_profile_show_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TT_AGENT_RUNTIME_DIR", str(tmp_path))
    assert main(["profile", "show", "--com", "9"]) == 2


def test_cli_call_matched_false(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TT_AGENT_RUNTIME_DIR", str(tmp_path))

    def fake_run_call(**kwargs):
        return CallResult(
            run_id="run_call",
            tx="help\r",
            rx="nope",
            matched=False,
            profile_baud=115200,
            log_file=str(tmp_path / "log.txt"),
            workspace=str(tmp_path / "ws"),
        )

    monkeypatch.setattr("tt_agent_hw.cli.run_call", fake_run_call)
    assert main(["call", "--com", "7", "help", "--json"]) == 1


def test_cli_call_matched_true(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TT_AGENT_RUNTIME_DIR", str(tmp_path))

    def fake_run_call(**kwargs):
        assert kwargs["com"] == 7
        assert kwargs["command_id"] == "help"
        return CallResult(
            run_id="run_call",
            tx="help\r",
            rx="OK",
            matched=True,
            profile_baud=115200,
            log_file=str(tmp_path / "log.txt"),
            workspace=str(tmp_path / "ws"),
        )

    monkeypatch.setattr("tt_agent_hw.cli.run_call", fake_run_call)
    assert main(["call", "--com", "7", "help"]) == 0


def test_cli_discover_invalid_baud_list(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TT_AGENT_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(
        "tt_agent_hw.cli.list_ports",
        lambda **kwargs: [
            PortInfo(
                name="COM7",
                com=7,
                description="USB Serial",
                hardware_id="USB\\VID_1234",
                has_profile=False,
            )
        ],
    )

    def boom(**kwargs):
        raise AssertionError("run_discover should not be called for bad baud-list")

    monkeypatch.setattr("tt_agent_hw.cli.run_discover", boom)
    assert main(["discover", "--com", "7", "--baud-list", "abc"]) == 2
    assert main(["discover", "--com", "7", "--baud-list", ""]) == 2
    assert main(["discover", "--com", "7", "--baud-list", ","]) == 2


def test_cli_discover_passes_usb_hint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TT_AGENT_RUNTIME_DIR", str(tmp_path))
    seen: dict = {}

    monkeypatch.setattr(
        "tt_agent_hw.cli.list_ports",
        lambda **kwargs: [
            PortInfo(
                name="COM7",
                com=7,
                description="USB Serial Device",
                hardware_id="USB\\VID_ABCD&PID_0001",
                has_profile=False,
            )
        ],
    )

    def fake_run_discover(**kwargs):
        seen.update(kwargs)
        return DiscoverResult(
            run_id="run_hint",
            status=SUCCESS_DISCOVERED,
            profile_path=None,
            log_file=str(tmp_path / "log.txt"),
            duration_sec=0.1,
            workspace=str(tmp_path / "ws"),
            profile=None,
        )

    monkeypatch.setattr("tt_agent_hw.cli.run_discover", fake_run_discover)
    assert main(["discover", "--com", "7"]) == 0
    assert seen.get("usb_hint") == {
        "name": "COM7",
        "description": "USB Serial Device",
        "hardware_id": "USB\\VID_ABCD&PID_0001",
    }

