"""Generated LiteLLM OpenRouter live-model client."""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import sys
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from . import config


class _LiteLLMNoiseFilter(io.TextIOBase):
    """Drops LiteLLM's raw ``print()`` calls (e.g. the red ``Provider List`` banner)
    while letting through anything else written to the wrapped stream."""

    _DROP_MARKERS = ("Provider List:", "GetLLMProvider")

    def __init__(self, wrapped: Any) -> None:
        self._wrapped = wrapped
        self._buffer = ""

    @property
    def encoding(self) -> str | None:
        return getattr(self._wrapped, "encoding", None)

    @property
    def errors(self) -> str | None:
        return getattr(self._wrapped, "errors", None)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)

    def write(self, text: str) -> int:
        self._buffer += text
        if "\n" in self._buffer:
            lines = self._buffer.split("\n")
            self._buffer = lines.pop()
            for line in lines:
                if not any(marker in line for marker in self._DROP_MARKERS):
                    self._wrapped.write(line + "\n")
        return len(text)

    def isatty(self) -> bool:
        return bool(getattr(self._wrapped, "isatty", lambda: False)())

    def fileno(self) -> int:
        return self._wrapped.fileno()

    def writable(self) -> bool:
        return True

    def flush(self) -> None:
        if self._buffer:
            if not any(marker in self._buffer for marker in self._DROP_MARKERS):
                self._wrapped.write(self._buffer)
            self._buffer = ""
        self._wrapped.flush()


class MissingOpenRouterKey(RuntimeError):
    pass


class EndpointPinViolation(RuntimeError):
    pass


class LiveModelError(RuntimeError):
    retryable = False


class LiveModelRateLimitError(LiveModelError):
    retryable = True

    def __init__(self, message: str, *, provider_detail: str | None = None) -> None:
        super().__init__(message)
        self.provider_detail = provider_detail


@dataclass
class ToolCall:
    tool_use_id: str
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelTurn:
    assistant_text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0
    raw_content: list[dict[str, Any]] = field(default_factory=list)
    model_id: str = ""
    cost_usd: float | None = None
    openrouter_provider: str | None = None


class LiveModelClient:
    endpoint = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str, endpoint: str | None = None, recorder: Any | None = None) -> None:
        self.api_key = api_key
        self.recorder = recorder
        if endpoint is not None:
            self.endpoint = endpoint

    @classmethod
    def from_env(cls, recorder: Any | None = None) -> "LiveModelClient":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise MissingOpenRouterKey("OPENROUTER_API_KEY is required when --live-model is used")
        return cls(api_key, recorder=recorder)

    def _assert_endpoint_pinned(self) -> None:
        parsed_url = urllib.parse.urlparse(self.endpoint)
        if parsed_url.hostname != config.OPENROUTER_ENDPOINT_HOST:
            if self.recorder is not None:
                self.recorder.emit(
                    "egress_blocked",
                    host=parsed_url.hostname,
                    expected_host=config.OPENROUTER_ENDPOINT_HOST,
                    endpoint=self.endpoint,
                )
            raise EndpointPinViolation(
                f"refusing to call non-pinned host {parsed_url.hostname!r}; "
                f"endpoint must use {config.OPENROUTER_ENDPOINT_HOST!r}"
            )

    def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 4096,
    ) -> ModelTurn:
        self._assert_endpoint_pinned()
        if not model.startswith("openrouter/"):
            raise RuntimeError(f"live model id must use LiteLLM OpenRouter form 'openrouter/...': {model!r}")

        logging.getLogger("LiteLLM").setLevel(logging.ERROR)
        logging.getLogger("litellm").setLevel(logging.ERROR)
        os.environ.setdefault("LITELLM_LOG", "ERROR")
        try:
            import litellm
        except ImportError as exc:
            raise RuntimeError("LiteLLM is required for --live-model runs; install the project dependencies") from exc
        litellm.suppress_debug_info = True
        litellm.set_verbose = False

        stdout_filter = _LiteLLMNoiseFilter(sys.stdout)
        stderr_filter = _LiteLLMNoiseFilter(sys.stderr)
        extra_body = _openrouter_extra_body(model)
        completion_kwargs: dict[str, Any] = {
            "model": model,
            "messages": _to_litellm_messages(system_prompt, messages),
            "tools": _to_litellm_tools(tools) if tools else None,
            "max_tokens": max_tokens,
            "api_key": self.api_key,
            "api_base": self.endpoint,
            "extra_headers": _openrouter_headers(),
        }
        if extra_body is not None:
            completion_kwargs["extra_body"] = extra_body
        with contextlib.redirect_stdout(stdout_filter), contextlib.redirect_stderr(stderr_filter):
            try:
                response = litellm.completion(**completion_kwargs)
            except Exception as exc:
                if _is_rate_limit_error(exc):
                    raise LiveModelRateLimitError(
                        _rate_limit_message(model),
                        provider_detail=_provider_error_detail(exc),
                    ) from exc
                raise
            finally:
                stdout_filter.flush()
                stderr_filter.flush()
        return _normalise_response(response, model)


LiteLLMOpenRouterClient = LiveModelClient


def _openrouter_headers() -> dict[str, str] | None:
    headers: dict[str, str] = {}
    site_url = os.environ.get("OPENROUTER_SITE_URL")
    app_name = os.environ.get("OPENROUTER_APP_NAME")
    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_name:
        headers["X-Title"] = app_name
    return headers or None


def _parse_csv_env(name: str) -> list[str] | None:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return None
    parts = [part.strip() for part in str(raw).split(",")]
    slugs = [part for part in parts if part]
    return slugs or None


def _openrouter_provider_body(model: str) -> dict[str, Any] | None:
    model_lower = model.lower()
    if "/deepseek/" in model_lower:
        only_deepseek = _parse_csv_env("OPENROUTER_PROVIDER_ONLY_DEEPSEEK")
        if only_deepseek is not None:
            return {"only": only_deepseek}
    provider: dict[str, Any] = {}
    order = _parse_csv_env("OPENROUTER_PROVIDER_ORDER")
    if order is not None:
        provider["order"] = order
    only = _parse_csv_env("OPENROUTER_PROVIDER_ONLY")
    if only is not None:
        provider["only"] = only
    sort_raw = os.environ.get("OPENROUTER_PROVIDER_SORT")
    if sort_raw is not None and str(sort_raw).strip():
        provider["sort"] = str(sort_raw).strip()
    allow_raw = os.environ.get("OPENROUTER_PROVIDER_ALLOW_FALLBACKS")
    if allow_raw is not None and str(allow_raw).strip():
        provider["allow_fallbacks"] = str(allow_raw).strip().lower() in ("1", "true", "yes", "on")
    if not provider:
        return None
    return provider


def _openrouter_extra_body(model: str) -> dict[str, Any] | None:
    provider = _openrouter_provider_body(model)
    if provider is None:
        return None
    return {"provider": provider}


def _to_litellm_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for tool in tools:
        converted.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return converted


def _to_litellm_messages(system_prompt: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for message in messages:
        role = str(message.get("role") or "user")
        content = message.get("content", "")
        if role == "assistant" and isinstance(content, list):
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text_parts.append(str(block.get("text", "")))
                elif block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": str(block.get("id", "")),
                        "type": "function",
                        "function": {
                            "name": str(block.get("name", "")),
                            "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                        },
                    })
            converted_message: dict[str, Any] = {"role": "assistant", "content": "\n".join(text_parts) or None}
            if tool_calls:
                converted_message["tool_calls"] = tool_calls
            converted.append(converted_message)
        elif role == "user" and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    converted.append({
                        "role": "tool",
                        "tool_call_id": str(block.get("tool_use_id", "")),
                        "content": str(block.get("content", "")),
                    })
                else:
                    converted.append({"role": "user", "content": str(block)})
        else:
            converted.append({"role": role, "content": content})
    return converted


def _value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _is_rate_limit_error(exc: BaseException) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True
    class_name = type(exc).__name__.lower()
    text = str(exc).lower()
    return (
        "ratelimit" in class_name
        or "rate_limit" in class_name
        or "429" in text
        or "too many requests" in text
        or "temporarily rate-limited" in text
        or "rate limited" in text
    )


def _rate_limit_message(model: str) -> str:
    return (
        f"live model provider rate-limited {model}. Retry shortly, switch models, "
        "or add your own provider key in OpenRouter integrations."
    )


def _provider_error_detail(exc: BaseException) -> str | None:
    flag = os.environ.get("VG_PROVIDER_ERROR_DETAIL", "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return None
    text = str(exc).strip()
    if not text:
        return None
    if len(text) > 4000:
        text = text[:4000] + "…"
    from .trace import _redact

    redacted, _ = _redact(text)
    return redacted


def _normalise_response(response: Any, requested_model: str) -> ModelTurn:
    choices = _value(response, "choices", []) or []
    choice = choices[0] if choices else {}
    message = _value(choice, "message", {}) or {}
    content = _value(message, "content", "") or ""
    stop_reason = str(_value(choice, "finish_reason", None) or "end_turn")
    tool_calls: list[ToolCall] = []
    raw_content: list[dict[str, Any]] = []
    if content:
        raw_content.append({"type": "text", "text": str(content)})
    for call in _value(message, "tool_calls", []) or []:
        function = _value(call, "function", {}) or {}
        args_raw = _value(function, "arguments", "{}") or "{}"
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
        except (TypeError, ValueError):
            args = {"_raw_arguments": str(args_raw)}
        tool_call = ToolCall(
            tool_use_id=str(_value(call, "id", "")),
            name=str(_value(function, "name", "")),
            args=args,
        )
        tool_calls.append(tool_call)
        raw_content.append({
            "type": "tool_use",
            "id": tool_call.tool_use_id,
            "name": tool_call.name,
            "input": tool_call.args,
        })
    usage = _value(response, "usage", {}) or {}
    cost = _extract_cost_usd(response)
    return ModelTurn(
        assistant_text=str(content),
        tool_calls=tool_calls,
        stop_reason=stop_reason,
        input_tokens=int(_value(usage, "prompt_tokens", _value(usage, "input_tokens", 0)) or 0),
        output_tokens=int(_value(usage, "completion_tokens", _value(usage, "output_tokens", 0)) or 0),
        raw_content=raw_content,
        model_id=requested_model,
        cost_usd=cost,
        openrouter_provider=_extract_openrouter_provider(response),
    )


def _extract_openrouter_provider(response: Any) -> str | None:
    """OpenRouter backend slug (e.g. novita, alibaba) from a completion response."""
    value = _value(response, "provider", None)
    if value:
        return str(value)
    hidden = _value(response, "_hidden_params", {}) or {}
    value = _value(hidden, "provider", None)
    if value:
        return str(value)
    original = _value(hidden, "original_response", None)
    if original is not None:
        if isinstance(original, str):
            try:
                original = json.loads(original)
            except (TypeError, ValueError):
                original = None
        value = _value(original, "provider", None)
        if value:
            return str(value)
    return None


def _extract_cost_usd(response: Any) -> float | None:
    for key in ("response_cost", "cost", "cost_usd"):
        value = _value(response, key, None)
        if value is not None:
            return float(value)
    hidden = _value(response, "_hidden_params", {}) or {}
    value = _value(hidden, "response_cost", None)
    return float(value) if value is not None else None
