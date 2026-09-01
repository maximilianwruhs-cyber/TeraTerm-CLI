"""Spike: verify the REAL ttpmacro.exe engine + STATUS-file handshake.

Transport-free. Proves that the actual Tera Term macro engine (not the
fake) executes a rendered TTL macro and that our STATUS=* file contract
(fileopen/filelock/filewrite) round-trips through the real binary and is
parsed correctly by tt_agent_hw.status.

Does NOT open any connection, so it needs no serial adapter and no network.

Run (once Tera Term is installed):
    .venv\\Scripts\\python.exe spikes\\verify_real_engine.py
    # optionally: --tt-bin-dir "C:\\Program Files (x86)\\teraterm"

Exit 0 => real engine wrote STATUS=SUCCESS_PROVISIONED and we read it back.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tt_agent_hw.paths import tt_bin_dir
from tt_agent_hw.status import is_success, is_terminal, read_status_file

PROBE_TTL = """; Transport-free real-engine probe for run {run_id}
StateFile = '{state_file}'

CurrentState = 'STATUS=INITIALIZING'
fileopen fHandle StateFile 0
filelock fHandle
filewrite fHandle CurrentState
fileunlock fHandle
fileclose fHandle

mpause 200

CurrentState = 'STATUS=SUCCESS_PROVISIONED'
fileopen fHandle StateFile 0
filelock fHandle
filewrite fHandle CurrentState
fileunlock fHandle
fileclose fHandle
end
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tt-bin-dir", type=Path, default=None)
    ap.add_argument("--timeout", type=float, default=20.0)
    args = ap.parse_args()

    bin_dir = Path(args.tt_bin_dir) if args.tt_bin_dir else tt_bin_dir()
    macro_exe = bin_dir / "ttpmacro.exe"
    if not macro_exe.is_file():
        print(f"[FAIL] ttpmacro.exe not found: {macro_exe}")
        print("       Install Tera Term or pass --tt-bin-dir.")
        return 2

    work = Path(tempfile.mkdtemp(prefix="tt_engine_probe_"))
    state_file = work / "execution.state"
    macro_file = work / "probe.ttl"
    # TTL string literals need doubled backslashes for Windows paths.
    macro_file.write_text(
        PROBE_TTL.format(run_id=work.name, state_file=str(state_file).replace("\\", "\\\\")),
        encoding="ascii",
    )

    print(f"[..] engine: {macro_exe}")
    print(f"[..] macro:  {macro_file}")
    print(f"[..] state:  {state_file}")

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

    print(f"[..] final status: {final!r}")
    if is_success(final):
        print("[OK] REAL ttpmacro.exe engine + STATUS handshake verified")
        return 0
    print("[FAIL] real engine did not produce STATUS=SUCCESS_PROVISIONED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
