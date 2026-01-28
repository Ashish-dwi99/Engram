from typing import Any, Dict

class EmbedderFactory:
    @classmethod
    def create(cls, provider: str, config: Dict[str, Any]):
        if provider == "gemini":
            from fadem.embeddings.gemini import GeminiEmbedder

            return GeminiEmbedder(config)
        if provider == "simple":
            from fadem.embeddings.simple import SimpleEmbedder

            return SimpleEmbedder(config)
        if provider == "openai":
            from fadem.embeddings.openai import OpenAIEmbedder

            return OpenAIEmbedder(config)
        raise ValueError(f"Unsupported embedder provider: {provider}")


class LLMFactory:
    @classmethod
    def create(cls, provider: str, config: Dict[str, Any]):
        if provider == "gemini":
            from fadem.llms.gemini import GeminiLLM

            return GeminiLLM(config)
        if provider == "mock":
            from fadem.llms.mock import MockLLM

            return MockLLM(config)
        if provider == "openai":
            from fadem.llms.openai import OpenAILLM

            return OpenAILLM(config)
        raise ValueError(f"Unsupported LLM provider: {provider}")


class VectorStoreFactory:
    @classmethod
    def create(cls, provider: str, config: Dict[str, Any]):
        if provider == "qdrant":
            from fadem.vector_stores.qdrant import QdrantVectorStore

            return QdrantVectorStore(config)
        if provider == "memory":
            from fadem.vector_stores.memory import InMemoryVectorStore

            return InMemoryVectorStore(config)
        raise ValueError(f"Unsupported vector store provider: {provider}")
