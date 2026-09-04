#!/usr/bin/env python3
"""Optionally build atom/concept embeddings for hybrid candidate recall."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from knowledge_relations import atomic_json, load_tagged, seal_artifact, validate_concept_payload


EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"


class EmbeddingError(RuntimeError):
    pass


def default_transport(request: urllib.request.Request, timeout: float) -> bytes:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise EmbeddingError(f"Embeddings API returned HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise EmbeddingError(f"Embeddings API request failed: {error.reason}") from error


def request_embeddings(texts: list[str], model: str, api_key: str, timeout: float, transport: Callable[[urllib.request.Request, float], bytes] = default_transport) -> list[list[float]]:
    request = urllib.request.Request(
        EMBEDDINGS_URL,
        data=json.dumps({"model": model, "input": texts, "encoding_format": "float"}, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST",
    )
    try:
        response = json.loads(transport(request, timeout).decode("utf-8"))
        ordered = sorted(response["data"], key=lambda item: int(item["index"]))
        vectors = [[float(number) for number in item["embedding"]] for item in ordered]
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EmbeddingError("Embeddings API returned malformed data") from error
    if len(vectors) != len(texts):
        raise EmbeddingError("Embeddings API returned the wrong vector count")
    return vectors


def run_embeddings(concept_jobs_path: Path, round1_path: Path, output_path: Path, model: str, api_key: str, execute: bool, timeout: float = 120.0, batch_size: int = 128, transport: Callable[[urllib.request.Request, float], bytes] = default_transport) -> dict[str, Any]:
    if not execute:
        raise EmbeddingError("Embedding calls require explicit --execute")
    if not model.strip():
        raise EmbeddingError("--model is required and has no implicit default")
    if not api_key:
        raise EmbeddingError("API key is missing")
    jobs = load_tagged(concept_jobs_path, "concept-jobs")
    round1 = load_tagged(round1_path, "round-1-concepts")
    report = validate_concept_payload(jobs, round1)
    if report["errors"]:
        raise EmbeddingError("Round-one concepts are invalid")
    atoms = {
        str(atom["atom_key"]): atom
        for job in jobs.get("jobs", []) for atom in job.get("atoms", [])
    }
    items = [
        (key, f"{atom['title']}\n{atom['source_text']}")
        for key, atom in sorted(atoms.items())
    ] + [
        (str(item["proposal_id"]), f"{item['preferred_label']}\n{item['definition']}\n{' '.join(item.get('aliases', []))}")
        for item in report["concepts"]
    ]
    vectors: dict[str, list[float]] = {}
    for index in range(0, len(items), batch_size):
        batch = items[index:index + batch_size]
        values = request_embeddings([text for _, text in batch], model, api_key, timeout, transport)
        vectors.update({key: vector for (key, _), vector in zip(batch, values)})
    payload = seal_artifact({
        "schema_version": 1, "kind": "relation-embeddings",
        "concept_jobs_sha256": jobs["artifact_sha256"], "round_1_concepts_sha256": round1["artifact_sha256"],
        "model": model, "vectors": vectors,
    })
    atomic_json(output_path.expanduser().resolve(), payload, overwrite=True)
    return {"status": "complete", "output": str(output_path.expanduser().resolve()), "model": model, "vectors": len(vectors), "artifact_sha256": payload["artifact_sha256"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("concept_jobs", type=Path)
    parser.add_argument("round_1_concepts", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--batch-size", type=int, default=128)
    args = parser.parse_args()
    try:
        report, code = run_embeddings(
            args.concept_jobs, args.round_1_concepts, args.output, args.model,
            os.environ.get(args.api_key_env, ""), args.execute, args.timeout, args.batch_size,
        ), 0
    except Exception as error:
        report, code = {"status": "failed", "error": f"{type(error).__name__}: {error}"}, 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
