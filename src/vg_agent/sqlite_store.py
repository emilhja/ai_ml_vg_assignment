"""SQLite observability mirror for generated trace events."""

from __future__ import annotations

import hashlib
import json
import platform
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config


SCHEMA_VERSION = 1


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_ms(started_at: Any, ended_at: Any) -> int | None:
    start = _parse_iso(started_at)
    end = _parse_iso(ended_at)
    if start is None or end is None:
        return None
    return max(0, int((end - start).total_seconds() * 1000))


def _provider(model_id: Any) -> str | None:
    text = str(model_id or "")
    if "/" in text:
        return text.split("/", 1)[0]
    return text or None


def _openrouter_provider_slug(event: dict[str, object]) -> str | None:
    """OpenRouter backend slug from trace (novita, alibaba, …)."""
    slug = _text(event.get("openrouter_provider"))
    return slug or None


def _args_summary(tool: str, args: Any) -> tuple[str | None, str | None, str | None]:
    if not isinstance(args, dict):
        return None, None, None
    if tool in {"read_file", "read_file_range", "write_file", "edit_file"}:
        path = _text(args.get("path") or args.get("rel_path"))
        if tool == "edit_file":
            old = str(args.get("old") or "")
            new = str(args.get("new") or "")
            return f"{path or ''}  - {old[:40]!r} -> + {new[:40]!r}", path, None
        return path, path, None
    if tool == "run_bash":
        command = _text(args.get("command"))
        return command, None, command
    if tool == "spawn_subagent":
        return str(args.get("question") or "")[:120], None, None
    if tool == "spawn_subagents":
        requests = args.get("requests") or []
        count = len(requests) if isinstance(requests, list) else "?"
        return f"{count} sub-agent requests", None, None
    return _json(args)[:160], None, None


def _git_commit(root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


class SQLiteTraceStore:
    """Mirrors redacted trace events into queryable SQLite tables."""

    def __init__(self, root: Path, *, db_path: Path | None = None, redaction_enabled: bool = True) -> None:
        self.root = Path(root)
        self.path = db_path or self.root / config.SQLITE_TRACE_DB
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.redaction_enabled = redaction_enabled
        self.git_commit = _git_commit(self.root)
        self._write_lock = threading.Lock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                schema_version INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL,
                app_version TEXT,
                spec_digest TEXT,
                python_version TEXT,
                platform TEXT,
                git_commit TEXT
            );

            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                first_seen_at TEXT,
                last_seen_at TEXT,
                run_count INTEGER DEFAULT 0,
                total_turns INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                total_cost_usd REAL DEFAULT 0,
                status TEXT,
                redaction_enabled INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                session_id TEXT,
                started_at TEXT,
                ended_at TEXT,
                duration_ms INTEGER,
                final_status TEXT,
                total_tokens INTEGER DEFAULT 0,
                total_cost_usd REAL DEFAULT 0,
                live_model INTEGER,
                redaction_enabled INTEGER DEFAULT 1,
                app_version TEXT,
                spec_digest TEXT,
                python_version TEXT,
                platform TEXT,
                git_commit TEXT
            );

            CREATE TABLE IF NOT EXISTS turns (
                turn_id TEXT PRIMARY KEY,
                run_id TEXT,
                session_id TEXT,
                turn_index INTEGER,
                prompt TEXT,
                prompt_sha256 TEXT,
                started_at TEXT,
                ended_at TEXT,
                duration_ms INTEGER,
                status TEXT,
                error_type TEXT,
                error_message TEXT,
                total_model_calls INTEGER DEFAULT 0,
                total_tool_calls INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                total_cost_usd REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS events (
                run_id TEXT NOT NULL,
                session_id TEXT,
                turn_id TEXT,
                event_idx INTEGER NOT NULL,
                timestamp_iso TEXT,
                agent_id TEXT,
                parent_id TEXT,
                kind TEXT NOT NULL,
                model_id TEXT,
                tool TEXT,
                status TEXT,
                tokens_in INTEGER,
                tokens_out INTEGER,
                cost_usd REAL,
                latency_ms INTEGER,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (run_id, event_idx)
            );

            CREATE TABLE IF NOT EXISTS model_calls (
                model_call_id TEXT PRIMARY KEY,
                run_id TEXT,
                session_id TEXT,
                turn_id TEXT,
                agent_id TEXT,
                parent_id TEXT,
                step_idx INTEGER,
                model_id TEXT,
                provider TEXT,
                endpoint_host TEXT,
                max_tokens INTEGER,
                temperature REAL,
                system_prompt_sha256 TEXT,
                tool_schema_count INTEGER,
                tool_schema_names_json TEXT,
                context_tokens INTEGER,
                tokens_in INTEGER,
                tokens_out INTEGER,
                cost_usd REAL,
                stop_reason TEXT,
                started_at TEXT,
                ended_at TEXT,
                latency_ms INTEGER,
                status TEXT,
                payload_json TEXT
            );

            CREATE TABLE IF NOT EXISTS tool_calls (
                tool_call_id TEXT PRIMARY KEY,
                run_id TEXT,
                session_id TEXT,
                turn_id TEXT,
                agent_id TEXT,
                parent_id TEXT,
                tool_use_id TEXT,
                tool TEXT,
                args_summary TEXT,
                target_path TEXT,
                command_summary TEXT,
                started_at TEXT,
                ended_at TEXT,
                latency_ms INTEGER,
                status TEXT,
                error_type TEXT,
                error_message TEXT,
                bytes INTEGER,
                tokens INTEGER,
                payload_json TEXT
            );

            CREATE TABLE IF NOT EXISTS subagents (
                subagent_id TEXT PRIMARY KEY,
                run_id TEXT,
                session_id TEXT,
                turn_id TEXT,
                parent_agent_id TEXT,
                agent_type TEXT,
                question TEXT,
                started_at TEXT,
                ended_at TEXT,
                duration_ms INTEGER,
                status TEXT,
                total_tokens INTEGER,
                total_cost_usd REAL
            );

            CREATE TABLE IF NOT EXISTS approvals (
                approval_id TEXT PRIMARY KEY,
                run_id TEXT,
                session_id TEXT,
                turn_id TEXT,
                event_idx INTEGER,
                tool_use_id TEXT,
                tool TEXT,
                args_summary TEXT,
                decision TEXT,
                scope_key TEXT,
                reason TEXT,
                timestamp_iso TEXT,
                wait_ms INTEGER
            );

            CREATE TABLE IF NOT EXISTS redactions (
                redaction_id TEXT PRIMARY KEY,
                run_id TEXT,
                session_id TEXT,
                turn_id TEXT,
                event_idx INTEGER,
                original_event_idx INTEGER,
                pattern TEXT,
                count INTEGER,
                timestamp_iso TEXT
            );

            CREATE TABLE IF NOT EXISTS compactions (
                compaction_id TEXT PRIMARY KEY,
                run_id TEXT,
                session_id TEXT,
                turn_id TEXT,
                event_idx INTEGER,
                tool_use_id TEXT,
                original_event_idx INTEGER,
                before_tokens INTEGER,
                after_tokens INTEGER,
                tokens_removed INTEGER,
                original_sha256 TEXT,
                summary TEXT,
                timestamp_iso TEXT
            );
            """
        )
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_events_turn ON events(turn_id)",
            "CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind)",
            "CREATE INDEX IF NOT EXISTS idx_events_time ON events(timestamp_iso)",
            "CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent_id)",
            "CREATE INDEX IF NOT EXISTS idx_model_turn ON model_calls(turn_id)",
            "CREATE INDEX IF NOT EXISTS idx_model_model ON model_calls(model_id)",
            "CREATE INDEX IF NOT EXISTS idx_tool_turn ON tool_calls(turn_id)",
            "CREATE INDEX IF NOT EXISTS idx_tool_tool ON tool_calls(tool)",
            "CREATE INDEX IF NOT EXISTS idx_tool_status ON tool_calls(status)",
            "CREATE INDEX IF NOT EXISTS idx_turn_session ON turns(session_id)",
        ]
        for statement in indexes:
            self.conn.execute(statement)
        self.conn.execute(
            """
            INSERT OR IGNORE INTO schema_meta
            (schema_version, created_at, app_version, spec_digest, python_version, platform, git_commit)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                SCHEMA_VERSION,
                datetime.now().astimezone().isoformat(),
                "0.1.0",
                config.SPEC_DIGEST,
                sys.version.split()[0],
                platform.platform(),
                self.git_commit,
            ),
        )
        self.conn.commit()

    def record_event(self, event: dict[str, object]) -> None:
        with self._write_lock:
            payload = _json(event)
            self._upsert_session(event)
            self._upsert_run(event)
            self._insert_event(event, payload)
            kind = str(event.get("kind") or "")
            if kind == "user_prompt":
                self._record_user_prompt(event)
            elif kind == "llm_start":
                self._record_llm_start(event, payload)
            elif kind == "assistant_step":
                self._record_assistant_step(event, payload)
            elif kind == "tool_call":
                self._record_tool_call(event, payload)
            elif kind == "tool_result":
                self._record_tool_result(event, payload)
            elif kind == "subagent_spawn":
                self._record_subagent_spawn(event)
            elif kind == "subagent_return":
                self._record_subagent_return(event)
            elif kind == "approval":
                self._record_approval(event)
            elif kind == "redaction":
                self._record_redaction(event)
            elif kind == "compaction":
                self._record_compaction(event)
            elif kind == "run_end":
                self._record_run_end(event)
            elif kind == "budget_event":
                self._record_budget_event(event)
            self._refresh_rollups(event)
            self.conn.commit()

    def _upsert_session(self, event: dict[str, object]) -> None:
        session_id = _text(event.get("session_id"))
        if session_id is None:
            return
        timestamp = _text(event.get("timestamp_iso"))
        self.conn.execute(
            """
            INSERT INTO sessions (session_id, first_seen_at, last_seen_at, status, redaction_enabled)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                last_seen_at=excluded.last_seen_at,
                redaction_enabled=excluded.redaction_enabled
            """,
            (session_id, timestamp, timestamp, "running", int(self.redaction_enabled)),
        )

    def _upsert_run(self, event: dict[str, object]) -> None:
        run_id = _text(event.get("run_id"))
        if run_id is None:
            return
        timestamp = _text(event.get("timestamp_iso"))
        live_model = event.get("live_model")
        self.conn.execute(
            """
            INSERT INTO runs
            (run_id, session_id, started_at, live_model, redaction_enabled, app_version, spec_digest, python_version, platform, git_commit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                session_id=excluded.session_id,
                live_model=COALESCE(runs.live_model, excluded.live_model),
                redaction_enabled=excluded.redaction_enabled
            """,
            (
                run_id,
                _text(event.get("session_id")),
                timestamp,
                int(bool(live_model)) if live_model is not None else None,
                int(self.redaction_enabled),
                "0.1.0",
                config.SPEC_DIGEST,
                sys.version.split()[0],
                platform.platform(),
                self.git_commit,
            ),
        )

    def _insert_event(self, event: dict[str, object], payload: str) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO events
            (run_id, session_id, turn_id, event_idx, timestamp_iso, agent_id, parent_id, kind,
             model_id, tool, status, tokens_in, tokens_out, cost_usd, latency_ms, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _text(event.get("run_id")),
                _text(event.get("session_id")),
                _text(event.get("turn_id")),
                _int(event.get("event_idx")),
                _text(event.get("timestamp_iso")),
                _text(event.get("agent_id")),
                _text(event.get("parent_id")),
                _text(event.get("kind")),
                _text(event.get("model_id") or event.get("model")),
                _text(event.get("tool")),
                _text(event.get("status") or event.get("final_status")),
                _int(event.get("tokens_in")),
                _int(event.get("tokens_out")),
                _float(event.get("cost_usd") or event.get("total_cost_usd")),
                _int(event.get("latency_ms")),
                payload,
            ),
        )

    def _record_user_prompt(self, event: dict[str, object]) -> None:
        prompt = str(event.get("prompt") or "")
        self.conn.execute(
            """
            INSERT OR REPLACE INTO turns
            (turn_id, run_id, session_id, turn_index, prompt, prompt_sha256, started_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _text(event.get("turn_id")),
                _text(event.get("run_id")),
                _text(event.get("session_id")),
                _int(event.get("turn_index")),
                prompt,
                _sha256_text(prompt),
                _text(event.get("timestamp_iso")),
                "running",
            ),
        )

    def _model_call_id(self, event: dict[str, object]) -> str:
        explicit = _text(event.get("model_call_id"))
        if explicit:
            return explicit
        return ":".join([
            str(event.get("run_id") or ""),
            str(event.get("turn_id") or ""),
            str(event.get("agent_id") or "parent"),
            "model",
            str(event.get("step_idx") or event.get("event_idx") or "0"),
        ])

    def _record_llm_start(self, event: dict[str, object], payload: str) -> None:
        model_id = _text(event.get("model_id") or event.get("model"))
        tool_names = event.get("tool_schema_names")
        self.conn.execute(
            """
            INSERT INTO model_calls
            (model_call_id, run_id, session_id, turn_id, agent_id, parent_id, step_idx, model_id,
             provider, endpoint_host, max_tokens, temperature, system_prompt_sha256,
             tool_schema_count, tool_schema_names_json, context_tokens, started_at, status, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(model_call_id) DO UPDATE SET
                context_tokens=excluded.context_tokens,
                max_tokens=excluded.max_tokens,
                started_at=excluded.started_at,
                payload_json=excluded.payload_json
            """,
            (
                self._model_call_id(event),
                _text(event.get("run_id")),
                _text(event.get("session_id")),
                _text(event.get("turn_id")),
                _text(event.get("agent_id")),
                _text(event.get("parent_id")),
                _int(event.get("step_idx")),
                model_id,
                _openrouter_provider_slug(event),
                _text(event.get("endpoint_host")),
                _int(event.get("max_tokens")),
                _float(event.get("temperature")),
                _text(event.get("system_prompt_sha256")),
                _int(event.get("tool_schema_count")),
                _json(tool_names) if tool_names is not None else None,
                _int(event.get("tokens_in")),
                _text(event.get("timestamp_iso")),
                "started",
                payload,
            ),
        )

    def _record_assistant_step(self, event: dict[str, object], payload: str) -> None:
        model_call_id = self._model_call_id(event)
        row = self.conn.execute(
            "SELECT started_at FROM model_calls WHERE model_call_id = ?",
            (model_call_id,),
        ).fetchone()
        started_at = row[0] if row else None
        ended_at = _text(event.get("timestamp_iso"))
        latency_ms = _duration_ms(started_at, ended_at)
        model_id = _text(event.get("model_id") or event.get("model"))
        self.conn.execute(
            """
            INSERT INTO model_calls
            (model_call_id, run_id, session_id, turn_id, agent_id, parent_id, step_idx,
             model_id, provider, tokens_in, tokens_out, cost_usd, stop_reason,
             started_at, ended_at, latency_ms, status, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(model_call_id) DO UPDATE SET
                model_id=excluded.model_id,
                provider=excluded.provider,
                tokens_in=excluded.tokens_in,
                tokens_out=excluded.tokens_out,
                cost_usd=excluded.cost_usd,
                stop_reason=excluded.stop_reason,
                ended_at=excluded.ended_at,
                latency_ms=excluded.latency_ms,
                status=excluded.status,
                payload_json=excluded.payload_json
            """,
            (
                model_call_id,
                _text(event.get("run_id")),
                _text(event.get("session_id")),
                _text(event.get("turn_id")),
                _text(event.get("agent_id")),
                _text(event.get("parent_id")),
                _int(event.get("step_idx")),
                model_id,
                _openrouter_provider_slug(event),
                _int(event.get("tokens_in")),
                _int(event.get("tokens_out")),
                _float(event.get("cost_usd")),
                _text(event.get("stop_reason")),
                started_at or ended_at,
                ended_at,
                latency_ms,
                "ok",
                payload,
            ),
        )
        self._record_assistant_tool_requests(event)

    def _record_assistant_tool_requests(self, event: dict[str, object]) -> None:
        for idx, call in enumerate(event.get("tool_calls") or []):
            if not isinstance(call, dict):
                continue
            tool = str(call.get("name") or call.get("tool") or "")
            args = call.get("args") or call.get("input") or {}
            tool_use_id = str(call.get("tool_use_id") or call.get("id") or f"tool-{idx}")
            summary, path, command = _args_summary(tool, args)
            tool_call_id = self._tool_call_id(event, tool_use_id)
            self.conn.execute(
                """
                INSERT INTO tool_calls
                (tool_call_id, run_id, session_id, turn_id, agent_id, parent_id, tool_use_id,
                 tool, args_summary, target_path, command_summary, started_at, status, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tool_call_id) DO UPDATE SET
                    tool=excluded.tool,
                    args_summary=excluded.args_summary,
                    target_path=excluded.target_path,
                    command_summary=excluded.command_summary,
                    started_at=COALESCE(tool_calls.started_at, excluded.started_at),
                    payload_json=excluded.payload_json
                """,
                (
                    tool_call_id,
                    _text(event.get("run_id")),
                    _text(event.get("session_id")),
                    _text(event.get("turn_id")),
                    _text(event.get("agent_id")),
                    _text(event.get("parent_id")),
                    tool_use_id,
                    tool,
                    summary,
                    path,
                    command,
                    _text(event.get("timestamp_iso")),
                    "requested",
                    _json(call),
                ),
            )

    def _tool_call_id(self, event: dict[str, object], tool_use_id: str | None = None) -> str:
        explicit = _text(event.get("tool_call_id"))
        if explicit:
            return explicit
        return ":".join([
            str(event.get("run_id") or ""),
            str(event.get("turn_id") or ""),
            str(event.get("agent_id") or "parent"),
            "tool",
            str(tool_use_id or event.get("tool_use_id") or event.get("event_idx") or "0"),
        ])

    def _record_tool_call(self, event: dict[str, object], payload: str) -> None:
        tool = str(event.get("tool") or "")
        args = event.get("args") or {}
        summary, path, command = _args_summary(tool, args)
        summary = _text(event.get("args_summary")) or summary
        self.conn.execute(
            """
            INSERT INTO tool_calls
            (tool_call_id, run_id, session_id, turn_id, agent_id, parent_id, tool_use_id,
             tool, args_summary, target_path, command_summary, started_at, status, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tool_call_id) DO UPDATE SET
                started_at=excluded.started_at,
                args_summary=excluded.args_summary,
                payload_json=excluded.payload_json
            """,
            (
                self._tool_call_id(event),
                _text(event.get("run_id")),
                _text(event.get("session_id")),
                _text(event.get("turn_id")),
                _text(event.get("agent_id")),
                _text(event.get("parent_id")),
                _text(event.get("tool_use_id")),
                tool,
                summary,
                _text(event.get("path")) or path,
                _text(event.get("command")) or command,
                _text(event.get("timestamp_iso")),
                "started",
                payload,
            ),
        )

    def _record_tool_result(self, event: dict[str, object], payload: str) -> None:
        tool_call_id = self._tool_call_id(event, _text(event.get("tool_use_id")))
        row = self.conn.execute(
            "SELECT started_at FROM tool_calls WHERE tool_call_id = ?",
            (tool_call_id,),
        ).fetchone()
        started_at = row[0] if row else None
        ended_at = _text(event.get("timestamp_iso"))
        latency_ms = _int(event.get("latency_ms")) or _duration_ms(started_at, ended_at)
        status = _text(event.get("status"))
        result = str(event.get("result_full") or "")
        error_message = result[:500] if status and status != "ok" else None
        self.conn.execute(
            """
            INSERT INTO tool_calls
            (tool_call_id, run_id, session_id, turn_id, agent_id, parent_id, tool_use_id,
             tool, started_at, ended_at, latency_ms, status, error_type, error_message,
             bytes, tokens, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tool_call_id) DO UPDATE SET
                tool=excluded.tool,
                ended_at=excluded.ended_at,
                latency_ms=excluded.latency_ms,
                status=excluded.status,
                error_type=excluded.error_type,
                error_message=excluded.error_message,
                bytes=excluded.bytes,
                tokens=excluded.tokens,
                payload_json=excluded.payload_json
            """,
            (
                tool_call_id,
                _text(event.get("run_id")),
                _text(event.get("session_id")),
                _text(event.get("turn_id")),
                _text(event.get("agent_id")),
                _text(event.get("parent_id")),
                _text(event.get("tool_use_id")),
                _text(event.get("tool")),
                started_at or ended_at,
                ended_at,
                latency_ms,
                status,
                "tool_error" if status and status != "ok" else None,
                error_message,
                _int(event.get("bytes")),
                _int(event.get("tokens")),
                payload,
            ),
        )

    def _record_subagent_spawn(self, event: dict[str, object]) -> None:
        subagent_id = f"{event.get('run_id')}:{event.get('child_agent_id')}"
        self.conn.execute(
            """
            INSERT INTO subagents
            (subagent_id, run_id, session_id, turn_id, parent_agent_id, agent_type,
             question, started_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(subagent_id) DO UPDATE SET
                question=excluded.question,
                started_at=COALESCE(subagents.started_at, excluded.started_at),
                status=excluded.status
            """,
            (
                subagent_id,
                _text(event.get("run_id")),
                _text(event.get("session_id")),
                _text(event.get("turn_id")),
                _text(event.get("agent_id")),
                "explorer",
                _text(event.get("question")),
                _text(event.get("timestamp_iso")),
                "running",
            ),
        )

    def _record_subagent_return(self, event: dict[str, object]) -> None:
        subagent_id = f"{event.get('run_id')}:{event.get('child_agent_id')}"
        row = self.conn.execute(
            "SELECT started_at FROM subagents WHERE subagent_id = ?",
            (subagent_id,),
        ).fetchone()
        started_at = row[0] if row else None
        ended_at = _text(event.get("timestamp_iso"))
        self.conn.execute(
            """
            INSERT INTO subagents
            (subagent_id, run_id, session_id, turn_id, started_at, ended_at,
             duration_ms, status, total_tokens, total_cost_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(subagent_id) DO UPDATE SET
                ended_at=excluded.ended_at,
                duration_ms=excluded.duration_ms,
                status=excluded.status,
                total_tokens=excluded.total_tokens,
                total_cost_usd=excluded.total_cost_usd
            """,
            (
                subagent_id,
                _text(event.get("run_id")),
                _text(event.get("session_id")),
                _text(event.get("turn_id")),
                started_at or ended_at,
                ended_at,
                _duration_ms(started_at, ended_at),
                _text(event.get("status")) or "ok",
                _int(event.get("child_total_tokens")),
                _float(event.get("child_total_cost_usd")),
            ),
        )

    def _record_approval(self, event: dict[str, object]) -> None:
        approval_id = f"{event.get('run_id')}:{event.get('event_idx')}"
        self.conn.execute(
            """
            INSERT OR REPLACE INTO approvals
            (approval_id, run_id, session_id, turn_id, event_idx, tool_use_id, tool,
             args_summary, decision, scope_key, reason, timestamp_iso, wait_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approval_id,
                _text(event.get("run_id")),
                _text(event.get("session_id")),
                _text(event.get("turn_id")),
                _int(event.get("event_idx")),
                _text(event.get("tool_use_id")),
                _text(event.get("tool")),
                _text(event.get("args_summary")),
                _text(event.get("decision")),
                _text(event.get("scope_key")),
                _text(event.get("reason")),
                _text(event.get("timestamp_iso")),
                _int(event.get("wait_ms")),
            ),
        )

    def _record_redaction(self, event: dict[str, object]) -> None:
        redaction_id = f"{event.get('run_id')}:{event.get('event_idx')}"
        self.conn.execute(
            """
            INSERT OR REPLACE INTO redactions
            (redaction_id, run_id, session_id, turn_id, event_idx, original_event_idx,
             pattern, count, timestamp_iso)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                redaction_id,
                _text(event.get("run_id")),
                _text(event.get("session_id")),
                _text(event.get("turn_id")),
                _int(event.get("event_idx")),
                _int(event.get("original_event_idx")),
                _text(event.get("pattern")),
                _int(event.get("count")),
                _text(event.get("timestamp_iso")),
            ),
        )

    def _record_compaction(self, event: dict[str, object]) -> None:
        before = _int(event.get("before_tokens"))
        after = _int(event.get("after_tokens"))
        self.conn.execute(
            """
            INSERT OR REPLACE INTO compactions
            (compaction_id, run_id, session_id, turn_id, event_idx, tool_use_id,
             original_event_idx, before_tokens, after_tokens, tokens_removed,
             original_sha256, summary, timestamp_iso)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"{event.get('run_id')}:{event.get('event_idx')}",
                _text(event.get("run_id")),
                _text(event.get("session_id")),
                _text(event.get("turn_id")),
                _int(event.get("event_idx")),
                _text(event.get("tool_use_id")),
                _int(event.get("original_event_idx")),
                before,
                after,
                before - after if before is not None and after is not None else None,
                _text(event.get("original_sha256")),
                _text(event.get("summary")),
                _text(event.get("timestamp_iso")),
            ),
        )

    def _record_run_end(self, event: dict[str, object]) -> None:
        run_id = _text(event.get("run_id"))
        row = self.conn.execute("SELECT started_at FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        started_at = row[0] if row else None
        ended_at = _text(event.get("timestamp_iso"))
        self.conn.execute(
            """
            UPDATE runs
            SET ended_at=?, duration_ms=?, final_status=?, total_tokens=?, total_cost_usd=?
            WHERE run_id=?
            """,
            (
                ended_at,
                _duration_ms(started_at, ended_at),
                _text(event.get("final_status")),
                _int(event.get("total_tokens")),
                _float(event.get("total_cost_usd")),
                run_id,
            ),
        )
        self._finalize_turn(event, _text(event.get("final_status")), None, None)

    def _record_budget_event(self, event: dict[str, object]) -> None:
        reason = _text(event.get("budget_reason"))
        if reason in {"step_cap", "token_cap", "usd_cap", "daily_cap", "repetition_abort", "timeout", "user_abort", "parallel_aborted"}:
            self._finalize_turn(event, "aborted", reason, _json(event.get("details") or {}))

    def _finalize_turn(
        self,
        event: dict[str, object],
        status: str | None,
        error_type: str | None,
        error_message: str | None,
    ) -> None:
        turn_id = _text(event.get("turn_id"))
        if turn_id is None:
            return
        row = self.conn.execute("SELECT started_at FROM turns WHERE turn_id = ?", (turn_id,)).fetchone()
        started_at = row[0] if row else None
        ended_at = _text(event.get("timestamp_iso"))
        totals = self.conn.execute(
            """
            SELECT
                COUNT(*),
                COALESCE(SUM(tokens_in + tokens_out), 0),
                COALESCE(SUM(cost_usd), 0)
            FROM model_calls
            WHERE turn_id = ?
            """,
            (turn_id,),
        ).fetchone()
        tool_count = self.conn.execute(
            "SELECT COUNT(*) FROM tool_calls WHERE turn_id = ?",
            (turn_id,),
        ).fetchone()[0]
        self.conn.execute(
            """
            UPDATE turns
            SET ended_at=?, duration_ms=?, status=?, error_type=?, error_message=?,
                total_model_calls=?, total_tool_calls=?, total_tokens=?, total_cost_usd=?
            WHERE turn_id=?
            """,
            (
                ended_at,
                _duration_ms(started_at, ended_at),
                status,
                error_type,
                error_message,
                int(totals[0] or 0),
                int(tool_count or 0),
                int(totals[1] or 0),
                float(totals[2] or 0),
                turn_id,
            ),
        )

    def _refresh_rollups(self, event: dict[str, object]) -> None:
        session_id = _text(event.get("session_id"))
        if session_id is None:
            return
        run_count = self.conn.execute(
            "SELECT COUNT(*) FROM runs WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
        turn_count = self.conn.execute(
            "SELECT COUNT(*) FROM turns WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
        totals = self.conn.execute(
            """
            SELECT COALESCE(SUM(total_tokens), 0), COALESCE(SUM(total_cost_usd), 0)
            FROM turns
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        self.conn.execute(
            """
            UPDATE sessions
            SET run_count=?, total_turns=?, total_tokens=?, total_cost_usd=?,
                status=CASE WHEN ? = 'run_end' THEN 'complete' ELSE COALESCE(status, 'running') END
            WHERE session_id=?
            """,
            (
                int(run_count or 0),
                int(turn_count or 0),
                int(totals[0] or 0),
                float(totals[1] or 0),
                _text(event.get("kind")),
                session_id,
            ),
        )

    def backfill_jsonl_file(self, path: Path) -> int:
        """Replay JSONL events through record_event (idempotent via INSERT OR REPLACE)."""
        events: list[dict[str, object]] = []
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return 0
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        for event in events:
            self.record_event(event)
        return len(events)
