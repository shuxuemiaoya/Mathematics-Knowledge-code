# MathOS Formatting Provider Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `learn-from-provider` workflow that calls DeepSeek twice: first for TOC-based heading rules, then for H1-based image/text cleanup, while modifying only a candidate backup.

**Architecture:** Keep `mathos_formatting_core.py` responsible for deterministic file and Markdown transformations, keep `mathos_provider.py` responsible for provider settings/calls/parsing, and keep `mathos_formatting.py` as the thin CLI orchestrator. Add a provider-learning orchestration function that writes a resumable artifact folder and fails closed with `run-state.json`.

**Tech Stack:** Python standard library, existing MathOS formatting scripts, `pytest`, DeepSeek-compatible chat API through `urllib.request`, JSON/Markdown artifacts.

---

## Scope Check

This plan implements one cohesive feature in `skills/mathos-formatting`: provider-driven one-file learning. It does not implement batch approval, automatic promotion beyond `manual-only`, or original-file mutation.

## File Structure

- Modify: `skills/mathos-formatting/scripts/mathos_formatting_core.py`
  - Add learning dataclasses, artifact/workdir helpers, TOC/H1 sample extraction, run-state writing, heading protection, and provider-learning orchestration.
- Modify: `skills/mathos-formatting/scripts/mathos_formatting.py`
  - Add `learn-from-provider` CLI command.
- Modify: `skills/mathos-formatting/scripts/mathos_provider.py`
  - Add fakeable provider call surface if needed by tests.
- Modify: `skills/mathos-formatting/agents/heading_rules_prompt.md`
  - Clarify that heading rules must be inferred from a TOC-containing sample.
- Modify: `skills/mathos-formatting/agents/content_cleaner_prompt.md`
  - Clarify image/text-only cleanup and no heading edits.
- Modify: `skills/mathos-formatting/SKILL.md`
  - Document `learn-from-provider`.
- Modify: `skills/mathos-formatting/README.md`
  - Document the two-stage provider learning flow.
- Modify: `tests/test_mathos_formatting.py`
  - Add tests for samples, state, failures, heading protection, successful provider learning, and CLI JSON.

## Task 1: Add Learning State And Artifact Helpers

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_formatting_core.py`
- Test: `tests/test_mathos_formatting.py`

- [ ] **Step 1: Write failing tests for workdir and run-state helpers**

Append these tests to `tests/test_mathos_formatting.py`:

```python
def test_learning_work_dir_defaults_to_nested_source_stem(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text("# 目录\n\n# 第一章 …… 1\n", encoding="utf-8")

    path = core.learning_work_dir_for(markdown)

    assert path == tmp_path / ".mathos-formatting" / "book"


def test_write_learning_state_records_error_without_secrets(tmp_path):
    work_dir = tmp_path / ".mathos-formatting" / "book"
    state = core.LearningRunState(
        source_path=tmp_path / "book.md",
        candidate_path=work_dir / "candidate.md",
        provider_base_url="https://api.deepseek.com",
        provider_model="deepseek-chat",
        stage="heading-provider",
        status="failed",
        artifacts={"toc_sample": work_dir / "toc_sample.md"},
        warnings=["sample warning"],
        errors=["TOC not found"],
        approved=False,
    )

    state_path = core.write_learning_state(work_dir, state)

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["stage"] == "heading-provider"
    assert payload["errors"] == ["TOC not found"]
    assert payload["artifacts"]["toc_sample"].endswith("toc_sample.md")
    assert "api_key" not in state_path.read_text(encoding="utf-8").lower()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_learning_work_dir_defaults_to_nested_source_stem tests/test_mathos_formatting.py::test_write_learning_state_records_error_without_secrets -v
```

Expected: FAIL with `AttributeError` for `learning_work_dir_for` or `LearningRunState`.

- [ ] **Step 3: Implement learning state helpers**

Add this near the existing dataclasses in `mathos_formatting_core.py`:

```python
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
```

Add these helper functions after `candidate_path_for`:

```python
def learning_work_dir_for(markdown_path: Path) -> Path:
    return markdown_path.parent / ".mathos-formatting" / markdown_path.stem


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
    }
    state_path = work_dir / "run-state.json"
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return state_path
```

- [ ] **Step 4: Run helper tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_learning_work_dir_defaults_to_nested_source_stem tests/test_mathos_formatting.py::test_write_learning_state_records_error_without_secrets -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add skills/mathos-formatting/scripts/mathos_formatting_core.py tests/test_mathos_formatting.py
git commit -m "feat: add formatting learning run state"
```

## Task 2: Add TOC Sample Extraction

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_formatting_core.py`
- Test: `tests/test_mathos_formatting.py`

- [ ] **Step 1: Write failing tests for TOC sample extraction**

Append:

```python
def test_extract_toc_sample_requires_detected_toc():
    markdown = "# 第一章\n\n正文\n"
    structure = core.extract_structure(markdown, "no-toc.md")

    with pytest.raises(core.FormattingError, match="TOC not found"):
        core.extract_toc_sample(markdown, structure)


def test_extract_toc_sample_contains_toc_and_heading_context():
    markdown = """# 数学

# 目录

# 第一章 分数乘法 …… 1
1.1 分数乘整数 …… 2

# 第一章 分数乘法

正文
"""
    structure = core.extract_structure(markdown, "book.md")

    sample = core.extract_toc_sample(markdown, structure)

    assert "# 目录" in sample
    assert "1.1 分数乘整数" in sample
    assert "# 第一章 分数乘法" in sample
    assert sample.index("# 目录") < sample.index("# 第一章 分数乘法")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_extract_toc_sample_requires_detected_toc tests/test_mathos_formatting.py::test_extract_toc_sample_contains_toc_and_heading_context -v
```

Expected: FAIL with missing `extract_toc_sample`.

- [ ] **Step 3: Implement TOC sample extraction**

Add after `extract_structure` helpers or before provider-learning orchestration:

```python
def extract_toc_sample(markdown: str, structure: MarkdownStructure, max_following_lines: int = 80) -> str:
    if structure.toc_block is None:
        raise FormattingError("TOC not found")
    lines = markdown.splitlines()
    start_index = max(structure.toc_block.start_line - 1, 0)
    end_index = min(len(lines), structure.toc_block.end_line + max_following_lines)
    sample_lines = lines[start_index:end_index]
    return "\n".join(sample_lines).strip() + "\n"
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_extract_toc_sample_requires_detected_toc tests/test_mathos_formatting.py::test_extract_toc_sample_contains_toc_and_heading_context -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add skills/mathos-formatting/scripts/mathos_formatting_core.py tests/test_mathos_formatting.py
git commit -m "feat: extract toc samples for formatting learning"
```

## Task 3: Add H1 Sample Extraction From Updated Candidate

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_formatting_core.py`
- Test: `tests/test_mathos_formatting.py`

- [ ] **Step 1: Write failing H1 extraction tests**

Append:

```python
def test_extract_h1_sample_uses_requested_h1_section():
    markdown = """# 第一章

正文一

# 第二章

正文二
"""
    structure = core.extract_structure(markdown, "candidate.md")

    sample = core.extract_h1_sample(markdown, structure, h1_index=1)

    assert sample.startswith("# 第二章")
    assert "正文二" in sample
    assert "正文一" not in sample


def test_extract_h1_sample_rejects_missing_h1():
    markdown = "正文\n"
    structure = core.extract_structure(markdown, "candidate.md")

    with pytest.raises(core.FormattingError, match="H1 section not found"):
        core.extract_h1_sample(markdown, structure, h1_index=0)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_extract_h1_sample_uses_requested_h1_section tests/test_mathos_formatting.py::test_extract_h1_sample_rejects_missing_h1 -v
```

Expected: FAIL with missing `extract_h1_sample`.

- [ ] **Step 3: Implement H1 sample extraction**

Add:

```python
def extract_h1_sample(markdown: str, structure: MarkdownStructure, h1_index: int = 0) -> str:
    if h1_index < 0 or h1_index >= len(structure.h1_sections):
        raise FormattingError("H1 section not found")
    return structure.h1_sections[h1_index].text.strip() + "\n"
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_extract_h1_sample_uses_requested_h1_section tests/test_mathos_formatting.py::test_extract_h1_sample_rejects_missing_h1 -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add skills/mathos-formatting/scripts/mathos_formatting_core.py tests/test_mathos_formatting.py
git commit -m "feat: extract h1 samples for formatting learning"
```

## Task 4: Protect Headings During Content Cleaner Runs

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_formatting_core.py`
- Test: `tests/test_mathos_formatting.py`

- [ ] **Step 1: Write failing heading protection tests**

Append:

```python
def test_run_content_plugin_rejects_heading_changes(tmp_path):
    plugin_path = tmp_path / "bad_cleaner.py"
    plugin_path.write_text(
        '''
PLUGIN_ID = "bad_cleaner"
PLUGIN_VERSION = "1.0.0"

def analyze(markdown: str) -> dict:
    return {"summary": [], "warnings": []}

def clean(markdown: str) -> str:
    return markdown.replace("# 第一章", "# Changed")
''',
        encoding="utf-8",
    )
    plugin = core.load_safe_plugin(plugin_path)
    markdown = "# 第一章\n\n正文\n"

    with pytest.raises(core.FormattingError, match="content cleaner modified heading lines"):
        core.run_content_plugin_protecting_headings(plugin, markdown)


def test_run_content_plugin_allows_text_changes(tmp_path):
    plugin_path = tmp_path / "text_cleaner.py"
    plugin_path.write_text(
        '''
PLUGIN_ID = "text_cleaner"
PLUGIN_VERSION = "1.0.0"

def analyze(markdown: str) -> dict:
    return {"summary": ["normalized spaces"], "warnings": []}

def clean(markdown: str) -> str:
    return markdown.replace("a  b", "a b")
''',
        encoding="utf-8",
    )
    plugin = core.load_safe_plugin(plugin_path)

    result = core.run_content_plugin_protecting_headings(plugin, "# 第一章\n\na  b\n")

    assert result.cleaned_markdown == "# 第一章\n\na b\n"
    assert result.summary == ["normalized spaces"]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_run_content_plugin_rejects_heading_changes tests/test_mathos_formatting.py::test_run_content_plugin_allows_text_changes -v
```

Expected: FAIL with missing `run_content_plugin_protecting_headings`.

- [ ] **Step 3: Implement heading comparison helper**

Add:

```python
def _heading_lines(markdown: str) -> list[str]:
    return [
        line.rstrip("\r\n")
        for line in markdown.splitlines()
        if HEADING_RE.match(line)
    ]


def run_content_plugin_protecting_headings(plugin: ModuleType, markdown: str) -> PluginResult:
    before_headings = _heading_lines(markdown)
    result = run_plugin(plugin, markdown)
    after_headings = _heading_lines(result.cleaned_markdown)
    if before_headings != after_headings:
        raise FormattingError("content cleaner modified heading lines")
    return result
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_run_content_plugin_rejects_heading_changes tests/test_mathos_formatting.py::test_run_content_plugin_allows_text_changes -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add skills/mathos-formatting/scripts/mathos_formatting_core.py tests/test_mathos_formatting.py
git commit -m "feat: protect headings during content cleanup"
```

## Task 5: Add Provider Learning Orchestration With Fake Provider

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_formatting_core.py`
- Test: `tests/test_mathos_formatting.py`

- [ ] **Step 1: Write failing successful learning test**

Append:

```python
class FakeFormattingProvider:
    base_url = "https://fake.deepseek.local"
    model = "deepseek-test"

    def __init__(self):
        self.calls = []

    def chat(self, system_prompt: str, user_payload: str, timeout_seconds: int = 120) -> str:
        self.calls.append((system_prompt, user_payload, timeout_seconds))
        if "Heading Rules Prompt" in system_prompt:
            return json.dumps(
                {
                    "rules": [
                        {
                            "id": "toc_chapter",
                            "pattern": r"^# (第一章 .+?)(?: …… \d+)?$",
                            "replacement": r"# \1",
                            "flags": ["MULTILINE"],
                        },
                        {
                            "id": "section_heading",
                            "pattern": r"^1\\.1 (.+)$",
                            "replacement": r"## 1.1 \1",
                            "flags": ["MULTILINE"],
                        },
                    ]
                },
                ensure_ascii=False,
            )
        return """```python
PLUGIN_ID = "image_text_cleaner"
PLUGIN_VERSION = "1.0.0"

def analyze(markdown: str) -> dict:
    return {"summary": ["normalized image alt text"], "warnings": []}

def clean(markdown: str) -> str:
    return markdown.replace("![](images/a.png)", "![figure](images/a.png)")
```"""


def test_run_learning_from_provider_writes_artifacts_and_keeps_original(tmp_path):
    markdown = tmp_path / "book.md"
    original_text = SAMPLE_MARKDOWN
    markdown.write_text(original_text, encoding="utf-8")
    provider_client = FakeFormattingProvider()

    result = core.run_learning_from_provider(
        markdown_path=markdown,
        provider_client=provider_client,
        heading_prompt="# Heading Rules Prompt",
        content_prompt="# Content Cleaner Prompt",
        work_dir=tmp_path / ".mathos-formatting" / "book",
    )

    assert result.status == "candidate-written"
    assert markdown.read_text(encoding="utf-8") == original_text
    assert result.candidate_path.exists()
    assert result.report_path.exists()
    assert (result.work_dir / "toc_sample.md").exists()
    assert (result.work_dir / "heading_rules_response.json").exists()
    assert (result.work_dir / "heading_rules.json").exists()
    assert (result.work_dir / "h1_sample.md").exists()
    assert (result.work_dir / "content_cleaner_response.py").exists()
    assert (result.work_dir / "content_cleaner.py").exists()
    assert (result.work_dir / "run-state.json").exists()
    candidate_text = result.candidate_path.read_text(encoding="utf-8")
    assert "![figure](images/a.png)" in candidate_text
    assert len(provider_client.calls) == 2
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_run_learning_from_provider_writes_artifacts_and_keeps_original -v
```

Expected: FAIL with missing `run_learning_from_provider`.

- [ ] **Step 3: Add learning result dataclass**

Add near `CandidateRunResult`:

```python
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
```

- [ ] **Step 4: Add provider prompt payload helpers**

Add:

```python
def _write_text_artifact(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _provider_identity(provider_client: object) -> tuple[str, str]:
    return (
        str(getattr(provider_client, "base_url", "")),
        str(getattr(provider_client, "model", "")),
    )
```

- [ ] **Step 5: Implement `run_learning_from_provider`**

Add:

```python
def run_learning_from_provider(
    markdown_path: Path,
    provider_client: object,
    heading_prompt: str,
    content_prompt: str,
    work_dir: Path | None = None,
    timeout_seconds: int = 120,
    h1_index: int = 0,
) -> LearningRunResult:
    markdown_path = markdown_path.resolve()
    work_dir = work_dir or learning_work_dir_for(markdown_path)
    candidate_path = learning_candidate_path_for(markdown_path, work_dir)
    report_path = work_dir / "candidate-report.md"
    artifacts: dict[str, Path] = {}
    warnings: list[str] = []
    errors: list[str] = []
    provider_base_url, provider_model = _provider_identity(provider_client)

    def state(stage: str, status: str) -> None:
        write_learning_state(
            work_dir,
            LearningRunState(
                source_path=markdown_path,
                candidate_path=candidate_path,
                provider_base_url=provider_base_url,
                provider_model=provider_model,
                stage=stage,
                status=status,
                artifacts=artifacts,
                warnings=warnings,
                errors=errors,
                approved=False,
            ),
        )

    try:
        original_text = markdown_path.read_text(encoding="utf-8")
        original_structure = extract_structure(original_text, str(markdown_path))
        toc_sample = extract_toc_sample(original_text, original_structure)
        artifacts["toc_sample"] = _write_text_artifact(work_dir / "toc_sample.md", toc_sample)
        artifacts["heading_prompt"] = _write_text_artifact(work_dir / "heading_rules_prompt.md", heading_prompt)
        heading_response = provider_client.chat(heading_prompt, toc_sample, timeout_seconds=timeout_seconds)
        artifacts["heading_response"] = _write_text_artifact(work_dir / "heading_rules_response.json", heading_response)
        heading_payload = json.loads(heading_response)
        rules = validate_heading_rules(heading_payload)
        artifacts["heading_rules"] = _write_text_artifact(
            work_dir / "heading_rules.json",
            json.dumps(heading_payload, ensure_ascii=False, indent=2),
        )

        work_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(markdown_path, candidate_path)
        stage1_text = apply_heading_rules(candidate_path.read_text(encoding="utf-8"), rules)
        candidate_path.write_text(stage1_text, encoding="utf-8")
        artifacts["stage1_report"] = write_review_report(
            original_path=markdown_path,
            candidate_path=candidate_path,
            report_path=work_dir / "stage1_heading_report.md",
            heading_summary=[rule.rule_id for rule in rules],
            plugin_summary=[],
            warnings=[],
        )

        updated_structure = extract_structure(stage1_text, str(candidate_path))
        h1_sample = extract_h1_sample(stage1_text, updated_structure, h1_index=h1_index)
        artifacts["h1_sample"] = _write_text_artifact(work_dir / "h1_sample.md", h1_sample)
        artifacts["content_prompt"] = _write_text_artifact(work_dir / "content_cleaner_prompt.md", content_prompt)
        content_response = provider_client.chat(content_prompt, h1_sample, timeout_seconds=timeout_seconds)
        artifacts["content_response"] = _write_text_artifact(work_dir / "content_cleaner_response.py", content_response)
        plugin_source = parse_python_artifact_from_text(content_response)
        artifacts["content_cleaner"] = _write_text_artifact(work_dir / "content_cleaner.py", plugin_source)
        plugin = load_safe_plugin(artifacts["content_cleaner"])
        plugin_result = run_content_plugin_protecting_headings(plugin, stage1_text)
        candidate_path.write_text(plugin_result.cleaned_markdown, encoding="utf-8")
        artifacts["candidate"] = candidate_path
        artifacts["report"] = write_review_report(
            original_path=markdown_path,
            candidate_path=candidate_path,
            report_path=report_path,
            heading_summary=[rule.rule_id for rule in rules],
            plugin_summary=plugin_result.summary,
            warnings=plugin_result.warnings,
        )
        warnings.extend(plugin_result.warnings)
        state("complete", "candidate-written")
        return LearningRunResult("candidate-written", work_dir, candidate_path, report_path, artifacts, plugin_result.summary, warnings, errors)
    except Exception as exc:
        errors.append(str(exc))
        state("failed", "failed")
        raise
```

This function references `parse_python_artifact_from_text`; the parser is defined in core so provider-learning orchestration can validate plugin text without importing the CLI module.

- [ ] **Step 6: Add temporary parser shim in core**

Add:

```python
def parse_python_artifact_from_text(text: str) -> str:
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:python)?\s*(.*?)```", stripped, flags=re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    if "def clean(" not in stripped or "def analyze(" not in stripped:
        raise FormattingError("python artifact must define analyze() and clean()")
    return stripped
```

This parser keeps Task 5 self-contained and uses the same validation behavior expected from provider Python artifacts.

- [ ] **Step 7: Run successful learning test**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_run_learning_from_provider_writes_artifacts_and_keeps_original -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add skills/mathos-formatting/scripts/mathos_formatting_core.py tests/test_mathos_formatting.py
git commit -m "feat: run formatting learning with provider client"
```

## Task 6: Add Fail-Closed Learning Behavior

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_formatting_core.py`
- Test: `tests/test_mathos_formatting.py`

- [ ] **Step 1: Write failing tests for TOC and heading mutation failures**

Append:

```python
class CountingProvider:
    base_url = "https://fake.deepseek.local"
    model = "deepseek-test"

    def __init__(self):
        self.calls = 0

    def chat(self, system_prompt: str, user_payload: str, timeout_seconds: int = 120) -> str:
        self.calls += 1
        return "{}"


def test_learning_without_toc_stops_before_provider_and_candidate(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text("# 第一章\n\n正文\n", encoding="utf-8")
    provider_client = CountingProvider()
    work_dir = tmp_path / ".mathos-formatting" / "book"

    with pytest.raises(core.FormattingError, match="TOC not found"):
        core.run_learning_from_provider(
            markdown,
            provider_client,
            heading_prompt="# Heading Rules Prompt",
            content_prompt="# Content Cleaner Prompt",
            work_dir=work_dir,
        )

    assert provider_client.calls == 0
    assert not (work_dir / "candidate.md").exists()
    state = json.loads((work_dir / "run-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "failed"
    assert state["stage"] == "toc-sample"
    assert state["errors"] == ["TOC not found"]


class HeadingMutatingProvider(FakeFormattingProvider):
    def chat(self, system_prompt: str, user_payload: str, timeout_seconds: int = 120) -> str:
        if "Heading Rules Prompt" in system_prompt:
            return super().chat(system_prompt, user_payload, timeout_seconds)
        return """```python
PLUGIN_ID = "bad_heading_cleaner"
PLUGIN_VERSION = "1.0.0"

def analyze(markdown: str) -> dict:
    return {"summary": [], "warnings": []}

def clean(markdown: str) -> str:
    return markdown.replace("# 第一章", "# Changed")
```"""


def test_learning_restores_stage1_candidate_when_content_changes_heading(tmp_path):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    work_dir = tmp_path / ".mathos-formatting" / "book"

    with pytest.raises(core.FormattingError, match="content cleaner modified heading lines"):
        core.run_learning_from_provider(
            markdown,
            HeadingMutatingProvider(),
            heading_prompt="# Heading Rules Prompt",
            content_prompt="# Content Cleaner Prompt",
            work_dir=work_dir,
        )

    candidate_text = (work_dir / "candidate.md").read_text(encoding="utf-8")
    assert "# Changed" not in candidate_text
    state = json.loads((work_dir / "run-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "failed"
    assert state["stage"] == "stage2-apply"
```

- [ ] **Step 2: Run tests and verify current failures**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_learning_without_toc_stops_before_provider_and_candidate tests/test_mathos_formatting.py::test_learning_restores_stage1_candidate_when_content_changes_heading -v
```

Expected: FAIL because `run-state.json` does not yet record precise failed stages `toc-sample` and `stage2-apply`.

- [ ] **Step 3: Improve failure stage tracking and restore behavior**

Modify `run_learning_from_provider`:

```python
    current_stage = "inspect"

    def state(stage: str | None, status: str) -> None:
        write_learning_state(
            work_dir,
            LearningRunState(
                source_path=markdown_path,
                candidate_path=candidate_path,
                provider_base_url=provider_base_url,
                provider_model=provider_model,
                stage=stage or current_stage,
                status=status,
                artifacts=artifacts,
                warnings=warnings,
                errors=errors,
                approved=False,
            ),
        )
```

Then set `current_stage` before each stage:

```python
        current_stage = "toc-sample"
        toc_sample = extract_toc_sample(original_text, original_structure)
        ...
        current_stage = "heading-provider"
        heading_response = provider_client.chat(...)
        ...
        current_stage = "stage1-apply"
        ...
        current_stage = "h1-sample"
        ...
        current_stage = "content-provider"
        ...
        current_stage = "stage2-apply"
        try:
            plugin_result = run_content_plugin_protecting_headings(plugin, stage1_text)
        except FormattingError:
            candidate_path.write_text(stage1_text, encoding="utf-8")
            raise
```

Update the exception block:

```python
    except Exception as exc:
        if not errors:
            errors.append(str(exc))
        state(None, "failed")
        raise
```

- [ ] **Step 4: Run fail-closed tests**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_learning_without_toc_stops_before_provider_and_candidate tests/test_mathos_formatting.py::test_learning_restores_stage1_candidate_when_content_changes_heading -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add skills/mathos-formatting/scripts/mathos_formatting_core.py tests/test_mathos_formatting.py
git commit -m "fix: fail closed during provider learning"
```

## Task 7: Add Real Provider Client Adapter

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_provider.py`
- Modify: `skills/mathos-formatting/scripts/mathos_formatting.py`
- Test: `tests/test_mathos_formatting.py`

- [ ] **Step 1: Write failing provider client test**

Append:

```python
def test_provider_client_exposes_redacted_identity(monkeypatch):
    settings = provider.ProviderSettings(
        api_key="secret-value",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
    )
    client = provider.DeepSeekProviderClient(settings)

    assert client.base_url == "https://api.deepseek.com"
    assert client.model == "deepseek-chat"
    assert "secret-value" not in repr(client)
```

- [ ] **Step 2: Run provider client test and verify it fails**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_provider_client_exposes_redacted_identity -v
```

Expected: FAIL with missing `DeepSeekProviderClient`.

- [ ] **Step 3: Implement provider client wrapper**

Add to `mathos_provider.py`:

```python
@dataclass(frozen=True)
class DeepSeekProviderClient:
    settings: ProviderSettings

    @property
    def base_url(self) -> str:
        return self.settings.base_url

    @property
    def model(self) -> str:
        return self.settings.model

    def __repr__(self) -> str:
        return f"DeepSeekProviderClient(base_url={self.base_url!r}, model={self.model!r})"

    def chat(self, system_prompt: str, user_payload: str, timeout_seconds: int = 120) -> str:
        return call_deepseek_chat(self.settings, system_prompt, user_payload, timeout_seconds)
```

- [ ] **Step 4: Run provider client test**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_provider_client_exposes_redacted_identity -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add skills/mathos-formatting/scripts/mathos_provider.py tests/test_mathos_formatting.py
git commit -m "feat: add deepseek provider client"
```

## Task 8: Add `learn-from-provider` CLI Command

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_formatting.py`
- Test: `tests/test_mathos_formatting.py`

- [ ] **Step 1: Write failing CLI smoke test using fake provider monkeypatch**

Append:

```python
def test_cli_learn_from_provider_outputs_json_with_env(tmp_path, monkeypatch):
    markdown = tmp_path / "book.md"
    markdown.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text("DEEPSEEK_API_KEY=secret\nDEEPSEEK_MODEL=deepseek-chat\n", encoding="utf-8")

    fake_cli = importlib.util.spec_from_file_location("mathos_formatting_cli_test", CLI_PATH)
    cli = importlib.util.module_from_spec(fake_cli)
    assert fake_cli.loader is not None
    sys.modules["mathos_formatting_cli_test"] = cli
    fake_cli.loader.exec_module(cli)

    class CliFakeProvider(FakeFormattingProvider):
        pass

    monkeypatch.setattr(cli.provider, "DeepSeekProviderClient", lambda settings: CliFakeProvider())

    exit_code = cli.main([
        "learn-from-provider",
        str(markdown),
        "--env",
        str(env_path),
        "--work-dir",
        str(tmp_path / ".mathos-formatting" / "book"),
    ])

    assert exit_code == 0
    assert (tmp_path / ".mathos-formatting" / "book" / "candidate.md").exists()
```

- [ ] **Step 2: Run CLI smoke test and verify it fails**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_cli_learn_from_provider_outputs_json_with_env -v
```

Expected: FAIL with missing CLI command or missing `provider` import.

- [ ] **Step 3: Import provider module in CLI**

In `mathos_formatting.py`, after `import mathos_formatting_core as core`, add:

```python
import mathos_provider as provider
```

- [ ] **Step 4: Add command implementation**

Add:

```python
def command_learn_from_provider(args: argparse.Namespace) -> int:
    settings = provider.load_provider_settings(Path(args.env))
    provider_client = provider.DeepSeekProviderClient(settings)
    heading_prompt = (SCRIPT_DIR.parent / "agents" / "heading_rules_prompt.md").read_text(encoding="utf-8")
    content_prompt = (SCRIPT_DIR.parent / "agents" / "content_cleaner_prompt.md").read_text(encoding="utf-8")
    result = core.run_learning_from_provider(
        markdown_path=Path(args.markdown),
        provider_client=provider_client,
        heading_prompt=heading_prompt,
        content_prompt=content_prompt,
        work_dir=Path(args.work_dir) if args.work_dir else None,
        timeout_seconds=args.timeout_seconds,
        h1_index=args.h1_index,
    )
    _print_json(
        {
            "status": result.status,
            "work_dir": str(result.work_dir),
            "candidate_path": str(result.candidate_path),
            "report_path": str(result.report_path),
            "summary": result.summary,
            "warnings": result.warnings,
            "errors": result.errors,
        }
    )
    return 0
```

- [ ] **Step 5: Add parser block**

Inside `build_parser()` add:

```python
    learn_parser = subparsers.add_parser("learn-from-provider", help="Learn heading and content cleanup artifacts through DeepSeek")
    learn_parser.add_argument("markdown")
    learn_parser.add_argument("--env", required=True)
    learn_parser.add_argument("--work-dir")
    learn_parser.add_argument("--timeout-seconds", type=int, default=120)
    learn_parser.add_argument("--h1-index", type=int, default=0)
    learn_parser.set_defaults(func=command_learn_from_provider)
```

- [ ] **Step 6: Run CLI smoke test**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_cli_learn_from_provider_outputs_json_with_env -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add skills/mathos-formatting/scripts/mathos_formatting.py tests/test_mathos_formatting.py
git commit -m "feat: add provider learning cli"
```

## Task 9: Update Prompts And Skill Documentation

**Files:**
- Modify: `skills/mathos-formatting/agents/heading_rules_prompt.md`
- Modify: `skills/mathos-formatting/agents/content_cleaner_prompt.md`
- Modify: `skills/mathos-formatting/SKILL.md`
- Modify: `skills/mathos-formatting/README.md`
- Test: `tests/test_mathos_formatting.py`

- [ ] **Step 1: Write failing docs test**

Append:

```python
def test_provider_learning_docs_name_toc_h1_and_heading_protection():
    heading_prompt = (SKILL_ROOT / "agents" / "heading_rules_prompt.md").read_text(encoding="utf-8")
    content_prompt = (SKILL_ROOT / "agents" / "content_cleaner_prompt.md").read_text(encoding="utf-8")
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    readme_text = (SKILL_ROOT / "README.md").read_text(encoding="utf-8")
    combined = "\n".join([heading_prompt, content_prompt, skill_text, readme_text]).lower()

    assert "learn-from-provider" in combined
    assert "toc" in combined or "table of contents" in combined
    assert "complete h1" in combined
    assert "image/text" in combined
    assert "must not modify heading" in combined
```

- [ ] **Step 2: Run docs test and verify it fails**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_provider_learning_docs_name_toc_h1_and_heading_protection -v
```

Expected: FAIL on missing wording.

- [ ] **Step 3: Update heading prompt**

Append to `agents/heading_rules_prompt.md`:

```markdown
The input sample must contain a table of contents. If the sample does not contain a TOC, return JSON with an empty `rules` list and a note explaining that a TOC is required.

Use the TOC to infer the intended heading hierarchy. Return deterministic regex rules only; do not include prose outside JSON.
```

- [ ] **Step 4: Update content prompt**

Append to `agents/content_cleaner_prompt.md`:

```markdown
The input sample is one complete H1 section after heading normalization. The cleaner is for image/text formatting only and must not modify heading lines.
```

- [ ] **Step 5: Update skill doc and README**

Add `learn-from-provider` to `SKILL.md` and `README.md` with this wording:

```markdown
`learn-from-provider` performs the two-stage DeepSeek learning workflow: TOC sample to heading rules, then complete H1 sample to image/text cleaner. It stops when TOC is not found and writes only candidate backups and learning artifacts.
```

- [ ] **Step 6: Run docs test**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py::test_provider_learning_docs_name_toc_h1_and_heading_protection -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add skills/mathos-formatting/agents/heading_rules_prompt.md skills/mathos-formatting/agents/content_cleaner_prompt.md skills/mathos-formatting/SKILL.md skills/mathos-formatting/README.md tests/test_mathos_formatting.py
git commit -m "docs: document provider learning workflow"
```

## Task 10: Final Verification

**Files:**
- Modify: none unless verification reveals issues
- Test: `tests/test_mathos_formatting.py`

- [ ] **Step 1: Run formatter test file**

Run:

```powershell
python -m pytest tests/test_mathos_formatting.py -v
```

Expected: all tests PASS.

- [ ] **Step 2: Run full repository tests**

Run:

```powershell
python -m pytest -q
```

Expected: all tests PASS.

- [ ] **Step 3: Compile scripts**

Run:

```powershell
python -m py_compile skills/mathos-formatting/scripts/mathos_formatting.py skills/mathos-formatting/scripts/mathos_formatting_core.py skills/mathos-formatting/scripts/mathos_provider.py
```

Expected: command exits 0.

- [ ] **Step 4: Check git diff**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; only intentional files are modified.

- [ ] **Step 5: Commit verification fixes if needed**

If verification required fixes, commit them:

```powershell
git add skills/mathos-formatting tests/test_mathos_formatting.py
git commit -m "fix: finalize provider learning workflow"
```

If no fixes were needed, do not create an empty commit.

## Self-Review Checklist

Spec coverage:

- TOC-required stage 1 is covered by Tasks 2, 5, 6, and 8.
- Stage 1 provider call, response saving, rule validation, and candidate mutation are covered by Task 5.
- Stage 2 H1 sampling from the updated candidate is covered by Tasks 3 and 5.
- Stage 2 image/text-only safety and heading protection are covered by Task 4 and Task 6.
- Artifact layout and `run-state.json` are covered by Task 1 and Task 5.
- CLI JSON and provider settings are covered by Tasks 7 and 8.
- Docs and prompts are covered by Task 9.
- Final verification is covered by Task 10.

Placeholder scan:

- This plan contains no red-flag markers or unspecified implementation steps.

Type consistency:

- `LearningRunState`, `LearningRunResult`, and helper names are introduced before later tasks use them.
- Provider clients expose `base_url`, `model`, and `chat()`.
- CLI uses `provider.DeepSeekProviderClient` and `core.run_learning_from_provider`.
