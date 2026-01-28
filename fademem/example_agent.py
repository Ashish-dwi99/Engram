#!/usr/bin/env python3
"""
Example: Using FadeMem with an AI Agent

This shows how to integrate FadeMem as a drop-in replacement for mem0
in your AI agent workflow.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fadem import Memory
from fadem.configs.base import MemoryConfig, VectorStoreConfig, LLMConfig, EmbedderConfig, FadeMemConfig


def create_memory() -> Memory:
    """Create a FadeMem instance configured for your agent."""

    config = MemoryConfig(
        vector_store=VectorStoreConfig(
            provider="qdrant",
            config={
                "path": os.path.expanduser("~/.fadem/qdrant"),
                "collection_name": "agent_memories",
                "embedding_model_dims": 768,
            }
        ),
        llm=LLMConfig(
            provider="gemini",
            config={
                "model": "gemini-1.5-flash",
                "temperature": 0.1,
            }
        ),
        embedder=EmbedderConfig(
            provider="gemini",
            config={"model": "text-embedding-004"}
        ),
        history_db_path=os.path.expanduser("~/.fadem/history.db"),
        fadem=FadeMemConfig(
            enable_forgetting=True,
            sml_decay_rate=0.15,      # Short-term memories decay faster
            lml_decay_rate=0.02,      # Long-term memories persist longer
            promotion_access_threshold=3,  # Promote after 3 accesses
            forgetting_threshold=0.1,      # Forget when strength < 0.1
        )
    )

    return Memory(config)


class SimpleAgent:
    """A simple agent that uses FadeMem for memory."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.memory = create_memory()

    def chat(self, user_message: str) -> str:
        """Process a user message and respond with context from memory."""

        # 1. Retrieve relevant memories
        relevant = self.memory.search(
            user_message,
            user_id=self.user_id,
            limit=5,
            min_strength=0.2,  # Only use memories with decent strength
        )

        memories_context = ""
        if relevant.get("results"):
            memories_context = "Relevant memories:\n"
            for mem in relevant["results"]:
                memories_context += f"- {mem['memory']} (strength: {mem['strength']:.2f})\n"

        # 2. Generate response (simplified - in real agent, call your LLM)
        response = f"[Agent received: '{user_message}']\n"
        if memories_context:
            response += f"\n{memories_context}"
        else:
            response += "\n(No relevant memories found)"

        # 3. Store the conversation as new memory
        self.memory.add(
            messages=[
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": response}
            ],
            user_id=self.user_id,
        )

        return response

    def get_user_context(self) -> str:
        """Get a summary of what we know about the user."""
        all_memories = self.memory.get_all(
            user_id=self.user_id,
            min_strength=0.3,
            limit=20
        )

        if not all_memories.get("results"):
            return "No memories stored for this user."

        context = f"User context ({len(all_memories['results'])} memories):\n"
        for mem in all_memories["results"]:
            layer_icon = "🔴" if mem.get("layer") == "sml" else "🟢"
            context += f"  {layer_icon} [{mem['strength']:.2f}] {mem['memory']}\n"

        return context

    def run_maintenance(self):
        """Run periodic maintenance - call this daily."""
        result = self.memory.apply_decay(scope={"user_id": self.user_id})
        print(f"Maintenance: decayed={result['decayed']}, "
              f"forgotten={result['forgotten']}, promoted={result['promoted']}")
        return result

    def stats(self):
        """Get memory statistics."""
        return self.memory.get_stats(user_id=self.user_id)


def main():
    print("=" * 60)
    print("FadeMem Agent Example")
    print("=" * 60)

    # Create agent for a user
    agent = SimpleAgent(user_id="demo_user")

    # Simulate conversations
    conversations = [
        "Hi! I'm Alex and I love hiking.",
        "I work as a data scientist at Google.",
        "My favorite food is sushi, especially salmon rolls.",
        "I'm planning a trip to Japan next month.",
        "Can you recommend hiking spots in Japan?",
    ]

    print("\n--- Simulating conversations ---\n")
    for msg in conversations:
        print(f"User: {msg}")
        response = agent.chat(msg)
        print(f"Agent: {response}\n")

    print("\n--- User Context Summary ---")
    print(agent.get_user_context())

    print("\n--- Memory Stats ---")
    stats = agent.stats()
    print(f"Total memories: {stats['total']}")
    print(f"Short-term (SML): {stats['sml_count']}")
    print(f"Long-term (LML): {stats['lml_count']}")
    print(f"Average strength: {stats['avg_strength']:.3f}")

    print("\n--- Running maintenance (decay) ---")
    agent.run_maintenance()

    print("\n" + "=" * 60)
    print("Done! Check ~/.fadem/ for the stored data.")
    print("=" * 60)


if __name__ == "__main__":
    main()
