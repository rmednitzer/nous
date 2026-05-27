# Changelog

All notable changes to `nous` land here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed (ADR 0019 follow-ups)

- Every subsystem constructor now accepts an optional keyword-only
  ``rng: np.random.Generator | None`` so future noise sampling can
  draw from the engine's deterministic seam without reaching for
  the ``numpy.random`` global. ``Engine`` threads ``self.rng``
  into all ten subsystems at construction. The kwarg defaults to
  ``None`` so existing test fixtures that build subsystems
  directly continue to work without modification.
- ``scripts/policy_checks.sh`` adds a third rule: ``np.random.X``
  and ``numpy.random.X`` calls in ``src/nous/`` fail the policy
  job unless ``X`` is ``Generator`` (type) or ``default_rng``
  (constructor for the fallback in modules that accept an optional
  ``rng`` kwarg). Tests, scripts, and examples are exempt. ``make
  policy`` enforces the ban in CI.
- ``src/nous/tick.py`` reads ``engine.clock.monotonic()`` instead
  of ``anyio.current_time()`` for the per-tick budget timer. Under
  the default ``MonotonicClock`` this is value-identical to the
  prior behaviour; under a ``VirtualClock`` the engine clock does
  not advance during ``engine.tick()`` so the budget stays at
  ``dt`` and the loop's real-time sleep semantics via
  ``anyio.move_on_after`` are unchanged.

### Added (AUDIT-2026-05-23 N2 follow-up B: opportunistic auto-resync)

- ``AuditLogger.write()`` runs an opportunistic auto-resync against
  a degraded sink before each emit, on an exponential backoff
  schedule (5-second initial, doubling to a 300-second cap). The
  retry triggers only when a tool call lands (every audit-write
  routes through ``write()``), so an operator who pauses tool
  calls during active diagnosis keeps full control of the
  timing. A successful manual ``audit_resync`` resets the
  backoff to its initial value.
- ``audit_summary`` MCP tool now exposes ``auto_resync_attempts``,
  ``last_auto_resync_ts_s`` (wall clock; ``None`` until the first
  attempt), and ``auto_resync_due_in_s`` (seconds-from-now to
  the next scheduled attempt; ``None`` when healthy). An
  operator diagnosing the degraded state can see the upcoming
  retry window.
- ``SECURITY.md`` "Audit-degraded posture and kill switches"
  documents the auto-resync schedule. ``skills/nous-troubleshooting.md``
  gains a new step 5 explaining the wait-and-let-it-retry path
  alongside the manual ``audit_resync`` call.

### Added (AUDIT-2026-05-23 N2 follow-up: audit_summary tool)

- ``AuditLogger`` now tracks ``writes_total`` (cumulative successful
  writes) and ``last_write_ts_s`` (unix timestamp of the most
  recent successful write; ``None`` until the first write). The
  counters update on the success path only; the swallowed-exception
  paths leave them untouched so a flat ``writes_total`` against
  active tick cadence is the silent-drop signal.
- New ``AuditLogger.summary()`` returns the full T0 view:
  ``path``, ``degraded``, ``degraded_reason``, ``fsync_failures``,
  ``writes_total``, ``last_write_ts_s``, ``also_stderr``.
- New MCP tool ``audit_summary`` (T0) wires
  ``app.audit.summary()`` through the audited runner. The tool
  was already classified ``Tier.READ_ONLY`` in ``policy.py`` but
  never registered in ``server.py``; this commit closes the
  registration gap. ``_INSTRUCTIONS`` advertises the tool in
  the existing "Device telemetry (T0)" line. A controller
  comparing ``audit_summary.writes_total`` against the tick
  cadence can detect a silently-dropping handler that
  ``device_info.audit.degraded`` (which only flips on a write
  exception) would not catch.

### Fixed (AUDIT-2026-05-23 N2 in-process recovery)

- ``AuditLogger`` carries a new ``resync()`` method that re-runs
  the sink-opening logic in place. ``_open_sink()`` was extracted
  from ``__init__`` so the same path serves both construction
  and recovery. An operator who fixes the underlying filesystem
  cause (permissions, mount, ``ReadWritePaths=`` drift, the
  audit file moved out from under the handler) no longer has to
  restart ``nous.service`` to clear ``audit.degraded``;
  ``resync()`` returns a status dict that distinguishes
  "recovered" from "no-op" via a ``recovered: bool`` field, and
  the cumulative ``fsync_failures`` counter is *not* reset so
  the operator can still see the loss window.
- New MCP tool ``audit_resync`` (T2) exposes the recovery path
  to a controller. Classified in ``policy._STATEFUL_TOOLS``
  (additive per ADR 0007) so guarded mode refuses it without an
  explicit allow; ``audit_resync`` lands in the
  ``_INSTRUCTIONS`` block under a new "Operational recovery"
  category. ``SECURITY.md`` and ``skills/nous-troubleshooting.md``
  document the triage flow: fix the cause, call the tool, verify
  ``device_info.audit.degraded`` is ``false``. Regression-pinned
  as ``TestN2AuditSinkRecoversInProcess``.

### Fixed (audit carry-forward closures, 2026-05-27 second pass)

- AUDIT-2026-05-20 H2: ``[tool.mypy] files`` now includes
  ``tests`` alongside ``src/nous``; ``src/nous/py.typed`` is the
  PEP 561 marker that makes the project's own modules visible to
  mypy from the test tree. Seventeen real findings fixed inline
  (fixture return-type, ``Link | None`` narrowing, ``str | None``
  refresh-token narrowing in tests, ``Mode`` identity check). A
  per-module override relaxes ``disallow_untyped_decorators`` and
  ``disallow_any_generics`` for ``tests.*`` only, matching the
  existing carve-out for ``nous.server``.
- AUDIT-2026-05-24 N3: ``state_get`` MCP tool returns ``mode``,
  ``tick``, ``ts_s``, ``operator_state`` plus reason,
  ``comms_state`` plus reason. Subsystem detail stays on
  ``device_health``.
- AUDIT-2026-05-24 N4: ``tests/integration/test_snapshot_mcp_parity.py``
  asserts ``device_health`` payload keys equal ``engine.snapshot()``
  keys, and ``state_get`` keys are a subset; a refactor that
  drifts the two views apart fails here.
- AUDIT-2026-05-24 N7: ``misb_klv.py`` decoder returns UTF-8
  strings (with hex fallback for non-UTF-8 bytes); timestamp key
  returns an ``int``. Round trip is now symmetric for the
  str-encoded values the encoder writes. Regression-pinned as
  ``TestN7MisbKlvDecodeReturnsSymmetricTypes``.
- AUDIT-2026-05-27 N16: ``docs/contributor-runbook.md`` §4.X
  "Local cache hygiene" documents the ``.hypothesis/`` examples
  database (reversible to clear; a new failing example without a
  code change is a real test gap).
- AUDIT-2026-05-27 N17: ``docs/security/bandit-suppressions.md``
  catalogues every ``# nosec`` annotation in ``src/nous/`` with
  its rationale and the regression test or conformance document
  that backs it. ``SECURITY.md`` cross-links the catalog.

### Added

- ADR 0019 implementation (first increment of AUDIT-2026-05-27
  N8). ``src/nous/clocks.py`` carries the ``Clock`` Protocol,
  ``MonotonicClock`` (default), and ``VirtualClock`` (test
  clock, advances under caller control). ``Engine`` grows
  ``seed`` and ``clock`` keyword-only kwargs; the engine's
  single ``numpy.random.Generator`` flows into
  ``CommsParticleFilter`` so same-seed engines produce identical
  comms-filter trajectories. Four new tests in
  ``tests/unit/test_engine_determinism.py``.
- ADR 0020 implementation (second increment of N8).
  ``tests/unit/test_subsystem_invariants.py`` covers compute
  draw monotonicity in load, power SoC monotone non-increasing
  under discharge, thermal convergence to ambient at zero load,
  comms link-age monotonicity, and tx-resets-age. Hypothesis
  drives the parametrisation; the deterministic seed seam from
  ADR 0019 makes shrinking sensible.

### Documented

- Delta audit at HEAD ``563175a`` published as
  [`docs/audit-2026-05-27b.md`](docs/audit-2026-05-27b.md). Closes
  six 2026-05-27 carry-forwards plus the foundation increments
  for ADR 0019 and ADR 0020. Carry-forward open items: N2
  (live VM action), ADR 0021 (per-subsystem tool modules), ADR
  0022 (runtime safety enforcer), additional ADR 0020
  invariants. One new observation: N18 (``CommsParticleFilter``
  retains its legacy ``seed`` kwarg for test ergonomics).

### Fixed

- AUDIT-2026-05-20 C2: ``src/nous/audit.py`` ``redact()`` now recurses
  through nested mappings and list values. The redaction allowlist
  applies at every depth; oversize strings are truncated at every
  depth too. Regression-pinned as
  ``tests/regression/test_audit_findings.py::TestC2RedactionRecurses``.
- AUDIT-2026-05-20 M1: ``src/nous/runner.py`` stamps ``exit_code=1``
  on the denial-path audit record so per-tier denial counts are
  machine-queryable without parsing the body string. The success
  path keeps ``exit_code=None`` (no abnormal exit) so a JSONL
  consumer can split denials and worker errors apart from normal
  returns. Regression-pinned as
  ``TestM1RunnerDenialStampsExitCode``.
- AUDIT-2026-05-20 H1: dedicated spine tests for the audited
  runner (``tests/unit/test_runner.py``, 11 cases) and the FSM
  transition table (``tests/unit/test_state_machine.py``, 8 cases
  plus 40 parametrised entries plus 1 Hypothesis property). The
  third spine module (``anthropic_client.py``) was already covered
  under PR #38 follow-up.
- AUDIT-2026-05-20 H6: ``FileOAuthProvider`` carries an
  ``asyncio.Lock`` arbitrating every load+modify+save sequence on
  the three JSON stores. ``_Store.save`` chmods the file to
  ``0o600`` and fsyncs the parent directory after the atomic
  rename. Regression-pinned as
  ``TestH6OAuthFileStoreLockedAndConfidential``.
- AUDIT-2026-05-20 H7: refresh-token records carry an ``issue_id``
  naming their family; rotation propagates the id; the consumed
  record is marked ``consumed=True`` so reuse stays detectable. On
  reuse, ``load_refresh_token`` and ``exchange_refresh_token`` fire
  family revocation per OAuth 2.1 BCP §4.13. Regression-pinned as
  ``TestH7RefreshTokenReuseRevokesFamily``.
- AUDIT-2026-05-20 H8: ``deploy/auto-update.sh`` writes
  ``/var/log/nous/auto-update.last_ok`` on success and
  ``last_failed`` on a post-restart sanity failure; subsequent
  ticks refuse to re-deploy a SHA listed in ``last_failed``,
  breaking the every-five-minutes retry loop. New companion
  script ``deploy/auto-update-rollback.sh`` reads ``last_ok`` and
  resets the working tree to the previous known-good commit.
  ``SECURITY.md`` kill-switch panel updated.
- AUDIT-2026-05-20 H9: every uncited inference numeric in
  ``profiles/*.yaml`` now carries an inline ``PLACEHOLDER`` comment
  naming BL-043 (real local model under TensorRT-LLM or
  llama.cpp).
- AUDIT-2026-05-24 N5 / N10 / N11: ``_INSTRUCTIONS`` in
  ``src/nous/server.py`` enumerates the full 26-tool surface
  grouped by purpose with tier badges. The stale "lands in L1"
  sentence is gone.
- AUDIT-2026-05-24 M10 closure pin: BL-006 wired
  ``ProfileModel.model_validate`` into ``engine._load_profile``;
  this release adds the regression-suite class
  ``TestM10ProfileLoaderValidatesAtLoadTime`` per ADR 0023.
- ``tests/unit/test_policy_fuzz.py`` skip lists were hardcoded and
  out of sync with ``policy.py``'s tool sets (the missing
  ``anthropic_cap_status`` was caught by Hypothesis during the H1
  spine-test work). Both fuzz cases now derive their skip lists
  from ``_READ_ONLY_TOOLS`` / ``_REVERSIBLE_TOOLS`` /
  ``_STATEFUL_TOOLS`` so future T0 / T1 / T2 additions do not
  require a test edit.

### Added

- ``docs/conformance/mqtt.md``, ``docs/conformance/sensors.md``,
  ``docs/conformance/biometrics.md``: three new conformance
  postures closing AUDIT-2026-05-20 L9 and AUDIT-2026-05-24 N9.
  The tree is now eleven postures: cot-tak, stanag-4609-misb-klv,
  ogc-sensorthings, nmea-0183, stanag-4774-4778, mosa, sosa,
  stanag-4677-dsss, mqtt, sensors, biometrics.
- ``uv.lock`` is now committed (was ``.gitignored``).
  Reproducibility no longer depends on Dependabot freshness alone.
- ``.github/workflows/*.yml`` SHA-pin every Action ``uses:`` line
  with the semver in a trailing comment for Dependabot tracking.
  The setup-uv major-tag drift caught during this engagement
  (``@v7`` lagged ``v7.6.0`` by several releases) is the exact
  attack surface SHA pinning closes.
- New CI job ``supply-chain`` in ``ci.yml`` runs ``pip-audit
  --strict`` (CVE / advisory) and ``bandit -r src/nous`` (SAST).
  Docs workflow emits a CycloneDX-JSON SBOM
  (``cyclonedx-py environment``) on every build and uploads it as
  a 90-day ``sbom-cyclonedx`` artefact.

### Documented

- Delta audit at HEAD ``4a6b394`` published as
  [`docs/audit-2026-05-27.md`](docs/audit-2026-05-27.md). Closes
  eleven open findings from the 2026-05-24 baseline plus three new
  supply-chain wins surfaced during the Phase 0 inventory of the
  engagement. Carry-forward open items: H2 (mypy strict for tests),
  N3 / N4 / N7 (polish), N2 (live-VM action), N8 (ADR 0019-0022
  implementation programme).
- Full code-index audit at revision `fb8356f` published as
  [`docs/audit-2026-05-24.md`](docs/audit-2026-05-24.md). Delta
  against the 2026-05-23 audit (including its §10 re-audit): the
  borrowed regression suite at
  `tests/regression/test_audit_findings.py` formally pins **C1**,
  **C4**, **C5** (five estimators), **H3**, and **M8** as closed
  with the prior defect in the class docstring; the
  `engine._assert_post_tick_finite` guard is a new defensive
  measure catching the C5-class "stub emits NaN" failure mode at
  the tick boundary. §4 walks each interop adapter against its
  `docs/conformance/` document and confirms the encoders match.
  Carry-forward open items (C2, H1, H2, H6, H7, H8, H9, M1, M10,
  N2 through N7, and L9 from the 2026-05-20 baseline) are
  re-verified at `file:line` against the source. New observations: **N8** (ADRs 0019 through 0022 are
  Proposed but unimplemented), **N9** (sensors and biometrics
  subsystems lack `docs/conformance/` entries), **N10** (six L1
  subsystem read tools missing from `_INSTRUCTIONS`).
- ADR 0023 accepted: audit cadence and regression-suite pattern.
  Codifies the delta-audit format
  (`docs/audit-YYYY-MM-DD.md`), the regression-pin convention
  (`tests/regression/test_audit_findings.py` classes named after
  the finding id, prior defect in the docstring), and the
  open-finding traceability rule (every open finding re-verified
  with a `file:line` reference in each audit document). The
  conventions apply prospectively; existing closed findings were
  retroactively pinned in PR #44.

### Fixed

- AUDIT-2026-05-23 C3: the FastMCP server now registers a lifespan
  context that drives the engine through the new
  `nous.server.tick_lifespan(engine, tick_hz)` async context manager.
  On entry it spawns `tick_loop(engine, tick_hz, stop)` in an anyio
  task group; on exit it sets the stop event so the task drains,
  then calls `engine.stop()` so the FSM lands on SHUTDOWN rather
  than leaking the running state. Before this fix the engine started
  but no tick task was ever scheduled; `device_health` returned
  `tick=0, mode=boot` on the live server even after a long uptime.
  `engine.stop()` runs in a `finally` so a crashed tick task still
  surrenders the engine cleanly (PR #40 review follow-up).
  Covered by `tests/integration/test_server_lifespan.py`.
- AUDIT-2026-05-23 C3 follow-up: `tick_loop` (`src/nous/tick.py`)
  no longer risks event-loop starvation on a sustained tick overrun.
  The overrun branch now hits `anyio.lowlevel.checkpoint()` so the
  loop always yields control and remains cancellable, even when
  every tick takes longer than its budget (PR #40 review P1).
- AUDIT-2026-05-23 C6: the em-dash and private-repo policy greps that
  CLAUDE.md advertised are now enforced. New `scripts/policy_checks.sh`
  runs `grep -rPn '\x{2014}' --include='*.md' .` and a placeholder
  deny-list grep for private-repo references; a hit prints the
  offending lines and exits non-zero. The CI workflow adds a `policy`
  job that calls the script; `make policy` is the local-parity
  target. The em-dash rule is enforced today; the private-repo
  deny-list is a structured extension point (no entries yet).

### Documented

- `docs/assumptions.md`: per-subsystem modelling-honesty document with
  a fidelity disclaimer at the top. Complements `LIMITATIONS.md`
  (scope boundaries) by recording the simplifications *inside* the
  components that do exist, each cross-referenced to its source file.
- ADRs 0019 through 0022 proposed: deterministic seed and clock seam
  at the engine boundary (0019), property-based invariants for
  subsystem physics (0020), per-subsystem MCP tool modules (0021),
  and a runtime safety enforcer with structured result (0022). All
  four are in Proposed status; they capture the design work for
  patterns that do not fit a single PR.
- Full system audit at revision `02f2062` published as
  [`docs/audit-2026-05-23.md`](docs/audit-2026-05-23.md). Delta against
  the 2026-05-20 baseline (`AUDIT.md`) and the 2026-05-21 in-depth
  review (`docs/review-2026-05-21.md`): C1, C4, C5 (estimator
  stubs), H3, H4, H5, M4, and the audit chmod 0600 are confirmed
  closed in code; C2, C3, C6, H1 (runner-only gap), H2, H6, H7, H8,
  M1, and M10 carry over. The new finding **N1** (deployment drift:
  `origin/main` 49 commits behind HEAD; the live MCP serves the v0.1
  surface) and **N2** (live audit sink reports `degraded: true`) are
  the highest-priority remediation items.
- Markdown tree refreshed against the audit findings: STATUS.md and
  LIMITATIONS.md date-stamped 2026-05-23; SECURITY.md adds the
  audit-degraded kill-switch procedure; `docs/showcase/capability-matrix.md`
  rows flipped from `stub` to `filtered` / `parametric` for the
  subsystems that landed under PRs #29 through #37.
- Re-audit at HEAD `43d0db2` (post PR #40 / #41 / #42) appended to
  [`docs/audit-2026-05-23.md`](docs/audit-2026-05-23.md) §10. **C3**
  (engine ticks via FastMCP lifespan), **C6** (CI policy greps
  enforced), and **N1** (deployment drift, `origin/main` caught up)
  are confirmed closed; **N2** (audit sink degraded on the live VM)
  carries forward as the next live-VM action item; the revised
  remediation order in §10.3 is the up-to-date plan. STATUS.md flips
  L0 to `stable` and L1 to `in-progress` to match the actual code
  state; quality-gate count rises to 351 tests. LIMITATIONS.md L17
  and AGENTS.md "Boundaries" now reference `scripts/policy_checks.sh`
  as the enforcement seam; `docs/showcase/capability-matrix.md`
  deployment note updated to reflect the post-catch-up state.

### Changed

- `pyproject.toml`: ruff pinned to `>=0.15,<0.16` (minor-range pin) so
  CI and developer environments agree on the rule set without
  surprises from a floating major. Bump deliberately when adopting a
  new minor's lint output.
- Deployment baseline moves to Ubuntu 26.04 LTS / Python 3.14 (ADR
  0016). `deploy/install.sh` selects `python3.14` -> `python3.13` ->
  `python3` so the bundle still works on 24.04 hosts. ADR 0008 is
  superseded.
- `Engine.tick` reads the per-tick load from `compute.draw_w` rather
  than the `_default_load_w()` placeholder; the helper is removed.
  Tests that previously monkeypatched it now drive load through
  `engine.compute.set_load_pct(...)`.
- `Engine.tick` reads the per-tick ambient temperature from
  `sensors.temp_c` rather than the `_default_ambient_c()`
  placeholder; the helper is removed. The sensors subsystem seeds
  itself from `sensors.environmental.temp_c_default` (falling back
  to `thermal.ambient_c_default`) so existing profiles keep their
  ambient baseline.

### Added

- `tests/regression/test_audit_findings.py`: regression suite that pins
  closed audit findings as named test classes. Each class docstring
  summarises the original defect (`AUDIT.md` finding id) and the tests
  assert the specific behaviour that closed it. Initial coverage:
  C1 (anthropic-cap fsync inside flock), C4 (MISB KLV overflow
  refusal), C5 (thermal / compute / storage / sensors / biometrics
  estimator covariance actually shrinks), H3 (CoT events carry
  `time` / `start` / `stale` / `how`), and M8 (engine tick reachable
  from a unit test).
- `Engine.tick` now ends with `_assert_post_tick_finite`, which raises
  `RuntimeError` if any estimator emits a non-finite point estimate or
  a negative / non-finite covariance. The check catches the C5-class
  failure mode (a stub returning a plausible-looking but invalid
  belief) at the source rather than at a downstream consumer.
- `benchmark.py` at the repo root: a small `timeit` harness over one
  engine tick, one audit-log fsync round trip, and a representative
  Kalman update. No baselines, no JSON, no regression tracker; the
  point is that "did this PR slow the loop?" has a runnable answer.
- BL-011 biometrics subsystem (parametric, not physiology-grounded).
  `BiometricsSubsystem` carries heart rate, core temperature,
  hydration percentage, and a unitless cognitive-load proxy as
  ground truth with physiological-range clamps (HR `[20, 240]`, core
  temp `[28, 44] C`, hydration `[0, 100] %`, cognitive load
  `[0, 1]`). Scenario seams `set_heart_rate_bpm`, `set_core_temp_c`,
  `set_hydration_pct`, `set_cognitive_load`. Profile sigmas under
  `sensors.biometrics` are advertised on the observation; defaults
  for the four channels can be seeded under the same key
  (`*_default`). `BiometricsKalman` extended with a `hydration_pct`
  channel (bounds + process noise + initial state) so the existing
  PositionEKF / EnvironmentalKalman validation contract now covers
  four biometric channels rather than three. New
  `biometrics_status` MCP tool (already T0 in policy); biometrics
  estimator added to `self_estimator_status`.
- BL-009 environmental sensor pack. `SensorsSubsystem` carries
  ambient temperature, humidity, and barometric pressure as ground
  truth and is the authoritative ambient source the engine feeds
  into `thermal.set_ambient_c` each tick. Scenario seams
  `set_temp_c`, `set_humidity_pct`, `set_baro_kpa` (humidity clamps
  to `[0, 100]`; baro to `[10, 200]` kPa). Profile sigmas under
  `sensors.environmental` are advertised on the observation. New
  multi-channel `EnvironmentalKalman` over the three channels with
  input validation (rejected readings are counted on
  `rejected_updates` without poisoning the central estimate). New
  `sensors_status` MCP tool (already T0 in policy); sensors
  estimator added to `self_estimator_status`.
- BL-010 position subsystem. Ground-truth lat / lon / alt advanced
  each tick by dead-reckoning from `set_velocity(speed_mps,
  heading_deg)` plus an optional `vertical_mps`; longitude wraps
  through the antimeridian; latitude clamps. Profile sigmas from
  `sensors.position` (lat / lon / alt_m) are advertised on the GNSS
  observation so the v0.1 `PositionEKF` sizes its Kalman gain
  correctly. `set_fix(False)` simulates loss of fix (empty
  observation payload; the EKF's variance grows under `predict`
  until the fix returns); `set_imu_drift` lets a scenario express a
  biased IMU during a fix-lost interval. New `position_status` MCP
  tool. Snapshot adds a position block; `self_estimator_status` now
  includes the position EKF. Full constant-velocity EKF remains
  BL-026.
- BL-012 comms subsystem. Per-link envelopes derived from
  `profile["comms"]["links"]` (RSSI, loss, throughput, age, max_age).
  Live state is the subsystem's ground truth: `comms.tx(link_id,
  bytes)` resets the age counter and refreshes throughput;
  `comms.set_link_state(link_id, ...)` is a sticky controller /
  scenario override; the engine ticks each link's age forward and
  drops `connected` once `age_s > max_age_s`. The aggregator
  `comms.derive_state()` is consulted every engine tick to update
  `state.comms_state` (the FSM signal that gates cloud-bound flows
  and the inference fallback ladder). `comms_state` MCP tool now
  returns the aggregate label, derivation reason, and per-link
  beliefs; new `comms_status` tool (T0) exposes the full envelope
  including age and forced-state. `CommsParticleFilter` upgraded
  from a no-op stub to a per-link belief tracker (the full
  transition particle filter remains BL-030).
- BL-008 storage subsystem. NAND wear and capacity accounting driven
  by physical writes: `storage.write(gib)` accepts a one-shot logical
  write (clamped by free space, inflated by
  `storage.write_amplification` into the lifetime physical-writes
  counter); `storage.set_write_rate(gib_per_s)` is consumed each tick
  for a sustained workload. The wear curve is linear against a TBW
  endurance budget that defaults to `capacity_gib * 600` GiB when
  `storage.tbw_gib` is unset. Paired 1-D `StorageKalman` estimator
  over (used_gib, wear_pct). New `storage_status` MCP tool; storage
  estimator added to `self_estimator_status`.
- BL-013 local-path inference subsystem. `InferenceSubsystem.request_local`
  returns a profile-derived `latency_s` (from
  `compute.inference_local.tok_per_s_p50`) and `energy_j` (from
  `energy_j_per_tok`) alongside the synthetic response. Running totals
  for `local_calls`, `total_tokens`, and `total_energy_j` accumulate
  over the simulator's lifetime and surface in `engine.snapshot()`.
  `set_continuous_rate(tok_per_s)` writes through to
  `ComputeSubsystem.set_inference_rate` so a sustained workload
  propagates into draw watts via the existing BL-007 wiring. The
  `inference_local` MCP tool now returns the cost figures (was a fixed
  echo); new `inference_status` MCP tool exposes the totals. Cloud
  path (fallback ladder + cap accounting) deferred.
- BL-007 compute subsystem: load fraction + profile-driven draw curve.
  `compute.set_load_pct` / `set_inference_rate` steer the request;
  draw watts come from the piecewise-linear `compute.load_curve` in
  the profile. The engine feeds `compute.draw_w` into both power
  (electrical draw) and thermal (junction dissipation). When the
  thermal subsystem reports throttling, the compute subsystem
  automatically clips delivered load to mimic hardware DVFS;
  `requested_load_pct` preserves the original request so the
  controller can see how much was clipped. New `compute_status` MCP
  tool; compute estimator added to `self_estimator_status`.
- `Engine._safety_context` now derives `thermal_headroom_c` from the
  live junction temperature reported by the thermal subsystem rather
  than a `junction_temp_throttle - ambient` placeholder. The SC-2
  guard therefore sees real heat soak.
- `Engine.tick` feeds the battery's cell temperature from the thermal
  subsystem's enclosure node instead of a static ambient constant, so
  Peukert + thermal-derate respond to actual case heating.

### Added

- BL-005 thermal subsystem: two-state lumped model (junction +
  enclosure) wired through the engine, with new optional profile
  fields `enclosure_to_ambient_resistance_c_per_w`,
  `junction_heat_capacity_j_per_k`, and `headroom_threshold_c`.
  Adds a `thermal_status` MCP tool and surfaces the thermal estimator
  through `self_estimator_status`. Existing profiles without the new
  fields fall back to sensible defaults.
- Hardening on `deploy/systemd/nous.service`: `ProtectClock`,
  `ProtectHostname`, `ProtectProc=invisible`, `ProcSubset=pid`,
  `RestrictNamespaces`, `RestrictAddressFamilies=AF_UNIX AF_INET
  AF_INET6`, `MemoryDenyWriteExecute`, `RemoveIPC`,
  `KeyringMode=private`, `UMask=0077`, empty
  `CapabilityBoundingSet`/`AmbientCapabilities`, and a
  `SystemCallFilter=@system-service` allowlist with the privileged
  groups (`@privileged @resources @debug @mount @cpu-emulation
  @obsolete @raw-io @reboot @swap`) explicitly denied. Lifted by the
  systemd version Ubuntu 26.04 ships.

### Fixed

- `tests/unit/test_anthropic_client.py` lands as the dedicated
  spine test for `src/nous/anthropic_client.py` (AUDIT.md C1 + H1
  partial, ADR-0005, BL-021). Cap exhaustion, UTC rollover,
  corrupted-state fail-closed, and concurrent multiprocess locking
  via `multiprocessing.Barrier` are all covered. The concurrency
  test pins C1 closed: it fails deterministically against the
  legacy unlock-before-flush ordering and passes deterministically
  against the patched flush-then-fsync-then-unlock ordering.
  `tests/unit/test_call_cap.py` is consolidated into the new file.

- `deploy/systemd/nous.service` now lists `/var/log/nous` in
  `ReadWritePaths=` so the audit log can be written when
  `NOUS_AUDIT_PATH=/var/log/nous/audit.jsonl` (the path the
  cloud-init env file and `deploy/logrotate.conf` already target).
  Previously only `/var/lib/nous` was writable under
  `ProtectSystem=strict`, so the audit sink degraded to stderr on a
  fresh install.

- ``docs/bom.md`` (Bill of Materials) added as the authoritative
  cross-reference for every numeric value in ``profiles/*.yaml``.
  One row per modeled component (battery, compute, solar, fuel
  cell, fuel cartridge, vehicle bus, USB-C PD profile, thermal
  envelope) naming the vendor / product / reference document and
  the profile fields it drives. New numbers land in the BOM
  first, then in a profile. ``AGENTS.md`` and
  ``docs/hardware-profiles.md`` link the BOM as the realism
  source of truth.

- ``BL-005b`` added to the backlog: PMU/PDU subsystem covering
  bus regulation, source arbitration, CC/CV charge profile, and
  dual-slot battery hot-swap. Lifts ``charge_limit_w`` and the
  offered/accepted clamp off ``PowerSubsystem`` onto a new
  ``PmuSubsystem``; supersedes ADR-0015. Dual-slot model:
  primary + secondary battery, PMU arbitrates the active source,
  the inactive slot can be removed without bus collapse.

- Profile values anchored to real spec sheets. Each profile YAML
  now carries a citation header naming the battery, compute,
  solar, fuel cell, and vehicle bus references:
  Bren-Tronics BB-2590/U (296 Wh, 14.4 V) for the Jetson
  profiles, Boston Dynamics Spot battery (605 Wh, 41.6 V) for
  spot-core, SFC EFOY (~0.9 L/kWh, ~25% system efficiency, ~1.4
  Wh/g electrical) for the methanol fuel cells,
  PowerFilm SOL90 / Bren-Tronics MFC class for the solar panels,
  NATO STANAG 4074 for the vehicle tether. ``AGENTS.md`` now
  states the realism rule explicitly so future profile edits
  stay grounded.

- Primary battery model: Li-ion with Peukert correction and thermal
  derate. Subsystem integrates coulomb counting over an effective
  capacity that scales with current and cell temperature; bus
  regulator clips APU-offered charge to ``charge_limit_w`` and
  reports ``charge_offered_w`` vs ``charge_accepted_w``. 1-D Kalman
  filter over (SoC, voltage) with covariance bounds documented in
  the model card. Tracked by `BL-003`.

- APU subsystem expanded to four auxiliary sources: solar PV with
  MPPT, methanol fuel cell, vehicle tether, and USB-C PD-in. Each
  source has scenario-friendly setters
  (``set_solar_insolation_w``, ``set_fuelcell_load_pct``,
  ``set_vehicle``, ``set_usb_c_pd``) plus direct overrides for
  compatibility with the existing ``inject_apu`` scenario action.
  Fuel cell tracks methanol mass and stops at empty;
  ``wh_per_g_fuel`` is derived from ``efficiency * 5.53 Wh/g``
  (methanol LHV) when not explicitly set. The USB-C
  ``default_profile_w`` is run through the PD negotiation at
  construction time. Per-source 1-D Kalman estimator. Tracked by
  `BL-005a`.

- Engine ``tick()`` now wires power and APU through the loop:
  ``apu.step`` -> ``power.set_charge_w(apu.total_w)`` ->
  ``power.step`` -> estimator updates. The compute-driven load and
  thermal cell temperature fall back to profile defaults until the
  compute (`BL-007`) and thermal (`BL-005`) subsystems land.

- MCP tools ``power_status``, ``apu_status``, and
  ``self_estimator_status`` now return real engine values instead
  of placeholder stubs.

- ADR-0015: APU is strictly auxiliary; the primary battery is the
  sole power bus. Compute never draws from an APU source directly.

- New model cards: ``subsystem-power``, ``subsystem-apu``,
  ``estimator-apu``.

- Hardware profile schema extended with the new
  ``power.{voltage_v_min,voltage_v_max,internal_resistance_ohm,
  rated_current_a,thermal_derate_slope_per_c,charge_limit_w}``
  fields and the nested ``apu.{solar,fuel_cell,vehicle,usb_c_pd}``
  blocks. The legacy flat ``apu`` keys are still parsed for
  backward compatibility.

- Self-updating deployment posture: `nous-auto-update.timer` polls
  `origin/main` every 5 minutes and fast-forwards + reinstalls +
  restarts when HEAD advances. New script `deploy/auto-update.sh`
  and systemd units under `deploy/systemd/`. Disable with
  `systemctl disable --now nous-auto-update.timer`.

- OAuth 2.1 authorization-server provider (file-backed DCR + PKCE +
  rotating refresh, single-client lockdown) wired into the FastMCP HTTP
  transport. Caddy carveout for `/authorize` and `/.well-known/oauth-*`;
  set `NOUS_OAUTH_ENABLED=true` and `NOUS_OAUTH_ISSUER=https://...` to
  enable. Tracked by `BL-019`.
- v0.1 scaffold: project layout, governance docs, audited MCP tool
  surface, finite-state machine, tick-loop engine, hardware-profile
  loader, OAuth issuer shape, and typed stubs for subsystems, estimators,
  the self-model, and interop adapters. Tracked by `BL-001`.
