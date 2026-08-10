from __future__ import annotations

import re
from typing import Any


def split_virtual_lines(
    raw_lines: list[str], marker_patterns: list[re.Pattern[str]]
) -> list[dict[str, Any]]:
    """Expose inline record boundaries without changing the frozen raw text.

    Marker syntax is supplied by the format adapter. Each virtual line retains
    its one-based raw line/column and a zero-based subline ordinal so later
    stages can use normalized boundaries while review anchors stay raw.
    """
    virtual: list[dict[str, Any]] = []
    for raw_line, text in enumerate(raw_lines, 1):
        starts = sorted(
            {
                match.start()
                for pattern in marker_patterns
                for match in pattern.finditer(text)
                if match.groupdict().get("number") is not None
            }
        )
        segments: list[tuple[str, int]] = []
        if not starts:
            segments.append((text, 1))
        else:
            first = starts[0]
            if first > 0 and text[:first].strip():
                segments.append((text[:first].rstrip(), 1))
            else:
                starts[0] = 0
            for index, start in enumerate(starts):
                end = starts[index + 1] if index + 1 < len(starts) else len(text)
                segment = text[start:end].strip()
                if segment:
                    segments.append((segment, start + 1))
        for subline, (segment, raw_column) in enumerate(segments):
            virtual.append(
                {
                    "text": segment,
                    "raw_line": raw_line,
                    "raw_column": raw_column,
                    "subline": subline,
                }
            )
    return virtual
