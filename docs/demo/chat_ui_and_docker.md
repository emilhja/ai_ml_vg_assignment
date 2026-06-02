# Chat UI and Docker image freshness

## Runtime paths

| Path | When to use | Chat UI code source |
|------|-------------|---------------------|
| `docker compose run … vg-agent` | Demos, grading, canonical live runs | Baked into the image at **last** `docker compose build` |
| `uv run -m vg_agent --chat` | Local dev / test iteration | Current `src/vg_agent/` on disk (after `generate_project.py --clean` if needed) |

Good and bad terminal layouts seen on 2026-06-02 were often **different binaries** (stale image vs fresh build) or **different parent models** (`claude-sonnet-4.6` vs `google/gemini-2.0-flash-001`), not a single afternoon code regression on `main`.

## Why a stale image changes the UI

The agent [`Dockerfile`](../../Dockerfile) copies `src/` at build time and runs:

```dockerfile
RUN uv sync --frozen --no-dev && python scripts/generate_project.py --clean
```

`chat_ui.py` is preserved from the build context (`EXTRA_SOURCE_GENERATED_FILES`). Running `docker compose run` **without** rebuilding reuses the old UI even after you edit the repo on the host.

## Rebuild after UI or generator changes

Whenever you change `src/vg_agent/chat_ui.py`, `scripts/generate_project.py`, or related specs:

```powershell
python scripts/generate_project.py --clean   # local dev
docker compose build vg-agent              # before demo/chat in Docker
docker compose run --rm -it vg-agent --chat --require-approval writes
```

If behavior still looks wrong:

```powershell
docker compose build --no-cache vg-agent
```

## Expected Rich TTY chat layout (checklist)

After a fresh build, interactive chat should show:

- Welcome panel + status bar + hint (`/status to refresh dashboard and print session summary`)
- Labeled `input` rule, then `> ` prompt
- One `… running` status line after submit (not a duplicate idle status)
- `── turn N ──` and `[llm]` / `[tool]` / `[agent]` progress on stderr
- Rich approval panels; inline indented diffs after successful `write_file` / `edit_file` on stderr
- Plain bulletized answer on stdout at turn end (no `Response` title panel)

See [`specs/16_chat_ui.md`](../../specs/16_chat_ui.md) for the full contract.
