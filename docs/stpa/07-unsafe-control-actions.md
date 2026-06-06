# 07 -- Unsafe control actions

For each controller -> controlled-process action, we ask: when is this action
*not provided*, when is it *provided but unsafe*, when is it *provided too early
or too late*, and when is it *stopped too early or too late*. Each UCA carries a
stable id (`UCA-Nx`) so the coverage report
([11-coverage.md](11-coverage.md)) can trace it.

## Controller -> Engine via `state_transition`

| ID | Type | UCA | Linked hazard |
|----|------|-----|--------------|
| UCA-1a | Provided unsafely | Issuing `trigger=mission` while thermal headroom is exhausted. | H-2 |
| UCA-1b | Not provided | Failing to issue `trigger=safe` when the self-model reports `viability=false`. | H-1, H-2 |
| UCA-1c | Too late | Issuing `trigger=low_power` after the SoC estimator has reached the critical reserve. | H-8 |

## Controller -> Engine via `comms_publish`

| ID | Type | UCA | Linked hazard |
|----|------|-----|--------------|
| UCA-2a | Provided unsafely | Publishing a CoT message constructed from a stale position estimate. | H-4 |
| UCA-2b | Provided unsafely | Publishing without including the source timestamp. | H-4 |

## Controller -> Engine via `inference_cloud`

| ID | Type | UCA | Linked hazard |
|----|------|-----|--------------|
| UCA-3a | Provided unsafely | Issuing a call after the cap has been exhausted (no fallback). | H-5 |
| UCA-3b | Provided unsafely | Treating cached untrusted content as if it lived in the trusted slot. | H-1 |

## Controller -> Engine via `scenario_inject`

| ID | Type | UCA | Linked hazard |
|----|------|-----|--------------|
| UCA-4a | Provided unsafely | Injecting a fault while the FSM is in `SHUTDOWN`. | H-2 |
| UCA-4b | Stopped too late | Continuing to inject after `safe` has been triggered. | H-2 |

## Engine -> Adapters

| ID | Type | UCA | Linked hazard |
|----|------|-----|--------------|
| UCA-5a | Provided unsafely | Adapter emits with `max_age` exceeded. | H-4 |
| UCA-5b | Not provided | Adapter silently drops a publish failure rather than surfacing it. | H-3 |

## Engine -> state machine via auto-safing

The engine is itself an automated controller of the FSM: each tick it may issue
a safing trigger (ADR 0027/0028). Its control action has its own UCAs.

| ID | Type | UCA | Linked hazard |
|----|------|-----|--------------|
| UCA-6a | Not provided | The engine does not drive the FSM out of an operational mode while SC-2 or SC-8 is violated mid-run, so the device sustains an unsafe posture. | H-2, H-8 |
| UCA-6b | Provided too early | Auto-safing fires on a single-tick sensor spike, dropping a healthy workload (false safing). | operational prudence |

UCA-6a is the unsafe case that DR-13 controls (the engine *does* auto-safe each
tick); UCA-6b is bounded by the operator-label debounce (the enforcer and comms
conditions read smoothly-evolving reported state and stay instantaneous).

## A note on non-UCA causal factors

STPA loss scenarios (artefact 08) do not all originate in a controller UCA.
LS-4 (logrotate without `chattr +a`) and LS-5 (OAuth lockdown left disabled) are
deployment and configuration faults inside the system boundary, not control
actions a controller issues. They are carried in the loss-scenario table and
the coverage report rather than here, and are mitigated by the audit-integrity
and admission requirements (DR-6 / DR-12 and DR-7 / DR-9).
