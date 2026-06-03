"""Shared JSONL trace parsing for the dashboard services."""

from __future__ import annotations

import json
from pathlib import Path


def read_jsonl_events(path: Path) -> list[dict]:
    """Parse a JSONL trace file into a list of dict events.

    Blank and malformed lines are skipped, non-dict JSON values are ignored,
    and a missing/unreadable file yields an empty list. This is the single
    source for the line-by-line parse that the session services share.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    events: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events
