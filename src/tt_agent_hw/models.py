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


@dataclass(frozen=True)
class DiscoveredCommand:
    """A command discovered from nudge or help parsing."""

    id: str
    send: str
    summary: str
    source: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "send": self.send,
            "summary": self.summary,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DiscoveredCommand:
        return cls(
            id=str(data["id"]),
            send=str(data["send"]),
            summary=str(data.get("summary", "")),
            source=str(data.get("source", "")),
        )


@dataclass(frozen=True)
class BaudAttempt:
    """Result of probing one baud rate during discover."""

    baud: int
    bytes_rx: int
    score: float

    def to_dict(self) -> dict[str, int | float]:
        return {
            "baud": self.baud,
            "bytes_rx": self.bytes_rx,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BaudAttempt:
        return cls(
            baud=int(data["baud"]),
            bytes_rx=int(data["bytes_rx"]),
            score=float(data["score"]),
        )


@dataclass
class DeviceProfile:
    """Persisted per-COM discovery profile (profiles/COMn.json)."""

    schema_version: int
    com: int
    port_name: str
    baud: int
    framing: dict
    usb_hint: dict
    fingerprint: dict
    commands: list[DiscoveredCommand]
    nudges_tried: list[str]
    baud_tried: list[BaudAttempt]
    confidence: float
    discovered_at: str
    run_id: str
    tool_version: str

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "com": self.com,
            "port_name": self.port_name,
            "baud": self.baud,
            "framing": dict(self.framing),
            "usb_hint": dict(self.usb_hint),
            "fingerprint": dict(self.fingerprint),
            "commands": [c.to_dict() for c in self.commands],
            "nudges_tried": list(self.nudges_tried),
            "baud_tried": [b.to_dict() for b in self.baud_tried],
            "confidence": self.confidence,
            "discovered_at": self.discovered_at,
            "run_id": self.run_id,
            "tool_version": self.tool_version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DeviceProfile:
        return cls(
            schema_version=int(data["schema_version"]),
            com=int(data["com"]),
            port_name=str(data["port_name"]),
            baud=int(data["baud"]),
            framing=dict(data.get("framing") or {}),
            usb_hint=dict(data.get("usb_hint") or {}),
            fingerprint=dict(data.get("fingerprint") or {}),
            commands=[DiscoveredCommand.from_dict(c) for c in data.get("commands") or []],
            nudges_tried=[str(n) for n in data.get("nudges_tried") or []],
            baud_tried=[BaudAttempt.from_dict(b) for b in data.get("baud_tried") or []],
            confidence=float(data["confidence"]),
            discovered_at=str(data["discovered_at"]),
            run_id=str(data["run_id"]),
            tool_version=str(data["tool_version"]),
        )


@dataclass(frozen=True)
class DiscoverResult:
    """Structured outcome of one discover run."""

    run_id: str
    status: str
    profile_path: str | None
    log_file: str
    duration_sec: float
    workspace: str
    profile: DeviceProfile | None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "profile_path": self.profile_path,
            "log_file": self.log_file,
            "duration_sec": self.duration_sec,
            "workspace": self.workspace,
            "profile": self.profile.to_dict() if self.profile is not None else None,
        }


@dataclass(frozen=True)
class CallResult:
    """Structured outcome of one call (send/expect) session."""

    run_id: str
    tx: str
    rx: str
    matched: bool | None
    profile_baud: int
    log_file: str
    workspace: str

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "tx": self.tx,
            "rx": self.rx,
            "matched": self.matched,
            "profile_baud": self.profile_baud,
            "log_file": self.log_file,
            "workspace": self.workspace,
        }

