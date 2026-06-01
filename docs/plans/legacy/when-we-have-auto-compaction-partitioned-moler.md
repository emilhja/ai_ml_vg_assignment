# Conversation-level compaction + per-model context-window data

## Context

The user wants the live chat agent to show, when compaction happens, the
context window **before vs after** (e.g. `80k -> 20k`), the **% reduced**, and a
note that the **full context is still retained separately** in case the
compaction summary loses something. They also want a **separate data file**
holding each model's context-window size and recommended auto-compaction
threshold, starting with `gemini-2.5-flash`, Sonnet, and Haiku.

**What exists today (so we don't reinvent it):**

- Compaction is **per-tool-result only**: `_compact_if_needed`
  (`src/vg_agent/agent.py:316`) swaps a single tool result over
  `K_COMPACT=4000` for a marker. There is **no conversation-level compaction**
  that takes a whole 80k history down to 20k.
- There is **no per-model context-window data** anywhere. `MAX_TOKENS_PER_RUN`
  is a cumulative *spend cap*, not a window. Output tokens are hardcoded.
- The Compaction system prompt at `PROMPTS.md:112` and `COMPACTOR_MODEL_ID`
  are generated but **never wired up** — we will finally use them.
- The statusline already prints `ctx Nk in`, and per-tool compaction prints
  `[context] compacted X -> Y tokens` (`__main__.py:425`). We extend these.

**Spec-first rule:** never hand-edit `src/vg_agent/*`. Edit specs / `PROMPTS.md`
/ `MODEL_CONFIG.md` / the new data file / the templates in
`scripts/generate_project.py`, then `python scripts/generate_project.py --clean`.

## Recommended design (answers "how should compaction work?")

1. **Threshold-based auto-trigger.** Before each parent model call in the live
   loop, estimate context tokens; if they exceed `window * compact_fraction`
   for the active model, run one compaction pass, then continue.
2. **Keep the tail verbatim, summarize the head.** Retain the most recent N
   turns (the live working set) unchanged; fold everything older into a single
   summary message produced by `COMPACTOR_MODEL_ID` using the existing
   `PROMPTS.md` compaction prompt. Folding starts from the front and the
   retained tail must begin on a `user`-role boundary so an assistant
   `tool_call` is never split from its `tool_result`.
3. **The trace is the safety net.** The full pre-compaction history already
   lives in the JSONL trace as `user_prompt` / `assistant_step` /
   `tool_result` events; the summary message only replaces the *in-memory*
   working set. The emitted event carries a pointer back to the trace so the
   "full context saved separately" guarantee is literally true and
   retrievable via `--show-context` / `--replay`.
4. **Manual override.** `/compact` runs the same pass on demand.
5. **Distinct event kind.** Use `context_compaction` (not the existing
   per-tool `compaction`) so tests/observability stay unambiguous.

## Changes

### 1. New data file — `CONTEXT_WINDOWS.md` (repo root, new source of truth)

Per-model window + recommended auto-compaction fraction, regex-parseable like
`MODEL_CONFIG.md` (a verification date in prose, like `MODEL_CONFIG.md`):

```yaml
GEMINI_2_0_FLASH_CONTEXT_WINDOW: 1000000
GEMINI_2_0_FLASH_COMPACT_FRACTION: 0.80
GEMINI_2_5_FLASH_CONTEXT_WINDOW: 1048576
GEMINI_2_5_FLASH_COMPACT_FRACTION: 0.80
CLAUDE_HAIKU_4_5_CONTEXT_WINDOW: 200000
CLAUDE_HAIKU_4_5_COMPACT_FRACTION: 0.80
CLAUDE_SONNET_4_6_CONTEXT_WINDOW: 200000
CLAUDE_SONNET_4_6_COMPACT_FRACTION: 0.80
```

### 2. `MODEL_CONFIG.md` — add `gemini-2.5-flash` as a covered model

Add `openrouter/google/gemini-2.5-flash` to the optional-models prose and add
pricing constants `GEMINI_2_5_FLASH_INPUT_PER_MTOK` /
`GEMINI_2_5_FLASH_OUTPUT_PER_MTOK` (verify against OpenRouter on the same date
line the file already tracks). The pinned default parent stays
`gemini-2.0-flash-001`; 2.5-flash becomes selectable via `--parent-model`.

### 3. `scripts/generate_project.py`

- **`SOURCE_INPUTS`** (`:11`): append `ROOT / "CONTEXT_WINDOWS.md"` so it feeds
  `SPEC_DIGEST` and the provenance check.
- **`read_config`** (`:23`): add the new gemini-2.5-flash pricing keys; add a
  `read_context_windows()` helper (mirrors the regex loop) and merge its keys
  into the `cfg` dict passed to `render`.
- **`config.py` template** (`:102`): add gemini-2.5-flash to
  `PRICING_USD_PER_MTOK`; add new constants:
  ```python
  CONTEXT_WINDOW_TOKENS = { "<id>": __..._CONTEXT_WINDOW__, ... }
  AUTO_COMPACT_FRACTION = { "<id>": __..._COMPACT_FRACTION__, ... }
  DEFAULT_CONTEXT_WINDOW = 128_000
  DEFAULT_COMPACT_FRACTION = 0.80
  COMPACT_KEEP_RECENT_TURNS = 4
  ```
- **`agent.py` template** (run_live_task region, generated `:732`):
  - Add `compact_conversation(recorder, messages, model_id, guard, *, client=None, reason, deterministic=False) -> dict`. It computes `before = _estimate_message_tokens(PARENT_SYSTEM_PROMPT, messages)`, splits head/tail at a user boundary keeping `COMPACT_KEEP_RECENT_TURNS`, builds a summary (live: `client.complete` with `COMPACTOR_MODEL_ID` + `COMPACTION_SYSTEM_PROMPT`, recording cost via `guard`; deterministic: a fixed summary string naming folded turn/token counts), rewrites `messages[:]` in place, computes `after`, and `recorder.emit("context_compaction", before_tokens, after_tokens, percent_reduced, model, window, threshold, reason, summary, trace_pointer=recorder.run_id)`. Returns the event.
  - In the loop (around `:759`), after `expected_in = _estimate_message_tokens(...)` and before `before_model_call`: look up `window`/`threshold` from the new config dicts; if `expected_in > threshold` and the head is foldable, call `compact_conversation(..., reason="auto")` and recompute `expected_in`. Compact at most once per iteration to avoid loops.
- **`__main__.py` template** (generated `:91`, `:563`, `:388`):
  - Add `/compact` to `SLASH_COMMANDS` + `SLASH_COMMAND_HELP`, and a handler in `_chat_loop` that calls `compact_conversation` on `conversation` (live client when `--live-model`, else `deterministic=True`) and prints `_format_compaction_summary(event)`.
  - Add `_format_compaction_summary(event)` →
    `[context] /compact: 80.2k -> 19.6k tokens (76% smaller) | gemini-2.5-flash window 1.0m, threshold 80% | full history retained in trace <run_id> (use --show-context / --replay)`
    (reuse `_format_compact_number`).
  - Extend `_format_progress_event` + color map to render `context_compaction` for the **auto** path during live runs (label `[context] auto-compact ...`).
  - Optionally enrich the statusline (`_format_chat_statusline:316`) to show window usage: `ctx 19.6k/1.0m (2%)` using `CONTEXT_WINDOW_TOKENS`.

### 4. Spec updates (source of truth, regenerate after)

- `specs/15_cli_contract.md`: add `/compact` row; note auto-compaction in `--chat`.
- `specs/30_runtime_governance.md`: add `context_compaction` to the event-kinds list and its fields (`before_tokens`, `after_tokens`, `percent_reduced`, `window`, `threshold`, `reason`, `trace_pointer`); document the new constants and the "full history retained in JSONL" invariant; add a compaction rollup to the SQLite list.
- `specs/10_main_agent.md`: document conversation-level compaction in the parent live loop (keep-tail / summarize-head, COMPACTOR model + compaction prompt).
- `specs/60_observability.md`: document the statusline window field and the auto-compact progress line.
- `PROMPTS.md`: keep the existing compaction prompt; it is now actually consumed.

### 5. Tests — `tests/test_vg_agent.py`

- **Config/provenance**: assert `CONTEXT_WINDOW_TOKENS` / `AUTO_COMPACT_FRACTION` contain the 4 models and that gemini-2.5-flash pricing exists; the existing regenerate-and-byte-compare provenance test now also covers `CONTEXT_WINDOWS.md`.
- **`compact_conversation` deterministic**: build a synthetic `messages` list, call with `deterministic=True`, assert `after < before`, `percent_reduced` correct, tail preserved on a user boundary, summary present, and a `context_compaction` event emitted. No network.
- **Auto-trigger in live loop**: use the `FakeClient`/`ModelTurn` pattern; seed a large `history` (or shrink the window via `--parent-model`/config monkeypatch) so `expected_in` exceeds threshold; assert a `context_compaction` event precedes the next `llm_start`, the in-memory history shrank, and the original `assistant_step`/`tool_result` events remain in the trace (safety-net assertion).

## Verification

```bash
python scripts/generate_project.py --clean   # regenerate incl. new data file
uv run pytest                                 # full suite incl. provenance + new tests
uv run pytest tests/test_vg_agent.py -k compact   # focused
```

Live smoke (optional, needs key): start `--chat --live-model`, feed enough
turns to cross the threshold, confirm the `[context] auto-compact ... ->
... (NN% smaller) ... full history retained` line appears, then run `/compact`
manually and `--show-context` to confirm the pre-compaction events are still
retrievable from the trace.
