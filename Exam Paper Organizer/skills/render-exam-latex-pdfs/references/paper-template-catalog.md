# Paper template catalog

Use `--template-style <id>` to select one structurally independent paper/solutions pair. All bundled implementations use `ctexart` and XeLaTeX so the renderer does not depend on the source package or class that inspired a style.

| ID | Display name | Best fit | Paper template | Solutions template |
|---|---|---|---|---|
| `minimal` | 期末试卷最简版 | Dense, neutral school papers; default | `assets/期末试卷最简版.tex` | `assets/exam-solutions-template.tex` |
| `math-magic` | 数学妙呀 | Chinese worked examples with a textbook-like blue/red annotation voice | `assets/math-magic-paper.tex` | `assets/math-magic-solutions.tex` |
| `chinese-standard` | 中式标准试卷 | Formal Chinese primary, junior-high, senior-high, or college final exams | `assets/chinese-standard-paper.tex` | `assets/chinese-standard-solutions.tex` |
| `classic-academic` | 经典学术考试 | University-style finals with strong running headers, candidate fields, and score boxes | `assets/classic-academic-paper.tex` | `assets/classic-academic-solutions.tex` |
| `ib-markscheme` | IB 评分框架 | Method-marked mathematics assessments and rubric-forward worked solutions | `assets/ib-markscheme-paper.tex` | `assets/ib-markscheme-solutions.tex` |

## Design provenance

The templates are original repo-local implementations. They adopt general layout ideas from the sources below; no upstream class or template source was copied into the assets.

- `math-magic`: Match the user-supplied “数学妙呀” reference image: compact Chinese Song-style text, centered two-line title, crop-corner marks, four-column choices, blue worked text, and restrained red accents.
- `chinese-standard`: Draw from the feature model of [CTAN `exam-zh`](https://ctan.org/pkg/exam-zh)—Chinese exam levels, automatic choices, format/content separation, and seal-line support. The upstream package is LPPL 1.3c.
- `classic-academic`: Draw from the stable header/footer, question hierarchy, and grading-table concepts in [CTAN `exam`](https://ctan.org/pkg/exam), plus the candidate-information and instructions treatment in Overleaf’s [Exam template with solutions](https://www.overleaf.com/latex/templates/exam-template-with-solutions/qqtbvksszkrs). The sources are LPPL 1.3 and CC BY 4.0 respectively.
- `ib-markscheme`: Draw from the criteria and mark-scheme emphasis in Overleaf’s [Exam Template IB style](https://www.overleaf.com/latex/templates/exam-template-ib-style/wrptsshvkzvc), licensed CC BY 4.0.

## Selection rules

- Keep `minimal` when the user gives no style preference.
- Select `math-magic` when the user names “数学妙呀”, “Math Magic”, or supplies the matching blue/red worked-example reference.
- Select `chinese-standard` for a formal Chinese school paper or when a seal-line/candidate-identity treatment is desired.
- Select `classic-academic` for university finals, bilingual headers, or conventional score boxes.
- Select `ib-markscheme` when method marks, criteria, or mark-scheme presentation are central.
- When comparing styles for the same Markdown source, give each run a distinct `--output-dir`; never overwrite an earlier comparison candidate.
