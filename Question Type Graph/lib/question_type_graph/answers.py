from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path
from typing import Any

from .common import (
    compile_number_patterns,
    ConfigurationError,
    load_json,
    load_profile,
    lexical_signature,
    prune_empty_directories,
    rebase_local_links,
    require_reviewed_adapter,
    sha256_file,
    sha256_text,
    write_json_atomic,
    write_text_atomic,
)
from .spans import split_virtual_lines


QUESTION_BODY_RE = re.compile(
    r"<!-- question-source:start -->\n(.*?)\n<!-- question-source:end -->",
    re.DOTALL,
)
ANSWER_BODY_RE = re.compile(
    r"\n## 答案与解析\n\n<!-- answer-source:start -->\n.*?\n<!-- answer-source:end -->\n?",
    re.DOTALL,
)
GENERATED_ANSWER_EMBED_RE = re.compile(
    r"(?m)^\s*!\[\[(?P<name>Q\d{8}A\d+)(?:[^\]]*)\]\]\s*\n?"
)


def source_for_answers(profile: dict[str, Any], adapter: dict[str, Any]) -> tuple[Path, str]:
    config = adapter.get("answers", {})
    role = str(config.get("source_role") or ("combined" if profile["answers"]["mode"] == "embedded" else "answers"))
    values = [source for source in profile["sources"] if source.get("role") == role]
    if len(values) != 1:
        raise ConfigurationError(f"Answer source role must resolve once: {role}")
    markdown = Path(values[0]["markdown_path"]).resolve()
    if not markdown.is_file():
        raise ConfigurationError(f"Converted answer Markdown is missing: {markdown}")
    return markdown, role


def in_ignored_range(line: int, ranges: list[dict[str, Any]]) -> bool:
    return any(int(item["start_line"]) <= line <= int(item["end_line"]) for item in ranges)


def parse_answer_blocks(path: Path, adapter: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    config = adapter.get("answers", {})
    context_rules = [
        (str(item["key"]), re.compile(str(item["pattern"])))
        for item in config.get("contexts", [])
        if item.get("pattern")
    ]
    fixed_contexts = {
        int(item["start_line"]): str(item["key"])
        for item in config.get("contexts", [])
        if item.get("start_line") is not None
    }
    answer_patterns = compile_number_patterns(
        config.get("answer_patterns"), "answers.answer_patterns"
    )
    inline_patterns = (
        compile_number_patterns(
            config.get("inline_answer_patterns"),
            "answers.inline_answer_patterns",
            required=False,
        )
        if "inline_answer_patterns" in config
        else answer_patterns
    )
    raw_lines = path.read_text(encoding="utf-8-sig").splitlines()
    for item in [
        *config.get("contexts", []),
        *config.get("implicit_answers", []),
        *config.get("choice_answer_overrides", []),
        *config.get("short_answer_overrides", []),
    ]:
        if item.get("start_line") is None:
            continue
        anchor_line = int(item["start_line"])
        if anchor_line < 1 or anchor_line > len(raw_lines):
            raise ConfigurationError(f"Answer context start_line is outside the raw Markdown: {item.get('key')}")
        anchor_text = str(item.get("anchor_text", "")).strip()
        if anchor_text and raw_lines[anchor_line - 1].strip() != anchor_text:
            raise ConfigurationError(f"Answer context anchor_text drifted: {item.get('key')}")
        anchor_pattern = item.get("anchor_pattern")
        if anchor_pattern and not re.search(str(anchor_pattern), raw_lines[anchor_line - 1]):
            raise ConfigurationError(
                f"Answer boundary anchor_pattern drifted: {item.get('key') or item.get('context')}"
            )
    implicit_answers = {
        (int(item["start_line"]), int(item.get("raw_column", 1))): item
        for item in config.get("implicit_answers", [])
        if item.get("start_line") is not None
    }
    implicit_starts: dict[int, set[int]] = {}
    for raw_line, raw_column in implicit_answers:
        implicit_starts.setdefault(raw_line, set()).add(raw_column)
    lines = split_virtual_lines(
        raw_lines,
        inline_patterns,
        additional_starts=implicit_starts,
    )
    number_shift_ranges = config.get("answer_number_shift_ranges", [])
    for item in number_shift_ranges:
        start_line = int(item["start_line"])
        end_line = int(item["end_line"])
        for line_number, text_key, pattern_key in (
            (start_line, "anchor_text", "anchor_pattern"),
            (end_line, "end_anchor_text", "end_anchor_pattern"),
        ):
            if line_number < 1 or line_number > len(raw_lines):
                raise ConfigurationError("Answer number shift range is outside the raw Markdown")
            anchor_text = str(item.get(text_key, "")).strip()
            if anchor_text and raw_lines[line_number - 1].strip() != anchor_text:
                raise ConfigurationError(f"Answer number shift range {text_key} drifted")
            anchor_pattern = item.get(pattern_key)
            if anchor_pattern and not re.search(str(anchor_pattern), raw_lines[line_number - 1]):
                raise ConfigurationError(f"Answer number shift range {pattern_key} drifted")

    def shifted_number(value: str, answer_context: str | None, raw_line: int, raw_column: int) -> str:
        result = value
        coordinate = (raw_line, raw_column)
        for item in number_shift_ranges:
            if str(item.get("context")) != str(answer_context):
                continue
            start_coordinate = (int(item["start_line"]), int(item.get("start_column", 1)))
            end_coordinate = (int(item["end_line"]), int(item.get("end_column", 2**31 - 1)))
            if start_coordinate <= coordinate <= end_coordinate:
                if not result.isdecimal():
                    raise ConfigurationError("Answer number shift requires a decimal source number")
                result = str(int(result) + int(item["offset"]))
                if int(result) < 1:
                    raise ConfigurationError("Answer number shift produced a non-positive number")
        return result
    region = config.get("region") or {}
    start_limit = int(region.get("start_line", 1))
    end_limit = int(region.get("end_line", len(raw_lines)))
    if start_limit < 1 or end_limit > len(raw_lines) or start_limit > end_limit:
        raise ConfigurationError("Answer region is outside the raw Markdown")
    ignored = config.get("ignore_ranges", [])
    events: list[dict[str, Any]] = []
    context: str | None = None
    review: list[dict[str, Any]] = []
    strategies = config.get("matching_strategies") or ["hierarchy-number"]
    needs_context = any(
        (item if isinstance(item, str) else item.get("name")) == "hierarchy-number"
        for item in strategies
    )
    for position, line_entry in enumerate(lines):
        line_number = int(line_entry["raw_line"])
        if line_number < start_limit or line_number > end_limit:
            continue
        if in_ignored_range(line_number, ignored):
            continue
        line = str(line_entry["text"])
        fixed_context = fixed_contexts.get(line_number) if line_entry["subline"] == 0 else None
        if fixed_context:
            context = fixed_context
            events.append({"kind": "context", "line": line_number, "position": position, "context": context})
        matched_context = next((key for key, pattern in context_rules if pattern.search(line)), None)
        if matched_context:
            context = matched_context
            events.append({"kind": "context", "line": line_number, "position": position, "context": context})
            continue
        implicit = implicit_answers.get(
            (line_number, int(line_entry["raw_column"]))
        )
        if implicit:
            implicit_context = str(implicit.get("context") or context or "").strip()
            implicit_number = str(implicit.get("number", "")).strip()
            if not implicit_context or not implicit_number:
                raise ConfigurationError(
                    "Every implicit answer requires a reviewed context and number"
                )
            context = implicit_context
            events.append(
                {
                    "kind": "answer",
                    "line": line_number,
                    "subline": int(line_entry["subline"]),
                    "raw_column": int(line_entry["raw_column"]),
                    "position": position,
                    "context": context,
                    "number": shifted_number(
                        implicit_number,
                        context,
                        line_number,
                        int(line_entry["raw_column"]),
                    ),
                    "evidence": {"implicit_header": "reviewed-ocr-omission"},
                }
            )
            continue
        for pattern in answer_patterns:
            match = pattern.match(line)
            if match:
                if context is None and needs_context:
                    review.append({"kind": "answer-without-context", "line": line_number, "text": line})
                evidence = {
                    key: str(value).strip()
                    for key, value in match.groupdict().items()
                    if key != "number" and value is not None and str(value).strip()
                }
                events.append(
                    {
                        "kind": "answer",
                        "line": line_number,
                        "subline": int(line_entry["subline"]),
                        "raw_column": int(line_entry["raw_column"]),
                        "position": position,
                        "context": context,
                        "number": shifted_number(
                            str(match.group("number")).strip(),
                            context,
                            line_number,
                            int(line_entry["raw_column"]),
                        ),
                        "evidence": evidence,
                    }
                )
                break
    answers = [event for event in events if event["kind"] == "answer"]
    for answer in answers:
        end_position = len(lines)
        for event in events:
            if event["position"] > answer["position"] and event["kind"] in {"answer", "context"}:
                end_position = event["position"]
                break
        body_entries = lines[answer["position"]:end_position]
        body = "\n".join(str(item["text"]) for item in body_entries).rstrip() + "\n"
        answer["end_line"] = int(body_entries[-1]["raw_line"]) if body_entries else answer["line"]
        answer["body"] = body
        answer["body_sha256"] = sha256_text(body)
        answer["id"] = (
            f"{answer.get('context')}:{answer['number']}:{answer['line']}:{answer['subline']}"
        )

    deduped_answers: list[dict[str, Any]] = []
    for ans in answers:
        if (
            deduped_answers
            and deduped_answers[-1].get("context") == ans.get("context")
            and deduped_answers[-1].get("number") == ans.get("number")
        ):
            prev = deduped_answers[-1]
            if ans["position"] - prev["position"] <= 4:
                if len(ans["body"].strip()) >= len(prev["body"].strip()):
                    deduped_answers[-1] = ans
                continue
        deduped_answers.append(ans)
    answers = deduped_answers

    # MinerU can omit an entire answer block even when the corresponding PDF
    # page is legible (for example, when two columns are merged incorrectly).
    # Allow a reviewer to restore that authoritative block without editing the
    # immutable converted Markdown.  The raw anchor and source page make the
    # recovery drift-resistant and auditable.
    recovered_keys = {(str(item.get("context")), str(item.get("number"))) for item in answers}
    for ordinal, item in enumerate(config.get("recovered_answers", []), 1):
        if item.get("reviewer_confirmed") is not True:
            raise ConfigurationError("Recovered answer must be reviewer_confirmed")
        after_line = int(item["after_line"])
        if after_line < 1 or after_line > len(raw_lines):
            raise ConfigurationError("Recovered answer anchor is outside the raw Markdown")
        anchor_text = str(item.get("anchor_text", "")).strip()
        if anchor_text and raw_lines[after_line - 1].strip() != anchor_text:
            raise ConfigurationError("Recovered answer anchor_text drifted")
        anchor_pattern = item.get("anchor_pattern")
        if anchor_pattern and not re.search(str(anchor_pattern), raw_lines[after_line - 1]):
            raise ConfigurationError("Recovered answer anchor_pattern drifted")
        answer_context = str(item["context"]).strip()
        number = str(item["number"]).strip()
        body = str(item["body"]).strip() + "\n"
        header = next((pattern.match(body) for pattern in answer_patterns if pattern.match(body)), None)
        if header is None or str(header.group("number")).strip() != number:
            raise ConfigurationError("Recovered answer body must start with its reviewed number")
        identity = (answer_context, number)
        if identity in recovered_keys:
            raise ConfigurationError("Recovered answer duplicates a parsed context-number identity")
        recovered_keys.add(identity)
        answers.append(
            {
                "kind": "answer",
                "line": after_line,
                "end_line": after_line,
                "subline": ordinal,
                "raw_column": 2**30 + ordinal,
                "position": len(lines) + ordinal,
                "context": answer_context,
                "number": number,
                "body": body,
                "body_sha256": sha256_text(body),
                "id": f"{answer_context}:{number}:{after_line}:recovered-{ordinal}",
                "evidence": {
                    "reviewed_pdf_recovery": str(item.get("source_page", "reviewed")),
                },
            }
        )

    return answers, review


def normalized_stem(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    return re.sub(r"[^\w\u4e00-\u9fff]", "", text).casefold()[:240]


def build_answer_indexes(answers: list[dict[str, Any]]) -> dict[str, Any]:
    indexes: dict[str, Any] = {
        "hierarchy_number": {},
        "number": {},
        "evidence": {},
        "evidence_number": {},
        "normalized_evidence": {},
    }
    for answer in answers:
        number = str(answer.get("number"))
        context = str(answer.get("context"))
        indexes["hierarchy_number"].setdefault((context, number), []).append(answer)
        indexes["number"].setdefault(number, []).append(answer)
        for field, raw_value in (answer.get("evidence") or {}).items():
            value = str(raw_value).strip()
            indexes["evidence"].setdefault((str(field), value), []).append(answer)
            indexes["evidence_number"].setdefault((str(field), value, number), []).append(answer)
            normalized = normalized_stem(value)
            if normalized:
                indexes["normalized_evidence"].setdefault((str(field), normalized), []).append(answer)
    return indexes


def strategy_candidates(
    strategy: str | dict[str, Any],
    question: dict[str, Any],
    question_body: str,
    answers: list[dict[str, Any]],
    indexes: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    config = {"name": strategy} if isinstance(strategy, str) else strategy
    name = str(config.get("name", "")).strip()
    question_evidence = question.get("evidence") or {}
    indexes = indexes or build_answer_indexes(answers)
    if name == "hierarchy-number":
        values = list(
            indexes["hierarchy_number"].get(
                (str(question.get("context_key")), str(question.get("number"))), []
            )
        )
    elif name in {"explicit-reference", "source-page-number"}:
        default_field = "reference" if name == "explicit-reference" else "source_page"
        question_field = str(config.get("question_field", default_field))
        answer_field = str(config.get("answer_field", default_field))
        expected = str(question_evidence.get(question_field, "")).strip()
        key = (answer_field, expected, str(question.get("number")))
        values = list(
            indexes["evidence_number"].get(key, [])
            if name == "source-page-number"
            else indexes["evidence"].get((answer_field, expected), [])
        ) if expected else []
    elif name == "normalized-stem-exact":
        question_field = str(config.get("question_field", "stem"))
        answer_field = str(config.get("answer_field", "stem"))
        expected = normalized_stem(str(question_evidence.get(question_field, "")) or question_body)
        values = list(indexes["normalized_evidence"].get((answer_field, expected), [])) if expected else []
    else:
        raise ConfigurationError(f"Unsupported answer matching strategy: {name}")
    return name, values


def plan_matches(profile_path: Path, adapter_path: Path, content_manifest_path: Path) -> dict[str, Any]:
    profile = load_profile(profile_path)
    adapter = require_reviewed_adapter(profile, adapter_path)
    content = load_json(content_manifest_path)
    external_questions = [
        question
        for question in content.get("questions", [])
        if question.get("answer_handling", "external") == "external"
    ]
    mode = profile.get("answers", {}).get("mode")
    if mode == "unavailable":
        return {
            "schema_version": 1,
            "stage": "answer-matching",
            "status": "passed",
            "reviewer_confirmed": True,
            "profile": profile["_profile_path"],
            "adapter": str(adapter_path.resolve()),
            "adapter_sha256": sha256_file(adapter_path),
            "content_manifest": str(content_manifest_path.resolve()),
            "content_manifest_sha256": sha256_file(content_manifest_path),
            "mode": "unavailable",
            "matches": [],
            "review_items": [],
            "review_summary": {},
            "review_groups": [],
            "metrics": {"question_count": len(external_questions), "separate_authoritative_count": len(content.get("questions", [])) - len(external_questions), "matched_count": 0, "match_rate": None},
        }
    answer_markdown, role = source_for_answers(profile, adapter)
    answers, review = parse_answer_blocks(answer_markdown, adapter)
    indexes = build_answer_indexes(answers)
    strategies = adapter.get("answers", {}).get("matching_strategies") or ["hierarchy-number"]
    matches: list[dict[str, Any]] = []
    used_answer_ids: set[str] = set()
    for question in external_questions:
        question_note = Path(question["output"])
        question_text = question_note.read_text(encoding="utf-8-sig") if question_note.is_file() else ""
        body_match = QUESTION_BODY_RE.search(question_text)
        question_body = body_match.group(1) if body_match else question["title"]
        evaluated = [
            strategy_candidates(strategy, question, question_body, answers, indexes)
            for strategy in strategies
        ]
        decisive = [(name, values[0]) for name, values in evaluated if len(values) == 1]
        conflicts = {answer["id"] for _, answer in decisive}
        ambiguous = [(name, values) for name, values in evaluated if len(values) > 1]
        if len(conflicts) > 1:
            review.append(
                {
                    "kind": "conflicting-answer-evidence",
                    "question_id": question["id"],
                    "evidence": [{"strategy": name, "answer_id": answer["id"]} for name, answer in decisive],
                }
            )
            continue
        if decisive and not ambiguous:
            strategy, answer = decisive[0]
            if answer["id"] in used_answer_ids:
                # Already claimed by an earlier question (numbering-restart
                # context where the second run's own answer block is missing
                # from OCR, so both runs see the same single candidate).  Never
                # double-assign: the audit hard-errors on answer-owned-more-
                # than-once.  Route to the duplicate-answer review queue like
                # the two-candidate restart numbers.
                review.append(
                    {
                        "kind": "duplicate-answer",
                        "root_cause": "context-boundary-mismatch",
                        "question_id": question["id"],
                        "context": str(question.get("context_key")),
                        "number": str(question.get("number")),
                        "candidate_count": 1,
                        "strategy_results": [
                            {"strategy": name, "candidate_ids": [item["id"] for item in values]}
                            for name, values in evaluated
                        ],
                        "fuzzy_suggestions_not_accepted": [],
                    }
                )
                continue
            used_answer_ids.add(answer["id"])
            matches.append(
                {
                    "question_id": question["id"],
                    "question_path": question["output"],
                    "answer_id": answer["id"],
                    "answer_context": answer.get("context"),
                    "answer_number": answer["number"],
                    "answer_start_line": answer["line"],
                    "answer_end_line": answer["end_line"],
                    "answer_body": answer["body"],
                    "answer_body_sha256": answer["body_sha256"],
                    "answer_body_lexical_signature": lexical_signature(answer["body"]),
                    "strategy": strategy,
                    "status": "matched",
                }
            )
        else:
            stem = normalized_stem(question_body)
            suggestions = []
            ambiguous_pool = {
                answer["id"]: answer
                for _, values in ambiguous
                for answer in values
            }
            candidate_pool = list(ambiguous_pool.values()) or list(
                indexes["number"].get(str(question.get("number")), [])
            )
            for answer in candidate_pool:
                ratio = difflib.SequenceMatcher(None, stem, normalized_stem(answer["body"])).ratio()
                if ratio >= 0.35:
                    suggestions.append({"answer_id": answer["id"], "ratio": round(ratio, 4)})
            suggestions.sort(key=lambda item: item["ratio"], reverse=True)
            review.append(
                {
                    "kind": "duplicate-answer" if ambiguous else "missing-answer",
                    "root_cause": (
                        "context-boundary-mismatch"
                        if ambiguous or indexes["number"].get(str(question.get("number")))
                        else "missing-answer-key"
                    ),
                    "question_id": question["id"],
                    "context": str(question.get("context_key")),
                    "number": str(question.get("number")),
                    "candidate_count": max((len(values) for _, values in evaluated), default=0),
                    "strategy_results": [{"strategy": name, "candidate_ids": [item["id"] for item in values]} for name, values in evaluated],
                    "fuzzy_suggestions_not_accepted": suggestions[:5],
                }
            )
    used = {match["answer_id"] for match in matches}
    for answer in answers:
        if answer["id"] not in used:
            review.append({"kind": "unmatched-answer", "answer_id": answer["id"], "context": answer.get("context"), "number": answer["number"]})
    review_summary: dict[str, int] = {}
    review_groups: dict[tuple[str, str, str], int] = {}
    for item in review:
        kind = str(item.get("kind", "unknown"))
        review_summary[kind] = review_summary.get(kind, 0) + 1
        group_key = (kind, str(item.get("context", "")), str(item.get("number", "")))
        review_groups[group_key] = review_groups.get(group_key, 0) + 1
    return {
        "schema_version": 1,
        "stage": "answer-matching",
        "status": "review_required" if review else "passed",
        "reviewer_confirmed": False if review else True,
        "profile": profile["_profile_path"],
        "adapter": str(adapter_path.resolve()),
        "adapter_sha256": sha256_file(adapter_path),
        "content_manifest": str(content_manifest_path.resolve()),
        "content_manifest_sha256": sha256_file(content_manifest_path),
        "mode": mode,
        "answer_source_role": role,
        "answer_markdown": str(answer_markdown),
        "answer_markdown_sha256": sha256_file(answer_markdown),
        "matches": matches,
        "review_items": review,
        "review_summary": review_summary,
        "review_groups": [
            {"kind": kind, "context": context, "number": number, "count": count}
            for (kind, context, number), count in sorted(review_groups.items())
        ],
        "metrics": {
            "question_count": len(external_questions),
            "separate_authoritative_count": len(content.get("questions", [])) - len(external_questions),
            "answer_block_count": len(answers),
            "matched_count": len(matches),
            "match_rate": round(len(matches) / len(external_questions), 4)
            if external_questions
            else 1.0,
        },
    }


def extract_choice_answer(body: str) -> str | None:
    """Extract a publisher-stated choice answer without guessing from prose.

    OCR sometimes drops the leading ``【N】D`` record while preserving a
    conclusive phrase such as ``故选:D`` at the end of the explanation.  The
    conclusion is authoritative evidence and should still render as a
    separate answer field.  Only explicit answer/conclusion phrases are
    accepted; isolated capital letters in mathematical prose are ignored.
    """
    conclusion_pattern = re.compile(
        r"(?:故\s*选|应\s*选|选|选项(?:为|是|有)?|答案(?:为|是)?)"
        r"\s*[：:]?\s*([A-F]+)\b",
        re.IGNORECASE,
    )
    matches = list(conclusion_pattern.finditer(body))
    if matches:
        # A worked conclusion is stronger evidence than an OCR-damaged
        # leading header (which can retain the neighbouring question number
        # and option after page/column interleaving).
        return matches[-1].group(1).upper()

    lines = body.strip().splitlines()
    if lines:
        first_line = lines[0].strip()
        header = re.match(
            r"^【?\d+】?[\.、\s]*([A-F]+)\b\s*(?:【解析】)?\s*",
            first_line,
        )
        if header:
            return header.group(1)
    return None


def extract_nonchoice_answer_prefix(body: str) -> tuple[str | None, str]:
    """Split a publisher-stated short answer from the following analysis.

    Common OCR blocks are shaped like ``【12】$\\frac12$ 解析：...`` or put
    the short answer on several display-math lines before ``【解析】``.  This
    helper accepts only that bounded, explicit prefix; it does not guess a
    result from derivation prose.
    """
    text = re.sub(r"^【?\d+】?[\.、\s]*", "", body.strip(), count=1)
    marker = re.search(r"【解析】|(?<!见)解析\s*[：:]", text)
    if marker is None:
        return None, text
    prefix = text[:marker.start()].strip()
    analysis = text[marker.end():].strip()
    prefix = re.sub(r"^(?:【答案】|答案\s*[：:])\s*", "", prefix).strip()
    prefix_lines = prefix.splitlines()
    leading_assets = [
        line.strip()
        for line in prefix_lines
        if re.fullmatch(r"!\[[^]]*\]\([^)]+\)", line.strip())
    ]
    prefix = "\n".join(
        line for line in prefix_lines if line.strip() not in leading_assets
    ).strip()
    if leading_assets:
        analysis = "\n".join([*leading_assets, analysis]).strip()
    compact = re.sub(r"\s+", " ", prefix).strip()
    if (
        not compact
        or len(compact) > 400
        or re.match(r"^\(\d+\)\s*[×√]", compact)
    ):
        return None, text
    return compact, analysis


def format_answer_callout(
    body: str,
    callout_title: str = "答案与解析",
    reviewed_choice_answer: str | None = None,
    reviewed_short_answer: str | None = None,
) -> str:
    source_body = body.strip()
    explicit_answer = None
    long_explicit_answer = None
    if re.match(r"^\s*(?:#{1,6}\s*)?【答案】", source_body):
        candidate_answer, _ = extract_nonchoice_answer_prefix(source_body)
        if candidate_answer is not None:
            explicit_answer = candidate_answer
        else:
            marker = re.search(r"【解析】|(?<!见)解析\s*[：:]", source_body)
            if marker is not None:
                prefix = re.sub(
                    r"^\s*(?:#{1,6}\s*)?【答案】\s*",
                    "",
                    source_body[: marker.start()],
                    count=1,
                ).strip()
                if prefix:
                    long_explicit_answer = prefix
    analysis_match = re.search(
        r"(?m)^\s*(?:#{1,6}\s*)?(?:【分析】|分析(?:\s|[：:]|▶|$))",
        source_body,
    )
    analysis_text = "本题未单列分析。"
    resolution_body = source_body
    if analysis_match is not None:
        resolution_match = re.search(
            r"(?m)^\s*(?:#{1,6}\s*)?(?:【(?:解析|详解)】|(?:解析|详解)(?:\s|[：:]|▶|$))",
            source_body[analysis_match.end():],
        )
        if resolution_match is not None:
            resolution_start = analysis_match.end() + resolution_match.start()
            analysis_text = source_body[analysis_match.start():resolution_start].strip()
            resolution_body = source_body[resolution_start:].strip()
        else:
            analysis_text = source_body[analysis_match.start():].strip()
            resolution_body = "本题未单列解析。"

    if long_explicit_answer:
        resolution_body = "\n".join(
            ["【答案】" + long_explicit_answer, resolution_body]
        ).strip()

    lines = resolution_body.splitlines() or [""]

    # Prefer an explicit worked conclusion over an OCR header when both are
    # present; a reviewed override remains the highest authority.
    explicit_choice_answer = (
        explicit_answer.upper()
        if explicit_answer and re.fullmatch(r"[A-F]+", explicit_answer, re.IGNORECASE)
        else None
    )
    option = (
        reviewed_choice_answer
        or extract_choice_answer(resolution_body)
        or extract_choice_answer(source_body)
        or explicit_choice_answer
    )
    explicit_nonchoice_answer = (
        explicit_answer if explicit_answer and explicit_choice_answer is None else None
    )
    prepared_analysis = None
    if option is None:
        candidate_answer, candidate_analysis = extract_nonchoice_answer_prefix(
            resolution_body
        )
        if candidate_answer is not None:
            explicit_nonchoice_answer = candidate_answer
            prepared_analysis = candidate_analysis
            lines = prepared_analysis.splitlines() or [""]
    first_line = lines[0].strip()
    m_opt = (
        re.match(r"^【?\d+】?[\.、\s]*([A-F]+)\b\s*(?:【解析】)?\s*", first_line)
        if prepared_analysis is None
        else None
    )
    if m_opt:
        option = option or m_opt.group(1)
        first_line = first_line[m_opt.end():].strip()
    else:
        # 判断题答案形如 (1) ×; (2) √; ... —— 把整段判断结果作为【答案】。
        # 答案可能跨行（如第一行 (1)…(7) ×;，第二行 (8) ×.），因此逐行收集
        # 以 "(N) ×/√" 开头的延续行并入答案，直到遇到解析行。
        # 与选择题选项提取互斥：先试 [A-Z]，再试 (N) ×/√ 序列。
        judge_parts = []
        judge_re = re.compile(r"^\(\d+\)\s*[×√]")
        stripped_first = (
            re.sub(r"^【?\d+】?[\s\.、]*", "", first_line)
            if prepared_analysis is None
            else first_line
        )
        if judge_re.match(stripped_first):
            first_line = stripped_first
            while first_line and judge_re.match(first_line):
                judge_parts.append(first_line.strip())
                lines = lines[1:]
                first_line = (lines[0].strip() if lines else "")
            option = " ".join(judge_parts).strip().rstrip(".").strip()
            # 跳过答案与解析之间的空行，定位到解析正文
            while lines and not lines[0].strip():
                lines = lines[1:]
            first_line = (lines[0].strip() if lines else "")
            first_line = re.sub(r"^【解析】\s*", "", first_line).strip()
        else:
            if prepared_analysis is None:
                first_line = re.sub(r"^【?\d+】?[\.、\s]*", "", first_line)
                first_line = re.sub(r"^【解析】\s*", "", first_line).strip()

    rebuilt_lines = [first_line] + [l.strip() for l in lines[1:] if l.strip()]

    extra_keywords = ["规律方法", "名师点拨", "敲黑板", "点悟", "链接教材", "易错警示", "避坑", "二级结论", "归纳总结", "多种解法", "思路导引", "巧思"]
    emoji_map = {
        "规律方法": "💡 规律方法",
        "名师点拨": "📌 名师点拨",
        "敲黑板": "🔔 敲黑板",
        "点悟": "💡 点悟",
        "链接教材": "🔗 链接教材",
        "易错警示": "⚠️ 易错警示",
        "避坑": "⚠️ 避坑",
        "二级结论": "📚 二级结论",
        "归纳总结": "📝 归纳总结",
        "多种解法": "🔀 多种解法",
        "思路导引": "🎯 思路导引",
        "巧思": "✨ 巧思",
    }

    blocks = []
    current_block = []
    current_type = "main"
    current_extra_kw = None

    for l in rebuilt_lines:
        matched_kw = next((kw for kw in extra_keywords if re.match(r"^" + re.escape(kw) + r"[\s：:]*", l)), None)
        if matched_kw:
            if current_block:
                blocks.append((current_type, current_extra_kw, "\n".join(current_block)))
                current_block = []
            current_type = "extra"
            current_extra_kw = matched_kw
            content = re.sub(r"^" + re.escape(matched_kw) + r"[\s：:]*", "", l).strip()
            if content:
                current_block.append(content)
        else:
            current_block.append(l)

    if current_block:
        blocks.append((current_type, current_extra_kw, "\n".join(current_block)))

    answer_value = reviewed_short_answer or option or explicit_nonchoice_answer or "详见解析"
    answer_value = re.sub(r"\s+", " ", answer_value).strip()
    main_text = blocks[0][2] if blocks and blocks[0][0] == "main" else ""
    raw_sub_items = re.split(r"\n(?=(?:对于\s*)?[①②③④⑤⑥⑦⑧⑨⑩])|(?<=[；;。])\s*(?=(?:对于\s*)?[①②③④⑤⑥⑦⑧⑨⑩])", main_text)
    conclusion_line = None
    resolution_lines: list[str] = []
    for sub in raw_sub_items:
        sub_str = sub.strip()
        if not sub_str:
            continue
        m_conc = re.search(r"(故选\s*[：:]?\s*[A-F]+\b.*)$", sub_str)
        if m_conc:
            conclusion = m_conc.group(1).strip()
            sub_str = sub_str[:m_conc.start()].strip()
            conclusion_line = re.sub(r"故选\s*[：:]?\s*([A-F]+)\b", r"故选 **\1**", conclusion)

        if re.match(r"^(?:对于\s*)?[①②③④⑤⑥⑦⑧⑨⑩]", sub_str):
            sub_str = re.sub(r"^(对于\s*[①②③④⑤⑥⑦⑧⑨⑩]|[①②③④⑤⑥⑦⑧⑨⑩])[\s：:]*", r"- **\1**：", sub_str)
            # ①② item block may itself contain continuation lines (e.g. a
            # trailing 故选 line merged into the last item) — quote every line.
            item_lines = sub_str.splitlines()
            resolution_lines.append(item_lines[0])
            for extra_line in item_lines[1:]:
                resolution_lines.append(extra_line)
        elif sub_str:
            sub_lines = sub_str.splitlines()
            resolution_lines.append(sub_lines[0])
            for extra_line in sub_lines[1:]:
                resolution_lines.append(extra_line)

    if conclusion_line:
        resolution_lines.extend(["", conclusion_line])

    for btype, kw, content in blocks:
        if btype == "extra" and content.strip():
            resolution_lines.extend(["", "---"])
            header = emoji_map.get(kw, f"💡 {kw}")
            resolution_lines.append(f"**{header}**")
            content_lines = content.strip().splitlines()
            resolution_lines.append(content_lines[0])
            for extra_line in content_lines[1:]:
                resolution_lines.append(extra_line)

    callout_lines = [
        f"> [!faq]- {callout_title}",
        ">",
        f"> > [!success]- **【答案】** {answer_value}",
        ">",
        "> > [!note]- **【分析】**",
    ]
    for line in analysis_text.splitlines() or ["本题未单列分析。"]:
        callout_lines.append(f"> > {line}" if line else "> >")
    callout_lines.extend([">", "> > [!note]- **【解析】**"])
    for line in resolution_lines or ["本题未单列解析。"]:
        callout_lines.append(f"> > {line}" if line else "> >")

    return "\n".join(callout_lines)


def apply_matches(profile_path: Path, manifest_path: Path, overwrite: bool) -> dict[str, Any]:
    profile = load_profile(profile_path)
    manifest = load_json(manifest_path)
    if manifest.get("status") != "passed":
        raise ConfigurationError("Answer match manifest must pass before application")
    graph_root = Path(profile["paths"]["graph_root"]).resolve()
    content_manifest_path = Path(
        manifest.get("content_manifest")
        or Path(profile["paths"]["staging_root"]) / "question-type-manifest.json"
    )
    content = load_json(content_manifest_path) if content_manifest_path.is_file() else {"questions": []}
    if manifest.get("content_manifest_sha256") and sha256_file(content_manifest_path) != manifest.get("content_manifest_sha256"):
        raise ConfigurationError("Content manifest changed after answer matching")
    all_questions = content.get("questions", [])
    external_questions = [
        question
        for question in all_questions
        if question.get("answer_handling", "external") == "external"
    ]
    output = Path(profile["paths"]["staging_root"]) / "answer-application-report.json"
    previous = load_json(output) if output.is_file() else {"questions": []}
    supplement_output = Path(profile["paths"]["staging_root"]) / "supplemental-solution-application-report.json"
    previous_supplement = load_json(supplement_output) if supplement_output.is_file() else {"questions": []}
    previously_owned = {
        str(Path(note).resolve())
        for item in previous.get("questions", [])
        for note in item.get("answer_notes", [])
        if note
    }
    previously_owned.update(
        str(Path(note).resolve())
        for item in previous_supplement.get("questions", [])
        for note in item.get("answer_notes", [])
        if note
    )
    desired_answer_paths: set[str] = set()
    desired_answer_paths.update(
        str(Path(question["answer_output"]).resolve())
        for question in all_questions
        if question.get("answer_handling") == "separate-authoritative"
        and question.get("answer_output")
    )
    removed_stale: list[str] = []
    if manifest.get("mode") == "unavailable":
        result = {
            "schema_version": 1,
            "stage": "answer-application",
            "status": "passed",
            "profile": profile["_profile_path"],
            "mode": "unavailable",
            "applied_count": 0,
            "questions": [],
            "removed_stale_outputs": [],
        }
    else:
        answer_markdown = Path(manifest["answer_markdown"])
        if sha256_file(answer_markdown) != manifest.get("answer_markdown_sha256"):
            raise ConfigurationError("Answer Markdown changed after matching")
        applied: list[dict[str, Any]] = []
        matches_by_question: dict[str, list[dict[str, Any]]] = {}
        for match in manifest.get("matches", []):
            matches_by_question.setdefault(match["question_path"], []).append(match)

        adapter_path = Path(manifest.get("adapter", profile["format"]["adapter"]))
        adapter_data = load_json(adapter_path) if adapter_path.is_file() else {}
        callout_title = adapter_data.get("answers", {}).get("callout_title", "答案与解析")
        choice_answer_overrides = {
            (
                str(item["context"]),
                str(item["number"]),
                int(item["start_line"]),
            ): str(item["answer"]).strip().upper()
            for item in adapter_data.get("answers", {}).get("choice_answer_overrides", [])
        }
        short_answer_overrides = {
            (
                str(item["context"]),
                str(item["number"]),
                int(item["start_line"]),
            ): str(item["answer"]).strip()
            for item in adapter_data.get("answers", {}).get("short_answer_overrides", [])
        }

        question_paths = [str(item["output"]) for item in external_questions]
        if not question_paths:
            question_paths = sorted(matches_by_question)
        for q_path_str in question_paths:
            q_matches = matches_by_question.get(q_path_str, [])
            note = Path(q_path_str).resolve()
            if not note.is_file():
                raise ConfigurationError(f"Atomic question note is missing: {note}")
            text = note.read_text(encoding="utf-8-sig")
            text = GENERATED_ANSWER_EMBED_RE.sub("", text).rstrip() + "\n"
            status = "matched" if q_matches else "unmatched"
            text = re.sub(r"(?m)^answer_status:\s*\S+", f"answer_status: {status}", text, count=1)
            q_basename = note.stem

            answers_dir = note.parent / "answers"
            if q_matches:
                answers_dir.mkdir(parents=True, exist_ok=True)

            embed_links: list[str] = []
            answer_note_records: list[dict[str, Any]] = []
            for i, match in enumerate(q_matches, 1):
                ans_name = f"{q_basename}A{i}"
                ans_path = answers_dir / f"{ans_name}.md"

                rebased_body = rebase_local_links(
                    match["answer_body"],
                    answer_markdown,
                    ans_path,
                    [(answer_markdown.parent / "images", Path(profile["paths"]["graph_root"]) / "images")],
                )

                reviewed_choice_answer = choice_answer_overrides.get(
                    (
                        str(match.get("answer_context")),
                        str(match.get("answer_number")),
                        int(match.get("answer_start_line")),
                    )
                )
                reviewed_short_answer = short_answer_overrides.get(
                    (
                        str(match.get("answer_context")),
                        str(match.get("answer_number")),
                        int(match.get("answer_start_line")),
                    )
                )
                callout_text = format_answer_callout(
                    rebased_body,
                    callout_title=callout_title,
                    reviewed_choice_answer=reviewed_choice_answer,
                    reviewed_short_answer=reviewed_short_answer,
                )
                answer_text = "\n".join(
                    [
                        "---",
                        f"answer_for: {json.dumps(q_basename)}",
                        "answer_provenance: authoritative",
                        f"answer_source_body_sha256: {match['answer_body_sha256']}",
                        "---",
                        callout_text,
                        "",
                    ]
                )
                write_text_atomic(ans_path, answer_text, overwrite=True)
                embed_links.append(f"![[{ans_name}]]")
                match["answer_note_path"] = str(ans_path)
                match["answer_name"] = ans_name
                desired_answer_paths.add(str(ans_path.resolve()))
                answer_note_records.append(
                    {
                        "path": str(ans_path.resolve()),
                        "sha256": sha256_file(ans_path),
                        "lexical_signature": lexical_signature(answer_text),
                        "provenance": "authoritative",
                        "source_body_sha256": match["answer_body_sha256"],
                    }
                )

            for embed_link in embed_links:
                text = text.rstrip() + "\n\n" + embed_link + "\n"

            write_text_atomic(note, text, overwrite=True)
            applied.append({
                "question_id": q_matches[0]["question_id"] if q_matches else next(
                    (item["id"] for item in all_questions if Path(item["output"]).resolve() == note),
                    q_basename,
                ),
                "path": str(note),
                "answer_notes": [m.get("answer_note_path") for m in q_matches],
                "answer_note_records": answer_note_records,
                "answer_status": status,
                "note_sha256": sha256_file(note),
            })

        stale_candidates = set(previously_owned)
        if graph_root.is_dir():
            stale_candidates.update(
                str(path.resolve())
                for path in graph_root.rglob("Q[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]A[0-9]*.md")
                if path.parent.name == "answers"
                and "answer_provenance: authoritative" in path.read_text(encoding="utf-8-sig")
            )
        for stale_name in sorted(stale_candidates - desired_answer_paths):
            stale = Path(stale_name).resolve()
            try:
                stale.relative_to(graph_root)
            except ValueError as exc:
                raise ConfigurationError(f"Refusing to prune answer outside graph root: {stale}") from exc
            if stale.is_file():
                stale.unlink()
                removed_stale.append(str(stale))
        result = {
            "schema_version": 1,
            "stage": "answer-application",
            "status": "passed",
            "profile": profile["_profile_path"],
            "mode": manifest.get("mode"),
            "applied_count": sum(1 for item in applied if item["answer_status"] == "matched"),
            "questions": applied,
            "removed_stale_outputs": removed_stale,
        }
    result["removed_empty_directories"] = prune_empty_directories(graph_root)
    write_json_atomic(output, result, overwrite=output.is_file() or overwrite)
    if supplement_output.is_file():
        write_json_atomic(
            supplement_output,
            {
                "schema_version": 1,
                "stage": "supplemental-solution-application",
                "status": "invalidated",
                "profile": profile["_profile_path"],
                "questions": [],
                "message": "Invalidated because authoritative answer application was rebuilt",
            },
            overwrite=True,
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or apply authoritative answer matches without fuzzy auto-acceptance.")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("profile", type=Path)
    plan.add_argument("adapter", type=Path)
    plan.add_argument("content_manifest", type=Path)
    plan.add_argument("output", type=Path)
    plan.add_argument("--overwrite", action="store_true")
    apply = sub.add_parser("apply")
    apply.add_argument("profile", type=Path)
    apply.add_argument("manifest", type=Path)
    apply.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            result = plan_matches(args.profile, args.adapter, args.content_manifest)
            write_json_atomic(args.output, result, overwrite=args.overwrite)
        else:
            result = apply_matches(args.profile, args.manifest, args.overwrite)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"schema_version": 1, "stage": "answer-matching", "status": "failed", "error_type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
