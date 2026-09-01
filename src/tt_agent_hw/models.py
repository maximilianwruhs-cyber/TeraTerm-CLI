"""Job and result models for hardware provisioning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TargetJob:
    """Single-target UART flash + boot-verify parameters."""

    com_port: int
    baud_rate: int
    boot_prompt: str
    erase_command: str
    erase_ack: str
    transfer_trigger_command: str
    boot_command: str
    boot_success_regex: str
    boot_timeout: int
    binary_path: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "binary_path", Path(self.binary_path))


@dataclass(frozen=True)
class ProvisionResult:
    """Structured outcome of one provisioning run."""

    run_id: str
    status: str
    log_file: str
    duration_sec: float
    workspace: str

    def is_success(self) -> bool:
        return "SUCCESS" in self.status

    def is_timeout(self) -> bool:
        return "TIMEOUT_ORCHESTRATOR" in self.status

    def to_dict(self) -> dict[str, str | float]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "log_file": self.log_file,
            "duration_sec": self.duration_sec,
            "workspace": self.workspace,
        }
