from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CHAT_UI = r'''"""Interactive TTY chat presentation for ``vg-agent --chat``."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from . import config
from .budget import BudgetGuard
from .trace import TraceRecorder

CHAT_PLACEHOLDER = 'Try "read data/sample.log and summarise auth/"'

_WELCOME_BORDER = "rgb(224,122,95)"
_PRODUCT_LABEL = "vg-agent"


def use_rich_ui() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    stdin_tty = bool(getattr(sys.stdin, "isatty", lambda: False)())
    stderr_tty = bool(getattr(sys.stderr, "isatty", lambda: False)())
    return stdin_tty and stderr_tty


def short_cwd(path: Path) -> str:
    resolved = path.resolve()
    home = Path.home().resolve()
    try:
        rel = resolved.relative_to(home)
        suffix = rel.as_posix()
        return "~" if not suffix else f"~/{suffix}"
    except ValueError:
        return resolved.as_posix()


def _console() -> Any:
    from rich.console import Console

    return Console(stderr=True, highlight=False)


def _format_compact_number(value: object) -> str:
    number = float(value or 0)
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}m"
    if number >= 1_000:
        return f"{number / 1_000:.1f}k"
    return str(int(number))


def _short_model(model: object) -> str:
    text = str(model or "")
    for prefix in ("openrouter/anthropic/", "openrouter/"):
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


def _latest_parent_llm_start(events: list[dict[str, object]]) -> dict[str, object] | None:
    for event in reversed(events):
        if event.get("kind") == "llm_start" and event.get("agent_id") == "parent":
            return event
    return None


def _latest_run_state(events: list[dict[str, object]], *, since_event_idx: int = 0) -> str:
    for event in reversed(events[since_event_idx:]):
        kind = event.get("kind")
        if kind == "run_end":
            final_status = str(event.get("final_status") or "done")
            if final_status == "tool_error":
                return "tool_error (turn failed)"
            return final_status
        if kind == "budget_event":
            return str(event.get("budget_reason") or "budget")
    return "ready"


def _tool_error_count(events: list[dict[str, object]]) -> int:
    return sum(
        1
        for event in events
        if event.get("kind") == "tool_result" and event.get("status") != "ok"
    )


def _status_token(events: list[dict[str, object]], *, since_event_idx: int) -> tuple[str, str, str]:
    status = _latest_run_state(events, since_event_idx=since_event_idx)
    lowered = status.lower()
    turn_errors = _tool_error_count(events[since_event_idx:])
    if (
        turn_errors > 0
        or "tool_error" in lowered
        or "model_error" in lowered
        or "aborted" in lowered
        or "error" in lowered
    ):
        label = status if status != "ready" else "error"
        return "\u2717", label, "red"
    if any(marker in lowered for marker in ("warn", "cap", "budget")):
        return "\u26a0", "warn", "yellow"
    if status in {"ready", "ok", "done"}:
        display = "ready" if status == "ready" else status
        return "\u2713", display, "green"
    return "\u2713", status, "green"


def _secondary_notice(events: list[dict[str, object]], *, since_event_idx: int) -> str | None:
    status = _latest_run_state(events, since_event_idx=since_event_idx)
    turn_errors = _tool_error_count(events[since_event_idx:])
    if status in {"ready", "ok"} and turn_errors == 0:
        return None
    reason = status
    if turn_errors > 0 and status in {"ready", "ok", "done"}:
        reason = f"{turn_errors} tool error(s)"
    return f"!! {reason} \u2014 see progress above"


def build_status_bar_text(
    *,
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    live_model: bool,
    since_event_idx: int = 0,
) -> str:
    mode = "live" if live_model else "deterministic"
    latest_llm = _latest_parent_llm_start(recorder.events)
    model = _short_model((latest_llm or {}).get("model") or config.PARENT_MODEL_ID)
    context_tokens = int((latest_llm or {}).get("tokens_in") or 0)
    icon, status_label, _style = _status_token(recorder.events, since_event_idx=since_event_idx)
    workspace_name = root.resolve().name or str(root)
    segments = [
        f"\U0001f4c1 {workspace_name}",
        f"\U0001f916 {model}",
        mode,
        f"ctx {_format_compact_number(context_tokens)} in",
        f"\U0001f4b5 ${guard.running_usd:.4f}/${guard.max_usd:.2f}",
        f"\U0001f4ca {guard.step_count}/{guard.max_steps} steps",
        f"{icon} {status_label}",
    ]
    return " | ".join(segments)


def _write_status_bar(
    console: Any,
    *,
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    live_model: bool,
    since_event_idx: int,
) -> None:
    mode = "live" if live_model else "deterministic"
    latest_llm = _latest_parent_llm_start(recorder.events)
    model = _short_model((latest_llm or {}).get("model") or config.PARENT_MODEL_ID)
    context_tokens = int((latest_llm or {}).get("tokens_in") or 0)
    icon, status_label, status_style = _status_token(recorder.events, since_event_idx=since_event_idx)
    workspace_name = root.resolve().name or str(root)
    status_part = f"[{status_style}]{icon} {status_label}[/{status_style}]"
    line = (
        f"\U0001f4c1 {workspace_name} | \U0001f916 {model} | {mode} | "
        f"ctx {_format_compact_number(context_tokens)} in | "
        f"\U0001f4b5 ${guard.running_usd:.4f}/${guard.max_usd:.2f} | "
        f"\U0001f4ca {guard.step_count}/{guard.max_steps} steps | {status_part}"
    )
    console.print(line)


def _write_hint(console: Any) -> None:
    console.print("[dim]/help for commands \u00b7 /status to refresh session[/dim]")


def _write_secondary(console: Any, events: list[dict[str, object]], *, since_event_idx: int) -> None:
    notice = _secondary_notice(events, since_event_idx=since_event_idx)
    if notice:
        console.print(f"[yellow]{notice}[/yellow]")


def print_chat_dashboard(
    *,
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    live_model: bool,
    since_event_idx: int = 0,
) -> None:
    if not use_rich_ui():
        return
    console = _console()
    console.print(f"[dim]{_PRODUCT_LABEL}[/dim]")
    from rich.panel import Panel
    from rich.text import Text

    welcome = Text()
    welcome.append("* ", style=f"bold {_WELCOME_BORDER}")
    welcome.append("Welcome to VG Agent!", style="bold white")
    welcome.append("\n")
    welcome.append("/help for commands \u00b7 /status for your current setup", style="italic dim")
    welcome.append("\n")
    welcome.append(f"cwd: {short_cwd(root)}", style="dim")
    console.print(Panel(welcome, border_style=_WELCOME_BORDER, padding=(0, 1)))
    _write_status_bar(
        console,
        root=root,
        recorder=recorder,
        guard=guard,
        live_model=live_model,
        since_event_idx=since_event_idx,
    )
    _write_hint(console)
    _write_secondary(console, recorder.events, since_event_idx=since_event_idx)


def render_input_top_rule() -> None:
    if not use_rich_ui():
        return
    from rich.rule import Rule

    _console().print(Rule(style="dim"))


def render_input_bottom_and_footer(
    *,
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    live_model: bool,
    since_event_idx: int = 0,
) -> None:
    if not use_rich_ui():
        return
    from rich.rule import Rule

    console = _console()
    console.print(Rule(style="dim"))
    _write_status_bar(
        console,
        root=root,
        recorder=recorder,
        guard=guard,
        live_model=live_model,
        since_event_idx=since_event_idx,
    )
    _write_hint(console)
    _write_secondary(console, recorder.events, since_event_idx=since_event_idx)


def refresh_chat_status_bar(
    *,
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    live_model: bool,
    since_event_idx: int = 0,
) -> None:
    if not use_rich_ui():
        return
    console = _console()
    _write_status_bar(
        console,
        root=root,
        recorder=recorder,
        guard=guard,
        live_model=live_model,
        since_event_idx=since_event_idx,
    )
    _write_hint(console)
    _write_secondary(console, recorder.events, since_event_idx=since_event_idx)
'''

def patch_generate() -> None:
    gen_path = ROOT / "scripts" / "generate_project.py"
    text = gen_path.read_text(encoding="utf-8")

    text = text.replace(
        'EXTRA_SOURCE_GENERATED_FILES = ["sqlite_store.py"]',
        'EXTRA_SOURCE_GENERATED_FILES = ["sqlite_store.py", "chat_ui.py"]',
    )

    old_import = '''try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.history import FileHistory
except ImportError:  # pragma: no cover - dependency is optional at runtime fallback level
    PromptSession = None
    Completer = None
    Completion = None
    FileHistory = None

from . import config, tools'''

    new_import = '''try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.styles import Style
except ImportError:  # pragma: no cover - dependency is optional at runtime fallback level
    PromptSession = None
    Completer = None
    Completion = None
    FileHistory = None
    Style = None

from . import config, tools
from .chat_ui import (
    CHAT_PLACEHOLDER,
    print_chat_dashboard,
    refresh_chat_status_bar,
    render_input_bottom_and_footer,
    render_input_top_rule,
    use_rich_ui,
)'''

    if old_import not in text:
        raise SystemExit("import block not found")
    text = text.replace(old_import, new_import)

    old_make = '''def _make_chat_prompt(history_path: Path) -> tuple[Any, Any]:
    if (
        bool(getattr(sys.stdin, "isatty", lambda: False)())
        and PromptSession is not None
        and FileHistory is not None
    ):
        session = PromptSession(
            "vg> ",
            completer=_slash_command_completer(),
            complete_while_typing=True,
            history=FileHistory(str(history_path)),
        )
        return session.prompt, lambda: None'''

    new_make = '''def _make_chat_prompt(history_path: Path) -> tuple[Any, Any]:
    if (
        bool(getattr(sys.stdin, "isatty", lambda: False)())
        and PromptSession is not None
        and FileHistory is not None
    ):
        prompt_style = Style.from_dict({"prompt": "dim"}) if Style is not None and use_rich_ui() else None
        message: Any = "> "
        if use_rich_ui():
            message = [("class:prompt", "> ")]
        session = PromptSession(
            message,
            completer=_slash_command_completer(),
            complete_while_typing=True,
            history=FileHistory(str(history_path)),
            placeholder=CHAT_PLACEHOLDER if use_rich_ui() else None,
            style=prompt_style,
        )
        return session.prompt, lambda: None'''

    if old_make not in text:
        raise SystemExit("_make_chat_prompt block not found")
    text = text.replace(old_make, new_make)

    old_read = '''    def read_prompt() -> str:
        return input("vg> ")'''

    new_read = '''    def read_prompt() -> str:
        return input("> ")'''

    if old_read not in text:
        raise SystemExit("read_prompt input not found")
    text = text.replace(old_read, new_read)

    helper = '''

def _chat_ui_kwargs(
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    args: argparse.Namespace,
    *,
    since_event_idx: int = 0,
) -> dict[str, Any]:
    return {
        "root": root,
        "recorder": recorder,
        "guard": guard,
        "live_model": bool(args.live_model),
        "since_event_idx": since_event_idx,
    }


'''

    anchor = "def _chat_loop(root: Path, args: argparse.Namespace) -> int:"
    if "_chat_ui_kwargs" not in text:
        if anchor not in text:
            raise SystemExit("_chat_loop anchor not found")
        text = text.replace(anchor, helper + anchor)

    old_status_meta = '    "/status": "Show compact live chat status",'
    new_status_meta = '    "/status": "Reprint session dashboard (TTY) or compact status + budget",'
    text = text.replace(old_status_meta, new_status_meta)

    old_loop_start = '''def _chat_loop(root: Path, args: argparse.Namespace) -> int:
    recorder = TraceRecorder(root, redact=not args.no_redact, event_sink=_make_progress_sink())
    policy = _make_policy(args)
    guard = BudgetGuard.for_workspace(root)
    history_path = root / ".vg_chat_history"
    read_prompt, save_history = _make_chat_prompt(history_path)
    sys.stderr.write("VG Agent chat mode. Type /help for commands.\\n")
    conversation: list[dict[str, Any]] = []
    last_intent_prompt = ""
    try:
        while True:
            try:
                _print_chat_statusline(
                    recorder,
                    guard,
                    live_model=bool(args.live_model),
                    since_event_idx=len(recorder.events),
                )
                prompt = read_prompt().strip()
            except KeyboardInterrupt:
                recorder.emit("budget_event", budget_reason="user_abort", details={})
                sys.stderr.write("\\n")
                break
            except EOFError:
                sys.stderr.write("\\n")
                break
            if not prompt:
                continue'''

    new_loop_start = '''def _chat_loop(root: Path, args: argparse.Namespace) -> int:
    recorder = TraceRecorder(root, redact=not args.no_redact, event_sink=_make_progress_sink())
    policy = _make_policy(args)
    guard = BudgetGuard.for_workspace(root)
    history_path = root / ".vg_chat_history"
    read_prompt, save_history = _make_chat_prompt(history_path)
    ui_since = 0
    if use_rich_ui():
        print_chat_dashboard(**_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=ui_since))
    else:
        sys.stderr.write("VG Agent chat mode. Type /help for commands.\\n")
    conversation: list[dict[str, Any]] = []
    last_intent_prompt = ""
    try:
        while True:
            try:
                render_input_top_rule()
                prompt = read_prompt().strip()
                render_input_bottom_and_footer(**_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=ui_since))
            except KeyboardInterrupt:
                recorder.emit("budget_event", budget_reason="user_abort", details={})
                sys.stderr.write("\\n")
                break
            except EOFError:
                sys.stderr.write("\\n")
                break
            if not prompt:
                continue'''

    if old_loop_start not in text:
        raise SystemExit("_chat_loop start block not found")
    text = text.replace(old_loop_start, new_loop_start)

    old_status_cmd = '''            if prompt == "/status":
                line = _format_chat_statusline(recorder, guard, live_model=bool(args.live_model))
                use_color = bool(getattr(sys.stdout, "isatty", lambda: False)()) and bool(args.live_model) and not os.environ.get("NO_COLOR")
                sys.stdout.write(_chat_statusline_color(line, use_color=use_color) + "\\n")
                continue'''

    new_status_cmd = '''            if prompt == "/status":
                if use_rich_ui():
                    print_chat_dashboard(**_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=ui_since))
                else:
                    line = _format_chat_statusline(recorder, guard, live_model=bool(args.live_model))
                    sys.stdout.write(line + "\\n")
                    _print_budget(guard)
                continue'''

    if old_status_cmd not in text:
        raise SystemExit("/status block not found")
    text = text.replace(old_status_cmd, new_status_cmd)

    old_reset = '''            if prompt == "/reset":
                policy.cache.clear()
                guard = BudgetGuard.for_workspace(root)
                conversation.clear()
                last_intent_prompt = ""
                recorder.emit("session_reset")
                continue'''

    new_reset = '''            if prompt == "/reset":
                policy.cache.clear()
                guard = BudgetGuard.for_workspace(root)
                conversation.clear()
                last_intent_prompt = ""
                ui_since = len(recorder.events)
                recorder.emit("session_reset")
                if use_rich_ui():
                    print_chat_dashboard(**_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=ui_since))
                continue'''

    text = text.replace(old_reset, new_reset)

    old_new = '''            if prompt == "/new":
                policy.cache.clear()
                guard = BudgetGuard.for_workspace(root)
                conversation.clear()
                last_intent_prompt = ""
                recorder = TraceRecorder(root, redact=not args.no_redact, event_sink=_make_progress_sink())
                recorder.emit("session_new")
                continue'''

    new_new = '''            if prompt == "/new":
                policy.cache.clear()
                guard = BudgetGuard.for_workspace(root)
                conversation.clear()
                last_intent_prompt = ""
                recorder = TraceRecorder(root, redact=not args.no_redact, event_sink=_make_progress_sink())
                ui_since = 0
                recorder.emit("session_new")
                if use_rich_ui():
                    print_chat_dashboard(**_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=ui_since))
                continue'''

    text = text.replace(old_new, new_new)

    old_turn_end = '''            if not _is_ack_prompt(prompt):
                last_intent_prompt = prompt
    finally:'''

    new_turn_end = '''            refresh_chat_status_bar(**_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=start_idx))
            if not _is_ack_prompt(prompt):
                last_intent_prompt = prompt
    finally:'''

    if old_turn_end not in text:
        raise SystemExit("turn end block not found")
    text = text.replace(old_turn_end, new_turn_end)

    gen_path.write_text(text, encoding="utf-8", newline="\n")


def patch_tests() -> None:
    test_path = ROOT / "tests" / "test_vg_agent.py"
    text = test_path.read_text(encoding="utf-8")
    if "test_chat_ui_status_bar_segments" in text:
        print("tests already patched")
        return
    insert = '''

def test_chat_ui_status_bar_segments(tmp_path: Path) -> None:
    from vg_agent.chat_ui import build_status_bar_text

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
    assert "ctx 4.2k in" in line
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


def test_chat_ui_non_tty_skips_rich(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vg_agent import __main__ as cli
    from vg_agent.chat_ui import use_rich_ui

    monkeypatch.setattr(cli, "use_rich_ui", lambda: False)

    prompts = iter(["/exit"])

    monkeypatch.setattr(cli, "_make_chat_prompt", lambda _history_path: (lambda: next(prompts), lambda: None))

    args = SimpleNamespace(
        no_redact=False,
        require_approval="off",
        yes=False,
        live_model=False,
    )
    assert use_rich_ui() is False
    assert cli._chat_loop(tmp_path, args) == 0

'''
    anchor = "def test_chat_slash_new_starts_fresh_trace_and_live_history("
    if anchor not in text:
        raise SystemExit("test anchor not found")
    text = text.replace(anchor, insert + anchor)
    test_path.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    (ROOT / "src" / "vg_agent" / "chat_ui.py").write_text(CHAT_UI, encoding="utf-8", newline="\n")
    patch_generate()
    patch_tests()
    print("patched chat_ui, generate_project.py, tests")


if __name__ == "__main__":
    main()
