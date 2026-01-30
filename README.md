<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License">
  <img src="https://img.shields.io/badge/PRs-Welcome-brightgreen?style=for-the-badge" alt="PRs Welcome">
  <img src="https://img.shields.io/badge/AI-Memory-purple?style=for-the-badge" alt="AI Memory">
</p>

<h1 align="center">
  <br>
  🧠 Engram
  <br>
</h1>

<h3 align="center">
  Biologically-Inspired Memory Layer for AI Agents
</h3>

<p align="center">
  Engram combines three powerful memory systems:<br>
  <b>FadeMem</b> brings human-like forgetting & consolidation.<br>
  <b>EchoMem</b> adds multi-modal encoding for stronger retention.<br>
  <b>CategoryMem</b> provides dynamic hierarchical organization.<br>
  Together, they create the most advanced memory system for AI agents.
</p>

<p align="center">
  <a href="#-features">Features</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-how-it-works">How It Works</a> •
  <a href="#-claude-code-integration">Claude Code</a> •
  <a href="#-api-reference">API</a>
</p>

---

## 🎯 Why Engram?

Traditional AI memory systems store everything forever. Humans don't work that way—and neither should your AI agents.

| Problem | Engram Solution |
|---------|---------------------------|
| Memory bloat over time | **Adaptive forgetting** - irrelevant memories fade naturally |
| All memories treated equal | **Dual-layer system** - important memories get promoted to long-term |
| Conflicting information | **LLM-guided conflict resolution** - newer info updates older |
| Weak retrieval on varied queries | **Multi-modal echo encoding** - multiple retrieval paths per memory |
| Shallow encoding | **Importance-based depth** - critical info gets deeper processing |

---

## ✨ Features

### 🔄 FadeMem — Decay & Consolidation

```
┌─────────────────────────────────────────────────────────┐
│                    FadeMem Layer                        │
├─────────────────────────────────────────────────────────┤
│  📥 Short-term Memory (SML)                             │
│     • Fast decay rate (0.15)                            │
│     • New memories land here                            │
│     • Frequently accessed → promoted                    │
│                    ↓                                    │
│  📦 Long-term Memory (LML)                              │
│     • Slow decay rate (0.02)                            │
│     • Important, consolidated memories                  │
│     • Persists across sessions                          │
└─────────────────────────────────────────────────────────┘
```

- **Adaptive Decay** — Memories fade based on time and access patterns
- **Dual-Layer Architecture** — SML for recent, LML for important
- **Automatic Promotion** — Frequently accessed memories get promoted
- **Conflict Resolution** — LLM detects contradictions and updates
- **Memory Fusion** — Related memories consolidate into stronger ones
- **~45% Storage Reduction** — Compared to store-everything approaches

### 🔊 EchoMem — Encoding & Retrieval

```
Input: "User prefers TypeScript over JavaScript"
                    │
                    ▼
        ┌───────────────────────┐
        │   Echo Processing     │
        │                       │
        │  Depth: MEDIUM        │
        │  (preference keyword) │
        └───────────────────────┘
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
│  strength: 1.3x (medium depth bonus)                    │
└─────────────────────────────────────────────────────────┘
```

- **Multi-Modal Encoding** — Stores paraphrase, keywords, implications, question form
- **Auto Depth Detection** — Shallow (1.0x) / Medium (1.3x) / Deep (1.6x)
- **Query-Optimized Retrieval** — Question-form embeddings match queries better
- **Echo-Based Re-ranking** — Boosts results matching keywords/implications
- **Re-Echo on Access** — Frequently accessed memories get stronger encoding

### 📊 Echo Depth Levels

| Depth | Trigger | Processing | Strength |
|-------|---------|------------|----------|
| **Shallow** | Generic info | Keywords only (no LLM) | 1.0x |
| **Medium** | Preferences, dates | + Paraphrase | 1.3x |
| **Deep** | Credentials, "important", numbers | + Implications, Q&A | 1.6x |

### 📂 CategoryMem — Dynamic Organization

```
┌─────────────────────────────────────────────────────────────────┐
│                      CategoryMem Layer                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  preferences/                 facts/                             │
│  ├── coding/                  ├── projects/                      │
│  │   ├── languages (3)        │   └── repos (5)                  │
│  │   └── tools (2)            └── knowledge (8)                  │
│  └── lifestyle (4)                                               │
│                                                                  │
│  context/                     corrections/                       │
│  └── work (6)                 └── learned_lessons (2)            │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│  • Auto-categorization on memory add                             │
│  • Hierarchical nesting (up to 3 levels)                         │
│  • Dynamic summaries per category                                │
│  • Category decay & merge (bio-inspired)                         │
│  • Category-aware search boosting                                │
└─────────────────────────────────────────────────────────────────┘
```

**Key Features:**

- **Dynamic Categories** — Auto-discovered from content, not predefined
- **Hierarchical Structure** — Nested categories (preferences > coding > languages)
- **Evolving Summaries** — LLM-generated summaries that update with new memories
- **Category Decay** — Unused categories weaken and merge 
- **Category Embeddings** — Categories have their own vectors for semantic matching
- **Category-Aware Retrieval** — Boost search results from relevant categories

---

## 💡 Why Dynamic Memory?

Most AI memory systems store everything forever. This causes problems:

```
Traditional Memory (after 6 months):
┌────────────────────────────────────────────────┐
│ 50,000 memories                                │
│ • Old preferences conflict with new            │
│ • Token costs explode                          │
│ • Retrieval precision drops                    │
│ • "Noise" dominates context                    │
└────────────────────────────────────────────────┘

Engram (after 6 months):
┌────────────────────────────────────────────────┐
│ 5,000 high-quality memories                    │
│ • Only relevant memories survive               │
│ • Important things strengthened via access     │
│ • Fast, precise retrieval                      │
│ • ~45% storage reduction                       │
└────────────────────────────────────────────────┘
```

### Engram Advantages

| Traditional | Engram |
|-------------|---------|
| Never forgets | Biologically-inspired decay |
| Single embedding | Multi-modal encoding (EchoMem) |
| Static categories | Dynamic hierarchical with decay |
| Manual summaries | Auto-evolving summaries |
| Noise accumulates | Adaptive forgetting |
| Cloud dependency | Local-first, your machine |

### Dynamic Categories

Traditional static hierarchy:
- Resource Layer → Item Layer → Category Layer (fixed)

Engram's CategoryMem is **dynamic**:
- Categories **emerge** from content (not predefined)
- Categories **decay** when unused (bio-inspired)
- Categories **merge** when too similar
- Summaries **evolve** with new memories
- Hierarchy is **flexible** (up to 3 levels)

---

## 🚀 Quick Start

### Installation

```bash
pip install engram
```

Or install from source:

```bash
git clone https://github.com/yourusername/engram.git
cd engram
pip install -e ".[gemini,qdrant]"
```

### Set Your API Key

```bash
export GEMINI_API_KEY="your-api-key"
```

### Basic Usage

```python
from engram import Memory

# Initialize with defaults (Gemini + Qdrant)
memory = Memory()

# Add memories from conversation
memory.add(
    messages=[
        {"role": "user", "content": "I'm a vegetarian and allergic to peanuts."},
        {"role": "assistant", "content": "Got it!"}
    ],
    user_id="user_123"
)

# Search memories
results = memory.search(
    "What are my dietary restrictions?",
    user_id="user_123"
)

print(results["results"][0]["memory"])
# → "User is vegetarian and allergic to peanuts"
```

### With EchoMem Enabled (Default)

```python
from engram import Memory
from engram.configs.base import MemoryConfig, EchoMemConfig

config = MemoryConfig(
    echo=EchoMemConfig(
        enable_echo=True,
        auto_depth=True,           # Auto-detect importance
        use_question_embedding=True # Better query matching
    )
)

memory = Memory(config)

# High-importance memory → DEEP echo (1.6x strength)
memory.add("My API key is sk-abc123", user_id="user_123")

# Preference → MEDIUM echo (1.3x strength)
memory.add("I prefer dark mode", user_id="user_123")

# Generic info → SHALLOW echo (1.0x strength)
memory.add("The weather is nice", user_id="user_123")
```

### With CategoryMem (New!)

```python
from engram import Memory

memory = Memory()  # CategoryMem enabled by default

# Add memories - auto-categorized!
memory.add("I prefer TypeScript over JavaScript", user_id="user_123")
memory.add("Working on the e-commerce project", user_id="user_123")
memory.add("Remember to use async/await", user_id="user_123")

# Get category tree
tree = memory.get_category_tree()
# → preferences/coding/languages, context/projects, procedures/...

# Get all category summaries
summaries = memory.get_all_summaries()
# → {"User Preferences": "User prefers TypeScript...", ...}

# Search within a category
results = memory.search_by_category("preferences")

# Apply category decay (merges weak categories)
memory.apply_category_decay()
```

---

## 🔧 Claude Code Integration

Engram works as an MCP server for Claude Code, giving Claude persistent memory across sessions.

### Setup

Add to your Claude Code config (`~/.claude.json`):

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

### Available Tools

| Tool | Description |
|------|-------------|
| `add_memory` | Store a new memory |
| `search_memory` | Find relevant memories |
| `get_all_memories` | List all stored memories |
| `get_memory` | Get a specific memory by ID |
| `update_memory` | Update memory content |
| `delete_memory` | Remove a memory |
| `get_memory_stats` | Get storage statistics |
| `apply_memory_decay` | Run decay algorithm |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Your AI Agent                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Engram                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   CategoryMem Layer                       │  │
│  │           (Dynamic Hierarchical Organization)             │  │
│  │                                                           │  │
│  │  • Auto-categorization on add                             │  │
│  │  • Hierarchical nesting (3 levels)                        │  │
│  │  • Evolving summaries per category                        │  │
│  │  • Category decay & merge                                 │  │
│  │  • Category-aware search boosting                         │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                     EchoMem Layer                         │  │
│  │         (Encoding & Retrieval Enhancement)                │  │
│  │                                                           │  │
│  │  • Multi-modal echo encoding                              │  │
│  │  • Importance-based depth selection                       │  │
│  │  • Query-optimized embeddings                             │  │
│  │  • Echo-based search re-ranking                           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                     FadeMem Layer                         │  │
│  │           (Decay & Consolidation Engine)                  │  │
│  │                                                           │  │
│  │  • Dual-layer memory (SML/LML)                            │  │
│  │  • Adaptive strength decay                                │  │
│  │  • Conflict resolution & fusion                           │  │
│  │  • Promotion/demotion logic                               │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   Embedder   │  │     LLM      │  │    Vector Store      │  │
│  │   (Gemini/   │  │  (Gemini/    │  │  (Qdrant/In-memory)  │  │
│  │   OpenAI)    │  │   OpenAI)    │  │                      │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📖 API Reference

### Memory Class

```python
from engram import Memory

memory = Memory(config=None)  # Uses defaults if no config
```

#### `add(messages, user_id, **kwargs)`

Add memories from messages or raw text.

```python
# From conversation
memory.add(
    messages=[{"role": "user", "content": "I love Python"}],
    user_id="user_123",
    categories=["preferences"],
    echo_depth="deep"  # Override auto-detection
)

# From raw text
memory.add("User's birthday is March 15", user_id="user_123")
```

#### `search(query, user_id, **kwargs)`

Search for relevant memories.

```python
results = memory.search(
    query="What programming language?",
    user_id="user_123",
    limit=10,
    min_strength=0.1,
    use_echo_rerank=True  # Use echo metadata for better ranking
)
```

#### `apply_decay(scope=None)`

Run the forgetting algorithm.

```python
result = memory.apply_decay(scope={"user_id": "user_123"})
# {"decayed": 5, "forgotten": 2, "promoted": 1}
```

#### `get_stats(user_id=None)`

Get memory statistics including echo info.

```python
stats = memory.get_stats(user_id="user_123")
# {
#   "total": 42,
#   "sml_count": 30,
#   "lml_count": 12,
#   "avg_strength": 0.73,
#   "echo_stats": {"shallow": 15, "medium": 20, "deep": 7}
# }
```

### CategoryMem Methods

#### `get_categories()`

Get all categories.

```python
categories = memory.get_categories()
# [{"id": "preferences", "name": "User Preferences", ...}, ...]
```

#### `get_category_tree()`

Get hierarchical category structure.

```python
tree = memory.get_category_tree()
# [{"id": "preferences", "name": "...", "children": [...], "depth": 0}, ...]
```

#### `get_all_summaries()`

Get summaries for all categories.

```python
summaries = memory.get_all_summaries()
# {"User Preferences": "User prefers TypeScript...", "Projects": "..."}
```

#### `get_category_summary(category_id, regenerate=False)`

Get or regenerate summary for a specific category.

```python
summary = memory.get_category_summary("preferences", regenerate=True)
```

#### `search_by_category(category_id, limit=50)`

Get memories in a specific category.

```python
results = memory.search_by_category("preferences")
# {"results": [...], "category": {...}, "total": 15}
```

#### `apply_category_decay()`

Apply decay to categories (merges weak/similar ones).

```python
result = memory.apply_category_decay()
# {"decayed": 3, "merged": 1, "deleted": 0}
```

#### `get_category_stats()`

Get category statistics.

```python
stats = memory.get_category_stats()
# {"total_categories": 12, "dynamic_categories": 7, "top_categories": [...]}
```

---

## ⚙️ Configuration

### Full Configuration Example

```python
from engram.configs.base import (
    MemoryConfig,
    VectorStoreConfig,
    LLMConfig,
    EmbedderConfig,
    FadeMemConfig,
    EchoMemConfig,
    CategoryMemConfig,
)

config = MemoryConfig(
    # Vector store
    vector_store=VectorStoreConfig(
        provider="qdrant",  # or "memory" for in-memory
        config={
            "host": "localhost",
            "port": 6333,
            "collection_name": "my_memories",
        }
    ),

    # LLM for extraction & conflict resolution
    llm=LLMConfig(
        provider="gemini",  # or "openai"
        config={
            "model": "gemini-2.0-flash",
            "temperature": 0.1,
        }
    ),

    # Embeddings
    embedder=EmbedderConfig(
        provider="gemini",
        config={"model": "gemini-embedding-001"}
    ),
    embedding_model_dims=3072,

    # FadeMem settings
    fadem=FadeMemConfig(
        enable_forgetting=True,
        sml_decay_rate=0.15,
        lml_decay_rate=0.02,
        promotion_access_threshold=3,
        forgetting_threshold=0.1,
        conflict_similarity_threshold=0.85,
    ),

    # EchoMem settings
    echo=EchoMemConfig(
        enable_echo=True,
        auto_depth=True,
        default_depth="medium",
        use_question_embedding=True,
        shallow_multiplier=1.0,
        medium_multiplier=1.3,
        deep_multiplier=1.6,
    ),

    # CategoryMem settings (NEW!)
    category=CategoryMemConfig(
        enable_categories=True,
        auto_categorize=True,
        use_llm_categorization=True,
        enable_category_decay=True,
        category_decay_rate=0.05,
        merge_weak_categories=True,
        auto_generate_summaries=True,
        category_boost_weight=0.15,
        max_category_depth=3,
    ),
)

memory = Memory(config)
```

---

## 📚 Research

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

Engram mimics human memory processes:

- **Ebbinghaus Forgetting Curve** → Exponential decay
- **Spaced Repetition** → Access boosts strength
- **Sleep Consolidation** → SML → LML promotion
- **Interference Theory** → Conflict resolution

EchoMem mimics human encoding:

- **Production Effect** → Saying/echoing improves retention
- **Elaborative Encoding** → Deeper processing = stronger memory
- **Multiple Retrieval Cues** → More paths to recall

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

```bash
# Clone the repo
git clone https://github.com/yourusername/engram.git
cd engram

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/
```

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

<p align="center">
  <b>Built with 🧠 for smarter AI agents</b>
</p>

<p align="center">
  <a href="https://github.com/yourusername/engram">GitHub</a> •
  <a href="https://github.com/yourusername/engram/issues">Issues</a> •
  <a href="https://twitter.com/yourusername">Twitter</a>
</p>
