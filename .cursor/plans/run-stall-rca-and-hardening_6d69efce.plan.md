---
name: run-stall-rca-and-hardening
overview: Analyze the calculator run stall, identify concrete runtime and prompt-level causes, and implement targeted guardrails so similar runs complete reliably under budget.
todos:
  - id: separate-step-accounting
    content: Refactor BudgetGuard and parent loop to enforce MAX_PARENT_STEPS on parent model calls only, with tests.
    status: completed
  - id: coder-tool-error-retry
    content: Add one-shot constrained coder respawn path when spawn_subagent returns actionable coder tool_error.
    status: completed
  - id: reason-coded-subagent-errors
    content: Emit structured subagent failure reason codes and consume them in parent recovery logic.
    status: completed
  - id: reviewer-import-check
    content: Strengthen reviewer rules for package-relative import correctness in generated Python modules.
    status: completed
  - id: regression-tests
    content: Add tests reproducing this run’s failure chain and validating successful recovery behavior.
    status: completed
isProject: false
---

# Harden Run Completion After Subagent Errors

## Findings From This Run
- The run did not silently crash; it terminated on a `spawn_subagent` tool error after `coder-4` returned `status=tool_error` with payload `"coder stopped before producing a final summary."`.
- `coder-4` first made two invalid actions (`read_file` on a directory and `run_bash` pipeline blocked by shell safety), then failed to recover before returning a valid final summary.
- Parent budget pressure was high near the end (`13/15` shown before final fixer spawn), so recovery margin was thin.

## Why It Stopped
- In `_run_live_subagent`, if tool errors occur and no valid terminal assistant summary is produced, the fallback summary path emits the generic failure (`"stopped before producing a final summary"`) and returns `tool_error`.
- Parent loop treats `spawn_subagent` tool errors as hard failures (non-soft-recoverable), so run ends immediately instead of trying one more automatic recovery strategy.
- Budget/step accounting currently increments a single `step_count` on every model call (parent + sub-agents), which makes the parent appear to burn steps faster during heavy delegation.

## Proposed Code Changes
- Split step accounting into parent-only vs global counters in budget/runtime flow:
  - keep `MAX_PARENT_STEPS` enforcement against parent calls only;
  - keep separate guardrails for sub-agent local steps (`MAX_SUBAGENT_STEPS`) and optional global total-call cap if desired.
- Add a targeted parent recovery path for fixer coders:
  - when a coder sub-agent exits `tool_error` due blocked command/read-directory/no-summary, auto-respawn once with a stricter constrained instruction (exact file path + exact allowed tool call form, no `run_bash` unless compile-check requested).
- Improve coder failure diagnostics:
  - return structured reason codes (e.g., `invalid_path_kind`, `blocked_shell_control`, `no_terminal_summary`) in subagent return payload so parent can branch intelligently.
- Tighten reviewer prompt contract for Python package entrypoints:
  - require reviewer to flag `from calculator import Calculator` in package subfolders and suggest package-safe import (`from .calculator import Calculator`) so parent avoids unnecessary re-review loops.
- Add regression tests around this scenario in runtime tests:
  - failing coder first with directory read + blocked pipeline, then verify single automatic constrained respawn succeeds;
  - verify parent-step cap is not consumed by sub-agent model calls.

## Key Files
- [C:/Users/emil_/vscode/vg_assignment/scripts/generate_project.py](C:/Users/emil_/vscode/vg_assignment/scripts/generate_project.py)
- [C:/Users/emil_/vscode/vg_assignment/specs/30_runtime_governance.md](C:/Users/emil_/vscode/vg_assignment/specs/30_runtime_governance.md)
- [C:/Users/emil_/vscode/vg_assignment/specs/20_tools.md](C:/Users/emil_/vscode/vg_assignment/specs/20_tools.md)
- [C:/Users/emil_/vscode/vg_assignment/tests/test_vg_agent.py](C:/Users/emil_/vscode/vg_assignment/tests/test_vg_agent.py)