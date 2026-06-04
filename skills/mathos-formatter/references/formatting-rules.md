# Formatting Rules Reference

## Package Paths

- CLI: `src/mathos/formatter/cli.py`
- Shared rules: `src/mathos/formatter/core.py`
- Textbook rules: `src/mathos/formatter/textbook.py`
- Current formatter implementations: `src/mathos/formatter/textbook.py`, `src/mathos/formatter/renjiao_highschool_textbook.py`

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
- Current discovered modes are `textbook` and `renjiao-highschool-textbook`.
- Large knowledge-base directories can contain thousands of files. Keep target paths narrow during validation.
