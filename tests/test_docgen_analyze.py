"""Unit tests for deterministic docgen analyzers."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.docgen.analyze import (
    analyze_non_python_file,
    analyze_python_file,
    build_doc_payload,
    collect_target_files,
)


def _init_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)


def _git_add_all(tmp_path: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)


def test_collect_target_files_filters_scope(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    files = {
        "engram/core/a.py": "print('a')\n",
        "engram/core/ignore.md": "# ignored\n",
        "plugins/engram-memory/hooks/prompt_context.py": "x = 1\n",
        "plugins/engram-memory/README.md": "ignored\n",
        "tests/test_ignore.py": "def test_x():\n    assert True\n",
        "pyproject.toml": "[project]\nname='x'\n",
        "Dockerfile": "FROM python:3.11\n",
        "docker-compose.yml": "services:\n  app:\n    image: x\n",
        "misc.py": "print('not in scope')\n",
    }

    for rel, content in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    _git_add_all(tmp_path)

    selected = collect_target_files(tmp_path, exclude_tests=True, include_non_python=True)
    assert "engram/core/a.py" in selected
    assert "plugins/engram-memory/hooks/prompt_context.py" in selected
    assert "pyproject.toml" in selected
    assert "Dockerfile" in selected
    assert "docker-compose.yml" in selected

    assert "tests/test_ignore.py" not in selected
    assert "engram/core/ignore.md" not in selected
    assert "plugins/engram-memory/README.md" not in selected
    assert "misc.py" not in selected

    py_only = collect_target_files(tmp_path, exclude_tests=True, include_non_python=False)
    assert all(item.endswith(".py") for item in py_only)


def test_analyze_python_file_extracts_core_metadata(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_text(
        """
import os
import logging

APP_NAME = "engram"


def helper(value: int) -> int:
    return value + 1


class Sample:
    def run(self, value: int) -> int:
        if value < 0:
            raise ValueError("bad")
        return helper(value)


async def top() -> int:
    return helper(1)
""".strip()
        + "\n",
        encoding="utf-8",
    )

    analysis = analyze_python_file(path)

    assert analysis["file_type"] == "python"
    assert analysis["line_count"] > 0
    assert any(item["name"] == "APP_NAME" for item in analysis["constants"])
    assert any(item["name"] == "Sample" for item in analysis["classes"])
    assert any(item["name"] == "top" and item["is_async"] for item in analysis["functions"])
    assert any(item["exception"] == "ValueError('bad')" or "ValueError" in item["exception"] for item in analysis["raises"])
    assert "helper" in analysis["call_map"].get("Sample.run", [])

    payload = build_doc_payload("engram/core/sample.py", analysis)
    section_titles = [section["title"] for section in payload["sections"]]
    assert section_titles == [
        "Role in repository",
        "File map and metrics",
        "Public interfaces and key symbols",
        "Execution/data flow walkthrough",
        "Error handling and edge cases",
        "Integration and dependencies",
        "Safe modification guide",
        "Reading order for large files",
    ]


def test_analyze_non_python_file_variants(tmp_path: Path) -> None:
    json_path = tmp_path / "sample.json"
    json_path.write_text('{"services": {"api": {"port": 8100}}, "token": "x"}\n', encoding="utf-8")

    toml_path = tmp_path / "sample.toml"
    toml_path.write_text("[project]\nname='engram'\n[tool.test]\nkey='value'\n", encoding="utf-8")

    docker_path = tmp_path / "Dockerfile"
    docker_path.write_text("FROM python:3.11\nRUN pip install engram\nCMD ['python']\n", encoding="utf-8")

    html_path = tmp_path / "page.html"
    html_path.write_text(
        "<html><body><div id='root' class='app'></div><script src='/app.js'></script></body></html>",
        encoding="utf-8",
    )

    json_analysis = analyze_non_python_file(json_path)
    assert json_analysis["format"] == "json"
    assert any("services" in key for key in json_analysis["structure"])

    toml_analysis = analyze_non_python_file(toml_path)
    assert toml_analysis["format"] == "toml"
    assert any("project" in key for key in toml_analysis["structure"])

    docker_analysis = analyze_non_python_file(docker_path)
    assert docker_analysis["format"] == "dockerfile"
    assert any(item["instruction"] == "FROM" for item in docker_analysis["instructions"])

    html_analysis = analyze_non_python_file(html_path)
    assert html_analysis["format"] == "html"
    assert any("<div>" in item for item in html_analysis["structure"])
    assert any("app.js" in item for item in html_analysis["integrations"])
