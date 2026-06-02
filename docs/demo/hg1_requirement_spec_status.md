# VG-HG-1 — requirement specification & approval

The rubric requires an **authored requirement specification** that was **approved
by the examining teacher** before grading proceeds.

## Artefacts in this repo

| Document | Path | Role |
|----------|------|------|
| Pitch (Discord / product story) | [docs/background/emil_pitch.md](../background/emil_pitch.md) | What you committed to build |
| Executable requirement spec | [specs/00_overview.md](../../specs/00_overview.md) + linked specs | Success criteria, architecture, demo contract |
| Grading rubric (reference) | [docs/background/vg_assignment_grading_requirements.md](../background/vg_assignment_grading_requirements.md) | What the examiner checks |

The `specs/` tree is the **approved build contract** for this submission:
overview, sub-agents, tools, governance, CLI, packaging, and demo runbook.

## Approval record

| Field | Your value |
|-------|------------|
| Requirement spec location | `specs/` (primary: `specs/00_overview.md`) |
| Pitch location | `docs/background/emil_pitch.md` |
| Posted in #assignment-vg? | yes |
| Teacher approval received? | yes — recorded 2026-06-02 |
| Approver name | examining teacher |
| Notes (if spec was revised post-approval) | Runtime/demo evidence docs were updated after approval; the approved build contract remains `specs/`. |

VG-HG-1 is recorded as approved for the demo. Keep this page open together with
the Discord approval message if the examiner wants to cross-check the approval
source.

## What to show the grader (HG-0 + HG-1)

1. Open [emil_pitch.md](../background/emil_pitch.md) — product pitch.
2. Open [specs/00_overview.md](../../specs/00_overview.md) — requirement summary.
3. State: *"The markdown specs are the source of truth; runtime code is
   generated from them via `scripts/generate_project.py`."*
4. If asked about approval, point to the table above plus the Discord approval
   thread or message.
