---
name: remember
description: Save a fact or preference to Engram memory
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

# /engram:remember

Saves the provided text directly to Engram's long-term memory store.

**Usage:** `/engram:remember <text to remember>`

Call the `remember` MCP tool with the following arguments:

```json
{
  "content": "$ARGUMENTS"
}
```

After the tool returns, confirm to the user that the memory was saved.
