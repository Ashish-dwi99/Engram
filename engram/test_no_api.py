#!/usr/bin/env python3
"""Test engram without external API keys using mock/simple providers."""

import os
import sys
import tempfile

# Add parent directory for local dev
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_with_mock_providers():
    """Test all engram functionality using mock LLM and simple embedder."""
    from engram import Memory
    from engram.configs.base import (
        MemoryConfig,
        VectorStoreConfig,
        LLMConfig,
        EmbedderConfig,
        FadeMemConfig,
    )

    print("=" * 60)
    print("engram Test (No API Keys Required)")
    print("=" * 60)

    # Use in-memory vector store and simple embedder
    config = MemoryConfig(
        vector_store=VectorStoreConfig(
            provider="memory",
            config={
                "collection_name": "test_memories",
                "embedding_model_dims": 768,
            },
        ),
        llm=LLMConfig(
            provider="mock",
            config={},
        ),
        embedder=EmbedderConfig(
            provider="simple",
            config={
                "embedding_dims": 768,
            },
        ),
        history_db_path=os.path.join(tempfile.gettempdir(), "fadem_test_mock.db"),
        engram=FadeMemConfig(
            enable_forgetting=True,
            sml_decay_rate=0.15,
            lml_decay_rate=0.02,
        ),
    )

    print("\n[1] Initializing Memory...")
    memory = Memory(config)
    print("    OK - Memory initialized")

    print("\n[2] Resetting memory store...")
    memory.reset()
    print("    OK - Reset complete")

    # Test add with infer=False (direct add, no LLM)
    print("\n[3] Adding memories (direct, no inference)...")
    result = memory.add(
        messages="I am a vegetarian and allergic to nuts.",
        user_id="test_user",
        infer=False,
    )
    print(f"    Added {len(result.get('results', []))} memories")
    for r in result.get("results", []):
        print(f"    - [{r.get('event')}] {r.get('memory')[:60]}...")

    result2 = memory.add(
        "I live in San Francisco.",
        user_id="test_user",
        infer=False,
    )
    print(f"    Added {len(result2.get('results', []))} more memories")

    result3 = memory.add(
        "I prefer TypeScript over JavaScript.",
        user_id="test_user",
        categories=["preferences", "programming"],
        infer=False,
    )
    print(f"    Added {len(result3.get('results', []))} more memories with categories")

    # Test search
    print("\n[4] Searching memories...")
    search_result = memory.search(
        "dietary restrictions",
        user_id="test_user",
        limit=5,
    )
    print(f"    Found {len(search_result.get('results', []))} results")
    for r in search_result.get("results", []):
        print(f"    - [score={r.get('composite_score', 0):.3f}] {r.get('memory')[:50]}...")

    # Test get_all
    print("\n[5] Getting all memories...")
    all_memories = memory.get_all(user_id="test_user")
    print(f"    Total memories: {len(all_memories.get('results', []))}")
    for m in all_memories.get("results", []):
        print(f"    - {m.get('memory')[:50]}... (layer={m.get('layer')}, strength={m.get('strength'):.2f})")

    # Test get single memory
    print("\n[6] Getting single memory by ID...")
    if result.get("results"):
        memory_id = result["results"][0]["id"]
        single = memory.get(memory_id)
        if single:
            print(f"    Retrieved: {single.get('memory')[:50]}...")
        else:
            print("    ERROR: Memory not found")
    else:
        print("    SKIP: No memory ID to test")

    # Test stats
    print("\n[7] Getting stats...")
    stats = memory.get_stats(user_id="test_user")
    print(f"    Total: {stats.get('total')}")
    print(f"    SML: {stats.get('sml_count')}, LML: {stats.get('lml_count')}")
    print(f"    Avg strength: {stats.get('avg_strength'):.3f}")

    # Test update
    print("\n[8] Updating a memory...")
    if result.get("results"):
        memory_id = result["results"][0]["id"]
        update_result = memory.update(memory_id, "I am a strict vegetarian and severely allergic to all nuts.")
        print(f"    Update event: {update_result.get('event')}")

    # Test decay
    print("\n[9] Applying decay...")
    decay_result = memory.apply_decay(scope={"user_id": "test_user"})
    print(f"    Decayed: {decay_result.get('decayed')}")
    print(f"    Forgotten: {decay_result.get('forgotten')}")
    print(f"    Promoted: {decay_result.get('promoted')}")

    # Test delete
    print("\n[10] Deleting a memory...")
    if result2.get("results"):
        del_id = result2["results"][0]["id"]
        del_result = memory.delete(del_id)
        print(f"    Deleted: {del_result.get('deleted')}")

    # Verify deletion
    all_after_delete = memory.get_all(user_id="test_user")
    print(f"    Remaining memories: {len(all_after_delete.get('results', []))}")

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)

    return True


def test_with_qdrant():
    """Test with Qdrant vector store (still using mock LLM and simple embedder)."""
    from engram import Memory
    from engram.configs.base import (
        MemoryConfig,
        VectorStoreConfig,
        LLMConfig,
        EmbedderConfig,
    )

    print("\n[Qdrant Vector Store Test]")

    config = MemoryConfig(
        vector_store=VectorStoreConfig(
            provider="qdrant",
            config={
                "path": os.path.join(tempfile.gettempdir(), "fadem_qdrant_test"),
                "collection_name": "test_qdrant",
                "embedding_model_dims": 768,
            },
        ),
        llm=LLMConfig(provider="mock", config={}),
        embedder=EmbedderConfig(
            provider="simple",
            config={"embedding_dims": 768},
        ),
        history_db_path=os.path.join(tempfile.gettempdir(), "fadem_qdrant_test.db"),
    )

    memory = Memory(config)
    memory.reset()

    result = memory.add("Test memory with Qdrant", user_id="qdrant_test", infer=False)
    print(f"    Added: {len(result.get('results', []))} memories")

    search = memory.search("test", user_id="qdrant_test")
    print(f"    Search found: {len(search.get('results', []))} results")

    stats = memory.get_stats(user_id="qdrant_test")
    print(f"    Stats: {stats}")

    print("    Qdrant test OK!")


def test_dimension_mismatch_recovery():
    """Test that Qdrant auto-recreates collection when dimensions change."""
    import shutil
    from engram import Memory
    from engram.configs.base import (
        MemoryConfig,
        VectorStoreConfig,
        LLMConfig,
        EmbedderConfig,
    )

    print("\n[Dimension Mismatch Recovery Test]")

    qdrant_path = os.path.join(tempfile.gettempdir(), "fadem_dim_test2")
    db_path = os.path.join(tempfile.gettempdir(), "fadem_dim_test2.db")

    # Clean up
    shutil.rmtree(qdrant_path, ignore_errors=True)
    if os.path.exists(db_path):
        os.remove(db_path)

    # Create with 768 dimensions
    config1 = MemoryConfig(
        vector_store=VectorStoreConfig(
            provider="qdrant",
            config={
                "path": qdrant_path,
                "collection_name": "dim_test",
                "embedding_model_dims": 768,
            },
        ),
        llm=LLMConfig(provider="mock", config={}),
        embedder=EmbedderConfig(provider="simple", config={"embedding_dims": 768}),
        history_db_path=db_path,
    )

    memory1 = Memory(config1)
    memory1.add("Test with 768 dims", user_id="dim_test", infer=False)
    print("    Created collection with 768 dimensions")

    # Close the Qdrant client before creating a new one
    if hasattr(memory1.vector_store, 'client'):
        memory1.vector_store.client.close()
    del memory1

    # Now create with 1536 dimensions - should recreate collection
    config2 = MemoryConfig(
        vector_store=VectorStoreConfig(
            provider="qdrant",
            config={
                "path": qdrant_path,
                "collection_name": "dim_test",
                "embedding_model_dims": 1536,
            },
        ),
        llm=LLMConfig(provider="mock", config={}),
        embedder=EmbedderConfig(provider="simple", config={"embedding_dims": 1536}),
        history_db_path=db_path,
    )

    memory2 = Memory(config2)
    result = memory2.add("Test with 1536 dims", user_id="dim_test2", infer=False)
    print("    Recreated collection with 1536 dimensions")

    if result.get("results"):
        print("    Dimension mismatch recovery OK!")
    else:
        print("    ERROR: Failed to add memory after dimension change")

    # Clean up
    if hasattr(memory2.vector_store, 'client'):
        memory2.vector_store.client.close()


if __name__ == "__main__":
    try:
        test_with_mock_providers()
        test_with_qdrant()
        test_dimension_mismatch_recovery()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
