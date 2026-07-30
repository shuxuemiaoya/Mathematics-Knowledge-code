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

Definition cues such as `叫做`, `称为`, `称…是`, `就说`, `判断为`,
`定义为`, `记为`, and `我们把` are candidates, not proof by themselves.
When several candidates exist for one reviewed term, direct naming evidence
(`叫做`, `称为`, `统称为`, or `定义为` immediately before the term)
outranks generic uses after `我们说`, `就说`, and `并且说`. File-path and
line order must not promote a generic noun use over a direct definition.
General definitions beginning with `一般地`, `通常`, or an explicit
domain-and-condition statement outrank concrete examples such as
`称函数 f(x)=x² 为偶函数`. A formula concept is incomplete unless the
reviewed copied range contains its actual equation.
Parallel terms in one formal sentence (for example, sufficient and necessary
conditions) remain separate review candidates.

## Files

- Put every concept file directly in the profile-mapped concept directory.
- Create no concept subdirectories.
- Use the concept name as the filename.
- Start every concept note with `# 概念名`, then a resolving `来源：` link,
  then `## 定义`, followed by the complete copied definition.
- Do not create an empty, link-only, or inferred concept file.
- Do not overwrite a splitter-created concept candidate silently. Accept it when its complete formal definition and provenance are valid; otherwise block and correct the split manifest.

## Source replacement

- Replace the first defining occurrence in each source file with one Markdown link.
- Use `[概念名](概念/概念名.md)` when the source file is at book root in
  relative mode. In vault-root mode, use a leading-slash destination such as
  `[概念名](/课本/书名/概念/概念名.md)`.
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
