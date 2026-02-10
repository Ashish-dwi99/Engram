<h1 align="center">
  <br>
  <img src="https://img.shields.io/badge/engram-PMK-black?style=for-the-badge" alt="Engram" height="32">
  <br>
  Engram
  <br>
</h1>

<h3 align="center">
  The Personal Memory Kernel for AI Agents
</h3>

<p align="center">
  A user-owned memory store that any agent can plug into to become instantly personalized.<br>
  Agents read via scoped retrieval. Writes land in staging until you approve.
</p>

<p align="center">
  <a href="https://pypi.org/project/engram"><img src="https://img.shields.io/badge/python-3.9%2B-blue.svg" alt="Python 3.9+"></a>
  <a href="https://github.com/Ashish-dwi99/Engram/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"></a>
  <a href="https://github.com/Ashish-dwi99/Engram/actions"><img src="https://github.com/Ashish-dwi99/Engram/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://github.com/Ashish-dwi99/Engram"><img src="https://img.shields.io/github/stars/Ashish-dwi99/Engram?style=social" alt="GitHub Stars"></a>
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> &middot;
  <a href="#-why-engram">Why Engram</a> &middot;
  <a href="#%EF%B8%8F-architecture">Architecture</a> &middot;
  <a href="#-integrations">Integrations</a> &middot;
  <a href="#-api--sdk">API & SDK</a> &middot;
  <a href="https://github.com/Ashish-dwi99/Engram/blob/main/CHANGELOG.md">Changelog</a>
</p>

---

## Why Engram

Every AI agent you use starts with amnesia. Your coding assistant forgets your preferences between sessions. Your planning agent has no idea what your research agent discovered yesterday. You end up re-explaining context that should already be known.

**Engram fixes this.** It's a Personal Memory Kernel (PMK) — a single memory store that sits between you and all your agents. Any agent can plug in via MCP or REST to become instantly personalized, without you having to repeat yourself.

But unlike "store everything forever" approaches, Engram treats agents as **untrusted writers**. Writes land in staging. You control what sticks. And memories that stop being useful fade away naturally — just like biological memory.

| Capability | Other Memory Layers | **Engram** |
|:-----------|:--------------------|:-----------|
| Bio-inspired forgetting | No | **Ebbinghaus decay curve** |
| Untrusted agent writes | Store directly | **Staging + verification + conflict stash** |
| Episodic narrative memory | No | **CAST scenes (time/place/topic)** |
| Multi-modal encoding | Rare | **5 retrieval paths (EchoMem)** |
| Cross-agent memory sharing | Per-agent silos | **Scoped retrieval with masking** |
| Knowledge graph | Sometimes | **Entity extraction + linking** |
| Reference-aware decay | No | **If other agents use it, don't delete it** |
| Hybrid search | Vector only | **Semantic + keyword + episodic** |
| Storage efficiency | Store everything | **~45% less** |
| MCP + REST | One or the other | **Both, plug-and-play** |
| Local-first | Cloud-required | **127.0.0.1:8100 by default** |

---

## Quick Start

```bash
pip install -e ".[all]"            # 1. Install
export GEMINI_API_KEY="your-key"   # 2. Set one API key (or OPENAI_API_KEY, or OLLAMA_HOST)
engram install                     # 3. Auto-configure Claude Code, Cursor, Codex
```

Restart your agent. Done — it now has persistent memory across sessions.

**Or with Docker:**

```bash
docker compose up -d               # API at http://localhost:8100
```

---

## Architecture

Engram is a **Personal Memory Kernel** — not just a vector store with an API. It has opinions about how memory should work:

1. **Agents are untrusted writers.** Every write is a proposal that lands in staging. Trusted agents can auto-merge; untrusted ones wait for approval.
2. **Memory has a lifecycle.** New memories start in short-term (SML), get promoted to long-term (LML) through repeated access, and fade away through Ebbinghaus decay if unused.
3. **Scoping is mandatory.** Every memory is scoped by user. Agents see only what they're allowed to — everything else gets the "all but mask" treatment (structure visible, details redacted).

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Orchestrator                            │
│              (Claude Code / Cursor / Codex / Custom)             │
└─────────────────────────┬───────────────────────────────────────┘
                          │
              ┌───────────┴───────────┐
              │                       │
              ▼                       ▼
        ┌──────────┐           ┌──────────┐
        │   MCP    │           │   REST   │
        │  Server  │           │   API    │
        └────┬─────┘           └────┬─────┘
             └───────────┬──────────┘
                         ▼
        ┌────────────────────────────────────┐
        │         Policy Gateway             │
        │   Scopes · Masking · Quotas ·      │
        │   Capability Tokens · Trust Score  │
        └────────────────┬───────────────────┘
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
   ┌──────────────────┐  ┌──────────────────┐
   │  Retrieval Engine │  │ Ingestion Pipeline│
   │  ┌─────────────┐ │  │                  │
   │  │Semantic     │ │  │  Text → Views    │
   │  │(hybrid+graph│ │  │  Views → Scenes  │
   │  │+categories) │ │  │  Scenes → LML    │
   │  ├─────────────┤ │  │                  │
   │  │Episodic     │ │  └────────┬─────────┘
   │  │(CAST scenes)│ │           │
   │  └─────────────┘ │           ▼
   │                  │  ┌──────────────────┐
   │  Intersection    │  │Write Verification│
   │  Promotion:      │  │                  │
   │  match in both → │  │ Invariant checks │
   │  boost score     │  │ Conflict → stash │
   └──────────────────┘  │ Trust scoring    │
                         └────────┬─────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
   ┌──────────────────┐  ┌──────────────┐  ┌──────────────────┐
   │  Staging (SML)   │  │ Long-Term    │  │    Indexes       │
   │  Proposals+Diffs │  │ Store (LML)  │  │ Vector + Graph   │
   │  Conflict Stash  │  │ Canonical    │  │ + Episodic       │
   └──────────────────┘  └──────────────┘  └──────────────────┘
              │                   │                   │
              └───────────────────┼───────────────────┘
                                  ▼
                       ┌──────────────────┐
                       │   FadeMem GC     │
                       │  Ref-aware decay │
                       │  If other agents │
                       │  use it → keep   │
                       └──────────────────┘
```

### The Memory Stack

Engram combines four bio-inspired memory systems, each handling a different aspect of how humans actually remember:

#### FadeMem — Decay & Consolidation

Memories fade based on time and access patterns, following the Ebbinghaus forgetting curve. Frequently accessed memories get promoted from short-term (SML) to long-term (LML). Unused memories weaken and eventually get forgotten. **Reference-aware:** if other agents still reference a memory, it won't be garbage collected — even if the original agent stopped using it.

```
New Memory → Short-term (SML)
                  │
                  │ Accessed frequently?
                  ▼
            ┌──────────┐
       No ← │  Decay   │ → Yes
            └──────────┘
            │           │
            ▼           ▼
       Forgotten    Promoted to Long-term (LML)
```

#### EchoMem — Multi-Modal Encoding

Each memory is encoded through multiple retrieval paths — keywords, paraphrases, implications, and question forms. This creates 5x the retrieval surface area compared to single-embedding approaches. Important memories get deeper processing (1.6x strength multiplier).

```
Input: "User prefers TypeScript over JavaScript"
  ↓
  raw:          "User prefers TypeScript over JavaScript"
  paraphrase:   "TypeScript is the user's preferred language"
  keywords:     ["typescript", "javascript", "preference"]
  implications: ["values type safety", "modern tooling"]
  question:     "What language does the user prefer?"
```

#### CategoryMem — Dynamic Organization

Categories aren't predefined — they emerge from content and evolve over time. As new memories arrive, the category tree grows, splits, and merges. Categories themselves decay when unused, keeping the taxonomy clean.

#### CAST Scenes — Episodic Narrative Memory

Inspired by the Contextual Associative Scene Theory of memory, Engram clusters interactions into **scenes** defined by three dimensions: time, place, and topic. Each scene has characters, a synopsis, and links to the semantic memories extracted from it.

```
Scene: "Engram v2 architecture session"
  Time:       2026-02-09 12:00–12:25
  Place:      repo:Engram (digital)
  Characters: [self, collaborator]
  Synopsis:   "Designed staged writes and scoped retrieval..."
  Views:      [view_1, view_2, view_3]
  Memories:   [mem_1, mem_2]  ← semantic facts extracted
```

---

### Key Flows

#### Read: Query → Context Packet

```
Agent calls search_memory or POST /v1/search
  → Policy Gateway enforces scope, quotas, masking
  → Dual retrieval: semantic index + episodic index (parallel)
  → Intersection promotion: results matching in both get boosted
  → Returns Context Packet (token-budgeted, with scene citations)
```

The dual retrieval approach reduces "similar but wrong time/place" errors. If a memory appears in both semantic search and the relevant episodic scene, it gets a confidence boost.

#### Write: Agent Proposal → Staging

```
Agent calls propose_write or POST /v1/memories
  → Lands in Staging SML as a Proposal Commit
  → Provenance recorded (agent, time, scope, trust score)
  → Verification runs:
      • Invariant contradiction check → stash if conflict
      • Duplication detection
      • PII risk detection → require manual approval if high
  → High-trust agents: auto-merge
  → Others: wait for user approval or daily digest
```

#### "All But Mask" Policy

When an agent queries data outside its scope, it sees structure but not details:

```json
{
  "type": "private_event",
  "time": "2026-02-10T17:00:00Z",
  "importance": "high",
  "details": "[REDACTED]"
}
```

Agents can still operate (scheduling, planning) without seeing secrets.

---

## Integrations

Engram is plug-and-play. Run `engram install` and it auto-configures everything:

### Claude Code (MCP + Plugin)

```bash
engram install    # Writes MCP config to ~/.claude.json
```

**MCP tools** give Claude reactive memory — it stores and retrieves when you ask.

The optional **Claude Code plugin** makes memory **proactive** — relevant context is injected automatically before Claude sees your message:

```bash
# Inside Claude Code:
/plugin install engram-memory --path ~/.engram/claude-plugin
```

What the plugin adds:

| Component | What it does |
|:----------|:-------------|
| **UserPromptSubmit hook** | Before each reply, queries Engram and injects matching memories into context. Stdlib-only, no extra deps. Under 2s latency. |
| `/engram:remember <text>` | Save a fact or preference on the spot |
| `/engram:search <query>` | Search memories by topic |
| `/engram:forget <id>` | Delete a memory (confirms before removing) |
| `/engram:status` | Show memory-store stats at a glance |
| **Skill** | Standing instructions telling Claude when to save, search, and surface memories |

**Without plugin** — Claude reacts to explicit requests:
```
You: Remember that I prefer TypeScript
Claude: [calls remember tool] Done.
```

**With plugin** — memory is proactive and invisible:
```
--- Session A ---
You: /engram:remember I prefer TypeScript for all new projects

--- Session B (new conversation, no history) ---
You: What stack should I use for the new API?
[Hook injects "TypeScript preference" before Claude sees the message]
Claude: Based on your preferences, I'd recommend TypeScript...
```

### Cursor

`engram install` writes MCP config to `~/.cursor/mcp.json`. Restart Cursor to load.

### OpenAI Codex

`engram install` writes MCP config to `~/.codex/config.toml`. Restart Codex to load.

### OpenClaw

`engram install` deploys the Engram skill to OpenClaw's skills directory.

### Any Agent Runtime

Any tool-calling agent can connect via REST:

```bash
engram-api    # Starts on http://127.0.0.1:8100
```

---

## MCP Tools

Once configured, your agent has access to these tools:

| Tool | Description |
|:-----|:------------|
| `add_memory` | Store a new memory (lands in staging by default) |
| `search_memory` | Semantic + keyword + episodic search |
| `get_all_memories` | List all stored memories for a user |
| `get_memory` | Get a specific memory by ID |
| `update_memory` | Update memory content |
| `delete_memory` | Remove a memory |
| `get_memory_stats` | Storage statistics and health |
| `apply_memory_decay` | Run the forgetting algorithm |
| `engram_context` | Session-start digest — load top memories from prior sessions |
| `remember` | Quick-save a fact (no LLM extraction, stores directly) |
| `propose_write` | Create a staged write proposal (default safe path) |
| `list_pending_commits` | Inspect staged write queue |
| `resolve_conflict` | Resolve invariant conflicts (accept proposed or keep existing) |
| `search_scenes` / `get_scene` | Episodic CAST scene retrieval with masking policy |

---

## API & SDK

### REST API

```bash
engram-api    # http://127.0.0.1:8100
              # Interactive docs at /docs
```

```bash
# 1. Create a capability session token
curl -X POST http://localhost:8100/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "u123",
    "agent_id": "planner",
    "allowed_confidentiality_scopes": ["work", "personal"],
    "capabilities": ["search", "propose_write", "read_scene"],
    "ttl_minutes": 1440
  }'

# 2. Propose a write (default: staging)
curl -X POST http://localhost:8100/v1/memories \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"content": "User prefers dark mode", "user_id": "u123", "mode": "staging"}'

# 3. Search (returns context packet with scene citations)
curl -X POST http://localhost:8100/v1/search \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"query": "UI preferences", "user_id": "u123"}'

# 4. Review staged commits
curl "http://localhost:8100/v1/staging/commits?user_id=u123&status=PENDING"
curl -X POST http://localhost:8100/v1/staging/commits/<id>/approve

# 5. Episodic scene search
curl -X POST http://localhost:8100/v1/scenes/search \
  -H "Content-Type: application/json" \
  -d '{"query": "architecture discussion", "user_id": "u123"}'

# 6. Namespace & trust management
curl -X POST http://localhost:8100/v1/namespaces \
  -d '{"user_id": "u123", "namespace": "workbench"}'
curl "http://localhost:8100/v1/trust?user_id=u123&agent_id=planner"

# 7. Sleep-cycle maintenance
curl -X POST http://localhost:8100/v1/sleep/run \
  -d '{"user_id": "u123", "apply_decay": true, "cleanup_stale_refs": true}'
```

### Python SDK

```python
from engram import Engram

memory = Engram()

# Add a memory
memory.add("User prefers Python over JavaScript", user_id="u123")

# Search with dual retrieval
results = memory.search("programming preferences", user_id="u123")

# Cross-agent knowledge sharing
memory.add(
    "The API rate limit is 100 req/min",
    user_id="team_alpha",
    agent_id="researcher",
    categories=["technical", "api"]
)

# Another agent finds it
results = memory.search("rate limits", user_id="team_alpha")
```

**Full Memory interface:**

```python
from engram import Memory

memory = Memory()

# Lifecycle
memory.add(content, user_id, agent_id=None, categories=None, metadata=None)
memory.get(memory_id)
memory.update(memory_id, content)
memory.delete(memory_id)

# Search
memory.search(query, user_id, agent_id=None, limit=10, categories=None)
memory.get_all(user_id, agent_id=None, layer=None, limit=100)

# Memory management
memory.promote(memory_id)                # SML → LML
memory.demote(memory_id)                 # LML → SML
memory.fuse(memory_ids)                  # Combine related memories
memory.decay(user_id=None)               # Apply forgetting
memory.history(memory_id)                # Access history

# Knowledge graph
memory.get_related_memories(memory_id)   # Graph traversal
memory.get_memory_entities(memory_id)    # Extracted entities
memory.get_entity_memories(entity_name)  # All memories with entity
memory.get_memory_graph(memory_id)       # Visualization data

# Categories
memory.get_category_tree()
memory.search_by_category(category_id)
memory.stats(user_id=None, agent_id=None)
```

**Async support:**

```python
from engram.memory.async_memory import AsyncMemory

async with AsyncMemory() as memory:
    await memory.add("User prefers Python", user_id="u1")
    results = await memory.search("programming", user_id="u1")
```

### CLI

```bash
engram install                     # Auto-configure all integrations
engram status                      # Version, config paths, DB stats
engram serve                       # Start REST API server

engram add "User prefers Python"   # Add a memory
engram search "preferences"        # Search
engram list --layer lml            # List long-term memories
engram stats                       # Memory statistics
engram decay                       # Apply forgetting
engram categories                  # List categories

engram export -o memories.json     # Export
engram import memories.json        # Import (Engram or Mem0 format)
```

---

## Configuration

```bash
# LLM & Embeddings (choose one)
export GEMINI_API_KEY="your-key"                      # Gemini (default)
export OPENAI_API_KEY="your-key"                      # OpenAI
export OLLAMA_HOST="http://localhost:11434"            # Ollama (local, no key)

# v2 features (all enabled by default)
export ENGRAM_V2_POLICY_GATEWAY="true"                # Token + scope enforcement
export ENGRAM_V2_STAGING_WRITES="true"                # Writes land in staging
export ENGRAM_V2_DUAL_RETRIEVAL="true"                # Semantic + episodic search
export ENGRAM_V2_REF_AWARE_DECAY="true"               # Preserve referenced memories
export ENGRAM_V2_TRUST_AUTOMERGE="true"               # Auto-approve for trusted agents
export ENGRAM_V2_AUTO_MERGE_TRUST_THRESHOLD="0.85"    # Trust threshold for auto-merge
```

**Python config:**

```python
from engram.configs.base import MemoryConfig, FadeMemConfig, EchoMemConfig, CategoryMemConfig

config = MemoryConfig(
    fadem=FadeMemConfig(
        enable_forgetting=True,
        sml_decay_rate=0.15,
        lml_decay_rate=0.02,
        promotion_access_threshold=3,
        forgetting_threshold=0.1,
    ),
    echo=EchoMemConfig(
        enable_echo=True,
        auto_depth=True,
        deep_multiplier=1.6,
    ),
    category=CategoryMemConfig(
        enable_categories=True,
        auto_categorize=True,
        enable_category_decay=True,
        max_category_depth=3,
    ),
)
```

---

## Multi-Agent Memory

Engram is designed for agent orchestrators. Every memory is scoped by `user_id` and optionally `agent_id`:

```python
# Research agent stores knowledge
memory.add("OAuth 2.0 with JWT tokens",
           user_id="project_123", agent_id="researcher")

# Implementation agent searches shared knowledge
results = memory.search("authentication", user_id="project_123")
# → Finds researcher's discovery

# Review agent adds findings
memory.add("Security review passed",
           user_id="project_123", agent_id="reviewer")
```

**Agent trust scoring** determines write permissions:
- High-trust agents (>0.85): proposals auto-merge
- Medium-trust: queued for daily digest review
- Low-trust: require explicit approval

---

## Research

Engram is based on:

> **FadeMem: Biologically-Inspired Forgetting for Efficient Agent Memory**
> [arXiv:2601.18642](https://arxiv.org/abs/2601.18642)

| Metric | Result |
|:-------|:-------|
| Storage Reduction | ~45% |
| Multi-hop Reasoning | +12% accuracy |
| Retrieval Precision | +8% on LTI-Bench |

Biological inspirations: Ebbinghaus Forgetting Curve → exponential decay, Spaced Repetition → access boosts strength, Sleep Consolidation → SML → LML promotion, Production Effect → echo encoding, Elaborative Encoding → deeper processing = stronger memory.

---

## Docker

```bash
# Quick start
docker compose up -d

# Or build manually
docker build -t engram .
docker run -p 8100:8100 -v engram-data:/data \
  -e GEMINI_API_KEY="your-key" engram
```

---

## Manual Integration Setup

<details>
<summary><b>Claude Code / Claude Desktop</b></summary>

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
</details>

<details>
<summary><b>Cursor</b></summary>

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
</details>

<details>
<summary><b>OpenAI Codex</b></summary>

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.engram-memory]
command = "python"
args = ["-m", "engram.mcp_server"]

[mcp_servers.engram-memory.env]
GEMINI_API_KEY = "your-api-key"
```
</details>

---

## Troubleshooting

<details>
<summary><b>Claude Code doesn't see the memory tools</b></summary>

- Restart Claude Code after running `engram install`
- Check that `~/.claude.json` has an `mcpServers.engram-memory` section
- Verify your API key: `echo $GEMINI_API_KEY`
</details>

<details>
<summary><b>The hook isn't injecting memories</b></summary>

- Check that `engram-api` is running: `curl http://127.0.0.1:8100/health`
- Verify the plugin is activated: run `/plugin` in Claude Code
- Check script permissions: `ls -l ~/.engram/claude-plugin/engram-memory/hooks/prompt_context.py`
</details>

<details>
<summary><b>API won't start (port in use)</b></summary>

- Check: `lsof -i :8100`
- Kill the process: `kill <PID>`
- Or use a different port: `ENGRAM_API_PORT=8200 engram-api`
</details>

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
  <b>Your agents forget everything between sessions. Engram fixes that.</b>
  <br><br>
  <a href="https://github.com/Ashish-dwi99/Engram">GitHub</a> &middot;
  <a href="https://github.com/Ashish-dwi99/Engram/issues">Issues</a> &middot;
  <a href="https://github.com/Ashish-dwi99/Engram/blob/main/CHANGELOG.md">Changelog</a>
</p>
