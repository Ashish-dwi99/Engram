---
name: search
description: Search Engram memory by topic or keyword
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

# /engram:search

Searches Engram for memories matching the given query and returns them
as a numbered list.

**Usage:** `/engram:search <query>`

Call the `search_memory` MCP tool with the following arguments:

```json
{
  "query": "$ARGUMENTS",
  "limit": 10
}
```

Format the results as a numbered list:
`1. [<layer>, relevance <score>] <memory content>`

If no results are returned, let the user know nothing matched.
