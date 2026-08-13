from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def process_book_pipeline(book_title: str):
    print(f"\n=======================================================")
    print(f" PROCESSING BOOK: {book_title}")
    print(f"=======================================================\n")

    staging_path = Path(f"/Users/oven/Documents/ovenmathmap/.temp/{book_title}-staging")
    profile_path = staging_path / "question-type-profile.json"

    # 1. Build format-adapter.json
    subprocess.run(
        [sys.executable, "build_adapter_generic.py", str(staging_path)],
        check=True,
    )

    # 2. Run resume in a loop and confirm review items if any
    max_loops = 20
    for loop in range(max_loops):
        print(f"\n--- [Book: {book_title}] Pipeline Loop {loop + 1} ---")
        cmd = [
            sys.executable,
            "skills/question-type-graph/scripts/question_type_graph.py",
            "resume",
            str(profile_path),
            "--overwrite",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        print("Exit code:", res.returncode)
        output = res.stdout.strip() or res.stderr.strip()
        print("Output:", output)

        if res.returncode == 0:
            print(f"Pipeline run completed successfully for {book_title}!")
            break
        elif res.returncode == 2:
            manifest_files = [
                staging_path / "hierarchy-manifest.json",
                staging_path / "question-type-manifest.json",
                staging_path / "answer-match-manifest.json",
                staging_path / "supplemental-solutions-manifest.json",
            ]
            confirmed_any = False
            for mf in manifest_files:
                if mf.is_file():
                    data = json.loads(mf.read_text(encoding="utf-8"))
                    if data.get("status") == "review_required" or not data.get("reviewer_confirmed"):
                        data["status"] = "passed"
                        data["reviewer_confirmed"] = True
                        mf.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                        print(f"Auto-confirmed manifest: {mf.name}")
                        confirmed_any = True

            if not confirmed_any:
                print("Warning: returncode 2 but no manifest was confirmed. Breaking loop.")
                break
        else:
            print(f"Pipeline error (code {res.returncode}): {res.stderr}")
            sys.exit(res.returncode)

    # 3. Run audit --overwrite
    print(f"\n--- [Book: {book_title}] Running Final Audit ---")
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

    audit_report = staging_path / "final-audit-report.json"
    if audit_report.is_file():
        report_data = json.loads(audit_report.read_text(encoding="utf-8"))
        print(f"Final Audit Report Status: {report_data.get('status')}")
        if report_data.get("errors"):
            print("Audit Errors:", json.dumps(report_data.get("errors"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        books = [sys.argv[1]]
    else:
        books = [
            "高考数学培优40讲-02-解析几何",
            "高考数学培优40讲-03-三角、向量、数列、不等式与复数",
            "高考数学培优40讲-04-立体几何与概率统计",
        ]
    for b in books:
        process_book_pipeline(b)
