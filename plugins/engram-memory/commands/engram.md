---
name: engram
description: Engram memory — help and status overview
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

# /engram — Engram Memory Commands

Engram gives Claude Code proactive persistent memory.  Context is injected
automatically on every message; the commands below let you manage memory
on demand.

| Command | What it does |
|---|---|
| `/engram:remember <text>` | Save a fact or preference right now |
| `/engram:search <query>` | Search memories by topic |
| `/engram:forget <id or query>` | Delete a memory (by ID or by searching first) |
| `/engram:status` | Show memory-store health and counts |

---

If `$ARGUMENTS` equals **status**, run `/engram:status` instead.
