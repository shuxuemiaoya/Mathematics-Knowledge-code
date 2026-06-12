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
