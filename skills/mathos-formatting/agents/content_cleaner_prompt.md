# Content Cleaner Prompt

You are generating a Python Markdown cleaner plugin.

Return one Python file only. It must expose:

```python
PLUGIN_ID = "descriptive_id"
PLUGIN_VERSION = "1.0.0"

# Note: Both "warnings" and "summary" in the return dict MUST be flat lists of strings.
def analyze(markdown: str) -> dict:
    return {"warnings": ["warning string"], "summary": ["summary string"]}

def clean(markdown: str) -> str:
    return markdown
```

The plugin receives Markdown text and returns Markdown text. Do not read files, write files, access environment variables, call subprocesses, or use network APIs.

The input sample is one complete H1 section after heading normalization. The cleaner is for image/text formatting only and must not modify heading lines.

