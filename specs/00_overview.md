# 00 Overview

Goal: build a Claude Code / Codex competitor demo with one parent agent, one
Explorer sub-agent type, two context-engineering tricks, cost guards, JSONL
observability, replay, and a deterministic fixture repository.

The competitor claim is about the agent shell and architecture: tool execution,
context management, sub-agent boundaries, tracing, replay, safety, and cost
control. It is not a claim to beat frontier model quality.

Non-goals:

- No multi-level sub-agent tree.
- No hidden state outside JSONL traces and the spend file.
- No hand-maintained executable project code. Runtime code, tests, fixtures,
  and demo scripts must be generated from markdown specs, prompt/config
  markdown, or generated-code templates with traceable provenance.
- No sub-agent concurrency requirement unless a future spec adds a demo and
  test proving it.

Success criteria:

- A sanity edit mutates `fixtures/demo_repo/app.py`.
- The VG slide run proves parent-scoped tool-result compaction and Explorer
  offloading with `--show-context`.
- A cost-cap run aborts with `budget_event.budget_reason`.
- Replay reconstructs the same trace tree and parent contexts without model
  calls.
- Generated executable project code is reproducible from specs.

Extension criteria:

- `--live-model` may switch from deterministic routes to a real
  Anthropic-backed parent loop while preserving the same trace, budget,
  compaction, and Explorer boundaries. Deterministic routes remain the core VG
  proof.
