from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from vg_agent import config
from vg_agent.agent import (
    ApprovalOutcome,
    ApprovalPolicy,
    ApprovalRequest,
    run_live_task,
    run_task,
)
from vg_agent.anthropic_client import (
    AnthropicClient,
    EndpointPinViolation,
    ModelTurn,
    ToolCall,
)
from vg_agent.budget import BudgetGuard, DailySpendLedger
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
    assert validate_shell_command("Remove-Item victim.txt") is not None
    assert validate_shell_command("sed -i 's/a/b/' foo") is not None
    assert validate_shell_command("find . -delete") is not None
    assert validate_shell_command("git fetch origin") is not None
    assert validate_shell_command("ssh user@host ls") is not None

    result = run_bash(tmp_path, "rm -rf .", "unsafe-rm")
    assert result["status"] == "error"
    assert "refused unsafe command" in str(result["result_full"])
    assert victim.exists()


def test_live_model_cli_requires_anthropic_key(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env["PYTHONPATH"] = str(ROOT / "src")
    completed = subprocess.run(
        [sys.executable, "-m", "vg_agent", "--task", "inspect", "--live-model"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 2
    assert "ANTHROPIC_API_KEY is required" in completed.stderr


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
    assert "sensitive path" in str(read_file(tmp_path, ".env", "r1")["result_full"])
    assert read_file(tmp_path, "secrets/id_rsa", "r2")["status"] == "error"
    assert read_file(tmp_path, "app.pem", "r3")["status"] == "error"
    assert read_file(tmp_path, ".aws/credentials", "r4")["status"] == "error"
    assert write_file(tmp_path, ".env", "x", "w1")["status"] == "error"
    assert edit_file(tmp_path, ".env", "SECRET=abc", "EVIL=", "e1")["status"] == "error"
    # .env.example is allowed
    ok = read_file(tmp_path, ".env.example", "ok")
    assert ok["status"] == "ok"


def test_live_loop_budget_abort_before_client_call(tmp_path: Path) -> None:
    client = FakeClient([])
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "do work", recorder, client=client, guard=BudgetGuard(max_steps=0))
    events = read_events(recorder.path)
    assert client.calls == []
    assert events[-2]["kind"] == "budget_event"
    assert events[-2]["budget_reason"] == "step_cap"
    assert events[-1]["final_status"] == "aborted"


def test_live_parent_tool_flow_reads_and_edits_fixture(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    client = FakeClient([
        ModelTurn(
            assistant_text="I will inspect and edit app.py.",
            tool_calls=[
                ToolCall("read-app", "read_file", {"path": "app.py"}),
                ToolCall("edit-app", "edit_file", {"path": "app.py", "old": "foo", "new": "baz"}),
            ],
            stop_reason="tool_use",
            input_tokens=100,
            output_tokens=50,
        ),
        ModelTurn("Renamed foo to baz.", input_tokens=100, output_tokens=20),
    ])
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "rename foo to baz", recorder, client=client)
    assert "def baz(" in (tmp_path / "app.py").read_text(encoding="utf-8")
    events = read_events(recorder.path)
    assert [e["tool"] for e in events if e["kind"] == "tool_result"] == ["read_file", "edit_file"]
    assert events[-1]["final_status"] == "ok"
    assert len(client.calls) == 2


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

    calls = {"count": 0}

    def grant_scoped(request: ApprovalRequest) -> ApprovalOutcome:
        calls["count"] += 1
        return ApprovalOutcome(decision="approved_scoped", scope_key="", reason="grant root")

    policy = ApprovalPolicy(mode="writes", prompt=grant_scoped)

    client = FakeClient([
        ModelTurn(
            "edit app",
            [ToolCall("e1", "edit_file", {"path": "app.py", "old": "foo", "new": "bar"})],
            stop_reason="tool_use",
            input_tokens=10,
            output_tokens=5,
        ),
        ModelTurn(
            "edit utils",
            [ToolCall("e2", "edit_file", {"path": "utils.py", "old": "foo", "new": "bar"})],
            stop_reason="tool_use",
            input_tokens=10,
            output_tokens=5,
        ),
        ModelTurn("done.", input_tokens=10, output_tokens=5),
    ])
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "rename in two files", recorder, client=client, policy=policy)
    approvals = [e for e in recorder.events if e["kind"] == "approval"]
    assert len(approvals) == 2
    assert approvals[0]["decision"] == "approved_scoped"
    assert approvals[1]["decision"] == "approved_scoped"
    # Prompt callback invoked only on the first call
    assert calls["count"] == 1


def test_approval_scope_does_not_bypass_denylist(tmp_path: Path) -> None:
    write_fixture(tmp_path)

    def grant_always(_request: ApprovalRequest) -> ApprovalOutcome:
        return ApprovalOutcome(decision="approved_always", reason="trust me")

    policy = ApprovalPolicy(mode="writes", prompt=grant_always)
    # First, populate cache with a write to app.py
    client = FakeClient([
        ModelTurn(
            "edit app",
            [ToolCall("e1", "edit_file", {"path": "app.py", "old": "foo", "new": "bar"})],
            stop_reason="tool_use",
            input_tokens=10,
            output_tokens=5,
        ),
        ModelTurn(
            "try .env",
            [ToolCall("e2", "edit_file", {"path": ".env", "old": "", "new": "EVIL=1"})],
            stop_reason="tool_use",
            input_tokens=10,
            output_tokens=5,
        ),
        ModelTurn("done", input_tokens=10, output_tokens=5),
    ])
    (tmp_path / ".env").write_text("SECRET=abc", encoding="utf-8")
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "rename in app then try env", recorder, client=client, policy=policy)
    # Even with approved_always, .env is denylisted at tools layer
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "SECRET=abc"
    sensitive_errors = [
        e for e in recorder.events
        if e["kind"] == "tool_result" and "sensitive path" in str(e.get("result_full", ""))
    ]
    assert sensitive_errors


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


def test_endpoint_host_pinned() -> None:
    client = AnthropicClient(api_key="dummy", endpoint="https://evil.example/v1/messages")
    with pytest.raises(EndpointPinViolation):
        client.complete(model=config.PARENT_MODEL_ID, system_prompt="x", messages=[], tools=[])


def test_trace_redacts_secrets(tmp_path: Path) -> None:
    redacted, summary = _redact("token sk-ant-AbCdEf-12 and key AKIA0123456789ABCDEF and Bearer xyz")
    assert "***REDACTED***" in redacted
    assert "sk-ant" not in redacted
    assert "AKIA" not in redacted
    assert any(name == "anthropic_key" for name, _ in summary)

    recorder = TraceRecorder(tmp_path)
    recorder.emit("tool_result", tool="read_file", tool_use_id="t1", result_full="leaked sk-ant-DEADBEEF-9")
    events = recorder.events
    assert not any("sk-ant-DEAD" in str(e.get("result_full", "")) for e in events)
    redaction_events = [e for e in events if e["kind"] == "redaction"]
    assert redaction_events


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
