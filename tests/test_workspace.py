from __future__ import annotations

from pathlib import Path

import pytest

from tt_agent_hw.workspace import create_workspace, ensure_runtime_writable


def test_create_workspace_layout(tmp_path: Path) -> None:
    ws = create_workspace(tmp_path, run_id="run_deadbeef")
    assert ws.run_id == "run_deadbeef"
    assert ws.root == tmp_path / "workspaces" / "run_deadbeef"
    assert ws.log_dir.is_dir()
    assert ws.status_dir.is_dir()
    assert ws.artifacts_dir.is_dir()
    assert ws.macro_file == ws.root / "task.ttl"
    assert ws.log_file == ws.log_dir / "console.log"
    assert ws.status_file == ws.status_dir / "execution.state"


def test_ensure_runtime_writable(tmp_path: Path) -> None:
    target = tmp_path / "runtime"
    ensure_runtime_writable(target)
    assert target.is_dir()


def test_ensure_runtime_writable_fails_on_file(tmp_path: Path) -> None:
    blocked = tmp_path / "not_a_dir"
    blocked.write_text("x", encoding="ascii")
    with pytest.raises((PermissionError, OSError)):
        ensure_runtime_writable(blocked)
