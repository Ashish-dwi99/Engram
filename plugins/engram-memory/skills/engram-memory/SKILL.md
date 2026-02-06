---
name: engram-memory
description: |
  Engram persistent-memory skill. Activates on phrases such as:
  "remember this", "don't forget", "what did we", "recall",
  "from last time", "engram", or when the injected context block
  starting with "[Engram — relevant memories from previous sessions]"
  is present.
version: "1.0"
provider: engram
---

# Engram Memory — Standing Instructions

You have access to a persistent memory store via Engram MCP tools.
A UserPromptSubmit hook may have already injected relevant context into
this conversation; look for the sentinel line
**[Engram — relevant memories from previous sessions]**.

Follow the five rules below on every turn.

---

## Rule 1 — Consume injected context silently

If the sentinel block is present, read and use it to inform your reply.
Do **not** paste or quote the raw injected block to the user.  Weave the
information naturally into your response.

## Rule 2 — Proactively save when the user signals intent

Call `remember` when you see any of:
* An explicit "remember this" or "don't forget" instruction
* A user correction to something previously stored
* A stated preference or recurring pattern

Do **not** spam the store — one clean save per signal is enough.

## Rule 3 — Search on explicit recall requests

When the user says something like "what did we …", "recall …", or
"from last time …", call `search_memory` with a short query derived
from their words.  Present results naturally; do not show raw JSON.

## Rule 4 — Stay quiet about the plumbing

Never mention hooks, plugin files, MCP transport, or internal URLs
unless the user explicitly asks how memory works.

## Rule 5 — Tool selection guide

| User intent | Tool to call | Key params |
|---|---|---|
| Quick save (no categories) | `remember` | `content` |
| Save with categories / scope | `add_memory` | `content`, `categories`, `scope` |
| Find something from before | `search_memory` | `query`, `limit` |
| Browse all memories | `get_all_memories` | `user_id`, `limit` |
| Load session context | `engram_context` | `limit` (default 15) |
| Fix something already stored | `update_memory` | `memory_id`, `content` |
| User wants to forget something | `delete_memory` | `memory_id` |
| Check memory health | `get_memory_stats` | — |
| Explicit maintenance only | `apply_memory_decay` | — |
