# 41 Runtime Quality Eval

Purpose: define a repeatable evaluation protocol for coding-task runs so claims
are based on trace evidence and artifact behavior, not only completion/cost.

This spec complements, and does not replace, model guidance in
`specs/model_experience.md`.

## Scope

Use this protocol for side-by-side model or profile comparisons on mutation
tasks. The protocol explicitly separates:

- orchestration quality (did the run finish correctly),
- reviewer quality (did verification catch real issues),
- artifact quality (does produced code actually work).

## Evaluation axes

For each run, record all axes below:

1. Orchestration quality
   - `run_end` presence and `final_status`
   - retry count (`subagent_empty_turn_retry`, tool retries)
   - handoff integrity (coder -> reviewer -> parent final answer)
2. Cost/tokens
   - total tokens and USD from `run_end` when present
   - if `run_end` absent, summed `assistant_step` tokens/cost with caveat
3. Latency
   - `run_end.duration_s` (preferred)
   - trace-window duration and dominant wait segments (`tool_result.latency_ms`)
4. Reviewer outcome
   - reviewer `subagent_return.status`
   - reviewer verdict text (`PASS:`/`FAIL:` contract)
5. Functional smoke-check outcome
   - task-specific runtime check result (`pass`/`fail`)
   - failure reason and evidence path

## Evidence contract

Any comparison note MUST include:

- trace IDs and file paths (for example: `traces/<run_id>.jsonl`),
- workspace artifact paths under test (for example: `workspace/calc_x/*.py`),
- the exact smoke-check command (or manual step) executed,
- whether values came from `run_end` or derived from per-step sums.

Without this evidence set, the result is a draft observation, not a protocol
grade.

## Tkinter calculator profile

This is the first concrete quality profile for local GUI calculator tasks.

### Required static checks

1. Syntax check:
   - `python3 -m py_compile <calculator_file.py>`
2. Required structure check by file read:
   - must define a main window and start `mainloop()`
   - must include digit buttons `0-9`
   - must include operations `+ - * /` (or display equivalents)
   - must include decimal point, equals, and clear behavior
   - must include explicit division-by-zero handling that surfaces `Error`

### Required runtime smoke check

Because Tkinter is GUI-driven, syntax-only checks are insufficient.

Use one of:

1. Local desktop smoke check (preferred)
   - run app manually
   - click representative flows: `1+2=`, decimal calculation, divide by zero,
     clear/reset
   - record observed result
2. Headless-safe fallback (when GUI interaction is unavailable)
   - import module and instantiate calculator/root without full interaction
   - classify as `partial` and mark residual runtime risk

If only fallback checks are run, the comparison must say runtime confidence is
limited.

## Severity and failure classes

- `P0` Incomplete run: missing terminal state/handoff ambiguity.
- `P1` Reviewer false positive: reviewer `PASS` but smoke-check fails.
- `P2` Runtime-risk implementation: likely GUI/runtime break despite syntax pass.
- `P3` Cost/latency regression with otherwise correct artifact.

## Reporting template

Use this template for each compared run:

- `Run ID`:
- `Model profile`:
- `Completion`: (`run_end`, `final_status`, retries, handoff notes)
- `Cost/Tokens`: (source: `run_end` or derived)
- `Latency`: (`duration_s` + dominant waits)
- `Reviewer`: (status + verdict text)
- `Smoke check`: (command/manual steps + pass/fail)
- `Final class`: (`pass`, `pass_with_risk`, `fail`)
- `Evidence`: (trace path + artifact path)

Comparison-level conclusion rules:

- Do not declare a model winner from a single run pair.
- Prefer wording: "in this task/profile sample".
- If smoke checks were partial-only, conclusions must include a confidence caveat.
