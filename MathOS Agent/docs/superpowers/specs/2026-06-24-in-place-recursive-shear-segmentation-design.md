# In-Place Recursive Shear Segmentation Design

This document details the design for modifying `mathos_segmentation_stage1.py` to use an **In-Place Recursive Shear** algorithm for textbook splitting.

## Goal

To split formatted long Markdown textbooks into atomic notes inside an Obsidian vault without discarding any preface, chapter introductions, section summaries, or text between headings. The root file of the textbook is updated in-place to act as the master index containing its preface and links to H1 chapters.

## Proposed Algorithm Changes

### 1. Definition of Node Body (Preserving Content)

Instead of identifying "directory nodes" and replacing their contents with `# 目录` and links, we define the **Body** of each node (including the root node):

- **Root Node (Book master note)**:
  - `start_index = 0`
  - `body_end_index = first_H1_heading.char_start` (if H1 headings exist, otherwise end of file).
- **Subheading Nodes (H1, H2, H3)**:
  - `start_index = heading.char_start`
  - `body_end_index`:
    - If the node has immediate subheadings (children) of the next level: `first_child_heading.char_start`.
    - If the node is a leaf (no subheadings down to `target-depth`): the next heading's `char_start` of same or higher level (or end of file).

### 2. Output Formatting

For any node `N`:
- If `N` has children `C_1, C_2, ... C_k`:
  - Output Content = `text[N.start_index:N.body_end_index]` + `\n\n` + `- [[C_1]]` + `\n` + `- [[C_2]]` ...
- If `N` has no children:
  - Output Content = `text[N.start_index:N.body_end_index]` (which contains the entire raw text of that node's subtree).

### 3. File Paths and In-Place Overwrite

- **Master File (Root)**:
  - Overwritten in-place at the original source file path (e.g. `高中\课本\【人教版】高中必修 第二册数学电子课本.md`).
- **Split Subheadings (H1, H2, H3)**:
  - Written to the sandbox folder (e.g. `高中\课本\【人教版】高中必修 第二册数学电子课本\`).
  - Written flatly inside the sandbox folder.
  - Linked via plain Wikilinks (e.g. `[[第七章 复数]]`) since Obsidian automatically resolves unique names flatly.

## Verification Plan

### Automated Tests
- Verification of output structure:
  - File exists checks.
  - Content preservation verification: check that text from the original file matches the concatenation of the split files (re-stitching test).
  - Check that the sum of the byte counts of split files matches or exceeds the original (excluding added wikilink lines).

### Manual Verification
- Inspect the output files in Obsidian.
- Verify Git diff of the master note.
