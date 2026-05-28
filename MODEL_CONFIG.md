# Model Config

Checked against official Anthropic documentation on 2026-05-28.

Sources:

- https://platform.claude.com/docs/en/about-claude/models/overview
- https://platform.claude.com/docs/en/about-claude/pricing

## Default profile — Haiku-only

The default profile ships with Haiku 4.5 for parent and every sub-agent.
This keeps demo cost low and is the configuration tested by the spec
assertions in `specs/40_demo_and_eval.md`.

```yaml
PARENT_MODEL_ID: claude-haiku-4-5-20251001
GRILLING_MODEL_ID: claude-haiku-4-5-20251001
EXPLORER_MODEL_ID: claude-haiku-4-5-20251001
CODER_MODEL_ID: claude-haiku-4-5-20251001
REVIEWER_MODEL_ID: claude-haiku-4-5-20251001
COMPACTOR_MODEL_ID: claude-haiku-4-5-20251001
```

## Beta profile — Sonnet parent + Haiku sub-agents

Documented for future use. Flipping to this profile is a **config-only**
change: set the override in `config.toml` or the corresponding env var, no
code change required.

```yaml
PARENT_MODEL_ID: claude-sonnet-4-6
GRILLING_MODEL_ID: claude-haiku-4-5-20251001
EXPLORER_MODEL_ID: claude-haiku-4-5-20251001
CODER_MODEL_ID: claude-haiku-4-5-20251001
REVIEWER_MODEL_ID: claude-haiku-4-5-20251001
COMPACTOR_MODEL_ID: claude-haiku-4-5-20251001
```

Use the beta profile only after the default profile passes every assertion
and the cost cap headroom has been measured for a representative demo run.

## Egress pin

The Anthropic Messages client refuses to open a socket to any other host. The
endpoint is pinned and validated on every request.

```yaml
ANTHROPIC_ENDPOINT_HOST: api.anthropic.com
```

## Pricing constants

All values are USD per million tokens for first-party Claude API global routing.

```yaml
CLAUDE_SONNET_4_6_INPUT_PER_MTOK: 3.00
CLAUDE_SONNET_4_6_OUTPUT_PER_MTOK: 15.00
CLAUDE_HAIKU_4_5_INPUT_PER_MTOK: 1.00
CLAUDE_HAIKU_4_5_OUTPUT_PER_MTOK: 5.00
```

Marketing names may appear in prose. Executable model selection must use the
exact IDs above.

Live mode uses these IDs through the Anthropic Messages API and reads
`ANTHROPIC_API_KEY` from the environment. Tests use fake clients and must not
make network calls.
