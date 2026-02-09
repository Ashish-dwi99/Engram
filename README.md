<h1 align="center">
  <br>
  Engram
  <br>
</h1>

<p align="center">
  <b>Memory layer for AI agents with biologically-inspired forgetting.</b>
</p>

<p align="center">
  <a href="https://github.com/Ashish-dwi99/Engram/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"></a>
  <a href="https://github.com/Ashish-dwi99/Engram/actions"><img src="https://github.com/Ashish-dwi99/Engram/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue.svg" alt="Python 3.9+">
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &middot;
  <a href="#what-is-engram">What is Engram</a> &middot;
  <a href="#key-features">Features</a> &middot;
  <a href="#integrations">Integrations</a> &middot;
  <a href="#rest-api">API</a>
</p>

---

## Quick Start

```bash
pip install -e ".[all]"        # 1. Install
export GEMINI_API_KEY="..."    # 2. Set API key (or OPENAI_API_KEY)
engram install                 # 3. Configure Claude Code, Cursor, Codex
```

Done. Your agents now have persistent memory.

---

## What is Engram

Engram is a memory layer for AI agents. It stores knowledge, forgets what doesn't matter, and strengthens what does — using mechanisms inspired by how biological memory works. It plugs into Claude Code, Cursor, and Codex via MCP, or into any application via REST API and Python SDK.

**100% free, forever. Bring your own API key (Gemini, OpenAI, or Ollama).**

---

## Key Features

- **FadeMem** — Dual-layer memory (short-term / long-term) with Ebbinghaus decay. Memories fade when unused, strengthen when accessed, and promote automatically.
- **EchoMem** — Multi-modal encoding creates multiple retrieval paths (keywords, paraphrases, implications, question forms) for better recall.
- **CategoryMem** — Dynamic hierarchical categories emerge from content and evolve over time. Categories decay too.
- **Scenes** — Episodic memory groups interactions into narrative scenes with time gap and topic shift detection.
- **Profiles** — Character profile extraction tracks entities across conversations.
- **Knowledge Graph** — Entity extraction and linking for relationship reasoning across memories.
- **MCP Server** — Native Model Context Protocol integration for Claude Code, Cursor, and Codex.
- **REST API** — Language-agnostic HTTP API with session tokens, staged writes, and namespace scoping.
- **Hybrid Search** — Combines semantic similarity with keyword matching for better precision.
- **Multi-Agent** — Scoped by user and agent. Agents share knowledge or isolate it.
- **~45% Storage Reduction** — Compared to store-everything approaches.

---

## Installation

### pip (recommended)

```bash
pip install -e ".[all]"
```

### Docker

```bash
docker compose up -d
# API available at http://localhost:8100
```

### From source

```bash
git clone https://github.com/Ashish-dwi99/Engram.git
cd Engram
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
```

Set one API key:

```bash
export GEMINI_API_KEY="your-key"    # Gemini (default)
# or OPENAI_API_KEY for OpenAI
# or OLLAMA_HOST for local Ollama (no key needed)
```

---

## Usage

### MCP Tools

After running `engram install`, your agent gets 14 MCP tools including:

| Tool | Description |
|------|-------------|
| `add_memory` | Store a new memory |
| `search_memory` | Semantic + keyword search |
| `get_all_memories` | List stored memories |
| `update_memory` / `delete_memory` | Modify or remove |
| `apply_memory_decay` | Run forgetting algorithm |
| `engram_context` | Load session digest from prior sessions |
| `remember` | Quick-save a fact (no LLM extraction) |
| `search_scenes` / `get_scene` | Episodic scene retrieval |

### CLI

```bash
engram add "User prefers Python" -u user123
engram search "programming" -u user123
engram list -u user123
engram stats
engram status          # Version, config paths, DB stats
engram serve           # Start REST API
engram decay           # Apply forgetting
engram export -o memories.json
engram import memories.json
```

### Python SDK

```python
from engram import Engram

memory = Engram()
memory.add("User prefers Python", user_id="u123")
results = memory.search("programming preferences", user_id="u123")
```

Full interface with `Memory` class:

```python
from engram import Memory

memory = Memory()
memory.add(content, user_id, agent_id=None, categories=None, metadata=None)
memory.search(query, user_id, limit=10)
memory.get(memory_id)
memory.update(memory_id, content)
memory.delete(memory_id)
memory.promote(memory_id)   # SML -> LML
memory.history(memory_id)
memory.get_related_memories(memory_id)  # Knowledge graph
```

### REST API

```bash
engram-api  # Starts on http://127.0.0.1:8100
```

```bash
# Add memory
curl -X POST http://localhost:8100/v1/memories \
  -H "Content-Type: application/json" \
  -d '{"content": "User prefers dark mode", "user_id": "u123"}'

# Search
curl -X POST http://localhost:8100/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "UI preferences", "user_id": "u123"}'

# Stats
curl "http://localhost:8100/v1/stats?user_id=u123"
```

Full API docs at http://localhost:8100/docs

---

## Integrations

### Claude Code

```bash
engram install   # Writes MCP config to ~/.claude.json
```

The optional **Claude Code plugin** adds proactive memory injection (relevant context is loaded before each reply), slash commands (`/engram:remember`, `/engram:search`, `/engram:status`), and standing instructions.

```bash
# Activate plugin inside Claude Code:
/plugin install engram-memory --path ~/.engram/claude-plugin
```

Requires `engram-api` running for the proactive hook.

### Cursor

`engram install` writes MCP config to `~/.cursor/mcp.json`. Restart Cursor to load.

### OpenAI Codex

`engram install` writes MCP config to `~/.codex/config.toml`. Restart Codex to load.

### OpenClaw

`engram install` deploys the Engram skill to OpenClaw's skills directory.

---

## Architecture

```
Agent (Claude Code / Codex / Cursor / LangChain)
  │
  ▼
┌─────────────────────────────────────────────┐
│                  Engram                      │
│                                              │
│  Knowledge Graph  (entity linking)           │
│  CategoryMem      (dynamic organization)     │
│  EchoMem          (multi-modal encoding)     │
│  FadeMem          (decay & consolidation)    │
│                                              │
│  Embedder: Gemini / OpenAI / Ollama          │
│  Store:    SQLite + in-memory vectors        │
└─────────────────────────────────────────────┘
```

Memories flow through four layers: FadeMem manages lifecycle (decay, promotion, forgetting), EchoMem creates multiple encodings for better retrieval, CategoryMem organizes content into dynamic hierarchies, and the Knowledge Graph links entities across memories.

---

## Contributing

```bash
git clone https://github.com/Ashish-dwi99/Engram.git
cd Engram
pip install -e ".[dev]"
pytest tests/ -v
```

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <b>Built for AI agents that need to remember what matters.</b>
</p>
