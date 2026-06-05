# Fidelity badges

Every number on every showcase page carries one of five badges. The
badge is the contract: a reader can trust the numeric value to the
extent the badge promises, and no further.

| Badge | Meaning | Example today |
| --- | --- | --- |
| `validated` | Physics or estimator output that has been compared against a published reference or a measured device trace. | None at v0.1. |
| `filtered` | A substantive subsystem feeding a recursive estimator with a real predict and update step and a documented covariance bound. | Power SoC (Kalman over SoC and voltage). APU per-source (parallel Kalman). |
| `parametric` | A substantive subsystem with profile-driven physics, but the estimator on top is a passthrough or stub. | Inference local path (profile-derived latency / energy / capacity, no estimator). Position estimator (v0.1 EKF passthrough; full constant-velocity EKF is BL-026). Comms estimator (per-link belief tracker; full particle filter is BL-030). |
| `stub` | A skeleton that returns plausible constants or simple time-additive values. No dynamics, no calibration. | None on the development line as of 2026-05-23; the L1 subsystem rollout closed the previous stub posture. The live VM still serves stubs because `origin/main` is behind. |
| `planned` | A surface mentioned in the architecture or the backlog that does not yet exist as code. | The self-model assess wiring (BL-018), the scenario injectors (BL-014), the PMU/PDU subsystem (BL-005b). |

The badges map directly onto the substance findings in the in-house
audit (`AUDIT.md`) and the systems review at `docs/review-2026-05-21.md`.
A subsystem moves up the ladder only when an ADR or a backlog item
records the move; the showcase pages are reviewed at the same time.

## Current subsystem mapping

Reflects the development branch at revision `02f2062`. The live VM lags
this mapping until the L1 rollout (PRs #29..#37) merges to `main`.

| Subsystem | Badge | Notes |
| --- | --- | --- |
| power | `filtered` | Li-ion + Peukert + SoC Kalman; per-cell internal resistance and thermal derate from profile. |
| apu | `filtered` | Solar MPPT, methanol fuel cell, vehicle tether, USB-C PD; per-source Kalman. |
| state machine | `filtered` | Explicit transition table, ADR 0004. Entry gates enforce SC-2 thermal headroom and SC-8 power reserve through a runtime enforcer (ADR 0018/0022); the engine auto-safes on tick when a constraint is violated (ADR 0027/0028). Strictly speaking not an estimator; included because its outputs are auditable. |
| comms_state | `filtered` | Derived each tick from the live per-link envelope; aggregator drives the FSM `state.comms_state`. |
| operator_state | `parametric` | Carried by the FSM; threshold logic over biometrics. Physiology grounding (BL-040) is planned. |
| thermal | `filtered` | Two-state lumped model (junction + enclosure); per-channel Kalman with shrinking covariance (BL-005, BL-028). |
| compute | `filtered` | Load fraction with profile-driven draw curve; per-channel Kalman over load and draw (BL-007, BL-031a). |
| storage | `filtered` | NAND wear and capacity accounting with write amplification; per-channel Kalman (BL-008). |
| sensors | `filtered` | Temperature, humidity, barometric pressure; authoritative ambient source. Multi-channel Kalman with bounds validation (BL-009). |
| position | `parametric` | Dead-reckoning + GNSS fix gating + IMU drift; v0.1 EKF passthrough validates NaN/Inf. Full constant-velocity EKF lands with BL-026. |
| biometrics | `filtered` | Heart rate, core temperature, hydration, cognitive load with physiological clamps. Multi-channel Kalman (BL-011, BL-029). Physiology grounding (BL-040) is planned. |
| comms | `parametric` | Per-link envelopes drive FSM state each tick; per-link belief tracker. Full transition particle filter (BL-030) is planned. |
| inference | `parametric` | Local-path with profile-derived latency / energy / capacity; cloud path is BL-013 follow-up, real local model is BL-043. |
| self model | `parametric` | Calibrated `p5`/`p50`/`p95` capability claims via Monte Carlo over the estimator posteriors (BL-018/BL-035); learned self-model is future. |

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
