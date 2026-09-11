#!/usr/bin/env python3
"""Public entry point for two-pass semantic book atomization."""

from semantic_atomization import (  # re-export the review API for Agent use
    ATOM_CATEGORY_NAMES,
    DERIVED_CATEGORY_NAMES,
    LOCAL_RELATION_TYPES,
    AtomizationError,
    DEFAULT_ATOMIZATION,
    actual_boundary_action,
    atomic_json,
    finalize_payload,
    finalize_feedback,
    finalize_role_review,
    main,
    prepare_audit_jobs,
    prepare_feedback_jobs,
    prepare_jobs,
    prepare_role_review,
    seal_artifact,
    validate_round1_payload,
    validate_role_review,
    verify_artifact,
)
from validate_book_graph import artifact_digest, canonical_digest, load_json, sha256_file


if __name__ == "__main__":
    raise SystemExit(main())
