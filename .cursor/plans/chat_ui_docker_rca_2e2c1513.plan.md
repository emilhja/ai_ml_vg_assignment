---
name: Chat UI Docker RCA
overview: Your terminal pastes today show at least two UI variants; the latest paste matches the desired layout. Likely cause of the “worse” sessions is a stale `vg-agent` Docker image, not the Jun 2 parallel commits. Finish by documenting rebuild discipline and optionally landing local chat_ui fixes already in the working tree.
todos:
  - id: confirm-runtime
    content: Confirm whether good vs bad sessions used Docker vs local uv; note image build time if possible
    status: completed
  - id: rebuild-doc
    content: "Add README/demo note: rebuild vg-agent image after chat_ui or generate_project changes"
    status: completed
  - id: land-or-drop-wip
    content: "Decide: commit uncommitted chat_ui throttle/inline-diff/show_status fixes, or discard and rely on rebuild of current main"
    status: completed
  - id: verify-docker
    content: docker compose build vg-agent && smoke --chat; compare to py_calc2 paste checklist
    status: completed
isProject: false
---

# Chat UI: paste comparison and Docker stale-image RCA

## Yes — your pastes differ (reviewed across today’s chats)

From transcripts and this thread, there are **at least two recognizable layouts**:

| Signal | “Detailed” paste (your long parallel session + **this new calc paste**) | “Simpler / worse” paste (screenshot + earlier chat) |
|--------|---------------------------------------------------------------------------|-----------------------------------------------------|
| Parent model | `claude-sonnet-4.6` | `google/gemini-2.0-flash-001` |
| Context window | `ctx …/200.0k` | `ctx …/1.0m` |
| Hint line | `/status to refresh **dashboard and print session summary**` | `/status to refresh **session**` (older hint) |
| Turn progress | `── turn N ──`, `[llm]`, `[tool]`, `[agent]` | Often shorter / less sub-agent detail |
| Parallel | `[parallel] …` when `spawn_subagents` runs | Often absent (different tasks) |
| Write approval | Rich panel **plus** inline `  --- a/…` after `[tool]` | More “Response” boxing; less log-style detail |
| End of turn | Bullet summary + optional `Tool output` / `Changes` | Heavy `Response` rules/panels |

So it was **not** one stable UI that slowly broke in code this afternoon — you were often comparing **different runs** (model/config/task) and possibly **different binaries** (Docker vs local).

---

## Your new paste = target behavior

The `py_calc2` session you just sent matches what we want:

- Welcome + status bar + labeled `input` rule
- **One** `… running` status after submit (no duplicate `✓ ready` block)
- `── turn 1 ──` and streaming `[llm]` / `[tool]` / `[agent]` lines
- Rich approval panels (spawn + write with diff preview)
- **Inline** progress diff right after `[tool] coder-1 write_file ok` (indented `  --- a/py_calc2/...`)

That inline diff + single running status align with **uncommitted** local changes in [`src/vg_agent/chat_ui.py`](src/vg_agent/chat_ui.py) / [`scripts/generate_project.py`](scripts/generate_project.py) (`write_progress_diff_lines`, `show_status=False` before runs, status-bar throttle). They are **not** on committed `main` yet.

---

## Docker build — why a stale image is plausible

[`Dockerfile`](Dockerfile) copies `src/` at **build time**, then runs:

```dockerfile
RUN uv sync --frozen --no-dev && python scripts/generate_project.py --clean
```

Implications:

- `docker compose run` **without** `build` reuses the old image → old `chat_ui.py` / generated `__main__.py` even after you edit the repo on the host.
- [`chat_ui.py`](src/vg_agent/chat_ui.py) is preserved via `EXTRA_SOURCE_GENERATED_FILES` — whatever was on disk **when the image was built** is what runs in the container.
- A “bad” afternoon session could be an image built **before** hint/progress tweaks, while “good now” = `docker compose build` (or local `uv run`) picked up current tree.

**Recommended habit after any `chat_ui` / generator change:**

```bash
docker compose build vg-agent
docker compose run --rm -it vg-agent --chat --require-approval writes
```

Use `docker compose build --no-cache vg-agent` if behavior still looks wrong.

---

## Revised root cause (vs earlier plan)

| Hypothesis | Verdict |
|------------|---------|
| Jun 2 commit `78501f6` broke terminal chrome | **Unlikely** — only parallel hint + `[parallel]` scoping (~11 lines in chat files) |
| May 29 commits added Response panels / Rich progress panels | **Real UX deltas**, but your “good” morning pastes already used sonnet + dashboard hint |
| Stale Docker image | **Strong fit** for “UI changed 1–2 hours ago” then “looks better now” after rebuild |
| Wrong model in status bar (gemini vs sonnet) | Explains **different** ctx/hint between pastes, not necessarily a bug |

---

## Recommended next steps (when you approve execution)

1. **Confirm runtime path** — note whether good/bad sessions used `docker compose run` vs `uv run -m vg_agent --chat` from the repo.
2. **Land or drop local WIP** — commit the uncommitted chat UI fixes (throttle, inline progress diff, lighter end-of-turn) **or** discard if you only want Docker rebuild on current `main`.
3. **Docs one-liner** — add to [`README.md`](README.md) / demo script: “After pulling or editing `src/vg_agent`, rebuild `vg-agent` image.”
4. **Skip large UI rewrites** — no need to revert parallel work from `78501f6`; optional polish only if something in the new paste still annoys you (e.g. huge write approval diff panel is intentional per spec).

No full git bisect required unless a **fresh** `docker compose build` still reproduces the bad layout.
