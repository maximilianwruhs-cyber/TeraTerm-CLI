# Self-discovering serial probe + agentic CLI — 2026-09-01

## Intent

Extend **tt-agent-hw** so an agent (or human) can attach to an unknown UART target, **find a working link**, **harvest usable commands**, persist them **per COM port**, and **invoke those commands later via CLI** — without assuming U-Boot, a fixed baud, or a flash workflow.

This complements v1 `provision` (fixed flash+verify macro). It does **not** replace it.

Related prior design: `2026-09-01-tt-agent-hw-design.md`.

## Problem

v1 CLI is a provisioning gun:

- `doctor` — binaries/runtime only  
- `provision` — requires COM, baud, binary, boot prompt, erase, YMODEM, boot regex  

Real lab/agent behavior is:

1. Find the port and baud  
2. Type `help` / poke the machine  
3. Learn what commands exist  
4. Use those commands deliberately  
5. Only later run a structured job (e.g. provision) if appropriate  

Without discovery, agents invent protocol strings and misread `FAILED_BOOT_PROMPT_TIMEOUT` as a tool failure.

## Goals

1. **Self-discovering probe** — sweep baud (and minimal framing assumptions), nudge the device, detect RX.  
2. **Command harvest** — from successful nudges + heuristic parse of help-like text.  
3. **Per-COM profile** — durable JSON under the runtime dir, keyed by COM port.  
4. **Agentic CLI** — `ports`, `discover`, `profile show`, `cmds`, `call` with stable exit codes and `--json`.  
5. **Hermetic logs** — each discover/call leaves a workspace trail (reuse runtime layout).  
6. **Tests without hardware** — fake serial port / mock transport seam.

## Non-goals (this slice)

- LLM-based help parsing or command synthesis  
- Auto-flash / YMODEM / replacing `provision`  
- Full interactive TUI (optional later; not required for agentic `call`)  
- Multi-COM parallel discover  
- Hunting 7E1/odd parity as a first-class matrix (default **8N1** only)  
- Binding profiles to USB serial numbers as the primary key (store as hint only)  
- Self-heal matrix (zombie ttermpro kill, USB re-enum) — still post-v1 for provision  
- GZMO coupling  

## Decisions (locked)

| Topic | Choice |
|-------|--------|
| Profile binding | **Per-COM** — `profiles/COM7.json` |
| Baud | **Searched by default**; `--baud` pins; `--baud-list` overrides sweep |
| Explore vs provision engine | **pyserial** for discover/call/ports; **ttpmacro** remains for `provision` |
| Help parsing | **Heuristic only** (no LLM in v1 of this feature) |
| Interactive console | **Deferred** — agentic `call` covers line send/expect; live REPL can follow |
| Default nudges | break (optional), `CR`, `help`, `?`, `AT` |
| Early stop | Stop baud sweep on strong score unless `--no-early-stop` |

## Architecture

```text
CLI
  ports          -> PortEnumerator (PnP / SERIALCOMM)
  discover       -> DiscoverController
                      -> BaudSweeper + NudgeLadder + HelpHarvester + CommandExtractor
                      -> ProfileStore.write(COMn)
                      -> RunWorkspace logs
  profile show   -> ProfileStore.read(COMn)
  cmds           -> ProfileStore.read(COMn).commands
  call           -> ProfileStore.read(COMn) + SerialSession.send_expect
  provision      -> (unchanged) TeraTermAgentController + TTL
```

### Transport seam

Introduce a small `SerialTransport` protocol (open/close/write/read/bytes_waiting) so:

- production uses **pyserial**  
- tests inject a **FakeSerialTransport** (scripted RX per baud / per write)

Do **not** drive discover/call through `ttpmacro.exe` (baud reopen + structured capture is awkward in TTL).

### Dependency

Add runtime dependency: `pyserial>=3.5` (or project-equivalent minimum).

## Runtime layout

```text
%TT_AGENT_RUNTIME_DIR%/
  profiles/
    COM7.json
    COM7.prev.json          # one-slot backup on successful re-discover
  workspaces/
    run_<8hex>/
      logs/console.log      # transcript
      status/execution.state
      artifacts/
        help_raw.txt
        discover_scores.json
```

Env defaults remain:

| Variable | Role |
|----------|------|
| `TT_AGENT_RUNTIME_DIR` | Runtime root (profiles + workspaces) |
| `TT_AGENT_TT_BIN_DIR` | Still required for `doctor` / `provision` only |
| `TT_AGENT_HW` | Hardware pytest marker (discover hardware tests optional later) |

`.env` is **documentation**; CLI continues to read process env / flags unless a later change adds explicit dotenv load (out of scope unless cheap and consistent).

## Profile schema (`profiles/COM{N}.json`)

```json
{
  "schema_version": 1,
  "com": 7,
  "port_name": "COM7",
  "baud": 9600,
  "framing": { "bytesize": 8, "parity": "N", "stopbits": 1 },
  "usb_hint": {
    "friendly_name": "USB Serial Port (COM7)",
    "instance_id": "FTDIBUS\\VID_0403+PID_6001+...",
    "serial_number": "BG00Z13Q"
  },
  "fingerprint": {
    "banner": "<first printable chunk if any>",
    "help_raw_path": "artifacts/help_raw.txt",
    "help_raw_sha256": "<hex or empty>"
  },
  "commands": [
    {
      "id": "help",
      "send": "help",
      "summary": "nudge: help",
      "source": "nudge"
    },
    {
      "id": "version",
      "send": "version",
      "summary": "optional parsed summary",
      "source": "parsed_help"
    }
  ],
  "nudges_tried": ["cr", "help", "?", "AT"],
  "baud_tried": [
    { "baud": 115200, "bytes_rx": 0, "score": 0.0 },
    { "baud": 9600, "bytes_rx": 120, "score": 0.82 }
  ],
  "confidence": 0.82,
  "discovered_at": "2026-09-01T12:00:00Z",
  "run_id": "run_ab12cd34",
  "tool_version": "0.2.0"
}
```

### Invariants

- `id` is unique within a profile; slug from `send` (`[^a-zA-Z0-9]+` → `_`, lowercased, trimmed).  
- Collision: suffix `_2`, `_3`, …  
- `commands` always includes every nudge that produced RX at the winning baud (source `nudge`).  
- Parsed entries source `parsed_help`.  
- Re-discover success: rename existing → `COM{N}.prev.json`, write new `COM{N}.json`.  

## Discover pipeline

### CLI

```text
tt-agent-hw discover [--com N] [--baud B] [--baud-list a,b,c]
                     [--no-early-stop] [--no-break]
                     [--timeout-per-baud S] [--json]
                     [--runtime-dir DIR]
```

### Port resolution

1. Enumerate serial ports (exclude obvious Bluetooth COM if filterable; still list them in `ports`).  
2. If `--com` given → use it.  
3. If omitted and **exactly one** non-Bluetooth USB-serial candidate → use it.  
4. Else exit `2` with message to run `ports` and pass `--com`.

### Baud resolution

- `--baud B` → single-rate list `[B]`  
- else `--baud-list` if provided  
- else default: `115200,57600,38400,19200,9600,4800` (fast → slow)

Framing fixed **8N1** for this slice.

### Per-baud probe

For each baud:

1. Open port (exclusive).  
2. Optional break (`--no-break` disables).  
3. Flush input.  
4. Nudge ladder (line discipline: payload + `\r` unless empty CR-only step):  
   - empty CR  
   - `help`  
   - `?`  
   - `AT`  
5. After each nudge: read until **quiet window** (e.g. 200–300 ms no RX) or per-nudge cap.  
6. Score aggregate RX for this baud (see Scoring).  
7. Early-stop if score ≥ strong threshold and bytes ≥ minimum (unless `--no-early-stop`).  
8. Close before next baud.

### Scoring (deterministic)

Inputs: raw RX bytes for the baud.

| Signal | Contribution |
|--------|----------------|
| byte count | log-scaled, capped |
| printable ratio (tab/CR/LF allowed) | weight up if ≥ ~0.7 |
| line breaks present | small bonus |
| keyword hits (`help`, `command`, `commands`, `usage`, `ok`, `error`, `menu`, `available`) case-insensitive | bonus |
| prompt-ish line endings (`>`, `#`, `$`, `:`) | small bonus |
| high binary/noise ratio | penalty |

Emit `discover_scores.json` in the run artifacts for debug.

**Winner** = highest score among bauds with score > silence floor.  
If none → status `FAILED_PROBE_SILENT`, exit `1`, **do not** overwrite profile.

### Help harvest (winning baud only)

1. Re-open at winning baud.  
2. Re-send the best help-like nudge that got RX (`help` preferred, else `?`, else first productive nudge).  
3. Capture until quiet window or cap → `artifacts/help_raw.txt`.  
4. Run `CommandExtractor` on text.

### Command extraction (heuristic v1)

Always:

- Add productive nudges as commands.

Parse `help_raw` lines (strip ANSI if trivial; ignore empty):

| Pattern family | Example | `send` |
|----------------|---------|--------|
| `cmd - description` | `reset - reboot board` | `reset` |
| `cmd: description` | `status: show status` | `status` |
| `cmd — description` | em-dash variants | `cmd` |
| bare token column (careful) | lines of single words in help blocks | token if `[A-Za-z][A-Za-z0-9_]*` and length 2–32 |
| `AT+...` | `AT+GMR` | full token |
| U-Boot-ish | leading word before spaces on non-indented lines under a Commands header if present | first word |

Reject obvious junk: pure numbers, single letters except `?`, paths, `----` rules.

v1 quality bar: **useful on common help formats; never crash; prefer fewer false commands over many**.

### Status tokens (discover)

| Token | Meaning |
|-------|---------|
| `STATUS=INITIALIZING` | start |
| `STATUS=SUCCESS_DISCOVERED` | profile written, link found |
| `STATUS=FAILED_PROBE_SILENT` | port opened, no baud produced RX |
| `STATUS=FAILED_CONNECTION_REFUSED` | cannot open COM |
| `STATUS=FAILED_NO_PORT` | could not resolve COM |
| `STATUS=TIMEOUT_ORCHESTRATOR` | unexpected hang watchdog |

### Exit codes (discover)

| Code | Meaning |
|------|---------|
| 0 | `SUCCESS_DISCOVERED` |
| 1 | silent / no usable link (`FAILED_PROBE_SILENT`) |
| 2 | preflight / no port / cannot open |
| 3 | orchestrator / unexpected |

## Agentic CLI

### `ports`

```text
tt-agent-hw ports [--json]
```

List present serial ports: name, description/friendly name, and whether `profiles/COMn.json` exists.

Exit `0` always if enumeration works; `2` on enumeration failure.

### `profile show`

```text
tt-agent-hw profile show --com N [--json]
```

Print profile or error if missing (exit `2`).

### `cmds`

```text
tt-agent-hw cmds --com N [--json]
```

List `id`, `send`, `summary`, `source`. Missing profile → exit `2` with “run discover”.

### `call`

```text
tt-agent-hw call --com N <command_id>
tt-agent-hw call --com N --send "raw line" [--expect REGEX] [--timeout S] [--json]
```

Behavior:

1. Load `profiles/COM{N}.json` (**required**). Missing profile → exit `2` with hint to run `discover`. No baud-only break-glass path in this slice.
2. Resolve TX payload: positional `<command_id>` → profile command `send`; or `--send "raw line"` for an ad-hoc line (still uses profile link settings). Exactly one of id or `--send` required.
3. Open serial at profile baud/framing.
4. Write payload + `\r` (no double-CR if payload already ends with CR).
5. Read until quiet window or `--timeout` (default e.g. 3s).
6. Print RX (human) or JSON `{tx, rx, matched, profile_baud, run_id, log_file}`.
7. If `--expect` given: exit `0` on match else `1`.
8. If no `--expect`: exit `0` if port I/O succeeded (RX may be empty).

Status file optional for call (workspace still created for log). Prefer always logging.

### `doctor` extension (light)

Keep existing binary checks. Optionally add:

- `pyserial` importable  
- not required to open a COM unless `--com` passed  

Do not fail doctor solely because no adapter is plugged in.

## Relationship to `provision`

| Stage | Tool |
|-------|------|
| Unknown device | `discover` → `cmds` / `call` |
| Confirmed U-Boot (or known recipe) | `provision` with explicit flags / future profiles |

Future (out of scope now): `provision --from-profile COM7` if fingerprint looks like U-Boot — **not** in this slice.

## Package / module layout (suggested)

```text
src/tt_agent_hw/
  cli.py                 # wire new subcommands
  models.py              # Profile, DiscoveredCommand, DiscoverResult, CallResult
  ports.py               # enumeration
  profile_store.py       # read/write/backup per-COM
  serial_transport.py    # protocol + pyserial impl
  discover.py            # sweep, score, harvest, extract
  call.py                # send/expect session
  ... existing provision stack unchanged
```

Bump package version to **0.2.0** when shipping this feature.

## Testing strategy

| Test | Hardware | Asserts |
|------|----------|---------|
| port enum parsing | no | friendly fixtures / mocked enumerator |
| scoring | no | silent vs help-like samples |
| command extractor | no | fixture help texts → expected ids |
| profile store | no | write/read/backup under tmp runtime |
| discover controller | no | FakeSerialTransport scripted multi-baud |
| call | no | fake transport expect match/mismatch |
| CLI smoke | no | argparse + mocked controller |
| `@pytest.mark.hardware` | optional | real COM7 path when `TT_AGENT_HW=1` |

## Error handling

- Port busy → `FAILED_CONNECTION_REFUSED`, exit `2`, leave profile untouched.  
- Partial discover crash → no profile replace; workspace retained.  
- Empty help parse → profile still success if link had RX; commands may be nudge-only.  
- `call` with unknown id → exit `2`, list cmds hint.  

## Success criteria

1. On a silent adapter (no DUT): `discover` opens COM, sweeps, exits `1`, no profile clobber.  
2. On a DUT that answers `help` at non-115200 baud: `discover` selects baud, writes `profiles/COMn.json`, `cmds` lists entries, `call help` returns RX.  
3. Mock tests cover silent / discovered / call expect without hardware.  
4. `provision` path unchanged and still green.  
5. README documents agent loop: `ports` → `discover` → `cmds` → `call`.  

## Agent loop (canonical)

```text
tt-agent-hw ports --json
tt-agent-hw discover --com 7 --json
tt-agent-hw cmds --com 7 --json
tt-agent-hw call --com 7 help --json
tt-agent-hw call --com 7 <id> --expect "..." --json
```

## Follow-ups (explicitly later)

1. Live `--interactive` console after discover  
2. USB serial-number-stable profile aliases  
3. Parity/databits hunt  
4. LLM-assisted command graph  
5. `provision --from-profile`  
6. dotenv auto-load  
7. Nudge profiles per device family (`--family at|uboot|raw`)  

## Open points (resolved for v1 of this feature)

| Point | Resolution |
|-------|------------|
| Profile key | COM port |
| Engine | pyserial for discover/call |
| Interactive | deferred; `call` is the agentic primitive |
| Parser | heuristic only |

## Decisions log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Feature shape | discover + per-COM profile + cmds/call | Matches “self-discover then use agentically” |
| Baud | sweep by default | Baud differs every time |
| Binding | per-COM file | Multiple adapters; user choice |
| No LLM | heuristics | Deterministic CI, offline, testable |
| Split from TT macro | pyserial for explore path | Baud sweep + capture ergonomics |
