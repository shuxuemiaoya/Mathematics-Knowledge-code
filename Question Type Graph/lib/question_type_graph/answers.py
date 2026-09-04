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

    deduped_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for ans in answers:
        key = (str(ans.get("context")), str(ans.get("number")))
        if key in deduped_by_key:
            prev = deduped_by_key[key]
            prev_has_res = bool(re.search(r"【(?:解析|详解|分析|解答|解法)】|(?<!见)(?:解析|详解)\s*[：:]|故选", prev.get("body", "")))
            curr_has_res = bool(re.search(r"【(?:解析|详解|分析|解答|解法)】|(?<!见)(?:解析|详解)\s*[：:]|故选", ans.get("body", "")))
            if curr_has_res and not prev_has_res:
                deduped_by_key[key] = ans
            elif prev_has_res and not curr_has_res:
                pass
            elif len(ans.get("body", "").strip()) >= len(prev.get("body", "").strip()):
                deduped_by_key[key] = ans
        else:
            deduped_by_key[key] = ans
    answers = list(deduped_by_key.values())


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
        "hierarchy_normalized_number": {},
        "number": {},
        "evidence": {},
        "evidence_number": {},
        "normalized_evidence": {},
    }
    for answer in answers:
        number = str(answer.get("number"))
        context = str(answer.get("context"))
        indexes["hierarchy_number"].setdefault((context, number), []).append(answer)
        normalized_number = re.sub(r"\s+", "", number)
        indexes["hierarchy_normalized_number"].setdefault(
            (context, normalized_number), []
        ).append(answer)
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
    elif name == "hierarchy-number-normalized":
        normalized_number = re.sub(r"\s+", "", str(question.get("number")))
        values = list(
            indexes["hierarchy_normalized_number"].get(
                (str(question.get("context_key")), normalized_number), []
            )
        )
    elif name == "number-global":
        # Opt-in for reviewed books whose question series is continuous across
        # chapters but whose answer appendix omits chapter boundaries. Duplicate
        # numbers deliberately remain multiple candidates and therefore require
        # review instead of being silently selected.
        values = list(indexes["number"].get(str(question.get("number")), []))
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
    m_conc = re.search(r"(?:故选|选|因此选|故选：|选：)\s*([A-D]+)\b|(?:故|则)?\s*([A-D])\s*项正确", body)
    if m_conc:
        return (m_conc.group(1) or m_conc.group(2)).upper()

    conclusion_pattern = re.compile(
        r"(?:故\s*选|应\s*选|选|选项(?:为|是|有)?|答案(?:为|是)?|也就是|即)\s*[：:]?\s*([A-F]+)\b|\b([A-F])\s*选项\b",
        re.IGNORECASE,
    )
    matches = list(conclusion_pattern.finditer(body))
    if matches:
        val = matches[-1].group(1) or matches[-1].group(2)
        if val:
            return val.upper()

    lines = body.strip().splitlines()
    if lines:
        first_line = lines[0].strip()
        header = re.match(
            r"^(?:#{1,6}\s*)?【?\d+】?[\.、\s]*([A-F]{1,4})\b\s*(?:【?(?:解析|详解)】?)?\s*",
            first_line,
        )
        if header:
            return header.group(1).upper()
    return None


def extract_nonchoice_answer_prefix(body: str) -> tuple[str | None, str]:
    """Split a publisher-stated short answer from the following analysis."""
    text = re.sub(r"^【?\d+】?[\.、\s]*", "", body.strip(), count=1)
    marker = re.search(r"【(?:解析|详解|分析|思路导航|解答|解法|证法|证明)】|(?<!见)(?:解析|详解)\s*[：:]", text)
    if marker is None:
        return None, text
    prefix = text[:marker.start()].strip()
    analysis = text[marker.start():].strip()
    analysis = re.sub(
        r"^\s*(?:【(?:解析|详解|分析|思路导航|解答|解法|证法|证明)】|(?:解析|详解)\s*[：:])\s*",
        "",
        analysis,
    ).strip()
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


def extract_composite_short_answer(body: str) -> str | None:
    """Summarize ordered explicit headers from an interleaved solution."""
    answers: list[str] = []
    pattern = re.compile(
        r"^\s*(?:\d+[.．、]\s*)?答案[.．、：:\s]*?(.*?)\s+(?:解析|详解)\b"
    )
    for line in body.splitlines():
        match = pattern.match(line)
        if match is None:
            continue
        value = re.sub(r"\s+", " ", match.group(1)).strip()
        if value:
            answers.append(value)
    if not answers:
        return None
    return "；".join(
        f"({index}) {value}" for index, value in enumerate(answers, start=1)
    )


def format_answer_callout(
    body: str,
    callout_title: str = "答案与解析",
    reviewed_choice_answer: str | None = None,
    reviewed_short_answer: str | None = None,
    question_body: str = "",
) -> str:
    source_body = body.strip()
    scan_body = (question_body + "\n" + source_body) if question_body else source_body

    # 1. Extract Answer Value
    answer_value = None
    if reviewed_short_answer:
        answer_value = reviewed_short_answer
    elif reviewed_choice_answer:
        answer_value = reviewed_choice_answer

    # Check leading 【正确答案】 or 【答案】
    if not answer_value and re.match(r"^\s*(?:#{1,6}\s*)?【(?:正确答案|答案)】", source_body):
        m_head = re.match(
            r"^\s*(?:#{1,6}\s*)?【(?:正确答案|答案)】\s*(.*?)(?=(?:\n\s*)*【(?:解析|详解|分析|思路导航|解答|解法|证法|证明|提示)】|(?:\n\s*)*(?<!见)(?:解析|详解)\s*[：:]|【(?:更多习题信息|智慧中小学)|$)",
            source_body,
            flags=re.DOTALL,
        )
        if m_head:
            val = m_head.group(1).strip()
            val = re.split(r"【", val)[0].strip()
            if val:
                answer_value = val
                source_body = source_body[m_head.end():].strip()
                source_body = re.sub(r"^\s*【(?:解析|详解|解答|解法)】\s*(?=(?:#{1,6}\s*)?【(?:分析|思路导航)】)", "", source_body).strip()

    # 2. Split out 分析 if present
    analysis_text = None
    resolution_body = source_body
    analysis_match = re.search(
        r"(?m)^\s*(?:#{1,6}\s*)?(?:【(?:分析|思路导航)】|(?:分析|思路导航)(?:\s|[：:]|▶|$))",
        source_body,
    )
    if analysis_match is not None:
        resolution_match = re.search(
            r"(?m)^\s*(?:#{1,6}\s*)?(?:【(?:解析|详解|解答|解法)】|(?:解析|详解|解答|解法)(?:\s|[：:]|▶|$))",
            source_body[analysis_match.end():],
        )
        if resolution_match is not None:
            resolution_start = analysis_match.end() + resolution_match.start()
            raw_analysis = source_body[analysis_match.start():resolution_start].strip()
            analysis_text = re.sub(r"^\s*(?:#{1,6}\s*)?(?:【(?:分析|思路导航)】|(?:分析|思路导航)\s*[：:]?)\s*", "", raw_analysis).strip()
            resolution_body = source_body[resolution_start:].strip()
        else:
            lines = [l for l in source_body[analysis_match.start():].splitlines() if l.strip()]
            if len(lines) > 1:
                raw_analysis = lines[0].strip()
                analysis_text = re.sub(r"^\s*(?:#{1,6}\s*)?(?:【(?:分析|思路导航)】|(?:分析|思路导航)\s*[：:]?)\s*", "", raw_analysis).strip()
                resolution_body = "\n".join(lines[1:]).strip()
            else:
                raw_analysis = source_body[analysis_match.start():].strip()
                analysis_text = re.sub(r"^\s*(?:#{1,6}\s*)?(?:【(?:分析|思路导航)】|(?:分析|思路导航)\s*[：:]?)\s*", "", raw_analysis).strip()
                resolution_body = "本题未单列解析。"

    # Check 故选: A / 选 C / 项正确 (authoritative conclusion wins over damaged header)
    if not answer_value:
        m_choice = re.search(r"(?:故选|选|因此选|故选：|选：)\s*([A-D]+)\b|(?:故|则)?\s*([A-D])\s*项正确", resolution_body or source_body)
        if m_choice:
            answer_value = (m_choice.group(1) or m_choice.group(2)).strip().upper()

    # Check leading 【正确答案】 or 【答案】 in resolution_body
    if not answer_value and re.search(r"^\s*(?:#{1,6}\s*)?【(?:正确答案|答案)】", resolution_body):
        m_head = re.search(
            r"^\s*(?:#{1,6}\s*)?【(?:正确答案|答案)】\s*(.*?)(?=\n|【(?:更多习题信息|智慧中小学|解析|详解|分析|思路导航|解答|解法|证法|证明|提示)】|(?<!见)(?:解析|详解)\s*[：:]|$)",
            resolution_body,
            flags=re.DOTALL,
        )
        if m_head:
            val = m_head.group(1).strip()
            val = re.split(r"【", val)[0].strip()
            if val and "\n" not in val and len(val) <= 100:
                answer_value = val
                resolution_body = resolution_body[m_head.end():].strip()

    # Check leading option header (e.g. 1. D, 7. AC, 7. ABD)
    if not answer_value:
        m_opt_head = re.search(r"^\s*(?:#{1,6}\s*)?(?:[1-9]\d?[.．、]\s*)?([A-D]{1,4})(?:\s*[【\n\s]|$)", source_body)
        if m_opt_head:
            val = m_opt_head.group(1).strip()
            # Ensure it is not a Roman numeral or accidental word
            if val and all(c in "ABCD" for c in val):
                answer_value = val

    # Check trailing or standalone 答案：...
    if not answer_value:
        m_ans_line = re.search(r"(?m)^\s*(?:【答案】|答案\s*[：:])\s*(\S.*?)\s*$", resolution_body)
        if m_ans_line:
            answer_value = m_ans_line.group(1).strip()
            resolution_body = resolution_body[:m_ans_line.start()] + "\n" + resolution_body[m_ans_line.end():]

    # Check leading number option header (e.g. 1. D or 2. AC or 3. B解法1：)
    if not answer_value:
        m_lead = re.search(r"^\s*(?:#{1,6}\s*)?(?:(?:[1-9]\d?|例\s*\d+|变式(?:题)?\s*\d*)[.．、\s]*)?([A-D]{1,4})(?:\s*[【\n\s解法解析详解分析]|$)", resolution_body)
        if m_lead:
            val = m_lead.group(1).strip().upper()
            if val and all(c in "ABCD" for c in val):
                answer_value = val

    # Check option interval / formula matching for multiple choice
    if not answer_value and re.search(r"[A-D][.．、\s]", scan_body):
        clean_res = re.split(r"【(?:反思|总结|规律总结|方法总结|名师点睛|点睛|考点|易错警示)】", resolution_body)[0]
        clean_res = re.sub(r"!\[.*?\]\(.*?\)", "", clean_res)
        clean_res = re.sub(r"(?m)^\s*(?:#{1,6}\s*)?(?:注[：:].*|一数[·\s]*必刷\d*讲|第\d+讲.*|强化训练|对点训练|类型\s*[IVXLCDM一二三四五六七八九十\d].*)\s*$", "", clean_res).strip()
        sentences = re.split(r"[。！？\n]+", clean_res.strip())
        final_sentence = ""
        for s in reversed(sentences):
            if s.strip() and len(s.strip()) >= 3 and not s.strip().startswith("!"):
                final_sentence = s.strip()
                break
        if not final_sentence:
            final_sentence = clean_res[-100:]
        
        opts = {}
        for opt in ["A", "B", "C", "D"]:
            m_opt = re.search(r"(?:^|\s)" + opt + r"[.．、]\s*(.*?)(?=(?:[B-D][.．、]|$|\n\n))", scan_body, flags=re.DOTALL)
            if m_opt:
                opts[opt] = m_opt.group(1).strip()
        
        # Priority 0: Circled numerals reasoning (e.g. ①④)
        correct_circled = "".join(item for item in ["①", "②", "③", "④", "⑤"] if re.search(item + r"(?:项|个)?正确", resolution_body))
        if correct_circled:
            for opt, val in opts.items():
                if val == correct_circled:
                    answer_value = opt
                    break

        # Priority 1: Exact equation match (e.g. = -32, 为 -32, 是 -32, = 0)
        if not answer_value:
            best_pos = -1
            for opt, val in opts.items():
                for m in re.finditer(r"(?:=|为|是|选)\s*[\$]*" + re.escape(val) + r"[\$]*(?:\b|[\$ \t\n\.\,\，\。：:]|$)", final_sentence):
                    if m.end() > best_pos:
                        best_pos = m.end()
                        answer_value = opt

        # Priority 2: Semantic and number matches
        if not answer_value:
            for opt, val in opts.items():
                clean_val = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]+", "", val)
                if len(clean_val) >= 2 and clean_val in re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]+", "", final_sentence):
                    answer_value = opt
                    break
                nums = re.findall(r"-?\d+", val)
                if len(nums) >= 2 and all(re.search(r"(?<!\d)" + re.escape(n) + r"(?!\d)", final_sentence) for n in nums):
                    answer_value = opt
                    break
                elif len(nums) == 1 and nums[0] not in {"0", "1"} and re.search(r"(?<![-\d])" + re.escape(nums[0]) + r"(?!\d)", final_sentence):
                    answer_value = opt
                    break

    # Check 故答案为：... / 所以答案为：...
    if not answer_value:
        conc_ans = re.search(r"(?m)(?:故|所以|因此|则)?\s*答案为\s*[：:]?\s*(\S.*?)(?:[。.]|\s*$)", resolution_body)
        if conc_ans:
            answer_value = conc_ans.group(1).strip()

    # Check 故选 / 应选
    if not answer_value:
        m_opt = re.search(r"(?:故\s*选|应\s*选|选|选项(?:为|是|有)?|答案(?:为|是)?|也就是|即)\s*[：:]?\s*([A-F]+)\b|\b([A-F])\s*选项\b", resolution_body, re.IGNORECASE)
        if m_opt:
            answer_value = (m_opt.group(1) or m_opt.group(2)).upper()
        else:
            # check non-choice short answer prefix
            marker = re.search(r"【(?:解析|详解|分析|思路导航|解答|解法|证法|证明)】|(?<!见)(?:解析|详解)\s*[：:]", resolution_body)
            if marker:
                prefix = re.sub(r"^【?\d+】?[\.、\s]*", "", resolution_body[:marker.start()]).strip()
                prefix = re.sub(r"^(?:【答案】|答案\s*[：:])\s*", "", prefix).strip()
                if prefix and len(prefix) <= 400 and not re.match(r"^\(\d+\)\s*[×√]", prefix):
                    answer_value = prefix
                    resolution_body = resolution_body[marker.start():].strip()

    if not answer_value:
        answer_value = "详见解析"

    answer_value = re.sub(r"\s+", " ", answer_value).strip()

    # Clean leading headers from resolution_body
    resolution_body = re.sub(r"^\s*【?\d+】?[\.、\s]*", "", resolution_body.strip())
    resolution_body = re.sub(r"^\s*【(?:解析|详解|解答|解法)】\s*", "", resolution_body).strip()
    resolution_body = re.sub(r"^\s*(?:解析|详解|解答)\s*[：:]\s*", "解析：", resolution_body)

    # 3. Identify and split sub-callouts: 【反思】, 【总结】, 【规律方法】, 【名师点睛】, etc.
    callout_tag_patterns = [
        ("tip", r"【?(?:反思|教学反思)】", "【反思】"),
        ("tip", r"【?(?:总结|规律总结|归纳总结)】", "【总结】"),
        ("tip", r"【?(?:规律方法|方法技巧|方法总结)】", "【规律方法】"),
        ("tip", r"【?(?:名师点睛|点睛|名师点拨|点拨)】", "【名师点睛】"),
        ("tip", r"【?(?:点悟|敲黑板)】", "【点悟】"),
        ("warning", r"【?(?:易错警示|避坑|易错点)】", "【易错警示】"),
        ("tip", r"【?(?:二级结论|核心结论)】", "【二级结论】"),
        ("tip", r"【?(?:多种解法|另解|其他解法)】", "【多种解法】"),
        ("note", r"【?(?:考点|相关考点)】", "【考点】"),
        ("note", r"【?(?:链接教材|教材链接)】", "【链接教材】"),
    ]

    tag_regex = r"(?m)^\s*(?:#{1,6}\s*)?(" + "|".join(p[1] for p in callout_tag_patterns) + r")[\s：:]*"
    split_indices = [m.start() for m in re.finditer(tag_regex, resolution_body)]

    sub_callouts = []
    if split_indices:
        main_res = resolution_body[:split_indices[0]].strip()
        for i, start_idx in enumerate(split_indices):
            end_idx = split_indices[i+1] if i+1 < len(split_indices) else len(resolution_body)
            chunk = resolution_body[start_idx:end_idx].strip()
            for c_type, pat, standard_title in callout_tag_patterns:
                m_tag = re.match(r"^\s*(?:#{1,6}\s*)?" + pat + r"[\s：:]*", chunk)
                if m_tag:
                    content = chunk[m_tag.end():].strip()
                    sub_callouts.append((c_type, standard_title, content))
                    break
    else:
        main_res = resolution_body.strip()

    # Clean ①② sub items in main resolution
    raw_sub_items = re.split(r"\n(?=(?:对于\s*)?[①②③④⑤⑥⑦⑧⑨⑩])|(?<=[；;。])\s*(?=(?:对于\s*)?[①②③④⑤⑥⑦⑧⑨⑩])", main_res)
    resolution_lines = []
    conclusion_line = None
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

    # Build output
    callout_lines = [
        f"> [!faq]- {callout_title}",
        ">",
        f"> > [!success]- **【答案】** {answer_value}",
    ]
    if analysis_text and analysis_text.strip():
        callout_lines.extend([
            ">",
            "> > [!note]- **【分析】**",
        ])
        for line in analysis_text.splitlines():
            callout_lines.append(f"> > {line}" if line else "> >")
    callout_lines.extend([">", "> > [!note]- **【解析】**"])
    for line in resolution_lines or ["本题未单列解析。"]:
        callout_lines.append(f"> > {line}" if line else "> >")

    # Append sub callouts (反思, 总结, 规律方法, etc.)
    for c_type, c_title, c_content in sub_callouts:
        if c_content.strip():
            callout_lines.extend([">", f"> > [!{c_type}]- **{c_title}**"])
            raw_c_items = re.split(r"\n(?=(?:对于\s*)?[①②③④⑤⑥⑦⑧⑨⑩])|(?<=[；;。])\s*(?=(?:对于\s*)?[①②③④⑤⑥⑦⑧⑨⑩])", c_content)
            for sub_c in raw_c_items:
                sub_c_str = sub_c.strip()
                if not sub_c_str:
                    continue
                if re.match(r"^(?:对于\s*)?[①②③④⑤⑥⑦⑧⑨⑩]", sub_c_str):
                    sub_c_str = re.sub(r"^(对于\s*[①②③④⑤⑥⑦⑧⑨⑩]|[①②③④⑤⑥⑦⑧⑨⑩])[\s：:]*", r"- **\1**：", sub_c_str)
                for line in sub_c_str.splitlines():
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
        choice_answer_overrides_by_key = {
            (
                str(item["context"]),
                str(item["number"]),
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
        short_answer_overrides_by_key = {
            (
                str(item["context"]),
                str(item["number"]),
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
                ) or choice_answer_overrides_by_key.get(
                    (
                        str(match.get("answer_context")),
                        str(match.get("answer_number")),
                    )
                )
                reviewed_short_answer = short_answer_overrides.get(
                    (
                        str(match.get("answer_context")),
                        str(match.get("answer_number")),
                        int(match.get("answer_start_line")),
                    )
                ) or short_answer_overrides_by_key.get(
                    (
                        str(match.get("answer_context")),
                        str(match.get("answer_number")),
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
