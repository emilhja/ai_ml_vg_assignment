from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
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
    run_live_task,
    run_task,
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
    run_bash,
    validate_sensitive_path,
    validate_shell_command,
    write_file,
)
from vg_agent.trace import TraceRecorder, _redact, load_trace, render_tree, show_context


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


def test_budget_guard_reasons_and_costs() -> None:
    guard = BudgetGuard(max_steps=1)
    assert guard.before_model_call(config.PARENT_MODEL_ID, 100, 100).allowed
    guard.record_model_call(config.PARENT_MODEL_ID, 100, 100)
    decision = guard.before_model_call(config.PARENT_MODEL_ID, 100, 100)
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


def test_sanity_run_edits_app(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    recorder = TraceRecorder(tmp_path)
    run_task(tmp_path, "rename foo to bar in app.py", recorder)
    app = (tmp_path / "app.py").read_text(encoding="utf-8")
    assert "def bar(" in app
    assert "def foo(" not in app
    assert recorder.events[-1]["kind"] == "run_end"
    assert recorder.events[-1]["final_status"] == "ok"


def test_parent_compaction_and_subagent_context(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    recorder = TraceRecorder(tmp_path)
    run_task(tmp_path, "find all auth handling and summarise", recorder)
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
    assert compaction["original_event_idx"] == original["event_idx"]
    expected_hash = hashlib.sha256(str(original["result_full"]).encode("utf-8")).hexdigest()
    assert compaction["original_sha256"] == expected_hash

    context = show_context(events, 3)
    context_text = json.dumps(context)
    assert "[COMPACTED tool_result for tool_use_id=parent-read-sample-log]" in context_text
    assert "req-00001" not in context_text
    assert "SESSION_SECRET" not in context_text
    assert "Auth is handled in auth/session.py and auth/middleware.py" in context_text
    assert "child-read-session" not in context_text
    assert "child-read-middleware" not in context_text


def test_replay_round_trip_tree_and_context(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    recorder = TraceRecorder(tmp_path)
    run_task(tmp_path, "find all auth handling and summarise", recorder)
    loaded = load_trace(recorder.path)
    assert render_tree(loaded) == render_tree(recorder.events)
    assert show_context(loaded, 3) == show_context(recorder.events, 3)


def test_sqlite_trace_mirror_and_dashboard_rollups(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    recorder = TraceRecorder(tmp_path)
    run_task(tmp_path, "find all auth handling and summarise", recorder)
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
        assert turns[0][0] == "find all auth handling and summarise"
        assert turns[0][1] == "ok"
        assert int(turns[0][2]) > 0
        assert int(turns[0][3]) > 0
        assert int(turns[0][4]) > 0
        assert int(turns[0][5]) >= 0

        assert conn.execute("SELECT COUNT(*) FROM model_calls WHERE run_id = ?", (recorder.run_id,)).fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM tool_calls WHERE run_id = ?", (recorder.run_id,)).fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM subagents WHERE run_id = ?", (recorder.run_id,)).fetchone()[0] > 0
        assert conn.execute("SELECT COUNT(*) FROM compactions WHERE run_id = ?", (recorder.run_id,)).fetchone()[0] > 0


def test_cost_cap_run_uses_budget_reason(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    recorder = TraceRecorder(tmp_path)
    run_task(
        tmp_path,
        "search this repo for the string __VG_SENTINEL_NEVER_PRESENT__ and don't stop until you find it",
        recorder,
    )
    events = read_events(recorder.path)
    assert events[-2]["kind"] == "budget_event"
    assert events[-2]["budget_reason"] == "repetition_abort"
    assert "kind" in events[-2]
    assert events[-1]["kind"] == "run_end"
    assert events[-1]["final_status"] == "aborted"
    assert float(events[-1]["total_cost_usd"]) > 0
    assert float(events[-1]["total_cost_usd"]) < config.MAX_USD_PER_RUN


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
    assert "run #---------" in line
    assert "1.3k/10.0k tok" in line
    assert "steps 1/5" in line
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
    assert "N: parent step index; default 0" in show_context[0].display_meta_text
    assert len(show_context[0].display_text) > len(show_context[0].text)
    assert list(completer.get_completions(Document(""), CompleteEvent())) == []
    assert list(completer.get_completions(Document(" "), CompleteEvent())) == []
    assert list(completer.get_completions(Document("hello "), CompleteEvent())) == []
    assert list(completer.get_completions(Document("/show-context "), CompleteEvent())) == []
    assert SLASH_COMMAND_HELP.startswith("Slash commands:\n")
    assert "/show-context N" in SLASH_COMMAND_HELP
    assert "Show steps, tokens, USD, and daily remaining" in SLASH_COMMAND_HELP
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
        ModelTurn("Done.", input_tokens=100, output_tokens=20),
    ])
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "read sample log", recorder, client=client)
    events = read_events(recorder.path)
    assert any(e["kind"] == "compaction" and e["tool_use_id"] == "read-log" for e in events)
    second_call_messages = json.dumps(client.calls[1]["messages"])
    assert "[COMPACTED tool_result for tool_use_id=read-log]" in second_call_messages
    assert "req-00001" not in second_call_messages


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
    assert (sandbox / "fixtures" / "demo_repo" / "data" / "sample.log").stat().st_size > 200_000


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
    run_task(tmp_path, "rename foo to bar in app.py", recorder, policy=policy)
    text = (tmp_path / "app.py").read_text(encoding="utf-8")
    assert "def foo(" in text
    assert "def bar(" not in text
    approvals = [e for e in recorder.events if e["kind"] == "approval"]
    assert approvals and approvals[0]["decision"] == "denied"


def test_approval_event_recorded_auto_yes(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    policy = ApprovalPolicy(mode="writes", auto_yes=True)
    recorder = TraceRecorder(tmp_path)
    run_task(tmp_path, "rename foo to bar in app.py", recorder, policy=policy)
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
    events = recorder.events
    assert not any("sk-or-v1-DEAD" in str(e.get("result_full", "")) for e in events)
    redaction_events = [e for e in events if e["kind"] == "redaction"]
    assert redaction_events
    with sqlite3.connect(tmp_path / config.SQLITE_TRACE_DB) as conn:
        payloads = "\n".join(row[0] for row in conn.execute("SELECT payload_json FROM events"))
        assert "sk-or-v1-DEAD" not in payloads
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
    assert outputs[0].startswith("Blocked (read_file):\n")
    assert ".env.example" in outputs[0]
    tool_event = next(event for event in recorder.events if event["kind"] == "tool_result")
    progress = str(_format_progress_event(tool_event))
    assert "sensitive path" in progress
    assert ".env.example" in progress
    assert _progress_event_color(tool_event, use_color=True) == "\x1b[31m"


def test_chat_persists_budget_and_approvals_across_turns(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    # Two turns: first turn renames foo to bar in app.py (auto-yes), then /budget, then exit
    stdin_text = (
        "rename foo to bar in app.py\n"
        "/budget\n"
        "/approvals\n"
        "/exit\n"
    )
    completed = subprocess.run(
        [sys.executable, "-m", "vg_agent", "--chat", "--require-approval", "writes", "--yes"],
        cwd=tmp_path,
        env=env,
        input=stdin_text,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr
    # Budget output should be present in stdout
    assert "steps" in completed.stdout
    assert "Renamed foo to bar in app.py." in completed.stdout
    assert "Approvals - session history" in completed.stdout
    assert "edit_file" in completed.stdout
    assert "app.py" in completed.stdout
    # Trace should be a single JSONL with one session_id
    trace_dir = tmp_path / "traces"
    traces = list(trace_dir.glob("*.jsonl"))
    assert len(traces) == 1
    events = read_events(traces[0])
    session_ids = {e.get("session_id") for e in events}
    assert len(session_ids) == 1
    approvals = [e for e in events if e["kind"] == "approval"]
    assert any(a["decision"] == "auto" for a in approvals)


def test_chat_slash_reset_emits_event(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
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


def test_chat_ui_turn_output_framed_on_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from vg_agent import chat_ui

    monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)
    buffer = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buffer)
    assert chat_ui.print_turn_output(answer="Hello", literal_outputs=["./auth"]) is True
    out = buffer.getvalue()
    assert "Hello" in out
    assert "./auth" in out
    assert out.index("\u2500") < out.index("Hello")
    assert out.index("Hello") < out.rindex("\u2500")


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
    from vg_agent import __main__ as cli

    captured: list[str] = []

    class FakeConsole:
        def print(self, *args: object, **kwargs: object) -> None:
            captured.append(str(args))

    from vg_agent import chat_ui

    monkeypatch.setattr(cli, "use_rich_ui", lambda: True)
    monkeypatch.setattr(cli, "_console", lambda: FakeConsole())
    sink = cli._make_progress_sink(turn_state={}, workspace_root=tmp_path)
    sink(
        {
            "kind": "tool_call",
            "tool_use_id": "e1",
            "tool": "edit_file",
            "args": {"path": "x.py", "old": "a", "new": "b"},
        }
    )
    sink({"kind": "tool_result", "tool_use_id": "e1", "tool": "edit_file", "status": "ok"})
    assert captured


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
