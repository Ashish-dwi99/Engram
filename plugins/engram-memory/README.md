# engram-memory — Claude Code Plugin

Gives Claude Code **proactive persistent memory** powered by
[Engram](https://github.com/Ashish-dwi99/engram).

## What it does

* **UserPromptSubmit hook** — before Claude sees your message, a lightweight
  script queries Engram and injects relevant memories into the system context.
  Zero latency impact on your typing; the hook runs in the background with an
  8-second ceiling.
* **Slash commands** — `/engram:remember`, `/engram:search`, `/engram:forget`,
  `/engram:status` for on-demand memory operations.
* **Skill (standing instructions)** — tells Claude *when* and *how* to use the
  memory tools automatically.

## Installation

Run `engram install` (requires the Engram package).  The plugin is deployed to
`~/.engram/claude-plugin/engram-memory/`.  Activate it in Claude Code:

```
/plugin install engram-memory --path ~/.engram/claude-plugin
```

## Requirements

* Python 3.8+ (hook script uses only the standard library)
* A running Engram API (`engram-api`) — defaults to `http://127.0.0.1:8100`
* Set `ENGRAM_API_URL` if your API lives elsewhere
