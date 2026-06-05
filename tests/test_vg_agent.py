from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from pathlib import Path

import pytest

from vg_agent import config
from vg_agent.agent import (
    ApprovalOutcome,
    ApprovalPolicy,
    ApprovalRequest,
    PARENT_SYSTEM_PROMPT,
    PARENT_TOOL_SCHEMAS,
    _build_review_slice,
    _resolve_review_coder_id,
    _run_live_subagent,
    _tool_path,
    run_live_task,
)
from vg_agent.live_model_client import (
    EndpointPinViolation,
    LiveModelClient,
    LiveModelRateLimitError,
    ModelTurn,
    ToolCall,
)
from vg_agent.budget import BudgetGuard, DailySpendLedger, PricingUnavailable
from vg_agent.demo_fixture import write_fixture
from vg_agent.tools import (
    edit_file,
    read_file,
    read_file_range,
    run_bash,
    run_tests,
    validate_run_tests_path,
    validate_sensitive_path,
    validate_shell_command,
    validate_shell_command_for_workspace,
    write_file,
)
from vg_agent.trace import TraceRecorder, _redact, show_context


ROOT = Path(__file__).resolve().parents[1]


def read_events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class FakeClient:
    def __init__(self, turns: list[ModelTurn]) -> None:
        self.turns = turns
        self.calls: list[dict[str, object]] = []

    def complete(self, **kwargs: object) -> ModelTurn:
        self.calls.append(json.loads(json.dumps(kwargs, default=str)))
        if not self.turns:
            raise AssertionError("fake client has no remaining turns")
        return self.turns.pop(0)


class FailingRateLimitClient:
    def complete(self, **_kwargs: object) -> ModelTurn:
        raise LiveModelRateLimitError(
            "live model provider rate-limited openrouter/google/gemini-2.0-flash-001. Retry shortly."
        )


def _classify_agent(system_prompt: str) -> str:
    if "Summarise the supplied tool result" in system_prompt:
        return "compactor"
    if "Summarise the supplied prior conversation" in system_prompt:
        return "compactor"
    if "parent coding agent" in system_prompt:
        return "parent"
    if "You are Grilling" in system_prompt:
        return "grilling"
    if "You are Explorer" in system_prompt:
        return "explorer"
    if "You are Coder" in system_prompt:
        return "coder"
    if "You are Reviewer" in system_prompt:
        return "reviewer"
    return "parent"


def _last_user_text(messages: list[dict[str, object]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(str(b.get("content") or b.get("text") or "") for b in content if isinstance(b, dict))
    return ""


class PipelineClient:
    """Thread-safe fake routing by typed system prompt.

    Parent turns are popped in order. Sub-agents pop from a per-type queue when
    provided; otherwise they return a single no-tool summary echoing the question,
    which keeps concurrent (threaded) spawn_subagents deterministic regardless of
    completion order.
    """

    def __init__(self, parent_turns: list[ModelTurn], by_type: dict[str, list[ModelTurn]] | None = None) -> None:
        self.parent_turns = list(parent_turns)
        self.by_type = {k: list(v) for k, v in (by_type or {}).items()}
        self.lock = threading.Lock()
        self.calls: list[dict[str, object]] = []

    def complete(self, **kwargs: object) -> ModelTurn:
        with self.lock:
            self.calls.append(json.loads(json.dumps(kwargs, default=str)))
            agent = _classify_agent(str(kwargs.get("system_prompt") or ""))
            if agent == "parent":
                return self.parent_turns.pop(0)
            queue = self.by_type.get(agent)
            if queue:
                return queue.pop(0)
            question = _last_user_text(kwargs.get("messages") or [])  # type: ignore[arg-type]
            return ModelTurn(assistant_text=f"{agent} summary: {question}", input_tokens=20, output_tokens=10)


def test_format_usd_display_sub_cent() -> None:
    from vg_agent.budget import format_usd_display, format_usd_number

    assert format_usd_display(0.0) == "$0.00"
    assert format_usd_display(0.5) == "$0.50"
    assert format_usd_display(5.0) == "$5.00"
    assert format_usd_display(0.0001) == "$0.0001"
    assert format_usd_display(0.00001) == "$0.00001"
    assert format_usd_display(0.0017) == "$0.0017"
    assert format_usd_number(1e-05) == "0.00001"
    assert "e" not in format_usd_number(0.00001).lower()


def test_budget_guard_reasons_and_costs() -> None:
    guard = BudgetGuard(max_steps=1)
    assert guard.before_model_call(config.PARENT_MODEL_ID, 100, 100).allowed
    guard.record_model_call(config.PARENT_MODEL_ID, 100, 100)
    decision = guard.before_model_call(
        config.PARENT_MODEL_ID,
        100,
        100,
        enforce_parent_step_cap=True,
    )
    assert not decision.allowed
    assert decision.budget_reason == "step_cap"

    guard = BudgetGuard(max_usd=0.000001)
    decision = guard.before_model_call(config.PARENT_MODEL_ID, 1000, 1000)
    assert not decision.allowed
    assert decision.budget_reason == "usd_cap"

    guard = BudgetGuard()
    assert guard.record_tool_signature("run_bash", "grep missing").allowed
    assert guard.record_tool_signature("run_bash", "grep missing").allowed
    decision = guard.record_tool_signature("run_bash", "grep missing")
    assert not decision.allowed
    assert decision.budget_reason == "repetition_abort"

    guard = BudgetGuard()
    assert guard.record_model_call("openrouter/example/unknown", 10, 10, cost_usd=0.01) == pytest.approx(0.01)
    with pytest.raises(PricingUnavailable):
        guard.record_model_call("openrouter/example/unknown", 10, 10)


def test_budget_guard_warn_usd_emits_once_at_eighty_percent() -> None:
    # VG.3 soft warning: crossing 80% of max_usd emits warn_usd once; run continues.
    max_usd = 1.0
    guard = BudgetGuard(max_usd=max_usd)
    threshold = config.WARN_USD_FRACTION * max_usd
    guard.record_model_call(config.PARENT_MODEL_ID, 10, 10, cost_usd=threshold - 0.01)
    assert guard.pending_warnings() == []
    guard.record_model_call(config.PARENT_MODEL_ID, 10, 10, cost_usd=0.02)
    warnings = guard.pending_warnings()
    assert len(warnings) == 1
    assert warnings[0].budget_reason == "warn_usd"
    assert warnings[0].allowed is True
    assert warnings[0].details["running_usd"] >= threshold
    assert guard.pending_warnings() == []


def _log_then_explorer_client() -> PipelineClient:
    """Parent reads the large log (forces compaction) then spawns one Explorer."""
    return PipelineClient(
        parent_turns=[
            ModelTurn(
                "Read the large log before delegating.",
                [ToolCall("parent-read-sample-log", "read_file", {"path": "data/sample.log"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=20,
            ),
            ModelTurn(
                "Delegate auth inspection to an Explorer.",
                [ToolCall("spawn-explorer", "spawn_subagent", {"type": "explorer", "question": "inspect auth/ SENTINEL_AUTH"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=20,
            ),
            ModelTurn("Auth summary integrated: SENTINEL_AUTH.", input_tokens=100, output_tokens=20),
        ],
        by_type={
            "compactor": [
                ModelTurn(
                    "SAMPLE_LOG_SUMMARY_SENTINEL: large log summarised for parent context.",
                    input_tokens=100,
                    output_tokens=50,
                )
            ],
            "explorer": [ModelTurn("SENTINEL_AUTH: session middleware and routes.", input_tokens=20, output_tokens=10)],
        },
    )


def _rename_via_coder_client() -> PipelineClient:
    """Parent delegates a foo->bar rename in app.py to a Coder sub-agent."""
    return PipelineClient(
        parent_turns=[
            ModelTurn(
                "Delegate the rename to a Coder.",
                [ToolCall("spawn-coder", "spawn_subagent", {"type": "coder", "question": "rename foo to bar in app.py"})],
                stop_reason="tool_use",
                input_tokens=50,
                output_tokens=10,
            ),
            ModelTurn("Coder renamed foo to bar in app.py.", input_tokens=50, output_tokens=10),
        ],
        by_type={
            "coder": [
                ModelTurn(
                    "Applying the rename.",
                    [ToolCall("coder-edit", "edit_file", {"path": "app.py", "old": "foo", "new": "bar"})],
                    stop_reason="tool_use",
                    input_tokens=40,
                    output_tokens=10,
                ),
                ModelTurn("app.py: renamed foo to bar", input_tokens=20, output_tokens=5),
            ],
        },
    )


def test_compactor_fallback_on_model_error(tmp_path: Path) -> None:
    from vg_agent.agent import _compact_if_needed

    write_fixture(tmp_path)
    recorder = TraceRecorder(tmp_path)
    recorder.emit("tool_result", tool="read_file", tool_use_id="t1", result_full="x" * 50000, bytes=50000, tokens=9000, status="ok")
    event = recorder.events[-1]

    class FailingCompactorClient:
        def complete(self, **_kwargs: object) -> ModelTurn:
            raise LiveModelRateLimitError("compactor rate limited")

    compaction = _compact_if_needed(
        recorder,
        event,
        client=FailingCompactorClient(),
        guard=BudgetGuard(),
        tool="read_file",
        deterministic=False,
    )
    assert compaction is not None
    assert compaction.get("compactor_fallback") is True
    assert "Large read_file" in str(compaction.get("summary") or "")


def test_compact_conversation_deterministic(tmp_path: Path) -> None:
    from vg_agent.agent import compact_conversation

    recorder = TraceRecorder(tmp_path)
    messages: list[dict[str, object]] = []
    for index in range(6):
        messages.append({"role": "user", "content": f"question {index} " + ("word " * 500)})
        messages.append({"role": "assistant", "content": f"answer {index} " + ("detail " * 500)})
    before = len(messages)
    event = compact_conversation(
        recorder,
        messages,  # type: ignore[arg-type]
        config.PARENT_MODEL_ID,
        BudgetGuard(),
        client=PipelineClient([]),
        reason="manual",
        deterministic=True,
    )
    assert event is not None
    assert event["kind"] == "context_compaction"
    assert int(event["after_tokens"]) < int(event["before_tokens"])
    assert len(messages) < before
    assert messages[0]["role"] == "user"
    assert "CONVERSATION COMPACTED" in str(messages[0]["content"])


def test_chat_ctx_gauge_drops_after_context_compaction() -> None:
    """The terminal ctx gauge must fall after a /compact, not re-count the folded head."""
    from vg_agent.chat_ui import estimate_parent_ctx_tokens
    from vg_agent.trace import show_context

    big = "word " * 800
    events: list[dict[str, object]] = []
    for index in range(4):
        events.append({"kind": "user_prompt", "agent_id": "parent", "prompt": f"q{index} {big}"})
        events.append(
            {
                "kind": "assistant_step",
                "agent_id": "parent",
                "step_idx": index,
                "assistant_text": f"a{index} {big}",
                "tool_calls": [],
            }
        )
    before = estimate_parent_ctx_tokens(events)
    events.append(
        {
            "kind": "context_compaction",
            "agent_id": "parent",
            "before_tokens": 16500,
            "after_tokens": 7500,
            "percent_reduced": 54.5,
            "kept_user_turns": 1,
            "reason": "manual",
            "summary": "folded summary of older turns",
        }
    )
    after = estimate_parent_ctx_tokens(events)
    assert after < before

    # show_context folds the head: only the kept tail turn plus the marker remain.
    context = show_context(events, 3)
    assert sum(1 for item in context if item.get("role") == "user") == 1
    assert any(item.get("kind") == "context_compaction" for item in context)
    assert not any("q0" in str(item.get("content", "")) for item in context)


def test_auto_context_compaction_before_parent_llm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(config.CONTEXT_WINDOW_TOKENS, config.PARENT_MODEL_ID, 200)
    monkeypatch.setitem(config.AUTO_COMPACT_FRACTION, config.PARENT_MODEL_ID, 0.5)
    write_fixture(tmp_path)
    recorder = TraceRecorder(tmp_path)
    history: list[dict[str, object]] = [
        {"role": "user", "content": "old " + ("context " * 800)},
        {"role": "assistant", "content": [{"type": "text", "text": "old reply " + ("x " * 800)}]},
        {"role": "user", "content": "recent 1"},
        {"role": "assistant", "content": [{"type": "text", "text": "recent reply 1"}]},
        {"role": "user", "content": "recent 2"},
        {"role": "assistant", "content": [{"type": "text", "text": "recent reply 2"}]},
        {"role": "user", "content": "recent 3"},
        {"role": "assistant", "content": [{"type": "text", "text": "recent reply 3"}]},
        {"role": "user", "content": "recent 4"},
        {"role": "assistant", "content": [{"type": "text", "text": "recent reply 4"}]},
    ]
    client = PipelineClient(
        parent_turns=[ModelTurn("Done.", input_tokens=10, output_tokens=5)],
        by_type={"compactor": [ModelTurn("folded head summary", input_tokens=10, output_tokens=5)]},
    )
    run_live_task(tmp_path, "finish", recorder, client=client, history=history)  # type: ignore[arg-type]
    assert any(e["kind"] == "context_compaction" and e.get("reason") == "auto" for e in read_events(recorder.path))


def test_compactor_budget_recorded(tmp_path: Path) -> None:
    from vg_agent.agent import _compact_if_needed

    write_fixture(tmp_path)
    recorder = TraceRecorder(tmp_path)
    guard = BudgetGuard()
    recorder.emit(
        "tool_result",
        tool="read_file",
        tool_use_id="budget-read",
        result_full="x" * 50000,
        bytes=50000,
        tokens=9000,
        status="ok",
    )
    event = recorder.events[-1]
    client = PipelineClient(
        [],
        by_type={
            "compactor": [
                ModelTurn(
                    "SAMPLE_LOG_SUMMARY_SENTINEL: budgeted compactor call.",
                    input_tokens=120,
                    output_tokens=60,
                )
            ],
        },
    )
    _compact_if_needed(
        recorder,
        event,
        client=client,
        guard=guard,
        tool="read_file",
        deterministic=False,
    )
    assert guard.per_agent_type_model_calls.get("compactor") == 1
    assert guard.per_agent_type_tokens.get("compactor", 0) > 0
    assert any(
        e["kind"] == "llm_start" and e.get("agent_type") == "compactor"
        for e in recorder.events
    )


def test_manual_compact_proceeds_below_threshold() -> None:
    from vg_agent.agent import conversation_compact_skip_reason

    # Manual /compact is an explicit request: it folds on demand even when the
    # context is far below the auto-fold token threshold.
    messages: list[dict[str, object]] = []
    for index in range(6):
        messages.append({"role": "user", "content": f"question {index}"})
        messages.append({"role": "assistant", "content": f"answer {index}"})
    assert conversation_compact_skip_reason(messages, config.PARENT_MODEL_ID) is None


def test_manual_compact_proceeds_with_two_user_turns() -> None:
    from vg_agent.agent import conversation_compact_skip_reason

    # Two user turns is enough to fold one older turn while keeping the latest verbatim.
    messages: list[dict[str, object]] = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "ack first"},
        {"role": "user", "content": "second"},
    ]
    assert conversation_compact_skip_reason(messages, config.PARENT_MODEL_ID) is None


def test_manual_compact_skip_warning_too_few_turns() -> None:
    from vg_agent.agent import conversation_compact_skip_reason, format_manual_compact_skip_warning

    messages = [{"role": "user", "content": "only one turn"}]
    reason = conversation_compact_skip_reason(messages, config.PARENT_MODEL_ID)
    assert reason == "too_few_user_turns"
    warning = format_manual_compact_skip_warning(reason, messages, config.PARENT_MODEL_ID)
    assert "only 1 user turn" in warning
    assert "at least 2" in warning


def test_chat_slash_compact_warns_when_unnecessary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from vg_agent import __main__ as cli

    write_fixture(tmp_path)
    prompts = iter(["/compact", "/exit"])
    monkeypatch.setattr(cli, "use_rich_ui", lambda: False)
    monkeypatch.setattr(cli, "_make_chat_prompt", lambda _history_path: (lambda: next(prompts), lambda: None))
    monkeypatch.setattr(cli, "LiveModelClient", SimpleNamespace(from_env=lambda recorder=None: object()))

    args = SimpleNamespace(no_redact=False, require_approval="off", yes=False, live_model=True)
    assert cli._chat_loop(tmp_path, args) == 0
    out = capsys.readouterr().out
    assert "/compact skipped" in out
    assert "no conversation history" in out


def test_chat_slash_compact_emits_manual_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from vg_agent import __main__ as cli

    monkeypatch.setitem(config.CONTEXT_WINDOW_TOKENS, config.PARENT_MODEL_ID, 5000)
    monkeypatch.setitem(config.AUTO_COMPACT_FRACTION, config.PARENT_MODEL_ID, 0.5)
    write_fixture(tmp_path)
    prompts = iter(["seed turn", "/compact", "/exit"])
    compactor_client = PipelineClient(
        [],
        by_type={
            "compactor": [
                ModelTurn(
                    "CONVERSATION FOLD: prior turns summarised for parent.",
                    input_tokens=80,
                    output_tokens=40,
                )
            ],
        },
    )

    def fake_run_live_task(
        root: Path,
        prompt: str,
        recorder: TraceRecorder,
        *,
        client: object,
        guard: BudgetGuard,
        policy: ApprovalPolicy,
        history: list[dict[str, object]],
    ) -> TraceRecorder:
        for index in range(6):
            history.append({"role": "user", "content": f"{prompt} question {index} " + ("word " * 400)})
            history.append(
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": f"answer {index} " + ("detail " * 400)}],
                }
            )
        recorder.emit("user_prompt", prompt=prompt)
        recorder.emit(
            "assistant_step",
            agent_id="parent",
            step_idx=1,
            assistant_text=f"ack {prompt}",
            tool_calls=[],
            stop_reason="end_turn",
        )
        recorder.emit("run_end", final_status="ok", total_tokens=0, total_cost_usd=0.0, duration_s=0.1)
        return recorder

    monkeypatch.setattr(cli, "use_rich_ui", lambda: False)
    monkeypatch.setattr(cli, "_make_chat_prompt", lambda _history_path: (lambda: next(prompts), lambda: None))
    monkeypatch.setattr(cli, "LiveModelClient", SimpleNamespace(from_env=lambda recorder=None: compactor_client))
    monkeypatch.setattr(cli, "run_live_task", fake_run_live_task)

    args = SimpleNamespace(no_redact=False, require_approval="off", yes=False, live_model=True)
    assert cli._chat_loop(tmp_path, args) == 0

    events = read_events(next(iter((tmp_path / "traces").glob("*.jsonl"))))
    manual = [e for e in events if e["kind"] == "context_compaction" and e.get("reason") == "manual"]
    assert manual
    assert "CONVERSATION FOLD" in str(manual[0].get("summary") or "")


def test_parent_compaction_and_subagent_context(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "read data/sample.log then summarise auth", recorder, client=_log_then_explorer_client())
    events = read_events(recorder.path)

    parent_large_results = [
        e for e in events
        if e["kind"] == "tool_result"
        and e["agent_id"] == "parent"
        and int(e["tokens"]) > config.K_COMPACT
    ]
    assert parent_large_results
    original = parent_large_results[0]

    compactions = [
        e for e in events
        if e["kind"] == "compaction"
        and e["agent_id"] == "parent"
        and e["tool_use_id"] == original["tool_use_id"]
    ]
    assert compactions
    compaction = compactions[0]
    assert "SAMPLE_LOG_SUMMARY_SENTINEL" in str(compaction.get("summary") or "")
    assert compaction.get("compactor_model") == config.COMPACTOR_MODEL_ID
    assert compaction["original_event_idx"] == original["event_idx"]
    expected_hash = hashlib.sha256(str(original["result_full"]).encode("utf-8")).hexdigest()
    assert compaction["original_sha256"] == expected_hash

    final_step = max(
        int(e["step_idx"]) for e in events
        if e["kind"] == "assistant_step" and e["agent_id"] == "parent"
    )
    context_text = json.dumps(show_context(events, final_step))
    # Compacted parent read is a marker, not the raw log; the Explorer summary is present.
    assert "[COMPACTED tool_result for tool_use_id=parent-read-sample-log]" in context_text
    assert "req-00001" not in context_text
    assert "SENTINEL_AUTH" in context_text


def test_resolve_workspace_root_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "workspace").mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("VG_WORKSPACE_ROOT", raising=False)
    from vg_agent.workspace_paths import resolve_workspace_root

    assert resolve_workspace_root() == (tmp_path / "workspace").resolve()


def test_resolve_workspace_root_docker_compose_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Compose uses working_dir=/workspace and VG_WORKSPACE_ROOT=."""
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True)
    monkeypatch.chdir(ws)
    monkeypatch.setenv("VG_WORKSPACE_ROOT", ".")
    from vg_agent.workspace_paths import resolve_workspace_root

    assert resolve_workspace_root() == ws.resolve()


def test_trace_recorder_uses_resolved_workspace_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VG_WORKSPACE_ROOT", "workspace")
    (tmp_path / "workspace").mkdir(parents=True, exist_ok=True)
    from vg_agent.workspace_paths import resolve_workspace_root
    from vg_agent.trace import TraceRecorder

    root = resolve_workspace_root()
    recorder = TraceRecorder(root)
    recorder.emit("user_prompt", prompt="workspace trace path")
    assert recorder.path.parent == root / "traces"
    assert (root / config.SQLITE_TRACE_DB).is_file()


def test_sqlite_trace_mirror_and_dashboard_rollups(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    recorder = TraceRecorder(tmp_path)
    task = "read data/sample.log then summarise auth"
    run_live_task(tmp_path, task, recorder, client=_log_then_explorer_client())
    db_path = tmp_path / config.SQLITE_TRACE_DB
    assert db_path.exists()

    with sqlite3.connect(db_path) as conn:
        event_rows = conn.execute(
            "SELECT event_idx, payload_json FROM events WHERE run_id = ? ORDER BY event_idx",
            (recorder.run_id,),
        ).fetchall()
        assert len(event_rows) == len(recorder.events)
        mirrored = [json.loads(row[1]) for row in event_rows]
        assert mirrored == recorder.events

        turns = conn.execute(
            "SELECT prompt, status, total_tokens, total_model_calls, total_tool_calls, duration_ms FROM turns WHERE run_id = ?",
            (recorder.run_id,),
        ).fetchall()
        assert len(turns) == 1
        assert turns[0][0] == task
        assert turns[0][1] == "ok"
        assert int(turns[0][2]) > 0
        assert int(turns[0][3]) > 0
        assert int(turns[0][4]) > 0
        assert int(turns[0][5]) >= 0

        assert conn.execute("SELECT COUNT(*) FROM model_calls WHERE run_id = ?", (recorder.run_id,)).fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM tool_calls WHERE run_id = ?", (recorder.run_id,)).fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM subagents WHERE run_id = ?", (recorder.run_id,)).fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM compactions WHERE run_id = ?", (recorder.run_id,)).fetchone()[0] > 0


def test_run_bash_rejects_dangerous_commands(tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me", encoding="utf-8")

    assert validate_shell_command("grep -R keep .") is None
    assert validate_shell_command("rm -rf .") is not None
    assert validate_shell_command("grep -R keep .; rm -rf .") is not None
    assert validate_shell_command("grep keep victim.txt > out.txt") is not None
    assert validate_shell_command('ls -l | grep "^d"') is not None
    assert validate_shell_command("Remove-Item victim.txt") is not None
    assert validate_shell_command("sed -i 's/a/b/' foo") is not None
    assert validate_shell_command("find . -delete") is not None
    assert validate_shell_command("find . -maxdepth 1 -type d") is None
    assert validate_shell_command("git fetch origin") is not None
    assert validate_shell_command("ssh user@host ls") is not None
    assert validate_shell_command("cat README.md") is None
    assert validate_shell_command("head README.md") is None
    assert validate_shell_command("rg keep README.md") is None
    assert validate_shell_command("cat .env") is not None
    assert validate_shell_command("head .env") is not None
    assert validate_shell_command("rg OPENROUTER_API_KEY .env") is not None
    assert validate_shell_command("cat foo/.env") is not None
    assert validate_shell_command("cat .ssh/id_ed25519") is not None
    assert validate_shell_command("cat .aws/credentials") is not None
    assert validate_shell_command("cat .vg_daily_spend.json") is not None
    assert validate_shell_command("cat secrets/private.key") is not None

    result = run_bash(tmp_path, "rm -rf .", "unsafe-rm")
    assert result["status"] == "error"
    assert "run_bash blocked" in str(result["result_full"])
    assert victim.exists()

    delete_me = tmp_path / "delete-me.txt"
    delete_me.write_text("remove me", encoding="utf-8")
    assert validate_shell_command("rm delete-me.txt") is None
    result = run_bash(tmp_path, "rm delete-me.txt", "safe-rm")
    assert result["status"] == "ok"
    assert not delete_me.exists()

    folder = tmp_path / "folder"
    folder.mkdir()
    list_dirs = run_bash(tmp_path, "find . -maxdepth 1 -type d", "list-dirs")
    assert list_dirs["status"] == "ok"
    assert "./folder" in str(list_dirs["result_full"])

    result = run_bash(tmp_path, "rm folder", "dir-rm")
    assert result["status"] == "error"
    assert "regular files" in str(result["result_full"])
    assert folder.exists()

    assert validate_shell_command("mkdir -p tkinter_calc") is None
    assert validate_shell_command("mkdir -m 700 secret") is not None
    assert validate_shell_command("mkdir -p ../outside") is not None
    assert validate_shell_command("mkdir -p .env") is not None

    nested = tmp_path / "tkinter_calc"
    assert not nested.exists()
    result = run_bash(tmp_path, "mkdir -p tkinter_calc", "safe-mkdir")
    assert result["status"] == "ok"
    assert nested.is_dir()

    result = run_bash(tmp_path, "mkdir tkinter_calc", "existing-mkdir")
    assert result["status"] == "ok"
    assert "directory already exists" in str(result["result_full"])
    result = run_bash(tmp_path, "mkdir -p tkinter_calc", "existing-mkdir-p")
    assert result["status"] == "ok"
    assert "directory already exists" in str(result["result_full"])

    assert validate_shell_command("mkdir -p /tmp/outside-mkdir-test") is not None


def test_run_bash_py_compile_strict_allowlist(tmp_path: Path) -> None:
    target = tmp_path / "module_ok.py"
    target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    another = tmp_path / "another.py"
    another.write_text("def sub(a, b):\n    return a - b\n", encoding="utf-8")

    allowed = "python3 -m py_compile module_ok.py"
    assert validate_shell_command(allowed) is None
    assert validate_shell_command_for_workspace(tmp_path, allowed) is None
    ok = run_bash(tmp_path, allowed, "py-compile-ok")
    assert ok["status"] == "ok"
    assert "__pycache__" not in str(ok["result_full"])

    multi = "python3 -m py_compile module_ok.py another.py"
    assert validate_shell_command(multi) is None
    assert validate_shell_command_for_workspace(tmp_path, multi) is None
    multi_ok = run_bash(tmp_path, multi, "py-compile-multi")
    assert multi_ok["status"] == "ok"

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "main.py").write_text("def main():\n    return 0\n", encoding="utf-8")
    pkg_multi = "python3 -m py_compile pkg/__init__.py pkg/main.py"
    assert validate_shell_command(pkg_multi) is None
    assert validate_shell_command_for_workspace(tmp_path, pkg_multi) is None

    assert validate_shell_command("python3 module_ok.py") is not None
    assert "py_compile" in (validate_shell_command("python3 module_ok.py") or "")
    assert validate_shell_command("python3 -c 'print(1)'") is not None
    assert validate_shell_command("python3 -m pytest module_ok.py") is not None
    assert validate_shell_command("python3 -m py_compile module_ok.py && ls") is not None
    assert validate_shell_command("python3 -m py_compile ../outside.py") is not None
    assert validate_shell_command("python3 -m py_compile /tmp/abs.py") is not None
    assert validate_shell_command("python3 -m py_compile module_ok.py not_py.txt") is not None

    over_cap = "python3 -m py_compile " + " ".join(f"f{i}.py" for i in range(9))
    over_cap_err = validate_shell_command(over_cap)
    assert over_cap_err is not None
    assert "at most 8" in over_cap_err

    missing = validate_shell_command_for_workspace(tmp_path, "python3 -m py_compile missing.py")
    assert missing is not None
    assert "does not exist" in missing

    not_file = tmp_path / "pkgdir"
    not_file.mkdir()
    not_regular = validate_shell_command_for_workspace(tmp_path, "python3 -m py_compile pkgdir")
    assert not_regular is not None

    sensitive = validate_shell_command_for_workspace(tmp_path, "python3 -m py_compile .env")
    assert sensitive is not None
    assert "sensitive path" in sensitive


def test_live_model_cli_requires_openrouter_key(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("OPENROUTER_API_KEY", None)
    env["PYTHONPATH"] = str(ROOT / "src")
    completed = subprocess.run(
        [sys.executable, "-m", "vg_agent", "--task", "inspect", "--live-model"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 2
    assert "OPENROUTER_API_KEY is required" in completed.stderr


def test_file_tools_reject_path_traversal(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-vg-agent-test.txt"
    outside.write_text("keep", encoding="utf-8")
    try:
        assert read_file(tmp_path, "../outside-vg-agent-test.txt", "read-escape")["status"] == "error"
        assert write_file(tmp_path, "../outside-vg-agent-test.txt", "bad", "write-escape")["status"] == "error"
        assert edit_file(tmp_path, "../outside-vg-agent-test.txt", "keep", "bad", "edit-escape")["status"] == "error"
        assert outside.read_text(encoding="utf-8") == "keep"
        assert validate_shell_command("cat ../outside-vg-agent-test.txt") is not None
    finally:
        outside.unlink(missing_ok=True)

    # sensitive-path denylist
    (tmp_path / ".env").write_text("SECRET=abc", encoding="utf-8")
    (tmp_path / ".env.example").write_text("SECRET=", encoding="utf-8")
    (tmp_path / "secrets").mkdir(exist_ok=True)
    (tmp_path / "secrets" / "id_rsa").write_text("private", encoding="utf-8")
    (tmp_path / "app.pem").write_text("cert", encoding="utf-8")
    (tmp_path / ".aws").mkdir(exist_ok=True)
    (tmp_path / ".aws" / "credentials").write_text("creds", encoding="utf-8")

    assert read_file(tmp_path, ".env", "r1")["status"] == "error"
    env_error = str(read_file(tmp_path, ".env", "r1")["result_full"])
    assert "sensitive path" in env_error
    assert ".env.example" in env_error
    assert read_file(tmp_path, "secrets/id_rsa", "r2")["status"] == "error"
    assert read_file(tmp_path, "app.pem", "r3")["status"] == "error"
    assert read_file(tmp_path, ".aws/credentials", "r4")["status"] == "error"
    assert write_file(tmp_path, ".env", "x", "w1")["status"] == "error"
    assert edit_file(tmp_path, ".env", "SECRET=abc", "EVIL=", "e1")["status"] == "error"
    # .env.example is allowed
    ok = read_file(tmp_path, ".env.example", "ok")
    assert ok["status"] == "ok"


def test_file_tools_reject_empty_path(tmp_path: Path) -> None:
    # An empty path must not silently resolve to (and clobber) the workspace
    # root. Before the fix this raised an opaque "[Errno 21] Is a directory"
    # that the model could not recover from, causing a write/retry loop.
    result = write_file(tmp_path, "", "x = 1\n", "w-empty")
    assert result["status"] == "error"
    message = str(result["result_full"])
    assert "empty path" in message
    assert "Is a directory" not in message
    # The root was not turned into a file.
    assert tmp_path.is_dir()

    assert write_file(tmp_path, "   ", "x", "w-blank")["status"] == "error"
    assert read_file(tmp_path, "", "r-empty")["status"] == "error"
    assert edit_file(tmp_path, "", "a", "b", "e-empty")["status"] == "error"

    # A real nested path still works and creates the parent folder.
    ok = write_file(tmp_path, "tkinter_calc2/calculator.py", "print('ok')\n", "w-ok")
    assert ok["status"] == "ok"
    assert (tmp_path / "tkinter_calc2" / "calculator.py").read_text(encoding="utf-8") == "print('ok')\n"


def test_tool_path_accepts_common_aliases() -> None:
    assert _tool_path({"path": "a.py"}) == "a.py"
    assert _tool_path({"rel_path": "b.py"}) == "b.py"
    # Models sometimes use file_path / filename instead of path.
    assert _tool_path({"file_path": "tkinter_calc2/calc.py"}) == "tkinter_calc2/calc.py"
    assert _tool_path({"filename": "main.py"}) == "main.py"
    # path wins over aliases when several are present.
    assert _tool_path({"path": "a.py", "file_path": "b.py"}) == "a.py"
    assert _tool_path({"content": "x"}) == ""


def test_edit_file_reports_replacement_count(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("foo = 1\nprint(foo)\n", encoding="utf-8")
    result = edit_file(tmp_path, "app.py", "foo", "bar", "edit-count")
    assert result["status"] == "ok"
    assert "replaced 2 occurrence(s)" in str(result["result_full"])
    assert target.read_text(encoding="utf-8") == "bar = 1\nprint(bar)\n"


def test_live_loop_budget_abort_before_client_call(tmp_path: Path) -> None:
    client = FakeClient([])
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "do work", recorder, client=client, guard=BudgetGuard(max_steps=0))
    events = read_events(recorder.path)
    assert client.calls == []
    assert events[-2]["kind"] == "budget_event"
    assert events[-2]["budget_reason"] == "step_cap"
    assert events[-1]["final_status"] == "aborted"


def test_parent_step_cap_ignores_subagent_model_calls(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "spawn coder",
                [ToolCall("spawn-coder", "spawn_subagent", {"type": "coder", "question": "create app.py"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("done", input_tokens=100, output_tokens=20),
        ],
        by_type={
            "coder": [
                ModelTurn(
                    "read context",
                    [ToolCall("r1", "read_file", {"path": "README.md"})],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn(
                    "write file",
                    [ToolCall("w1", "write_file", {"path": "app.py", "content": "x = 1\n"})],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn("app.py: created file", input_tokens=40, output_tokens=10),
            ]
        },
    )
    recorder = TraceRecorder(tmp_path)
    guard = BudgetGuard(max_steps=2)
    run_live_task(tmp_path, "create app.py", recorder, client=client, guard=guard)
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "x = 1\n"
    assert guard.parent_step_count == 2
    assert guard.step_count > guard.parent_step_count


def test_cli_exit_code_for_final_status() -> None:
    from vg_agent.__main__ import _exit_code_for_final_status

    assert _exit_code_for_final_status("aborted") == 3
    assert _exit_code_for_final_status("model_error") == 75
    assert _exit_code_for_final_status("ok") == 0
    assert _exit_code_for_final_status(None) == 0


def test_live_loop_budget_cap_approval_extends_steps(tmp_path: Path) -> None:
    client = FakeClient(
        [
            ModelTurn("done", input_tokens=10, output_tokens=5),
        ]
    )
    recorder = TraceRecorder(tmp_path)

    def approve_once(request: ApprovalRequest) -> ApprovalOutcome:
        assert request.tool == "budget_cap"
        assert request.path == "step_cap"
        return ApprovalOutcome(decision="approved", reason="test yes")

    policy = ApprovalPolicy(mode="writes", prompt=approve_once)
    guard = BudgetGuard(max_steps=0)
    run_live_task(tmp_path, "do work", recorder, client=client, guard=guard, policy=policy)
    events = read_events(recorder.path)
    assert len(client.calls) == 1
    approvals = [e for e in events if e.get("kind") == "approval" and e.get("tool") == "budget_cap"]
    assert len(approvals) == 1
    assert approvals[0]["decision"] == "approved"
    assert events[-1]["final_status"] == "ok"


def test_proactive_step_extend_at_last_step(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    client = FakeClient(
        [
            ModelTurn(
                "",
                [ToolCall("t1", "read_file", {"path": "README.md"})],
                stop_reason="tool_use",
                input_tokens=10,
                output_tokens=5,
            ),
            ModelTurn(
                "",
                [ToolCall("t2", "read_file", {"path": "utils.py"})],
                stop_reason="tool_use",
                input_tokens=10,
                output_tokens=5,
            ),
            ModelTurn("done", input_tokens=10, output_tokens=5),
        ]
    )
    recorder = TraceRecorder(tmp_path)

    def approve(request: ApprovalRequest) -> ApprovalOutcome:
        if request.tool == "budget_cap" and request.path == "step_extend":
            return ApprovalOutcome(decision="approved_scoped", scope_key="step_extend", reason="extend")
        return ApprovalOutcome(decision="approved", reason="yes")

    policy = ApprovalPolicy(mode="writes", prompt=approve)
    guard = BudgetGuard(max_steps=2)
    run_live_task(tmp_path, "work", recorder, client=client, guard=guard, policy=policy)
    events = read_events(recorder.path)
    assert len(client.calls) == 3
    extend_approvals = [
        e
        for e in events
        if e.get("kind") == "approval" and e.get("tool") == "budget_cap" and e.get("budget_reason") == "step_extend"
    ]
    assert len(extend_approvals) == 1
    assert events[-1]["final_status"] == "ok"


def test_proactive_step_extend_deny_then_hard_cap(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    client = FakeClient(
        [
            ModelTurn(
                "",
                [ToolCall("t1", "read_file", {"path": "README.md"})],
                stop_reason="tool_use",
                input_tokens=10,
                output_tokens=5,
            ),
            ModelTurn(
                "",
                [ToolCall("t2", "read_file", {"path": "utils.py"})],
                stop_reason="tool_use",
                input_tokens=10,
                output_tokens=5,
            ),
            ModelTurn("three", input_tokens=10, output_tokens=5),
        ]
    )
    recorder = TraceRecorder(tmp_path)

    def approve(request: ApprovalRequest) -> ApprovalOutcome:
        return ApprovalOutcome(decision="denied", reason="no")

    policy = ApprovalPolicy(mode="writes", prompt=approve)
    guard = BudgetGuard(max_steps=2)
    run_live_task(tmp_path, "work", recorder, client=client, guard=guard, policy=policy)
    events = read_events(recorder.path)
    assert len(client.calls) == 2
    assert events[-1]["final_status"] == "aborted"
    reasons = [e.get("budget_reason") for e in events if e.get("kind") == "approval"]
    assert "step_extend" in reasons
    assert "step_cap" in reasons


def test_budget_cap_approval_step_copy() -> None:
    from vg_agent.chat_ui import format_budget_cap_approval_text

    body = format_budget_cap_approval_text("step_cap", {"step_count": 14, "max_steps": 15})
    assert "14/15" in body
    assert "Cap (--max-usd)" not in body
    assert "step cap" in body.lower() or "Step cap" in body


def test_budget_cap_choice_2_scoped_scope_key_is_reason() -> None:
    from vg_agent.chat_ui import _parse_approval_choice

    req = SimpleNamespace(tool="budget_cap", path="token_cap", args={}, summary="")
    outcome = _parse_approval_choice("2", req)
    assert outcome.decision == "approved_scoped"
    assert outcome.scope_key == "token_cap"


def test_sanitize_summary_text_flattens_newlines() -> None:
    from vg_agent.chat_ui import sanitize_summary_text

    assert sanitize_summary_text("a\nb\r\nc") == "a ↵ b ↵ c"
    assert sanitize_summary_text("hello", limit=3) == "hel"


def test_args_summary_spawn_subagent_single_line() -> None:
    from vg_agent.agent import _args_summary

    summary = _args_summary("spawn_subagent", {"question": "Edit only\n\nEngine API"})
    assert "\n" not in summary
    assert "↵" in summary


def test_args_summary_file_tools_never_blank() -> None:
    from vg_agent.agent import _args_summary

    # A write with a path shows the path plus content size.
    summary = _args_summary("write_file", {"path": "calc/main.py", "content": "x = 1\n"})
    assert "calc/main.py" in summary
    assert "6 chars" in summary

    # A missing path must never render as an empty approval line.
    blank = _args_summary("write_file", {"content": "x = 1\n"})
    assert blank.strip() != ""
    assert "<missing path>" in blank


def test_use_rich_approval_ui_latched_when_stderr_not_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    from vg_agent import chat_ui

    chat_ui.reset_rich_chat_latch()
    monkeypatch.delenv("NO_COLOR", raising=False)

    def stdin_tty() -> bool:
        return True

    def stderr_tty() -> bool:
        return False

    monkeypatch.setattr(sys.stdin, "isatty", stdin_tty)
    monkeypatch.setattr(sys.stderr, "isatty", stderr_tty)
    assert chat_ui.use_rich_ui() is False

    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    chat_ui.latch_rich_chat_session()
    monkeypatch.setattr(sys.stderr, "isatty", stderr_tty)
    assert chat_ui.use_rich_approval_ui() is True
    chat_ui.reset_rich_chat_latch()


def test_use_rich_ui_latched_when_stderr_temporarily_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    from vg_agent import chat_ui

    chat_ui.reset_rich_chat_latch()
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)

    chat_ui.latch_rich_chat_session()
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)

    assert chat_ui.use_latched_rich_ui() is True
    assert chat_ui.use_rich_ui() is True
    chat_ui.reset_rich_chat_latch()


def test_litellm_noise_filter_delegates_tty_stream_attributes() -> None:
    import io

    from vg_agent.live_model_client import _LiteLLMNoiseFilter

    class FakeTTY(io.StringIO):
        encoding = "utf-8"
        errors = "strict"

        def isatty(self) -> bool:
            return True

        def fileno(self) -> int:
            return 42

        def custom_attr(self) -> str:
            return "delegated"

    wrapped = FakeTTY()
    filtered = _LiteLLMNoiseFilter(wrapped)

    assert filtered.isatty() is True
    assert filtered.fileno() == 42
    assert filtered.encoding == "utf-8"
    assert filtered.errors == "strict"
    assert filtered.writable() is True
    assert filtered.custom_attr() == "delegated"


def test_prompt_approval_rich_spawn_no_plain_pre_decision_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import io

    from vg_agent import chat_ui
    from vg_agent.agent import ApprovalRequest

    chat_ui.reset_rich_chat_latch()
    chat_ui.latch_rich_chat_session()
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(chat_ui, "use_rich_approval_ui", lambda: True)

    stderr_buf = io.StringIO()

    class FakeStderr(io.StringIO):
        def isatty(self) -> bool:
            return True

    fake_stderr = FakeStderr()
    monkeypatch.setattr(sys, "stderr", fake_stderr)

    class FakeStdin:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            return "2\n"

    monkeypatch.setattr(sys, "stdin", FakeStdin())

    question = "Edit only `main.py`\n\nEngine API:\n- `Cal"
    req = ApprovalRequest(
        tool="spawn_subagent",
        path=None,
        args={"question": question},
        summary=question,
    )
    outcome = chat_ui.prompt_approval(req, input_stream=FakeStdin(), workspace_root=tmp_path)
    err = fake_stderr.getvalue()
    assert outcome.decision == "approved_scoped"
    assert "yes (this folder)" not in err
    assert "[approval] spawn_subagent  Edit" not in err
    assert "Approve spawn_subagent" in err or "yes (scoped)" in err


def test_budget_cap_scope_cache_avoids_re_prompt_for_same_reason() -> None:
    prompt_calls = 0

    def approve(req: ApprovalRequest) -> ApprovalOutcome:
        nonlocal prompt_calls
        prompt_calls += 1
        assert req.tool == "budget_cap"
        assert req.path == "token_cap"
        return ApprovalOutcome(decision="approved_scoped", scope_key=str(req.path), reason="test grant")

    policy = ApprovalPolicy(mode="writes", prompt=approve)
    details = {"tokens": 79_000, "max_tokens": 80_000}
    summary = "token_cap test"

    out1 = policy.check_budget_cap("token_cap", details, summary)
    out2 = policy.check_budget_cap("token_cap", details, summary)

    assert out1.decision == "approved_scoped"
    assert out1.scope_key == "token_cap"
    assert out2.decision == "approved_scoped"
    assert out2.scope_key == "token_cap"
    assert out2.reason == "budget scope cache hit"
    assert prompt_calls == 1


def test_budget_cap_token_prompt_shows_bump_and_new_maxes() -> None:
    from vg_agent.chat_ui import format_budget_cap_approval_text

    tokens = 79_000
    max_tokens = 80_000
    bump = max(10_000, max_tokens // 4)
    new_once = tokens + bump
    new_scoped = max_tokens + bump

    body = format_budget_cap_approval_text(
        "token_cap",
        {
            "tokens": tokens,
            "max_tokens": max_tokens,
        },
    )

    assert f"Bump:                ~{bump:,} tokens" in body
    assert f"1/y (one-time) max: ~{new_once:,}" in body
    assert f"2/3 (this cap) max: ~{new_scoped:,}" in body


def test_sqlite_mirror_survives_parallel_subagents(tmp_path: Path) -> None:
    import sqlite3

    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "parallel",
                [
                    ToolCall(
                        "spawn-many",
                        "spawn_subagents",
                        {
                            "requests": [
                                {"type": "explorer", "question": "inspect app.py SENTINEL_APP"},
                                {"type": "explorer", "question": "inspect utils.py SENTINEL_UTILS"},
                            ]
                        },
                    )
                ],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=40,
            ),
            ModelTurn("done", input_tokens=100, output_tokens=20),
        ],
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "parallel explore", recorder, client=client)
    assert recorder.sqlite_store is not None
    db_path = tmp_path / "traces" / "vg_agent.sqlite3"
    assert db_path.is_file()
    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM subagents WHERE run_id = ?",
            (recorder.run_id,),
        ).fetchone()[0]
    assert int(count) >= 2


def test_parent_has_no_write_tools_and_coder_is_sole_mutation_path(tmp_path: Path) -> None:
    # VG.6 / architecture: the parent tool schema never exposes write/edit; all
    # mutation flows through a Coder sub-agent.
    names = {schema["name"] for schema in PARENT_TOOL_SCHEMAS}
    assert "write_file" not in names and "edit_file" not in names
    assert {"spawn_subagent", "spawn_subagents"} <= names
    prompt_tool_block = PARENT_SYSTEM_PROMPT.split("Pipeline guidance", 1)[0]
    assert "write_file" not in prompt_tool_block
    assert "edit_file" not in prompt_tool_block
    assert "spawn a Coder sub-agent" in PARENT_SYSTEM_PROMPT

    write_fixture(tmp_path)
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "Inspect then delegate the edit to a Coder.",
                [ToolCall("read-app", "read_file", {"path": "app.py"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn(
                "Delegate the rename to a Coder sub-agent.",
                [ToolCall("spawn-coder", "spawn_subagent", {"type": "coder", "question": "rename foo to baz in app.py"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("Coder renamed foo to baz in app.py.", input_tokens=100, output_tokens=20),
        ],
        by_type={
            "coder": [
                ModelTurn(
                    "Applying the minimal edit.",
                    [ToolCall("coder-edit", "edit_file", {"path": "app.py", "old": "foo", "new": "baz"})],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn("app.py: renamed foo to baz", input_tokens=40, output_tokens=10),
            ],
        },
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "rename foo to baz in app.py", recorder, client=client)
    assert "def baz(" in (tmp_path / "app.py").read_text(encoding="utf-8")
    events = read_events(recorder.path)
    coder_spawn = next(e for e in events if e["kind"] == "subagent_spawn" and e["agent_type"] == "coder")
    edit_results = [e for e in events if e["kind"] == "tool_result" and e["tool"] == "edit_file"]
    assert edit_results and edit_results[0]["agent_id"] == coder_spawn["child_agent_id"]
    assert events[-1]["final_status"] == "ok"


def test_parent_prompt_requires_reviewer_after_every_coder_write() -> None:
    # Reviewer now runs after every Coder that wrote a file, greenfield
    # creation included (no longer exempt). Guard the prompt intent so the
    # behavior cannot silently regress to "greenfield skips Reviewer".
    pipeline = PARENT_SYSTEM_PROMPT.split("Pipeline guidance", 1)[-1]
    assert "writes_ok > 0" in pipeline
    assert "greenfield creation included" in pipeline
    assert "does not require a Reviewer" not in pipeline.replace("\n", " ")


def test_coder_subagent_recovers_after_tool_error(tmp_path: Path) -> None:
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "Create the file via Coder.",
                [ToolCall("spawn-coder", "spawn_subagent", {"type": "coder", "question": "create tkinter_calc/calc.py"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("Created tkinter_calc/calc.py.", input_tokens=100, output_tokens=20),
        ],
        by_type={
            "coder": [
                ModelTurn(
                    "Try edit first.",
                    [ToolCall("coder-edit", "edit_file", {"path": "tkinter_calc/calc.py", "old": "missing", "new": "x"})],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn(
                    "Write the new file.",
                    [ToolCall("coder-write", "write_file", {"path": "tkinter_calc/calc.py", "content": "x = 1\n"})],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn("tkinter_calc/calc.py: created new file", input_tokens=40, output_tokens=10),
            ],
        },
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "create tkinter_calc/calc.py", recorder, client=client)
    assert (tmp_path / "tkinter_calc" / "calc.py").read_text(encoding="utf-8") == "x = 1\n"
    coder_return = next(event for event in read_events(recorder.path) if event["kind"] == "subagent_return")
    assert coder_return["status"] == "ok"


def test_parent_skips_redundant_greenfield_explorer_readback(tmp_path: Path) -> None:
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "Create the game via Coder.",
                [
                    ToolCall(
                        "spawn-coder",
                        "spawn_subagent",
                        {
                            "type": "coder",
                            "question": "create number_guessing/game.py and number_guessing/README.md, then py_compile game.py",
                        },
                    )
                ],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn(
                "Take a quick look at what was created.",
                [
                    ToolCall(
                        "spawn-readback",
                        "spawn_subagents",
                        {
                            "requests": [
                                {
                                    "type": "explorer",
                                    "question": "Read and return the full contents of `number_guessing/game.py`.",
                                },
                                {
                                    "type": "explorer",
                                    "question": "Read and return the full contents of `number_guessing/README.md`.",
                                },
                            ]
                        },
                    )
                ],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("Done.", input_tokens=100, output_tokens=20),
        ],
        by_type={
            "coder": [
                ModelTurn(
                    "Write game.",
                    [
                        ToolCall(
                            "write-game",
                            "write_file",
                            {
                                "path": "number_guessing/game.py",
                                "content": "def main():\n    print('guess')\n\nif __name__ == '__main__':\n    main()\n",
                            },
                        )
                    ],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn(
                    "Write README.",
                    [
                        ToolCall(
                            "write-readme",
                            "write_file",
                            {"path": "number_guessing/README.md", "content": "# Number Guessing\n"},
                        )
                    ],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn(
                    "Compile.",
                    [
                        ToolCall(
                            "compile",
                            "run_bash",
                            {"command": "python3 -m py_compile number_guessing/game.py"},
                        )
                    ],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn(
                    "number_guessing/game.py and README.md: created; py_compile passed",
                    input_tokens=40,
                    output_tokens=10,
                ),
            ],
        },
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "write a simple game in python in a new subfolder", recorder, client=client)
    events = read_events(recorder.path)

    explorer_spawns = [
        event
        for event in events
        if event.get("kind") == "subagent_spawn" and event.get("agent_type") == "explorer"
    ]
    assert explorer_spawns == []
    skipped = [
        event
        for event in events
        if event.get("kind") == "budget_event"
        and event.get("budget_reason") == "redundant_greenfield_readback_skipped"
    ]
    assert skipped
    readback_result = next(
        event
        for event in events
        if event.get("kind") == "tool_result" and event.get("tool") == "spawn_subagents"
    )
    assert readback_result["status"] == "ok"
    assert "skipped redundant greenfield readback" in str(readback_result["result_full"])


def test_followup_read_after_greenfield_creation_still_runs_explorer(tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    create_client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "Create the file via Coder.",
                [
                    ToolCall(
                        "spawn-coder",
                        "spawn_subagent",
                        {
                            "type": "coder",
                            "question": "create number_guessing/game.py, then py_compile it",
                        },
                    )
                ],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("Done.", input_tokens=100, output_tokens=20),
        ],
        by_type={
            "coder": [
                ModelTurn(
                    "Write game.",
                    [
                        ToolCall(
                            "write-game",
                            "write_file",
                            {
                                "path": "number_guessing/game.py",
                                "content": "print('guess')\n",
                            },
                        )
                    ],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn(
                    "Compile.",
                    [
                        ToolCall(
                            "compile",
                            "run_bash",
                            {"command": "python3 -m py_compile number_guessing/game.py"},
                        )
                    ],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn("number_guessing/game.py: created; py_compile passed", input_tokens=40, output_tokens=10),
            ],
        },
    )
    run_live_task(tmp_path, "write a simple game in python in a new subfolder", recorder, client=create_client)

    read_client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "Read it back for the user.",
                [
                    ToolCall(
                        "spawn-read",
                        "spawn_subagent",
                        {
                            "type": "explorer",
                            "question": "Read and return the full contents of `number_guessing/game.py`.",
                        },
                    )
                ],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("Shown.", input_tokens=100, output_tokens=20),
        ],
    )
    run_live_task(tmp_path, "show number_guessing/game.py", recorder, client=read_client)
    events = read_events(recorder.path)
    explorer_spawns = [
        event
        for event in events
        if event.get("kind") == "subagent_spawn" and event.get("agent_type") == "explorer"
    ]
    assert len(explorer_spawns) == 1


def test_parent_retries_after_subagent_tool_error(tmp_path: Path) -> None:
    fail_turns = [
        ModelTurn(
            f"attempt {index}",
            [ToolCall(f"edit-{index}", "edit_file", {"path": "missing.py", "old": "x", "new": "y"})],
            stop_reason="tool_use",
            input_tokens=60,
            output_tokens=20,
        )
        for index in range(config.MAX_SUBAGENT_STEPS)
    ]
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "spawn coder",
                [ToolCall("spawn-1", "spawn_subagent", {"type": "coder", "question": "edit missing.py"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn(
                "retry coder",
                [ToolCall("spawn-2", "spawn_subagent", {"type": "coder", "question": "write app.py with x=1"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("app.py created.", input_tokens=100, output_tokens=20),
        ],
        by_type={
            "coder": fail_turns
            + [
                ModelTurn(
                    "write file",
                    [ToolCall("write", "write_file", {"path": "app.py", "content": "x = 1\n"})],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn("app.py: created file", input_tokens=40, output_tokens=10),
            ],
        },
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "create app.py", recorder, client=client)
    events = read_events(recorder.path)
    spawns = [event for event in events if event["kind"] == "subagent_spawn" and event["agent_type"] == "coder"]
    assert len(spawns) >= 2
    first_return = next(
        event
        for event in events
        if event["kind"] == "subagent_return" and event["child_agent_id"] == spawns[0]["child_agent_id"]
    )
    assert first_return["status"] == "tool_error"
    assert any(
        e.get("kind") == "budget_event" and e.get("budget_reason") == "coder_constrained_retry"
        for e in events
    )
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "x = 1\n"


def test_coder_retries_truncated_tool_call_instead_of_empty_write(tmp_path: Path) -> None:
    # Simulate the client's fallback when a write_file arguments blob is cut off
    # at the output cap: json.loads fails and args become {"_raw_arguments": ...}.
    # The coder must NOT execute that as an empty-path write; it must retry.
    truncated = ModelTurn(
        "writing calculator",
        [ToolCall("trunc-write", "write_file", {"_raw_arguments": '{"path": "calc/main.py", "content": "import tk'})],
        stop_reason="length",
        input_tokens=60,
        output_tokens=20,
    )
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "spawn coder",
                [ToolCall("spawn-1", "spawn_subagent", {"type": "coder", "question": "create calc/main.py"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("calc/main.py created.", input_tokens=80, output_tokens=20),
        ],
        by_type={
            "coder": [
                truncated,
                ModelTurn(
                    "writing complete file",
                    [ToolCall("good-write", "write_file", {"path": "calc/main.py", "content": "print('ok')\n"})],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn("calc/main.py: created", input_tokens=40, output_tokens=10),
            ],
        },
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "create calc/main.py", recorder, client=client)
    events = read_events(recorder.path)
    # The truncated call triggered a retry rather than an empty-path write error.
    assert any(
        e.get("kind") == "budget_event"
        and e.get("budget_reason") == "subagent_truncated_tool_call_retry"
        for e in events
    )
    # No empty-path write error was emitted for the truncated call.
    assert not any(
        e.get("kind") == "tool_result"
        and e.get("tool_use_id") == "trunc-write"
        and "empty path" in str(e.get("result_full") or "")
        for e in events
    )
    # The complete retry actually wrote the file.
    assert (tmp_path / "calc" / "main.py").read_text(encoding="utf-8") == "print('ok')\n"


def test_parent_auto_constrained_retry_for_actionable_coder_tool_error(tmp_path: Path) -> None:
    (tmp_path / "calc_haiku_2").mkdir(parents=True, exist_ok=True)
    fail_turns = [
        ModelTurn(
            f"bad read {i}",
            [ToolCall(f"bad-read-{i}", "read_file", {"path": "calc_haiku_2"})],
            stop_reason="tool_use",
            input_tokens=60,
            output_tokens=20,
        )
        for i in range(config.MAX_SUBAGENT_STEPS)
    ]
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "spawn coder",
                [ToolCall("spawn-1", "spawn_subagent", {"type": "coder", "question": "Fix import in calc_haiku_2/main.py"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("import fixed", input_tokens=80, output_tokens=20),
        ],
        by_type={
            "coder": fail_turns
            + [
                ModelTurn(
                    "write fixed file",
                    [ToolCall("fix-write", "write_file", {"path": "calc_haiku_2/main.py", "content": "from .calculator import Calculator\n"})],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn("calc_haiku_2/main.py: fixed import", input_tokens=40, output_tokens=10),
            ]
        },
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "fix import", recorder, client=client)
    events = read_events(recorder.path)
    coder_spawns = [e for e in events if e.get("kind") == "subagent_spawn" and e.get("agent_type") == "coder"]
    assert len(coder_spawns) == 2
    assert any(
        e.get("kind") == "budget_event" and e.get("budget_reason") == "coder_constrained_retry"
        for e in events
    )
    spawn_result = next(
        e for e in events if e.get("kind") == "tool_result" and e.get("tool") == "spawn_subagent"
    )
    payload = json.loads(str(spawn_result["result_full"]))
    assert payload["initial"]["status"] == "tool_error"
    assert payload["retry"]["status"] == "ok"
    assert (tmp_path / "calc_haiku_2" / "main.py").exists()


def test_coder_approval_denial_stops_same_turn_retry(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("from auth.middleware import require_auth\n", encoding="utf-8")
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "spawn coder",
                [
                    ToolCall(
                        "spawn-1",
                        "spawn_subagent",
                        {
                            "type": "coder",
                            "question": "prepend a to app.py",
                        },
                    )
                ],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn(
                "should not continue",
                [ToolCall("find-app", "run_bash", {"command": 'find . -maxdepth 2 -name "app.py"'})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
        ],
        by_type={
            "coder": [
                ModelTurn(
                    "try edit",
                    [
                        ToolCall(
                            "edit-1",
                            "edit_file",
                            {
                                "path": "app.py",
                                "old": "from auth.middleware import require_auth",
                                "new": "afrom auth.middleware import require_auth",
                            },
                        )
                    ],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn(
                    "should not fallback",
                    [
                        ToolCall(
                            "write-1",
                            "write_file",
                            {
                                "path": "app.py",
                                "content": "afrom auth.middleware import require_auth\n",
                            },
                        )
                    ],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
            ]
        },
    )

    def approve_spawn_only(request: ApprovalRequest) -> ApprovalOutcome:
        if request.tool == "spawn_subagent":
            return ApprovalOutcome(decision="approved", reason="test approve spawn")
        return ApprovalOutcome(decision="denied", reason="user no")

    recorder = TraceRecorder(tmp_path)
    policy = ApprovalPolicy(mode="writes", prompt=approve_spawn_only)
    run_live_task(tmp_path, "add an a as first character in app.py", recorder, client=client, policy=policy)
    events = read_events(recorder.path)

    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "from auth.middleware import require_auth\n"
    assert len([e for e in events if e.get("kind") == "subagent_spawn" and e.get("agent_type") == "coder"]) == 1
    assert not any(e.get("kind") == "budget_event" and e.get("budget_reason") == "coder_constrained_retry" for e in events)
    assert len(client.parent_turns) == 1
    assert len(client.by_type["coder"]) == 1
    coder_return = next(e for e in events if e.get("kind") == "subagent_return")
    assert coder_return["failure_reason"] == "approval_denied"
    assert events[-1]["kind"] == "run_end"
    assert events[-1]["final_status"] == "tool_error"


def test_parallel_coder_approval_denial_is_not_retried(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "parallel coder + explorer",
                [
                    ToolCall(
                        "spawn-p",
                        "spawn_subagents",
                        {
                            "requests": [
                                {"type": "coder", "question": "change app.py to x = 2"},
                                {"type": "explorer", "question": "inspect app.py"},
                            ]
                        },
                    )
                ],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("should not continue", input_tokens=80, output_tokens=20),
        ],
        by_type={
            "coder": [
                ModelTurn(
                    "try edit",
                    [
                        ToolCall(
                            "edit-1",
                            "edit_file",
                            {"path": "app.py", "old": "x = 1", "new": "x = 2"},
                        )
                    ],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn(
                    "should not retry",
                    [
                        ToolCall(
                            "write-1",
                            "write_file",
                            {"path": "app.py", "content": "x = 2\n"},
                        )
                    ],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
            ]
        },
    )

    def approve_batch_only(request: ApprovalRequest) -> ApprovalOutcome:
        if request.tool == "spawn_subagents":
            return ApprovalOutcome(decision="approved", reason="test approve batch")
        return ApprovalOutcome(decision="denied", reason="user no")

    recorder = TraceRecorder(tmp_path)
    policy = ApprovalPolicy(mode="writes", prompt=approve_batch_only)
    run_live_task(tmp_path, "parallel edit app.py and inspect it", recorder, client=client, policy=policy)
    events = read_events(recorder.path)

    assert (tmp_path / "app.py").read_text(encoding="utf-8") == "x = 1\n"
    assert len([e for e in events if e.get("kind") == "subagent_spawn" and e.get("agent_type") == "coder"]) == 1
    assert not any(e.get("kind") == "budget_event" and e.get("budget_reason") == "coder_constrained_retry" for e in events)
    spawn_result = next(e for e in events if e.get("kind") == "tool_result" and e.get("tool") == "spawn_subagents")
    payload = json.loads(str(spawn_result["result_full"]))
    coder_entry = next(item for item in payload if item.get("agent_type") == "coder")
    assert "retry" not in coder_entry
    assert coder_entry["failure_reason"] == "approval_denied"
    assert events[-1]["kind"] == "run_end"
    assert events[-1]["final_status"] == "tool_error"


def test_trace_event_sink_receives_progress_events(tmp_path: Path) -> None:
    seen: list[dict[str, object]] = []
    recorder = TraceRecorder(tmp_path, event_sink=seen.append)
    recorder.emit("llm_start", model=config.PARENT_MODEL_ID, step_idx=1, tokens_in=10, max_tokens=20)

    from vg_agent.__main__ import _format_progress_event

    assert seen and seen[0]["kind"] == "llm_start"
    assert "[llm] parent step 1" in str(_format_progress_event(seen[0]))


def test_progress_formats_model_error(tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    event = recorder.emit(
        "model_error",
        agent_id="parent",
        step_idx=1,
        message="live model provider rate-limited openrouter/google/gemini-2.0-flash-001. Retry shortly.",
        retryable=True,
    )

    from vg_agent.__main__ import _format_progress_event

    line = str(_format_progress_event(event))
    assert "failed retryable" in line
    assert "rate-limited" in line


def test_live_chat_statusline_shows_context_and_budget(tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    guard = BudgetGuard(max_steps=5, max_tokens=10_000, max_usd=0.5)
    recorder.emit("llm_start", model=config.PARENT_MODEL_ID, step_idx=1, tokens_in=1234, max_tokens=4096)
    guard.record_model_call(config.PARENT_MODEL_ID, 1234, 66)

    from vg_agent.__main__ import _chat_statusline_color, _format_chat_statusline

    line = _format_chat_statusline(recorder, guard, live_model=True, width=200)
    assert "[live]" in line
    assert "ctx 1.2k" in line
    assert "session #---------" in line
    assert "1.3k/10.0k tok" in line
    assert "1/5 steps" in line
    assert "usd $" in line
    assert "tool errs 0" in line
    assert _chat_statusline_color(line, use_color=True).startswith("\x1b[32m[live]")
    assert _chat_statusline_color(line, use_color=True).endswith("\x1b[0m")

    recorder.emit(
        "tool_result",
        tool="read_file",
        tool_use_id="bad-read",
        result_full="sensitive path '.env' is on the read/write denylist",
        status="error",
    )
    error_line = _format_chat_statusline(recorder, guard, live_model=True, width=200)
    assert "tool errs 1" in error_line
    assert _chat_statusline_color(error_line, use_color=True).startswith("\x1b[31m[live]")


def test_chat_slash_command_completer_matches_prefixes() -> None:
    from prompt_toolkit.completion import CompleteEvent
    from prompt_toolkit.document import Document
    from vg_agent.__main__ import SLASH_COMMAND_HELP, SLASH_COMMANDS, _slash_command_completer

    completer = _slash_command_completer()
    all_commands = list(completer.get_completions(Document("/"), CompleteEvent()))
    finops = list(completer.get_completions(Document("/fin"), CompleteEvent()))
    new_session = list(completer.get_completions(Document("/ne"), CompleteEvent()))
    show_context = list(completer.get_completions(Document("/show"), CompleteEvent()))

    assert [completion.text for completion in all_commands] == list(SLASH_COMMANDS)
    assert [completion.text for completion in finops] == ["/finops"]
    assert [completion.text for completion in new_session] == ["/new"]
    assert [completion.text for completion in show_context] == ["/show-context"]
    assert "fresh chat session" in new_session[0].display_meta_text
    assert "Overview" in show_context[0].display_meta_text
    assert len(show_context[0].display_text) > len(show_context[0].text)
    assert list(completer.get_completions(Document(""), CompleteEvent())) == []
    assert list(completer.get_completions(Document(" "), CompleteEvent())) == []
    assert list(completer.get_completions(Document("hello "), CompleteEvent())) == []
    assert list(completer.get_completions(Document("/show-context "), CompleteEvent())) == []
    assert SLASH_COMMAND_HELP.startswith("Slash commands:\n")
    assert "/show-context N" in SLASH_COMMAND_HELP
    assert "Show or set session caps" in SLASH_COMMAND_HELP
    assert "/budget [steps N]" in SLASH_COMMAND_HELP
    assert "Normal text is sent to the agent as the next task." in SLASH_COMMAND_HELP


def test_live_explorer_context_excludes_child_intermediate_results(tmp_path: Path) -> None:
    (tmp_path / "secret.txt").write_text("CHILD_PRIVATE_TOKEN", encoding="utf-8")
    client = FakeClient([
        ModelTurn(
            "Delegating bounded inspection.",
            [ToolCall("spawn-1", "spawn_subagent", {"question": "inspect secret.txt"})],
            stop_reason="tool_use",
            input_tokens=100,
            output_tokens=40,
        ),
        ModelTurn(
            "Reading target.",
            [ToolCall("child-read", "read_file", {"path": "secret.txt"})],
            stop_reason="tool_use",
            input_tokens=50,
            output_tokens=20,
        ),
        ModelTurn("Explorer summary: the requested file was inspected.", input_tokens=60, output_tokens=20),
        ModelTurn("Parent final using Explorer summary.", input_tokens=100, output_tokens=20),
    ])
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "delegate inspection", recorder, client=client)
    events = read_events(recorder.path)
    context_text = json.dumps(show_context(events, 4))
    assert "Explorer summary: the requested file was inspected." in context_text
    assert "CHILD_PRIVATE_TOKEN" not in context_text
    assert "child-read" not in context_text


def test_parallel_explorers_run_concurrently_with_overlap(tmp_path: Path) -> None:
    # VG.1: a single spawn_subagents call runs >=2 explorers with overlapping
    # wall-clock, and the parent consumes both returns.
    names = {schema["name"] for schema in PARENT_TOOL_SCHEMAS}
    assert {"spawn_subagent", "spawn_subagents"} <= names

    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "Delegating two bounded inspections in parallel.",
                [
                    ToolCall(
                        "spawn-many",
                        "spawn_subagents",
                        {
                            "requests": [
                                {"type": "explorer", "question": "inspect app.py SENTINEL_APP"},
                                {"type": "explorer", "question": "inspect utils.py SENTINEL_UTILS"},
                            ]
                        },
                    )
                ],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=40,
            ),
            ModelTurn("Parent integrates SENTINEL_APP and SENTINEL_UTILS findings.", input_tokens=100, output_tokens=20),
        ],
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "inspect app.py and utils.py in parallel", recorder, client=client)
    events = read_events(recorder.path)

    returns = [e for e in events if e["kind"] == "subagent_return" and e["agent_type"] == "explorer"]
    assert len(returns) == 2
    (a_start, a_end), (b_start, b_end) = [(r["started_at"], r["ended_at"]) for r in returns]
    assert a_start <= b_end and b_start <= a_end  # genuinely overlapping wall-clock

    parallel_result = next(e for e in events if e["kind"] == "tool_result" and e["tool"] == "spawn_subagents")
    payload = json.loads(str(parallel_result["result_full"]))
    assert [item["status"] for item in payload] == ["ok", "ok"]
    assert "SENTINEL_APP" in payload[0]["payload"]
    assert "SENTINEL_UTILS" in payload[1]["payload"]
    final = [e for e in events if e["kind"] == "assistant_step" and e["agent_id"] == "parent"][-1]
    assert "SENTINEL_APP" in final["assistant_text"] and "SENTINEL_UTILS" in final["assistant_text"]


def test_parallel_cap_and_coder_conflict(tmp_path: Path) -> None:
    # A request beyond MAX_PARALLEL_SUBAGENTS overflows; a second Coder in the
    # same batch is serialised as a conflict rather than run concurrently.
    requests = [{"type": "explorer", "question": f"q{i}"} for i in range(config.MAX_PARALLEL_SUBAGENTS + 1)]
    requests[0] = {"type": "coder", "question": "edit A"}
    requests[1] = {"type": "coder", "question": "edit B"}
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "Over-request on purpose.",
                [ToolCall("spawn-many", "spawn_subagents", {"requests": requests})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=40,
            ),
            ModelTurn("Done.", input_tokens=50, output_tokens=10),
        ],
        by_type={"coder": [ModelTurn("A: edited", input_tokens=20, output_tokens=10)]},
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "batch", recorder, client=client)
    payload = json.loads(str(next(e for e in read_events(recorder.path) if e["kind"] == "tool_result" and e["tool"] == "spawn_subagents")["result_full"]))
    statuses = [item["status"] for item in payload]
    assert "conflict" in statuses  # second Coder serialised
    assert "tool_error" in statuses  # fifth request over the cap
    assert any(item["payload"] == "parallel cap exceeded" for item in payload)


def test_near_cap_blocks_spawn_subagents(tmp_path: Path) -> None:
    guard = BudgetGuard(max_steps=15)
    guard.parent_step_count = 14
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "try spawn at cap",
                [
                    ToolCall(
                        "spawn-many",
                        "spawn_subagents",
                        {
                            "requests": [
                                {"type": "explorer", "question": "list auth/"},
                                {"type": "explorer", "question": "list utils.py"},
                            ]
                        },
                    )
                ],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn(
                "calc_haiku_3 is ready with engine, ui, and main.",
                input_tokens=80,
                output_tokens=20,
            ),
        ],
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "finish calculator", recorder, client=client, guard=guard)
    spawn_result = next(
        e for e in read_events(recorder.path) if e["kind"] == "tool_result" and e["tool"] == "spawn_subagents"
    )
    payload = json.loads(str(spawn_result["result_full"]))
    assert payload["status"] == "near_cap_blocked"
    assert "final step" in payload["message"].lower()
    assert not any(e["kind"] == "subagent_spawn" for e in read_events(recorder.path))


def test_spawn_repetition_abort_on_identical_parallel_batch(tmp_path: Path) -> None:
    same_requests = {
        "requests": [
            {"type": "explorer", "question": "auth/"},
            {"type": "explorer", "question": "utils.py"},
        ]
    }
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "batch 1",
                [ToolCall("s1", "spawn_subagents", dict(same_requests))],
                stop_reason="tool_use",
                input_tokens=50,
                output_tokens=20,
            ),
            ModelTurn(
                "batch 2",
                [ToolCall("s2", "spawn_subagents", dict(same_requests))],
                stop_reason="tool_use",
                input_tokens=50,
                output_tokens=20,
            ),
            ModelTurn(
                "batch 3",
                [ToolCall("s3", "spawn_subagents", dict(same_requests))],
                stop_reason="tool_use",
                input_tokens=50,
                output_tokens=20,
            ),
            ModelTurn("stopped repeating.", input_tokens=40, output_tokens=10),
        ],
    )
    recorder = TraceRecorder(tmp_path)
    guard = BudgetGuard(max_steps=20)
    run_live_task(tmp_path, "repeat parallel spawn", recorder, client=client, guard=guard)
    events = read_events(recorder.path)
    assert any(
        e.get("kind") == "budget_event" and e.get("budget_reason") == "repetition_abort" for e in events
    )
    spawn_results = [e for e in events if e["kind"] == "tool_result" and e["tool"] == "spawn_subagents"]
    assert len(spawn_results) == 3
    assert "repetition_abort" in str(spawn_results[-1]["result_full"])


def test_parallel_failed_coder_constrained_retry(tmp_path: Path) -> None:
    (tmp_path / "calc_haiku_3").mkdir(parents=True, exist_ok=True)
    fail_turns = [
        ModelTurn(
            f"bad read {i}",
            [ToolCall(f"bad-read-{i}", "read_file", {"path": "calc_haiku_3"})],
            stop_reason="tool_use",
            input_tokens=60,
            output_tokens=20,
        )
        for i in range(config.MAX_SUBAGENT_STEPS)
    ]
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "parallel coder + explorer",
                [
                    ToolCall(
                        "spawn-p",
                        "spawn_subagents",
                        {
                            "requests": [
                                {"type": "coder", "question": "Create calc_haiku_3/x.py with x=1"},
                                {"type": "explorer", "question": "List calc_haiku_3 files"},
                            ]
                        },
                    )
                ],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("Files created.", input_tokens=80, output_tokens=20),
        ],
        by_type={
            "coder": fail_turns
            + [
                ModelTurn(
                    "write fixed",
                    [ToolCall("fix-write", "write_file", {"path": "calc_haiku_3/x.py", "content": "x = 1\n"})],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn("calc_haiku_3/x.py: created", input_tokens=40, output_tokens=10),
            ],
        },
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "parallel coder retry", recorder, client=client)
    events = read_events(recorder.path)
    assert any(
        e.get("kind") == "budget_event" and e.get("budget_reason") == "coder_constrained_retry" for e in events
    )
    spawn_result = next(e for e in events if e["kind"] == "tool_result" and e["tool"] == "spawn_subagents")
    payload = json.loads(str(spawn_result["result_full"]))
    coder_entry = next(item for item in payload if item.get("agent_type") == "coder")
    assert "retry" in coder_entry
    assert coder_entry["retry"]["status"] == "ok"
    assert (tmp_path / "calc_haiku_3" / "x.py").read_text(encoding="utf-8") == "x = 1\n"


def test_parallel_aborted_when_slice_exceeded(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    expensive = ModelTurn(
        "inspect",
        [ToolCall("read", "read_file", {"path": "app.py"})],
        stop_reason="tool_use",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.03,
    )
    cheap_done = ModelTurn("done", input_tokens=10, output_tokens=5, cost_usd=0.001)
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "parallel explore",
                [
                    ToolCall(
                        "spawn-p",
                        "spawn_subagents",
                        {
                            "requests": [
                                {"type": "explorer", "question": "read app.py"},
                                {"type": "explorer", "question": "read app.py again"},
                            ]
                        },
                    )
                ],
                stop_reason="tool_use",
                input_tokens=50,
                output_tokens=20,
            ),
            ModelTurn("Partial parallel results noted.", input_tokens=50, output_tokens=20),
        ],
        by_type={"explorer": [expensive, cheap_done, expensive, cheap_done]},
    )
    guard = BudgetGuard(max_usd=0.05, max_tokens=100_000)
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "parallel slice", recorder, client=client, guard=guard)
    events = read_events(recorder.path)
    assert any(
        e.get("kind") == "budget_event" and e.get("budget_reason") == "parallel_aborted" for e in events
    )
    payload = json.loads(
        str(next(e for e in events if e["kind"] == "tool_result" and e["tool"] == "spawn_subagents")["result_full"])
    )
    assert any(item.get("status") == "parallel_aborted" for item in payload)


def test_subagent_structured_summary_without_terminal_text(tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    client = PipelineClient(
        parent_turns=[ModelTurn("done", input_tokens=10, output_tokens=5)],
        by_type={
            "coder": [
                ModelTurn(
                    "no tools",
                    [],
                    stop_reason="stop",
                    input_tokens=10,
                    output_tokens=5,
                )
            ]
        },
    )
    guard = BudgetGuard()
    summary, status, writes_ok, reads_ok, failure_reason = _run_live_subagent(
        tmp_path,
        "coder",
        "write nothing",
        recorder,
        client,
        guard,
        "coder-test-1",
        time.perf_counter(),
        ApprovalPolicy(mode="off"),
    )
    assert status == "tool_error"
    assert failure_reason == "no_write"
    assert "reason=no_write" in summary


def test_literal_tool_output_tail_preview_large_file(tmp_path: Path) -> None:
    from vg_agent.__main__ import _literal_tool_outputs
    from vg_agent.chat_ui import format_literal_tool_body

    body = "\n".join(f"line-{index}" for index in range(500))
    preview = format_literal_tool_body(
        body,
        tool="read_file",
        path="data/big.txt",
        event_idx=42,
        trace_path=tmp_path / "traces" / "abc.jsonl",
    )
    assert "500 lines" in preview
    assert "line-499" in preview
    assert "line-0" not in preview
    assert "470 earlier lines" in preview
    assert "read_file_range data/big.txt" in preview

    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="read data/big.txt")
    recorder.emit("tool_call", tool="read_file", tool_use_id="read-big", args={"path": "data/big.txt"})
    recorder.emit(
        "tool_result",
        tool="read_file",
        tool_use_id="read-big",
        result_full=body,
        bytes=len(body.encode()),
        tokens=5000,
        latency_ms=1,
        status="ok",
    )
    recorder.emit("assistant_step", assistant_text="Read complete.", tool_calls=[], stop_reason="end_turn")
    outputs = _literal_tool_outputs(
        recorder.events, 0, "read data/big.txt", "Read complete.", trace_path=recorder.path
    )
    assert len(outputs) == 1
    assert "470 earlier lines" in outputs[0]


def test_literal_tool_output_compacted_read(tmp_path: Path) -> None:
    from vg_agent.__main__ import _literal_tool_outputs

    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="read data/sample.log")
    recorder.emit("tool_call", tool="read_file", tool_use_id="read-log", args={"path": "data/sample.log"})
    recorder.emit(
        "tool_result",
        tool="read_file",
        tool_use_id="read-log",
        result_full="request_id=req-00001 route=/health\n" * 100,
        bytes=4000,
        tokens=9000,
        latency_ms=1,
        status="ok",
    )
    recorder.emit(
        "compaction",
        tool_use_id="read-log",
        before_tokens=9000,
        after_tokens=120,
        summary="Large log overview",
        original_event_idx=2,
        run_id=recorder.run_id,
    )
    recorder.emit("assistant_step", assistant_text="Log scanned.", tool_calls=[], stop_reason="end_turn")
    outputs = _literal_tool_outputs(
        recorder.events, 0, "read data/sample.log", "Log scanned.", trace_path=recorder.path
    )
    assert outputs
    assert "compacted" in outputs[0].lower() or "COMPACTED" in outputs[0]
    assert "request_id=req-00001" not in outputs[0]


def test_parallel_subagent_summary_overlap() -> None:
    from vg_agent.trace import parallel_subagent_summary

    events = [
        {"kind": "subagent_spawn", "child_agent_id": "explorer.0", "question": "auth/"},
        {
            "kind": "subagent_return",
            "child_agent_id": "explorer.0",
            "agent_type": "explorer",
            "started_at": "2026-05-10T12:00:00+00:00",
            "ended_at": "2026-05-10T12:00:03+00:00",
            "summary": "auth ok",
        },
        {"kind": "subagent_spawn", "child_agent_id": "explorer.1", "question": "utils.py"},
        {
            "kind": "subagent_return",
            "child_agent_id": "explorer.1",
            "agent_type": "explorer",
            "started_at": "2026-05-10T12:00:01+00:00",
            "ended_at": "2026-05-10T12:00:04+00:00",
            "summary": "utils ok",
        },
    ]
    summary = parallel_subagent_summary(events)
    assert summary is not None
    assert summary.overlap is True
    assert len(summary.returns) == 2


def test_parallel_finops_batch_lines(tmp_path: Path) -> None:
    from vg_agent.trace import parallel_finops_batch_lines

    spawn_payload = json.dumps(
        [
            {"agent_id": "explorer.0", "agent_type": "explorer", "status": "ok", "payload": "a"},
            {"agent_id": "explorer.1", "agent_type": "explorer", "status": "ok", "payload": "b"},
        ]
    )
    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="parallel task")
    recorder.emit(
        "subagent_return",
        child_agent_id="explorer.0",
        agent_type="explorer",
        started_at="2026-05-10T12:00:00+00:00",
        ended_at="2026-05-10T12:00:02+00:00",
    )
    recorder.emit(
        "subagent_return",
        child_agent_id="explorer.1",
        agent_type="explorer",
        started_at="2026-05-10T12:00:01+00:00",
        ended_at="2026-05-10T12:00:03+00:00",
    )
    recorder.emit(
        "tool_result",
        tool="spawn_subagents",
        agent_id="parent",
        status="ok",
        result_full=spawn_payload,
    )
    lines = parallel_finops_batch_lines(recorder.events)
    assert lines
    assert "Parallel batches this session: 1" in lines[0]
    assert "2 sub-agents" in lines[1]
    assert "overlapping wall-clock" in lines[1]


def test_parallel_finops_batch_lines_ignore_later_spawns_in_turn(tmp_path: Path) -> None:
    """VG.1 / FinOps: Coder+Reviewer returns in the same turn must not inflate batch count."""
    from vg_agent.trace import parallel_finops_batch_lines

    spawn_payload = json.dumps(
        [
            {"agent_id": "explorer-1.0", "agent_type": "explorer", "status": "ok", "payload": "engine"},
            {"agent_id": "explorer-1.1", "agent_type": "explorer", "status": "ok", "payload": "ui"},
        ]
    )
    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="calc_haiku_4 parallel inspect then coder")
    recorder.emit(
        "subagent_return",
        child_agent_id="explorer-1.0",
        agent_type="explorer",
        started_at="2026-05-10T12:00:00+00:00",
        ended_at="2026-05-10T12:00:03+00:00",
    )
    recorder.emit(
        "subagent_return",
        child_agent_id="explorer-1.1",
        agent_type="explorer",
        started_at="2026-05-10T12:00:01+00:00",
        ended_at="2026-05-10T12:00:04+00:00",
    )
    recorder.emit(
        "tool_result",
        tool="spawn_subagents",
        agent_id="parent",
        status="ok",
        result_full=spawn_payload,
    )
    recorder.emit(
        "subagent_return",
        child_agent_id="coder-3",
        agent_type="coder",
        started_at="2026-05-10T12:00:10+00:00",
        ended_at="2026-05-10T12:00:20+00:00",
    )
    recorder.emit(
        "subagent_return",
        child_agent_id="reviewer-4",
        agent_type="reviewer",
        started_at="2026-05-10T12:00:21+00:00",
        ended_at="2026-05-10T12:00:30+00:00",
    )
    lines = parallel_finops_batch_lines(recorder.events)
    assert any("2 sub-agents" in line for line in lines)
    assert not any("4 sub-agents" in line for line in lines)


def test_parallel_subagent_summary_for_tool_result_scopes_batch() -> None:
    from vg_agent.trace import parallel_subagent_summary_for_tool_result

    spawn_payload = json.dumps(
        [
            {"agent_id": "explorer.0", "status": "ok"},
            {"agent_id": "explorer.1", "status": "ok"},
        ]
    )
    events = [
        {
            "kind": "subagent_return",
            "child_agent_id": "explorer.0",
            "agent_type": "explorer",
            "started_at": "2026-05-10T12:00:00+00:00",
            "ended_at": "2026-05-10T12:00:03+00:00",
        },
        {
            "kind": "subagent_return",
            "child_agent_id": "explorer.1",
            "agent_type": "explorer",
            "started_at": "2026-05-10T12:00:01+00:00",
            "ended_at": "2026-05-10T12:00:04+00:00",
        },
        {
            "kind": "tool_result",
            "tool": "spawn_subagents",
            "agent_id": "parent",
            "status": "ok",
            "result_full": spawn_payload,
        },
        {
            "kind": "subagent_return",
            "child_agent_id": "coder-1",
            "agent_type": "coder",
            "started_at": "2026-05-10T12:00:10+00:00",
            "ended_at": "2026-05-10T12:00:20+00:00",
        },
    ]
    summary = parallel_subagent_summary_for_tool_result(events, 2)
    assert summary is not None
    assert len(summary.returns) == 2
    assert summary.overlap is True
    assert {item.child_agent_id for item in summary.returns} == {"explorer.0", "explorer.1"}


def test_show_context_overview_lists_steps_and_parallel() -> None:
    from vg_agent.trace import format_show_context_overview

    events = [
        {"kind": "user_prompt", "agent_id": "parent", "prompt": "go"},
        {
            "kind": "assistant_step",
            "agent_id": "parent",
            "step_idx": 0,
            "tool_calls": [{"name": "read_file", "args": {"path": "data/sample.log"}}],
        },
        {
            "kind": "assistant_step",
            "agent_id": "parent",
            "step_idx": 1,
            "tool_calls": [{"name": "spawn_subagents", "args": {"requests": []}}],
        },
        {
            "kind": "subagent_return",
            "child_agent_id": "explorer.0",
            "agent_type": "explorer",
            "started_at": "2026-05-10T12:00:00+00:00",
            "ended_at": "2026-05-10T12:00:02+00:00",
        },
        {
            "kind": "subagent_return",
            "child_agent_id": "explorer.1",
            "agent_type": "explorer",
            "started_at": "2026-05-10T12:00:01+00:00",
            "ended_at": "2026-05-10T12:00:03+00:00",
        },
        {
            "kind": "assistant_step",
            "agent_id": "parent",
            "step_idx": 2,
            "assistant_text": "done",
            "tool_calls": [],
        },
    ]
    text = format_show_context_overview(events)
    assert "step" in text
    assert "read_file" in text
    assert "spawn_subagents" in text
    assert "parallel sub-agents" in text
    assert "overlap yes" in text
    assert "/show-context N" in text


def test_format_turn_review_includes_parallel_section(tmp_path: Path) -> None:
    from vg_agent.trace import format_turn_review

    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="summarise in parallel")
    recorder.emit(
        "assistant_step",
        agent_id="parent",
        assistant_text="",
        tool_calls=[{"name": "spawn_subagents", "args": {"requests": []}}],
        stop_reason="tool_use",
    )
    recorder.emit(
        "subagent_return",
        child_agent_id="explorer.0",
        agent_type="explorer",
        started_at="2026-05-10T12:00:00+00:00",
        ended_at="2026-05-10T12:00:02+00:00",
        summary="AUTH_SENTINEL",
    )
    recorder.emit(
        "subagent_return",
        child_agent_id="explorer.1",
        agent_type="explorer",
        started_at="2026-05-10T12:00:01+00:00",
        ended_at="2026-05-10T12:00:03+00:00",
        summary="UTILS_SENTINEL",
    )
    recorder.emit(
        "tool_result",
        tool="spawn_subagents",
        agent_id="parent",
        status="ok",
        result_full=json.dumps(
            [
                {"agent_id": "explorer.0", "status": "ok", "payload": "AUTH_SENTINEL"},
                {"agent_id": "explorer.1", "status": "ok", "payload": "UTILS_SENTINEL"},
            ]
        ),
    )
    recorder.emit(
        "assistant_step",
        agent_id="parent",
        assistant_text="Combined AUTH_SENTINEL and UTILS_SENTINEL.",
        tool_calls=[],
        stop_reason="end_turn",
    )
    text = format_turn_review(recorder.events, trace_path=recorder.path)
    assert "summarise in parallel" in text
    assert "overlap yes" in text
    assert "AUTH_SENTINEL" in text
    assert "UTILS_SENTINEL" in text


def test_format_turn_review_includes_compaction_details(tmp_path: Path) -> None:
    from vg_agent.trace import format_turn_review

    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="read the log")
    recorder.emit(
        "compaction",
        agent_id="parent",
        tool_use_id="read-log",
        before_tokens=9000,
        after_tokens=120,
        summary="SAMPLE_LOG_SUMMARY_SENTINEL: compacted for parent context.",
        compactor_model=config.COMPACTOR_MODEL_ID,
        compactor_fallback=False,
        original_event_idx=3,
        original_sha256="abc",
    )
    recorder.emit(
        "assistant_step",
        agent_id="parent",
        assistant_text="Done reading.",
        tool_calls=[],
        stop_reason="end_turn",
    )
    text = format_turn_review(recorder.events, trace_path=recorder.path)
    assert "tool_result compacted 9000 -> 120 tokens" in text
    assert f"model={config.COMPACTOR_MODEL_ID}" in text
    assert "fallback=False" in text
    assert "SAMPLE_LOG_SUMMARY_SENTINEL" in text


def test_live_parent_large_tool_result_compacted_before_next_turn(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    client = FakeClient([
        ModelTurn(
            "Read the large log.",
            [ToolCall("read-log", "read_file", {"path": "data/sample.log"})],
            stop_reason="tool_use",
            input_tokens=100,
            output_tokens=20,
        ),
        ModelTurn(
            "SAMPLE_LOG_SUMMARY_SENTINEL: compacted log summary.",
            input_tokens=50,
            output_tokens=30,
        ),
        ModelTurn("Done.", input_tokens=100, output_tokens=20),
    ])
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "read sample log", recorder, client=client)
    events = read_events(recorder.path)
    assert any(e["kind"] == "compaction" and e["tool_use_id"] == "read-log" for e in events)
    parent_calls = [
        c for c in client.calls
        if "parent coding agent" in str(c.get("system_prompt") or "")
    ]
    assert len(parent_calls) >= 2
    second_parent_messages = json.dumps(parent_calls[1]["messages"])
    assert "[COMPACTED tool_result for tool_use_id=read-log]" in second_parent_messages
    assert "req-00001" not in second_parent_messages


def test_generated_source_reproducible(tmp_path: Path) -> None:
    generated = tmp_path / "vg_agent"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_project.py"), "--src-dir", str(generated), "--no-fixture", "--clean"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    current = ROOT / "src" / "vg_agent"
    current_files = sorted(p.relative_to(current) for p in current.rglob("*.py"))
    generated_files = sorted(p.relative_to(generated) for p in generated.rglob("*.py"))
    assert generated_files == current_files
    for rel in current_files:
        assert (generated / rel).read_text(encoding="utf-8") == (current / rel).read_text(encoding="utf-8")


def test_documented_generation_command(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    shutil.copytree(ROOT, sandbox, ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", "traces"))
    subprocess.run(
        [sys.executable, "scripts/generate_project.py", "--clean"],
        cwd=sandbox,
        check=True,
        text=True,
        capture_output=True,
    )
    assert (sandbox / "src" / "vg_agent" / "agent.py").exists()
    sample_log_size = (sandbox / "fixtures" / "demo_repo" / "data" / "sample.log").stat().st_size
    assert 200_000 < sample_log_size < 600_000


def test_find_exec_and_delete_blocked() -> None:
    assert validate_shell_command("find . -delete") is not None
    assert validate_shell_command("find . -exec ls {}") is not None
    assert validate_shell_command("find . -execdir ls {}") is not None
    assert validate_shell_command("find . -okdir ls {}") is not None
    assert validate_shell_command("find . -fprint /tmp/x") is not None
    assert validate_shell_command("find . -name foo") is None


def test_approval_required_for_write_tools(tmp_path: Path) -> None:
    write_fixture(tmp_path)

    def deny_all(_request: ApprovalRequest) -> ApprovalOutcome:
        return ApprovalOutcome(decision="denied", reason="test denies")

    policy = ApprovalPolicy(mode="writes", prompt=deny_all)
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "rename foo to bar in app.py", recorder, client=_rename_via_coder_client(), policy=policy)
    text = (tmp_path / "app.py").read_text(encoding="utf-8")
    # The gated spawn is denied before any Coder edit runs, so the file is unchanged.
    assert "def foo(" in text
    assert "def bar(" not in text
    approvals = [e for e in recorder.events if e["kind"] == "approval"]
    assert approvals and approvals[0]["decision"] == "denied"


def test_approval_event_recorded_auto_yes(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    policy = ApprovalPolicy(mode="writes", auto_yes=True)
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "rename foo to bar in app.py", recorder, client=_rename_via_coder_client(), policy=policy)
    approvals = [e for e in recorder.events if e["kind"] == "approval"]
    assert approvals and approvals[0]["decision"] == "auto"
    assert "def bar(" in (tmp_path / "app.py").read_text(encoding="utf-8")


def test_approval_scope_cache_hit(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    (tmp_path / "utils.py").write_text("foo=1\n", encoding="utf-8")

    prompt_calls: dict[str, int] = {}

    def grant_scoped(request: ApprovalRequest) -> ApprovalOutcome:
        prompt_calls[request.tool] = prompt_calls.get(request.tool, 0) + 1
        if request.tool == "edit_file":
            return ApprovalOutcome(decision="approved_scoped", scope_key="", reason="grant root for edits")
        return ApprovalOutcome(decision="approved_always", reason="allow spawn")

    policy = ApprovalPolicy(mode="writes", prompt=grant_scoped)

    # One Coder edits two files in the same directory; the second edit_file reuses
    # the scoped grant from the first without re-prompting.
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "Delegate both edits to a Coder.",
                [ToolCall("spawn-coder", "spawn_subagent", {"type": "coder", "question": "rename foo to bar in app.py and utils.py"})],
                stop_reason="tool_use",
                input_tokens=10,
                output_tokens=5,
            ),
            ModelTurn("Coder renamed foo to bar in both files.", input_tokens=10, output_tokens=5),
        ],
        by_type={
            "coder": [
                ModelTurn("edit app", [ToolCall("e1", "edit_file", {"path": "app.py", "old": "foo", "new": "bar"})], stop_reason="tool_use", input_tokens=10, output_tokens=5),
                ModelTurn("edit utils", [ToolCall("e2", "edit_file", {"path": "utils.py", "old": "foo", "new": "bar"})], stop_reason="tool_use", input_tokens=10, output_tokens=5),
                ModelTurn("both: renamed", input_tokens=10, output_tokens=5),
            ],
        },
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "rename in two files", recorder, client=client, policy=policy)
    edit_approvals = [e for e in recorder.events if e["kind"] == "approval" and e["tool"] == "edit_file"]
    assert len(edit_approvals) == 2
    assert all(a["decision"] == "approved_scoped" for a in edit_approvals)
    # The edit_file prompt callback fires only once; the second edit is a cache hit.
    assert prompt_calls.get("edit_file") == 1
    assert "bar" in (tmp_path / "app.py").read_text(encoding="utf-8")


def test_approval_scope_does_not_bypass_denylist(tmp_path: Path) -> None:
    write_fixture(tmp_path)

    def grant_always(_request: ApprovalRequest) -> ApprovalOutcome:
        return ApprovalOutcome(decision="approved_always", reason="trust me")

    policy = ApprovalPolicy(mode="writes", prompt=grant_always)
    # A Coder tries to write .env; even with approved_always the tools layer refuses.
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "Delegate the edit to a Coder.",
                [ToolCall("spawn-coder", "spawn_subagent", {"type": "coder", "question": "write the env file"})],
                stop_reason="tool_use",
                input_tokens=10,
                output_tokens=5,
            ),
            ModelTurn("Coder reported the write was refused.", input_tokens=10, output_tokens=5),
        ],
        by_type={
            "coder": [
                ModelTurn("try .env", [ToolCall("e2", "edit_file", {"path": ".env", "old": "", "new": "EVIL=1"})], stop_reason="tool_use", input_tokens=10, output_tokens=5),
                ModelTurn(".env: refused", input_tokens=10, output_tokens=5),
            ],
        },
    )
    (tmp_path / ".env").write_text("SECRET=abc", encoding="utf-8")
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "try to write env", recorder, client=client, policy=policy)
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "SECRET=abc"
    sensitive_errors = [
        e for e in recorder.events
        if e["kind"] == "tool_result" and "sensitive path" in str(e.get("result_full", ""))
    ]
    assert sensitive_errors


def test_unsafe_run_bash_is_rejected_before_approval_prompt(tmp_path: Path) -> None:
    calls = {"count": 0}

    def approve(_request: ApprovalRequest) -> ApprovalOutcome:
        calls["count"] += 1
        return ApprovalOutcome(decision="approved", reason="unused")

    policy = ApprovalPolicy(mode="writes", prompt=approve)
    client = FakeClient([
        ModelTurn(
            "try unsafe shell",
            [ToolCall("bad-find", "run_bash", {"command": 'find . -name "calculator.py" | head -20'})],
            stop_reason="tool_use",
            input_tokens=10,
            output_tokens=5,
        )
    ])
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "inspect", recorder, client=client, policy=policy)
    assert calls["count"] == 0
    result = next(e for e in recorder.events if e["kind"] == "tool_result")
    assert result["status"] == "error"
    assert "shell control" in str(result["result_full"])


def test_daily_spend_persists_across_runs(tmp_path: Path) -> None:
    ledger = DailySpendLedger(tmp_path)
    assert ledger.remaining_today() == config.MAX_USD_PER_DAY
    ledger.add(0.10)
    ledger2 = DailySpendLedger(tmp_path)
    assert ledger2.today_spent() == pytest.approx(0.10)
    assert ledger2.remaining_today() == pytest.approx(config.MAX_USD_PER_DAY - 0.10)

    guard = BudgetGuard.for_workspace(tmp_path)
    assert guard.daily_remaining_usd == pytest.approx(config.MAX_USD_PER_DAY - 0.10)


def test_daily_spend_fail_closed_on_corrupt_ledger(tmp_path: Path) -> None:
    (tmp_path / config.DAILY_SPEND_FILE).write_text("not-json-{", encoding="utf-8")
    ledger = DailySpendLedger(tmp_path)
    assert ledger.fail_closed
    assert ledger.remaining_today() == 0.0


def test_endpoint_host_pinned(tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    client = LiveModelClient(api_key="dummy", endpoint="https://evil.example/api/v1", recorder=recorder)
    with pytest.raises(EndpointPinViolation):
        client.complete(model=config.PARENT_MODEL_ID, system_prompt="x", messages=[], tools=[])
    assert recorder.events[-1]["kind"] == "egress_blocked"
    assert recorder.events[-1]["host"] == "evil.example"


def test_live_client_maps_litellm_429_provider_detail_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RateLimitError(Exception):
        status_code = 429

    def completion(**_kwargs: object) -> object:
        raise RateLimitError(
            "429 Too Many Requests temporarily rate-limited upstream key sk-or-v1-AbCdEf-12"
        )

    fake_litellm = SimpleNamespace(completion=completion, suppress_debug_info=False, set_verbose=True)
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)
    monkeypatch.setenv("VG_PROVIDER_ERROR_DETAIL", "1")

    client = LiveModelClient(api_key="dummy")
    with pytest.raises(LiveModelRateLimitError) as exc_info:
        client.complete(model=config.PARENT_MODEL_ID, system_prompt="x", messages=[], tools=[])

    assert exc_info.value.provider_detail is not None
    assert "sk-or-v1" not in exc_info.value.provider_detail
    assert "rate-limited" in exc_info.value.provider_detail


def test_live_client_maps_litellm_429_to_readable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class RateLimitError(Exception):
        status_code = 429

    def completion(**_kwargs: object) -> object:
        raise RateLimitError(
            '429 Too Many Requests {"user_id":"user_secret","metadata":{"raw":"temporarily rate-limited upstream"}}'
        )

    fake_litellm = SimpleNamespace(completion=completion, suppress_debug_info=False, set_verbose=True)
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    client = LiveModelClient(api_key="dummy")
    with pytest.raises(LiveModelRateLimitError) as exc_info:
        client.complete(model=config.PARENT_MODEL_ID, system_prompt="x", messages=[], tools=[])

    message = str(exc_info.value)
    assert "rate-limited" in message
    assert "OpenRouter integrations" in message
    assert "user_secret" not in message


def test_live_task_records_model_error_without_traceback(tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "do work", recorder, client=FailingRateLimitClient())
    events = read_events(recorder.path)
    model_errors = [event for event in events if event["kind"] == "model_error"]
    assert model_errors
    assert model_errors[0]["retryable"] is True
    assert events[-1]["kind"] == "run_end"
    assert events[-1]["final_status"] == "model_error"


def test_trace_redacts_secrets(tmp_path: Path) -> None:
    redacted, summary = _redact("token sk-or-v1-AbCdEf-12 and key AKIA0123456789ABCDEF and Bearer xyz")
    assert "***REDACTED***" in redacted
    assert "sk-or-v1" not in redacted
    assert "AKIA" not in redacted
    assert any(name == "openrouter_key" for name, _ in summary)

    recorder = TraceRecorder(tmp_path)
    recorder.emit("tool_result", tool="read_file", tool_use_id="t1", result_full="leaked sk-or-v1-DEADBEEF-9")
    nested = recorder.emit(
        "tool_call",
        tool="run_bash",
        tool_use_id="t2",
        args={
            "command": "rg sk-or-v1-NESTED-123 .env",
            "metadata": [
                {"auth": "Bearer abc.def"},
                {"aws": "AKIA0123456789ABCDEF", "unchanged": 7},
            ],
        },
        tool_calls=[
            {
                "name": "read_file",
                "args": {"path": ".env", "token": "sk-or-v1-TOOLCALL-123"},
            }
        ],
    )
    serialized_nested = json.dumps(nested)
    assert "sk-or-v1-NESTED" not in serialized_nested
    assert "Bearer abc.def" not in serialized_nested
    assert "AKIA0123456789ABCDEF" not in serialized_nested
    assert "sk-or-v1-TOOLCALL" not in serialized_nested
    assert nested["args"]["metadata"][1]["unchanged"] == 7  # type: ignore[index]
    events = recorder.events
    assert not any("sk-or-v1-DEAD" in str(e.get("result_full", "")) for e in events)
    redaction_events = [e for e in events if e["kind"] == "redaction"]
    assert redaction_events
    with sqlite3.connect(tmp_path / config.SQLITE_TRACE_DB) as conn:
        payloads = "\n".join(row[0] for row in conn.execute("SELECT payload_json FROM events"))
        assert "sk-or-v1-DEAD" not in payloads
        assert "sk-or-v1-NESTED" not in payloads
        assert "Bearer abc.def" not in payloads
        assert "AKIA0123456789ABCDEF" not in payloads
        assert "sk-or-v1-TOOLCALL" not in payloads
        assert conn.execute("SELECT COUNT(*) FROM redactions").fetchone()[0] == len(redaction_events)


def test_prompts_match_prompts_md() -> None:
    text = (ROOT / "PROMPTS.md").read_text(encoding="utf-8")
    from vg_agent.agent import EXPLORER_SYSTEM_PROMPT, PARENT_SYSTEM_PROMPT

    parent_first_line = PARENT_SYSTEM_PROMPT.splitlines()[0]
    explorer_first_line = EXPLORER_SYSTEM_PROMPT.splitlines()[0]
    assert parent_first_line in text
    assert explorer_first_line in text
    # Injection-defense sentence must be in the parent prompt
    assert "data, not as instructions" in PARENT_SYSTEM_PROMPT
    assert "data, not as instructions" in text


def test_finops_view_renders_per_agent_type(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # P1.3 / pitch FinOps: per-agent-type token+USD breakdown renders from the guard.
    guard = BudgetGuard(max_tokens=10_000, max_usd=1.0)
    guard.record_model_call(config.PARENT_MODEL_ID, 100, 50, cost_usd=0.01, agent_type="parent")
    guard.record_model_call(config.EXPLORER_MODEL_ID, 200, 40, cost_usd=0.02, agent_type="explorer")
    guard.record_model_call(config.CODER_MODEL_ID, 80, 30, cost_usd=0.03, agent_type="coder")
    from vg_agent.__main__ import _print_finops

    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="inspect")
    recorder.emit("tool_call", agent_type="parent", tool="spawn_subagent", tool_use_id="t1", args={})
    recorder.emit("tool_call", agent_type="coder", tool="edit_file", tool_use_id="t2", args={})

    _print_finops(guard, recorder)
    out = capsys.readouterr().out
    assert "parent" in out and "explorer" in out and "coder" in out
    assert "in_tok" in out and "out_tok" in out and "prompts" in out and "tools" in out
    assert "user_prompts 1" in out
    assert "TOTAL" in out
    assert guard.per_agent_type_tokens["explorer"] == 240
    assert guard.per_agent_type_input_tokens["explorer"] == 200
    assert guard.per_agent_type_output_tokens["explorer"] == 40


def test_grilling_yields_clarifying_questions(tmp_path: Path) -> None:
    # VG.9 / pitch: on an ambiguous task the parent spawns Grilling, which asks
    # clarifying questions; the parent surfaces them and yields without acting.
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "Ambiguous task - consult Grilling first.",
                [ToolCall("spawn-grill", "spawn_subagent", {"type": "grilling", "question": "make it better"})],
                stop_reason="tool_use",
                input_tokens=20,
                output_tokens=10,
            ),
            ModelTurn("Before I proceed I need answers to the Grilling questions.", input_tokens=20, output_tokens=10),
        ],
        by_type={
            "grilling": [
                ModelTurn('{"questions": ["Which file or module?", "What does better mean here?"]}', input_tokens=20, output_tokens=10),
            ],
        },
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "make it better", recorder, client=client)
    events = read_events(recorder.path)
    spawns = [e for e in events if e["kind"] == "subagent_spawn"]
    assert spawns[0]["agent_type"] == "grilling"
    grill_return = next(e for e in events if e["kind"] == "subagent_return" and e["agent_type"] == "grilling")
    payload = json.loads(str(grill_return["summary"]))
    assert "questions" in payload and len(payload["questions"]) >= 1
    assert events[-1]["final_status"] == "ok"
    # P1.2: every event carries an agent_type attribution field.
    assert all("agent_type" in e for e in events)


def test_run_live_task_history_persists_across_turns(tmp_path: Path) -> None:
    # P1.1: a shared history list carries conversation context across turns.
    history: list[dict[str, object]] = []
    recorder = TraceRecorder(tmp_path)
    run_live_task(
        tmp_path,
        "remember MEMORY_TOKEN for later",
        recorder,
        client=PipelineClient([ModelTurn("Noted MEMORY_TOKEN.", input_tokens=10, output_tokens=5)]),
        history=history,
    )
    second = PipelineClient([ModelTurn("You asked me to remember it.", input_tokens=10, output_tokens=5)])
    run_live_task(tmp_path, "what did I ask you to remember?", recorder, client=second, history=history)
    seen = json.dumps(second.calls[0]["messages"])
    assert "MEMORY_TOKEN" in seen  # turn-1 content visible in turn-2 context
    assert "what did I ask you to remember?" in seen


def test_literal_tool_output_fallback_for_listing_requests(tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="list all files")
    recorder.emit("tool_call", tool="run_bash", tool_use_id="ls-1", command="ls -l", args={"command": "ls -l"})
    recorder.emit(
        "tool_result",
        tool="run_bash",
        tool_use_id="ls-1",
        result_full="total 1\n-rw-r--r-- 1 user user 7 app.py\n",
        bytes=41,
        tokens=10,
        latency_ms=1,
        status="ok",
    )
    recorder.emit(
        "assistant_step",
        assistant_text="Here is the list of files.",
        tool_calls=[],
        stop_reason="end_turn",
    )

    from vg_agent.__main__ import _literal_tool_outputs

    outputs = _literal_tool_outputs(recorder.events, 0, "list all files", "Here is the list of files.")
    assert outputs == ["Tool output (ls -l):\ntotal 1\n-rw-r--r-- 1 user user 7 app.py"]


def test_literal_tool_output_keeps_file_read_echoed_in_answer(tmp_path: Path) -> None:
    """A ``show <file>`` read still surfaces its panel even when the model
    pastes the same content into its prose answer."""
    recorder = TraceRecorder(tmp_path)
    file_body = "from auth.middleware import require_auth\n\ndef foo():\n    return 1"
    recorder.emit("user_prompt", prompt="show app.py")
    recorder.emit("tool_call", tool="read_file", tool_use_id="read-app", args={"path": "app.py"})
    recorder.emit(
        "tool_result",
        tool="read_file",
        tool_use_id="read-app",
        result_full=file_body,
        bytes=len(file_body.encode()),
        tokens=20,
        latency_ms=1,
        status="ok",
    )
    answer = f"Here is the contents of `app.py`:\n\n```python\n{file_body}\n```\n\nIt defines `foo`."
    recorder.emit("assistant_step", assistant_text=answer, tool_calls=[], stop_reason="end_turn")

    from vg_agent.__main__ import _literal_tool_outputs

    outputs = _literal_tool_outputs(recorder.events, 0, "show app.py", answer)
    assert len(outputs) == 1
    assert outputs[0].startswith("Tool output (app.py):\n")
    assert "def foo():" in outputs[0]


def test_literal_tool_output_still_suppresses_run_bash_echoed_in_answer(tmp_path: Path) -> None:
    """Non-file tools (run_bash) remain suppressed when the answer quotes them."""
    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="grep foo")
    recorder.emit("tool_call", tool="run_bash", tool_use_id="bash-1", command="grep foo app.py", args={})
    recorder.emit(
        "tool_result",
        tool="run_bash",
        tool_use_id="bash-1",
        result_full="app.py:def foo():",
        bytes=18,
        tokens=8,
        latency_ms=1,
        status="ok",
    )
    answer = "I found one match: app.py:def foo():"
    recorder.emit("assistant_step", assistant_text=answer, tool_calls=[], stop_reason="end_turn")

    from vg_agent.__main__ import _literal_tool_outputs

    outputs = _literal_tool_outputs(recorder.events, 0, "grep foo", answer)
    assert outputs == []


def test_literal_tool_output_includes_read_errors(tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="read .env")
    recorder.emit("tool_call", tool="read_file", tool_use_id="read-env", args={"path": ".env"})
    recorder.emit(
        "tool_result",
        tool="read_file",
        tool_use_id="read-env",
        result_full="sensitive path '.env' is on the read/write denylist",
        bytes=52,
        tokens=8,
        latency_ms=1,
        status="error",
    )
    recorder.emit(
        "assistant_step",
        assistant_text="I could not read that file.",
        tool_calls=[],
        stop_reason="end_turn",
    )

    from vg_agent.__main__ import _format_progress_event, _literal_tool_outputs, _progress_event_color

    outputs = _literal_tool_outputs(recorder.events, 0, "read .env", "I could not read that file.")
    assert outputs
    assert outputs[0].startswith("Blocked (.env):\n")
    assert ".env.example" in outputs[0]
    tool_event = next(event for event in recorder.events if event["kind"] == "tool_result")
    progress = str(_format_progress_event(tool_event))
    assert "sensitive path" in progress
    assert ".env.example" in progress
    assert _progress_event_color(tool_event, use_color=True) == "\x1b[31m"


def test_chat_persists_budget_and_approvals_across_turns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # In-process chat over the live loop with an injected fake client (no network):
    # turn 1 renames foo to bar via a Coder (auto-yes), then /budget, /approvals, /exit.
    from vg_agent import __main__ as cli

    write_fixture(tmp_path)
    prompts = iter([
        "rename foo to bar in app.py",
        "/budget",
        "/approvals",
        "/exit",
    ])
    monkeypatch.setattr(cli, "use_rich_ui", lambda: False)
    monkeypatch.setattr(cli, "_make_chat_prompt", lambda _history_path: (lambda: next(prompts), lambda: None))
    monkeypatch.setattr(
        cli, "LiveModelClient", SimpleNamespace(from_env=lambda recorder=None: _rename_via_coder_client())
    )

    args = SimpleNamespace(no_redact=False, require_approval="writes", yes=True, live_model=True)
    assert cli._chat_loop(tmp_path, args) == 0

    out = capsys.readouterr().out
    assert "steps" in out  # /budget
    assert "Set caps:" in out
    assert "renamed foo to bar in app.py." in out  # parent final answer
    assert "Approvals - session history" in out  # /approvals
    assert "edit_file" in out
    assert "app.py" in out

    trace_dir = tmp_path / "traces"
    traces = list(trace_dir.glob("*.jsonl"))
    assert len(traces) == 1
    events = read_events(traces[0])
    session_ids = {e.get("session_id") for e in events}
    assert len(session_ids) == 1
    approvals = [e for e in events if e["kind"] == "approval"]
    assert any(a["decision"] == "auto" for a in approvals)


def test_chat_budget_slash_sets_caps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from vg_agent import __main__ as cli

    write_fixture(tmp_path)
    prompts = iter(
        [
            "/budget steps 100 tokens 200000 usd 10 daily 8",
            "/budget",
            "/exit",
        ]
    )
    monkeypatch.setattr(cli, "use_rich_ui", lambda: False)
    monkeypatch.setattr(cli, "_make_chat_prompt", lambda _history_path: (lambda: next(prompts), lambda: None))
    monkeypatch.setattr(
        cli, "LiveModelClient", SimpleNamespace(from_env=lambda recorder=None: _rename_via_coder_client())
    )

    args = SimpleNamespace(no_redact=False, require_approval="writes", yes=True, live_model=True)
    assert cli._chat_loop(tmp_path, args) == 0

    out = capsys.readouterr().out
    assert "steps 0/100" in out
    assert "session_tokens 0/200000" in out
    assert "usd 0.00/10.00" in out
    assert "daily_remaining 8.00" in out

    traces = list((tmp_path / "traces").glob("*.jsonl"))
    events = read_events(traces[0])
    config_events = [e for e in events if e.get("kind") == "budget_event" and e.get("budget_reason") == "user_config"]
    assert len(config_events) == 1
    assert config_events[0]["details"] == {
        "max_steps": 100,
        "max_tokens": 200000,
        "max_usd": 10.0,
        "daily_remaining_usd": 8.0,
    }


def test_chat_slash_reset_emits_event(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["VG_WORKSPACE_ROOT"] = "."
    stdin_text = "/reset\n/exit\n"
    completed = subprocess.run(
        [sys.executable, "-m", "vg_agent", "--chat"],
        cwd=tmp_path,
        env=env,
        input=stdin_text,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr
    trace_dir = tmp_path / "traces"
    traces = list(trace_dir.glob("*.jsonl"))
    assert len(traces) == 1
    events = read_events(traces[0])
    assert any(e["kind"] == "session_reset" for e in events)




def test_chat_ui_status_bar_segments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vg_agent import chat_ui
    from vg_agent.chat_ui import build_status_bar_text

    monkeypatch.setattr(chat_ui, "use_emoji", lambda: True)

    recorder = TraceRecorder(tmp_path)
    guard = BudgetGuard.for_workspace(tmp_path)
    recorder.emit(
        "llm_start",
        agent_id="parent",
        model="openrouter/anthropic/claude-haiku-4.5",
        tokens_in=4200,
    )
    recorder.emit("run_end", final_status="ready")
    line = build_status_bar_text(
        root=tmp_path,
        recorder=recorder,
        guard=guard,
        live_model=True,
        since_event_idx=0,
    )
    assert "\U0001f4c1" in line
    assert "claude-haiku-4.5" in line
    assert "live" in line
    assert "ctx 4.2k" in line
    assert "\u2713 ready" in line

    recorder.emit("tool_result", agent_id="parent", tool="read_file", status="error", result_full="nope")
    recorder.emit("run_end", final_status="tool_error")
    turn_line = build_status_bar_text(
        root=tmp_path,
        recorder=recorder,
        guard=guard,
        live_model=True,
        since_event_idx=2,
    )
    assert "\u2717" in turn_line
    assert "tool_error" in turn_line


def test_chat_status_shows_partial_when_subagent_failed_but_run_ok(tmp_path: Path) -> None:
    from vg_agent.chat_ui import build_status_bar_text

    recorder = TraceRecorder(tmp_path)
    guard = BudgetGuard.for_workspace(tmp_path)
    start = len(recorder.events)
    recorder.emit("subagent_return", child_agent_id="coder-1", status="tool_error", summary="mkdir failed")
    recorder.emit("assistant_step", agent_id="parent", step_idx=1, assistant_text="partial", tool_calls=[])
    recorder.emit("run_end", final_status="ok")
    line = build_status_bar_text(
        root=tmp_path,
        recorder=recorder,
        guard=guard,
        live_model=True,
        since_event_idx=start,
    )
    assert "\u2717" in line
    assert "partial" in line


def test_chat_ui_session_status_emits_statusline(tmp_path: Path) -> None:
    from vg_agent.chat_ui import build_session_status, emit_session_statusline

    recorder = TraceRecorder(tmp_path)
    guard = BudgetGuard.for_workspace(tmp_path)
    recorder.emit("user_prompt", prompt="hello")
    recorder.emit(
        "assistant_step",
        agent_id="parent",
        step_idx=1,
        model=config.PARENT_MODEL_ID,
        tokens_in=100,
        tokens_out=20,
        assistant_text="hi",
        tool_calls=[],
    )
    guard.record_model_call(config.PARENT_MODEL_ID, 100, 20)
    status = build_session_status(
        root=tmp_path,
        recorder=recorder,
        guard=guard,
        live_model=True,
    )
    emit_session_statusline(recorder, status)
    statuslines = [event for event in recorder.events if event.get("kind") == "statusline"]
    assert len(statuslines) == 1
    assert statuslines[0]["text"].startswith("[live]")


def test_chat_ui_running_state(tmp_path: Path) -> None:
    from vg_agent.chat_ui import build_status_bar_text

    recorder = TraceRecorder(tmp_path)
    guard = BudgetGuard.for_workspace(tmp_path)
    line = build_status_bar_text(
        root=tmp_path,
        recorder=recorder,
        guard=guard,
        live_model=True,
        force_state="running",
    )
    assert "running" in line
    assert "\u2026" in line


QWEN_CODER_MODEL_ID = "openrouter/qwen/qwen3-coder-30b-a3b-instruct"


def test_qwen_pricing_preflight_not_unknown_fallback() -> None:
    guard = BudgetGuard()
    cost = guard.estimate_cost(QWEN_CODER_MODEL_ID, 512, 4096)
    assert cost == pytest.approx(0.00114176, rel=1e-6)
    unknown = guard.estimate_cost("openrouter/unknown/example-model", 512, 4096)
    assert unknown > 0.5
    assert cost < 0.01


UNPRICED_MODEL_ID = "openrouter/example/unpriced-model"


def test_unpriced_model_statusline_no_next_dollar_estimate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vg_agent import chat_ui
    from vg_agent.chat_ui import build_session_status, build_status_bar_text

    monkeypatch.setattr(chat_ui, "use_emoji", lambda: True)
    recorder = TraceRecorder(tmp_path)
    guard = BudgetGuard(max_steps=15, max_tokens=80_000, max_usd=0.0001)
    recorder.emit("llm_start", model=UNPRICED_MODEL_ID, step_idx=0, tokens_in=0)
    status = build_session_status(
        root=tmp_path, recorder=recorder, guard=guard, live_model=True
    )
    assert not status.model_priced
    assert not status.usd_would_exceed
    assert status.usd_projected is None
    bar = build_status_bar_text(
        root=tmp_path, recorder=recorder, guard=guard, live_model=True
    )
    assert "(next ~$" not in bar
    assert "(unpriced model)" in bar


def test_qwen_statusline_no_false_usd_cap_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vg_agent import chat_ui
    from vg_agent.chat_ui import build_session_status, build_status_bar_text

    monkeypatch.setattr(chat_ui, "use_emoji", lambda: True)
    recorder = TraceRecorder(tmp_path)
    guard = BudgetGuard(max_steps=15, max_tokens=80_000, max_usd=0.50)
    recorder.emit("llm_start", model=QWEN_CODER_MODEL_ID, step_idx=0, tokens_in=0)
    status = build_session_status(
        root=tmp_path, recorder=recorder, guard=guard, live_model=True
    )
    assert not status.usd_would_exceed
    assert status.usd_projected is not None
    assert status.usd_projected < status.max_usd
    bar = build_status_bar_text(
        root=tmp_path, recorder=recorder, guard=guard, live_model=True
    )
    assert "(next ~$" not in bar
    assert "\u26a0" not in bar


def test_chat_ui_budget_warning_icon_when_next_step_exceeds_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vg_agent import chat_ui
    from vg_agent.chat_ui import (
        build_session_status,
        build_status_bar_text,
        format_budget_cap_approval_text,
        format_statusline_compact,
    )
    from vg_agent.__main__ import _chat_statusline_color, _format_chat_statusline

    monkeypatch.setattr(chat_ui, "use_emoji", lambda: True)

    recorder = TraceRecorder(tmp_path)
    guard = BudgetGuard(max_steps=15, max_tokens=80_000, max_usd=0.0001)
    recorder.emit("llm_start", model=config.PARENT_MODEL_ID, step_idx=0, tokens_in=100)
    status = build_session_status(
        root=tmp_path, recorder=recorder, guard=guard, live_model=True
    )
    assert status.usd_would_exceed
    assert status.usd_projected is not None
    assert status.usd_projected > status.max_usd

    bar = build_status_bar_text(
        root=tmp_path, recorder=recorder, guard=guard, live_model=True
    )
    assert "\u26a0" in bar
    assert "(next ~$" in bar

    compact = format_statusline_compact(status, width=240)
    assert compact.startswith("[live]")
    assert "!usd" in compact
    assert "(next ~$" in compact

    line = _format_chat_statusline(recorder, guard, live_model=True, width=240)
    colored = _chat_statusline_color(line, use_color=True)
    assert colored.startswith("\x1b[31m[live]")

    body = format_budget_cap_approval_text(
        "usd_cap",
        {
            "max_usd": 0.0001,
            "running_usd": 0.0,
            "worst_next_usd": 0.0017,
        },
    )
    assert "exceed your USD cap" in body
    assert "Cap (--max-usd)" in body
    assert "$0.0001" in body
    assert "$0.0017" in body
    assert "Cap (--max-usd):     $0.0001" in body
    assert "Total after step" in body


def test_clear_chat_screen_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from vg_agent import chat_ui

    cleared: list[bool] = []

    class FakeConsole:
        def clear(self) -> None:
            cleared.append(True)

    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)
    monkeypatch.setenv("VG_CHAT_NO_CLEAR", "1")
    monkeypatch.setattr(chat_ui, "_console", lambda: FakeConsole())
    chat_ui.clear_chat_screen()
    assert cleared == []


def test_clear_chat_screen_noop_when_not_rich(monkeypatch: pytest.MonkeyPatch) -> None:
    from vg_agent import chat_ui

    cleared: list[bool] = []

    class FakeConsole:
        def clear(self) -> None:
            cleared.append(True)

    monkeypatch.delenv("VG_CHAT_NO_CLEAR", raising=False)
    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: False)
    monkeypatch.setattr(chat_ui, "_console", lambda: FakeConsole())
    chat_ui.clear_chat_screen()
    assert cleared == []


def test_clear_chat_screen_clears_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from vg_agent import chat_ui

    cleared: list[bool] = []
    scrollback: list[str] = []

    class FakeFile(io.StringIO):
        pass

    class FakeConsole:
        file = FakeFile()

        def clear(self) -> None:
            cleared.append(True)

    monkeypatch.delenv("VG_CHAT_NO_CLEAR", raising=False)
    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)
    monkeypatch.setattr(chat_ui, "_console", lambda: FakeConsole())
    chat_ui.clear_chat_screen()
    assert cleared == [True]
    assert FakeConsole.file.getvalue() == "\033[3J"


def test_print_chat_dashboard_cleared_shows_trace_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vg_agent import chat_ui
    from vg_agent.budget import BudgetGuard
    from vg_agent.trace import TraceRecorder

    printed: list[str] = []

    class FakeConsole:
        def print(self, text: str = "", **kwargs: object) -> None:
            printed.append(str(text))

        def clear(self) -> None:
            pass

        file = type("F", (), {"write": lambda *_a, **_k: None, "flush": lambda *_a, **_k: None})()

    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)
    monkeypatch.setattr(chat_ui, "_console", lambda: FakeConsole())
    monkeypatch.setattr(chat_ui, "clear_chat_screen", lambda **_k: None)
    monkeypatch.setattr(
        chat_ui,
        "print_chat_dashboard",
        lambda **_k: printed.append("dashboard"),
    )
    recorder = TraceRecorder(tmp_path, run_id="abc123", sqlite_enabled=False)
    chat_ui.print_chat_dashboard_cleared(
        root=tmp_path,
        recorder=recorder,
        guard=BudgetGuard.for_workspace(tmp_path),
        live_model=False,
        show_trace_path=True,
    )
    assert "dashboard" in printed
    assert any("traces/abc123.jsonl" in line for line in printed)


def test_print_chat_status_report_writes_stdout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from vg_agent import __main__ as cli
    from vg_agent.budget import BudgetGuard
    from vg_agent.trace import TraceRecorder

    recorder = TraceRecorder(tmp_path, run_id="run1", sqlite_enabled=False)
    recorder.emit("run_end", final_status="ok")
    guard = BudgetGuard.for_workspace(tmp_path)
    args = SimpleNamespace(live_model=True)
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)
    cli._print_chat_status_report(recorder, guard, args, since_event_idx=0)
    out = buffer.getvalue()
    assert "steps " in out
    assert "trace:" in out
    assert "last_run: ok" in out


def test_chat_status_slash_command_writes_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from vg_agent import __main__ as cli

    monkeypatch.setattr(cli, "use_rich_ui", lambda: True)
    dashboard_calls: list[bool] = []
    monkeypatch.setattr(
        cli,
        "print_chat_dashboard_cleared",
        lambda **_k: dashboard_calls.append(True),
    )
    monkeypatch.setattr(cli, "render_chat_prompt_ready", lambda **_k: None)
    monkeypatch.setattr(cli, "render_input_bottom_and_footer", lambda **_k: None)

    prompts = iter(["/status", "/exit"])
    monkeypatch.setattr(cli, "_make_chat_prompt", lambda _history_path: (lambda: next(prompts), lambda: None))

    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)

    args = SimpleNamespace(
        no_redact=False,
        require_approval="off",
        yes=False,
        live_model=True,
    )
    assert cli._chat_loop(tmp_path, args) == 0
    assert dashboard_calls
    out = buffer.getvalue()
    assert "steps " in out
    assert "trace:" in out


def test_chat_loop_isolates_read_only_followup_after_denied_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vg_agent import __main__ as cli

    monkeypatch.setattr(cli, "use_rich_ui", lambda: False)
    monkeypatch.setattr(cli.LiveModelClient, "from_env", lambda **_k: object())

    prompts = iter(
        [
            'add function debug_info() to app.py that returns "debug"; make the smallest edit',
            "show app.py",
            "/exit",
        ]
    )
    monkeypatch.setattr(cli, "_make_chat_prompt", lambda _history_path: (lambda: next(prompts), lambda: None))

    history_lengths: list[int] = []

    def fake_run_live_task(
        root: Path,
        task: str,
        recorder: TraceRecorder,
        *,
        client: object,
        guard: BudgetGuard,
        policy: ApprovalPolicy,
        history: list[dict[str, object]],
    ) -> TraceRecorder:
        history_lengths.append(len(history))
        history.append({"role": "user", "content": task})
        recorder.emit("user_prompt", prompt=task, live_model=True)
        if task.startswith("add function"):
            recorder.emit(
                "approval",
                tool="spawn_subagent",
                tool_use_id="spawn-1",
                decision="denied",
                reason="user no",
            )
            recorder.emit("run_end", final_status="tool_error", total_tokens=1, total_cost_usd=0.0)
        else:
            recorder.emit(
                "assistant_step",
                agent_id="parent",
                model="fake",
                model_id="fake",
                step_idx=1,
                assistant_text="app.py contents",
                tool_calls=[],
            )
            recorder.emit("run_end", final_status="ok", total_tokens=1, total_cost_usd=0.0)
        return recorder

    monkeypatch.setattr(cli, "run_live_task", fake_run_live_task)

    args = SimpleNamespace(
        no_redact=False,
        require_approval="off",
        yes=False,
        live_model=True,
    )
    assert cli._chat_loop(tmp_path, args) == 0
    assert history_lengths == [0, 0]


def test_read_only_followup_isolation_predicate() -> None:
    from vg_agent import __main__ as cli

    assert cli._should_isolate_read_only_followup(
        "show app.py", previous_mutation_blocked=True
    )
    assert cli._should_isolate_read_only_followup(
        "show the contents of app.py", previous_mutation_blocked=True
    )
    assert not cli._should_isolate_read_only_followup(
        "show app.py and add debug_info", previous_mutation_blocked=True
    )
    assert not cli._should_isolate_read_only_followup(
        "show app.py", previous_mutation_blocked=False
    )


def test_chat_ui_non_tty_skips_rich(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vg_agent import __main__ as cli

    monkeypatch.setattr(cli, "use_rich_ui", lambda: False)

    prompts = iter(["/exit"])

    monkeypatch.setattr(cli, "_make_chat_prompt", lambda _history_path: (lambda: next(prompts), lambda: None))

    args = SimpleNamespace(
        no_redact=False,
        require_approval="off",
        yes=False,
        live_model=False,
    )
    assert cli.use_rich_ui() is False
    assert cli._chat_loop(tmp_path, args) == 0


def test_chat_ui_turn_output_plain_on_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from vg_agent import chat_ui

    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)
    assert chat_ui.print_turn_output(answer="Hello", literal_outputs=["./auth"]) is True
    out = buffer.getvalue()
    assert "Hello" in out
    assert "./auth" in out
    assert "\u2500" not in out
    assert "Response" not in out


def test_chat_ui_renders_file_literal_output_as_file_panel(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from vg_agent import chat_ui

    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)
    assert (
        chat_ui.print_turn_output(
            answer="Here is app.py",
            literal_outputs=[
                "Tool output (app.py):\n"
                "from auth.middleware import require_auth\n"
                "\n"
                "def foo():\n"
                "    return 1\n"
            ],
        )
        is True
    )
    out = buffer.getvalue()
    assert "File app.py" in out
    assert "from auth.middleware import require_auth" in out
    assert "    return 1" in out


def test_chat_ui_keeps_file_literal_output_even_if_answer_mentions_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import io

    from vg_agent import chat_ui

    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)
    assert (
        chat_ui.print_turn_output(
            answer="from auth.middleware import require_auth\n    return 1",
            literal_outputs=[
                "Tool output (app.py):\n"
                "from auth.middleware import require_auth\n"
                "def foo():\n"
                "    return 1\n"
            ],
        )
        is True
    )
    assert "File app.py" in buffer.getvalue()


def test_chat_ui_strips_duplicate_file_code_block_from_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the file is shown in its own panel, the duplicate fenced block in the
    answer prose is removed but the surrounding prose is kept."""
    import io

    from vg_agent import chat_ui

    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)
    body = "from auth.middleware import require_auth\n\ndef foo():\n    return 1"
    answer = f"Here is the contents of app.py:\n\n```python\n{body}\n```\n\nIt defines foo."
    assert (
        chat_ui.print_turn_output(
            answer=answer,
            literal_outputs=[f"Tool output (app.py):\n{body}\n"],
        )
        is True
    )
    out = buffer.getvalue()
    assert "File app.py" in out  # rich panel rendered
    assert "Here is the contents of app.py" in out  # intro prose kept
    assert "It defines foo" in out  # trailing prose kept
    # The fenced ``` markers from the duplicated block are gone (panel is sole source).
    assert "```" not in out


def test_strip_redundant_file_code_blocks_keeps_unrelated_blocks() -> None:
    from vg_agent.chat_ui import _strip_redundant_file_code_blocks

    body = "def foo():\n    return 1"
    answer = (
        f"The file says:\n\n```python\n{body}\n```\n\n"
        "But you should change it to:\n\n```python\ndef bar():\n    return 2\n```"
    )
    stripped = _strip_redundant_file_code_blocks(answer, [body])
    assert "def foo()" not in stripped
    assert "def bar()" in stripped  # unrelated suggestion block preserved
    assert "But you should change it to:" in stripped


def test_chat_ui_turn_output_plain_when_non_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from vg_agent import chat_ui

    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: False)
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)
    assert chat_ui.print_turn_output(answer="Hello", literal_outputs=["./auth"]) is True
    out = buffer.getvalue()
    assert out == "Hello\n./auth\n"
    assert "\u2500" not in out


def test_format_response_bullets_multiline() -> None:
    from vg_agent.chat_ui import format_response_bullets

    assert format_response_bullets("only one line") == "only one line"
    assert format_response_bullets("alpha\nbeta") == "• alpha\n• beta"
    assert format_response_bullets("- item one\nitem two") == "- item one\n• item two"
    assert format_response_bullets("1. first\nsecond") == "1. first\n• second"


def test_render_input_top_rule_spacing(monkeypatch: pytest.MonkeyPatch) -> None:
    from vg_agent import chat_ui

    printed: list[object] = []

    class FakeConsole:
        def print(self, *args: object, **kwargs: object) -> None:
            printed.append((args, kwargs))

    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)
    monkeypatch.setattr(chat_ui, "_console", lambda: FakeConsole())
    chat_ui.render_input_top_rule()
    assert len(printed) == 3
    assert printed[0] == ((), {})
    assert printed[1] == ((), {})
    rule_arg = printed[2][0][0]
    assert getattr(rule_arg, "title", None) == "input"


def test_chat_ui_turn_output_multiline_bullets(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from vg_agent import chat_ui

    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)
    assert chat_ui.print_turn_output(answer="line one\nline two", literal_outputs=[]) is True
    out = buffer.getvalue()
    assert "Response" in out
    assert "line one" in out
    assert "line two" in out


def test_chat_ui_rich_answer_renders_markdown_table(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from vg_agent import chat_ui

    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)
    answer = (
        "## Combined Findings\n\n"
        "| Priority | Issue | Fix |\n"
        "| --- | --- | --- |\n"
        "| High | Missing auth | Add middleware |\n"
    )
    assert chat_ui.print_turn_output(answer=answer, literal_outputs=[]) is True
    out = buffer.getvalue()
    assert "Response" in out
    assert "Combined Findings" in out
    assert "Missing auth" in out


def test_looks_like_markdown_detects_tables_and_headings() -> None:
    from vg_agent.chat_ui import _looks_like_markdown

    assert _looks_like_markdown("## Title\n\n| A | B |\n|---|---|\n| 1 | 2 |")
    assert not _looks_like_markdown("only one line")
    assert _looks_like_markdown("- bullet one\n- bullet two")


def test_plain_prose_to_markdown_converts_multiline() -> None:
    from vg_agent.chat_ui import _plain_prose_to_markdown

    assert _plain_prose_to_markdown("single") == "single"
    assert _plain_prose_to_markdown("alpha\nbeta") == "- alpha\n- beta"


def test_print_turn_review_rich_answer_panel(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import io

    from vg_agent import chat_ui
    from vg_agent.trace import TraceRecorder

    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)
    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="summarise")
    recorder.emit(
        "assistant_step",
        agent_id="parent",
        assistant_text="## Findings\n\n| Priority | Issue |\n| --- | --- |\n| High | Fix auth |",
        tool_calls=[],
        stop_reason="end_turn",
    )
    chat_ui.print_turn_review(recorder.events, trace_path=recorder.path)
    out = buffer.getvalue()
    assert "=== Turn 1 review ===" in out
    assert "Response" in out
    assert "Findings" in out
    assert "Fix auth" in out


def test_print_finops_rich_table(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import io

    from vg_agent import chat_ui
    from vg_agent.budget import BudgetGuard
    from vg_agent.trace import TraceRecorder

    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)
    guard = BudgetGuard(max_tokens=10_000, max_usd=1.0)
    guard.record_model_call("parent-model", 10, 5, cost_usd=0.01, agent_type="parent")
    recorder = TraceRecorder(tmp_path)
    chat_ui.print_finops_report(
        guard=guard,
        agent_types=["parent"],
        tool_counts={"parent": 0},
        user_prompts=0,
        parallel_lines=[],
    )
    out = buffer.getvalue()
    assert "FinOps" in out
    assert "parent" in out
    assert "TOTAL" in out


def test_print_show_context_overview_rich_table(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from vg_agent import chat_ui

    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)
    events = [
        {
            "kind": "assistant_step",
            "agent_id": "parent",
            "step_idx": 1,
            "tool_calls": [{"name": "read_file", "args": {"path": "app.py"}}],
        }
    ]
    chat_ui.print_show_context_overview(events)
    out = buffer.getvalue()
    assert "Parent context overview" in out
    assert "read_file" in out or "app.py" in out


def test_build_turn_review_sections_extracts_answer(tmp_path: Path) -> None:
    from vg_agent.trace import TraceRecorder, build_turn_review_sections

    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="go")
    recorder.emit(
        "assistant_step",
        agent_id="parent",
        assistant_text="Final answer text.",
        tool_calls=[],
        stop_reason="end_turn",
    )
    sections = build_turn_review_sections(recorder.events)
    assert sections.error is None
    assert sections.answer == "Final answer text."


def test_format_unified_diff_includes_plus_minus_lines() -> None:
    from vg_agent.chat_ui import format_unified_diff

    lines, truncated = format_unified_diff("foo\nbar", "foo\nbaz", path="app.py")
    assert any(line.startswith("-bar") for line in lines)
    assert any(line.startswith("+baz") for line in lines)
    assert not truncated


def test_format_unified_diff_truncates_large_hunks() -> None:
    from vg_agent.chat_ui import DIFF_MAX_LINES, format_unified_diff

    old = "\n".join(f"line-{index}" for index in range(80))
    new = "\n".join(f"line-{index}" for index in range(80, 160))
    lines, truncated = format_unified_diff(old, new, path="big.txt", max_lines=DIFF_MAX_LINES)
    assert truncated
    assert any("more lines" in line for line in lines)
    assert len(lines) == DIFF_MAX_LINES + 1


def test_collect_file_changes_edit_and_write(tmp_path: Path) -> None:
    from vg_agent.chat_ui import collect_file_changes

    target = tmp_path / "app.py"
    target.write_text("before\n", encoding="utf-8")
    events = [
        {
            "kind": "tool_call",
            "tool_use_id": "e1",
            "tool": "edit_file",
            "args": {"path": "app.py", "old": "before", "new": "after"},
        },
        {"kind": "tool_result", "tool_use_id": "e1", "tool": "edit_file", "status": "ok"},
        {
            "kind": "tool_call",
            "tool_use_id": "w1",
            "tool": "write_file",
            "args": {"path": "new.txt", "content": "fresh\n"},
        },
        {"kind": "tool_result", "tool_use_id": "w1", "tool": "write_file", "status": "ok"},
    ]
    changes = collect_file_changes(events, 0, workspace_root=tmp_path, pending_priors={"w1": ""})
    paths = {change.path for change in changes}
    assert paths == {"app.py", "new.txt"}
    edit = next(change for change in changes if change.path == "app.py")
    assert edit.old == "before" and edit.new == "after"


def test_chat_ui_status_bar_throttled_while_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vg_agent import chat_ui

    printed: list[object] = []

    class FakeConsole:
        def print(self, *args: object, **kwargs: object) -> None:
            printed.append(args)

    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)
    monkeypatch.setattr(chat_ui, "_STATUS_THROTTLE_S", 10.0)
    monkeypatch.setattr(chat_ui, "_console", lambda: FakeConsole())
    monkeypatch.setattr(chat_ui, "_last_status_bar_refresh", 1e9)
    from vg_agent.budget import BudgetGuard
    from vg_agent.trace import TraceRecorder

    recorder = TraceRecorder(tmp_path)
    guard = BudgetGuard.for_workspace(tmp_path)
    kwargs = {
        "root": tmp_path,
        "recorder": recorder,
        "guard": guard,
        "live_model": True,
        "since_event_idx": 0,
        "force_state": "running",
    }
    chat_ui.refresh_chat_status_bar(**kwargs)
    assert not printed
    monkeypatch.setattr(chat_ui, "_last_status_bar_refresh", 0.0)
    chat_ui.refresh_chat_status_bar(**kwargs)
    assert len(printed) == 1
    printed.clear()
    chat_ui.refresh_chat_status_bar(**kwargs, force=True)
    assert len(printed) > 1


def test_render_chat_prompt_ready_redraws_status_hint_and_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vg_agent import chat_ui

    printed: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class FakeConsole:
        def print(self, *args: object, **kwargs: object) -> None:
            printed.append((args, kwargs))

    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)
    monkeypatch.setattr(chat_ui, "_console", lambda: FakeConsole())
    from vg_agent.budget import BudgetGuard
    from vg_agent.trace import TraceRecorder

    recorder = TraceRecorder(tmp_path, sqlite_enabled=False)
    guard = BudgetGuard.for_workspace(tmp_path)
    chat_ui.render_chat_prompt_ready(
        root=tmp_path,
        recorder=recorder,
        guard=guard,
        live_model=True,
        since_event_idx=0,
    )

    assert len(printed) >= 5
    assert any("/help for commands" in str(args[0]) for args, _kwargs in printed if args)
    assert any(getattr(args[0], "title", None) == "input" for args, _kwargs in printed if args)


def test_chat_ui_turn_output_skips_progress_shown_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import io

    from vg_agent import chat_ui

    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)
    events = [
        {
            "kind": "tool_call",
            "tool_use_id": "e1",
            "tool": "edit_file",
            "args": {"path": "app.py", "old": "foo", "new": "bar"},
        },
        {"kind": "tool_result", "tool_use_id": "e1", "tool": "edit_file", "status": "ok"},
    ]
    assert (
        chat_ui.print_turn_output(
            answer="done",
            literal_outputs=[],
            events=events,
            start_idx=0,
            workspace_root=tmp_path,
            skip_change_paths={"app.py"},
        )
        is True
    )
    out = buffer.getvalue()
    assert "done" in out
    assert "Changes:" not in out


def test_chat_ui_turn_output_includes_edit_diff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from vg_agent import chat_ui

    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)
    events = [
        {
            "kind": "tool_call",
            "tool_use_id": "e1",
            "tool": "edit_file",
            "args": {"path": "app.py", "old": "foo", "new": "bar"},
        },
        {"kind": "tool_result", "tool_use_id": "e1", "tool": "edit_file", "status": "ok"},
    ]
    assert (
        chat_ui.print_turn_output(
            answer="Done.",
            literal_outputs=[],
            events=events,
            start_idx=0,
            workspace_root=tmp_path,
        )
        is True
    )
    out = buffer.getvalue()
    assert "-foo" in out or "-foo\n" in out
    assert "+bar" in out or "+bar\n" in out
    assert "app.py" in out


def test_progress_sink_prints_edit_diff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from io import StringIO

    from vg_agent import __main__ as cli

    buffer = StringIO()
    turn_state: dict[str, object] = {}
    monkeypatch.setattr(cli, "use_rich_ui", lambda: True)
    sink = cli._make_progress_sink(stream=buffer, turn_state=turn_state, workspace_root=tmp_path)
    sink(
        {
            "kind": "tool_call",
            "tool_use_id": "e1",
            "tool": "edit_file",
            "args": {"path": "x.py", "old": "a", "new": "b"},
        }
    )
    sink({"kind": "tool_result", "tool_use_id": "e1", "tool": "edit_file", "status": "ok"})
    out = buffer.getvalue()
    assert "--- a/x.py" in out
    assert "+b" in out
    assert turn_state.get("progress_diff_paths") == {"x.py"}


def test_progress_sink_spawn_subagents_parallel_summary(tmp_path: Path) -> None:
    from io import StringIO

    from vg_agent import __main__ as cli
    from vg_agent.trace import TraceRecorder

    spawn_payload = json.dumps(
        [
            {"agent_id": "explorer.0", "status": "ok"},
            {"agent_id": "explorer.1", "status": "ok"},
        ]
    )
    buffer = StringIO()
    recorder = TraceRecorder(tmp_path, event_sink=None)
    recorder.event_sink = cli._make_progress_sink(
        stream=buffer,
        turn_state={},
        workspace_root=tmp_path,
        recorder=recorder,
    )
    recorder.emit(
        "subagent_return",
        child_agent_id="explorer.0",
        agent_type="explorer",
        started_at="2026-05-10T12:00:00+00:00",
        ended_at="2026-05-10T12:00:03+00:00",
    )
    recorder.emit(
        "subagent_return",
        child_agent_id="explorer.1",
        agent_type="explorer",
        started_at="2026-05-10T12:00:01+00:00",
        ended_at="2026-05-10T12:00:04+00:00",
    )
    recorder.emit(
        "tool_result",
        tool="spawn_subagents",
        agent_id="parent",
        status="ok",
        result_full=spawn_payload,
    )
    out = buffer.getvalue()
    assert "[parallel]" in out
    assert "2 explorer finished" in out


def test_progress_sink_rich_chat_suppresses_child_noise_keeps_parallel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from io import StringIO

    from vg_agent import __main__ as cli
    from vg_agent.trace import TraceRecorder

    spawn_payload = json.dumps(
        [
            {"agent_id": "explorer.0", "status": "ok"},
            {"agent_id": "explorer.1", "status": "ok"},
        ]
    )
    monkeypatch.delenv("VG_CHAT_VERBOSE_PROGRESS", raising=False)
    buffer = StringIO()
    recorder = TraceRecorder(tmp_path, event_sink=None)
    recorder.event_sink = cli._make_progress_sink(
        stream=buffer,
        turn_state={},
        workspace_root=tmp_path,
        recorder=recorder,
        rich_chat=True,
    )
    recorder.emit(
        "llm_start",
        agent_id="explorer.0",
        agent_type="explorer",
        step_idx=1,
        model="openrouter/google/gemini",
        tokens_in=100,
        max_tokens=200,
    )
    recorder.emit(
        "tool_result",
        agent_id="explorer.0",
        agent_type="explorer",
        tool="read_file",
        status="ok",
        tokens=10,
        latency_ms=1,
    )
    recorder.emit(
        "subagent_return",
        child_agent_id="explorer.0",
        agent_type="explorer",
        status="ok",
        started_at="2026-05-10T12:00:00+00:00",
        ended_at="2026-05-10T12:00:03+00:00",
    )
    recorder.emit(
        "subagent_return",
        child_agent_id="explorer.1",
        agent_type="explorer",
        status="ok",
        started_at="2026-05-10T12:00:01+00:00",
        ended_at="2026-05-10T12:00:04+00:00",
    )
    recorder.emit(
        "tool_result",
        tool="spawn_subagents",
        agent_id="parent",
        status="ok",
        result_full=spawn_payload,
    )
    out = buffer.getvalue()
    assert "[llm] explorer.0" not in out
    assert "[tool] explorer.0 read_file ok" not in out
    assert "[agent] return explorer.0" not in out
    assert "[parallel]" in out
    assert "2 explorer finished" in out


def test_progress_sink_rich_chat_keeps_write_diffs_and_errors(tmp_path: Path) -> None:
    from io import StringIO

    from vg_agent import __main__ as cli

    buffer = StringIO()
    turn_state: dict[str, object] = {}
    sink = cli._make_progress_sink(
        stream=buffer,
        turn_state=turn_state,
        workspace_root=tmp_path,
        rich_chat=True,
    )
    sink(
        {
            "kind": "tool_call",
            "agent_id": "coder-1",
            "agent_type": "coder",
            "tool_use_id": "e1",
            "tool": "edit_file",
            "args": {"path": "x.py", "old": "a", "new": "b"},
        }
    )
    sink(
        {
            "kind": "tool_result",
            "agent_id": "coder-1",
            "agent_type": "coder",
            "tool_use_id": "e1",
            "tool": "edit_file",
            "status": "ok",
            "tokens": 1,
            "latency_ms": 1,
        }
    )
    sink(
        {
            "kind": "tool_result",
            "agent_id": "explorer-1",
            "agent_type": "explorer",
            "tool": "read_file",
            "status": "error",
            "result_full": "missing file",
            "tokens": 1,
            "latency_ms": 1,
        }
    )
    out = buffer.getvalue()
    assert "[tool] coder-1 edit_file ok" in out
    assert "--- a/x.py" in out
    assert "+b" in out
    assert "[tool] explorer-1 read_file error" in out


def test_progress_sink_verbose_env_restores_child_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from io import StringIO

    from vg_agent import __main__ as cli

    monkeypatch.setenv("VG_CHAT_VERBOSE_PROGRESS", "1")
    buffer = StringIO()
    sink = cli._make_progress_sink(stream=buffer, workspace_root=tmp_path, rich_chat=True)
    sink(
        {
            "kind": "llm_start",
            "agent_id": "explorer-1",
            "agent_type": "explorer",
            "step_idx": 1,
            "model": "openrouter/google/gemini",
            "tokens_in": 100,
            "max_tokens": 200,
        }
    )
    assert "[llm] explorer-1 step 1" in buffer.getvalue()


def test_chat_slash_new_starts_fresh_trace_and_live_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vg_agent import __main__ as cli

    prompts = iter(["remember first turn", "/new", "second turn", "/exit"])
    history_lengths: list[int] = []

    def read_prompt() -> str:
        return next(prompts)

    def fake_run_live_task(
        root: Path,
        prompt: str,
        recorder: TraceRecorder,
        *,
        client: object,
        guard: BudgetGuard,
        policy: ApprovalPolicy,
        history: list[dict[str, object]],
    ) -> TraceRecorder:
        history_lengths.append(len(history))
        history.append({"role": "user", "content": prompt})
        recorder.emit("user_prompt", prompt=prompt)
        recorder.emit(
            "assistant_step",
            agent_id="parent",
            step_idx=1,
            assistant_text=f"ack {prompt}",
            tool_calls=[],
            stop_reason="end_turn",
        )
        recorder.emit("run_end", final_status="ok", total_tokens=0, total_cost_usd=0.0, duration_s=0.1)
        return recorder

    monkeypatch.setattr(cli, "_make_chat_prompt", lambda _history_path: (read_prompt, lambda: None))
    monkeypatch.setattr(cli, "LiveModelClient", SimpleNamespace(from_env=lambda recorder=None: object()))
    monkeypatch.setattr(cli, "run_live_task", fake_run_live_task)

    args = SimpleNamespace(
        no_redact=False,
        require_approval="off",
        yes=False,
        live_model=True,
    )
    assert cli._chat_loop(tmp_path, args) == 0
    assert history_lengths == [0, 0]

    traces = sorted((tmp_path / "traces").glob("*.jsonl"))
    assert len(traces) == 2
    loaded = [read_events(path) for path in traces]
    first_trace = next(events for events in loaded if any(e.get("prompt") == "remember first turn" for e in events))
    second_trace = next(events for events in loaded if any(e["kind"] == "session_new" for e in events))
    assert not any(e["kind"] == "session_new" for e in first_trace)
    assert any(e.get("prompt") == "second turn" for e in second_trace)
    assert not any(e.get("prompt") == "remember first turn" for e in second_trace)


def test_parent_tool_schemas_include_run_tests() -> None:
    names = {schema["name"] for schema in PARENT_TOOL_SCHEMAS}
    assert "run_tests" in names
    assert "write_file" not in names


def test_run_tests_blocks_non_test_paths(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    assert validate_run_tests_path(tmp_path, "app.py") is not None
    assert validate_run_tests_path(tmp_path, "../outside.py") is not None
    result = run_tests(tmp_path, "app.py", "bad-path")
    assert result["status"] == "error"
    assert "run_tests blocked" in str(result["result_full"])


def test_run_tests_runs_pytest_on_test_file(tmp_path: Path) -> None:
    test_dir = tmp_path / "tkinter_calc"
    test_dir.mkdir()
    (test_dir / "test_sample.py").write_text(
        "def test_ok():\n    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )
    result = run_tests(tmp_path, "tkinter_calc/test_sample.py", "pytest-1")
    assert result["status"] == "ok", result["result_full"]
    (test_dir / "test_fail.py").write_text(
        "def test_bad():\n    assert False\n",
        encoding="utf-8",
    )
    fail = run_tests(tmp_path, "tkinter_calc/test_fail.py", "pytest-2")
    assert fail["status"] == "error"


def test_coder_read_only_exit_is_tool_error(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "Spawn coder to add tests.",
                [ToolCall("spawn", "spawn_subagent", {"type": "coder", "question": "add test_foo.py"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("Coder did not write.", input_tokens=100, output_tokens=20),
        ],
        by_type={
            "coder": [
                ModelTurn(
                    "Read only.",
                    [ToolCall("read", "read_file", {"path": "app.py"})],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn("app.py looks fine.", input_tokens=40, output_tokens=10),
            ],
        },
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "add tests for app.py", recorder, client=client)
    returns = [e for e in read_events(recorder.path) if e["kind"] == "subagent_return" and e["agent_type"] == "coder"]
    assert returns
    assert returns[-1]["status"] == "tool_error"
    assert returns[-1]["writes_ok"] == 0


def test_coder_empty_turn_retries_then_writes_successfully(tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    client = FakeClient(
        [
            ModelTurn("", input_tokens=20, output_tokens=1),
            ModelTurn(
                "",
                [ToolCall("write-1", "write_file", {"path": "calc3/calculator.py", "content": "print('ok')\n"})],
                stop_reason="tool_use",
                input_tokens=30,
                output_tokens=20,
            ),
            ModelTurn(
                "calc3/calculator.py: created file; replaced 0 occurrence(s)",
                input_tokens=15,
                output_tokens=10,
            ),
        ]
    )
    guard = BudgetGuard(max_steps=20, max_tokens=1_000_000, max_usd=10.0, daily_remaining_usd=10.0)
    policy = ApprovalPolicy(mode="off")

    summary, status, writes_ok, _reads_ok, failure_reason = _run_live_subagent(
        tmp_path,
        "coder",
        "Create calc3/calculator.py",
        recorder,
        client,
        guard,
        child_id="coder-1",
        started=time.perf_counter(),
        policy=policy,
    )

    assert status == "ok"
    assert writes_ok == 1
    assert "calc3/calculator.py" in summary
    assert failure_reason is None
    assert (tmp_path / "calc3" / "calculator.py").exists()
    events = read_events(recorder.path)
    retry_events = [
        e for e in events if e.get("kind") == "budget_event" and e.get("budget_reason") == "subagent_empty_turn_retry"
    ]
    assert retry_events


def test_coder_truncated_turn_retries_then_writes_successfully(tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    client = FakeClient(
        [
            ModelTurn("", stop_reason="length", input_tokens=20, output_tokens=2048),
            ModelTurn(
                "",
                [ToolCall("write-1", "write_file", {"path": "calc4/calculator.py", "content": "print('ok')\n"})],
                stop_reason="tool_use",
                input_tokens=30,
                output_tokens=20,
            ),
            ModelTurn(
                "calc4/calculator.py: created file; replaced 0 occurrence(s)",
                input_tokens=15,
                output_tokens=10,
            ),
        ]
    )
    guard = BudgetGuard(max_steps=20, max_tokens=1_000_000, max_usd=10.0, daily_remaining_usd=10.0)
    policy = ApprovalPolicy(mode="off")

    summary, status, writes_ok, _reads_ok, failure_reason = _run_live_subagent(
        tmp_path,
        "coder",
        "Create calc4/calculator.py",
        recorder,
        client,
        guard,
        child_id="coder-1",
        started=time.perf_counter(),
        policy=policy,
    )

    assert status == "ok"
    assert writes_ok == 1
    assert "calc4/calculator.py" in summary
    assert failure_reason is None
    assert (tmp_path / "calc4" / "calculator.py").exists()
    events = read_events(recorder.path)
    retry_events = [
        e for e in events if e.get("kind") == "budget_event" and e.get("budget_reason") == "subagent_empty_turn_retry"
    ]
    assert retry_events


def test_subagent_wall_clock_timeout_reports_timeout_not_silent_step_limit(tmp_path: Path) -> None:
    # Regression: when a sub-agent is entered after the run's wall-clock budget
    # is already spent (e.g. the user lingered at the spawn approval prompt for
    # minutes), it must surface a real timeout and never reach a model call -
    # not spin through all MAX_SUBAGENT_STEPS doing nothing and return a
    # misleading status="ok" / reason=step_limit with 0 writes.
    recorder = TraceRecorder(tmp_path)
    client = FakeClient([])  # any model call would raise: none should happen
    guard = BudgetGuard(max_steps=20, max_tokens=1_000_000, max_usd=10.0, daily_remaining_usd=10.0)
    policy = ApprovalPolicy()  # no interactive prompt -> timeout extension denied

    summary, status, writes_ok, _reads_ok, failure_reason = _run_live_subagent(
        tmp_path,
        "coder",
        "Create calc_timeout/calculator.py",
        recorder,
        client,
        guard,
        child_id="coder-1",
        started=time.perf_counter() - (config.WALL_CLOCK_TIMEOUT + 100),
        policy=policy,
    )

    assert status == "timeout"
    assert failure_reason == "timeout"
    assert writes_ok == 0
    assert client.calls == []  # never reached the model
    assert "step_limit" not in summary
    events = read_events(recorder.path)
    assert any(
        e.get("kind") == "budget_event" and e.get("budget_reason") == "timeout"
        for e in events
    )


def test_long_approval_pause_is_credited_so_spawned_coder_still_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression: time the user spends blocked at an approval prompt must not
    # count toward the wall-clock timeout. A human who deliberates past
    # WALL_CLOCK_TIMEOUT before approving a spawn should still get a working
    # sub-agent run, not a coder that silently times out on its first step.
    from vg_agent import agent as agent_module

    clock = {"t": 1000.0}
    monkeypatch.setattr(agent_module.time, "perf_counter", lambda: clock["t"])

    def slow_approve(request: ApprovalRequest) -> ApprovalOutcome:
        if request.tool == "spawn_subagent":
            # Human sits at the prompt well past the wall-clock timeout.
            clock["t"] += config.WALL_CLOCK_TIMEOUT + 60
            return ApprovalOutcome(decision="approved", reason="test approve spawn")
        return ApprovalOutcome(decision="approved", reason="test approve")

    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "spawn coder",
                [
                    ToolCall(
                        "spawn-1",
                        "spawn_subagent",
                        {"type": "coder", "question": "Create calc_pause/calculator.py"},
                    )
                ],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("done", input_tokens=20, output_tokens=10),
        ],
        by_type={
            "coder": [
                ModelTurn(
                    "",
                    [
                        ToolCall(
                            "write-1",
                            "write_file",
                            {"path": "calc_pause/calculator.py", "content": "print('ok')\n"},
                        )
                    ],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn(
                    "calc_pause/calculator.py: created file; replaced 0 occurrence(s)",
                    input_tokens=15,
                    output_tokens=10,
                ),
            ]
        },
    )
    recorder = TraceRecorder(tmp_path)
    guard = BudgetGuard(max_steps=20, max_tokens=1_000_000, max_usd=10.0, daily_remaining_usd=10.0)
    policy = ApprovalPolicy(mode="writes", prompt=slow_approve)

    run_live_task(tmp_path, "create calc_pause", recorder, client=client, guard=guard, policy=policy)

    # The approval pause was credited, so the coder ran and wrote the file.
    assert (tmp_path / "calc_pause" / "calculator.py").exists()
    assert guard.wall_clock_extra_s >= config.WALL_CLOCK_TIMEOUT
    events = read_events(recorder.path)
    coder_return = next(
        e for e in events if e.get("kind") == "subagent_return" and e.get("agent_type") == "coder"
    )
    assert coder_return["status"] == "ok"
    assert coder_return["writes_ok"] == 1
    assert "step_limit" not in str(coder_return["summary"])


def test_coder_empty_turn_retries_exhausted_is_tool_error(tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    client = FakeClient(
        [
            ModelTurn("", input_tokens=20, output_tokens=1),
            ModelTurn("", input_tokens=20, output_tokens=1),
            ModelTurn("", input_tokens=20, output_tokens=1),
        ]
    )
    guard = BudgetGuard(max_steps=20, max_tokens=1_000_000, max_usd=10.0, daily_remaining_usd=10.0)
    policy = ApprovalPolicy(mode="off")

    summary, status, writes_ok, _reads_ok, failure_reason = _run_live_subagent(
        tmp_path,
        "coder",
        "Create calc3/calculator.py",
        recorder,
        client,
        guard,
        child_id="coder-1",
        started=time.perf_counter(),
        policy=policy,
    )

    assert status == "tool_error"
    assert writes_ok == 0
    assert "repeated empty responses" in summary
    assert failure_reason == "no_terminal_summary"
    events = read_events(recorder.path)
    assert any(
        e.get("kind") == "budget_event" and e.get("budget_reason") == "subagent_empty_turn_abort"
        for e in events
    )


def test_chat_loop_emits_run_end_on_keyboard_interrupt_during_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vg_agent import __main__ as cli

    write_fixture(tmp_path)
    prompts = iter(["do work"])
    monkeypatch.setattr(cli, "use_rich_ui", lambda: False)
    monkeypatch.setattr(cli, "_make_chat_prompt", lambda _history_path: (lambda: next(prompts), lambda: None))
    monkeypatch.setattr(cli, "LiveModelClient", SimpleNamespace(from_env=lambda recorder=None: object()))

    def fake_run_live_task(
        root: Path,
        prompt: str,
        recorder: TraceRecorder,
        *,
        client: object,
        guard: BudgetGuard,
        policy: ApprovalPolicy,
        history: list[dict[str, object]],
    ) -> TraceRecorder:
        recorder.emit("user_prompt", prompt=prompt)
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run_live_task", fake_run_live_task)
    args = SimpleNamespace(no_redact=False, require_approval="off", yes=False, live_model=True)
    assert cli._chat_loop(tmp_path, args) == 0
    events = read_events(next(iter((tmp_path / "traces").glob("*.jsonl"))))
    assert any(e.get("kind") == "budget_event" and e.get("budget_reason") == "user_abort" for e in events)
    assert any(e.get("kind") == "run_end" and e.get("final_status") == "aborted" for e in events)


def test_reviewer_spawn_includes_review_slice(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "Coder then reviewer.",
                [ToolCall("spawn-c", "spawn_subagent", {"type": "coder", "question": "rename foo to baz in app.py"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn(
                "Review coder.",
                [ToolCall("spawn-r", "spawn_subagent", {"type": "reviewer", "question": "verify app.py edit"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("Review complete.", input_tokens=100, output_tokens=20),
        ],
        by_type={
            "coder": [
                ModelTurn(
                    "Edit.",
                    [ToolCall("edit", "edit_file", {"path": "app.py", "old": "foo", "new": "baz"})],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn("app.py: renamed foo to baz", input_tokens=40, output_tokens=10),
            ],
            "reviewer": [
                ModelTurn(
                    "Read and pass.",
                    [ToolCall("read", "read_file", {"path": "app.py"})],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn("PASS: baz present on disk", input_tokens=40, output_tokens=10),
            ],
        },
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "rename and review app.py", recorder, client=client)
    reviewer_calls = [
        c for c in client.calls if "You are Reviewer" in str(c.get("system_prompt") or "")
    ]
    assert reviewer_calls
    first_user = str((reviewer_calls[0].get("messages") or [{}])[0].get("content") or "")
    assert "Coder run under review" in first_user
    assert "subagent_spawn" in first_user
    rev_return = next(
        e for e in read_events(recorder.path) if e["kind"] == "subagent_return" and e["agent_type"] == "reviewer"
    )
    assert rev_return["status"] == "ok"
    assert rev_return["reads_ok"] >= 1


def test_reviewer_py_compile_flow_returns_clean_verdict(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "Coder then reviewer.",
                [ToolCall("spawn-c", "spawn_subagent", {"type": "coder", "question": "rename foo to baz in app.py"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn(
                "Review coder.",
                [ToolCall("spawn-r", "spawn_subagent", {"type": "reviewer", "question": "verify app.py edit"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("Review complete.", input_tokens=100, output_tokens=20),
        ],
        by_type={
            "coder": [
                ModelTurn(
                    "Edit.",
                    [ToolCall("edit", "edit_file", {"path": "app.py", "old": "foo", "new": "baz"})],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn("app.py: renamed foo to baz", input_tokens=40, output_tokens=10),
            ],
            "reviewer": [
                ModelTurn(
                    "Compile check and pass.",
                    [ToolCall("compile", "run_bash", {"command": "python3 -m py_compile app.py"})],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn("PASS: py_compile succeeded and edit is present", input_tokens=40, output_tokens=10),
            ],
        },
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "rename and review app.py", recorder, client=client)
    events = read_events(recorder.path)
    rev_return = next(
        e for e in events if e["kind"] == "subagent_return" and e["agent_type"] == "reviewer"
    )
    assert rev_return["status"] == "ok"
    assert str(rev_return["summary"]).startswith("PASS:")
    reviewer_tool_results = [
        e
        for e in events
        if e.get("kind") == "tool_result" and e.get("agent_type") == "reviewer" and e.get("tool") == "run_bash"
    ]
    assert reviewer_tool_results
    assert all(e.get("status") == "ok" for e in reviewer_tool_results)
    assert all("run_bash blocked" not in str(e.get("result_full") or "") for e in reviewer_tool_results)


def test_reviewer_no_read_is_tool_error(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "Coder.",
                [ToolCall("spawn-c", "spawn_subagent", {"type": "coder", "question": "touch app.py comment"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn(
                "Review.",
                [ToolCall("spawn-r", "spawn_subagent", {"type": "reviewer", "question": "verify"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("Done.", input_tokens=100, output_tokens=20),
        ],
        by_type={
            "coder": [
                ModelTurn(
                    "Edit.",
                    [ToolCall("edit", "edit_file", {"path": "app.py", "old": "foo", "new": "baz"})],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn("app.py: edit", input_tokens=40, output_tokens=10),
            ],
            "reviewer": [
                ModelTurn("PASS: looks good", input_tokens=40, output_tokens=10),
            ],
        },
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "review without read", recorder, client=client)
    rev_return = next(
        e for e in read_events(recorder.path) if e["kind"] == "subagent_return" and e["agent_type"] == "reviewer"
    )
    assert rev_return["status"] == "tool_error"


def test_reviewer_verdict_fallback_on_step_exhaustion(tmp_path: Path) -> None:
    # Reviewer is bounded tighter than other sub-agents so a non-converging
    # reviewer cannot burn the full sub-agent step budget.
    assert config.MAX_REVIEWER_STEPS < config.MAX_SUBAGENT_STEPS
    write_fixture(tmp_path)
    recorder = TraceRecorder(tmp_path)
    turns: list[ModelTurn] = []
    for i in range(config.MAX_SUBAGENT_STEPS):
        turns.append(
            ModelTurn(
                "",
                [ToolCall(f"t{i}", "read_file", {"path": "README.md"})],
                stop_reason="tool_use",
                input_tokens=10,
                output_tokens=5,
            )
        )
    client = FakeClient(turns)
    guard = BudgetGuard(
        max_steps=config.MAX_SUBAGENT_STEPS + 5,
        max_tokens=1_000_000,
        max_usd=10.0,
        daily_remaining_usd=10.0,
    )
    policy = ApprovalPolicy(mode="writes", prompt=lambda _req: ApprovalOutcome(decision="denied", reason="no"))

    summary, status, _writes_ok, _reads_ok, _reason = _run_live_subagent(
        tmp_path,
        "reviewer",
        "verify README.md",
        recorder,
        client,
        guard,
        child_id="reviewer-1",
        started=time.time(),
        policy=policy,
    )
    # Genuinely exhaust the reviewer step loop (not the wall-clock path): the
    # fallback must report the step limit, not a timeout.
    assert len(client.calls) == config.MAX_REVIEWER_STEPS
    assert summary.startswith("FAIL:")
    assert "step limit" in summary
    assert status == "tool_error"


def test_reviewer_verdict_fallback_on_budget_cap_abort(tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    client = FakeClient([])
    guard = BudgetGuard(
        max_steps=0,
        max_tokens=1_000_000,
        max_usd=10.0,
        daily_remaining_usd=10.0,
    )
    policy = ApprovalPolicy(mode="writes", prompt=lambda _req: ApprovalOutcome(decision="denied", reason="no"))

    summary, status, _writes_ok, _reads_ok, _reason = _run_live_subagent(
        tmp_path,
        "reviewer",
        "verify README.md",
        recorder,
        client,
        guard,
        child_id="reviewer-1",
        started=0.0,
        policy=policy,
    )
    assert summary.startswith("FAIL:")
    assert status == "tool_error"


def test_build_review_slice_and_resolve_coder_id(tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    recorder.emit("subagent_spawn", agent_id="coder-1", agent_type="coder", child_agent_id="coder-1", question="q")
    recorder.emit("tool_call", agent_id="coder-1", tool="edit_file", tool_use_id="e1")
    recorder.emit("subagent_return", agent_id="coder-1", agent_type="coder", child_agent_id="coder-1", status="ok")
    assert _resolve_review_coder_id(recorder, None) == "coder-1"
    assert _resolve_review_coder_id(recorder, "coder-1") == "coder-1"
    slice_text = _build_review_slice(recorder, "coder-1")
    assert "subagent_spawn" in slice_text
    assert "edit_file" in slice_text


def test_pytest_importable_in_runtime() -> None:
    import pytest as pytest_mod

    assert pytest_mod.__version__


def test_run_tests_soft_error_continues_parent_loop(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    test_dir = tmp_path / "tkinter_calc"
    test_dir.mkdir(exist_ok=True)
    (test_dir / "test_fail.py").write_text(
        "def test_bad():\n    assert False\n",
        encoding="utf-8",
    )
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "Run tests.",
                [ToolCall("rt", "run_tests", {"path": "tkinter_calc/test_fail.py"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn(
                "Tests failed; spawn coder to fix.",
                [ToolCall("spawn", "spawn_subagent", {"type": "coder", "question": "fix test_fail.py"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("Recovery complete.", input_tokens=100, output_tokens=20),
        ],
        by_type={
            "coder": [
                ModelTurn(
                    "Fix.",
                    [ToolCall("edit", "edit_file", {"path": "tkinter_calc/test_fail.py", "old": "False", "new": "True"})],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn("tkinter_calc/test_fail.py: fixed assertion", input_tokens=40, output_tokens=10),
            ],
        },
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "run tests and recover", recorder, client=client)
    events = read_events(recorder.path)
    run_test_results = [e for e in events if e.get("kind") == "tool_result" and e.get("tool") == "run_tests"]
    assert run_test_results
    assert run_test_results[0]["status"] == "error"
    run_end = next(e for e in events if e.get("kind") == "run_end")
    assert run_end["final_status"] != "tool_error"
    assert len(client.calls) >= 3


def test_reviewer_spawn_without_coder_returns_error(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "Review existing code.",
                [ToolCall("spawn-r", "spawn_subagent", {"type": "reviewer", "question": "review app.py"})],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("Use explorer instead.", input_tokens=100, output_tokens=20),
        ],
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "review app.py without coder", recorder, client=client)
    spawn_results = [
        e
        for e in read_events(recorder.path)
        if e.get("kind") == "tool_result" and e.get("tool") == "spawn_subagent"
    ]
    assert spawn_results
    assert spawn_results[0]["status"] == "error"
    assert "Explorer" in str(spawn_results[0]["result_full"])
    reviewer_spawns = [e for e in read_events(recorder.path) if e.get("kind") == "subagent_spawn" and e.get("agent_type") == "reviewer"]
    assert not reviewer_spawns


def test_coder_read_before_test_guard(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    calc_dir = tmp_path / "tkinter_calc"
    calc_dir.mkdir(exist_ok=True)
    (calc_dir / "calculator.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "Add pytest.",
                [
                    ToolCall(
                        "spawn",
                        "spawn_subagent",
                        {"type": "coder", "question": "add test_calculator.py for calculator.py"},
                    )
                ],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            ModelTurn("Coder blocked on test write.", input_tokens=100, output_tokens=20),
        ],
        by_type={
            "coder": [
                ModelTurn(
                    "Write test without reading impl.",
                    [
                        ToolCall(
                            "write",
                            "write_file",
                            {
                                "path": "tkinter_calc/test_calculator.py",
                                "content": "from calculator import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
                            },
                        )
                    ],
                    stop_reason="tool_use",
                    input_tokens=60,
                    output_tokens=20,
                ),
                ModelTurn("Could not write tests yet.", input_tokens=40, output_tokens=10),
            ],
        },
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "add pytest for calculator", recorder, client=client)
    coder_returns = [
        e for e in read_events(recorder.path) if e.get("kind") == "subagent_return" and e.get("agent_type") == "coder"
    ]
    assert coder_returns
    assert coder_returns[-1]["status"] == "tool_error"
    blocked = [
        e
        for e in read_events(recorder.path)
        if e.get("kind") == "tool_result"
        and e.get("tool") == "write_file"
        and "read the implementation" in str(e.get("result_full") or "")
    ]
    assert blocked


def test_clarify_tool_error_pytest_missing() -> None:
    from vg_agent.__main__ import clarify_tool_error

    msg = clarify_tool_error("run_tests", "No module named pytest")
    assert "pytest" in msg.lower()
    assert "venv" in msg.lower() or "runtime" in msg.lower()


# --- Demo-gate + refactor-guard tests (quick_demo.md coverage) ---------------


def test_read_file_range_out_of_bounds_returns_empty_ok(tmp_path: Path) -> None:
    """Characterize current leniency: an out-of-range start yields empty 'ok',
    not an error (Python slice semantics). Pins behavior so it can't drift
    silently; flip the assertions if read_file_range is made strict."""
    (tmp_path / "a.txt").write_text("l1\nl2\nl3\n", encoding="utf-8")
    res = read_file_range(tmp_path, "a.txt", 100, 200, "r1")
    assert res["status"] == "ok"
    assert res["result_full"] == ""


def test_run_bash_allowlisted_read_only_commands_succeed(tmp_path: Path) -> None:
    """Positive complement to the run_bash denial tests (demo VG.5)."""
    assert run_bash(tmp_path, "pwd", "b1")["status"] == "ok"
    assert run_bash(tmp_path, "ls", "b2")["status"] == "ok"


def test_denied_edit_leaves_app_py_unchanged_on_disk(tmp_path: Path) -> None:
    """quick_demo.md §5: denying a Coder write must leave the file byte-for-byte
    unchanged and surface as approval_denied, with no fallback write."""
    write_fixture(tmp_path)
    target = tmp_path / "app.py"
    original = target.read_text(encoding="utf-8")
    client = _rename_via_coder_client()

    def deny_writes(request: ApprovalRequest) -> ApprovalOutcome:
        if request.tool in {"edit_file", "write_file"}:
            return ApprovalOutcome(decision="denied", reason="user no")
        return ApprovalOutcome(decision="approved", reason="ok")

    recorder = TraceRecorder(tmp_path)
    policy = ApprovalPolicy(mode="writes", prompt=deny_writes)
    run_live_task(tmp_path, "rename foo to bar in app.py", recorder, client=client, policy=policy)

    assert target.read_text(encoding="utf-8") == original
    events = read_events(recorder.path)
    assert any(e.get("kind") == "approval" and e.get("decision") == "denied" for e in events)
    assert not any(
        e.get("kind") == "tool_result"
        and e.get("tool") in {"edit_file", "write_file"}
        and e.get("status") == "ok"
        for e in events
    )


@pytest.mark.parametrize(
    "rel_path,needle",
    [
        (".env", "Use '.env.example'"),
        ("secrets/id_rsa", "SSH private keys"),
        ("app.pem", "Cryptographic key files"),
        (".aws/credentials", "Cloud credential files"),
        (".ssh/credentials", "Cloud credential files"),  # precedence: credential before ssh-dir
        (".ssh/config", "SSH credential directories"),
        (".netrc", "Netrc credential files"),
        (".vg_approvals.json", "Internal governance files"),
    ],
)
def test_sensitive_path_hint_precedence(rel_path: str, needle: str) -> None:
    """Guards the consolidated (pattern, hint) table in tools.py."""
    message = validate_sensitive_path(rel_path)
    assert message is not None
    assert "sensitive path" in message
    assert needle in message


def test_sensitive_path_allows_env_example() -> None:
    assert validate_sensitive_path(".env.example") is None


def test_model_dicts_derive_from_catalog() -> None:
    """Guards config._MODELS consolidation: the public per-field dicts must
    stay in sync with the single catalog."""
    catalog_ids = set(config._MODELS)
    assert set(config.PRICING_USD_PER_MTOK) == catalog_ids
    assert set(config.CONTEXT_WINDOW_TOKENS) == catalog_ids
    assert set(config.AUTO_COMPACT_FRACTION) == catalog_ids
    for model_id, spec in config._MODELS.items():
        assert config.PRICING_USD_PER_MTOK[model_id] == spec["pricing"]
        assert config.CONTEXT_WINDOW_TOKENS[model_id] == spec["context_window"]
        assert config.AUTO_COMPACT_FRACTION[model_id] == spec["compact_fraction"]
