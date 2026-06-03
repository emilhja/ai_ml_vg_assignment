# 00 Overview

Full spec index: [`specs/README.md`](README.md).

Goal: build a Claude Code / Codex competitor demo with one parent agent,
typed sub-agents (Grilling, Explorer, Coder, Reviewer) including parallel
fan-out, three context-engineering mechanisms (see [`01_architecture.md`](01_architecture.md)),
cost guards with live monitoring,
JSONL observability, and a fixture repository.

The competitor claim is about the agent shell and architecture: tool execution,
context management, sub-agent boundaries, tracing, safety, and cost
control. It is not a claim to beat frontier model quality.

Product architecture and technology inventory:

- [`specs/README.md`](README.md) — full index and reading order.
- `specs/01_architecture.md` — system context, agent topology, context
  engineering, observability, safety layers, module map.
- `specs/02_tech_stack.md` — Python dependencies, LLM stack, persistence,
  dashboard stack, Docker, configuration surfaces, codegen toolchain.
- `specs/03_testing.md`, `specs/04_demo_fixture.md`, `specs/25_security.md` —
  verification, demo workspace, safety rollup.

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
- Generated executable project code is reproducible from specs.
- **At least one demo scene shows ≥2 sub-agents executing with overlapping
  wall-clock and both returns consumed in the next parent step** (VG.1).
- A live statusline reports tokens, USD, per-agent breakdown, tool count,
  and model ID each parent step; a soft warning fires at 80% before the
  hard cap aborts (VG.3).

Execution model:

- The runtime is a single live path: an OpenRouter-backed parent loop via
  LiteLLM where the model decides each turn whether to call a tool or yield
  (VG.9). Sub-agent dispatch is model-driven, guided by the typed pipeline in
  `specs/12_subagent_pipeline.md`. The agent requires `OPENROUTER_API_KEY`.
- Docker is the primary execution boundary for demos
  (`specs/50_packaging.md`); in-process safety properties hold without it
  so unit tests run unsandboxed.
- Grading evidence is the **live demo**. Unit tests exercise the same live loop
  with an injected `FakeClient` (no network, per the no-network test rule) to
  prove caps, parallelism, safety, and context behavior reproducibly in CI.
- Product shape and stack: `specs/01_architecture.md`, `specs/02_tech_stack.md`.
- Source-of-truth and CLI details live in
  `specs/05_source_of_truth_and_generation.md`,
  `specs/15_cli_contract.md`, and
  `specs/16_chat_ui.md` (interactive TTY chat layout), and
  `specs/17_rich_tui_stack.md` (Rich / prompt-toolkit stack reference).
