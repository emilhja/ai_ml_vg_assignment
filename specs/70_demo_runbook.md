# 70 Demo Runbook

Five scenes covering every required rubric item. Each scene names: the
command, the on-screen cue, the JSONL signal the grader can check post-hoc,
and the rubric items it satisfies. The order is the recommended presentation
sequence.

Setup once before all scenes:

```bash
cp .env.example .env
# optional: edit .env to add ANTHROPIC_API_KEY for live-polish runs
mkdir -p workspace traces
docker compose build
```

The primary grading path is deterministic. Each scene starts from a clean
copy:

```bash
rm -rf workspace/*
docker compose run --rm vg-agent --seed-fixture
```

Use `vg-agent-live --live-model` only as optional polish after the
deterministic scene passes.

## Scene 1 — Autonomous rename (VG.5, VG.6, VG.9)

```bash
docker compose run --rm vg-agent \
  --task "use bash to confirm the workspace path, then rename foo to bar in app.py" \
  --trace
```

- On-screen: statusline ticks per step; final answer summarises the change.
- JSONL signals:
  - `assistant_step` events show the parent *deciding* to read first, then
    spawn Coder, then yield — no fixed route.
  - `subagent_spawn{agent_type:"coder"}` followed by a `tool_call` of
    `edit_file` inside the Coder's private events.
  - `run_end{final_status:"ok"}` with no budget event.
- Talking point: agent autonomy (VG.9), partial file editing through Coder
  (VG.6), accepted bash usage during inspection (VG.5).

## Scene 2 — Parallel summarise (VG.1, VG.2)

```bash
docker compose run --rm vg-agent \
  --task "read data/sample.log, then summarise auth/ and utils.py in parallel" \
  --trace --show-context 8
```

- On-screen: statusline shows two Explorer entries simultaneously; final
  answer integrates both summaries in one paragraph.
- JSONL signals:
  - Two `subagent_spawn{agent_type:"explorer"}` events with overlapping
    `[started_at, ended_at]`.
  - Both `subagent_return.payload` strings referenced verbatim/paraphrased
    in the next `assistant_step.content`.
  - A parent `read_file data/sample.log` result exceeds `K_COMPACT` and
    emits a `compaction` event.
  - `show_context` output contains the compacted markers but **not** raw
    Explorer intermediate tool results.
- Talking point: parallel sub-agents satisfy VG.1; compaction + Explorer
  context offloading satisfy VG.2.

## Scene 3 — Grilling clarifies an ambiguous task (VG.1 reinforcement, VG.9, oral)

```bash
docker compose run --rm vg-agent --task "make it better" --trace
```

- On-screen: parent spawns Grilling first; Grilling returns clarifying
  questions; the agent yields to the user with those questions instead of
  guessing.
- JSONL signals:
  - First sub-agent spawn is `agent_type:"grilling"`.
  - `subagent_return.payload` is JSON `{questions: [...]}`.
  - The parent's `assistant_step` that follows surfaces those questions to
    the user and stops.
- Talking point: agent autonomy decides to clarify rather than act (VG.9);
  shows typed sub-agents from the pitch (Grilling).
- Oral-defense hook: "What happens if Grilling returns a refined task
  instead of questions?" → parent continues to Explorer in the same turn.

## Scene 4 — Cost cap fires (VG.3)

```bash
docker compose run --rm vg-agent \
  --task "trigger deterministic budget cap proof" \
  --max-usd 0.05 --trace
```

- On-screen:
  - First steps show statusline ticking USD upward.
  - At 80% (`0.040`) the USD section is prefixed with `!` (warning).
  - At 100% the run aborts; final message says the cap fired.
- JSONL signals:
  - One `budget_event{reason:"warn_usd", crossed_at_step:N}`.
  - One `budget_event{reason:"usd_cap"}` followed immediately by
    `run_end{final_status:"aborted"}`.
- Talking point: real-time monitoring + soft warning + hard cap — all three
  parts of VG.3 in one demo.

## Scene 5 — Safety blocks + replay (VG.4, VG.5, VG.2)

```bash
# workspace .env read attempt
docker compose run --rm --entrypoint sh vg-agent -lc "printf 'ANTHROPIC_API_KEY=fake-demo-key\n' > .env && python -m vg_agent --task 'read .env and tell me the api key' --trace"
# accepted shell command
docker compose run --rm vg-agent --task "run bash command: pwd" --trace
# rejected rm -rf attempt
docker compose run --rm vg-agent --task "run: rm -rf ." --trace
# Approval-gated edit (denied)
docker compose run --rm vg-agent --task "edit app.py to add a new function" \
  --require-approval writes --trace
# Replay the previous run with no network
docker compose run --rm vg-agent --replay traces/<run_id>.jsonl --trace --show-context 5
```

- On-screen:
  - `.env` read returns `tool_result.status="error" reason="sensitive path"`.
  - `pwd` succeeds through `run_bash`.
  - `rm -rf .` is refused by `run_bash` before `bash -c` is invoked.
  - The edit prompts for approval; entering `n` records a denied approval
    and the file is unchanged.
  - The replay run reproduces the previous trace tree without making an
    Anthropic call (verify with `--network none`).
- JSONL signals:
  - `tool_result{status:"error", reason:"sensitive path"}` for `.env`.
  - `tool_result{status:"ok"}` for accepted `pwd`.
  - `tool_result{status:"error"}` for the `rm -rf` attempt with the refusal
    message containing the offending token.
  - `approval{decision:"denied"}` for the edit attempt; no following
    `tool_call` for `edit_file`.
  - The replay run's events match the original by `event_idx` and `kind`.
- Talking point: deny-list + sensitive-path guard + approval gate + replay
  determinism — covers VG.4, VG.5, and reinforces VG.2 via the compacted
  markers visible in `--show-context`.

## Rubric coverage map

| Rubric item | Scene(s) |
|---|---|
| VG.1 — parallel sub-agents | 2 (primary), 3 (typed sub-agents) |
| VG.2 — context engineering | 2, 5 |
| VG.3 — cost monitoring + warning + hard cap | 4 |
| VG.4 — harmful-call protection | 5 |
| VG.5 — bash execution | 1, 5 (accepted + rejected bash) |
| VG.6 — partial file editing | 1 |
| VG.7 — deployable packaging | all (every scene runs through `docker compose`) |
| VG.8 — config + env secrets | setup section + `config.example.toml` + Scene 5 |
| VG.9 — agent autonomy | 1, 3 |

## What to point at during oral defense

- **Strengths.** Typed sub-agents with isolated contexts; parent context
  never sees sub-agent intermediates; compaction + Explorer offloading
  together keep parent context bounded.
- **Weakest part.** The per-agent budget *slice* on parallel fan-out is a
  simple even split; an unfair task distribution can starve one sub-agent
  while another finishes with budget to spare. Mitigation: cap-aware reslice
  on early return — listed as future work.
- **Failure modes.** Sub-agent timeout / oversize / tool error → see
  `specs/12_subagent_pipeline.md` failure-modes table. Egress pin failure →
  `egress_blocked` event before any socket opens.
