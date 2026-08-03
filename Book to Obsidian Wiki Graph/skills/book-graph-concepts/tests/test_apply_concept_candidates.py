import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "apply_concept_candidates.py"
SPEC = importlib.util.spec_from_file_location("apply_concept_candidates", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class ApplyConceptCandidatesTests(unittest.TestCase):
    def test_detaches_quoted_formula_when_naming_sentence_is_unquoted(self):
        definition = (
            "> 根据性质得\n>\n> $$\n> x = 1\n> $$\n\n"
            "我们把上式叫做公式。"
        )

        self.assertEqual(
            MODULE.detach_definition_from_source_callout(definition),
            "根据性质得\n\n$$\nx = 1\n$$\n\n我们把上式叫做公式。",
        )

    def test_materializes_definition_and_links_only_term_inside_anchor(self):
        with tempfile.TemporaryDirectory() as temp:
            tmp_path = Path(temp)
            vault = tmp_path / "vault"
            book = vault / "课本" / "测试书"
            staging = tmp_path / "stage"
            source = book / "知识点" / "集合.md"
            source.parent.mkdir(parents=True)
            staging.mkdir()
            source.write_text(
                "## 集合\n\n一般地，我们把研究对象统称为元素，把一些元素组成的总体叫做集合。\n",
                encoding="utf-8",
            )
            profile = {
                "source": {"sha256": "abc"},
                "paths": {"vault_root": str(vault), "book_root": str(book)},
                "categories": [
                    {"role": "concept", "directory": "概念", "enabled": True}
                ],
                "links": {"note_mode": "vault-root", "encode_spaces": True},
            }
            coverage = {
                "units": [{"source_key": "set", "target": "知识点/集合.md"}],
            }
            candidates = {
                "status": "approved",
                "concepts": [
                    {
                        "name": "集合",
                        "definition_source": "知识点/集合.md",
                        "definition_start_line": 3,
                        "definition_end_line": 3,
                        "anchor_text": "总体叫做集合",
                        "link_text": "集合",
                        "reviewed": True,
                    }
                ]
            }
            profile_path = staging / "book-profile.json"
            coverage_path = staging / "coverage.json"
            candidates_path = staging / "candidates.json"
            manifest_path = staging / "concept-manifest.json"
            write_json(profile_path, profile)
            write_json(coverage_path, coverage)
            write_json(candidates_path, candidates)

            result = MODULE.apply_candidates(
                profile_path, coverage_path, candidates_path, manifest_path
            )

            self.assertEqual(result["concepts"], 1)
            source_text = source.read_text(encoding="utf-8")
            self.assertIn("## 集合", source_text)
            self.assertIn("总体叫做[集合](/课本/测试书/概念/集合.md)", source_text)
            concept = (book / "概念" / "集合.md").read_text(encoding="utf-8")
            self.assertTrue(concept.startswith("# 集合\n"))
            self.assertIn("来源：[集合](/课本/测试书/知识点/集合.md)", concept)
            self.assertIn("## 定义", concept)
            self.assertIn("一般地，我们把研究对象统称为元素", concept)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["concepts"][0]["definition_unit"], "set")

    def test_refuses_nonempty_concept_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            tmp_path = Path(temp)
            vault = tmp_path / "vault"
            book = vault / "课本" / "测试书"
            concept = book / "概念"
            concept.mkdir(parents=True)
            (concept / "existing.md").write_text("existing", encoding="utf-8")
            profile_path = tmp_path / "profile.json"
            coverage_path = tmp_path / "coverage.json"
            candidates_path = tmp_path / "candidates.json"
            write_json(
                profile_path,
                {
                    "source": {"sha256": "abc"},
                    "paths": {"vault_root": str(vault), "book_root": str(book)},
                    "categories": [
                        {"role": "concept", "directory": "概念", "enabled": True}
                    ],
                    "links": {"note_mode": "vault-root", "encode_spaces": True},
                },
            )
            write_json(coverage_path, {"units": []})
            write_json(candidates_path, {"concepts": []})

            with self.assertRaisesRegex(ValueError, "not empty"):
                MODULE.apply_candidates(
                    profile_path,
                    coverage_path,
                    candidates_path,
                    tmp_path / "manifest.json",
                )

    def test_rejects_defining_term_inside_display_math(self):
        candidate = {
            "name": "整数集",
            "definition_start_line": 2,
            "definition_end_line": 2,
            "anchor_text": "称为整数集",
            "link_text": "整数集",
        }
        lines = ["$$", r"\mathrm{全体整数组成的集合称为整数集}", "$$"]

        with self.assertRaisesRegex(ValueError, "inside math"):
            MODULE.validate_candidate(candidate, lines)

    def test_refuses_unapproved_planner_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            tmp_path = Path(temp)
            vault = tmp_path / "vault"
            book = vault / "课本" / "测试书"
            source = book / "知识点" / "集合.md"
            source.parent.mkdir(parents=True)
            source.write_text(
                "# 集合\n\n总体叫做集合。\n",
                encoding="utf-8",
            )
            profile_path = tmp_path / "profile.json"
            coverage_path = tmp_path / "coverage.json"
            candidates_path = tmp_path / "candidates.json"
            write_json(
                profile_path,
                {
                    "source": {"sha256": "abc"},
                    "paths": {"vault_root": str(vault), "book_root": str(book)},
                    "categories": [
                        {"role": "concept", "directory": "概念", "enabled": True}
                    ],
                    "links": {"note_mode": "vault-root", "encode_spaces": True},
                },
            )
            write_json(coverage_path, {"units": []})
            write_json(
                candidates_path,
                {
                    "status": "review_required",
                    "concepts": [
                        {
                            "name": "集合",
                            "definition_source": "知识点/集合.md",
                            "definition_start_line": 3,
                            "definition_end_line": 3,
                            "anchor_text": "总体叫做集合",
                            "link_text": "集合",
                            "reviewed": False,
                        }
                    ],
                },
            )

            with self.assertRaisesRegex(ValueError, "not approved"):
                MODULE.apply_candidates(
                    profile_path,
                    coverage_path,
                    candidates_path,
                    tmp_path / "manifest.json",
                )

    def test_formula_concept_requires_an_equation(self):
        candidate = {
            "name": "半角公式",
            "definition_start_line": 1,
            "definition_end_line": 1,
            "anchor_text": "半角公式",
            "link_text": "半角公式",
        }
        lines = ["称之为半角公式，符号由 $\\alpha/2$ 所在象限决定。"]

        with self.assertRaisesRegex(ValueError, "has no equation"):
            MODULE.validate_candidate(candidate, lines)

    def test_rejects_definition_range_crossing_a_teaching_boundary(self):
        candidate = {
            "name": "函数的一般方程",
            "definition_start_line": 1,
            "definition_end_line": 5,
            "anchor_text": "叫做函数的一般方程",
            "link_text": "函数的一般方程",
        }
        lines = [
            "$$y=ax+b$$",
            "",
            "> [!question] 探究",
            "> 参数满足什么条件？",
            "我们把这个方程叫做函数的一般方程。",
        ]

        with self.assertRaisesRegex(ValueError, "crosses teaching boundary"):
            MODULE.validate_candidate(candidate, lines)

    def test_accepts_ordered_segments_around_a_teaching_block(self):
        candidate = {
            "name": "函数的一般方程",
            "definition_segments": [
                {"start_line": 1, "end_line": 1},
                {"start_line": 5, "end_line": 5},
            ],
            "anchor_text": "叫做函数的一般方程",
            "link_text": "函数的一般方程",
        }
        lines = [
            "$$y=ax+b$$",
            "",
            "> [!question] 探究",
            "> 参数满足什么条件？",
            "我们把这个方程叫做函数的一般方程。",
        ]

        ranges, definition = MODULE.validate_candidate(candidate, lines)

        self.assertEqual(ranges, [(1, 1), (5, 5)])
        self.assertEqual(
            definition,
            "$$y=ax+b$$\n\n我们把这个方程叫做函数的一般方程。",
        )

    def test_links_anchor_in_the_matching_definition_segment(self):
        lines = [
            "$$y=ax+b$$",
            "",
            "> [!question] 探究",
            "> 参数满足什么条件？",
            "我们把这个方程叫做函数的一般方程。",
        ]

        MODULE.link_first_defining_occurrence(
            lines,
            [(1, 1), (5, 5)],
            anchor="叫做函数的一般方程",
            link_text="函数的一般方程",
            target="../概念/函数的一般方程.md",
        )

        self.assertEqual(
            lines[4],
            "我们把这个方程叫做"
            "[函数的一般方程](../概念/函数的一般方程.md)。",
        )

    def test_equation_concept_requires_an_equation(self):
        candidate = {
            "name": "函数方程",
            "definition_start_line": 1,
            "definition_end_line": 1,
            "anchor_text": "叫做函数方程",
            "link_text": "函数方程",
        }

        with self.assertRaisesRegex(ValueError, "has no equation"):
            MODULE.validate_candidate(
                candidate,
                ["我们把上面的关系叫做函数方程。"],
            )

    def test_detaches_definition_copied_from_source_callout(self):
        definition = (
            "> 在数学中，这种图称为Venn图。\n"
            ">\n"
            "> $$\n"
            "> A\\subseteq B\n"
            "> $$"
        )

        detached = MODULE.detach_definition_from_source_callout(definition)

        self.assertEqual(
            detached,
            "在数学中，这种图称为Venn图。\n\n$$\nA\\subseteq B\n$$",
        )


if __name__ == "__main__":
    unittest.main()
