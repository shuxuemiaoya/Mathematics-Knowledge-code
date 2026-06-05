---
name: template
description: Template folder for creating MathOS repo-local skills. Do not invoke for user tasks.
---

# Skill Template

Copy this directory when creating a new MathOS repo-local skill.

Expected structure:

```text
skill-name/
|-- scripts/
|-- references/
|-- assets/
|-- agents/
|-- LICENSE.txt
|-- NOTICE.txt
`-- SKILL.md
```

Keep `SKILL.md` concise. Put deterministic programs in `scripts/`, detailed documentation in `references/`, output resources in `assets/`, and product-facing metadata in `agents/`.
