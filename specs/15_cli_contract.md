# 15 CLI Contract

The executable entrypoint is:

```bash
python -m vg_agent
```

Docker services use the same entrypoint through Compose. Local `uv run` is a
developer convenience only; grading commands use `docker compose`.

## Commands and modes

Exactly one of these modes is required:

- `--task TEXT` — run one task against the current workspace.
- `--chat` — start a multi-turn REPL using one trace/session.
- `--replay TRACE.jsonl` — replay a recorded trace without network access.
- `--seed-fixture` — write the deterministic fixture repository into the
  current workspace, then exit.

## Flags

| Flag | Default | Behavior |
|---|---:|---|
| `--trace` | off | Print a human-readable trace tree and the JSONL path after the run. |
| `--show-context N` | unset | Print parent-visible context at parent step `N`. |
| `--live-model` | off | Use Anthropic Messages API. Requires `ANTHROPIC_API_KEY`. |
| `--budget` | off | Print a machine-readable JSON budget summary at run end. |
| `--require-approval off|writes|all` | config/default | Gate tools before execution. |
| `--yes` | off | Auto-approve gated tools and record `approval{decision:"auto"}`. |
| `--no-redact` | off | Disable trace redaction and print a warning to stderr. |
| `--max-usd FLOAT` | config/default | Override per-run USD cap. |
| `--max-tokens INT` | config/default | Override per-run token cap. |
| `--parent-model MODEL_ID` | config/default | Override parent model. |
| `--subagent-model MODEL_ID` | config/default | Override all sub-agent models unless type-specific env/config is set. |
| `--no-grill` | off | Skip the Grilling ambiguity step for the current task. |

## Streams and exit codes

- Final user-facing answers go to stdout.
- Statusline, approval prompts, warnings, and live progress go to stderr.
- JSONL traces are written to `<workspace_root>/traces/<run_id>.jsonl`.
- `0`: successful run, replay, seed, or chat exit.
- `1`: validation/config/tool-policy error.
- `2`: missing live-model secret or refused live-model network setup.
- `3`: budget, timeout, or user-abort termination.

Replay mode must not open the network. `vg-agent` Compose service runs with
`network_mode: none` and is the canonical replay/smoke-test path.

## Sub-agent tools

Parent model tool schema exposes both:

- `spawn_subagent(request: SubagentRequest) -> SubagentReturn`
- `spawn_subagents(requests: list[SubagentRequest]) -> list[SubagentReturn]`

`spawn_subagents` is the only parallel primitive. A task with two or more
independent inspection targets must use one `spawn_subagents` call rather
than serial `spawn_subagent` calls.
