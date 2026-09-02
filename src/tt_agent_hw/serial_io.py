"""Shared serial read/write helpers for discover and call."""

from __future__ import annotations

import time

from tt_agent_hw.serial_transport import SerialTransport


def append_cr(payload: str | bytes) -> bytes:
    """Encode payload and ensure a single trailing CR (no double-CR)."""
    data = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
    if data.endswith(b"\r"):
        return data
    return data + b"\r"


def read_until_quiet(
    transport: SerialTransport,
    *,
    quiet_s: float = 0.25,
    max_s: float = 2.0,
    first_byte_s: float = 0.75,
) -> bytes:
    """Read RX until a quiet gap or overall cap is reached.

    Before any RX arrives, wait up to ``first_byte_s`` (capped by ``max_s``).
    After RX has started, stop once ``quiet_s`` elapses with no further bytes.
    """
    buf = bytearray()
    start = time.monotonic()
    got_data = False
    last_rx = start
    first_budget = min(first_byte_s, max_s)
    while True:
        now = time.monotonic()
        elapsed = now - start
        if elapsed >= max_s:
            break
        remaining = max_s - elapsed
        if not got_data:
            if elapsed >= first_budget:
                break
            slice_s = min(0.05, remaining, first_budget - elapsed)
        else:
            quiet_elapsed = now - last_rx
            if quiet_elapsed >= quiet_s:
                break
            slice_s = min(0.05, remaining, quiet_s - quiet_elapsed)
        chunk = transport.read(4096, timeout=max(0.0, slice_s))
        if chunk:
            buf.extend(chunk)
            got_data = True
            last_rx = time.monotonic()
            continue
        # Fake transports return immediately on empty; avoid a tight spin.
        time.sleep(min(0.01, max(slice_s, 0.001)))
    return bytes(buf)
