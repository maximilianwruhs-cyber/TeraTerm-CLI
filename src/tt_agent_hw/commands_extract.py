"""Heuristic extraction of device commands from help text."""

from __future__ import annotations

import re

from tt_agent_hw.models import DiscoveredCommand

_SEP_RE = re.compile(r"\s+[-—]\s+|:\s+")
_AT_RE = re.compile(r"\b(AT\+[A-Za-z0-9_]+)\b")
_BARE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,31}$")
_SLUG_RE = re.compile(r"[^a-zA-Z0-9]+")
_JUNK_RE = re.compile(r"^[\d.\-_/\\]+$")
_PATH_RE = re.compile(r"[/\\]")


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

    found: list[tuple[str, str]] = []

    # cmd - desc | cmd — desc | cmd: desc
    parts = _SEP_RE.split(s, maxsplit=1)
    if len(parts) == 2:
        left = parts[0].strip()
        right = parts[1].strip()
        # take first token of left as command
        token = left.split()[0] if left.split() else ""
        if token and not _is_junk_token(token):
            if _BARE_RE.fullmatch(token) or token.startswith("AT+") or token == "?":
                found.append((token, right))
                return found

    # AT+... anywhere on the line
    for m in _AT_RE.finditer(s):
        tok = m.group(1)
        if not _is_junk_token(tok):
            found.append((tok, ""))

    if found:
        return found

    # bare single-token line
    if _BARE_RE.fullmatch(s) and not _is_junk_token(s):
        found.append((s, ""))

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
