---
name: budget-ux-reviewer-fix
overview: Fix budget-cap override prompts so option “2 yes (this cap)” caches per cap reason (step_cap/token_cap) instead of producing repeated prompts; improve token-cap prompt clarity by showing the actual cap bump. Also ensure the `reviewer` sub-agent always returns a `PASS:/FAIL:` verdict string even when it stops early (budget caps / step exhaustion), so failures are readable and actionable.
todos:
  - id: fix-budget-cap-scope-and-token-text
    content: "Fix `src/vg_agent/chat_ui.py` budget-cap prompt parsing: for `budget_cap` choice `2`, set cache `scope_key=request.path` (cap reason) instead of parent folder; update `format_budget_cap_approval_text` wording for step caps and enrich `token_cap` prompt with computed bump + resulting max values."
    status: completed
  - id: fix-reviewer-early-stop-into-verdict
    content: Update `scripts/generate_project.py` sub-agent loop template so reviewer early exits always return a `PASS:/FAIL:` verdict (prefer `FAIL:` with reason) when `final_summary` is empty or non-verdict.
    status: completed
  - id: update-spec-docs
    content: Update `specs/16_chat_ui.md` and `specs/12_subagent_pipeline.md` to document the new budget-cap caching semantics and reviewer verdict fallback contract.
    status: completed
  - id: add-tests-budget-cap-and-reviewer-fallback
    content: "Extend `tests/test_vg_agent.py` with: (1) scope_key test for budget-cap choice `2`, (2) runtime caching behavior test ensuring prompt is asked once per cap reason, (3) token-cap prompt text bump assertions, and (4) reviewer verdict fallback tests for both step exhaustion and budget abort cases."
    status: completed
  - id: regenerate-and-run-tests
    content: "After code/spec changes: run `python scripts/generate_project.py --clean` and `uv run pytest` (optionally targeted tests first)."
    status: completed
isProject: false
---

## Goals from your run
- Repeated prompts for overriding step/token caps (`step_cap`, `token_cap`) were especially noisy.
- `reviewer-*` sometimes returned `tool_error` with `"stopped before producing a final summary"`, which wasn’t a `PASS:/FAIL:` verdict and reduced clarity.

## What went well
- Proactive `step_extend` prompt at the last step exists and provided useful context (`Parent steps used`, how the cap changes).
- The budget system still enforces hard caps safely (no silent overruns).

## What went wrong (root causes)
1. **Budget-cap scope caching bug (UX + behavior):**
   - In `src/vg_agent/chat_ui.py`, when the user picks option `2` (`"yes (this cap)"`) for `budget_cap`, the scope cache key is derived from the *parent folder of* `request.path`.
   - For `budget_cap`, `request.path` is the cap reason (`step_cap`, `token_cap`, …), not a filesystem path. That derivation yields `""`, so the cache never matches `step_cap`/`token_cap` later.
   - Result: the agent keeps prompting repeatedly even after you selected “scoped for this cap”.
2. **Reviewer verdict fallback wasn’t a verdict:**
   - When the reviewer sub-agent stops early, it can return a generic message (`"reviewer stopped before producing a final summary."`) that does not start with `PASS:` or `FAIL:`.
   - This violates the “final message must start with `PASS:` or `FAIL:`” contract and is less helpful than a deterministic `FAIL:` reason.

## Implementation changes
### 1) Budget-cap override prompt fixes (scope + clarity)
- Update `[_parse_approval_choice]`](src/vg_agent/chat_ui.py) so that for `request.tool == "budget_cap"` and choice `"2"`, `scope_key` is set to the cap *reason* (`request.path`) rather than the parent directory.
- Align budget-cap UI wording:
  - In `format_budget_cap_approval_text`, update the step-cap/extend body so the option `2` wording matches the menu label (`"2 yes (this cap)"`).
  - For `token_cap`, include the computed bump and show the resulting max for:
    - `1/y yes` (one-time bump)
    - `2` / `3` (scoped vs always)

Key code to change (current behavior):
- `src/vg_agent/chat_ui.py`: option `2` currently computes a parent folder from `request.path`, which breaks for `budget_cap` (where `request.path` is a reason string).

### 2) Reviewer verdict reliability
- Update the generated sub-agent loop template in `[scripts/generate_project.py](scripts/generate_project.py)` so that:
  - If `reviewer` stops early without producing a verdict (empty `final_summary` or non-`PASS:/FAIL:` content), the returned `summary` becomes a deterministic `FAIL:` line that explains the stop reason (budget cap / timeout / step exhaustion).
  - If the sub-agent budget-cap denial happens mid-loop (i.e. `_handle_budget_cap(...)=False`), ensure we still return a verdict for `reviewer`.

Key code to change (current behavior):
- `scripts/generate_project.py` (template for `_run_live_subagent`) currently ends with:
  - `if not final_summary: final_summary = f"{agent_type} stopped before producing a final summary."`
  - This string does not start with `PASS:` or `FAIL:` for reviewers.

### 3) Specs/docs alignment
- Update `[specs/16_chat_ui.md](specs/16_chat_ui.md)` to document that `budget_cap` option `2` caches by **cap reason**, not by folder.
- Update `[specs/12_subagent_pipeline.md](specs/12_subagent_pipeline.md)` to document the new reviewer fallback behavior: when the reviewer can’t complete, it still returns a `FAIL:` verdict.

### 4) Tests
Add focused unit tests in `[tests/test_vg_agent.py](tests/test_vg_agent.py)`:
1. **Budget-cap choice `2` scope key test**
   - Assert `chat_ui._parse_approval_choice("2", request)` returns `scope_key == request.path` when `request.tool == "budget_cap"`.
2. **Budget-cap caching behavior test**
   - Run a synthetic `run_live_task` where `step_cap` hits multiple times in one run.
   - Use an approval prompt that selects option `2` and counts how many times the prompt is invoked.
   - Assert the prompt is called only once after the first extension.
3. **Token-cap text clarity test**
   - Assert `format_budget_cap_approval_text("token_cap", ...)` includes the computed bump and resulting max values.
4. **Reviewer verdict fallback tests**
   - A) “never produces final tool-less response” scenario: feed reviewer a sequence of tool-calling turns until `MAX_SUBAGENT_STEPS` is exhausted; assert the returned summary starts with `FAIL:`.
   - B) “budget cap abort before any final response” scenario: set `BudgetGuard(max_steps=0)` and deny the cap prompt; assert the returned summary starts with `FAIL:`.

## Regeneration / verification steps
1. Run `python scripts/generate_project.py --clean`.
2. Run `uv run pytest`.
3. (Optional) Run targeted tests for the new cases.
