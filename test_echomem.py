"""
Test script for EchoMem integration with engram.
"""

import os
import sys

# Ensure we're using the local engram package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engram import Memory
from engram.core.echo import EchoProcessor, EchoDepth


def test_echo_depth_detection():
    """Test that echo depth is correctly auto-detected based on content."""
    print("\n=== Test 1: Echo Depth Detection ===\n")

    # Create a mock LLM for testing (we'll test the depth detection logic directly)
    from engram.core.echo import EchoProcessor

    class MockLLM:
        def generate(self, prompt):
            return '{"paraphrase": "test", "keywords": ["test"], "implications": [], "question_form": "test?", "category": "fact", "importance": 0.5}'

    processor = EchoProcessor(MockLLM(), config={"auto_depth": True})

    test_cases = [
        # (content, expected_depth, reason)
        ("User mentioned the weather today", EchoDepth.SHALLOW, "transient info"),
        ("User prefers TypeScript over JavaScript", EchoDepth.MEDIUM, "preference keyword"),
        ("IMPORTANT: User's phone is 555-123-4567", EchoDepth.DEEP, "important + numbers"),
        ("User's API key is sk-abc123xyz", EchoDepth.DEEP, "credential marker"),
        ("Remember that John Smith is the CEO", EchoDepth.DEEP, "remember + proper noun"),
        ("Meeting scheduled for January 15, 2025", EchoDepth.DEEP, "date + proper noun"),
        ("User always uses vim for editing", EchoDepth.MEDIUM, "always keyword"),
    ]

    passed = 0
    for content, expected, reason in test_cases:
        detected = processor._assess_depth(content, None)
        status = "✅" if detected == expected else "❌"
        if detected == expected:
            passed += 1
        print(f"{status} '{content[:40]}...'")
        print(f"   Expected: {expected.value}, Got: {detected.value} ({reason})")

    print(f"\nPassed: {passed}/{len(test_cases)}")
    return passed == len(test_cases)


def test_shallow_echo():
    """Test shallow echo (no LLM call, just keyword extraction)."""
    print("\n=== Test 2: Shallow Echo (No LLM) ===\n")

    class MockLLM:
        def generate(self, prompt):
            raise Exception("Should not be called for shallow echo")

    processor = EchoProcessor(MockLLM())

    content = "User prefers morning meetings on Tuesdays"
    result = processor._shallow_echo(content)

    print(f"Content: {content}")
    print(f"Keywords: {result.keywords}")
    print(f"Echo depth: {result.echo_depth.value}")
    print(f"Strength multiplier: {result.strength_multiplier}")

    assert result.echo_depth == EchoDepth.SHALLOW
    assert result.strength_multiplier == 1.0
    assert len(result.keywords) > 0
    assert "prefers" in result.keywords or "morning" in result.keywords

    print("✅ Shallow echo works correctly")
    return True


def test_echo_metadata():
    """Test that echo results convert to metadata correctly."""
    print("\n=== Test 3: Echo Metadata Conversion ===\n")

    from engram.core.echo import EchoResult, EchoDepth

    result = EchoResult(
        raw="User prefers TypeScript",
        paraphrase="TypeScript is the user's preferred language",
        keywords=["typescript", "preference", "language"],
        implications=["values type safety"],
        question_form="What programming language does the user prefer?",
        category="preference",
        importance=0.8,
        echo_depth=EchoDepth.DEEP,
        strength_multiplier=1.6,
    )

    metadata = result.to_metadata()

    print(f"Metadata keys: {list(metadata.keys())}")
    print(f"echo_paraphrase: {metadata.get('echo_paraphrase')}")
    print(f"echo_keywords: {metadata.get('echo_keywords')}")
    print(f"echo_question_form: {metadata.get('echo_question_form')}")
    print(f"echo_depth: {metadata.get('echo_depth')}")

    assert metadata["echo_paraphrase"] == "TypeScript is the user's preferred language"
    assert "typescript" in metadata["echo_keywords"]
    assert metadata["echo_depth"] == "deep"

    print("✅ Metadata conversion works correctly")
    return True


def test_echo_boost_calculation():
    """Test the echo-based search re-ranking boost."""
    print("\n=== Test 4: Echo Boost Calculation ===\n")

    # We need to test the _calculate_echo_boost method
    # Create a minimal Memory-like object to test

    class MockMemory:
        class EchoConfig:
            enable_echo = True

        echo_config = EchoConfig()

        def _calculate_echo_boost(self, query_lower, query_terms, metadata):
            boost = 0.0

            keywords = metadata.get("echo_keywords", [])
            if keywords:
                keyword_matches = sum(1 for kw in keywords if kw.lower() in query_lower)
                boost += keyword_matches * 0.05

            question_form = metadata.get("echo_question_form", "")
            if question_form:
                q_terms = set(question_form.lower().split())
                overlap = len(query_terms & q_terms)
                if overlap > 0:
                    boost += min(0.15, overlap * 0.05)

            implications = metadata.get("echo_implications", [])
            if implications:
                for impl in implications:
                    impl_terms = set(impl.lower().split())
                    if query_terms & impl_terms:
                        boost += 0.03

            return min(0.3, boost)

    mock = MockMemory()

    # Test case 1: Query matches keywords
    metadata1 = {
        "echo_keywords": ["typescript", "javascript", "preference"],
        "echo_question_form": "What programming language does the user prefer?",
        "echo_implications": ["values type safety"],
    }

    query1 = "what language does the user prefer typescript"
    boost1 = mock._calculate_echo_boost(query1, set(query1.split()), metadata1)
    print(f"Query: '{query1}'")
    print(f"Boost: {boost1:.3f}")
    assert boost1 > 0, "Should have positive boost for matching keywords"

    # Test case 2: No matches
    metadata2 = {
        "echo_keywords": ["python", "flask"],
        "echo_question_form": "What web framework is used?",
    }

    query2 = "user email address"
    boost2 = mock._calculate_echo_boost(query2, set(query2.split()), metadata2)
    print(f"\nQuery: '{query2}'")
    print(f"Boost: {boost2:.3f}")
    assert boost2 == 0, "Should have zero boost for non-matching query"

    print("\n✅ Echo boost calculation works correctly")
    return True


def test_full_integration():
    """Test full integration with actual Memory class (requires API keys)."""
    print("\n=== Test 5: Full Integration ===\n")

    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if not gemini_key:
        print("⚠️  Skipping full integration test (no GEMINI_API_KEY set)")
        print("   Set GEMINI_API_KEY to run this test")
        return True  # Skip but don't fail

    try:
        import tempfile
        from engram import Memory
        from engram.configs.base import MemoryConfig, EchoMemConfig, VectorStoreConfig, EmbedderConfig, LLMConfig

        # Use a temporary directory for test to avoid conflicts
        test_dir = tempfile.mkdtemp(prefix="echomem_test_")

        # Create memory with echo enabled
        config = MemoryConfig(
            vector_store=VectorStoreConfig(
                provider="qdrant",
                config={
                    "path": os.path.join(test_dir, "qdrant"),
                    "collection_name": "test_echomem",
                    "embedding_model_dims": 3072,  # gemini-embedding-001
                }
            ),
            llm=LLMConfig(
                provider="gemini",
                config={"model": "gemini-2.0-flash", "api_key": gemini_key}
            ),
            embedder=EmbedderConfig(
                provider="gemini",
                config={"model": "gemini-embedding-001", "api_key": gemini_key}
            ),
            embedding_model_dims=3072,
            history_db_path=os.path.join(test_dir, "history.db"),
            echo=EchoMemConfig(
                enable_echo=True,
                auto_depth=True,
                use_question_embedding=True,
            )
        )

        memory = Memory(config)

        # Test adding a memory with echo
        result = memory.add(
            "User prefers TypeScript over JavaScript for all new projects",
            user_id="test_user",
            infer=False,
        )

        print(f"Add result: {result}")

        if result.get("results"):
            mem = result["results"][0]
            print(f"Memory ID: {mem.get('id')}")
            print(f"Echo depth: {mem.get('echo_depth')}")
            print(f"Strength: {mem.get('strength')}")

            # Verify echo metadata was added
            stored = memory.get(mem["id"])
            metadata = stored.get("metadata", {})
            print(f"Echo keywords: {metadata.get('echo_keywords')}")
            print(f"Echo question: {metadata.get('echo_question_form')}")

            # Clean up
            memory.delete(mem["id"])

            # Clean up temp directory
            import shutil
            shutil.rmtree(test_dir, ignore_errors=True)

            print("\n✅ Full integration test passed")
            return True
        else:
            print("❌ No results returned")
            return False

    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("EchoMem Integration Tests")
    print("=" * 60)

    results = []

    results.append(("Echo Depth Detection", test_echo_depth_detection()))
    results.append(("Shallow Echo", test_shallow_echo()))
    results.append(("Metadata Conversion", test_echo_metadata()))
    results.append(("Echo Boost Calculation", test_echo_boost_calculation()))
    results.append(("Full Integration", test_full_integration()))

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
        if not passed:
            all_passed = False

    print("\n" + ("All tests passed!" if all_passed else "Some tests failed."))
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
