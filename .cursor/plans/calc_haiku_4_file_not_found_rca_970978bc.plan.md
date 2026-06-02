---
name: calc_haiku_4 file not found RCA
overview: Explorers failed because the prompt named `engine.py` and `ui.py`, but the workspace only has `calculator_engine.py` and `calculator_ui.py` under `calc_haiku_4/`. The folder exists; `read_file` behaved correctly. This is a prompt/script shorthand issue, not a new runtime or Docker bug.
todos:
  - id: retry-canonical-prompt
    content: Re-run chat with calculator_engine.py / calculator_ui.py in spawn_subagents (not engine.py / ui.py)
    status: completed
  - id: fix-demo-alt-line
    content: "Optional: edit final_demo_live_chat_script.md alt block to use real filenames or delete alt"
    status: completed
isProject: false
---

# calc_haiku_4 “file not found” — root cause

## Verdict

**Not a new prompt regression in the agent runtime.** The directory [`workspace/calc_haiku_4/`](workspace/calc_haiku_4/) exists and is mounted at `/workspace` in Docker (`cwd: /workspace`). Tools resolved paths correctly. Explorers got `[Errno 2]` because **`calc_haiku_4/engine.py` and `calc_haiku_4/ui.py` do not exist on disk**.

## What is actually on disk

| You / parent asked for | Actual file |
|------------------------|-------------|
| `calc_haiku_4/engine.py` | [`workspace/calc_haiku_4/calculator_engine.py`](workspace/calc_haiku_4/calculator_engine.py) |
| `calc_haiku_4/ui.py` | [`workspace/calc_haiku_4/calculator_ui.py`](workspace/calc_haiku_4/calculator_ui.py) |

Also present: [`main.py`](workspace/calc_haiku_4/main.py), [`__init__.py`](workspace/calc_haiku_4/__init__.py) (imports use `calculator_engine` / `calculator_ui`).

```mermaid
flowchart LR
  userPrompt["User: engine.py + ui.py"]
  parentSpawn["Parent spawn_subagents"]
  explorerRead["Explorer read_file"]
  enoent["ENOENT — correct"]
  findRecovery["Parent find calc_haiku_4"]

  userPrompt --> parentSpawn --> explorerRead --> enoent
  enoent --> findRecovery
```

## Why the log looks like “folder missing”

From your trace:

- `read_file calc_haiku_4/engine.py` → `No such file or directory: '/workspace/calc_haiku_4/engine.py'`
- Same for `ui.py`

That message means **that exact path** is absent, not that `calc_haiku_4/` is missing. The parent’s follow-up `find . -maxdepth 1 -type d` and `find calc_haiku_4 -type f` is the right recovery and should list `calculator_engine.py` / `calculator_ui.py`.

## Prompt source of the mistake

You used the **“alt”** one-liner from [`docs/demo/final_demo_live_chat_script.md`](docs/demo/final_demo_live_chat_script.md) (lines 13–14):

```text
spawn_subagents: 2× Explorer (read-only) — engine.py + ui.py APIs in calc_haiku_4/.
```

The **canonical** block above it (lines 1–4) uses the real names:

```text
- calc_haiku_4/calculator_engine.py
- calc_haiku_4/calculator_ui.py
```

Your [`workspace/.vg_chat_history`](workspace/.vg_chat_history) shows the same pattern: runs at 10:51 / 11:50 used full paths; runs at 11:57 / 12:28 used `engine.py + ui.py` and hit the same errors.

The parent faithfully passed shorthand into Explorer briefs; Explorers called `read_file` on literal paths. [`PROMPTS.md`](PROMPTS.md) says to spawn Explorer on named paths directly — it does not rewrite `engine.py` → `calculator_engine.py`.

## What is *not* broken

- **Workspace root** — `resolve_workspace_path` in generated [`src/vg_agent/tools.py`](src/vg_agent/tools.py) maps `calc_haiku_4/...` under `/workspace`; the error path proves mount + resolution work.
- **Parallel spawn** — two Explorers ran concurrently; failures were independent ENOENTs, not a race.
- **Explorer / parent system prompts** — no recent change required to explain this; earlier successful sessions in history used correct filenames.

## What to do next (no code change required)

**Use the canonical prompt** (paste from demo script lines 1–11), e.g.:

```text
Use one spawn_subagents call with two Explorer requests (read-only):
- Summarize public API of calc_haiku_4/calculator_engine.py ...
- Summarize public API of calc_haiku_4/calculator_ui.py ...
Wait for both Explorer returns, then spawn one Coder to create or update only:
- calc_haiku_4/main.py
- calc_haiku_4/__init__.py
```

Or the shorter variant that still names real files:

```text
spawn_subagents: Explorer inspect calc_haiku_4/calculator_engine.py AND Explorer inspect calc_haiku_4/calculator_ui.py (read-only), then one Coder for main.py + __init__.py after both return.
```

After re-running, Explorers should `read_file` successfully; Coder can align `main.py` / `__init__.py` with existing modules.

## Optional doc hygiene (if you want a repo fix later)

1. **Remove or fix the “alt” line** in [`docs/demo/final_demo_live_chat_script.md`](docs/demo/final_demo_live_chat_script.md) so it never says `engine.py` / `ui.py` without the `calculator_` prefix.
2. **Do not change** `PROMPTS.md` or generated agent code for this — behavior is correct; the input paths were wrong.

## Pass criteria for a retry

- Explorer tool lines show `read_file calc_haiku_4/calculator_engine.py` and `.../calculator_ui.py` with `ok`, not `error`.
- Parent Coder spawn references APIs from those files, not “file not found” summaries.
