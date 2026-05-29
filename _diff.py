from pathlib import Path
import _patch_all as pa
from pathlib import Path
ROOT = Path(__file__).resolve().parent
text = (ROOT / "scripts" / "generate_project.py").read_text(encoding="utf-8")
# extract old_loop from patch module by reading source
src = (ROOT / "_patch_all.py").read_text(encoding="utf-8")
start = src.index("old_loop_start = '''") + len("old_loop_start = '''")
end = src.index("'''", start)
old = src[start:end]
print("old found", old in text)
if old not in text:
    # find first diff line
    for i, (a, b) in enumerate(zip(old.splitlines(), text[text.index("def _chat_loop"):text.index("def _chat_loop")+len(old)].splitlines())):
        if a != b:
            print("diff line", i)
            print("old", repr(a))
            print("file", repr(b))
            break
    else:
        print("len old", len(old), "len file chunk", len(text[text.index("def _chat_loop"):text.index("def _chat_loop")+len(old)]))
        print("repr old first 200", repr(old[:200]))
        i = text.index("def _chat_loop")
        print("repr file first 200", repr(text[i:i+200]))
