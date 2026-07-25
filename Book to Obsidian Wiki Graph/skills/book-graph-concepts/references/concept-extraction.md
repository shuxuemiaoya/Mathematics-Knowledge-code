# Concept Extraction Prompt Contract

This reference isolates Task 1 from the supplied `概念提取与Markdown排版美化.md` prompt so concept extraction and Markdown standardization remain separate stages.

## Extraction

1. Validate concept-category files created by splitting before accepting them.
2. Extract only a concept formally defined in the current split note or chapter section.
3. Do not extract a term that has no defining sentence.
4. Do not extract a concept whose definition exists only in another chapter or note.
5. Copy the complete definition; never truncate or paraphrase it.
6. Preserve immediately required notation, formula, and source-supplied annotation.
7. Record the source and include a resolving Markdown link back to it.

Definition cues such as `叫做`, `称为`, `定义为`, `记为`, and `我们把` are candidates, not proof by themselves.

## Files

- Put every concept file directly in the profile-mapped concept directory.
- Create no concept subdirectories.
- Use the concept name as the filename.
- Do not create an empty, link-only, or inferred concept file.
- Do not overwrite a splitter-created concept candidate silently. Accept it when its complete formal definition and provenance are valid; otherwise block and correct the split manifest.

## Source replacement

- Replace the first defining occurrence in each source file with one Markdown link.
- Use `[概念名](概念/概念名.md)` when the source file is at book root.
- When the source note is inside another category, compute the resolving relative equivalent such as `[概念名](../概念/概念名.md)`, or the configured vault-root equivalent.
- Link the same concept only once in the same file.
- Leave later repetitions unchanged.
- Do not link H1-H3 headings.

## Manifest

Record:

```json
{
  "schema_version": 1,
  "profile": "C:/.../book-profile.json",
  "source_sha256": "<frozen book digest>",
  "concepts": [
    {
      "name": "集合",
      "definition_source": "知识点/集合.md",
      "definition_unit": "topic-set",
      "target": "概念/集合.md",
      "linked_from": ["知识点/集合.md"]
    }
  ],
  "rejected": [
    {"name": "术语", "reason": "no formal definition in current note"}
  ]
}
```
