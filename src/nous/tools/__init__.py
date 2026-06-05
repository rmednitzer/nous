"""Per-subsystem MCP tool modules (ADR 0021).

Each module exposes ``register(mcp, app, wrap)`` that decorates its tool
handlers against the shared FastMCP instance. ``server.py`` keeps the
lifespan, the :class:`~nous.server.Nous` orchestrator, and the audited-runner
``wrap``; this package keeps the per-subsystem grouping of handlers so the
tool layer mirrors the subsystem and estimator decomposition (ADR 0021).

The split lands incrementally: a module is added here and its inline
definitions are removed from ``server.py`` in the same change, so the
registered surface stays identical at every step (guarded by the e2e tool
smoke and the tier-classifier coverage test).
"""

from __future__ import annotations
