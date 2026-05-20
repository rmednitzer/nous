# nous

[![CI](https://github.com/rmednitzer/nous/actions/workflows/ci.yml/badge.svg)](https://github.com/rmednitzer/nous/actions/workflows/ci.yml)
[![Docs](https://github.com/rmednitzer/nous/actions/workflows/docs.yml/badge.svg)](https://github.com/rmednitzer/nous/actions/workflows/docs.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

## What this is

`nous` is a simulator for a man-portable AI inference appliance, the kind of
device you might wear as a backpack to support a single operator working in
disconnected or contested environments. The simulated appliance pairs a
Jetson-class compute module with battery, solar/fuel-cell auxiliary power, a
thermal envelope, environmental and biometric sensors, multi-mode radios, and
a local-plus-cloud inference path. The simulator runs the device end-to-end
as a tick-driven asynchronous system that exposes itself to a controller (a
Claude session or any MCP client) through the Model Context Protocol.

The point of the simulator is to make the *behaviour* of a backpack inference
unit legible: which capabilities are intact right now, which have degraded,
how long the device can sustain a given workload, and what an estimator can
honestly say about the operator and the environment. To that end every
subsystem has a parametric physics model, a sensor model that emits noisy
observations, and a recursive estimator (Kalman, EKF, UKF, or particle filter
as appropriate) that turns those observations back into a calibrated belief
state. A self-model layer aggregates those beliefs into capability claims the
controller can reason about.

The codebase is meant to be small, hand-written, and easy to inspect. It is
not a wrapper around a commercial sim; it is a deliberate, opinionated
reimplementation of just enough physics, control, and standards-interop to
support useful conversations with a controller. Every numeric curve lives in
a hardware profile YAML so the same engine can be retargeted to a new device
(Jetson AGX Orin 64GB is the reference profile). NATO and open-standard
adapters (CoT/TAK, SensorThings, MISB KLV, NMEA 0183, STANAG 4774, MQTT)
provide the seams for plugging the simulated unit into mission stacks.

## Status

Pre-1.0. The v0.1 scaffold establishes the layout, the audited MCP tool
surface, the state machine, the engine tick loop, the hardware-profile
loader, the policy/audit/runner spine, and placeholders for subsystems,
estimators, the self-model, and interop adapters. Physics, estimators, and
the self-model land in subsequent phases. See [STATUS.md](STATUS.md) for the
phase table, [LIMITATIONS.md](LIMITATIONS.md) for the explicit gaps, and
[docs/backlog.md](docs/backlog.md) for the line-item tracker.

## Layout

```
src/nous/        engine, server, policy/audit/runner, subsystems, estimators,
                 self-model, interop adapters, OAuth issuer, scenarios loader
profiles/        hardware profile YAML (jetson-agx-orin reference, others)
scenarios/       scripted scenario YAML for replayable runs
skills/          short markdown runbooks for the controller
docs/            architecture, ADRs, STPA artefacts, conformance posture,
                 model cards, hardware-profile reference, deployment guide
deploy/          systemd units, Caddy template, cloud-init, install script
alembic/         database migrations (SQLite + WAL by default)
tests/           unit, integration, and stdio end-to-end tests
scripts/         autogen helpers for tool reference, ADR index, backlog
examples/        a self-driving demo, an inspector quickstart
```

## Capabilities

- Tick-loop physics simulation of a backpack inference appliance, with
  subsystem models for compute, power, auxiliary power (battery, solar, fuel
  cell), thermal, storage, sensors, position, biometrics, comms, and
  inference, all driven by a single hardware-profile YAML.
- Hand-rolled finite-state machine over the mission posture (stowed, boot,
  idle, mission, relay, monitoring, C2, degraded, thermal-limited, low-power,
  safe, shutdown, fault) with explicit transitions.
- Recursive estimators per subsystem (Kalman / EKF / UKF / particle filter as
  appropriate) feeding a self-model capability layer that produces calibrated
  endurance, thermal-headroom, inference-capacity, and link-budget claims.
- A FastMCP tool surface exposed over stdio or HTTP with OAuth 2.1, with
  every tool call classified into a tier (read-only, reversible, stateful,
  irreversible) and gated by policy mode.
- An append-only JSONL audit trail (output hashed, never stored verbatim)
  and a Claude/Anthropic client with a hard daily call cap and explicit
  prompt-cache discipline.
- Interop adapters for the standards a mission stack expects: CoT/TAK, OGC
  SensorThings, MISB KLV, NMEA 0183, STANAG 4774/4778, and MQTT.
- A VM deployment bundle (Ubuntu 26.04 LTS + systemd + Caddy + logrotate;
  also works on 24.04) and an `examples/self_driving_demo.py` for running
  the simulator with a Claude session as the controller.

## Install

`nous` builds with `uv` and Python 3.12+ (the deployment baseline is
3.14 on Ubuntu 26.04 LTS; 3.12 and 3.13 are still supported).

```sh
git clone https://github.com/rmednitzer/nous
cd nous
uv sync --all-extras
```

Once installed, `nous --help` lists the CLI subcommands (`serve`, `tick`,
`scenario`).

## Build and test

```sh
make install     # uv sync --all-extras
make check       # ruff + mypy strict + pytest
make docs-build  # mkdocs build --strict
```

## Run it

```sh
uv run nous serve              # MCP server on stdio (default)
NOUS_TRANSPORT=http uv run nous serve   # HTTP transport with OAuth
uv run nous scenario scenarios/env-monitoring-urban.yaml
```

`examples/self_driving_demo.py` wires Claude to the stdio transport for a
short end-to-end demo. Pair it with the runbooks in `skills/` for a guided
tour.

## Cross-references

- [STATUS.md](STATUS.md) -- maturity by phase and per-document state
- [LIMITATIONS.md](LIMITATIONS.md) -- explicit boundaries (no mesh/DTN, single
  operator, simulator only, etc.)
- [docs/backlog.md](docs/backlog.md) -- BL-NNN line-item tracker
- [docs/adr/](docs/adr/) -- numbered architecture decision records
- [docs/stpa/](docs/stpa/) -- STPA-Pro safety analysis artefacts
- [AGENTS.md](AGENTS.md) -- conventions for AI-assisted contributors
- [CONTRIBUTING.md](CONTRIBUTING.md) -- how to land changes
- [SECURITY.md](SECURITY.md) -- reporting and hardening posture

## Live deployment

The reference instance at <https://nous.blackphoenix.org/>
tracks `main` automatically. Every merged PR is live on the
VM within five minutes. See `docs/deployment.md`.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Source files are
SPDX-tagged where appropriate; `REUSE.toml` declares the project-wide
license posture for REUSE 3.x compliance.
