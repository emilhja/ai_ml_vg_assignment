# Model Config

Checked against the OpenRouter + LiteLLM live-model contract on 2026-05-28.

Sources:

- https://docs.litellm.ai/docs/providers/openrouter
- https://openrouter.ai/docs

## Default Profile - Haiku-Class OpenRouter

The default profile uses LiteLLM executable OpenRouter model IDs for the
parent and every sub-agent. This keeps demo cost low and is the configuration
tested by the spec assertions in `specs/40_demo_and_eval.md`.

```yaml
PARENT_MODEL_ID: openrouter/anthropic/claude-haiku-4.5
GRILLING_MODEL_ID: openrouter/anthropic/claude-haiku-4.5
EXPLORER_MODEL_ID: openrouter/anthropic/claude-haiku-4.5
CODER_MODEL_ID: openrouter/anthropic/claude-haiku-4.5
REVIEWER_MODEL_ID: openrouter/anthropic/claude-haiku-4.5
COMPACTOR_MODEL_ID: openrouter/anthropic/claude-haiku-4.5
```

Optional examples for manual demos include
`openrouter/openai/gpt-5.2`, `openrouter/google/gemini-3.1-pro-preview`,
and `openrouter/deepseek/deepseek-r1`. They are not test requirements.

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
CLAUDE_SONNET_4_6_INPUT_PER_MTOK: 3.00
CLAUDE_SONNET_4_6_OUTPUT_PER_MTOK: 15.00
CLAUDE_HAIKU_4_5_INPUT_PER_MTOK: 1.00
CLAUDE_HAIKU_4_5_OUTPUT_PER_MTOK: 5.00
UNKNOWN_MODEL_INPUT_ESTIMATE_PER_MTOK: 30.00
UNKNOWN_MODEL_OUTPUT_ESTIMATE_PER_MTOK: 120.00
```

Executable model selection must use the exact `openrouter/...` IDs above or a
compatible LiteLLM OpenRouter model string.

Live mode reads `OPENROUTER_API_KEY` from the environment. Tests use fake
clients and must not import, initialize, or call LiteLLM.
