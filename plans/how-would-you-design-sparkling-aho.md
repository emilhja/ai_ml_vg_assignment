# Plan: VG-Assignment — Claude-Code / Codex Competitor

## Context

The assignment (`assignment_background.md`) requires building a competitor to
Claude Code / Codex featuring **sub-agent management** and **context
engineering**, demonstrated live in class. Hard constraints from the brief:

- **Zero hand-written code.** All implementation must be AI-generated. The
  "real source code" of this project is the `.md` spec/prompt files — Python
  is downstream of them. Provenance is part of the deliverable: README must
  document the one-command generation flow, generated Python under
  `src/vg_agent/` must be reproducible from the specs, and verification must
  delete/regenerate that tree and compare it to the committed/generated tree
  except for allowed timestamps or trace output.
- **Live demo gates the grade.** Anything not demonstrable on stage scores
  zero.
- **Scope ≈ 3 hours** of expert collaboration time (the brief's stated
  target).
- **Implementation target:** Python + Anthropic SDK. Sonnet 4.6 (parent
  agent), Haiku 4.5 (Explorer sub-agent / compactor). Windows + Git Bash dev
  environment. Exact Anthropic API model IDs and pricing constants are pinned
  once in the generated config/spec layer; prose may use marketing names, but
  runtime code never does.

### Why Python + Anthropic (the brief says language is irrelevant)

The specs are deliberately written language-neutral; any compliant
implementation could regenerate them. The implementation choice is justified
on three pragmatic grounds:

1. **Anthropic prompt caching** materially cuts agent-loop cost; in a live
   demo where every API call is visible, it stabilises latency and budget.
2. **Two-tier model strategy is native to Anthropic** (Sonnet for the
   parent, Haiku for the Explorer) — gives the demo a concrete "we offload
   to a smaller model AND a separate context window" slide.
3. **Existing tooling familiarity** — the dev environment already has an
   Anthropic key and the `anthropic` SDK is the fastest stack for
   AI-generated tool-use code.

The highest implementation-risk item (tool-use plumbing) is the same on any
SDK; this choice does not increase risk over OpenAI.

### Design refinements after planning review

- The second context-engineering trick was swapped from file-read
  summarisation to **tool-result compaction** because the latter fires on
  every non-trivial run instead of needing a contrived trigger.
- A **`--replay`** mode was added as a forensic viewer over a richer trace
  schema, so the demo is bulletproof against API or network hiccups.
- A **seeded fixture repo** under `fixtures/demo_repo/` was added so demo
  prompts have a deterministic substrate.
- Cost accounting was unified: actual spend is recorded; the per-run cap is
  a ceiling, not a fixed charge.

## Architecture (one parent, one sub-agent type)

- **Main agent loop.** Tools: `read_file`, `read_file_range`, `write_file`,
  `edit_file`, `run_bash`, `spawn_subagent`. Model: Sonnet 4.6 marketing
  name in prose; exact API ID is read from the generated config.
- **Explorer sub-agent.** The only sub-agent type. Accepts a search
  question, runs `grep`/`read_file` iteratively in its own fresh context
  window, returns a bounded ≤ 2 KB summary to the parent. Model: Haiku 4.5
  marketing name in prose; exact API ID is read from the generated config.
- **Sub-agent rules** (specced and enforced in code, not by trust):
  - `MAX_SUBAGENT_DEPTH = 1` — sub-agents cannot themselves spawn sub-agents.
  - Fresh context window per spawn.
  - Stricter step cap than the parent.
  - Cheaper model.

## Context engineering — exactly two tricks, fully specified

### 1. Sub-agent offloading

The parent never sees the Explorer's intermediate tool calls or noisy
results — only the bounded ≤ 2 KB summary string returned by the Explorer.
**Proof artifact:** `--show-context <step>` dumps the parent's actual
message-history array at any step in the run; it must contain the Explorer's
return summary as a single `tool_result` block and contain none of the
Explorer's intermediate `read_file`/`grep` results. The eval harness asserts
this directly by parsing the dumped history.

### 2. Tool-result compaction (concrete contract)

**Trigger.** Immediately after a `tool_result` is appended to the parent's
in-flight message history, the orchestrator counts its tokens. If
`tokens(tool_result) > K_COMPACT` (default `K_COMPACT = 4000`), a compaction
is performed before the next model call.

**Compaction operation.** A Haiku 4.5 call with a fixed system prompt (in
`PROMPTS.md`) summarises the tool result. The original `tool_result` block
in the parent's message history is replaced with:

```
[COMPACTED tool_result for tool_use_id=<id>]
Summary (≤300 tokens): <model summary>
Original size: <X> tokens. Trace pointer: <run_id>:event:<n>.
Use read_file_range or re-invoke the tool to retrieve specific details.
```

**Lossiness rule.** The parent's *in-flight* message history is the only
thing compacted. The JSONL trace ALWAYS retains the full original
`tool_result` content as a separate `tool_result` event (see schema below);
nothing is lost from disk.

**Insertion point.** Compaction happens between turns, not within a turn.
The current turn's `tool_result` block is replaced in place; previously
compacted blocks are not re-compacted.

**Proof artifact.** Each compaction emits a `compaction` event in the
JSONL with `before_tokens`, `after_tokens`, `tool_use_id`,
`original_event_idx`, and `original_sha256`. `original_event_idx` points to
the original `tool_result` event, and `original_sha256` is the SHA-256 hash
of that event's full `tool_result.result_full`. The trace tree printer
renders these inline as `↘ compacted 4127 → 287 tokens (tool_use xyz)`.
The eval harness asserts ≥ 1 such event for the VG-slide run AND asserts
the parent's `--show-context` no longer contains the original content for
that `tool_use_id`.

`read_file_range` stays as a tool but is not part of the
context-engineering narrative.

## Spec files — 6, plus README + PROMPTS + MODEL_CONFIG (the actual deliverables)

```
specs/
  00_overview.md           # goal, non-goals, success criteria, architecture diagram
  10_main_agent.md         # main-agent system prompt + loop pseudocode
  11_subagent_explorer.md  # Explorer system prompt + return contract
  20_tools.md              # JSON schema for every tool + Windows path/shell rules
  30_runtime_governance.md # cost caps, repetition guard, retries, JSONL event schema, replay
  40_demo_and_eval.md      # 3 demo prompts (1:1 with eval), property assertions, fixture spec
PROMPTS.md                 # parent + Explorer + compaction system prompts at top level
                           # (the "specs ARE the source code" thesis)
MODEL_CONFIG.md            # exact Anthropic API model IDs + pricing constants
README.md                  # one-click build pipeline + how to run/demo
```

`50_observability` is folded into `30_runtime_governance` as a single
"runtime" doc. `BUILD.md` is folded into `README.md`.

## Cost guard — concrete numbers and one accounting model

In `30_runtime_governance.md`:

- Concrete Anthropic API IDs and price constants are declared once:
  `PARENT_MODEL_ID`, `EXPLORER_MODEL_ID`, `COMPACTOR_MODEL_ID`, and
  per-million-token input/output prices for each. Generated runtime code must
  import/read these values from config; it must not contain marketing names
  such as "Sonnet 4.6" or "Haiku 4.5" in executable model-selection paths.
- `MAX_PARENT_STEPS = 15`, `MAX_SUBAGENT_STEPS = 8`
- `MAX_SUBAGENT_DEPTH = 1`, `MAX_CONCURRENT_SUBAGENTS = 2`
- `MAX_TOKENS_PER_RUN = 80_000`
- `MAX_USD_PER_RUN = 0.50`, `MAX_USD_PER_DAY = 5.00`
  (persisted to `%LOCALAPPDATA%/vg_agent/spend.json`)
- `WALL_CLOCK_TIMEOUT = 120 s` per run, `30 s` per tool call
- `K_COMPACT = 4000` tokens
- **Repetition guard:** same tool + same args twice in a row → inject "try a
  different approach"; third time → abort.
- **Retries:** max 2, only on 429/5xx, exponential backoff, counted against
  the budget.

**Accounting model (single source of truth).** Every API call's actual
input + output token cost is recorded in real time using the public
Anthropic price constants pinned in `MODEL_CONFIG.md`. `spend.json`
accumulates **actual** spend, not the cap. The cap is enforced
*prospectively*: before each model call, the guard checks
`running_spend + worst_case_next_call_cost ≤ MAX_USD_PER_RUN`; on failure
it aborts and records the actual spend so far. Daily cap is checked the
same way against `spend.json`.

A single `BudgetGuard` object the agent loop consults every step.
Unit-tested without an API key.

## Observability — JSONL event schema (sufficient for forensic replay)

`traces/<run_id>.jsonl` contains one JSON object per *event*, not per step.
Every event has `run_id`, `event_idx`, `timestamp_iso`, `agent_id`,
`parent_id` (null for root agent), and a `kind` discriminator. Per `kind`:

| `kind` | Additional fields |
|---|---|
| `user_prompt` | `prompt` (full text) |
| `assistant_step` | `model`, `step_idx`, `tokens_in`, `tokens_out`, `cost_usd`, `assistant_text` (full), `tool_calls` (array of `{tool_use_id, name, args}`), `stop_reason` |
| `tool_result` | `tool_use_id`, `tool`, `result_full` (full content), `bytes`, `tokens`, `latency_ms`, `status` |
| `compaction` | `tool_use_id`, `before_tokens`, `after_tokens`, `summary`, `original_event_idx`, `original_sha256` |
| `subagent_spawn` | `child_agent_id`, `question`, `model` |
| `subagent_return` | `child_agent_id`, `summary` (≤2 KB), `child_total_cost_usd`, `child_total_tokens` |
| `budget_event` | `budget_reason` ∈ {`step_cap`, `token_cap`, `usd_cap`, `daily_cap`, `repetition_abort`, `timeout`}, `details` |
| `run_end` | `final_status` ∈ {`ok`, `aborted`, `error`}, `total_cost_usd`, `total_tokens`, `duration_s` |

The top-level `kind` remains the event discriminator. `budget_event` uses
the nested `budget_reason` field so the budget-abort cause is not confused
with event type.

Because every event records its full payload, `--replay <jsonl>` is a
**forensic viewer**: it reconstructs the parent and sub-agent transcripts
verbatim, re-renders the trace tree, replays compaction events with
before/after token counts, and produces output indistinguishable from the
live run. No model is called during replay.

`--trace` pretty-prints the tree live as events are written.
`--show-context <step_idx>` reconstructs the parent's message history at
the start of the given step from the event stream — this is the artifact
that proves both context-engineering claims.

## Demo substrate — `fixtures/demo_repo/`

Demos cannot run against an empty workspace. A small deterministic fixture
repo is checked into `fixtures/demo_repo/` containing:

```
fixtures/demo_repo/
  app.py            # entry-point with foo() and bar() callers; imports auth, utils
  auth/
    __init__.py
    session.py      # ~80 LOC, real-looking session/token handling
    middleware.py   # ~60 LOC, decorator-based auth checks
  utils.py          # helper functions
  README.md         # short repo description
  data/             # one large file for compaction trigger
    sample.log      # >200 KB log file used by demo run #2 to trigger K_COMPACT
```

Demo runs `cd fixtures/demo_repo && python -m vg_agent --task "..."`. The
`40_demo_and_eval.md` spec defines the exact contents of every fixture file
so the implementation can regenerate them deterministically.

## Windows + Git Bash gotchas (pinned in `20_tools.md`)

- `run_bash` invokes `bash -c` explicitly, never `cmd`.
- Path normalisation at the tool boundary: `C:\...` ↔ `/c/...`.
- `.env` loaded via `set -a; source .env; set +a` — Git Bash doesn't
  auto-load.
- `git config core.autocrlf=false`; write files with `\n` only (mixed
  endings break grep-based Explorer assertions).
- Daily-spend file at a fixed absolute path under `%LOCALAPPDATA%`; do not
  rely on `~` resolution.

## Demo plan (5 minutes, 3 runs against `fixtures/demo_repo/`)

1. **Sanity run** — "rename `foo` to `bar` in `app.py`." ~10 s. Proves the
   loop + tools work.
2. **The VG slide** — "find every place auth is handled in this repo and
   summarise in one paragraph." This run is deterministic:
   - Parent handles the user prompt.
   - Parent directly calls `read_file data/sample.log`, producing a large
     parent `tool_result`.
   - Parent compacts that result because it exceeds `K_COMPACT`.
   - Parent then spawns Explorer to inspect `auth/` and summarise auth
     handling.
   - `--show-context <last_step>` proves both claims: the parent context
     contains the compacted marker instead of the original `sample.log`
     content, and it contains only the Explorer return summary, not Explorer
     intermediate tool calls or tool results.
   The trace tree shows the parent's clean context vs. the Explorer's
   separate transcript. Compaction is parent-scoped for this demo; Explorer
   context replay/viewing is not required.
   *This is the run the grade hinges on.*
3. **Cost-cap demo** — adversarial prompt deliberately designed to loop
   (e.g. "search this repo for the string `__VG_SENTINEL_NEVER_PRESENT__`
   and don't stop until you find it"). `BudgetGuard` trips on
   `MAX_PARENT_STEPS` or `MAX_USD_PER_RUN`. The trace ends with a
   `budget_event` followed by `run_end` with `final_status: "aborted"`.

Closer: 60-second architecture walk-through with `00_overview.md` on
screen, satisfying the rubric's "must understand the architecture"
requirement.

**Backup:** screencast recorded ahead of class + saved JSONL traces
playable via `--replay` (forensic, full-fidelity).

## Time budget (3 h active collaboration)

| Block | Minutes | Output |
|---|---:|---|
| Specs (6 files + PROMPTS) | 45 | The bulk of the real work |
| Generate code from specs | 30 | Hello-world run green |
| BudgetGuard + JSONL events + tree printer + `--replay` | 30 | Sanity run passes; replay round-trips |
| Explorer + tool-result compaction + `--show-context` | 30 | VG-slide run passes |
| Fixture repo seeding + demo runs + screencast | 20 | Backup ready |
| Buffer | 15 | The one thing that will break |
| 1-page report | 10 | (separate from coding) |

Highest overrun risk per the planning review: tool-use plumbing on the
Anthropic SDK (have a known-good `tool_use`/`tool_result` snippet pinned
before starting); spec churn (cap rewrites at 1 per file).

## Critical files (all to be created)

- `C:/Users/emil_/vscode/vg_assignment/specs/00_overview.md`
- `C:/Users/emil_/vscode/vg_assignment/specs/10_main_agent.md`
- `C:/Users/emil_/vscode/vg_assignment/specs/11_subagent_explorer.md`
- `C:/Users/emil_/vscode/vg_assignment/specs/20_tools.md`
- `C:/Users/emil_/vscode/vg_assignment/specs/30_runtime_governance.md`
- `C:/Users/emil_/vscode/vg_assignment/specs/40_demo_and_eval.md`
- `C:/Users/emil_/vscode/vg_assignment/PROMPTS.md`
- `C:/Users/emil_/vscode/vg_assignment/MODEL_CONFIG.md`
- `C:/Users/emil_/vscode/vg_assignment/README.md`
- `C:/Users/emil_/vscode/vg_assignment/fixtures/demo_repo/...` (seeded; spec
  in `40_demo_and_eval.md`)
- Generated (not hand-written) Python under
  `C:/Users/emil_/vscode/vg_assignment/src/vg_agent/`

## Verification (end-to-end, runnable against the fixture repo)

1. **Sanity run.**
   `(cd fixtures/demo_repo && python -m vg_agent --task "rename foo to bar in app.py")`
   — exits 0, file modified, trace shows ≤ 6 parent steps,
   `final_status: "ok"`.
2. **Sub-agent + compaction run.**
   `(cd fixtures/demo_repo && python -m vg_agent --task "find all auth handling and summarise" --trace)`
   — JSONL contains ≥ 1 `subagent_spawn`/`subagent_return` pair AND ≥ 1
   parent-scoped `compaction` event. The test asserts at least one parent
   `tool_result` exceeds `K_COMPACT`; a `compaction` event exists for that
   parent `tool_use_id`; the event includes `original_event_idx` and
   `original_sha256`, where `original_sha256` equals the SHA-256 of the
   original full `tool_result.result_full`; `--show-context <last_step>` on
   the parent contains the compacted marker; it does NOT contain the original
   `sample.log` content; and it contains only the Explorer return summary,
   not Explorer intermediate tool calls or tool results.
3. **Cost-cap run.**
   `(cd fixtures/demo_repo && python -m vg_agent --task "<adversarial loop prompt>")`
   — JSONL ends with a `budget_event` followed by `run_end` with
   `final_status: "aborted"`. `spend.json` increment equals the
   `total_cost_usd` reported on `run_end` (NOT the cap). Increment is
   strictly less than `MAX_USD_PER_RUN` (cap is a ceiling) and
   strictly greater than zero.
4. **Replay round-trip.**
   `python -m vg_agent --replay traces/<run_id>.jsonl --trace` re-renders
   the same tree and the same `--show-context` outputs as the live run for
   every recorded step, with no API calls made (verifiable by network
   sniffing or by mocking the Anthropic client to raise on any call).
5. **Unit tests** for `BudgetGuard` (prospective check, daily cap,
   repetition guard, retry accounting), JSONL event schema
   (`budget_event.budget_reason`, `compaction.original_event_idx`,
   `compaction.original_sha256`, round-trip serialisation), and tool schemas
   pass without an API key.
6. **Daily-cap test.** Set `spend.json` to within `MAX_USD_PER_RUN - 0.01`
   of the daily cap; attempt a run; assert refusal before any API call is
   issued (verifiable by mocking the Anthropic client to raise on any
   call). `spend.json` is unchanged after the refusal.
7. **Generated-code provenance test.** Run the README's documented
   generation command, delete and regenerate `src/vg_agent/` from the `.md`
   specs, and assert the regenerated Python tree matches the committed /
   generated version except for explicitly allowed timestamps or trace
   output. The full test suite must pass after regeneration without manual
   edits to generated Python.
