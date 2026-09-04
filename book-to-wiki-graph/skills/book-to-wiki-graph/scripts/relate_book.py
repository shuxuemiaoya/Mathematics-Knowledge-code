#!/usr/bin/env python3
"""CLI entrypoint for two-pass, evidence-bound teaching relation analysis."""

from semantic_relations import (
    DEFAULT_CANVAS,
    DEFAULT_RELATION_ANALYSIS,
    RELATION_TYPES,
    apply_relation_final,
    finalize_relations,
    main,
    prepare_audit_jobs,
    prepare_relation_jobs,
    relation_key,
    validate_round1_payload,
)


if __name__ == "__main__":
    raise SystemExit(main())
