---
name: forget
description: Delete a memory from Engram by ID or by searching first
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

# /engram:forget

Deletes a memory from Engram.

**Usage:** `/engram:forget <memory-id or search query>`

**Logic:**
1. If `$ARGUMENTS` looks like a UUID (contains hyphens and is 36 chars),
   call `delete_memory` directly with that ID.
2. Otherwise, call `search_memory` with `$ARGUMENTS` as the query.
   Present the results to the user and ask which one to delete.
   Once confirmed, call `delete_memory` with the chosen ID.

Always confirm the deletion with the user before proceeding in case (2).
