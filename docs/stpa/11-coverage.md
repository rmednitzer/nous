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
| Every UCA traces to a hazard | met |
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
| H-7 OAuth admits an extra client | L-2, L-3 | SC-7 | (LS-5, config fault) | LS-5 | DR-9 (enforced), DR-7 (review) | partial |
| H-8 unsafe power mode entry / sustain | L-2 | SC-8 | UCA-1c, UCA-6a | LS-3 | DR-11, DR-13, DR-14 | enforced |

Every hazard has at least one enforced derived requirement. H-7 is the only row
with a residual review item (DR-7), detailed below; its admission control
(DR-9) is enforced, so the hazard is not unmitigated.

## Derived-requirement enforcement

Each **enforced** DR is pinned by the named test (verified to exist at the time
of this report):

| DR | Pinning test |
|----|--------------|
| DR-1 | `tests/unit/test_self_model.py::test_endurance_band_widens_as_soc_covariance_grows` |
| DR-2 | `tests/unit/test_state_machine_guards.py::test_mission_refused_when_headroom_below_threshold` |
| DR-3 | `tests/unit/test_comms_subsystem.py::test_derive_state_limited_when_one_link_unhealthy` |
| DR-4 | `tests/unit/test_interop_adapters.py::test_cot_encode_refuses_stale_estimate` (and the per-adapter `*_refuses_stale` cases) |
| DR-5 | `tests/unit/test_anthropic_client.py::test_cap_raises_when_exhausted` |
| DR-6 | `tests/unit/test_audit_durability.py::test_audit_degraded_on_fsync_failure` |
| DR-8 | `tests/unit/test_anthropic_client.py::test_corrupt_state_fails_closed` |
| DR-9 | `tests/unit/test_policy.py::test_unknown_tool_refused_under_guarded_without_allow` |
| DR-10 | `tests/unit/test_estimator_properties.py::test_position_rejects_garbage_lat` |
| DR-11 | `tests/unit/test_state_machine_guards.py::test_low_power_recover_refused_under_critical_soc` |
| DR-12 | `tests/unit/test_audit_hash_chain.py::test_verify_detects_in_place_mutation` ; `tests/unit/test_audit_anchor.py::test_verify_detects_tail_truncation` |
| DR-13 | `tests/unit/test_fsm_auto_safe.py::test_auto_safe_power_from_mission_enters_low_power` |
| DR-14 | `tests/unit/test_fsm_reachability.py` (walks the table; fails the build on any broken reachability invariant) |

## Residual items (review, not enforced)

- **DR-7 (OAuth disable warning).** The single-client default and the
  replace-on-re-DCR lockdown are tested
  (`tests/unit/test_oauth.py::test_single_client_replaces_on_re_dcr`), so an
  unintended second client cannot silently join. What is *not* pinned by a test
  is the secondary claim that disabling lockdown emits a startup warning and an
  audit event; that is asserted in code review. Tracked under BL-019 (issuer)
  and BL-059 (regulated-deployment token-state hardening).

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
