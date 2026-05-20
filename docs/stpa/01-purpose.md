# 01 -- Purpose of the STPA

`nous` is a simulator, not a deployed device. We run an STPA on the
simulator for two reasons:

1. **Legibility.** The simulator's controller (a Claude session) makes
   decisions that influence which mode the simulated device is in.
   Identifying the hazards that arise from miscommunication between the
   controller and the device makes the simulator more useful as a
   teaching artefact for the broader question "how would we operate the
   real device?".
2. **Scoping discipline.** STPA forces us to write down what we are
   *not* simulating. The hazards we do not cover (operator injury,
   regulatory non-compliance for spectrum use) are explicit in
   `LIMITATIONS.md`.

The STPA is *not* a safety case for a real device. It is a tool for
keeping the simulator honest about what it claims.
