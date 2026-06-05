# Model card: Inference (local mock)

**Module:** `src/nous/tools/inference.py::inference_local` (subsystem:
`src/nous/subsystems/inference.py`)

**Backlog:** BL-013, BL-043 (real local model in L3)

## Inputs

- A prompt string from the controller.

## Outputs

A structured JSON response. Alongside `{model, prompt_len}` the tool merges
the subsystem result, so the full payload is `{model, prompt_len, n_tokens,
latency_s, energy_j, rate_tok_per_s, saturated, response}`. The `response`
echoes the first 160 characters of the prompt prefixed with
`[nous-local-mock tokens=N]`. The mock does *not* run a model.

## SLA

- Latency: token-rate-driven, `n_tokens / tok_per_s_p50` from the profile's
  local-inference curve (zero when the rate is zero); not a fixed delay.
- Energy: derived from the profile's per-token energy figure
  (`energy_j_per_tok`).

## Known failure modes

- The mock is not a model. It cannot answer questions; it cannot
  reason. Treat its outputs as deterministic placeholders. For a scenario
  that needs an actual response, use the cloud path (the Anthropic client
  gated by the daily cap; the `inference_cloud` tool is classified but not
  yet registered, see STATUS L1).

## Replacement

The L3 implementation (BL-043) wires either TensorRT-LLM (Jetson) or
llama.cpp (Pi 5 / x86) into this tool. Replacing the mock will produce
real responses and real energy/latency; the SLA in this card will be
replaced by the new model's card at that time.
