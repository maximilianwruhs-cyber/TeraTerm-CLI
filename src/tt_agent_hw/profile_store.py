"""Per-COM device profile read/write with one-slot backup."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from tt_agent_hw.models import DeviceProfile


def profiles_dir(runtime_dir: Path) -> Path:
    return Path(runtime_dir) / "profiles"


def profile_path(runtime_dir: Path, com: int) -> Path:
    return profiles_dir(runtime_dir) / f"COM{com}.json"


def save_profile(runtime_dir: Path, profile: DeviceProfile) -> Path:
    dest = profile_path(runtime_dir, profile.com)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        backup = dest.with_name(f"COM{profile.com}.prev.json")
        shutil.copy2(dest, backup)
    dest.write_text(
        json.dumps(profile.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    return dest


def load_profile(runtime_dir: Path, com: int) -> DeviceProfile:
    path = profile_path(runtime_dir, com)
    data = json.loads(path.read_text(encoding="utf-8"))
    return DeviceProfile.from_dict(data)
