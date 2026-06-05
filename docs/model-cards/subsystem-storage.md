# Model card: Storage subsystem

**Module:** `src/nous/subsystems/storage.py`

**Backlog:** BL-008

## Scope

Tracks the two quantities a controller cares about for an inference
appliance: how full the drive is (`used_gib`) and how worn the NAND is
(`wear_pct`). Wear is driven by *physical* writes, which the profile inflates
from logical writes via `write_amplification`. The wear curve is linear:
`wear_pct = wear_pct_initial + 100 * lifetime_physical_gib / tbw_gib`, clipped
to [0, 100]. The endurance budget defaults to a generic "0.3 drive-writes-per-
day over 5 years" rating (`capacity_gib * 600`) when `tbw_gib` is unset, so a
heavy ingest workload visibly shrinks remaining drive life.

## Inputs

| Seam | Notes |
|------|-------|
| `write(gib)` | One-shot logical write; clamped by free space, inflated by write amplification |
| `set_write_rate(gib_per_s)` | Sustained logical write rate, consumed each tick |
| `set_used_gib` | Scenario seed for the used-space figure |

## State (truth())

| Field | Units | Notes |
|-------|-------|-------|
| `used_gib` / `free_gib` / `used_pct` | GiB / GiB / % | Capacity accounting |
| `wear_pct` | % | Linear in lifetime physical writes |
| `lifetime_physical_gib` | GiB | Accumulated physical writes |
| `at_capacity` / `worn_out` | bool | `used >= capacity` / `wear >= 100` |

## Outputs (sensor_obs())

| Field | Units | Sigma |
|-------|-------|-------|
| `used_gib` | GiB | 0.05 |
| `wear_pct` | % | 0.1 |

## Profile fields

```yaml
storage:
  capacity_gib: 256
  wear_pct_initial: 0
  write_amplification: 1.0      # logical -> physical inflation (>= 1.0)
  tbw_gib: null                 # optional; else capacity_gib * 600
```

## Known limitations

- Linear wear. Real NAND wear accelerates near end-of-life and exhibits a
  retention/write cliff; the model has no such non-linearity, so `wear_pct` is
  a budget burn-down, not a failure-probability curve.
- Single write-amplification constant. Real WA varies with fill level,
  workload, and over-provisioning; here it is one number from the profile.
- No bad-block, ECC, retention, or journaling-recovery model (that resilience
  posture is BL-058). Used space only grows via writes; there is no delete /
  garbage-collection / TRIM model.
