#!/usr/bin/env python3
"""Generate deep deterministic per-file PDF documentation for Engram."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:  # Script execution path: /.../scripts on sys.path
    from docgen.analyze import (
        analyze_non_python_file,
        analyze_python_file,
        build_doc_payload,
        collect_target_files,
    )
    from docgen.render_pdf import render_file_pdf, render_index_pdf
except ModuleNotFoundError:  # Module import path: scripts.generate_deep_docs
    from scripts.docgen.analyze import (
        analyze_non_python_file,
        analyze_python_file,
        build_doc_payload,
        collect_target_files,
    )
    from scripts.docgen.render_pdf import render_file_pdf, render_index_pdf


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate deep per-file PDF documentation.")
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Repository root path.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parents[1] / "docs" / "pdf"),
        help="Output folder for generated PDFs and manifest.",
    )
    parser.add_argument(
        "--exclude-tests",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Exclude files under tests/ from documentation scope.",
    )
    parser.add_argument(
        "--include-non-python",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include supported non-Python files (JSON/TOML/YAML/HTML/Dockerfile).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate all files even when hash is unchanged.",
    )
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Alias for incremental mode: regenerate only changed/added files.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Parallel workers for PDF generation.",
    )
    return parser.parse_args()


def main(argv: List[str] | None = None) -> int:
    args = parse_args() if argv is None else _parse_from_list(argv)

    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    files_dir = output_dir / "files"
    manifest_path = output_dir / "manifest.json"
    index_path = output_dir / "INDEX.pdf"

    output_dir.mkdir(parents=True, exist_ok=True)
    files_dir.mkdir(parents=True, exist_ok=True)

    selected = collect_target_files(
        repo_root=repo_root,
        exclude_tests=args.exclude_tests,
        include_non_python=args.include_non_python,
    )

    print(f"[docgen] inventory ({len(selected)} files):")
    for rel in selected:
        print(f"[docgen]  - {rel}")

    prev_manifest = _load_manifest(manifest_path)
    prev_index = {item["source_path"]: item for item in prev_manifest.get("items", [])}

    commit_hash = _get_commit_hash(repo_root)
    run_ts = _utc_now()

    jobs: List[Dict[str, Any]] = []
    skipped_entries: Dict[str, Dict[str, Any]] = {}

    for rel in selected:
        src = repo_root / rel
        sha = _sha256_file(src)
        output_rel = f"files/{_sanitize_path(rel)}"
        output_abs = output_dir / output_rel
        line_count = _line_count(src)

        previous = prev_index.get(rel)
        unchanged = (
            previous is not None
            and previous.get("source_sha256") == sha
            and output_abs.exists()
        )

        if args.force:
            should_generate = True
        else:
            should_generate = not unchanged

        if args.changed_only and not args.force:
            should_generate = not unchanged

        if should_generate:
            jobs.append(
                {
                    "source_path": rel,
                    "source_abs": src,
                    "source_sha256": sha,
                    "output_pdf": output_rel,
                    "output_abs": output_abs,
                    "line_count": line_count,
                    "generated_at": run_ts,
                }
            )
        else:
            reused = dict(previous)
            reused["line_count"] = line_count
            skipped_entries[rel] = reused

    print(f"[docgen] generate={len(jobs)} skip={len(skipped_entries)}")

    generated_entries: Dict[str, Dict[str, Any]] = {}

    if jobs:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(args.max_workers, 1)) as executor:
            future_map = {
                executor.submit(_generate_one, repo_root, commit_hash, job): job["source_path"]
                for job in jobs
            }
            for future in concurrent.futures.as_completed(future_map):
                source_path = future_map[future]
                result = future.result()
                generated_entries[source_path] = result
                print(
                    f"[docgen] rendered {source_path} -> {result['output_pdf']} "
                    f"({result['page_count']} pages)"
                )

    all_entries: List[Dict[str, Any]] = []
    for rel in selected:
        if rel in generated_entries:
            all_entries.append(generated_entries[rel])
        elif rel in skipped_entries:
            all_entries.append(skipped_entries[rel])

    all_entries.sort(key=lambda item: item["source_path"])

    manifest = {
        "generated_at": run_ts,
        "repo_root": str(repo_root),
        "commit_hash": commit_hash,
        "doc_depth": "deep",
        "method": "deterministic_static",
        "file_count": len(all_entries),
        "items": all_entries,
    }

    index_payload = {
        "generated_at": run_ts,
        "commit_hash": commit_hash,
        "total_files": len(all_entries),
        "reading_guide": _reading_guide(all_entries),
        "groups": _group_for_index(all_entries),
    }
    index_pages = render_index_pdf(index_payload, index_path)

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=False), encoding="utf-8")

    print(f"[docgen] wrote manifest: {manifest_path}")
    print(f"[docgen] wrote index: {index_path} ({index_pages} pages)")
    return 0


def _parse_from_list(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate deep per-file PDF documentation.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parents[1] / "docs" / "pdf"))
    parser.add_argument("--exclude-tests", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-non-python", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--changed-only", action="store_true")
    parser.add_argument("--max-workers", type=int, default=4)
    return parser.parse_args(argv)


def _generate_one(repo_root: Path, commit_hash: str, job: Dict[str, Any]) -> Dict[str, Any]:
    source_path = job["source_path"]
    source_abs = job["source_abs"]

    if source_path.endswith(".py"):
        analysis = analyze_python_file(source_abs)
    else:
        analysis = analyze_non_python_file(source_abs)

    payload = build_doc_payload(source_path, analysis)
    payload["generated_at"] = job["generated_at"]
    payload["commit_hash"] = commit_hash

    page_count = render_file_pdf(payload, job["output_abs"])

    return {
        "source_path": source_path,
        "source_sha256": job["source_sha256"],
        "output_pdf": job["output_pdf"],
        "line_count": analysis.get("line_count", job["line_count"]),
        "page_count": page_count,
        "generated_at": job["generated_at"],
        "doc_depth": "deep",
        "method": "deterministic_static",
    }


def _group_for_index(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for item in items:
        path = item["source_path"]
        parts = path.split("/")

        if path.startswith("engram/") and len(parts) >= 2:
            group = f"engram/{parts[1]}"
        elif path.startswith("plugins/engram-memory/") and len(parts) >= 3:
            group = f"plugins/engram-memory/{parts[2]}"
        else:
            group = "root"

        groups[group].append(item)

    for value in groups.values():
        value.sort(key=lambda item: item["source_path"])

    return dict(sorted(groups.items(), key=lambda item: item[0]))


def _reading_guide(items: List[Dict[str, Any]]) -> List[str]:
    paths = {item["source_path"] for item in items}
    guide = [
        "Start with `engram/memory/main.py` to understand the top-level orchestration flow.",
        "Read `engram/db/sqlite.py` next to map persistence behavior and storage contracts.",
        "Then inspect `engram/mcp_server.py` for tool/API exposure and request handling.",
        "Use module-group sections in this index to drill into subsystems after the core pass.",
    ]

    dynamic_hints: List[str] = []
    for candidate in [
        "engram/memory/main.py",
        "engram/db/sqlite.py",
        "engram/mcp_server.py",
        "engram/core/kernel.py",
        "engram/api/app.py",
    ]:
        if candidate in paths:
            dynamic_hints.append(f"Priority module present: `{candidate}`.")

    return guide + dynamic_hints


def _load_manifest(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)


def _sanitize_path(rel_path: str) -> str:
    return rel_path.replace("/", "__") + ".pdf"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _get_commit_hash(repo_root: Path) -> str:
    try:
        return (
            subprocess.check_output(["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True)
            .strip()
        )
    except Exception:
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
