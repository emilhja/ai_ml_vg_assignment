from pathlib import Path
ROOT = Path(__file__).resolve().parent
text = (ROOT / "scripts" / "generate_project.py").read_text(encoding="utf-8")
src = (ROOT / "_patch_all.py").read_text(encoding="utf-8")
start = src.index("old_loop_start = '''") + len("old_loop_start = '''")
end = src.index("'''", start)
old = src[start:end]
start2 = src.index("new_loop_start = '''") + len("new_loop_start = '''")
end2 = src.index("'''", start2)
new = src[start2:end2]
for label, block in [("old", old), ("new", new)]:
    print(label, block in text)
