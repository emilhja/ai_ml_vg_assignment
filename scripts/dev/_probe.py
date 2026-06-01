from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
t = (ROOT / "scripts" / "generate_project.py").read_text(encoding="utf-8")
start = t.index('def _chat_loop')
chunk = t[start:start+800]
for line in chunk.splitlines():
    if 'stderr' in line or '_print_chat' in line or 'read_prompt' in line:
        print(repr(line))
