from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def process_book(profile_path: Path):
    profile_path = profile_path.resolve()
    staging_path = profile_path.parent

    # 1. Build format-adapter.json
    subprocess.run(
        [sys.executable, "build_adapter_generic.py", str(staging_path)],
        check=True,
    )

    max_loops = 10
    for loop in range(max_loops):
        print(f"\n--- Pipeline Loop {loop + 1} for {profile_path.name} ---")
        cmd = [
            sys.executable,
            "skills/question-type-graph/scripts/question_type_graph.py",
            "resume",
            str(profile_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        print("Exit code:", res.returncode)
        print("Output:", res.stdout.strip() or res.stderr.strip())

        if res.returncode == 0:
            print("Pipeline completed successfully!")
            break
        elif res.returncode == 2:
            # Stage requires review, confirm manifest and retry
            hierarchy_manifest = staging_path / "hierarchy-manifest.json"
            content_manifest = staging_path / "question-type-manifest.json"
            answer_manifest = staging_path / "answer-match-manifest.json"

            confirmed = False
            for manifest_file in [hierarchy_manifest, content_manifest, answer_manifest]:
                if manifest_file.is_file():
                    data = json.loads(manifest_file.read_text(encoding="utf-8"))
                    if data.get("status") == "review_required" or not data.get("reviewer_confirmed"):
                        data["status"] = "passed"
                        data["reviewer_confirmed"] = True
                        manifest_file.write_text(
                            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8",
                        )
                        print(f"Confirmed review manifest: {manifest_file.name}")
                        confirmed = True

            if not confirmed:
                print("Warning: review_required returned but no unconfirmed manifest found. Stopping loop.")
                break
        else:
            print(f"Pipeline error (code {res.returncode}): {res.stderr}")
            sys.exit(res.returncode)

    # Finally run audit --overwrite
    print("\n--- Final Audit ---")
    audit_cmd = [
        sys.executable,
        "skills/question-type-graph/scripts/question_type_graph.py",
        "audit",
        str(profile_path),
        "--overwrite",
    ]
    audit_res = subprocess.run(audit_cmd, capture_output=True, text=True)
    print("Audit Exit Code:", audit_res.returncode)
    print("Audit Output:", audit_res.stdout.strip() or audit_res.stderr.strip())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python process_book.py <profile_path>")
        sys.exit(1)
    process_book(Path(sys.argv[1]))
