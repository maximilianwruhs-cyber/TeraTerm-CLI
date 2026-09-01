"""Tera Term agent controller: render TTL, spawn macro, poll status."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from jinja2 import Template

from tt_agent_hw.models import ProvisionResult, TargetJob
from tt_agent_hw.paths import template_path, ttl_escape_path
from tt_agent_hw.status import (
    ORCHESTRATOR_NO_STATUS,
    ORCHESTRATOR_PREFLIGHT,
    ORCHESTRATOR_TIMEOUT,
    is_terminal,
    read_status_file,
    write_status_file,
)
from tt_agent_hw.workspace import RunWorkspace, create_workspace, ensure_runtime_writable


class PreflightError(Exception):
    """Configuration or environment not ready for provisioning."""


class TeraTermAgentController:
    """Orchestrates one hermetic flash+verify job via ttpmacro.exe."""

    def __init__(
        self,
        base_dir: Path,
        tt_bin_dir: Path,
        *,
        macro_exe: Path | None = None,
        term_exe: Path | None = None,
        template_file: Path | None = None,
        poll_interval_sec: float = 0.5,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.tt_bin_dir = Path(tt_bin_dir)
        self.macro_exe = Path(macro_exe) if macro_exe else self.tt_bin_dir / "ttpmacro.exe"
        self.term_exe = Path(term_exe) if term_exe else self.tt_bin_dir / "ttermpro.exe"
        self.template_file = Path(template_file) if template_file else template_path()
        self.poll_interval_sec = poll_interval_sec

    def preflight(self, job: TargetJob) -> None:
        ensure_runtime_writable(self.base_dir)
        if not self.macro_exe.is_file():
            raise PreflightError(f"macro engine not found: {self.macro_exe}")
        if not job.binary_path.is_file():
            raise PreflightError(f"firmware binary not found: {job.binary_path}")
        if not self.template_file.is_file():
            raise PreflightError(f"TTL template not found: {self.template_file}")

    def render_macro(self, job: TargetJob, ws: RunWorkspace) -> str:
        template_str = self.template_file.read_text(encoding="utf-8")
        rendered = Template(template_str).render(
            execution_id=ws.run_id,
            com_port=job.com_port,
            baud_rate=job.baud_rate,
            boot_prompt=job.boot_prompt,
            erase_command=job.erase_command,
            erase_ack=job.erase_ack,
            transfer_trigger_command=job.transfer_trigger_command,
            boot_command=job.boot_command,
            boot_success_regex=job.boot_success_regex,
            boot_timeout=job.boot_timeout,
            binary_path=ttl_escape_path(job.binary_path.resolve()),
            log_dir=ttl_escape_path(ws.log_dir.resolve()),
            status_dir=ttl_escape_path(ws.status_dir.resolve()),
            log_file=ttl_escape_path(ws.log_file.resolve()),
            status_file=ttl_escape_path(ws.status_file.resolve()),
        )
        # TTL engine historically prefers ASCII; keep UTF-8 only if needed later.
        ws.macro_file.write_text(rendered, encoding="ascii", errors="replace")
        return rendered

    def execute_provisioning(self, job: TargetJob) -> ProvisionResult:
        start = time.monotonic()
        try:
            self.preflight(job)
        except (PreflightError, PermissionError, OSError) as exc:
            try:
                ws = create_workspace(self.base_dir)
                write_status_file(ws.status_file, ORCHESTRATOR_PREFLIGHT)
                (ws.log_dir / "preflight_error.txt").write_text(str(exc), encoding="utf-8")
                return ProvisionResult(
                    run_id=ws.run_id,
                    status=ORCHESTRATOR_PREFLIGHT,
                    log_file=str(ws.log_file),
                    duration_sec=round(time.monotonic() - start, 2),
                    workspace=str(ws.root),
                )
            except OSError:
                return ProvisionResult(
                    run_id="run_none",
                    status=ORCHESTRATOR_PREFLIGHT,
                    log_file="",
                    duration_sec=round(time.monotonic() - start, 2),
                    workspace="",
                )

        ws = create_workspace(self.base_dir)
        self.render_macro(job, ws)

        cmd = self._macro_command(ws.macro_file)
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(self.tt_bin_dir if self.tt_bin_dir.is_dir() else ws.root),
            )
        except OSError as exc:
            write_status_file(ws.status_file, ORCHESTRATOR_PREFLIGHT)
            (ws.log_dir / "spawn_error.txt").write_text(str(exc), encoding="utf-8")
            return ProvisionResult(
                run_id=ws.run_id,
                status=ORCHESTRATOR_PREFLIGHT,
                log_file=str(ws.log_file),
                duration_sec=round(time.monotonic() - start, 2),
                workspace=str(ws.root),
            )

        max_duration = float(job.boot_timeout) + 60.0
        final_status = ORCHESTRATOR_TIMEOUT

        while (time.monotonic() - start) < max_duration:
            status = read_status_file(ws.status_file)
            if is_terminal(status):
                final_status = status or ORCHESTRATOR_NO_STATUS
                break

            rc = process.poll()
            if rc is not None:
                status = read_status_file(ws.status_file)
                if is_terminal(status):
                    final_status = status or ORCHESTRATOR_NO_STATUS
                elif status:
                    final_status = status
                else:
                    final_status = ORCHESTRATOR_NO_STATUS
                break

            time.sleep(self.poll_interval_sec)

        if process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            if not is_terminal(read_status_file(ws.status_file)):
                final_status = ORCHESTRATOR_TIMEOUT
                write_status_file(ws.status_file, ORCHESTRATOR_TIMEOUT)
            else:
                final_status = read_status_file(ws.status_file) or ORCHESTRATOR_TIMEOUT

        return ProvisionResult(
            run_id=ws.run_id,
            status=final_status,
            log_file=str(ws.log_file),
            duration_sec=round(time.monotonic() - start, 2),
            workspace=str(ws.root),
        )

    def _macro_command(self, macro_file: Path) -> list[str]:
        """Build process argv. Python fakes use sys.executable."""
        exe = self.macro_exe
        suffix = exe.suffix.lower()
        if suffix == ".py":
            return [sys.executable, str(exe), str(macro_file)]
        if suffix in {".cmd", ".bat"}:
            return ["cmd", "/c", str(exe), str(macro_file)]
        # Real ttpmacro.exe: /V = invisible
        return [str(exe), "/V", str(macro_file)]
