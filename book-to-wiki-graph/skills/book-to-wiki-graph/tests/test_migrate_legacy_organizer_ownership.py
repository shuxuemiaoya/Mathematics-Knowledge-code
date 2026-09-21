from __future__ import annotations

import sys
import unittest
from pathlib import Path, PurePosixPath


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import migrate_legacy_organizer_ownership as migration


class LegacyOrganizerOwnershipMigrationTests(unittest.TestCase):
    def test_reparented_organizer_rebases_complete_subtree(self) -> None:
        nodes = {
            "topic": {
                "key": "topic",
                "layer": "organizer",
                "filename": "组织层/Book/Chapter/Section/Topic/Topic.md",
                "children": ["detail", "atom"],
            },
            "detail": {
                "key": "detail",
                "layer": "organizer",
                "filename": "组织层/Book/Chapter/Section/Topic/Detail/Detail.md",
                "children": [],
            },
            "atom": {
                "key": "atom",
                "layer": "atom",
                "filename": "原子层/知识点/0001-K.md",
            },
        }

        migration.rebase_organizer_subtree(
            nodes,
            "topic",
            PurePosixPath("组织层/Book/Chapter/Section/Topic"),
            PurePosixPath("组织层/Book/Chapter/Section/Printed/Topic"),
        )

        self.assertEqual(
            nodes["topic"]["filename"],
            "组织层/Book/Chapter/Section/Printed/Topic/Topic.md",
        )
        self.assertEqual(
            nodes["detail"]["filename"],
            "组织层/Book/Chapter/Section/Printed/Topic/Detail/Detail.md",
        )
        self.assertEqual(nodes["atom"]["filename"], "原子层/知识点/0001-K.md")

    def test_safe_path_component_removes_filesystem_separators(self) -> None:
        self.assertEqual(
            migration.safe_path_component('综合/运用: "集合"'),
            "综合_运用_ _集合_",
        )


if __name__ == "__main__":
    unittest.main()
