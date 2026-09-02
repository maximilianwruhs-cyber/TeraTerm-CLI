# tt-agent-hw

Autonomous **single-target** hardware flash + boot verify driven by [Tera Term](https://teratermproject.github.io/) (`ttpmacro.exe` / `ttermpro.exe`).

An orchestrator renders a hermetic TTL macro, spawns the macro engine headlessly, and reads a file-based `STATUS=*` handshake — no GUI clicks.

Design: [`docs/superpowers/specs/2026-09-01-tt-agent-hw-design.md`](docs/superpowers/specs/2026-09-01-tt-agent-hw-design.md)  
Source specs: [`docs/source/`](docs/source/)

## Requirements

- Windows
- Python 3.12+
- Tera Term 4.x/5.x installed (for real hardware runs)
- UART target with bootloader supporting YMODEM (e.g. U-Boot `loady`)

## Install

```bat
cd C:\Users\z005a5ff\Projects\tt-agent-hw
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

Optional environment (see `.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `TT_AGENT_RUNTIME_DIR` | `C:\agent_runtime` | Hermetic workspaces root |
| `TT_AGENT_TT_BIN_DIR` | `C:\Program Files (x86)\teraterm` | Tera Term binaries |
| `TT_AGENT_HW` | unset | Set `1` to enable `@pytest.mark.hardware` |

## CLI

```bat
tt-agent-hw doctor

tt-agent-hw provision ^
  --com 4 --baud 115200 ^
  --binary build\firmware.bin ^
  --boot-prompt "U-Boot>" ^
  --erase-command "sf probe 0; sf erase 0x0 0x100000" ^
  --erase-ack "Erased: OK" ^
  --transfer-trigger "loady 0x80000000 115200" ^
  --boot-command "bootm 0x80000000" ^
  --boot-success-regex "System Ready" ^
  --boot-timeout 30
```

## Discover + call (unknown UART)

```bat
tt-agent-hw ports --json
tt-agent-hw discover --com 7 --json
tt-agent-hw cmds --com 7 --json
tt-agent-hw call --com 7 help --json
```


### Exit codes

| Code | Meaning |
|------|---------|
| 0 | `SUCCESS` in status |
| 1 | TTL reported `FAILED_*` |
| 2 | Preflight / config |
| 3 | Orchestrator timeout or unexpected failure |

## Architecture (v1)

```
CLI / agent
    -> TeraTermAgentController
        -> Jinja2 task_template.ttl.j2
        -> workspaces/run_<id>/{task.ttl, logs/, status/}
        -> ttpmacro.exe /V task.ttl
        -> poll status/execution.state
```

Runtime layout (not in git):

```
C:\agent_runtime\workspaces\run_<id>\
  task.ttl
  logs\console.log
  status\execution.state
  artifacts\
```

## Tests (no hardware)

```bat
pytest -q
```

Uses `tests/fixtures/fake_ttpmacro.py` as a drop-in macro engine.

## CI sketch (self-hosted Windows runner)

Not checked in for v1. Pattern from the framework spec:

```yaml
runs-on: [self-hosted, windows, hw-bench-com4]
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with: { python-version: "3.12" }
  - run: pip install -e .
  - run: tt-agent-hw provision --com 4 --binary build/firmware.bin ...
```

## Non-goals (v1)

Self-heal matrix, multi-COM fan-out, SSH jobs, shipping Tera Term binaries.

## License

MIT
