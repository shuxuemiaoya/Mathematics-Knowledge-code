# Preservation Contract

Allowed changes:

- UTF-8 and LF normalization;
- trailing-space removal;
- bounded blank lines;
- blank separation before headings and callouts;
- generated non-atomic headings, provenance metadata, and standalone
  vault-relative `![[...]]` navigation embeds.

Atomic question notes remain headingless before their source marker; an
optional answer-section heading is permitted after the exact question body.

Protected content:

- every source word, symbol, formula, number, question option, and subpart;
- tables, images, link destinations, captions, and source order;
- exact question and answer blocks inside provenance markers.

Compute lexical signatures before and after the presentation pass. A mismatch
is blocking. OCR correction belongs to a separate visually reviewed artifact.
