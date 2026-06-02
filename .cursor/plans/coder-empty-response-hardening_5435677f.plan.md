---
name: coder-empty-response-hardening
overview: Harden sub-agent execution so coder flows recover automatically when a model returns empty text and no tool calls, instead of burning steps with repeated ineffective spawns.
todos:
  - id: spec-template-update
    content: Update generator template logic for coder empty-turn detection and bounded retry/fallback behavior.
    status: completed
  - id: trace-surface
    content: Add explicit trace signal/reason for empty-turn retries and terminal failure reason.
    status: completed
  - id: test-coverage
    content: Add tests covering successful recovery and capped failure for empty coder turns.
    status: completed
  - id: regen-validate
    content: Regenerate project and run tests to verify behavior and invariants.
    status: completed
isProject: false
---

# Harden Coder Empty-Response Flow

## What I found
- The failing run in `traces/c834fe816085.jsonl` shows three coder spawns (`coder-1..3`) using `openrouter/google/gemini-2.5-flash`, each returning `assistant_text: ""`, `tokens_out: 1`, `tool_calls: []`, provider `Google`, then failing with `"Coder returned without writing or editing any file."`.
- Parent behavior is currently compliant with prompts (it retries), but retries are semantically weak because runtime does not distinguish a transient empty model turn from normal no-tool completion.

## Plan
- Add explicit empty-turn detection in sub-agent loop in [`C:/Users/emil_/vscode/vg_assignment/scripts/generate_project.py`](C:/Users/emil_/vscode/vg_assignment/scripts/generate_project.py) template that generates `_run_live_subagent` in [`C:/Users/emil_/vscode/vg_assignment/src/vg_agent/agent.py`](C:/Users/emil_/vscode/vg_assignment/src/vg_agent/agent.py):
  - Treat `(no tool calls) + (blank/whitespace assistant text)` as `empty_turn`.
  - For `coder`, retry locally with a deterministic nudge message that forces `write_file`/`edit_file` and concrete path usage.
- Add bounded fallback policy for coder empty-turns (e.g., 1-2 local retries max per coder spawn) before returning to parent, so one parent spawn has a fair chance to recover.
- Emit trace diagnostics (`budget_event` or dedicated event field) for empty-turn retries to make this class of model failure visible in dashboard review.
- Preserve current contract that coder must produce `writes_ok > 0`, but update failure payload text to indicate whether it was due to repeated empty turns vs normal read-only completion.
- Extend tests in [`C:/Users/emil_/vscode/vg_assignment/tests/test_vg_agent.py`](C:/Users/emil_/vscode/vg_assignment/tests/test_vg_agent.py):
  - New test: coder first returns empty/no-tools, second step writes file successfully within same sub-agent run.
  - New test: repeated empty turns exceed retry cap and return deterministic `tool_error` reason.
  - Keep existing `writes_ok == 0` guard test intact.
- Regenerate generated artifacts via [`C:/Users/emil_/vscode/vg_assignment/scripts/generate_project.py`](C:/Users/emil_/vscode/vg_assignment/scripts/generate_project.py) and validate with pytest.