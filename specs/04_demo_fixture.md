# 04 Demo fixture

The seeded workspace used for graded demos and most unit tests. Layout and
generator behavior are defined here; VG assertions live in
[`40_demo_and_eval.md`](40_demo_and_eval.md); live scenes in
[`70_demo_runbook.md`](70_demo_runbook.md).

## Source and seeding

- **Generator:** `src/vg_agent/demo_fixture.py` (Tier A — from
  `scripts/templates/demo_fixture.py.tmpl`). Writes
  `fixtures/demo_repo/` at build/regenerate time.
- **Seed command:** `vg-agent --seed-fixture` copies that tree into
  `VG_WORKSPACE_ROOT` (default `./workspace`).
- **Docker:** `docker compose run --rm vg-agent --seed-fixture` with
  `./workspace` mounted ([`50_packaging.md`](50_packaging.md)).

## Layout

```
demo_repo/
  app.py              # Uses auth + utils; entry for sanity edits
  utils.py            # render_response helper
  auth/
    __init__.py
    session.py        # Token issue/validate, load_session
    middleware.py     # require_auth decorator
  data/
    sample.log        # Large reproducible log (see below)
  README.md
```

## File roles (demo narrative)

| Path | Role in demos |
|------|----------------|
| `app.py` | **Scene 1** sanity edit target (`fixtures/demo_repo/app.py` via Coder) |
| `auth/session.py` | Token issuing, validation, session load — Explorer Scene 2 |
| `auth/middleware.py` | Route guard / `require_auth` — Explorer Scene 2 |
| `utils.py` | Second parallel Explorer target in canonical summarise task |
| `data/sample.log` | Parent `read_file` triggers **tool-result compaction** (VG.2) |

## `data/sample.log`

- Produced by `sample_log()` in `demo_fixture.py`: **4600 lines**, deterministic
  content (`request_id=req-NNNNN`, rotating timestamps).
- Total size **> 200 KB** so a parent `read_file data/sample.log` `tool_result`
  exceeds `K_COMPACT` (4000 token estimate).
- Same bytes on every regenerate — provenance tests and compaction demos depend
  on this.

## Auth-heavy theme

The fixture is intentionally small but models a typical app:

- **Session layer** — issues and validates tokens tied to `SESSION_SECRET`.
- **Middleware** — `require_auth` wraps handlers; failures raise `AuthError`.
- **App** — `foo` and `protected_dashboard` exercise session + auth paths.

Parallel summarise demo (`read data/sample.log, then summarise auth/ and utils.py
in parallel`) reads the log on the parent, then fans out two Explorers without
loading sub-agent tool noise into parent context.

## Changing the fixture

1. Edit `scripts/templates/demo_fixture.py.tmpl` (or spec here + `40` if
   assertions change).
2. `python scripts/generate_project.py --clean`
3. `uv run pytest` — compaction and demo tests may depend on line count / size.
4. Re-seed workspace before live demos.

## Related specs

- [`40_demo_and_eval.md`](40_demo_and_eval.md) — VG.1/VG.2 assertions
- [`70_demo_runbook.md`](70_demo_runbook.md) — scene-by-scene script
- [`11_subagent_explorer.md`](11_subagent_explorer.md) — Explorer auth scene detail
- [`README.md`](README.md) — spec index
