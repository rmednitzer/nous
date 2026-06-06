"""OpenTelemetry instruments for the simulator (BL-037, ADR 0036).

Instrumented with the OTel *API* only. With no ``MeterProvider`` configured
the instruments are no-ops, so ``nous`` adds no measurable overhead and takes
no dependency on a collector by default. An operator opts in by wiring an SDK
and exporter, most simply by launching under ``opentelemetry-instrument`` so
the standard ``OTEL_*`` environment variables configure a provider; the
instruments below then rebind to it.

The tick loop is a hot path (the default profile ticks at 2 Hz), so it is
instrumented with metrics, not a span per tick: a duration histogram answers
"how long does a tick take" and an overrun counter answers "how often does
work exceed the inter-tick budget" without flooding a trace backend.
"""

from __future__ import annotations

from opentelemetry import metrics

__all__ = ["tick_duration", "tick_overruns"]

_meter = metrics.get_meter("nous")

tick_duration = _meter.create_histogram(
    "nous.tick.duration",
    unit="s",
    description="Wall-clock time to advance one engine tick.",
)

tick_overruns = _meter.create_counter(
    "nous.tick.overruns",
    unit="1",
    description="Ticks whose work exceeded the inter-tick budget.",
)
