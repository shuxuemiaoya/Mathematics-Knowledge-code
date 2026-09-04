#!/usr/bin/env python3
"""Optionally execute atomization packets with Responses API Structured Outputs."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from semantic_atomization import atomic_json, seal_artifact, verify_artifact
from validate_book_graph import artifact_digest, load_json


RESPONSES_URL = "https://api.openai.com/v1/responses"


class ModelRunnerError(RuntimeError):
    pass


ATOM_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "atom_id": {"type": "string"}, "owner_key": {"type": "string"},
        "source_range": {"type": "array", "items": {"type": "integer", "minimum": 1}, "minItems": 2, "maxItems": 2},
        "category": {"type": "string", "enum": ["knowledge", "worked-example", "exercise", "scenario"]},
        "title": {"type": "string"}, "boundary_reason": {"type": "string"},
        "cohesion_reason": {"type": "string"}, "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "standalone_kind": {"type": ["string", "null"], "enum": ["formal-definition", "theorem", "law", None]},
        "standalone_reason": {"type": ["string", "null"]},
    },
    "required": ["atom_id", "owner_key", "source_range", "category", "title", "boundary_reason", "cohesion_reason", "confidence", "standalone_kind", "standalone_reason"],
}


def output_schema(round_number: int) -> dict[str, Any]:
    if round_number == 1:
        return {"type": "object", "additionalProperties": False, "properties": {"job_id": {"type": "string"}, "packet_sha256": {"type": "string"}, "atoms": {"type": "array", "minItems": 1, "items": ATOM_SCHEMA}}, "required": ["job_id", "packet_sha256", "atoms"]}
    boundary = {"type": "object", "additionalProperties": False, "properties": {"boundary_id": {"type": "string"}, "action": {"type": "string", "enum": ["keep", "merge", "resegment"]}, "reason": {"type": "string"}, "confidence": {"type": "number", "minimum": 0, "maximum": 1}}, "required": ["boundary_id", "action", "reason", "confidence"]}
    return {"type": "object", "additionalProperties": False, "properties": {"audit_id": {"type": "string"}, "packet_sha256": {"type": "string"}, "boundary_reviews": {"type": "array", "items": boundary}, "atoms": {"type": "array", "minItems": 1, "items": ATOM_SCHEMA}}, "required": ["audit_id", "packet_sha256", "boundary_reviews", "atoms"]}


def prompt(round_number: int) -> str:
    shared = "Audit book atomization using only numbered source lines. Return ranges and metadata only; never rewrite, summarize, translate, or omit source. Preserve organizer ownership and hard boundaries. Knowledge is a complete teaching unit; only substantial scenarios stand alone; examples include solutions; exercises include all subparts."
    return shared + (" Produce a complete contiguous first-pass partition." if round_number == 1 else " Review every adjacency as keep, merge, or resegment and return the complete final partition. Short knowledge must merge unless it is a formal independent definition, theorem, or law.")


def default_transport(request: urllib.request.Request, timeout: float) -> bytes:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise ModelRunnerError(f"Responses API returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ModelRunnerError(f"Responses API request failed: {exc.reason}") from exc


def extract_output(response: dict[str, Any]) -> dict[str, Any]:
    texts: list[str] = []
    if isinstance(response.get("output_text"), str):
        texts.append(response["output_text"])
    for item in response.get("output", []):
        if isinstance(item, dict):
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    texts.append(content["text"])
    if not texts:
        raise ModelRunnerError("Responses API returned no output text")
    try:
        result = json.loads("".join(texts))
    except json.JSONDecodeError as exc:
        raise ModelRunnerError("Responses API output was not valid JSON") from exc
    if not isinstance(result, dict):
        raise ModelRunnerError("Structured output must be an object")
    return result


def request_packet(packet: dict[str, Any], round_number: int, model: str, api_key: str, timeout: float, transport: Callable[[urllib.request.Request, float], bytes] = default_transport) -> dict[str, Any]:
    body = {"model": model, "store": False, "instructions": prompt(round_number), "input": json.dumps(packet, ensure_ascii=False, separators=(",", ":")), "text": {"format": {"type": "json_schema", "name": f"book_atomization_round_{round_number}", "strict": True, "schema": output_schema(round_number)}}}
    request = urllib.request.Request(RESPONSES_URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    try:
        response = json.loads(transport(request, timeout).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelRunnerError("Responses API returned invalid JSON") from exc
    if not isinstance(response, dict) or response.get("status") not in {None, "completed"}:
        raise ModelRunnerError(f"Responses API did not complete: {getattr(response, 'get', lambda *_: None)('status')}")
    return extract_output(response)


def run_packets(input_path: Path, output_path: Path, round_number: int, model: str, api_key: str, execute: bool, timeout: float = 120.0, transport: Callable[[urllib.request.Request, float], bytes] = default_transport) -> dict[str, Any]:
    if not execute:
        raise ModelRunnerError("External model calls require explicit --execute")
    if not model.strip():
        raise ModelRunnerError("--model is required and has no implicit default")
    if not api_key:
        raise ModelRunnerError("OPENAI_API_KEY is missing")
    input_path, output_path = input_path.expanduser().resolve(), output_path.expanduser().resolve()
    source = load_json(input_path)
    input_kind = "atomization-jobs" if round_number == 1 else "round-2-jobs"
    output_kind = "round-1-decisions" if round_number == 1 else "round-2-decisions"
    binding = "jobs_sha256" if round_number == 1 else "round_2_jobs_sha256"
    packet_field, packets_field = ("job_id", "jobs") if round_number == 1 else ("audit_id", "audits")
    verify_artifact(source, input_kind)
    packets = source[packets_field]
    completed: dict[str, dict[str, Any]] = {}
    if output_path.exists():
        existing = load_json(output_path)
        verify_artifact(existing, output_kind)
        if existing.get(binding) != source["artifact_sha256"] or existing.get("reviewer", {}).get("model") != model:
            raise ModelRunnerError("Existing output binds a different input or model")
        completed = {str(item.get(packet_field)): item for item in existing.get("decisions", []) if isinstance(item, dict)}
    for packet in packets:
        packet_id = str(packet[packet_field])
        if packet_id in completed:
            continue
        decision = request_packet(packet, round_number, model, api_key, timeout, transport)
        if decision.get(packet_field) != packet_id or decision.get("packet_sha256") != packet.get("packet_sha256"):
            raise ModelRunnerError(f"Model returned a wrong ID or stale digest for {packet_id}")
        completed[packet_id] = decision
        partial = seal_artifact({"schema_version": 1, "kind": output_kind, binding: source["artifact_sha256"], "reviewer": {"type": "openai-responses-api", "model": model}, "status": "incomplete", "decisions": [completed[str(item[packet_field])] for item in packets if str(item[packet_field]) in completed]})
        atomic_json(output_path, partial, overwrite=True)
    final = seal_artifact({"schema_version": 1, "kind": output_kind, binding: source["artifact_sha256"], "reviewer": {"type": "openai-responses-api", "model": model}, "status": "complete", "decisions": [completed[str(item[packet_field])] for item in packets]})
    atomic_json(output_path, final, overwrite=True)
    return {"status": "complete", "output": str(output_path), "model": model, "packets": len(packets), "artifact_sha256": artifact_digest(final)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--round", type=int, choices=(1, 2), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    try:
        report, code = run_packets(args.input, args.output, args.round, args.model, os.environ.get(args.api_key_env, ""), args.execute, args.timeout), 0
    except Exception as exc:
        report, code = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
