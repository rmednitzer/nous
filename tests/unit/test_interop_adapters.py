"""Interop adapter conformance tests.

Closes the SC-4 gap (D-02): every adapter must include the source
timestamp and refuse to encode when the source estimate is stale. The
tests below pin the contract for each adapter.

NMEA / KLV / CoT also get format-conformance checks: the encoded output
must be parseable by the adapter's own decoder, and the checksum or
length fields must be correct.
"""

from __future__ import annotations

import math
import time

import pytest

from nous.interop.base import StaleEstimateError, assert_fresh
from nous.interop.cot import CotAdapter
from nous.interop.misb_klv import MisbKlvAdapter
from nous.interop.mqtt import MqttAdapter
from nous.interop.nmea0183 import Nmea0183Adapter
from nous.interop.sensorthings import SensorThingsAdapter
from nous.interop.stanag_4774 import Stanag4774Adapter


def test_assert_fresh_invalid_max_age_names_the_misconfiguration() -> None:
    # ITP-1 (ADR 0052): a non-positive or NaN max_age_s is a configuration
    # fault, not a stale estimate. The gate still refuses (fail closed), but
    # the error names the misconfiguration instead of a fabricated 0.0s age.
    with pytest.raises(StaleEstimateError) as raised:
        assert_fresh("cot", {"ts_s": 100.0}, max_age_s=-5.0, now_s=100.0)
    exc = raised.value
    assert exc.reason is not None
    assert "max_age_s" in str(exc)
    assert "0.00s old" not in str(exc)  # no fabricated staleness age
    with pytest.raises(StaleEstimateError):
        assert_fresh("cot", {"ts_s": 100.0}, max_age_s=math.nan, now_s=100.0)


def test_assert_fresh_zero_timestamp_is_a_valid_epoch() -> None:
    # FRESH-1 (ADR 0052): ts_s=0.0 is a valid epoch (the sim clock starts
    # there), not "missing". With now_s on the same clock it reads fresh.
    ts = assert_fresh("cot", {"ts_s": 0.0}, max_age_s=10.0, now_s=0.0)
    assert ts == 0.0


def test_stale_estimate_error_default_message_unchanged() -> None:
    # The genuine-staleness message keeps its shape; reason defaults to None.
    err = StaleEstimateError("cot", 100.0, 10.0)
    assert err.reason is None
    assert "source estimate is 100.00s old" in str(err)
    assert "max_age_s=10.00" in str(err)


def test_cot_encode_stamps_source_timestamp() -> None:
    ts = time.time()
    a = CotAdapter()
    out = a.encode({"uid": "x", "ts_s": ts, "lat": 1.0, "lon": 2.0}).decode()
    assert "time=" in out
    assert "start=" in out
    assert "stale=" in out


def test_cot_encode_refuses_stale_estimate() -> None:
    a = CotAdapter(max_age_s=10.0)
    with pytest.raises(StaleEstimateError):
        a.encode({"uid": "x", "ts_s": time.time() - 100.0, "lat": 0, "lon": 0})


def test_cot_decode_round_trips_canonical_attrs() -> None:
    a = CotAdapter()
    payload = a.encode({"uid": "alpha", "ts_s": time.time(), "lat": 45.0, "lon": -75.0})
    decoded = a.decode(payload)
    assert decoded["uid"] == "alpha"
    assert decoded["lat"] == pytest.approx(45.0, rel=1e-6)
    assert decoded["lon"] == pytest.approx(-75.0, rel=1e-6)


def test_cot_decode_refuses_xxe_doctype() -> None:
    payload = b"<?xml version='1.0'?><!DOCTYPE foo><event/>"
    a = CotAdapter()
    decoded = a.decode(payload)
    assert "error" in decoded


def test_cot_escapes_xml_in_uid() -> None:
    a = CotAdapter()
    out = a.encode({"uid": '<evil attr="x">', "ts_s": time.time(), "lat": 0, "lon": 0})
    # The angle brackets and embedded quote must be escaped regardless of
    # which quote character xml.sax.saxutils.quoteattr selected.
    assert b"&lt;evil" in out
    assert b"&gt;" in out
    # Raw '<evil' must not appear as a sibling element.
    assert b"<evil " not in out


def test_nmea_encode_uses_ddmm_format_and_correct_checksum() -> None:
    ts = time.time()
    a = Nmea0183Adapter(max_age_s=60.0)
    out = a.encode({"lat": 37.5, "lon": -122.25, "alt_m": 30.0, "ts_s": ts})
    decoded = a.decode(out)
    assert decoded.get("error") is None
    assert decoded["type"] == "GGA"


def test_nmea_encode_refuses_stale() -> None:
    a = Nmea0183Adapter(max_age_s=1.0)
    with pytest.raises(StaleEstimateError):
        a.encode({"lat": 0.0, "lon": 0.0, "ts_s": time.time() - 100.0})


def test_nmea_decode_rejects_bad_checksum() -> None:
    a = Nmea0183Adapter()
    out = a.encode({"lat": 1.0, "lon": 2.0, "ts_s": time.time()})
    # Replace just the two checksum hex digits, keep the '*' delimiter.
    tampered = out[:-4] + b"00\r\n"
    decoded = a.decode(tampered)
    assert "checksum mismatch" in decoded.get("error", "")


def test_nmea_rejects_invalid_lat() -> None:
    a = Nmea0183Adapter()
    with pytest.raises(ValueError):
        a.encode({"lat": 999.0, "lon": 0.0, "ts_s": time.time()})


def test_klv_encode_uses_ber_long_form_for_large_values() -> None:
    a = MisbKlvAdapter(max_age_s=60.0, max_value_len=4096)
    payload = a.encode({"3": "x" * 200, "ts_s": time.time()})
    decoded = a.decode(payload)
    assert "items" in decoded


def test_klv_refuses_oversized_value() -> None:
    a = MisbKlvAdapter(max_age_s=60.0, max_value_len=10)
    with pytest.raises(ValueError, match="max"):
        a.encode({"3": "x" * 100, "ts_s": time.time()})


def test_klv_refuses_invalid_key() -> None:
    a = MisbKlvAdapter(max_age_s=60.0)
    with pytest.raises(ValueError, match="out of range"):
        a.encode({"500": "x", "ts_s": time.time()})


def test_stanag_refuses_stale() -> None:
    a = Stanag4774Adapter(max_age_s=10.0)
    with pytest.raises(StaleEstimateError):
        a.encode({"classification": "SECRET", "ts_s": time.time() - 100.0})


def test_stanag_decode_rejects_oversized_payload() -> None:
    a = Stanag4774Adapter(max_payload_len=64)
    decoded = a.decode(b"x" * 1024)
    assert "exceeds max_payload_len" in decoded.get("error", "")


def test_sensorthings_includes_phenomenon_time() -> None:
    ts = time.time()
    a = SensorThingsAdapter()
    out = a.encode({"id": 1, "result": 42, "ts_s": ts}).decode()
    assert "phenomenonTime" in out
    assert "resultTime" in out


def test_sensorthings_refuses_stale() -> None:
    a = SensorThingsAdapter(max_age_s=5.0)
    with pytest.raises(StaleEstimateError):
        a.encode({"id": 1, "result": 42, "ts_s": time.time() - 100.0})


def test_mqtt_refuses_stale() -> None:
    a = MqttAdapter(max_age_s=5.0)
    with pytest.raises(StaleEstimateError):
        a.encode({"foo": 1, "ts_s": time.time() - 100.0})


def test_mqtt_decode_rejects_oversized() -> None:
    a = MqttAdapter(max_payload_len=32)
    decoded = a.decode(b"x" * 1024)
    assert "exceeds max_payload_len" in decoded.get("error", "")


def test_registry_exposes_every_shipped_adapter() -> None:
    from nous.interop import REGISTRY, build_adapter

    expected = {"cot", "sensorthings", "misb_klv", "nmea0183", "stanag_4774", "mqtt"}
    assert expected.issubset(set(REGISTRY))
    for name in expected:
        impl = build_adapter(name)
        assert impl.name == name


def test_build_adapter_rejects_unknown_name() -> None:
    from nous.interop import build_adapter

    with pytest.raises(KeyError, match="unknown interop adapter"):
        build_adapter("does-not-exist")
