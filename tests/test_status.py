from __future__ import annotations

from pathlib import Path

from tt_agent_hw.status import (
    is_success,
    is_terminal,
    normalize_status_line,
    read_status_file,
    write_status_file,
)


def test_normalize_strips_and_keeps_prefix() -> None:
    assert normalize_status_line("  STATUS=SUCCESS_PROVISIONED\n") == "STATUS=SUCCESS_PROVISIONED"
    assert normalize_status_line("nope") is None
    assert normalize_status_line("") is None


def test_terminal_classification() -> None:
    assert is_terminal("STATUS=INITIALIZING") is False
    assert is_terminal("STATUS=SUCCESS_PROVISIONED") is True
    assert is_terminal("STATUS=FAILED_FLASH_ERASE") is True
    assert is_terminal("STATUS=TIMEOUT_ORCHESTRATOR") is True
    assert is_success("STATUS=SUCCESS_PROVISIONED") is True
    assert is_success("STATUS=FAILED_BOOT_TIMEOUT") is False


def test_read_write_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "status" / "execution.state"
    write_status_file(path, "STATUS=SUCCESS_PROVISIONED")
    assert read_status_file(path) == "STATUS=SUCCESS_PROVISIONED"
    assert read_status_file(tmp_path / "missing.state") is None
