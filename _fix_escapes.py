from pathlib import Path
p = Path(__file__).resolve().parent / "_patch_all.py"
t = p.read_text(encoding="utf-8")
t = t.replace('commands.\\n")', 'commands.\\\\n")')
t = t.replace('_chat_statusline_color(line, use_color=use_color) + "\\n")', '_chat_statusline_color(line, use_color=use_color) + "\\\\n")')
t = t.replace('sys.stdout.write(line + "\\n")', 'sys.stdout.write(line + "\\\\n")')
t = t.replace(
    "    from rich.rule import Rule\n\n    console.print(Rule(style=\"dim\"))\n    _write_status_bar(\n        console,\n        root=root,\n        recorder=recorder,\n        guard=guard,\n        live_model=live_model,\n        since_event_idx=since_event_idx,\n    )\n    _write_hint(console)\n    _write_secondary(console, recorder.events, since_event_idx=since_event_idx)\n\n\ndef render_input_top_rule",
    "    _write_status_bar(\n        console,\n        root=root,\n        recorder=recorder,\n        guard=guard,\n        live_model=live_model,\n        since_event_idx=since_event_idx,\n    )\n    _write_hint(console)\n    _write_secondary(console, recorder.events, since_event_idx=since_event_idx)\n\n\ndef render_input_top_rule",
)
p.write_text(t, encoding="utf-8")
print("fixed")
