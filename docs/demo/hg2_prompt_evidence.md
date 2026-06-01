# VG-HG-2 — student-prompted build evidence

The rubric requires that the solution was **prompted by the student** (not
hand-written) and that **chat sessions can be shown on request**.

## Generated-source story (say this at demo open)

> Runtime code under `src/vg_agent/` and `fixtures/demo_repo/` is **generated**.
> I edit markdown specs, `PROMPTS.md`, and `MODEL_CONFIG.md`, then run
> `python scripts/generate_project.py --clean`. Provenance is verified by
> `test_generated_source_reproducible` in CI.

## In-repo evidence (always available)

| Evidence | Path |
|----------|------|
| Spec-first contract | [specs/05_source_of_truth_and_generation.md](../../specs/05_source_of_truth_and_generation.md) |
| System prompts fed to generator | [PROMPTS.md](../../PROMPTS.md) |
| Model IDs and pricing | [MODEL_CONFIG.md](../../MODEL_CONFIG.md) |
| Generator + embedded templates | [scripts/generate_project.py](../../scripts/generate_project.py) |
| Digest pinned in generated code | `SPEC_DIGEST` in `src/vg_agent/__init__.py` |
| Reproducibility test | `tests/test_vg_agent.py::test_generated_source_reproducible` |

## Chat sessions to export (prepare before exam)

Export or screenshot **Cursor / Claude / Codex** sessions that show you
*prompting* the build, not typing Python by hand. Suggested bundles:

1. **Initial architecture** — sessions where you defined sub-agents, compaction,
   and budget design (maps to early `specs/` commits).
2. **Generator workflow** — sessions editing specs + running
   `generate_project.py --clean`.
3. **Demo hardening** — sessions for chat UI, `/finops`, `/show-context`, demo
   script (recent).

### How to export from Cursor

- Open each relevant chat in Cursor history.
- Use **Export chat** (or copy transcript to a file under `docs/demo/sessions/`).
- Name files by topic, e.g. `session_01_specs_and_generator.md`.

### Optional local folder

Create `docs/demo/sessions/` and add exported transcripts (gitignore if they
contain API keys or personal data). At minimum, keep **three** sessions ready
to screen-share without scrolling.

## What NOT to claim

- Do not hand-edit `src/vg_agent/*.py` — regenerator overwrites and provenance
  tests fail.
- If the examiner asks for a specific file's origin, trace: spec markdown →
  generator template → generated file → `SPEC_DIGEST` match.

## Quick verification command

```powershell
python scripts/generate_project.py --clean
uv run pytest tests/test_vg_agent.py::test_generated_source_reproducible -q
```

Green = checked-in tree matches a fresh regeneration from your specs.
