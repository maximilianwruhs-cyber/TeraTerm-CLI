# tt-agent-hw v1 Implementation Plan

> Executed inline in the founding session (autonomous build).

**Goal:** Ship a installable Python 3.12 package that provisions one UART target via Tera Term with mock-tested STATUS handshake.

**Architecture:** `TeraTermAgentController` renders Jinja2 TTL, spawns macro engine, polls `execution.state`.

**Tech Stack:** Python 3.12, Jinja2, pytest, Tera Term external binaries.

**Spec:** `docs/superpowers/specs/2026-09-01-tt-agent-hw-design.md`

## Global Constraints

- Windows-first; no GZMO coupling
- Runtime dir separate from repo
- Mock tests must pass without hardware

## Tasks (completed in founding commit series)

1. Scaffold pyproject, package layout, template, base ini, README
2. Implement models, status, workspace, paths, controller, CLI
3. Fake ttpmacro + unit/integration mock tests
4. venv install + pytest + doctor/provision smoke
