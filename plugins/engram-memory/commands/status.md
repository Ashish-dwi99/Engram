---
name: status
description: Show Engram memory-store health and statistics
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

# /engram:status

Shows a summary of your Engram memory store.

Call the `get_memory_stats` MCP tool with no arguments, then render the
result as a simple markdown table:

| Metric | Value |
|---|---|
| Total memories | … |
| Short-term (SML) | … |
| Long-term (LML) | … |
| … | … |

If the tool returns an error, display it clearly.
