from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_pipeline_state.py"
SPEC = importlib.util.spec_from_file_location("validate_pipeline_state", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PipelineStateValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name).resolve()
        self.source = self.folder / "paper.md"
        self.source.write_text("# Paper\n", encoding="utf-8")
        self.state_path = self.folder / "pipeline-state.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_state(self, **overrides: object) -> None:
        state = {
            "schema_version": 1,
            "run_id": "20260723T000000",
            "folder": str(self.folder),
            "stage_order": ["order", "convert", "reformat"],
            "stages": {
                "order": {"status": "not_applicable"},
                "convert": {"status": "not_applicable"},
                "reformat": {"status": "pending"},
            },
            "artifacts": [
                {
                    "stage": "reformat",
                    "role": "source",
                    "path": str(self.source),
                    "sha256": digest(self.source),
                }
            ],
            "papers": [],
            "image_cleaning": {},
            "eligible_to_render": False,
            "publishing_complete": False,
        }
        state.update(overrides)
        self.state_path.write_text(json.dumps(state), encoding="utf-8")

    def test_valid_state_identifies_resume_stage(self) -> None:
        self.write_state()
        result = MODULE.validate_pipeline_state(self.folder, self.state_path)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["reusable_stages"], ["order", "convert"])
        self.assertEqual(result["resume_from"], "reformat")

    def test_hash_mismatch_marks_stage_stale(self) -> None:
        self.write_state()
        self.source.write_text("# Changed\n", encoding="utf-8")
        result = MODULE.validate_pipeline_state(self.folder, self.state_path)
        self.assertEqual(result["status"], "stale")
        self.assertTrue(any("hash mismatch" in error for error in result["errors"]))

    def test_folder_mismatch_is_rejected(self) -> None:
        self.write_state(folder=str(self.folder / "other"))
        result = MODULE.validate_pipeline_state(self.folder, self.state_path)
        self.assertEqual(result["status"], "stale")
        self.assertTrue(any("Folder mismatch" in error for error in result["errors"]))

    def test_completed_image_stage_requires_backup(self) -> None:
        self.write_state(
            stage_order=["batch_clean_images"],
            stages={"batch_clean_images": {"status": "completed"}},
            image_cleaning={
                "image_replacement_status": "completed",
                "image_quality_status": "unverified",
                "replacements": [],
                "failed_paths": [],
            },
        )
        result = MODULE.validate_pipeline_state(self.folder, self.state_path)
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["resume_from"], "batch_clean_images")
        self.assertTrue(any("backup_folder" in error for error in result["errors"]))

    def test_completed_image_stage_reuses_verified_backup_and_replacement(self) -> None:
        images = self.folder / "images"
        backup = images / "original-images-backup-20260723-000000"
        backup.mkdir(parents=True)
        current = images / "figure.png"
        original = backup / "figure.png"
        original.write_bytes(b"original")
        current.write_bytes(b"replacement")
        self.write_state(
            stage_order=["batch_clean_images", "render"],
            stages={
                "batch_clean_images": {"status": "completed"},
                "render": {"status": "pending"},
            },
            image_cleaning={
                "image_replacement_status": "completed",
                "image_quality_status": "unverified",
                "backup_folder": str(backup),
                "replacements": [
                    {
                        "path": str(current),
                        "source_sha256": digest(original),
                        "replacement_sha256": digest(current),
                    }
                ],
                "failed_paths": [],
            },
        )
        result = MODULE.validate_pipeline_state(self.folder, self.state_path)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["reusable_stages"], ["batch_clean_images"])
        self.assertEqual(result["resume_from"], "render")


if __name__ == "__main__":
    unittest.main()
