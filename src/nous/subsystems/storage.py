"""Storage subsystem: NAND wear, capacity, and write-rate accounting (BL-008).

The simulator tracks two quantities the controller cares about for an
inference appliance: how full the drive is (``used_gib``) and how worn
the NAND is (``wear_pct``). Wear is driven by physical writes, which
the profile inflates from logical writes via
``storage.write_amplification``; the endurance budget defaults to a
generic "0.3 drive-writes-per-day over 5 years" rating
(``capacity_gib * 600`` when ``storage.tbw_gib`` is unset) so a
controller running a heavy ingest workload can see the drive's
remaining life shrink in a physically plausible way.

Controller seams:

* :meth:`write` -- a one-shot logical write in GiB. Bumps
  ``used_gib`` and accumulates lifetime physical writes.
* :meth:`set_write_rate` -- a sustained logical write rate
  (``gib_per_s``) consumed each tick.
* :meth:`set_used_gib` -- scenario seed for the used-space figure.

The subsystem reports ``at_capacity`` when used reaches the configured
ceiling and ``worn_out`` when wear reaches 100 %. Higher-level policy
(self-model viability, FSM degradation) can read those flags via the
estimator and capability layer.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..types import Observation

__all__ = ["StorageSubsystem"]


_DEFAULT_CAPACITY_GIB = 256.0
_DEFAULT_WEAR_INITIAL = 0.0
_DEFAULT_WRITE_AMPLIFICATION = 1.0
_DEFAULT_TBW_PER_CAPACITY = 600.0


class StorageSubsystem:
    """Storage utilisation and wear curve.

    State is three scalars: logical bytes used, lifetime physical
    writes (in GiB), and the resulting NAND wear percentage. The wear
    curve is linear:
    ``wear_pct = wear_pct_initial + 100 * physical_writes_gib / tbw_gib``,
    clipped to ``[0, 100]``.
    """

    name: str = "storage"

    def __init__(self, profile: Mapping[str, Any]) -> None:
        self.profile = profile
        cfg = dict(profile.get("storage") or {})
        self._capacity_gib = max(
            0.0, float(cfg.get("capacity_gib", _DEFAULT_CAPACITY_GIB))
        )
        self._wear_initial = max(
            0.0,
            min(100.0, float(cfg.get("wear_pct_initial", _DEFAULT_WEAR_INITIAL))),
        )
        self._write_amplification = max(
            1.0, float(cfg.get("write_amplification", _DEFAULT_WRITE_AMPLIFICATION))
        )
        explicit_tbw = cfg.get("tbw_gib")
        if explicit_tbw is None:
            self._tbw_gib = max(1.0, self._capacity_gib * _DEFAULT_TBW_PER_CAPACITY)
        else:
            self._tbw_gib = max(1.0, float(explicit_tbw))

        self._t = 0.0
        self._used_gib = 0.0
        self._lifetime_physical_gib = 0.0
        self._wear_pct = self._wear_initial
        self._write_rate_gib_per_s = 0.0

    def write(self, gib: float) -> float:
        """Apply a one-shot logical write. Returns the GiB actually accepted.

        The amount is clamped by the remaining free space; physical
        writes are inflated by ``write_amplification`` and accumulate
        into the wear figure.
        """
        amount = max(0.0, float(gib))
        accepted = min(amount, self.free_gib)
        if accepted <= 0.0:
            return 0.0
        self._used_gib = min(self._capacity_gib, self._used_gib + accepted)
        physical = accepted * self._write_amplification
        self._lifetime_physical_gib += physical
        self._recompute_wear()
        return accepted

    def set_write_rate(self, gib_per_s: float) -> None:
        """Steer a sustained logical write rate (clamped to >= 0)."""
        self._write_rate_gib_per_s = max(0.0, float(gib_per_s))

    def set_used_gib(self, gib: float) -> None:
        """Scenario seed for the used-space figure."""
        self._used_gib = max(0.0, min(self._capacity_gib, float(gib)))

    @property
    def capacity_gib(self) -> float:
        return self._capacity_gib

    @property
    def used_gib(self) -> float:
        return self._used_gib

    @property
    def free_gib(self) -> float:
        return max(0.0, self._capacity_gib - self._used_gib)

    @property
    def used_pct(self) -> float:
        if self._capacity_gib <= 0.0:
            return 0.0
        return 100.0 * self._used_gib / self._capacity_gib

    @property
    def wear_pct(self) -> float:
        return self._wear_pct

    @property
    def lifetime_physical_gib(self) -> float:
        return self._lifetime_physical_gib

    @property
    def write_rate_gib_per_s(self) -> float:
        return self._write_rate_gib_per_s

    @property
    def write_amplification(self) -> float:
        return self._write_amplification

    @property
    def tbw_gib(self) -> float:
        return self._tbw_gib

    @property
    def at_capacity(self) -> bool:
        return self._used_gib >= self._capacity_gib

    @property
    def worn_out(self) -> bool:
        return self._wear_pct >= 100.0

    def step(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        if self._write_rate_gib_per_s > 0.0:
            self.write(self._write_rate_gib_per_s * dt)

    def truth(self) -> Mapping[str, Any]:
        return {
            "capacity_gib": self._capacity_gib,
            "used_gib": self._used_gib,
            "free_gib": self.free_gib,
            "used_pct": self.used_pct,
            "wear_pct": self._wear_pct,
            "lifetime_physical_gib": self._lifetime_physical_gib,
            "write_rate_gib_per_s": self._write_rate_gib_per_s,
            "at_capacity": self.at_capacity,
            "worn_out": self.worn_out,
            "t": self._t,
        }

    def sensor_obs(self) -> Observation:
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={"used_gib": self._used_gib, "wear_pct": self._wear_pct},
            noise={"used_gib_sigma": 0.05, "wear_pct_sigma": 0.1},
        )

    def _recompute_wear(self) -> None:
        delta = 100.0 * self._lifetime_physical_gib / self._tbw_gib
        self._wear_pct = max(0.0, min(100.0, self._wear_initial + delta))
