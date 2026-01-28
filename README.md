# FadeMem — Biologically‑Inspired Memory Layer for Agents

FadeMem is a **drop‑in replacement for mem0** that adds biologically‑inspired forgetting, dual‑layer memory (SML/LML), LLM‑guided conflict resolution, and memory fusion. It is designed to be API‑compatible with mem0 while improving long‑term relevance and storage efficiency.

## Research Highlights (FadeMem paper)
- **~45% storage reduction** with adaptive forgetting and consolidation.
- **Improved multi‑hop reasoning and retrieval** on Multi‑Session Chat, LoCoMo, and LTI‑Bench.
- **Dual‑layer memory** with differential decay rates and promotion/demotion logic.

Reference: *FadeMem: Biologically‑Inspired Forgetting for Efficient Agent Memory* (arXiv:2601.18642).

## Key Features
- **mem0‑compatible API** (`Memory`, `AsyncMemory`, `MemoryClient`).
- **Adaptive decay** using access‑modulated exponential forgetting.
- **Conflict resolution** (COMPATIBLE / CONTRADICTORY / SUBSUMES / SUBSUMED).
- **Memory fusion** to consolidate redundant facts into stronger, generalized memories.
- **Strength‑weighted retrieval** (similarity × strength).

## Quickstart (Gemini + Qdrant)

### 1) Install dependencies
```bash
pip install qdrant-client google-generativeai google-genai pydantic
```

### 2) Run Qdrant (local)
```bash
docker run -p 6333:6333 qdrant/qdrant
```

### 3) Set your Gemini API key
```bash
export GEMINI_API_KEY=your_key_here
```

### 4) Use FadeMem
```python
from fadem import Memory

memory = Memory(config={
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "host": "localhost",
            "port": 6333,
            "collection_name": "fadem_memories",
            "embedding_model_dims": 768
        }
    },
    "llm": {"provider": "gemini", "config": {"model": "gemini-1.5-flash"}},
    "embedder": {"provider": "gemini", "config": {"model": "text-embedding-004"}}
})

messages = [
    {"role": "user", "content": "I’m vegetarian and allergic to peanuts."},
    {"role": "assistant", "content": "Got it!"}
]
memory.add(messages, user_id="user_123")

results = memory.search("What are my dietary restrictions?", user_id="user_123")
print(results["results"][0]["memory"])
```

## Configuration Notes
- **Embedding dims**: `text-embedding-004` returns 768 dims (default in config).
- **LLM prompts** for extraction, conflict, and fusion live in `fadem/utils/prompts.py`.
- **Decay settings** and thresholds live in `fadem/configs/base.py` under `fadem`.

## Repository Structure
```
fadem/
  memory/       # Memory + AsyncMemory + client
  core/         # decay, conflict, fusion, retrieval
  db/           # SQLite history + metadata
  vector_stores/# Qdrant + in-memory store
  embeddings/   # Gemini/OpenAI/simple embedders
  llms/         # Gemini/OpenAI/mock LLMs
  utils/        # prompts + factories + helpers
```

## Citation
```bibtex
@article{fademem2026,
  title={FadeMem: Biologically-Inspired Forgetting for Efficient Agent Memory},
  author={Wei, Lei and Dong, Xu and Peng, Xiao and Xie, Niantao and Wang, Bin},
  journal={arXiv preprint arXiv:2601.18642},
  year={2026}
}
```
