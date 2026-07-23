# In-Place Recursive Shear Segmentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modify `mathos_segmentation_stage1.py` to recursively split textbooks by shearing H1, H2, and H3 headings into a subfolder while preserving all intermediate text (prefaces, intros) and overwriting the source textbook in-place as the master note containing only the preface and top-level links.

**Architecture:** We will define `body_end` for each heading node using the start index of its first child heading (or next sibling/parent boundary if a leaf). Non-leaf nodes and the master root note will render their text slices from start to `body_end`, followed by Wikilinks of their immediate children. The master file will write to the original source path, while child files will write flatly inside the sandbox subfolder.

**Tech Stack:** Python, pytest.

---

### Task 1: Update DirectoryNode Data Structure and Path Configurations

**Files:**
- Modify: [mathos_segmentation_stage1.py](file:///c:/Mathematics-Knowledge/Mathematics-Knowledge-code/skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py)

- [ ] **Step 1: Add body_end property to DirectoryNode**
  Update `DirectoryNode` to dynamically find the end index of its body block:
  ```python
  @property
  def body_end(self) -> int:
      if self.children:
          return self.children[0].raw_start
      return self.raw_end
  ```

- [ ] **Step 2: Update master note path definition to source_path**
  In `build_segmentation_plan`, change:
  ```python
  master_path = source_path
  ```
  And update all related references to ensure the master directory note overwrites the source file directly.

### Task 2: Implement Preservation Rendering for Non-Leaf and Master Directory Notes

**Files:**
- Modify: [mathos_segmentation_stage1.py](file:///c:/Mathematics-Knowledge/Mathematics-Knowledge-code/skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py)

- [ ] **Step 1: Rewrite render_directory_note to preserve body text**
  ```python
  def render_directory_note(node: DirectoryNode, markdown: str) -> str:
      if node.is_leaf:
          raise SegmentationError(f"Cannot render leaf as directory note: {node.note_stem}")
      body = markdown[node.raw_start:node.body_end]
      links = [f"- [[{link_for_node(child)}]]" for child in node.children]
      return f"{body.rstrip()}\n\n" + "\n".join(links) + "\n"
  ```

- [ ] **Step 2: Rewrite render_master_directory to preserve book preface**
  ```python
  def render_master_directory(plan: SegmentationPlan, markdown: str) -> str:
      preface_end = plan.top_level_nodes[0].raw_start if plan.top_level_nodes else len(markdown)
      preface = markdown[0:preface_end]
      links = [f"- [[{link_for_node(node)}]]" for node in plan.top_level_nodes]
      return f"{preface.rstrip()}\n\n" + "\n".join(links) + "\n"
  ```

- [ ] **Step 3: Update write_segmentation_package call signature**
  Pass the `markdown` string to `render_directory_note` and `render_master_directory` in `write_segmentation_package`.

### Task 3: Adjust Verification Logic for In-Place Master File

**Files:**
- Modify: [mathos_segmentation_stage1.py](file:///c:/Mathematics-Knowledge/Mathematics-Knowledge-code/skills/mathos-segmentation-stage1/scripts/mathos_segmentation_stage1.py)

- [ ] **Step 1: Modify verify_package file count checks**
  Adjust the glob count verification to account for `master_path` being outside the `sandbox_dir`.
  ```python
  expected_files = {plan.master_path.resolve()} | {node.output_path.resolve() for node in plan.nodes}
  actual_files = {p.resolve() for p in plan.sandbox_dir.glob("*.md")}
  if plan.master_path.resolve().parent != plan.sandbox_dir.resolve():
      if plan.master_path.exists():
          actual_files.add(plan.master_path.resolve())
  ```

- [ ] **Step 2: Disable source file hash check in write verification if in-place**
  Since writing the package modifies the source file, verify hash immediately before write, but avoid checking original hash against modified file during post-write validation.

### Task 4: Test and Execute the Segmentation on All Textbooks

**Files:**
- Run commands on the textbook directories.

- [ ] **Step 1: Run plan on textbook 2 and verify no error**
  Run:
  ```powershell
  python .\skills\mathos-segmentation-stage1\scripts\mathos_segmentation_stage1.py plan "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\高中\课本\【人教版】高中必修 第二册数学电子课本.md" --vault-root "C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map" --yes
  ```

- [ ] **Step 2: Run segment on all 5 textbooks and confirm output files and preface preservation**
  Ensure all chapters and prefaces are correctly generated and the source files are rewritten in-place.
