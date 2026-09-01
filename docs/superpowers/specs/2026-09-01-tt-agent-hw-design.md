# tt-agent-hw Design — 2026-09-01

## Intent

Standalone Windows project that lets an orchestration agent deterministically configure, drive, and verify **Tera Term** (`ttermpro.exe` / `ttpmacro.exe`) for single-target hardware flash + boot verify over UART — without human UI interaction.

**Not related to GZMO.** Own repo, own venv, own runtime directory.

Source material (copied under `docs/source/`):

- `Autonomous Multi-Agent Hardware Provisioning & CI_CD Framework.txt`
- `Tera Term Deep Dive Guide.txt`

## Goals (v1)

1. Hermetic per-run workspace under a configurable runtime root.
2. Jinja2-rendered TTL macro with a file-based `STATUS=*` handshake.
3. Python 3.12 controller that spawns `ttpmacro.exe`, polls status, enforces timeout, returns structured result.
4. CLI: `provision` + `doctor`.
5. Tests that do **not** require hardware (fake macro binary).
6. Documented path to real COM-port flash+verify.

## Non-goals (v1)

- Self-healing matrix (taskkill zombies, USB re-enum, relay power cycle, YMODEM→XMODEM fallback).
- Multi-COM / multi-agent fan-out / JSON-RPC orchestrator fabric.
- SSH/Telnet target jobs.
- Checked-in GitHub Actions workflow (README snippet only).
- Shipping Tera Term binaries inside the git repo.
- Any GZMO dependency or shared path.

## Layout

### Source repo

`C:\Users\z005a5ff\Projects\tt-agent-hw`

```
tt-agent-hw/
  pyproject.toml
  README.md
  .env.example
  .gitignore
  config/base_teraterm.ini
  templates/task_template.ttl.j2
  src/tt_agent_hw/
    __init__.py
    models.py       # TargetJob
    status.py       # STATUS=* parse + terminal classification
    workspace.py    # run_<id> hermetic dirs
    controller.py   # TeraTermAgentController
    cli.py          # provision, doctor
  tests/
    test_status.py
    test_workspace.py
    test_controller_mock.py
    fixtures/fake_ttpmacro.py  # or .bat/.cmd wrapper
  docs/
    source/         # original specs
    superpowers/specs/
```

### Runtime (not in git)

Default: `C:\agent_runtime` via `TT_AGENT_RUNTIME_DIR`.

```
C:\agent_runtime\
  workspaces\
    run_<8hex>\
      task.ttl
      logs\console.log
      status\execution.state
      artifacts\          # optional staging
```

Tera Term install: `TT_AGENT_TT_BIN_DIR` (default `C:\Program Files (x86)\teraterm`) containing `ttpmacro.exe`, `ttermpro.exe`.

## Package & environment

| Item | Choice |
|------|--------|
| Language | Python ≥ 3.12 |
| Package name | `tt_agent_hw` |
| Console script | `tt-agent-hw` |
| Build | `pyproject.toml` (hatchling or setuptools) |
| Runtime deps | `jinja2` |
| Dev deps | `pytest`, `ruff` |
| Venv | `.venv\` at repo root |
| Secrets/config | `.env` (gitignored); `.env.example` committed |

Install:

```bat
cd C:\Users\z005a5ff\Projects\tt-agent-hw
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Core types

### `TargetJob`

| Field | Type | Role |
|-------|------|------|
| `com_port` | `int` | COM index for `/C=` |
| `baud_rate` | `int` | `/BAUD=` |
| `boot_prompt` | `str` | `wait` target (e.g. `U-Boot>`) |
| `erase_command` | `str` | sent after prompt |
| `erase_ack` | `str` | success token for erase |
| `transfer_trigger_command` | `str` | e.g. `loady 0x80000000 115200` |
| `boot_command` | `str` | post-transfer boot |
| `boot_success_regex` | `str` | `waitregex` success pattern |
| `boot_timeout` | `int` | seconds for boot wait + orchestrator budget base |
| `binary_path` | `Path` | firmware image for `ymodemsend` |

### Status contract

TTL writes a single-line ASCII file `status/execution.state`:

```
STATUS=<TOKEN>
```

| Token class | Examples | Terminal? |
|-------------|----------|-----------|
| Progress | `INITIALIZING` | no |
| Success | `SUCCESS_PROVISIONED` | yes |
| Failure | `FAILED_CONNECTION_REFUSED`, `FAILED_BOOT_PROMPT_TIMEOUT`, `FAILED_FLASH_ERASE`, `FAILED_YMODEM_READY_TIMEOUT`, `FAILED_YMODEM_TRANSFER_ABORTED`, `FAILED_TARGET_CRASH`, `FAILED_BOOT_TIMEOUT` | yes |
| Orchestrator | `TIMEOUT_ORCHESTRATOR` | yes (controller-synthesized) |

Orchestrator treats any status containing `SUCCESS` or `FAILED` as terminal when the line starts with `STATUS=`.

## Controller algorithm

`TeraTermAgentController.execute_provisioning(job) -> dict`:

1. **Preflight** — runtime writable; `ttpmacro.exe` exists; `job.binary_path` is a file.
2. **Workspace** — `run_id = run_<uuid4.hex[:8]>`; create `logs/`, `status/` (and `artifacts/` empty).
3. **Render** — load `templates/task_template.ttl.j2`; write `task.ttl` as ASCII; escape Windows paths for TTL (`\` → `\\`).
4. **Spawn** — `subprocess.Popen([ttpmacro, "/V", task.ttl], cwd=tt_bin_dir, stdout=DEVNULL, stderr=DEVNULL)`.
5. **Poll** loop (0.5s):
   - If `execution.state` readable and terminal → break.
   - If process exited → break (read status if present; else synthesize failure).
   - If `monotonic elapsed > boot_timeout + 60` → kill process → `TIMEOUT_ORCHESTRATOR`.
6. **Return** `{run_id, status, log_file, duration_sec}`.

On failure paths, **do not** delete the workspace (operator debug).

## TTL template (v1 behavior)

Matches the framework spec:

1. `ReportStatus` helper with `fileopen` / `filelock` / `filewrite` / `fileunlock` / `fileclose`.
2. `STATUS=INITIALIZING`.
3. `connect` with `/C={{com_port}} /BAUD={{baud_rate}} /L="<log>" /H /AUTOWINCLOSE=on`.
4. Connection check (`result != 2` → `FAILED_CONNECTION_REFUSED`).
5. `flushrecv`, `sendbreak`, short pause, empty `sendln`, `wait` boot prompt.
6. Erase command + ack vs `ERROR`.
7. Transfer trigger, `wait 'C'`, `ymodemsend`.
8. Boot command + `waitregex` success vs `Kernel panic` / `Hard Fault`.
9. `disconnect` / `end`.

`config/base_teraterm.ini` is shipped for operators (headless defaults from the framework doc). v1 connect string uses CLI flags; optional `/F=` wiring is a follow-up.

## CLI

### `tt-agent-hw doctor`

Checks:

- Python package importable
- `TT_AGENT_RUNTIME_DIR` creatable/writable
- `ttpmacro.exe` and `ttermpro.exe` under `TT_AGENT_TT_BIN_DIR`

Exit `0` if all OK, `2` otherwise. Prints each check.

### `tt-agent-hw provision`

Flags map 1:1 to `TargetJob` fields. Prints JSON-ish or plain result summary.

| Exit code | Meaning |
|-----------|---------|
| 0 | status contains `SUCCESS` |
| 1 | terminal `FAILED_*` from TTL |
| 2 | preflight / config / usage |
| 3 | orchestrator timeout or unexpected controller failure |

## Testing strategy

| Test | Hardware? | Asserts |
|------|-----------|---------|
| `test_status` | no | parse + terminal classification |
| `test_workspace` | no | dir layout under temp runtime |
| `test_controller_mock` | no | controller with **fake** `ttpmacro` that writes `SUCCESS_PROVISIONED` or `FAILED_*` |
| `@pytest.mark.hardware` | yes | real COM; skipped unless `TT_AGENT_HW=1` |

Fake macro: small Python script or `.cmd` invoked instead of real `ttpmacro.exe` via injected `macro_exe` path on the controller (test seam).

## Error handling (v1)

- Preflight failures → CLI exit 2, no spawn.
- Locked status file → ignore `PermissionError`, retry next poll.
- Hung macro → kill, `TIMEOUT_ORCHESTRATOR`, exit 3.
- No automatic global `taskkill /IM ttermpro.exe` (documented Phase 4 only).

## CI stance (v1)

- No required self-hosted runner workflow in-repo.
- README documents the framework’s GHA sketch for later.
- Default CI (when added) runs mock tests only on any Windows/python runner.

## Success criteria

1. Fresh clone + venv + `pip install -e ".[dev]"` works on Windows.
2. `tt-agent-hw doctor` reflects real binary/runtime state.
3. Mock provision → success and failure paths covered by pytest.
4. Manual hardware run documented with U-Boot/YMODEM example values.
5. Zero references to GZMO.

## Follow-ups (post-v1)

1. Phase 4 self-heal matrix.
2. `/F=run.ini` merged from `base_teraterm.ini` per run.
3. XMODEM-CRC fallback profile.
4. Multi-port broadcast / parallel workspaces.
5. Checked-in GHA workflow for labeled `hw-bench-*` runners.
6. SSH target job type.

## Decisions log

| Decision | Choice |
|----------|--------|
| Repo path | `C:\Users\z005a5ff\Projects\tt-agent-hw` |
| Stack | Python 3.12 |
| v1 scope | Single-target flash+verify E2E |
| Runtime vs repo | Separate configurable runtime path |
| Package / CLI | `tt_agent_hw` / `tt-agent-hw` |
| Approach | Spec-faithful Python package with mockable controller |
