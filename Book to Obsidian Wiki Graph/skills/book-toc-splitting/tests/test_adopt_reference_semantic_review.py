from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT = SCRIPTS / "adopt_reference_semantic_review.py"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "adopt_reference_semantic_review", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AdoptReferenceSemanticReviewTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
        formatted = root / "formatted.md"
        formatted.write_text(
            (
                "# 第一章 集合\n"
                "## 1.1 集合的概念\n"
                "先说明学习集合的背景。\n"
                "集合是研究对象组成的整体。\n"
                "这里给出集合的表示方法。\n"
                "最后说明集合定义的使用范围。\n"
            ),
            encoding="utf-8",
        )
        reference = root / "reference"
        reference.mkdir()
        (reference / "集合的定义.md").write_text(
            "集合是研究对象组成的整体。\n",
            encoding="utf-8",
        )
        reference_digest = "b" * 64
        profile = root / "book-profile.json"
        profile.write_text(
            json.dumps(
                {
                    "source": {"sha256": "a" * 64},
                    "reference": {
                        "path": str(reference.resolve()),
                        "sha256": reference_digest,
                        "scope": "same-book-content-and-style",
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        split = root / "split-manifest.json"
        split.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "profile": str(profile.resolve()),
                    "source_sha256": "a" * 64,
                    "semantic_review": {
                        "headings": [],
                        "sections": [
                            {
                                "node_key": "lesson",
                                "title": "1.1 集合的概念",
                                "start_line": 2,
                                "end_line": 6,
                                "decision": "retain",
                            }
                        ],
                        "ranges": [],
                    },
                    "nodes": [
                        {
                            "key": "lesson",
                            "title": "1.1 集合的概念",
                            "parent_key": None,
                            "category": "knowledge",
                            "filename": "1.1 集合的概念.md",
                            "start_line": 2,
                            "end_line": 6,
                            "toc_key": "lesson",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        proposal = root / "reference-semantic-proposals.json"
        proposal.write_text(
            json.dumps(
                {
                    "formatted_markdown": str(formatted.resolve()),
                    "split_manifest": str(split.resolve()),
                    "reference": {
                        "path": str(reference.resolve()),
                        "sha256": reference_digest,
                        "scope": "same-book-content-and-style",
                    },
                    "suggestions": [
                        {
                            "title": "集合的定义",
                            "parent_node_key": "lesson",
                            "status": "ambiguous",
                            "review_flags": [
                                "incomplete-reference-body-match"
                            ],
                            "containment": 0.8,
                            "matched_character_count": 50,
                            "start_line": 4,
                            "end_line": 6,
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return formatted, split, proposal, profile

    def test_ambiguous_proposal_requires_explicit_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            formatted, split, proposal, _ = self.fixture(Path(temporary))
            with self.assertRaisesRegex(
                MODULE.AdoptionError,
                "ambiguous reference proposals require --review-decisions",
            ):
                MODULE.adopt(
                    formatted,
                    split,
                    proposal,
                    Path(temporary) / "output.json",
                    0.55,
                    35,
                    reviewer_confirmed=True,
                )

    def test_duplicate_ambiguous_titles_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, _, proposal, _ = self.fixture(root)
            payload = json.loads(proposal.read_text(encoding="utf-8"))
            payload["suggestions"].append(dict(payload["suggestions"][0]))
            proposal.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )

            with self.assertRaisesRegex(
                MODULE.AdoptionError,
                "unique non-empty titles",
            ):
                MODULE.load_ambiguity_decisions(payload, proposal, None)

    def test_accept_decision_is_bound_to_proposal_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            formatted, split, proposal, _ = self.fixture(root)
            decisions = root / "reference-ambiguity-decisions.json"
            decisions.write_text(
                json.dumps(
                    {
                        "proposal_report_sha256": hashlib.sha256(
                            proposal.read_bytes()
                        ).hexdigest(),
                        "decisions": [
                            {
                                "title": "集合的定义",
                                "decision": "accept",
                                "reason": (
                                    "The complete source range was reviewed "
                                    "and is one reusable teaching arc."
                                ),
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            decisions_digest = hashlib.sha256(
                decisions.read_bytes()
            ).hexdigest()
            output = root / "reviewed-split-manifest.json"

            result = MODULE.adopt(
                formatted,
                split,
                proposal,
                output,
                0.55,
                35,
                review_decisions=decisions,
                reviewer_confirmed=True,
            )
            reviewed = json.loads(output.read_text(encoding="utf-8"))
            reference_review = reviewed["semantic_review"]["reference"]
            added = next(
                node
                for node in reviewed["nodes"]
                if node["title"] == "集合的定义"
            )

        self.assertEqual(result["added_node_count"], 1)
        self.assertEqual(added["start_line"], 4)
        self.assertEqual(added["end_line"], 6)
        self.assertEqual(reference_review["ambiguous_count"], 1)
        self.assertEqual(reference_review["resolved_ambiguity_count"], 1)
        self.assertEqual(
            reference_review["decision_report_sha256"],
            decisions_digest,
        )


if __name__ == "__main__":
    unittest.main()
