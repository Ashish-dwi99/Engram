from typing import Any, Dict

class EmbedderFactory:
    @classmethod
    def create(cls, provider: str, config: Dict[str, Any]):
        if provider == "gemini":
            from engram.embeddings.gemini import GeminiEmbedder

            return GeminiEmbedder(config)
        if provider == "simple":
            from engram.embeddings.simple import SimpleEmbedder

            return SimpleEmbedder(config)
        if provider == "openai":
            from engram.embeddings.openai import OpenAIEmbedder

            return OpenAIEmbedder(config)
        raise ValueError(f"Unsupported embedder provider: {provider}")


class LLMFactory:
    @classmethod
    def create(cls, provider: str, config: Dict[str, Any]):
        if provider == "gemini":
            from engram.llms.gemini import GeminiLLM

            return GeminiLLM(config)
        if provider == "mock":
            from engram.llms.mock import MockLLM

            return MockLLM(config)
        if provider == "openai":
            from engram.llms.openai import OpenAILLM

            return OpenAILLM(config)
        raise ValueError(f"Unsupported LLM provider: {provider}")


class VectorStoreFactory:
    @classmethod
    def create(cls, provider: str, config: Dict[str, Any]):
        if provider == "qdrant":
            from engram.vector_stores.qdrant import QdrantVectorStore

            return QdrantVectorStore(config)
        if provider == "memory":
            from engram.vector_stores.memory import InMemoryVectorStore

            return InMemoryVectorStore(config)
        raise ValueError(f"Unsupported vector store provider: {provider}")
