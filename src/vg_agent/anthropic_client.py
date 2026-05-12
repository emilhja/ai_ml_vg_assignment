"""Generated Anthropic Messages API client."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


class MissingAnthropicKey(RuntimeError):
    pass


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


class AnthropicClient:
    endpoint = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, endpoint: str | None = None) -> None:
        self.api_key = api_key
        if endpoint is not None:
            self.endpoint = endpoint

    @classmethod
    def from_env(cls) -> "AnthropicClient":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise MissingAnthropicKey("ANTHROPIC_API_KEY is required when --live-model is used")
        return cls(api_key)

    def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 4096,
    ) -> ModelTurn:
        payload = {
            "model": model,
            "system": system_prompt,
            "messages": messages,
            "tools": tools,
            "max_tokens": max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=data,
            headers={
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Anthropic API error {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Anthropic API request failed: {exc.reason}") from exc

        content = parsed.get("content", [])
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        raw_content: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            raw_content.append(block)
            if block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    ToolCall(
                        tool_use_id=str(block.get("id", "")),
                        name=str(block.get("name", "")),
                        args=dict(block.get("input") or {}),
                    )
                )
        usage = parsed.get("usage") or {}
        return ModelTurn(
            assistant_text="\n".join(part for part in text_parts if part),
            tool_calls=tool_calls,
            stop_reason=str(parsed.get("stop_reason") or ("tool_use" if tool_calls else "end_turn")),
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            raw_content=raw_content,
        )
