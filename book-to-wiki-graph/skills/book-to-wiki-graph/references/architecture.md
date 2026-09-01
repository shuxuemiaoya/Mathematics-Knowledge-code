# Organizer and Atom Architecture

## Two node layers

Every Markdown note is exactly one of:

- `organizer`: owns an ordered list of direct children;
- `atom`: owns nothing and contains one smallest source-complete unit.

Do not introduce a third node layer. Terms such as book, part, chapter,
section, topic, and subsection describe organizer roles, not new node types.
Terms such as definition, theorem, proof, example, problem, activity, case
study, and narrative describe atom content, not new node types.

## Organizer hierarchy

Start from the printed table of contents. Preserve its order and nesting.
Intermediate organizers may be added when the body has a clear source-backed
grouping missing from the printed TOC. Do not add organizers merely to make
the tree symmetrical.

Depth is not fixed. The root is level 1; every organizer child increments its
parent's level by one. A bottom organizer has no organizer children and links
only atoms. Higher organizers may link organizers and, when the source places
standalone material directly there, atoms.

An organizer note contains:

1. optional YAML frontmatter;
2. one Markdown heading with its source or reviewed organizer title;
3. one embedded Markdown note link per direct child, in source order.

It contains no teaching prose, summaries, duplicated atom bodies, or links to
descendants that are not direct children.

Store organizers below `组织层/`. Use folder-index placement for organizers
that own organizers: the owner note and child organizer folders share the
owner's directory. The manifest path is authoritative.

## Atomic units

An atom must preserve a complete source-backed unit. Do not split a definition
from the explanation that makes it intelligible, an example stem from its
solution, a question from its subparts, or a scenario from the prompt it
introduces. Do not merge unrelated adjacent units merely because they share a
heading.

Assign exactly one category:

| Manifest category | Directory | Includes |
| --- | --- | --- |
| `knowledge` | `原子层/知识点/` | exposition, definitions, propositions, proofs, methods, explanations |
| `worked-example` | `原子层/例题/` | one complete worked example, case, demonstration, or solved problem |
| `exercise` | `原子层/习题/` | one complete unsolved question or source exercise block |
| `scenario` | `原子层/情景引入/` | motivation, situation, narrative setup, observation, or opening prompt |

The categories are semantic roles that work across subjects. For a novel,
manual, or history book, use the closest role only when it is defensible from
the source; do not invent additional categories during this version of the
workflow.

Atoms have no children and no outgoing note links. Reject Wikilinks, ordinary
Markdown links, embedded Markdown-note links, and HTML anchors in atom bodies.
Local image/media embeds are allowed because they preserve the atom's source
content. Canvas cards provide navigation outside atoms; reviewed semantic
relations are rendered separately from the organization Canvas.

## Coverage and order

Every atom records an inclusive one-based `source_range`. Every organizer
records the source heading lines it owns. Printed TOC pages, running headers,
page numbers, and conversion artifacts may be excluded only through explicit
ranges with specific reasons.

After combining atom ranges, organizer heading ranges, and reviewed
exclusions, every nonblank source Markdown line must be covered exactly once.
Atom ranges must be disjoint. `source_order` must equal atoms sorted by their
source starts.

## Ownership and relations

Every non-root node has exactly one organizer parent. Each organizer's
`children` list is the canonical direct-child order, must agree with every
child's `parent_key`, and must match child source positions. For an organizer
without its own heading range, its earliest descendant supplies the ordering
anchor.

Optional semantic relations are stored in the manifest, never in atom files
or organization Canvas files. Each relation names two node keys and includes
specific source evidence. Do not infer a semantic relation from proximity
alone.
