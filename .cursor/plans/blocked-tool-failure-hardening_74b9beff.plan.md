---
name: blocked-tool-failure-hardening
overview: Reduce wasted steps from blocked shell calls by tightening Reviewer/Coder guidance and adding a narrowly scoped `python3 -m py_compile` exception in `run_bash` validation, with tests to prove safety and expected behavior.
todos:
  - id: update-prompts-for-blocked-shell-retries
    content: Harden Reviewer/Coder guidance in PROMPTS.md to reduce blocked run_bash retries and clarify the safe compile path.
    status: completed
  - id: specify-pycompile-exception
    content: Update specs/20_tools.md to document exact allowed form and constraints for python3 -m py_compile.
    status: completed
  - id: implement-validator-exception
    content: Implement strict py_compile exception in src/vg_agent/tools.py without relaxing other python restrictions.
    status: completed
  - id: add-safety-and-behavior-tests
    content: Add tests in tests/test_vg_agent.py for allowed py_compile and blocked variants, including reviewer-related behavior expectations.
    status: completed
  - id: regenerate-and-run-suite
    content: Run python scripts/generate_project.py --clean, targeted pytest, then full uv run pytest.
    status: completed
isProject: false
---

# Harden Blocked Tool Failures

## Goal
Improve behavior/clarity when sub-agents attempt blocked shell commands (like `python3`) while preserving safety and reducing wasted retries.

## Scope I will implement
- Prompt hardening (as requested) for Reviewer/Coder to steer away from blocked shell patterns.
- Add a tightly constrained runtime exception for `python3 -m py_compile <relative.py>` in `run_bash` validation.
- Keep all other Python/shell control commands blocked.

## Why this scope
- Current policy in [specs/20_tools.md](specs/20_tools.md) blocks foreign runners (`python`) and shell control markers; this is safe but can cause repeated failed Reviewer steps when the model tries compile checks.
- Runtime validator in [src/vg_agent/tools.py](src/vg_agent/tools.py) currently rejects any command whose head is not in the allowlist, producing `run_bash blocked` errors.
- Reviewer prompt in [PROMPTS.md](PROMPTS.md) already discourages Python/pytest, but observed traces still show attempts; adding stronger guidance + one safe compile path reduces churn.

## Planned changes
- **Prompt updates** in [PROMPTS.md](PROMPTS.md):
  - Reviewer section: explicitly prefer `read_file`/`read_file_range`; only use `run_bash` for listed read commands; if compile confidence is needed, use `python3 -m py_compile <single relative .py>` only.
  - Coder section: clarify compile checks should use `run_tests` for tests and avoid arbitrary Python shell usage.
- **Tool safety update** in [specs/20_tools.md](specs/20_tools.md):
  - Document one exception: `python3 -m py_compile <relative.py>` allowed under strict constraints (no chains, no absolute paths, no traversal, exactly one target file).
- **Runtime validation** in [src/vg_agent/tools.py](src/vg_agent/tools.py):
  - Add parser/validator branch for the exact token pattern:
    - `python3 -m py_compile <path>` (and optionally `python -m py_compile <path>` if already normalized in rules).
  - Reuse existing path safety checks (`resolve_workspace_path`, sensitive path denylist, no shell control markers).
  - Keep all other Python invocation forms blocked.
- **Regression and safety tests** in [tests/test_vg_agent.py](tests/test_vg_agent.py):
  - Positive: exact `python3 -m py_compile relative.py` passes validation.
  - Negative: `python3 file.py`, `python3 -c`, `python3 -m pytest`, chained/pipe forms, multiple file args, absolute/outside/sensitive paths remain blocked.
  - Reviewer-flow test proving fewer dead-end blocked attempts (or at minimum that allowed py_compile path works while forbidden forms still fail).

## Verification
- Run regeneration: `python scripts/generate_project.py --clean`.
- Run targeted tests in `tests/test_vg_agent.py` for validator + reviewer behavior.
- Run full test suite: `uv run pytest`.
- Confirm no broad allowlist expansion beyond the documented `py_compile` exception.