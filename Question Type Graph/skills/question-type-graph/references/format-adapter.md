# Format Adapter

Store one reviewed adapter in staging. Reusable code consumes semantic roles;
literal publisher labels and page assumptions live here.

Minimum shape:

```json
{
  "schema_version": 1,
  "status": "passed",
  "reviewer_confirmed": true,
  "profile": "C:/absolute/question-type-profile.json",
  "hierarchy": {
    "source_role": "questions",
    "root_output": "index.md",
    "primary_authority": {
      "status": "passed",
      "reviewer_confirmed": true,
      "start_line": 10,
      "end_line": 40,
      "entries": [
        {"key": "chapter-1", "title": "authoritative source title", "level": 1, "source_line": 12}
      ]
    },
    "entries": [
      {
        "key": "chapter-1",
        "output": "chapter-1/chapter-1.md",
        "body_anchor": {
          "kind": "reviewed-boundary",
          "start_line": 100,
          "evidence": "reviewed first body block for this TOC entry",
          "reviewer_confirmed": true
        },
        "emit_title": true,
        "answer_context": "chapter-1"
      }
    ]
  },
  "content": {
    "unknown_label_policy": "review",
    "question_folder": "questions",
    "question_title_template": "Question {number}",
    "question_patterns": ["^(?P<number>\\d+)[.．、]\\s*"],
    "roles": [
      {"role": "training-band", "depth": 0, "pattern": "source-specific regex", "answer_context": true},
      {"role": "question-type", "depth": 1, "pattern": "source-specific regex"}
    ]
  },
  "answers": {
    "source_role": "answers",
    "contexts": [{"key": "chapter-1", "pattern": "source-specific regex"}],
    "answer_patterns": ["^(?P<number>\\d+)[.．、]\\s*"],
    "ignore_ranges": []
  }
}
```

For a content-derived no-TOC hierarchy, replace `primary_authority` with an
explicit `no_toc_authority` object containing `status: passed`,
`reviewer_confirmed: true`, and a non-empty evidence-based `reason`; omission
of both authority forms is an error. Record the reviewed entries and exact
start lines. Training-band entries nested below a
TOC node must be marked `supplemental: true`. Use `structural_only: true` when
a parent has no independent body range and shares its first child's anchor.
For combined inputs, set the answer role to `combined` and freeze a
non-overlapping `answers.region`. Save a series preset only after removing
paths, titles, line ranges, and content-specific regex captures.

Set `answer_context: true` on a repeated functional role when question numbers
restart inside those blocks. Its stable context is
`{note_key}:{role}:{occurrence}` by default; use `answer_context_template` only
when the answer-source context keys require another reviewed convention.
Generated paths default to a conservative 220-character budget and fall back
to deterministic `_compact` names without changing visible note titles.
