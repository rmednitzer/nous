# ADR 0001: FastMCP server with a tiered policy + audited runner

- **Status:** Accepted
- **Date:** 2026-05-20
- **Authors:** rmednitzer
- **Builds on:** n/a

## Context

`nous` needs an MCP server that a Claude session can drive. The server
must expose dozens of tools that range from harmless reads (battery
state) to mutating writes (scenario injection, comms publish). Putting
every tool on the same path risks an over-eager controller mutating
simulator state, and putting the policy logic in the tool handlers
themselves means we cannot audit refusals.

Three properties drove the decision:

1. The server must be small enough to read in one sitting. FastMCP from
   the official `mcp` SDK is the lightest option that still supports
   stdio and HTTP transports plus OAuth.
2. Every tool call must be classified into a tier and admitted or refused
   by a policy mode that operators can configure at deploy time without
   redeploying code.
3. Every call (admitted or refused) must produce exactly one audit line,
   and the audit line must be safe to ship off host.

## Decision

The server is built with FastMCP. Every registered tool runs through
`src/nous/runner.py`, which:

1. classifies the tool via `src/nous/policy.py` into one of
   `READ_ONLY`, `REVERSIBLE`, `STATEFUL`, or `IRREVERSIBLE`,
2. admits or refuses the call under the configured mode (`open`,
   `guarded`, `readonly`),
3. executes the supplied work coroutine,
4. truncates the output to the configured budget,
5. appends one audit record to the JSONL audit log.

The deny list, when set, applies in *every* mode, including `open`.

## Consequences

Easier: adding a tool is a single decorator + a body. Refusing a tool is
a configuration change, not a code change. Operators can review the
recent tool surface by `tail`-ing one file.

Harder: every tool author must pass the call through the runner. The CI
grep enforces this by scanning `src/nous/server.py` for `@mcp.tool` blocks
that do not call `app.run`.

Alternatives rejected:

- Hand-rolling an MCP transport. FastMCP already handles the schema and
  the stdio framing.
- Treating the policy as advisory. A persuaded model would inevitably
  ignore advisory text; admission control needs to be enforceable.

## Revisit triggers

- FastMCP's API breaks compatibly in a way that prevents middleware.
- A second runtime (other than Claude) needs to drive `nous`.
- A new tier is needed (e.g. a `T4 PRIVILEGED` for direct file access).
