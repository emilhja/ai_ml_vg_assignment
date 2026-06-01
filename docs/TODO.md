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
