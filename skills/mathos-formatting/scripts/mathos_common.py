from __future__ import annotations
import ast
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    line_number: int


@dataclass(frozen=True)
class HeadingRule:
    rule_id: str
    pattern: str
    replacement: str
    flags: int


@dataclass(frozen=True)
class TextBlock:
    kind: str
    text: str
    start_line: int
    end_line: int

@dataclass(frozen=True)
class H1Section:
    heading: str
    text: str
    start_line: int
    end_line: int

@dataclass(frozen=True)
class MarkdownStructure:
    source_label: str
    headings: list[Heading]
    toc_block: TextBlock | None
    heading_like_lines: list[str]
    heading_level_distribution: dict[int, int]
    h1_sections: list[H1Section]
    protected_blocks: list[TextBlock]

@dataclass(frozen=True)
class PreservationCounts:
    image_references: int
    details_blocks: int
    math_delimiters: int
    table_like_lines: int

@dataclass(frozen=True)
class PluginResult:
    cleaned_markdown: str
    summary: list[str]
    warnings: list[str]

@dataclass(frozen=True)
class ApprovedApplyResult:
    candidate_path: Path
    report_path: Path
    summary: list[str]
    warnings: list[str]

@dataclass(frozen=True)
class CandidateRunResult:
    candidate_path: Path
    report_path: Path
    summary: list[str]
    warnings: list[str]

@dataclass(frozen=True)
class LearningRunState:
    source_path: Path
    candidate_path: Path
    provider_base_url: str
    provider_model: str
    stage: str
    status: str
    artifacts: dict[str, Path]
    warnings: list[str]
    errors: list[str]
    approved: bool
    toc_start_line: int | None = None
    toc_end_line: int | None = None
    stage1_validated: bool = False

@dataclass(frozen=True)
class LearningRunResult:
    status: str
    work_dir: Path
    candidate_path: Path
    report_path: Path
    artifacts: dict[str, Path]
    summary: list[str]
    warnings: list[str]
    errors: list[str]

class FormattingError(RuntimeError):
    """Raised when formatting configuration or execution is unsafe."""

SAFE_IMPORTS = {"re", "math", "typing"}
UNSAFE_CALL_NAMES = {"open", "exec", "eval", "compile", "__import__", "getattr", "globals", "locals", "vars"}
UNSAFE_ATTRIBUTE_ROOTS = {"__builtins__", "builtins", "os", "sys", "subprocess", "pathlib", "socket", "requests", "urllib", "http", "shutil"}
PYTHON_ARTIFACT_ALLOWED_IMPORTS = {"os", "re", "pathlib"}
PYTHON_ARTIFACT_UNSAFE_IMPORTS = {
    "subprocess", "shutil", "socket", "requests", "urllib", "http", "ftplib", "pathlib2"
}
PYTHON_ARTIFACT_UNSAFE_CALLS = {
    "eval", "exec", "compile", "__import__", "remove", "unlink", "rename", "rmdir", "removedirs", "system", "popen"
}
PYTHON_ARTIFACT_UNSAFE_ATTRS = {
    "remove", "unlink", "rename", "rmdir", "removedirs", "system", "popen", "rmtree",
    "move", "copy", "copy2", "copytree", "urlopen", "request",
}

def _validate_plugin_ast(source: str) -> None:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in SAFE_IMPORTS:
                    raise FormattingError(f"unsafe import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in SAFE_IMPORTS:
                raise FormattingError(f"unsafe import: {node.module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in UNSAFE_CALL_NAMES:
                raise FormattingError(f"unsafe call: {node.func.id}")
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in UNSAFE_ATTRIBUTE_ROOTS:
                raise FormattingError(f"unsafe attribute access: {node.value.id}.{node.attr}")
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            if node.value.id in UNSAFE_ATTRIBUTE_ROOTS:
                raise FormattingError(f"unsafe subscript access: {node.value.id}")

def load_safe_plugin(plugin_path: Path) -> ModuleType:
    source = plugin_path.read_text(encoding="utf-8")
    _validate_plugin_ast(source)
    module_name = f"mathos_candidate_{abs(hash(plugin_path.resolve()))}"
    spec = importlib.util.spec_from_file_location(module_name, plugin_path)
    if spec is None or spec.loader is None:
        raise FormattingError(f"cannot load plugin: {plugin_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        for attr in ["PLUGIN_ID", "PLUGIN_VERSION", "analyze", "clean"]:
            if not hasattr(module, attr):
                raise FormattingError(f"plugin missing required attribute: {attr}")
        probe = module.clean("probe")
        if not isinstance(probe, str):
            raise FormattingError("plugin clean() must return a string")
        analysis = module.analyze("probe")
        if not isinstance(analysis, dict):
            raise FormattingError("plugin analyze() must return a dict")
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module

def run_plugin(plugin: ModuleType, markdown: str) -> PluginResult:
    analysis = plugin.analyze(markdown)
    if not isinstance(analysis, dict):
        raise FormattingError("plugin analyze() must return a dict")
    cleaned = plugin.clean(markdown)
    if not isinstance(cleaned, str):
        raise FormattingError("plugin clean() must return a string")
    summary = analysis.get("summary", [])
    warnings = analysis.get("warnings", [])
    return PluginResult(cleaned_markdown=cleaned, summary=summary, warnings=warnings)

def candidate_path_for(original_path: Path) -> Path:
    return original_path.parent / "mathos-formatting" / f"{original_path.stem}.candidate{original_path.suffix}"

def learning_work_dir_for(markdown_path: Path) -> Path:
    return markdown_path.parent / "mathos-formatting" / markdown_path.stem

def learning_candidate_path_for(markdown_path: Path, work_dir: Path | None = None) -> Path:
    base = work_dir if work_dir is not None else learning_work_dir_for(markdown_path)
    return base / "candidate.md"

def _json_path_map(paths: dict[str, Path]) -> dict[str, str]:
    return {key: str(value) for key, value in paths.items()}

def write_learning_state(work_dir: Path, state: LearningRunState) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_path": str(state.source_path),
        "candidate_path": str(state.candidate_path),
        "provider_base_url": state.provider_base_url,
        "provider_model": state.provider_model,
        "stage": state.stage,
        "status": state.status,
        "artifacts": _json_path_map(state.artifacts),
        "warnings": state.warnings,
        "errors": state.errors,
        "approved": state.approved,
        "toc_start_line": state.toc_start_line,
        "toc_end_line": state.toc_end_line,
        "stage1_validated": state.stage1_validated,
    }
    state_path = work_dir / "run-state.json"
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return state_path

def create_fresh_candidate(original_path: Path) -> Path:
    import shutil
    original_path = original_path.resolve()
    if not original_path.exists():
        raise FormattingError(f"source Markdown file does not exist: {original_path}")
    if original_path.suffix.lower() != ".md":
        raise FormattingError(f"source file must be Markdown: {original_path}")
    if not original_path.is_file():
        raise FormattingError(f"source Markdown file must be a file: {original_path}")
    candidate_path = candidate_path_for(original_path)
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    if candidate_path.exists():
        candidate_path.unlink()
    shutil.copy2(original_path, candidate_path)
    return candidate_path

def _strip_single_line_ending(text: str) -> tuple[str, bool]:
    if text.endswith("\r\n"):
        return text[:-2], True
    if text.endswith(("\n", "\r")):
        return text[:-1], True
    return text, False

def _split_single_line_ending(text: str) -> tuple[str, str]:
    if text.endswith("\r\n"):
        return text[:-2], "\r\n"
    if text.endswith("\n"):
        return text[:-1], "\n"
    if text.endswith("\r"):
        return text[:-1], "\r"
    return text, ""

def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _write_text_artifact(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path

# Constants & Regexes
HEADING_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*$")
ATX_CLOSING_SEQUENCE_RE = re.compile(r"\s+#+\s*$")
TOC_HEADING_RE = re.compile(r"^#{1,6}\s*(目录|目\s*录|contents?)\s*$", re.IGNORECASE)
HEADING_LIKE_RE = re.compile(
    r"^(第[一二三四五六七八九十百千万0-9]+[章节篇部].+|"
    r"\d+(?:\.\d+)+\s+.+|"
    r"(阅读与思考|探究与发现|信息技术应用|文献阅读|小结|复习参考题).*)$"
)
TOC_ENTRY_PAGE_RE = re.compile(r"(?:…+|\.{2,}|·{2,}|．{2,}|\s+)\s*\d+\s*$")
CODE_FENCE_OPEN_RE = re.compile(r"^(`{3,}|~{3,}).*$")
FLAG_MAP = {
    "MULTILINE": re.MULTILINE,
    "IGNORECASE": re.IGNORECASE,
    "DOTALL": re.DOTALL,
}
CHINESE_CHAPTER_RE = re.compile(r"第\s*([一二三四五六七八九十百千万零〇两0-9]+)\s*章")
ENGLISH_CHAPTER_RE = re.compile(r"\bChapter\s+([0-9]+)\b", re.IGNORECASE)

CHINESE_DIGIT_VALUES = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
CHINESE_UNIT_VALUES = {
    "十": 10, "百": 100, "千": 1000, "万": 10000,
}
CHINESE_DIGITS = "零一二三四五六七八九"

def _is_code_fence_close(line: str, fence_character: str, fence_length: int) -> bool:
    candidate = line.rstrip()
    leading_spaces = len(candidate) - len(candidate.lstrip(" "))
    if leading_spaces > 3:
        return False
    candidate = candidate.lstrip(" ")
    return len(candidate) >= fence_length and all(character == fence_character for character in candidate)

def _match_code_fence_open(line: str) -> re.Match[str] | None:
    leading_spaces = len(line) - len(line.lstrip(" "))
    if leading_spaces > 3:
        return None
    return CODE_FENCE_OPEN_RE.match(line.lstrip(" "))

def _normalize_toc_page_heading(text: str) -> str:
    return TOC_ENTRY_PAGE_RE.sub("", text).strip()

def _normalize_atx_heading_text(text: str) -> str:
    return ATX_CLOSING_SEQUENCE_RE.sub("", text)

def _line_offsets(markdown: str) -> list[str]:
    return markdown.splitlines()

def _chinese_number_to_int(text: str) -> int | None:
    if text.isdecimal():
        return int(text)
    total = 0
    section = 0
    number = 0
    saw_number = False
    for character in text:
        if character in CHINESE_DIGIT_VALUES:
            number = CHINESE_DIGIT_VALUES[character]
            saw_number = True
            continue
        unit = CHINESE_UNIT_VALUES.get(character)
        if unit is None:
            return None
        if unit == 10000:
            section = (section + number) * unit
            total += section
            section = 0
            number = 0
            continue
        section += (number or 1) * unit
        number = 0
    total += section + number
    return total if saw_number or total else None

def _int_to_chinese_number(value: int) -> str:
    if value < 0 or value > 9999:
        return str(value)
    if value < 10:
        return CHINESE_DIGITS[value]
    if value < 100:
        tens, ones = divmod(value, 10)
        prefix = "" if tens == 1 else CHINESE_DIGITS[tens]
        return f"{prefix}十{CHINESE_DIGITS[ones] if ones else ''}"
    if value < 1000:
        hundreds, remainder = divmod(value, 100)
        if remainder == 0:
            return f"{CHINESE_DIGITS[hundreds]}百"
        zero = "零" if remainder < 10 else ""
        return f"{CHINESE_DIGITS[hundreds]}百{zero}{_int_to_chinese_number(remainder)}"
    thousands, remainder = divmod(value, 1000)
    if remainder == 0:
        return f"{CHINESE_DIGITS[thousands]}千"
    zero = "零" if remainder < 100 else ""
    return f"{CHINESE_DIGITS[thousands]}千{zero}{_int_to_chinese_number(remainder)}"

def _normalize_chinese_chapter_number(raw_number: str) -> str:
    parsed = _chinese_number_to_int(raw_number)
    return _int_to_chinese_number(parsed) if parsed is not None else raw_number

def _chapter_context_from_heading_text(text: str) -> tuple[str, str, str] | None:
    chinese_match = CHINESE_CHAPTER_RE.search(text)
    if chinese_match:
        chapter_number = _normalize_chinese_chapter_number(chinese_match.group(1))
        return ("zh", f"第{chapter_number}章", str(_chinese_number_to_int(chinese_match.group(1)) or chapter_number))
    english_match = ENGLISH_CHAPTER_RE.search(text)
    if english_match:
        chapter_number = english_match.group(1)
        return ("en", f"Chapter {chapter_number}", chapter_number)
    return None

def _extract_protected_blocks(lines: list[str]) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    code_fence_character = ""
    code_fence_length = 0
    code_start = 0
    in_math = False
    math_start = 0
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if code_fence_character:
            if _is_code_fence_close(line, code_fence_character, code_fence_length):
                blocks.append(TextBlock("code_fence", "\n".join(lines[code_start - 1:index]), code_start, index))
                code_fence_character = ""
                code_fence_length = 0
            continue
        if in_math:
            if stripped == "$$":
                blocks.append(TextBlock("math_block", "\n".join(lines[math_start - 1:index]), math_start, index))
                in_math = False
            continue
        code_fence_match = _match_code_fence_open(line)
        if code_fence_match:
            code_fence = code_fence_match.group(1)
            code_fence_character = code_fence[0]
            code_fence_length = len(code_fence)
            code_start = index
            continue
        if stripped == "$$":
            in_math = True
            math_start = index
            continue
        if re.search(r"!\[[^\]]*\]\([^)]+\)", line):
            blocks.append(TextBlock("image", line, index, index))
    if code_fence_character:
        blocks.append(TextBlock("code_fence", "\n".join(lines[code_start - 1:]), code_start, len(lines)))
    if in_math:
        blocks.append(TextBlock("math_block", "\n".join(lines[math_start - 1:]), math_start, len(lines)))
    return blocks

def _line_in_blocks(line_number: int, blocks: list[TextBlock], kinds: set[str]) -> bool:
    return any(block.kind in kinds and block.start_line <= line_number <= block.end_line for block in blocks)

def _extract_toc_block(lines: list[str], headings: list[Heading]) -> TextBlock | None:
    toc_heading = next(
        (heading for heading in headings if TOC_HEADING_RE.match("#" * heading.level + " " + heading.text)),
        None,
    )
    if toc_heading is None:
        return None
    following_h1 = None
    toc_page_titles: set[str] = set()
    first_toc_h1_normalized = None
    for heading in headings:
        if heading.level != 1 or heading.line_number <= toc_heading.line_number:
            continue
        if TOC_ENTRY_PAGE_RE.search(heading.text):
            normalized_title = _normalize_toc_page_heading(heading.text)
            if first_toc_h1_normalized is None:
                first_toc_h1_normalized = normalized_title
            if normalized_title == first_toc_h1_normalized and len(toc_page_titles) > 0:
                following_h1 = heading
                break
            toc_page_titles.add(normalized_title)
            continue
        following_h1 = heading
        break
    end_line = (following_h1.line_number - 1) if following_h1 else len(lines)
    text = "\n".join(lines[toc_heading.line_number - 1:end_line])
    return TextBlock("toc", text, toc_heading.line_number, end_line)

def _extract_h1_sections(lines: list[str], headings: list[Heading]) -> list[H1Section]:
    h1_headings = [heading for heading in headings if heading.level == 1]
    sections: list[H1Section] = []
    for index, heading in enumerate(h1_headings):
        end_line = h1_headings[index + 1].line_number - 1 if index + 1 < len(h1_headings) else len(lines)
        sections.append(
            H1Section(
                heading=heading.text,
                text="\n".join(lines[heading.line_number - 1:end_line]),
                start_line=heading.line_number,
                end_line=end_line,
            )
        )
    return sections

def extract_structure(markdown: str, source_label: str) -> MarkdownStructure:
    lines = _line_offsets(markdown)
    protected_blocks = _extract_protected_blocks(lines)
    headings: list[Heading] = []
    heading_like_lines: list[str] = []
    distribution: dict[int, int] = {}
    for line_number, line in enumerate(lines, start=1):
        if _line_in_blocks(line_number, protected_blocks, {"code_fence", "math_block"}):
            continue
        heading_match = HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            headings.append(Heading(level, _normalize_atx_heading_text(heading_match.group(2)), line_number))
            distribution[level] = distribution.get(level, 0) + 1
            continue
        stripped = line.strip()
        if stripped and HEADING_LIKE_RE.match(stripped):
            heading_like_lines.append(stripped)
    return MarkdownStructure(
        source_label=source_label,
        headings=headings,
        toc_block=_extract_toc_block(lines, headings),
        heading_like_lines=heading_like_lines,
        heading_level_distribution=distribution,
        h1_sections=_extract_h1_sections(lines, headings),
        protected_blocks=protected_blocks,
    )


def find_total_pages_from_metadata(markdown_path: Path) -> int | None:
    search_roots = [
        Path(r"C:\Mathematics-Knowledge\agent-memory\records"),
        Path(r"C:\Mathematics-Knowledge\Mathematics-Knowledge-code\agent-memory\records"),
    ]
    target_name = markdown_path.name.lower()
    
    for root in search_roots:
        if not root.exists():
            continue
        try:
            for record_dir in root.iterdir():
                if not record_dir.is_dir():
                    continue
                run_state_file = record_dir / "run-state.json"
                if run_state_file.exists():
                    try:
                        state_data = json.loads(run_state_file.read_text(encoding="utf-8"))
                        outputs = state_data.get("outputs", [])
                        matches = False
                        for out in outputs:
                            target_md = out.get("target_md", "")
                            if Path(target_md).name.lower() == target_name:
                                matches = True
                                break
                        if matches:
                            extracted_dir = record_dir / "extracted"
                            if extracted_dir.exists():
                                for part_dir in extracted_dir.iterdir():
                                    layout_file = part_dir / "layout.json"
                                    if layout_file.exists():
                                        try:
                                            layout_data = json.loads(layout_file.read_text(encoding="utf-8"))
                                            if "pdf_info" in layout_data and isinstance(layout_data["pdf_info"], list):
                                                return len(layout_data["pdf_info"])
                                        except Exception:
                                            pass
                    except Exception:
                        pass
        except Exception:
            pass
    return None


def extract_first_20_pages(markdown: str, markdown_path: Path) -> str:
    total_pages = find_total_pages_from_metadata(markdown_path) or 200
    lines = markdown.splitlines()
    total_lines = len(lines)
    
    lines_per_page = total_lines / total_pages if total_pages > 0 else 40
    num_lines = min(total_lines, max(800, int(20 * lines_per_page)))
    
    prepended_lines = [f"{i}: {line}" for i, line in enumerate(lines[:num_lines], start=1)]
    return "\n".join(prepended_lines) + ("\n" if prepended_lines else "")


IMAGE_REFERENCE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)|<img\s+[^>]*src=", re.IGNORECASE)
DETAILS_OPEN_RE = re.compile(r"^ {0,3}<details(?:\s|>)", re.IGNORECASE)

def _is_table_line(line: str) -> bool:
    stripped = line.strip()
    return "|" in stripped and bool(stripped)

def _content_protected_line_mask(lines: list[str]) -> list[bool]:
    protected = [False] * len(lines)
    in_yaml = len(lines) > 0 and lines[0].strip() == "---"
    in_code = False
    code_marker = ""
    in_math = False
    in_bracket_math = False
    in_details = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if in_yaml:
            protected[index] = True
            if index > 0 and stripped == "---":
                in_yaml = False
            continue
        if in_code:
            protected[index] = True
            if stripped.startswith(code_marker):
                in_code = False
            continue
        if in_math:
            protected[index] = True
            if stripped == "$$":
                in_math = False
            continue
        if in_bracket_math:
            protected[index] = True
            if stripped == r"\]":
                in_bracket_math = False
            continue
        if in_details:
            protected[index] = True
            if stripped.lower().startswith("</details>"):
                in_details = False
            continue
        if HEADING_RE.match(line):
            protected[index] = True
        elif stripped.startswith("```") or stripped.startswith("~~~"):
            protected[index] = True
            in_code = True
            code_marker = stripped[:3]
        elif stripped == "$$":
            protected[index] = True
            in_math = True
        elif stripped == r"\[":
            protected[index] = True
            in_bracket_math = True
        elif stripped.lower().startswith("<details"):
            protected[index] = True
            in_details = True
        elif _is_table_line(line):
            protected[index] = True
    return protected


def parse_json_artifact_from_text(text: str) -> str:
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    # Sanitize invalid backslash escape sequences in the JSON string
    # Group 1 matches valid JSON escapes. Group 2 matches invalid backslashes.
    cleaned = re.sub(
        r'(\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})|(\\)',
        lambda m: m.group(1) if m.group(1) else '\\\\',
        stripped,
    )
    return cleaned


def parse_python_artifact_from_text(text: str) -> str:
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:python)?\s*(.*?)```", stripped, flags=re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    if "def clean(" not in stripped or "def analyze(" not in stripped:
        raise FormattingError("python artifact must define analyze() and clean()")
    return stripped


def parse_python_source_artifact(text: str) -> str:
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:python)?\s*(.*?)```", stripped, flags=re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    try:
        ast.parse(stripped)
    except SyntaxError as exc:
        raise FormattingError(f"python artifact is not valid Python: {exc}") from exc
    return stripped + ("\n" if not stripped.endswith("\n") else "")


def _validate_python_artifact_ast(source: str) -> ast.Module:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in PYTHON_ARTIFACT_UNSAFE_IMPORTS or root not in PYTHON_ARTIFACT_ALLOWED_IMPORTS:
                    raise FormattingError(f"unsafe import in python artifact: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in PYTHON_ARTIFACT_UNSAFE_IMPORTS or root not in PYTHON_ARTIFACT_ALLOWED_IMPORTS:
                raise FormattingError(f"unsafe import in python artifact: {node.module}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in PYTHON_ARTIFACT_UNSAFE_CALLS:
                raise FormattingError(f"unsafe call in python artifact: {node.func.id}")
            if isinstance(node.func, ast.Attribute) and node.func.attr in PYTHON_ARTIFACT_UNSAFE_ATTRS:
                raise FormattingError(f"unsafe attribute call in python artifact: {node.func.attr}")
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in {"subprocess", "shutil", "socket", "requests", "urllib", "http"}:
                raise FormattingError(f"unsafe attribute access in python artifact: {node.value.id}.{node.attr}")
    return tree


def validate_batch_processor_source(source: str) -> None:
    tree = _validate_python_artifact_ast(source)
    if not source.startswith("import os"):
        raise FormattingError("python batch artifact must start with import os")
    required_imports = {"os": False, "re": False, "Path": False}
    required_functions = {"get_target_root", "protect_blocks", "restore_blocks", "replace_in_file", "main"}
    defined_functions: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    required_imports["os"] = True
                if alias.name == "re":
                    required_imports["re"] = True
        elif isinstance(node, ast.ImportFrom) and node.module == "pathlib":
            for alias in node.names:
                if alias.name == "Path":
                    required_imports["Path"] = True
        elif isinstance(node, ast.FunctionDef):
            defined_functions.add(node.name)
    missing_imports = [name for name, present in required_imports.items() if not present]
    if missing_imports:
        raise FormattingError(f"python batch artifact missing imports: {', '.join(missing_imports)}")
    missing_functions = sorted(required_functions - defined_functions)
    if missing_functions:
        raise FormattingError(f"python batch artifact missing functions: {', '.join(missing_functions)}")


def validate_title_rewrite_source(source: str) -> dict[str, str]:
    tree = _validate_python_artifact_ast(source)
    assignments = [
        node for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
    ]
    other_statements = [
        node for node in tree.body
        if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr))
    ]
    if other_statements:
        raise FormattingError("title rewrite artifact must only define TITLE_REWRITE_MAP")
    title_node: ast.AST | None = None
    for node in assignments:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "TITLE_REWRITE_MAP" for target in node.targets):
                title_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "TITLE_REWRITE_MAP":
            title_node = node.value
    if title_node is None:
        raise FormattingError("title rewrite artifact must define TITLE_REWRITE_MAP")
    try:
        mapping = ast.literal_eval(title_node)
    except Exception as exc:
        raise FormattingError("TITLE_REWRITE_MAP must be a literal dict") from exc
    if not isinstance(mapping, dict):
        raise FormattingError("TITLE_REWRITE_MAP must be a dict")
    validated: dict[str, str] = {}
    for key, value in mapping.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise FormattingError("TITLE_REWRITE_MAP keys and values must be strings")
        key_strip = key.strip()
        value_strip = value.strip()
        if not HEADING_RE.match(key_strip) or not HEADING_RE.match(value_strip):
            raise FormattingError("TITLE_REWRITE_MAP keys and values must be Markdown heading lines")
        key_level = len(key_strip) - len(key_strip.lstrip("#"))
        value_level = len(value_strip) - len(value_strip.lstrip("#"))
        if not (key_level == value_level or 4 <= value_level <= 6):
            raise FormattingError("TITLE_REWRITE_MAP may only preserve level or downgrade to H4-H6")
        validated[key_strip] = value_strip
    return validated


def validate_candidate_not_too_short(before: str, after: str, stage: str) -> None:
    before_len = len(before.strip())
    after_len = len(after.strip())
    if before_len >= 200 and after_len < before_len * 0.5:
        raise FormattingError(
            f"candidate too short after {stage}: {after_len} characters after, {before_len} before"
        )


def run_batch_processor_in_sandbox(
    script_path: Path,
    markdown: str,
    work_dir: Path,
    sandbox_name: str,
    filename: str = "candidate.md",
) -> str:
    script_path = script_path.resolve()
    source = script_path.read_text(encoding="utf-8")
    validate_batch_processor_source(source)
    sandbox_root = work_dir / "_python-artifact-sandboxes" / sandbox_name
    if sandbox_root.exists():
        shutil.rmtree(sandbox_root)
    sandbox_root.mkdir(parents=True)
    candidate = sandbox_root / filename
    candidate.write_text(markdown, encoding="utf-8")
    import os
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, str(script_path)],
        input=str(sandbox_root) + "\n",
        text=True,
        capture_output=True,
        cwd=str(sandbox_root),
        timeout=120,
        encoding="utf-8",
        env=env,
    )
    if completed.returncode != 0:
        raise FormattingError(
            "python batch artifact failed "
            f"(exit {completed.returncode}): {completed.stderr.strip() or completed.stdout.strip()}"
        )
    if not candidate.exists():
        raise FormattingError("python batch artifact removed the sandbox candidate")
    return candidate.read_text(encoding="utf-8")
