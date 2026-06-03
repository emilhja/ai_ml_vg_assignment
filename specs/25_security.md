# 25 Security

Concise threat model and safety-layer index. Tool-level rules and constants
remain authoritative in [`20_tools.md`](20_tools.md) and
[`30_runtime_governance.md`](30_runtime_governance.md).

## Trust boundary

- **Intended use:** single developer machine or local Docker Compose with
  `./workspace` and `./traces` bind-mounted.
- **Operator trust:** the user running `vg-agent` is trusted; the agent is not
  hardened for hostile multi-tenant input on a shared server.
- **Network egress:** live runs may call **only** the pinned OpenRouter host
  (`openrouter.ai`); see egress pin below.

## Defense layers

| Layer | Mechanism | Detail in |
|-------|-----------|-----------|
| Workspace sandbox | Relative paths resolved under `VG_WORKSPACE_ROOT`; block `..` and absolute paths | [`20_tools.md`](20_tools.md) |
| Sensitive reads | Denylist (`.env`, keys, credentials patterns) | [`20_tools.md`](20_tools.md) |
| `run_bash` | Allowlist of read-only commands; no pipes/redirection/substitution; destructive token blocklist | [`20_tools.md`](20_tools.md) |
| Egress pin | LiteLLM client refuses non-`OPENROUTER_ENDPOINT_HOST`; emits `egress_blocked` | [`30_runtime_governance.md`](30_runtime_governance.md) |
| Approval policy | Gates spawns and Coder writes (`writes` / `all`); scoped cache cannot override deny-lists | [`10_main_agent.md`](10_main_agent.md) |
| Budget guards | Step/token/USD/daily caps; repetition abort; wall-clock timeout | [`30_runtime_governance.md`](30_runtime_governance.md) |
| Trace redaction | Optional secret redaction in JSONL/SQLite (`--no-redact` disables) | [`60_observability.md`](60_observability.md) |
| Docker (demo) | Non-root user, `cap_drop: ALL`, `pids_limit`, workspace-only mounts | [`50_packaging.md`](50_packaging.md) |

Docker is an **outer** boundary; in-process gates above are mandatory and
unit-tested without Docker.

## Out of scope (v1)

- Dashboard authentication or multi-user tenancy ([`70_dashboard.md`](70_dashboard.md)).
- Encrypting traces at rest (operator secures `workspace/` and `traces/`).
- Supply-chain signing of generated artifacts (provenance is regenerate + byte compare; see [`03_testing.md`](03_testing.md)).
- Blocking malicious **content** inside allowed read paths (only path/command policy).

## Failure posture

- Tool and policy violations return **errors in `tool_result`** or
  `subagent_return`, not silent allow.
- Egress violations raise `EndpointPinViolation` after `egress_blocked` is traced.
- Hard budget caps abort with `budget_event` then `run_end{final_status:"aborted"}`.

Quick reference: [`01_architecture.md`](01_architecture.md) § Failure modes,
[`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) (oral).

## Related specs

- [`01_architecture.md`](01_architecture.md) — Safety in depth diagram
- [`README.md`](README.md) — spec index
