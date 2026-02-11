"""Integration and renderer tests for deterministic deep docgen pipeline."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from scripts.generate_deep_docs import main
from scripts.docgen.render_pdf import render_file_pdf, render_index_pdf


def _init_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)


def _write(tmp_path: Path, rel: str, content: str) -> None:
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _git_add_all(tmp_path: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)


def _has_reportlab() -> bool:
    return importlib.util.find_spec("reportlab") is not None


@pytest.mark.skipif(not _has_reportlab(), reason="reportlab is required for PDF generation tests")
def test_renderers_smoke(tmp_path: Path) -> None:
    file_pdf = tmp_path / "file.pdf"
    index_pdf = tmp_path / "index.pdf"

    payload = {
        "file_path": "engram/core/demo.py",
        "generated_at": "2026-02-11T00:00:00+00:00",
        "commit_hash": "abc123",
        "method": "deterministic_static",
        "doc_depth": "deep",
        "line_count": 10,
        "sections": [
            {
                "title": "Role in repository",
                "paragraphs": ["Demo paragraph."],
                "code_blocks": ["def demo():\n    return 1"],
            }
        ],
    }
    pages = render_file_pdf(payload, file_pdf)
    assert pages >= 1
    assert file_pdf.exists()
    assert file_pdf.stat().st_size > 0

    index_payload = {
        "generated_at": "2026-02-11T00:00:00+00:00",
        "commit_hash": "abc123",
        "total_files": 1,
        "reading_guide": ["Read core files first."],
        "groups": {
            "engram/core": [
                {
                    "source_path": "engram/core/demo.py",
                    "output_pdf": "files/engram__core__demo.py.pdf",
                    "line_count": 10,
                    "page_count": pages,
                }
            ]
        },
    }
    index_pages = render_index_pdf(index_payload, index_pdf)
    assert index_pages >= 1
    assert index_pdf.exists()
    assert index_pdf.stat().st_size > 0


@pytest.mark.skipif(not _has_reportlab(), reason="reportlab is required for PDF generation tests")
def test_generator_end_to_end_and_incremental(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    _write(tmp_path, "engram/core/a.py", "def alpha():\n    return 1\n")
    _write(tmp_path, "engram/memory/b.py", "class Beta:\n    pass\n")
    _write(tmp_path, "plugins/engram-memory/hooks/prompt_context.py", "HOOK = True\n")
    _write(tmp_path, "plugins/engram-memory/hooks/hooks.json", '{"hooks": ["x"]}\n')
    _write(tmp_path, "pyproject.toml", "[project]\nname='tmp'\n")
    _write(tmp_path, "Dockerfile", "FROM python:3.11\nCMD ['python']\n")
    _write(tmp_path, "docker-compose.yml", "services:\n  app:\n    image: test\n")
    _write(tmp_path, "tests/test_ignore.py", "def test_ignore():\n    assert True\n")
    _write(tmp_path, "engram/core/ignore.md", "# ignored\n")

    _git_add_all(tmp_path)

    output_dir = tmp_path / "docs" / "pdf"

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--output-dir",
            str(output_dir),
            "--exclude-tests",
            "--include-non-python",
            "--max-workers",
            "2",
        ]
    )
    assert exit_code == 0

    manifest_path = output_dir / "manifest.json"
    index_path = output_dir / "INDEX.pdf"
    assert manifest_path.exists()
    assert index_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["file_count"] == 7

    required_item_keys = {
        "source_path",
        "source_sha256",
        "output_pdf",
        "line_count",
        "page_count",
        "generated_at",
        "doc_depth",
        "method",
    }

    items = manifest["items"]
    for item in items:
        assert required_item_keys.issubset(item)
        target_pdf = output_dir / item["output_pdf"]
        assert target_pdf.exists()
        assert target_pdf.stat().st_size > 0

    target_item = next(item for item in items if item["source_path"] == "engram/core/a.py")
    untouched_item = next(item for item in items if item["source_path"] == "engram/memory/b.py")

    target_pdf = output_dir / target_item["output_pdf"]
    untouched_pdf = output_dir / untouched_item["output_pdf"]
    initial_target_mtime = target_pdf.stat().st_mtime
    initial_untouched_mtime = untouched_pdf.stat().st_mtime

    time.sleep(1.1)
    exit_code_2 = main(
        [
            "--repo-root",
            str(tmp_path),
            "--output-dir",
            str(output_dir),
            "--exclude-tests",
            "--include-non-python",
            "--changed-only",
            "--max-workers",
            "2",
        ]
    )
    assert exit_code_2 == 0
    assert target_pdf.stat().st_mtime == initial_target_mtime
    assert untouched_pdf.stat().st_mtime == initial_untouched_mtime

    time.sleep(1.1)
    _write(tmp_path, "engram/core/a.py", "def alpha():\n    return 2\n")

    exit_code_3 = main(
        [
            "--repo-root",
            str(tmp_path),
            "--output-dir",
            str(output_dir),
            "--exclude-tests",
            "--include-non-python",
            "--changed-only",
            "--max-workers",
            "2",
        ]
    )
    assert exit_code_3 == 0

    assert target_pdf.stat().st_mtime > initial_target_mtime
    assert untouched_pdf.stat().st_mtime == initial_untouched_mtime

    manifest_after = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_after["file_count"] == 7
    assert any(item["source_path"] == "engram/core/a.py" for item in manifest_after["items"])
