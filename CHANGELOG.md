# Changelog

All notable changes to `nous` land here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added (EMCON rejected-default legibility and MCP-path coverage, BL-104 / BL-105)

- A configured `comms.emcon.default` that named an unknown profile silently fell
  back to `unrestricted`, with no field distinguishing an operator who chose
  `unrestricted` from one whose default was rejected (AUDIT-2026-06-15 M-3).
  `Emcon.status()` (the `emcon_status` / `emcon_set` read) now surfaces
  `default_requested` (the configured name, or null when none was set) and
  `default_valid` (false only when a configured default named an unknown
  profile). Additive and reporting-only: the fall-back-to-unrestricted behaviour
  and `permits` / `active` are unchanged (BL-104).
- The EMCON window-drain and silence-defer proofs exercised `outbox.flush` /
  `encode_and_tx` directly, leaving the `comms_publish` / `comms_flush` /
  `self_model_publish` MCP wrappers (audit, JSON shape, `now_s` injection, the
  `_publish_shape` step) uncovered under those postures (AUDIT-2026-06-15 M-4).
  New integration tests now drive those tools under silence, a duty-cycle window,
  and a minimising posture (BL-105).

### Added (per-cause diagnostics for held and dropped traffic, BL-108)

- The store-and-forward outbox and the DTN mesh each kept a single counter that
  conflated distinct failure causes, so a controller could see traffic was not
  moving but not why (AUDIT-2026-06-15 L-3). Two additive maps now carry the
  cause (ADR 0070). The `comms_outbox` counters gain `defer_causes` (`link_down`,
  `loss`, `emcon`, `no_capacity`), driven by a new `last_tx_reason` the comms
  `tx()` records per link; a deferral is counted once per link per flush, and a
  budget-held package is not a failed attempt and is not counted. The `dtn_mesh`
  counters gain `drop_causes` (`max_hops`, `forward_loss`, `retry_exhausted`,
  `store_overflow`). The existing `attempts`, `dropped`, and `expired` aggregates
  are unchanged. The mesh breakdown is process-local by design: the persisted
  `dropped_total` carries forward across a restart while the split restarts from
  the new process, so no schema change or migration is needed.

### Fixed (DTN persistence: distinguish a load fault from a save fault, BL-101)

- `DtnStore.load()` incremented `save_failures` on a corrupt or unreadable
  restore, so a read fault showed up as a save-shaped `last_error` and a
  controller could not tell the two apart (AUDIT-2026-06-15 M-1). `load()` now
  increments a runtime `load_failures` and records `last_load_error`; `degraded`
  is true on either counter, and the `dtn_mesh` persistence `status()` surfaces
  both pairs additively. Runtime-only fields, no schema change or migration.

### Changed (comms-stack hygiene and performance, AUDIT-2026-06-15 L-1/L-2/M-2)

- Three low-risk audit follow-ons. The store-and-forward outbox dedup is now
  O(1): a `_queued_ids` set parallels the package list, so `_is_duplicate` no
  longer linearly scans on every enqueue (BL-102). Tool bodies that catch an
  exception inside `_work` now return the exception class name via a shared
  `tools/_errors.error_class` helper instead of `str(exc)`, matching the runner's
  escaped-exception redaction so a payload-derived message cannot leak through
  `interop_encode` / `interop_decode` / `comms_publish` / `self_model_publish`
  (or the adjacent `comms_enqueue` hex path) (BL-106). The never-read
  `Engine._wall_start` field and its now-unused `import time` are removed
  (BL-107). The BL-107 proposal to delete the forward-classified
  `inference_request` / `db_reset` / `audit_rotate` names from `policy.py` was
  re-assessed and not done (ADR 0033 keeps them on purpose); a guard test that
  allowlists them now catches a real typo without touching the policy module.

### Documentation (model-card and conformance completeness pass)

- Brought the model cards and conformance posture docs up to the current
  comms-stack feature set. New: a comms subsystem model card
  (`docs/model-cards/subsystem-comms.md`) covering the per-link envelope,
  propagation, the store-and-forward outbox, the DTN mesh, and EMCON; and a
  DTN / BPv7 conformance posture (`docs/conformance/dtn-bpv7.md`) stating the
  RFC 4838 / RFC 9171 behaviour modelled and the wire format omitted (no CBOR
  bundle, no BPSec, BPv6-style custody). Refreshed: the comms particle-filter
  card no longer calls the propagation model absent (BL-048 / BL-088 shipped;
  multi-obstacle DEM is the remaining BL-089); the inference-local-mock card
  drops the stale "inference_cloud not yet registered" note (it is a live T2
  tool); and the sensors and CoT/TAK conformance docs stop citing the done
  BL-056 as an omission. Nav and the model-card index updated for the two new
  pages.

### Fixed (docs + hardware profiles: cross-check against trusted sources, AUDIT-2026-06-15b)

- A documentation and hardware-profile audit (`docs/audit-2026-06-15b.md`) swept
  every code comment, every markdown file, and the profile numbers against vendor
  datasheets and reference data. Documentation drift: LIMITATIONS.md,
  `docs/architecture.md`, and README.md still said "no mesh/DTN, point-to-point"
  after the BL-056 DTN mesh shipped (ADR 0061-0064); SECURITY.md called the daily
  audit anchor "optional" and unshipped when `audit_anchor_verify` is a live T0
  tool (BL-031, ADR 0026); three live docs carried a stale "forty-six" or
  "forty-eight" tool count (the surface is fifty); STATUS.md capped the ADR range
  at 0065 (now 0069); CLAUDE.md's layout omitted `dtn_mesh.py` and `emcon.py`.
  Profile numbers: the pi5-hailo battery was 99 Wh for a 6-cell 18650 pack that
  holds ~55 Wh (the BOM's ~16.5 Wh/cell was arithmetically impossible); the
  BB-2590/U was 296 Wh against a real 294 Wh (and the AGX pack already used
  588 = 2 x 294); the 28 V vehicle bus was mis-cited as STANAG 4074 (it is
  MIL-STD-1275). EFOY nameplate, Hailo-8L power, and BB-2590 weight were corrected
  in the BOM. No schema or behaviour change.

### Fixed (engine: atomic profile reload, BL-103 / ADR 0069)

- `Engine.reload_profile` was committing the new profile and rebuilding the
  subsystems in place, so a malformed section that passed top-level validation
  (for example a non-mapping `comms`) crashed a constructor mid-rebuild and left
  the engine in a mixed-generation state, contradicting the docstring's promise to
  keep the previous profile loaded. The rebuild now constructs every subsystem
  into locals first and commits only once they all succeed, so a malformed reload
  raises with the previous profile and subsystems intact. This was the last HIGH
  finding of the 2026-06-15 audit (H-4).

### Fixed (comms: DTN custody-store bound and restore-loss accounting, BL-098 / BL-100 / ADR 0068)

- The 2026-06-15 audit's three DTN custody gaps are addressed. A node's store is
  now bounded by `dtn.max_store` (default 256): an admit beyond the cap sheds the
  triage-worst held bundle (lowest precedence, newest) and counts it as `dropped`,
  so a stream of unroutable or no-expiry bundles cannot grow memory without bound
  (BL-098), and a low-precedence flood cannot evict a high-precedence custody
  bundle. `restore()` now counts every bundle it skips because the holder node
  left the topology into a `restore_lost` counter on the `dtn_mesh` read, so the
  custody loss is no longer silent (BL-100). The retransmit storm (BL-099) was
  over-stated: per-node dedup already bounds live copies to the node count and the
  persisted `attempts` cap bounds each lineage, and the new store cap makes the
  per-node bound explicit, so no second cap was needed. Migration-free: `max_store`
  is config, the eviction reuses `dropped`, and `restore_lost` is runtime.

### Fixed (comms: EMCON OPSEC remediations from the 2026-06-15 audit, BL-060)

- An adversarial audit pass (`docs/audit-2026-06-15.md`) found and fixed three
  OPSEC-invariant gaps in the EMCON layer. A `comms.emcon` profile named `silent`
  or `unrestricted` could overwrite the built-in posture, so `emcon_set("silent")`
  might still emit; the built-ins are now immutable. Altitude (`hae` / `alt_m`)
  leaked at full precision under a `minimize` posture that coarsened only latitude
  and longitude; `_POSITION_KEYS` now covers the altitude variants. An extreme
  `phase_s` could make a duty-cycle window read permanently closed; the phase is
  now normalised modulo the period. The same pass recorded eleven further gaps as
  BL-098 through BL-108 for their own increments.

### Added (comms: EMCON metadata minimisation, BL-060 / ADR 0067)

- A `minimize` policy on an EMCON profile: `{ position_decimals, drop }`.
  `position_decimals` rounds recognised position fields (`lat`, `lon`,
  `latitude`, `longitude`) to a coarser grid (two decimals is roughly a
  kilometre); `drop` removes named fields from a published payload. The policy is
  applied by `Emcon.minimize` at the `encode_and_tx` publish seam, before the
  interop adapter encodes, so the coarsened mapping is what a restricted posture
  emits (and, if the link is silent, what the outbox holds and later ships). It
  composes with the rest of EMCON: a profile can permit one link, burst on a
  schedule, and coarsen its content at once. `emcon_status` reports the active
  profile's `minimize` policy and the per-profile `minimizers` map. Inert under a
  profile without a policy and the default `unrestricted` posture; the raw
  `comms_send` byte path has no structured content and is untouched. The
  spot-core `low_pi` profile now ships a demonstrative policy (two-decimal grid,
  biometrics dropped). This is increment 3 of BL-060; a first-class denied audit
  record remains.

### Added (comms: EMCON scheduled emission windows, BL-060 / ADR 0066)

- A duty-cycle emission `window` on an EMCON profile: `{ period_s, on_s, phase_s }`
  permits the profile's links only inside a scheduled burst (`on_s` open out of
  every `period_s`) and silences them between bursts. The window is evaluated at
  the same `CommsSubsystem.tx` seam against the injected `now_s` sim clock, so a
  send offered between bursts is held in the BL-077 store-and-forward outbox and
  ships on the next open burst, with no new plumbing. `emcon_status` reports the
  active profile's `window` and whether it is `emitting` now, plus the per-profile
  `windows` map. A window registers only as a genuine duty cycle (`0 < on_s <
  period_s`); a malformed or always-open window is ignored, so a misconfiguration
  cannot silently black-hole traffic. The `window` key is an additive extension of
  the `comms.emcon` schema, inert for an unwindowed profile; the spot-core profile
  ships a demonstrative `lte_burst` window. This is increment 2 of BL-060;
  metadata minimisation and a first-class denied audit record remain.

### Added (comms: EMCON emission control with store-and-forward triage, BL-060 / ADR 0065)

- An emission-control posture layer. EMCON is an orthogonal, operator-imposed
  posture (like the operator and comms states): a set of named emission profiles,
  each listing the comms links permitted to emit, with one active at a time.
  `unrestricted` (all links) and `silent` (none) are always present; further
  profiles come from an optional `comms.emcon` profile section. `emcon_status`
  (T0) reads the posture and `emcon_set` (T2) changes it. The gate sits at the
  single `CommsSubsystem.tx` seam, so when a profile forbids a link every path
  (direct send, interop publish, the BL-077 outbox flush) declines to emit. A
  silenced `comms_send` / `comms_publish` / `self_model_publish` is held in the
  store-and-forward outbox (tagged `emcon_deferred`) rather than dropped, and the
  tick-driven drain ships the backlog once the posture is lifted, closing the
  loop with the BL-056 triage layer. Inert without a `comms.emcon` section and
  under the default `unrestricted` profile, so every existing profile is
  unchanged; the spot-core profile ships a demonstrative `low_pi` profile. This
  is increment 1 of BL-060; metadata minimisation and burst windows follow.

### Added (comms: DTN store persistence across a restart, BL-056 / ADR 0064)

- Increment 4 of the DTN layer, the replay increment, completing BL-056. The
  mesh store (every node's held bundles, the bounded dedup ledgers, the
  disposition counters, and the next sequence) is now checkpointed to the
  `state.db` SQLite database after a mutating tick and restored whenever a fresh
  `DtnMesh` is built, so in-flight and in-custody bundles survive a process
  restart or a hot reload, not just a link drop. A new `DtnStore` wrapper
  persists a `DtnMesh.snapshot()` through two tables (`dtn_bundles` relational,
  `dtn_meta` single-row) behind an Alembic migration; writes are best effort and
  degrade silently like the FSM transition log, carrying only the exception
  class. Restore rebases each bundle's lifetime to its remaining TTL so a clock
  reset on a true restart preserves the remaining lifetime. The `dtn_mesh` read
  gains a `persistence` block. Inert without a `dtn` profile section and in the
  memory-only mode, so every shipped profile is unchanged.

### Added (comms: DTN contact-graph routing and an explicit custody ack, BL-056 / ADR 0063)

- Increment 3 of the DTN layer. Routing moves from the increment-2 hop-count
  shortest path to contact-graph routing: a `Contact` carries an optional
  schedule (`start_s` / `end_s`), and each held bundle is routed along the
  earliest-arrival path over the time-windowed contact graph that still meets its
  deadline, so a bundle moves toward a node where a future contact will open and
  waits there rather than being held in place. Custody transfer now models a
  separately-lossy acknowledgement (`ack_loss_pct`, default zero): a lost ack
  makes the previous custodian retain and retransmit, and the duplicate that
  creates is deduplicated per node on the bundle id (a bounded recent-id ledger,
  the ADR 0061 pattern), so a guaranteed
  bundle survives a lost ack as a deduplicated duplicate rather than a silent
  second delivery. With `ack_loss_pct` at zero and no contact schedules the mesh
  behaves exactly as increment 2, so the change is additive and inert without a
  `dtn` profile section. The `dtn_mesh` read adds a `deduped` counter, the
  acknowledgement-loss fraction, and each contact's window. Replay on reconnect
  follows.

### Added (comms: multi-node DTN mesh with custody transfer, BL-056 / ADR 0062)

- A delay-tolerant-networking overlay above the BL-077 outbox: a configured graph
  of nodes (the device as the `self` node plus abstract hold-and-forward peers)
  connected by contacts, from a new optional `dtn` profile section. `dtn_send`
  (T2) originates a bundle at the device toward a destination EID; the tick loop
  routes it hop by hop over the shortest path on the currently-up contact
  subgraph (one hop per tick), storing it at each hop while a contact is down.
  Custody transfer is the reliability distinction: a custodial bundle is retained
  and retransmitted on a lost forward (a Bernoulli draw on the contact loss, the
  ADR 0019 RNG seam) up to a retry bound, while a best-effort bundle is dropped;
  a bundle past its lifetime expires. `dtn_mesh` (T0) reads the topology, per-node
  holdings, in-transit bundles, and the disposition counters. The mesh is inert
  without a `dtn` profile section, so existing profiles are unchanged. This is
  increment 2 of BL-056 (the multi-node model chosen over a device-centric one);
  intermittent-contact routing and replay follow.

### Added (comms: BPv7 bundle identity and dedup for the DTN layer, BL-056 / ADR 0061)

- The store-and-forward outbox (BL-077) now stamps every queued package with a
  BPv7-shaped bundle identity: a source EID (the device's node EID, `dtn://<profile
  name>/` by default, overridable via `comms.node_eid`), a destination EID
  (`comms.peer_eid` or a per-`comms_enqueue` `dest_eid`, default
  `dtn://controller/`), a creation sequence, and a `bundle_id`, with the existing
  TTL serving as the bundle lifetime. A bounded delivered-bundle ledger makes
  `comms_enqueue` idempotent: pass an explicit `bundle_id` and a re-submission
  whose id is still queued or recently delivered is refused as a duplicate
  (counted, not an error). An unkeyed enqueue gets a unique auto-id and behaves
  exactly as before, so the change is additive. This is the first increment of
  the DTN layer (BL-056); multi-hop custody transfer, mesh routing, and replay
  follow. The `comms_outbox` read surfaces the node and peer EIDs and the dedup
  counter; each package's `bundle` block carries the identity.

### Added (docs: generate the MkDocs ADR nav with a drift gate, BL-097)

- A new `scripts/gen_mkdocs_adr_nav.py` regenerates the `mkdocs.yml` ADR nav
  block from each ADR's H1 (the source `gen_adr_index.py` already uses), between
  `# BEGIN/END generated ADR nav` markers, wired into `make schema` and the docs
  workflow. The 2026-06-14b audit (DOC-1) found the hand-maintained nav had
  drifted to list only ADRs 0000 through 0017, and a page absent from the nav is
  only an INFO line under `mkdocs build --strict`, so CI never caught it.
  `tests/unit/test_docs_nav.py` is the drift gate the strict build cannot be: it
  runs on every PR, asserting the ADR block is generator-current and that every
  `docs/**/*.md` page is in the nav or on the dated-logs / showcase-gallery
  exemption list. Generating from each H1 also normalised the 0001 through 0017
  nav labels, which had been hand-abbreviated, to their full ADR titles.

### Documented (policy: inference_local stays T1 despite its usage counters, BL-096 / ADR 0060)

- `inference_local` is T1 (reversible), yet it increments monotonic
  `local_calls` / `total_tokens` / `total_energy_j` counters that nothing undoes.
  The 2026-06-14b audit (LOW-2) asked whether that side effect warrants T2; the
  deliberate decision is to keep it T1. Those counters are pure accounting with
  no feedback into battery or thermal physics (so unbounded calls exhaust no
  modelled resource), `tick_advance` already advances the whole clock
  monotonically under T1, and local inference is the fallback that must stay
  admittable in guarded mode, the posture used when comms are degraded (whereas
  `inference_cloud` is correctly T2: it spends the daily cap and makes an
  external call). No behaviour change: a comment on the `_REVERSIBLE_TOOLS`
  membership records the rationale. Recorded in ADR 0060 and pinned as the
  `TestLow2` regression class (ADR 0023).

### Documented (comms_state: CONNECTED keeps its all-configured-links meaning, BL-095 / ADR 0059)

- `comms_state.derive` reports CONNECTED only when every configured link is
  connected and healthy, so a dark or aged-out backup caps the report at LIMITED.
  The 2026-06-14b audit (M-3) asked whether this should relax to "all
  currently-connected links healthy"; the deliberate decision is to keep the
  conservative meaning, because a profile's link inventory is the redundancy the
  top-line label should reflect, and the alternative would make CONNECTED mean
  only "the link I happen to have up is fine". No behaviour change: the
  CONNECTED-vs-LIMITED distinction is reporting-only (the `REQ_COMMS_LINK` gate,
  the engine link-mode auto-degrade, and the self-model situation read all key on
  DENIED), and `derive` is unchanged beyond a clarifying comment. Recorded in ADR
  0059 and pinned as the `TestM3` regression class (ADR 0023).

### Changed (estimators/interop: read rejections through health, stringify decode keys, BL-094 / ADR 0058)

- `position_status` / `sensors_status` / `biometrics_status` now read
  `rejected_updates` from the estimate's health block (`estimate.health`) rather
  than a bare `est.rejected_updates` attribute, so a future Protocol-conforming
  estimator that omits the attribute no longer breaks the T0 read (the Estimator
  Protocol stays at three methods, per ADR 0045). The biometrics and sensors
  reads now include innovation-gate rejections in the count, not just
  input-validation rejections, matching what the position read and the
  self-model already reported (unchanged at zero when nothing is gated). And
  `interop_decode` stringifies every mapping key recursively before
  `json.dumps`, so a non-string-keyed payload (a future CBOR / msgpack adapter,
  or any exotic key `json.dumps` would reject) decodes to valid JSON instead of
  an exception body; MISB's integer tag keys serialise exactly as before. Pinned
  as the `TestMed3` and `TestLow4` regression classes (ADR 0023).

### Changed (scenarios: tick_advance reports an honest, breaking tick count, BL-093 / ADR 0057)

- **BREAKING CHANGE:** `tick_advance`'s result drops the `ticks_advanced` field
  and replaces it with `ticks_requested` (the ticks this call stepped) and
  `ticks_elapsed` (the net engine advance, `state.tick - start_tick`). The former
  `ticks_advanced` was set to the requested count `n`, but the call yields to the
  event loop every 50 ticks and the concurrent tick loop can fire its own
  `engine.tick()` during the yield, so the engine's `tick` / `ts_s` advanced by
  more than `n` and a caller computing `start_ts + n*dt` disagreed with the
  reported `ts_s`. `ts_s` now tracks `ticks_elapsed`; the advance itself is
  unchanged. Renaming a field on the MCP tool surface is a breaking change under
  ADR 0007, authorised here by ADR 0057. Pinned as the `TestMed2` regression
  class (ADR 0023).

### Fixed (inference: reuse the Anthropic client and name a cap durability fault honestly, BL-092 / ADR 0056)

- `inference_cloud` built a fresh `AnthropicClient` per call, churning the httpx
  pool and discarding the prompt-cache token metric. `Nous` now builds one client
  eagerly in its constructor (from its own settings), and the tool reuses it, so
  one pool serves the process and `last_cache_read_input_tokens` stays observable
  (the dead `build_client()` global, which read the wrong settings, is left in
  place but superseded). And `CallCap.increment` raised `CapExhausted` on an
  `os.fsync` failure, so a transient durability fault read to a controller as a
  spent budget; it now raises a distinct `CapPersistError`, the fallback ladder
  reports it as `cap not persisted` while still failing closed to the local mock,
  and the cache-control markers in `call` are untouched.

### Fixed (comms: propagation-link correctness fixes, BL-091)

- Four contained fixes to the BL-048 / BL-088 propagation code, all additive and
  low-blast. `CommsSubsystem.tx` no longer reports bytes "accepted" on a
  zero-capacity link (a propagation link driven below its SNR floor): it returns
  0 and stamps the zero achieved rate rather than claiming a delivery a dead link
  cannot make (H-1). The comms particle filter refreshes a link absent from the
  current observation each update instead of freezing its estimate after the
  first absence (H-2). The filter's `LinkEstimate` now carries the rated
  `bandwidth_bps`, so `comms_state` uses the per-link capacity fraction rather
  than the legacy flat throughput floor for the informational estimator read
  (M-1). The connected-likelihood floor check is `<` rather than `<=`, so a link
  exactly at the 1 bps floor is processed, matching the liveness boundary
  elsewhere (M-2). The FSM-facing comms state is unchanged; covered by additive
  unit tests across the comms subsystem, outbox, and estimator suites and pinned
  as the `TestH1` / `TestH2` / `TestM1` / `TestM2` regression classes (ADR 0023).

### Fixed (runner: redact the caught-exception body so a backend error cannot leak credentials, BL-090 / ADR 0055)

- The audited runner returned a caught worker error to the MCP caller as
  `[error <class>: <message>]` with the raw exception string, only truncated,
  never redacted. A database failure on a read-only call (`state_get` /
  `state_history` reach the database) raises an exception whose message can
  embed the `NOUS_DB_URL` data source, host, user, and password, so an admitted
  read-only caller could read a credential out of an error body. The body now
  carries the exception class only (`[error <class>]`); the full `class: message`
  is echoed to stderr for an operator with host access, mirroring the
  `device_info` persistence handler (BL-078). The ADR 0048 `exit_code` / `denied`
  audit contract is unchanged, and the audit record only ever stored the body's
  SHA-256. Pinned by a regression in `tests/regression/test_audit_findings.py`.

### Added (comms: higher-fidelity propagation, BL-088 / ADR 0054)

- Five additive, opt-in upgrades to the BL-048 link budget in
  `subsystems/propagation.py`, each defaulting to reproduce the ADR 0053
  free-space budget so a link that does not opt in is byte-for-byte unchanged: a
  log-distance path-loss exponent (the environment, not just free space), a
  single knife-edge diffraction loss for a discrete terrain obstruction (ITU-R
  P.526, no DEM needed), a kTB thermal-noise floor when a channel bandwidth is
  configured, a directional antenna pattern keyed on the bearing to the peer, and
  a Rician multipath fast-fade draw on top of the log-normal shadowing.
- `solve_link_budget` gains one optional `fast_fade_db` argument (the second
  stochastic draw); the other four upgrades read from `LinkPropagation`.
  `subsystems/comms.py` draws the fade in `_apply_propagation` and is otherwise
  unchanged, so the observation to filter to `derive` to FSM pipeline and the
  whole existing suite are untouched. The net effects surface through the same
  `comms_status` diagnostics (a blocked link shows a higher path loss, a wider
  channel a lower SNR). Covered by `tests/unit/test_propagation.py` and
  `tests/integration/test_propagation_demo.py`. DEM-driven multi-obstacle terrain
  is split out to BL-089; mesh routing stays in the BL-056 DTN layer.

### Added (comms: propagation-aware link quality, BL-048 / ADR 0053)

- A comms link with a `propagation` block now solves its RSSI, packet loss, and
  SNR-derived capacity each tick from a first-order link budget instead of
  holding the profile's static nominal: a Friis free-space path loss over the
  slant range from the device position to the link's peer, a constant
  excess-loss margin for terrain and obstruction, and a log-normal shadowing
  draw from the engine RNG. A new `subsystems/propagation.py` holds the pure
  link-budget functions; the result feeds the existing `rssi_dbm` / `loss_pct`
  fields, so the unchanged observation to particle-filter to `derive` to FSM
  pipeline degrades on its own as the device moves away from its peer. Device
  position enters through a lazy `position_fn` seam that mirrors the `rng=`
  injection.
- The four couplings the earlier ADRs deferred land with the model. `tx` caps
  the achieved rate at the SNR-derived `capacity_bps` (supersedes the ADR 0051
  bandwidth cap; realizes the ADR 0020 throughput-monotone-in-SNR invariant).
  `comms_state.derive` gates link health on a per-link fraction of each link's
  own bandwidth rather than the flat 5000 bps. The comms particle filter uses
  the modeled capacity as its expected throughput, so an observed rate far below
  capacity now weighs against the connected hypothesis. The store-and-forward
  flush models per-link Bernoulli packet loss on a propagation link (amends
  ADR 0047).
- The model is additive and inert without config: `LinkEstimate` gains optional
  `bandwidth_bps` / `capacity_bps`, a static link's capacity is its rated
  bandwidth, and every new channel carries a legacy fallback, so all existing
  comms, estimator, outbox, and scenario tests are unchanged. `comms_status`
  surfaces the range, path loss, SNR, and capacity behind a link's quality.
  Demonstrated by `profiles/propagation-demo.yaml` and
  `tests/integration/test_propagation_demo.py`. The forced-state override and
  the `inject_comms_loss` / `set_link_state` seam still hard-override the physics.

### Fixed (self-model: Monte Carlo `p50` is the sample median, not the deterministic point, BL-087)

- Each capability's Monte Carlo branch in `self_model/assess.py` computed the
  5th, 50th, and 95th percentiles from the sample but published
  `Capability.p50 = point` and discarded the sample median (audit 2026-06-14
  ASSESS-1), so a band mixed sampled tails with a deterministic centre. The
  three branches (endurance, thermal headroom, inference capacity) now bind
  `p5, p50, p95 = _quantiles(samples)` and publish the empirical median,
  lighting up the previously dead `_quantiles` helper. The Gaussian fallback,
  whose median equals its mean, still reports the deterministic point as `p50`,
  so the v0.1 contract is unchanged for `mode="gaussian"`. The p5 and p95 clamps
  that bracket the point are kept, so the band still contains the point; only
  the centre changed. Low-blast and additive (no ADR): `cap.p50` is
  display-only, the FSM-facing `last_capabilities` snapshot reads `cap.point`,
  so no admission or transition path moves. This closes the last open finding of
  the 2026-06-14 audit. Pinned by `tests/unit/test_self_model.py`.

### Fixed (interop: name the freshness gate's config fault distinctly from staleness, BL-086 / ADR 0052)

- `assert_fresh` (`interop/base.py`) reported a fabricated `0.00s old` age when an
  adapter's `max_age_s` was invalid (non-positive or NaN), so the error blamed a
  brand-new estimate for a refusal that was really a configuration fault (audit
  ITP-1). `StaleEstimateError` gains an optional `reason`; the gate now resolves
  the source timestamp and real age first, then on an invalid `max_age_s` raises
  with that real age and a reason naming the misconfiguration. It stays a
  `StaleEstimateError`, so the fail-closed catch in the interop and publish tools
  is unchanged, and the genuine-staleness message is byte-for-byte unchanged
  (`reason` defaults to `None`). FRESH-1 (`resolve_ts` returns `ts_s=0.0`
  verbatim) is documented as by-design: `0.0` is a valid sim epoch, so the
  requirement is clock consistency between `ts` and `now_s`, now spelled out on
  `resolve_ts` rather than enforced. High-blast surface, so behind ADR 0052; the
  change is additive (the `reason` field) with no Protocol change. Pinned by
  `tests/unit/test_interop_adapters.py`.

### Changed (comms: link throughput is an achieved rate, not a packet size, BL-085 / ADR 0051)

- `CommsSubsystem.tx` recorded `throughput_bps = n_bytes * 8`, the bit count of
  the last packet, on a field consumed as a rate (audit 2026-06-14 COMMS-3).
  `comms_state.derive` gates a link healthy on `throughput_bps > 5000`, so a
  large packet read as healthy and a small one as degraded regardless of the
  actual rate. `throughput_bps` is now an achieved rate: the bits sent over the
  interval since the link last transmitted (`link.age_s`), capped at the link
  bandwidth, with a first-send / zero-interval fallback to the link capacity
  rather than a divide by zero. The flat 5000 bps `comms_state` threshold is
  unchanged but now compares a genuine rate, and the value bounds at the link
  capacity. Behind ADR 0051 because it reaches the FSM-facing comms state,
  though `subsystems/comms.py` is not a high-blast surface. No estimator-test
  churn (the filter sets `expected = max(observed, floor)`, so it is
  scale-insensitive) and no existing test pinned the old bit count. Pinned by
  `tests/unit/test_comms_subsystem.py`.

### Added (comms: stamp the link age-out so the transition is legible, BL-084)

- A comms link aging out is no longer silent (audit 2026-06-14 COMMS-2). When a
  link crosses `max_age_s` in `CommsSubsystem.step`, a genuine live-to-aged-out
  transition (gated on `is_live()`, so a link that went stale while forced down
  is not miscounted when the override clears) now stamps a cumulative
  `age_out_count` and a `last_aged_out_at_s` on the link, both surfaced through
  `comms_status`, and emits a structured
  `nous.comms` log line at the moment. The count is cumulative, so a controller
  polling `comms_status` detects a link that aged out and recovered between
  polls rather than only seeing the current state. Additive and low-blast: the
  age-out physics (the `connected` and throughput flip) is unchanged, the
  estimator path (`link_estimates` / `comms_state`) is untouched, and a
  controller-forced disconnect is not counted as an age-out. Covered by
  `tests/unit/test_comms_subsystem.py`.

### Changed (estimators: make the comms log-throughput sigma an explicit constant, BL-083)

- Simplified the comms particle filter's connected-likelihood z-score (audit
  2026-06-14 COMMS-4). It normalized the log-throughput residual by a divisor
  `sigma / max(expected, 1.0)` in which `sigma` itself was
  `_THROUGHPUT_OBS_SIGMA_FRAC * max(expected, 1.0)`, so the two
  `max(expected, 1.0)` terms always cancelled and the divisor was the constant
  `_THROUGHPUT_OBS_SIGMA_FRAC` for every link. The dead `sigma` intermediate is
  removed and the residual is divided by `_THROUGHPUT_OBS_SIGMA_FRAC` directly,
  with a comment noting it is the constant log-space observation sigma, not a
  scale-dependent one. Exactly behaviour-preserving (the cancellation was
  algebraic); the particle filter and its convergence are untouched. Pinned by
  `tests/unit/test_comms_estimator.py`
  (`test_connected_likelihood_depends_only_on_log_ratio`). The remaining LOW
  audit findings were dispositioned by review (TICK-1 intentional per ADR 0036,
  DOC-3 backlog text already accurate); see `docs/audit-2026-06-14.md`.

### Documented (audit: chain head tracks the on-disk tail, BL-082 / ADR 0050)

- Recorded the invariant that `AuditLogger`'s hash-chain head tracks the on-disk
  tail, not the fsync confirmation (audit 2026-06-14 AUD-1). The finding first
  proposed gating the head advance on a clean fsync; that is the hazard, not the
  fix. `_FsyncingFileHandler` writes the line into the append-only log before it
  fsyncs, so an fsync-failed record is physically present, and gating the head
  would make the next record skip it and break `verify_chain`. `write` is
  reordered so the fsync-state poll runs before the (still unconditional) head
  advance, with the invariant in a comment so no future change re-introduces the
  bug; durability stays tracked separately via `degraded` / `fsync_failures` /
  the fsync-gated `writes_total` and the BL-031 daily anchor. No behaviour
  change. High-blast surface, so behind ADR 0050. Pinned by
  `tests/regression/test_audit_findings.py` (`TestAud1ChainHeadTracksOnDiskTail`),
  which proves the chain survives a silent fsync failure and fails under the
  gate-on-fsync variant.

### Fixed (inference: cap status fails closed on a corrupt counter, BL-081 / ADR 0049)

- `anthropic_cap_status` no longer advertises a healthy cap when the daily
  counter file is corrupt (audit 2026-06-14 CAP-1). `CallCap.increment` (the
  spend path) raised `CapExhausted` on a corrupt counter, but `CallCap.peek`
  (the status path) returned `(0, cap)` on the same file, so the T0 tool
  reported the cap fully available at the instant every `inference_cloud` call
  was being silently downgraded to the local mock. Both readers now parse
  through one `_parse_count` helper, so they cannot drift: a corrupt counter
  makes `peek` return a `CapReading` with `corrupt=True`, and the tool reports
  `available: false` / `exhausted: true` / `corrupt: true` /
  `count_today: null`. `increment` also fails closed uniformly, rejecting a
  malformed `count` (a non-integer or negative value) where it previously
  coerced it or leaked a raw `ValueError`. High-blast
  surface (`anthropic_client.py`), so behind ADR 0049; `peek` returns
  `CapReading` rather than a tuple (four in-repo call sites updated), while
  `increment` keeps its tuple. Pinned by `tests/unit/test_anthropic_client.py`,
  `tests/unit/test_anthropic_status.py`, and
  `tests/regression/test_audit_findings.py`.

### Changed (audit: exit_code on the runner's caught-exception path, BL-080 / ADR 0048)

- The audited runner now stamps `exit_code=1` on a caught worker exception, so
  an audit consumer can tell it apart from a normal return on the typed field
  rather than the `[error ...]` body prefix (audit 2026-06-14 RUN-1). The M1 fix
  had stamped `exit_code=1` on the policy-denial path and assumed `exit_code is
  not None` would bucket denials and worker errors apart from normal returns,
  but the exception path left `exit_code=None`, identical to a normal return.
  The contract is now two-valued: `None` is a normal return, `1` is any abnormal
  outcome, and the `denied` flag separates a policy refusal (`denied=True`) from
  a caught error (`denied=False`). Four lines in `runner.py`; the body mapping,
  truncation, redaction, and BL-016 hash chain are untouched. High-blast
  surface, so behind ADR 0048. Pinned by `tests/unit/test_runner.py` and
  `tests/regression/test_audit_findings.py`.

### Fixed (engine: restart the safety law on profile reload, BL-079)

- `Engine.reload_profile` rebuilt every subsystem and estimator but left the
  `FailsafeArbiter` debounce streaks and `state.last_capabilities` intact (audit
  2026-06-14 RLD-1), so a streak part-way to an auto-safe carried across a
  reload onto a profile that may define a different threshold, and a read taken
  between the reload and the next tick saw capability claims computed from the
  old profile's physics. The reload now rebuilds the arbiter for fresh streaks
  and recomputes the capabilities from the rebuilt estimators, so both restart
  against the new physics. Engine-local and additive (the ADR 0044 failsafe
  contract is unchanged; the `SafetyEnforcer` violation counters stay cumulative
  by design). Pinned by `tests/unit/test_profile_hot_reload.py`.

### Fixed (persistence: surface state-DB health in device_info, BL-078)

- A failed `init_db` at server start was swallowed silently, leaving the
  state-transition history memory-only with no signal anywhere (audit
  2026-06-14 DB-1). `StateTransitionLog` now takes an optional `init_error`
  that separates the intentional memory-only mode (the pure-Python engine)
  from a failed init, exposes a `degraded` property and a `status()` read, and
  `server.py` captures the failure reason and echoes it to stderr the way the
  audit sink does. `device_info` gains a `persistence` block (`persistent`,
  `degraded`, `init_error`, `append_failures`, `last_error`) so an operator who
  misconfigures `NOUS_DB_URL` sees a degraded sink instead of discovering it
  from an empty `state_history`. The surfaced error fields carry only the
  exception class, not the message, so a connection string with credentials
  cannot leak through the T0 `device_info` read; the full detail goes to stderr.
  Additive and low-blast (`db.py`, `server.py`, `tools/meta.py`); pinned by
  `tests/unit/test_state_transition_log.py` and
  `tests/integration/test_persistence_status.py`.

### Added (comms: store-and-forward outbox with precedence triage, BL-077 / ADR 0047)

- Outbound traffic now survives a degraded or denied link. The 2026-06-14 audit
  (finding COMMS-1) confirmed the send seam was fire-and-forget: `comms_send`,
  `comms_publish`, and `self_model_publish` all drop a transmission the moment
  the link cannot carry it, so a publish during an outage encoded a full message
  and discarded it (validated on the live twin, a 352-byte CoT event lost on a
  denied link). A new `src/nous/state/comms_outbox.py` adds a bounded,
  precedence-ordered `CommsOutbox` the engine owns beside the comms subsystem.
  Queued packages carry military message precedence (routine, priority,
  immediate, flash) and a time-to-live; a flush walks them by descending
  precedence then enqueue order, a package is only ever evicted to make room for
  a strictly higher-precedence one, and an expired package is dropped rather than
  shipped stale (the store-and-forward analogue of the SC-4 freshness gate). The
  engine drains the outbox each tick at each link's modelled per-tick capacity,
  so a recovered narrow link clears its backlog at its real rate.
- Three tools join `tools/subsystems.py` beside the comms reads: `comms_enqueue`
  (T2, raw `n_bytes` or a `payload_hex` blob), `comms_outbox` (T0, depth plus
  per-precedence and per-link breakdown, head package, and disposition
  counters), and `comms_flush` (T2, forced triage-ordered drain). Additive
  policy classification only; the tool surface grows from 43 to 46. An optional
  `comms.outbox` profile section (`enabled`, `max_packages`, `max_bytes`,
  `default_ttl_s`) tunes the bounds, defaulting safely when absent. Pinned by
  `tests/unit/test_comms_outbox.py`, `tests/integration/test_comms_outbox_tools.py`,
  and a regression in `tests/regression/test_audit_findings.py`. Deliberately
  single-hop and below the full DTN layer (BL-056); LIMITATIONS L12 updated.

### Fixed (audit 2026-06-14)

- The `inference_fallback` module docstring now names the DEGRADED comms route
  it always took to the local mock (audit DOC-1). STATUS.md tool and test counts
  reconciled to the current surface (DOC-2). The remaining adversarial findings
  (audit chain-head versus fsync ordering, the cap status fail-open, the silent
  database-init degradation, the failsafe streak carry-over on reload, and the
  runner exception `exit_code`) are recorded in `docs/audit-2026-06-14.md` for
  their own dedicated changes.

### Changed (FSM: first-class failsafe action framework, ADR 0044)

- The tick-loop auto-safe is now a declarative table behind a pure arbiter
  (ADR 0044, BL-076). A new `src/nous/state/failsafe.py` holds a
  `FailsafeCondition` (id, severity, debounce ticks, decay, preferred and
  fallback triggers) and a `FailsafeArbiter` that debounces the raw-active
  condition set each tick and selects the highest-severity tripped condition,
  the way PX4 separates its `FailsafeBase` framework from the concrete
  `checkStateAndMode`. Hysteresis is now a per-condition property: the arbiter
  decays an inactive streak by one per clear tick rather than resetting it, so
  a sustained-but-flapping condition still accrues toward firing instead of
  handing back the whole grace period on a single-tick blip. The engine keeps
  the detectors (operator label from every mode, the device hazards through the
  enforcer with power short-circuiting thermal, the comms label scoped to the
  link modes), feeds the arbiter, and fires one transition per tick exactly as
  before. Behaviour is preserved: the device and comms conditions stay
  instantaneous, the operator condition keeps its three-tick window (now with
  anti-toggle), the severity order reproduces the previous
  operator-over-power-over-thermal-over-comms priority, and recovery stays
  controller-gated (the one-way posture of ADR 0029). The `_SAFING_RULES` table
  and the bespoke `_operator_incap_streak` counter are gone. Pinned by
  `tests/unit/test_failsafe_arbiter.py` and an engine-level flap test in
  `tests/unit/test_fsm_auto_safe.py`.

### Changed (FSM: declarative mode-requirements gate, ADR 0046)

- Operational-mode entry now gates on the full precondition set, the same flags
  the auto-safe reads on exit (ADR 0046, BL-075). Beyond the existing SC-2
  thermal and SC-8 power gates, all four IDLE to operational entries require an
  available operator, and the link modes (RELAY, C2) additionally require a live
  comms link, so a controller can no longer enter a relay posture into a dead
  link, or a mission with the operator incapacitated, and have it degrade only
  on the next tick. A new categorical enforcer evaluator, `forbid_value`, backs
  the operator and comms gates; both reuse the `label:` constraint ids the
  auto-safe records, so an entry refusal and an auto-safe firing on the same
  condition land under one `constraint_id` in the audit trail (those auto-safe
  decisions stay label-driven, so the enforcer counter reflects entry
  refusals). The device hazards stay first in the gate
  order, so the SC-2 / SC-8 refusal messages are unchanged; the recover and cool
  transitions out of an impaired mode keep their thermal and power gates only.
  Pinned by `tests/unit/test_fsm_requirements_gate.py`.

### Added (estimators: innovation gating and health, ADR 0045)

- Innovation gating and a health surface for the scalar Kalman estimators
  (ADR 0045, BL-074). A shared primitive, `ScalarChannel` in
  `src/nous/estimators/health.py`, centralises the per-channel recursion every
  estimator open-coded and adds the diagnostics PX4's EKF2 publishes: a
  normalised innovation squared gate (`test_ratio = innovation^2 /
  (gate_sigma^2 * S)`, a reading above the gate is rejected), a signed,
  exponentially weighted test ratio so a persistent bias is legible before it
  trips the gate, a posterior-variance floor so a converged belief stops
  reporting the false-certainty zero (the position filter's lat/lon variance
  no longer collapses to `0.0`), and a counted reset that adopts a sustained
  shift after `reset_after` rejections rather than fighting it forever. A
  channel seeds through the gate on its first fusion.
- `Estimate` gains an optional `EstimatorHealth` block (`healthy`, `fused`,
  `dead_reckoning`, `rejected_updates`, `reset_count`, and the per-channel
  `test_ratio`, `test_ratio_filtered`, and `innovation`). `self_estimator_status`
  now serialises it, so the tool finally delivers the divergence flags its
  description always promised. The `Estimator` Protocol (`predict` / `update` /
  `state`) is unchanged: health rides inside the returned `Estimate`, so every
  consumer that reads only `point` and `covariance` is unaffected. The comms
  particle filter reports a compatible block from particle-weight collapse, and
  the position filter raises `dead_reckoning` when it coasts without a fix.
  Pinned by `tests/unit/test_estimator_health.py`.

### Changed (engine lifecycle: start completes to IDLE, ADR 0039)

- `Engine.start()` now drives `STOWED -> BOOT -> IDLE` (ADR 0039, BL-070)
  instead of parking in the transient `BOOT`. Completing boot is plant
  behaviour: the `ready` edge is ungated, so the engine fires it on start, while
  the gated operational entries from `idle` (mission / relay / monitoring / c2)
  stay controller-driven and the terminal `fault` / `shutdown` triggers stay on
  their own tools. An unattended deployment now rests in the `idle` standby
  posture, so `device_health` reads `idle` after an auto-update restart rather
  than `boot`. Both bring-up transitions are logged. The scenario runner drops
  its now-redundant post-start `ready` step; the FSM transition table is
  unchanged. Pinned by a new `test_engine_start_completes_to_idle` plus updated
  smoke / restart / `state_transition`-tool tests.

### Added (self-model: situational awareness, ADR 0038)

- Situational-awareness fusion (ADR 0038, BL-061). `self_model_situation` (T0)
  is the one-call tactical picture: `src/nous/self_model/situation.py` reuses
  the `assess` capability claims (so the headline numbers match
  `self_model_assess`) and layers on each claim's provenance (the backing
  estimator's source and its staleness), the FSM posture (mode plus the
  operator and comms labels, with a one-word summary), the `SafetyEnforcer`
  violation posture, and a short ranked list of degraded-mode recommendations
  ordered to mirror the engine's auto-safing priority. Staleness (`age_s`) is
  the literal estimator clock lag and the live trust signal stays the
  covariance-derived `confidence`; the recommendations are advisory, not a
  safety gate (the enforcer remains the only authority that refuses or clamps).
  The tool surface grows from thirty-six to thirty-seven; the existing
  self-model tools are untouched. Covered by
  `tests/unit/test_self_model_situation.py` and
  `tests/integration/test_self_model_situation_tool.py`. The old BL-061
  cross-references to the position EKF / IMU-fusion track are re-pointed to
  BL-026, removing a backlog double-booking.

### Changed (framing: simulation-based digital twin)

- The project describes itself consistently as a *simulation-based* digital
  twin of an edge-AI inference appliance: a model driven by per-subsystem
  physics and recursive estimators, not a hardware-linked twin. README, the
  docs site, and the governance files lead with that framing so the scope
  stays honest about what the artefact is and is not.

### Added (migrations: project-standard runner, ADR 0037)

- Schema migration runner (ADR 0037, BL-051). `scripts/migrate.py` is the
  project-standard entry point for Alembic migrations: it builds the config
  from `alembic.ini`, pins `script_location` to `alembic/`, and targets the
  engine's own `Settings.resolved_db_url()` (`NOUS_DB_URL` or the `$NOUS_HOME`
  sqlite default), then dispatches `upgrade` / `downgrade` / `current` /
  `history` / `revision` / `stamp` through `alembic.command`, so a migration
  hits the same database the server reads with no URL to remember. Alembic
  stays the source of truth; `init_db` remains a first-boot convenience. The
  path is pinned by `tests/integration/test_migrations.py` (a fresh-sqlite
  upgrade / downgrade round-trip that drives the runner directly), and the
  workflow is documented in `docs/deployment.md` and an AGENTS.md recipe.

### Added (observability: tick-loop OTel metrics, ADR 0036)

- Tick-loop instrumentation (ADR 0036, BL-037). `src/nous/telemetry.py` adds
  two OpenTelemetry instruments built from the OTel API alone: a
  `nous.tick.duration` histogram (seconds, with the FSM mode as an attribute)
  and a `nous.tick.overruns` counter. `tick_loop` records the elapsed time each
  tick and increments the counter on an over-budget tick. The runtime depends
  only on `opentelemetry-api`, whose instruments are no-ops until a
  `MeterProvider` is configured, so the default footprint and behaviour are
  unchanged; an operator opts in by launching under `opentelemetry-instrument`
  (standard `OTEL_*` env vars). Metrics, not a span per tick, because the loop
  runs at 2 Hz. The SDK is a dev dependency only, driving the in-memory reader
  the test asserts against (no exporter, no network in CI).

### Added (inference: enrich the cloud call, ADR 0035)

- Cloud-call enrichment (ADR 0035, BL-069). `AnthropicClient.call` gains
  model-tier selection (`tier` resolves to `anthropic_model_default` /
  `anthropic_model_advanced`; an explicit `model` still overrides), adaptive
  thinking that is capability-guarded (sent only on a thinking-capable model,
  so the default Haiku 4.5 tier never receives a block it would reject), and
  streaming via `messages.stream` + `get_final_message` for generations above
  `_STREAM_OVER_TOKENS`. Both paths run under `with_options(timeout=...)` and
  extract only text blocks, so an adaptive-thinking block never leaks into the
  answer; the response's `usage.cache_read_input_tokens` is surfaced on
  `last_cache_read_input_tokens`. `inference_cloud` exposes the tier as a
  validated tool parameter (default on an unknown value). No sampling
  parameters are sent (the 4.x families reject them), and the slot discipline
  and daily cap (ADR 0005) are unchanged. The SDK is faked in tests so CI makes
  no real call; the tool surface stays at thirty-six tools.

### Added (tool surface: posture, terminal, comms, and cloud inference)

- Posture control (ADR 0031, BL-066). `state_transition` (T2) registers the
  FSM write seam `Engine.request_transition`, so a controller can drive the
  mission posture directly (`ready` -> `idle`, then `mission` / `relay` /
  `monitoring` / `c2`, or the recoverable `safe` hold) instead of only through
  `scenario_inject`. Operational entries stay SC-2 / SC-8 gated; the terminal
  `fault` / `shutdown` triggers are refused here and reserved for the T3 force
  tools. Covered by `tests/integration/test_state_transition_tool.py`.
- Terminal control (ADR 0032, BL-067). `state_force_fault` and
  `state_force_shutdown` (T3, no arguments) register the reset-only FAULT /
  SHUTDOWN postures through the audited surface, resolving the dangling
  reference ADR 0031 left. Recovery stays on the T2 path (`reset` -> STOWED ->
  `boot`). Covered by `tests/integration/test_state_force_tools.py`.
- Comms control (ADR 0033, BL-068). `comms_send` (record a transmission of N
  bytes on a link, resetting the age-out timer) and `comms_publish` (encode a
  message via an interop adapter and account its bytes on the link) register the
  two comms write seams that already had engine support. ADR 0033 also records
  the disposition of every remaining classified-but-unregistered name, closing
  the 2026-06-06 audit's finding F. Covered by
  `tests/integration/test_comms_tools.py`.
- Cloud inference (ADR 0034, BL-013). `inference_cloud` (T2) registers the
  cloud path: the SC-5 fallback ladder routes to the capped `AnthropicClient`
  and degrades to the local mock when the cap is exhausted, comms are down, or
  the call fails, so a controller always gets an answer. Call enrichment
  (adaptive thinking, streaming, model-tier selection) is tracked as BL-069.
  Covered by `tests/integration/test_inference_cloud_tool.py`. Across these
  additions the registered surface grows from thirty to thirty-six tools.

### Added (safety: FSM actuation and uniform fault reachability, ADR 0029 / 0030)

- FSM actuation, neutral recovery, and fail-closed robustness (ADR 0029).
  Entering `SAFE`, `LOW_POWER`, or `THERMAL_LIMIT` now caps the compute
  subsystem's delivered load through `ComputeSubsystem.set_mode_load_ceiling`
  (composing with the thermal-throttle ceiling), so auto-safing to `LOW_POWER`
  genuinely sheds load and slows the drain it was named for. `recover` and
  `cool` now target the neutral `IDLE` rather than `MISSION` (the controller
  re-selects the operational mode, re-gated), removing the silent
  `RELAY -> MISSION` collapse. The operator-incapacitation auto-safe is
  debounced over three consecutive ticks, so a single estimator spike no longer
  forces a one-way `SAFE`.
- Uniform fault reachability (ADR 0030). Adds the three missing failsafe edges
  (`THERMAL_LIMIT` / `LOW_POWER` / `SAFE` to `FAULT`), so `FAULT` is reachable
  in exactly one ungated `fault` trigger from every powered mode (the table
  grows from 47 to 50 transitions, purely additive). The reachability suite
  gains `test_failsafe_edges_are_never_gated`, turning the prose-only "no
  failsafe edge is gated" claim into a build-breaking assertion.

### Documented (STPA coverage, estimator model cards, reserved audit mirror)

- STPA derived requirements and coverage report (BL-044). Artefact 09 now
  carries a derived requirement for every safety constraint (new DR-11 through
  DR-14), and a new `docs/stpa/11-coverage.md` traces every loss end to end
  (Loss -> Hazard -> SC -> UCA/LS -> DR) and names the test that pins each
  enforced requirement. Pinned by a new band-widening test in
  `tests/unit/test_self_model.py`.
- Estimator model-card coverage (BL-050). Every estimator now carries a card
  under `docs/model-cards/` (power SoC, APU per-source, thermal, compute,
  storage, environmental sensors, biometrics, the comms particle filter, and
  the position Kalman filter), each reachable from the docs nav, the
  model-cards index, and the capability matrix.
- Reserved SQLite audit mirror (BL-065). The `audit_entries` table is recorded
  as reserved, not live: the JSONL sink stays the single authoritative audit
  trail (BL-016 hash chain plus BL-031 daily anchor). ADR 0002 carries a
  2026-06-05 update with the decision and its revisit trigger; pinned by
  `tests/unit/test_audit_entries_reserved.py`.

### Added (safety: FSM hardening, ADR 0022 / 0027 / 0028)

- Runtime safety enforcer (ADR 0022). `src/nous/safety/enforcer.py` turns an
  STPA constraint into an observable runtime artefact: every check returns a
  structured `SafetyResult` (approved, value, was_clamped, violation_type,
  evidence), and the enforcer keeps per-constraint and total violation
  counters. The FSM entry gates route through it: SC-2 (thermal headroom)
  and SC-8 (power reserve) refuse a transition into any operational mode
  (MISSION/RELAY/MONITORING/C2), failing closed on missing context. A new
  audit-only `Tier.SAFETY` classification and an optional `safety` field on
  the audit record mirror every check; `device_info` surfaces the violation
  posture. SC-8 and hazard H-8 were added to the STPA artefacts.
- Condition-driven auto-safing (ADR 0027). `Engine.tick` drives the FSM
  toward a safer mode when a constraint is violated mid-run, closing the
  "sustains" half of H-2/H-8 that the entry gate alone could not cover. The
  move is one-way (recovery stays controller-gated, so there is no
  oscillation to debounce); every auto-safing decision is mirrored under
  `Tier.SAFETY` and recorded with an `auto-safe:` reason.
- FSM failsafe reachability and label-driven safing (ADR 0028). Every
  operational mode gains a direct `safe` edge and RELAY/MONITORING/C2 gain a
  `fault` edge, so every operational or impaired mode reaches SAFE in one
  trigger; the invariant is checked exhaustively in
  `tests/unit/test_fsm_reachability.py`. Mode classification helpers
  (`is_operational`/`is_impaired`/`is_terminal`) land in `state/machine.py`.
  Auto-safing gains the label-driven conditions: operator `INCAPACITATED`
  takes the full `safe` posture (outranking the device hazards) and comms
  `DENIED` degrades the link-bearing modes (`RELAY`/`C2`).
  `docs/stpa/10-fsm-constraints-mapping.md` traces every safety-relevant
  transition to its constraint and hazard.

### Changed (server: per-subsystem tool modules, ADR 0021)

- The MCP tool handlers moved out of `server.py` into per-capability modules
  under `src/nous/tools/` (meta, audit, state, subsystems, self_model,
  inference, interop, scenarios). Each exposes a `register(mcp, app, wrap)`
  seam; handler bodies and the registered tool surface are byte-faithful, so
  the move is behaviour-preserving. `server.py` is now engine/FastMCP wiring
  plus the eight `register` calls.

### Added (audit: daily anchor, ADR 0026)

- The audit hash chain gains a daily anchor (ADR 0026, BL-031): the chain
  head is anchored once per UTC day, so tail truncation (which the chain
  alone cannot detect) becomes detectable across days. `device_info` reports
  the anchor path and degraded state, and an `audit_anchor_verify` (T0) tool
  exposes the check to a controller.

### Added (audit: tamper-evident hash chain)

- The audit JSONL is now a per-record hash chain (ADR 0025, BL-016).
  Each line carries `prev_hash` and `entry_hash`, so the chain head is
  a fingerprint of the whole history; `AuditLogger` recovers the head
  from the file tail on restart so the chain survives a process bounce.
  A module-level `verify_chain` walks a file and reports the first
  broken link, and a new T0 `audit_verify` MCP tool plus a `chain_head`
  field on `audit_summary` expose it to a controller. The chain detects
  in-place mutation and mid-stream deletion, insertion, or reordering;
  tail truncation needs the BL-031 daily anchor. The change is additive
  (ADR 0007): existing readers ignore the new fields and pre-chain lines
  verify as a legacy prefix.

### Fixed (server: engine ran per request under stateless HTTP)

- The engine tick loop ran on the FastMCP server lifespan, which under
  `stateless_http=True` executes once per request: the live server
  rebooted the engine on every tool call (`reset -> boot -> one tick ->
  shutdown`), pinning `device_health` at `tick: 1` / `mode: boot` and
  churning the `state_transitions` table. The engine lifecycle is now
  process-scoped (ADR 0024): `build_app()` exposes the engine and the
  FastMCP without a server-lifespan tick loop, and `nous serve` attaches
  `tick_lifespan` to the process ASGI lifespan (`attach_tick_lifespan`
  for HTTP; a `tick_lifespan` wrap of `run_stdio_async` for stdio).
  `stateless_http=True` is retained, so the claude.ai connector is
  unchanged. Tracked as BL-064.

### Fixed (deployment: install.sh self-install aborted every auto-update)

- `deploy/install.sh` installed `deploy/auto-update.sh` onto itself when
  `REPO_DIR=/opt/nous` (the production layout): source and destination
  were the same file, so `install` exited non-zero ("are the same file")
  and, under `set -e`, aborted the deploy after `git reset` had advanced
  `HEAD` but before the service restart. This was the underlying cause of
  the stale-build freeze on `nous-prod-01` (the service ran the initial
  deploy's code while `HEAD` silently advanced). The step now chmods the
  script in place when source and destination are the same file, and only
  copies it for a non-`/opt/nous` `REPO_DIR`. Tracked as BL-063.

### Fixed (deployment: auto-update stale-build freeze)

- `deploy/auto-update.sh` no longer leaves `HEAD` advanced past a failed
  deploy. It used to `git reset --hard origin/main` before `install.sh`
  and the service restart, so a failed install left the working tree on
  the new commit while `nous.service` kept running the old code; the next
  tick then computed `LOCAL == REMOTE` and exited as a no-op, freezing the
  box on the stale build with no marker. The critical section now runs
  under an EXIT trap that rolls `HEAD` back and reinstalls the previous
  good artifacts (units and venv, which a git reset alone does not undo);
  it records the commit in `last_failed` only when a freshly-restarted
  build fails its health check, so a transient install or network failure
  is not blacklisted and the still-running previous service is left
  untouched. The rollback resets `HEAD` before any fallible logging (and
  `log` is best-effort), so a full disk that makes the audit log
  unwritable cannot abort it. Regression-pinned by
  `tests/integration/test_auto_update_rollback.py`.
  Tracked as BL-063; the live `nous-prod-01` resync and the AUDIT N2
  degraded audit sink it should clear remain the open server-side action.

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
