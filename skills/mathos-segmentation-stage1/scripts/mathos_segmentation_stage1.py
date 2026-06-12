"""Deterministic stage-one Markdown segmentation for MathOS."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


STAGE_NAME = "segmentation-stage1"
SKILL_NAME = "skills/mathos-segmentation-stage1"
SCRIPT_COMMAND = r".\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py"
HEADING_RE = re.compile(r"^(#{1,6})\s+((\d+(?:\.\d+)*)\s+(.+?))\s*$")
INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class SegmentationError(Exception):
    """Raised when stage-one segmentation cannot continue safely."""


@dataclass(frozen=True)
class Heading:
    marker: str
    markdown_depth: int
    number: str
    number_depth: int
    title: str
    full_title: str
    line_index: int
    char_start: int
    char_end: int

    @property
    def depth(self) -> int:
        return self.markdown_depth


def extract_numbered_headings(markdown: str) -> list[Heading]:
    headings: list[Heading] = []
    char_offset = 0

    for line_index, line in enumerate(markdown.splitlines(keepends=True)):
        line_text = line.rstrip("\r\n")
        match = HEADING_RE.match(line_text)
        if match:
            marker, full_title, number, title = match.groups()
            headings.append(
                Heading(
                    marker=marker,
                    markdown_depth=len(marker),
                    number=number,
                    number_depth=number.count(".") + 1,
                    title=title,
                    full_title=full_title,
                    line_index=line_index,
                    char_start=char_offset,
                    char_end=char_offset + len(line),
                )
            )
        char_offset += len(line)

    return headings


def select_target_depth(headings: list[Heading], requested_depth: int | None) -> int:
    if not headings:
        raise SegmentationError("No numbered headings detected")

    if requested_depth is None:
        return max(heading.number_depth for heading in headings)

    if not any(heading.number_depth == requested_depth for heading in headings):
        raise SegmentationError(f"Target depth {requested_depth} produced zero segments")

    return requested_depth
