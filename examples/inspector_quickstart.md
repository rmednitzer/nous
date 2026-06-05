# MCP Inspector quickstart

The MCP Inspector is the fastest way to poke at the nous tool surface
without an LLM in the loop. It speaks the same MCP protocol your client
will use.

## Install + run

```bash
# from the nous repo, spawn nous and connect Inspector to it via stdio
make install   # if you have not already
NOUS_HOME=/tmp/nous-inspector npx @modelcontextprotocol/inspector nous serve
```

A browser tab opens. Switch transport to **stdio**, command to
`nous`, args to `serve`, and connect.

## What to try

1. **List tools.** The right panel shows every registered tool, its tier,
   and its input schema. Confirm the surface matches what you expected.
2. **Call `device_info`.** Zero args; should return the active profile
   name, version, and configured policy mode.
3. **Call `state_get`.** Returns the current FSM `mode`, `tick`, `ts_s`,
   and the derived `operator_state` / `comms_state` (each with a reason).
   The transition history is on `state_history`.
4. **Call `power_status`.** Returns primary battery SoC, instantaneous
   load, and remaining-runtime estimate from the estimator.
5. **Call `apu_status`.** Lists all auxiliary power inputs with their
   active/inactive state and current output (W).
6. **Call `self_model_assess` with `{"question": "endurance"}`.** Returns
   capability claims plus an `explanation` string. The calibrated
   p5/p50/p95 quantiles and confidence arrive with the full self-model
   layer (BL-018).

Each call writes one record to `$NOUS_HOME/audit.jsonl`; tail it in
another shell to watch the audit trail in real time::

    tail -F $NOUS_HOME/audit.jsonl | jq .

## HTTP transport

Once you have a deployment, point Inspector at
`https://nous.example.org/` and complete the OAuth dance to
authenticate. Refer to `docs/deployment.md` for the full setup.

## Troubleshooting

See `skills/nous-troubleshooting.md` for common failure modes (no tools
listed, OAuth loop, audit log permissions, daily-cap hit).
