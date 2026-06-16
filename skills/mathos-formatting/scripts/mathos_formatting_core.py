"""Core utilities facade for MathOS adaptive Markdown formatting.

Re-exports all stages, managers, and shared elements from separate modules
to preserve full backward compatibility with CLI entrypoints and tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from mathos_common import *
from stage1_heading import *
from stage2_3_toc import *
from stage4_content import *
from stage5_optimize import *
from program_manager import *
from learning_pipeline import *
