from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, unquote


class GraphError(RuntimeError):
    """Base error for deterministic pipeline failures."""


class ConfigurationError(GraphError):
    """Raised when a frozen interface is missing or inconsistent."""


class ReviewRequired(GraphError):
    """Raised when a semantic choice has not been reviewed."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ConfigurationError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError(f"JSON root must be an object: {path}")
    return value


def write_text_atomic(path: Path, text: str, overwrite: bool = False) -> None:
    path = path.resolve()
    if path.exists() and not overwrite:
        raise ConfigurationError(f"Output exists; explicit overwrite required: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def write_json_atomic(path: Path, value: dict[str, Any], overwrite: bool = False) -> None:
    write_text_atomic(
        path,
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        overwrite=overwrite,
    )


def pdf_page_count(path: Path) -> int:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise ConfigurationError("pypdf is required for PDF inputs") from exc
    try:
        count = len(PdfReader(str(path)).pages)
    except Exception as exc:
        raise ConfigurationError(f"Cannot inspect PDF {path}: {exc}") from exc
    if count < 1:
        raise ConfigurationError(f"PDF has no pages: {path}")
    return count


def resolve_inside(root: Path, relative: str | Path) -> Path:
    root = root.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ConfigurationError(f"Path escapes root {root}: {relative}") from exc
    return candidate


def safe_name(value: str, fallback: str = "node") -> str:
    """Normalize one generated path component to the vault filename policy.

    Generated titles may contain only Unicode letters, Unicode digits, and
    underscores.  A conventional alphanumeric file suffix is preserved so
    that Markdown, JSON, Canvas, and image artifacts remain usable.
    """

    def split_suffix(raw: str) -> tuple[str, str]:
        suffix = Path(raw).suffix
        if suffix and re.fullmatch(r"\.[A-Za-z0-9]{1,10}", suffix):
            return raw[: -len(suffix)], suffix
        return raw, ""

    def normalize_stem(raw: str) -> str:
        return "".join(character if character == "_" or character.isalnum() else "_" for character in raw)

    stem, suffix = split_suffix(str(value))
    normalized = normalize_stem(stem)
    if not normalized.strip("_"):
        fallback_stem, fallback_suffix = split_suffix(str(fallback))
        normalized = normalize_stem(fallback_stem).strip("_") or "node"
        if not suffix:
            suffix = fallback_suffix
    budget = max(1, 120 - len(suffix))
    return f"{normalized[:budget]}{suffix}"


def prune_empty_directories(root: Path) -> list[str]:
    """Remove empty generated directories below ``root`` without deleting files."""
    root = root.resolve()
    if not root.is_dir():
        return []
    removed: list[str] = []
    directories = sorted(
        (path for path in root.rglob("*") if path.is_dir() and not path.is_symlink()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        try:
            directory.rmdir()
        except OSError:
            continue
        removed.append(str(directory.resolve()))
    return removed


def bounded_output_path(root: Path, desired: Path, max_length: int, identity: str) -> Path:
    """Keep generated paths inside the graph and below a conservative Windows budget."""
    root = root.resolve()
    desired = desired.resolve()
    try:
        desired.relative_to(root)
    except ValueError as exc:
        raise ConfigurationError("Generated output escaped graph root") from exc
    if max_length < 160 or max_length > 320:
        raise ConfigurationError("content.max_path_length must be between 160 and 320")
    if len(str(desired)) <= max_length:
        return desired
    suffix = desired.suffix or ".md"
    digest = sha256_text(f"{identity}\n{desired}")[:16]
    compact = (root / "_compact" / f"{digest}{suffix}").resolve()
    if len(str(compact)) > max_length:
        raise ConfigurationError(f"Graph root leaves no safe output-path budget: {root}")
    return compact


def markdown_target(from_note: Path, to_note: Path) -> str:
    relative = os.path.relpath(to_note, from_note.parent).replace("\\", "/")
    return quote(relative, safe="/%._-~")


def markdown_link(label: str, from_note: Path, to_note: Path) -> str:
    return f"[{label}]({markdown_target(from_note, to_note)})"


def obsidian_target(to_note: Path, vault_root: Path) -> str:
    target = to_note.resolve()
    root = vault_root.resolve()
    try:
        return target.relative_to(root).as_posix()
    except ValueError as exc:
        raise ConfigurationError(f"Obsidian embed target is outside the vault: {target}") from exc


def obsidian_embed(to_note: Path, vault_root: Path) -> str:
    return f"![[{obsidian_target(to_note, vault_root)}]]"


MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
IMAGE_LINK_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
OBSIDIAN_EMBED_RE = re.compile(r"!\[\[([^\]]+)\]\]")
ALL_MARKDOWN_LINK_RE = re.compile(r"(!?\[[^\]]*\]\()([^)]+)(\))")
HTML_IMAGE_RE = re.compile(r"(<img\b[^>]*?\bsrc=[\"'])([^\"']+)([\"'])", re.IGNORECASE)


def rebase_local_links(
    text: str,
    from_note: Path,
    to_note: Path,
    relocations: list[tuple[Path, Path]] | None = None,
) -> str:
    """Keep local link identity while making it resolve from a moved note."""
    roots = [(source.resolve(), target.resolve()) for source, target in (relocations or [])]

    def destination(value: str) -> str | None:
        clean = value.strip().strip("<>")
        if not clean or clean.startswith(("http://", "https://", "data:", "#")):
            return None
        anchor = ""
        if "#" in clean:
            clean, fragment = clean.split("#", 1)
            anchor = f"#{fragment}"
        target = (from_note.parent / unquote(clean)).resolve()
        for source_root, target_root in roots:
            try:
                relative = target.relative_to(source_root)
            except ValueError:
                continue
            target = target_root / relative
            break
        if not target.exists():
            return None
        return f"{markdown_target(to_note, target)}{anchor}"

    def replace_markdown(match: re.Match[str]) -> str:
        rewritten = destination(match.group(2))
        return match.group(0) if rewritten is None else f"{match.group(1)}{rewritten}{match.group(3)}"

    def replace_html(match: re.Match[str]) -> str:
        rewritten = destination(match.group(2))
        return match.group(0) if rewritten is None else f"{match.group(1)}{rewritten}{match.group(3)}"

    return HTML_IMAGE_RE.sub(replace_html, ALL_MARKDOWN_LINK_RE.sub(replace_markdown, text))


def local_markdown_destinations(text: str) -> Iterable[str]:
    for pattern in (MARKDOWN_LINK_RE, IMAGE_LINK_RE):
        for match in pattern.finditer(text):
            value = match.group(1).strip().strip("<>")
            if not value or value.startswith(("http://", "https://", "#", "data:")):
                continue
            yield unquote(value.split("#", 1)[0])


def obsidian_embed_destinations(text: str) -> Iterable[str]:
    for match in OBSIDIAN_EMBED_RE.finditer(text):
        value = match.group(1).strip()
        if not value:
            continue
        value = value.split("|", 1)[0].split("#", 1)[0].strip()
        if value:
            yield value


def lexical_signature(text: str) -> str:
    """Hash lexical content while allowing Markdown-only presentation changes."""
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.DOTALL)
    text = re.sub(r"<!--\s*(?:question|answer)-source:(?:start|end)\s*-->", "", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"(?m)^\s*(?:#{1,6}|>|[-+*])\s*", "", text)
    return sha256_text(re.sub(r"\s+", "", text))


def load_profile(path: Path, verify_sources: bool = True) -> dict[str, Any]:
    path = path.expanduser().resolve()
    profile = load_json(path)
    if profile.get("schema_version") != 1:
        raise ConfigurationError("question-type-profile schema_version must be 1")
    if not isinstance(profile.get("sources"), list) or not profile["sources"]:
        raise ConfigurationError("profile.sources must be a non-empty list")
    if verify_sources:
        for source in profile["sources"]:
            source_path = Path(str(source.get("path", ""))).resolve()
            if not source_path.is_file():
                raise ConfigurationError(f"Frozen source is missing: {source_path}")
            if sha256_file(source_path) != source.get("sha256"):
                raise ConfigurationError(f"Frozen source changed: {source_path}")
        preset = profile.get("format", {}).get("preset")
        if preset:
            preset_path = Path(str(preset.get("path", ""))).resolve()
            if not preset_path.is_file():
                raise ConfigurationError(f"Frozen format preset is missing: {preset_path}")
            if sha256_file(preset_path) != preset.get("sha256"):
                raise ConfigurationError(f"Frozen format preset changed: {preset_path}")
    profile["_profile_path"] = str(path)
    return profile


def compile_number_patterns(
    values: Any,
    field: str,
    *,
    required: bool = True,
) -> list[re.Pattern[str]]:
    if values is None:
        values = []
    if not isinstance(values, list) or any(
        not isinstance(value, str) or not value for value in values
    ):
        raise ConfigurationError(f"{field} must be a list of non-empty regex strings")
    if required and not values:
        raise ConfigurationError(f"{field} is required")
    compiled: list[re.Pattern[str]] = []
    for index, value in enumerate(values):
        try:
            pattern = re.compile(value)
        except re.error as exc:
            raise ConfigurationError(f"Invalid regex in {field}[{index}]: {exc}") from exc
        if "number" not in pattern.groupindex:
            raise ConfigurationError(
                f"Every pattern in {field} requires a named 'number' group"
            )
        if pattern.search("") is not None:
            raise ConfigurationError(f"{field}[{index}] must not match an empty string")
        compiled.append(pattern)
    return compiled


def _validate_regex(value: Any, field: str, *, allow_empty_match: bool = False) -> None:
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"{field} must be a non-empty regex string")
    try:
        pattern = re.compile(value)
    except re.error as exc:
        raise ConfigurationError(f"Invalid regex in {field}: {exc}") from exc
    if not allow_empty_match and pattern.search("") is not None:
        raise ConfigurationError(f"{field} must not match an empty string")


def _validate_optional_bbox(value: Any, field: str) -> None:
    if value is None:
        return
    if not (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
        and value[0] <= value[2]
        and value[1] <= value[3]
    ):
        raise ConfigurationError(f"{field} must be [x0, y0, x1, y1]")


def validate_adapter_contract(adapter: dict[str, Any], profile: dict[str, Any]) -> None:
    """Validate the executable v1 adapter contract before any stage uses it."""
    output_policy = adapter.get("output_policy", {})
    if not isinstance(output_policy, dict):
        raise ConfigurationError("format-adapter.output_policy must be an object")
    for key in ("generate_index", "generate_canvas"):
        if key in output_policy and not isinstance(output_policy[key], bool):
            raise ConfigurationError(
                f"format-adapter.output_policy.{key} must be boolean"
            )
    filename_policy = adapter.get("filename_policy")
    if filename_policy is not None and (
        not isinstance(filename_policy, dict)
        or filename_policy.get("colon_replacement") != "_"
    ):
        raise ConfigurationError(
            "format-adapter.filename_policy.colon_replacement must be '_'"
        )
    for field in ("hierarchy", "content"):
        if not isinstance(adapter.get(field), dict):
            raise ConfigurationError(f"format-adapter.{field} must be an object")

    hierarchy = adapter["hierarchy"]
    if not isinstance(hierarchy.get("source_role"), str) or not hierarchy[
        "source_role"
    ].strip():
        raise ConfigurationError("format-adapter.hierarchy.source_role is required")
    root_output = hierarchy.get("root_output")
    if not isinstance(root_output, str) or not root_output.endswith(".md"):
        raise ConfigurationError(
            "format-adapter.hierarchy.root_output must be a Markdown path"
        )
    entries = hierarchy.get("entries")
    if not isinstance(entries, list):
        raise ConfigurationError("format-adapter.hierarchy.entries must be a list")
    keys: set[str] = set()
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            raise ConfigurationError(
                f"format-adapter.hierarchy.entries[{index}] must be an object"
            )
        key = str(item.get("key", "")).strip()
        if not key or key in keys:
            raise ConfigurationError(
                "format-adapter hierarchy entry keys must be non-empty and unique"
            )
        keys.add(key)
        if item.get("match_pattern") is not None:
            _validate_regex(
                item["match_pattern"], f"hierarchy.entries[{index}].match_pattern"
            )
    has_primary = isinstance(hierarchy.get("primary_authority"), dict)
    has_no_toc = isinstance(hierarchy.get("no_toc_authority"), dict)
    if has_primary == has_no_toc:
        raise ConfigurationError(
            "format-adapter.hierarchy requires exactly one of primary_authority or no_toc_authority"
        )

    content = adapter["content"]
    if content.get("unknown_label_policy", "review") not in {"review", "retain"}:
        raise ConfigurationError(
            "content.unknown_label_policy must be 'review' or 'retain'"
        )
    compile_number_patterns(
        content.get("question_patterns"), "content.question_patterns"
    )
    if "inline_question_patterns" in content:
        compile_number_patterns(
            content.get("inline_question_patterns"),
            "content.inline_question_patterns",
            required=False,
        )
    question_kind_rules = content.get("question_kind_rules", [])
    if not isinstance(question_kind_rules, list):
        raise ConfigurationError("content.question_kind_rules must be a list")
    legacy_solution_patterns = content.get("worked_example_solution_patterns", [])
    if not isinstance(legacy_solution_patterns, list):
        raise ConfigurationError(
            "content.worked_example_solution_patterns must be a list"
        )
    for index, pattern in enumerate(legacy_solution_patterns):
        _validate_regex(
            pattern, f"content.worked_example_solution_patterns[{index}]"
        )
    configured_kinds = {"exercise"}
    for index, rule in enumerate(question_kind_rules):
        if not isinstance(rule, dict) or not str(rule.get("kind", "")).strip():
            raise ConfigurationError(
                f"content.question_kind_rules[{index}] requires a non-empty kind"
            )
        configured_kinds.add(str(rule["kind"]))
        _validate_regex(
            rule.get("pattern"), f"content.question_kind_rules[{index}].pattern"
        )
        handling = (
            "separate-authoritative"
            if str(rule["kind"]) == "worked-example"
            else str(rule.get("answer_handling", "external"))
        )
        if handling not in {"external", "separate-authoritative"}:
            raise ConfigurationError(
                f"content.question_kind_rules[{index}].answer_handling is invalid"
            )
        solution_layout = str(rule.get("solution_layout", "tail"))
        if solution_layout not in {"tail", "interleaved"}:
            raise ConfigurationError(
                f"content.question_kind_rules[{index}].solution_layout is invalid"
            )
        answer_shape = str(rule.get("answer_shape", "auto"))
        if answer_shape not in {"auto", "composite"}:
            raise ConfigurationError(
                f"content.question_kind_rules[{index}].answer_shape is invalid"
            )
        atomize = rule.get("atomize_interleaved_subquestions", False)
        if not isinstance(atomize, bool):
            raise ConfigurationError(
                f"content.question_kind_rules[{index}].atomize_interleaved_subquestions must be boolean"
            )
        atomized_patterns = rule.get("atomized_subquestion_patterns", [])
        if atomize:
            if solution_layout != "interleaved":
                raise ConfigurationError(
                    f"content.question_kind_rules[{index}] atomization requires interleaved layout"
                )
            if not isinstance(atomized_patterns, list) or not atomized_patterns:
                raise ConfigurationError(
                    f"content.question_kind_rules[{index}] atomization requires atomized_subquestion_patterns"
                )
            for pattern_index, pattern in enumerate(atomized_patterns):
                _validate_regex(
                    pattern,
                    f"content.question_kind_rules[{index}].atomized_subquestion_patterns[{pattern_index}]",
                )
                compiled = re.compile(pattern)
                if "part" not in compiled.groupindex:
                    raise ConfigurationError(
                        f"content.question_kind_rules[{index}].atomized_subquestion_patterns[{pattern_index}] requires a named part group"
                    )
            template = str(rule.get("atomized_number_template", "{number}({part})"))
            if "{part}" not in template:
                raise ConfigurationError(
                    f"content.question_kind_rules[{index}].atomized_number_template requires {{part}}"
                )
        sequence_policy = str(rule.get("sequence_policy", "none"))
        if sequence_policy not in {"none", "continuous"}:
            raise ConfigurationError(
                f"content.question_kind_rules[{index}].sequence_policy is invalid"
            )
        start_patterns = rule.get("solution_start_patterns", [])
        resume_patterns = rule.get("solution_resume_patterns", [])
        for field, values in (
            ("solution_start_patterns", start_patterns),
            ("solution_resume_patterns", resume_patterns),
        ):
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value for value in values
            ):
                raise ConfigurationError(
                    f"content.question_kind_rules[{index}].{field} must be a list of non-empty regex strings"
                )
            for pattern_index, pattern in enumerate(values):
                _validate_regex(
                    pattern,
                    f"content.question_kind_rules[{index}].{field}[{pattern_index}]",
                )
        if handling == "separate-authoritative":
            if not start_patterns and not legacy_solution_patterns:
                raise ConfigurationError(
                    f"content.question_kind_rules[{index}] requires solution_start_patterns for separate-authoritative answers"
                )
            if solution_layout == "interleaved" and not resume_patterns:
                raise ConfigurationError(
                    f"content.question_kind_rules[{index}] requires solution_resume_patterns for interleaved answers"
                )
        if "authoritative_callout_title" in rule and not str(
            rule["authoritative_callout_title"]
        ).strip():
            raise ConfigurationError(
                f"content.question_kind_rules[{index}].authoritative_callout_title must be non-empty"
            )
        if "preserve_internal_headings" in rule and not isinstance(
            rule["preserve_internal_headings"], bool
        ):
            raise ConfigurationError(
                f"content.question_kind_rules[{index}].preserve_internal_headings must be boolean"
            )
        if "folder" in rule and not str(rule["folder"]).strip():
            raise ConfigurationError(
                f"content.question_kind_rules[{index}].folder must be non-empty"
            )
    count_expectations = content.get("question_count_expectations", [])
    if not isinstance(count_expectations, list):
        raise ConfigurationError("content.question_count_expectations must be a list")
    seen_count_expectations: set[tuple[str, str]] = set()
    for index, item in enumerate(count_expectations):
        if not isinstance(item, dict):
            raise ConfigurationError(
                f"content.question_count_expectations[{index}] must be an object"
            )
        context = str(item.get("context", "")).strip()
        kind = str(item.get("kind", "")).strip()
        count = item.get("count")
        key = (context, kind)
        if (
            not context
            or kind not in configured_kinds
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
            or item.get("reviewer_confirmed") is not True
            or not str(item.get("evidence", "")).strip()
            or key in seen_count_expectations
        ):
            raise ConfigurationError(
                f"Invalid content.question_count_expectations[{index}]"
            )
        seen_count_expectations.add(key)
    if "worked_example_solution_backtrack_fence" in content and not isinstance(
        content["worked_example_solution_backtrack_fence"], bool
    ):
        raise ConfigurationError(
            "content.worked_example_solution_backtrack_fence must be boolean"
        )
    if content.get("answer_callout_layout_version", 2) != 2:
        raise ConfigurationError(
            "content.answer_callout_layout_version must be 2"
        )
    roles = content.get("roles")
    if not isinstance(roles, list):
        raise ConfigurationError("format-adapter.content.roles must be a list")
    for index, rule in enumerate(roles):
        if not isinstance(rule, dict) or not str(rule.get("role", "")).strip():
            raise ConfigurationError(
                f"content.roles[{index}] requires a non-empty role"
            )
        try:
            depth = int(rule.get("depth"))
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"content.roles[{index}].depth must be an integer"
            ) from exc
        if depth < 0:
            raise ConfigurationError(
                f"content.roles[{index}].depth must be non-negative"
            )
        _validate_regex(rule.get("pattern"), f"content.roles[{index}].pattern")
        if "heading_only" in rule and not isinstance(rule["heading_only"], bool):
            raise ConfigurationError(
                f"content.roles[{index}].heading_only must be boolean"
            )
    question_scopes = content.get("question_scopes")
    if question_scopes is not None:
        if not isinstance(question_scopes, list) or not question_scopes:
            raise ConfigurationError("content.question_scopes must be a non-empty list")
        configured_roles = {str(rule.get("role")) for rule in roles}
        for index, scope in enumerate(question_scopes):
            if not isinstance(scope, dict):
                raise ConfigurationError(f"content.question_scopes[{index}] must be an object")
            if not any(
                key in scope for key in ("context", "contexts", "roles", "kinds", "start_line", "end_line")
            ):
                raise ConfigurationError(
                    f"content.question_scopes[{index}] requires a context, role, or line range"
                )
            contexts = scope.get("contexts")
            if contexts is not None and (
                not isinstance(contexts, list)
                or not contexts
                or any(not str(value).strip() for value in contexts)
            ):
                raise ConfigurationError(
                    f"content.question_scopes[{index}].contexts must be a non-empty list"
                )
            scoped_roles = scope.get("roles")
            if scoped_roles is not None and (
                not isinstance(scoped_roles, list)
                or not scoped_roles
                or any(str(value) not in configured_roles for value in scoped_roles)
            ):
                raise ConfigurationError(
                    f"content.question_scopes[{index}].roles must name configured roles"
                )
            scoped_kinds = scope.get("kinds")
            if scoped_kinds is not None and (
                not isinstance(scoped_kinds, list)
                or not scoped_kinds
                or any(str(value) not in configured_kinds for value in scoped_kinds)
            ):
                raise ConfigurationError(
                    f"content.question_scopes[{index}].kinds must name configured question kinds"
                )
            for key in ("start_line", "end_line"):
                if key in scope and (
                    not isinstance(scope[key], int) or isinstance(scope[key], bool) or scope[key] < 1
                ):
                    raise ConfigurationError(
                        f"content.question_scopes[{index}].{key} must be a positive integer"
                    )
            if (
                scope.get("start_line") is not None
                and scope.get("end_line") is not None
                and int(scope["start_line"]) > int(scope["end_line"])
            ):
                raise ConfigurationError(
                    f"content.question_scopes[{index}] line range is reversed"
                )
    question_overrides = content.get("question_number_overrides", [])
    if not isinstance(question_overrides, list):
        raise ConfigurationError("content.question_number_overrides must be a list")
    override_keys: set[tuple[str, int, int]] = set()
    for index, item in enumerate(question_overrides):
        if not isinstance(item, dict):
            raise ConfigurationError(
                f"content.question_number_overrides[{index}] must be an object"
            )
        context = str(item.get("context", "")).strip()
        number = str(item.get("number", "")).strip()
        try:
            start_line = int(item.get("start_line"))
            raw_column = int(item.get("raw_column", 1))
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"content.question_number_overrides[{index}] coordinates must be positive integers"
            ) from exc
        key = (context, start_line, raw_column)
        if not context or not number or start_line < 1 or raw_column < 1 or key in override_keys:
            raise ConfigurationError(
                "question number override identity must be complete, positive, and unique"
            )
        override_keys.add(key)
        if not str(item.get("anchor_text", "")).strip() and not item.get("anchor_pattern"):
            raise ConfigurationError(
                f"content.question_number_overrides[{index}] requires a drift anchor"
            )
        if item.get("anchor_pattern") is not None:
            _validate_regex(
                item["anchor_pattern"],
                f"content.question_number_overrides[{index}].anchor_pattern",
                allow_empty_match=True,
            )

    recovered_questions = content.get("recovered_questions", [])
    if not isinstance(recovered_questions, list):
        raise ConfigurationError("content.recovered_questions must be a list")
    recovered_keys: set[tuple[str, str]] = set()
    for index, item in enumerate(recovered_questions):
        if not isinstance(item, dict):
            raise ConfigurationError(f"content.recovered_questions[{index}] must be an object")
        context = str(item.get("context", "")).strip()
        number = str(item.get("number", "")).strip()
        body = str(item.get("body", "")).strip()
        source_page = str(item.get("source_page", "")).strip()
        try:
            after_line = int(item.get("after_line"))
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"content.recovered_questions[{index}].after_line must be positive"
            ) from exc
        identity = (context, number)
        if (
            not context
            or not number
            or not body
            or not source_page
            or after_line < 1
            or identity in recovered_keys
            or item.get("reviewer_confirmed") is not True
        ):
            raise ConfigurationError(
                "recovered question identity, body, page provenance, anchor, and review are required"
            )
        recovered_keys.add(identity)
        _validate_optional_bbox(
            item.get("source_bbox"),
            f"content.recovered_questions[{index}].source_bbox",
        )
        if not str(item.get("anchor_text", "")).strip() and not item.get("anchor_pattern"):
            raise ConfigurationError(f"content.recovered_questions[{index}] requires a drift anchor")
        if item.get("anchor_pattern") is not None:
            _validate_regex(
                item["anchor_pattern"],
                f"content.recovered_questions[{index}].anchor_pattern",
                allow_empty_match=True,
            )

    recovered_fragments = content.get("recovered_question_fragments", [])
    if not isinstance(recovered_fragments, list):
        raise ConfigurationError(
            "content.recovered_question_fragments must be a list"
        )
    fragment_keys: set[tuple[str, int, int, str]] = set()
    for index, item in enumerate(recovered_fragments):
        if not isinstance(item, dict):
            raise ConfigurationError(
                f"content.recovered_question_fragments[{index}] must be an object"
            )
        context = str(item.get("context", "")).strip()
        text = str(item.get("text", ""))
        position = str(item.get("position", ""))
        source_page = str(item.get("source_page", "")).strip()
        try:
            raw_line = int(item.get("raw_line"))
            raw_column = int(item.get("raw_column"))
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"content.recovered_question_fragments[{index}] coordinates must be positive integers"
            ) from exc
        identity = (context, raw_line, raw_column, position)
        if (
            not context
            or not text
            or position not in {"before", "after"}
            or not source_page
            or raw_line < 1
            or raw_column < 1
            or identity in fragment_keys
            or item.get("reviewer_confirmed") is not True
        ):
            raise ConfigurationError(
                "recovered question fragment identity, text, position, page provenance, and review are required"
            )
        fragment_keys.add(identity)
        _validate_optional_bbox(
            item.get("source_bbox"),
            f"content.recovered_question_fragments[{index}].source_bbox",
        )
        if not str(item.get("anchor_text", "")).strip() and not item.get(
            "anchor_pattern"
        ):
            raise ConfigurationError(
                f"content.recovered_question_fragments[{index}] requires a drift anchor"
            )
        if item.get("anchor_pattern") is not None:
            _validate_regex(
                item["anchor_pattern"],
                f"content.recovered_question_fragments[{index}].anchor_pattern",
                allow_empty_match=True,
            )

    semantic_exclusions = content.get(
        "reviewed_semantic_line_exclusions", []
    )
    if not isinstance(semantic_exclusions, list):
        raise ConfigurationError(
            "content.reviewed_semantic_line_exclusions must be a list"
        )
    exclusion_keys: set[tuple[str, int]] = set()
    for index, item in enumerate(semantic_exclusions):
        if not isinstance(item, dict):
            raise ConfigurationError(
                f"content.reviewed_semantic_line_exclusions[{index}] must be an object"
            )
        context = str(item.get("context", "")).strip()
        source_page = str(item.get("source_page", "")).strip()
        reason = str(item.get("reason", "")).strip()
        try:
            raw_line = int(item.get("raw_line"))
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"content.reviewed_semantic_line_exclusions[{index}].raw_line must be positive"
            ) from exc
        identity = (context, raw_line)
        if (
            not context
            or raw_line < 1
            or not source_page
            or not reason
            or identity in exclusion_keys
            or item.get("reviewer_confirmed") is not True
        ):
            raise ConfigurationError(
                f"Invalid content.reviewed_semantic_line_exclusions[{index}]"
            )
        exclusion_keys.add(identity)
        _validate_optional_bbox(
            item.get("source_bbox"),
            f"content.reviewed_semantic_line_exclusions[{index}].source_bbox",
        )
        if not str(item.get("anchor_text", "")).strip() and not item.get(
            "anchor_pattern"
        ):
            raise ConfigurationError(
                f"content.reviewed_semantic_line_exclusions[{index}] requires a drift anchor"
            )
        if item.get("anchor_pattern") is not None:
            _validate_regex(
                item["anchor_pattern"],
                f"content.reviewed_semantic_line_exclusions[{index}].anchor_pattern",
                allow_empty_match=True,
            )

    semantic_splits = content.get("reviewed_semantic_line_splits", [])
    if not isinstance(semantic_splits, list):
        raise ConfigurationError(
            "content.reviewed_semantic_line_splits must be a list"
        )
    split_keys: set[tuple[str, int]] = set()
    for index, item in enumerate(semantic_splits):
        if not isinstance(item, dict):
            raise ConfigurationError(
                f"content.reviewed_semantic_line_splits[{index}] must be an object"
            )
        context = str(item.get("context", "")).strip()
        source_page = str(item.get("source_page", "")).strip()
        reason = str(item.get("reason", "")).strip()
        try:
            raw_line = int(item.get("raw_line"))
            raw_columns = [int(value) for value in item.get("raw_columns", [])]
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"content.reviewed_semantic_line_splits[{index}] coordinates must be positive integers"
            ) from exc
        identity = (context, raw_line)
        if (
            not context
            or raw_line < 1
            or not raw_columns
            or any(value < 2 for value in raw_columns)
            or len(set(raw_columns)) != len(raw_columns)
            or not source_page
            or not reason
            or identity in split_keys
            or item.get("reviewer_confirmed") is not True
        ):
            raise ConfigurationError(
                f"Invalid content.reviewed_semantic_line_splits[{index}]"
            )
        split_keys.add(identity)
        _validate_optional_bbox(
            item.get("source_bbox"),
            f"content.reviewed_semantic_line_splits[{index}].source_bbox",
        )
        if not str(item.get("anchor_text", "")).strip() and not item.get(
            "anchor_pattern"
        ):
            raise ConfigurationError(
                f"content.reviewed_semantic_line_splits[{index}] requires a drift anchor"
            )
        if item.get("anchor_pattern") is not None:
            _validate_regex(
                item["anchor_pattern"],
                f"content.reviewed_semantic_line_splits[{index}].anchor_pattern",
                allow_empty_match=True,
            )

    relocations = content.get("virtual_span_relocations", [])
    if not isinstance(relocations, list):
        raise ConfigurationError("content.virtual_span_relocations must be a list")
    relocation_keys: set[tuple[str, int, int]] = set()
    for index, item in enumerate(relocations):
        if not isinstance(item, dict):
            raise ConfigurationError(
                f"content.virtual_span_relocations[{index}] must be an object"
            )
        context = str(item.get("context", "")).strip()
        try:
            start_line = int(item.get("start_line"))
            start_column = int(item.get("start_column", 1))
            end_before_line = int(item.get("end_before_line"))
            end_before_column = int(item.get("end_before_column", 1))
            before_line = int(item.get("before_line"))
            before_column = int(item.get("before_column", 1))
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"content.virtual_span_relocations[{index}] coordinates must be positive integers"
            ) from exc
        key = (context, start_line, start_column)
        if (
            not context
            or min(
                start_line,
                start_column,
                end_before_line,
                end_before_column,
                before_line,
                before_column,
            )
            < 1
            or key in relocation_keys
            or item.get("reviewer_confirmed") is not True
        ):
            raise ConfigurationError(
                "virtual span relocation identity, coordinates, and review must be complete and unique"
            )
        relocation_keys.add(key)
        if not str(item.get("anchor_text", "")).strip() and not item.get("anchor_pattern"):
            raise ConfigurationError(
                f"content.virtual_span_relocations[{index}] requires a start drift anchor"
            )
        for pattern_key in (
            "anchor_pattern",
            "end_anchor_pattern",
            "before_anchor_pattern",
        ):
            if item.get(pattern_key) is not None:
                _validate_regex(
                    item[pattern_key],
                    f"content.virtual_span_relocations[{index}].{pattern_key}",
                    allow_empty_match=True,
                )

    for section_name, items in (
        ("content.question_number_shift_ranges", content.get("question_number_shift_ranges", [])),
        (
            "answers.answer_number_shift_ranges",
            (adapter.get("answers") or {}).get("answer_number_shift_ranges", []),
        ),
    ):
        if not isinstance(items, list):
            raise ConfigurationError(f"{section_name} must be a list")
        seen_ranges: set[tuple[str, int, int, int, int]] = set()
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ConfigurationError(f"{section_name}[{index}] must be an object")
            context = str(item.get("context", "")).strip()
            try:
                start_line = int(item.get("start_line"))
                start_column = int(item.get("start_column", 1))
                end_line = int(item.get("end_line"))
                end_column = int(item.get("end_column", 2**31 - 1))
                offset = int(item.get("offset"))
            except (TypeError, ValueError) as exc:
                raise ConfigurationError(f"{section_name}[{index}] has invalid coordinates or offset") from exc
            identity = (context, start_line, start_column, end_line, end_column)
            if (
                not context
                or min(start_line, start_column, end_line, end_column) < 1
                or (start_line, start_column) > (end_line, end_column)
                or offset == 0
                or identity in seen_ranges
                or item.get("reviewer_confirmed") is not True
            ):
                raise ConfigurationError(f"{section_name}[{index}] must be reviewed, non-empty, ordered, and unique")
            seen_ranges.add(identity)
            if not str(item.get("anchor_text", "")).strip() and not item.get("anchor_pattern"):
                raise ConfigurationError(f"{section_name}[{index}] requires a start drift anchor")
            if not str(item.get("end_anchor_text", "")).strip() and not item.get("end_anchor_pattern"):
                raise ConfigurationError(f"{section_name}[{index}] requires an end drift anchor")
            for pattern_key in ("anchor_pattern", "end_anchor_pattern"):
                if item.get(pattern_key) is not None:
                    _validate_regex(
                        item[pattern_key],
                        f"{section_name}[{index}].{pattern_key}",
                        allow_empty_match=True,
                    )

    if profile.get("answers", {}).get("mode") == "unavailable":
        return
    answers = adapter.get("answers")
    if not isinstance(answers, dict):
        raise ConfigurationError(
            "format-adapter.answers must be an object when answers are enabled"
        )
    compile_number_patterns(answers.get("answer_patterns"), "answers.answer_patterns")
    if "inline_answer_patterns" in answers:
        compile_number_patterns(
            answers.get("inline_answer_patterns"),
            "answers.inline_answer_patterns",
            required=False,
        )
    contexts = answers.get("contexts", [])
    if not isinstance(contexts, list):
        raise ConfigurationError("answers.contexts must be a list")
    context_keys: set[str] = set()
    for index, item in enumerate(contexts):
        if not isinstance(item, dict):
            raise ConfigurationError(f"answers.contexts[{index}] must be an object")
        key = str(item.get("key", "")).strip()
        if not key or key in context_keys:
            raise ConfigurationError(
                "answers context keys must be non-empty and unique"
            )
        context_keys.add(key)
        if item.get("pattern") is not None:
            _validate_regex(item["pattern"], f"answers.contexts[{index}].pattern")
        if item.get("anchor_pattern") is not None:
            _validate_regex(
                item["anchor_pattern"],
                f"answers.contexts[{index}].anchor_pattern",
                allow_empty_match=True,
            )
        try:
            if item.get("start_line") is not None and int(item["start_line"]) < 1:
                raise ConfigurationError(
                    f"answers.contexts[{index}].start_line must be positive"
                )
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"answers.contexts[{index}].start_line must be a positive integer"
            ) from exc
    recovered_answers = answers.get("recovered_answers", [])
    if not isinstance(recovered_answers, list):
        raise ConfigurationError("answers.recovered_answers must be a list")
    recovered_answer_keys: set[tuple[str, str]] = set()
    for index, item in enumerate(recovered_answers):
        if not isinstance(item, dict):
            raise ConfigurationError(f"answers.recovered_answers[{index}] must be an object")
        context = str(item.get("context", "")).strip()
        number = str(item.get("number", "")).strip()
        body = str(item.get("body", "")).strip()
        source_page = str(item.get("source_page", "")).strip()
        try:
            after_line = int(item.get("after_line"))
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"answers.recovered_answers[{index}].after_line must be positive"
            ) from exc
        identity = (context, number)
        if (
            not context
            or not number
            or not body
            or not source_page
            or after_line < 1
            or identity in recovered_answer_keys
            or item.get("reviewer_confirmed") is not True
        ):
            raise ConfigurationError(
                "recovered answer identity, body, page provenance, anchor, and review are required"
            )
        recovered_answer_keys.add(identity)
        _validate_optional_bbox(
            item.get("source_bbox"),
            f"answers.recovered_answers[{index}].source_bbox",
        )
        if not str(item.get("anchor_text", "")).strip() and not item.get("anchor_pattern"):
            raise ConfigurationError(f"answers.recovered_answers[{index}] requires a drift anchor")
        if item.get("anchor_pattern") is not None:
            _validate_regex(
                item["anchor_pattern"],
                f"answers.recovered_answers[{index}].anchor_pattern",
                allow_empty_match=True,
            )
    implicit = answers.get("implicit_answers", [])
    if not isinstance(implicit, list):
        raise ConfigurationError("answers.implicit_answers must be a list")
    implicit_keys: set[tuple[str, str, int, int]] = set()
    for index, item in enumerate(implicit):
        if not isinstance(item, dict):
            raise ConfigurationError(
                f"answers.implicit_answers[{index}] must be an object"
            )
        context = str(item.get("context", "")).strip()
        number = str(item.get("number", "")).strip()
        try:
            start_line = int(item.get("start_line"))
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"answers.implicit_answers[{index}].start_line must be a positive integer"
            ) from exc
        try:
            raw_column = int(item.get("raw_column", 1))
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"answers.implicit_answers[{index}].raw_column must be a positive integer"
            ) from exc
        key = (context, number, start_line, raw_column)
        if (
            not context
            or not number
            or start_line < 1
            or raw_column < 1
            or key in implicit_keys
        ):
            raise ConfigurationError(
                "implicit answer identity must be complete, positive, and unique"
            )
        implicit_keys.add(key)
        if not str(item.get("anchor_text", "")).strip() and not item.get(
            "anchor_pattern"
        ):
            raise ConfigurationError(
                f"answers.implicit_answers[{index}] requires a drift anchor"
            )
        if item.get("anchor_pattern") is not None:
            _validate_regex(
                item["anchor_pattern"],
                f"answers.implicit_answers[{index}].anchor_pattern",
                allow_empty_match=True,
            )
    choice_overrides = answers.get("choice_answer_overrides", [])
    if not isinstance(choice_overrides, list):
        raise ConfigurationError("answers.choice_answer_overrides must be a list")
    override_keys: set[tuple[str, str, int]] = set()
    for index, item in enumerate(choice_overrides):
        if not isinstance(item, dict):
            raise ConfigurationError(
                f"answers.choice_answer_overrides[{index}] must be an object"
            )
        context = str(item.get("context", "")).strip()
        number = str(item.get("number", "")).strip()
        answer = str(item.get("answer", "")).strip().upper()
        try:
            start_line = int(item.get("start_line"))
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"answers.choice_answer_overrides[{index}].start_line must be a positive integer"
            ) from exc
        key = (context, number, start_line)
        if (
            not context
            or not number
            or start_line < 1
            or not re.fullmatch(r"[A-F]+", answer)
            or key in override_keys
        ):
            raise ConfigurationError(
                "choice answer override identity and A-F answer must be complete and unique"
            )
        override_keys.add(key)
        if not str(item.get("anchor_text", "")).strip() and not item.get(
            "anchor_pattern"
        ):
            raise ConfigurationError(
                f"answers.choice_answer_overrides[{index}] requires a drift anchor"
            )
        if item.get("anchor_pattern") is not None:
            _validate_regex(
                item["anchor_pattern"],
                f"answers.choice_answer_overrides[{index}].anchor_pattern",
                allow_empty_match=True,
            )
    short_answer_overrides = answers.get("short_answer_overrides", [])
    if not isinstance(short_answer_overrides, list):
        raise ConfigurationError("answers.short_answer_overrides must be a list")
    short_override_keys: set[tuple[str, str, int]] = set()
    for index, item in enumerate(short_answer_overrides):
        if not isinstance(item, dict):
            raise ConfigurationError(
                f"answers.short_answer_overrides[{index}] must be an object"
            )
        context = str(item.get("context", "")).strip()
        number = str(item.get("number", "")).strip()
        answer = str(item.get("answer", "")).strip()
        try:
            start_line = int(item.get("start_line"))
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"answers.short_answer_overrides[{index}].start_line must be a positive integer"
            ) from exc
        key = (context, number, start_line)
        if not context or not number or not answer or start_line < 1 or key in short_override_keys:
            raise ConfigurationError(
                "short answer override identity and answer must be complete and unique"
            )
        short_override_keys.add(key)
        if not str(item.get("anchor_text", "")).strip() and not item.get(
            "anchor_pattern"
        ):
            raise ConfigurationError(
                f"answers.short_answer_overrides[{index}] requires a drift anchor"
            )
        if item.get("anchor_pattern") is not None:
            _validate_regex(
                item["anchor_pattern"],
                f"answers.short_answer_overrides[{index}].anchor_pattern",
                allow_empty_match=True,
            )


def adapter_output_policy(adapter: dict[str, Any]) -> dict[str, bool]:
    """Resolve optional adapter output switches with backward-compatible defaults."""
    configured = adapter.get("output_policy") or {}
    return {
        "generate_index": configured.get("generate_index", True) is True,
        "generate_canvas": configured.get("generate_canvas", True) is True,
    }


def require_reviewed_adapter(profile: dict[str, Any], adapter_path: Path) -> dict[str, Any]:
    adapter = load_json(adapter_path.resolve())
    if adapter.get("schema_version") != 1:
        raise ConfigurationError("format-adapter schema_version must be 1")
    if adapter.get("status") != "passed" or adapter.get("reviewer_confirmed") is not True:
        raise ReviewRequired("format-adapter must be passed and reviewer_confirmed")
    expected = adapter.get("profile")
    if expected and Path(str(expected)).resolve() != Path(profile["_profile_path"]).resolve():
        raise ConfigurationError("format-adapter is bound to another profile")
    validate_adapter_contract(adapter, profile)
    return adapter
