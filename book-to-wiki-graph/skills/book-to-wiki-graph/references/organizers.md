# Organizer Review

Run organizer review after TOC extraction and before semantic atomization.
Its purpose is to distinguish real ownership structure from headings that only
label a local teaching activity.

## Decision test

Keep or synthesize an organizer only when it owns more than one reusable unit
or represents a stable navigation boundary such as a book, part, chapter,
section, terminal exercise set, or source-supported knowledge topic.

Demote a heading when it merely says how the reader should engage with the
immediately following content: observe, think, try, discuss, communicate,
operate, investigate, reflect, and similar labels. Keep the heading line inside
the following atom's audited source range so ownership and adjacency remain
traceable. The Markdown renderer omits that presentation-only heading line from
the final heading-free atom note while retaining the prompt and teaching body.

Under each TOC section, use this canonical direct-child flow in source order:

1. a section-wide framing scenario, when present;
2. independently reusable knowledge-topic organizers;
3. the terminal formal exercise set, when present.

A short prior-knowledge question is section-wide when its answer is the set of
several sibling topics, rather than only the first topic. Keep it as a direct
`section-introduction` scenario and place it before those organizers. Inline
practice blocks belong to the preceding or explicitly targeted knowledge topic;
they are not section-level siblings. A terminal numbered exercise set remains a
direct section organizer. Topic titles describe the knowledge subject, not the
pedagogical action.

Do not merge adjacent formal concepts merely because the printed source places
them below one presentation heading. If each concept has its own definition,
dependency role, and reuse value, synthesize separate topic organizers. For
example, a universal set is a prerequisite context for complement and therefore
remains separate from complement.

## Review artifact

`refine_organizers.py` consumes a sealed `organizer-review.json`:

```json
{
  "schema_version": 1,
  "kind": "organizer-review",
  "status": "passed",
  "base_manifest_sha256": "<file digest>",
  "source_markdown_sha256": "<file digest>",
  "reviewer": {"type": "codex-agent", "model": "current-agent"},
  "demote_organizer_keys": ["activity-heading-key"],
  "content_runs": [
    {
      "owner_key": "topic-key",
      "create_organizer": true,
      "parent_key": "toc-section-key",
      "title": "Source-supported knowledge topic",
      "source_range": [100, 180],
      "reason": "Why this continuous range is one reusable subject topic."
    },
    {
      "owner_key": "existing-practice-key",
      "create_organizer": false,
      "source_range": [182, 196],
      "reason": "Why these lines are the direct content of the practice block."
    }
  ],
  "renumber_parent_keys": ["toc-section-key"],
  "artifact_sha256": "<canonical artifact digest>"
}
```

Content runs are continuous, non-overlapping ownership ranges. They may split a
draft atom when OCR or the first heuristic pass crossed a real organization
boundary. They must contain every nonblank line of affected atoms and every
demoted heading. A run cannot cross a retained organizer heading.

The output is still a draft graph: its organizer ownership is reviewed, while
its provisional atom boundaries are intentionally passed to the two-round
semantic atomization workflow.
