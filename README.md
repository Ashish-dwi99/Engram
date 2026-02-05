<h1 align="center">
  <br>
  Engram
  <br>
</h1>

<h3 align="center">
  The Memory Layer for AI Agent Orchestrators
</h3>

<p align="center">
  <b>Give your agents persistent memory that learns, forgets, and shares knowledge like humans do.</b>
  <br><br>
  Native MCP integration for <b>Claude Code</b>, <b>Cursor</b>, and <b>OpenAI Codex</b>.<br>
  Bio-inspired architecture: memories strengthen with use, fade when irrelevant.<br>
  Multi-agent knowledge sharing with user and agent scoping.
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-why-engram">Why Engram</a> •
  <a href="#-multi-agent-memory">Multi-Agent</a> •
  <a href="#-claude-code-cursor--codex-setup">Claude Code, Cursor & Codex</a> •
  <a href="#-api-reference">API</a>
</p>

---

## Why Engram?

| Feature | Other Memory Layers | **Engram** |
|---------|---------------------|------------|
| Bio-inspired forgetting | No | **Ebbinghaus decay** |
| Multi-modal encoding | No | **5 modes (echo)** |
| Knowledge graph | Sometimes | **Entity linking** |
| Dynamic categories | Rare | **Auto-discovered** |
| Category decay | No | **Bio-inspired** |
| Hybrid search | Vector only | **Semantic + Keyword** |
| Storage efficiency | Store everything | **~45% less** |
| MCP Server | Rare | **Claude/Cursor/Codex** |
| Local LLMs (Ollama) | Sometimes | **Yes** |
| Self-hosted | Cloud-first | **Local-first** |

**Engram is different.** While other memory layers store everything forever, Engram uses bio-inspired mechanisms:

- **Memories fade** when not accessed (Ebbinghaus decay curve)
- **Important memories strengthen** through repeated access and get promoted to long-term storage
- **Echo encoding** creates multiple retrieval paths (keywords, paraphrases, implications)
- **Dynamic categories** emerge from content and evolve over time
- **Knowledge graph** links memories by shared entities for relationship reasoning
- **Hybrid search** combines semantic similarity with keyword matching

The result: **better retrieval precision, lower storage costs, and memories that actually matter.**

---

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/Ashish-dwi99/Engram.git
cd Engram

# Install with all dependencies
pip install -e ".[all]"

# Set your API key
export GEMINI_API_KEY="your-key"  # or OPENAI_API_KEY
```

Or install directly from GitHub:
```bash
pip install "engram[all] @ git+https://github.com/Ashish-dwi99/Engram.git"
```

### Usage

```python
from engram import Engram

memory = Engram()
memory.add("User prefers Python over JavaScript", user_id="u123")
results = memory.search("programming preferences", user_id="u123")
```

---

## Multi-Agent Memory

Engram is designed for agent orchestrators. Every memory is scoped by `user_id` and optionally `agent_id`, enabling:

### Knowledge Isolation

```python
# Agent 1 stores knowledge
memory.add("Project deadline is Friday", user_id="project_x", agent_id="planner")

# Agent 2 stores different knowledge
memory.add("Budget is $50k", user_id="project_x", agent_id="analyst")

# Search across all agents for a user
all_results = memory.search("project details", user_id="project_x")

# Search only one agent's knowledge
planner_results = memory.search("deadlines", user_id="project_x", agent_id="planner")
```

### Cross-Agent Knowledge Sharing

```python
# Researcher agent discovers information
memory.add(
    "The API rate limit is 100 req/min",
    user_id="team_alpha",
    agent_id="researcher",
    categories=["technical", "api"]
)

# Coder agent can access shared knowledge
results = memory.search("rate limits", user_id="team_alpha")
# Returns the researcher's finding
```

### Memory Layers for Different Retention

```python
# Short-term (SML): Fast decay, recent context
# Long-term (LML): Slow decay, important facts

# Get only long-term memories
important = memory.get_all(user_id="u123", layer="lml")

# Memories auto-promote based on access patterns
# Or manually promote critical information
memory.promote(memory_id="abc123")
```

### Agent-Specific Statistics

```python
stats = memory.stats(user_id="project_x", agent_id="planner")
# {
#   "total": 42,
#   "sml_count": 30,
#   "lml_count": 12,
#   "avg_strength": 0.73,
#   "categories": ["deadlines", "tasks", "dependencies"]
# }
```

---

## Claude Code, Cursor & Codex Setup

Engram provides a native MCP (Model Context Protocol) server for seamless integration with Claude Code, Cursor, and OpenAI Codex.

### Automatic Installation

After [installing Engram](#quick-start), run:

```bash
engram-install
```

This detects and configures:
- Claude Code CLI (`~/.claude.json`)
- Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`)
- Cursor (`~/.cursor/mcp.json`)
- OpenAI Codex (`~/.codex/config.toml`)
- Claude Code plugin (proactive hook + `/engram` commands + skill)

### Manual Configuration

#### Claude Code / Claude Desktop

Add to `~/.claude.json` (CLI) or `claude_desktop_config.json` (Desktop):

```json
{
  "mcpServers": {
    "engram-memory": {
      "command": "python",
      "args": ["-m", "engram.mcp_server"],
      "env": {
        "GEMINI_API_KEY": "your-api-key"
      }
    }
  }
}
```

#### Cursor

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "engram-memory": {
      "command": "python",
      "args": ["-m", "engram.mcp_server"],
      "env": {
        "GEMINI_API_KEY": "your-api-key"
      }
    }
  }
}
```

> **Note:** If the file doesn't exist, create it. You can also configure MCP servers through Cursor's Settings UI under the MCP section.

#### OpenAI Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.engram-memory]
command = "python"
args = ["-m", "engram.mcp_server"]

[mcp_servers.engram-memory.env]
GEMINI_API_KEY = "your-api-key"
```

### Claude Code Plugin (Proactive Memory)

The MCP tools above let Claude *react* to your requests. The **Claude Code plugin** makes memory *proactive* — relevant context is injected automatically before Claude even sees your message.

`engram-install` deploys the plugin to `~/.engram/claude-plugin/engram-memory/`. To activate it inside Claude Code, run:

```
/plugin install engram-memory --path ~/.engram/claude-plugin
```

> **Requires a running Engram API** (`engram-api`) for the hook to fetch memories. If the API is down the hook exits silently — nothing breaks, you just don't get the auto-injection.

#### What the plugin adds

| Piece | What it does |
|---|---|
| **UserPromptSubmit hook** | Before each reply, queries Engram and injects matching memories into Claude's context. Stdlib-only script, no extra deps. |
| `/engram:remember <text>` | Save a fact or preference on the spot |
| `/engram:search <query>` | Search memories by topic |
| `/engram:forget <id or query>` | Delete a memory (confirms before removing) |
| `/engram:status` | Show memory-store stats at a glance |
| **Skill (standing instructions)** | Tells Claude when to save, when to search, and how to surface injected context naturally |

#### How the hook works

```
User types a message
  → hook reads it, extracts a short query (no LLM, pure string ops)
  → GET /health  (3 s timeout — fast-fail if API is down)
  → POST /v1/search  (6 s timeout)
  → matching memories injected as a system message
  → Claude replies with that context already loaded
```

Total added latency is typically under 2 seconds, well within the 8-second hook timeout. On any failure the hook outputs `{}` and Claude proceeds normally.

---

### Available MCP Tools

Once configured, your agent has access to these tools:

| Tool | Description | Example Use |
|------|-------------|-------------|
| `add_memory` | Store a new memory | "Remember that the user prefers dark mode" |
| `search_memory` | Find relevant memories | "What are the user's UI preferences?" |
| `get_all_memories` | List all stored memories | "Show me everything I know about this user" |
| `get_memory` | Get a specific memory by ID | Retrieve exact memory content |
| `update_memory` | Update memory content | Correct outdated information |
| `delete_memory` | Remove a memory | Remove sensitive or incorrect data |
| `get_memory_stats` | Get storage statistics | Monitor memory health |
| `apply_memory_decay` | Run forgetting algorithm | Periodic cleanup of stale memories |
| `engram_context` | Load session digest from prior sessions | Call once at conversation start; returns top memories, LML first |
| `remember` | Quick-save a fact or preference | Stores directly with `source_app=claude-code`, no LLM extraction |

### Example: Claude Code with Memory

**Without the plugin** — Claude reacts to explicit requests via MCP tools:

```
You: Remember that I prefer using TypeScript for all new projects

Claude: I'll remember that preference for you.
[Calls remember tool → stored with source_app=claude-code]
```

**With the plugin** — memory is proactive and invisible:

```
--- Session A ---
You: /engram:remember I prefer TypeScript for all new projects
Claude: Saved to memory.

--- Session B (new conversation, no history) ---
You: What stack should I use for the new API?

[Hook runs silently: queries Engram, injects "TypeScript preference" into context]

Claude: Based on your preferences, I'd recommend TypeScript...
        (no search_memory call needed — context was already there)
```

### Example: Multi-Agent Codex Workflow

```python
# Agent 1: Research Agent
memory.add(
    "The target API uses OAuth 2.0 with JWT tokens",
    user_id="project_123",
    agent_id="researcher"
)

# Agent 2: Implementation Agent searches shared knowledge
results = memory.search("authentication method", user_id="project_123")
# Finds: "OAuth 2.0 with JWT tokens"

# Agent 3: Review Agent adds findings
memory.add(
    "Security review passed for OAuth implementation",
    user_id="project_123",
    agent_id="reviewer"
)
```

---

## REST API

Start the HTTP API server for language-agnostic integration:

```bash
engram-api  # Starts on http://127.0.0.1:8100
```

### Endpoints

```bash
# Add memory
curl -X POST http://localhost:8100/v1/memories \
  -H "Content-Type: application/json" \
  -d '{"content": "User prefers dark mode", "user_id": "u123", "agent_id": "ui_agent"}'

# Search memories
curl -X POST http://localhost:8100/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "UI preferences", "user_id": "u123"}'

# Get all memories
curl "http://localhost:8100/v1/memories?user_id=u123"

# Get statistics
curl "http://localhost:8100/v1/stats?user_id=u123"

# Apply decay (forgetting)
curl -X POST http://localhost:8100/v1/decay \
  -H "Content-Type: application/json" \
  -d '{"user_id": "u123"}'

# Get categories
curl "http://localhost:8100/v1/categories?user_id=u123"
```

API documentation: http://localhost:8100/docs

---

## How It Works

Engram combines three bio-inspired memory systems:

### FadeMem: Decay & Consolidation

```
┌─────────────────────────────────────────────────────────┐
│                    Memory Lifecycle                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  New Memory → Short-term (SML)                          │
│                    │                                    │
│                    │ Accessed frequently?               │
│                    ▼                                    │
│              ┌─────────┐                                │
│         No ← │ Decay   │ → Yes                          │
│              └─────────┘                                │
│              │         │                                │
│              ▼         ▼                                │
│         Forgotten   Promoted to Long-term (LML)         │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

- **Adaptive Decay**: Memories fade based on time and access patterns
- **Dual-Layer Architecture**: Short-term (fast decay) → Long-term (slow decay)
- **Automatic Promotion**: Frequently accessed memories get promoted
- **Conflict Resolution**: LLM detects contradictions and updates old info
- **~45% Storage Reduction**: Compared to store-everything approaches

### EchoMem: Multi-Modal Encoding

```
Input: "User prefers TypeScript over JavaScript"
                    │
                    ▼
┌─────────────────────────────────────────────────────────┐
│                  Stored Memory                          │
├─────────────────────────────────────────────────────────┤
│  raw: "User prefers TypeScript over JavaScript"         │
│  paraphrase: "TypeScript is the user's preferred..."    │
│  keywords: ["typescript", "javascript", "preference"]   │
│  implications: ["values type safety", "modern tooling"] │
│  question_form: "What language does the user prefer?"   │
│  strength: 1.3x (medium depth)                          │
└─────────────────────────────────────────────────────────┘
```

- **Multiple Retrieval Paths**: Keywords, paraphrases, implications, questions
- **Importance-Based Depth**: Critical info gets deeper processing (1.6x strength)
- **Better Query Matching**: Question-form embeddings match search queries
- **Re-Echo on Access**: Accessed memories get stronger encoding

### CategoryMem: Dynamic Organization

```
┌─────────────────────────────────────────────────────────┐
│                  Auto-Generated Categories               │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  preferences/              technical/                   │
│  ├── coding/               ├── apis/                    │
│  │   ├── languages (3)     │   └── rate_limits (2)      │
│  │   └── tools (2)         └── infrastructure (4)       │
│  └── ui (4)                                             │
│                                                         │
│  projects/                 corrections/                 │
│  └── active (6)            └── learned (2)              │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

- **Dynamic Categories**: Auto-discovered from content, not predefined
- **Category Decay**: Unused categories weaken and merge
- **Category-Aware Search**: Boost results from relevant categories
- **Hierarchical Structure**: Up to 3 levels of nesting

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Orchestrator                           │
│              (Claude Code / Codex / LangChain / etc.)           │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐
        │ Agent 1  │   │ Agent 2  │   │ Agent 3  │
        │ (user,   │   │ (user,   │   │ (user,   │
        │  agent)  │   │  agent)  │   │  agent)  │
        └──────────┘   └──────────┘   └──────────┘
              │               │               │
              └───────────────┼───────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Engram                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                 Knowledge Graph Layer                     │  │
│  │            (Entity Extraction & Linking)                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   CategoryMem Layer                       │  │
│  │           (Dynamic Hierarchical Organization)             │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                     EchoMem Layer                         │  │
│  │         (Multi-Modal Encoding & Retrieval)                │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                     FadeMem Layer                         │  │
│  │           (Decay, Promotion & Consolidation)              │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   Embedder   │  │     LLM      │  │    Vector Store      │  │
│  │   (Gemini/   │  │  (Gemini/    │  │  (Qdrant/In-memory)  │  │
│  │ OpenAI/Ollama│  │ OpenAI/Ollama│  │                      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## API Reference

### Engram Class (Simple Interface)

```python
from engram import Engram

memory = Engram(
    provider="gemini",      # or "openai", "ollama" - auto-detected from env
    in_memory=False,        # True for testing
    enable_echo=True,       # Multi-modal encoding
    enable_categories=True, # Dynamic categorization
    enable_graph=True       # Knowledge graph for entity linking
)

# Add memory
memory.add(content, user_id, agent_id=None, categories=None, metadata=None)

# Search memories
memory.search(query, user_id, agent_id=None, limit=10, categories=None)

# Get all memories
memory.get_all(user_id, agent_id=None, layer=None, limit=100)

# Get statistics
memory.stats(user_id=None, agent_id=None)

# Apply decay (forgetting)
memory.decay(user_id=None, agent_id=None)
```

### Memory Class (Full Interface)

```python
from engram import Memory
from engram.configs.base import MemoryConfig

config = MemoryConfig(
    # Vector store: "qdrant" or "memory"
    # LLM: "gemini" or "openai"
    # FadeMem, EchoMem, CategoryMem configs
)

memory = Memory(config)

# All Engram methods plus:
memory.get(memory_id)
memory.update(memory_id, content)
memory.delete(memory_id)
memory.delete_all(user_id=None, agent_id=None)
memory.history(memory_id)
memory.promote(memory_id)  # SML → LML
memory.demote(memory_id)   # LML → SML
memory.fuse(memory_ids)    # Combine related memories

# Category methods
memory.get_category_tree()
memory.get_all_summaries()
memory.search_by_category(category_id)

# Knowledge graph methods
memory.get_related_memories(memory_id)   # Graph traversal
memory.get_memory_entities(memory_id)    # Extracted entities
memory.get_entity_memories(entity_name)  # Memories with entity
memory.get_memory_graph(memory_id)       # Visualization data
memory.get_graph_stats()                 # Graph statistics
```

### Async Support

```python
from engram.memory.async_memory import AsyncMemory

async with AsyncMemory() as memory:
    await memory.add("User prefers Python", user_id="u1")
    results = await memory.search("programming", user_id="u1")
```

---

## Configuration

### Environment Variables

```bash
# LLM & Embeddings (choose one)
export GEMINI_API_KEY="your-key"    # Gemini (default)
export OPENAI_API_KEY="your-key"    # OpenAI
export OLLAMA_HOST="http://localhost:11434"  # Ollama (local, no key needed)

# Optional: Vector store
export QDRANT_HOST="localhost"
export QDRANT_PORT="6333"
```

### Full Configuration

```python
from engram.configs.base import (
    MemoryConfig,
    FadeMemConfig,
    EchoMemConfig,
    CategoryMemConfig,
)

config = MemoryConfig(
    # FadeMem: Decay & consolidation
    fadem=FadeMemConfig(
        enable_forgetting=True,
        sml_decay_rate=0.15,      # Short-term decay
        lml_decay_rate=0.02,      # Long-term decay
        promotion_access_threshold=3,
        forgetting_threshold=0.1,
    ),

    # EchoMem: Multi-modal encoding
    echo=EchoMemConfig(
        enable_echo=True,
        auto_depth=True,
        shallow_multiplier=1.0,
        medium_multiplier=1.3,
        deep_multiplier=1.6,
    ),

    # CategoryMem: Dynamic organization
    category=CategoryMemConfig(
        enable_categories=True,
        auto_categorize=True,
        enable_category_decay=True,
        max_category_depth=3,
    ),
)
```

---

## CLI

```bash
# Install MCP server for Claude/Cursor/Codex
engram-install

# Start REST API server
engram-api

# Start MCP server directly
engram-mcp

# Interactive commands
engram add "User prefers Python" --user u123
engram search "programming" --user u123
engram list --user u123
engram stats --user u123
engram decay --user u123
engram categories --user u123
engram export --user u123 --output memories.json
engram import memories.json --user u123  # Import from Engram/Mem0 format
```

---

## Research

Engram is based on the paper:

> **FadeMem: Biologically-Inspired Forgetting for Efficient Agent Memory**
>
> arXiv:2601.18642

### Key Results

| Metric | Improvement |
|--------|-------------|
| Storage Reduction | ~45% |
| Multi-hop Reasoning | +12% accuracy |
| Retrieval Precision | +8% on LTI-Bench |

### Biological Inspiration

- **Ebbinghaus Forgetting Curve** → Exponential decay
- **Spaced Repetition** → Access boosts strength
- **Sleep Consolidation** → SML → LML promotion
- **Production Effect** → Echo encoding improves retention
- **Elaborative Encoding** → Deeper processing = stronger memory

---

## Contributing

```bash
git clone https://github.com/Ashish-dwi99/Engram.git
cd Engram
pip install -e ".[dev]"
pytest
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

<p align="center">
  <b>Built for AI agents that need to remember what matters.</b>
</p>

<p align="center">
  <a href="https://github.com/Ashish-dwi99/Engram">GitHub</a> •
  <a href="https://github.com/Ashish-dwi99/Engram/issues">Issues</a>
</p>
