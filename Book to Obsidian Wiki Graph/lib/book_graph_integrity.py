"""Shared content evidence. Presentation may change; words and mathematics may not."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ALGORITHM = "book-content-v1"
LINK = re.compile(r"(?<!!)\[([^\]\n]*)\]\(((?:[^()\n]|\([^()\n]*\))*)\)")
MATH_OR_CODE = re.compile(r"```.*?```|~~~.*?~~~|\$\$.*?\$\$|(?<![\\$])\$(?!\$).*?(?<!\\)\$|`[^`\n]+`", re.S)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)(.*)\Z", text, re.S)
    if not match:
        raise ValueError("unterminated YAML frontmatter")
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("Install book agent requirements.txt (PyYAML is required)") from exc

    class UniqueLoader(yaml.SafeLoader):
        pass

    def mapping(loader, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in result:
                raise ValueError(f"duplicate YAML key: {key}")
            result[key] = loader.construct_object(value_node, deep=deep)
        return result

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    metadata = yaml.load(match.group(1), Loader=UniqueLoader)
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict) or any(not isinstance(k, str) for k in metadata):
        raise ValueError("frontmatter must be a mapping with string keys")
    return metadata, match.group(2)


def content_tokens(text: str) -> list[str]:
    """Ignore approved Markdown wrappers, retaining ordered prose, table cells and TeX.

    Destinations are audited separately. Math/code contents stay literal, including
    spaces inside TeX text commands. No OCR digit repair or punctuation deletion.
    """
    _, text = parse_frontmatter(text)
    lines = []
    verbatim = None
    quote_prefix = ""
    for line in text.splitlines():
        if verbatim:
            if quote_prefix and line.startswith(quote_prefix):
                line = line[len(quote_prefix):]
            elif quote_prefix and line.rstrip() == quote_prefix.rstrip():
                line = ""
            lines.append(line)
            if (verbatim in {"```", "~~~"} and line.lstrip().startswith(verbatim)) or (verbatim == "$$" and line.count("$$") % 2):
                verbatim = None
            continue
        raw = line
        while line.startswith("> "):
            line = line[2:]
        if line == ">":
            line = ""
        quote_prefix = raw[:len(raw) - len(line)]
        # These exact running-header/ornament forms are the formatter's
        # documented presentation-only removals, never arbitrary paragraphs.
        if re.fullmatch(r"#{4,6}\s+(?:人民教育出版社|[●•·\s]+)", line):
            continue
        if quote_prefix and re.fullmatch(r"(?:#{4,6}\s+)?[●•·\s]+", line):
            continue
        if re.fullmatch(r"\s*(?:\d{1,3}\s*)?第[一二三四五六七八九十]+章\s+[^。！？!?；;：:\[\]()（）]{1,40}\s*", line):
            continue
        line = re.sub(r"^\[![^\]]+\][+-]?\s*", "", line)
        line = re.sub(r"^#{1,6}\s+", "", line)
        lines.append(line)
        if line.startswith(("```", "~~~")):
            verbatim = line[:3]
        elif line.count("$$") % 2:
            verbatim = "$$"
    text = "\n".join(lines)
    tokens = []
    end = 0

    def prose(value):
        value = LINK.sub(lambda m: m.group(1), value)
        value = value.replace("**", "")
        # Reasoning labels move from prose to a callout title (colon omitted).
        value = re.sub(r"(分析|思路|点拨|解答|解析|证明|解)\s*[：:]", r"\1 ", value)
        return re.findall(r"\w+|[^\w\s]", value)

    for match in MATH_OR_CODE.finditer(text):
        tokens.extend(prose(text[end:match.start()]))
        tokens.append(match.group(0))
        end = match.end()
    tokens.extend(prose(text[end:]))
    return tokens


def content_sha256(text: str) -> str:
    return hashlib.sha256(json.dumps(content_tokens(text), ensure_ascii=False).encode()).hexdigest()


def link_destinations(text: str) -> list[str]:
    _, body = parse_frontmatter(text)
    body = MATH_OR_CODE.sub("", body)
    return [match.group(2) for match in LINK.finditer(body)]


def reviewed_content_changes(reports: list[Path], profile: Path | None, source_hash: str | None) -> dict:
    changes: dict[str, list[dict]] = {}
    for path in reports:
        report = json.loads(path.read_text(encoding="utf-8"))
        recipe = Path(report["repairs"])
        if (report.get("status") != "passed" or report.get("reviewer_confirmed") is not True
                or profile is None or Path(report["profile"]).resolve() != profile.resolve()
                or report.get("source_sha256") != source_hash or sha256_file(recipe) != report.get("repairs_sha256")):
            raise ValueError("reviewed repair report identity or recipe hash mismatch")
        decisions = json.loads(recipe.read_text(encoding="utf-8"))
        if (decisions.get("reviewer_confirmed") is not True or len(decisions.get("repairs", [])) != len(report["files"])
                or decisions.get("profile") != report["profile"] or decisions.get("source_sha256") != source_hash):
            raise ValueError("repair decisions are not confirmed or complete")
        for decision, result in zip(decisions["repairs"], report["files"]):
            if (decision["path"] != result["path"] or decision.get("before_sha256") != result.get("before_sha256")
                    or not decision.get("evidence") or not decision.get("reason")):
                raise ValueError("repair result does not match its reviewed decision")
            changes.setdefault(result["path"], []).append(result)
    return changes


def expected_content_hash(original: str, target: str, changes: dict) -> str:
    expected = original
    for item in changes.get(target, []):
        if item.get("before_content_sha256") != expected:
            raise ValueError(f"reviewed content repair chain is broken: {target}")
        expected = item["after_content_sha256"]
    return expected


def corpus_snapshot(root: Path) -> dict:
    files = {p.relative_to(root).as_posix(): sha256_file(p)
             for p in sorted(root.rglob("*")) if p.is_file()}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {"root": str(root.resolve()), "sha256": digest, "files": files}


def owned_ranges(start: int, end: int, children: list[tuple[int, int]], excluded: set[int]) -> list[list[int]]:
    moved = set(excluded)
    for left, right in children:
        moved.update(range(left, right + 1))
    result = []
    for line in range(start, end + 1):
        if line in moved:
            continue
        if result and result[-1][1] + 1 == line:
            result[-1][1] = line
        else:
            result.append([line, line])
    return result
