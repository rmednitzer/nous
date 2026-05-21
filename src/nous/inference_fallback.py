"""Inference fallback ladder for degraded comms and exhausted-cap scenarios.

The ladder is consulted by ``inference_cloud`` and any controller-facing
tool that wants to honour the SC-5 contract ("fail closed with
``CapExhausted``, surfacing the failure"). It is *not* a fancy routing
layer -- it picks the first path that is currently feasible and reports
which path was used so the audit trail makes the fallback observable.

Order of preference (when ``call_cloud`` is requested):

1. ``cloud`` if the cap is not exhausted and the comms estimator's
   recent label is ``CONNECTED``.
2. ``cloud`` if the cap is not exhausted and the comms estimator's
   label is ``LIMITED`` (best effort).
3. ``local_mock`` (always available -- the simulator's deterministic
   fallback). Returns a structured response that downstream controllers
   can treat as a degraded answer rather than a transient error.

A controller that requested ``call_cloud`` but ended up on the local
mock is informed via the ``path`` field on the response. The runner
logs ``path`` into the audit line so an analyst can reconstruct what
happened during a degraded-comms window without consulting the cloud
provider's API logs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .anthropic_client import CapExhausted
from .state.comms_state import CommsState

__all__ = ["FallbackResult", "InferenceFallback"]


@dataclass(frozen=True)
class FallbackResult:
    """One inference outcome, including the path the ladder picked."""

    path: str
    response: str
    cap_remaining: int | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "response": self.response,
            "cap_remaining": self.cap_remaining,
            "reason": self.reason,
        }


CloudCall = Callable[[str, str], Awaitable[str]]
LocalCall = Callable[[str], Awaitable[str]]


class InferenceFallback:
    """Decision ladder for cloud vs. local inference paths."""

    def __init__(
        self,
        *,
        cloud_call: CloudCall,
        local_call: LocalCall,
        comms_state: Callable[[], CommsState],
        cap_remaining: Callable[[], int | None],
    ) -> None:
        self._cloud_call = cloud_call
        self._local_call = local_call
        self._comms_state = comms_state
        self._cap_remaining = cap_remaining

    async def call(self, prompt: str, *, system: str = "") -> FallbackResult:
        """Pick a path and execute it.

        The ladder never raises ``CapExhausted`` upward -- the whole
        point is to fail to the local mock. A controller that wants the
        cap-exhausted signal explicitly should read ``device_info`` or
        consult ``self._cap_remaining`` directly.
        """
        comms = self._comms_state()
        cap = self._cap_remaining()
        if comms is CommsState.DENIED or comms is CommsState.DEGRADED:
            return await self._do_local(prompt, reason=f"comms={comms.value}")
        if cap is not None and cap <= 0:
            return await self._do_local(prompt, reason="cap exhausted")
        try:
            body = await self._cloud_call(prompt, system)
        except CapExhausted as exc:
            return await self._do_local(prompt, reason=f"cap exhausted: {exc}")
        except Exception as exc:  # noqa: BLE001
            return await self._do_local(
                prompt, reason=f"cloud call failed: {exc.__class__.__name__}"
            )
        return FallbackResult(
            path="cloud",
            response=body,
            cap_remaining=cap,
            reason=f"comms={comms.value}",
        )

    async def _do_local(self, prompt: str, *, reason: str) -> FallbackResult:
        body = await self._local_call(prompt)
        return FallbackResult(
            path="local_mock",
            response=body,
            cap_remaining=self._cap_remaining(),
            reason=reason,
        )
