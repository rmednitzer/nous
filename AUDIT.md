# AUDIT

> **Superseded for current state by [`docs/audit-2026-05-23.md`](docs/audit-2026-05-23.md).**
> This document is preserved as the 2026-05-20 baseline; consult the
> 2026-05-23 audit for which findings closed, which remain open, and
> for the live-MCP probe results.

Point-in-time repository audit of `nous` against Python, FastMCP, OAuth
2.1, OGC/MISB/NMEA/CoT, and STPA-Pro best practices. The audit covers
governance, the spine (policy / audit / runner / server / engine /
anthropic_client / state machine), subsystem physics and estimators,
interop adapters, the OAuth issuer, deployment, tests, CI, scripts, and
the documentation tree.

Conducted: 2026-05-20.
Branch audited: `claude/repo-audit-best-practices-fHVFy` against `main`.
Source revision baseline: `a2d0ed4` ("Merge pull request #19 from
rmednitzer/claude/review-deployment-docs-00r88").

## 1. Executive summary

`nous` is a v0.1 alpha simulator that is unusually well-governed for its
maturity. The audit invariants (output hashing, append-only JSONL,
SHA-256 only, redaction allowlist), policy tier discipline, FSM design,
prompt-cache discipline, single-client OAuth lockdown, REUSE 3.x
compliance, BOM-grounded profile sourcing, and the model-card / ADR /
STPA tree are all done correctly and conservatively. Documentation is
internally consistent, honest about uncertified posture, free of
em-dashes per the CI ban, and every ADR follows the project template.

The audit found no privilege-escalation, no remote-code-execution, and
no audit-bypass classes of bug. The most material defects are narrow:
(1) a race window between the daily-cap counter's write and its flock
release in `anthropic_client.py`, (2) flat (non-recursive) argument
redaction in `audit.py`, (3) the engine starts but no tick task is
scheduled by the server so `state_history` is frozen at boot, (4) the
file-backed OAuth store has no inter-handler lock and no enforced 0600
file mode, (5) several interop adapter stubs encode malformed output
(MISB key truncation, CoT missing required attributes, incomplete NMEA
GGA), and (6) three "high blast radius" spine modules
(`runner.py`, `state/machine.py`, `anthropic_client.py`) have no
dedicated unit tests. Each of these maps to a v0.1 stub or a documented
phase-L1/L2 commitment, but the audit recommends that several be
remediated *before* L1 lands rather than treated as part of L1.

The CI grep claims advertised in `CLAUDE.md` (em-dash ban,
private-repo-reference ban) are not actually enforced by
`.github/workflows/ci.yml`; the repository happens to pass them by
authorial discipline. The biggest deployment risk is the auto-update
loop pulling `origin/main` every five minutes onto the live VM with
the `nous-auto-update.service` running as root and unhardened: this is
documented as intentional but lacks a written kill-switch / rollback
procedure tied to `SECURITY.md`.

Overall: the project is approximately where `STATUS.md` says it is.
The L0 scaffold lands cleanly and the governance discipline is the
strongest part of the codebase. Stubs are clearly marked, but several
behave too plausibly (returning realistic-looking zeros or
not-actually-filtered observations) and risk being mistaken for working
implementations by a controller that reads their output.

## 2. Severity legend

| Severity | Meaning |
|----------|---------|
| **Critical** | Correctness, security, or audit-invariant violation. Should land before the next release. |
| **High** | Real defect or architectural smell that will bite in L1. Plan to fix within a phase. |
| **Medium** | Idiom, hardening, or completeness gap. Triage and fix opportunistically. |
| **Low / Nit** | Stylistic or documentation polish. |
| **Strength** | Done well; called out so it survives future refactors. |

## 3. Critical findings

### C1. Daily-cap counter unlocks before the buffer is flushed

`src/nous/anthropic_client.py:53-77`. `CallCap.increment()` opens
`$NOUS_HOME/.anthropic_daily_count` in `"a+"` mode, takes an exclusive
`fcntl.flock`, mutates the JSON state, writes via `fh.write(...)`, then
releases the lock in the `finally` block. The file is only flushed when
the `with` statement exits, which is *after* the lock has been
released. A second process holding the lock immediately after release
can therefore read the stale (pre-flush) file content and double-count
the same day, breaching the daily-cap invariant documented in
ADR-0005 and `LIMITATIONS.md L4`.

Recommendation: flush and `os.fsync()` *before* releasing the flock.
Move the unlock out of the `finally` block, or restructure so the
buffer is flushed inside the lock:

```python
fh.write(json.dumps(state))
fh.flush()
os.fsync(fh.fileno())
fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
```

This module is on the "no change without an ADR" list. Treat the fix
as a one-line correctness patch and reference ADR-0005 in the commit
message; no new ADR required.

### C2. Argument redaction is shallow

`src/nous/audit.py:49-65`. `redact()` walks the top-level keys of the
argument mapping only. A caller that passes
`{"context": {"headers": {"Authorization": "Bearer ..."}}}` writes the
secret to the audit log verbatim, because the regex only inspects the
*key* at the outer level. The redaction allowlist (`authorization`,
`cookie`, `token`, `password`, `secret`, `api[_-]?key`, `bearer`) is
otherwise well-chosen, so the fix is to recurse:

```python
def redact(args: Mapping[str, Any]) -> dict[str, Any]:
    def walk(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                k: _REDACT_PLACEHOLDER if _REDACT_KEYS.search(k) else walk(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [walk(v) for v in value]
        ...
```

The current MCP tool surface accepts only top-level scalar arguments,
so the immediate blast radius is small, but the fix is required before
any tool accepts structured payloads (e.g. `interop_encode` in L1).

### C3. Engine starts but is never ticked by the server

`src/nous/server.py:48` calls `self.engine.start()` once in
`Nous.__init__`, but no FastMCP lifespan hook schedules
`nous.tick.tick_loop()`. As a consequence the live HTTP/stdio server
reports a frozen engine: `state_history`, `power_status`, and
`apu_status` only ever return the boot snapshot. The standalone CLI
`tick` subcommand can drive `engine.tick()` manually, but the public
server cannot.

Recommendation: introduce a FastMCP lifespan context that starts a
background task running `tick_loop(engine, hz=settings.tick_hz, stop)`
and cancels it on shutdown. While doing so, also call `engine.stop()`
in the shutdown branch so the FSM lands on `shutdown` rather than
leaking the running state. This is the canonical fix for both the
"never ticks" and the "engine.stop() never called" issues and should
ship with the L1 subsystem rollout.

### C4. MISB KLV encoder silently truncates keys and lengths

`src/nous/interop/misb_klv.py:27-28`. The TLV helper hard-bitwise-ANDs
the key and length to one byte. MISB ST 0601 local-set tags can exceed
255 (BER-OID multi-byte tags), and value lengths over 255 require
BER length encoding. The current encoder will produce malformed frames
for any value over 255 bytes and silently mis-encode any high-byte key.
A KLV parser will either reject the frame or, worse, misinterpret it.

Even as a "stub" this is unsafe because the `interop_formats` tool
advertises the adapter and a controller could call `interop_encode`
expecting standards-compliant output. Either implement BER-OID
properly or raise `NotImplementedError("MISB KLV ST 0601 BER-OID
encoding lands with BL-032")` for inputs that would overflow.

### C5. Stub estimators advertise covariance they never compute

`src/nous/estimators/thermal.py`, `src/nous/estimators/compute.py`.
`ThermalKalman.update()` and `ComputeKalman.update()` simply copy the
observation payload into the state; `state()` returns a static
`covariance={"junction_c": 1.0, "ambient_c": 0.25}` (etc.) that was
chosen at construction and never updated. There is no innovation, no
gain, no covariance evolution. Any controller reading
`self_estimator_status` will see a plausible covariance and believe
the estimator is filtering. This is the most dangerous shape a stub
can take: a working interface returning misleading values.

Recommendation: either implement a one-state Kalman in the same shape
as `PowerEstimator` (the bar is low; it would be ten lines) or have
the stubs return `covariance={"_stub": True}` with a clearly invalid
sentinel so a downstream consumer can tell the difference. The same
note applies to `self_model/assess.py:29-44` and
`self_model/viability.py:24`, which return point/p5/p50/p95 all set to
`0.0`: distinguish "unknown" from "zero endurance" by returning
`None` or a sentinel rather than a numeric 0.

### C6. CI does not enforce the em-dash or private-repo grep

`.github/workflows/ci.yml:38-39` only runs `make check`, and `make
check` (Makefile:32) is `lint typecheck test`. `CLAUDE.md` claims "the
CI grep checks both" (em-dashes in markdown and private-repo
references). It does not. The repository currently passes by authorial
discipline, but the next contributor who introduces an em-dash will
not be told. This is the only place in the audit where the gap between
documented and actual posture matters.

Recommendation: add a `policy` job to `ci.yml`:

```yaml
- name: Policy greps
  run: |
    ! grep -rPn '\x{2014}' --include='*.md' .
    ! grep -rn 'internal-repo-name' .
```

Use a script under `scripts/policy_checks.sh` for cleanliness and
include any other prose rules (`No emoji in source files`, `No bare
TODOs in shipped docs`, etc.).

## 4. High findings

### H1. Three spine modules have no unit tests

`tests/` has no `test_runner.py`, no `test_machine.py` (FSM), and no
`test_anthropic_client.py`. These are three of the eight modules
`CLAUDE.md` lists as "do not change without an ADR." `runner.py`
(85 LOC) covers tier classification, admission, truncation, exception
mapping, and audit writes for every tool call. `state/machine.py`
encodes the entire mission posture. `anthropic_client.py` enforces the
daily cap and prompt-cache discipline.

Recommendation: add at minimum:

* `tests/unit/test_runner.py` -- parametrized over the four tiers and
  three policy modes; assert that audit records are written on both
  the success and denial paths; assert exception-to-body mapping
  preserves the exception class name; assert truncation kicks in at
  the configured `max_output`.
* `tests/unit/test_state_machine.py` -- a small property-based test
  using `hypothesis` that walks the transition table and asserts that
  `transition()` raises `ValueError` for unknown triggers, that
  history records every step, and that `can()` agrees with
  `transition()`.
* `tests/unit/test_anthropic_client.py` -- exercises `CallCap` only
  (no SDK call): cap exhaustion, UTC rollover, concurrent locking
  (use `multiprocessing` to verify the flock semantics), corrupted
  state file recovery.

These three test files are the highest-leverage testing work in the
repo right now.

### H2. `mypy --strict` does not cover tests

`pyproject.toml:101` sets `files = ["src/nous"]`, so the test tree is
not type-checked. Several test files declare fixtures with
non-trivial types, and any test that mocks the `runner` or the
`audit` record will silently drift. Add the test tree once the test
suite is sufficient to compile under strict mode (today it likely
needs a relaxed override for fixture decorators).

### H3. CoT adapter omits the required event attributes

`src/nous/interop/cot.py:16-25`. CoT/TAK 2.0 events require `time`,
`start`, `stale`, and `how` attributes; the encoder emits only
`version`, `uid`, and `type`, plus a point element with all accuracy
fields set to `"0"`. A TAK server consuming this frame will display
the unit but have no time-to-live (stale immediately) and no
confidence to render. The current implementation is fine for the
v0.1 round-trip smoke test, but the `docs/conformance/cot-tak.md`
"Conformance claim: None" sentence does not absolve the encoder from
producing well-formed XML.

Recommendation: even at stub maturity, write the four required
timestamps from the engine clock and set `how="m-g"` (machine, GPS)
as a sane default. Derive `ce`/`le` from `PowerEstimator` /
`PositionEKF` covariance bounds once those land (L1).

### H4. SensorThings encoder does not normalise timestamps to UTC

`src/nous/interop/sensorthings.py:21`. `phenomenonTime` is taken
verbatim from `data.get("ts")`. OGC SensorThings v1.1 §6.5 requires
an ISO 8601 instant or interval with explicit timezone. The encoder
should parse, validate, and serialise to `YYYY-MM-DDTHH:MM:SS.ffffffZ`
(matching `audit._now_iso`'s format). Add `Datastream` and `result`
type validation while the file is open: an Observation without a
`Datastream@iot.navigationLink` reference is not interoperable.

### H5. NMEA encoder ships an incomplete GGA sentence

`src/nous/interop/nmea0183.py:20`. The body has eight comma-separated
fields; a complete `$GPGGA` has fourteen (UTC, lat, NS, lon, EW,
quality, satellites, HDOP, MSL altitude, M, geoid separation, M,
DGPS age, DGPS station). The current sentence will fail strict
parsers; pynmea2 will accept it but report missing fields as `None`.
The XOR checksum implementation is correct.

Recommendation: emit a fully-specified GGA and parameterise the
talker ID (`GP`, `GL`, `GN`, `GA`, `GB`).

### H6. OAuth file store has no inter-handler lock and no chmod 0600

`src/nous/auth/oauth.py:52-69`. `_Store.save()` writes via tmp file
plus `Path.replace()`, which is atomic on POSIX but does not fsync
the directory and does not enforce file mode. The directory is
created `0750 nous:nous` by `deploy/install.sh:40`, so the files end
up owned by the `nous` user with whatever the umask gives (default
`0022` → `0644`). For a single-tenant VM this is fine, but defence in
depth would `chmod 0600` after every write and `os.fsync()` the
written file plus the parent directory before the rename. Concurrent
FastMCP requests can also interleave `load()` and `save()` because
there is no lock around the read-modify-write cycle of token /
client / code state. Under the single-client lockdown deployment the
practical risk is low; under the planned multi-tenant L3 work it
becomes a real race.

Recommendation: add an `_async_lock = asyncio.Lock()` inside
`FileOAuthProvider` and wrap every `_Store.load() ... _Store.save()`
sequence inside the lock. Add a `chmod(0o600)` after the rename, and
fsync the parent directory once per write.

### H7. Refresh-token rotation has no family revocation

`src/nous/auth/oauth.py:247-257`. `exchange_refresh_token()` deletes
the old refresh token and issues a fresh access+refresh pair. OAuth
2.1 BCP §4.13 requires that refresh tokens be one-time-use, *and* that
detected reuse revoke the entire token family for the client. The
current implementation revokes the consumed token but leaves any
parallel refresh tokens issued earlier in the chain alive. If an
attacker captures a refresh token *and* the rightful client then uses
it, the attacker's parallel chain continues to mint access tokens
silently.

Recommendation: track an `issue_id` on every refresh token grouping
the entire chain, and on reuse / collision wipe every record sharing
that id. Add an integration test under
`tests/integration/test_oauth_rotation.py`.

### H8. Auto-update runs `git reset --hard` as root every five minutes

`deploy/auto-update.sh:41` does `git reset --hard "${REMOTE}"` and then
`bash install.sh`, all as root, every five minutes via
`nous-auto-update.timer`. `deploy/systemd/nous-auto-update.service`
correctly notes that root is required (it touches `/etc/systemd`,
`/var/log/nous`, and restarts the service unit), but the unit has no
hardening and the script has no rollback. If a commit lands on
`main` that breaks `install.sh` or the new `nous.service`, the timer
will retry every five minutes for the same broken commit until a
human intervenes.

This is documented as intentional in `docs/deployment.md`, but the
audit recommends two cheap improvements: (1) capture the prior commit
SHA before `git reset --hard` and write it to
`/var/log/nous/auto-update.last_ok` only after `systemctl is-active`
returns success; (2) add a `[Service]` `Restart=no` and a
`SuccessExitStatus=0` line so a hard failure does not loop. The
kill-switch (`systemctl disable --now nous-auto-update.timer`) should
appear in `SECURITY.md` alongside the supported-versions table.

### H9. Inference placeholders missing from profile YAML

`profiles/jetson-agx-orin.yaml:71-72`. `tok_per_s_p50: 200` and
`energy_j_per_tok: 0.12` have no source comment. The same pattern
applies to the other three profiles in the repository. AGENTS.md
requires that "every battery capacity, panel rating, fuel-cell
consumption rate, compute envelope, inference benchmark, etc." trace
to a vendor datasheet or MLPerf number, with a citation comment at
the top of each profile YAML. The inference numbers are the only
values currently in violation of that rule.

Recommendation: mark these values explicitly:

```yaml
inference_local:
  # PLACEHOLDER until BL-043 (real local model under TensorRT-LLM /
  # llama.cpp). See docs/bom.md, "Inference benchmark" section.
  tok_per_s_p50: 200
  energy_j_per_tok: 0.12
```

`docs/bom.md` already notes that these are placeholders; the comment
needs to propagate to the YAML so the next contributor reading the
profile in isolation sees it.

## 5. Medium findings

### M1. `runner.py` denial path omits the `reason` field from the audit record

`src/nous/runner.py:55-67` writes a denial audit record but does not
populate `AuditRecord`'s `exit_code` and embeds the policy reason
inside the body string only. Adding `exit_code=1` (or a dedicated
`denied=True` plus `reason: str` field) makes the audit log
machine-queryable without parsing the body, which matters when the
operator wants to count denials per tier per day.

### M2. Caddy template ships TLS defaults

`deploy/Caddyfile.example` sets HSTS (`max-age=31536000;
includeSubDomains`), `X-Content-Type-Options`, `Referrer-Policy`, and
strips `Server`, but does not pin TLS version (Caddy 2.x defaults to
1.2+), and the HSTS line omits `preload`. For an OAuth 2.1 issuer
host, recommend an explicit `tls { min_version tls1.3 }` block, and
adding `preload` once the operator is willing to register at
`hstspreload.org`.

### M3. `audit.py` swallows all sink errors silently

`src/nous/audit.py:144`. `with contextlib.suppress(Exception):` around
`self._log.info(...)` is correct (audit failure must not block a tool
call) but the operator has no way to learn that audit is degraded
*after* construction (the `degraded` flag only flips on initial open).
Recommendation: track per-write degradation in a counter and expose
it via `audit_summary` (already in the read-only tool list).

### M4. systemd hardening: `ProtectClock` missing on `nous.service`

`deploy/systemd/nous.service`. The unit applies most modern Linux
sandbox knobs but omits `ProtectClock=true` and
`SystemCallFilter=@system-service`. Neither is required, but both
align with the project's defence-in-depth posture and cost nothing.
`ProtectKernelLogs=true` is also worth adding.

### M5. OAuth access TTL defaults to one hour

`src/nous/config.py:69`. `oauth_access_ttl=3600` is fine for a
long-lived bearer in a single-client lockdown deployment but is on
the high end for OAuth 2.1. Recommend documenting in `SECURITY.md`
the rationale (single-client, refresh rotation present) and noting
that a tighter 300-900 s default is appropriate for any future
multi-tenant deployment.

### M6. CoT type code hard-coded to `a-f-G-U-C`

`src/nous/interop/cot.py:22` always emits `type="a-f-G-U-C"`
(affiliation: friendly, dimension: ground, entity: unit, modifier:
combatant). A simulator is more honestly modelled as friendly
equipment (`a-f-G-E-V`) or, when used in a defensive context, as a
sensor (`a-f-G-S-E`). Either parameterise from `data.get("type")` or
adjust the default and document the choice in
`docs/conformance/cot-tak.md`.

### M7. Alembic versions tree is empty

`alembic/versions/.gitkeep`. There are no migrations checked in,
which is consistent with v0.1 booting against
`SQLModel.metadata.create_all()` but means the first schema change
will need a baseline migration written by hand. Recommend landing an
empty "0001 baseline" migration ahead of the first schema change so
the upgrade path is testable from the moment a real migration lands.

### M8. `engine.tick()` is not directly tested at the unit level

`tests/integration/test_apu_charges_battery.py` exercises one engine
tick path. There is no unit test that asserts `engine.tick()`
increments `state.tick`, advances `state.ts_s` by `dt_s`, and feeds
both estimators. The current pass rate is fine, but a regression in
the tick wiring will only fail an integration test.

### M9. `tests/conftest.py` engine fixture starts but does not deliver tick state

The `engine` fixture (`tests/conftest.py:32`) calls `eng.start()` and
then yields. A test that wants ticked state must call `eng.tick()`
itself. Recommend adding a second fixture, `running_engine`, that
emits a known number of ticks before yielding, so tests that need a
non-trivial state machine history do not duplicate setup.

### M10. Profile YAML has no JSON-schema validation at load time

`src/nous/engine.py:159-167`. `_load_profile()` returns whatever
`yaml.safe_load` produces. A typo in a key (`peukert_k` →
`peukart_k`) silently degrades to the default. `scripts/gen_schemas.py`
already generates JSON schemas; wire them into the loader so a bad
profile fails fast at startup (per `config.py`'s own discipline).

## 6. Low / nits

### L1. `_now_iso` replaces `+00:00` with `Z` via string substitution

`src/nous/audit.py:42`. Works but fragile. `datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")` is a touch clearer.

### L2. FSM history list is unbounded

`src/nous/state/machine.py:80,97`. For long-running servers the list
will grow without limit. A `collections.deque(maxlen=4096)` would cap
it. Not a real issue today.

### L3. `examples/self_driving_demo.py` should advertise its own daily-cap awareness

The demo is the canonical entry point for new users; it should print
the daily-cap remaining count on startup and re-route to
`inference_local` automatically when exhausted.

### L4. CI does not pin minor versions

`.github/workflows/ci.yml:33` pins Python `"3.12"` but lets the patch
version float. For reproducibility under uv resolution, consider
pinning Python via `astral-sh/setup-uv@v7`'s `python-version` input
(supported in v7) and a `.python-version` file at the repo root.

### L5. CI does not run security scanners

No `pip-audit`, `safety`, `bandit`, or `reuse lint` step. Each takes
under a minute and is appropriate for an alpha project that ships a
public-facing OAuth issuer.

### L6. CODEOWNERS is single-line

`.github/CODEOWNERS` is `* @rmednitzer`. Fine for a pre-1.0 single
maintainer project; consider per-path entries (e.g. the spine files
under separate review) before opening to outside contributors.

### L7. CHANGELOG entries cite ADRs but not BL-NNN

Most ADRs in `docs/adr/` cross-link the backlog; `CHANGELOG.md`
should follow the same discipline so a reader can trace a shipped
behaviour back to the backlog item that motivated it.

### L8. Skills do not declare their MCP tool dependencies

`skills/nous-getting-started.md` reads cleanly but does not state
which tools the runbook will call. A controller pre-checking
permissions against the policy mode benefits from a one-line
"Required tier" header in each skill.

### L9. `interop/mqtt.py` has no `docs/conformance/mqtt.md`

The conformance tree covers seven adapters but not MQTT. Even at
"None" maturity, a one-page doc declaring the QoS policy, retained
behaviour, last-will, and topic ACL is useful.

### L10. `examples/inspector_quickstart.md` is markdown but lives next to a `.py` example

Either rename to `inspector_quickstart.py` (stub) and link the
markdown from there, or move it under `docs/` so the examples
directory is exclusively runnable code.

## 7. Strengths

### S1. Audit discipline is enforced end-to-end

`src/nous/runner.py` routes every tool call through the audit sink;
`src/nous/audit.py` only ever stores SHA-256 plus byte length, never
the body; `deploy/install.sh:52` applies `chattr +a` to make the log
append-only on ext4; `deploy/logrotate.conf` rotates the log without
breaking the append-only invariant. This is the right shape for an
auditable simulator and very few projects at v0.1 get it this clean.

### S2. Policy tiers are explicit and conservative

`src/nous/policy.py:115-132` returns `Tier.REVERSIBLE` for any
unclassified tool. The four frozenset-backed tables are reviewable in
one screen. The decision function (`decide()`) is pure and side-effect
free. ADR-0001 explains the why; the code matches.

### S3. Hand-rolled FSM is easier to review than a library

`src/nous/state/machine.py:33-72` is a flat dict of allowed
transitions. Unknown triggers raise `ValueError` rather than no-op
silently. ADR-0004 documents the choice; the code matches.

### S4. Prompt-cache discipline is correct

`src/nous/anthropic_client.py:100-139` places the system prompt and
all trusted context blocks in the `system=[...]` slot with explicit
`cache_control={"type": "ephemeral"}`, and routes untrusted user
input to the user message. This is the correct Anthropic prompt-cache
pattern for the Claude SDK and matches ADR-0005 plus the
`claude-api` skill's guidance.

### S5. Hardware profile sourcing

`profiles/jetson-agx-orin.yaml:8-14` reads as a paragraph of
citations: BB-2590/U battery, Jetson AGX Orin 64GB envelope, PowerFilm
SOL90, SFC EFOY methanol fuel cell, STANAG 4074 vehicle bus. The
in-line citations on `solar.mppt_efficiency`,
`fuel_cell.wh_per_g_fuel`, etc. are exemplary. `docs/bom.md` is the
authoritative cross-reference. This level of provenance is rare for a
simulator and very welcome here.

### S6. STPA-Pro coverage and traceability

`docs/stpa/` walks the canonical 01-purpose through 09-derived-requirements
sequence. Loss → Hazard → Safety Constraint → Unsafe Control Action →
Loss Scenario → Derived Requirement chain is intact. Each derived
requirement cross-links to a backlog item and a governing ADR. The
control-structure mermaid diagram matches the actual code layout.

### S7. Documentation is em-dash-clean

A grep for U+2014 across the `.md` tree returns zero hits.
Long-form prose in `STATUS.md`, `LIMITATIONS.md`, the ADRs, and the
STPA documents follows the 3-5 short paragraph rule. The model
cards are uniformly structured.

### S8. REUSE 3.x compliance

`REUSE.toml` is a valid v1 file with `precedence = "aggregate"` and
covers every file pattern in the tree. `LICENSE` and `NOTICE` are
present and consistent. `pyproject.toml` declares
`license = "Apache-2.0"` and `license-files = ["LICENSE"]` per PEP
621.

### S9. Test isolation

`tests/conftest.py` is small and correct. `tmp_nous_home` resets the
settings cache, points `NOUS_HOME`, `NOUS_AUDIT_PATH`, and
`NOUS_DB_URL` at a `tmp_path`, and yields. The autouse
`_clear_anthropic_key` fixture defends against ambient credentials.
`pytest-asyncio` is in auto mode. No live network calls.

### S10. Single-client OAuth lockdown is the right default

`src/nous/auth/oauth.py:103-117` atomically replaces the prior client
record when `oauth_single_client=True`, preventing registration
squatting and supporting the documented claude.ai retry pattern. The
default in `config.py:68` is `True`.

## 8. Findings by domain

| Domain | Critical | High | Medium | Low | Notes |
|--------|----------|------|--------|-----|-------|
| Spine (policy/audit/runner/server) | C1, C2, C3 | H1, H2 | M1, M3, M8, M9 | L1 | Strongest discipline in the repo; defects are narrow. |
| State machine | -- | H1 (test gap) | -- | L2 | Implementation matches ADR-0004. |
| Anthropic client | C1 | H1 (test gap) | -- | L3 | Prompt cache is correct. |
| Subsystems / estimators | C5 | -- | M10 | -- | Power and APU sound; thermal/compute stubs need sentinels. |
| Self-model | C5 (zeros) | -- | -- | -- | Distinguish "unknown" from "zero". |
| Interop adapters | C4 | H3, H4, H5 | M6, L9 | -- | Stubs but produce malformed output. |
| OAuth issuer | -- | H6, H7 | M5 | -- | Single-client lockdown is good; locking and rotation are gaps. |
| Tests | -- | H1, H2 | M8, M9 | -- | Three spine modules untested. |
| CI / scripts | C6 | -- | M7 | L4, L5 | Policy greps missing; security scanners absent. |
| Deployment | -- | H8 | M2, M4 | L6 | Auto-update loop documented but lacking rollback discipline. |
| Profiles / BOM | -- | H9 | -- | -- | Inference values uncited. |
| Docs / ADRs / STPA | -- | -- | -- | L7, L8, L10 | High quality; minor polish only. |
| Licensing / governance | -- | -- | -- | -- | Clean. |

## 9. Recommended remediation order

The recommended sequence balances blast radius against effort. Each
item is one to four hours of work; the whole list is roughly a sprint.

1. **C1 anthropic_client.py flush before unlock.** One-line fix in a
   tier-stable file. Land first; reference ADR-0005.
2. **C5 estimator and self-model stubs return sentinels.** Touches
   four files. Prevents controllers from being misled by plausible
   zero output. Land before any L1 self-model work.
3. **C6 CI policy greps.** Two-line `policy.sh` plus a workflow step.
   Closes the doc-vs-CI drift.
4. **H1 spine unit tests.** Three new files under `tests/unit/`.
   Largest single remediation but also the highest leverage.
5. **C2 recursive redaction in audit.py.** Required before any tool
   accepts structured payloads (likely L1).
6. **C3 tick task in server lifespan.** Activates the engine in the
   live server. Closes the "state_history is frozen" issue.
7. **H6, H7 OAuth file lock + chmod 0600 + family revocation.** Three
   small additions to `oauth.py`. Required before any multi-tenant L3
   work and good defence in depth today.
8. **C4 MISB KLV BER-OID encoding.** Either implement or raise.
9. **H3, H4, H5 CoT / SensorThings / NMEA encoder completeness.**
   Stubs but should produce well-formed output even at stub maturity.
10. **H8 auto-update rollback discipline.** SECURITY.md kill switch
    + commit-SHA snapshot.
11. **H2 mypy strict for tests/.**
12. **H9 profile inference-placeholder citations.**
13. **M1-M10 and L1-L10 as opportunistic cleanup.**

## 10. Out-of-scope and explicitly not flagged

The audit deliberately did **not** flag the following, even though
some of them came up during scanning:

* **Stub adapters returning `note: lands with BL-NNN`.** Documented
  v0.1 posture per `LIMITATIONS.md L15`; the flagged interop
  findings concern *malformed output*, not the stub posture itself.
* **No mesh / DTN / propagation comms model.** Per `LIMITATIONS.md
  L7` and `L12`. Tracked.
* **Parametric biometrics and self-model.** Per `LIMITATIONS.md L6`
  and `L14`. Tracked in BL-040, BL-046.
* **No real local inference.** Per `LIMITATIONS.md L9`. Tracked in
  BL-043.
* **FSM raises on unknown trigger.** This is the documented design
  choice in ADR-0004, not a defect.
* **`audit.py` swallowing exceptions silently.** This is a
  correctness requirement (audit must never break a tool call),
  not a bug. The medium-severity finding M3 is about *visibility*,
  not about the swallow itself.
* **Anthropic SDK response parsing using `getattr(block, "text", "")`.**
  Defensive against block-type drift in the SDK; if the SDK changes
  block shapes, the worst case is an empty response, which the
  controller can detect and fall back from.
* **Single-1-D Kalman without Joseph form.** The Joseph form matters
  for numerical asymmetry in multi-state covariance matrices; for a
  scalar Kalman the simplified `(1-K) P` is identical up to floating
  point. The bound documented in
  `docs/model-cards/estimator-power-soc.md` is consistent with the
  filter once warm-up has run.

## 11. How to consume this report

This document is the v0.1 audit baseline. Findings should be tracked
as backlog items (`BL-NNN`) in `docs/backlog.md`. The recommended
mapping:

* C-series → next sprint, all branches.
* H-series → in-phase: H1, H6, H7 before L2; H3-H5 before L1
  interop completion; H8, H9 before next deployment cycle.
* M-series → opportunistic, no phase gate.
* L-series → polish during the next docs sweep.

The audit was conducted read-only; no code changes were made on the
`claude/repo-audit-best-practices-fHVFy` branch other than this file.
