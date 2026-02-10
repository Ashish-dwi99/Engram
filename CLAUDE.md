<!-- ENGRAM_CONTINUITY:START -->
## Engram Continuity (Auto-Generated)

Follow these rules for cross-agent continuity on every new task/thread.

1) Before answering substantive repo/task questions, call `get_last_session`:
- `user_id`: `"default"` unless provided
- `requester_agent_id`: `"claude-code"`
- `repo`: absolute workspace path
- Include `agent_id` only when the user explicitly asks to continue from a specific source agent.

2) If no handoff session exists, continue normally and use memory tools as needed.

3) On major milestones and before pausing/ending, call `save_session_digest` with:
- `task_summary`
- `repo`
- `status` (`"active"`, `"paused"`, or `"completed"`)
- `decisions_made`, `files_touched`, `todos_remaining`
- `blockers`, `key_commands`, `test_results` when available
- `agent_id`: `"claude-code"`, `requester_agent_id`: `"claude-code"`

4) Prefer Engram MCP handoff tools over shell/SQLite inspection for continuity.

Target agent profile: `Claude Code`.
<!-- ENGRAM_CONTINUITY:END -->



