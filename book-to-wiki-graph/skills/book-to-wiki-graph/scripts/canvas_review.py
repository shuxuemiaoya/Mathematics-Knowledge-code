#!/usr/bin/env python3
"""Prepare and validate PNG-backed Canvas logic/visual reviews.

The PNG is mandatory visual evidence, while the manifest and Canvas JSON remain
the authority for node identity, relation direction, ownership and links.  The
current Codex agent can inspect each PNG with ``view_image`` and write the
structured decision file; an external model is never called implicitly.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from validate_book_graph import artifact_digest, load_json, sha256_file, stable_canvas_id


class CanvasReviewError(ValueError):
    pass


PRIORITY = [
    "knowledge-logic-completeness",
    "relation-correctness",
    "direction-and-ports",
    "organization-clarity",
    "aesthetics",
]
ALLOWED_ACTIONS = {
    "add-relation", "remove-relation", "reverse-relation", "reroute-relation",
    "rebuild-layout", "increase-spacing", "resize-region", "rename-label",
    "no-change",
}


def seal(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["artifact_sha256"] = artifact_digest(result)
    return result


def verify(payload: dict[str, Any], kind: str) -> None:
    if payload.get("kind") != kind:
        raise CanvasReviewError(f"Expected {kind}, got {payload.get('kind')!r}")
    if payload.get("artifact_sha256") != artifact_digest(payload):
        raise CanvasReviewError(f"Stale or missing digest for {kind}")


def atomic_json(path: Path, payload: dict[str, Any], overwrite: bool = False) -> None:
    path = path.expanduser().resolve()
    if path.exists() and not overwrite:
        raise FileExistsError(f"Output exists; pass --overwrite explicitly: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def entries(index: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name in ("atlas", "chapter_maps", "section_maps"):
        value = index.get(name)
        if isinstance(value, dict):
            result.append(value)
        elif isinstance(value, list):
            result.extend(item for item in value if isinstance(item, dict))
    return [item for item in result if isinstance(item.get("path"), str) and item.get("path")]


def safe_relative(root: Path, value: str, suffix: str | None = None) -> Path:
    path = Path(value.replace("\\", "/"))
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CanvasReviewError(f"Unsafe relative path: {value}")
    if suffix and path.suffix.casefold() != suffix:
        raise CanvasReviewError(f"Expected {suffix} path: {value}")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise CanvasReviewError(f"Path escapes output root: {value}") from exc
    return resolved


def canvas_catalog(canvas: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes = [item for item in canvas.get("nodes", []) if isinstance(item, dict)]
    edges = [item for item in canvas.get("edges", []) if isinstance(item, dict)]
    return (
        [{"id": str(item.get("id")), "type": item.get("type"), "label": item.get("text", item.get("label", "")), "x": item.get("x"), "y": item.get("y"), "width": item.get("width"), "height": item.get("height")} for item in nodes],
        [{"id": str(item.get("id")), "fromNode": str(item.get("fromNode")), "toNode": str(item.get("toNode")), "fromSide": item.get("fromSide"), "toSide": item.get("toSide"), "label": item.get("label", ""), "color": item.get("color")} for item in edges],
    )


def prepare(index_path: Path, output: Path, cycle: int = 1, overwrite: bool = False) -> dict[str, Any]:
    index_path, output = index_path.expanduser().resolve(), output.expanduser().resolve()
    index = load_json(index_path)
    if index.get("schema_version") not in {2, 3}:
        raise CanvasReviewError("Canvas review supports canvas-index schema v2/v3")
    index_root = index_path.parent
    manifest_path = Path(str(index.get("manifest", ""))).expanduser().resolve()
    manifest = load_json(manifest_path)
    graph_nodes = {str(item.get("key")): item for item in manifest.get("nodes", []) if isinstance(item, dict) and item.get("key")}
    graph_relations = [item for item in manifest.get("relations", []) if isinstance(item, dict)]
    jobs: list[dict[str, Any]] = []
    for number, entry in enumerate(entries(index), start=1):
        canvas_path = safe_relative(index_root, str(entry["path"]), ".canvas")
        png_value = entry.get("png_path") or str(Path(str(entry["path"])).with_suffix(".png"))
        png_path = safe_relative(index_root, str(png_value), ".png")
        if not canvas_path.is_file() or not png_path.is_file():
            raise CanvasReviewError(f"Canvas/PNG missing for {entry.get('path')}")
        canvas = load_json(canvas_path)
        node_catalog, edge_catalog = canvas_catalog(canvas)
        ids = {item["id"] for item in node_catalog}
        visible_graph_relations = []
        for relation in graph_relations:
            left, right = str(relation.get("from_key")), str(relation.get("to_key"))
            left_id, right_id = stable_canvas_id("card", left), stable_canvas_id("card", right)
            if left_id in ids and right_id in ids:
                visible_graph_relations.append({"key": relation.get("key"), "from_key": left, "to_key": right, "type": relation.get("type"), "tier": relation.get("tier"), "basis_keys": relation.get("basis_keys", [])})
        job_id = f"canvas-{number:04d}-{str(entry.get('role', 'map')).replace('_', '-')}-{entry.get('root_key', 'root')}"
        jobs.append({
            "job_id": job_id,
            "role": entry.get("role"), "root_key": entry.get("root_key"), "chapter_key": entry.get("chapter_key"),
            "canvas_path": str(canvas_path), "canvas_sha256": sha256_file(canvas_path),
            "png_path": str(png_path), "png_sha256": sha256_file(png_path),
            "canvas_index": str(index_path), "canvas_index_sha256": sha256_file(index_path),
            "node_count": len(node_catalog), "edge_count": len(edge_catalog),
            "nodes": node_catalog, "edges": edge_catalog,
            "authoritative_relations": visible_graph_relations,
            "logic_contract": {
                "priority": PRIORITY,
                "all_semantic_nodes_incident": True,
                "outgoing_progression_must_move_right": True,
                "outgoing_containment_must_move_down": True,
                "image_required": True,
            },
            "instructions": "Inspect the bound PNG. First compare visible logic with authoritative relation evidence and report missing, reversed, spurious, orphan, or port-direction problems. Only after logic is complete assess spacing, crossings, density, labels and aesthetics. Do not invent relations from appearance alone.",
        })
    payload = seal({
        "schema_version": 1, "kind": "canvas-review-jobs", "cycle": int(cycle),
        "canvas_index": str(index_path), "canvas_index_sha256": sha256_file(index_path),
        "manifest": str(manifest_path), "manifest_sha256": sha256_file(manifest_path),
        "review_scope": "every-canvas", "priority": PRIORITY, "jobs": jobs,
    })
    atomic_json(output, payload, overwrite)
    return payload


def _score(value: Any, field: str, errors: list[dict[str, Any]]) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
        errors.append({"code": "canvas-review-score-invalid", "field": field})
        return None
    return float(value)


def validate(jobs_path: Path, decisions_path: Path) -> dict[str, Any]:
    jobs = load_json(jobs_path.expanduser().resolve())
    decisions = load_json(decisions_path.expanduser().resolve())
    verify(jobs, "canvas-review-jobs")
    verify(decisions, "canvas-review-decisions")
    errors: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    if decisions.get("canvas_review_jobs_sha256") != jobs.get("artifact_sha256"):
        errors.append({"code": "canvas-review-jobs-binding-invalid"})
    expected = {str(item["job_id"]) for item in jobs.get("jobs", [])}
    raw = decisions.get("decisions")
    if not isinstance(raw, list):
        raw = []
        errors.append({"code": "canvas-review-decisions-missing"})
    by_id = {str(item.get("job_id")): item for item in raw if isinstance(item, dict)}
    if set(by_id) != expected or len(by_id) != len(raw):
        errors.append({"code": "canvas-review-coverage-invalid", "missing": sorted(expected - set(by_id)), "extra": sorted(set(by_id) - expected)})
    for job in jobs.get("jobs", []):
        job_id = str(job["job_id"])
        decision = by_id.get(job_id)
        if not isinstance(decision, dict):
            continue
        if decision.get("png_sha256") != job.get("png_sha256") or decision.get("canvas_sha256") != job.get("canvas_sha256"):
            errors.append({"code": "canvas-review-image-binding-invalid", "job_id": job_id})
        observations = decision.get("image_observations")
        if not isinstance(observations, list) or not observations or not all(isinstance(item, str) and item.strip() for item in observations):
            errors.append({"code": "canvas-review-image-observation-missing", "job_id": job_id})
        logic = decision.get("logic")
        visual = decision.get("visual")
        if not isinstance(logic, dict) or not isinstance(visual, dict):
            errors.append({"code": "canvas-review-score-block-missing", "job_id": job_id})
            continue
        logic_score = _score(logic.get("score"), f"{job_id}.logic.score", errors)
        visual_score = _score(visual.get("score"), f"{job_id}.visual.score", errors)
        verdict = str(decision.get("verdict", ""))
        if verdict not in {"passed", "needs-change", "blocked"}:
            errors.append({"code": "canvas-review-verdict-invalid", "job_id": job_id})
        confidence = _score(decision.get("confidence"), f"{job_id}.confidence", errors)
        if confidence is not None and confidence < 0.90:
            review.append({"code": "canvas-review-low-confidence", "job_id": job_id, "confidence": confidence})
        actions = decision.get("actions", [])
        if not isinstance(actions, list):
            errors.append({"code": "canvas-review-actions-invalid", "job_id": job_id})
            actions = []
        priorities = [str(item.get("priority")) for item in actions if isinstance(item, dict)]
        if any(item not in {"logic", "visual"} for item in priorities) or priorities != sorted(priorities, key=lambda item: {"logic": 0, "visual": 1}[item]):
            errors.append({"code": "canvas-review-priority-order-invalid", "job_id": job_id})
        for index, action in enumerate(actions):
            if not isinstance(action, dict) or action.get("action") not in ALLOWED_ACTIONS:
                errors.append({"code": "canvas-review-action-invalid", "job_id": job_id, "index": index})
            elif action.get("priority") == "logic" and not str(action.get("evidence", "")).strip():
                errors.append({"code": "canvas-review-logic-action-evidence-missing", "job_id": job_id, "index": index})
        for field in ("missing_relations", "wrong_relations", "orphan_nodes", "port_violations", "visual_issues"):
            if field in logic and field != "visual_issues" and not isinstance(logic.get(field), list):
                errors.append({"code": "canvas-review-issue-list-invalid", "job_id": job_id, "field": field})
        if verdict != "passed" or (logic_score is not None and logic_score < 0.90):
            review.append({"code": "canvas-logic-not-passed", "job_id": job_id, "score": logic_score, "verdict": verdict})
        elif visual_score is not None and visual_score < 0.75:
            review.append({"code": "canvas-visual-needs-improvement", "job_id": job_id, "score": visual_score})
    return {"status": "failed" if errors else ("review_required" if review else "passed"), "errors": errors, "review_items": review, "counts": {"jobs": len(expected), "decisions": len(by_id), "errors": len(errors), "review_items": len(review)}}


def seal_decisions(
    jobs_path: Path, draft_path: Path, output: Path, overwrite: bool = False,
) -> dict[str, Any]:
    """Bind Agent-authored evaluations to the exact Canvas and PNG bytes.

    The command deliberately does not generate observations, scores, verdicts,
    or actions.  It only removes repetitive digest transcription from a draft
    written after the Agent has viewed every PNG, while requiring exact job
    coverage before the sealed decision artifact can be finalized.
    """
    jobs_path = jobs_path.expanduser().resolve()
    draft_path = draft_path.expanduser().resolve()
    output = output.expanduser().resolve()
    jobs = load_json(jobs_path)
    draft = load_json(draft_path)
    verify(jobs, "canvas-review-jobs")
    raw = draft.get("decisions")
    if not isinstance(raw, list):
        raise CanvasReviewError("Decision draft must contain a decisions array")
    expected = {str(item["job_id"]): item for item in jobs.get("jobs", [])}
    supplied = {
        str(item.get("job_id")): item
        for item in raw if isinstance(item, dict) and item.get("job_id")
    }
    if len(supplied) != len(raw) or set(supplied) != set(expected):
        raise CanvasReviewError(
            "Decision draft must cover every Canvas review job exactly once"
        )
    bound: list[dict[str, Any]] = []
    for job in jobs.get("jobs", []):
        item = dict(supplied[str(job["job_id"])])
        item["canvas_sha256"] = job["canvas_sha256"]
        item["png_sha256"] = job["png_sha256"]
        bound.append(item)
    payload = seal({
        "schema_version": 1,
        "kind": "canvas-review-decisions",
        "canvas_review_jobs_sha256": jobs["artifact_sha256"],
        "reviewer": draft.get("reviewer"),
        "decisions": bound,
    })
    atomic_json(output, payload, overwrite)
    return payload


def finalize(jobs_path: Path, decisions_path: Path, output_dir: Path, overwrite: bool = False) -> dict[str, Any]:
    jobs_path, decisions_path, output_dir = jobs_path.expanduser().resolve(), decisions_path.expanduser().resolve(), output_dir.expanduser().resolve()
    jobs, decisions = load_json(jobs_path), load_json(decisions_path)
    report = validate(jobs_path, decisions_path)
    if report["errors"]:
        raise CanvasReviewError(json.dumps(report["errors"], ensure_ascii=False))
    unresolved = report["review_items"]
    final = seal({
        "schema_version": 1, "kind": "canvas-review-final",
        "status": "passed" if not unresolved else "review_required", "unresolved_count": len(unresolved),
        "cycle": jobs.get("cycle", 1), "canvas_index": jobs.get("canvas_index"), "canvas_index_sha256": jobs.get("canvas_index_sha256"),
        "jobs_sha256": jobs.get("artifact_sha256"), "decisions_sha256": decisions.get("artifact_sha256"),
        "reviewer": decisions.get("reviewer"), "priority": PRIORITY, "decisions": decisions.get("decisions", []),
    })
    queue = seal({"schema_version": 1, "kind": "canvas-review-queue", "status": "passed" if not unresolved else "blocked", "canvas_review_final_sha256": final["artifact_sha256"], "unresolved_count": len(unresolved), "items": unresolved})
    quality = seal({"schema_version": 1, "kind": "canvas-quality-report", "canvas_review_final_sha256": final["artifact_sha256"], "status": final["status"], "priority": PRIORITY, "counts": report["counts"], "logic_first": True})
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(output_dir / "canvas-review-final.json", final, overwrite)
    atomic_json(output_dir / "canvas-review-queue.json", queue, overwrite)
    atomic_json(output_dir / "canvas-quality-report.json", quality, overwrite)
    lines = ["# Canvas PNG 评价报告", "", f"状态：{final['status']}", f"未解决项：{len(unresolved)}", "", "评价顺序：" + " → ".join(PRIORITY), ""]
    for item in unresolved:
        lines.append(f"- `{item.get('job_id', '')}`：{item.get('code', '')}（{item.get('score', '')}）")
    (output_dir / "canvas-review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"status": final["status"], "output_dir": str(output_dir), "unresolved_count": len(unresolved), "counts": report["counts"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("canvas_index", type=Path)
    prepare_parser.add_argument("--output", type=Path, required=True)
    prepare_parser.add_argument("--cycle", type=int, default=1)
    prepare_parser.add_argument("--overwrite", action="store_true")
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("jobs", type=Path)
    validate_parser.add_argument("decisions", type=Path)
    seal_parser = sub.add_parser("seal-decisions")
    seal_parser.add_argument("jobs", type=Path)
    seal_parser.add_argument("draft", type=Path)
    seal_parser.add_argument("--output", type=Path, required=True)
    seal_parser.add_argument("--overwrite", action="store_true")
    finalize_parser = sub.add_parser("finalize")
    finalize_parser.add_argument("jobs", type=Path)
    finalize_parser.add_argument("decisions", type=Path)
    finalize_parser.add_argument("--output-dir", type=Path, required=True)
    finalize_parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.canvas_index, args.output, args.cycle, args.overwrite)
            output = {"status": "passed", "jobs": len(result["jobs"]), "output": str(args.output.expanduser().resolve())}
        elif args.command == "validate":
            output = validate(args.jobs, args.decisions)
        elif args.command == "seal-decisions":
            result = seal_decisions(args.jobs, args.draft, args.output, args.overwrite)
            output = {
                "status": "passed", "decisions": len(result["decisions"]),
                "output": str(args.output.expanduser().resolve()),
            }
        else:
            output = finalize(args.jobs, args.decisions, args.output_dir, args.overwrite)
            output["status"] = output["status"]
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if output.get("status") == "passed" else 1
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
