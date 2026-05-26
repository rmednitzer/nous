"""Interop adapters. Each adapter implements :class:`Adapter`."""

from __future__ import annotations

from .base import Adapter, StaleEstimateError
from .cot import CotAdapter
from .misb_klv import MisbKlvAdapter
from .mqtt import MqttAdapter
from .nmea0183 import Nmea0183Adapter
from .sensorthings import SensorThingsAdapter
from .stanag_4774 import Stanag4774Adapter

__all__ = [
    "REGISTRY",
    "Adapter",
    "CotAdapter",
    "MisbKlvAdapter",
    "MqttAdapter",
    "Nmea0183Adapter",
    "SensorThingsAdapter",
    "StaleEstimateError",
    "Stanag4774Adapter",
    "build_adapter",
]


REGISTRY: dict[str, type[Adapter]] = {
    "cot": CotAdapter,
    "sensorthings": SensorThingsAdapter,
    "misb_klv": MisbKlvAdapter,
    "nmea0183": Nmea0183Adapter,
    "stanag_4774": Stanag4774Adapter,
    "mqtt": MqttAdapter,
}


def build_adapter(name: str) -> Adapter:
    """Construct the registered adapter named ``name``. Raises KeyError if unknown."""
    cls = REGISTRY.get(name.strip().lower())
    if cls is None:
        raise KeyError(f"unknown interop adapter: {name!r}")
    return cls()
