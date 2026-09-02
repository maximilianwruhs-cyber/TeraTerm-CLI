"""Serial port enumeration and default COM selection."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from serial.tools import list_ports as serial_list_ports

from tt_agent_hw import paths
from tt_agent_hw.profile_store import profile_path

_COM_RE = re.compile(r"^COM(\d+)$", re.IGNORECASE)
_BT_RE = re.compile(r"BTHENUM|Bluetooth", re.IGNORECASE)


@dataclass(frozen=True)
class PortInfo:
    name: str
    com: int | None
    description: str
    hardware_id: str
    has_profile: bool


def parse_com_number(name: str) -> int | None:
    """Parse ``COM7`` / ``com12`` style names to an integer port number."""
    match = _COM_RE.match(name.strip())
    if not match:
        return None
    return int(match.group(1))


def _default_enumerator() -> list[Any]:
    return list(serial_list_ports.comports())


def list_ports(
    *,
    runtime_dir: Path | None = None,
    enumerator: Callable[[], Iterable[Any]] | None = None,
) -> list[PortInfo]:
    """List serial ports; mark those with a saved profile under runtime_dir."""
    root = runtime_dir if runtime_dir is not None else paths.runtime_dir()
    profiles = root / "profiles"
    enum = enumerator if enumerator is not None else _default_enumerator
    result: list[PortInfo] = []
    for port in enum():
        name = str(getattr(port, "device", "") or "")
        description = str(getattr(port, "description", "") or "")
        hardware_id = str(getattr(port, "hwid", "") or "")
        com = parse_com_number(name)
        has_profile = False
        if com is not None:
            has_profile = profile_path(root, com).is_file()
        result.append(
            PortInfo(
                name=name,
                com=com,
                description=description,
                hardware_id=hardware_id,
                has_profile=has_profile,
            )
        )
    return result


def _is_bluetooth(port: PortInfo) -> bool:
    blob = f"{port.description}\n{port.hardware_id}"
    return _BT_RE.search(blob) is not None


def resolve_default_com(ports: list[PortInfo]) -> int | None:
    """Return the sole non-Bluetooth COM candidate, else None."""
    candidates = [p.com for p in ports if p.com is not None and not _is_bluetooth(p)]
    if len(candidates) == 1:
        return candidates[0]
    return None
