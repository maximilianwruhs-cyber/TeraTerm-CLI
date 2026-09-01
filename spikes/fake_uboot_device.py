"""Fake U-Boot serial device for real end-to-end CLI provisioning tests.

Pairs with a virtual COM port (e.g. com0com) so `tt-agent-hw provision`
can drive the REAL ttpmacro.exe/ttermpro.exe against a scripted bootloader
without physical hardware. Emulates just enough U-Boot to satisfy the
default TTL template's happy path:

    <boot prompt>           e.g. "U-Boot>"
    <erase command> -> <erase ack>
    <transfer trigger> -> emits 'C' (YMODEM ready)
    <YMODEM receive>  -> ACKs blocks minimally
    <boot command>    -> emits <boot success string>

Requires pyserial:  pip install pyserial

Run (bind to the device END of a com0com pair, e.g. COM6 if CLI uses COM5):
    .venv\\Scripts\\python.exe spikes\\fake_uboot_device.py --port COM6

Then in another shell:
    tt-agent-hw provision --com 5 --baud 115200 --binary <file> \\
        --boot-prompt "U-Boot>" --erase-command "sf erase 0 0x1000" \\
        --erase-ack "Erased: OK" --transfer-trigger "loady" \\
        --boot-command "bootm" --boot-success-regex "System Ready" \\
        --boot-timeout 30

This is a SIMPLIFIED YMODEM sink: it accepts and ACKs frames so the
transfer completes, but does not persist the image. Enough to prove the
CLI + real Tera Term + serial transport path end-to-end.
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    import serial  # type: ignore
except ImportError:
    print("[FAIL] pyserial not installed. Run: pip install pyserial")
    raise SystemExit(2) from None

# YMODEM control bytes
SOH = 0x01
STX = 0x02
EOT = 0x04
ACK = 0x06
NAK = 0x15
CAN = 0x18
C = 0x43  # 'C'


def readline(ser: serial.Serial, timeout: float = 30.0) -> str:
    """Read until CR or LF; return decoded stripped line."""
    buf = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        b = ser.read(1)
        if not b:
            continue
        if b in (b"\r", b"\n"):
            if buf:
                return buf.decode("ascii", "replace").strip()
            continue
        buf += b
    return buf.decode("ascii", "replace").strip()


def ymodem_sink(ser: serial.Serial, timeout: float = 60.0) -> bool:
    """Minimal YMODEM receiver: send C, ACK every frame, ACK EOT, finish."""
    ser.write(bytes([C]))  # signal ready
    deadline = time.monotonic() + timeout
    got_data = False
    while time.monotonic() < deadline:
        h = ser.read(1)
        if not h:
            continue
        if h[0] in (SOH, STX):
            size = 128 if h[0] == SOH else 1024
            # seq + ~seq + payload + 2 CRC bytes
            _ = ser.read(2 + size + 2)
            ser.write(bytes([ACK]))
            got_data = True
        elif h[0] == EOT:
            ser.write(bytes([NAK]))  # first EOT -> NAK per spec
            h2 = ser.read(1)
            if h2 and h2[0] == EOT:
                ser.write(bytes([ACK]))
            ser.write(bytes([C]))  # ready for (empty) next file / batch end
            # batch terminator: a final null block 0
            h3 = ser.read(1)
            if h3 and h3[0] in (SOH, STX):
                size = 128 if h3[0] == SOH else 1024
                _ = ser.read(2 + size + 2)
                ser.write(bytes([ACK]))
            return got_data
        elif h[0] == CAN:
            return False
    return got_data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="device-side virtual COM port, e.g. COM6")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--prompt", default="U-Boot>")
    ap.add_argument("--erase-ack", default="Erased: OK")
    ap.add_argument("--boot-success", default="System Ready")
    ap.add_argument("--idle-timeout", type=float, default=120.0)
    args = ap.parse_args()

    ser = serial.Serial(args.port, args.baud, timeout=1)
    print(f"[..] fake U-Boot on {args.port} @ {args.baud}; prompt={args.prompt!r}")

    # Emit prompt repeatedly until the host breaks in.
    ser.write(f"\r\n{args.prompt} ".encode("ascii"))

    end = time.monotonic() + args.idle_timeout
    while time.monotonic() < end:
        line = readline(ser, timeout=5)
        if not line:
            ser.write(f"\r\n{args.prompt} ".encode("ascii"))
            continue
        print(f"[rx] {line!r}")
        low = line.lower()

        if "erase" in low:
            ser.write(f"\r\n{args.erase_ack}\r\n{args.prompt} ".encode("ascii"))
        elif "loady" in low or "loadb" in low or "ymodem" in low:
            ser.write(b"\r\n## Ready for binary (ymodem) download ...\r\n")
            ok = ymodem_sink(ser)
            ser.write(f"\r\n## downloaded {'OK' if ok else 'FAIL'}\r\n{args.prompt} ".encode())
        elif "boot" in low:
            ser.write(f"\r\n{args.boot_success}\r\n".encode("ascii"))
            print("[ok] emitted boot-success string; provisioning should now SUCCEED")
            time.sleep(1)
            return 0
        else:
            ser.write(f"\r\nunknown command\r\n{args.prompt} ".encode("ascii"))

    print("[..] idle timeout reached")
    return 0


if __name__ == "__main__":
    sys.exit(main())
