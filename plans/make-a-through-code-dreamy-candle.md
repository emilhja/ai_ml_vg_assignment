# Code Review + README/Docs Alignment

## Context

The repo is **spec-first**: `specs/*.md`, `PROMPTS.md`, `MODEL_CONFIG.md`, and
`scripts/generate_project.py` are the source of truth; everything under
`src/vg_agent/` and `fixtures/demo_repo/` is generated. A recent wave of work
(staged but uncommitted) updated the specs and regenerated the runtime:
`SPEC_DIGEST` changed, `CODER_MODEL_ID` moved Gemini→Haiku, and `run_bash`
gained three narrow allowances (`rm <single file>`, `mkdir [-p]`,
`python3 -m py_compile <file>`) plus Coder empty-turn-retry and Reviewer
verdict-guarantee hardening.

The **specs were updated in lockstep with the generated code, but the
user-facing docs were not.** This pass closes that gap: it corrects the stale
parts of `README.md` and `docs/ARCHITECTURE.md` so the documentation matches
the shipped behavior. No code or spec generation changes (per scope decision).

## Code-review findings (summary)

Verified during exploration; no action required beyond the doc fixes below
unless noted:

- **Specs ↔ generated code: aligned.** `specs/12/16/20/50` match the
  regenerated runtime; `MODEL_CONFIG.md` carries the Haiku Coder + pricing.
- **Dead code (report only):** `MAX_CONCURRENT_SUBAGENTS = 2` is defined in
  `scripts/generate_project.py:198` and emitted into `src/vg_agent/config.py:59`
  but never read; only `MAX_PARALLEL_SUBAGENTS = 4` is used. Left as-is this
  pass (would require generator edit + regenerate).
- **Untracked `specs/model_experience.md`** is descriptive model-selection
  guidance, outside the generation contract. Fine to leave; optionally linked
  from README's Documentation table.
- Runtime architecture is coherent: parent has no write tools, Coder is the
  sole mutation path, parallel Explorers overlap, second Coder in a batch
  returns `status:"conflict"`, budget/approval/redaction/egress-pin all wired.

## Changes

### 1. `README.md` — "Command safety" section (lines ~112–127) — STALE, must fix

Current text says `run_bash` rejects `rm` and `mkdir` as destructive tokens.
That contradicts `specs/20_tools.md:67-76` and `src/vg_agent/tools.py:16`.

- Rewrite the destructive-token sentence so the *blocked* list no longer
  implies `rm`/`mkdir` are categorically rejected. Keep the truly-blocked
  tokens (`del`, `rmdir`, `Remove-Item`, `mv`, `cp`, `chmod`, `mkfs`, `dd`,
  `git`, `ssh`, `scp`, package installers, foreign runtimes, `sed`).
- Add a short "narrow allowances" note mirroring `specs/20_tools.md`:
  - `rm <file>` — exactly one existing regular file, no flags/dirs/globs.
  - `mkdir [-p] <dir> …` — workspace-relative only, `-p` the only flag.
  - `python3 -m py_compile <relative .py>` — syntax check only, single target.
- Reuse the wording already in `specs/20_tools.md:63-76` so the README stays a
  faithful summary of the spec.

### 2. `README.md` — Dashboard section (lines ~172–244) — tidy

- Replace the hardcoded `cd C:\Users\emil_\vscode\vg_assignment` (line 199)
  with a generic placeholder (`cd <repo-root>`); same for the absolute paths in
  the "Alternative" block (lines 241–242).
- Lead with the recommended one-command launcher `./start-web.sh` (already at
  line 191) and briefly note its options (`--no-install`, `--api-port`) and
  that it requires `uv` + `npm` on PATH and serves http://127.0.0.1:5173.
  Keep the manual two-terminal setup as the labeled fallback (no reordering of
  the whole section required — just promote/annotate).

### 3. `README.md` — Documentation table (lines ~251–260) — small additions

- Add a row for `specs/` (source-of-truth spec set) and optionally
  `specs/model_experience.md` (model-selection guidance) and
  `CONTEXT_WINDOWS.md` (used by the generator) so readers can find them.

### 4. `docs/ARCHITECTURE.md` — remove bogus `--no-grill` flag (lines 71–73)

The "Weakest part" paragraph claims `--no-grill` is "the user-facing escape
hatch." No such flag exists in `__main__.py`, the specs, or tests. Grilling is
model-decided. Replace that clause with an accurate statement: the parent model
itself decides whether to invoke Grilling (no flag gate), so an over-eager
Grilling trigger costs at most one clarifying round-trip the parent can
override. Keep the rest of the paragraph (even budget-split weakness) intact.

## Out of scope (this pass)

- No edits under `src/vg_agent/**` or `fixtures/demo_repo/**` (generated).
- No spec/`PROMPTS.md`/`MODEL_CONFIG.md` changes — they already match the code.
- Not removing `MAX_CONCURRENT_SUBAGENTS` and not implementing `--no-grill`
  (per scope decisions); both noted in the review summary instead.

## Verification

1. `git diff -- README.md docs/ARCHITECTURE.md` — confirm only the four edit
   areas changed; no hardcoded user path remains
   (`grep -n "emil_" README.md` returns nothing).
2. Cross-check the rewritten Command-safety wording against
   `specs/20_tools.md:56-99` — every allowed/blocked item should agree.
3. `grep -rn "no-grill\|no_grill" docs/ README.md` returns nothing.
4. Docs-only change, so no regeneration needed; optionally run
   `uv run pytest` to confirm nothing else drifted (expected: green, since
   generated tree is untouched).
