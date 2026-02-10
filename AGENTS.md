# Repository Guidelines

## Project Structure & Module Organization
- `engram/` is the main package. Core logic lives in `engram/core/` (decay, echo, fusion, conflict), while the user-facing API and orchestration live in `engram/memory/`.
- Integrations are split by concern: `engram/llms/` (Gemini/OpenAI mocks), `engram/embeddings/`, `engram/vector_stores/`, and `engram/db/`.
- Configuration and utilities live in `engram/configs/` and `engram/utils/`.
- Entry points/examples: `engram/mcp_server.py` (MCP server) and `engram/example_agent.py`.
- Tests are simple pytest files in the repo root and package, e.g. `test_echomem.py`, `engram/test_quick.py`, `engram/test_no_api.py`.

## Build, Test, and Development Commands
- `pip install -e ".[dev]"` installs dev extras (pytest, pytest-asyncio).
- `pip install -e ".[gemini,qdrant]"` installs optional runtime dependencies for Gemini + Qdrant.
- `pytest` runs all tests discovered under `test_*.py`.
- `python -m engram.mcp_server` or `engram-mcp` runs the MCP server entry point.

## Coding Style & Naming Conventions
- Python 3.9+ codebase; follow PEP 8 with 4-space indentation.
- Use `snake_case` for functions/variables, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants.
- No formatter/linter is configured in `pyproject.toml`; keep style consistent with surrounding files.

## Testing Guidelines
- Test framework: `pytest` with `pytest-asyncio` for async cases.
- Name new tests `test_*.py` and place them in the repo root or within `engram/` alongside related modules.
- Keep tests isolated from external services unless explicitly marked or documented.

## Commit & Pull Request Guidelines
- Git history shows short, imperative messages (e.g., “added category layer”, “Add EchoMem…”). Keep commits concise and descriptive without enforced scopes.
- PRs should include a brief summary, tests run (e.g., `pytest`), and note any API keys or optional dependencies required to validate the change.

## Configuration & Secrets
- Gemini requires `GEMINI_API_KEY` (or `GOOGLE_API_KEY`). OpenAI uses `OPENAI_API_KEY` via the SDK.
- Never commit secrets; document new environment variables in README or this file when introduced.

<!-- ENGRAM_CONTINUITY:START -->
## Engram Continuity (Auto-Generated)

Follow these rules for cross-agent continuity on every new task/thread.

1) Before answering substantive repo/task questions, call `get_last_session`:
- `user_id`: `"default"` unless provided
- `requester_agent_id`: `"codex"`
- `repo`: absolute workspace path
- Include `agent_id` only when the user explicitly asks to continue from a specific source agent.

2) If no handoff session exists, continue normally and use memory tools as needed.

3) On major milestones and before pausing/ending, call `save_session_digest` with:
- `task_summary`
- `repo`
- `status` (`"active"`, `"paused"`, or `"completed"`)
- `decisions_made`, `files_touched`, `todos_remaining`
- `blockers`, `key_commands`, `test_results` when available
- `agent_id`: `"codex"`, `requester_agent_id`: `"codex"`

4) Prefer Engram MCP handoff tools over shell/SQLite inspection for continuity.

Target agent profile: `Codex/agent-runner`.
<!-- ENGRAM_CONTINUITY:END -->



