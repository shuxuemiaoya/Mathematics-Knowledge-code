import importlib.util
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1]
    / "scripts"
    / "flatten_navigation_containers.py"
)
SPEC = importlib.util.spec_from_file_location(
    "flatten_navigation_containers", SCRIPT
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class FlattenNavigationContainersTests(unittest.TestCase):
    def test_practice_gap_cannot_introduce_the_next_topic(self):
        lines = [
            "#### 练习",
            "求下列集合的交集，并说明运算过程。",
        ]

        self.assertFalse(
            MODULE.gap_supplies_link_context(lines, 1, len(lines))
        )

    def test_question_gap_can_introduce_the_next_topic(self):
        lines = [
            "#### 思考",
            "根式是否也可以表示为分数指数幂？",
        ]

        self.assertTrue(
            MODULE.gap_supplies_link_context(lines, 1, len(lines))
        )

    def test_formula_block_is_not_duplicated_as_parent_preview(self):
        lines = [
            "#### 描述法",
            "把这个解集表示为",
            "$$",
            r"\{x \mid x < 10\}.",
            "$$",
            "后续正文。",
        ]
        child = {
            "title": "描述法",
            "start_line": 1,
            "end_line": len(lines),
        }

        preview = MODULE.derive_preview(lines, child)

        self.assertIsNone(preview)

    def test_formal_definition_preview_is_exposition_not_situation(self):
        lines = [
            "一般地，如果 $x^n=a$，那么 $x$ 叫做 n 次方根。",
        ]

        self.assertEqual(
            MODULE.classify_preview(lines, 1, 1),
            ("exposition", "原文讲解"),
        )

    def test_definition_sequence_is_not_duplicated_as_parent_preview(self):
        lines = [
            "#### n次方根",
            "如果 $x^2=a$，那么 $x$ 叫做 $a$ 的平方根。",
            "如果 $x^3=a$，那么 $x$ 叫做 $a$ 的立方根。",
            "类似地，还可以考察四次方根与五次方根。",
            "一般地，如果 $x^n=a$，那么 $x$ 叫做 n 次方根。",
            "后续性质。",
        ]
        child = {
            "title": "n次方根",
            "start_line": 1,
            "end_line": len(lines),
        }

        preview = MODULE.derive_preview(lines, child)

        self.assertIsNone(preview)

    def test_worked_example_preview_is_not_a_question_callout(self):
        lines = [
            "例2 下列命题中，哪些命题的结论是必要条件？",
        ]

        self.assertEqual(
            MODULE.classify_preview(lines, 1, 1),
            ("worked-example", "原文例题"),
        )

    def test_figure_example_is_not_duplicated_as_parent_preview(self):
        lines = [
            "例2 如图 1.2-3，证明两条直线垂直。",
            "",
            "![](images/figure.jpg)",
            "",
            "分析过程完整说明了证明思路。",
            "",
            "解：",
            "",
            "(1)",
            "图1.2-3",
            "证明正文。",
        ]
        child = {
            "title": "应用",
            "start_line": 1,
            "end_line": len(lines),
        }

        preview = MODULE.derive_preview(lines, child)

        self.assertIsNone(preview)

    def test_figure_exposition_is_not_duplicated_as_parent_preview(self):
        lines = [
            "根据图1.1-4和图1.1-5定义两种运算。",
            "",
            "![](images/first.jpg)",
            "图1.1-4",
            "",
            "![](images/second.jpg)",
            "图1.1-5",
            "后续正文。",
        ]
        child = {
            "title": "线性运算",
            "start_line": 1,
            "end_line": len(lines),
        }

        preview = MODULE.derive_preview(lines, child)

        self.assertIsNone(preview)

    def test_prefers_concise_question_over_long_preliminary_exposition(self):
        lines = [
            "#### 线性运算",
            "这里是一段很长的定义、推导和公式说明，它不应复制到父文件中。" * 8,
            "想一想，向量线性运算的结果与起点选择有关吗？",
            "后续正文。",
        ]
        child = {"title": "线性运算", "start_line": 1, "end_line": 4}

        preview = MODULE.derive_preview(lines, child)

        self.assertIsNotNone(preview)
        self.assertEqual(preview["start_line"], 3)
        self.assertEqual(preview["end_line"], 3)
        self.assertEqual(preview["role"], "question")
        self.assertEqual(
            lines[preview["start_line"] - 1],
            "想一想，向量线性运算的结果与起点选择有关吗？",
        )

    def test_promotes_fine_topics_and_adds_missing_parent_preview(self):
        lines = [
            "## 4.1 指数",
            "为了研究指数函数，需要拓展指数范围。",
            "#### 4.1.1 n 次方根与分数指数幂",
            "情景引入",
            "我们知道：",
            "如果 $x^2=a$，那么 $x$ 叫做 $a$ 的平方根。",
            "一般地，如果 $x^n=a$，那么 $x$ 叫做 n 次方根。",
            "根式还可以怎样表示为分数指数幂？",
            "规定正数的正分数指数幂具有如下意义。",
            "分数指数幂仍满足相应的指数幂运算性质。",
        ]
        payload = {
            "semantic_review": {
                "headings": [
                    {
                        "line": 3,
                        "title": "4.1.1 n 次方根与分数指数幂",
                        "decision": "split",
                        "node_key": "container",
                        "confidence": 0.99,
                    }
                ],
                "sections": [
                    {
                        "node_key": "lesson",
                        "child_node_keys": ["container"],
                    },
                    {"node_key": "container", "child_node_keys": ["root", "fraction"]},
                ],
                "ranges": [],
            },
            "nodes": [
                {
                    "key": "lesson",
                    "title": "4.1 指数",
                    "parent_key": "chapter",
                    "category": "knowledge",
                    "start_line": 1,
                    "end_line": 10,
                    "toc_key": "toc-lesson",
                },
                {
                    "key": "container",
                    "title": "4.1.1 n 次方根与分数指数幂",
                    "parent_key": "lesson",
                    "category": "knowledge",
                    "start_line": 3,
                    "end_line": 10,
                    "toc_key": None,
                },
                {
                    "key": "root",
                    "title": "n次方根",
                    "parent_key": "container",
                    "category": "knowledge",
                    "start_line": 6,
                    "end_line": 7,
                    "toc_key": None,
                },
                {
                    "key": "fraction",
                    "title": "分数指数幂",
                    "parent_key": "container",
                    "category": "knowledge",
                    "start_line": 9,
                    "end_line": 10,
                    "toc_key": None,
                },
            ],
        }

        result, flattened = MODULE.flatten(
            payload,
            lines,
            maximum_residual_nonblank=8,
        )

        self.assertEqual(len(flattened), 1)
        nodes = {node["key"]: node for node in result["nodes"]}
        self.assertNotIn("container", nodes)
        self.assertEqual(nodes["root"]["parent_key"], "lesson")
        self.assertEqual(nodes["fraction"]["parent_key"], "lesson")
        self.assertNotIn("parent_preview", nodes["root"])
        self.assertEqual(
            nodes["fraction"]["parent_preview"]["start_line"],
            9,
        )
        heading = result["semantic_review"]["headings"][0]
        self.assertEqual(heading["decision"], "retain")
        self.assertTrue(heading["structural_container"])
        self.assertEqual(
            result["semantic_review"]["sections"][0]["child_node_keys"],
            ["root", "fraction"],
        )

    def test_flattens_single_child_container_when_no_body_remains(self):
        lines = [
            "## 1.1 向量运算",
            "#### 1.1.2 向量的数量积",
            "数量积用于研究长度和夹角。",
        ]
        payload = {
            "semantic_review": {
                "headings": [
                    {
                        "line": 2,
                        "title": "1.1.2 向量的数量积",
                        "decision": "split",
                        "node_key": "container",
                        "confidence": 0.99,
                    }
                ],
                "sections": [
                    {
                        "node_key": "lesson",
                        "child_node_keys": ["container"],
                    },
                    {
                        "node_key": "container",
                        "child_node_keys": ["product"],
                    },
                ],
                "ranges": [],
            },
            "nodes": [
                {
                    "key": "lesson",
                    "title": "1.1 向量运算",
                    "parent_key": "chapter",
                    "category": "knowledge",
                    "start_line": 1,
                    "end_line": 3,
                    "toc_key": "toc-lesson",
                },
                {
                    "key": "container",
                    "title": "1.1.2 向量的数量积",
                    "parent_key": "lesson",
                    "category": "knowledge",
                    "start_line": 2,
                    "end_line": 3,
                    "toc_key": None,
                },
                {
                    "key": "product",
                    "title": "向量的数量积",
                    "parent_key": "container",
                    "category": "knowledge",
                    "start_line": 3,
                    "end_line": 3,
                    "toc_key": None,
                },
            ],
        }

        result, flattened = MODULE.flatten(
            payload,
            lines,
            maximum_residual_nonblank=0,
        )

        self.assertEqual(len(flattened), 1)
        nodes = {node["key"]: node for node in result["nodes"]}
        self.assertNotIn("container", nodes)
        self.assertEqual(nodes["product"]["parent_key"], "lesson")

    def test_removes_parent_preview_from_non_knowledge_children(self):
        lines = [
            "## 1.1 向量",
            "阅读材料的开头。",
            "#### 阅读与思考 向量的推广",
            "阅读正文。",
        ]
        payload = {
            "semantic_review": {"headings": [], "sections": [], "ranges": []},
            "nodes": [
                {
                    "key": "lesson",
                    "title": "1.1 向量",
                    "parent_key": "chapter",
                    "category": "knowledge",
                    "start_line": 1,
                    "end_line": 4,
                    "toc_key": "lesson",
                },
                {
                    "key": "reading",
                    "title": "阅读与思考 向量的推广",
                    "parent_key": "lesson",
                    "category": "reading",
                    "start_line": 2,
                    "end_line": 4,
                    "toc_key": None,
                    "parent_preview": {
                        "start_line": 2,
                        "end_line": 2,
                        "role": "exposition",
                    },
                },
            ],
        }

        result, _ = MODULE.flatten(
            payload,
            lines,
            maximum_residual_nonblank=0,
        )

        nodes = {node["key"]: node for node in result["nodes"]}
        self.assertNotIn("parent_preview", nodes["reading"])


if __name__ == "__main__":
    unittest.main()
