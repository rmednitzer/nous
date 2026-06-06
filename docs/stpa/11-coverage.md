# 11 -- Coverage report

This report is the BL-044 deliverable. It closes the STPA loop by tracing every
loss to the requirement that mitigates it and recording how each requirement is
enforced. It is the artefact a reviewer reads to confirm the analysis has no
dangling hazard, constraint, or requirement.

The STPA remains a teaching artefact, not a certified safety case for a real
device (see [01-purpose.md](01-purpose.md) and `LIMITATIONS.md` L16). What this
report asserts is internal completeness: the chain *Loss -> Hazard -> Safety
constraint -> Unsafe control action / Loss scenario -> Derived requirement* is
unbroken, and every **enforced** requirement names a real test.

## Completeness criteria

| Criterion | Result |
|-----------|--------|
| Every loss (L-1..L-4) has at least one hazard | met |
| Every hazard (H-1..H-8) has at least one safety constraint | met (H-N maps to SC-N) |
| Every safety constraint (SC-1..SC-8) has at least one derived requirement | met |
| Every safety constraint has at least one **enforced** derived requirement | met |
| Every UCA traces to a hazard (or is flagged operational-prudence) | met -- all UCAs link an H-* hazard except UCA-6b (false safing), which is an operational-prudence item, not a safety hazard (the same category artefact 10 uses for the comms-DENIED auto-safe condition) |
| Every loss scenario traces to a UCA or a named causal factor, and to a loss | met |
| Every **enforced** requirement names a pinning test | met (table below) |

## Traceability matrix

One row per hazard: the loss it threatens, the constraint that bounds it, the
unsafe control action(s) and loss scenario(s) that realise it, and the derived
requirement(s) that mitigate it. UCA ids are defined in
[07-unsafe-control-actions.md](07-unsafe-control-actions.md); loss scenarios in
[08-loss-scenarios.md](08-loss-scenarios.md).

| Hazard | Loss | SC | UCA(s) | Loss scenario | DR(s) | Status |
|--------|------|----|--------|---------------|-------|--------|
| H-1 self-model overconfidence | L-1 | SC-1 | UCA-1b, UCA-3b | LS-1 | DR-1, DR-10 | enforced |
| H-2 unsafe thermal mode entry | L-2 | SC-2 | UCA-1a, UCA-4a, UCA-6a | LS-1 | DR-2, DR-13, DR-14 | enforced |
| H-3 comms mislabelled connected | L-1, L-3 | SC-3 | UCA-5b | LS-2 | DR-3 | enforced |
| H-4 stale-estimate interop emit | L-3 | SC-4 | UCA-2a, UCA-2b, UCA-5a | LS-2 | DR-4 | enforced |
| H-5 cap exhaustion, no fallback | L-2 | SC-5 | UCA-3a | LS-3 | DR-5, DR-8 | enforced |
| H-6 audit append-only broken | L-4 | SC-6 | (LS-4, deployment fault) | LS-4 | DR-6, DR-12 | enforced |
| H-7 OAuth admits an extra client | L-2, L-3 | SC-7 | (LS-5, config fault) | LS-5 | DR-7 (lockdown enforced), DR-9 (defence in depth) | enforced |
| H-8 unsafe power mode entry / sustain | L-2 | SC-8 | UCA-1c, UCA-6a | LS-6 | DR-11, DR-13, DR-14 | enforced |

Every hazard has at least one enforced derived requirement. For H-7 the enforced
control is DR-7 (the OAuth single-client lockdown, pinned below); DR-9 (the
additive-surface tool rule) is defence in depth, not the OAuth admission control,
so it is not counted as SC-7's enforcement. The one sub-claim still unpinned is
the disable-time warning on DR-7, detailed under residual items.

## Derived-requirement enforcement

Each **enforced** DR is pinned by the named test (verified to exist at the time
of this report):

| DR | Pinning test |
|----|--------------|
| DR-1 | `tests/unit/test_self_model.py::test_endurance_band_widens_as_soc_covariance_grows` |
| DR-2 | `tests/unit/test_state_machine_guards.py::test_mission_refused_when_headroom_below_threshold` |
| DR-3 | `tests/unit/test_comms_subsystem.py::test_derive_state_limited_when_one_link_unhealthy` |
| DR-4 | `tests/unit/test_interop_adapters.py::test_cot_encode_refuses_stale_estimate` (and the per-adapter `*_refuses_stale` cases) |
| DR-5 | `tests/unit/test_anthropic_client.py::test_cap_raises_when_exhausted` (cap fail-closed) ; `tests/unit/test_anthropic_status.py::test_cap_exhausted_payload_carries_reason_and_snapshot` (structured payload) ; `tests/unit/test_inference_fallback.py::test_local_used_when_cap_exhausted`, `::test_local_used_when_cloud_raises_cap_exhausted` (fallback ladder routes to the local mock) ; `tests/integration/test_inference_cloud_tool.py::test_inference_cloud_degrades_on_cap_exhausted` (the registered `inference_cloud` tool degrades to the mock, ADR 0034) |
| DR-6 | `tests/unit/test_audit_durability.py::test_audit_degraded_on_fsync_failure` |
| DR-7 | `tests/unit/test_oauth.py::test_single_client_replaces_on_re_dcr` (a re-registration evicts the prior client; lockdown enforced). The disable-time warning is the lone unpinned sub-claim, below. |
| DR-8 | `tests/unit/test_anthropic_client.py::test_corrupt_state_fails_closed` |
| DR-9 | `tests/unit/test_policy.py::test_unknown_tool_refused_under_guarded_without_allow` |
| DR-10 | `tests/unit/test_estimator_properties.py::test_position_rejects_garbage_lat` |
| DR-11 | `tests/unit/test_state_machine_guards.py::test_low_power_recover_refused_under_critical_soc` |
| DR-12 | `tests/unit/test_audit_hash_chain.py::test_verify_detects_in_place_mutation` ; `tests/unit/test_audit_anchor.py::test_verify_detects_tail_truncation` |
| DR-13 | `tests/unit/test_fsm_auto_safe.py::test_auto_safe_power_from_mission_enters_low_power` |
| DR-14 | `tests/unit/test_fsm_reachability.py` (walks the table; fails the build on any broken reachability invariant) |

## Residual items

Every derived requirement is enforced; one *sub-claim* is not yet pinned:

- **DR-7, disable-time warning.** The OAuth single-client default and the
  evict-on-re-registration lockdown are enforced and tested
  (`tests/unit/test_oauth.py::test_single_client_replaces_on_re_dcr`), so an
  unintended second client cannot silently co-exist. The secondary claim that
  *disabling* lockdown emits a startup warning and an audit event is asserted in
  code review, not a test. Tracked under BL-019 (issuer) and BL-059
  (regulated-deployment token-state hardening).

## Loss scenarios without a controller UCA

STPA loss scenarios arise either from an unsafe control action or from the
inadequate execution of a control action / an unsafe input from outside the
boundary. LS-4 (logrotate without `chattr +a`) and LS-5 (OAuth lockdown left
disabled for debugging) are the second kind: deployment and configuration
faults, not controller UCAs. They are mitigated by DR-6 / DR-12 (audit
integrity) and DR-7 / DR-9 (admission), and are listed in the matrix with a
parenthetical so it is not read as "every scenario is a UCA".

## Transition-level traceability

The FSM-specific join (every gated transition to its constraint and hazard,
plus the auto-safing conditions and the failsafe-reachability invariants) is
maintained separately in
[10-fsm-constraints-mapping.md](10-fsm-constraints-mapping.md), which the
reachability and guard tests pin directly. This report is the system-level
view; artefact 10 is the state-machine-level view, and the two share the SC and
hazard ids.
