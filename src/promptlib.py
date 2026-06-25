"""Load prompt files that are split into [SYSTEM] and [USER] blocks.

File format:

    [SYSTEM]
    ...system message...

    [USER]
    ...user template (may contain {placeholder} tokens)...

`load_prompt` returns (system_text, user_template). Callers substitute their own
placeholder tokens (e.g. {reviews_json}, {stats_json}, {blocks}) into the template.
"""
from __future__ import annotations

import re
from pathlib import Path

_HEADER = re.compile(r"(?m)^\[(SYSTEM|USER)\]\s*$")


def load_prompt(path) -> tuple[str, str]:
    text = Path(path).read_text(encoding="utf-8")
    parts = _HEADER.split(text)  # [pre, 'SYSTEM', body, 'USER', body, ...]
    blocks = {}
    for i in range(1, len(parts) - 1, 2):
        blocks[parts[i].lower()] = parts[i + 1].strip()
    if "system" not in blocks or "user" not in blocks:
        raise ValueError(f"{path} must contain both [SYSTEM] and [USER] blocks")
    return blocks["system"], blocks["user"]
