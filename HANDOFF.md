# Handoff: tt-agent-hw — Tera Term Hardware Provisioning Orchestrator (v1)

**Timestamp:** 2026-09-01 (session-local, no wall-clock UTC source available in this environment)
**Status:** Complete for what's reachable here — real-binary verified (engine, TCP connect, full CLI pipeline); serial-success path blocked by locked-down environment (no admin for com0com, no RS232 adapter).
**Primary Objectives:** Stand up a standalone (non-GZMO) Windows project that drives Tera Term (`ttpmacro.exe`/`ttermpro.exe`) to flash and boot-verify one UART target headlessly, with a file-based STATUS handshake and hardware-free mock tests.

---
> **Addendum 2026-09-01 (real Tera Term 5.6.2 installed):** The mock-only
> caveat below is partially closed. Against the **real** binaries we verified
> `doctor` (4/4 OK), the macro engine + STATUS handshake, real
> `connect`/`wait`/`sendln` over TCP, and the full CLI `provision` pipeline
> (genuine COM4 attempt → `FAILED_CONNECTION_REFUSED` → exit 1). The serial
> **success** path (`/C=` open + `ymodemsend`) stays blocked — com0com's
> kernel driver needs admin (denied here; Zscaler also blocked its download)
> and no RS232 adapter is available. Full detail + reproduce commands:
> `docs/superpowers/reports/2026-09-01-real-binary-verification.md`.


## 1. Executive Summary & Changes Made

- Scaffolded new independent repo `tt-agent-hw` at `C:\Users\z005a5ff\Projects\tt-agent-hw` (own git history, own venv, zero GZMO coupling — verified by grep).
- Implemented Python 3.12 package `tt_agent_hw`: Jinja2-rendered TTL macro generation, hermetic per-run workspace, `TeraTermAgentController` (spawn `ttpmacro.exe`, poll `execution.state`, enforce timeout+kill), CLI (`tt-agent-hw doctor` / `provision`).
- Built a hardware-free test harness: `tests/fixtures/fake_ttpmacro.py` stands in for `ttpmacro.exe` so the full status handshake (`STATUS=SUCCESS_PROVISIONED` / `STATUS=FAILED_*`) is exercised without physical UART/Tera Term.
- Ran a full grounded claims-verification pass (re-executed every claim rather than trusting prior prose) and documented one real methodology defect found along the way: `cmd.exe /c "cmd & echo %ERRORLEVEL%"` chaining under this shell wrapper reports stale exit codes — use native language exit capture instead.
- Ran `ruff` for the first time this session (was a declared dev dependency but never executed) — found and fixed 4 real lint violations (unused imports, stale `noqa`, import ordering); re-verified tests still 13/13 green after the fix.
- Dependencies added: `jinja2>=3.1` (runtime), `pytest>=8.0` + `ruff>=0.6` (dev). No dependencies removed (greenfield project).

## 2. File & Artifact Manifest

| Action | File Path | Description of Changes |
| :--- | :--- | :--- |
| Created | `pyproject.toml` | Package metadata, `hatchling` build, `tt-agent-hw` console script, pytest config (`testpaths=tests`, `pythonpath=src`, `hardware` marker), ruff config |
| Created | `README.md` | Architecture overview, install steps, CLI usage/exit codes, test instructions, CI sketch |
| Created | `.env.example` | `TT_AGENT_RUNTIME_DIR`, `TT_AGENT_TT_BIN_DIR`, `TT_AGENT_HW` documented |
| Created | `.gitignore` | `.venv/`, caches, `.env`, smoke-test scratch dirs (`smoke_fw/`, `smoke_runtime*/`) |
| Created | `config/base_teraterm.ini` | Headless Tera Term defaults (HideTitle, AutoWinClose, FileSendHighSpeedMode, log rotation off) |
| Created | `templates/task_template.ttl.j2` | Canonical TTL macro source (repo-root copy for reference/editing) |
| Created | `src/tt_agent_hw/__init__.py` | Package marker, `__version__ = "0.1.0"` |
| Created | `src/tt_agent_hw/models.py` | `TargetJob` (frozen dataclass, 10 fields incl. `binary_path`), `ProvisionResult` (`is_success`, `is_timeout`, `to_dict`) |
| Created | `src/tt_agent_hw/status.py` | `STATUS=*` line contract: `normalize_status_line`, `is_terminal`, `is_success`, `read_status_file` (tolerates lock/missing), `write_status_file` |
| Created | `src/tt_agent_hw/workspace.py` | `RunWorkspace` dataclass, `new_run_id()` (`run_<8hex>`), `create_workspace()` (mkdir `logs/status/artifacts`), `ensure_runtime_writable()` (write-probe) |
| Created | `src/tt_agent_hw/paths.py` | Env-driven defaults: `TT_AGENT_RUNTIME_DIR` → `C:\agent_runtime`, `TT_AGENT_TT_BIN_DIR` → `C:\Program Files (x86)\teraterm`; `template_path()`/`base_ini_path()` (package-data-first, repo-fallback); `ttl_escape_path()` |
| Created | `src/tt_agent_hw/controller.py` | `TeraTermAgentController`: `preflight()`, `render_macro()`, `execute_provisioning()` (spawn → poll @0.5s → timeout-kill), `_macro_command()` (real `.exe` gets `/V`, `.py` fakes get `sys.executable`, `.cmd`/`.bat` via `cmd /c`); `PreflightError` |
| Created | `src/tt_agent_hw/cli.py` | `argparse`-based `doctor` and `provision` subcommands; exit codes 0/1/2/3 per design spec; `--json` output flag |
| Created | `src/tt_agent_hw/templates/task_template.ttl.j2` | Bundled copy of TTL template (package-data path resolved by `paths.template_path()`) |
| Created | `src/tt_agent_hw/config/base_teraterm.ini` | Bundled copy of base INI |
| Created | `tests/fixtures/fake_ttpmacro.py` | Drop-in fake macro engine: reads `StateFile`/`LogFile` out of rendered TTL, writes `STATUS=INITIALIZING` then a configurable terminal status (`FAKE_TT_STATUS`, `FAKE_TT_DELAY`, `FAKE_TT_HANG` env vars) |
| Created | `tests/test_status.py` | 3 tests: normalize/strip, terminal classification, read/write roundtrip |
| Created | `tests/test_workspace.py` | 3 tests: workspace layout, runtime-writable happy path, runtime-writable failure-on-file-not-dir |
| Created | `tests/test_controller_mock.py` | 5 tests: TTL render content, success path, failure path, missing-binary preflight, orchestrator-timeout-kills-hung-macro (local `FastTimeoutController` subclass with a 1s window) |
| Created | `tests/test_cli.py` | 2 tests: CLI provision success → exit 0, CLI provision failure → exit 1 |
| Created | `scripts/smoke_verify.py` | Manual end-to-end smoke: `doctor` + mock success + mock failure, asserts expected exit codes, prints `SMOKE_PASS` |
| Created | `docs/source/Autonomous Multi-Agent Hardware Provisioning & CI_CD Framework.txt` | Original spec, copied verbatim from Downloads |
| Created | `docs/source/Tera Term Deep Dive Guide.txt` | Original reference manual, copied verbatim from Downloads |
| Created | `docs/superpowers/specs/2026-09-01-tt-agent-hw-design.md` | Approved architectural design (brainstorming-skill output) — goals, non-goals, layout, controller algorithm, status contract, CLI, testing strategy, error model, decisions log |
| Created | `docs/superpowers/plans/2026-09-01-tt-agent-hw-v1.md` | Short implementation-plan record (build executed inline, not via subagent-driven-development) |
| Created | `docs/superpowers/reports/2026-09-01-claims-verification-report.md` | Reusable merged trajectory+claims verifier prompt (Part 1) + applied JSON verification report against this v1 build (Part 2) |
| Modified | `src/tt_agent_hw/controller.py` | Ruff auto-fix: blank line inserted after `from jinja2 import Template` for import-block grouping (`I001`) |
| Modified | `scripts/smoke_verify.py` | Ruff auto-fix: removed unused `import sys`, removed stale `# noqa: E402` |
| Modified | `tests/test_controller_mock.py` | Ruff auto-fix: removed unused `import os` |
| Not created (by design) | `.github/workflows/*.yml` | Explicit v1 non-goal — GHA pattern documented in `README.md` only, not checked in |

## 3. Architecture & Key Technical Decisions

- **Decision:** Repo is source-only; runtime workspace lives at a separate configurable path (`TT_AGENT_RUNTIME_DIR`, default `C:\agent_runtime`), not inside the git tree.
  - **Rationale:** Matches production CI-runner topology from the source spec; keeps generated `.ttl`/logs/binaries out of version control.
  - **Alternatives Considered:** Monorepo with `./runtime` skeleton; repo-root-as-`C:\agent_runtime`. Rejected — messier `.gitignore`, harder to reason about clean state between runs.
  - **Trade-offs:** Requires an env var or `--runtime-dir`/`--tt-bin-dir` CLI flag on every invocation in non-default environments (tests always pass these explicitly via `tmp_path`).

- **Decision:** File-based `STATUS=<TOKEN>` handshake (TTL writes, Python polls) instead of parsing `ttpmacro.exe` stdout/DDE directly.
  - **Rationale:** `ttpmacro.exe` does not return dynamic exit codes to the shell; this is the only deterministic signal channel documented in the source spec.
  - **Alternatives Considered:** None viable — DDE introspection from Python was out of scope for v1.
  - **Trade-offs:** Requires a 0.5s poll loop (default `poll_interval_sec`) and an orchestrator-side timeout (`boot_timeout + 60s`) independent of the macro engine's own timeout handling; a locked/mid-write status file is tolerated by treating `PermissionError`/`OSError` as "not ready yet," not failure.

- **Decision:** Fake-macro test seam via file extension dispatch in `_macro_command()` (`.py` → `sys.executable`, `.exe` → real `/V` flag).
  - **Rationale:** Lets `tests/fixtures/fake_ttpmacro.py` be injected as `macro_exe=` with zero controller-side test-mode branching.
  - **Alternatives Considered:** Mock `subprocess.Popen` directly. Rejected — would not exercise the real render→spawn→poll→status-file round trip, which is the actual risk surface.
  - **Trade-offs:** `sys.executable` must be resolvable (it is, inside the project's own venv); no `py` launcher dependency (this environment's `py`/`python`/`python3` PATH aliases were all broken — see §6).

- **Decision:** v1 explicitly excludes self-heal matrix, multi-COM fan-out, SSH jobs, checked-in CI workflow, shipped Tera Term binaries.
  - **Rationale:** Per approved design spec — prove the single-target status contract before expanding surface area.
  - **Alternatives Considered:** Full spec in one pass (rejected, too much unverified surface); mock-only library with no CLI (rejected, doesn't prove operator UX).
  - **Trade-offs:** Zombie `ttpmacro.exe`/USB re-enumeration/relay power-cycle recovery is undocumented-but-planned (§7 P1).

## 4. Current State & Verification

- **Verified Working (this session, re-executed, not read from prior logs):**
  ```
  .venv\Scripts\pytest.exe -q
  13 passed in 2.97s
  ```
  - `tests/test_status.py` (3), `tests/test_workspace.py` (3), `tests/test_controller_mock.py` (5), `tests/test_cli.py` (2)
  ```
  .venv\Scripts\ruff.exe check .
  All checks passed!
  ```
  - `tt-agent-hw doctor` (via `scripts/smoke_verify.py`, native Python exit capture) → exit `2`, correctly flags missing `C:\Program Files (x86)\teraterm\ttpmacro.exe` / `ttermpro.exe` in this environment
  - `tt-agent-hw provision` mock success path → exit `0`, `STATUS=SUCCESS_PROVISIONED`
  - `tt-agent-hw provision` mock failure path → exit `1`, `STATUS=FAILED_FLASH_ERASE`
  - `git status --porcelain` → clean working tree at `cae9620` (only gitignored caches/venv present)
  - `grep -i GZMO` across repo → 3 matches, all in this project's own design-doc non-goal prose, zero code coupling

- **Unfinished / Work in Progress:**
  - **Real hardware run never performed** — no physical UART target or Tera Term install available in this environment. `doctor` intentionally fails on that check; this is expected, not a defect.
  - **Phase 4 self-healing matrix** (taskkill zombie `ttermpro.exe`, USB re-enumeration wait, relay power-cycle, YMODEM→XMODEM-CRC fallback) — documented as follow-up in the design spec, not implemented.
  - **`/F=run.ini` merge of `config/base_teraterm.ini` per run** — INI is shipped but the connect string currently uses CLI flags only (`/C=`, `/BAUD=`, `/L=`, `/H`, `/AUTOWINCLOSE=on`); INI is reference/operator documentation, not yet wired into `render_macro()`.
  - **Checked-in GitHub Actions workflow** — pattern documented in `README.md` only; no `.github/workflows/*.yml` exists (explicit v1 non-goal).
  - **SSH/Telnet target job type** — `TargetJob` models UART-only; no SSH variant exists.

## 5. Environment & Configuration State

```bash
# Effective in this session (no .env file was created; these are documented defaults)
TT_AGENT_RUNTIME_DIR=C:\agent_runtime         # not overridden; doctor probed this default and it is writable
TT_AGENT_TT_BIN_DIR=C:\Program Files (x86)\teraterm   # not overridden; binaries absent in this environment
# TT_AGENT_HW=1                                # unset — @pytest.mark.hardware tests do not exist yet in v1, no-op today
```

- **Interpreter:** Python 3.12.10, installed this session at `C:\Users\z005a5ff\AppData\Local\Programs\Python\Python312\python.exe` (user-local, silent install; prior `py`/`python`/`python3` PATH entries were broken/absent — see §6).
- **Virtualenv:** `.venv\` at repo root (gitignored), created from the interpreter above.
- **Installed (editable):** `pip install -e ".[dev]"` → `tt-agent-hw==0.1.0`, `jinja2`, `pytest`, `ruff`, transitive deps (`MarkupSafe`, `colorama`, `iniconfig`, `packaging`, `pluggy`, `pygments`).
- **No daemons, containers, or network ports** — this is a CLI/library project with no long-running services.
- **No schema/migrations** — no database in v1.

## 6. Known Issues, Blockers & Edge Cases

- **Shell exit-code capture bug (environment, not product):** `cmd.exe /c "cmd1 & echo EXITCODE=%ERRORLEVEL%"` under this bash-wrapped shell reported `EXITCODE=0` once even though the real return code was `2`. Root-caused during the claims-verification pass; **do not trust chained-`&` `%ERRORLEVEL%` echoes in this environment** — always capture exit codes via `sys.exit()`/`subprocess.run(...).returncode` in a native script (see `scripts/smoke_verify.py` for the pattern).
- **No `py` launcher / broken `python` PATH aliases at session start:** `py`, `python`, `python3` all failed; the `WindowsApps\python.exe` symlink pointed at an inaccessible WindowsApps package path. Resolved by downloading `python-3.12.10-amd64.exe` from python.org and silent-installing user-locally. Any future session on this same machine should first confirm `C:\Users\z005a5ff\AppData\Local\Programs\Python\Python312\python.exe` still exists before re-downloading.
- **`ruff` was an unexercised dev dependency until this session's final verification pass** — always run `ruff check .` as part of any "verify the project" request; it is not implied by a green `pytest` run.
- **No real hardware/hardware-marked tests exist yet** — `TT_AGENT_HW` env var and the `hardware` pytest marker are wired in `pyproject.toml` but no test currently uses `@pytest.mark.hardware`; adding real hardware tests is future work, not a currently-skipped/broken suite.
- **CRLF warnings on every git operation** (`LF will be replaced by CRLF`) — cosmetic, expected on Windows without a `.gitattributes`; not a functional issue, but worth adding a `.gitattributes` (`* text=auto`) if diff noise becomes a problem.

## 7. Immediate Next Steps (Prioritized Backlog)

1. **[P0] Immediate Resume Task:** Install Tera Term on this machine (or point `TT_AGENT_TT_BIN_DIR` at an existing install), then run `tt-agent-hw doctor` to confirm both binaries resolve — this is the single blocker preventing any real-hardware verification.
2. **[P1] Follow-up Implementation:** Wire a real UART target: connect a board with a YMODEM-capable bootloader (e.g. U-Boot), run `tt-agent-hw provision --com <N> --binary <firmware.bin> --boot-prompt "U-Boot>" ...` (see `README.md` for the full flag example), and confirm the real TTL macro (not the fake) produces `STATUS=SUCCESS_PROVISIONED`.
3. **[P1] Follow-up Implementation:** Implement Phase 4 self-heal behaviors documented in `docs/superpowers/specs/2026-09-01-tt-agent-hw-design.md` §Follow-ups — start with zombie-process detection (`FAILED_CONNECTION_REFUSED` → `taskkill /F /IM ttermpro.exe` → retry).
4. **[P2] Polish & Edge-Case Handling:** Wire `config/base_teraterm.ini` into `render_macro()` via `/F=` so operator-tunable settings (log rotation, buffer size) actually take effect per run, not just as reference documentation.
5. **[P2] Polish & Edge-Case Handling:** Add a `.gitattributes` (`* text=auto`) to silence the recurring CRLF warnings on every `git add`/`commit` in this environment.
