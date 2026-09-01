"""Hermetic per-run workspace under the runtime root."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunWorkspace:
    run_id: str
    root: Path
    log_dir: Path
    status_dir: Path
    artifacts_dir: Path
    macro_file: Path
    log_file: Path
    status_file: Path


def new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:8]}"


def create_workspace(runtime_dir: Path, run_id: str | None = None) -> RunWorkspace:
    """Create workspaces/run_<id>/{logs,status,artifacts} under runtime_dir."""
    rid = run_id or new_run_id()
    root = Path(runtime_dir) / "workspaces" / rid
    log_dir = root / "logs"
    status_dir = root / "status"
    artifacts_dir = root / "artifacts"
    for d in (log_dir, status_dir, artifacts_dir):
        d.mkdir(parents=True, exist_ok=True)
    return RunWorkspace(
        run_id=rid,
        root=root,
        log_dir=log_dir,
        status_dir=status_dir,
        artifacts_dir=artifacts_dir,
        macro_file=root / "task.ttl",
        log_file=log_dir / "console.log",
        status_file=status_dir / "execution.state",
    )


def ensure_runtime_writable(runtime_dir: Path) -> None:
    """Create runtime root and verify write access."""
    runtime_dir = Path(runtime_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    probe = runtime_dir / ".tt_agent_hw_write_probe"
    try:
        probe.write_text("ok", encoding="ascii")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise PermissionError(f"runtime dir not writable: {runtime_dir}") from exc
