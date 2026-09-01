"""EXPERIMENTAL (known hang): real YMODEM over a named pipe. NOT PASSING.

Intended as a no-admin substitute for com0com to verify real `ymodemsend`.
Tera Term 5.6.2 DOES open the pipe, but the byte dialogue hangs -- almost
certainly telnet IAC negotiation corrupting the stream (and it would corrupt
binary YMODEM frames too). Left in the tree as a documented starting point;
needs telnet-IAC stripping + a binary-safe connect mode before it can pass.

Do not treat a run of this file as verification. See
docs/superpowers/reports/2026-09-01-real-binary-verification.md for the
status of what IS verified on real binaries.

com0com (virtual serial) needs a kernel driver + admin, which is blocked on
this machine. Windows named pipes need neither, and Tera Term 5.x can
`connect '\\\\.\\pipe\\<name>'`. This drives the REAL macro engine through the
full choreography -- prompt, erase-ack, `loady`, real `ymodemsend`, boot --
against a Python fake-U-Boot that implements a YMODEM *receiver* over the
pipe, then checks the transferred bytes match the source AND the macro
reached STATUS=SUCCESS_PROVISIONED.
"""

from __future__ import annotations

import argparse
import ctypes
import subprocess
import sys
import tempfile
import threading
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tt_agent_hw.paths import tt_bin_dir
from tt_agent_hw.status import is_success, is_terminal, read_status_file

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_BYTE = 0x0
PIPE_WAIT = 0x0
INVALID_HANDLE = ctypes.c_void_p(-1).value
SOH, STX, EOT, ACK, NAK, CAN, C = 0x01, 0x02, 0x04, 0x06, 0x15, 0x18, 0x43


class Pipe:
    def __init__(self, name: str) -> None:
        self.h = k32.CreateNamedPipeW(
            name, PIPE_ACCESS_DUPLEX, PIPE_TYPE_BYTE | PIPE_WAIT, 1, 65536, 65536, 0, None
        )
        if self.h == INVALID_HANDLE or self.h is None:
            raise ctypes.WinError(ctypes.get_last_error())

    def connect(self) -> None:
        ok = k32.ConnectNamedPipe(self.h, None)
        if not ok:
            err = ctypes.get_last_error()
            if err not in (0, 535):  # 535 = ERROR_PIPE_CONNECTED
                raise ctypes.WinError(err)

    def read(self, n: int) -> bytes:
        buf = (ctypes.c_char * n)()
        got = wintypes.DWORD(0)
        if not k32.ReadFile(self.h, buf, n, ctypes.byref(got), None):
            return b""
        return bytes(buf[: got.value])

    def read_exact(self, n: int, deadline: float) -> bytes:
        out = bytearray()
        while len(out) < n and time.monotonic() < deadline:
            c = self.read(n - len(out))
            if c:
                out += c
        return bytes(out)

    def write(self, data: bytes) -> None:
        wrote = wintypes.DWORD(0)
        k32.WriteFile(self.h, data, len(data), ctypes.byref(wrote), None)

    def close(self) -> None:
        try:
            k32.DisconnectNamedPipe(self.h)
            k32.CloseHandle(self.h)
        except OSError:
            pass


class Device:
    def __init__(self, pipe: Pipe) -> None:
        self.p = pipe
        self.prompt = "U-Boot>"
        self.erase_ack = "Erased: OK"
        self.boot_success = "System Ready"
        self.received = bytearray()
        self.transfer_ok = False
        self.error: str | None = None

    def _readline(self, timeout: float) -> str:
        buf = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            b = self.p.read(1)
            if not b:
                continue
            if b in (b"\r", b"\n"):
                if buf:
                    return buf.decode("ascii", "replace").strip()
                continue
            buf += b
        return buf.decode("ascii", "replace").strip()

    def _ymodem_recv(self, timeout: float = 60.0) -> None:
        self.p.write(bytes([C]))
        deadline = time.monotonic() + timeout
        first = True
        while time.monotonic() < deadline:
            h = self.p.read(1)
            if not h:
                continue
            if h[0] in (SOH, STX):
                size = 128 if h[0] == SOH else 1024
                frame = self.p.read_exact(2 + size + 2, deadline)
                if len(frame) < 2 + size + 2:
                    break
                if first:
                    self.p.write(bytes([ACK]))
                    self.p.write(bytes([C]))
                    first = False
                else:
                    self.received += frame[2 : 2 + size]
                    self.p.write(bytes([ACK]))
            elif h[0] == EOT:
                self.p.write(bytes([NAK]))
                h2 = self.p.read(1)
                if h2 and h2[0] == EOT:
                    self.p.write(bytes([ACK]))
                self.p.write(bytes([C]))
                h3 = self.p.read(1)
                if h3 and h3[0] in (SOH, STX):
                    size = 128 if h3[0] == SOH else 1024
                    self.p.read_exact(2 + size + 2, deadline)
                    self.p.write(bytes([ACK]))
                self.transfer_ok = True
                return
            elif h[0] == CAN:
                return

    def run(self) -> None:
        try:
            self.p.connect()
            self.p.write(f"\r\n{self.prompt} ".encode("ascii"))
            end = time.monotonic() + 90
            while time.monotonic() < end:
                line = self._readline(8)
                if not line:
                    self.p.write(f"\r\n{self.prompt} ".encode("ascii"))
                    continue
                low = line.lower()
                if "erase" in low:
                    self.p.write(f"\r\n{self.erase_ack}\r\n{self.prompt} ".encode("ascii"))
                elif "loady" in low or "loadb" in low:
                    self.p.write(b"\r\n## Ready for binary (ymodem) ...\r\n")
                    self._ymodem_recv()
                    tag = "OK" if self.transfer_ok else "FAIL"
                    self.p.write(f"\r\n## done {tag}\r\n{self.prompt} ".encode("ascii"))
                elif "boot" in low:
                    self.p.write(f"\r\n{self.boot_success}\r\n".encode("ascii"))
                    time.sleep(1)
                    return
                else:
                    self.p.write(f"\r\nunknown\r\n{self.prompt} ".encode("ascii"))
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)


PROBE_TTL = """; named-pipe YMODEM probe {run_id}
StateFile = '{state_file}'
CurrentState = 'STATUS=INITIALIZING'
fileopen fHandle StateFile 0
filewrite fHandle CurrentState
fileclose fHandle

connect '{pipe}'
timeout = 20
wait 'U-Boot>'
if result == 0 then
    CurrentState = 'STATUS=FAILED_CONNECTION_REFUSED'
    fileopen fHandle StateFile 0
    filewrite fHandle CurrentState
    fileclose fHandle
    disconnect
    end
endif

sendln 'sf erase 0 0x10000'
wait 'Erased: OK' 'ERROR'
if result != 1 then
    CurrentState = 'STATUS=FAILED_FLASH_ERASE'
    fileopen fHandle StateFile 0
    filewrite fHandle CurrentState
    fileclose fHandle
    disconnect
    end
endif

sendln 'loady 0x80000000'
wait 'C'
if result == 0 then
    CurrentState = 'STATUS=FAILED_YMODEM_READY_TIMEOUT'
    fileopen fHandle StateFile 0
    filewrite fHandle CurrentState
    fileclose fHandle
    disconnect
    end
endif

ymodemsend '{binary}'
if result == 0 then
    CurrentState = 'STATUS=FAILED_YMODEM_TRANSFER_ABORTED'
    fileopen fHandle StateFile 0
    filewrite fHandle CurrentState
    fileclose fHandle
    disconnect
    end
endif

sendln 'bootm 0x80000000'
timeout = 20
waitregex 'System Ready' 'Kernel panic' 'Hard Fault'
if result == 1 then
    CurrentState = 'STATUS=SUCCESS_PROVISIONED'
else
    CurrentState = 'STATUS=FAILED_BOOT_TIMEOUT'
endif
fileopen fHandle StateFile 0
filewrite fHandle CurrentState
fileclose fHandle
disconnect
end
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tt-bin-dir", type=Path, default=None)
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--size", type=int, default=4096)
    args = ap.parse_args()

    bin_dir = Path(args.tt_bin_dir) if args.tt_bin_dir else tt_bin_dir()
    macro_exe = bin_dir / "ttpmacro.exe"
    if not macro_exe.is_file():
        print(f"[FAIL] ttpmacro.exe not found: {macro_exe}")
        return 2

    pipe_name = r"\\.\pipe\ttagent_ymodem"
    work = Path(tempfile.mkdtemp(prefix="tt_pipe_ymodem_"))
    fw = work / "firmware.bin"
    payload = bytes((i * 7 + 13) & 0xFF for i in range(args.size))
    fw.write_bytes(payload)
    state_file = work / "execution.state"
    macro_file = work / "probe.ttl"
    macro_file.write_text(
        PROBE_TTL.format(
            run_id=work.name,
            state_file=str(state_file).replace("\\", "\\\\"),
            pipe=pipe_name.replace("\\", "\\\\"),
            binary=str(fw).replace("\\", "\\\\"),
        ),
        encoding="ascii",
    )

    pipe = Pipe(pipe_name)
    dev = Device(pipe)
    t = threading.Thread(target=dev.run, daemon=True)
    t.start()
    print(f"[..] pipe server: {pipe_name}")
    print(f"[..] firmware: {len(payload)} bytes")

    proc = subprocess.Popen(
        [str(macro_exe), "/V", str(macro_file)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(bin_dir),
    )
    start = time.monotonic()
    final = None
    while (time.monotonic() - start) < args.timeout:
        st = read_status_file(state_file)
        if is_terminal(st):
            final = st
            break
        if proc.poll() is not None:
            final = read_status_file(state_file)
            break
        time.sleep(0.25)
    if proc.poll() is None:
        proc.kill()
    pipe.close()
    t.join(timeout=3)

    got = bytes(dev.received[: len(payload)])
    match = got == payload
    print(f"[..] transfer_ok={dev.transfer_ok} received={len(dev.received)}B match={match}")
    if dev.error:
        print(f"[..] device error: {dev.error}")
    print(f"[..] final status: {final!r}")
    if is_success(final) and dev.transfer_ok and match:
        print("[OK] REAL ttermpro YMODEM transfer verified over named pipe")
        return 0
    print("[FAIL] named-pipe YMODEM path not fully verified")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
