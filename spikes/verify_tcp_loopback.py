"""Spike: verify REAL Tera Term connect/wait/sendln over TCP (loopback).

Proves the actual macro engine can open a network connection and that the
real `connect` / `wait` / `sendln` primitives work end-to-end against a live
socket. Uses 127.0.0.1 by default (no external device or serial adapter
needed); point --host/--port at a real box on the Ethernet wire to exercise
the NIC path too.

Double-sided assertion:
  * server side must observe the macro's 'hello' line, AND
  * macro side must reach STATUS=SUCCESS_PROVISIONED after 'OK READY'.

Protocol driven by this server:
  server -> 'LOGIN>\\r\\n'
  (macro sends 'hello')
  server -> 'OK READY\\r\\n'

Run (once Tera Term is installed):
    .venv\\Scripts\\python.exe spikes\\verify_tcp_loopback.py
    # optionally: --tt-bin-dir "C:\\Program Files (x86)\\teraterm"

Exit 0 => real Tera Term completed the TCP handshake both ways.
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tt_agent_hw.paths import tt_bin_dir
from tt_agent_hw.status import is_success, is_terminal, read_status_file

# Telnet: strip IAC (0xFF) 3-byte command sequences so we can find 'hello'.
IAC = 0xFF


def strip_telnet(buf: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(buf):
        if buf[i] == IAC and i + 2 < len(buf):
            i += 3  # skip IAC + command + option
            continue
        out.append(buf[i])
        i += 1
    return bytes(out)


class ProbeServer:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.saw_hello = False
        self.error: str | None = None
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((host, port))
        self.port = self._sock.getsockname()[1]
        self._sock.listen(1)
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _serve(self) -> None:
        try:
            self._sock.settimeout(25)
            conn, _ = self._sock.accept()
            with conn:
                conn.sendall(b"LOGIN>\r\n")
                conn.settimeout(15)
                acc = bytearray()
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    try:
                        chunk = conn.recv(1024)
                    except TimeoutError:
                        break
                    if not chunk:
                        break
                    acc += chunk
                    if b"hello" in strip_telnet(bytes(acc)):
                        self.saw_hello = True
                        break
                conn.sendall(b"OK READY\r\n")
                time.sleep(0.5)  # let macro read before close
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
        finally:
            try:
                self._sock.close()
            except OSError:
                pass


PROBE_TTL = """; TCP loopback probe for run {run_id}
StateFile = '{state_file}'

CurrentState = 'STATUS=INITIALIZING'
fileopen fHandle StateFile 0
filewrite fHandle CurrentState
fileclose fHandle

connect '{host}:{port} /nossh /T=1'
timeout = 15
wait 'LOGIN>'
if result == 0 then
    CurrentState = 'STATUS=FAILED_CONNECTION_REFUSED'
    fileopen fHandle StateFile 0
    filewrite fHandle CurrentState
    fileclose fHandle
    disconnect
    end
endif

sendln 'hello'
wait 'OK READY'
if result == 0 then
    CurrentState = 'STATUS=FAILED_BOOT_PROMPT_TIMEOUT'
    fileopen fHandle StateFile 0
    filewrite fHandle CurrentState
    fileclose fHandle
    disconnect
    end
endif

CurrentState = 'STATUS=SUCCESS_PROVISIONED'
fileopen fHandle StateFile 0
filewrite fHandle CurrentState
fileclose fHandle
disconnect
end
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tt-bin-dir", type=Path, default=None)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0, help="0 = ephemeral")
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args()

    bin_dir = Path(args.tt_bin_dir) if args.tt_bin_dir else tt_bin_dir()
    macro_exe = bin_dir / "ttpmacro.exe"
    if not macro_exe.is_file():
        print(f"[FAIL] ttpmacro.exe not found: {macro_exe}")
        print("       Install Tera Term or pass --tt-bin-dir.")
        return 2

    server = ProbeServer(args.host, args.port)
    server.start()
    print(f"[..] probe server listening on {args.host}:{server.port}")

    work = Path(tempfile.mkdtemp(prefix="tt_tcp_probe_"))
    state_file = work / "execution.state"
    macro_file = work / "tcp_probe.ttl"
    macro_file.write_text(
        PROBE_TTL.format(
            run_id=work.name,
            state_file=str(state_file).replace("\\", "\\\\"),
            host=args.host,
            port=server.port,
        ),
        encoding="ascii",
    )
    print(f"[..] macro: {macro_file}")

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

    print(f"[..] server saw 'hello': {server.saw_hello}")
    if server.error:
        print(f"[..] server error: {server.error}")
    print(f"[..] final status: {final!r}")

    if is_success(final) and server.saw_hello:
        print("[OK] REAL Tera Term TCP connect/wait/sendln verified end-to-end")
        return 0
    print("[FAIL] TCP loopback handshake not fully verified")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
