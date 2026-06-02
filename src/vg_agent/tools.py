"""Generated local tools."""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

TOOL_TIMEOUT = 30
MAX_TOOL_RESULT_BYTES = 1_048_576


SAFE_COMMANDS = {"grep", "rg", "find", "ls", "pwd", "cat", "head", "tail", "wc", "rm", "mkdir"}
DESTRUCTIVE_TOKENS = {
    "del", "erase", "rmdir", "remove-item", "ri", "rd",
    "mv", "move", "cp", "copy", "chmod", "chown", "mkfs", "dd",
    "curl", "wget", "pip", "npm", "pnpm", "yarn", "uv", "python",
    "powershell", "pwsh", "cmd",
    "nc", "ncat", "netcat", "ssh", "scp", "rsync", "ftp", "git",
    "sftp", "telnet", "socat",
}
FORBIDDEN_ARG_TOKENS = {
    "-exec", "-execdir", "-delete", "-ok", "-okdir",
    "-fprint", "-fprintf", "-fls",
}
SHELL_CONTROL_MARKERS = [";", "&&", "||", "|", ">", "<", "`", "$("]
GLOB_MARKERS = ["*", "?", "["]

SENSITIVE_PATH_PATTERNS = [
    re.compile(r"(?:^|/)\.env(?:$|\.(?!example))"),
    re.compile(r"(?:^|/)id_rsa(?:\..*)?$"),
    re.compile(r"(?:^|/)id_ed25519(?:\..*)?$"),
    re.compile(r"\.pem$"),
    re.compile(r"\.key$"),
    re.compile(r"\.pfx$"),
    re.compile(r"\.p12$"),
    re.compile(r"(?:^|/)\.aws/"),
    re.compile(r"(?:^|/)\.ssh/"),
    re.compile(r"(?:^|/)\.netrc$"),
    re.compile(r"(?:^|/)credentials(?:\.json)?$"),
    re.compile(r"(?:^|/)\.vg_daily_spend\.json$"),
    re.compile(r"(?:^|/)\.vg_approvals\.json$"),
]


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


def _sensitive_path_hint(normalized: str) -> str:
    if re.search(r"(?:^|/)\.env(?:$|\.(?!example))", normalized):
        return "Use '.env.example' for variable names without secret values."
    if re.search(r"(?:^|/)id_rsa(?:\..*)?$", normalized) or re.search(
        r"(?:^|/)id_ed25519(?:\..*)?$", normalized
    ):
        return "SSH private keys cannot be read or written by the agent."
    if normalized.endswith((".pem", ".key", ".pfx", ".p12")):
        return "Cryptographic key files are blocked."
    if re.search(r"(?:^|/)\.aws/", normalized) or re.search(
        r"(?:^|/)credentials(?:\.json)?$", normalized
    ):
        return "Cloud credential files are blocked."
    if re.search(r"(?:^|/)\.ssh/", normalized):
        return "SSH credential directories are blocked."
    if re.search(r"(?:^|/)\.netrc$", normalized):
        return "Netrc credential files are blocked."
    if re.search(r"(?:^|/)\.vg_daily_spend\.json$", normalized) or re.search(
        r"(?:^|/)\.vg_approvals\.json$", normalized
    ):
        return "Internal governance files are not accessible to the agent."
    return "Secrets and credentials cannot be read or written by the agent."


def validate_sensitive_path(rel_path: str) -> str | None:
    normalized = rel_path.replace("\\", "/")
    if normalized.endswith(".env.example") or normalized == ".env.example":
        return None
    for pattern in SENSITIVE_PATH_PATTERNS:
        if pattern.search(normalized):
            hint = _sensitive_path_hint(normalized)
            return f"sensitive path: cannot access {rel_path!r} - blocked for safety. {hint}"
    return None


def _path_token_error(token: str) -> str | None:
    if token.startswith("-"):
        return None
    if token in {".", "./"}:
        return None
    looks_like_path = "/" in token or "\\" in token or token in {".."} or token.startswith("~")
    if not looks_like_path:
        return None
    candidate = Path(token)
    if candidate.is_absolute() or token.startswith("~") or token.startswith("/"):
        return f"path token {token!r} must stay inside the workspace"
    if ".." in candidate.parts:
        return f"path token {token!r} escapes the workspace root"
    return None


def rm_delete_target(command: str) -> str | None:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return None
    if not tokens:
        return None
    head = Path(tokens[0]).name.lower()
    if head.endswith(".exe"):
        head = head[:-4]
    if head != "rm" or len(tokens) != 2:
        return None
    return tokens[1]


def _validate_rm_tokens(tokens: list[str]) -> str | None:
    if len(tokens) != 2:
        return "rm may delete exactly one file and accepts no flags"
    target = tokens[1]
    if target.startswith("-"):
        return "rm flags are not allowed"
    if target in {".", "./", "..", "../"}:
        return "rm target must be a regular file, not a directory"
    if any(marker in target for marker in GLOB_MARKERS):
        return "rm glob patterns are not allowed"
    sensitive = validate_sensitive_path(target)
    if sensitive:
        return sensitive
    return _path_token_error(target)


def _mkdir_paths_from_tokens(tokens: list[str]) -> tuple[list[str], str | None]:
    if len(tokens) < 2:
        return [], "mkdir requires at least one directory path"
    paths: list[str] = []
    for token in tokens[1:]:
        if token == "-p":
            continue
        if token.startswith("-"):
            return [], "mkdir accepts only the -p flag"
        paths.append(token)
    if not paths:
        return [], "mkdir requires at least one directory path"
    return paths, None


def _py_compile_target_from_tokens(tokens: list[str]) -> str | None:
    if len(tokens) != 4:
        return None
    head = Path(tokens[0]).name.lower()
    if head.endswith(".exe"):
        head = head[:-4]
    if head != "python3":
        return None
    if tokens[1] != "-m" or tokens[2] != "py_compile":
        return None
    return tokens[3]


def _validate_py_compile_tokens(tokens: list[str]) -> str | None:
    target = _py_compile_target_from_tokens(tokens)
    if target is None:
        return "only `python3 -m py_compile <single relative .py path>` is allowed"
    if target.startswith("-"):
        return "py_compile target must be a workspace-relative .py file"
    if any(marker in target for marker in GLOB_MARKERS):
        return "py_compile glob patterns are not allowed"
    sensitive = validate_sensitive_path(target)
    if sensitive:
        return sensitive
    path_error = _path_token_error(target)
    if path_error:
        return path_error
    if not target.endswith(".py"):
        return "py_compile target must be a .py file"
    return None


def _validate_mkdir_target(target: str) -> str | None:
    if target in {"..", "../"}:
        return "mkdir target must stay inside the workspace"
    if any(marker in target for marker in GLOB_MARKERS):
        return "mkdir glob patterns are not allowed"
    sensitive = validate_sensitive_path(target)
    if sensitive:
        return sensitive
    return _path_token_error(target)


def _validate_mkdir_tokens(tokens: list[str]) -> str | None:
    paths, error = _mkdir_paths_from_tokens(tokens)
    if error:
        return error
    for target in paths:
        target_error = _validate_mkdir_target(target)
        if target_error:
            return target_error
    return None


def mkdir_create_targets(command: str) -> list[str] | None:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return None
    if not tokens:
        return None
    head = Path(tokens[0]).name.lower()
    if head.endswith(".exe"):
        head = head[:-4]
    if head != "mkdir":
        return None
    paths, error = _mkdir_paths_from_tokens(tokens)
    if error:
        return None
    return paths


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
    py_compile_target = _py_compile_target_from_tokens(tokens)
    if py_compile_target is not None:
        return _validate_py_compile_tokens(tokens)
    if normalized[0] == "rm":
        return _validate_rm_tokens(tokens)
    if normalized[0] == "mkdir":
        return _validate_mkdir_tokens(tokens)
    if normalized[0] not in SAFE_COMMANDS:
        return f"command {normalized[0]!r} is not in the read-only allowlist"
    for token in normalized:
        if token in DESTRUCTIVE_TOKENS:
            return f"destructive token {token!r} is not allowed"
    for token in tokens[1:]:
        lower_token = token.lower()
        if lower_token in FORBIDDEN_ARG_TOKENS or lower_token.startswith("--exec"):
            return f"forbidden argument token {token!r} is not allowed"
    for token in tokens[1:]:
        path_error = _path_token_error(token)
        if path_error:
            return path_error
    return None


def validate_shell_command_for_workspace(root: Path, command: str) -> str | None:
    syntax_error = validate_shell_command(command)
    if syntax_error:
        return syntax_error
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return "could not parse command"
    py_compile_target = _py_compile_target_from_tokens(tokens)
    if py_compile_target is not None:
        try:
            path = resolve_workspace_path(root, py_compile_target)
        except ValueError as exc:
            return str(exc)
        if not path.exists():
            return f"py_compile target {py_compile_target!r} does not exist"
        if not path.is_file():
            return "py_compile target must be a regular file"
        return None
    target = rm_delete_target(command)
    if target is not None:
        try:
            path = resolve_workspace_path(root, target)
        except ValueError as exc:
            return str(exc)
        if not path.exists():
            return f"rm target {target!r} does not exist"
        if not path.is_file():
            return "rm may delete only regular files"
        return None
    mkdir_targets = mkdir_create_targets(command)
    if mkdir_targets is not None:
        for rel_target in mkdir_targets:
            if rel_target in {".", "./"}:
                continue
            try:
                path = resolve_workspace_path(root, rel_target)
            except ValueError as exc:
                return str(exc)
            if path.exists() and not path.is_dir():
                return f"mkdir target {rel_target!r} exists and is not a directory"
        return None
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
    refusal = validate_sensitive_path(rel_path)
    if refusal:
        return _result(tool_use_id, "read_file", refusal, "error", started)
    try:
        path = resolve_workspace_path(root, rel_path)
        content = path.read_text(encoding="utf-8")
        return _result(tool_use_id, "read_file", content, "ok", started)
    except (OSError, ValueError) as exc:
        return _result(tool_use_id, "read_file", str(exc), "error", started)


def read_file_range(root: Path, rel_path: str, start_line: int, end_line: int, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    refusal = validate_sensitive_path(rel_path)
    if refusal:
        return _result(tool_use_id, "read_file_range", refusal, "error", started)
    try:
        path = resolve_workspace_path(root, rel_path)
        lines = path.read_text(encoding="utf-8").splitlines()
        content = "\n".join(lines[max(0, int(start_line) - 1):int(end_line)])
        return _result(tool_use_id, "read_file_range", content, "ok", started)
    except (OSError, ValueError) as exc:
        return _result(tool_use_id, "read_file_range", str(exc), "error", started)


def write_file(root: Path, rel_path: str, content: str, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    refusal = validate_sensitive_path(rel_path)
    if refusal:
        return _result(tool_use_id, "write_file", refusal, "error", started)
    try:
        path = resolve_workspace_path(root, rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        return _result(tool_use_id, "write_file", f"wrote {rel_path}", "ok", started)
    except (OSError, ValueError) as exc:
        return _result(tool_use_id, "write_file", str(exc), "error", started)


def edit_file(root: Path, rel_path: str, old: str, new: str, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    refusal = validate_sensitive_path(rel_path)
    if refusal:
        return _result(tool_use_id, "edit_file", refusal, "error", started)
    try:
        path = resolve_workspace_path(root, rel_path)
        content = path.read_text(encoding="utf-8")
        occurrences = content.count(old)
        if occurrences == 0:
            return _result(tool_use_id, "edit_file", f"old text not found in {rel_path}", "error", started)
        path.write_text(content.replace(old, new), encoding="utf-8", newline="\n")
        return _result(tool_use_id, "edit_file", f"edited {rel_path}; replaced {occurrences} occurrence(s)", "ok", started)
    except (OSError, ValueError) as exc:
        return _result(tool_use_id, "edit_file", str(exc), "error", started)


def run_bash(root: Path, command: str, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    safety_error = validate_shell_command_for_workspace(root, command)
    if safety_error:
        return _result(tool_use_id, "run_bash", f"run_bash blocked: {safety_error}", "error", started)
    mkdir_targets = mkdir_create_targets(command)
    if mkdir_targets is not None:
        rel_targets = [target for target in mkdir_targets if target not in {".", "./"}]
        if rel_targets:
            existing: list[str] = []
            for rel_target in rel_targets:
                try:
                    path = resolve_workspace_path(root, rel_target)
                except ValueError:
                    existing = []
                    break
                if path.is_dir():
                    existing.append(rel_target)
                else:
                    existing = []
                    break
            if existing and len(existing) == len(rel_targets):
                joined = ", ".join(existing)
                return _result(
                    tool_use_id,
                    "run_bash",
                    f"mkdir: directory already exists: {joined}",
                    "ok",
                    started,
                )
    completed = subprocess.run(["bash", "-c", command], cwd=root, text=True, capture_output=True, timeout=TOOL_TIMEOUT)
    content = completed.stdout + completed.stderr
    status = "ok" if completed.returncode == 0 else "error"
    return _result(tool_use_id, "run_bash", content, status, started)


def validate_run_tests_path(root: Path, rel_path: str) -> str | None:
    refusal = validate_sensitive_path(rel_path)
    if refusal:
        return refusal
    try:
        path = resolve_workspace_path(root, rel_path)
    except ValueError as exc:
        return str(exc)
    if not path.exists():
        return f"run_tests path {rel_path!r} does not exist"
    if path.is_file():
        name = path.name
        if not (name.startswith("test_") and name.endswith(".py")):
            return f"run_tests file must match test_*.py, got {rel_path!r}"
    elif not path.is_dir():
        return f"run_tests path must be a test file or directory, got {rel_path!r}"
    return None


def run_tests(root: Path, rel_path: str, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    path_error = validate_run_tests_path(root, rel_path)
    if path_error:
        return _result(tool_use_id, "run_tests", f"run_tests blocked: {path_error}", "error", started)
    try:
        resolved = resolve_workspace_path(root, rel_path)
    except ValueError as exc:
        return _result(tool_use_id, "run_tests", str(exc), "error", started)
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", str(resolved), "-q", "--tb=short"],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=TOOL_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return _result(tool_use_id, "run_tests", f"run_tests timed out after {TOOL_TIMEOUT}s", "error", started)
    content = (completed.stdout or "") + (completed.stderr or "")
    if not content.strip():
        content = f"pytest exit code {completed.returncode}"
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_TOOL_RESULT_BYTES:
        half = MAX_TOOL_RESULT_BYTES // 2
        content = content[:half] + f"\n[TRUNCATED at {MAX_TOOL_RESULT_BYTES} bytes]"
    status = "ok" if completed.returncode == 0 else "error"
    if completed.returncode != 0 and status == "error":
        content = f"pytest exit code {completed.returncode}\n{content}"
    return _result(tool_use_id, "run_tests", content, status, started)
