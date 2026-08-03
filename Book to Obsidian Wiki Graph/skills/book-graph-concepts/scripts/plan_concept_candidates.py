#!/usr/bin/env python3
"""Locate reviewable formal-definition candidates from a reviewed term list."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


CUE_RE = re.compile(
    r"叫做|称为|简称为|统称为|定义为|叫作|称作|定义是|"
    r"判断为|就说|我们说|并且说|"
    r"(?<!全)(?<!简)(?<!统)(?<!俗)称[^，。；]{0,48}是|"
    r"(?<!全)(?<!简)(?<!统)(?<!俗)称[^，。；]{0,24}为"
)
DIRECT_NAMING_CUE_RE = re.compile(
    r"叫做|称为|简称为|统称为|定义为|叫作|称作|定义是"
)
DISCOURSE_CUES = {"就说", "我们说", "并且说"}
MATH_RE = re.compile(r"\$\$.*?\$\$|(?<!\$)\$(?!\$).*?(?<!\$)\$(?!\$)")
HEADING_RE = re.compile(r"^#{1,6}\s+")
FORWARD_EXTENSION_RE = re.compile(r"(?:即|记作|表示为|可写成|如下)[：:]?\s*$")
BACKWARD_START_RE = re.compile(r"^(?:一般地|通常|我们规定|对于|如果|设)")
GENERAL_DEFINITION_RE = re.compile(
    r"^(?:一般地|通常|我们规定|如果)|"
    r"定义域为[^。；]{0,120}如果"
)
EXAMPLE_SPECIFIC_RE = re.compile(
    r"^(?:实际上|例如|举例|如图)|"
    r"称函数\s*\$?[^，。；]{0,80}="
)


class ConceptPlanningError(ValueError):
    pass


def mask_math(text: str) -> str:
    return MATH_RE.sub(lambda match: " " * len(match.group(0)), text)


def reviewed_terms(directory: Path) -> list[str]:
    terms = sorted(
        {
            path.stem
            for path in directory.glob("*.md")
            if path.is_file() and path.stem
        },
        key=lambda item: (-len(item), item),
    )
    if not terms:
        raise ConceptPlanningError(
            f"Reviewed concept directory contains no Markdown files: {directory}"
        )
    return terms


def reviewed_term_matches(text: str, term: str) -> list[re.Match[str]]:
    """Match a canonical `X的Y` term even when source inserts a math variable."""

    alternatives = [re.escape(term)]
    if term.count("的") == 1:
        owner, property_name = term.split("的", 1)
        if owner and property_name:
            inserted_variable = (
                r"(?:\s{2,}|\s*[A-Za-zΑ-Ωα-ω]"
                r"[A-Za-z0-9_Α-Ωα-ω]*\s*)"
            )
            alternatives.append(
                re.escape(owner)
                + inserted_variable
                + r"的\s*"
                + re.escape(property_name)
            )
    return list(re.finditer("(?:" + "|".join(alternatives) + ")", text))


def definition_surface(text: str, term: str) -> str:
    masked = mask_math(text)
    matches = reviewed_term_matches(masked, term)
    if not matches:
        raise ConceptPlanningError(
            f"selected reviewed term has no source surface: {term}"
        )
    selected = matches[-1]
    return text[selected.start() : selected.end()]


def candidate_terms_for_line(text: str, terms: list[str]) -> set[str]:
    masked = mask_math(text)
    found: set[str] = set()
    cues = list(CUE_RE.finditer(masked))
    for cue_index, cue in enumerate(cues):
        tail_start = cue.end()
        while (
            tail_start < len(masked)
            and masked[tail_start] in " \t，,：:"
        ):
            tail_start += 1
        punctuation = [
            position
            for marker in ("。", "．", ".", "；", ";", "，", ",")
            if (position := masked.find(marker, tail_start)) >= 0
        ]
        next_cue = (
            cues[cue_index + 1].start()
            if cue_index + 1 < len(cues)
            else len(masked)
        )
        tail_end = min(
            [tail_start + 240, next_cue, *punctuation]
        )
        tail = masked[tail_start:tail_end]
        occurrences: list[tuple[int, int, str]] = []
        for term in terms:
            matches = [
                match
                for match in reviewed_term_matches(tail, term)
                if not (
                    "的" in term
                    and match.start() > 0
                    and re.fullmatch(
                        r"[\u3400-\u9fff]+", tail[: match.start()]
                    )
                )
            ]
            if matches:
                selected_match = matches[-1]
                occurrences.append(
                    (
                        selected_match.start(),
                        -(selected_match.end() - selected_match.start()),
                        term,
                    )
                    )
        if not occurrences and cue.group(0) in DIRECT_NAMING_CUE_RE.pattern:
            sentence_positions = [
                position
                for marker in ("。", "．", ".", "；", ";")
                if (position := masked.find(marker, tail_start)) >= 0
            ]
            extended_end = min(sentence_positions or [len(masked)])
            extended_tail = masked[tail_start:extended_end]
            for term in terms:
                if "的" not in term:
                    continue
                for match in reviewed_term_matches(extended_tail, term):
                    prefix = extended_tail[: match.start()].rstrip()
                    if prefix.endswith("的"):
                        occurrences.append(
                            (
                                match.start(),
                                -(match.end() - match.start()),
                                term,
                            )
                        )
            if occurrences:
                tail = extended_tail
        if not occurrences:
            continue
        occurrences = [
            item
            for item in occurrences
            if not any(
                other is not item
                and other[0] <= item[0]
                and other[0] + (-other[1]) >= item[0] + (-item[1])
                and (-other[1]) > (-item[1])
                for other in occurrences
            )
        ]
        selected = (
            min(occurrences, key=lambda item: (item[0], item[1]))
            if cue.group(0) in {"就说", "我们说", "并且说"}
            and "是" not in tail
            else max(occurrences, key=lambda item: (item[0], -item[1]))
        )
        found.add(selected[2])
        # Keep an explicitly stated alternative name, for example
        # 非负整数集（或自然数集）.
        for offset, neg_length, term in occurrences:
            if term == selected[2]:
                continue
            between = tail[offset + (-neg_length) : selected[0]]
            if re.fullmatch(r"[\s（(]*或[\s）)]*", between):
                found.add(term)

        # A single definition sentence may introduce parallel terms after the
        # first cue, for example “p 是 q 的充分条件，q 是 p 的必要条件”.
        # Keep these as review candidates only when the same sentence already
        # contains a recognized definition cue.
        sentence_end = min(
            [
                position
                for marker in ("。", "．", ".")
                if (position := masked.find(marker, cue.end())) >= 0
            ]
            or [len(masked)]
        )
        sentence = masked[cue.end() : sentence_end]
        for term in terms:
            if term in found or not reviewed_term_matches(sentence, term):
                continue
            if any(term in existing and len(existing) > len(term) for existing in found):
                continue
            for clause in re.split(r"[，,；;]", sentence):
                if "规定" in clause:
                    continue
                if re.search(
                    rf"^[^。；;]{{0,48}}是[^。；;]{{0,32}}{re.escape(term)}",
                    clause.strip(),
                ):
                    found.add(term)
                    break
    return found


def definition_evidence_priority(text: str, term: str) -> int:
    """Rank direct naming evidence ahead of broader discourse cues."""

    masked = mask_math(text)
    term_positions = [
        match.start() for match in reviewed_term_matches(masked, term)
    ]
    if not term_positions:
        return 3

    for cue in DIRECT_NAMING_CUE_RE.finditer(masked):
        for position in term_positions:
            if cue.end() <= position:
                between = masked[cue.end() : position]
                if len(between) <= 80 and not re.search(r"[。．；;]", between):
                    return 0

    for cue in CUE_RE.finditer(masked):
        for position in term_positions:
            if cue.end() <= position:
                between = masked[cue.end() : position]
                if len(between) <= 120 and not re.search(r"[。．；;]", between):
                    return 2 if cue.group(0) in DISCOURSE_CUES else 1
    return 3


def definition_generality_priority(text: str) -> int:
    """Prefer general formal definitions over concrete worked examples."""

    masked = mask_math(text).strip()
    if GENERAL_DEFINITION_RE.search(masked):
        return 0
    if EXAMPLE_SPECIFIC_RE.search(masked):
        return 2
    return 1


def has_math_equation(text: str) -> bool:
    return any(
        "=" in match.group(0) or r"\equiv" in match.group(0)
        for match in MATH_RE.finditer(text)
    )


def definition_range(lines: list[str], cue_line: int) -> tuple[int, int]:
    start = cue_line
    end = cue_line
    current = lines[cue_line - 1].strip()

    if current.startswith(("那么", "其中", "此时")):
        lower_bound = max(1, cue_line - 12)
        for line_number in range(cue_line - 1, lower_bound - 1, -1):
            text = lines[line_number - 1].strip()
            if HEADING_RE.match(text):
                break
            if BACKWARD_START_RE.match(text):
                start = line_number
                break

    if FORWARD_EXTENSION_RE.search(current):
        saw_nonempty = False
        for line_number in range(cue_line + 1, min(len(lines), cue_line + 12) + 1):
            text = lines[line_number - 1].strip()
            if HEADING_RE.match(text):
                break
            if text:
                saw_nonempty = True
                end = line_number
            elif saw_nonempty:
                break
    return start, end


def plan_candidates(
    book_root: Path,
    reviewed_directory: Path,
    rejected_terms: set[str] | None = None,
) -> dict[str, Any]:
    terms = reviewed_terms(reviewed_directory)
    rejected_terms = rejected_terms or set()
    concept_directory_names = {"概念"}
    hits: dict[str, list[dict[str, Any]]] = {term: [] for term in terms}

    for source in sorted(book_root.rglob("*.md")):
        if any(part in concept_directory_names for part in source.relative_to(book_root).parts):
            continue
        lines = source.read_text(encoding="utf-8-sig").splitlines()
        display_math = False
        for line_number, text in enumerate(lines, start=1):
            delimiter_count = text.count("$$")
            line_in_display_math = display_math or delimiter_count > 0
            if delimiter_count % 2:
                display_math = not display_math
            if HEADING_RE.match(text):
                continue
            if line_in_display_math:
                continue
            for term in candidate_terms_for_line(text, terms):
                start, end = definition_range(lines, line_number)
                definition_text = "\n".join(lines[start - 1 : end])
                surface = definition_surface(text, term)
                review_flags: list[str] = []
                if term.endswith(("公式", "方程")) and not has_math_equation(
                    definition_text
                ):
                    review_flags.append("formula-definition-has-no-equation")
                hits[term].append(
                    {
                        "definition_source": source.relative_to(book_root).as_posix(),
                        "definition_start_line": start,
                        "definition_end_line": end,
                        "anchor_text": surface,
                        "link_text": surface,
                        "confidence": "low" if review_flags else "high",
                        "reviewed": False,
                        "review_flags": review_flags,
                        "_generality_priority": definition_generality_priority(
                            text
                        ),
                        "_evidence_priority": definition_evidence_priority(
                            text, term
                        ),
                        "_category_priority": (
                            0
                            if source.relative_to(book_root).parts[0] == "知识点"
                            else 1
                        ),
                    }
                )

    concepts: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for term in sorted(terms):
        if term in rejected_terms:
            rejected.append(
                {
                    "name": term,
                    "reason": (
                        "Rejected during current-source review because the "
                        "located occurrence is not a complete formal definition."
                    ),
                }
            )
            continue
        options = sorted(
            hits[term],
            key=lambda item: (
                item["_generality_priority"],
                item["_evidence_priority"],
                item["_category_priority"],
                item["definition_source"],
                item["definition_start_line"],
            ),
        )
        if not options:
            rejected.append(
                {
                    "name": term,
                    "reason": (
                        "No current definition cue links this reviewed term to "
                        "a complete, linkable occurrence."
                    ),
                }
            )
            continue
        selected = dict(options[0])
        selected.pop("_generality_priority", None)
        selected.pop("_evidence_priority", None)
        selected.pop("_category_priority", None)
        concepts.append({"name": term, **selected})

    return {
        "schema_version": 1,
        "status": "review_required",
        "review_basis": str(reviewed_directory),
        "concepts": concepts,
        "rejected": rejected,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_root", type=Path)
    parser.add_argument("reviewed_concept_directory", type=Path)
    parser.add_argument("output_candidates", type=Path)
    parser.add_argument(
        "--reject-term",
        action="append",
        default=[],
        help="Record a reviewed term as rejected for the current source",
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        book_root = args.book_root.resolve()
        reviewed = args.reviewed_concept_directory.resolve()
        output = args.output_candidates.resolve()
        if not book_root.is_dir():
            raise FileNotFoundError(f"Book root does not exist: {book_root}")
        if not reviewed.is_dir():
            raise FileNotFoundError(
                f"Reviewed concept directory does not exist: {reviewed}"
            )
        if output.exists() and not args.overwrite:
            raise FileExistsError(
                f"Output exists; pass --overwrite explicitly: {output}"
            )
        unknown_rejections = sorted(
            set(args.reject_term) - set(reviewed_terms(reviewed))
        )
        if unknown_rejections:
            raise ConceptPlanningError(
                "Rejected terms are absent from the reviewed directory: "
                + ", ".join(unknown_rejections)
            )
        payload = plan_candidates(
            book_root,
            reviewed,
            rejected_terms=set(args.reject_term),
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "stage": "book-concept-candidate-planning",
                    "status": "review_required",
                    "candidates": str(output),
                    "accepted_candidates": len(payload["concepts"]),
                    "rejected_candidates": len(payload["rejected"]),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "stage": "book-concept-candidate-planning",
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
