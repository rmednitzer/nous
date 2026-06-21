# nous

Simulation-based digital twin of an edge-AI inference appliance: the
man-portable, backpack-class kind of device that supports a single operator
in a disconnected or contested environment. `nous` runs the appliance's
physics in software, turns its noisy readings into calibrated beliefs, and
exposes the whole picture to an LLM controller over the Model Context
Protocol (MCP). The point is legibility: the controller can always see which
capabilities are intact right now, which have degraded, how long the device
can sustain a given workload, and how much an estimator can honestly say.

It is a model, not a hardware-linked twin. Every output that looks like
operational telemetry is simulated, and no number here has been compared
against measured traces from real hardware. That honesty is a design goal,
not a disclaimer: the showcase carries per-number fidelity badges, the
estimators report calibrated uncertainty rather than false precision, and the
safety analysis is published alongside the code.

This tree is the source for the MkDocs site at
<https://rmednitzer.github.io/nous/>; the top-level navigation lives in
`mkdocs.yml`.

## What it models

The device is an inference appliance: compute and storage drawing on a
battery, kept inside a thermal envelope, fed by an auxiliary power source
(solar, a methanol fuel cell, a vehicle tether, USB-C), carrying radios,
environmental and electro-optical sensors, a position fix, and a read on the
operator's own state. A dozen subsystems model that physics tick by tick,
each from a parametric [hardware profile](hardware-profiles.md) anchored to a
[bill of materials](bom.md), so the same engine can stand in for a different
box by swapping a YAML file rather than code.

The operating context is the hard part. Links degrade, go silent under
emission control, or drop entirely; the operator can become impaired; the
environment obscures a sensor. The twin is built to stay legible through all
of that, which is why the comms stack carries a store-and-forward outbox, a
delay-tolerant mesh, and EMCON postures, and why the self-model speaks in
uncertainty bands instead of bare point values.

## How it works

A tick-driven [engine](architecture.md) orchestrates four layers. The
**subsystems** advance the physics and emit noisy observations. The
**estimators** fold those observations into calibrated belief states through
the simplest recursive filter (scalar Kalman, a particle filter for the
discrete comms link, an error-state EKF for position) that meets each model
card's covariance bound. The **self-model** aggregates the beliefs into
capability claims with Monte Carlo quantiles, so a claim carries a `p5` /
`p50` / `p95` band rather than a single number. The **state machine** governs
the mission posture and auto-safes the device when a safety constraint is
violated mid-run.

```
profile -> Subsystem.step(dt) -> Subsystem.sensor_obs() -> Estimator.update()
        -> Estimator.predict(dt) -> SelfModel.assess() -> Capability claims
```

A [FastMCP server](architecture.md) sits on top, and every tool call runs
through an audited runner that classifies it by authority tier, admits or
refuses it, and writes an append-only audit record whose output body is
SHA-256 hashed, never stored.

## What a controller can do

A controller drives the device through the
[MCP tool surface](tool-reference.md), more than fifty tier-classified tools:
a read tool for every subsystem, an estimator summary, the fused
`self_model_situation` read, and the mutating controls for scenarios, comms,
posture, and cloud inference. The headline reads are the four self-model
capabilities, each with an honest uncertainty band: endurance (how long the
battery lasts under the current net load), thermal headroom, inference
capacity in tokens per second, and EO/IR perception range.

Beyond the live reads, the controller can run [scenarios](scenarios/README.md)
end to end, publish the device's state to a coalition over the
[interop adapters](conformance/cot-tak.md) (Cursor-on-Target / TAK, OGC
SensorThings, MISB KLV, NMEA 0183, STANAG 4774/4778, MQTT), and step the
simulated clock deterministically for a repeatable run.

## Safety and governance

Safety is analysed with [STPA](stpa/README.md): losses, hazards, system
constraints, and the unsafe control actions that would breach them, each
traced to an enforced requirement and a test. At runtime a safety enforcer
gates every operational-mode entry on thermal headroom and power reserve, and
the tick loop auto-safes the device when either is violated while running.

Authority is tiered. Read tools are T0; reversible controls are T1; stateful
mutations are T2; the terminal fault and shutdown actions are T3. The audit
trail is tamper-evident: a per-record hash chain plus a daily anchor make a
mutation, deletion, or reordering detectable within the retention window. The
self-model never overstates what it knows, and the [showcase](showcase/README.md)
labels every figure with a fidelity badge so a reader can tell a calibrated
filter from a stub at a glance.

## What it is not

- Not a real device. Telemetry-shaped outputs (CoT, MQTT, MISB KLV) are
  simulated.
- Not a learned self-model. The self-model is parametric and reviewable, not
  trained.
- Not a multi-operator system. The current simulation is single-operator.
- Not a real radio network. The comms links and the DTN mesh run over
  abstract peer nodes, not physical radios.

The full scope boundary is in
[LIMITATIONS.md](https://github.com/rmednitzer/nous/blob/main/LIMITATIONS.md).

## Explore the docs

For a first read, in order:

1. [Showcase](showcase/README.md): the fidelity-badged public view (ADR 0017),
   including the [capability matrix](showcase/capability-matrix.md) of what is
   real today.
2. [Architecture](architecture.md): how the engine, server, and self-model fit
   together, with the data flow and the external surfaces.
3. [State machine](state-machine.md): the mission-posture FSM and its safety
   gates.
4. [Tool reference](tool-reference.md): the full MCP surface, generated from
   the live server.
5. [Hardware profiles](hardware-profiles.md) and [bill of materials](bom.md):
   the profile YAML schema and the reference build it is anchored to.
6. [Model cards](model-cards/README.md): one card per subsystem and estimator,
   with inputs, outputs, an SLA, and known failure modes.
7. [Interoperability](conformance/cot-tak.md): the conformance posture for each
   adapter.

For the engineering record:

- [Architecture decisions](adr/README.md): the numbered ADRs.
- [STPA](stpa/README.md): the safety analysis.
- [Backlog](backlog.md): the `BL-NNN` tracker.
- [Deployment](deployment.md) and [releasing](releasing.md): the VM deployment
  pattern and the release process.

## Generated pages

A few pages are regenerated by scripts; do not hand-edit them:

- `tool-reference.md` from the FastMCP server.
- `adr/README.md` and the `mkdocs.yml` ADR nav from the ADR file headers.
- the `backlog.md` summary footer from the backlog table.

Run `make schema` to regenerate them.
