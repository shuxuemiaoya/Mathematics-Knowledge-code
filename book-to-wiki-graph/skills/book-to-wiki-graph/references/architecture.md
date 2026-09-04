# Organizer and Atom Architecture

## Two node layers

Every Markdown note is exactly one of:

- `organizer`: owns an ordered list of direct children;
- `atom`: owns nothing and contains one smallest source-complete unit.

Book, part, chapter, section, topic, appendix, and similar terms are organizer
roles, not additional layers. Definition, theorem, proof, example, problem,
activity, case study, and narrative describe atom content, not extra layers.

## Open-depth organizer hierarchy

Start with the printed TOC. Preserve its hierarchy, direct ownership, and
reading order. Add an intermediate organizer only when the source or an
explicit human review supports that ownership boundary.

Do not impose a fixed number of levels or a subject-specific wrapper scheme.
An organizer may own organizers, atoms, or both. Mixed children remain in the
order in which their earliest source content appears. In the common case, only
the deepest organizer owns atoms; this is a tendency, not a validity rule.

An organizer note has one embedded Markdown note link per direct child and does
not repeat its own title. The parent precedes every organizer-child embed with
the child's root-relative directory heading: `#` for a top-level organizer,
`##` for the next level, `###` for the third, and so on (capped at Markdown
`H6`). Atom embeds receive no added heading. A terminal organizer that links
directly to atoms therefore contains no heading at all. Organizer notes contain
no teaching prose, summaries, duplicated atom bodies, or links to non-direct
descendants.

Keep a directory only for an organizer that owns another organizer. Materialize
an organizer with only atom children as one numbered Markdown file directly in
its parent's directory; never create a subdirectory whose only local file is
that organizer note.

### Structural headings versus activity labels

A Markdown heading is not automatically an organizer. Printed TOC entries and
source-supported reusable knowledge topics are organizational. Pedagogical
labels such as observe, think, try, discuss, communicate, operate, or explore
normally introduce one atomic activity and belong inside that atom's source
range. Practice headings and exercise-set/group headings may remain organizers
when they own multiple questions.

Within a TOC section, place reviewed knowledge-topic organizers and the
practice/exercise organizers as ordered siblings. Name a synthesized topic for
the subject it teaches, never for the activity label used to teach it.

## Atomic units

An atom preserves a complete source-backed teaching unit. For exposition, the
default unit is the local teaching arc: motivation or short prompt, definition,
conditions, notation, explanation, derivation, and nearby conclusion. Do not
split that arc because a converter inserted a blank line, image, formula,
activity label, or box boundary. Split only when both sides can be named,
understood, and reused independently.

A short “observe”, “think”, or “try” prompt belongs with the knowledge it
elicits. A standalone scenario must be a complete narrative, real-world
context, experiment setup, or learning motivation. Keep an example stem with
its analysis, solution, and nearby conclusion. Keep a top-level exercise with
all subparts, figures, tables, and supplied material.

Assign exactly one category:

| Manifest category | Directory | Complete unit | Canvas color |
| --- | --- | --- | --- |
| `knowledge` | `原子层/知识点/` | exposition, definition, proposition, proof, method, explanation | `2` |
| `worked-example` | `原子层/例题/` | solved example with stem and solution | `4` |
| `exercise` | `原子层/习题/` | unsolved problem with all subparts/material | `6` |
| `scenario` | `原子层/情景引入/` | substantial context, narrative, experiment, or motivation | `5` |

Atoms have no children and no outgoing note links. Reject Wikilinks, ordinary
Markdown note links, embedded note links, and HTML anchors in atom bodies.
Local source image/media embeds are allowed. Render atom bodies without
Markdown heading lines. Store atoms under opaque sequence-and-category codes:
`K` knowledge, `W` worked example, `E` exercise, and `S` scenario (for example,
`0001-K.md`). Human-readable titles remain manifest metadata and link labels,
not filenames or headings inside atom notes.

## Hard constraints and audit thresholds

Organizer ownership, reviewed exclusions, explicit worked-example starts, and
top-level exercise starts are hard constraints. Empty lines, images, formulas,
boxed conclusions, and ordinary activity labels are soft boundary evidence.

Knowledge under 150 normalized characters or containing one nonblank line is
always audited. It remains independent only when it is a formal definition,
theorem, or law, has a concrete independence reason, and meets the configured
short-atom confidence threshold (default `0.95`). General decisions must meet
the configured confidence threshold (default `0.90`).

## Coverage and order

Each atom records an inclusive one-based `source_range`. Each organizer records
the source heading lines it owns. Printed TOC pages, running headers, page
numbers, and conversion artifacts are explicit reviewed exclusions.

Combining atom ranges, organizer heading ranges, and exclusions must cover
every nonblank source line exactly once. Atom ranges never overlap, and
`source_order` equals atoms sorted by source position. Classification affects
storage and Canvas color only; it never changes reading order.

## Teaching relations and learning maps

Materialize stable atom identities before analyzing relations. Then perform a
separate two-pass relation review: first index and connect atoms inside each
chapter; second audit the complete chapter graphs, packet seams, cross-chapter
candidates, mainline direction, cycles, and teaching satellites. Read
[relations.md](relations.md) before producing either pass.

Relations never change organizer ownership or atom prose. Explicit source
connections and pedagogical inferences remain distinguishable. Every inferred
edge cites both endpoint ranges and uses the higher confidence threshold.

Canvas uses two semantic scales. The book atlas contains only chapters and
aggregated cross-chapter routes. A chapter Canvas contains every knowledge and
scenario atom, only the worked examples reviewed as major-method `bridge`
examples, and exercise-organizer cards instead of individual exercise atoms.
Reviewed relations, direct-section regions, deeper organizer landmarks, and
optional unlinked convergence nodes express the learning map. Explicit edge
sides distinguish forward development (`right` to `left`), inspiration
(`right` to `top`), and subordinate/parallel branches (`bottom` to `top`).
Spatial containment communicates ownership. Retain a deeper landmark only when
it owns rendered content, and give it one gray containment edge to the nearest
rendered descendant so it cannot become an unexplained island. Do not redraw
the complete hierarchy as a left-to-right tree. Read [canvas.md](canvas.md)
before building or repairing Canvas output.
