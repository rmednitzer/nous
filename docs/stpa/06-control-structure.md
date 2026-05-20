# 06 -- Control structure

```mermaid
flowchart TD
    Controller["Controller (Claude session)"]
    Server["nous MCP server (FastMCP)"]
    Runner["Audited runner"]
    Policy["Tier classifier + policy"]
    Engine["Engine (tick loop)"]
    SelfModel["Self-model"]
    Estimators["Estimators"]
    Subsystems["Subsystems"]
    Profile["Hardware profile YAML"]
    Adapters["Interop adapters"]
    Audit["Audit JSONL"]
    DB["SQLite state DB"]
    Anthropic["Anthropic API (external)"]

    Controller -->|tool calls| Server
    Server --> Runner --> Policy
    Runner --> Audit
    Server --> Engine
    Engine --> Subsystems
    Engine --> Estimators
    Engine --> SelfModel
    SelfModel --> Controller
    Subsystems --> Estimators
    Subsystems --> Profile
    Engine --> DB
    Adapters --> Engine
    Engine --> Adapters
    Server -->|"inference_cloud"| Anthropic
```

The simulator exposes itself as the controlled process; the Claude
session is the controller. Refusals at the policy gate and entries in
the audit log are the *feedback* edges that allow the controller to
correct course.
