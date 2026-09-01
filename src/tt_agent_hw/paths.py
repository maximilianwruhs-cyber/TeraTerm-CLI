"""Resolve package data, repo assets, and environment defaults."""

from __future__ import annotations

import os
from pathlib import Path

# Defaults from design spec.
DEFAULT_RUNTIME_DIR = Path(r"C:\agent_runtime")
DEFAULT_TT_BIN_DIR = Path(r"C:\Program Files (x86)\teraterm")

ENV_RUNTIME = "TT_AGENT_RUNTIME_DIR"
ENV_TT_BIN = "TT_AGENT_TT_BIN_DIR"
ENV_HW = "TT_AGENT_HW"


def package_dir() -> Path:
    return Path(__file__).resolve().parent


def repo_root() -> Path | None:
    """Best-effort repo root when running from a source checkout."""
    here = package_dir()
    # src/tt_agent_hw -> repo
    candidate = here.parent.parent
    if (candidate / "pyproject.toml").is_file():
        return candidate
    return None


def template_path() -> Path:
    """Jinja2 TTL template: package data first, then repo templates/."""
    bundled = package_dir() / "templates" / "task_template.ttl.j2"
    if bundled.is_file():
        return bundled
    root = repo_root()
    if root:
        alt = root / "templates" / "task_template.ttl.j2"
        if alt.is_file():
            return alt
    raise FileNotFoundError("task_template.ttl.j2 not found in package or repo")


def base_ini_path() -> Path | None:
    bundled = package_dir() / "config" / "base_teraterm.ini"
    if bundled.is_file():
        return bundled
    root = repo_root()
    if root:
        alt = root / "config" / "base_teraterm.ini"
        if alt.is_file():
            return alt
    return None


def runtime_dir() -> Path:
    raw = os.environ.get(ENV_RUNTIME)
    return Path(raw) if raw else DEFAULT_RUNTIME_DIR


def tt_bin_dir() -> Path:
    raw = os.environ.get(ENV_TT_BIN)
    return Path(raw) if raw else DEFAULT_TT_BIN_DIR


def ttl_escape_path(path: Path | str) -> str:
    """Escape Windows paths for embedding in TTL string literals."""
    return str(path).replace("\\", "\\\\")
