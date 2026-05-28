# 00 Overview

Goal: build a Claude Code / Codex competitor demo with one parent agent,
typed sub-agents (Grilling, Explorer, Coder, Reviewer) including parallel
fan-out, two context-engineering tricks, cost guards with live monitoring,
JSONL observability, replay, and a deterministic fixture repository.

The competitor claim is about the agent shell and architecture: tool execution,
context management, sub-agent boundaries, tracing, replay, safety, and cost
control. It is not a claim to beat frontier model quality.

Non-goals:

- No multi-level sub-agent tree (`MAX_SUBAGENT_DEPTH = 1` is hard).
- No hidden state outside JSONL traces and the spend file.
- No hand-maintained executable project code. Runtime code, tests, fixtures,
  and demo scripts must be generated from markdown specs, prompt/config
  markdown, or generated-code templates with traceable provenance.

Success criteria:

- A sanity edit mutates `fixtures/demo_repo/app.py` via a Coder sub-agent
  (the parent has no direct write tools).
- The VG slide run proves parent-scoped tool-result compaction and Explorer
  offloading with `--show-context`.
- A cost-cap run aborts with `budget_event.budget_reason`.
- Replay reconstructs the same trace tree and parent contexts without model
  calls.
- Generated executable project code is reproducible from specs.
- **At least one demo scene shows ≥2 sub-agents executing with overlapping
  wall-clock and both returns consumed in the next parent step** (VG.1).
- A live statusline reports tokens, USD, per-agent breakdown, tool count,
  and model ID each parent step; a soft warning fires at 80% before the
  hard cap aborts (VG.3).

Execution model:

- The default grading demo path is deterministic replay/fake-client behavior:
  the parent loop still records model turns and tool decisions, but no
  external API is required for proof. Optional `--live-model` runs use a real
  OpenRouter-backed parent loop via LiteLLM where the model decides each turn
  whether to call a tool or yield (VG.9). Sub-agent dispatch is model-driven,
  guided by the typed pipeline in `specs/12_subagent_pipeline.md`.
- `--replay <trace.jsonl>` reproduces a previously recorded live run via
  `FakeClient` with no network call. This is the CI / deterministic path.
- Docker is the primary execution boundary for demos
  (`specs/50_packaging.md`); in-process safety properties hold without it
  so unit tests run unsandboxed.
- Primary grading evidence is deterministic first: replay/fake-client traces
  prove caps, parallelism, safety, and context behavior. Live OpenRouter runs
  are optional polish, not the only way to satisfy a rubric item.
- Source-of-truth and CLI details live in
  `specs/05_source_of_truth_and_generation.md` and
  `specs/15_cli_contract.md`.
