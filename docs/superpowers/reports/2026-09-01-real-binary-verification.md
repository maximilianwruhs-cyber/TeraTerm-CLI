# tt-agent-hw — Real-Binary Verification Report

**Date:** 2026-09-01
**Tera Term:** 5.6.2 x64 portable at `%LOCALAPPDATA%\Programs\TeraTerm\5.6.2` (`current` symlink)
**Interpreter:** Python 3.12.10 venv
**Scope:** what is verified against the **real** `ttpmacro.exe`/`ttermpro.exe` (not the mock), and what remains blocked.

---

## Verified on real binaries — PASS

| # | Check | Command | Observed result |
|---|-------|---------|-----------------|
| 1 | `doctor` finds real binaries | `tt-agent-hw doctor` (TT_AGENT_TT_BIN_DIR set) | 4/4 `[OK]`, incl. real `ttpmacro.exe`/`ttermpro.exe`, exit 0 |
| 2 | Real engine + STATUS handshake | `spikes\verify_real_engine.py` | `final status: 'STATUS=SUCCESS_PROVISIONED'` → `[OK]` |
| 3 | Real `connect`/`wait`/`sendln` over TCP | `spikes\verify_tcp_loopback.py` | `server saw 'hello': True`, `STATUS=SUCCESS_PROVISIONED` → `[OK]` |
| 4 | Full CLI `provision` pipeline | `spikes\depth1_cli_provision.py` | real Tera Term launched, attempted COM4 (~5.5s), `STATUS=FAILED_CONNECTION_REFUSED`, CLI exit 1 (expected — no device) |

**What #1–#4 collectively prove on real binaries:**
argument parsing → Jinja2 TTL render → spawn real `ttpmacro.exe` → real `ttermpro.exe`
executes the macro → file-based `STATUS=*` handshake → orchestrator poll →
status parse → CLI exit-code mapping — plus the real `connect`/`wait`/`sendln`
primitives over a live socket. The entire orchestration + macro-engine +
network-transport + CLI surface is verified against the actual product.

Check #4's `FAILED_CONNECTION_REFUSED` is the **correct** result: with no device
on COM4, real Tera Term's connect fails and the macro's `if result != 2` branch
fires exactly as designed. The 5.5s duration confirms a genuine connection
attempt, not an instant preflight bail.

---

## Blocked — could NOT verify on real binaries

| Gap | Why blocked |
|-----|-------------|
| Serial `connect /C= /BAUD=` **succeeding** | No RS232/USB-UART adapter available |
| Real `ymodemsend` transfer | Same — needs a serial peer, or a virtual COM pair |
| com0com virtual serial pair | Download intercepted by corporate **Zscaler** proxy (fetched manually), but the **kernel-driver install needs admin** — every elevation attempt hung/failed, consistent with corporate policy blocking it (same wall Tera Term's system installer hit, "exited 4") |
| Named-pipe YMODEM workaround (`spikes\verify_named_pipe_ymodem.py`) | Tera Term **does** open the pipe, but the byte dialogue hangs — almost certainly telnet IAC negotiation corrupting the stream (and it would corrupt binary YMODEM frames). Marked EXPERIMENTAL / NOT PASSING; needs IAC stripping + binary-safe connect before it can pass |

These gaps are **environmental** (locked-down corporate machine: no admin, no
adapter, proxy interception), not defects in tt-agent-hw. The serial success
path remains covered by the mock suite (`tests/`) and the rendered-TTL content
tests.

---

## How to close the remaining gap later

- **Cheapest:** on a machine with admin, install com0com, create a `COM5<->COM6`
  pair, run `spikes\fake_uboot_device.py --port COM6`, then
  `tt-agent-hw provision --com 5 ...` → expect real `STATUS=SUCCESS_PROVISIONED`.
- **Most faithful:** a real board with a YMODEM bootloader on a USB-UART adapter.
- **No-admin (needs dev work):** finish `verify_named_pipe_ymodem.py` — add
  telnet-IAC stripping and confirm Tera Term's pipe connect mode is 8-bit clean.

---

## Reproduce the passing checks

```bat
set TT=C:\Users\z005a5ff\AppData\Local\Programs\TeraTerm\current
set TT_AGENT_TT_BIN_DIR=%TT%

.venv\Scripts\tt-agent-hw.exe doctor
.venv\Scripts\python.exe spikes\verify_real_engine.py   --tt-bin-dir %TT%
.venv\Scripts\python.exe spikes\verify_tcp_loopback.py  --tt-bin-dir %TT%
.venv\Scripts\python.exe spikes\depth1_cli_provision.py --tt-bin-dir %TT%
```
