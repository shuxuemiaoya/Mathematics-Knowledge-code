from pathlib import Path
import importlib.util
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills" / "mathos-segmentation-stage1" / "scripts" / "mathos_segmentation_stage1.py"

spec = importlib.util.spec_from_file_location("mathos_segmentation_stage1", SCRIPT_PATH)
seg = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["mathos_segmentation_stage1"] = seg
spec.loader.exec_module(seg)


def test_module_exposes_stage_constants():
    assert seg.STAGE_NAME == "segmentation-stage1"
    assert seg.SKILL_NAME == "skills/mathos-segmentation-stage1"
