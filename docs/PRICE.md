# OpenRouter pricing notes (VG assignment)

Informal reference from model-page research (2026-06). List prices change on
[OpenRouter](https://openrouter.ai); confirm on each model’s **Providers** tab
before committing spend.

Executable pricing for the agent runtime lives in [`MODEL_CONFIG.md`](../MODEL_CONFIG.md)
(generated into `src/vg_agent/config.py`). This file is for humans choosing models
and provider pins.

---

## Recommended stack (DeepSeek test — current `.env.example`)

| Role | Model | Provider pin |
|------|--------|----------------|
| Parent, Coder | `deepseek/deepseek-v4-flash` | `OPENROUTER_PROVIDER_ONLY_DEEPSEEK=baidu/fp8,deepinfra/fp4` |
| Grilling, Explorer, Reviewer, Compactor | `google/gemini-2.5-flash-lite` | *(none — global `only`/`order` not applied to Gemini)* |

```ini
OPENROUTER_PROVIDER_ONLY_DEEPSEEK=baidu/fp8,deepinfra/fp4
OPENROUTER_EXPENSIVE_PROVIDERS=alibaba,morph,parasail/fp8
VG_PARENT_MODEL=deepseek/deepseek-v4-flash
VG_CODER_MODEL=deepseek/deepseek-v4-flash
```

Copy slugs from the model [Providers tab](https://openrouter.ai/deepseek/deepseek-v4-flash/providers).
Traces record `openrouter_provider`; denylisted slugs emit `warn_expensive_provider` once per slug per run.

**Live check** (after `.env` matches the table above):

```powershell
docker compose run --rm vg-agent --task "read data/sample.log, then summarise auth/ and utils.py in parallel" --trace
# Parent/coder assistant_step lines should show provider=baidu/fp8 or deepinfra/fp4
Select-String -Path traces\*.jsonl -Pattern '"openrouter_provider"'
Select-String -Path traces\*.jsonl -Pattern 'warn_expensive_provider'
```

If you temporarily clear `OPENROUTER_PROVIDER_ONLY_DEEPSEEK` and routing hits `alibaba`,
expect one `budget_event` with `budget_reason: warn_expensive_provider` per denylisted slug.

---

## Qwen3 Coder 30B A3B Instruct — provider matrix

Model: [qwen/qwen3-coder-30b-a3b-instruct](https://openrouter.ai/qwen/qwen3-coder-30b-a3b-instruct)

The **headline** rate ($0.07 / $0.27 per Mtok) matches the **cheapest** backend
(Novita), not every provider.

| Provider | Input / Mtok | Output / Mtok | Total context | Max output (one completion) |
|----------|----------------|----------------|---------------|---------------------------|
| **NovitaAI** | **$0.07** | **$0.27** | 160K | 32.8K |
| Amazon Bedrock | $0.15 | $0.60 | — | — |
| **Alibaba Cloud Int.** | **$0.29–$0.78** (tiered by prompt size) | **$1.46–$3.90** (tiered) | 262K | 65.5K |

Alibaba tiers (discounted rates shown on OR; increase with context length):

- ≤32K prompt: ~$0.29 in / ~$1.46 out per Mtok  
- ≤128K: ~$0.49 / ~$2.44  
- \>128K: ~$0.78 / ~$3.90  

### Takeaways

- **Do not** assume “Alibaba = cheapest” for this model on OpenRouter. For typical
  agent steps, **Novita is ~4–5× cheaper on output** than Alibaba’s lowest tier.
- **`OPENROUTER_PROVIDER_ORDER=alibaba`** can **increase** cost vs Novita or vs
  OpenRouter’s default price-weighted routing.
- **Alibaba** buys larger **context** (262K) and **max output** (65.5K) per request,
  not the headline $0.07 / $0.27 rate.
- **Novita** is enough for VG: parent/coder `max_tokens` is ~4096; normal tool JSON
  and summaries stay well under 32.8K max output.

### Field glossary (Providers tab)

| Field | Meaning |
|--------|--------|
| **Total context** | Max size of prompt + history + completion together. |
| **Max output** | Max **new** tokens the backend will generate in **one** API response. |
| **`max_tokens` in API** | What you request; capped by the active provider’s max output. |

---

## Other models compared (headline OR prices)

Per-million-token list prices on model cards (not per-provider breakdown):

| Model | Input | Output | Context | Fit for VG |
|-------|--------|--------|---------|------------|
| [Qwen3 Coder 30B A3B Instruct](https://openrouter.ai/qwen/qwen3-coder-30b-a3b-instruct) | $0.07 | $0.27 | 160K | **Best Qwen $ for code agents** (pin Novita) |
| [Qwen3 Coder Next](https://openrouter.ai/qwen/qwen3-coder-next) | $0.11 | $0.80 | 256K | Coder successor; pricier output |
| [Qwen3.6 35B A3B](https://openrouter.ai/qwen/qwen3.6-35b-a3b) | $0.14 | $1.00 | 262K | General multimodal; **not** a cheap coder drop-in |
| [DeepSeek V4 Flash](https://openrouter.ai/deepseek/deepseek-v4-flash) | $0.098 | $0.20 | 1M | Strong non-Qwen alt; cheap **output** |
| [Gemini 2.5 Flash Lite](https://openrouter.ai/google/gemini-2.5-flash-lite) | $0.10 | $0.40 | (see OR) | Good for fast/cheap explorers |

**Output-heavy** agent work (long summaries, big tool payloads): DeepSeek V4 Flash
and Qwen3 Coder 30B (Novita) tend to beat Qwen3 Coder Next and Qwen3.6 35B on $/Mtok.

---

## Provider routing in this repo

OpenRouter accepts a `provider` object on chat completions
([docs](https://openrouter.ai/docs/guides/routing/provider-selection)).
The live client forwards it via LiteLLM `extra_body` when set in `.env`:

| Variable | Purpose |
|----------|---------|
| `OPENROUTER_PROVIDER_ORDER` | Comma-separated slugs, try first (e.g. `novita`) |
| `OPENROUTER_PROVIDER_ONLY` | Whitelist for **all** models (avoid with mixed Gemini + DeepSeek) |
| `OPENROUTER_PROVIDER_ONLY_DEEPSEEK` | `only` whitelist when `model_id` contains `/deepseek/` |
| `OPENROUTER_EXPENSIVE_PROVIDERS` | Denylist → `warn_expensive_provider` once per slug per run |
| `OPENROUTER_PROVIDER_SORT` | `price`, `throughput`, or `latency` |
| `OPENROUTER_PROVIDER_ALLOW_FALLBACKS` | `true` / `false` (default true if unset) |

## DeepSeek V4 Flash — provider spread

Model: [deepseek/deepseek-v4-flash](https://openrouter.ai/deepseek/deepseek-v4-flash)

Headline ~$0.098 / $0.20 per Mtok is the **floor**; **Alibaba**, **morph**, and
**parasail/fp8** on the Providers tab are often **much** more expensive (same pattern
as Qwen Coder). Use `OPENROUTER_PROVIDER_ONLY_DEEPSEEK` to whitelist cheap hosts;
keep `OPENROUTER_EXPENSIVE_PROVIDERS` so traces warn if routing slips.

**Future:** per-role `VG_*_PROVIDER_ONLY` — see [`TODO.md`](TODO.md) (this file).

---

## Adding a priced model (checklist)

When you change any `VG_*_MODEL` or `[models]` in `workspace/config.toml`:

1. Add `*_INPUT_PER_MTOK` / `*_OUTPUT_PER_MTOK` and the `openrouter/...` id in
   [`MODEL_CONFIG.md`](../MODEL_CONFIG.md).
2. Add `*_CONTEXT_WINDOW` / `*_COMPACT_FRACTION` in [`CONTEXT_WINDOWS.md`](../CONTEXT_WINDOWS.md).
3. Wire entries in [`scripts/generate_project.py`](scripts/generate_project.py)
   (`PRICING_USD_PER_MTOK`, `CONTEXT_WINDOW_TOKENS`, `AUTO_COMPACT_FRACTION`).
4. Run `python scripts/generate_project.py --clean` and `uv run pytest`.
5. Restart the agent; optional `VG_STRICT_MODEL_PRICING=1` to fail fast if any
   role model is still unpriced.
6. Confirm one live turn on [OpenRouter Activity](https://openrouter.ai/activity).

---

## Statusline / budget estimates vs real bills

If a model is **not** in `MODEL_CONFIG.md` → `PRICING_USD_PER_MTOK`, startup prints a
**warning** (or exits when `VG_STRICT_MODEL_PRICING=1`). Preflight `usd_cap` still uses
conservative unknown-model rates ($30 / $120 per Mtok), but the chat statusline shows
`(unpriced model)` instead of a misleading `(next ~$…)`.

- **Spent (`$0.00`)** after calls: uses OpenRouter/LiteLLM **returned cost** (accurate).
- **Next ~$…`** (priced models only): worst-case `max(ctx, 512)` in + `4096` out × estimate table.

`openrouter/qwen/qwen3-coder-30b-a3b-instruct` is in the pricing table (Novita headline
`0.07` / `0.27` per Mtok); preflight for that model is ~$0.001 per small step, not ~$0.51.

---

## Verify spend

1. Run a short task or chat turn.  
2. Open [OpenRouter Activity](https://openrouter.ai/activity).  
3. Check **model**, **provider** (e.g. Novita vs Alibaba), and **charged cost**.

The agent also records the routed backend on each live `assistant_step` as
`openrouter_provider` in JSONL (and in SQLite `model_calls.provider` when the
dashboard mirror is enabled). Live stderr progress lines include
`provider=<slug>` when present.

---

## Related repo files

- [`MODEL_CONFIG.md`](../MODEL_CONFIG.md) — generated pricing constants  
- [`.env.example`](../.env.example) — provider routing env template  
- [`specs/50_packaging.md`](../specs/50_packaging.md) — packaging contract for `OPENROUTER_PROVIDER_*`  
- [`TODO.md`](TODO.md) — per-role provider routing follow-up (same directory)  
