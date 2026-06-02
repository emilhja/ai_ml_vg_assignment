# Model Experience

Per-role notes on how each model behaves inside the VG agent shell, plus a
consolidated pricelist. This doc is descriptive guidance for choosing model
profiles; the executable source of truth for IDs and pricing constants stays in
`MODEL_CONFIG.md`. Keep the pricelist below in sync with that file.

Verified against the OpenRouter + LiteLLM live-model contract on 2026-05-28.

## Per-role experience

The agent shell (tool execution, context engineering, sub-agent boundaries) is
the VG claim — not raw model quality. These notes describe what each model
*feels* like in each role so you can pick a profile that balances cost and
reliability.

| Role | Model | Experience |
| --- | --- | --- |
| Parent (orchestrate) | `openrouter/anthropic/claude-sonnet-4.6` | Strongest at planning multi-spawn pipelines and respecting sub-agent boundaries. Most expensive; raise `VG_MAX_USD_PER_RUN` for fan-out flows. |
| Parent (orchestrate) | `openrouter/google/gemini-2.5-flash` | Default. Low cost, good enough for the scripted demo scenes; occasionally over-spawns Explorers. |
| Coder (mutate) | `openrouter/qwen/qwen3-coder-30b-a3b-instruct` | Anchored edits, few hallucinated APIs. Pair with `OPENROUTER_PROVIDER_ORDER=novita`. |
| Coder (mutate) | `openrouter/deepseek/deepseek-v4-flash` | Cheap agent/coding model; pair with `OPENROUTER_PROVIDER_ONLY_DEEPSEEK` for a low-cost host whitelist. |
| Explorer / Grilling | `openrouter/google/gemini-2.5-flash-lite` | Read-only roles; lite is sufficient and keeps fan-out cheap. |
| Reviewer (verify) | `openrouter/anthropic/claude-haiku-4.5` | Reliably reads files and returns PASS/FAIL. **Do not use a lite model here** — it skips verification. |
| Compactor | `openrouter/google/gemini-2.5-flash-lite` | Summarisation only; cheapest tier is fine. |

### Active demo profile

Sonnet parent + Haiku coder/reviewer, cheap models elsewhere:

```yaml
VG_PARENT_MODEL: openrouter/anthropic/claude-sonnet-4.6
VG_REVIEWER_MODEL: openrouter/anthropic/claude-haiku-4.5
VG_CODER_MODEL: openrouter/anthropic/claude-haiku-4.5
VG_EXPLORER_MODEL: openrouter/google/gemini-2.5-flash-lite
VG_GRILLING_MODEL: openrouter/google/gemini-2.5-flash-lite
VG_COMPACTOR_MODEL: openrouter/google/gemini-2.5-flash-lite
```

Override any role via the matching `VG_*_MODEL` env var or CLI flag
(see `specs/50_packaging.md`). Changing a model requires pricing in
`MODEL_CONFIG.md` or startup warns (set `VG_STRICT_MODEL_PRICING=1` to exit
instead).

## Comparative note: Haiku vs Gemini (observed runs)

This is a narrow, run-specific comparison from this repo and tooling path
(VG agent shell + LiteLLM/OpenRouter). It is not a universal benchmark of
either model family.

Compared traces:

- `traces/293ed45ebd6f.jsonl` (Haiku coder/reviewer path)
- `traces/322e77cad165.jsonl` (Gemini coder path)
- `traces/45bb5b875143.jsonl` (Gemini coder rerun, completed)
- `traces/7b633ed594d3.jsonl` (Haiku coder rerun, completed)

| Dimension | `293ed45ebd6f` (Haiku) | `322e77cad165` (Gemini) |
| --- | --- | --- |
| Completion signal | Explicit `run_end` with `final_status: ok` | No explicit parent `run_end` in captured trace tail |
| End-to-end timing | `run_end.duration_s = 51.212` | Trace window ~171.989 s (dominant wait in one subagent return latency) |
| Tool-call pattern | 5 tool calls: `spawn_subagent x2`, `write_file`, `read_file`, `run_bash` | 3 tool calls: `spawn_subagent x2`, `write_file` |
| Notable flow behavior | Single turn, both subagents return, clear final response path | First coder attempt returns `tool_error`; second attempt writes file but flow tail is incomplete |
| Tokens / cost | 30,286 tokens, `$0.069976` (`run_end` totals) | 13,601 tokens, `$0.0450845` (sum of `assistant_step` fields; no terminal run summary event) |

Neutral reading of this sample:

- The Haiku run appears operationally smoother (clean completion, fewer retries,
  clearer end state).
- The Gemini run appears cheaper in this sample, but slower in observed
  wall-clock due largely to long wait/approval segments in the trace.
- For model-speed conclusions, separate orchestration/approval latency from
  pure inference latency.
- Re-validate with repeated tasks before making policy changes; these two runs
  are informative but not statistically representative.

### Follow-up rerun (user-reported quality issue)

The newer pair (`45bb5b875143` vs `7b633ed594d3`) adds an important quality
signal:

| Dimension | `45bb5b875143` (Gemini coder) | `7b633ed594d3` (Haiku coder) |
| --- | --- | --- |
| Completion signal | `run_end` present, `final_status: ok` | `run_end` present, `final_status: ok` |
| End-to-end timing | `duration_s = 87.22` | `duration_s = 71.179` |
| Tokens / cost | 44,045 tokens, `$0.073463` | 42,266 tokens, `$0.086262` |
| Reviewer verdict | `PASS` | `PASS` |
| Observed implementation quality | Produced a calculator file that appears to contain runtime-risk UI code patterns | Produced a cleaner single-file implementation that aligns better with the requested behavior |

Critical assessment of the Gemini "finished but not working" finding:

- This finding is credible. The Gemini-generated calculator in
  `workspace/calc_gemini/calculator.py` includes likely runtime-breaking
  Tkinter usage (mixed geometry manager calls on the same widget and
  non-standard cursor value), even though syntax checks pass.
- The trace shows reviewer checks relied on `py_compile` + file reads, which
  validates syntax/static structure but can miss GUI runtime failures.
- Because both reruns were marked `PASS`, "run completed" and "artifact works"
  must be treated as separate quality axes in evaluations.
- In this specific task family (Tkinter GUI coding), Haiku coder appears more
  reliable despite higher cost in the rerun pair.
- This is still a small sample; keep cost/latency/quality comparisons tied to
  repeated task suites rather than single traces.

## Pricelist

USD per million tokens (per-Mtok). Mirrors the pricing constants in
`MODEL_CONFIG.md`.

| Model | Input $/Mtok | Output $/Mtok |
| --- | ---: | ---: |
| `openrouter/google/gemini-2.0-flash-001` (legacy) | 0.10 | 0.40 |
| `openrouter/google/gemini-2.5-flash` | 0.10 | 0.40 |
| `openrouter/google/gemini-2.5-flash-lite` | 0.10 | 0.40 |
| `openrouter/anthropic/claude-sonnet-4.6` | 3.00 | 15.00 |
| `openrouter/anthropic/claude-haiku-4.5` | 1.00 | 5.00 |
| `openrouter/qwen/qwen3-coder-30b-a3b-instruct` | 0.07 | 0.27 |
| `openrouter/deepseek/deepseek-v4-flash` | 0.0983 | 0.1966 |
| Unknown model (conservative preflight estimate) | 30.00 | 120.00 |

Notes:

- Local fallback pricing exists only for configured models. An unknown live
  model must have OpenRouter/LiteLLM return an explicit response cost, or live
  mode fails closed before the next step.
- Preflight budget checks use the conservative *Unknown model* estimate above.
- Expensive-provider warnings (`warn_expensive_provider`) fire for the slugs in
  `EXPENSIVE_OPENROUTER_PROVIDER_SLUGS` (default `alibaba,morph,parasail/fp8`);
  override with `OPENROUTER_EXPENSIVE_PROVIDERS`.

## Cross-provider tool use: Anthropic vs Gemini vs OpenAI

The recommended demo profile already mixes vendors (Sonnet parent, Haiku
reviewer, Gemini Flash coder/explorers). This section summarises what that
mixing costs and why it works here.

### The formats differ, but have converged on JSON Schema

All three vendors implement the same loop — describe tools, model emits a
structured call, your code runs it, you feed the result back — and all three
settled independently on JSON-Schema-based tool definitions. The wire shapes
still differ:

- **OpenAI** — `tools: [{type: "function", function: {name, description,
  parameters}}]`; the model returns a `tool_calls` array.
- **Anthropic** — "tool use" with `name` / `description` / `input_schema`;
  calls and text arrive as separate **content blocks**, and `system` is a
  top-level parameter, not a message.
- **Gemini** — "function declarations" with `FunctionDeclaration` objects
  (Protocol-Buffer-style types over JSON Schema).

These schema details — especially how `system` and parallel calls are
represented — are the most common source of migration bugs when talking to the
raw vendor SDKs.

### Why this repo mostly avoids those issues

This project never touches the raw vendor SDKs. Every call goes through
**LiteLLM → OpenRouter** (`live_model_client.py`, endpoint pinned to
`openrouter.ai`), which normalises all three vendors to one OpenAI-style
request/response shape. Tools are defined once and the adapter translates per
vendor, so the parent loop and sub-agents see a single uniform tool-call
schema regardless of which model fills which role. That normalisation layer is
exactly what makes the heterogeneous demo profile safe.

### Issues that can still surface when models communicate

Cross-vendor pipelines fail at the **plumbing**, not the model quality:

- **Chat-template / output-format mismatches** — some models (notably certain
  open-weight "tool-calling specialist" models) emit custom tool-call syntax
  that an OpenAI-compatible gateway parses poorly, so they score far worse in a
  real serving stack than on leaderboards. Prefer the models in the pricelist
  above, which are known-good through OpenRouter.
- **Malformed intermediate results** — a prompt that works in a single-model
  playground can break inside the multi-step pipeline because a *prior* tool
  result (or sub-agent return) was malformed. In this repo the ≤2 KB Explorer
  return summary and parent-scoped compaction marker are the hand-off contract;
  keep them well-formed so the next parent step parses cleanly.
- **Parallel tool calls** — vendors differ on whether/how they batch calls.
  Our fan-out (`spawn_subagents`) is orchestrated by the parent loop, not by a
  single model's native parallel-call feature, which sidesteps the divergence.
- **Coordination overhead** — more (or more diverse) agents is not automatically
  better; mismatched coordination adds cost and error cascades. `MAX_SUBAGENT_DEPTH
  = 1` and the typed pipeline cap that blast radius here.

### Is it better to keep similar models in a repo like this?

Mixed-vendor is fine **because** of the LiteLLM/OpenRouter abstraction, and
the per-role tiering (cheap read-only Explorers, a non-lite Reviewer, a strong
parent) is a deliberate cost/quality trade-off worth keeping. Practical
guidance for this repo:

- **Mix by role, not at random.** Route cheap models to read-only/summarisation
  roles and reserve a stronger model for the parent and the Reviewer, where
  instruction-following matters most.
- **Keep the gateway uniform.** As long as every model is reached through the
  same OpenRouter adapter, schema differences are hidden — do **not** add a
  second raw vendor SDK path.
- **Pin and price every model.** A model that is not in `MODEL_CONFIG.md`
  triggers a startup pricing warning (or an exit under
  `VG_STRICT_MODEL_PRICING=1`); unknown live models also fail closed if no cost
  is returned.
- **Single-vendor is simpler when reproducibility dominates.** If you want the
  fewest cross-vendor surprises (uniform tokenizer behaviour, identical
  parallel-call semantics, one pricing source), the all-`gemini-2.5-flash`
  default profile is the lowest-variance choice — at some quality cost on the
  parent/reviewer roles.

Sources:

- [Function Calling & Tool Use: The Complete Guide for GPT, Claude, and Gemini (2026)](https://ofox.ai/blog/function-calling-tool-use-complete-guide-2026/)
- [OpenAI API vs Anthropic API vs Gemini API: a practical guide (eesel AI)](https://www.eesel.ai/blog/openai-api-vs-anthropic-api-vs-gemini-api)
- [Agent Skills as an Open Standard (MindStudio)](https://www.mindstudio.ai/blog/agent-skills-open-standard-claude-openai-google)
- [I Tested 13 Local LLMs on Tool Calling — 2026 Eval Results](https://www.jdhodges.com/blog/local-llms-on-tool-calling-2026-pt1-local-lm/)
- [The Market Shift: Why Multi-agent LLM Coordination Matters in 2026 (Sesame Disk)](https://sesamedisk.com/multi-agent-llm-coordination-2026/)
- [Tool Calling Explained: The Core of AI Agents (Composio, 2026)](https://composio.dev/content/ai-agent-tool-calling-guide)
