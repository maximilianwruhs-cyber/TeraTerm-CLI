# spikes/ — real Tera Term verification (no serial adapter required)

These probes drive the **real** `ttpmacro.exe`/`ttermpro.exe` binaries to
close the gap the mock tests cannot: they only run when Tera Term is
actually installed. They deliberately avoid the serial/YMODEM/bootloader
path (no RS232 adapter available), and instead verify everything up to and
including a live network connection.

| Spike | Proves | Needs |
|-------|--------|-------|
| `verify_real_engine.py` | Real macro engine runs a rendered TTL and the `STATUS=*` file handshake round-trips through the actual binary | Tera Term only |
| `verify_tcp_loopback.py` | Real `connect` / `wait` / `sendln` work end-to-end over TCP (127.0.0.1 by default) | Tera Term only |

## Run

```bat
.venv\Scripts\python.exe spikes\verify_real_engine.py
.venv\Scripts\python.exe spikes\verify_tcp_loopback.py
:: point the TCP probe at a real box on the wire instead of loopback:
.venv\Scripts\python.exe spikes\verify_tcp_loopback.py --host 192.168.1.50 --port 23
```

Each exits `0` on success, `2` if Tera Term isn't found, `1` on a real failure.

## What these do NOT prove

The serial-transport commands (`connect /C= /BAUD=`, `ymodemsend`,
U-Boot `sf erase` / `loady` / `bootm`) remain unverified until an RS232/USB-UART
adapter and a target board are available. That is the only remaining gap once
these two spikes pass.
