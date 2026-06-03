# TODO

## OpenRouter provider routing (future)

Today `OPENROUTER_PROVIDER_*` applies the same `provider` block to **every** live
completion (parent, explorers, compactor, etc.). That is fine when all roles use
Qwen, but mixed setups (e.g. Qwen parent + Gemini explorers) send Qwen-specific
prefs on non-Qwen models — usually ignored by OpenRouter, but confusing.

**Cleaner follow-up (pick one):**

- Per-role env vars mirroring `VG_*_MODEL`, e.g. `VG_PARENT_PROVIDER_ORDER=alibaba`,
  `VG_CODER_PROVIDER_ORDER=alibaba`, unset for Gemini roles; pass provider prefs
  into `LiveModelClient.complete()` per call.
- Or model-aware gating: only attach `provider.order: ["alibaba"]` when the
  LiteLLM model id contains `/qwen/` (aligns provider prefs with model choice
  without six new env keys).

Spec-first: update `specs/50_packaging.md`, generator template in
`scripts/generate_project.py`, regenerate, tests in `tests/test_openrouter_provider.py`.

Related: global routing landed via `OPENROUTER_PROVIDER_ORDER` / `OPENROUTER_PROVIDER_SORT`
(see `MODEL_CONFIG.md` Qwen + Alibaba note).

## Rich TTY chat — low-priority polish

Spec-first (`specs/16_chat_ui.md`), then `chat_ui.py` / `scripts/templates/__main__.py.tmpl`,
regenerate, pytest.

- [ ] Progress turn header `── turn N ──` → Rich `Rule` on stderr (compact chat only).
- [ ] `[parallel]` rollup → optional dim Rich `Panel` instead of plain magenta lines.
- [ ] Live progress diffs: wire `render_progress_file_diff()` (Syntax panels) instead of
  inline `write_progress_diff_lines()` ANSI hunks — matches approval/end-of-turn panels;
  may add stderr noise during fast Coder loops.
