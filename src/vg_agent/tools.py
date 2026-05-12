"""Generated local tools."""

from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path


SAFE_COMMANDS = {"grep", "rg", "find", "ls", "pwd", "cat", "sed", "head", "tail", "wc"}
DESTRUCTIVE_TOKENS = {
    "rm", "del", "erase", "rmdir", "remove-item", "ri", "rd",
    "mv", "move", "cp", "copy", "chmod", "chown", "mkfs", "dd",
    "curl", "wget", "pip", "npm", "pnpm", "yarn", "uv", "python",
    "powershell", "pwsh", "cmd",
}
SHELL_CONTROL_MARKERS = [";", "&&", "||", "|", ">", "<", "`", "$("]


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def resolve_workspace_path(root: Path, rel_path: str) -> Path:
    root_resolved = root.resolve()
    requested = Path(rel_path)
    if requested.is_absolute():
        raise ValueError(f"path {rel_path!r} must be relative to the workspace")
    resolved = (root_resolved / requested).resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(f"path {rel_path!r} escapes the workspace root")
    return resolved


def _path_token_error(token: str) -> str | None:
    if token.startswith("-"):
        return None
    if token in {".", "./"}:
        return None
    looks_like_path = "/" in token or "\\" in token or token in {".."} or token.startswith("~")
    if not looks_like_path:
        return None
    candidate = Path(token)
    if candidate.is_absolute() or token.startswith("~"):
        return f"path token {token!r} must stay inside the workspace"
    if ".." in candidate.parts:
        return f"path token {token!r} escapes the workspace root"
    return None


def validate_shell_command(command: str) -> str | None:
    lowered = command.lower()
    for marker in SHELL_CONTROL_MARKERS:
        if marker in lowered:
            return f"shell control or redirection marker {marker!r} is not allowed"
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as exc:
        return f"could not parse command: {exc}"
    if not tokens:
        return "empty command is not allowed"
    normalized = []
    for token in tokens:
        base = Path(token).name.lower()
        if base.endswith(".exe"):
            base = base[:-4]
        normalized.append(base)
    if normalized[0] not in SAFE_COMMANDS:
        return f"command {normalized[0]!r} is not in the read-only allowlist"
    for token in normalized:
        if token in DESTRUCTIVE_TOKENS:
            return f"destructive token {token!r} is not allowed"
    for token in tokens[1:]:
        path_error = _path_token_error(token)
        if path_error:
            return path_error
    return None


def _result(tool_use_id: str, tool: str, content: str, status: str, started: float) -> dict[str, object]:
    return {
        "tool_use_id": tool_use_id,
        "tool": tool,
        "result_full": content,
        "bytes": len(content.encode("utf-8")),
        "tokens": estimate_tokens(content),
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "status": status,
    }


def read_file(root: Path, rel_path: str, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    try:
        path = resolve_workspace_path(root, rel_path)
        content = path.read_text(encoding="utf-8")
        return _result(tool_use_id, "read_file", content, "ok", started)
    except (OSError, ValueError) as exc:
        return _result(tool_use_id, "read_file", str(exc), "error", started)


def read_file_range(root: Path, rel_path: str, start_line: int, end_line: int, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    try:
        path = resolve_workspace_path(root, rel_path)
        lines = path.read_text(encoding="utf-8").splitlines()
        content = "\n".join(lines[max(0, int(start_line) - 1):int(end_line)])
        return _result(tool_use_id, "read_file_range", content, "ok", started)
    except (OSError, ValueError) as exc:
        return _result(tool_use_id, "read_file_range", str(exc), "error", started)


def write_file(root: Path, rel_path: str, content: str, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    try:
        path = resolve_workspace_path(root, rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        return _result(tool_use_id, "write_file", f"wrote {rel_path}", "ok", started)
    except (OSError, ValueError) as exc:
        return _result(tool_use_id, "write_file", str(exc), "error", started)


def edit_file(root: Path, rel_path: str, old: str, new: str, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    try:
        path = resolve_workspace_path(root, rel_path)
        content = path.read_text(encoding="utf-8")
        if old not in content:
            return _result(tool_use_id, "edit_file", f"old text not found in {rel_path}", "error", started)
        path.write_text(content.replace(old, new), encoding="utf-8", newline="\n")
        return _result(tool_use_id, "edit_file", f"edited {rel_path}", "ok", started)
    except (OSError, ValueError) as exc:
        return _result(tool_use_id, "edit_file", str(exc), "error", started)


def run_bash(root: Path, command: str, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    safety_error = validate_shell_command(command)
    if safety_error:
        return _result(tool_use_id, "run_bash", f"refused unsafe command: {safety_error}", "error", started)
    completed = subprocess.run(["bash", "-c", command], cwd=root, text=True, capture_output=True, timeout=30)
    content = completed.stdout + completed.stderr
    status = "ok" if completed.returncode == 0 else "error"
    return _result(tool_use_id, "run_bash", content, status, started)
