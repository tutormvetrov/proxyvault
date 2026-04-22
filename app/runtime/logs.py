from __future__ import annotations

from collections import deque
from pathlib import Path


def read_log_excerpt(log_path: str | Path, max_lines: int = 20) -> str:
    if max_lines <= 0:
        return ""
    path = Path(log_path)
    if not path.exists():
        return ""

    lines: deque[str] = deque(maxlen=max_lines)
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                lines.append(line.rstrip("\r\n"))
    except OSError:
        return ""
    return "\n".join(lines)
