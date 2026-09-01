"""Heuristic extraction of device commands from help text."""

from __future__ import annotations

import re

from tt_agent_hw.models import DiscoveredCommand

_DASH_SEP_RE = re.compile(r"\s+[-—]\s+")
_COLON_SEP_RE = re.compile(r":\s+")
_AT_RE = re.compile(r"\b(AT\+[A-Za-z0-9_]+)\b")
_BARE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,31}$")
_SLUG_RE = re.compile(r"[^a-zA-Z0-9]+")
_JUNK_RE = re.compile(r"^[\d.\-_/\\]+$")
_PATH_RE = re.compile(r"[/\\]")
_BULLET_RE = re.compile(r"^[\-\*\u2022\u25cf\u00b7]\s+")


def slug_id(send: str) -> str:
    """Slugify a send string into a stable command id base."""
    slug = _SLUG_RE.sub("_", send).lower().strip("_")
    return slug or "cmd"


def _unique_id(base: str, used: set[str]) -> str:
    if base not in used:
        used.add(base)
        return base
    n = 2
    while f"{base}_{n}" in used:
        n += 1
    candidate = f"{base}_{n}"
    used.add(candidate)
    return candidate


def _is_junk_token(token: str) -> bool:
    if not token:
        return True
    if token == "?":
        return False
    if len(token) == 1:
        return True
    if _JUNK_RE.fullmatch(token):
        return True
    if _PATH_RE.search(token):
        return True
    if set(token) <= {"-"}:
        return True
    return False


def _parse_line(line: str) -> list[tuple[str, str]]:
    """Return (send, summary) pairs found on one help line."""
    s = line.strip()
    if not s or set(s) <= {"-", "=", "*"}:
        return []

    # Strip leading list bullets so "- reset - reboot" still parses.
    while True:
        stripped = _BULLET_RE.sub("", s, count=1)
        if stripped == s:
            break
        s = stripped.strip()
        if not s:
            return []

    found: list[tuple[str, str]] = []
    seen_local: set[str] = set()

    def _add(send: str, summary: str) -> None:
        if send in seen_local or _is_junk_token(send):
            return
        if not (_BARE_RE.fullmatch(send) or send.startswith("AT+") or send == "?"):
            return
        seen_local.add(send)
        found.append((send, summary))

    # cmd - desc | cmd — desc (left must be a single token)
    dash_parts = _DASH_SEP_RE.split(s, maxsplit=1)
    if len(dash_parts) == 2:
        left = dash_parts[0].strip()
        right = dash_parts[1].strip()
        if left and len(left.split()) == 1:
            _add(left, right)

    # cmd: desc — left must be exactly one token (skips "Available commands: …")
    colon_parts = _COLON_SEP_RE.split(s, maxsplit=1)
    if len(colon_parts) == 2:
        left = colon_parts[0].strip()
        right = colon_parts[1].strip()
        if left and len(left.split()) == 1:
            # Header lines like "Commands: AT+RST" should not emit "Commands";
            # AT+ tokens on the line are picked up below instead.
            if not _AT_RE.search(s) or left.upper().startswith("AT+"):
                _add(left, right)

    # Always scan for AT+... tokens (no early return after separators).
    for m in _AT_RE.finditer(s):
        _add(m.group(1), "")

    if found:
        return found

    # bare single-token line
    if _BARE_RE.fullmatch(s):
        _add(s, "")

    return found


def extract_commands(
    help_raw: str, *, productive_nudges: list[str]
) -> list[DiscoveredCommand]:
    """Build DiscoveredCommand list: productive nudges first, then parsed help."""
    commands: list[DiscoveredCommand] = []
    seen_sends: set[str] = set()
    used_ids: set[str] = set()

    for nudge in productive_nudges:
        if nudge in seen_sends:
            continue
        seen_sends.add(nudge)
        cmd_id = _unique_id(slug_id(nudge), used_ids)
        commands.append(
            DiscoveredCommand(
                id=cmd_id,
                send=nudge,
                summary=f"nudge: {nudge}",
                source="nudge",
            )
        )

    for line in help_raw.splitlines():
        for send, summary in _parse_line(line):
            if send in seen_sends:
                continue
            seen_sends.add(send)
            cmd_id = _unique_id(slug_id(send), used_ids)
            commands.append(
                DiscoveredCommand(
                    id=cmd_id,
                    send=send,
                    summary=summary,
                    source="parsed_help",
                )
            )

    return commands
