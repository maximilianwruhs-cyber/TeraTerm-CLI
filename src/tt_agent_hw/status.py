"""STATUS=* file handshake between TTL macros and the orchestrator."""

from __future__ import annotations

from pathlib import Path

STATUS_PREFIX = "STATUS="

# Known tokens from the framework spec (non-exhaustive; parser is prefix-based).
KNOWN_PROGRESS = frozenset({"STATUS=INITIALIZING"})
KNOWN_SUCCESS = frozenset(
    {
        "STATUS=SUCCESS_PROVISIONED",
        "STATUS=SUCCESS_DISCOVERED",
    }
)
KNOWN_FAILURE = frozenset(
    {
        "STATUS=FAILED_CONNECTION_REFUSED",
        "STATUS=FAILED_BOOT_PROMPT_TIMEOUT",
        "STATUS=FAILED_FLASH_ERASE",
        "STATUS=FAILED_YMODEM_READY_TIMEOUT",
        "STATUS=FAILED_YMODEM_TRANSFER_ABORTED",
        "STATUS=FAILED_TARGET_CRASH",
        "STATUS=FAILED_BOOT_TIMEOUT",
        "STATUS=FAILED_PROBE_SILENT",
        "STATUS=FAILED_NO_PORT",
    }
)
ORCHESTRATOR_TIMEOUT = "STATUS=TIMEOUT_ORCHESTRATOR"
ORCHESTRATOR_NO_STATUS = "STATUS=FAILED_NO_STATUS"
ORCHESTRATOR_PREFLIGHT = "STATUS=FAILED_PREFLIGHT"

SUCCESS_DISCOVERED = "STATUS=SUCCESS_DISCOVERED"
FAILED_PROBE_SILENT = "STATUS=FAILED_PROBE_SILENT"
FAILED_NO_PORT = "STATUS=FAILED_NO_PORT"


def normalize_status_line(raw: str) -> str | None:
    """Return canonical STATUS=... line or None if not a status payload."""
    line = raw.strip()
    if not line:
        return None
    # Accept first line only if multi-line garbage appears.
    line = line.splitlines()[0].strip()
    if not line.startswith(STATUS_PREFIX):
        if line.startswith("STATUS"):
            # Tolerate missing '=' after strip artifacts.
            return None
        return None
    return line


def is_terminal(status: str | None) -> bool:
    """True when orchestrator should stop polling."""
    if not status:
        return False
    if not status.startswith(STATUS_PREFIX):
        return False
    body = status[len(STATUS_PREFIX) :]
    return "SUCCESS" in body or "FAILED" in body or "TIMEOUT" in body


def is_success(status: str | None) -> bool:
    if not status:
        return False
    return status.startswith(STATUS_PREFIX) and "SUCCESS" in status


def read_status_file(path: Path) -> str | None:
    """Read status file; return None if missing or locked."""
    try:
        if not path.exists():
            return None
        content = path.read_text(encoding="ascii", errors="replace")
    except OSError:
        return None
    except PermissionError:
        return None
    return normalize_status_line(content)


def write_status_file(path: Path, status: str) -> None:
    """Write a status line (used by fake macro and orchestrator synthesis)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = status if status.startswith(STATUS_PREFIX) else f"{STATUS_PREFIX}{status}"
    path.write_text(text.strip() + "\n", encoding="ascii")
