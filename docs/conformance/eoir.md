# Conformance posture: EO/IR thermo-optical payload

**Subsystem:** `src/nous/subsystems/eoir.py` (BL-055)

**Estimator:** `src/nous/estimators/eoir.py` (`EoirKalman`)

**MCP tool:** `eoir_status` (T0)

**Standard alignment:** None as a sensor interface. There is no claim of
conformance to a camera, thermal-imager, or targeting standard. The subsystem
models the *capability envelope* of an electro-optical and long-wave infrared
payload, not its imagery or its control interface, and uses the same
`Observation` shape as the rest of the simulator (`nous.types.Observation`).

**Method alignment:** The detection-range model is grounded in three textbook
methods, named here and cited below rather than reproduced:

- The per-band **detection, recognition, identification** ranges follow the
  Johnson criteria's cycle-ratio scaling (recognition and identification at
  successively shorter ranges than detection). The simulator uses the classic
  fixed cycle ratios, not the later Targeting Task Performance (TTP) metric.
- The **atmospheric extinction** cap is Koschmieder's meteorological-range law
  (`V = 3.912 / sigma_ext` at the 2 percent contrast threshold), applied per band
  with separate extinction coefficients so the infrared band penetrates haze
  better than the visible band.
- The **infrared signal** model is a thermal-contrast factor that collapses at
  thermal crossover (background temperature approaching the target), the standard
  qualitative behaviour of an uncooled LWIR imager, with calibration health
  standing in for non-uniformity-correction (NUC) drift and NETD growth.

**Current posture:** Two bands carried as a bounded detection-range envelope
(`eo_range_m`, `ir_range_m`), each the product of a clear-air reference range and
the atmospheric, signal, and calibration factors. Ambient temperature and
humidity are read live from the environmental sensor pack. The `EoirKalman` tracks
both band ranges with bounds validation (a reading outside `[0, 60000]` m
increments `rejected_updates` without poisoning the estimate). The measurement
sigma widens as calibration drifts, so a degraded payload's reading is folded more
gently.

**What is supported:** Per-band detection / recognition / identification ranges;
Koschmieder atmospheric extinction driven by humidity and an obscurant level;
infrared thermal-contrast collapse at crossover; electro-optical illumination
fall-off at night; calibration drift on the RNG seam with a `recalibrate` seam;
`set_obscurant` / `set_illumination` scenario seams; the two-band Kalman with
calibration-scaled sigma; the `eoir_status` T0 read.

**What is not supported:** Imagery or pixel-level output; a learned detector or
probability of identification; per-object tracks; terrain line-of-sight occlusion
of a specific target (the named follow-on, reusing the `WorldSource`
`path_profile`); spectral transmittance within the LWIR window; a background
temperature distribution (a single target temperature drives the contrast).

**Conformance claim:** None. The model is a legible, physically motivated
capability envelope for exercising the perception code path and the controller's
band-selection decision. It is explicit (here and in `LIMITATIONS.md`) that the
ranges do not represent a calibrated sensor and must not be used for real
targeting or detection-performance prediction.

**References:**

- Johnson, J. (1958). "Analysis of image forming systems." Proceedings of the
  Image Intensifier Symposium, US Army Engineer Research and Development
  Laboratories, Fort Belvoir, 249-273. (The Johnson criteria / DRI cycle ratios.)
- Vollmerhausen, R. H., Jacobs, E., Driggers, R. G. (2004). "New metric for
  predicting target acquisition performance." Optical Engineering 43(11). (The
  TTP metric that supersedes Johnson; named as the more accurate successor.)
- Koschmieder, H. (1924). "Theorie der horizontalen Sichtweite." Beitraege zur
  Physik der freien Atmosphaere, 12, 33-53. (Meteorological-range law and the
  3.912 constant.)
- Holst, G. C. (2000). "Common Sense Approach to Thermal Imaging." SPIE Press.
  (NETD, thermal contrast, and the LWIR / MWIR atmospheric windows.)

**Cross-references:** `LIMITATIONS.md` (EO/IR model-fidelity boundary), the model
cards (`docs/model-cards/subsystem-eoir.md`,
`docs/model-cards/estimator-eoir-kalman.md`), ADR 0077, and the biometrics
conformance note (`docs/conformance/biometrics.md`), which names imaging-based
thermography as this subsystem.
