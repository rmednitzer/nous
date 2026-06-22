"""The `imu_status` tool (BL-026, ADR 0084): inertial truth, bias, and estimate.

The IMU read surfaces the along-track acceleration and yaw rate, the true
sensor biases, the measurement-noise envelope, and the position EKF's inferred
biases. It must read truth and the estimator only, never the observation, so a
read draws no engine RNG and leaves the seeded determinism intact (ADR 0019).
"""

from __future__ import annotations

import json
from typing import Any

from nous.config import Settings
from nous.server import build_app


def _payload(result: Any) -> dict[str, Any]:
    content, _structured = result
    data: dict[str, Any] = json.loads(content[0].text)
    return data


async def test_imu_status_reports_truth_and_estimate(config: Settings) -> None:
    app = build_app(config)
    out = _payload(await app.mcp.call_tool("imu_status", {}))
    for key in (
        "accel_mps2",
        "yaw_rate_rps",
        "accel_bias_mps2",
        "gyro_bias_rps",
        "accel_sigma_mps2",
        "gyro_sigma_rps",
    ):
        assert key in out
    assert "estimate" in out
    for key in ("accel_bias_mps2", "gyro_bias_rps", "accel_bias_sigma_mps2"):
        assert key in out["estimate"]
    assert out["accel_sigma_mps2"] >= 0.0
    assert out["gyro_sigma_rps"] >= 0.0


async def test_imu_status_reflects_an_injected_bias(config: Settings) -> None:
    app = build_app(config)
    app.engine.imu.set_bias(accel_bias=0.25, gyro_bias=0.01, freeze_walk=True)
    out = _payload(await app.mcp.call_tool("imu_status", {}))
    assert out["accel_bias_mps2"] == 0.25
    assert out["gyro_bias_rps"] == 0.01


async def test_imu_status_does_not_perturb_the_rng(config: Settings) -> None:
    # The read must draw no engine RNG (it reads truth and the EKF only, never
    # sensor_obs), so the bit-generator state is identical across the call. A
    # tool that drew noise would advance it and break ADR 0019 determinism.
    app = build_app(config)
    app.engine.tick()
    before = app.engine.rng.bit_generator.state
    await app.mcp.call_tool("imu_status", {})
    after = app.engine.rng.bit_generator.state
    assert before == after
