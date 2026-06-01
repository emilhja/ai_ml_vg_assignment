# Model Config

Checked against the OpenRouter + LiteLLM live-model contract on 2026-05-28.

Sources:

- https://docs.litellm.ai/docs/providers/openrouter
- https://openrouter.ai/docs

## Default Profile - Gemini 2.5 Flash OpenRouter

The default profile uses LiteLLM executable OpenRouter model IDs for the
parent and every sub-agent. This keeps demo cost low and is the configuration
tested by the spec assertions in `specs/40_demo_and_eval.md`.

```yaml
PARENT_MODEL_ID: openrouter/google/gemini-2.5-flash
GRILLING_MODEL_ID: openrouter/google/gemini-2.5-flash
EXPLORER_MODEL_ID: openrouter/google/gemini-2.5-flash
CODER_MODEL_ID: openrouter/google/gemini-2.5-flash
REVIEWER_MODEL_ID: openrouter/google/gemini-2.5-flash
COMPACTOR_MODEL_ID: openrouter/google/gemini-2.5-flash
```

Legacy pricing for `openrouter/google/gemini-2.0-flash-001` remains in the
generated pricing table for historical traces. Override models via
`workspace/config.toml`, `.env`, or CLI flags (see `specs/50_packaging.md`).

Optional examples for manual demos include
`openrouter/google/gemini-2.5-flash-lite`, `openrouter/anthropic/claude-haiku-4.5`,
`openrouter/openai/gpt-5.2`, `openrouter/deepseek/deepseek-r1`, and
`openrouter/qwen/qwen3-coder-30b-a3b-instruct` (low-cost coding; pair with
`OPENROUTER_PROVIDER_ORDER=novita`), and `openrouter/deepseek/deepseek-v4-flash`
(agent/coding; pair with `OPENROUTER_PROVIDER_ONLY_DEEPSEEK` for a cheap-host
whitelist — see `docs/PRICE.md`).
They are not test requirements. Select via `--parent-model` when supported by
the CLI.

## Egress Pin

The LiteLLM OpenRouter client refuses to call any other host. The endpoint is
pinned and validated before every live request.

```yaml
OPENROUTER_ENDPOINT_HOST: openrouter.ai
```

## Pricing Constants

Local fallback pricing is available only for known configured models. If a
manual demo uses an unknown live model, OpenRouter/LiteLLM must return an
explicit response cost; otherwise live mode fails closed before the next step.
Preflight budget checks use a conservative estimate for unknown models.

```yaml
GEMINI_2_0_FLASH_INPUT_PER_MTOK: 0.10
GEMINI_2_0_FLASH_OUTPUT_PER_MTOK: 0.40
GEMINI_2_5_FLASH_INPUT_PER_MTOK: 0.10
GEMINI_2_5_FLASH_OUTPUT_PER_MTOK: 0.40
GEMINI_2_5_FLASH_LITE_INPUT_PER_MTOK: 0.10
GEMINI_2_5_FLASH_LITE_OUTPUT_PER_MTOK: 0.40
CLAUDE_SONNET_4_6_INPUT_PER_MTOK: 3.00
CLAUDE_SONNET_4_6_OUTPUT_PER_MTOK: 15.00
CLAUDE_HAIKU_4_5_INPUT_PER_MTOK: 1.00
CLAUDE_HAIKU_4_5_OUTPUT_PER_MTOK: 5.00
QWEN3_CODER_30B_INPUT_PER_MTOK: 0.07
QWEN3_CODER_30B_OUTPUT_PER_MTOK: 0.27
DEEPSEEK_V4_FLASH_INPUT_PER_MTOK: 0.0983
DEEPSEEK_V4_FLASH_OUTPUT_PER_MTOK: 0.1966
UNKNOWN_MODEL_INPUT_ESTIMATE_PER_MTOK: 30.00
UNKNOWN_MODEL_OUTPUT_ESTIMATE_PER_MTOK: 120.00
```

## OpenRouter provider warnings

Default expensive-provider slugs for `warn_expensive_provider` budget events
(override at runtime with `OPENROUTER_EXPENSIVE_PROVIDERS`).

```yaml
EXPENSIVE_OPENROUTER_PROVIDER_SLUGS: alibaba,morph,parasail/fp8
```

Executable model selection must use the exact `openrouter/...` IDs above or a
compatible LiteLLM OpenRouter model string.

Live mode reads `OPENROUTER_API_KEY` from the environment. Tests use fake
clients and must not import, initialize, or call LiteLLM.
