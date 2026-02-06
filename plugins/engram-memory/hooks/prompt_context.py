#!/usr/bin/env python3
"""Engram UserPromptSubmit hook — stdlib-only proactive memory injector.

Reads the user prompt from STDIN (or falls back to the USER_PROMPT env var),
queries the running Engram API for relevant memories, and prints a JSON
object with a ``systemMessage`` key that Claude Code will inject into context.

Design constraints
------------------
* stdlib only — runs as a bare subprocess, no pip install
* Phase 1: GET /health with 3 s timeout  – fast-fail if API is down
* Phase 2: POST /v1/search with 6 s timeout
* Query derivation is pure string ops (no LLM call)
* Always exits 0; any failure prints ``{}``
"""

import json
import os
import sys

try:
    from urllib.request import Request, urlopen
    from urllib.error import URLError
except ImportError:  # pragma: no cover – safety net
    sys.stdout.write("{}")
    sys.exit(0)

# ---------------------------------------------------------------------------
# Configuration (all env-overridable)
# ---------------------------------------------------------------------------
API_BASE = os.environ.get("ENGRAM_API_URL", "http://127.0.0.1:8100")
HEALTH_TIMEOUT = 3   # seconds
SEARCH_TIMEOUT = 6   # seconds
MAX_QUERY_CHARS = 120
SENTINEL = "[Engram \u2014 relevant memories from previous sessions]"


def _derive_query(raw: str) -> str:
    """Extract a short query from the raw user prompt (no LLM).

    Takes the first sentence (split on .  !  ?) or the first MAX_QUERY_CHARS
    characters, whichever is shorter.
    """
    raw = raw.strip()
    # Find the end of the first sentence
    for i, ch in enumerate(raw):
        if ch in ".!?" and i > 0:
            candidate = raw[: i + 1].strip()
            if candidate:
                return candidate[:MAX_QUERY_CHARS]
    # No sentence-ending punctuation found — just truncate
    return raw[:MAX_QUERY_CHARS]


def _health_check() -> bool:
    """GET /health — returns True if the API is reachable and healthy."""
    try:
        req = Request(f"{API_BASE}/health")
        resp = urlopen(req, timeout=HEALTH_TIMEOUT)
        return resp.status == 200
    except Exception:
        return False


def _search(query: str) -> list:
    """POST /v1/search — returns the raw results list (may be empty)."""
    payload = json.dumps({"query": query, "limit": 5}).encode("utf-8")
    req = Request(
        f"{API_BASE}/v1/search",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urlopen(req, timeout=SEARCH_TIMEOUT)
    body = json.loads(resp.read().decode("utf-8"))
    return body.get("results", [])


def _format_memories(results: list) -> str:
    """Turn search results into the injected system-message block."""
    lines = [SENTINEL]
    for idx, mem in enumerate(results, 1):
        layer = mem.get("layer", "sml")
        score = mem.get("composite_score", mem.get("score", 0.0))
        content = mem.get("memory", mem.get("content", "")).strip()
        lines.append(f"{idx}. [{layer}, relevance {score:.2f}] {content}")
    return "\n".join(lines)


def main() -> None:
    """Entry point — orchestrates health-check → search → output."""
    # Read the user prompt.  Claude Code may pass it via USER_PROMPT env var
    # or via STDIN depending on hook invocation mode.
    raw_prompt = os.environ.get("USER_PROMPT", "")
    if not raw_prompt:
        try:
            raw_prompt = sys.stdin.read()
        except Exception:
            raw_prompt = ""

    if not raw_prompt.strip():
        sys.stdout.write("{}")
        return

    # Phase 1 – health check (fast-fail)
    if not _health_check():
        sys.stdout.write("{}")
        return

    # Phase 2 – search
    query = _derive_query(raw_prompt)
    results = _search(query)

    if not results:
        sys.stdout.write("{}")
        return

    # Emit the hook response
    output = {"systemMessage": _format_memories(results)}
    sys.stdout.write(json.dumps(output))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Outermost safety net — never crash, never block the user
        sys.stdout.write("{}")
