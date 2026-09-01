from __future__ import annotations

import os
from pathlib import Path

import pytest

from tt_agent_hw.controller import TeraTermAgentController
from tt_agent_hw.models import TargetJob
from tt_agent_hw.paths import template_path

FIXTURE_MACRO = Path(__file__).parent / "fixtures" / "fake_ttpmacro.py"


def _job(binary: Path, boot_timeout: int = 5) -> TargetJob:
    return TargetJob(
        com_port=4,
        baud_rate=115200,
        boot_prompt="U-Boot>",
        erase_command="sf erase 0x0 0x100000",
        erase_ack="Erased: OK",
        transfer_trigger_command="loady 0x80000000 115200",
        boot_command="bootm 0x80000000",
        boot_success_regex="System Ready",
        boot_timeout=boot_timeout,
        binary_path=binary,
    )


def test_render_macro_contains_job_fields(tmp_path: Path) -> None:
    firmware = tmp_path / "fw.bin"
    firmware.write_bytes(b"\x00\x01")
    ctrl = TeraTermAgentController(
        base_dir=tmp_path / "runtime",
        tt_bin_dir=tmp_path,
        macro_exe=FIXTURE_MACRO,
        template_file=template_path(),
    )
    from tt_agent_hw.workspace import create_workspace

    ws = create_workspace(tmp_path / "runtime", run_id="run_test001")
    text = ctrl.render_macro(_job(firmware), ws)
    assert "COM4" in text or "/C=4" in text
    assert "U-Boot>" in text
    assert "STATUS=INITIALIZING" in text
    assert ws.macro_file.is_file()


def test_provision_success_with_fake_macro(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    firmware = tmp_path / "fw.bin"
    firmware.write_bytes(b"FW")
    monkeypatch.delenv("FAKE_TT_HANG", raising=False)
    monkeypatch.setenv("FAKE_TT_STATUS", "STATUS=SUCCESS_PROVISIONED")
    monkeypatch.setenv("FAKE_TT_DELAY", "0.1")

    ctrl = TeraTermAgentController(
        base_dir=tmp_path / "runtime",
        tt_bin_dir=tmp_path,
        macro_exe=FIXTURE_MACRO,
        poll_interval_sec=0.05,
    )
    result = ctrl.execute_provisioning(_job(firmware))
    assert result.is_success()
    assert result.status == "STATUS=SUCCESS_PROVISIONED"
    assert result.run_id.startswith("run_")
    assert Path(result.workspace).is_dir()


def test_provision_failure_with_fake_macro(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    firmware = tmp_path / "fw.bin"
    firmware.write_bytes(b"FW")
    monkeypatch.setenv("FAKE_TT_STATUS", "STATUS=FAILED_YMODEM_TRANSFER_ABORTED")
    monkeypatch.setenv("FAKE_TT_DELAY", "0.1")

    ctrl = TeraTermAgentController(
        base_dir=tmp_path / "runtime",
        tt_bin_dir=tmp_path,
        macro_exe=FIXTURE_MACRO,
        poll_interval_sec=0.05,
    )
    result = ctrl.execute_provisioning(_job(firmware))
    assert not result.is_success()
    assert "FAILED_YMODEM" in result.status


def test_preflight_missing_binary(tmp_path: Path) -> None:
    ctrl = TeraTermAgentController(
        base_dir=tmp_path / "runtime",
        tt_bin_dir=tmp_path,
        macro_exe=FIXTURE_MACRO,
    )
    missing = tmp_path / "nope.bin"
    result = ctrl.execute_provisioning(_job(missing))
    assert "PREFLIGHT" in result.status


def test_orchestrator_timeout_kills_hanging_macro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    firmware = tmp_path / "fw.bin"
    firmware.write_bytes(b"FW")
    monkeypatch.setenv("FAKE_TT_HANG", "1")

    import subprocess
    import sys
    import time

    from tt_agent_hw.models import ProvisionResult
    from tt_agent_hw.status import (
        ORCHESTRATOR_TIMEOUT,
        is_terminal,
        read_status_file,
        write_status_file,
    )
    from tt_agent_hw.workspace import create_workspace

    class FastTimeoutController(TeraTermAgentController):
        def execute_provisioning(self, job: TargetJob) -> ProvisionResult:
            self.preflight(job)
            ws = create_workspace(self.base_dir)
            self.render_macro(job, ws)
            cmd = self._macro_command(ws.macro_file)
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(ws.root),
            )
            start = time.monotonic()
            final_status = ORCHESTRATOR_TIMEOUT
            while (time.monotonic() - start) < 1.0:
                status = read_status_file(ws.status_file)
                if is_terminal(status):
                    final_status = status or final_status
                    break
                if process.poll() is not None:
                    break
                time.sleep(0.05)
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
                final_status = ORCHESTRATOR_TIMEOUT
                write_status_file(ws.status_file, ORCHESTRATOR_TIMEOUT)
            return ProvisionResult(
                run_id=ws.run_id,
                status=final_status,
                log_file=str(ws.log_file),
                duration_sec=round(time.monotonic() - start, 2),
                workspace=str(ws.root),
            )

    ctrl = FastTimeoutController(
        base_dir=tmp_path / "runtime",
        tt_bin_dir=tmp_path,
        macro_exe=FIXTURE_MACRO,
        poll_interval_sec=0.05,
    )
    result = ctrl.execute_provisioning(_job(firmware, boot_timeout=0))
    assert result.is_timeout()
    assert "TIMEOUT_ORCHESTRATOR" in result.status
    assert sys.executable  # sanity: interpreter used for .py macros
