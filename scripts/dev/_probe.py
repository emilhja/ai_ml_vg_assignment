from pathlib import Path
t = Path(r"c:\Users\emil_\vscode\vg_assignment\scripts\generate_project.py").read_text(encoding="utf-8")
start = t.index('def _chat_loop')
chunk = t[start:start+800]
for line in chunk.splitlines():
    if 'stderr' in line or '_print_chat' in line or 'read_prompt' in line:
        print(repr(line))
