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
    monkeypatch.setattr("dashboard.api.paths._repo_root", lambda: tmp_path.resolve())
    import dashboard.api.db as db_module
    from dashboard.api.paths import clear_path_cache
    from dashboard.api.runtime_config import ensure_runtime_config
    from dashboard.api.services import trace_backfill

    ensure_runtime_config()
    bootstrap = TraceRecorder(tmp_path)
    bootstrap.emit("session_new")
    clear_path_cache()
    db_module._engine = None
    db_module._SessionLocal = None
    trace_backfill._BACKFILLED.clear()

    from dashboard.api.main import app

    client = TestClient(app)
    yield client
    clear_path_cache()
    db_module._engine = None
    db_module._SessionLocal = None
    trace_backfill._BACKFILLED.clear()


def test_list_sessions_backfills_orphan_jsonl(
    dashboard_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlite3

    from dashboard.api.paths import clear_path_cache
    from dashboard.api.services import trace_backfill

    trace_backfill._BACKFILLED.clear()
    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="mirror me on list")
    recorder.emit("run_end", final_status="ok")
    session_id = str(recorder.session_id)
    db_path = tmp_path / "traces" / "vg_agent.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()

    import dashboard.api.db as db_module

    clear_path_cache()
    db_module._engine = None
    db_module._SessionLocal = None
    trace_backfill._BACKFILLED.clear()

    response = dashboard_client.get("/api/v1/sessions")
    assert response.status_code == 200
    row = next(item for item in response.json()["items"] if item["session_id"] == session_id)
    assert row["status"] != "jsonl_only"
    assert row["total_turns"] >= 1


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
    messages = context.json()["messages"]
    assert isinstance(messages, list)
    compacted_msgs = [m for m in messages if m.get("compacted")]
    assert compacted_msgs
    assert compacted_msgs[0].get("compaction_before_tokens", 0) > compacted_msgs[0].get(
        "compaction_after_tokens", 0
    )

    row = next(item for item in items if item["session_id"] == session_id)
    assert row.get("has_tool_compaction") is True

    max_step = dashboard_client.get(f"/api/v1/runs/{run_id}/context/max-step")
    assert max_step.status_code == 200
    body = max_step.json()
    assert body["max_step_idx"] >= 1
    assert isinstance(body.get("compaction_steps"), list)
    assert len(body["compaction_steps"]) >= 1

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


def test_stats_tolerates_null_turn_id_rows(dashboard_client: TestClient, tmp_path: Path) -> None:
    import sqlite3

    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="valid turn")
    db_path = tmp_path / "traces" / "vg_agent.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO turns (turn_id, run_id, session_id, started_at, status) VALUES (NULL, ?, ?, ?, ?)",
            (str(recorder.run_id), str(recorder.session_id), "2020-01-01T00:00:00+00:00", "ok"),
        )
        conn.commit()

    stats = dashboard_client.get("/api/v1/stats", params={"range": "7d"})
    assert stats.status_code == 200
    assert stats.json()["total_turns"] >= 1


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


def test_stats_model_dashboard(dashboard_client: TestClient, tmp_path: Path) -> None:
    import sqlite3
    from datetime import datetime, timedelta, timezone

    from dashboard.api.runtime_config import ensure_runtime_config
    from vg_agent import config

    ensure_runtime_config()

    recorder = TraceRecorder(tmp_path)
    session_id = str(recorder.session_id)
    run_id = str(recorder.run_id)
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(days=1)).isoformat()
    old = (now - timedelta(days=14)).isoformat()

    db_path = tmp_path / "traces" / "vg_agent.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO model_calls
            (model_call_id, run_id, session_id, agent_id, model_id,
             tokens_in, tokens_out, cost_usd, latency_ms, started_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "mc-parent-1",
                    run_id,
                    session_id,
                    "parent",
                    config.PARENT_MODEL_ID,
                    100,
                    50,
                    0.01,
                    200,
                    recent,
                    "ok",
                ),
                (
                    "mc-explorer-1",
                    run_id,
                    session_id,
                    "explorer-1",
                    config.EXPLORER_MODEL_ID,
                    80,
                    40,
                    0.008,
                    150,
                    recent,
                    "ok",
                ),
                (
                    "mc-explorer-1-slot0",
                    run_id,
                    session_id,
                    "explorer-1.0",
                    config.EXPLORER_MODEL_ID,
                    60,
                    30,
                    0.005,
                    120,
                    recent,
                    "ok",
                ),
                (
                    "mc-haiku-old",
                    run_id,
                    session_id,
                    "parent",
                    "openrouter/anthropic/claude-haiku-4.5",
                    20,
                    10,
                    0.021,
                    100,
                    old,
                    "ok",
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO subagents
            (subagent_id, run_id, session_id, agent_type, question, started_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (f"{run_id}:explorer-1", run_id, session_id, "explorer", "auth?", recent, "ok"),
        )
        conn.commit()

    stats = dashboard_client.get("/api/v1/stats", params={"range": "7d"})
    assert stats.status_code == 200
    body = stats.json()

    assert body["configured_models"]
    parent_cfg = next(item for item in body["configured_models"] if item["role"] == "parent")
    assert parent_cfg["model_id"] == config.PARENT_MODEL_ID

    assert body["by_agent_role"]
    role_labels = {item["label"] for item in body["by_agent_role"]}
    assert "parent" in role_labels
    assert "explorer" in role_labels
    assert len(role_labels) == len(body["by_agent_role"])
    explorer_role = next(item for item in body["by_agent_role"] if item["label"] == "explorer")
    assert explorer_role["cost_usd"] == pytest.approx(0.013, abs=1e-6)
    assert explorer_role["count"] == 2

    assert body["models"]
    parent_model = next(m for m in body["models"] if m["model_id"] == config.PARENT_MODEL_ID)
    assert parent_model["call_count"] >= 1
    assert parent_model["active_in_range"] is True
    assert parent_model["last_used_at_all_time"]
    parent_roles = {r["agent_role"] for r in parent_model["by_role"]}
    assert "parent" in parent_roles

    explorer_model = next(m for m in body["models"] if m["model_id"] == config.EXPLORER_MODEL_ID)
    explorer_roles = {r["agent_role"] for r in explorer_model["by_role"]}
    assert "explorer" in explorer_roles

    haiku = next(
        m for m in body["models"] if m["model_id"] == "openrouter/anthropic/claude-haiku-4.5"
    )
    assert haiku["call_count"] == 0
    assert haiku["active_in_range"] is False
    assert haiku["last_used_at_all_time"]
    assert haiku["last_used_at"] is None


def test_stats_configured_models_use_env_overrides(
    dashboard_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    override = "openrouter/anthropic/claude-haiku-4.5"
    monkeypatch.setenv("VG_PARENT_MODEL", override)
    stats = dashboard_client.get("/api/v1/stats", params={"range": "7d"})
    assert stats.status_code == 200
    parent_cfg = next(
        item for item in stats.json()["configured_models"] if item["role"] == "parent"
    )
    assert parent_cfg["model_id"] == override


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


def test_subagent_flags_overlapping_spawns_without_returns() -> None:
    from dashboard.api.services.session_tags import _flags_from_turn_events

    base = "2026-06-01T08:00:04"
    events = [
        {"kind": "user_prompt", "event_idx": 0},
        {
            "kind": "tool_call",
            "tool": "spawn_subagents",
            "event_idx": 1,
        },
        {
            "kind": "subagent_spawn",
            "child_agent_id": "explorer-2.0",
            "agent_id": "explorer-2.0",
            "timestamp_iso": f"{base}.492522+00:00",
            "event_idx": 2,
        },
        {
            "kind": "subagent_spawn",
            "child_agent_id": "explorer-2.1",
            "agent_id": "explorer-2.1",
            "timestamp_iso": f"{base}.497101+00:00",
            "event_idx": 3,
        },
        {
            "kind": "tool_call",
            "agent_id": "explorer-2.0",
            "timestamp_iso": f"{base}.516181+00:00",
            "event_idx": 4,
        },
        {
            "kind": "tool_call",
            "agent_id": "explorer-2.1",
            "timestamp_iso": f"{base}.505445+00:00",
            "event_idx": 5,
        },
    ]
    flags = _flags_from_turn_events(events)
    assert flags.has_subagents is True
    assert flags.has_parallel_subagents is True
    assert flags.has_sequential_subagents is False


def test_subagent_flags_serial_spawn_subagents_returns() -> None:
    from dashboard.api.services.session_tags import _flags_from_turn_events

    events = [
        {"kind": "user_prompt", "event_idx": 0},
        {"kind": "tool_call", "tool": "spawn_subagents", "event_idx": 1},
        {
            "kind": "subagent_return",
            "child_agent_id": "coder-1.0",
            "agent_id": "coder-1.0",
            "started_at": "2026-06-01T08:03:10.047489+00:00",
            "ended_at": "2026-06-01T08:03:29.055551+00:00",
            "event_idx": 2,
        },
        {
            "kind": "subagent_return",
            "child_agent_id": "coder-2",
            "agent_id": "coder-2",
            "started_at": "2026-06-01T08:03:30.178614+00:00",
            "ended_at": "2026-06-01T08:03:34.060463+00:00",
            "event_idx": 3,
        },
    ]
    flags = _flags_from_turn_events(events)
    assert flags.has_subagents is True
    assert flags.has_parallel_subagents is False
    assert flags.has_sequential_subagents is True


def test_compaction_flags_from_jsonl_tool_event() -> None:
    from dashboard.api.services.session_compaction_tags import (
        CompactionFlags,
        _flags_from_events,
        compaction_flags_from_jsonl,
    )

    events = [
        {"kind": "user_prompt", "agent_id": "parent", "prompt": "read log"},
        {"kind": "compaction", "agent_id": "parent", "tool_use_id": "t1", "before_tokens": 5000},
        {
            "kind": "context_compaction",
            "agent_id": "parent",
            "reason": "manual",
            "before_tokens": 80000,
            "after_tokens": 20000,
        },
        {
            "kind": "context_compaction",
            "agent_id": "parent",
            "reason": "auto",
            "before_tokens": 90000,
            "after_tokens": 25000,
        },
    ]
    flags = _flags_from_events(events)
    assert flags == CompactionFlags(
        has_tool_compaction=True,
        has_context_compaction_auto=True,
        has_context_compaction_manual=True,
    )

    empty = compaction_flags_from_jsonl("nonexistent-session-id-xyz")
    assert empty == CompactionFlags()


def test_session_agent_types_present(dashboard_client: TestClient, tmp_path: Path) -> None:
    import json

    recorder = TraceRecorder(tmp_path)
    recorder.emit("user_prompt", prompt="agent type tags")
    recorder.emit("assistant_step", agent_id="parent", agent_type="parent", step_idx=1)
    session_id = str(recorder.session_id)
    run_id = str(recorder.run_id)

    jsonl_path = tmp_path / "traces" / f"{session_id}.jsonl"
    extras = [
        {
            "agent_id": "explorer-1.0",
            "agent_type": "explorer",
            "child_agent_id": "explorer-1.0",
            "event_idx": 50,
            "kind": "subagent_spawn",
            "parent_id": "parent",
            "run_id": run_id,
            "session_id": session_id,
            "timestamp_iso": "2026-06-01T12:00:01+00:00",
            "turn_id": f"{session_id}:turn:1",
            "turn_index": 1,
        },
        {
            "agent_id": "parent",
            "agent_type": "compactor",
            "event_idx": 51,
            "kind": "llm_start",
            "parent_id": "parent",
            "run_id": run_id,
            "session_id": session_id,
            "timestamp_iso": "2026-06-01T12:00:02+00:00",
        },
        {
            "agent_id": "parent",
            "event_idx": 52,
            "kind": "context_compaction",
            "parent_id": "parent",
            "reason": "auto",
            "run_id": run_id,
            "session_id": session_id,
            "timestamp_iso": "2026-06-01T12:00:03+00:00",
        },
    ]
    with jsonl_path.open("a", encoding="utf-8") as handle:
        for row in extras:
            handle.write(json.dumps(row) + "\n")

    listed = dashboard_client.get("/api/v1/sessions")
    assert listed.status_code == 200
    row = next(item for item in listed.json()["items"] if item["session_id"] == session_id)
    types = row["agent_types_present"]
    assert "parent" in types
    assert "explorer" in types
    assert "compactor" in types


def test_history_filter_tool_compaction(dashboard_client: TestClient, tmp_path: Path) -> None:
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
    row = next(item for item in listed.json()["items"] if item["session_id"] == session_id)
    assert row["has_tool_compaction"] is True
    assert row["has_context_compaction_auto"] is False
    assert row["has_context_compaction_manual"] is False


@pytest.mark.parametrize(
    ("session_id", "parallel", "sequential"),
    [
        ("907ec426c934", True, True),
        ("cdf51f5010f5", False, True),
    ],
)
def test_subagent_flags_regression_fixtures(
    session_id: str,
    parallel: bool,
    sequential: bool,
) -> None:
    from pathlib import Path

    from dashboard.api.paths import clear_path_cache
    from dashboard.api.services.session_tags import subagent_flags_from_jsonl

    clear_path_cache()
    if not (Path("traces") / f"{session_id}.jsonl").exists():
        pytest.skip("local trace fixture not present")
    flags = subagent_flags_from_jsonl(session_id)
    assert flags.has_subagents is True
    assert flags.has_parallel_subagents is parallel
    assert flags.has_sequential_subagents is sequential


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
