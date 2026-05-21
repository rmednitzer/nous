# Fidelity badges

Every number on every showcase page carries one of five badges. The
badge is the contract: a reader can trust the numeric value to the
extent the badge promises, and no further.

| Badge | Meaning | Example today |
| --- | --- | --- |
| `validated` | Physics or estimator output that has been compared against a published reference or a measured device trace. | None at v0.1. |
| `filtered` | A substantive subsystem feeding a recursive estimator with a real predict and update step and a documented covariance bound. | Power SoC (Kalman over SoC and voltage). APU per-source (parallel Kalman). |
| `parametric` | A substantive subsystem with profile-driven physics, but the estimator on top is a passthrough or stub. | None today; this badge exists for the transitional state when a subsystem ships before its estimator. |
| `stub` | A skeleton that returns plausible constants or simple time-additive values. No dynamics, no calibration. | Thermal, compute, comms, position, biometrics, sensors, storage, inference. |
| `planned` | A surface mentioned in the architecture or the backlog that does not yet exist as code. | The self-model assess wiring (BL-018), the scenario injectors (BL-014). |

The badges map directly onto the substance findings in the in-house
audit (`AUDIT.md`) and the systems review at `docs/review-2026-05-21.md`.
A subsystem moves up the ladder only when an ADR or a backlog item
records the move; the showcase pages are reviewed at the same time.

## Current subsystem mapping

| Subsystem | Badge | Notes |
| --- | --- | --- |
| power | `filtered` | Li-ion + Peukert + SoC Kalman; per-cell internal resistance and thermal derate from profile. |
| apu | `filtered` | Solar MPPT, methanol fuel cell, vehicle tether, USB-C PD; per-source Kalman. |
| state machine | `filtered` | Explicit transition table, ADR 0004. Strictly speaking not an estimator; included because its outputs are auditable. |
| comms_state | `stub` | Derives state from a fixed link health envelope; no per-link physics yet. |
| operator_state | `stub` | Threshold logic over heart rate; physiology model is planned (BL-040). |
| thermal | `stub` | Returns ambient default; no two-state model (BL-005). |
| compute | `stub` | Idle draw only; load curve not coupled (BL-007). |
| storage | `stub` | Fixed capacity; wear curve planned (BL-008). |
| sensors | `stub` | Hardcoded reads; sensor pack planned (BL-009). |
| position | `stub` | Hardcoded covariance, no EKF (BL-010, BL-026). |
| biometrics | `stub` | Threshold over noisy values; Kalman planned (BL-011, BL-029). |
| comms | `stub` | Nominal `CONNECTED`; link envelopes planned (BL-012). |
| inference | `planned` | Local and cloud paths planned (BL-013, BL-043). |
| self model | `planned` | Capability claims wired in BL-018. |

## How badges roll up

A scenario page rolls up to the strongest badge that every plotted
metric on that page can honestly claim. If a scenario plots SoC
(`filtered`) and thermal (`stub`), the page header shows `stub`
because the weakest link sets the contract. The per-metric badges on
the same page remain individual so a reader can see which metrics are
trustworthy and which are decoration.

The covariance reporting rule follows from this: a `stub` estimator
reports its covariance as `null` on the showcase, never as a numeric
zero. The same value can appear as a numeric zero inside the engine
without contradicting this rule; the showcase is the seam where the
substance level becomes visible.

## Revisit triggers

This page is reviewed whenever a backlog item moves a subsystem from
`stub` to `parametric` or `filtered`, whenever an ADR adds or removes
a subsystem, and whenever the audit at `AUDIT.md` is refreshed.
