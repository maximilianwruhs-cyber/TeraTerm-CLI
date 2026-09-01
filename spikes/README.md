# spikes/ — real Tera Term verification (no serial adapter required)

These probes drive the **real** `ttpmacro.exe`/`ttermpro.exe` binaries to
close the gap the mock tests cannot: they only run when Tera Term is
actually installed. They avoid the serial/YMODEM/bootloader path (no RS232
adapter) except Depth 3, which substitutes a virtual serial pair.

| Spike | Proves | Needs | Status (2026-09-01) |
|-------|--------|-------|---------------------|
| `verify_real_engine.py` | Real macro engine runs a rendered TTL and the `STATUS=*` handshake round-trips through the actual binary | Tera Term only | ✅ PASS |
| `verify_tcp_loopback.py` | Real `connect` / `wait` / `sendln` end-to-end over TCP (127.0.0.1 default) | Tera Term only | ✅ PASS |
| `depth1_cli_provision.py` | Full real CLI pipeline; expected `FAILED_CONNECTION_REFUSED` with no device | Tera Term only | ✅ PASS (exit 1 expected) |
| `fake_uboot_device.py` | Enables a REAL `tt-agent-hw provision` **success** over a virtual serial port | Tera Term + com0com + pyserial | ⛔ blocked (no admin) |
| `verify_named_pipe_ymodem.py` | No-admin real `ymodemsend` over a named pipe | Tera Term only | ⚠️ EXPERIMENTAL — hangs (telnet IAC), not passing |

Results detail: `../docs/superpowers/reports/2026-09-01-real-binary-verification.md`.

## Testing the CLI itself against real Tera Term

Three depths, increasing fidelity:

### Depth 1 — real CLI pipeline, no device (Tera Term only)

```bat
tt-agent-hw doctor
:: expect exit 0 once binaries are found

tt-agent-hw provision --com 4 --baud 115200 --binary <any-file> ^
  --boot-prompt "U-Boot>" --erase-command "sf erase 0 0x1000" ^
  --erase-ack "Erased: OK" --transfer-trigger "loady" ^
  --boot-command "bootm" --boot-success-regex "System Ready" --boot-timeout 15
:: real ttpmacro.exe launches, tries COM4, fails with no device:
:: STATUS=FAILED_CONNECTION_REFUSED, CLI exit 1 (expected).
:: Still fully exercises arg-parse -> render -> spawn real engine ->
:: poll -> status parse -> exit-code mapping.
```

### Depth 2 — real primitives (Tera Term only)

```bat
.venv\Scripts\python.exe spikes\verify_real_engine.py
.venv\Scripts\python.exe spikes\verify_tcp_loopback.py
:: point the TCP probe at a real box on the Ethernet wire instead of loopback:
.venv\Scripts\python.exe spikes\verify_tcp_loopback.py --host 192.168.1.50 --port 23
```

Each exits `0` on success, `2` if Tera Term isn't found, `1` on a real failure.

### Depth 3 — real CLI SUCCESS over a virtual serial pair (no board)

1. Install **com0com** (creates a null-modem pair, e.g. `COM5`<->`COM6`). Needs admin.
2. `pip install pyserial` into the venv.
3. Start the fake bootloader on the device end:
   ```bat
   .venv\Scripts\python.exe spikes\fake_uboot_device.py --port COM6
   ```
4. Provision against the host end:
   ```bat
   tt-agent-hw provision --com 5 --baud 115200 --binary <file> ^
     --boot-prompt "U-Boot>" --erase-command "sf erase 0 0x1000" ^
     --erase-ack "Erased: OK" --transfer-trigger "loady" ^
     --boot-command "bootm" --boot-success-regex "System Ready" --boot-timeout 30
   ```
   Expect `STATUS=SUCCESS_PROVISIONED`, CLI exit 0 — a real serial provision.

## What stays unproven without Depth 3 or real hardware

The serial-transport commands (`connect /C= /BAUD=`, `ymodemsend`,
U-Boot `sf erase` / `loady` / `bootm`) remain unverified until either a
com0com virtual pair (Depth 3) or a real RS232/USB-UART adapter + board is
available.
