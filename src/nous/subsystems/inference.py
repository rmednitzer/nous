"""Inference subsystem: local-path latency and energy metering (BL-013).

The simulator's controller asks for inference through the
:func:`inference_local` MCP tool; this subsystem turns that request
into the physical quantities a backpack-class device would actually
spend: wall-clock latency (set by the profile's
``compute.inference_local.tok_per_s_p50``) and joules consumed
(``compute.inference_local.energy_j_per_tok``). The subsystem also
exposes :meth:`set_continuous_rate` so a scenario can model a
sustained inference workload by writing through to the compute
subsystem, mirroring how a controller would steer load in practice.

Single one-shot requests do not directly mutate battery SoC: the
energy figure is reported to the caller so it is visible in the
audit trail, but sustained compute load (and therefore battery
drain) is the controller's lever via :meth:`set_continuous_rate` or
``compute.set_load_pct``. This keeps the load_pct -> draw_w -> SoC
chain the single source of truth for the power loop and avoids a
parallel SoC-debit path the estimator cannot see.

Cloud path (model selection, network round-trip, cap accounting)
lives in :mod:`nous.inference_fallback` and lands in a later ADR.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..types import Observation

__all__ = ["InferenceResult", "InferenceSubsystem"]


_DEFAULT_TOK_PER_S = 0.0
_DEFAULT_ENERGY_J_PER_TOK = 0.0
_DEFAULT_MAX_TOKENS = 128


@dataclass(frozen=True)
class InferenceResult:
    """One inference outcome with the cost the device would have paid."""

    n_tokens: int
    latency_s: float
    energy_j: float
    rate_tok_per_s: float
    saturated: bool
    response: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_tokens": self.n_tokens,
            "latency_s": round(self.latency_s, 4),
            "energy_j": round(self.energy_j, 4),
            "rate_tok_per_s": round(self.rate_tok_per_s, 3),
            "saturated": self.saturated,
            "response": self.response,
        }


class InferenceSubsystem:
    """Local-inference physics: latency, energy, and sustained-rate control.

    The subsystem can hold an optional reference to the
    :class:`~nous.subsystems.compute.ComputeSubsystem` so
    :meth:`set_continuous_rate` translates a token rate into compute
    load directly. When the reference is ``None`` the controller is
    expected to drive compute themselves.
    """

    name: str = "inference"

    def __init__(
        self,
        profile: Mapping[str, Any],
        *,
        compute: Any | None = None,
    ) -> None:
        self.profile = profile
        compute_cfg = profile.get("compute") or {}
        cfg = dict(compute_cfg.get("inference_local") or {})
        self._tok_per_s_p50 = float(cfg.get("tok_per_s_p50", _DEFAULT_TOK_PER_S))
        self._energy_j_per_tok = float(
            cfg.get("energy_j_per_tok", _DEFAULT_ENERGY_J_PER_TOK)
        )
        self._compute = compute

        self._t = 0.0
        self._local_calls = 0
        self._total_tokens = 0
        self._total_energy_j = 0.0
        self._last_latency_s = 0.0
        self._last_rate_tok_per_s = 0.0
        self._continuous_rate = 0.0

    def request_local(
        self,
        prompt: str,
        *,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> InferenceResult:
        """Run a synthetic local inference and return its physical cost."""
        n_tokens = max(1, int(max_tokens))
        rate = self._tok_per_s_p50
        latency = n_tokens / rate if rate > 0.0 else 0.0
        energy = n_tokens * self._energy_j_per_tok
        saturated = self._compute is not None and bool(
            getattr(self._compute, "saturated", False)
        )

        self._local_calls += 1
        self._total_tokens += n_tokens
        self._total_energy_j += energy
        self._last_latency_s = latency
        self._last_rate_tok_per_s = rate

        return InferenceResult(
            n_tokens=n_tokens,
            latency_s=latency,
            energy_j=energy,
            rate_tok_per_s=rate,
            saturated=saturated,
            response=_mock_response(prompt, n_tokens),
        )

    def set_continuous_rate(self, tok_per_s: float) -> None:
        """Steer a sustained inference rate through the compute subsystem.

        Pushes the rate to ``compute.set_inference_rate(...)``; when no
        compute reference is attached the call records the requested
        rate but does not propagate it.
        """
        rate = max(0.0, float(tok_per_s))
        self._continuous_rate = rate
        if self._compute is not None:
            self._compute.set_inference_rate(rate)

    @property
    def tok_per_s_capacity(self) -> float:
        return self._tok_per_s_p50

    @property
    def energy_j_per_tok(self) -> float:
        return self._energy_j_per_tok

    @property
    def local_calls(self) -> int:
        return self._local_calls

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def total_energy_j(self) -> float:
        return self._total_energy_j

    @property
    def last_latency_s(self) -> float:
        return self._last_latency_s

    @property
    def last_rate_tok_per_s(self) -> float:
        return self._last_rate_tok_per_s

    @property
    def continuous_rate(self) -> float:
        return self._continuous_rate

    def step(self, dt: float) -> None:
        if dt > 0.0:
            self._t += dt

    def truth(self) -> Mapping[str, Any]:
        return {
            "local_calls": self._local_calls,
            "total_tokens": self._total_tokens,
            "total_energy_j": self._total_energy_j,
            "last_latency_s": self._last_latency_s,
            "last_rate_tok_per_s": self._last_rate_tok_per_s,
            "tok_per_s_capacity": self._tok_per_s_p50,
            "energy_j_per_tok": self._energy_j_per_tok,
            "continuous_rate": self._continuous_rate,
            "t": self._t,
        }

    def sensor_obs(self) -> Observation:
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={
                "local_calls": self._local_calls,
                "total_tokens": self._total_tokens,
                "last_latency_s": self._last_latency_s,
            },
            noise={},
        )


def _mock_response(prompt: str, n_tokens: int) -> str:
    head = prompt[:160].replace("\n", " ")
    return f"[nous-local-mock tokens={n_tokens}] {head}"
