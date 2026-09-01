# Self-discovering serial probe + agentic CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `ports`, `discover`, `profile show`, `cmds`, and `call` so an agent can find baud/link, harvest commands into a per-COM profile, and invoke them via CLI — without assuming U-Boot or fixed baud.

**Architecture:** pyserial-backed `SerialTransport` for discover/call (fake transport in tests). Deterministic baud sweep + nudge ladder + heuristic help parser → `profiles/COMn.json`. Provision/TTL path stays untouched. Package bumps to 0.2.0.

**Tech Stack:** Python 3.12, pyserial, pytest, existing `tt_agent_hw` workspace/status/CLI patterns.

**Spec:** `docs/superpowers/specs/2026-09-01-self-discovering-probe-design.md`

## Global Constraints

- Windows-first serial (`COMn`); framing fixed **8N1** this slice.
- Profile key = COM number → file `profiles/COM{N}.json` under `TT_AGENT_RUNTIME_DIR`.
- Baud default list: `115200,57600,38400,19200,9600,4800` (fast→slow); `--baud` pins; `--baud-list` overrides.
- Default nudges: optional break, CR, `help`, `?`, `AT`.
- No LLM parsing; heuristic extract only.
- `call` requires an existing profile; TX is command id **or** `--send`, not both missing.
- Exit codes: 0 success, 1 soft fail (silent / expect miss), 2 preflight/config, 3 unexpected.
- Keep all existing provision tests green; do not change TTL provision semantics.
- Runtime dep: `pyserial>=3.5`.
- Version: package `__version__` and `pyproject.toml` → `0.2.0`.

## File map

| File | Responsibility |
|------|----------------|
| `src/tt_agent_hw/serial_transport.py` | `SerialTransport` protocol, `PyserialTransport`, `FakeSerialTransport` |
| `src/tt_agent_hw/ports.py` | Enumerate COM ports + USB hints |
| `src/tt_agent_hw/scoring.py` | Score RX blob → float |
| `src/tt_agent_hw/commands_extract.py` | Heuristic help → list of commands |
| `src/tt_agent_hw/profile_store.py` | Read/write/backup per-COM JSON profiles |
| `src/tt_agent_hw/discover.py` | Baud sweep, nudges, harvest, write profile |
| `src/tt_agent_hw/call_session.py` | Send line + capture + optional expect |
| `src/tt_agent_hw/models.py` | Add profile/discover/call dataclasses |
| `src/tt_agent_hw/status.py` | Add discover status token constants |
| `src/tt_agent_hw/cli.py` | Wire new subcommands |
| `src/tt_agent_hw/__init__.py` | Version 0.2.0 |
| `pyproject.toml` | Version + pyserial dep |
| `README.md` | Agent loop docs |
| `tests/test_scoring.py` | Scoring unit tests |
| `tests/test_commands_extract.py` | Parser fixtures |
| `tests/test_profile_store.py` | Profile IO |
| `tests/test_ports.py` | Port enum with monkeypatch |
| `tests/test_discover.py` | Discover with fake transport |
| `tests/test_call_session.py` | call send/expect |
| `tests/test_cli_discover.py` | CLI integration with fakes |

---

### Task 1: Models, status tokens, dependency, version bump

**Files:**
- Modify: `src/tt_agent_hw/models.py`
- Modify: `src/tt_agent_hw/status.py`
- Modify: `src/tt_agent_hw/__init__.py`
- Modify: `pyproject.toml`
- Test: `tests/test_models_discover.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class DiscoveredCommand: id: str; send: str; summary: str; source: str`
  - `@dataclass(frozen=True) class BaudAttempt: baud: int; bytes_rx: int; score: float`
  - `@dataclass class DeviceProfile:` fields per spec (`schema_version`, `com`, `port_name`, `baud`, `framing` dict, `usb_hint` dict, `fingerprint` dict, `commands: list[DiscoveredCommand]`, `nudges_tried: list[str]`, `baud_tried: list[BaudAttempt]`, `confidence: float`, `discovered_at: str`, `run_id: str`, `tool_version: str`) with `to_dict()` / `from_dict(cls, data: dict) -> DeviceProfile`
  - `@dataclass(frozen=True) class DiscoverResult: run_id: str; status: str; profile_path: str | None; log_file: str; duration_sec: float; workspace: str; profile: DeviceProfile | None` + `to_dict()`
  - `@dataclass(frozen=True) class CallResult: run_id: str; tx: str; rx: str; matched: bool | None; profile_baud: int; log_file: str; workspace: str` + `to_dict()`
  - Status constants: `SUCCESS_DISCOVERED = "STATUS=SUCCESS_DISCOVERED"`, `FAILED_PROBE_SILENT`, `FAILED_NO_PORT` (full `STATUS=` prefix form)

- [ ] **Step 1: Write failing tests for profile roundtrip**

```python
# tests/test_models_discover.py
from tt_agent_hw.models import BaudAttempt, DeviceProfile, DiscoveredCommand

def test_device_profile_roundtrip():
    p = DeviceProfile(
        schema_version=1,
        com=7,
        port_name="COM7",
        baud=9600,
        framing={"bytesize": 8, "parity": "N", "stopbits": 1},
        usb_hint={"friendly_name": "USB Serial Port (COM7)"},
        fingerprint={"banner": "hi", "help_raw_path": "artifacts/help_raw.txt", "help_raw_sha256": ""},
        commands=[DiscoveredCommand(id="help", send="help", summary="nudge", source="nudge")],
        nudges_tried=["cr", "help"],
        baud_tried=[BaudAttempt(baud=9600, bytes_rx=10, score=0.8)],
        confidence=0.8,
        discovered_at="2026-09-01T00:00:00Z",
        run_id="run_abc",
        tool_version="0.2.0",
    )
    data = p.to_dict()
    p2 = DeviceProfile.from_dict(data)
    assert p2.com == 7
    assert p2.commands[0].id == "help"
    assert p2.baud_tried[0].baud == 9600
```

- [ ] **Step 2: Run test — expect fail (classes missing)**

Run: `pytest tests/test_models_discover.py -v`  
Expected: FAIL import/attribute error

- [ ] **Step 3: Implement models + status constants + version + pyserial dep**

Append to `models.py` the dataclasses above.  
In `status.py` add to known sets / module-level constants:

```python
SUCCESS_DISCOVERED = "STATUS=SUCCESS_DISCOVERED"
FAILED_PROBE_SILENT = "STATUS=FAILED_PROBE_SILENT"
FAILED_NO_PORT = "STATUS=FAILED_NO_PORT"
# Keep FAILED_CONNECTION_REFUSED already present
```

`__init__.py`: `__version__ = "0.2.0"`  
`pyproject.toml`: `version = "0.2.0"` and dependencies include `"pyserial>=3.5"`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_models_discover.py tests/test_status.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tt_agent_hw/models.py src/tt_agent_hw/status.py src/tt_agent_hw/__init__.py pyproject.toml tests/test_models_discover.py
git commit -m "feat: add discover/call models and bump to 0.2.0"
```

---

### Task 2: Serial transport seam + fake

**Files:**
- Create: `src/tt_agent_hw/serial_transport.py`
- Test: `tests/test_serial_transport.py`

**Interfaces:**
- Produces:
  - `class SerialTransport(Protocol):` methods `open() -> None`, `close() -> None`, `write(data: bytes) -> None`, `read(max_bytes: int = 4096, timeout: float | None = None) -> bytes`, `reset_input_buffer() -> None`, `send_break(duration: float = 0.25) -> None`, property `is_open: bool`
  - `class PyserialTransport:` ctor `(port: str, baud: int, bytesize=8, parity="N", stopbits=1, timeout: float = 0.2)`
  - `class FakeSerialTransport:` ctor optional `script: dict[int, list[tuple[bytes | None, bytes]]]` mapping baud → list of (tx_contains_or_None, rx_response). Also `recorded: list[tuple[int, bytes]]` of writes. `configure_baud(baud: int)` before open or pass baud in ctor like pyserial.

- [ ] **Step 1: Failing test — fake echoes by script**

```python
# tests/test_serial_transport.py
from tt_agent_hw.serial_transport import FakeSerialTransport

def test_fake_returns_scripted_rx_for_help():
    fake = FakeSerialTransport(
        port="COM7",
        baud=9600,
        script={
            9600: [
                (b"help", b"Available commands:\r\nhelp - show help\r\n"),
            ]
        },
    )
    fake.open()
    fake.write(b"help\r")
    rx = fake.read(4096)
    assert b"Available commands" in rx
    fake.close()
```

- [ ] **Step 2: Run — expect fail**

Run: `pytest tests/test_serial_transport.py -v`

- [ ] **Step 3: Implement protocol + Fake + PyserialTransport**

```python
# serial_transport.py sketch
from typing import Protocol
import serial  # pyserial

class SerialTransport(Protocol):
    def open(self) -> None: ...
    def close(self) -> None: ...
    def write(self, data: bytes) -> None: ...
    def read(self, max_bytes: int = 4096, timeout: float | None = None) -> bytes: ...
    def reset_input_buffer(self) -> None: ...
    def send_break(self, duration: float = 0.25) -> None: ...
    @property
    def is_open(self) -> bool: ...

class PyserialTransport:
    def __init__(self, port: str, baud: int, bytesize: int = 8, parity: str = "N",
                 stopbits: float = 1, timeout: float = 0.2) -> None:
        self.port = port
        self.baud = baud
        # map parity N/E/O to serial.PARITY_*
        self._ser: serial.Serial | None = None
    # implement open/close/write/read/reset_input_buffer/send_break

class FakeSerialTransport:
    """Match write substrings in script[baud] FIFO; unmatched write → empty read."""
    ...
```

- [ ] **Step 4: pytest pass**

Run: `pytest tests/test_serial_transport.py -q`

- [ ] **Step 5: Commit**

```bash
git add src/tt_agent_hw/serial_transport.py tests/test_serial_transport.py
git commit -m "feat: add SerialTransport with pyserial and fake"
```

---

### Task 3: Port enumeration

**Files:**
- Create: `src/tt_agent_hw/ports.py`
- Test: `tests/test_ports.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class PortInfo: name: str; com: int | None; description: str; hardware_id: str; has_profile: bool`
  - `def parse_com_number(name: str) -> int | None`  # "COM7" → 7
  - `def list_ports(*, runtime_dir: Path | None = None, enumerator=None) -> list[PortInfo]`
  - Default enumerator uses `serial.tools.list_ports.comports()`
  - `has_profile` true if `(runtime_dir or paths.runtime_dir()) / "profiles" / f"COM{n}.json"` exists
  - `def resolve_default_com(ports: list[PortInfo]) -> int | None` — exactly one non-Bluetooth candidate (description/hwid not matching `BTHENUM` / `Bluetooth` case-insensitive); else None

- [ ] **Step 1: Failing tests**

```python
from pathlib import Path
from tt_agent_hw.ports import PortInfo, list_ports, parse_com_number, resolve_default_com

def test_parse_com_number():
    assert parse_com_number("COM7") == 7
    assert parse_com_number("com12") == 12
    assert parse_com_number("not") is None

def test_list_ports_marks_profile(tmp_path: Path):
    prof = tmp_path / "profiles"
    prof.mkdir()
    (prof / "COM7.json").write_text("{}", encoding="utf-8")

    class Fake:
        device = "COM7"
        description = "USB Serial Port"
        hwid = "FTDIBUS\\VID_0403"

    ports = list_ports(runtime_dir=tmp_path, enumerator=lambda: [Fake()])
    assert ports[0].com == 7
    assert ports[0].has_profile is True

def test_resolve_default_com_single_usb():
    ports = [
        PortInfo("COM3", 3, "Standard Serial over Bluetooth link", "BTHENUM\\x", False),
        PortInfo("COM7", 7, "USB Serial Port", "FTDIBUS\\x", False),
    ]
    assert resolve_default_com(ports) == 7
```

- [ ] **Step 2: Run fail → implement `ports.py` → pass**

Run: `pytest tests/test_ports.py -q`

- [ ] **Step 3: Commit**

```bash
git add src/tt_agent_hw/ports.py tests/test_ports.py
git commit -m "feat: enumerate serial ports with profile flags"
```

---

### Task 4: RX scoring

**Files:**
- Create: `src/tt_agent_hw/scoring.py`
- Test: `tests/test_scoring.py`

**Interfaces:**
- Produces: `def score_rx(data: bytes) -> float` in `[0.0, 1.0]` approximately  
- Silence floor constant: `SILENCE_FLOOR = 0.05`  
- Strong threshold: `STRONG_SCORE = 0.55`

Scoring rules (implement exactly):

```python
def score_rx(data: bytes) -> float:
    if not data:
        return 0.0
    # printable: 0x09,0x0a,0x0d or 0x20-0x7e
    # ratio = printable/len
    # byte_score = min(1.0, log2(1+len)/10)
    # keyword bonus: each of help,command,commands,usage,ok,error,menu,available in lower text → +0.08 cap +0.32
    # prompt bonus: if any line stripped endswith > # $ : → +0.05
    # if ratio < 0.5: multiply total by 0.3 (noise penalty)
    # clamp 0..1
```

- [ ] **Step 1: Tests**

```python
from tt_agent_hw.scoring import score_rx, SILENCE_FLOOR, STRONG_SCORE

def test_empty_is_zero():
    assert score_rx(b"") == 0.0

def test_help_text_scores_high():
    s = score_rx(b"Available commands:\r\nhelp - show help\r\nOK>\r\n")
    assert s >= STRONG_SCORE

def test_binary_noise_low():
    s = score_rx(bytes(range(256)) * 2)
    assert s < SILENCE_FLOOR or s < 0.3
```

- [ ] **Step 2: Implement → pytest pass → commit**

```bash
git add src/tt_agent_hw/scoring.py tests/test_scoring.py
git commit -m "feat: deterministic serial RX scoring"
```

---

### Task 5: Command extraction

**Files:**
- Create: `src/tt_agent_hw/commands_extract.py`
- Test: `tests/test_commands_extract.py`

**Interfaces:**
- Produces:
  - `def slug_id(send: str) -> str`
  - `def extract_commands(help_raw: str, *, productive_nudges: list[str]) -> list[DiscoveredCommand]`
  - Dedup by `send`; unique `id` with `_2` suffix on collision
  - Always emit productive nudges with `source="nudge"` first
  - Parse lines for ` - `, ` — `, `: ` patterns; `AT+...`; bare tokens length 2–32

- [ ] **Step 1: Tests**

```python
from tt_agent_hw.commands_extract import extract_commands, slug_id

def test_slug_id():
    assert slug_id("AT+GMR") == "at_gmr"
    assert slug_id("help") == "help"

def test_extract_nudge_and_parsed():
    raw = "Available commands:\nreset - reboot board\nstatus: show status\n"
    cmds = extract_commands(raw, productive_nudges=["help", "?"])
    sends = [c.send for c in cmds]
    assert "help" in sends
    assert "?" in sends
    assert "reset" in sends
    assert "status" in sends
    assert all(c.id for c in cmds)
```

- [ ] **Step 2: Implement → pass → commit**

```bash
git add src/tt_agent_hw/commands_extract.py tests/test_commands_extract.py
git commit -m "feat: heuristic help command extraction"
```

---

### Task 6: Profile store

**Files:**
- Create: `src/tt_agent_hw/profile_store.py`
- Test: `tests/test_profile_store.py`

**Interfaces:**
- Produces:
  - `def profiles_dir(runtime_dir: Path) -> Path`
  - `def profile_path(runtime_dir: Path, com: int) -> Path`  # `.../profiles/COM{com}.json`
  - `def save_profile(runtime_dir: Path, profile: DeviceProfile) -> Path`  
    - If existing file: copy to `COM{n}.prev.json` then write  
    - JSON indent=2, utf-8
  - `def load_profile(runtime_dir: Path, com: int) -> DeviceProfile`  
    - FileNotFoundError if missing

- [ ] **Step 1: Test backup on overwrite**

```python
def test_save_profile_backs_up_previous(tmp_path, sample_profile):
    path = save_profile(tmp_path, sample_profile)
    assert path.name == "COM7.json"
    p2 = replace(sample_profile, baud=115200, confidence=0.9)
    save_profile(tmp_path, p2)
    assert (tmp_path / "profiles" / "COM7.prev.json").is_file()
    loaded = load_profile(tmp_path, 7)
    assert loaded.baud == 115200
```

- [ ] **Step 2: Implement → pass → commit**

```bash
git add src/tt_agent_hw/profile_store.py tests/test_profile_store.py
git commit -m "feat: per-COM profile store with prev backup"
```

---

### Task 7: Discover controller

**Files:**
- Create: `src/tt_agent_hw/discover.py`
- Test: `tests/test_discover.py`

**Interfaces:**
- Produces:
  - `DEFAULT_BAUD_LIST: list[int] = [115200, 57600, 38400, 19200, 9600, 4800]`
  - `class DiscoverError(Exception): ...`
  - `def read_until_quiet(transport, *, quiet_s: float = 0.25, max_s: float = 2.0) -> bytes`
  - `def run_discover(*, com: int, runtime_dir: Path, baud_list: list[int] | None = None, send_break: bool = True, early_stop: bool = True, transport_factory=None, usb_hint: dict | None = None, tool_version: str = ...) -> DiscoverResult`
  - `transport_factory(port: str, baud: int) -> SerialTransport` default builds `PyserialTransport`
  - On success: write status SUCCESS_DISCOVERED, help_raw.txt, discover_scores.json, save_profile
  - On all silent: FAILED_PROBE_SILENT, no profile write
  - On open failure all bauds: FAILED_CONNECTION_REFUSED

**Nudge ladder implementation:**

```python
NUDGES = [
    ("cr", b"\r"),
    ("help", b"help\r"),
    ("?", b"?\r"),
    ("AT", b"AT\r"),
]
```

For each baud: open → optional break → reset_input → for each nudge write + read_until_quiet → aggregate RX → score → close.

- [ ] **Step 1: Failing test — silent all bauds**

```python
def test_discover_silent(tmp_path):
    def factory(port, baud):
        return FakeSerialTransport(port=port, baud=baud, script={})  # always empty RX
    result = run_discover(com=7, runtime_dir=tmp_path, baud_list=[9600, 115200],
                          transport_factory=factory, send_break=False)
    assert "FAILED_PROBE_SILENT" in result.status
    assert result.profile is None
    assert not (tmp_path / "profiles" / "COM7.json").exists()
```

- [ ] **Step 2: Failing test — finds help at 9600**

```python
def test_discover_finds_baud_and_writes_profile(tmp_path):
    help_body = b"\r\nAvailable commands:\r\nreset - reboot\r\nhelp - help\r\n>"
    def factory(port, baud):
        script = {}
        if baud == 9600:
            script[9600] = [
                (b"\r", b""),
                (b"help", help_body),
                (b"?", b""),
                (b"AT", b""),
                (b"help", help_body),  # harvest
            ]
        return FakeSerialTransport(port=port, baud=baud, script=script)
    result = run_discover(com=7, runtime_dir=tmp_path, baud_list=[115200, 9600],
                          transport_factory=factory, send_break=False, early_stop=True)
    assert "SUCCESS_DISCOVERED" in result.status
    assert result.profile is not None
    assert result.profile.baud == 9600
    assert (tmp_path / "profiles" / "COM7.json").is_file()
    assert any(c.send == "reset" for c in result.profile.commands)
```

- [ ] **Step 3: Implement `discover.py` → pass both tests**

Run: `pytest tests/test_discover.py -q`

- [ ] **Step 4: Commit**

```bash
git add src/tt_agent_hw/discover.py tests/test_discover.py
git commit -m "feat: self-discovering baud sweep and profile write"
```

---

### Task 8: Call session

**Files:**
- Create: `src/tt_agent_hw/call_session.py`
- Test: `tests/test_call_session.py`

**Interfaces:**
- Produces:
  - `def run_call(*, runtime_dir: Path, com: int, command_id: str | None = None, send: str | None = None, expect: str | None = None, timeout_s: float = 3.0, transport_factory=None) -> CallResult`
  - Raises `FileNotFoundError` if profile missing; `ValueError` if neither/both id and send; `KeyError` if id unknown
  - `matched` is `None` if no expect; else bool
  - Uses `read_until_quiet` from discover module (import to avoid duplication) or shared `serial_io.py` — **prefer move `read_until_quiet` to `serial_transport.py` or tiny `serial_io.py` if discover already shipped; if still same PR, put `read_until_quiet` in `serial_io.py` used by both**

**Refactor note for implementer:** If Task 7 already landed `read_until_quiet` in `discover.py`, either re-export from there for call or extract to `serial_io.py` in this task with no behavior change (update discover imports). Prefer extract:

- Create `src/tt_agent_hw/serial_io.py` with `read_until_quiet` + `append_cr(payload: str | bytes) -> bytes`

- [ ] **Step 1: Tests**

```python
def test_call_by_id_expect_match(tmp_path, profile_on_disk):
    def factory(port, baud):
        return FakeSerialTransport(port=port, baud=baud, script={
            baud: [(b"help", b"help text OK\r\n")]
        })
    result = run_call(runtime_dir=tmp_path, com=7, command_id="help", expect="OK",
                      transport_factory=factory)
    assert result.matched is True
    assert "OK" in result.rx

def test_call_expect_miss(tmp_path, profile_on_disk):
    ...
    assert result.matched is False
```

- [ ] **Step 2: Implement → pass → commit**

```bash
git add src/tt_agent_hw/call_session.py src/tt_agent_hw/serial_io.py src/tt_agent_hw/discover.py tests/test_call_session.py
git commit -m "feat: agentic call session against per-COM profile"
```

---

### Task 9: CLI wiring

**Files:**
- Modify: `src/tt_agent_hw/cli.py`
- Test: `tests/test_cli_discover.py`
- Modify: `README.md`

**Interfaces:**
- Produces subcommands:
  - `ports [--json] [--runtime-dir]`
  - `discover [--com N] [--baud B] [--baud-list a,b] [--no-early-stop] [--no-break] [--json] [--runtime-dir]`
  - `profile show --com N [--json] [--runtime-dir]`
  - `cmds --com N [--json] [--runtime-dir]`
  - `call --com N [command_id] [--send TEXT] [--expect RE] [--timeout S] [--json] [--runtime-dir]`
- `doctor` still works; optionally print pyserial OK line without failing if missing only when? Spec: add pyserial check — if import fails, doctor FAIL (since required dep now).

**CLI exit mapping:**

| command | condition | code |
|---------|-----------|------|
| ports | ok | 0 |
| discover | SUCCESS_DISCOVERED | 0 |
| discover | FAILED_PROBE_SILENT | 1 |
| discover | no port / open fail | 2 |
| profile/cmds | missing profile | 2 |
| call | matched True / no expect + IO ok | 0 |
| call | matched False | 1 |
| call | missing profile / bad args | 2 |

- [ ] **Step 1: CLI tests using monkeypatch on `run_discover` / `run_call` / `list_ports`**

```python
def test_cli_discover_success(monkeypatch, tmp_path):
    from tt_agent_hw.cli import main
    monkeypatch.setenv("TT_AGENT_RUNTIME_DIR", str(tmp_path))
    # monkeypatch run_discover to return DiscoverResult SUCCESS...
    assert main(["discover", "--com", "7", "--json"]) == 0

def test_cli_call_requires_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("TT_AGENT_RUNTIME_DIR", str(tmp_path))
    assert main(["call", "--com", "7", "help"]) == 2
```

- [ ] **Step 2: Implement argparse + handlers in `cli.py`**

Keep `build_parser()` structure; add subparsers. For `profile` use sub-subparser `show`.

- [ ] **Step 3: Update README with agent loop**

```markdown
## Discover + call (unknown UART)

```bat
tt-agent-hw ports --json
tt-agent-hw discover --com 7 --json
tt-agent-hw cmds --com 7 --json
tt-agent-hw call --com 7 help --json
```
```

- [ ] **Step 4: Full suite**

Run: `pytest -q`  
Expected: all prior + new tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/tt_agent_hw/cli.py tests/test_cli_discover.py README.md
git commit -m "feat: CLI ports/discover/profile/cmds/call"
```

---

### Task 10: Live hardware smoke (manual, optional)

**Files:** none required (operator script ok under `spikes/discover_com7.py` if useful)

- [ ] **Step 1: With FTDI on COM7**

```bat
cd C:\Users\z005a5ff\Projects\tt-agent-hw
set TT_AGENT_RUNTIME_DIR=%TEMP%\tt-agent-runtime
set TT_AGENT_TT_BIN_DIR=%LOCALAPPDATA%\Programs\TeraTerm\current
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\tt-agent-hw.exe ports --json
.venv\Scripts\tt-agent-hw.exe discover --com 7 --json
```

Expected without DUT: exit 1, `FAILED_PROBE_SILENT`, no profile.  
Expected with DUT answering help: exit 0, `profiles\COM7.json`, then `cmds` / `call`.

- [ ] **Step 2: Note results in `docs/superpowers/reports/` only if run** — skip if no DUT.

- [ ] **Step 3: Final commit if smoke script added; else done**

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| Per-COM profiles + `.prev` | 6 |
| Baud sweep defaults + pin/list | 7, 9 |
| Nudges CR/help/?/AT + break flag | 7 |
| Scoring + early stop | 4, 7 |
| Help harvest + heuristic commands | 5, 7 |
| ports / discover / profile show / cmds / call | 3, 7, 8, 9 |
| call profile-required + id or --send | 8, 9 |
| Exit codes 0/1/2/3 | 7–9 |
| pyserial + fake seam | 2 |
| provision unchanged | 9 (full pytest) |
| Version 0.2.0 | 1 |
| README agent loop | 9 |
| Interactive console | out of scope (spec follow-up) |
| LLM parse | out of scope |

## Placeholder / consistency review

- No TBD steps; fake transport script FIFO must be documented in Task 2 implementation comments.
- `read_until_quiet` shared via `serial_io.py` by Task 8 if not extracted earlier — Task 7 may define it locally then Task 8 extracts (allowed).
- Types: `DeviceProfile`, `DiscoveredCommand`, `DiscoverResult`, `CallResult` named consistently across tasks.
- CLI `profile show` is two tokens: subparser `profile` → `show`.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-01-self-discovering-probe.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session with executing-plans and checkpoints  

Which approach?
