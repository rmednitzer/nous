# Model card: Inference (local mock)

**Module:** `src/nous/server.py::inference_local`

**Backlog:** BL-013, BL-043 (real local model in L3)

## Inputs

- A prompt string from the controller.

## Outputs

A structured JSON response with `{model, prompt_len, response}`. The
`response` echoes the first 160 characters of the prompt prefixed with
`[local mock]`. The mock does *not* run a model.

## SLA

- Latency: fixed at a configurable simulator-time delay (default
  20 ms wall, 200 ms simulated).
- Energy: derived from the hardware profile's compute curve.

## Known failure modes

- The mock is not a model. It cannot answer questions; it cannot
  reason. Treat its outputs as deterministic placeholders. Calling
  `inference_local` should be paired with `inference_cloud` for any
  scenario that needs an actual response.

## Replacement

The L3 implementation (BL-043) wires either TensorRT-LLM (Jetson) or
llama.cpp (Pi 5 / x86) into this tool. Replacing the mock will produce
real responses and real energy/latency; the SLA in this card will be
replaced by the new model's card at that time.
