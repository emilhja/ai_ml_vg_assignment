from pathlib import Path
import re
ROOT = Path(__file__).resolve().parent
text = (ROOT / "scripts" / "generate_project.py").read_text(encoding="utf-8")
src = (ROOT / "_patch_all.py").read_text(encoding="utf-8")

def extract(name):
    key = f"{name} = '''"
    start = src.index(key) + len(key)
    end = src.index("'''", start)
    return src[start:end]

# replicate patch steps
text = text.replace(
    'EXTRA_SOURCE_GENERATED_FILES = ["sqlite_store.py"]',
    'EXTRA_SOURCE_GENERATED_FILES = ["sqlite_store.py", "chat_ui.py"]',
)
old_import = extract("old_import") if "old_import = '''" in src else None
# skip - use manual
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
print('import', old_import in text)
old_make = extract("old_make") if False else None
# read from patch file between old_make and new_make markers manually
om_start = src.index('old_make = \'\'\'') + len("old_make = '''")
om_end = src.index("'''", om_start)
old_make = src[om_start:om_end]
print('make before', old_make in text)
if old_make in text:
    nm_start = src.index('new_make = \'\'\'') + len("new_make = '''")
    nm_end = src.index("'''", nm_start)
    text = text.replace(old_make, src[nm_start:nm_end])
print('make after replaced')
old_read = extract("old_read") if "old_read" in src else None
old_read = '''    def read_prompt() -> str:
        return input("vg> ")'''
text = text.replace(old_read, '''    def read_prompt() -> str:
        return input("> ")''')
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
    text = text.replace(anchor, helper + anchor)
text = text.replace(
    '    "/status": "Show compact live chat status",',
    '    "/status": "Reprint session dashboard (TTY) or compact status + budget",',
)
old_loop = extract("old_loop_start")
print('loop after steps', old_loop in text)
if old_loop not in text:
    i = text.index("def _chat_ui_kwargs")
    j = text.index("if not prompt:", i)
    print(repr(text[i:j][-300:]))
