"""OpenRouter provider routing env → extra_body (no network)."""

from __future__ import annotations

import pytest

from vg_agent.agent import (
    _emit_expensive_provider_warning,
    _is_expensive_openrouter_provider,
    run_live_task,
)
from vg_agent.budget import BudgetGuard
from vg_agent.live_model_client import (
    ModelTurn,
    _extract_openrouter_provider,
    _openrouter_extra_body,
    _openrouter_provider_body,
    _parse_csv_env,
)
from vg_agent.trace import TraceRecorder
from tests.test_vg_agent import FakeClient


def test_parse_csv_env_splits_and_strips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "alibaba, deepinfra")
    assert _parse_csv_env("OPENROUTER_PROVIDER_ORDER") == ["alibaba", "deepinfra"]


def test_parse_csv_env_empty_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_PROVIDER_ORDER", raising=False)
    assert _parse_csv_env("OPENROUTER_PROVIDER_ORDER") is None
    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "  ,  ")
    assert _parse_csv_env("OPENROUTER_PROVIDER_ORDER") is None


def test_openrouter_provider_body_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "OPENROUTER_PROVIDER_ORDER",
        "OPENROUTER_PROVIDER_ONLY",
        "OPENROUTER_PROVIDER_ONLY_DEEPSEEK",
        "OPENROUTER_PROVIDER_SORT",
        "OPENROUTER_PROVIDER_ALLOW_FALLBACKS",
    ):
        monkeypatch.delenv(name, raising=False)
    model = "openrouter/google/gemini-2.5-flash-lite"
    assert _openrouter_provider_body(model) is None
    assert _openrouter_extra_body(model) is None


def test_openrouter_provider_body_global(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_PROVIDER_ONLY_DEEPSEEK", raising=False)
    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "alibaba")
    monkeypatch.setenv("OPENROUTER_PROVIDER_ONLY", "alibaba,deepinfra")
    monkeypatch.setenv("OPENROUTER_PROVIDER_SORT", "price")
    monkeypatch.setenv("OPENROUTER_PROVIDER_ALLOW_FALLBACKS", "false")
    model = "openrouter/google/gemini-2.5-flash-lite"
    assert _openrouter_provider_body(model) == {
        "order": ["alibaba"],
        "only": ["alibaba", "deepinfra"],
        "sort": "price",
        "allow_fallbacks": False,
    }


def test_openrouter_provider_only_deepseek(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_PROVIDER_ORDER", raising=False)
    monkeypatch.delenv("OPENROUTER_PROVIDER_ONLY", raising=False)
    monkeypatch.setenv("OPENROUTER_PROVIDER_ONLY_DEEPSEEK", "baidu/fp8, deepinfra/fp4")
    deepseek = "openrouter/deepseek/deepseek-v4-flash"
    gemini = "openrouter/google/gemini-2.5-flash-lite"
    assert _openrouter_extra_body(deepseek) == {
        "provider": {"only": ["baidu/fp8", "deepinfra/fp4"]},
    }
    assert _openrouter_extra_body(gemini) is None


def test_extract_openrouter_provider_from_response() -> None:
    assert _extract_openrouter_provider({"provider": "novita"}) == "novita"
    assert _extract_openrouter_provider({"_hidden_params": {"provider": "alibaba"}}) == "alibaba"
    assert _extract_openrouter_provider(
        {"_hidden_params": {"original_response": {"provider": "deepinfra"}}}
    ) == "deepinfra"
    assert _extract_openrouter_provider({}) is None


def test_is_expensive_openrouter_provider() -> None:
    assert _is_expensive_openrouter_provider("alibaba")
    assert _is_expensive_openrouter_provider("Alibaba/cloud")
    assert _is_expensive_openrouter_provider("morph")
    assert _is_expensive_openrouter_provider("parasail/fp8")
    assert not _is_expensive_openrouter_provider("novita")
    assert not _is_expensive_openrouter_provider("baidu/fp8")


def test_expensive_provider_warning_once_per_slug(tmp_path) -> None:
    recorder = TraceRecorder(tmp_path)
    guard = BudgetGuard(max_steps=5, max_tokens=10_000, max_usd=1.0)
    for _ in range(2):
        _emit_expensive_provider_warning(
            recorder,
            guard,
            openrouter_provider="alibaba",
            model_id="openrouter/deepseek/deepseek-v4-flash",
            step_idx=1,
            agent_id="parent",
            cost_usd=0.01,
        )
    warns = [
        e
        for e in recorder.events
        if e.get("kind") == "budget_event" and e.get("budget_reason") == "warn_expensive_provider"
    ]
    assert len(warns) == 1
    assert warns[0]["details"]["openrouter_provider"] == "alibaba"


def test_assistant_step_trace_includes_openrouter_provider(tmp_path) -> None:
    recorder = TraceRecorder(tmp_path)
    client = FakeClient(
        [
            ModelTurn(
                "done",
                input_tokens=10,
                output_tokens=5,
                openrouter_provider="novita",
            )
        ]
    )
    run_live_task(
        tmp_path,
        "say done",
        recorder=recorder,
        client=client,
        guard=BudgetGuard(max_steps=3, max_tokens=10_000, max_usd=1.0),
    )
    steps = [e for e in recorder.events if e.get("kind") == "assistant_step"]
    assert steps
    assert steps[0].get("openrouter_provider") == "novita"
