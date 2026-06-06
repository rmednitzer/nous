# ADR 0036: Tick-loop observability via OpenTelemetry

- **Status:** Accepted
- **Date:** 2026-06-06
- **Authors:** rmednitzer
- **Builds on:** ADR 0019 (engine clock seam), ADR 0024 (process-scoped tick loop)

## Context

BL-037 asks for observability on the tick loop. `tick_loop` advances the
engine at the profile cadence (2 Hz by default) and already counts overruns
in-process (`state.last_capabilities["tick_overruns"]`), but that count is only
visible through a snapshot and resets when the loop restarts. An operator
running the live VM has no standard way to see tick health (the latency
distribution, the overrun rate) in their own monitoring stack.

Two constraints shape the choice. `nous` is a small edge-class artefact, so it
should not require a metrics collector to run, nor carry a heavy dependency for
a feature that is off in most deployments. And the tick loop is a hot path: a
span emitted per tick would flood a trace backend at 2 Hz (over a hundred
thousand spans a day) for signals that are really about rates and
distributions.

## Decision

Instrument the tick loop with OpenTelemetry metrics through the OTel API alone.
`nous` depends on `opentelemetry-api`, whose instruments are no-ops until a
`MeterProvider` is configured; it does not depend on the SDK at runtime.
`src/nous/telemetry.py` owns two instruments: a `nous.tick.duration` histogram
(seconds, carrying the FSM mode as an attribute) and a `nous.tick.overruns`
counter. `tick_loop` records the elapsed time on every tick and increments the
counter when a tick runs over its budget. With no provider configured (the
default), both calls are no-ops, so behaviour and overhead are unchanged.

An operator opts in without any `nous`-specific configuration by launching the
server under `opentelemetry-instrument` (or by wiring an SDK in their own
entrypoint): the standard `OTEL_*` environment variables then select the
exporter, and the instruments created at import rebind to the configured
provider. Metrics, not spans, are the right tool for a loop this hot, because a
histogram and a counter aggregate cheaply where a per-tick span cannot.

## Consequences

Tick health becomes exportable to any OTLP-compatible backend without touching
`nous` code, closing the BL-037 gap. The runtime dependency set grows by one
lightweight, no-op-by-default package; the SDK stays a dev dependency, used only
to drive the in-memory reader the test asserts against, so CI needs no
collector. The change is confined to `tick.py` and the new `telemetry.py`, and
touches no boundary surface. The in-process `tick_overruns` snapshot is kept: it
is a cheap, always-available signal that needs no collector and predates this
ADR.

## Revisit triggers

Revisit if other hot paths (estimator updates, tool calls) warrant their own
instruments, which would argue for a shared meter and naming convention.
Revisit if a turnkey exporter is wanted inside `nous` (a `configure_telemetry`
helper that pulls the SDK into the runtime), trading the minimal footprint for
export that works without `opentelemetry-instrument`. Revisit if per-tick
tracing is ever needed for debugging, which would add a sampled span alongside
the metrics rather than replace them.
