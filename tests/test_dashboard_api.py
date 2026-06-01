"""Dashboard API tests (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vg_agent.agent import run_live_task
from vg_agent.trace import TraceRecorder
from tests.test_vg_agent import (
    ModelTurn,
    PipelineClient,
    ToolCall,
    _log_then_explorer_client,
    write_fixture,
)


@pytest.fixture()
def dashboard_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    write_fixture(tmp_path)
    traces = tmp_path / "traces"
    traces.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VG_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("VG_TRACES_DIR", str(traces))
    monkeypatch.setenv("VG_SQLITE_PATH", str(traces / "vg_agent.sqlite3"))
    import dashboard.api.db as db_module
    from dashboard.api.paths import clear_path_cache

    clear_path_cache()
    db_module._engine = None
    db_module._SessionLocal = None

    from dashboard.api.main import app

    return TestClient(app)


def test_health(dashboard_client: TestClient, tmp_path: Path) -> None:
    response = dashboard_client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["sqlite_exists"] is False or body["ok"] is True
    assert str(tmp_path) in body["workspace_root"]
    assert "sqlite_path" in body
    assert body["schema_ready"] is True


def test_sessions_and_timeline_after_run(dashboard_client: TestClient, tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    run_live_task(
        tmp_path,
        "read data/sample.log then summarise auth",
        recorder,
        client=_log_then_explorer_client(),
    )
    session_id = str(recorder.session_id)

    listed = dashboard_client.get("/api/v1/sessions")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert any(item["session_id"] == session_id for item in items)

    detail = dashboard_client.get(f"/api/v1/sessions/{session_id}")
    assert detail.status_code == 200
    assert detail.json()["session"]["session_id"] == session_id
    run_id = detail.json()["runs"][0]["run_id"]

    timeline = dashboard_client.get(f"/api/v1/runs/{run_id}/timeline")
    assert timeline.status_code == 200
    assert timeline.json()["model_calls"]
    assert timeline.json()["tool_calls"]

    context = dashboard_client.get(f"/api/v1/runs/{run_id}/context", params={"step_idx": 1})
    assert context.status_code == 200
    assert isinstance(context.json()["messages"], list)

    parallel = dashboard_client.get(f"/api/v1/runs/{run_id}/parallel")
    assert parallel.status_code == 200

    safety = dashboard_client.get(f"/api/v1/runs/{run_id}/safety")
    assert safety.status_code == 200

    stats = dashboard_client.get("/api/v1/stats", params={"range": "7d"})
    assert stats.status_code == 200
    assert stats.json()["total_runs"] >= 1

    finops = dashboard_client.get("/api/v1/finops/daily")
    assert finops.status_code == 200
    assert "daily_cap_usd" in finops.json()


def test_session_events_pagination(dashboard_client: TestClient, tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="hello")
    session_id = str(recorder.session_id)

    response = dashboard_client.get(
        f"/api/v1/sessions/{session_id}/events",
        params={"from_event_idx": -1, "limit": 10},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) >= 1
    assert items[0]["kind"] == "user_prompt"
    assert items[0].get("turn_id") is not None
    assert items[0].get("turn_index") == 1


def test_active_session(dashboard_client: TestClient, tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="active test")
    response = dashboard_client.get("/api/v1/sessions/active")
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == recorder.session_id


def test_stats_extended_aggregations(dashboard_client: TestClient, tmp_path: Path) -> None:
    import sqlite3

    recorder = TraceRecorder(tmp_path)
    session_id = str(recorder.session_id)
    turn_id = f"{session_id}:turn:1"

    recorder.emit("user_prompt", prompt="Summarize the auth module")
    recorder.emit("tool_call", tool="read_file", tool_use_id="t1", args={"path": "auth/x.py"})
    recorder.emit(
        "tool_result",
        tool="read_file",
        tool_use_id="t1",
        status="ok",
        latency_ms=50,
        result_full="content",
    )
    recorder.emit("tool_call", tool="read_file", tool_use_id="t2", args={"path": "auth/y.py"})
    recorder.emit(
        "tool_result",
        tool="read_file",
        tool_use_id="t2",
        status="ok",
        latency_ms=80,
        result_full="content2",
    )
    recorder.emit("tool_call", tool="run_bash", tool_use_id="t3", command="rm -rf .")
    recorder.emit(
        "tool_result",
        tool="run_bash",
        tool_use_id="t3",
        status="error",
        result_full="run_bash blocked",
        latency_ms=10,
    )
    recorder.emit("subagent_spawn", child_agent_id="exp-1", question="What is in auth/?")
    recorder.emit("subagent_spawn", child_agent_id="exp-2", question="what is in auth/?")
    recorder.emit("user_prompt", prompt="summarize the auth module")

    db_path = tmp_path / "traces" / "vg_agent.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE turns SET total_cost_usd=1.25, total_tokens=5000 WHERE turn_id = ?",
            (turn_id,),
        )
        conn.commit()

    recorder.emit("run_end", final_status="ok", total_cost_usd=1.25, total_tokens=5000)

    stats = dashboard_client.get("/api/v1/stats", params={"range": "7d"})
    assert stats.status_code == 200
    body = stats.json()
    assert body["total_turns"] >= 2
    assert body["by_tool"]
    read_file = next(item for item in body["by_tool"] if item["tool"] == "read_file")
    assert read_file["count"] == 2
    assert read_file["error_count"] == 0
    assert read_file["avg_latency_ms"] == 65.0

    run_bash = next(item for item in body["by_tool"] if item["tool"] == "run_bash")
    assert run_bash["count"] == 1
    assert run_bash["error_count"] == 1

    assert body["top_user_prompts"]
    assert body["top_user_prompts"][0]["count"] == 2

    assert body["top_subagent_questions"]
    assert body["top_subagent_questions"][0]["count"] == 2

    assert body["top_expensive_turns"]
    assert body["top_expensive_turns"][0]["total_cost_usd"] == 1.25
    assert body["top_expensive_turns"][0]["session_id"] == session_id

    assert body["tool_error_groups"]
    bash_group = next(g for g in body["tool_error_groups"] if g["tool"] == "run_bash")
    assert bash_group["count"] == 1
    assert len(bash_group["occurrences"]) == 1
    assert bash_group["occurrences"][0]["tool_call_id"]

    drill = dashboard_client.get(
        "/api/v1/stats/tool-errors",
        params={"range": "7d", "tool": "run_bash"},
    )
    assert drill.status_code == 200
    drill_body = drill.json()
    assert drill_body["total"] == 1
    assert drill_body["items"][0]["error_message"] == "run_bash blocked"


def test_session_list_subagent_flags(dashboard_client: TestClient, tmp_path: Path) -> None:
    write_fixture(tmp_path)
    parallel_client = PipelineClient(
        parent_turns=[
            ModelTurn(
                "Two explorers in parallel.",
                [
                    ToolCall(
                        "spawn-many",
                        "spawn_subagents",
                        {
                            "requests": [
                                {"type": "explorer", "question": "inspect app.py"},
                                {"type": "explorer", "question": "inspect utils.py"},
                            ]
                        },
                    )
                ],
                stop_reason="tool_use",
                input_tokens=100,
                output_tokens=40,
            ),
            ModelTurn("Integrated both.", input_tokens=50, output_tokens=10),
        ],
    )
    recorder = TraceRecorder(tmp_path)
    run_live_task(tmp_path, "parallel explorers", recorder, client=parallel_client)
    session_id = str(recorder.session_id)
    listed = dashboard_client.get("/api/v1/sessions")
    row = next(item for item in listed.json()["items"] if item["session_id"] == session_id)
    assert row["has_subagents"] is True
    assert row["has_parallel_subagents"] is True

    seq_recorder = TraceRecorder(tmp_path)
    run_live_task(
        tmp_path,
        "single explorer",
        seq_recorder,
        client=_log_then_explorer_client(),
    )
    seq_id = str(seq_recorder.session_id)
    listed_again = dashboard_client.get("/api/v1/sessions")
    seq_row = next(item for item in listed_again.json()["items"] if item["session_id"] == seq_id)
    assert seq_row["has_subagents"] is True
    assert seq_row["has_sequential_subagents"] is True


def test_session_rename_dual_storage(dashboard_client: TestClient, tmp_path: Path) -> None:
    import json

    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="rename me")
    session_id = str(recorder.session_id)

    patch = dashboard_client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"display_name": "Explorer demo"},
    )
    assert patch.status_code == 200
    assert patch.json()["display_name"] == "Explorer demo"
    assert patch.json()["session_id"] == session_id

    detail = dashboard_client.get(f"/api/v1/sessions/{session_id}")
    assert detail.status_code == 200
    assert detail.json()["session"]["display_name"] == "Explorer demo"

    listed = dashboard_client.get("/api/v1/sessions")
    row = next(item for item in listed.json()["items"] if item["session_id"] == session_id)
    assert row["display_name"] == "Explorer demo"

    sidecar = tmp_path / "traces" / "session_metadata.json"
    assert sidecar.is_file()
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    assert meta[session_id]["display_name"] == "Explorer demo"
    assert meta[session_id]["updated_at"]

    cleared = dashboard_client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"display_name": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["display_name"] is None
    meta_after = json.loads(sidecar.read_text(encoding="utf-8"))
    assert session_id not in meta_after


def test_events_merge_jsonl_when_sqlite_lags(dashboard_client: TestClient, tmp_path: Path) -> None:
    """JSONL audit log may contain events not yet mirrored in SQLite."""
    import json

    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="merge test")
    recorder.emit("assistant_step", step_idx=1, tokens_in=10, tokens_out=5)
    session_id = str(recorder.session_id)
    run_id = str(recorder.run_id)

    jsonl_path = tmp_path / "traces" / f"{session_id}.jsonl"
    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    extra = {
        "agent_id": "explorer-9.0",
        "agent_type": "explorer",
        "child_agent_id": "explorer-9.0",
        "event_idx": 99,
        "kind": "subagent_spawn",
        "parent_id": "parent",
        "question": "extra from jsonl",
        "run_id": run_id,
        "session_id": session_id,
        "timestamp_iso": "2026-06-01T12:00:00+00:00",
        "turn_id": f"{session_id}:turn:1",
        "turn_index": 1,
    }
    with jsonl_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(extra) + "\n")

    before = dashboard_client.get(
        f"/api/v1/sessions/{session_id}/events",
        params={"from_event_idx": -1, "limit": 300},
    )
    assert before.status_code == 200
    items = before.json()["items"]
    assert any(item["event_idx"] == 99 and item["kind"] == "subagent_spawn" for item in items)
    assert max(item["event_idx"] for item in items) == 99

    parallel = dashboard_client.get(f"/api/v1/runs/{run_id}/parallel")
    assert parallel.status_code == 200


def test_sse_stream_yields_events(dashboard_client: TestClient, tmp_path: Path) -> None:
    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="sse test")
    session_id = str(recorder.session_id)
    jsonl_path = tmp_path / "traces" / f"{session_id}.jsonl"
    assert jsonl_path.is_file()

    with dashboard_client.stream(
        "GET",
        f"/api/v1/sessions/{session_id}/stream",
        params={"from_event_idx": -1, "max_ticks": "2"},
        timeout=5.0,
    ) as response:
        assert response.status_code == 200
        chunks = []
        for line in response.iter_lines():
            if line:
                chunks.append(line)
            if len(chunks) > 5:
                break
        text = "\n".join(chunks)
        assert "event:" in text or "data:" in text
