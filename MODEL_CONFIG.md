# Model Config

Checked against official Anthropic documentation on 2026-05-10.

Sources:

- https://platform.claude.com/docs/en/about-claude/models/overview
- https://platform.claude.com/docs/en/about-claude/pricing

## Runtime model IDs

```yaml
PARENT_MODEL_ID: claude-sonnet-4-6
EXPLORER_MODEL_ID: claude-haiku-4-5-20251001
COMPACTOR_MODEL_ID: claude-haiku-4-5-20251001
```

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
