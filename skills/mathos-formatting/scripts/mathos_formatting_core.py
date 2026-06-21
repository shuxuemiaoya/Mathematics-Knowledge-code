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
from legacy_heading_rules import *
from legacy_title_map import *
from legacy_toc_helpers import *
from reporting import *
from step1_toc_extraction import *
from step2_heading_extraction import *
from step3_heading_processing import *
from step4_toc_removal import *
from step5_heading_validation import *
from step6_content_processing import *
from program_manager import *
from learning_pipeline import *
