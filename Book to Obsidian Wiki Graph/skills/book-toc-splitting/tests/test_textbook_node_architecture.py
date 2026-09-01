from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "textbook_node_architecture.py"
)
SPEC = importlib.util.spec_from_file_location("textbook_node_architecture", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def node(
    key: str,
    title: str,
    parent: str | None,
    category: str,
    start: int,
    end: int,
    node_type: str,
    *,
    organizer_type: str | None = None,
    emit_title: bool = False,
    question_number: int | None = None,
) -> dict:
    value = {
        "key": key,
        "title": title,
        "parent_key": parent,
        "category": category,
        "filename": f"{title}.md",
        "start_line": start,
        "end_line": end,
        "toc_key": None,
        "node_type": node_type,
        "emit_title": emit_title,
    }
    if organizer_type:
        value["organizer_type"] = organizer_type
    if question_number is not None:
        value["question_number"] = question_number
    return value


class TextbookNodeArchitectureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = {
            "book": {"kind": "textbook"},
            "decomposition": {"require_textbook_node_architecture": True},
            "categories": [
                {"role": "knowledge", "directory": "知识点", "enabled": True},
                {"role": "exercise", "directory": "习题", "enabled": True},
            ],
        }
        self.nodes = [
            node(
                "book", "教材", None, "root", 1, 100, "organizer",
                organizer_type="book", emit_title=True,
            ),
            node(
                "chapter", "第一章", "book", "knowledge", 1, 100,
                "organizer", organizer_type="chapter", emit_title=True,
            ),
            node(
                "section", "1.1 集合的概念", "chapter", "knowledge", 1, 70,
                "organizer", organizer_type="section", emit_title=True,
            ),
            node(
                "theme", "集合的表达方式", "section", "knowledge", 2, 50,
                "organizer", organizer_type="knowledge-theme",
            ),
            node("scenario", "情景导入 2", "theme", "knowledge", 2, 5, "scenario"),
            node("knowledge", "列举法", "theme", "knowledge", 6, 50, "knowledge"),
            node(
                "example", "例题 1", "knowledge", "knowledge", 20, 30,
                "worked-example",
            ),
            node(
                "practice", "练习 1", "section", "knowledge", 51, 60,
                "organizer", organizer_type="practice",
            ),
            node(
                "practice-q", "课内练习 1", "practice", "knowledge", 52, 59,
                "practice-question",
            ),
            node(
                "section-exercise", "习题1.1 集合的概念", "section", "exercise",
                61, 70, "organizer", organizer_type="section-exercise",
            ),
            node(
                "section-q", "习题1.1 第1题", "section-exercise", "exercise",
                62, 69, "section-exercise-question", question_number=1,
            ),
        ]
        atomic_order = [
            "scenario",
            "knowledge",
            "example",
            "practice-q",
            "section-q",
        ]
        self.manifest = {
            "node_architecture": {
                "status": "passed",
                "reviewed_entire_book": True,
                "source_order_expansion": "passed",
                "source_content_preservation": "passed",
                "source_names_preserved": "passed",
                "physical_hierarchy": "passed",
                "atomic_source_order": atomic_order,
            },
            "nodes": self.nodes,
        }
        MODULE.apply_hierarchical_filenames(self.manifest)

    def test_accepts_theme_example_practice_and_section_exercise_ownership(self) -> None:
        report = MODULE.validate_manifest(self.manifest, self.profile)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["atom_count"], 5)

    def test_physical_paths_mirror_reviewed_ownership(self) -> None:
        filenames = {item["key"]: item["filename"] for item in self.nodes}
        section = "第一章/1.1 集合的概念"
        theme = f"{section}/集合的表达方式"
        self.assertEqual(
            filenames["section"],
            f"{section}/1.1 集合的概念.md",
        )
        self.assertEqual(
            filenames["theme"],
            f"{theme}/集合的表达方式.md",
        )
        self.assertEqual(
            filenames["knowledge"],
            f"{theme}/列举法/列举法.md",
        )
        self.assertEqual(
            filenames["example"],
            f"{theme}/列举法/例题 1.md",
        )
        self.assertEqual(
            filenames["practice-q"],
            f"{section}/练习 1/课内练习 1.md",
        )
        self.assertEqual(
            filenames["section-q"],
            "第一章/习题1.1 集合的概念/习题1.1 第1题.md",
        )

    def test_rejects_flat_filename_after_hierarchy_review(self) -> None:
        theme = next(item for item in self.nodes if item["key"] == "theme")
        theme["filename"] = "集合的表达方式.md"
        with self.assertRaisesRegex(MODULE.ArchitectureError, "hierarchical filename"):
            MODULE.validate_manifest(self.manifest, self.profile)

    def test_rejects_example_linked_directly_from_section(self) -> None:
        example = next(item for item in self.nodes if item["key"] == "example")
        example["parent_key"] = "section"
        MODULE.apply_hierarchical_filenames(self.manifest)
        with self.assertRaisesRegex(MODULE.ArchitectureError, "directly owns"):
            MODULE.validate_manifest(self.manifest, self.profile)

    def test_rejects_section_exercise_inside_practice_group(self) -> None:
        section_exercise = next(
            item for item in self.nodes if item["key"] == "section-exercise"
        )
        section_exercise["parent_key"] = "practice"
        MODULE.apply_hierarchical_filenames(self.manifest)
        with self.assertRaisesRegex(MODULE.ArchitectureError, "invalid child types"):
            MODULE.validate_manifest(self.manifest, self.profile)

    def test_rejects_generic_knowledge_theme_name(self) -> None:
        theme = next(item for item in self.nodes if item["key"] == "theme")
        theme["title"] = "组织1"
        with self.assertRaisesRegex(MODULE.ArchitectureError, "semantic title"):
            MODULE.validate_manifest(self.manifest, self.profile)

    def test_rendered_audit_rejects_redundant_atomic_heading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vault = root / "vault"
            book = vault / "book"
            (book / "知识点").mkdir(parents=True)
            (book / "习题").mkdir()
            self.profile["paths"] = {
                "vault_root": str(vault),
                "book_root": str(book),
            }
            by_key = {item["key"]: item for item in self.nodes}

            def link(parent: str, child: str) -> str:
                parent_path = MODULE.node_path(
                    by_key[parent], book, MODULE.category_map(self.profile)
                )
                child_path = MODULE.node_path(
                    by_key[child], book, MODULE.category_map(self.profile)
                )
                href = Path(
                    __import__("os").path.relpath(child_path, parent_path.parent)
                ).as_posix()
                return f"![{by_key[child]['title']}]({href})"

            bodies = {
                "book": "# 教材\n\n正文。",
                "chapter": "# 第一章\n\n正文。",
                "section": "# 1.1 集合的概念\n\n"
                + "\n\n".join(
                    link("section", key)
                    for key in ("theme", "practice", "section-exercise")
                ),
                "theme": "\n\n".join(
                    link("theme", key) for key in ("scenario", "knowledge")
                ),
                "scenario": "情景正文。",
                "knowledge": "知识正文。\n\n" + link("knowledge", "example"),
                "example": "# 例题 1\n\n题目与完整解答。",
                "practice": link("practice", "practice-q"),
                "practice-q": "练习题正文。",
                "section-exercise": link("section-exercise", "section-q"),
                "section-q": "习题正文。",
            }
            categories = MODULE.category_map(self.profile)
            for key, body in bodies.items():
                path = MODULE.node_path(by_key[key], book, categories)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body + "\n", encoding="utf-8")

            report = MODULE.audit_corpus(
                book, vault, self.manifest, self.profile
            )
            self.assertEqual(report["status"], "failed")
            self.assertIn(
                "redundant-atomic-or-organizer-title",
                {item["code"] for item in report["errors"]},
            )

    def test_rendered_audit_accepts_parentheses_in_link_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vault = root / "vault"
            book = vault / "book"
            (book / "知识点").mkdir(parents=True)
            (book / "习题").mkdir()
            self.profile["paths"] = {
                "vault_root": str(vault),
                "book_root": str(book),
            }
            section = next(item for item in self.nodes if item["key"] == "section")
            theme = next(item for item in self.nodes if item["key"] == "theme")
            theme["title"] = "函数 y = A sin(ωx + φ) 的图象变换"
            theme["filename"] = f"{theme['title']}.md"
            MODULE.apply_hierarchical_filenames(self.manifest)
            by_key = {item["key"]: item for item in self.nodes}
            categories = MODULE.category_map(self.profile)

            for item in self.nodes:
                path = MODULE.node_path(item, book, categories)
                path.parent.mkdir(parents=True, exist_ok=True)
                children = sorted(
                    (
                        child
                        for child in self.nodes
                        if child.get("parent_key") == item["key"]
                    ),
                    key=lambda child: (child["start_line"], child["end_line"]),
                )
                if (
                    item.get("node_type") == "knowledge"
                    or (
                        item.get("node_type") == "organizer"
                        and item.get("organizer_type")
                        in {
                            "section",
                            "knowledge-theme",
                            "practice",
                            "section-exercise",
                        }
                    )
                ):
                    links = []
                    for child in children:
                        child_path = MODULE.node_path(child, book, categories)
                        href = Path(
                            __import__("os").path.relpath(child_path, path.parent)
                        ).as_posix()
                        links.append(f"![{child['title']}]({href})")
                    prefix = f"## {item['title']}\n\n" if item is section else ""
                    body = prefix + "\n\n".join(links)
                else:
                    body = "正文。"
                path.write_text(body + "\n", encoding="utf-8")

            report = MODULE.audit_corpus(book, vault, self.manifest, self.profile)
            self.assertEqual(report["status"], "passed", report["errors"])


if __name__ == "__main__":
    unittest.main()
