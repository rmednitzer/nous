# 07 -- Unsafe control actions

For each controller -> controlled-process action, we ask: when is this
action *not provided*, when is it *provided but unsafe*, when is it
*provided too early or too late*, and when is it *stopped too early or
too late*.

## Controller -> Engine via `state_transition`

| Type | UCA | Linked hazard |
|------|-----|--------------|
| Provided unsafely | Issuing `trigger=mission` while thermal headroom is exhausted. | H-2 |
| Not provided | Failing to issue `trigger=safe` when the self-model reports `viability=false`. | H-1, H-2 |
| Too late | Issuing `trigger=low_power` after the SoC estimator has reached zero. | H-8 |

## Controller -> Engine via `comms_publish`

| Type | UCA | Linked hazard |
|------|-----|--------------|
| Provided unsafely | Publishing a CoT message constructed from a stale position estimate. | H-4 |
| Provided unsafely | Publishing without including the source timestamp. | H-4 |

## Controller -> Engine via `inference_cloud`

| Type | UCA | Linked hazard |
|------|-----|--------------|
| Provided unsafely | Issuing a call after the cap has been exhausted (no fallback). | H-5 |
| Provided unsafely | Treating cached untrusted content as if it lived in the trusted slot. | H-1 |

## Controller -> Engine via `scenario_inject`

| Type | UCA | Linked hazard |
|------|-----|--------------|
| Provided unsafely | Injecting a fault while the FSM is in `SHUTDOWN`. | H-2 |
| Stopped too late | Continuing to inject after `safe` has been triggered. | H-2 |

## Engine -> Adapters

| Type | UCA | Linked hazard |
|------|-----|--------------|
| Provided unsafely | Adapter emits with `max_age` exceeded. | H-4 |
| Not provided | Adapter silently drops a publish failure rather than surfacing it. | H-3 |
