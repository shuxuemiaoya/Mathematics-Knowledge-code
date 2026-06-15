# Heading Optimization Stage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate a heading optimization stage (Stage 5) into `mathos-formatting` to correct OCR typos and refine heading text semantically using Deepseek.

**Architecture:** We will add a new system prompt file `heading_optimization_prompt.md` under `agents/`. In `mathos_formatting_core.py`, after applying content rules, we will extract all headings, call Deepseek with JSON response format, validate that heading levels are unchanged, apply replacements to the candidate document, and save `heading_optimizations.json`. We will update the `approve` and `apply-approved` functions to support local mapping replay.

**Tech Stack:** Python, pytest, Deepseek API

---

### Task 1: Create Prompt Template File

**Files:**
- Create: `skills/mathos-formatting/agents/heading_optimization_prompt.md`

- [ ] **Step 1: Write heading optimization system prompt**

Create the prompt file with the following content:
```markdown
# Role: 章节标题优化与 OCR 纠错专家

## Profile
* language: JSON
* description: 你是一个 Markdown 标题优化专家，专门纠正教材 Markdown 标题中的 OCR 识别错误并对标题进行合理的语义润色和标化。

## Core Goal
根据输入的 Markdown 标题列表，输出一个 JSON 对象，键为原始标题行，值为优化后的标题行。

## Safety Constraints
1. 绝对不能修改标题层级。如果原始标题是 `## 标题`，优化后必须也是 `## 优化标题`。
2. 绝对不能返回除 JSON 之外的任何解释、说明或包裹代码块。
3. 只能处理由于 OCR 导致的明显拼写错误或乱码（例如将 `ϰο4` 纠正为 `复习参考题 4`，将 `ƽ` 纠正为 `平行`）。

## Expected JSON Schema
```json
{
  "原始标题行": "优化后的标题行"
}
```
```

- [ ] **Step 2: Commit**

```bash
git add skills/mathos-formatting/agents/heading_optimization_prompt.md
git commit -m "feat: add heading optimization prompt template"
```

---

### Task 2: Implement Heading Optimization Logic in Core

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_formatting_core.py`

- [ ] **Step 1: Add helper function `run_heading_optimization`**

Add the helper function above `run_learning_from_provider` in `skills/mathos-formatting/scripts/mathos_formatting_core.py`:
```python
def run_heading_optimization(
    markdown: str,
    provider_client: object,
    prompt: str,
    timeout_seconds: int = 120,
) -> dict[str, str]:
    heading_lines = [line.strip() for line in markdown.splitlines() if line.strip().startswith("#")]
    if not heading_lines:
        return {}

    input_payload = "\n".join(heading_lines)
    try:
        response = provider_client.chat(
            prompt,
            input_payload,
            timeout_seconds=timeout_seconds,
            response_format={"type": "json_object"}
        )
        payload = json.loads(parse_json_artifact_from_text(response))
        validated = {}
        for k, v in payload.items():
            k_strip = k.strip()
            v_strip = v.strip()
            if not k_strip.startswith("#") or not v_strip.startswith("#"):
                continue
            k_level = len(k_strip) - len(k_strip.lstrip("#"))
            v_level = len(v_strip) - len(v_strip.lstrip("#"))
            if k_level == v_level:
                validated[k_strip] = v_strip
        return validated
    except Exception:
        return {}
```

- [ ] **Step 2: Integrate optimization stage in `run_learning_from_provider`**

Modify the end of `run_learning_from_provider` in `skills/mathos-formatting/scripts/mathos_formatting_core.py` (around lines 1664-1688) to run Stage 5:
```python
        current_stage = "stage4-apply"
        try:
            plugin_result = run_content_rules_protecting_headings(content_rules_payload, stripped_text)
        except FormattingError:
            candidate_path.write_text(stripped_text, encoding="utf-8")
            raise

        # Stage 5: Heading Optimization
        current_stage = "heading-optimization-provider"
        heading_opt_prompt_path = Path(__file__).resolve().parent.parent / "agents" / "heading_optimization_prompt.md"
        heading_opt_prompt = heading_opt_prompt_path.read_text(encoding="utf-8")
        artifacts["heading_opt_prompt"] = _write_text_artifact(work_dir / "heading_optimization_prompt.md", heading_opt_prompt)

        opt_mapping = run_heading_optimization(
            plugin_result.cleaned_markdown,
            provider_client,
            heading_opt_prompt,
            timeout_seconds=timeout_seconds
        )

        final_markdown = plugin_result.cleaned_markdown
        if opt_mapping:
            artifacts["heading_optimizations"] = _write_text_artifact(
                work_dir / "heading_optimizations.json",
                json.dumps(opt_mapping, ensure_ascii=False, indent=2)
            )
            opt_lines = final_markdown.splitlines()
            for idx, l in enumerate(opt_lines):
                stripped = l.strip()
                if stripped in opt_mapping:
                    opt_lines[idx] = l.replace(stripped, opt_mapping[stripped])
            final_markdown = "\n".join(opt_lines) + "\n"

        candidate_path.write_text(final_markdown, encoding="utf-8")
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
```

- [ ] **Step 3: Update `apply_approved_program` to apply saved optimizations**

Modify `apply_approved_program` in `skills/mathos-formatting/scripts/mathos_formatting_core.py` to replay `heading_optimizations.json` locally if present:
```python
    # Apply heading optimizations if present
    opt_path = program_dir / "heading_optimizations.json"
    if opt_path.exists():
        opt_mapping = json.loads(opt_path.read_text(encoding="utf-8"))
        opt_lines = cleaned.splitlines()
        for idx, l in enumerate(opt_lines):
            stripped = l.strip()
            if stripped in opt_mapping:
                opt_lines[idx] = l.replace(stripped, opt_mapping[stripped])
        cleaned = "\n".join(opt_lines) + "\n"
```

- [ ] **Step 4: Commit**

```bash
git add skills/mathos-formatting/scripts/mathos_formatting_core.py
git commit -m "feat: implement heading optimization stage and apply logic"
```

---

### Task 3: Update CLI Controller Commands

**Files:**
- Modify: `skills/mathos-formatting/scripts/mathos_formatting.py`

- [ ] **Step 1: Update `command_approve` to propagate optimizations**

Modify `command_approve` in `skills/mathos-formatting/scripts/mathos_formatting.py` to copy `heading_optimizations.json` to the approved root:
```python
def command_approve(args: argparse.Namespace) -> int:
    original = Path(args.original)
    candidate = Path(args.candidate)
    
    # Locate optimizations file in work directory
    work_dir = candidate.parent
    opt_src = work_dir / "heading_optimizations.json"
    
    program_dir = core.save_approved_program(
        approved_root=Path(args.approved_root),
        plugin_id=args.plugin_id,
        heading_rules_path=Path(args.heading_rules),
        plugin_path=Path(args.plugin) if args.plugin else None,
        content_rules_path=Path(args.content_rules) if args.content_rules else None,
        original_path=original,
        candidate_path=candidate,
        summary=args.summary,
    )
    
    if opt_src.exists():
        shutil.copy2(opt_src, program_dir / "heading_optimizations.json")
        print(f"Propagated heading optimizations to approved directory: {program_dir}")
        
    return 0
```

- [ ] **Step 2: Update `command_candidate_from_artifacts` to support manual optimizations**

Update argument parser and implementation of `command_candidate_from_artifacts` in `skills/mathos-formatting/scripts/mathos_formatting.py`:
```python
    # Under command_candidate_from_artifacts:
    # After core.create_candidate_from_artifacts call:
    if hasattr(args, "heading_optimizations") and args.heading_optimizations:
        opt_path = Path(args.heading_optimizations)
        if opt_path.exists():
            candidate_path = core.candidate_path_for(Path(args.markdown))
            cleaned = candidate_path.read_text(encoding="utf-8")
            opt_mapping = json.loads(opt_path.read_text(encoding="utf-8"))
            opt_lines = cleaned.splitlines()
            for idx, l in enumerate(opt_lines):
                stripped = l.strip()
                if stripped in opt_mapping:
                    opt_lines[idx] = l.replace(stripped, opt_mapping[stripped])
            candidate_path.write_text("\n".join(opt_lines) + "\n", encoding="utf-8")
```

Also, update `build_parser` to register `--heading-optimizations` in `candidate_parser`:
```python
    candidate_parser.add_argument("--heading-optimizations")
```

- [ ] **Step 3: Commit**

```bash
git add skills/mathos-formatting/scripts/mathos_formatting.py
git commit -m "feat: propagate heading optimizations in approve and candidate-from-artifacts commands"
```

---

### Task 4: Add Unit Tests

**Files:**
- Modify: `tests/test_mathos_formatting_guarded.py`

- [ ] **Step 1: Add heading optimization test cases**

Add the following tests to the bottom of `tests/test_mathos_formatting_guarded.py`:
```python
class MockOptimizationProvider:
    base_url = "https://fake.deepseek.local"
    model = "deepseek-test"

    def __init__(self, response_json):
        self.response_json = response_json

    def chat(self, system_prompt, user_payload, timeout_seconds=120, response_format=None):
        return self.response_json

def test_heading_optimization_success(tmp_path):
    markdown_text = "# 第一章 数列\n## ϰο4\n正文内容\n"
    markdown_file = tmp_path / "book.md"
    markdown_file.write_text(markdown_text, encoding="utf-8")
    
    provider = MockOptimizationProvider('{"## ϰο4": "## 复习参考题 4"}')
    heading_prompt = "# Headings prompt"
    
    mapping = core.run_heading_optimization(markdown_text, provider, heading_prompt)
    assert mapping == {"## ϰο4": "## 复习参考题 4"}

def test_heading_optimization_level_safety(tmp_path):
    markdown_text = "## ϰο4\n"
    # Mapping to a different level (H1 instead of H2)
    provider = MockOptimizationProvider('{"## ϰο4": "# 复习参考题 4"}')
    heading_prompt = "# Headings prompt"
    
    mapping = core.run_heading_optimization(markdown_text, provider, heading_prompt)
    # Different heading levels should be discarded by validation safety check
    assert mapping == {}
```

- [ ] **Step 2: Run test suite**

Run `pytest` to make sure all 66+ tests pass successfully.
Run: `pytest`
Expected: 68 passed

- [ ] **Step 3: Commit**

```bash
git add tests/test_mathos_formatting_guarded.py
git commit -m "test: add heading optimization success and level safety unit tests"
```

---

### Task 5: Verify the Changes (Dry-Run)

- [ ] **Step 1: Execute `learn-from-provider` on a test document**

Ensure `.env` contains `DEEPSEEK_API_KEY`.
Run:
```powershell
python skills/mathos-formatting/scripts/mathos_formatting.py learn-from-provider "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\【人教版】高中选择性必修 第二册数学电子课本.md" --env "C:\Mathematics-Knowledge\.env"
```
Verify:
1. Output includes: `"status": "candidate-written"`
2. Verify that `C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\test\mathos-formatting\【人教版】高中选择性必修 第二册数学电子课本\heading_optimizations.json` was generated.
3. Verify that `candidate.md` contains the corrected heading `## 复习参考题 4`.
