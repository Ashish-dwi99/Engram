#!/usr/bin/env python3
from __future__ import annotations

import math
import os
import random
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from engram.configs.base import (
    CategoryMemConfig,
    EchoMemConfig,
    EmbedderConfig,
    LLMConfig,
    MemoryConfig,
    VectorStoreConfig,
)
from engram.memory.main import Memory


def _load_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    if p <= 0:
        return min(values)
    if p >= 1:
        return max(values)
    values_sorted = sorted(values)
    k = (len(values_sorted) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return values_sorted[int(k)]
    return values_sorted[f] * (c - k) + values_sorted[c] * (k - f)


def _build_config(base_dir: str, use_gemini: bool) -> MemoryConfig:
    collection = f"retention_{uuid.uuid4().hex[:8]}"
    vector_store = VectorStoreConfig(
        provider="qdrant",
        config={
            "path": os.path.join(base_dir, "qdrant"),
            "collection_name": collection,
        },
    )

    if use_gemini:
        embedder = EmbedderConfig(provider="gemini", config={"model": "gemini-embedding-001"})
        embedding_dims = 3072
    else:
        embedder = EmbedderConfig(provider="simple", config={"embedding_dims": 1536})
        embedding_dims = 1536

    llm = LLMConfig(provider="mock", config={})

    return MemoryConfig(
        history_db_path=os.path.join(base_dir, f"{collection}.db"),
        vector_store=vector_store,
        llm=llm,
        embedder=embedder,
        embedding_model_dims=embedding_dims,
        echo=EchoMemConfig(enable_echo=False),
        category=CategoryMemConfig(enable_categories=False),
    )


def _core_items() -> List[Dict[str, object]]:
    return [
        {"content": "Remember that I prefer TypeScript over JavaScript.", "categories": ["preferences", "coding"]},
        {"content": "I prefer dark themes in my code editor.", "categories": ["preferences", "tooling"]},
        {"content": "I avoid tabs and prefer two-space indentation.", "categories": ["preferences", "coding"]},
        {"content": "My long-term goal is to ship a memory-first assistant.", "categories": ["goals"]},
        {"content": "Every morning I review and respond to emails at 9am.", "categories": ["routines"]},
        {"content": "I always run tests before release.", "categories": ["procedures", "engineering"]},
        {"content": "Remember that I like mechanical keyboards.", "categories": ["preferences", "hardware"]},
        {"content": "I use Vim keybindings in code editors.", "categories": ["preferences", "tooling"]},
        {"content": "I prefer concise explanations.", "categories": ["preferences", "communication"]},
        {"content": "I dislike excessive logging by default.", "categories": ["preferences", "engineering"]},
        {"content": "I want low-latency memory retrieval in production.", "categories": ["goals", "performance"]},
        {"content": "I plan to integrate with MCP for universal memory access.", "categories": ["goals", "architecture"]},
        {"content": "I always document breaking changes.", "categories": ["procedures", "engineering"]},
        {"content": "I keep configuration in environment variables.", "categories": ["procedures", "ops"]},
        {"content": "I prefer tests to be fast and isolated.", "categories": ["preferences", "testing"]},
    ]


def _ephemeral_items() -> List[str]:
    return [
        "Schedule a meeting tomorrow at 3pm.",
        "Remind me to buy milk tonight.",
        "Book a flight next week.",
        "Call Alex later today.",
        "Send the report by this evening.",
        "Pick up groceries this afternoon.",
        "Email the client tomorrow morning.",
        "Pay the invoice next week.",
        "Follow up in 2 days.",
        "Add a TODO to refactor the auth flow.",
    ]


def _blocked_items() -> List[str]:
    return [
        "My email is test@example.com.",
        "My phone number is 555-123-4567.",
        "My address is 123 Main Street.",
        "My SSN is 111-22-3333.",
        "I have asthma.",
        "My bank account number is 123456789.",
        "I was diagnosed with ADHD.",
        "My credit card is 4111 1111 1111 1111.",
    ]


def _small_talk_items() -> List[str]:
    return [
        "Today is a busy day.",
        "I worked on the project earlier.",
        "The build seems fine.",
        "We should keep moving.",
        "That was helpful.",
        "I am thinking about new ideas.",
        "The demo went smoothly.",
        "We can revisit this later.",
        "That makes sense.",
        "I have mixed feelings about that approach.",
    ]


def _make_dataset(seed: int = 7, sessions: int = 8) -> List[Dict[str, object]]:
    random.seed(seed)
    core = _core_items()
    ephemeral = _ephemeral_items()
    blocked = _blocked_items()
    small_talk = _small_talk_items()

    items: List[Dict[str, object]] = []
    agents = ["codex", "claude"]

    for session in range(sessions):
        agent_id = agents[session % len(agents)]
        # Core items (repeat a few across sessions)
        for item in random.sample(core, k=6):
            items.append(
                {
                    "content": item["content"],
                    "categories": item["categories"],
                    "agent_id": agent_id,
                    "tag": "core",
                    "metadata": {"confidence": 0.9},
                }
            )

        # Ephemeral tasks (should be skipped unless explicit remember)
        for text in random.sample(ephemeral, k=7):
            items.append({"content": text, "agent_id": agent_id, "tag": "ephemeral"})

        # Small talk / low-confidence statements
        for text in random.sample(small_talk, k=6):
            items.append({"content": text, "agent_id": agent_id, "tag": "noise"})

        # PII / health / finance (should be blocked)
        if session % 2 == 0:
            for text in random.sample(blocked, k=2):
                items.append({"content": text, "agent_id": agent_id, "tag": "blocked"})

    return items


def _evaluate_queries(memory: Memory, queries: List[Tuple[str, str]], user_id: str, agent_id: str) -> Tuple[float, List[float]]:
    times: List[float] = []
    hits = 0
    for query, expected in queries:
        start = time.perf_counter()
        results = memory.search(query, user_id=user_id, agent_id=agent_id, limit=5)
        elapsed = (time.perf_counter() - start) * 1000.0
        times.append(elapsed)
        found = any(expected.lower() in r.get("memory", "").lower() for r in results.get("results", []))
        if found:
            hits += 1
    recall = hits / max(1, len(queries))
    return recall, times


def main() -> None:
    _load_env()
    base_dir = os.path.join("/tmp", "engram_retention")
    os.makedirs(base_dir, exist_ok=True)

    embedder_choice = os.environ.get("ENGRAM_SIM_EMBEDDER", "").strip().lower()
    if embedder_choice in {"simple", "local"}:
        use_gemini = False
    elif embedder_choice == "gemini":
        use_gemini = True
    else:
        use_gemini = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    config = _build_config(base_dir, use_gemini=use_gemini)
    memory = Memory(config)

    user_id = "u_sim"
    dataset = _make_dataset()

    stats = {"ADD": 0, "SKIP": 0, "BLOCKED": 0, "FORGET": 0, "UPDATE": 0, "NOOP": 0}
    write_times: List[float] = []
    ids_by_tag: Dict[str, List[str]] = {"core": [], "noise": []}

    for item in dataset:
        start = time.perf_counter()
        result = memory.add(
            item["content"],
            user_id=user_id,
            agent_id=item.get("agent_id"),
            categories=item.get("categories"),
            metadata=item.get("metadata"),
            infer=False,
        )
        elapsed = (time.perf_counter() - start) * 1000.0
        write_times.append(elapsed)

        entry = result.get("results", [{}])[0] if result.get("results") else {}
        event = entry.get("event", "ADD")
        stats[event] = stats.get(event, 0) + 1
        if event in {"ADD", "UPDATE"}:
            tag = item.get("tag")
            memory_id = entry.get("id")
            if tag in ids_by_tag and memory_id:
                ids_by_tag[tag].append(memory_id)

    queries = [
        ("typescript preference", "TypeScript"),
        ("dark theme editor", "dark themes"),
        ("memory-first assistant goal", "memory-first"),
        ("run tests before release", "run tests"),
        ("vim keybindings", "Vim"),
    ]

    pre_recall, pre_times = _evaluate_queries(memory, queries, user_id, agent_id="codex")

    now = datetime.utcnow()
    for mid in ids_by_tag["core"]:
        memory.db.update_memory(mid, {"last_accessed": (now - timedelta(days=5)).isoformat()})
    for mid in ids_by_tag["noise"]:
        memory.db.update_memory(mid, {"last_accessed": (now - timedelta(days=120)).isoformat()})

    decay_result = memory.apply_decay()
    post_recall, post_times = _evaluate_queries(memory, queries, user_id, agent_id="codex")

    retained_core = sum(1 for mid in ids_by_tag["core"] if memory.db.get_memory(mid))
    retained_noise = sum(1 for mid in ids_by_tag["noise"] if memory.db.get_memory(mid))

    print("Retention simulation results")
    print("-" * 32)
    print(f"Embedder: {'gemini' if use_gemini else 'simple'}")
    print(f"Total messages: {len(dataset)}")
    print(f"Stored: {stats.get('ADD', 0)} | Skipped: {stats.get('SKIP', 0)} | Blocked: {stats.get('BLOCKED', 0)}")
    print(f"Write p50: {_percentile(write_times, 0.50):.1f} ms | Write p95: {_percentile(write_times, 0.95):.1f} ms")
    print(f"Search p50 (pre-decay): {_percentile(pre_times, 0.50):.1f} ms | p95: {_percentile(pre_times, 0.95):.1f} ms")
    print(f"Search p50 (post-decay): {_percentile(post_times, 0.50):.1f} ms | p95: {_percentile(post_times, 0.95):.1f} ms")
    print(f"Core recall pre-decay: {pre_recall:.2f} | post-decay: {post_recall:.2f}")
    print(f"Core retained: {retained_core}/{len(ids_by_tag['core'])}")
    print(f"Noise retained: {retained_noise}/{len(ids_by_tag['noise'])}")
    print(f"Decay stats: {decay_result}")


if __name__ == "__main__":
    main()
