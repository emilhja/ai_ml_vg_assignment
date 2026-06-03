# 05 Source Of Truth And Generation

The assignment's "programming language" is markdown. Codex must treat this
document set as the implementation contract and must not infer runtime
behavior from stale generated Python.

## Editable sources

These files are human-/agent-edited sources of truth:

- `specs/*.md` — architecture, tool contracts, governance, tests, packaging,
  observability, and demo behavior.
- `PROMPTS.md` — parent and sub-agent prompts compiled into runtime code.
- `MODEL_CONFIG.md` — exact model IDs, endpoint host, and pricing constants.
- `CONTEXT_WINDOWS.md` — per-model context window and auto-compact fraction.
- `scripts/generate_project.py` — generated-code templates.
- Top-level packaging/docs that are not generated: `Dockerfile`,
  `docker-compose.yml`, `.env.example`, `config.example.toml`, `README.md`,
  and human-authored files under `docs/` (for example `docs/ARCHITECTURE.md`,
  `docs/PRICE.md`, `docs/dev/*.md`, `docs/demo/*.md`).

## Generated artifacts

These paths are generated artifacts and must not be hand-edited:

- `src/vg_agent/` — **except** the three hand-written source files below
- `fixtures/demo_repo/`
- generated fixture traces or seeded demo files under `workspace/`

To change generated behavior, edit the source markdown or generator template,
then regenerate:

```powershell
python scripts/generate_project.py --clean
```

### Hand-written files inside `src/vg_agent/`

`sqlite_store.py`, `chat_ui.py`, and `workspace_paths.py` are **not** produced
from template strings. They are listed in `EXTRA_SOURCE_GENERATED_FILES` in
`scripts/generate_project.py`; the generator reads them from `src/vg_agent/`
(before `--clean` removes the directory), applies placeholder substitution, and
writes them back. They are their own source of truth and **are** edited
directly. (Because substitution still runs, avoid literal `__NAME__` tokens.)
A reviewer-facing map of all three tiers lives in `DEVELOPER_README.md`.

The generator computes a `SPEC_DIGEST` over the markdown prompt/config/spec
inputs and embeds it into generated runtime files. Provenance tests regenerate
the runtime tree in a temporary directory and compare it byte-for-byte with
the checked-in generated tree.

## Drift checks

Tests must fail if:

- Runtime prompts drift from `PROMPTS.md`.
- Runtime constants drift from `MODEL_CONFIG.md` or
  `specs/30_runtime_governance.md`.
- Generated files differ after a clean regeneration.
- README/runbook commands name flags or services not defined in
  `specs/15_cli_contract.md` or `specs/50_packaging.md`.

Codex implementation work must start from this source-of-truth list. If an
implementation detail is missing from these files, add it to the spec first,
then regenerate or patch the non-generated packaging file.
