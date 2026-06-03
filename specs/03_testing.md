# 03 Testing

How the repository verifies behavior without live OpenRouter calls in CI.
Complements [`specs/05_source_of_truth_and_generation.md`](05_source_of_truth_and_generation.md).

## Rules

- **No network in unit tests.** Live model paths must use an injected
  `FakeClient` or `PipelineClient` from [`tests/test_vg_agent.py`](../tests/test_vg_agent.py).
- **Dashboard API tests** ([`tests/test_dashboard_api.py`](../tests/test_dashboard_api.py),
  [`tests/test_openrouter_provider.py`](../tests/test_openrouter_provider.py)) also
  avoid outbound API calls.
- Changing runtime behavior that specs describe should add or extend tests in
  the same PR (or document why not).

## Spec-first change loop

| Tier | What you edit | Regenerate? |
|------|---------------|---------------|
| A — Generated | `scripts/templates/*.tmpl`, digest-input specs, `PROMPTS.md`, `MODEL_CONFIG.md`, `CONTEXT_WINDOWS.md` | Yes: `python scripts/generate_project.py --clean` |
| B — Hand-written in `src/vg_agent/` | `chat_ui.py`, `sqlite_store.py`, `workspace_paths.py` | Regenerate still re-copies them (placeholders only) |
| C — Ordinary | `tests/`, `dashboard/`, `specs/`, `docs/` | No |

See [`DEVELOPER_README.md`](../DEVELOPER_README.md) for the full tier map.

## Provenance tests

Generated runtime must match a fresh regeneration byte-for-byte:

- `test_generated_source_reproducible` — regenerates into a temp dir and compares to checked-in `src/vg_agent/`.
- `test_documented_generation_command` — runs `python scripts/generate_project.py --clean` from repo root.

Hand-editing Tier A files without regenerating fails CI.

## FakeClient pattern

`FakeClient` returns a predetermined list of `ModelTurn` objects (tool calls and
assistant text). The same live parent loop runs; only the model backend is swapped.

Use for:

- Budget caps and `budget_event` reasons
- Parallel Explorer overlap (barrier-synchronized fakes)
- Compaction and `show_context` invariants
- `run_bash` deny-list and sensitive-path blocks
- Chat slash commands and Rich UI (monkeypatch `chat_ui.use_rich_ui`)

`PipelineClient` wraps scripted multi-step flows when turns depend on prior tool results.

## When to run tests

```powershell
# Full suite (after spec/template/regenerate changes)
uv run pytest

# Focused (examples)
uv run pytest tests/test_vg_agent.py -k "compaction or show_context"
uv run pytest tests/test_vg_agent.py -k "progress_sink or chat_ui"
uv run pytest tests/test_dashboard_api.py
```

Optional extras:

```powershell
uv sync --extra dev          # httpx for some tests
uv sync --extra dashboard    # dashboard package imports
```

## What tests do not cover

- Frontier model quality (see [`model_experience.md`](model_experience.md),
  [`41_runtime_quality_eval.md`](41_runtime_quality_eval.md) for manual protocols).
- Hosted multi-user dashboard security (local-only v1).
- Docker-in-CI full demo runs (packaging is documented in [`50_packaging.md`](50_packaging.md); most gates are in-process).

## Related specs

- [`05_source_of_truth_and_generation.md`](05_source_of_truth_and_generation.md)
- [`40_demo_and_eval.md`](40_demo_and_eval.md) — assertion-level demo checks
- [`README.md`](README.md) — full spec index
