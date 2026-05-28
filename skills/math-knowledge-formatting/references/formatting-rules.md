# Formatting Rules Reference

## Package Paths

- CLI: `src/math_knowledge_tools/md_formatter/cli.py`
- Shared rules: `src/math_knowledge_tools/md_formatter/core.py`
- Textbook rules: `src/math_knowledge_tools/md_formatter/textbook.py`
- Exercise rules: `src/math_knowledge_tools/md_formatter/exercise.py`

## Safe Run Pattern

Always prefer:

```powershell
mk-format --dir "<target-dir>" --mode "<mode>" --dry-run
```

Then:

```powershell
mk-format --dir "<target-dir>" --mode "<mode>" --backup
```

## Behavior Notes

- `BaseFormatter` removes bold markers, normalizes math-option markers, converts some block math to inline math, fixes common OCR math mistakes, and cleans repeated blank lines.
- `TextbookFormatter` handles Obsidian callouts, textbook headings, examples, figure captions, centered image blocks, and figure tables.
- `ExerciseFormatter` handles question headings, answer and analysis tags, option indentation, and exercise-book variants.
- Large knowledge-base directories can contain thousands of files. Keep target paths narrow during validation.
