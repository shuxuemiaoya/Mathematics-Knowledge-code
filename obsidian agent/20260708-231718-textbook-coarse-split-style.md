# Textbook Markdown coarse split style

When splitting ordinary textbook Markdown files in `C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\初中\课本\【2024版】【北师大版】`, follow the user's confirmed manual split style from:

`...\【2024版】【北师大版】八年级上册数学\知识点\1.1 探索勾股定理.md`

Do not over-split into many tiny files. Use coarse textbook lesson chunks:

- Keep the original lesson file as an entry/index.
- In the original lesson file, keep only short intro/context callouts and links to a few large target files, separated by `---`.
- A large target file should usually correspond to a major lesson subsection or learning arc, not every activity, thought prompt, or exercise.
- Keep `随堂练习` inside the relevant large `知识点/` file instead of creating separate exercise files for each随堂练习.
- Put the end-of-section `习题x.x` into the book-level sibling `习题/` folder, not under `知识点/习题/`.
- Put extracted formal concepts into the book-level sibling `概念/` folder, not under `知识点/概念/`.
- Keep `趣味阅读/` and `思维/` as book-level sibling folders only when a whole reading/thinking article is clearly separate, matching the manual corpus style.
- Use link paths from the vault/book corpus root style, e.g. `课本/【2024版】【北师大版】/.../知识点/xxx.md`, like the manual example.
- Extract only formally defined concepts. Link each concept's first occurrence in the large content file with the concept name as link text.
- Do local Markdown cleanup while splitting: normalize callouts such as `think`/`observe` to supported types, preserve original meaning, keep images with captions, and group related images instead of splitting them apart.

Concrete confirmed example for `八年级下册数学\知识点\1 不等式及其基本性质.md`:

- original entry file links to three large knowledge files: `不等式.md`, `不等式的解集.md`, `不等式的基本性质.md`
- one final exercise file: `习题\习题2.1 不等式及其基本性质.md`
- four concept files: `概念\不等式.md`, `概念\不等式的解.md`, `概念\不等式的解集.md`, `概念\解不等式.md`

# Update to 20260708-231718 textbook coarse split style

This updates the earlier note `20260708-231718-textbook-coarse-split-style.md`.

For ordinary textbook Markdown splitting in `C:\Mathematics-Knowledge\Secondary-School-Mathematics-Knowledge-Map\初中\课本\【2024版】【北师大版】`, keep the confirmed coarse split style, but revise the link and entry-file rules as follows:

- Prefer relative Markdown links from the current file to the target file, such as `分式.md`, `../习题/习题5.1 分式及其基本性质.md`, and `../概念/分式.md`.
- Do not use vault-root links like `课本/【2024版】【北师大版】/...` for newly generated split links, because they can display as uncreated when the user's Obsidian vault root or parser differs.
- Avoid URL-encoded spaces such as `%20` in local Markdown links; use the real filename text.
- In the original lesson entry file, do not leave only bare links when a split target continues the teaching thought. Add a short `> [!info] 情景引入` or transition preview before non-exercise target links so the source file preserves the learning flow.
- The 情景引入 should follow the target being split out: if the next knowledge file starts from a situation, question, observation, operation, or motivating example, keep that context with the link instead of cutting the thought process off.
- Do not add noisy 情景引入 previews before ordinary exercise links; exercises can stay as direct links unless the source itself has a meaningful transition paragraph.
- When optimizing existing split files, run an actual filesystem link check for both Markdown links and image references. If a referenced Markdown target or image file is truly missing, create or restore the target instead of only changing the visible link text.
- If old image paths were moved during splitting, either rewrite the image reference to the correct relative path or restore the missing image at the referenced path; do not leave broken image references.
- Continue to normalize unsupported callouts such as `think`, `observe`, and `todo` to supported types, and use `question` rather than `tip` for 尝试、观察、交流 style prompts.

Concrete correction from the 八年级下册数学 cleanup on 2026-07-09:

- The earlier vault-root path rule was superseded by relative links after many links displayed as uncreated.
- Entry pages were improved with 情景引入 previews before knowledge, thinking, and reading links.
- All links and image references were verified against the filesystem.
- Missing image resources under `知识点/images` were restored when they were still referenced.
