#!/usr/bin/env python3
"""Quick test script for engram - run this to verify your setup works."""

import os
import sys

# Add parent directory to path for local development
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_fadem():
    from engram import Memory
    from engram.configs.base import MemoryConfig, VectorStoreConfig, LLMConfig, EmbedderConfig, FadeMemConfig

    print("=" * 60)
    print("engram Quick Test")
    print("=" * 60)

    # Configure with in-memory vector store for quick testing
    # Uses Gemini by default - set GEMINI_API_KEY env var
    config = MemoryConfig(
        vector_store=VectorStoreConfig(
            provider="qdrant",
            config={
                "path": "/tmp/fadem_test_qdrant",
                "collection_name": "test_memories",
                "embedding_model_dims": 3072,  # gemini-embedding-001 dimension
            }
        ),
        llm=LLMConfig(
            provider="gemini",
            config={
                "model": "gemini-2.0-flash",
                "temperature": 0.1,
            }
        ),
        embedder=EmbedderConfig(
            provider="gemini",
            config={
                "model": "gemini-embedding-001",
            }
        ),
        history_db_path="/tmp/fadem_test_history.db",
        engram=FadeMemConfig(
            enable_forgetting=True,
            sml_decay_rate=0.15,
            lml_decay_rate=0.02,
        )
    )

    print("\n[1] Initializing Memory...")
    memory = Memory(config)
    print("    OK - Memory initialized")

    # Reset for clean test
    print("\n[2] Resetting memory store...")
    memory.reset()
    print("    OK - Reset complete")

    # Test add
    print("\n[3] Adding memories...")
    result = memory.add(
        messages=[
            {"role": "user", "content": "I prefer plant-based meals."},
            {"role": "assistant", "content": "Got it! I'll remember your preferences."}
        ],
        user_id="test_user_123"
    )
    print(f"    Added {len(result.get('results', []))} memories")
    for r in result.get("results", []):
        print(f"    - [{r.get('event')}] {r.get('memory')[:60]}...")

    # Add more memories
    result2 = memory.add(
        "I live in San Francisco and work as a software engineer.",
        user_id="test_user_123"
    )
    print(f"    Added {len(result2.get('results', []))} more memories")

    # Test search
    print("\n[4] Searching memories...")
    search_result = memory.search(
        "What are my food preferences?",
        user_id="test_user_123",
        limit=5
    )
    print(f"    Found {len(search_result.get('results', []))} results")
    for r in search_result.get("results", []):
        print(f"    - [score={r.get('composite_score', 0):.3f}] {r.get('memory')[:50]}...")

    # Test get_all
    print("\n[5] Getting all memories...")
    all_memories = memory.get_all(user_id="test_user_123")
    print(f"    Total memories: {len(all_memories.get('results', []))}")

    # Test stats
    print("\n[6] Getting stats...")
    stats = memory.get_stats(user_id="test_user_123")
    print(f"    Total: {stats.get('total')}")
    print(f"    SML: {stats.get('sml_count')}, LML: {stats.get('lml_count')}")
    print(f"    Avg strength: {stats.get('avg_strength'):.3f}")

    # Test decay
    print("\n[7] Testing decay...")
    decay_result = memory.apply_decay(scope={"user_id": "test_user_123"})
    print(f"    Decayed: {decay_result.get('decayed')}")
    print(f"    Forgotten: {decay_result.get('forgotten')}")
    print(f"    Promoted: {decay_result.get('promoted')}")

    print("\n" + "=" * 60)
    print("All tests passed! engram is ready to use.")
    print("=" * 60)

    return True


def test_openai_provider():
    """Test with OpenAI provider instead of Gemini."""
    from engram import Memory
    from engram.configs.base import MemoryConfig, VectorStoreConfig, LLMConfig, EmbedderConfig

    print("\n[OpenAI Provider Test]")

    config = MemoryConfig(
        vector_store=VectorStoreConfig(
            provider="qdrant",
            config={
                "path": "/tmp/fadem_test_openai",
                "collection_name": "test_openai",
                "embedding_model_dims": 1536,  # OpenAI text-embedding-3-small
            }
        ),
        llm=LLMConfig(
            provider="openai",
            config={"model": "gpt-4o-mini"}
        ),
        embedder=EmbedderConfig(
            provider="openai",
            config={"model": "text-embedding-3-small"}
        ),
        history_db_path="/tmp/fadem_test_openai.db",
    )

    memory = Memory(config)
    memory.reset()

    result = memory.add("Test memory with OpenAI", user_id="openai_test")
    print(f"    Added: {result}")

    search = memory.search("test", user_id="openai_test")
    print(f"    Search found: {len(search.get('results', []))} results")

    print("    OpenAI provider OK!")


if __name__ == "__main__":
    # Check for API key
    if not os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
        print("WARNING: GEMINI_API_KEY not set. Set it to run tests:")
        print("  export GEMINI_API_KEY='your-api-key'")
        print("")

    if not os.getenv("OPENAI_API_KEY"):
        print("NOTE: OPENAI_API_KEY not set. OpenAI tests will be skipped.")
        print("")

    try:
        test_fadem()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Optionally test OpenAI if key is available
    if os.getenv("OPENAI_API_KEY"):
        try:
            test_openai_provider()
        except Exception as e:
            print(f"\nOpenAI test error: {e}")
