from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
_DEV = Path(__file__).resolve().parent
exec((_DEV / "_patch_all.py").read_text(encoding="utf-8").split("def patch_tests")[0])
text = (ROOT / "scripts" / "generate_project.py").read_text(encoding="utf-8")
# manually run patch_generate body with debug - import patch_generate from module
import importlib.util
spec = importlib.util.spec_from_file_location("pa", _DEV / "_patch_all.py")
pa = importlib.util.module_from_spec(spec)
# patch patch_generate to add debug
source = (_DEV / "_patch_all.py").read_text(encoding="utf-8")
source = source.replace(
    'if old_loop_start not in text:\n        raise SystemExit("_chat_loop start block not found")',
    'print("loop check", old_loop_start in text, len(old_loop_start))\n    if old_loop_start not in text:\n        raise SystemExit("_chat_loop start block not found")',
)
source = source.replace(
    'if old_import not in text:\n        raise SystemExit("import block not found")',
    'print("import check", old_import in text)\n    if old_import not in text:\n        raise SystemExit("import block not found")',
)
source = source.replace(
    'if old_make not in text:\n        raise SystemExit("_make_chat_prompt block not found")',
    'print("make check", old_make in text)\n    if old_make not in text:\n        raise SystemExit("_make_chat_prompt block not found")',
)
ns = {"Path": Path, "ROOT": ROOT}
exec(compile(source, str(_DEV / "_patch_all.py"), "exec"), ns)
ns["patch_generate"]()
